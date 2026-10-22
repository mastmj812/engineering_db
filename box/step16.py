"""BOX step 16b — the PRE-REGISTERED selection variants, metrics and adoption rule (D118 / D119; docs/box/step16b-2026-10-22/
PREREGISTRATION.md). Frozen at gate 16b by commit SHA; nothing here changes after a score is seen (a change needs Michael and a
later commit that says why).

Variants (all on the D53 harness's analog fold, scored beside the record's `box_v2`, each with its own F(k) as the harness
calibrates every variant):
  box_v2s         box_v2 rules on a pool with MEASURED spacing for every well (D119: the spacing fix, every bench)
  box_v2s_tr      + lateral as a TRANSLATION, not a filter: analogs 5,000-15,000 ft completed lateral, every cohort Cui-translated
                    (attribution: the lateral rule alone)
  box_v2s_lo      + level-only short-history wells (attribution: D118's middle path alone)
  box_v2s_r1      the first ladder (relax count, then spacing, then a +/-40 % lateral band, before the radius grows) — kept as
                    the COMPARISON, never adopted (Michael 2026-10-22)
  box_v2s_r2      translate + the ladder count, then spacing (same bench > distance > spacing > count; lateral is no longer a
                    rule) — adoption candidate
  box_v2s_r2lo    box_v2s_r2 + level-only short-history wells — adoption candidate
and `box_v2s_wf` for the groups whose record carries a walk-forward haircut (WCA, BS2_S). LINEAR_TWINS also predict
`<name>_lin`: the same cohort scaled linearly per ft, for the Cui-vs-linear check (`cui_check`).

Revision 2026-10-22 (Michael, before any score; commit "step 16b lateral as translation"): r1's lateral band step replaced by
the translate rule (r2); box_v2s_lat / box_v2s_r1lo dropped; the Cui-vs-linear check added as adoption condition 6.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import analog as an

MEASURED = "pool2_measured"  # the predict_many_v2 state key of the measured-spacing pool
TRANSLATE = an.Rules(lateral="translate")
VARIANTS: dict[str, tuple[str, an.Rules]] = {
    "box_v2s": (MEASURED, an.Rules()),
    "box_v2s_tr": (MEASURED, TRANSLATE),
    "box_v2s_lo": (MEASURED, an.Rules(level_only=True)),
    "box_v2s_r1": (MEASURED, an.Rules(relax=("count", "spacing", "lateral"))),
    "box_v2s_r2": (MEASURED, an.Rules(lateral="translate", relax=("count", "spacing"))),
    "box_v2s_r2lo": (MEASURED, an.Rules(lateral="translate", relax=("count", "spacing"), level_only=True)),
}
BASE = "box_v2s"
CANDIDATES: tuple[str, ...] = ("box_v2s_r2", "box_v2s_r2lo")  # adoption candidates for the provisional groups
COMPARISON: tuple[str, ...] = ("box_v2s_r1",)  # reported beside the candidates, never adopted
ATTRIBUTION: tuple[str, ...] = ("box_v2s_tr", "box_v2s_lo")  # reported, never adopted
LINEAR_TWINS: tuple[str, ...] = ("box_v2s_tr", "box_v2s_r2")  # also predict <name>_lin (Cui-vs-linear check)
SCORED: tuple[str, ...] = (*VARIANTS, *(f"{v}_lin" for v in LINEAR_TWINS))  # every prediction the harness scores

# Cui-vs-linear check (PREREGISTRATION §6b): length mismatch = location completed lateral / cohort mean completed lateral
MISMATCH_BINS: tuple[tuple[str, float, float], ...] = (("shorter", 0.0, 0.80), ("near", 0.80, 1.25), ("longer", 1.25, np.inf))
CUI_FLAG_PTS = 0.05  # a bench where Cui's summed class |bias| exceeds linear's by > 5 points is flagged to Michael
CUI_MIN_WELLS = 10  # a mismatch class with fewer scored wells is reported, not used
MISMATCHED: tuple[str, ...] = ("shorter", "longer")  # judged SEPARATELY: linear errs high on longer, low on shorter (they cancel pooled)

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


def cui_vs_linear(view: pd.DataFrame, variant: str, stream: str, k: int) -> pd.DataFrame:
    """Per length-mismatch class (+ "mismatched" = shorter + longer, reported only — the decision uses the classes
    separately): well-level Σ actual / Σ predicted − 1 of `variant` (Cui-translated) and of its linear twin `<variant>_lin`, on
    the SAME wells (both predictions finite)."""
    r = pd.to_numeric(view[f"{variant}_lat_ratio"], errors="coerce")
    a = view[f"actual_{stream}{k}"].astype(float)
    pc, pl = view[f"pred_{variant}_{stream}{k}"].astype(float), view[f"pred_{variant}_lin_{stream}{k}"].astype(float)
    ok = np.isfinite(a) & np.isfinite(pc) & np.isfinite(pl) & (pc > 0) & (pl > 0) & np.isfinite(r)
    rows = []
    for name, lo, hi in (*MISMATCH_BINS, ("mismatched", np.nan, np.nan)):
        m = ok & (((r < MISMATCH_BINS[0][2]) | (r >= MISMATCH_BINS[2][1])) if name == "mismatched" else ((r >= lo) & (r < hi)))
        rows.append({"variant": variant, "stream": stream, "horizon": k, "mismatch": name, "n_wells": int(m.sum()),
                     "bias_cui": float(a[m].sum() / pc[m].sum() - 1.0) if m.any() else float("nan"),
                     "bias_linear": float(a[m].sum() / pl[m].sum() - 1.0) if m.any() else float("nan")})
    return pd.DataFrame(rows)


def _class_abs(check: pd.DataFrame, k: int) -> tuple[float, float] | None:
    """(Σ |Cui bias|, Σ |linear bias|) over the MISMATCHED classes holding >= CUI_MIN_WELLS wells, oil, horizon k; None when
    no such class (cannot judge) or a used class has a NaN."""
    m = check[check["mismatch"].isin(MISMATCHED) & (check["stream"] == "oil") & (check["horizon"] == k) & (check["n_wells"] >= CUI_MIN_WELLS)]
    if not len(m) or not np.isfinite(m[["bias_cui", "bias_linear"]].to_numpy()).all():
        return None
    return float(m["bias_cui"].abs().sum()), float(m["bias_linear"].abs().sum())


def cui_holds(check: pd.DataFrame, horizons: Sequence[int] = (12, 24)) -> bool:
    """Adoption condition 6 (pooled over the provisional groups): at every horizon in `horizons`, oil, the Cui-translated
    prediction's |bias| summed over the shorter and longer classes (each with >= CUI_MIN_WELLS wells, judged separately so
    linear's opposite-sign errors do not cancel) is <= the linear twin's. A horizon that cannot be judged fails."""
    for k in horizons:
        r = _class_abs(check, k)
        if r is None or r[0] > r[1]:
            return False
    return True


def cui_flags(by_group: pd.DataFrame, horizons: Sequence[int] = (12, 24)) -> list[str]:
    """Groups (any tier) where, at any horizon, Cui's summed class |bias| exceeds linear's by more than CUI_FLAG_PTS — to Michael."""
    out = set()
    for g, x in by_group.groupby("group"):
        for k in horizons:
            r = _class_abs(x, k)
            if r is not None and r[0] - r[1] > CUI_FLAG_PTS:
                out.add(str(g))
    return sorted(out)


def adopt(cells: pd.DataFrame, stratum: pd.DataFrame, off_local: pd.DataFrame, hindcast_bias: float | None,
          cui_ok: bool | None = None) -> dict[str, Any]:
    """PREREGISTRATION §5, one variant for EVERY provisional group (no per-group choice after the look).

    cells     pooled tuning cells, every provisional group: variant, group, stream, horizon, verdict, pkg_bias
    stratum   far-with-local oil cum-12 well-level bias, pooled over the provisional groups: variant, bias
    off_local production far-with-local PUDs: variant, share_off (share > OFF_LOCAL from local)
    hindcast_bias  the level-only 3-5-month hindcast bias (next-12-month oil), None when not run
    cui_ok    `cui_holds` on box_v2s_r2's pooled Cui-vs-linear check (both candidates share its translation), None = not run

    A candidate passes when (1) it fails no more judged cells than the base, (2) its median |pkg bias| over judged cells is
    <= the base's + MEDIAN_ABS_SLACK, (3) its far-with-local |bias| <= the base's, (4) its off-local share <= the base's, and
    (5) a level-only candidate also has |hindcast bias| <= HINDCAST_TOL, and (6) the Cui translation holds (`cui_ok`).
    Among passing candidates the lower median |bias| wins;
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
               "off_local": sc["off_local"] <= base["off_local"],
               "cui": bool(cui_ok)}
        if VARIANTS[v][1].level_only:
            chk["hindcast"] = hindcast_bias is not None and abs(hindcast_bias) <= HINDCAST_TOL
        out["checks"][v] = chk
        if all(chk.values()):
            passing.append(v)
    passing.sort(key=lambda v: (out["scores"][v]["median_abs"], VARIANTS[v][1].level_only))
    out["adopted"] = passing[0] if passing else BASE
    return out
