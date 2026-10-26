"""BOX step 20a — allocation-well screen for a bench family (plan Phase 3 difference 6; read-only, pure).

The defect class of record is El Campeon / Los Vaqueros (docs/box/exclusions.csv, D29): one lateral booked under TWO api10s
with its production split between them, so each api10 reads low per foot. The screen looks for that signature and for
the second allocation question the Midland raises (36 % of 2023+ horizontals carry Novi `has_production_sharing`):

  * twin laterals: two producing horizontals whose sticks coincide — >= TWIN_SHARE of the shorter within TWIN_BUFFER_FT of
    the longer, |dTVD| <= TWIN_DTVD_FT — classed as
        stacked pair   different formation_blueox tags (a pad drilling two benches down one surface path);
        re-drill       one side never reached 12 months of oil, or first production > REDRILL_DAYS apart (replacement);
        twin           same tag, both producing, first production within REDRILL_DAYS = the El Campeon signature: a
                       review list for the gate, never an automatic exclusion (exclusions.csv rows are Michael's);
  * production sharing: within-location contrast (5-mi block FE + first-production-year FE, D9 cohort, family_qc.fe_with_ci)
    of 12-mo oil / kft and GOR, sharing vs not. An allocation artefact would show as a level shift.

Check of the detector (verification): run on the Delaware, it must find the recorded El Campeon / Los Vaqueros exclusions
among its twins; the recall is reported on the page.
"""

from __future__ import annotations

import html
from typing import Any

import numpy as np
import pandas as pd
import shapely

from box import bench_qc as bq
from box import family_qc as fq

TWIN_SHARE = 0.8
TWIN_BUFFER_FT = 150.0
TWIN_DTVD_FT = 150.0
REDRILL_DAYS = 180
SPLIT_OIL_RATIO = 0.5  # split signature: the low side holds < half the high side's 12-mo oil ...
SPLIT_GOR_TOL = 1.2  # ... at the same GOR (within x1.2): one stream split, not two reservoirs

PAIR_COLS = ["api10_a", "api10_b", "well_name_a", "well_name_b", "operator_a", "operator_b", "formation_blueox_a", "formation_blueox_b",
             "share", "dtvd_ft", "dfp_days", "cum_12m_oil_a", "cum_12m_oil_b", "gor12_a", "gor12_b", "sharing_a", "sharing_b", "pair_class", "split_signature"]


def twin_pairs(wells: pd.DataFrame) -> pd.DataFrame:
    """``wells`` = producing horizontals with ``geom`` (UTM 13N ft linestrings) and the bench_qc columns. One row per
    coinciding pair (api10_a < api10_b by row order), classed."""
    w = wells[wells["geom"].notna()].reset_index(drop=True)
    G = np.asarray(list(w["geom"]), dtype=object)
    L = shapely.length(G)
    i, j = shapely.STRtree(G).query(G, predicate="dwithin", distance=TWIN_BUFFER_FT)
    keep = i < j
    i, j = i[keep], j[keep]
    if len(i) == 0:
        return pd.DataFrame(columns=PAIR_COLS)
    short = np.where(L[i] <= L[j], i, j)
    long_ = np.where(L[i] <= L[j], j, i)
    share = shapely.length(shapely.intersection(G[short], shapely.buffer(G[long_], TWIN_BUFFER_FT))) / np.maximum(L[short], 1.0)
    tvd = w["tvd_ft"].to_numpy(float)
    dtvd = tvd[i] - tvd[j]
    m = (share >= TWIN_SHARE) & (np.abs(dtvd) <= TWIN_DTVD_FT)
    i, j, share, dtvd = i[m], j[m], share[m], dtvd[m]
    fp = list(w["first_production_date"])
    dfp = np.array([(fp[a] - fp[b]).days if pd.notna(fp[a]) and pd.notna(fp[b]) else np.nan for a, b in zip(i, j)], dtype=float)
    p = pd.DataFrame({
        "api10_a": w["api10"].values[i], "api10_b": w["api10"].values[j], "well_name_a": w["well_name"].values[i], "well_name_b": w["well_name"].values[j],
        "operator_a": w["operator"].values[i], "operator_b": w["operator"].values[j],
        "formation_blueox_a": w["formation_blueox"].values[i], "formation_blueox_b": w["formation_blueox"].values[j],
        "share": share, "dtvd_ft": dtvd, "dfp_days": dfp,
        "cum_12m_oil_a": w["cum_12m_oil_bbl"].values[i], "cum_12m_oil_b": w["cum_12m_oil_bbl"].values[j],
        "gor12_a": w["gor12"].values[i], "gor12_b": w["gor12"].values[j],
        "sharing_a": w["has_production_sharing"].values[i], "sharing_b": w["has_production_sharing"].values[j],
    })
    p["pair_class"] = [classify(r) for r in p.itertuples()]
    p["split_signature"] = [split_signature(r) for r in p.itertuples()]
    return p[PAIR_COLS].sort_values(["pair_class", "api10_a"]).reset_index(drop=True)


def classify(r: Any) -> str:
    if r.formation_blueox_a != r.formation_blueox_b:
        return "stacked pair"
    no12 = not (r.cum_12m_oil_a > 0) or not (r.cum_12m_oil_b > 0)
    if no12 or not (abs(r.dfp_days) <= REDRILL_DAYS):
        return "re-drill"
    return "twin"


def split_signature(r: Any) -> bool:
    """The El Campeon production split on a twin: same GOR, one side well under half the other's 12-mo oil."""
    if r.pair_class != "twin" or not (r.gor12_a > 0 and r.gor12_b > 0):
        return False
    lo, hi = sorted((r.cum_12m_oil_a, r.cum_12m_oil_b))
    return bool(lo / hi < SPLIT_OIL_RATIO and max(r.gor12_a, r.gor12_b) / min(r.gor12_a, r.gor12_b) <= SPLIT_GOR_TOL)


def recall(pairs: pd.DataFrame, excluded_ids: set[str]) -> dict[str, int]:
    """How many recorded exclusions the detector finds as `twin` (verification on the Delaware)."""
    def ids(q: pd.DataFrame) -> set[str]:
        return (set(q["api10_a"]) | set(q["api10_b"])) & excluded_ids

    return {"found": len(ids(pairs[pairs["pair_class"] == "twin"])), "found_any_pair": len(ids(pairs[pairs["pair_class"] != "stacked pair"])),
            "split_signature": len(ids(pairs[pairs["split_signature"]])), "recorded": len(excluded_ids)}


def sharing_contrast(cohort: pd.DataFrame) -> dict[str, Any]:
    """Within-location effect of `has_production_sharing` on 12-mo oil / kft and GOR (D9 cohort rows with mid_lon / mid_lat)."""
    c = cohort[cohort["mid_lon"].notna()]
    is_s = c["has_production_sharing"].fillna(False).astype(bool).to_numpy().astype(int)
    xy = bq._project_xy_ft(c["mid_lon"].to_numpy(float), c["mid_lat"].to_numpy(float))
    blk = fq._blocks(xy)
    yr = np.array([d.year for d in c["first_production_date"]])
    oil = c["oil12_kft"].to_numpy(float)
    gor = c["gor12"].to_numpy(float)
    return {
        "n_cohort": len(c), "share_sharing": float(is_s.mean()) if len(c) else np.nan,
        "oil12_kft": fq.fe_with_ci(np.log(np.where(oil > 0, oil, np.nan)), is_s, blk, yr),
        "gor12": fq.fe_with_ci(np.log(np.where(gor > 0, gor, np.nan)), is_s, blk, yr),
    }


def render_section(pairs: pd.DataFrame, family: tuple[str, ...], contrast: dict[str, Any], contrast_ref: dict[str, Any] | None,
                   check: dict[str, int] | None) -> str:
    fam = set(family)
    p = pairs[pairs["formation_blueox_a"].isin(fam) | pairs["formation_blueox_b"].isin(fam)]
    cnt = p["pair_class"].value_counts()
    tw = p[p["pair_class"] == "twin"]

    def f(v: Any, nd: int = 0) -> str:
        return "–" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:,.{nd}f}"

    rows = "".join(
        f"<tr><td>{html.escape(str(r.well_name_a))} ({r.api10_a})</td><td>{html.escape(str(r.well_name_b))} ({r.api10_b})</td><td>{html.escape(str(r.operator_a))}</td>"
        f"<td>{r.formation_blueox_a}</td><td>{r.share:.2f}</td><td>{f(r.dtvd_ft)}</td><td>{f(r.dfp_days)}</td><td>{f(r.cum_12m_oil_a)} / {f(r.cum_12m_oil_b)}</td>"
        f"<td>{f(r.gor12_a)} / {f(r.gor12_b)}</td><td>{r.sharing_a} / {r.sharing_b}</td><td>{'<b>yes</b>' if r.split_signature else 'no'}</td></tr>" for r in tw.itertuples())
    def ctr(c: dict[str, Any], k: str) -> str:
        e = c[k]
        return f"{e['ratio']:.3f} [{e['ci90'][0]:.3f}–{e['ci90'][1]:.3f}], {e['n_blocks_both']} blocks"
    ref = (f" Delaware Texas Wolfcamp, same test: oil {ctr(contrast_ref, 'oil12_kft')}; GOR {ctr(contrast_ref, 'gor12')} "
           f"(sharing share {contrast_ref['share_sharing']:.0%}).") if contrast_ref else ""
    chk = (f" <b>Detector check:</b> on the Delaware pull it puts {check['found_any_pair']} of the {check['recorded']} recorded El Campeon / Los Vaqueros "
           f"exclusions in a coinciding same-bench pair ({check['found']} as twins, {check['split_signature']} with the split signature; the rest pair with a twin whose TVD "
           "or first production differs beyond the thresholds, or one side never reached 12 months) — the screen is a review list, not a filter.") if check else ""
    return (
        "<h2 id=alloc>4c. Allocation-well screen (plan Phase 3 difference 6)</h2>"
        f"<p><b>Twin laterals</b> touching the family (≥ {TWIN_SHARE:.0%} of the shorter stick within {TWIN_BUFFER_FT:,.0f} ft of the other, |ΔTVD| ≤ {TWIN_DTVD_FT:,.0f} ft): "
        + ", ".join(f"{k} {v:,}" for k, v in cnt.items()) + ". "
        "<i>stacked pair</i> = two benches down one surface path; <i>re-drill</i> = one side never reached 12 months or first production "
        f"> {REDRILL_DAYS} d apart; <i>twin</i> = same bench, both producing, first production within {REDRILL_DAYS} d. <i>Split signature</i> (El Campeon) = a twin whose low side "
        f"holds &lt; {SPLIT_OIL_RATIO:.0%} of the high side's 12-mo oil at the same GOR (within ×{SPLIT_GOR_TOL:g}): <b>{int(tw['split_signature'].sum())}</b> in the family.{chk}</p>"
        + (f"<table><tr><th>well a</th><th>well b</th><th>operator</th><th>bench</th><th>share</th><th>ΔTVD ft</th><th>Δ first prod d</th>"
           f"<th>12-mo oil a / b, bbl</th><th>GOR a / b</th><th>sharing a / b</th><th>split signature</th></tr>{rows}</table>" if len(tw) else "<p>No twin in the family.</p>")
        + f"<p><b>Production sharing</b> (Novi <code>has_production_sharing</code>; {contrast['share_sharing']:.0%} of the family's D9 cohort, n {contrast['n_cohort']:,}): "
        f"sharing / not, same 5-mi block and first-production year — 12-mo oil per 1,000 ft {ctr(contrast, 'oil12_kft')}; 12-mo GOR {ctr(contrast, 'gor12')}.{ref}</p>"
    )
