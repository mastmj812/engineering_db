"""BOX step 16b — the PRE-REGISTERED selection variants, metrics and adoption rule (D118 / D119; docs/box/step16b-2026-10-22/
PREREGISTRATION.md). Frozen at gate 16b by commit SHA; nothing here changes after a score is seen (a change needs Michael and a
later commit that says why).

Variants (all on the D53 harness's analog fold, scored beside the record's `box_v2`, each with its own F(k) as the harness
calibrates every variant):
  box_v2s         box_v2 rules on a pool with MEASURED spacing for every well (D119: the spacing fix, every bench)
  box_v2s_lat     + lateral relaxed before the radius grows (attribution: the lateral rule alone)
  box_v2s_lo      + level-only short-history wells (attribution: D118's middle path alone)
  box_v2s_r1      + the ranked ladder: at each ring relax count, then spacing, then lateral before the radius grows
                    (the candidate priority order same bench > distance > lateral > spacing > count — Michael ranks at gate 16b)
  box_v2s_r1lo    box_v2s_r1 + level-only short-history wells
and `box_v2s_wf` for the groups whose record carries a walk-forward haircut (WCA, BS2_S).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import analog as an

MEASURED = "pool2_measured"  # the predict_many_v2 state key of the measured-spacing pool
VARIANTS: dict[str, tuple[str, an.Rules]] = {
    "box_v2s": (MEASURED, an.Rules()),
    "box_v2s_lat": (MEASURED, an.Rules(relax=("lateral",))),
    "box_v2s_lo": (MEASURED, an.Rules(level_only=True)),
    "box_v2s_r1": (MEASURED, an.Rules(relax=("count", "spacing", "lateral"))),
    "box_v2s_r1lo": (MEASURED, an.Rules(relax=("count", "spacing", "lateral"), level_only=True)),
}
BASE = "box_v2s"
CANDIDATES: tuple[str, ...] = ("box_v2s_r1", "box_v2s_r1lo")  # adoption candidates for the provisional groups
ATTRIBUTION: tuple[str, ...] = ("box_v2s_lat", "box_v2s_lo")  # reported, never adopted

# local evidence (= box.cohort_review's definition, applied to a scored well at its cutoff)
NEAR_MI = 3.0
FAR_MI = 15.0
LOCAL_MIN_MONTHS = 12
LOCAL_MIN_WELLS = 3
LOCAL_FP_FLOOR = dt.date(2016, 1, 1)
MI = 5280.0

# adoption rule (PREREGISTRATION §5)
MEDIAN_ABS_SLACK = 0.01  # a candidate's median |pooled package bias| may exceed the base's by at most 1 point
OFF_LOCAL = 0.25  # production: a far-with-local PUD is "off local" when its cohort year-1 is > 25 % from its local wells'
HINDCAST_TOL = 0.15  # level-only: the 3-5-month next-12-month oil hindcast must be within +/-15 %


def measured_pool(pool2: Mapping[str, Any], spacing_ft: Mapping[str, float]) -> dict[str, Any]:
    """pool2 with every well's curated.wells_enriched.lateral_closer_xy_ft (NULL stays NaN = standalone, as deal-intake)."""
    return {**pool2, "spacing": np.array([float(spacing_ft.get(str(a), np.nan)) for a in pool2["api10"]], dtype=float)}


def local_evidence(pool: Mapping[str, Any], tree: Any, x: float, y: float) -> tuple[int, float]:
    """(n, mean year-1 oil per 1,000 ft) of the pool wells within NEAR_MI with >= LOCAL_MIN_MONTHS months and first production
    on/after LOCAL_FP_FLOOR — whatever their lateral or spacing. The pool is the fold's pre-cutoff pool, so a tuning well sees
    only wells that existed at its cutoff."""
    idx = tree.query_ball_point([x, y], r=NEAR_MI * MI)
    v = [float(pool["oil12_kft"][i]) for i in idx
         if pool["months"][i] >= LOCAL_MIN_MONTHS and pool["fp"][i] is not None and pool["fp"][i] >= LOCAL_FP_FLOOR
         and np.isfinite(pool["oil12_kft"][i]) and pool["oil12_kft"][i] > 0]
    return len(v), (float(np.mean(v)) if v else float("nan"))


def far_with_local(radius_mi: pd.Series, n_local: pd.Series) -> pd.Series:
    return (pd.to_numeric(radius_mi, errors="coerce") >= FAR_MI) & (pd.to_numeric(n_local, errors="coerce") >= LOCAL_MIN_WELLS)


def stratum_mask(view: pd.DataFrame) -> pd.Series:
    """The far-with-local stratum of a scored view: ONE fixed set, defined by the BASE selection, every variant scored on it."""
    return far_with_local(view[f"{BASE}_radius_mi"], view["n_local"])


def stratum_bias(view: pd.DataFrame, variant: str, stream: str, k: int, mask: pd.Series) -> tuple[float, int]:
    """Well-level Σ actual / Σ predicted − 1 over the masked scored wells (a diagnostic stratum, too thin for package cells)."""
    a, p = view.loc[mask, f"actual_{stream}{k}"].astype(float), view.loc[mask, f"pred_{variant}_{stream}{k}"].astype(float)
    ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
    return (float(a[ok].sum() / p[ok].sum() - 1.0) if ok.any() else float("nan")), int(ok.sum())


def abs_error_stats(pkg_err: Sequence[float]) -> dict[str, float]:
    """Dispersion next to the Σ / Σ bias: median |package error| and the share of packages more than 25 % off."""
    e = np.asarray(pkg_err, float)
    e = e[np.isfinite(e)]
    if not len(e):
        return {"median_abs": float("nan"), "share_gt25": float("nan")}
    return {"median_abs": float(np.median(np.abs(e))), "share_gt25": float(np.mean(np.abs(e) > 0.25))}


def adopt(cells: pd.DataFrame, stratum: pd.DataFrame, off_local: pd.DataFrame, hindcast_bias: float | None) -> dict[str, Any]:
    """PREREGISTRATION §5, one variant for EVERY provisional group (no per-group choice after the look).

    cells     pooled tuning cells, every provisional group: variant, group, stream, horizon, verdict, pkg_bias
    stratum   far-with-local oil cum-12 well-level bias, pooled over the provisional groups: variant, bias
    off_local production far-with-local PUDs: variant, share_off (share > OFF_LOCAL from local)
    hindcast_bias  the level-only 3-5-month hindcast bias (next-12-month oil), None when not run

    A candidate passes when (1) it fails no more judged cells than the base, (2) its median |pkg bias| over judged cells is
    <= the base's + MEDIAN_ABS_SLACK, (3) its far-with-local |bias| <= the base's, (4) its off-local share <= the base's, and
    (5) a level-only candidate also has |hindcast bias| <= HINDCAST_TOL. Among passing candidates the lower median |bias| wins;
    a tie goes to the one without level-only. No candidate passing = the base (box_v2s) is the provisional record."""
    def judged(v: str) -> pd.DataFrame:
        c = cells[(cells["variant"] == v) & cells["verdict"].isin(["PASS", "FAIL"])]
        return c

    def score(v: str) -> dict[str, float]:
        j = judged(v)
        s = stratum.loc[stratum["variant"] == v, "bias"]
        o = off_local.loc[off_local["variant"] == v, "share_off"]
        return {"n_fail": int((j["verdict"] == "FAIL").sum()), "median_abs": float(j["pkg_bias"].abs().median()) if len(j) else float("nan"),
                "stratum_abs": float(abs(s.iloc[0])) if len(s) else float("nan"), "off_local": float(o.iloc[0]) if len(o) else float("nan")}

    base = score(BASE)
    out: dict[str, Any] = {"base": BASE, "scores": {BASE: base}, "checks": {}}
    passing = []
    for v in CANDIDATES:
        sc = score(v)
        out["scores"][v] = sc
        chk = {"cells": sc["n_fail"] <= base["n_fail"],
               "median_abs": sc["median_abs"] <= base["median_abs"] + MEDIAN_ABS_SLACK,
               "stratum": sc["stratum_abs"] <= base["stratum_abs"],
               "off_local": sc["off_local"] <= base["off_local"]}
        if VARIANTS[v][1].level_only:
            chk["hindcast"] = hindcast_bias is not None and abs(hindcast_bias) <= HINDCAST_TOL
        out["checks"][v] = chk
        if all(chk.values()):
            passing.append(v)
    passing.sort(key=lambda v: (out["scores"][v]["median_abs"], VARIANTS[v][1].level_only))
    out["adopted"] = passing[0] if passing else BASE
    return out
