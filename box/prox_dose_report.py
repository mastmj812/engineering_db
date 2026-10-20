"""PDP-proximity study, step 2 — assemble children x as-of BOX forecasts x exposure, tables, page (DB-FREE).

Inputs (git-ignored runs/):
  runs/prox/links.pkl, children.pkl     step-1 pair table (scripts.box_prox_study atlas)
  runs/prox/views/{tuning,holdout}/<group>/view_*.csv.gz   the harness's per-well views — the step-11/12a input set
      (tuning = box_v2 tuning folds, holdout = the once-scored holdout folds; disjoint) copied from the worktree that
      built them, sha256-checked against their digests.txt before use.
AVA_0/1/2 and BS2_C have tuning views only (D105: no holdout run) — their holdout-block wells are absent.
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import pickle
from itertools import pairwise
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box import dev_factor as dfx
from box import prox_dose as pdz
from box.dev_factor_report import _xy
from box.edge_gap_report import _CSS, _png, _table

KEEP = ["api10", "cutoff", "first_production_date", "mid_lon", "mid_lat", "lateral_ft", "operator", "well_name",
        *[f"{p}{s}{k}" for p in ("actual_", "pred_box_v2_") for s in ("oil", "gas") for k in (12, 24, 36)]]
CUM_BINS = (0.0, 20e3, 40e3, 60e3, np.inf)
AGE_BINS = (365.0, 730.0, 1461.0, np.inf)
CLASSES = ("same", "topfill", "underfill")
PRIORITY_GROUPS = ("WCXY_WCA1",)


def verify_digests(root: Path) -> dict[str, str]:
    """sha256 of every file listed in each split's digests.txt; raises on a mismatch. Returns {split: digest-of-digests}."""
    out = {}
    for split in ("tuning", "holdout"):
        txt = (root / split / "digests.txt").read_text(encoding="utf-8")
        for line in txt.splitlines():
            if not line.strip():
                continue
            h, name = line.split(maxsplit=1)
            got = hashlib.sha256((root / split / name.lstrip("*")).read_bytes()).hexdigest()
            if got != h:
                raise RuntimeError(f"digest mismatch: {split}/{name}")
        out[split] = hashlib.sha256(txt.encode()).hexdigest()[:12]
    return out


def load_views(root: Path) -> pd.DataFrame:
    frames = []
    for split in ("tuning", "holdout"):
        for gdir in sorted(p for p in (root / split).iterdir() if p.is_dir()):
            for f in sorted(gdir.glob("view_*.csv.gz")):
                with gzip.open(f, "rt", encoding="utf-8") as fh:
                    v = pd.read_csv(fh, dtype={"api10": str}, usecols=lambda c: c in KEEP)
                v["bench_group"], v["split"] = gdir.name, split
                frames.append(v)
    v = pd.concat(frames, ignore_index=True)
    v["cutoff"] = v["cutoff"].astype(str)
    return v


def assemble(root: Path, runs: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    digests = verify_digests(root)
    v = load_views(root)
    n_rows = len(v)
    # a WCXY well is scored twice (WCA guard pool and WCXY_WCA1); its record spec is WCXY_WCA1 (D93/D97) -> that row wins
    v = v.assign(_pri=[0 if g in PRIORITY_GROUPS else 1 for g in v["bench_group"]]).sort_values("_pri", kind="stable").drop(columns="_pri")
    dup = v["api10"].duplicated(keep="first")
    v = v[~dup].reset_index(drop=True)
    with open(runs / "links.pkl", "rb") as f:
        links = pickle.load(f)
    with open(runs / "children.pkl", "rb") as f:
        kids = pickle.load(f)
    known = set(kids["api10"])
    d = v[v["api10"].isin(known)].reset_index(drop=True)
    d = d.merge(kids[["api10", "bench", "state"]], on="api10", how="left")
    d = d.merge(pdz.exposure(list(d["api10"]), links), on="api10", how="left")
    d = pd.concat([d, pdz.log_ratios(d)], axis=1)
    x, y = _xy(d["mid_lon"], d["mid_lat"])
    d["block"] = dfx.blocks(x, y)
    meta = {"view_rows": n_rows, "duplicate_api10_dropped": int(dup.sum()), "not_in_step1_children": int((~v["api10"].isin(known)).sum()),
            "children": len(d), "digests": digests, "by_group": d.groupby("bench_group").size().to_dict(),
            "by_split": d.groupby("split").size().to_dict(), "groups": d.groupby("group").size().to_dict()}
    return d, meta


def _bin(vals: pd.Series, edges: tuple[float, ...], fmt) -> pd.Series:
    return pd.cut(vals.astype(float), bins=list(edges), right=False, labels=[fmt(a, b) for a, b in pairwise(edges)])


def masks(d: pd.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    g = d["group"].to_numpy()
    exp = g == "exposed"
    cls = d["cls"].to_numpy()
    v14 = d["v14"].fillna(False).to_numpy(bool)
    dvb, dhb = d["dv_bin"].to_numpy(), d["dh_bin"].to_numpy()
    out: dict[str, dict[str, np.ndarray]] = {}
    out["headline"] = {
        "control (no parent within 1,000 / 2,640)": g == "control",
        "young parent only (6-12 mo)": g == "young",
        "permit / shielded only": g == "ambiguous",
        "exposed, all": exp,
        **{f"{c}: inside v14 (300 / 800)": exp & (cls == c) & v14 for c in CLASSES},
        **{f"{c}: exposed, outside v14": exp & (cls == c) & ~v14 for c in CLASSES},
    }
    for c in CLASSES:
        out[f"grid_{c}"] = {f"{a} vt | {b} hz": exp & (cls == c) & (dvb == a) & (dhb == b) for a in pdz.DV_BINS for b in pdz.DH_BINS}
        if c == "same":
            out[f"dh_{c}"] = {f"{b} hz": exp & (cls == c) & (dhb == b) for b in pdz.DH_BINS}
        else:
            out[f"dv_{c}"] = {f"{a} vt (hz <= 800)": exp & (cls == c) & (dvb == a) & (d["dh_ft"].to_numpy(float) <= 800) for a in pdz.DV_BINS}
            out[f"dh_{c}"] = {f"{b} hz (vt <= 300)": exp & (cls == c) & (dhb == b) & (d["dv_ft"].to_numpy(float) <= 300) for b in pdz.DH_BINS}
    st = d["state"].to_numpy()
    out["same_state"] = {f"{s} {b} hz": exp & (cls == "same") & (dhb == b) & (st == s) for s in ("NM", "TX") for b in pdz.DH_BINS}
    out["same_state"].update({f"{s} control": (g == "control") & (st == s) for s in ("NM", "TX")})
    # bench pairs inside v14 (child group x parent bench), n >= 10
    pairs = d[exp & v14].groupby(["bench_group", "parent_bench", "cls"]).size()
    out["pairs_v14"] = {f"{bg} child / {pb} parent ({c})": exp & v14 & (d["bench_group"].to_numpy() == bg) & (d["parent_bench"].to_numpy() == pb) & (cls == c)
                        for (bg, pb, c), n in pairs.items() if n >= 10}
    cumb = _bin(d["parent_cum_bbl_per_kft"], CUM_BINS, lambda a, b: f"{a / 1e3:.0f}-{b / 1e3:.0f}" if np.isfinite(b) else f">={a / 1e3:.0f}").astype(str).to_numpy()
    ageb = _bin(d["age_days"], AGE_BINS, lambda a, b: f"{a / 365.25:.0f}-{b / 365.25:.0f} yr" if np.isfinite(b) else f">={a / 365.25:.0f} yr").astype(str).to_numpy()
    out["dose_v14"] = {**{f"parent cum {b} kbbl/kft": exp & v14 & (cumb == b) for b in sorted(set(cumb[exp & v14]) - {"nan"})},
                       **{f"parent age {b}": exp & v14 & (ageb == b) for b in sorted(set(ageb[exp & v14]) - {"nan"})}}
    return out


def heat_png(t: pd.DataFrame, title: str, metric: str = "oil24") -> str:
    grid = np.full((len(pdz.DV_BINS), len(pdz.DH_BINS)), np.nan)
    ns = np.zeros_like(grid)
    for i, a in enumerate(pdz.DV_BINS):
        for j, b in enumerate(pdz.DH_BINS):
            r = t[t["cell"] == f"{a} vt | {b} hz"]
            if len(r):
                ns[i, j] = r.iloc[0][f"n_{metric}"]
                grid[i, j] = r.iloc[0][metric] if ns[i, j] >= 10 else np.nan
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    im = ax.imshow(grid, cmap="RdBu", vmin=0.6, vmax=1.4, aspect="auto")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            txt = f"{grid[i, j]:.2f}\nn={int(ns[i, j])}" if np.isfinite(grid[i, j]) else (f"n={int(ns[i, j])}" if ns[i, j] else "")
            ax.text(j, i, txt, ha="center", va="center", fontsize=7)
    ax.set_xticks(range(len(pdz.DH_BINS)), pdz.DH_BINS, fontsize=8)
    ax.set_yticks(range(len(pdz.DV_BINS)), pdz.DV_BINS, fontsize=8)
    ax.set_xlabel("horizontal gap to worst parent, ft")
    ax.set_ylabel("vertical gap, ft")
    ax.set_title(f"{title} — {metric} actual ÷ as-of BOX, vs controls (n<10 blank)", fontsize=9)
    fig.colorbar(im, ax=ax, fraction=0.03)
    fig.tight_layout()
    return _png(fig)


def line_png(tabs: dict[str, pd.DataFrame], title: str, metrics: tuple[str, ...] = ("oil12", "oil24", "oil36")) -> str:
    fig, axes = plt.subplots(1, len(tabs), figsize=(4.4 * len(tabs), 3.4), squeeze=False)
    for ax, (name, t) in zip(axes[0], tabs.items(), strict=True):
        x = np.arange(len(t))
        for k, m in enumerate(metrics):
            ok = t[f"n_{m}"] >= 10
            ax.errorbar(x[ok] + (k - 1) * 0.08, t.loc[ok, m], yerr=[t.loc[ok, m] - t.loc[ok, f"{m}_lo"], t.loc[ok, f"{m}_hi"] - t.loc[ok, m]],
                        marker="o", ms=4, capsize=2, lw=1, label=m)
        ax.axhline(1.0, color="#6b7280", lw=0.8)
        ax.set_xticks(x, [c.split(" (")[0] for c in t["cell"]], rotation=35, ha="right", fontsize=7)
        ax.set_ylim(0.4, 1.4)
        ax.set_title(name, fontsize=9)
        ax.legend(fontsize=7)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    return _png(fig)


FMT = {m: ".2f" for m in pdz.METRICS} | {f"{m}_{s}": ".2f" for m in pdz.METRICS for s in ("lo", "hi", "vs_box")}


def slim(t: pd.DataFrame, metrics: tuple[str, ...] = ("oil12", "oil24", "oil36", "gor12", "gor24")) -> pd.DataFrame:
    cols = ["cell", "n_children"]
    for m in metrics:
        cols += [f"n_{m}", m, f"{m}_lo", f"{m}_hi", f"{m}_vs_box"]
    return t[[*cols, "below_floor"]]


def render(ctx: dict[str, Any]) -> str:
    T, meta = ctx["tables"], ctx["meta"]
    p = [f"<!doctype html><html><head><meta charset=utf-8><title>PDP proximity dose</title><style>{_CSS}</style></head><body>",
         "<h1>PDP-proximity study — step 2: dose-response vs the as-of BOX forecast (Delaware)</h1>",
         (f"<div class=meta>{meta['built']} · {meta['children']:,} scored children (folds Dec 2019-2024, FP Dec 2019 - Nov 2025) · "
          f"view digests {meta['digests']} · DB-free</div>"),
         ("<p>Each cell is the typical child's actual ÷ the <b>box_v2 raw</b> forecast made at its fold cutoff, normalised by the "
          "no-parent controls of the same bench group and cutoff (so BOX's own bench / vintage bias cancels). "
          "1.00 = produces like an unexposed well relative to BOX; 0.80 = a 20 % haircut BOX does not know about. "
          "Brackets = 90 % 3-mi block-bootstrap interval. <i>_vs_box</i> = the same cell against BOX as-is (no control normalisation). GOR cells: actual GOR ÷ forecast GOR, same normalisation. "
          "Exposure = the child's worst depleting parent (≥ 12 mo, ≥ 30 % alongside, permit TVD / shielded excluded), as at gate 1. "
          f"<b>Survivorship:</b> these are the infills operators chose to drill — an upper bound for undrilled PUDs. "
          f"Cells under the gate-1 precedent floor ({pdz.PRECEDENT_FLOOR} children) are flagged.</p>"),
         "<h2>Headline</h2>", _table(slim(T["headline"]), FMT),
         "<h2>Grids — oil cum-24</h2>"]
    for c in CLASSES:
        p.append(f"<img src='{heat_png(T[f'grid_{c}'], c)}'>")
    p.append(f"<img src='{line_png({'topfill dv (hz<=800)': T['dv_topfill'], 'underfill dv (hz<=800)': T['dv_underfill'], 'same dh': T['dh_same']}, 'Marginals')}'>")
    p.append(f"<img src='{line_png({'topfill dh (vt<=300)': T['dh_topfill'], 'underfill dh (vt<=300)': T['dh_underfill']}, 'Horizontal marginals for the vertical classes')}'>")
    for name, title in (("dv_topfill", "Topfill by vertical gap (hz ≤ 800)"), ("dh_topfill", "Topfill by horizontal gap (vt ≤ 300)"),
                        ("dv_underfill", "Underfill by vertical gap (hz ≤ 800)"), ("dh_underfill", "Underfill by horizontal gap (vt ≤ 300)"),
                        ("dh_same", "Same pool by horizontal gap"), ("same_state", "Same pool by state"),
                        ("pairs_v14", "Bench pairs inside v14 (n ≥ 10)"), ("dose_v14", "Inside v14: parent depletion and age")):
        p += [f"<h2>{title}</h2>", _table(slim(T[name]), FMT)]
    p += ["<h2>Full grids (all metrics) are in the CSVs</h2>", "</body></html>"]
    return "\n".join(p)


def run(views_root: Path, runs: Path, out: Path, n_boot: int = pdz.N_BOOT) -> dict[str, Any]:
    d, meta = assemble(views_root, runs)
    W = pdz.boot_weights(d["block"].to_numpy(), n_boot=n_boot)
    eff = {m: pdz.Effects(d, m, W) for m in pdz.METRICS}
    M = masks(d)
    T = {k: pdz.table(d, eff, v) for k, v in M.items()}
    meta |= {"built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"), "n_boot": n_boot, "seed": pdz.SEED,
             "min_ctrl": pdz.MIN_CTRL, "precedent_floor": pdz.PRECEDENT_FLOOR}
    out.mkdir(parents=True, exist_ok=True)
    for k, t in T.items():
        t.to_csv(out / f"dose_{k}.csv", index=False)
    keep = ["api10", "well_name", "operator", "bench_group", "split", "cutoff", "first_production_date", "state", "group", "cls", "parent", "parent_bench",
            "dv_ft", "dh_ft", "dz_ft", "overlap", "age_days", "parent_cum_bbl_per_kft", "v14", *[f"l_{m}" for m in pdz.METRICS]]
    d[keep].to_csv(out / "dose_children.csv.gz", index=False, compression="gzip")
    (out / "dose_summary.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    (out / "dose.html").write_text(render({"tables": T, "meta": meta}), encoding="utf-8")
    return {"meta": meta, "tables": T, "d": d}
