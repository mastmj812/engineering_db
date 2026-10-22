"""BOX cohort-selection review (2026-10-22, Michael: off-trend BS1_S EUR/ft in erebor). READ ONLY — diagnoses the record selection, changes nothing.

Per covered PUD of a record build: what the frozen box_v2 selection (`box.analog.select_cohort_v2`) reached, against the LOCAL
evidence it did not use. Local evidence = the group's analog-pool wells within NEAR_MI of the PUD with >= LOCAL_MIN_MONTHS calendar
months at the cutoff and first production on/after the selection's vintage floor (2016), whatever their lateral or spacing.
Each near pool well is classified against the PUD's own rules
(`dealintake.select_wells.classify` with the box_v2 lateral band) so the binding rule is named. A PUD is in the "far with local
control" class (the Pad 1925 case) when its record radius reached >= FAR_MI although >= LOCAL_MIN_WELLS local wells exist.

Year-1 oil per 1,000 ft is the pool's `oil12_kft` (Novi cum-12 pass-through over the reported lateral) for both the record
cohort and the local wells, so the gap compares like with like (the forecast's own month 1-12 is not used: the P50 curve runs
~+15 % above its own cohort's actual cum-12 on BS1_S, a separate item).

Spacing artifact (found 2026-10-22): the production build and the D53 harness fill the pool's `spacing` only for the F(k)
training cohort (+ the harness's scored wells) — every other pool well is NaN, which `classify` reads as standalone and excludes
(every well with < 13 months, every lateral > 13,000 ft). `pud_row(..., pool_fix=...)` re-runs the record selection
(`select_cohort_v2`, unchanged) on the same pool with `curated.wells_enriched.lateral_closer_xy_ft` for every well, so the
review shows what the measured spacing alone would change. Selection only — no curve is refit here.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import analog as an
from dealintake import select_wells as sw

NEAR_MI = 3.0
FAR_MI = 15.0
LOCAL_MIN_MONTHS = 12
LOCAL_MIN_WELLS = 3
MI = 5280.0
REASONS: tuple[str, ...] = ("lateral", "spacing_standalone", "spacing_tight", "months", "first_prod", "other")
# rule sets whose lifting would make an excluded near well eligible (every one of its reasons is in the set)
RESCUE: dict[str, frozenset[str]] = {
    "lateral": frozenset({"lateral"}),
    "spacing": frozenset({"spacing_standalone", "spacing_tight"}),
    "lateral_spacing": frozenset({"lateral", "spacing_standalone", "spacing_tight"}),
    "months": frozenset({"months"}),
}


def reason_set(exclusion: str | None) -> frozenset[str]:
    """`classify`'s exclusion string -> the rule families it names (empty = eligible)."""
    if not exclusion:
        return frozenset()
    out = set()
    for r in exclusion.split(";"):
        if r.startswith("lateral_outside"):
            out.add("lateral")
        elif r == "spacing_standalone":
            out.add("spacing_standalone")
        elif r == "spacing_tight":
            out.add("spacing_tight")
        elif r.startswith("months<"):
            out.add("months")
        elif r.startswith("first_prod<"):
            out.add("first_prod")
        else:
            out.add("other")
    return frozenset(out)


def bucket(reasons: frozenset[str]) -> str:
    """'eligible', the single rule that excluded the well, or 'multiple'."""
    if not reasons:
        return "eligible"
    return next(iter(reasons)) if len(reasons) == 1 else "multiple"


def lateral_band(lateral_ft: float) -> tuple[float, float] | None:
    """The band box_v2 applies (select_cohort_v2): short completed laterals draw SHORT_BAND_FT; else None = classify's
    per-basin tolerance (+/-25 % Delaware; +/-40 % at >= 12,500 ft)."""
    return an.SHORT_BAND_FT if float(lateral_ft) < an.SHORT_LAT_FT else None


def planned_spacing(loc: Mapping[str, Any]) -> float:
    sp = loc.get("spacing_ft")
    return float(sp) if sp is not None and np.isfinite(sp) and 0 < sp < 2800 else an.DEFAULT_SPACING_FT


def _mean_known(ids: Sequence[int], k12: np.ndarray) -> tuple[float, int]:
    v = [float(k12[i]) for i in ids if np.isfinite(k12[i]) and k12[i] > 0]
    return (float(np.mean(v)), len(v)) if v else (float("nan"), 0)


def pud_row(loc: Mapping[str, Any], res: Mapping[str, Any], pool: Mapping[str, Any], tree: Any, cfg: Any, bench: str,
            pool_fix: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """One covered PUD: record selection vs the near pool wells (binding rule per well) and the year-1 gap; with `pool_fix`
    (the pool with measured spacing), the record selection re-run on it, and a reproduction check of the record itself."""
    lat = float(loc["lateral_eff"])
    lo = {**loc, "lateral_ft": lat}
    idx = [int(i) for i in tree.query_ball_point([loc["x"], loc["y"]], r=NEAR_MI * MI)]
    cands = an._candidates(pool, idx, lo)
    el, ex, _ = sw.classify(cands, cfg, bench=bench, planned_stack=[bench], planned_lateral_ft=lat, basin="delaware",
                            planned_spacing_ft=planned_spacing(loc), lateral_band_ft=lateral_band(lat))
    months = {int(c["_i"]): float(pool["months"][c["_i"]]) for c in cands}
    counts = {f"near_{k}": 0 for k in ("eligible", *REASONS, "multiple")}
    counts |= {f"near_any_{k}": 0 for k in REASONS} | {f"rescue_{k}": 0 for k in RESCUE}
    for c in el + ex:
        rs = reason_set(c.get("exclusion"))
        counts[f"near_{bucket(rs)}"] += 1
        for k in rs:
            counts[f"near_any_{k}"] += 1
        for k, lifted in RESCUE.items():
            counts[f"rescue_{k}"] += bool(rs) and rs <= lifted
    floor = cfg["type_curve"]["first_prod_after"]
    floor = floor if isinstance(floor, dt.date) else dt.date.fromisoformat(str(floor))
    local = [i for i in idx if months.get(i, 0.0) >= LOCAL_MIN_MONTHS and pool["fp"][i] is not None and pool["fp"][i] >= floor]
    an_ids = [a["api10"] for a in (res.get("analogs") or [])]
    ai = {a: i for i, a in enumerate(pool["api10"])}
    an_ix = [ai[a] for a in an_ids if a in ai]
    d = [float(np.hypot(pool["x"][i] - loc["x"], pool["y"][i] - loc["y"]) / MI) for i in an_ix]
    own, n_own = _mean_known(an_ix, pool["oil12_kft"])
    loc_y1, n_loc = _mean_known(local, pool["oil12_kft"])
    r = float(res["radius_mi"])
    fix: dict[str, Any] = {}
    if pool_fix is not None:
        rep, r_rep, _, _ = an.select_cohort_v2(pool, tree, cfg, lo, bench=bench)
        fi, r_fix, _, mode_fix = an.select_cohort_v2(pool_fix, tree, cfg, lo, bench=bench)
        own_fix, n_own_fix = _mean_known(fi, pool["oil12_kft"])
        df = [float(np.hypot(pool["x"][i] - loc["x"], pool["y"][i] - loc["y"]) / MI) for i in fi]
        fix = {"repro_ok": bool(r_rep == r and sorted(pool["api10"][i] for i in rep) == sorted(an_ids)),
               "fix_radius_mi": float(r_fix), "fix_mode": mode_fix, "fix_n": len(fi), "fix_dist_med_mi": float(np.median(df)) if df else np.nan,
               "fix_overlap": len({pool["api10"][i] for i in fi} & set(an_ids)), "fix_cohort_y1_kft": own_fix,
               "fix_gap_vs_local": own_fix / loc_y1 - 1 if n_loc >= LOCAL_MIN_WELLS and n_own_fix >= 3 else np.nan}
    return {"stick_id": int(loc["stick_id"]), "lateral_ft": float(loc["lateral_ft"]), "lateral_eff": lat, "radius_mi": r,
            "search_mode": res.get("search_mode"), "n_analogs": len(an_ids), "n_analogs_in_pool": len(an_ix), "analog_dist_med_mi": float(np.median(d)) if d else np.nan,
            "near_pool": len(cands), **counts, "n_local": n_loc, "local_y1_kft": loc_y1,
            "cohort_y1_kft": own, "n_cohort_y1": n_own,
            "far_with_local": bool(r >= FAR_MI and n_loc >= LOCAL_MIN_WELLS),
            "gap_cohort_vs_local": own / loc_y1 - 1 if n_loc >= LOCAL_MIN_WELLS and n_own >= 3 else np.nan, **fix}


def lateral_class_mi(lateral_ft: pd.Series) -> pd.Series:
    """Novi stick laterals are quantized (5,080 / 7,720 / 10,360 / 13,000 / 15,640 ft) -> 1.0 / 1.5 / 2.0 / 2.5 / 3.0 mi."""
    return (pd.to_numeric(lateral_ft, errors="coerce") / MI * 2).round() / 2


def summarize(d: pd.DataFrame) -> pd.DataFrame:
    """Per group: closure, the far-with-local-control class, its year-1 gap, and the rule that excluded its near wells."""
    rows = []
    for g, x in d.groupby("group", sort=False):
        far = x[x["far_with_local"]]
        excl = far[[f"near_{k}" for k in (*REASONS, "multiple")]].to_numpy().sum()  # excluded near wells of the class
        share = {f"fails_{k}": (100 * far[f"near_any_{k}"].sum() / excl if excl else np.nan) for k in REASONS[:5]}
        share |= {f"rescued_by_{k}": (100 * far[f"rescue_{k}"].sum() / excl if excl else np.nan) for k in RESCUE}
        gap = far["gap_cohort_vs_local"].dropna()
        if "fix_radius_mi" in x:
            fg = far["fix_gap_vs_local"].dropna()
            share |= {"repro_ok_pct": 100 * x["repro_ok"].mean(), "fix_pct_5mi": 100 * (x["fix_radius_mi"] <= 5).mean(),
                      "fix_pct_15plus": 100 * (x["fix_radius_mi"] >= FAR_MI).mean(),
                      "fix_pct_cohort_changed": 100 * (x["fix_overlap"] < x["n_analogs"]).mean(),
                      "fix_dist_med_mi": x["fix_dist_med_mi"].median(), "dist_med_mi": x["analog_dist_med_mi"].median(),
                      "far_fix_gap_med_pct": 100 * fg.median() if len(fg) else np.nan}
        rows.append({"group": g, "tier": x["tier"].iloc[0], "covered": len(x), "pct_5mi": 100 * (x["radius_mi"] <= 5).mean(),
                     "pct_15plus": 100 * (x["radius_mi"] >= FAR_MI).mean(), "far_with_local": len(far),
                     "pct_far_with_local": 100 * len(far) / len(x) if len(x) else np.nan, "near_excluded": int(excl),
                     "gap_med_pct": 100 * gap.median() if len(gap) else np.nan,
                     "gap_p10_pct": 100 * gap.quantile(0.1) if len(gap) else np.nan,
                     "gap_p90_pct": 100 * gap.quantile(0.9) if len(gap) else np.nan, **share})
    return pd.DataFrame(rows)


def closure_by_lateral(d: pd.DataFrame) -> pd.DataFrame:
    """Share of covered PUDs closing inside the 5-mi ring, per group x lateral class (the 1.5-mi band gap)."""
    x = d.assign(lat_mi=lateral_class_mi(d["lateral_ft"]))
    t = x.groupby(["group", "lat_mi"]).agg(n=("stick_id", "size"), pct_5mi=("radius_mi", lambda r: 100 * (r <= 5).mean()),
                                            pct_far_with_local=("far_with_local", lambda f: 100 * f.mean())).reset_index()
    return t[t["n"] >= 30]
