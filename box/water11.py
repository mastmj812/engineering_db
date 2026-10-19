"""BOX step 11 — water: measured-water analog reach + the method comparison on TUNING blocks (read-only, plan §5 step 11).

Kickoff (Michael 2026-10-19, not re-litigated here):
  1. every location is forecast from MEASURED-water analogs, reaching farther than the D54 ladder when needed (the reach is
     recorded); only where none are found does it fall back to vendor-calculated water, flagged. No provisional water tier
     for lack of measured analogs.
  2. measured = sql/41 water_source 'measured' + seller VDR daily water where loaded; 'indeterminate' does not count.
     AMENDED (Michael 2026-10-19, before any scoring): NM water counts as measured unless sql/41 would call it
     'insufficient' (NM C-115 water is reported; sql/41's 0.05 CV floor marks steady real NM water 'calculated').
     TX keeps the sql/41 label only.
  3. the water tolerance is pre-registered before any scoring (docs/box/step11-2026-10-19/PREREGISTRATION.md).

Measured label AS OF a date (`classify_asof`): sql/41's own statistics recomputed on months reported through that date, so a
fold's analog pool never reads post-cutoff production (sql/41 itself is computed on all data — used only for the scored
targets' own label, which is their outcome side).

Selection (`select_water`): the deal-intake classify + tier-blind fill exactly as box_v2's first ring (config v10: same bench,
first production >= 2016, >= 6 months, lateral band, representative spacing; completed laterals, D56; short completed laterals
draw the 7,500-12,500 ft band, D58), over the D54 ladder 5 / 7.5 / 10 / 15 / 20 mi and then the WATER EXTENSION 30 / 40 / 50 mi,
circles only (no D55 strike ellipse: the ellipse exists to keep oil analogs on structure; a water reach is about measurement
coverage). Stops at the first radius with >= MIN_WELLS (10) eligible measured wells. At 50 mi: >= MIN_USE (3) measured ->
used, flagged `thin`; fewer -> FALLBACK: the same selection on the group's whole pool (any water label) over the D54 ladder,
flagged `calculated_fallback`.

Methods (pre-registered in the kickoff; scored on TUNING packages only, D52 salt unchanged):
  ratio     WOR vs cumulative oil (boxfit ratio mode: ln WOR = alpha + beta * Np on the measured cohort's aggregated per-1,000-ft
            MEAN series, post oil peak; beta bounded) applied to the location's BOX oil months (raw box_v2, uptime-free, the
            tuning run's own months) x F_oil(k)
  arps      independent water Arps P50 of the measured cohort (D57 pattern, water's own Di cap 12/yr, D38) x completed lateral
            / 1,000 x F_oil(k)
  ratio_actual_oil   diagnostic only: the same WOR curve applied to the scored well's ACTUAL oil months — the WOR's own skill
            with the oil error removed (what a later oil refinement would carry through)
  bench     D53 local-offsets benchmark on measured wells: median per-1,000-ft water cum-k of the 15 nearest measured pre-cutoff
            pool wells whose cum-k was known at the cutoff, x lateral
F_oil(k) (the oil calendar factor of the tuning fold) is used for both methods: downtime hits oil and water together, and the
tuning run calibrated no water factor.

Error convention: actual / forecast - 1 (negative = the forecast is HIGH). Package = the D53 package of the tuning view,
restricted to its measured-water members.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import acceptance as ac
from box import analog as an
from box import tc_curve as tc

LADDER_MI: tuple[float, ...] = an.RADII_MI  # D54
EXTENSION_MI: tuple[float, ...] = (30.0, 40.0, 50.0)  # water only: measured-water reach past the D54 cap
WATER_RADII_MI: tuple[float, ...] = (*LADDER_MI, *EXTENSION_MI)
MIN_WELLS = 10  # deal-intake config v10 type_curve.min_wells
MIN_USE = 3  # a cohort with fewer analogs is not a cohort (D74's floor)
K = 48
HORIZONS: tuple[int, ...] = (12, 24, 36)
BENCH_K = 15
NM, TX = "30", "42"
LAST = dt.date(2026, 7, 1)  # production through, = every tuning / holdout run and record run 10
MI = 5280.0
DOCS = Path("docs") / "box"
POOL_REFRESH = DOCS / "pool-2026-10-15"

# the well set each record-run-10 group was built / tuned on (production_run9.wells_dir; WCA / BS2_S / WCXY = the D84 refresh)
GROUP_WELLS: dict[str, Path] = {"WCA": POOL_REFRESH, "BS2_S": POOL_REFRESH, "WCXY_WCA1": POOL_REFRESH,
                                "WCB_1": DOCS / "step15-WCB-2026-10-16", "WCB_2": DOCS / "step15-WCB-2026-10-16",
                                "WCC": DOCS / "step15-WCC-2026-10-16", "BS1_S": DOCS / "step15-BS1-2026-10-16",
                                "BS2_C": DOCS / "step15-BS2C-2026-10-16", "BS3_S": DOCS / "step15a-2026-10-16",
                                "BS3_C": DOCS / "step15a-2026-10-16", "AVA_0": DOCS / "step15-AVA-2026-10-16",
                                "AVA_1": DOCS / "step15-AVA-2026-10-16", "AVA_2": DOCS / "step15-AVA-2026-10-16"}
GROUPS: tuple[str, ...] = tuple(GROUP_WELLS)

# tuning artefacts of each group (runs/<...>, git-ignored; copied to runs/step11_inputs/<group>/, digests in digests.txt)
TUNING_TAG: dict[str, str] = {"WCA": "guard_tuning", "BS2_S": "tuning_BS2_S", "WCXY_WCA1": "tuning_WCXY_WCA1"} | {
    g: f"tuning_v2_{g}_analog" for g in GROUPS if g not in ("WCA", "BS2_S", "WCXY_WCA1")}


# step 12a: each group's SPENT oil holdout run (holdout views + box_v2 oil months; runs/step12a_inputs/<group>/, digests). AVA_0 / 1 / 2
# and BS2_C have none: D105 provisional benches were never holdout-scored, so no holdout oil forecast exists for them.
HOLDOUT_TAG: dict[str, str] = {"WCA": "guard_holdout", "BS2_S": "holdout_BS2_S", "WCXY_WCA1": "holdout_WCXY_WCA1"} | {
    g: f"holdout_v2_{g}_analog" for g in ("WCB_1", "WCC", "BS3_S", "BS3_C", "WCB_2", "BS1_S")}


def ac_label(group: str) -> str:
    """The deal-intake bench label a group's selection runs under (BENCH_SPECS)."""
    return str(ac.BENCH_SPECS[group]["label"])


def group_of(bench: str, formation_blueox: str) -> str:
    """box.pud_forecast (bench, formation_blueox) -> the run-10 group (WCXY PUDs sit on bench WCA, D95)."""
    if bench == "WCA":
        return "WCXY_WCA1" if formation_blueox == "WCXY" else "WCA"
    return bench


# ----------------------------------------------------------------------------
# Pure: the measured label as of a date
# ----------------------------------------------------------------------------


def wor_stats(rows: pd.DataFrame, asof: dt.date | None) -> pd.DataFrame:
    """sql/41's statistics per api10 from usable rows (mop 1-24, oil > 0, water > 0; columns api10, prod_date, oil, water,
    prop) reported through `asof` (None = all): n_wor_months, water_prop_share, wor_cv."""
    r = rows if asof is None else rows[rows["prod_date"] <= asof]
    w = r["water"].to_numpy(float) / r["oil"].to_numpy(float)
    d = pd.DataFrame({"api10": r["api10"].to_numpy(), "wor": w, "prop": r["prop"].astype(float).to_numpy()})
    g = d.groupby("api10")
    out = pd.DataFrame({"n_wor_months": g.size(), "water_prop_share": g["prop"].mean(), "wor_mean": g["wor"].mean(), "wor_sd": g["wor"].std(ddof=1)})
    out["wor_cv"] = out["wor_sd"] / out["wor_mean"].replace(0, np.nan)
    return out.reset_index()


def sql41_label(n: float, prop: float, cv: float) -> str:
    """sql/41's CASE, in its order."""
    if not np.isfinite(n) or n < 6:
        return "insufficient"
    if np.isfinite(prop) and prop >= 0.9:
        return "measured"
    if np.isfinite(prop) and prop <= 0.1 and np.isfinite(cv) and cv < 0.05:
        return "calculated"
    if np.isfinite(cv) and cv >= 0.15:
        return "measured"
    return "indeterminate"


def water_label(state_code: str, n: float, prop: float, cv: float, vdr_months: int = 0) -> str:
    """The BOX-water label (kickoff 2 as amended 2026-10-19): 'measured' | 'calculated' | 'indeterminate' | 'insufficient'.
    NM: measured unless insufficient. TX: sql/41's label. Either state: >= 6 months of seller VDR daily water -> measured."""
    if vdr_months >= 6:
        return "measured"
    lab = sql41_label(n, prop, cv)
    if str(state_code) == NM and lab != "insufficient":
        return "measured"
    return lab


def labels_asof(wells: pd.DataFrame, rows: pd.DataFrame, asof: dt.date | None, vdr_months: Mapping[str, int] | None = None) -> pd.Series:
    """api10 -> BOX-water label as of `asof` for every well of `wells` (api10, state_code)."""
    st = wor_stats(rows, asof).set_index("api10")
    vm = vdr_months or {}
    out = {}
    for a, sc in zip(wells["api10"], wells["state_code"].astype(str), strict=True):
        if a in st.index:
            r = st.loc[a]
            out[a] = water_label(sc, float(r.n_wor_months), float(r.water_prop_share), float(r.wor_cv), int(vm.get(a, 0)))
        else:
            out[a] = water_label(sc, 0.0, np.nan, np.nan, int(vm.get(a, 0)))
    return pd.Series(out, dtype=object)


def vdr_months_asof(vdr: pd.DataFrame, asof: dt.date | None) -> dict[str, int]:
    """api10 -> months with seller-reported water > 0 through `asof` (vdr monthly frame: api10, month, water)."""
    v = vdr if asof is None else vdr[vdr["month"] <= asof]
    return v[v["water"] > 0].groupby("api10").size().astype(int).to_dict()


# ----------------------------------------------------------------------------
# Pure: selection
# ----------------------------------------------------------------------------


def select_water(pool: Mapping[str, Any], tree: cKDTree, cfg: Any, loc: Mapping[str, Any], radii: Sequence[float], bench: str,
                 min_w: int = MIN_WELLS, basin: str = "delaware") -> tuple[list[int], float, int]:
    """(pool indices, radius reached mi, eligible count at that radius): box_v2's first-ring selection on circles over `radii`.
    `basin` sets deal-intake's per-basin lateral tolerance (BOX is Delaware-only; deal-intake screens pass their own)."""
    from dealintake import select_wells as sw

    sp = loc.get("spacing_ft")
    planned_sp = float(sp) if sp is not None and np.isfinite(sp) and 0 < sp < 2800 else an.DEFAULT_SPACING_FT
    lat = float(loc["lateral_ft"])
    band = an.SHORT_BAND_FT if lat < an.SHORT_LAT_FT else None
    for r in radii:
        idx = tree.query_ball_point([loc["x"], loc["y"]], r=r * MI)
        cands = an._candidates(pool, idx, loc)
        eligible, _, _ = sw.classify(cands, cfg, bench=bench, planned_stack=[bench], planned_lateral_ft=lat, basin=basin,
                                     planned_spacing_ft=planned_sp, lateral_band_ft=band)
        if len(eligible) >= min_w or r == radii[-1]:
            sel = sw.fill(eligible, cfg, bench=bench, adjacent=[], order=["stack_standalone"], order_reason="tier-blind (v10)", tier_blind=True)
            return [c["_i"] for c in sel.selected], float(r), len(eligible)
    return [], float(radii[-1]), 0


def choose(meas: tuple[list[int], float, int], fallback_fn: Any) -> dict[str, Any]:
    """Kickoff 1: measured analogs at whatever reach; >= MIN_USE at the cap -> used (thin); fewer -> calculated fallback."""
    idx, r, n_elig = meas
    if len(idx) >= MIN_USE:
        return {"source": "measured", "idx": idx, "radius_mi": r, "n_eligible": n_elig, "thin": len(idx) < MIN_WELLS}
    fidx, fr, fn = fallback_fn()
    return {"source": "calculated_fallback", "idx": fidx, "radius_mi": fr, "n_eligible": fn, "thin": len(fidx) < MIN_WELLS,
            "n_measured_at_cap": len(idx)}


_W: dict[str, Any] = {}


def _init(state: dict[str, Any]) -> None:
    import logging

    _W.clear()
    _W.update(state)
    _W["tree_m"] = cKDTree(np.column_stack([state["pool_m"]["x"], state["pool_m"]["y"]])) if len(state["pool_m"]["x"]) else None
    _W["tree_a"] = cKDTree(np.column_stack([state["pool_a"]["x"], state["pool_a"]["y"]]))
    logging.getLogger().setLevel(logging.CRITICAL)
    try:
        import structlog

        structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
    except ImportError:
        pass


def _empty() -> tuple[list[int], float, int]:
    return [], WATER_RADII_MI[-1], 0


def select_one(loc: dict[str, Any]) -> dict[str, Any]:
    pm, pa, cfg, bench = _W["pool_m"], _W["pool_a"], _W["cfg"], _W["bench"]
    meas = select_water(pm, _W["tree_m"], cfg, loc, WATER_RADII_MI, bench) if _W["tree_m"] is not None else _empty()
    ch = choose(meas, lambda: select_water(pa, _W["tree_a"], cfg, loc, LADDER_MI, bench))
    pool = pm if ch["source"] == "measured" else pa
    ch["api10s"] = [str(pool["api10"][i]) for i in ch["idx"]]
    ch["nm_share"] = float(np.mean([pool["state"][i] == NM for i in ch["idx"]])) if ch["idx"] else float("nan")
    ch["loc"] = loc["api10"]
    del ch["idx"]
    return ch


def select_many(locs: list[dict[str, Any]], pool_m: dict[str, Any], pool_a: dict[str, Any], bench: str, workers: int | None) -> list[dict[str, Any]]:
    from dealintake import config as di_config

    state = {"pool_m": pool_m, "pool_a": pool_a, "cfg": di_config.load(), "bench": bench}
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    if workers == 1 or len(locs) < 64:
        _init(state)
        return [select_one(x) for x in locs]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(state,)) as ex:
        return list(ex.map(select_one, locs, chunksize=32))


def make_pool(w: pd.DataFrame) -> dict[str, Any]:
    """Selection pool from a frame with api10, x, y, first_production_date, lateral (completed), months, spacing, state_code."""
    return {"api10": w["api10"].to_numpy(), "x": w["x"].to_numpy(float), "y": w["y"].to_numpy(float), "fp": list(w["first_production_date"]),
            "lateral": w["lateral"].to_numpy(float), "months": w["months"].to_numpy(float), "spacing": w["spacing"].to_numpy(float),
            "state": w["state_code"].astype(str).to_numpy()}


# ----------------------------------------------------------------------------
# Pure: the two water methods on a measured cohort
# ----------------------------------------------------------------------------


def cohort_water(members: Sequence[tc.Member]) -> dict[str, Any]:
    """Per-1,000-ft water curves of a cohort: the WOR-vs-cum-oil ratio (alpha, beta, sub_mode) and the water Arps P50 months."""
    from boxfit.tc.fit_p50 import fit_p50_series
    from boxfit.tc.ratio_mode import build_ratio_fitted

    agg = tc.aggregate_only(members)
    st = agg.streams
    out: dict[str, Any] = {"ratio": None, "arps_months": None, "arps": None}
    oil_mean = fit_p50_series(st["oil"].mean, df_terminal_per_year=an.DF_DELAWARE, stream="oil")
    if oil_mean:
        r = build_ratio_fitted(mean_oil=st["oil"].mean, mean_stream=st["water"].mean, oil_fitted=oil_mean, n_months=tc.N_MONTHS)
        if r:
            out["ratio"] = {k: r[k] for k in ("alpha", "beta", "sub_mode", "r2", "n_months")}
    wf = fit_p50_series(st["water"].p50, df_terminal_per_year=an.DF_DELAWARE, stream="water")
    if wf:
        out["arps"] = {k: wf.get(k) for k in ("qi", "Di", "b", "Df", "qo", "peak_index")}
        out["arps_months"] = tc.monthly_volumes(wf, K)
    return out


def ratio_water(oil_months: np.ndarray, lateral_ft: float, ratio: Mapping[str, Any]) -> np.ndarray:
    """Monthly water = WOR(Np per 1,000 ft) x the location's oil months (D39 midpoint rule, tc.ratio_monthly_volumes)."""
    s = lateral_ft / 1000.0
    return tc.ratio_monthly_volumes(np.nan_to_num(np.asarray(oil_months, float)) / s, float(ratio["alpha"]), float(ratio["beta"])) * s


def cum_at(months: np.ndarray, F: np.ndarray | None, horizons: Sequence[int] = HORIZONS) -> dict[int, float]:
    c = np.cumsum(np.asarray(months, float)[:K])
    if F is not None:
        c = c * np.asarray(F, float)[: len(c)]
    return {k: float(c[k - 1]) if len(c) >= k else float("nan") for k in horizons}


def package_stats(df: pd.DataFrame, actual: str, pred: str) -> dict[str, float]:
    """D53 package statistics: per package sum actual / sum predicted - 1; bias = mean, band = P10 - P90 (P10 high), scale-free band."""
    p = ac.package_errors(df, "package", actual, pred)
    e = p["err"].to_numpy(float)
    e = e[np.isfinite(e)]
    if not len(e):
        return {"n_packages": 0, "n_wells": 0, "bias": np.nan, "median": np.nan, "band": np.nan, "band_sf": np.nan}
    band = float(np.percentile(e, 90) - np.percentile(e, 10))
    bias = float(np.mean(e))
    return {"n_packages": len(e), "n_wells": int(p["n"].sum()), "bias": bias, "median": float(np.median(e)), "band": band,
            "band_sf": ac.scale_free(band, bias)}


def month_index(d0: dt.date, d: dt.date) -> int:
    return (d.year - d0.year) * 12 + d.month - d0.month


def stream_matrix(prod: pd.DataFrame, api10s: Sequence[str], col: str, *, asof: dt.date | None = None, drop_latest: bool = False, k: int = K) -> np.ndarray:
    """hindcast_production.monthly_matrix for any column (water_bbl here): [wells, k] from the first reported month, NaN = not known."""
    out = np.full((len(api10s), k), np.nan)
    g = dict(tuple(prod.groupby("api10")))
    for i, a in enumerate(api10s):
        p = g.get(a)
        if p is None:
            continue
        p = p.sort_values("prod_date")
        d0 = p["prod_date"].iloc[0]
        idx = np.array([month_index(d0, d) for d in p["prod_date"]])
        n = month_index(d0, asof) + 1 if asof is not None else int(idx.max()) + (0 if drop_latest else 1)
        n = min(n, k)
        v = np.zeros(k)
        m = idx < k
        v[idx[m]] = pd.to_numeric(p[col], errors="coerce").fillna(0.0).to_numpy(float)[m]
        out[i, :n] = v[:n]
    return out

