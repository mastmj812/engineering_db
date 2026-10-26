"""BOX step 18 — Midland scope + value-case evidence pack (pure; decision only, nothing stored).

Plan docs/box_type_curves_plan.md PHASE 3 step 18: per Midland bench a card (TVD, spacing, operator mix, vintage,
analog-distance spread) next to the plan's headline table, so Michael can decide (a)-(g). This module holds the
DB-free arithmetic; scripts/box_midland_scope.py pulls (read-only) and renders.

Definitions (the plan's Phase-3 evidence table, verbatim):
  modern     horizontal, first production >= 2016-01-01, completed lateral 5,000-15,000 ft (the r2 analog band, D121)
  oil        median 12-month calendar-day oil per 1,000 ft, wells first-producing 2016-01 ... 2025-07
  undrilled  reconciled Novi sticks with status NULL / remaining_pud / conflict (PUD + RES, D117); PUD-only alongside
Analog reach is a GEOMETRY proxy for the r2 selection (same bench, nearest-first, modern producers with >= 6 months),
not the selection itself: it ignores the spacing rule and the strike ellipse, so it reads optimistic at the ring edge.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

FT_PER_MI = 5280.0
BASIN = "midland"
# stratigraphic order, shallow -> deep (formation_blueox codes as the warehouse carries them)
SPRABERRY: tuple[str, ...] = ("US", "MS", "JM", "LSSH", "DEAN")
WOLFCAMP: tuple[str, ...] = ("WCA_1", "WCB_1", "WCB_2", "WCC", "WCD")
BENCHES: tuple[str, ...] = (*SPRABERRY, *WOLFCAMP)
ADJACENT: tuple[tuple[str, str], ...] = tuple(itertools.pairwise(BENCHES))
EMERGING_D2: tuple[str, ...] = ("MISS", "BRNT", "MRMC", "WDFD")

MODERN_FROM = dt.date(2016, 1, 1)
OIL_WINDOW = (dt.date(2016, 1, 1), dt.date(2025, 7, 31))  # first production window for the 12-mo oil / GOR medians
LAT_BAND = (5_000.0, 15_000.0)  # r2 translate_range (box/analog.Rules) = the plan's "modern" band
LONG_FT = 12_500.0  # the Cui & Cross Delaware curve's last point (box/lateral.py)
RECENT_FROM = dt.date(2023, 1, 1)
WATER_FROM = dt.date(2019, 1, 1)
ANALOG_MIN_MONTHS = 6  # deal-intake config v10 min_months_data
RING_MI = (5.0, 7.5, 10.0, 15.0, 20.0)  # box/analog.RADII_MI
COUNT_FLOOR = 5  # r2 count relax (Rules.count_floor)
MIN_WELLS = 10  # deal-intake type_curve.min_wells
SEP_RADIUS_FT = 1.5 * FT_PER_MI  # step-1 / sql/23 neighbourhood radius
SEP_MIN_N = 3  # wells of EACH bench inside the neighbourhood
MERGED_FT = 100.0  # step-1: bands < 100 ft apart locally = merged
COLOC_FT = 1.0 * FT_PER_MI
SENTINEL_FT = 2800.0  # Novi's no-neighbour spacing sentinel (rule 14)
FOLD_CUTOFFS: tuple[dt.date, ...] = tuple(dt.date(y, 12, 1) for y in range(2019, 2025))  # D53 cutoffs


def months_between(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def modern_mask(fp: Sequence[Any], lateral_ft: Sequence[Any]) -> np.ndarray:
    lat = pd.to_numeric(pd.Series(list(lateral_ft)), errors="coerce").to_numpy(float)
    f = np.array([d is not None and not pd.isna(d) and d >= MODERN_FROM for d in fp])
    with np.errstate(invalid="ignore"):
        return f & (lat >= LAT_BAND[0]) & (lat <= LAT_BAND[1])


def per_kft(cum: Sequence[Any], lateral_ft: Sequence[Any]) -> np.ndarray:
    c = pd.to_numeric(pd.Series(list(cum)), errors="coerce").to_numpy(float)
    lat = pd.to_numeric(pd.Series(list(lateral_ft)), errors="coerce").to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((lat > 0) & (c > 0), c / lat * 1000.0, np.nan)


def gor(gas_mcf: Sequence[Any], oil_bbl: Sequence[Any]) -> np.ndarray:
    g = pd.to_numeric(pd.Series(list(gas_mcf)), errors="coerce").to_numpy(float)
    o = pd.to_numeric(pd.Series(list(oil_bbl)), errors="coerce").to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((o > 0) & (g >= 0), g * 1000.0 / o, np.nan)


def quantiles(x: Sequence[float], qs: Sequence[float] = (0.1, 0.5, 0.9)) -> list[float]:
    v = np.asarray([y for y in x if y is not None and np.isfinite(y)], float)
    return [float(np.quantile(v, q)) if len(v) else math.nan for q in qs]


def operator_mix(ops: Sequence[Any], top: int = 3) -> dict[str, Any]:
    """Operator concentration of a well set: count, top-n names + shares, HHI (0-10,000 on percent shares)."""
    s = pd.Series([o if isinstance(o, str) and o.strip() else "(unknown)" for o in ops])
    if s.empty:
        return {"n_operators": 0, "top": [], "hhi": math.nan}
    share = s.value_counts(normalize=True)
    return {"n_operators": int(share.size),
            "top": [{"operator": k, "share": float(v)} for k, v in share.head(top).items()],
            "hhi": float(((share * 100.0) ** 2).sum())}


def vintage_counts(fp: Sequence[Any], years: Sequence[int]) -> dict[int, int]:
    yrs = pd.Series([d.year for d in fp if d is not None and not pd.isna(d)])
    return {int(y): int((yrs == y).sum()) for y in years}


def fold_counts(fp: Sequence[Any], cutoffs: Sequence[dt.date] = FOLD_CUTOFFS) -> dict[str, int]:
    """Wells first-producing in each D53 fold's next-12-months window (cutoff Dec 1). Wells, NOT packages: a D53 cell
    needs >= 30 PACKAGES (co-developed groups), so these read high — package counts are step 21a's job."""
    out = {}
    for c in cutoffs:
        end = dt.date(c.year + 1, c.month, 1)
        out[str(c)] = int(sum(1 for d in fp if d is not None and not pd.isna(d) and c <= d < end))
    return out


def analog_reach(stick_xy: np.ndarray, prod_xy: np.ndarray, ks: Sequence[int] = (COUNT_FLOOR, MIN_WELLS)) -> dict[str, Any]:
    """Distance (mi) from each undrilled stick midpoint to its k-th nearest same-bench analog candidate, for each k:
    P10 / P50 / P90 and the share whose k-th analog sits inside each r2 ring (5 / 7.5 / 10 / 15 / 20 mi). A stick whose
    k-th candidate is beyond 20 mi would be `not_covered_no_analogs` at that k (D74)."""
    from scipy.spatial import cKDTree

    out: dict[str, Any] = {"n_sticks": len(stick_xy), "n_candidates": len(prod_xy)}
    if not len(stick_xy):
        return out
    kmax = max(ks)
    if len(prod_xy) < kmax:
        for k in ks:
            out[f"k{k}"] = {"p10_mi": math.nan, "p50_mi": math.nan, "p90_mi": math.nan,
                            "share_within": {str(r): 0.0 for r in RING_MI}}
        return out
    d, _ = cKDTree(prod_xy).query(stick_xy, k=kmax)
    d = np.atleast_2d(d) / FT_PER_MI
    for k in ks:
        dk = d[:, k - 1]
        p10, p50, p90 = quantiles(dk)
        out[f"k{k}"] = {"p10_mi": p10, "p50_mi": p50, "p90_mi": p90,
                        "share_within": {str(r): float((dk <= r).mean()) for r in RING_MI}}
    return out


def local_separation(xy_a: np.ndarray, tvd_a: np.ndarray, xy_b: np.ndarray, tvd_b: np.ndarray,
                     radius_ft: float = SEP_RADIUS_FT, min_n: int = SEP_MIN_N) -> dict[str, Any]:
    """Step-1 pattern (D19 evidence): around every well of either bench, where BOTH benches hold >= min_n wells within
    radius_ft, local separation = median TVD(b) - median TVD(a). Reports the neighbourhood count, the median / P10 / P90
    separation, the share 'merged' (< MERGED_FT apart) and the share INVERTED (b shallower than a)."""
    from scipy.spatial import cKDTree

    ok_a = np.isfinite(tvd_a)
    ok_b = np.isfinite(tvd_b)
    xa, ta, xb, tb = xy_a[ok_a], tvd_a[ok_a], xy_b[ok_b], tvd_b[ok_b]
    if len(xa) < min_n or len(xb) < min_n:
        return {"n_hoods": 0}
    ta_tree, tb_tree = cKDTree(xa), cKDTree(xb)
    centres = np.vstack([xa, xb])
    seps = []
    for ia, ib in zip(ta_tree.query_ball_point(centres, radius_ft), tb_tree.query_ball_point(centres, radius_ft), strict=True):
        if len(ia) >= min_n and len(ib) >= min_n:
            seps.append(float(np.median(tb[ib]) - np.median(ta[ia])))
    if not seps:
        return {"n_hoods": 0}
    s = np.asarray(seps)
    p10, p50, p90 = quantiles(s)
    return {"n_hoods": len(s), "p10_ft": p10, "median_ft": p50, "p90_ft": p90,
            "share_merged": float((np.abs(s) < MERGED_FT).mean()), "share_inverted": float((s < 0).mean())}


def colocation(xy_a: np.ndarray, xy_b: np.ndarray, radius_ft: float = COLOC_FT) -> dict[str, Any]:
    """Share of bench-a wells with a bench-b well within radius_ft, and the reverse."""
    from scipy.spatial import cKDTree

    if not len(xy_a) or not len(xy_b):
        return {"a_with_b": math.nan, "b_with_a": math.nan}
    da, _ = cKDTree(xy_b).query(xy_a, k=1)
    db, _ = cKDTree(xy_a).query(xy_b, k=1)
    return {"a_with_b": float((da <= radius_ft).mean()), "b_with_a": float((db <= radius_ft).mean())}


def spacing_stats(spacing_ft: Sequence[Any]) -> dict[str, Any]:
    """lateral_closer_xy_ft (as of first production, rule 14): NULL + the 2,800 sentinel = 'unbounded' class;
    the measured gap quantiles exclude it."""
    v = pd.to_numeric(pd.Series(list(spacing_ft)), errors="coerce").to_numpy(float)
    n = len(v)
    unb = (~np.isfinite(v)) | (v >= SENTINEL_FT)
    p10, p50, p90 = quantiles(v[~unb])
    return {"n": n, "share_unbounded": float(unb.mean()) if n else math.nan, "p10_ft": p10, "median_ft": p50, "p90_ft": p90}


def length_shares(lateral_ft: Sequence[Any], cuts: Sequence[float] = (LONG_FT, LAT_BAND[1], 20_000.0)) -> dict[str, float]:
    v = pd.to_numeric(pd.Series(list(lateral_ft)), errors="coerce").to_numpy(float)
    v = v[np.isfinite(v) & (v > 0)]
    return {f"ge_{int(c)}": (float((v >= c).mean()) if len(v) else math.nan) for c in cuts} | {"n": len(v)}


def water_split(sources: Sequence[Any]) -> dict[str, Any]:
    s = pd.Series([x if isinstance(x, str) else "(no row)" for x in sources])
    vc = s.value_counts()
    n = len(s)
    return {"n": n, "counts": {k: int(v) for k, v in vc.items()},
            "share_calculated": float((s == "calculated").mean()) if n else math.nan,
            "share_measured": float((s == "measured").mean()) if n else math.nan}


def df_eur_ratio(params: Sequence[dict[str, Any]], df_new: float, df_old: float) -> dict[str, Any]:
    """50-yr EUR with terminal Df = df_new over Df = df_old, same (qi, Di nominal, b) — the switch-to-exponential
    point moves; the fit itself is not redone (Df enters the fit only through months past the switch, which a
    <= 10-year analog history rarely reaches). Modified hyperbolic, rule 6 (no economic limit)."""
    from boxfit.eur import compute_eur

    r = []
    for p in params:
        base = {"qi": float(p["qi"]), "Di": float(p["Di_nominal"]), "b": float(p["b"])}
        lo = compute_eur("modified_hyperbolic", base | {"Df": df_old})
        hi = compute_eur("modified_hyperbolic", base | {"Df": df_new})
        if lo > 0:
            r.append(hi / lo)
    p10, p50, p90 = quantiles(r)
    return {"n": len(r), "p10": p10, "median": p50, "p90": p90}
