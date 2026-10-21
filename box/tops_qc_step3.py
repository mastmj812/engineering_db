"""Tops-vs-tag QC — step 3: where wells actually land around each interface, by area (READ ONLY).

Tag-blind landing position relative to one reference surface per interface family, station-median along the
lateral (sql/64) or the midpoint tvd_ft. Per family x area: stacked histograms by tag with the neighbouring
surfaces marked, KDE landing zones with their tag mix, and the depth that best separates each adjacent tag pair
(the candidate naming rule). Evidence only — nothing here re-tags a well; the rules are for Michael + the geologist.
Writes docs/box/tops-qc-<date>/{step3.html, wells_step3.csv, summary_step3.json}.
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box import extent_package as pkg
from box import tops_qc as tq
from box import tops_qc_report as rep
from box.edge_gap_report import _CSS, _png, _table

ROOT = Path(__file__).resolve().parent.parent
MIN_FACET_N = 60
BIN_FT = 10.0
TAG_COLOURS = {"BS3_S": "#a16207", "WCXY": "#f59e0b", "WCA_1": "#2563eb", "WCA_2": "#7c3aed", "WCB_1": "#16a34a",
               "WCB_2": "#0f766e", "AVA_0": "#db2777", "AVA_1": "#f97316", "AVA_2": "#4b5563"}


@dataclass(frozen=True)
class Family:
    key: str
    title: str
    ref: str                       # reference surface: x = ft relative to it (− above)
    tags: tuple[str, ...]          # shallow -> deep naming order
    marks: tuple[str, ...]         # neighbouring surfaces drawn as lines
    window: tuple[float, float]    # x range shown / used, ft
    note: str = ""


FAMILIES = (
    Family("xy", "Bone Spring 3 / XY / Wolfcamp A — the XY squeeze", "WOLFCAMP_A", ("BS3_S", "WCXY", "WCA_1", "WCA_2"),
           ("3BSPGS", "WOLFCAMP_XY", "WOLFCAMP-B1"), (-450.0, 300.0)),
    Family("wcb", "Wolfcamp A2 / B1 / B2", "WOLFCAMP-B1", ("WCA_2", "WCB_1", "WCB_2"),
           ("WOLFCAMP_A", "WOLFCAMP-B2", "WOLFCAMP-C"), (-300.0, 500.0),
           "WOLFCAMP-C is suspect (to be relabelled / re-picked) — its line is dashed."),
    Family("ava", "Avalon — Upper / Middle / Lower", "AVALON2", ("AVA_0", "AVA_1", "AVA_2"),
           ("AVALON1", "1BSPGS"), (-650.0, 400.0),
           "No Middle Avalon surface exists; operator Middle Avalon tops sit ~110 ft above AVALON2 (geologist, 29 wells, "
           "MAD 24 ft) — drawn as the dotted line at −110."),
)
FAMILY_SURFACES = tuple(sorted({s for f in FAMILIES for s in (f.ref, *f.marks)}, key=tq.STACK.index))


def positions(conn: Any) -> pd.DataFrame:
    """Per evidence well in any family tag: rel_<surface> for every family surface (survey station median, else
    midpoint tvd_ft), plus county / tag / source. Pecos is dropped: every family's reference surface is masked there."""
    w, st = rep.pull(conn)
    s, m = rep.station_inputs(w, st)
    stack = tq.load_stack(pkg.GRID_DIR, FAMILY_SURFACES)
    sv = tq.relative_positions(s, stack, FAMILY_SURFACES)
    md = tq.relative_positions(m, stack, FAMILY_SURFACES)
    tags = {t for f in FAMILIES for t in f.tags}
    W = w[w["evidence"] & w["formation_blueox"].isin(tags) & ~w["county"].isin(tq.CAUTION_COUNTIES)].set_index("api10")
    has = W["tvd_source"].eq("survey")
    P = pd.concat([sv.reindex(W.index[has]), md.reindex(W.index[~has])]).reindex(W.index)
    return W[["formation_blueox", "county", "operator", "tvd_source", "first_production_date"]].rename(
        columns={"formation_blueox": "tag"}).join(P)


def facets(d: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    out = [("All Delaware (ex Pecos)", d)]
    for c, g in sorted(d.groupby("county"), key=lambda kv: -len(kv[1])):
        if len(g) >= MIN_FACET_N:
            out.append((str(c), g))
    return out


def mark_positions(g: pd.DataFrame, f: Family) -> dict[str, float]:
    """Median depth of each marked surface relative to the reference at these wells (− above the reference)."""
    ref = g[f"rel_{f.ref}"]
    return {s: float(np.nanmedian(ref - g[f"rel_{s}"])) for s in f.marks}


def family_frame(d: pd.DataFrame, f: Family) -> pd.DataFrame:
    g = d[d["tag"].isin(f.tags)].copy()
    g["x"] = g[f"rel_{f.ref}"]
    return g[g["x"].between(*f.window)]


def facet_tables(f: Family, d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    g0 = family_frame(d, f)
    mrows, srows, lrows = [], [], []
    for name, g in facets(g0):
        marks = mark_positions(g, f)
        for t in f.tags:
            v = g.loc[g["tag"] == t, "x"]
            lrows.append({"family": f.key, "area": name, "tag": t, "n": len(v),
                          "p25 ft": float(v.quantile(0.25)) if len(v) else np.nan,
                          "p50 ft": float(v.median()) if len(v) else np.nan,
                          "p75 ft": float(v.quantile(0.75)) if len(v) else np.nan})
        for z in tq.kde_modes(g["x"].to_numpy()):
            near = g[(g["x"] - z["pos_ft"]).abs() <= tq.MODE_WINDOW_FT]
            mix = near["tag"].value_counts(normalize=True)
            mrows.append({"family": f.key, "area": name, "zone ft (rel " + f.ref + ")": z["pos_ft"], "wells ±25 ft": z["n"],
                          "prominence": z["prominence"],
                          "tag mix": ", ".join(f"{t} {p:.0%}" for t, p in mix.items() if p >= 0.05),
                          "majority tag": mix.index[0] if len(mix) else "", "majority share": float(mix.iloc[0]) if len(mix) else np.nan})
        for up, lo in zip(f.tags, f.tags[1:], strict=False):
            uv, lv = g.loc[g["tag"] == up, "x"].to_numpy(), g.loc[g["tag"] == lo, "x"].to_numpy()
            sp = tq.best_split(uv, lv)
            inverted = len(uv) >= 3 and len(lv) >= 3 and float(np.median(uv)) >= float(np.median(lv))
            weak = not inverted and np.isfinite(sp["separation"]) and sp["separation"] < tq.MIN_SEPARATION
            if inverted or weak:  # a split depth would be meaningless: report the pair without one
                sp["split_ft"] = np.nan
            near_s = min(((s, v) for s, v in ({f.ref: 0.0} | marks).items()), key=lambda sv: abs(sv[1] - sp["split_ft"])) \
                if np.isfinite(sp["split_ft"]) else ("", np.nan)
            srows.append({"family": f.key, "area": name, "pair": f"{up} | {lo}", "split ft": sp["split_ft"],
                          "error": sp["error"], "separation": sp["separation"], "n upper": sp["n_upper"], "n lower": sp["n_lower"],
                          "nearest surface": near_s[0], "surface ft": near_s[1],
                          "split − surface (ft)": sp["split_ft"] - near_s[1] if np.isfinite(sp["split_ft"]) else np.nan,
                          "note": (f"INVERTED: {up} median {np.median(uv):.0f} ft ≥ {lo} median {np.median(lv):.0f} ft"
                                   if inverted else "no separation: the tags overlap (best split no better than lumping)" if weak else "")})
    return pd.DataFrame(mrows), pd.DataFrame(srows), pd.DataFrame(lrows)


def family_png(f: Family, d: pd.DataFrame, splits: pd.DataFrame) -> str:
    g0 = family_frame(d, f)
    fs = facets(g0)
    ncol = 3
    nrow = int(np.ceil(len(fs) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(15, 3.0 * nrow), squeeze=False, sharex=True)
    bins = np.arange(f.window[0], f.window[1] + BIN_FT, BIN_FT)
    for ax, (name, g) in zip(axes.ravel(), fs, strict=False):
        ax.hist([g.loc[g["tag"] == t, "x"] for t in f.tags], bins=bins, stacked=True,
                color=[TAG_COLOURS[t] for t in f.tags], label=list(f.tags))
        ax.axvline(0, color="#111827", lw=1.4)
        ax.text(0, ax.get_ylim()[1] * 0.97, f" {f.ref}", fontsize=7, va="top")
        for s, v in mark_positions(g, f).items():
            ls = "--" if s in tq.SUSPECT_SURFACES else "-"
            ax.axvline(v, color="#6b7280", lw=1.0, ls=ls)
            ax.text(v, ax.get_ylim()[1] * 0.85, f" {s}", fontsize=6.5, color="#374151", va="top")
        if f.key == "ava":
            ax.axvline(-110, color="#f97316", lw=1.0, ls=":")
        for _, r in splits[(splits["area"] == name)].iterrows():
            if np.isfinite(r["split ft"]):
                ax.axvline(r["split ft"], color="#dc2626", lw=0.8, ls=(0, (1, 2)))
        ax.set_title(f"{name}  (n={len(g):,})", fontsize=9)
        ax.tick_params(labelsize=7)
    for ax in axes.ravel()[len(fs):]:
        ax.axis("off")
    axes[0, 0].legend(fontsize=7, loc="upper left")
    for ax in axes[-1]:
        ax.set_xlabel(f"landing position, ft relative to {f.ref} top (− above, + below)", fontsize=8)
    fig.tight_layout()
    return _png(fig, dpi=100)


def render(parts: list[str], meta: str) -> str:
    head = [
        f"<meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'><title>Tops vs Tags · Step 3</title><style>{_CSS}</style>",
        "<h1>Tops vs tags — step 3: where wells land around each interface</h1>", meta,
        ("<p>Tag-blind landing position (lateral station median, else midpoint tvd_ft) relative to ONE reference "
         "surface per interface family, so the clusters show where development actually lands regardless of what "
         "the wells are called. Grey lines = neighbouring surfaces at the median of these wells; red dotted = the "
         "depth that best separates each adjacent tag pair. Evidence wells only, Pecos excluded (reference surfaces "
         "masked there). <b>Nothing here re-tags a well</b>: the split depths are candidate naming rules for Michael "
         "and the geologist to decide.</p>"),
    ]
    return "\n".join(head + parts)


def run(conn: Any, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    d = positions(conn)
    built = _dt.datetime.now(tz=_dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=False).stdout.strip()
    meta = (f"<div class=meta>built {built} · git {html.escape(sha)} · grids {html.escape(str(pkg.GRID_DIR))} · KDE bandwidth "
            f"{tq.KDE_BW_FT:.0f} ft · zone = ±{tq.MODE_WINDOW_FT:.0f} ft · facets with ≥ {MIN_FACET_N} wells · READ ONLY</div>")
    parts, allm, alls, alll = [], [], [], []
    for f in FAMILIES:
        modes, splits, land = facet_tables(f, d)
        allm.append(modes)
        alls.append(splits)
        alll.append(land)
        lt = land.pivot_table(index="area", columns="tag", values="p50 ft", sort=False)[list(f.tags)]
        ln = land.pivot_table(index="area", columns="tag", values="n", sort=False)[list(f.tags)]
        land_tbl = pd.DataFrame({t: [f"{v:.0f} (n {int(n)})" if np.isfinite(v) else "–" for v, n in zip(lt[t], ln[t], strict=True)]
                                 for t in f.tags}, index=lt.index).reset_index()
        sp = splits.copy()
        sp["error"] = (sp["error"] * 100).round(1)
        mo = modes.copy()
        mo["majority share"] = (mo["majority share"] * 100).round(0)
        parts += [f"<h2>{html.escape(f.title)}</h2>",
                  f"<div class=meta>x = ft relative to {f.ref}; tags {', '.join(f.tags)}. {html.escape(f.note)}</div>",
                  f"<img src='{family_png(f, d, splits)}'>",
                  f"<h3>Median landing by tag (ft relative to {f.ref}; − above)</h3>", _table(land_tbl),
                  "<h3>Candidate splits (red dotted)</h3>",
                  _table(sp.drop(columns=["family"]), {"split ft": ".0f", "surface ft": ".0f", "split − surface (ft)": ".0f", "separation": ".2f"}),
                  ("<div class=meta>split = depth minimising misplaced wells of the pair; error = % of the pair's wells on "
                  "the wrong side; split − surface &gt; 0 = operators put the boundary BELOW the gridded surface.</div>"),
                  "<details><summary>Landing zones (KDE peaks, tag-blind) and their tag mix</summary>",
                  _table(mo.drop(columns=["family"]), {f"zone ft (rel {f.ref})": ".0f", "prominence": ".2f"}), "</details>"]
    (out / "step3.html").write_text(render(parts, meta), encoding="utf-8")
    d.to_csv(out / "wells_step3.csv", index_label="api10")
    modes, splits, land = pd.concat(allm), pd.concat(alls), pd.concat(alll)
    (out / "summary_step3.json").write_text(json.dumps({
        "built": built, "git": sha, "families": [f.__dict__ for f in FAMILIES], "kde_bw_ft": tq.KDE_BW_FT,
        "splits": splits.to_dict(orient="records"), "modes": modes.to_dict(orient="records"),
        "landing": land.to_dict(orient="records")}, indent=2, default=str), encoding="utf-8")
    return {"modes": modes, "splits": splits, "landing": land, "d": d}
