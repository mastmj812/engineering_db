"""BOX D54 candidate — deal-intake analog workup at every location, for the D53 harness (five pre-registered variants).

Per location (a scored well at a fold's cutoff, or a PUD later): candidate analogs = WCA wells first-producing before the
cutoff with a per-well fit at the cutoff (the fold's boxfit fits), selected by `dealintake.select_wells` exactly as the
deal-intake skill does (config v10: same bench, first production >= 2016, >= 6 months, lateral band around the location's
lateral, representative spacing vs the location's planned spacing, tier-blind nearest-first up to max_wells). Distance =
lateral midpoint to lateral midpoint. Radius ladder 5 -> 7.5 -> 10 -> 15 -> 20 mi until min_wells (10) are eligible (D54:
inside the extent a location is always forecast; the radius reached is provenance). Short-history transfer as deal-intake:
a cohort well with < 9 months after its peak takes the eligible pool's long-well median Di / b (its own qi kept).

Variants (fixed before running; each calibrated by its own F(k) on a seeded training sample, leave-self-out):
  di_p50            faithful deal-intake: P50 curve per stream (gas = its own Arps P50), linear per-ft lateral scaling
  di_mean           cohort MEAN curve (D32: package sums are unbiased against a mean), gas = ratio at the local GOR (D30)
  di_mean_cui       + Cui & Cross lateral efficiency (D50) relative to the cohort's own laterals
  di_mean_cui_scen  + dev-scenario factors: analogs normalised to the reference with their pooled factors (D43 ref_mult)
                    and the location's own factor applied (gas: local GOR x f_GOR, D46)
  di_recent         di_mean_cui with analogs preferentially from the last 4 years (stance (a): persistence at the newest
                    regime) when >= min_wells such wells lie within 10 mi; else the full cohort (flagged)
"""

from __future__ import annotations

import datetime as dt
import math
import os
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import pandas as pd
from boxfit.tc.fit_p50 import fit_p50_series
from boxfit.tc.ratio_mode import build_ratio_fitted
from scipy.spatial import cKDTree

from box import lateral as lat_eff
from box import tc_curve as tc
from box import tc_record as tr
from dealintake import config as di_config
from dealintake import select_wells as sw

VARIANTS: tuple[str, ...] = ("di_p50", "di_mean", "di_mean_cui", "di_mean_cui_scen", "di_recent")
RADII_MI: tuple[float, ...] = (5.0, 7.5, 10.0, 15.0, 20.0)
RECENT_YEARS = 4
RECENT_MAX_MI = 10.0
DEFAULT_SPACING_FT = 880.0  # narvi fallback planned spacing
TRANSFER_MONTHS = 9
DF_DELAWARE = 0.08
MI = 5280.0
STREAMS = ("oil", "gas")

_STATE: dict[str, Any] = {}


# ----------------------------------------------------------------------------
# Pool + selection
# ----------------------------------------------------------------------------


def build_pool(frame: pd.DataFrame, fits: dict[str, dict[str, Any]], spacing_ft: pd.Series, f_oil: dict[str, float]) -> dict[str, Any]:
    """Analog candidates at a cutoff: wells of the fold's curve frame with an oil fit and a real lateral."""
    f = frame[frame["fit_oil"].astype(bool) & (pd.to_numeric(frame["lateral_ft"], errors="coerce") > 0)].copy()
    f = f[f["months"].fillna(0) >= 1].reset_index(drop=True)
    params = {a: {s: (fits.get(a, {}).get(s) or {}).get("params") for s in ("oil", "gas", "water")} for a in f["api10"]}
    return {"api10": f["api10"].to_numpy(), "x": f["x"].to_numpy(float), "y": f["y"].to_numpy(float),
            "fp": list(f["first_production_date"]), "lateral": f["lateral_ft"].to_numpy(float), "months": f["months"].fillna(0).to_numpy(float),
            "spacing": f["api10"].map(spacing_ft).to_numpy(float), "oil12_kft": pd.to_numeric(f["oil12_kft"], errors="coerce").to_numpy(float),
            "f_oil": np.array([float(f_oil.get(a, 1.0)) for a in f["api10"]]), "params": params}


def _candidates(pool: dict[str, Any], idx: Sequence[int], loc: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    fp_max = loc.get("fp_max")
    for i in idx:
        if pool["api10"][i] == loc["api10"]:
            continue  # leave-self-out (training sample)
        if fp_max is not None and not pool["fp"][i] < fp_max:
            continue  # as-of: only wells that first produced before the location (calibration mirrors prediction)
        sp = pool["spacing"][i]
        out.append({"api10": pool["api10"][i], "first_production_date": pool["fp"][i], "lateral_length_ft": float(pool["lateral"][i]),
                    "months_produced": float(pool["months"][i]), "lateral_closer_xy_ft": None if not np.isfinite(sp) else float(sp),
                    "codev_scorable": True, "dist_ft": float(math.hypot(pool["x"][i] - loc["x"], pool["y"][i] - loc["y"])), "_i": int(i)})
    return out


def select_cohort(pool: dict[str, Any], tree: cKDTree, cfg: di_config.Config, loc: dict[str, Any], *, fp_from: dt.date | None = None,
                  radii: Sequence[float] = RADII_MI) -> tuple[list[int], float, list[str]]:
    """deal-intake classify + tier-blind fill over a growing radius; returns (pool indices, radius mi, flags)."""
    sp = loc.get("spacing_ft")
    planned_sp = float(sp) if sp is not None and np.isfinite(sp) and 0 < sp < 2800 else DEFAULT_SPACING_FT
    min_w = int(cfg["type_curve"]["min_wells"])
    for r in radii:
        idx = tree.query_ball_point([loc["x"], loc["y"]], r=r * MI)
        cands = _candidates(pool, idx, loc)
        if fp_from is not None:
            cands = [c for c in cands if c["first_production_date"] >= fp_from]
        eligible, _, _ = sw.classify(cands, cfg, bench="WCA", planned_stack=["WCA"], planned_lateral_ft=float(loc["lateral_ft"]),
                                     basin="delaware", planned_spacing_ft=planned_sp)
        if len(eligible) >= min_w or r == radii[-1]:
            sel = sw.fill(eligible, cfg, bench="WCA", adjacent=[], order=["stack_standalone"], order_reason="tier-blind (v10)", tier_blind=True)
            return [c["_i"] for c in sel.selected], r, sel.flags
    return [], radii[-1], ["no candidates"]


# ----------------------------------------------------------------------------
# Curve + prediction
# ----------------------------------------------------------------------------


def _post_peak(p: dict[str, Any] | None, months: float) -> float:
    if not p:
        return -1.0
    return months - float(p.get("onset_index_months") or 0) - float(p.get("peak_index_months") or 0)


def members_with_transfer(pool: dict[str, Any], idx: Sequence[int]) -> list[tc.Member]:
    """tc.Member per cohort well; < TRANSFER_MONTHS post-peak -> the cohort's long-well median Di / b (qi kept)."""
    med: dict[str, tuple[float, float] | None] = {}
    for s in STREAMS:
        long = [pool["params"][pool["api10"][i]][s] for i in idx
                if pool["params"][pool["api10"][i]][s] and _post_peak(pool["params"][pool["api10"][i]][s], pool["months"][i]) >= TRANSFER_MONTHS]
        med[s] = (float(np.median([p["Di"] for p in long])), float(np.median([p["b"] for p in long]))) if long else None
    out = []
    for i in idx:
        a = pool["api10"][i]
        ps = {}
        for s in ("oil", "gas", "water"):
            p = pool["params"][a][s]
            if p and s in STREAMS and med[s] and _post_peak(p, pool["months"][i]) < TRANSFER_MONTHS:
                p = {**p, "Di": med[s][0], "b": med[s][1]}
            ps[s] = p
        out.append(tc.Member(api10=a, lateral_ft=float(pool["lateral"][i]), params=ps))
    return out


def cohort_fits(members: Sequence[tc.Member], need_p50: bool) -> dict[str, Any] | None:
    agg = tc.aggregate_only(members)
    st = agg.streams
    oil_mean = fit_p50_series(st["oil"].mean, df_terminal_per_year=DF_DELAWARE, stream="oil")
    if not oil_mean:
        return None
    out: dict[str, Any] = {"oil_mean": oil_mean,
                           "ratio": build_ratio_fitted(mean_oil=st["oil"].mean, mean_stream=st["gas"].mean, oil_fitted=oil_mean, n_months=tc.N_MONTHS)}
    if need_p50:
        out["oil_p50"] = fit_p50_series(st["oil"].p50, df_terminal_per_year=DF_DELAWARE, stream="oil")
        out["gas_p50"] = fit_p50_series(st["gas"].p50, df_terminal_per_year=DF_DELAWARE, stream="gas")
    return out


def _months(fit: dict[str, Any] | None, k: int) -> np.ndarray:
    return tc.monthly_volumes(fit, tc.N_MONTHS)[:k] if fit else np.full(k, np.nan)


def _gas_ratio_months(cf: dict[str, Any], target: float | None, k: int) -> np.ndarray:
    ratio = cf["ratio"]
    if not ratio:
        return np.full(k, np.nan)
    curve = {"gas_ratio": ratio, "fits": {"oil": {"mean": cf["oil_mean"]}}, "record": "mean"}
    if target and np.isfinite(target) and target > 0:
        sh = tc.shift_gor_level(curve, target)
        if sh:
            return np.asarray(sh["gas_volumes"][:k], float)
    ov = tc.monthly_volumes(cf["oil_mean"], tc.N_MONTHS)
    return tc.ratio_monthly_volumes(ov, float(ratio["alpha"]), float(ratio["beta"]))[:k]


def predict_location(loc: dict[str, Any]) -> dict[str, Any]:
    """Monthly oil / gas (months 1..k, uptime-free) for every variant at one location + provenance."""
    pool, tree, cfg, k, cutoff = _STATE["pool"], _STATE["tree"], _STATE["cfg"], _STATE["k"], _STATE["cutoff"]
    lat = float(loc["lateral_ft"])
    out: dict[str, Any] = {"api10": loc["api10"]}
    idx, r, flags = select_cohort(pool, tree, cfg, loc)
    out.update({"radius_mi": r, "n_analogs": len(idx), "flags": ";".join(flags)})
    if len(idx) < 3:
        return out
    cf = cohort_fits(members_with_transfer(pool, idx), need_p50=True)
    if cf is None:
        return out
    scale = lat / 1000.0
    lats = [pool["lateral"][i] for i in idx]
    cui = lat_eff.relative(lat, lats)
    oil_mean, gas_local = _months(cf["oil_mean"], k), _gas_ratio_months(cf, loc.get("gor_local"), k)
    out["di_p50"] = {"oil": _months(cf.get("oil_p50"), k) * scale, "gas": _months(cf.get("gas_p50"), k) * scale}
    out["di_mean"] = {"oil": oil_mean * scale, "gas": gas_local * scale}
    out["di_mean_cui"] = {"oil": oil_mean * scale * cui, "gas": gas_local * scale * cui}
    w = [pool["oil12_kft"][i] for i in idx]
    fac = [pool["f_oil"][i] for i in idx]
    ref = tr.weighted_ref_mult(w, fac)
    ref = ref if np.isfinite(ref) else 1.0
    f_loc = float(loc.get("f_oil") or 1.0)
    gt = (loc.get("gor_local") or np.nan) * float(loc.get("f_gor") or 1.0)
    gas_scen = _gas_ratio_months(cf, gt, k)
    out["di_mean_cui_scen"] = {"oil": oil_mean * scale * cui * ref * f_loc, "gas": gas_scen * scale * cui * ref * f_loc}
    out["ref_mult"] = ref
    # recency-preferred cohort
    fp_from = dt.date(cutoff.year - RECENT_YEARS, cutoff.month, 1)
    ridx, rr, _ = select_cohort(pool, tree, cfg, loc, fp_from=fp_from, radii=tuple(x for x in RADII_MI if x <= RECENT_MAX_MI))
    if len(ridx) >= int(cfg["type_curve"]["min_wells"]):
        rcf = cohort_fits(members_with_transfer(pool, ridx), need_p50=False)
        rlats = [pool["lateral"][i] for i in ridx]
        rcui = lat_eff.relative(lat, rlats)
        out["di_recent"] = {"oil": _months(rcf["oil_mean"], k) * scale * rcui, "gas": _gas_ratio_months(rcf, loc.get("gor_local"), k) * scale * rcui} if rcf else out["di_mean_cui"]
        out.update({"recent_radius_mi": rr, "recent_n": len(ridx), "recent_fallback": not rcf})
    else:
        out["di_recent"] = out["di_mean_cui"]
        out.update({"recent_radius_mi": np.nan, "recent_n": len(ridx), "recent_fallback": True})
    return out


def _init(state: dict[str, Any]) -> None:
    import logging

    _STATE.update(state)
    _STATE["tree"] = cKDTree(np.column_stack([state["pool"]["x"], state["pool"]["y"]]))
    logging.getLogger().setLevel(logging.CRITICAL)
    try:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
    except ImportError:
        pass


def predict_many(locs: list[dict[str, Any]], pool: dict[str, Any], cutoff: dt.date, k: int, workers: int | None = None) -> list[dict[str, Any]]:
    state = {"pool": pool, "cfg": di_config.load(), "k": k, "cutoff": cutoff}
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    if workers == 1:
        _init(state)
        return [predict_location(x) for x in locs]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(state,)) as ex:
        return list(ex.map(predict_location, locs, chunksize=16))


def monthly_arrays(preds: list[dict[str, Any]], k: int) -> dict[str, dict[str, np.ndarray]]:
    """variant -> stream -> [locations, k] (NaN where a variant has no prediction)."""
    out = {v: {s: np.full((len(preds), k), np.nan) for s in STREAMS} for v in VARIANTS}
    for i, p in enumerate(preds):
        for v in VARIANTS:
            if v in p:
                for s in STREAMS:
                    out[v][s][i] = p[v][s]
    return out


# ============================================================================
# v2 — the pre-registered follow-on run (Michael 2026-10-14): di_p50 (D57) vs box_v2
#   box_v2 = di_p50 + D55 strike-ellipse search past the first ring + short-lateral Cui translation + D56 U-turn
#            completed laterals (analogs and locations)
# ============================================================================

VARIANTS_V2: tuple[str, ...] = ("di_p50", "box_v2")
SHORT_LAT_FT = 7_500.0  # a location whose COMPLETED lateral is shorter than this draws contemporary longer analogs ...
SHORT_BAND_FT = (7_500.0, 12_500.0)  # ... from this band, translated to its length by Cui & Cross (D50)

_UTURN_SQL = """
SELECT w.api10,
       extensions.ST_Distance(
           COALESCE(CASE WHEN w.landing_point_lat IS NOT NULL AND w.landing_point_lon IS NOT NULL
                         THEN extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326) END,
                    extensions.ST_StartPoint(w.wellstick_geom))::extensions.geography,
           extensions.ST_EndPoint(w.wellstick_geom)::extensions.geography) * 3.28084 AS leg_spacing_ft
FROM curated.wells w
WHERE w.api10 = ANY(%(a)s) AND w.wellstick_geom IS NOT NULL
  AND COALESCE(w.novi_slant_calculated, '') ILIKE 'u-turn%%'
"""


def uturn_leg_spacing(conn: Any, ids: Sequence[str]) -> dict[str, float]:
    """D56: U-turn wells -> leg-to-leg spacing (landing point to bottom hole, ft); the skipped-curve estimate."""
    from box import tc_curve_report as rep

    return {a: float(d) for a, d in rep._read(conn, _UTURN_SQL, {"a": list(ids)}) if d is not None and d > 0}


def completed_lateral(api10: str, lateral_ft: float, uturn: dict[str, float]) -> float:
    """D56: reported lateral minus the skipped curve for a U-turn; unchanged otherwise (never below 1,000 ft)."""
    sk = uturn.get(api10)
    return max(1000.0, float(lateral_ft) - sk) if sk else float(lateral_ft)


def with_completed_laterals(pool: dict[str, Any], uturn: dict[str, float], tvd: dict[str, float]) -> dict[str, Any]:
    p = dict(pool)
    p["lateral"] = np.array([completed_lateral(a, lv, uturn) for a, lv in zip(pool["api10"], pool["lateral"], strict=True)])
    p["tvd"] = np.array([float(tvd.get(a, np.nan)) for a in pool["api10"]])
    return p


def select_cohort_v2(pool: dict[str, Any], tree: cKDTree, cfg: di_config.Config, loc: dict[str, Any]) -> tuple[list[int], float, list[str], str]:
    """box_v2 selection: first ring circular; past it, a strike-aligned ellipse when local strike is trusted (D55);
    short completed laterals draw the SHORT_BAND_FT analogs (translated later by Cui). Returns (idx, radius, flags, mode)."""
    from box import strike as stk

    sp = loc.get("spacing_ft")
    planned_sp = float(sp) if sp is not None and np.isfinite(sp) and 0 < sp < 2800 else DEFAULT_SPACING_FT
    lat = float(loc["lateral_ft"])
    band = SHORT_BAND_FT if lat < SHORT_LAT_FT else None
    min_w = int(cfg["type_curve"]["min_wells"])

    def attempt(idx: Sequence[int], dist: dict[int, float] | None) -> tuple[list[int], list[str], int]:
        cands = _candidates(pool, idx, loc)
        if dist is not None:
            for c in cands:
                c["dist_ft"] = dist[c["_i"]]
        eligible, _, _ = sw.classify(cands, cfg, bench="WCA", planned_stack=["WCA"], planned_lateral_ft=lat, basin="delaware",
                                     planned_spacing_ft=planned_sp, lateral_band_ft=band)
        sel = sw.fill(eligible, cfg, bench="WCA", adjacent=[], order=["stack_standalone"], order_reason="tier-blind (v10)", tier_blind=True)
        return [c["_i"] for c in sel.selected], sel.flags, len(eligible)

    idx, flags, n = attempt(tree.query_ball_point([loc["x"], loc["y"]], r=RADII_MI[0] * MI), None)
    if n >= min_w:
        return idx, RADII_MI[0], flags, "circle"
    near = tree.query_ball_point([loc["x"], loc["y"]], r=stk.RADIUS_FT)
    s = stk.local_strike(pool["x"][near], pool["y"][near], pool["tvd"][near], loc["x"], loc["y"]) if len(near) else None
    for r in RADII_MI[1:]:
        cand = tree.query_ball_point([loc["x"], loc["y"]], r=r * MI * (stk.ASPECT if s else 1.0))
        if s:
            d = stk.ellipse_distance(pool["x"][cand] - loc["x"], pool["y"][cand] - loc["y"], s.azimuth_deg)
            keep = [int(i) for i, dd in zip(cand, d, strict=True) if dd <= r * MI]
            idx, flags, n = attempt(keep, {int(i): float(dd) for i, dd in zip(cand, d, strict=True)})
        else:
            idx, flags, n = attempt(cand, None)
        if n >= min_w or r == RADII_MI[-1]:
            return idx, r, flags, ("strike" if s else "circle")
    return idx, RADII_MI[-1], flags, "circle"


def _p50_months(idx: Sequence[int], pool: dict[str, Any], k: int) -> dict[str, np.ndarray] | None:
    agg = tc.aggregate_only(members_with_transfer(pool, idx))
    oil = fit_p50_series(agg.streams["oil"].p50, df_terminal_per_year=DF_DELAWARE, stream="oil")
    gas = fit_p50_series(agg.streams["gas"].p50, df_terminal_per_year=DF_DELAWARE, stream="gas")
    if not oil:
        return None
    return {"oil": _months(oil, k), "gas": _months(gas, k)}


def predict_location_v2(loc: dict[str, Any]) -> dict[str, Any]:
    """di_p50 exactly as v1 (raw laterals) and box_v2 (completed laterals, strike edges, short-lateral translation)."""
    pool1, pool2, tree, cfg, k = _STATE["pool"], _STATE["pool2"], _STATE["tree"], _STATE["cfg"], _STATE["k"]
    out: dict[str, Any] = {"api10": loc["api10"]}
    idx, r, flags = select_cohort(pool1, tree, cfg, loc)
    out.update({"radius_mi": r, "n_analogs": len(idx), "flags": ";".join(flags)})
    if len(idx) >= 3:
        m = _p50_months(idx, pool1, k)
        if m:
            out["di_p50"] = {s: m[s] * float(loc["lateral_ft"]) / 1000.0 for s in STREAMS}
    loc2 = {**loc, "lateral_ft": loc["lateral_eff"]}
    idx2, r2, _, mode = select_cohort_v2(pool2, tree, cfg, loc2)
    out.update({"v2_radius_mi": r2, "v2_n": len(idx2), "v2_mode": mode, "v2_short": loc2["lateral_ft"] < SHORT_LAT_FT,
                "v2_uturn": loc["lateral_eff"] != loc["lateral_ft"]})
    if len(idx2) >= 3:
        m2 = _p50_months(idx2, pool2, k)
        if m2:
            L = float(loc2["lateral_ft"])
            mult = L / 1000.0 * (lat_eff.relative(L, [pool2["lateral"][i] for i in idx2]) if L < SHORT_LAT_FT else 1.0)
            out["box_v2"] = {s: m2[s] * mult for s in STREAMS}
    return out


def predict_many_v2(locs: list[dict[str, Any]], pool: dict[str, Any], pool2: dict[str, Any], cutoff: dt.date, k: int,
                    workers: int | None = None) -> list[dict[str, Any]]:
    state = {"pool": pool, "pool2": pool2, "cfg": di_config.load(), "k": k, "cutoff": cutoff}
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    if workers == 1:
        _init(state)
        return [predict_location_v2(x) for x in locs]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(state,)) as ex:
        return list(ex.map(predict_location_v2, locs, chunksize=16))


def monthly_arrays_v2(preds: list[dict[str, Any]], k: int) -> dict[str, dict[str, np.ndarray]]:
    out = {v: {s: np.full((len(preds), k), np.nan) for s in STREAMS} for v in VARIANTS_V2}
    for i, p in enumerate(preds):
        for v in VARIANTS_V2:
            if v in p:
                for s in STREAMS:
                    out[v][s][i] = p[v][s]
    return out


def walk_forward(bias_by_cutoff: dict[str, float], cutoff: str, min_prior: int = 2) -> float | None:
    """D57: the haircut for `cutoff` = mean package bias at the SAME horizon over strictly earlier cutoffs (>= min_prior
    of them); None when too few. Corrected prediction = prediction x (1 + haircut)."""
    prior = [b for c, b in sorted(bias_by_cutoff.items()) if c < cutoff and b is not None and np.isfinite(b)]
    return float(np.mean(prior)) if len(prior) >= min_prior else None
