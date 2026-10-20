"""PDP-proximity study, step 2b — haircut by configuration (class x parent count x geometry, flanking), DB-FREE.

Michael 2026-10-20: a PUD over a developed DSU is flanked by several depleted parents; the step-2 averages were diluted
by lone single-parent tests. Each child is placed by box.prox_dose.configuration (the class it has parents in, how
many, the nearest parent's band, flanked or one-sided). Haircuts are against BOX's CALIBRATED level: each child's
ln(actual / as-of box_v2) minus the mean of ALL scored children of its bench group and cutoff (the analog mix BOX
forecasts, and what the walk-forward calibration centres) — so applying one to a BOX forecast doesn't double-count
the unexposed-vs-mix gap. Precedent per cell counts every Delaware child drilled since 2016 (step-1 universe).
"""

from __future__ import annotations

import datetime as dt
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import prox_dose as pdz
from box.edge_gap_report import _CSS, _table
from box.prox_dose_report import assemble

M2B = ("oil12", "oil24", "oil36", "gor24")
WCA_POOL = ("WCA_1", "WCA_2", "WCXY")
FMT = {m: ".2f" for m in (*M2B, "oil24_lo", "oil24_hi", "oil36_lo", "oil36_hi", "oil24_vs_control")}


def _row(name: str, mask: np.ndarray, prec: int, mix: dict[str, pdz.Effects], ctrl: pdz.Effects) -> dict[str, Any]:
    r: dict[str, Any] = {"cell": name, "precedent_n": int(prec), "n_scored": int(mask.sum())}
    for m in M2B:
        c = mix[m].cell(mask)
        r[f"n_{m}"], r[m] = c["n"], c["effect"]
        if m in ("oil24", "oil36"):
            r[f"{m}_lo"], r[f"{m}_hi"] = c["lo"], c["hi"]
    r["oil24_vs_control"] = ctrl.cell(mask)["effect"]
    r["below_floor"] = r["precedent_n"] < pdz.PRECEDENT_FLOOR
    return r


def _nbin(s: pd.Series) -> np.ndarray:
    return np.array([pdz.npar_bin(int(n)) if n > 0 else "0" for n in s])


def tables(d: pd.DataFrame, allc: pd.DataFrame, W: np.ndarray) -> dict[str, pd.DataFrame]:
    mix = {m: pdz.Effects(d, m, W, ref="all") for m in M2B}
    ctrl = pdz.Effects(d, "oil24", W, ref="control")
    A = allc
    g = d["group"].to_numpy()
    cc = d["config_class"].astype(object).to_numpy()
    acc = A["config_class"].astype(object).to_numpy()
    out: dict[str, pd.DataFrame] = {}
    ref_rows = [("control (no parent within 1,000 / 2,640)", g == "control", int((A["group"] == "control").sum())),
                ("all scored children (= BOX's calibrated mix)", np.ones(len(d), bool), len(A)),
                ("exposed, outside every class envelope", (g == "exposed") & pd.isna(d["config_class"]).to_numpy(),
                 int(((A["group"] == "exposed") & A["config_class"].isna()).sum())),
                ("mixed classes (parents in 2+ classes)", cc == "mixed", int((acc == "mixed").sum()))]
    out["reference"] = pd.DataFrame([_row(n, m, p, mix, ctrl) for n, m, p in ref_rows])
    for c in pdz.ENVELOPE:
        rows = []
        nb, nb_all = _nbin(d[f"n_{c}"]), _nbin(A[f"n_{c}"])
        pure, pure_all = cc == c, acc == c
        band, band_all = d[f"band_{c}"].astype(object).to_numpy(), A[f"band_{c}"].astype(object).to_numpy()
        for k in pdz.NPAR_BINS:
            rows.append(_row(f"{c} | {k} parent(s) | all bands", pure & (nb == k), int((pure_all & (nb_all == k)).sum()), mix, ctrl))
            for b in pdz.GEOM_BANDS[c]:
                rows.append(_row(f"{c} | {k} | {b}", pure & (nb == k) & (band == b), int((pure_all & (nb_all == k) & (band_all == b)).sum()), mix, ctrl))
        fl, fl_all = d[f"flanked_{c}"].fillna(False).to_numpy(bool), A[f"flanked_{c}"].fillna(False).to_numpy(bool)
        two, two_all = pure & (d[f"n_{c}"].to_numpy() >= 2), pure_all & (A[f"n_{c}"].to_numpy() >= 2)
        rows.append(_row(f"{c} | 2+ | flanked (both sides)", two & fl, int((two_all & fl_all).sum()), mix, ctrl))
        rows.append(_row(f"{c} | 2+ | one side only", two & ~fl, int((two_all & ~fl_all).sum()), mix, ctrl))
        out[c] = pd.DataFrame(rows)
    tot, tot_all = d["n_parents_total"].to_numpy(), A["n_parents_total"].to_numpy()
    out["mixed"] = pd.DataFrame([_row(f"mixed | {k} parents total", (cc == "mixed") & s, int(((acc == "mixed") & sa).sum()), mix, ctrl)
                                 for k, s, sa in (("2", tot == 2, tot_all == 2), ("3", tot == 3, tot_all == 3), ("4+", tot >= 4, tot_all >= 4))])
    # BS3_S over the WCA pool: nearest topfill parent in WCA_1 / WCA_2 / WCXY, any configuration class (mixed included)
    bs, bs_all = d["bench"].to_numpy() == "BS3_S", A["bench"].to_numpy() == "BS3_S"
    wca, wca_all = d["pb_topfill"].isin(WCA_POOL).to_numpy(), A["pb_topfill"].isin(WCA_POOL).to_numpy()
    nt, nt_all = d["n_topfill"].to_numpy(), A["n_topfill"].to_numpy()
    flt, flt_all = d["flanked_topfill"].fillna(False).to_numpy(bool), A["flanked_topfill"].fillna(False).to_numpy(bool)
    rows = [_row(f"BS3_S over WCA | {k} topfill parent(s)", bs & wca & s, int((bs_all & wca_all & sa).sum()), mix, ctrl)
            for k, s, sa in (("1", nt == 1, nt_all == 1), ("2", nt == 2, nt_all == 2), ("3+", nt >= 3, nt_all >= 3))]
    rows.append(_row("BS3_S over WCA | 2+ flanked", bs & wca & (nt >= 2) & flt, int((bs_all & wca_all & (nt_all >= 2) & flt_all).sum()), mix, ctrl))
    out["bs3s_wca"] = pd.DataFrame(rows)
    return out


def render(T: dict[str, pd.DataFrame], meta: dict[str, Any]) -> str:
    p = [(f"<!doctype html><html><head><meta charset=utf-8><title>PDP proximity config</title><style>{_CSS} body{{overflow-x:hidden}} "
          "table{display:block;overflow-x:auto;max-width:100%}</style></head><body>"),
         "<h1>PDP-proximity study — step 2b: haircut by configuration (Delaware)</h1>",
         (f"<div class=meta>{meta['built']} · {meta['children']:,} scored children · precedent from {meta['n_all_children']:,} "
          "Delaware wells drilled since 2016 · DB-free</div>"),
         ("<p>Each child is placed by the class it has depleted parents in (≥ 12 mo, ≥ 30 % alongside, no permit / shielded) inside "
          "the class envelope — same pool 1,400 ft hz; topfill 800 ft vt / 1,400 ft hz; underfill 500 ft vt / 1,400 ft hz, where "
          "step 2's effects faded — then by parent count (1 / 2 / 3+), the nearest parent's band, and flanking (parents on both "
          "sides; one within 100 ft counts for both). <b>Haircuts are against BOX's calibrated level</b>: the child's "
          "ln(actual ÷ as-of box_v2) minus the mean of ALL scored children of its bench group and cutoff. 1.00 = BOX's forecast "
          "holds; 0.75 = the well makes 75 % of it. <i>oil24_vs_control</i> = the same cell against unexposed wells (physical "
          "effect). Brackets = 90 % 3-mi block bootstrap. <b>precedent_n</b> = Delaware wells drilled since 2016 in that "
          f"configuration; below {pdz.PRECEDENT_FLOOR} = no precedent (gate 1). Survivorship: operator-selected wells — an upper "
          "bound for undrilled PUDs.</p>"),
         "<h2>Reference rows</h2>", _table(T["reference"], FMT)]
    for k, title in (("topfill", "Topfill (parent below)"), ("same", "Same pool (horizontal)"), ("underfill", "Underfill (parent above)"),
                     ("bs3s_wca", "BS3_S over the WCA pool"), ("mixed", "Mixed-class children")):
        p += [f"<h2>{title}</h2>", _table(T[k], FMT)]
    p.append("</body></html>")
    return "\n".join(p)


def run(views_root: Path, runs: Path, out: Path, n_boot: int = pdz.N_BOOT) -> dict[str, Any]:
    d, meta = assemble(views_root, runs)
    with open(runs / "links.pkl", "rb") as f:
        links = pickle.load(f)
    with open(runs / "children.pkl", "rb") as f:
        kids = pickle.load(f)
    if "dxy_ft" not in links.columns:
        raise RuntimeError("links.pkl predates the signed offset — re-run `python -m scripts.box_prox_study atlas` first")
    ids = list(kids["api10"])
    allc = (pdz.configuration(ids, links).merge(kids[["api10", "bench"]], on="api10", how="left")
            .merge(pdz.exposure(ids, links)[["api10", "group"]], on="api10", how="left"))
    d = d.merge(allc.drop(columns=["bench", "group"]), on="api10", how="left")
    W = pdz.boot_weights(d["block"].to_numpy(), n_boot=n_boot)
    T = tables(d, allc, W)
    meta |= {"built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"), "n_boot": n_boot, "n_all_children": len(allc),
             "envelope": pdz.ENVELOPE, "beneath_ft": pdz.BENEATH_FT, "reference": "all scored children per (bench group, cutoff)"}
    out.mkdir(parents=True, exist_ok=True)
    for k, t in T.items():
        t.to_csv(out / f"config_{k}.csv", index=False)
    allc.to_csv(out / "config_children.csv.gz", index=False, compression="gzip")
    (out / "config_summary.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    (out / "config.html").write_text(render(T, meta), encoding="utf-8")
    return {"meta": meta, "tables": T}
