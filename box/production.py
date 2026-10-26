"""BOX step 7c — the production run of the frozen analog workup `box_v2_wf` (D58) at every location of the D67 universe.

Pieces (pure unless they take `conn`):

  universe(conn)            D67: Novi PUD category (no RES) x reconciled remaining_pud / conflict / not-yet-reconciled, on every
                            box.bench_scope bench; the share of each stick inside its bench's record extent (step 3's >= 50 % rule).
  classify(row, covered)    coverage class with the D67 precedence: emerging -> wcxy (D61) -> unvalidated (D60) -> outside_extent;
                            the rest are candidates (covered, or no_analogs when selection finds < 3 analogs at the 20-mi cap);
                            a provisional group's candidates are `covered_provisional` (D105, run 9).
                            `covered` = the PRODUCTION_BENCHES groups this run covers (step 9c: WCA + BS2_S + WCXY_WCA1); the
                            default (WCA only) is runs 4-7.
  merge_cells_by_cutoff     D102: tuning + holdout cells of one bench merged per (cutoff, stream, horizon) before the floor.
  planned_gaps(...)         D64: perpendicular gap to the nearest SAME-FORMATION stick (PUD or PDP) whose along-axis span overlaps
                            the location's by >= 30 % of the shorter (rule 9); none within 2,800 ft -> 880 ft default.
  fit_location(loc)         the box_v2 path of box.analog.predict_location_v2 exactly (select_cohort_v2 -> members_with_transfer ->
                            P50 fit per stream -> lateral multiplier), returning the fit dicts and the named analogs.
  haircut_table(cells)      D62: per stream x horizon, the package-weighted mean box_v2 package bias over every cutoff's tuning AND
                            holdout cells with >= 30 packages (the walk-forward history rule, pooled).
  apply_haircut_c1(m, tab)  D92 (current): the D62 factors applied to the RATE as g(k) = a + b ln(min(k, 48)), held after 48, (a, b)
                            least squares to the cum factors at 12/24/36/48 per location — no rate rebound.
  haircut_curve(tab)        D62 as built (runs 4, 6): factor by month, cum-12 before month 12, linear between 12/24/36/48, cum-48 held.
  apply_haircut(months, f)  D62 as built: corrected cumulative = cumulative x f(month); monthly = its differences.

The haircut is measured on CALENDAR predictions (F(k) applied, the D53 harness); BOX delivers uptime-free volumes x haircut (D63),
which is right when the consumer's downtime factor plays F(k)'s role — the delivery says so.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
import shapely
from boxfit.tc.fit_p50 import fit_p50_series

from box import acceptance as ac
from box import analog as an
from box import basin as bsn
from box import edge_gap as eg
from box import strike as stk
from box import tc_curve as tc

SPEC = "box_v2_wf"
N_MONTHS = tc.N_MONTHS  # 600 (rule 6: the raw 50-yr integral)
STREAMS = ("oil", "gas")
HORIZONS = (12, 24, 36, 48)
MIN_PACKAGES = 30  # the walk-forward history rule (box.acceptance.MIN_PACKAGES)
VALIDATED = {("delaware", "WCA")}  # D60: benches the frozen spec was accepted on (runs 4-7)
COVERED_FORMATIONS = {"WCA_1", "WCA_2"}  # D61: WCXY PUDs are not covered (runs 4-7)

# Step 9c: the coverage groups a production run can cover. Key = the box.acceptance.BENCH_SPECS entry whose pool / spec the
# group is forecast with; value = (basin, box.bench_scope bench, formations). WCXY rows sit under bench_scope 'WCA', so the
# universe's extent join already gives them extent 6 (D95). Record spec per group: WCA + BS2_S box_v2_wf on their own
# haircut (D58 / D94, D102), WCXY_WCA1 raw box_v2 (D97) on the D93 pool.
PRODUCTION_BENCHES: dict[str, tuple[str, str, frozenset[str]]] = {
    "WCA": ("delaware", "WCA", frozenset({"WCA_1", "WCA_2"})),
    "BS2_S": ("delaware", "BS2_S", frozenset({"BS2_S"})),
    "WCXY_WCA1": ("delaware", "WCA", frozenset({"WCXY"})),
    # Run 9 (2026-10-18): the step-15 benches, each its own bench_scope bench + formation + extent of record. Validated after a
    # passed one-time holdout: WCB_1, WCC. PROVISIONAL (D105, sql/63 `covered_provisional`): AVA_0/1/2, BS2_C (never out-of-time
    # tested) and BS3_S, BS3_C, WCB_2, BS1_S (holdout FAIL 2026-10-18) - BENCH_SPECS["provisional"] is the authority.
    **{b: ("delaware", b, frozenset({b})) for b in ("WCB_1", "WCC", "AVA_0", "AVA_1", "AVA_2", "BS2_C", "BS3_S", "BS3_C", "WCB_2", "BS1_S")},
}
COVERED = ("covered", "covered_provisional")  # the two forecast-carrying classes; `covered` alone = VALIDATED in every reader
RUN7_COVERED: tuple[str, ...] = ("WCA",)
INSIDE_SHARE = 0.5  # step 3's in-extent rule
GAP_MAX_FT = 2800.0  # beyond = no neighbour (Novi's no-neighbour sentinel distance)
GAP_OVERLAP = 0.30  # rule 9 co-extent
GAP_DEFAULT_FT = an.DEFAULT_SPACING_FT  # 880 (narvi fallback)
RING_MI = an.RADII_MI[0]

# ----------------------------------------------------------------------------
# Universe + coverage
# ----------------------------------------------------------------------------

_UNIVERSE_SQL = """
SELECT il.stick_id, il.report_version, bs.basin, bs.bench, bs.in_scope, fb.formation_blueox,
       COALESCE(ri.status, 'not_reconciled') AS recon_status, il.pad_name, il.ll_ft,
       extensions.ST_AsText(il.wellstick_geom) AS wkt,
       extensions.ST_X(extensions.ST_LineInterpolatePoint(il.wellstick_geom, 0.5)) AS mid_lon,
       extensions.ST_Y(extensions.ST_LineInterpolatePoint(il.wellstick_geom, 0.5)) AS mid_lat,
       extensions.ST_Length(il.wellstick_geom::extensions.geography) * 3.28084 AS stick_ft,
       e.extent_id,
       CASE WHEN e.extent_id IS NULL THEN NULL ELSE
           extensions.ST_Length(extensions.ST_Intersection(il.wellstick_geom, e.geom)::extensions.geography)
           / NULLIF(extensions.ST_Length(il.wellstick_geom::extensions.geography), 0) END AS inside_share
FROM curated.intel_locations il
JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
JOIN box.bench_scope bs ON bs.basin = il.basin AND fb.formation_blueox = ANY (bs.member_benches)
LEFT JOIN box.extent e ON e.is_record AND e.basin = bs.basin AND e.bench = bs.bench
LEFT JOIN curated.reconciled_inventory ri ON ri.stick_id = il.stick_id
WHERE il.category = 'PUD'
  AND COALESCE(ri.status, 'not_reconciled') IN ('remaining_pud', 'conflict', 'not_reconciled')
  AND il.wellstick_geom IS NOT NULL
  AND il.basin = ANY (%(basins)s)
ORDER BY il.stick_id
"""

# D64 "PDP" = wells that have PRODUCED (first_production_date set), the same test sql/20 producing_reference applies.
# curated.wells also carries permits, cancelled permits and spuds; counting those read 172 of the 275 7c "near a
# producer" flags off sticks that never produced (reconciliation audit, eng_db #134, 2026-10-15).
_PDP_SQL = """
SELECT w.api10, extensions.ST_AsText(w.wellstick_geom)
FROM curated.wells w
JOIN curated.formation_blueox f ON f.api10 = w.api10
WHERE f.basin_blueox = %(basin)s AND f.formation_blueox = ANY (%(forms)s)
  AND w.wellstick_geom IS NOT NULL AND COALESCE(w.lateral_length_ft, 0) > 1000
  AND w.first_production_date IS NOT NULL
"""


def group_basin(group: str) -> str:
    """The basin a PRODUCTION_BENCHES group belongs to."""
    return PRODUCTION_BENCHES[group][0]


def run_basin(groups: Sequence[str]) -> str:
    """The ONE basin of a run's groups (D130: one record run per basin); a run mixing basins is refused."""
    b = sorted({group_basin(g) for g in groups})
    if len(b) != 1:
        raise ValueError(f"a BOX run covers one basin (D130); groups {list(groups)} span {b}")
    return b[0]


def universe(conn: Any, covered: Sequence[str] = RUN7_COVERED, basins: Sequence[str] | None = None) -> pd.DataFrame:
    """The D67 / D117 universe of `basins` (default: the covered groups' basin, D130 - a run's universe is its own basin's).
    Before step 19 the universe was every basin's: run 19 (Delaware) carries the 4,154 Midland emerging-bench rows."""
    basins = list(basins) if basins is not None else [run_basin(covered)]
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_UNIVERSE_SQL, {"basins": basins})
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    conn.rollback()
    d = pd.DataFrame(rows, columns=cols)
    for c in ("ll_ft", "mid_lon", "mid_lat", "stick_ft", "inside_share"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["inside_extent"] = np.where(d["extent_id"].notna(), d["inside_share"].fillna(0) >= INSIDE_SHARE, None)
    d["prod_bench"] = [production_bench(r, covered) for r in d.itertuples()]
    d["coverage"] = [classify(r, covered) for r in d.itertuples()]
    return d


def production_bench(r: Any, covered: Sequence[str] = RUN7_COVERED) -> str | None:
    """The covered PRODUCTION_BENCHES group a universe row belongs to, or None."""
    for key in covered:
        basin, bench, forms = PRODUCTION_BENCHES[key]
        if r.basin == basin and r.bench == bench and r.formation_blueox in forms:
            return key
    return None


def classify(r: Any, covered: Sequence[str] = RUN7_COVERED) -> str:
    """D67 precedence. Candidates come back as 'covered' / 'covered_provisional' and become 'not_covered_no_analogs' when selection
    fails."""
    if not bool(r.in_scope):
        return "not_covered_emerging"
    grp = production_bench(r, covered)
    if r.formation_blueox == "WCXY" and grp is None:
        return "not_covered_wcxy"
    if grp is None:
        return "not_covered_unvalidated"
    if not bool(r.inside_extent):
        return "not_covered_outside_extent"
    return covered_class(grp)


def covered_class(group: str) -> str:
    """'covered_provisional' for a D105 provisional group (BENCH_SPECS["provisional"]), else 'covered'."""
    return "covered_provisional" if ac.BENCH_SPECS[group].get("provisional") else "covered"


def pdp_sticks(conn: Any, forms: Sequence[str], basin: str = bsn.DELAWARE) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_PDP_SQL, {"forms": list(forms), "basin": basin})
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=["api10", "wkt"])


# ----------------------------------------------------------------------------
# D64 planned spacing
# ----------------------------------------------------------------------------


def _axis(line: Any) -> tuple[np.ndarray, np.ndarray, float]:
    c = np.asarray(line.coords, float)
    a, b = c[0], c[-1]
    L = float(np.hypot(*(b - a)))
    u = (b - a) / L if L > 0 else np.array([1.0, 0.0])
    return a, u, L


def perpendicular_gap(line: Any, other: Any, min_overlap: float = GAP_OVERLAP) -> float | None:
    """Mean perpendicular offset of `other` from `line` over their shared along-axis span (straight-stick approximation,
    end to end), when that span is >= min_overlap of the shorter stick; else None."""
    a, u, L = _axis(line)
    if L <= 0:
        return None
    oc = np.asarray(other.coords, float)
    s = (oc - a) @ u
    lo, hi = max(0.0, float(s.min())), min(L, float(s.max()))
    lo_len = min(L, float(s.max() - s.min()))
    if hi <= lo or lo_len <= 0 or (hi - lo) < min_overlap * lo_len:
        return None
    n = np.array([-u[1], u[0]])
    o0, o1 = oc[0], oc[-1]
    if float((o1 - o0) @ u) < 0:
        o0, o1 = o1, o0
    sa, sb = float((o0 - a) @ u), float((o1 - a) @ u)
    if sb - sa <= 0:
        return None

    def off(t: float) -> float:
        p = o0 + (o1 - o0) * (t - sa) / (sb - sa)
        return float(abs((p - a) @ n))

    return 0.5 * (off(lo) + off(hi))


def nearest_gaps(targets: Sequence[Any], neighbours: Sequence[Any], target_ids: Sequence[Any], neighbour_ids: Sequence[Any],
                 max_ft: float = GAP_MAX_FT) -> list[tuple[float, Any] | None]:
    """(gap ft, neighbour id) of the nearest perpendicular neighbour per target (projected ft lines), excluding itself; None = none
    in range. Ties keep the first neighbour in STRtree order."""
    tree = shapely.STRtree(list(neighbours))
    out: list[tuple[float, Any] | None] = []
    for t, tid in zip(targets, target_ids, strict=True):
        best: tuple[float, Any] | None = None
        for j in tree.query(t.buffer(max_ft)):
            if neighbour_ids[j] == tid:
                continue
            g = perpendicular_gap(t, neighbours[j])
            if g is not None and 1.0 <= g <= max_ft and (best is None or g < best[0]):
                best = (g, neighbour_ids[j])
        out.append(best)
    return out


def planned_gaps(targets: Sequence[Any], neighbours: Sequence[Any], target_ids: Sequence[Any], neighbour_ids: Sequence[Any],
                 max_ft: float = GAP_MAX_FT) -> list[float | None]:
    """Nearest perpendicular gap (ft) per target; None = none in range."""
    return [None if b is None else b[0] for b in nearest_gaps(targets, neighbours, target_ids, neighbour_ids, max_ft)]


def project_ft(wkts: Sequence[str]) -> list[Any]:
    return eg.to_ft(list(shapely.from_wkt(list(wkts))))


# ----------------------------------------------------------------------------
# The box_v2 path at one location
# ----------------------------------------------------------------------------


def de_eff_1yr(di: float, b: float) -> float:
    """1-year effective decline of a hyperbolic with nominal Di (per year) and b."""
    if b <= 1e-9:
        return 1.0 - math.exp(-di)
    return 1.0 - (1.0 + b * di) ** (-1.0 / b)


def _params(fit: Mapping[str, Any]) -> dict[str, Any]:
    di, b = float(fit["Di"]), float(fit["b"])
    return {"model_type": fit.get("model_type"), "qo": float(fit["qo"]), "qi": float(fit["qi"]), "peak_index_months": int(fit["peak_index"]),
            "Di_nominal": di, "Di_eff_1yr": de_eff_1yr(di, b), "b": b, "Df": float(fit["Df"]), "basis": "per 1,000 ft, analog cohort P50 (D57)"}


def _analog_rows(pool: Mapping[str, Any], idx: Sequence[int], loc: Mapping[str, Any], mode: str) -> list[dict[str, Any]]:
    dx = np.array([pool["x"][i] - loc["x"] for i in idx], float)
    dy = np.array([pool["y"][i] - loc["y"] for i in idx], float)
    dist = np.hypot(dx, dy)
    if mode == "strike":
        near = _STATE["tree"].query_ball_point([loc["x"], loc["y"]], r=stk.RADIUS_FT)
        s = stk.local_strike(pool["x"][near], pool["y"][near], pool["tvd"][near], loc["x"], loc["y"]) if len(near) else None
        if s:
            dist = np.asarray(stk.ellipse_distance(dx, dy, s.azimuth_deg), float)
    return [{"api10": str(pool["api10"][i]), "rank": k + 1, "dist_ft": float(dist[k]), "lateral_ft": float(pool["lateral"][i]),
             "first_production": pool["fp"][i], "transfer": an._post_peak(pool["params"][pool["api10"][i]]["oil"], pool["months"][i]) < an.TRANSFER_MONTHS}
            for k, i in enumerate(idx)]


_STATE: dict[str, Any] = {}


def fit_location(loc: dict[str, Any]) -> dict[str, Any]:
    """box_v2 at one location (box.analog.predict_location_v2's box_v2 branch, unchanged): returns provenance, per-stream fits,
    lateral multiplier and 600 uptime-free months (x multiplier, before the haircut). `_STATE["rules"]` (step 16d) = the
    selection rules (default the record; D121 builds pass box.production16.RULES with a measured-spacing pool), and the
    lateral multiplier is box.analog.lateral_multiplier (Cui when short or when the rules translate / relax the lateral)."""
    pool2, tree, cfg = _STATE["pool2"], _STATE["tree"], _STATE["cfg"]
    basin = _STATE.get("basin", an.BASIN)
    idx, r, flags, mode = an.select_cohort_v2(pool2, tree, cfg, loc, bench=_STATE.get("bench", an.BENCH),
                                              rules=_STATE.get("rules") or an.RECORD_RULES, basin=basin)
    out: dict[str, Any] = {"key": loc["api10"], "radius_mi": float(r), "n_analogs": len(idx), "search_mode": mode, "flags": list(flags),
                           "short_lateral": float(loc["lateral_ft"]) < an.SHORT_LAT_FT}
    if len(idx) < 3:
        return out
    agg = tc.aggregate_only(an.members_with_transfer(pool2, idx))
    fits = {s: fit_p50_series(agg.streams[s].p50, df_terminal_per_year=bsn.df_terminal(basin), stream=s) for s in STREAMS}
    if not fits["oil"]:
        out["flags"].append("oil P50 fit failed")
        return out
    mult = an.lateral_multiplier(float(loc["lateral_ft"]), [pool2["lateral"][i] for i in idx], flags)
    out.update({"lateral_mult": mult, "analogs": _analog_rows(pool2, idx, loc, mode), "streams": {}})
    for s in STREAMS:
        if fits[s]:
            out["streams"][s] = {"params": _params(fits[s]), "months_raw": tc.monthly_volumes(fits[s], N_MONTHS) * mult}
        else:
            out["flags"].append(f"{s} P50 fit failed")
    return out


def init_state(state: dict[str, Any]) -> None:
    an._init(state)  # same tree / logging set-up as the harness (tree on pool1's xy == pool2's xy)
    _STATE.update(an._STATE)


def fit_many(locs: list[dict[str, Any]], pool: dict[str, Any], pool2: dict[str, Any], cfg: Any, workers: int,
             bench: str = an.BENCH, rules: an.Rules | None = None, basin: str = an.BASIN) -> list[dict[str, Any]]:
    """`bench` = the deal-intake bench label passed to selection (the harness's BENCH_SPECS[...]["label"]); `rules` = the
    selection rules (None = the record); `basin` = the group's basin (Df, step 19)."""
    from concurrent.futures import ProcessPoolExecutor

    state = {"pool": pool, "pool2": pool2, "cfg": cfg, "k": N_MONTHS, "cutoff": None, "bench": bench, "rules": rules, "basin": basin}
    if workers == 1:
        init_state(state)
        return [fit_location(x) for x in locs]
    with ProcessPoolExecutor(max_workers=workers, initializer=init_state, initargs=(state,)) as ex:
        return list(ex.map(fit_location, locs, chunksize=8))


# ----------------------------------------------------------------------------
# D62 haircut
# ----------------------------------------------------------------------------


def haircut_table(cells: pd.DataFrame, variant: str = "box_v2", min_packages: int = MIN_PACKAGES) -> dict[str, dict[int, dict[str, float]]]:
    """Per stream x horizon: factor = 1 + package-weighted mean package bias over every (tuning + holdout) cell of `variant`
    with >= min_packages packages; also n_packages and the cutoffs used."""
    c = cells[(cells["variant"] == variant) & (cells["n_packages"] >= min_packages) & np.isfinite(cells["pkg_bias"].astype(float))]
    out: dict[str, dict[int, dict[str, float]]] = {}
    for s in STREAMS:
        out[s] = {}
        for k in HORIZONS:
            x = c[(c["stream"] == s) & (c["horizon"] == k)]
            if x.empty:
                raise ValueError(f"no cells for {s} cum-{k}")
            w = x["n_packages"].to_numpy(float)
            bias = float(np.sum(w * x["pkg_bias"].to_numpy(float)) / w.sum())
            out[s][k] = {"factor": 1.0 + bias, "bias": bias, "n_packages": int(w.sum()), "n_cells": len(x),
                         "cutoffs": sorted({str(v) for v in x["cutoff"]})}
    return out


def merge_cells_by_cutoff(cells: pd.DataFrame) -> pd.DataFrame:
    """D102 (BS2_S, Michael 2026-10-17): the tuning and holdout cells of one bench merged into one cell per (variant, cutoff,
    stream, horizon) — n_packages summed, pkg_bias package-weighted — so the >= 30 floor applies to the merged cell (the 9b
    holdout cells alone hold 0-40 packages). Equals D62's pooling wherever each part clears the floor on its own."""
    c = cells[np.isfinite(cells["pkg_bias"].astype(float)) & (cells["n_packages"] > 0)].copy()
    c["_w"] = c["n_packages"].astype(float) * c["pkg_bias"].astype(float)
    g = c.groupby(["variant", "cutoff", "stream", "horizon"], as_index=False).agg(n_packages=("n_packages", "sum"), _w=("_w", "sum"))
    g["pkg_bias"] = g["_w"] / g["n_packages"]
    return g.drop(columns="_w")


def haircut_curve(tab: Mapping[int, Mapping[str, float]], n: int = N_MONTHS) -> np.ndarray:
    """Factor for months 1..n: cum-12 factor for months <= 12, linear in months between horizons, cum-48 held after."""
    hs = sorted(int(k) for k in tab)
    fs = [float(tab[k]["factor"]) for k in hs]
    m = np.arange(1, n + 1, dtype=float)
    return np.interp(m, hs, fs, left=fs[0], right=fs[-1])


HAIRCUT_METHOD = "D92 C1: rate factor g(k) = a + b ln(min(k, 48)), least squares to the D62 cum factors, held after month 48"


def apply_haircut_c1(months_raw: np.ndarray, tab: Mapping[int, Mapping[str, float]]) -> tuple[np.ndarray, dict[str, Any]]:
    """D92 (replaces the D62 APPLICATION for runs built after 2026-10-15; the D62 factors themselves are unchanged).

    The haircut multiplies the monthly RATE by a smooth factor g(k) = a + b ln(min(k, 48)) — g held at g(48) from month 48 on —
    with (a, b) chosen per location by least squares so the realised cumulative factor sum(raw x g) / sum(raw) at months
    12 / 24 / 36 / 48 matches the D62 table's factors (each horizon weighted equally). D62's linear cum factor met the knots
    exactly but, being a falling CUMULATIVE factor held flat after 48, forced the rate down through year 4 and back up at month 49
    (record run 6: year-4 oil = 0.735 x year 5); g is monotone in k, so the haircut never makes a rate rise. Returns
    (monthly volumes, info: a, b, g at months 1 and 48, realised cum factor per horizon, eur factor)."""
    raw = np.asarray(months_raw, float)
    ks = sorted(int(k) for k in tab)
    fs = np.array([float(tab[k]["factor"]) for k in ks])
    idx = np.array(ks) - 1
    lnk = np.log(np.minimum(np.arange(1, len(raw) + 1, dtype=float), float(ks[-1])))
    c = np.cumsum(raw)[idx]
    if (c <= 0).any():
        raise ValueError("haircut C1 needs production before every horizon")
    A = np.column_stack([np.ones(len(ks)), np.cumsum(raw * lnk)[idx] / c])
    a, b = np.linalg.lstsq(A, fs, rcond=None)[0]
    g = a + b * lnk
    if not (g > 0).all():
        raise ValueError(f"haircut C1 factor not positive (a={a}, b={b})")
    v = raw * g
    real = np.cumsum(v)[idx] / c
    return v, {"method": "c1_log_rate", "a": float(a), "b": float(b), "g_month1": float(g[0]), "g_tail": float(g[-1]),
               "realised": {str(k): float(r) for k, r in zip(ks, real, strict=True)}, "eur_factor": float(v.sum() / raw.sum())}


def apply_haircut(months_raw: np.ndarray, f: np.ndarray) -> np.ndarray:
    """D62 AS BUILT for runs 4 and 6 (superseded by apply_haircut_c1, D92; kept to reproduce those stored runs).
    Corrected cumulative = raw cumulative x f(month); monthly = its differences (clipped at 0, re-normalised so the sum is exact)."""
    cum = np.cumsum(np.asarray(months_raw, float)) * f
    v = np.diff(np.concatenate(([0.0], cum)))
    if (v < 0).any():
        v = np.maximum(v, 0.0)
        v *= cum[-1] / v.sum()
    return v


DI_CAP = 4.0  # rule 1: oil / gas nominal Di cap (per year)
B_BOUNDS = (0.9, 1.2)


def bound_flags(streams: Mapping[str, Mapping[str, Any]], near_pdp_ft: float | None = None) -> list[str]:
    """Review flags that never change the forecast: P50 fits pinned at a parameter bound (flagged, never silently accepted), and a
    planned gap to an existing same-formation producer under 500 ft (possible realized-but-unreconciled PUD, rule 11)."""
    out = []
    for s, st in streams.items():
        p = st["params"]
        if p["Di_nominal"] >= DI_CAP - 1e-3:
            out.append(f"{s} Di at bound {DI_CAP:.1f}/yr nominal ({p['Di_eff_1yr']:.0%} 1-yr effective): review")
        if p["b"] <= B_BOUNDS[0] + 1e-4 or p["b"] >= B_BOUNDS[1] - 1e-4:
            out.append(f"{s} b at bound {p['b']:.2f}: review")
    if near_pdp_ft is not None and near_pdp_ft < 500:
        out.append(f"planned gap {near_pdp_ft:,.0f} ft to an existing same-formation producer: possible realized PUD (reconciliation)")
    return out


# ----------------------------------------------------------------------------
# D73 quarterly crosswalk
# ----------------------------------------------------------------------------

XWALK_BUFFER_FT = 250.0  # "co-extent": the shorter stick lies within this of the other (well under the ~755-ft P10 PUD-PUD gap)
XWALK_SHARE = 0.5  # D73: >= 50 % of the shorter stick


def crosswalk(prev: Sequence[tuple[int, str, str, Any]], new: Sequence[tuple[int, str, str, Any]],
              buffer_ft: float = XWALK_BUFFER_FT, min_share: float = XWALK_SHARE) -> dict[int, tuple[int, float]]:
    """D73: new-vintage stick -> (location_id, share) when basin + formation_blueox match and >= min_share of the SHORTER stick lies
    within buffer_ft of the other (rule 9 co-extent overlap); 1:1, greedy by share then midpoint distance. Unmatched sticks are new
    locations; unmatched locations stop at their last_seen_vintage. prev = (location_id, basin, formation, line_ft);
    new = (stick_id, basin, formation, line_ft), projected ft."""
    if not prev or not new:
        return {}
    tree = shapely.STRtree([p[3] for p in prev])
    cands: list[tuple[float, float, int, int]] = []
    for sid, basin, form, line in new:
        for j in tree.query(line.buffer(buffer_ft)):
            lid, pb, pf, pline = prev[int(j)]
            if pb != basin or pf != form:
                continue
            short, long_ = (line, pline) if line.length <= pline.length else (pline, line)
            if short.length <= 0:
                continue
            share = float(shapely.intersection(short, long_.buffer(buffer_ft)).length / short.length)
            if share >= min_share:
                d = float(shapely.distance(line.interpolate(0.5, normalized=True), pline.interpolate(0.5, normalized=True)))
                cands.append((-share, d, int(sid), int(lid)))
    out: dict[int, tuple[int, float]] = {}
    taken: set[int] = set()
    for neg_share, _, sid, lid in sorted(cands):
        if sid in out or lid in taken:
            continue
        out[sid] = (lid, -neg_share)
        taken.add(lid)
    return out


def radius_class(radius_mi: float) -> str:
    return "5 mi ring" if radius_mi <= RING_MI else "past 5 mi"
