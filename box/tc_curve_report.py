"""BOX step 5b — baseline curves per WCA TC area: inputs, per-well fits, curves, gate tests, review page.

Read-only against the warehouse (session pooler, READ ONLY transactions):
  * the gate-1 final WCA well set minus docs/box/exclusions.csv (D29);
  * the TC areas of record (box.tc_area, is_record, on the WCA extent of record) — membership by
    lateral midpoint, checked by identity against the step-4 deliverable;
  * curated.production monthly volumes + calendar-day rates (the columns anduin syncs), cut at the
    last fully reported month;
  * curated.wells_enriched sub-basin + formation_blueox (Df and the b prior, as anduin keys them).

Per-well fits: boxfit.well.fit_well_streams, default ForecastConfig — exactly anduin's autoforecast.
Curves: box/tc_curve.py. Nothing is written to the warehouse; box.type_curve / tc_member DDL is 5d.
"""

from __future__ import annotations

import datetime as dt
import html
import itertools
import json
import logging
import math
import os
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import tc_curve as tc
from box.edge_gap_report import _CSS, _png, _table

POOL = "WCA"
BASIN = "delaware"
COHORT_FP_MIN = dt.date(2016, 1, 1)
STEP4_WELLS = Path("docs") / "box" / "step4-2026-10-09" / "wells_area_WCA.csv"
LOCAL_GOR_K = 15  # D30 / §6: median 12-mo GOR of the 15 nearest D9 cohort wells
FULL_MONTH_SHARE = 0.90  # a month is "fully reported" when it carries >= 90 % of the prior month's rows
OIL_DI_BOUNDS = (0.5, 4.0)
B_BOUNDS = (0.9, 1.2)
WATER_TC_DI_HI = 12.0  # D38: water type-curve fits run under water's own nominal Di cap (boxfit >= d3fabcc)
BOUND_TOL = 1e-3
SUBS = ("WCA_1", "WCA_2")
STREAM_UNIT = {"oil": "bbl", "gas": "mcf", "water": "bbl"}
RATE_UNIT = {"oil": "bopd", "gas": "mcfd", "water": "bwpd"}

_AREA_SQL = """
SELECT a.area_no, a.version, a.extent_id, extensions.ST_AsText(a.geom)
FROM box.tc_area a JOIN box.extent e USING (extent_id)
WHERE e.basin = %(basin)s AND e.bench = %(bench)s AND e.is_record AND a.is_record
ORDER BY a.area_no
"""
_MONTHS_SQL = """
SELECT prod_date, count(*) FROM curated.production
WHERE prod_date >= (date_trunc('month', now()) - interval '8 months')::date GROUP BY prod_date ORDER BY prod_date
"""
_PROD_SQL = """
SELECT api10, prod_date, oil_per_month_bbl, gas_per_month_mcf, water_per_month_bbl, producing_days,
       oil_per_day_bbl, gas_per_day_mcf, water_per_day_bbl
FROM curated.production
WHERE api10 = ANY(%(api10s)s) AND prod_date <= %(asof)s
ORDER BY api10, prod_date
"""
_META_SQL = "SELECT api10, subbasin, formation_blueox FROM curated.wells_enriched WHERE api10 = ANY(%(api10s)s)"
_MONTHLY = ("prod_date", "oil_bbl", "gas_mcf", "water_bbl", "producing_days", "rate_calday_bopd", "rate_calday_mcfd", "rate_calday_bwpd")


def _read(conn: Any, sql: str, params: dict[str, Any] | None = None) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, params or {})
        rows = cur.fetchall()
    conn.rollback()
    return rows


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------


def pull_areas(conn: Any) -> dict[str, Any]:
    rows = _read(conn, _AREA_SQL, {"basin": BASIN, "bench": POOL})
    if not rows:
        raise RuntimeError("no TC areas of record for delaware/WCA")
    versions = {(int(r[1]), int(r[2])) for r in rows}
    if len(versions) != 1:
        raise RuntimeError(f"expected one area version of record, found {versions}")
    nos = [int(r[0]) for r in rows]
    if nos != list(range(1, len(nos) + 1)):
        raise RuntimeError(f"area numbers not 1..n: {nos}")
    geoms = eg.to_ft([shapely.from_wkt(r[3]) for r in rows])
    (ver, eid), = versions
    return {"version": ver, "extent_id": eid, "geoms": geoms, "lonlat": [shapely.from_wkt(r[3]) for r in rows]}


def last_full_month(counts: Sequence[tuple[dt.date, int]], share: float = FULL_MONTH_SHARE) -> dt.date:
    """Latest month whose row count is >= `share` x the previous month's (reporting lag leaves the
    newest months thin — fitting them would read lag as decline)."""
    c = sorted(counts)
    best = c[0][0]
    for (_, n0), (d1, n1) in itertools.pairwise(c):
        if n1 >= share * n0:
            best = d1
        else:
            break
    return best


def pull_production(conn: Any, api10s: list[str], asof: dt.date, chunk: int = 2000) -> pd.DataFrame:
    frames = []
    for i in range(0, len(api10s), chunk):
        rows = _read(conn, _PROD_SQL, {"api10s": api10s[i : i + chunk], "asof": asof})
        frames.append(pd.DataFrame(rows, columns=["api10", *_MONTHLY]))
    return pd.concat(frames, ignore_index=True)


def pull_meta(conn: Any, api10s: list[str]) -> pd.DataFrame:
    return pd.DataFrame(_read(conn, _META_SQL, {"api10s": api10s}), columns=["api10", "subbasin", "we_formation_blueox"])


# ----------------------------------------------------------------------------
# Per-well fits (worker functions are module-level for the process pool)
# ----------------------------------------------------------------------------


def _quiet() -> None:
    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
    logging.getLogger().setLevel(logging.CRITICAL)


def fit_one(job: tuple[str, pd.DataFrame, str | None, str | None]) -> tuple[str, dict[str, Any]]:
    """Fit one well exactly as anduin's forecast_well does (no DB): prepare_monthly + fit_well_streams."""
    from boxfit.types import ForecastConfig
    from boxfit.well import fit_well_streams, prepare_monthly

    api10, monthly, subbasin, formation = job
    m = prepare_monthly(monthly.reset_index(drop=True).copy())
    cfg = ForecastConfig()
    res = fit_well_streams(m, config=cfg, subbasin=subbasin, formation_blueox=formation, api10=api10)
    out: dict[str, Any] = {}
    for s, r in res.items():
        out[s] = None if r is None else {"params": dict(r.params), "eur": float(r.eur), "r2": float(r.fit_r2), "n_points": int(r.n_points_fit),
                                          "fit_method": r.fit_method, "insufficient_history": bool(r.insufficient_history)}
    out["water_di_cap"] = float(cfg.water_di_nominal_hi_per_year)
    return api10, out


def fit_wells(prod: pd.DataFrame, meta: pd.DataFrame, workers: int | None = None) -> dict[str, dict[str, Any]]:
    md = meta.set_index("api10")
    jobs = [(a, g.drop(columns="api10"), md.at[a, "subbasin"] if a in md.index else None, md.at[a, "we_formation_blueox"] if a in md.index else None)
            for a, g in prod.groupby("api10", sort=True)]
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    if workers == 1:
        _quiet()
        return dict(fit_one(j) for j in jobs)
    with ProcessPoolExecutor(max_workers=workers, initializer=_quiet) as ex:
        return dict(ex.map(fit_one, jobs, chunksize=64))


def at_bound(stream: str, p: dict[str, Any], water_cap: float) -> dict[str, bool]:
    hi = water_cap if stream == "water" else OIL_DI_BOUNDS[1]
    di, b = float(p["Di"]), float(p["b"])
    return {"di_at_bound": abs(di - OIL_DI_BOUNDS[0]) < BOUND_TOL or abs(di - hi) < BOUND_TOL, "b_at_bound": abs(b - B_BOUNDS[0]) < BOUND_TOL or abs(b - B_BOUNDS[1]) < BOUND_TOL}


# ----------------------------------------------------------------------------
# Actuals (calendar months from the first reported month)
# ----------------------------------------------------------------------------


def actuals(prod: pd.DataFrame, asof: dt.date, windows: Sequence[int] = (6, 12, 24)) -> pd.DataFrame:
    """Per well: first reported month, full months to asof, cum oil / gas / water over the first k
    calendar months (NaN until k full months exist), GOR12 / GOR24 scf/bbl, and the calday rate
    series per stream (for the observed overlay)."""
    rows = []
    for a, g in prod.groupby("api10", sort=True):
        g = g.sort_values("prod_date")
        d0 = g["prod_date"].iloc[0]
        months = (asof.year - d0.year) * 12 + asof.month - d0.month + 1
        idx = np.array([(d.year - d0.year) * 12 + d.month - d0.month for d in g["prod_date"]])
        r: dict[str, Any] = {"api10": a, "first_month": d0, "months": months}
        for s, col in (("oil", "oil_bbl"), ("gas", "gas_mcf"), ("water", "water_bbl")):
            v = pd.to_numeric(g[col], errors="coerce").fillna(0.0).to_numpy(float)
            for k in windows:
                r[f"{s}{k}"] = float(v[idx < k].sum()) if months >= k else np.nan
        for k in (12, 24):
            r[f"gor{k}"] = 1000.0 * r[f"gas{k}"] / r[f"oil{k}"] if r[f"oil{k}"] and r[f"oil{k}"] > 0 else np.nan
        full = np.full(int(idx.max()) + 1, np.nan)
        for s, col in (("oil", "rate_calday_bopd"), ("gas", "rate_calday_mcfd"), ("water", "rate_calday_bwpd")):
            arr = full.copy()
            arr[idx] = pd.to_numeric(g[col], errors="coerce").fillna(0.0).to_numpy(float)
            r[f"rates_{s}"] = np.nan_to_num(arr, nan=0.0).tolist()
        rows.append(r)
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Frames
# ----------------------------------------------------------------------------


def sub_bench(df: pd.DataFrame, view: str) -> pd.Series:
    """D19 sub-bench per well. 'tag' = the warehouse formation_blueox (WCXY counts as WCA_1, D20;
    wells the gate-1 rule reassigned INTO the pool take their consensus suggestion). 'consensus' =
    'tag', but in-pool WCA_1 <-> WCA_2 consensus flags take the suggested sub-bench (a suggestion of
    WCXY is moot, D20)."""
    f = df["formation_blueox"].astype(str)
    sug = df["cons_suggest"].astype(object).where(df["cons_suggest"].notna(), None)
    out = f.where(f.isin(SUBS), None)
    out = out.where(f != "WCXY", "WCA_1")
    re = df["box_action"].eq("reassign") & sug.isin(SUBS)
    out = out.where(~re, sug)
    if view == "consensus":
        flip = df["cons_status"].eq("flag") & sug.isin(SUBS) & f.isin((*SUBS, "WCXY"))
        out = out.where(~flip, sug)
    return out


def assign_area(xy: np.ndarray, geoms: list[Any]) -> np.ndarray:
    tree = shapely.STRtree(geoms)
    pi, gi = tree.query(shapely.points(xy), predicate="intersects")
    out = np.zeros(len(xy), dtype=int)
    out[pi] = gi + 1
    return out


def neighbours(geoms: list[Any]) -> dict[int, list[int]]:
    """Edge-adjacent areas (shared boundary longer than ~200 ft, as in step 4's cell graph)."""
    nb: dict[int, list[int]] = {i + 1: [] for i in range(len(geoms))}
    buf = [shapely.buffer(g, 1.0) for g in geoms]
    for i in range(len(geoms)):
        for j in range(i + 1, len(geoms)):
            if buf[i].intersects(geoms[j]) and shapely.area(shapely.intersection(buf[i], geoms[j])) > 200.0:
                nb[i + 1].append(j + 1)
                nb[j + 1].append(i + 1)
    return nb


def build_frame(wells: pd.DataFrame, areas: dict[str, Any], act: pd.DataFrame, fits: dict[str, dict[str, Any]], asof: dt.date) -> pd.DataFrame:
    d = wells.copy()
    tr = eg._transformer()
    x, y = tr.transform(d["mid_lon"].to_numpy(float), d["mid_lat"].to_numpy(float))
    d["x"], d["y"] = np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT
    d["area_no"] = assign_area(d[["x", "y"]].to_numpy(), areas["geoms"])
    a_cols = [c for c in act.columns if not c.startswith("rates_")]
    d = d.drop(columns=[c for c in a_cols if c != "api10" and c in d.columns]).merge(act[a_cols], on="api10", how="left")
    d["lateral_ft"] = pd.to_numeric(d["lateral_length_ft"], errors="coerce")
    d["full12"] = d["months"].fillna(0) >= 12
    d["sub_tag"] = sub_bench(d, "tag")
    d["sub_cons"] = sub_bench(d, "consensus")
    for s in tc.STREAMS:
        d[f"fit_{s}"] = [bool(fits.get(a, {}).get(s)) for a in d["api10"]]
    o = [fits.get(a, {}).get("oil") for a in d["api10"]]
    d["oil_eur"] = [np.nan if f is None else f["eur"] for f in o]
    d["oil_eur_kft"] = d["oil_eur"] / d["lateral_ft"] * 1000.0
    d["oil_b"] = [np.nan if f is None else f["params"]["b"] for f in o]
    d["oil_di"] = [np.nan if f is None else f["params"]["Di"] for f in o]
    d["oil_di_eff"] = [np.nan if f is None else tc.effective_decline(f["params"]["Di"], f["params"]["b"]) for f in o]
    d["oil_r2"] = [np.nan if f is None else f["r2"] for f in o]
    cap = next((v["water_di_cap"] for v in fits.values()), 12.0)
    bnd = [at_bound("oil", f["params"], cap) if f else {"di_at_bound": False, "b_at_bound": False} for f in o]
    d["oil_di_at_bound"] = [b["di_at_bound"] for b in bnd]
    d["oil_b_at_bound"] = [b["b_at_bound"] for b in bnd]
    for k in (6, 12, 24):
        for s in tc.STREAMS:
            d[f"{s}{k}_kft"] = d[f"{s}{k}"] / d["lateral_ft"] * 1000.0
    d.attrs["asof"] = asof
    return d


def member(row: Any, fits: dict[str, dict[str, Any]], rates: dict[str, dict[str, list[float]]]) -> tc.Member:
    f = fits.get(row.api10, {})
    return tc.Member(api10=row.api10, lateral_ft=float(row.lateral_ft) if row.lateral_ft and row.lateral_ft > 0 else None,
                     params={s: (f.get(s) or {}).get("params") for s in tc.STREAMS}, rates=rates.get(row.api10, {}))


# ----------------------------------------------------------------------------
# Curves
# ----------------------------------------------------------------------------


def area_pools(d: pd.DataFrame, a: int, nb: dict[int, list[int]], mask: pd.Series | None = None) -> list[tuple[int, pd.DataFrame]]:
    """The D10 ladder pools for area `a` (optionally restricted by `mask`, e.g. one sub-bench):
    1 strict = the step-4 D9 cohort in the area; 2 relax lateral = any lateral > 0, first prod >= 2016,
    12 full months; 4 = rung 1 of the area and its edge neighbours; 5 = parent (the caller appends it).
    No rung 3: relaxing the vintage floor is retired (D37) — pre-2016 wells never enter a curve."""
    m = pd.Series(True, index=d.index) if mask is None else mask
    in_a = (d["area_no"] == a) & m
    base = d["full12"] & (d["lateral_ft"] > 0)
    fp16 = pd.Series([bool(fp and fp >= COHORT_FP_MIN) for fp in d["first_production_date"]], index=d.index)
    return [
        (1, d[in_a & d["c12"]]),
        (2, d[in_a & base & fp16]),
        (4, d[d["area_no"].isin([a, *nb[a]]) & m & d["c12"]]),
    ]


def climb_frames(pools: list[tuple[int, pd.DataFrame]], stream: str, fits: dict[str, dict[str, Any]], rates: dict[str, Any]) -> tuple[int, pd.DataFrame, bool]:
    mem = [(r, [member(x, fits, rates) for x in p.itertuples()]) for r, p in pools]
    rung, _, thin = tc.climb(mem, stream)
    return rung, dict(pools)[rung], thin


def build_area_curves(d: pd.DataFrame, fits: dict[str, dict[str, Any]], rates: dict[str, Any], nb: dict[int, list[int]], n_areas: int) -> dict[int, dict[str, Any]]:
    parent = d[d["c12"]]
    out: dict[int, dict[str, Any]] = {}
    for a in range(1, n_areas + 1):
        pools = [*area_pools(d, a, nb), (5, parent)]
        per_stream = {}
        for s in tc.STREAMS:
            rung, frame, thin = climb_frames(pools, s, fits, rates)
            per_stream[s] = (rung, frame, thin)
        # one curve per distinct pool (all three streams normally share rung 1)
        curves: dict[int, dict[str, Any]] = {}
        for s, (rung, frame, _) in per_stream.items():
            if rung not in curves:
                curves[rung] = tc.fit_curve([member(x, fits, rates) for x in frame.itertuples()])
        out[a] = {"streams": {s: {"rung": r, "thin": t, "api10s": list(f["api10"]), "curve": curves[r]} for s, (r, f, t) in per_stream.items()}}
    return out


def curve_rows(a: Any, cur: dict[str, Any], frame_by: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    """Flat rows per (stream, statistic) incl. the gas ratio and the curve-vs-actual cum check."""
    rows = []
    for s in tc.STREAMS:
        st = cur["streams"][s]
        c = st["curve"]
        mem = frame_by[s]
        stats = [tc.curve_row(c, s, k) for k in tc.STATS]
        if s == "gas":
            stats = [tc.gas_ratio_row(c), *[{**r, "mode": "arps (diagnostic)"} for r in stats]]
        for r in stats:
            r.update({"area_no": a, "rung": st["rung"], "rung_label": tc.RUNG_LABEL[st["rung"]], "thin": st["thin"],
                      "record": (r["stat"] == tc.RECORD_STAT and (r["mode"] == "ratio" if s == "gas" else r["mode"] == "arps"))})
            for k in (12, 24):
                act = mem[f"{s}{k}_kft"].dropna()
                r[f"actual_mean_cum{k}_kft"] = float(act.mean()) if len(act) else np.nan
                r[f"actual_n{k}"] = len(act)
                r[f"curve_vs_actual_cum{k}"] = r.get(f"cum{k}_kft", np.nan) / r[f"actual_mean_cum{k}_kft"] - 1.0 if len(act) and r.get(f"cum{k}_kft") else np.nan
            rows.append(r)
    return rows


# ----------------------------------------------------------------------------
# Gate tests
# ----------------------------------------------------------------------------


def subbench_sensitivity(d: pd.DataFrame, fits: dict[str, dict[str, Any]], rates: dict[str, Any], nb: dict[int, list[int]], n_areas: int,
                         area_curves: dict[int, dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """D19: fit WCA_1 and WCA_2 oil curves per area under both tag views through the same ladder
    (rung 5 = the pooled WCA area curve), plus within-area well-level contrasts."""
    rows = []
    for view, col in (("tag", "sub_tag"), ("consensus", "sub_cons")):
        for a in range(1, n_areas + 1):
            pooled = area_curves[a]["streams"]["oil"]["curve"]
            prow = tc.curve_row(pooled, "oil", tc.RECORD_STAT)
            for sb in SUBS:
                pools = area_pools(d, a, nb, mask=d[col] == sb)
                rung, frame, thin = climb_frames(pools, "oil", fits, rates)
                n_strict = int(tc.n_fitted([member(x, fits, rates) for x in pools[0][1].itertuples()], "oil"))
                if thin:  # rung 5: the pooled area curve is the parent
                    r = {**prow, "rung": 5, "n_wells": prow["n_wells"]}
                else:
                    r = {**tc.curve_row(tc.fit_curve([member(x, fits, rates) for x in frame.itertuples()]), "oil", tc.RECORD_STAT), "rung": rung}
                rows.append({"view": view, "area_no": a, "sub_bench": sb, "n_strict": n_strict, "rung": r["rung"], "n_wells": r.get("n_wells"),
                             "eur_per_kft": r.get("eur_per_kft"), "cum12_kft": r.get("cum12_kft"), "b": r.get("b"), "Di_nominal": r.get("Di_nominal"),
                             "Di_eff_1yr": r.get("Di_eff_1yr"), "pooled_eur_per_kft": prow.get("eur_per_kft"), "pooled_cum12_kft": prow.get("cum12_kft")})
    sb = pd.DataFrame(rows)
    summ: dict[str, Any] = {}
    coh = d[d["c12"] & d["fit_oil"]]
    for view, col in (("tag", "sub_tag"), ("consensus", "sub_cons")):
        w = sb[sb.view == view].pivot(index="area_no", columns="sub_bench", values=["eur_per_kft", "cum12_kft", "rung", "n_strict"])
        both = w[(w[("rung", "WCA_1")] == 1) & (w[("rung", "WCA_2")] == 1)]
        r_eur = (both[("eur_per_kft", "WCA_1")] / both[("eur_per_kft", "WCA_2")]).astype(float)
        r_c12 = (both[("cum12_kft", "WCA_1")] / both[("cum12_kft", "WCA_2")]).astype(float)
        c = coh[coh[col].isin(SUBS)]
        is2 = (c[col] == "WCA_2").astype(float)
        fe_eur = tc.within_slope(np.log(c["oil_eur_kft"]), is2, c["area_no"])
        fe_c12 = tc.within_slope(np.log(c["oil12_kft"].where(c["oil12_kft"] > 0)), is2, c["area_no"])
        summ[view] = {
            "n_wells": {s: int((c[col] == s).sum()) for s in SUBS},
            "areas_both_strict": len(both),
            "areas_one_or_none_strict": int(len(w) - len(both)),
            "rung_counts": {sb_: {str(int(k)): int(v) for k, v in sb[(sb.view == view) & (sb.sub_bench == sb_)]["rung"].value_counts().sort_index().items()} for sb_ in SUBS},
            "curve_ratio_wca1_over_wca2_eur": _dist(r_eur),
            "curve_ratio_wca1_over_wca2_cum12": _dist(r_c12),
            "areas_eur_gap_gt_10pct": int((np.abs(r_eur - 1) > 0.10).sum()),
            "well_fe_wca2_vs_wca1_log_eur_kft": fe_eur,
            "well_fe_wca2_vs_wca1_log_oil12_kft": fe_c12,
        }
    summ["n_wells_changing_sub_bench"] = int((coh["sub_tag"] != coh["sub_cons"]).sum())
    return sb, summ


def _dist(v: pd.Series) -> dict[str, float] | None:
    v = v.dropna()
    if not len(v):
        return None
    return {"n": len(v), "median": float(v.median()), "p25": float(v.quantile(0.25)), "p75": float(v.quantile(0.75)), "min": float(v.min()), "max": float(v.max())}


def gor_shape_tests(d: pd.DataFrame, fits: dict[str, dict[str, Any]], rates: dict[str, Any], n_areas: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Does oil b / nominal Di move with GOR inside an area? Well level: within-area slope of b, Di,
    effective Di on ln(GOR12). Curve level: split each area's strict cohort at its median GOR12,
    fit a mean curve per half (>= 10 wells each), compare."""
    c = d[d["c12"] & d["fit_oil"] & (d["gor12"] > 0)].copy()
    lg = np.log(c["gor12"])
    well: dict[str, Any] = {k: tc.within_slope(c[v], lg, c["area_no"]) for k, v in (("b", "oil_b"), ("Di_nominal", "oil_di"), ("Di_eff_1yr", "oil_di_eff"))}
    well["ln_eur_kft"] = tc.within_slope(np.log(c["oil_eur_kft"]), lg, c["area_no"])
    well["share_b_at_bound"] = float(c["oil_b_at_bound"].mean())
    well["share_di_at_bound"] = float(c["oil_di_at_bound"].mean())
    rows = []
    for a in range(1, n_areas + 1):
        ca = c[c["area_no"] == a]
        med = float(ca["gor12"].median()) if len(ca) else np.nan
        halves = {"low": ca[ca["gor12"] <= med], "high": ca[ca["gor12"] > med]}
        if min(len(h) for h in halves.values()) < tc.MIN_WELLS:
            rows.append({"area_no": a, "gor12_median": med, "n_low": len(halves["low"]), "n_high": len(halves["high"]), "fit": False})
            continue
        r: dict[str, Any] = {"area_no": a, "gor12_median": med, "n_low": len(halves["low"]), "n_high": len(halves["high"]), "fit": True}
        for k, h in halves.items():
            cr = tc.curve_row(tc.fit_curve([member(x, fits, rates) for x in h.itertuples()], stats=(tc.RECORD_STAT,)), "oil", tc.RECORD_STAT)
            r.update({f"{k}_gor12": float(h["gor12"].median()), f"{k}_b": cr.get("b"), f"{k}_Di_nominal": cr.get("Di_nominal"),
                      f"{k}_Di_eff_1yr": cr.get("Di_eff_1yr"), f"{k}_eur_per_kft": cr.get("eur_per_kft")})
        rows.append(r)
    t = pd.DataFrame(rows)
    f = t[t["fit"]]
    curve = {"n_areas_split": len(f),
             "b_high_minus_low": _dist(f["high_b"] - f["low_b"]) if len(f) else None,
             "Di_nominal_high_minus_low": _dist(f["high_Di_nominal"] - f["low_Di_nominal"]) if len(f) else None,
             "Di_eff_high_minus_low": _dist(f["high_Di_eff_1yr"] - f["low_Di_eff_1yr"]) if len(f) else None,
             "eur_ratio_high_over_low": _dist(f["high_eur_per_kft"] / f["low_eur_per_kft"]) if len(f) else None,
             "areas_high_steeper_di_nominal": int((f["high_Di_nominal"] > f["low_Di_nominal"]).sum()) if len(f) else 0}
    return t, {"well_level": well, "curve_level": curve, "n_wells": len(c)}


def r2_log(actual: pd.Series, pred: pd.Series) -> float:
    a, p = np.log(actual), np.log(pred)
    ok = np.isfinite(a) & np.isfinite(p)
    a, p = a[ok], p[ok]
    return float(1.0 - ((a - p) ** 2).sum() / ((a - a.mean()) ** 2).sum()) if len(a) > 2 else np.nan


def gas_level_test(d: pd.DataFrame, area_rows: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """D30 check, held out: each cohort well's local GOR12 is the median of its 15 nearest OTHER D9
    cohort wells. Predict its 12-mo and 24-mo GOR by (a) its area's ratio curve alone, (b) the local
    level x the area's shape (the D30 composition), (c) the local level held flat."""
    c = d[d["c12"] & (d["gor12"] > 0)].copy()
    xy = c[["x", "y"]].to_numpy()
    _, j = cKDTree(xy).query(xy, k=LOCAL_GOR_K + 1)
    g = c["gor12"].to_numpy()
    c["local_gor12"] = [float(np.median(g[jj[1:]])) for jj in j]
    rec = area_rows[(area_rows["stream"] == "gas") & (area_rows["mode"] == "ratio")].set_index("area_no")
    c["tc_gor12"] = c["area_no"].map(rec["gor12_scf_bbl"])
    c["tc_gor24"] = c["area_no"].map(rec["gor24_scf_bbl"])
    c["pred24_area"] = c["tc_gor24"]
    c["pred24_d30"] = c["local_gor12"] * c["tc_gor24"] / c["tc_gor12"]
    c["pred24_flat"] = c["local_gor12"]
    h24 = c[c["gor24"] > 0]
    res = {
        "n12": len(c), "n24": len(h24),
        "gor12_r2_log": {"area_curve": r2_log(c["gor12"], c["tc_gor12"]), "local_level": r2_log(c["gor12"], c["local_gor12"])},
        "gor24_r2_log": {"area_curve": r2_log(h24["gor24"], h24["pred24_area"]), "local_x_area_shape_D30": r2_log(h24["gor24"], h24["pred24_d30"]),
                         "local_level_flat": r2_log(h24["gor24"], h24["pred24_flat"])},
        "gor24_median_ratio_actual_over_pred": {"area_curve": float((h24["gor24"] / h24["pred24_area"]).median()),
                                               "local_x_area_shape_D30": float((h24["gor24"] / h24["pred24_d30"]).median()),
                                               "local_level_flat": float((h24["gor24"] / h24["pred24_flat"]).median())},
        "alpha_shift_ln": _dist(np.log(c["local_gor12"] / c["tc_gor12"])),
    }
    return c[["api10", "area_no", "gor12", "gor24", "local_gor12", "tc_gor12", "tc_gor24", "pred24_d30"]], res


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------


def area_png(a: int, cur: dict[str, Any], obs: dict[str, Any], title: str) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(15, 3.9))
    months = np.arange(121)
    for ax, s in zip(axes, tc.STREAMS):
        c = cur["streams"][s]["curve"]
        st = c["agg"].streams[s]
        p10 = np.array([np.nan if v is None else v for v in st.p10[:121]], float)
        p90 = np.array([np.nan if v is None else v for v in st.p90[:121]], float)
        ax.fill_between(months, p90, p10, color="#bfdbfe", alpha=0.6, lw=0, label="forecast P10–P90 (P10 = high)")
        o = obs[s]
        om = np.array([np.nan if (v is None or n < 5) else v for v, n in zip(o.mean[:121], o.well_count[:121])], float)
        ax.plot(np.arange(len(om)), om, ".", ms=3, color="#111827", label="observed mean (≥ 5 wells)")
        f_mean = c["fits"][s].get("mean")
        f_p50 = c["fits"][s].get("p50")
        if s == "gas" and c.get("gas_ratio"):
            ax.plot(months, c["gas_ratio"]["smoothed_rate"][:121], "-", color="#dc2626", lw=2, label="record: GOR ratio × mean oil")
            if f_mean:
                ax.plot(months, tc.oil_grid(f_mean)[:121], ":", color="#6b7280", lw=1.4, label="mean Arps (diagnostic)")
        elif f_mean:
            ax.plot(months, tc.oil_grid(f_mean)[:121], "-", color="#dc2626", lw=2, label="record: mean fit")
        if f_p50 and s != "gas":
            ax.plot(months, tc.oil_grid(f_p50)[:121], "--", color="#2563eb", lw=1.3, label="P50 fit")
        ax.set_yscale("log")
        ax.set_xlim(0, 120)
        lo = np.nanmin(p90[1:]) if np.isfinite(p90[1:]).any() else 1.0
        ax.set_ylim(max(lo * 0.5, 1e-2), None)
        ax.set_title(f"{s} — {RATE_UNIT[s]} per 1,000 ft · n {cur['streams'][s]['curve']['n_by_stream'][s]} · rung {cur['streams'][s]['rung']}", fontsize=9)
        ax.set_xlabel("months on the aligned panel", fontsize=8)
        ax.grid(alpha=0.3, which="both")
        ax.tick_params(labelsize=8)
        if s == "oil" or s == "gas":
            ax.legend(fontsize=7, loc="upper right")
    fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    return _png(fig, dpi=72)


_MAP_JS = """
<link rel=stylesheet href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'>
<script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script>
<script>
const D = __DATA__;
const map = L.map('map', {preferCanvas: true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {attribution: 'Esri', maxZoom: 16}).addTo(map);
const vals = D.areas.map(a => a.eur).filter(v => v != null).sort((a, b) => a - b);
const lo = vals[Math.floor(vals.length * 0.05)], hi = vals[Math.floor(vals.length * 0.95)];
const ramp = ['#fff7ec','#fee8c8','#fdd49e','#fdbb84','#fc8d59','#ef6548','#d7301f','#990000'];
function col(v) { if (v == null) return '#e5e7eb'; const t = Math.max(0, Math.min(0.999, (v - lo) / (hi - lo))); return ramp[Math.floor(t * ramp.length)]; }
const grp = L.featureGroup().addTo(map);
D.areas.forEach(a => {
  const p = L.polygon(a.rings, {color: '#374151', weight: 1, fillColor: col(a.eur), fillOpacity: 0.75}).addTo(grp);
  p.bindTooltip(`<b>area ${a.no}</b><br>oil ${a.eur ? Math.round(a.eur).toLocaleString() : '–'} bbl/1,000 ft (mean, 50-yr)<br>n ${a.n} · rung ${a.rung}`);
  p.on('click', () => { const el = document.getElementById('area' + a.no); if (el) el.scrollIntoView({behavior: 'smooth'}); });
  L.marker(a.label, {icon: L.divIcon({className: 'albl', html: `${a.no}<br>${a.eur ? (a.eur / 1000).toFixed(0) : '–'}k`, iconSize: [40, 24]})}).addTo(map);
});
map.fitBounds(grp.getBounds());
document.getElementById('legend').innerHTML = 'oil EUR per 1,000 ft (mean curve, 50-yr technical): ' + ramp.map((c, i) => `<span style="background:${c}"></span>${Math.round((lo + (hi - lo) * i / ramp.length) / 1000)}k`).join(' ');
</script>
"""


def _rings(g: Any, tol: float = 1e-4) -> list[list[list[float]]]:
    g = shapely.simplify(g, tol)
    polys = list(g.geoms) if hasattr(g, "geoms") else [g]
    return [[[round(y, 5), round(x, 5)] for x, y in p.exterior.coords] for p in polys if not p.is_empty]


def render_page(ctx: dict[str, Any]) -> str:
    summ, ar = ctx["summary"], ctx["area_table"]
    sb, gor, gas = summ["subbench"], summ["gor_shape"], summ["gas_level"]
    map_data = {"areas": [{"no": int(r.area_no), "eur": None if not np.isfinite(r.oil_eur_kft) else float(r.oil_eur_kft), "n": int(r.n_oil), "rung": int(r.rung_oil),
                           "rings": _rings(g), "label": [round(g.representative_point().y, 5), round(g.representative_point().x, 5)]}
                          for r, g in zip(ar.itertuples(), ctx["areas"]["lonlat"])]}
    fmt = {"oil_qi": ",.0f", "oil_Di_nominal": ".2f", "oil_Di_eff_1yr": ".0%", "oil_b": ".2f", "oil_eur_kft": ",.0f", "oil_p50_eur_kft": ",.0f", "mean_over_p50": ".2f",
           "gas_eur_kft": ",.0f", "gas_gor12": ",.0f", "gas_beta_e6": ".2f", "water_eur_kft": ",.0f", "water_Di_nominal": ".2f", "oil_cum12_vs_actual": "+.1%",
           "gas_cum12_vs_actual": "+.1%", "area_gor12_actual": ",.0f", "gas_eur_kft_at_area_gor": ",.0f", "gas_cum12_vs_actual_at_area_gor": "+.1%", "max_reconcile": ".2e", "fp_year_p50": ".0f"}
    sb_rows = []
    for view in ("tag", "consensus"):
        v = sb[view]
        sb_rows.append({"view": view, "WCA_1 wells": v["n_wells"]["WCA_1"], "WCA_2 wells": v["n_wells"]["WCA_2"], "areas with both strict": v["areas_both_strict"],
                        "curve EUR WCA_1/WCA_2 median": (v["curve_ratio_wca1_over_wca2_eur"] or {}).get("median", np.nan),
                        "IQR": f"{(v['curve_ratio_wca1_over_wca2_eur'] or {}).get('p25', np.nan):.2f}–{(v['curve_ratio_wca1_over_wca2_eur'] or {}).get('p75', np.nan):.2f}",
                        "areas |gap| > 10 %": v["areas_eur_gap_gt_10pct"],
                        "well FE: WCA_2 vs WCA_1, EUR/kft": math.expm1((v["well_fe_wca2_vs_wca1_log_eur_kft"] or {}).get("slope", np.nan)),
                        "± 1 SE": math.expm1((v["well_fe_wca2_vs_wca1_log_eur_kft"] or {}).get("slope", np.nan) + (v["well_fe_wca2_vs_wca1_log_eur_kft"] or {}).get("se", np.nan)) - math.expm1((v["well_fe_wca2_vs_wca1_log_eur_kft"] or {}).get("slope", np.nan)),
                        "well FE: WCA_2 vs WCA_1, cum-12/kft": math.expm1((v["well_fe_wca2_vs_wca1_log_oil12_kft"] or {}).get("slope", np.nan))})
    wl = gor["well_level"]
    gor_rows = [{"quantity": k, "within-area slope per ln(GOR12)": wl[k]["slope"], "SE": wl[k]["se"], "t": wl[k]["t"],
                 "effect across the GOR12 IQR": wl[k]["slope"] * wl[k]["x_iqr"]} for k in ("b", "Di_nominal", "Di_eff_1yr", "ln_eur_kft") if wl.get(k)]
    cards = []
    for r in ar.itertuples():
        a = int(r.area_no)
        mem = ctx["members"][ctx["members"]["area_no"] == a]
        cards.append(
            f"<h3 id=area{a}>Area {a} — oil {r.oil_eur_kft:,.0f} bbl/1,000 ft (mean) · P50 {r.oil_p50_eur_kft:,.0f} · gas {r.gas_eur_kft:,.0f} mcf/1,000 ft · "
            f"water {r.water_eur_kft:,.0f} bbl/1,000 ft</h3>"
            f"<div class=meta>n oil {r.n_oil} / gas {r.n_gas} / water {r.n_water} · rung oil {r.rung_oil} gas {r.rung_gas} water {r.rung_water} · oil qi {r.oil_qi:,.0f} bopd/kft, "
            f"Di {r.oil_Di_nominal:.2f}/yr nominal = {r.oil_Di_eff_1yr:.0%} 1-yr effective, b {r.oil_b:.2f}, Df 0.08 · gas = GOR ratio (12-mo GOR {r.gas_gor12:,.0f} scf/bbl) · "
            f"median first prod {r.fp_year_p50:.0f} · top operator {html.escape(str(r.top_operator))} ({r.top_operator_share:.0%})</div>"
            f"<img src='{ctx['pngs'][a]}'>"
            f"<details><summary>{len(mem)} members (strict D9 cohort, rung 1)</summary>"
            + _table(mem.drop(columns=["area_no"]), {"lateral_ft": ",.0f", "oil_eur_kft": ",.0f", "oil_b": ".2f", "oil_di": ".2f", "oil12_kft": ",.0f", "gor12": ",.0f"})
            + "</details>"
        )
    parts = [
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>WCA baseline curves</title>",
        f"<style>{_CSS} #map{{height:640px}} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}} .albl{{font:10px/1.15 sans-serif;text-align:center;color:#111827;text-shadow:0 0 3px #fff,0 0 3px #fff}} #legend span{{display:inline-block;width:18px;height:10px;margin:0 3px 0 8px;vertical-align:middle;border:1px solid #e5e7eb}}</style></head><body>",
        f"<h1>BOX step 5b — baseline type curves, WCA (Delaware), {len(ar)} TC areas</h1>",
        (f"<div class=meta>built {summ['built_at']} · TC areas of record box.tc_area v{summ['area_version']} on extent {summ['extent_id']} · well set wells_final_WCA.csv minus exclusions.csv "
         f"({summ['n_excluded']} wells) · production curated.production through {summ['prod_asof']} (last fully reported month) · fitting engine blueox-boxfit @ {summ['boxfit_sha'][:7]} · read-only</div>"),
        ("<div class='flag'>Curve of record = the cohort <b>MEAN</b> per 1,000 ft of lateral (labelled mean, never P50): the panel is every member's ramp + Arps forecast (anduin's per-well fit), "
         "peak_ramp aligned, normalized per 1,000 ft; the mean series is fitted with ramp + modified-hyperbolic Arps (b ∈ [0.9, 1.2], Df 0.08/yr Delaware). EUR = raw 50-yr technical integral, no economic limit. "
         "Di is NOMINAL per year with the 1-yr effective (secant) decline beside it. P10 = HIGH. Gas = GOR ratio mode on the mean oil curve (D30); the gas Arps fit is a diagnostic. Water = independent Arps.</div>"),
        "<h2>Area map</h2><div class=meta>Click an area to jump to its card.</div><div id=legend class=meta></div><div id=map></div>",
        ("<h2>Areas</h2><div class=meta>oil_* = record (mean) fit; oil_p50_eur_kft = the P50 fit's EUR; mean_over_p50 = record / P50 EUR. cum12_vs_actual = the record curve's 12-mo cum vs the members' mean actual 12-mo cum per 1,000 ft (calendar months from first report). "
        "gas_* = the area ratio curve as fitted; *_at_area_gor = the same curve shifted (D30) to the members' own 12-mo GOR — the area supplies shape, the location supplies level. "
         "max_reconcile = worst |stored − trapezoid| / stored over the area's Arps fits (rule 6, must be < 0.1 %).</div>"),
        _table(ar.drop(columns=["top_operator"]), fmt),
        "<h2>Gate question: WCA_1 vs WCA_2 (D19)</h2>",
        (f"<div class=meta>Per area, a WCA_1 and a WCA_2 oil curve through the same ladder (rung 5 = the pooled WCA area curve). 'tag' = warehouse formation_blueox (WCXY → WCA_1, D20); 'consensus' = tag with the in-pool consensus "
         f"flags applied ({sb['n_wells_changing_sub_bench']} cohort wells change sub-bench). Well FE = within-area contrast of per-well 50-yr oil EUR/kft and 12-mo cum/kft, WCA_2 relative to WCA_1.</div>"),
        _table(pd.DataFrame(sb_rows), {"curve EUR WCA_1/WCA_2 median": ".3f", "well FE: WCA_2 vs WCA_1, EUR/kft": "+.1%", "± 1 SE": ".1%", "well FE: WCA_2 vs WCA_1, cum-12/kft": "+.1%"}),
        "<h2>Gate question: do oil b / Di move with GOR inside an area? (report, don't act)</h2>",
        (f"<div class=meta>Well level, {gor['n_wells']:,} cohort wells with an oil fit and a 12-mo GOR: within-area OLS on ln(GOR12). {wl['share_b_at_bound']:.0%} of per-well b sit at a bound "
         f"(0.9 / 1.2) and {wl['share_di_at_bound']:.0%} of Di — bounded parameters damp the well-level slopes; the curve-level split below is the cleaner read.</div>"),
        _table(pd.DataFrame(gor_rows), {"within-area slope per ln(GOR12)": "+.3f", "SE": ".3f", "t": "+.1f", "effect across the GOR12 IQR": "+.3f"}),
        (f"<div class=meta>Curve level ({gor['curve_level']['n_areas_split']} areas split at their median GOR12, ≥ 10 wells per half): high − low b {_fmtd(gor['curve_level']['b_high_minus_low'], '+.3f')}; "
        f"nominal Di {_fmtd(gor['curve_level']['Di_nominal_high_minus_low'], '+.2f')}/yr; 1-yr effective {_fmtd(gor['curve_level']['Di_eff_high_minus_low'], '+.3f')}; EUR high/low {_fmtd(gor['curve_level']['eur_ratio_high_over_low'], '.2f')}.</div>"),
        "<h2>Gas level check (D30, held out)</h2>",
        (f"<div class=meta>{gas['n24']:,} cohort wells with 24 months: predict each well's 24-mo GOR from its 15 nearest OTHER cohort wells' 12-mo GOR (the local level) × its area curve's GOR24/GOR12 shape. "
         f"R² of ln GOR24 — area curve alone {gas['gor24_r2_log']['area_curve']:.2f}; local level × area shape (D30) {gas['gor24_r2_log']['local_x_area_shape_D30']:.2f}; local level held flat {gas['gor24_r2_log']['local_level_flat']:.2f}. "
         f"Median actual/predicted: {gas['gor24_median_ratio_actual_over_pred']['area_curve']:.2f} / {gas['gor24_median_ratio_actual_over_pred']['local_x_area_shape_D30']:.2f} / {gas['gor24_median_ratio_actual_over_pred']['local_level_flat']:.2f}.</div>"),
        "<h2>Area cards</h2><div class=meta>Blue band = cross-well P10–P90 of the members' forecasts; dots = observed mean on the same aligned panel (months with ≥ 5 wells); red = record curve; blue dashed = P50 fit.</div>",
        *cards,
        _MAP_JS.replace("__DATA__", json.dumps(map_data, separators=(",", ":"))),
        "</body></html>",
    ]
    return "\n".join(parts)


def _fmtd(dd: dict[str, float] | None, f: str) -> str:
    if not dd:
        return "–"
    return f"median {format(dd['median'], f)} (IQR {format(dd['p25'], f)} to {format(dd['p75'], f)}, n {dd['n']})"


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------


def area_gas_at_own_level(d: pd.DataFrame, curves: dict[int, dict[str, Any]]) -> dict[int, dict[str, float]]:
    """D30 at the area grain: shift each area's ratio curve to its OWN members' 12-mo GOR (sum gas /
    sum oil over the gas pool) and compare the shifted curve's 12-mo gas with the members' actual mean."""
    out = {}
    for a, cur in curves.items():
        st = cur["streams"]["gas"]
        mem = d[d.api10.isin(st["api10s"]) & (d["oil12"] > 0)]
        lvl = 1000.0 * mem["gas12"].sum() / mem["oil12"].sum() if len(mem) else np.nan
        sh = tc.shift_gor_level(st["curve"], lvl) if np.isfinite(lvl) else None
        act = mem["gas12_kft"].dropna()
        out[a] = {"area_gor12_actual": lvl, "gas_eur_kft_at_area_gor": np.nan if not sh else sh["eur_per_kft"],
                  "gas_cum12_vs_actual_at_area_gor": np.nan if (not sh or not len(act)) else tc.cum_months(sh["gas_rates"], 12) / act.mean() - 1.0}
    return out


def area_table(d: pd.DataFrame, rows: pd.DataFrame, n_areas: int) -> pd.DataFrame:
    out = []
    for a in range(1, n_areas + 1):
        R = rows[rows.area_no == a]

        def g(stream: str, stat: str, mode: str = "arps", col: str = "eur_per_kft", R: pd.DataFrame = R) -> Any:
            x = R[(R.stream == stream) & (R.stat == stat) & (R["mode"] == mode)]
            return x[col].iloc[0] if len(x) and col in x and pd.notna(x[col].iloc[0]) else np.nan

        coh = d[(d.area_no == a) & d.c12]
        ops = coh["operator"].value_counts()
        rec_oil = R[(R.stream == "oil") & (R.stat == "mean")]
        rec_gas = R[(R.stream == "gas") & (R["mode"] == "ratio")]
        out.append({
            "area_no": a, "n_oil": int(g("oil", "mean", col="n_wells")), "n_gas": int(g("gas", "mean", "ratio", "n_wells")), "n_water": int(g("water", "mean", col="n_wells")),
            "rung_oil": int(rec_oil["rung"].iloc[0]), "rung_gas": int(rec_gas["rung"].iloc[0]), "rung_water": int(R[(R.stream == "water")]["rung"].iloc[0]),
            "oil_qi": g("oil", "mean", col="qi"), "oil_Di_nominal": g("oil", "mean", col="Di_nominal"), "oil_Di_eff_1yr": g("oil", "mean", col="Di_eff_1yr"),
            "oil_b": g("oil", "mean", col="b"), "oil_eur_kft": g("oil", "mean"), "oil_p50_eur_kft": g("oil", "p50"),
            "mean_over_p50": g("oil", "mean") / g("oil", "p50"),
            "gas_eur_kft": g("gas", "mean", "ratio"), "gas_gor12": g("gas", "mean", "ratio", "gor12_scf_bbl"), "gas_beta_e6": g("gas", "mean", "ratio", "beta") * 1e6,
            "water_eur_kft": g("water", "mean"), "water_Di_nominal": g("water", "mean", col="Di_nominal"),
            "oil_cum12_vs_actual": g("oil", "mean", col="curve_vs_actual_cum12"), "gas_cum12_vs_actual": g("gas", "mean", "ratio", "curve_vs_actual_cum12"),
            "max_reconcile": float(np.nanmax(np.abs(R["reconcile"].astype(float)))) if R["reconcile"].notna().any() else np.nan,
            "fp_year_p50": float(pd.Series([fp.year for fp in coh["first_production_date"]]).median()) if len(coh) else np.nan,
            "top_operator": ops.index[0] if len(ops) else "", "top_operator_share": float(ops.iloc[0] / ops.sum()) if len(ops) else np.nan,
        })
    return pd.DataFrame(out)


def run(conn: Any, wells_dir: Path, out: Path, boxfit_sha: str, workers: int | None = None, asof: dt.date | None = None) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    wells, excluded = exclusions.drop(egr.load_final_sets(wells_dir, (POOL,)))
    areas = pull_areas(conn)
    n_areas = len(areas["geoms"])
    asof = asof or last_full_month(_read(conn, _MONTHS_SQL))  # --asof pins a re-run to the record cutoff
    # every well that can sit in any ladder pool: in an area, real lateral
    tr = eg._transformer()
    x, y = tr.transform(wells["mid_lon"].to_numpy(float), wells["mid_lat"].to_numpy(float))
    in_area = assign_area(np.column_stack([np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT]), areas["geoms"]) > 0
    cand = wells[in_area & (pd.to_numeric(wells["lateral_length_ft"], errors="coerce") > 0)]
    ids = sorted(cand["api10"])
    prod = pull_production(conn, ids, asof)
    meta = pull_meta(conn, ids)
    act = actuals(prod, asof)
    fits = fit_wells(prod, meta, workers)
    rates = {r.api10: {s: getattr(r, f"rates_{s}") for s in tc.STREAMS} for r in act.itertuples()}
    d = build_frame(wells, areas, act, fits, asof)
    # strict cohort = the step-4 D9 12-mo cohort, carried by identity
    s4 = pd.read_csv(STEP4_WELLS, dtype={"api10": str})
    s4c = s4[s4["c12"].astype(str).str.lower().eq("true")][["api10", "area_no"]]
    d = d.merge(s4c.rename(columns={"area_no": "area_no_step4"}), on="api10", how="left")
    d["c12"] = d["area_no_step4"].notna()
    mism = d[d.c12 & (d.area_no != d.area_no_step4)]
    if len(mism) or int(d.c12.sum()) != len(s4c):
        raise RuntimeError(f"area membership identity failed: {len(mism)} cohort wells moved, {int(d.c12.sum())} vs {len(s4c)} cohort wells")
    nb = neighbours(areas["geoms"])
    curves = build_area_curves(d, fits, rates, nb, n_areas)
    rows = []
    for a, cur in curves.items():
        frame_by = {s: d[d.api10.isin(cur["streams"][s]["api10s"])] for s in tc.STREAMS}
        rows += curve_rows(a, cur, frame_by)
    basin = tc.fit_curve([member(r_, fits, rates) for r_ in d[d.c12].itertuples()])
    bcur = {"streams": {s: {"rung": 5, "thin": False, "curve": basin} for s in tc.STREAMS}}
    rows += curve_rows("pool", bcur, {s: d[d.c12] for s in tc.STREAMS})
    crow = pd.DataFrame(rows)
    area_rows = crow[crow.area_no != "pool"].copy()
    area_rows["area_no"] = area_rows["area_no"].astype(int)
    at = area_table(d, area_rows, n_areas)
    own = area_gas_at_own_level(d, curves)
    at.insert(at.columns.get_loc("gas_gor12") + 1, "area_gor12_actual", [own[a]["area_gor12_actual"] for a in at["area_no"]])
    pos = at.columns.get_loc("gas_cum12_vs_actual") + 1
    at.insert(pos, "gas_cum12_vs_actual_at_area_gor", [own[a]["gas_cum12_vs_actual_at_area_gor"] for a in at["area_no"]])
    at.insert(pos, "gas_eur_kft_at_area_gor", [own[a]["gas_eur_kft_at_area_gor"] for a in at["area_no"]])
    # sensitivity: the pool curve without the wells whose oil Di is pinned at a bound (anduin would
    # flag them for review; BOX keeps them — reported, not decided)
    ex = d[d.c12 & ~d["oil_di_at_bound"]]
    ex_curve = tc.fit_curve([member(r_, fits, rates) for r_ in ex.itertuples()], stats=(tc.RECORD_STAT,))
    ex_row = tc.curve_row(ex_curve, "oil", tc.RECORD_STAT)
    ex_act = ex["oil12_kft"].dropna()
    sbt, sbs = subbench_sensitivity(d, fits, rates, nb, n_areas, curves)
    gt, gs = gor_shape_tests(d, fits, rates, n_areas)
    gl, gls = gas_level_test(d, area_rows)
    # observed overlay per area (strict pool, same anchors as the curve)
    pngs = {}
    for a in range(1, n_areas + 1):
        cur = curves[a]
        obs = {}
        for s in tc.STREAMS:
            mem = [member(r_, fits, rates) for r_ in d[d.api10.isin(cur["streams"][s]["api10s"])].itertuples()]
            oa = tc.aggregate(tc.observed_panel(mem, cur["streams"][s]["curve"]["anchors"], 121), normalization_basis="per_lateral_ft", alignment_method="peak_ramp", n_months=121)
            obs[s] = oa.streams[s]
        pngs[a] = area_png(a, cur, obs, f"Area {a}")
    members = d[d.c12][["area_no", "api10", "well_name", "operator", "formation_blueox", "sub_tag", "sub_cons", "first_production_date", "lateral_ft", "months",
                        "fit_oil", "fit_gas", "fit_water", "oil_eur_kft", "oil_b", "oil_di", "oil_di_at_bound", "oil12_kft", "gor12"]].sort_values(["area_no", "api10"])
    members["included"] = members["fit_oil"]
    members["drop_reason"] = np.where(members["fit_oil"], "", "no oil fit")
    worst_rec = float(np.nanmax(np.abs(crow["reconcile"].astype(float))))
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    coh = d[d.c12]
    summ = {
        "built_at": built, "prod_asof": str(asof), "boxfit_sha": boxfit_sha, "area_version": areas["version"], "extent_id": areas["extent_id"], "n_areas": n_areas,
        "n_excluded": len(excluded), "n_wells_fitted": len(fits), "n_cohort": len(coh),
        "n_cohort_fit": {s: int(coh[f"fit_{s}"].sum()) for s in tc.STREAMS},
        "cohort_oil_di_at_bound": float(coh.loc[coh.fit_oil, "oil_di_at_bound"].mean()), "cohort_oil_b_at_bound": float(coh.loc[coh.fit_oil, "oil_b_at_bound"].mean()),
        "record_stat": tc.RECORD_STAT, "max_abs_reconcile": worst_rec, "reconcile_pass": worst_rec < tc.RECONCILE_TOL,
        "rungs": {s: {str(k): int(v) for k, v in at[f"rung_{s}"].value_counts().sort_index().items()} for s in tc.STREAMS},
        "pool_curve": {r["stream"] + ("_ratio" if r["mode"] == "ratio" else "") + "_" + r["stat"]: {k: r.get(k) for k in ("eur_per_kft", "qi", "Di_nominal", "Di_eff_1yr", "b", "alpha", "beta", "gor12_scf_bbl", "cum12_kft", "curve_vs_actual_cum12", "n_wells")}
                       for r in rows if r["area_no"] == "pool"},
        "area_eur_kft_oil": _dist(at["oil_eur_kft"]), "mean_over_p50": _dist(at["mean_over_p50"]),
        "oil_cum12_vs_actual": _dist(at["oil_cum12_vs_actual"]), "gas_cum12_vs_actual": _dist(at["gas_cum12_vs_actual"]),
        "water_di_at_cap_areas": int((area_rows[(area_rows.stream == "water") & (area_rows.stat == "mean")]["Di_nominal"] >= WATER_TC_DI_HI - BOUND_TOL).sum()),
        "subbench": sbs, "gor_shape": gs, "gas_level": gls,
        "gas_cum12_vs_actual_at_area_gor": _dist(at["gas_cum12_vs_actual_at_area_gor"]),
        "pool_ex_oil_di_at_bound": {"n_wells": ex_row.get("n_wells"), "eur_per_kft": ex_row.get("eur_per_kft"), "Di_nominal": ex_row.get("Di_nominal"),
                                    "Di_eff_1yr": ex_row.get("Di_eff_1yr"), "b": ex_row.get("b"), "cum12_kft": ex_row.get("cum12_kft"),
                                    "curve_vs_actual_cum12": ex_row.get("cum12_kft", np.nan) / ex_act.mean() - 1.0 if len(ex_act) else None},
    }
    ctx = {"summary": summ, "area_table": at, "areas": areas, "members": members, "pngs": pngs}
    (out / f"curves_{POOL}.html").write_text(render_page(ctx), encoding="utf-8")
    crow.drop(columns=[c for c in crow.columns if c in ("smoothed_rate",)], errors="ignore").to_csv(out / f"curves_{POOL}.csv", index=False)
    at.to_csv(out / f"areas_{POOL}.csv", index=False)
    members.to_csv(out / f"members_{POOL}.csv", index=False)
    sbt.to_csv(out / f"subbench_{POOL}.csv", index=False)
    gt.to_csv(out / f"gor_split_{POOL}.csv", index=False)
    gl.to_csv(out / f"gas_level_{POOL}.csv", index=False)
    wf = []
    for a_, f in sorted(fits.items()):
        r_ = {"api10": a_}
        for s in tc.STREAMS:
            p = (f.get(s) or {}).get("params") or {}
            r_.update({f"{s}_{k}": p.get(k) for k in ("qo", "qi", "Di", "b", "Df", "peak_index_months", "onset_index_months")})
            r_[f"{s}_eur"] = (f.get(s) or {}).get("eur")
            r_[f"{s}_r2"] = (f.get(s) or {}).get("r2")
        wf.append(r_)
    pd.DataFrame(wf).to_csv(out / f"well_fits_{POOL}.csv", index=False)
    (out / "summary.json").write_text(json.dumps(_clean(summ), indent=2, default=_json), encoding="utf-8")
    return {"summary": summ, "area_table": at, "frame": d, "curves": curves, "fits": fits}


def _clean(o: Any) -> Any:
    """NaN / inf -> None recursively (summary.json stays strict JSON)."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def _json(o: Any) -> Any:
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    return None
