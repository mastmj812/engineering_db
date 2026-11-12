"""BOX sticks, phase 2a: realized well spacing per bench per neighbourhood (read-only) -- docs/box_sticks_plan.md.

    python -m scripts.box_sticks_phase2a --out docs/box_sticks/phase2a-<date> --cache <phase 0 cache>

The gap method of dealintake/spacing.py (config: planned_spacing in the deal-intake thresholds.yaml), run on producer
laterals instead of Novi sticks: a well's gap is the median perpendicular distance to its NEAREST parallel same-bench
neighbour (axial azimuth within parallel_tol_deg, alongside for >= overlap_min_frac of the well, measured over the
shared length); a neighbour closer than same_slot_ft is the same slot, not a spacing. `pair_table` is an array
re-implementation that also returns WHICH neighbour (needed for the co-development test); `method_check` runs the
original `dealintake.spacing.neighbour_gaps_ft` on the focus benches and reports how often the two agree.

Populations (live tags):
  universe   every horizontal producer with a lateral line and a live tag (any vintage, any evidence status);
             neighbours are searched in the universe so an older or unjudged well between two wells is seen.
  measured   evidence wells (phase 0 rules) that pass the two-part screen (phase 1c), first production >= 2016.
  primary gap  a measured well whose NEAREST same-bench neighbour (>= same_slot_ft, < UNBOUNDED_FT) is itself
             measured and came on within CODEV_DAYS of it. Otherwise the well is not measured, reason recorded.
Cross-check: wells_enriched.lateral_closer_xy_ft (NULL and exactly 2800.0 excluded) against this method's nearest
same-bench neighbour that was on production when the well came on. The pass thresholds (CHECK_*) were fixed before
the first run.

Neighbourhood: each Novi 2026Q3 DSU polygon x each bench whose BOX record extent it intersects (WCXY: Michael's
hand-drawn extent file). Local spacing = median primary gap of same-bench wells within 1 -> 2 -> 3 mi of the polygon,
first radius with >= min_gaps. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
import yaml
from matplotlib.collections import PolyCollection

from box import landing_surfaces as ls
from box import tag_scoreboard as sb
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1c as p1c

ROOT = Path(__file__).resolve().parent.parent
FT_PER_M = p0.FT_PER_M
MI = ls.M_PER_MI
PS = yaml.safe_load((ROOT / ".claude/skills/deal-intake/config/thresholds.yaml").read_text(encoding="utf-8"))["planned_spacing"]
TOL_DEG, OVERLAP_MIN, SAME_SLOT_FT, SEARCH_FT = (float(PS[k]) for k in ("parallel_tol_deg", "overlap_min_frac", "same_slot_ft", "neighbour_search_ft"))
MIN_GAPS, RADII_MI = int(PS["min_gaps"]), tuple(float(r) for r in PS["radius_steps_mi"])
SPREAD_FLAG = float(PS["spread_flag_frac"])
SAMPLES = 21
SENTINEL_FT = 2800.0          # Novi LateralCloserXY no-neighbour value; also this study's "unbounded" limit
UNBOUNDED_FT = SENTINEL_FT
SINCE = pd.Timestamp("2016-01-01")
CODEV_DAYS = 365              # co-developed: first production within 12 months of each other
CODEV_SENS_DAYS = (183, 730)
ASOF_SLACK_DAYS = 31          # "on production when the well came on": first production no later than own + 1 month
STAGGER_FT = 75.0             # pair landing depths further apart than this = two landings inside one tag
FLOOR_FT = 1320.0
FLOOR_ALT_FT = 1540.0
CAP_GUESS_FT = 660.0
SETBACK_FT = p0.SETBACK_FT
FOCUS = (("delaware", "BS1_S"), ("midland", "DEAN"))
WCXY_FILE = ROOT / "docs/box_sticks/wcxy-extent-2026-11-12/extent_WCXY_edited.geojson"
# cross-check pass thresholds, fixed before the first run
CHECK_MEDIAN_DIFF_FT = 50.0   # |median(this - Novi)| per basin
CHECK_AGREE_PCT = 70.0        # share of wells within max(100 ft, 15 %) of Novi
CHECK_REPRO_PCT = 99.0        # share of wells where pair_table reproduces dealintake.spacing.neighbour_gaps_ft

_WELL_GEOM_SQL = """
SELECT w.api10, w.lateral_closer_xy_ft,
       extensions.ST_AsText(extensions.ST_Transform(w.wellstick_geom, 3083)) AS wkt,
       extensions.ST_AsText(w.wellstick_geom) AS wkt_ll
FROM curated.wells_enriched w
WHERE w.basin_blueox IN ('delaware', 'midland') AND w.is_horizontal AND w.first_production_date IS NOT NULL
  AND extensions.ST_GeometryType(w.wellstick_geom) = 'ST_LineString'
"""
_STICK_GEOM_SQL = """
SELECT il.stick_id, extensions.ST_AsText(extensions.ST_Transform(il.wellstick_geom, 3083)) AS wkt
FROM curated.intel_locations il
WHERE il.category IN ('PUD', 'RES') AND il.wellstick_geom IS NOT NULL
"""


def pull_geoms(cache: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    f1, f2 = cache / "p2a_well_geom.pkl", cache / "p2a_stick_geom.pkl"
    if f1.exists() and f2.exists():
        return pd.read_pickle(f1), pd.read_pickle(f2)
    from etl.db import get_connection

    with get_connection() as conn:
        wg, sg = sb._read(conn, _WELL_GEOM_SQL, {}), sb._read(conn, _STICK_GEOM_SQL, {})
    wg["api10"] = wg["api10"].astype(str)
    wg["lateral_closer_xy_ft"] = pd.to_numeric(wg["lateral_closer_xy_ft"], errors="coerce")
    wg.to_pickle(f1)
    sg.to_pickle(f2)
    return wg, sg


# ----------------------------------------------------------------------------
# The gap method
# ----------------------------------------------------------------------------


def pair_table(geoms: np.ndarray, grp: np.ndarray) -> pd.DataFrame:
    """Directed pairs (i -> j) of same-group lines that pass the parallel and alongside tests, with d_ft = median
    distance from i's sample points inside the shared length to line j. Coordinates in metres (EPSG:3083)."""
    n = len(geoms)
    first = shapely.get_coordinates(shapely.get_point(geoms, 0))
    last = shapely.get_coordinates(shapely.get_point(geoms, -1))
    dx, dy = last[:, 0] - first[:, 0], last[:, 1] - first[:, 1]
    ok = np.hypot(dx, dy) >= 1.0
    az = np.degrees(np.arctan2(dx, dy)) % 180.0
    ux, uy = np.sin(np.radians(az)), np.cos(np.radians(az))
    i, j = shapely.STRtree(geoms).query(shapely.buffer(geoms, SEARCH_FT / FT_PER_M))   # bbox test, as the original
    keep = (i != j) & (grp[i] == grp[j]) & ok[i] & ok[j]
    i, j = i[keep], j[keep]
    d = np.abs(az[i] - az[j])
    keep = np.minimum(d, 180.0 - d) <= TOL_DEG
    i, j = i[keep], j[keep]
    # along-axis extents: i's own, and j's projected on i's axis
    c, ci = shapely.get_coordinates(geoms, return_index=True)
    al = c[:, 0] * ux[ci] + c[:, 1] * uy[ci]
    lo, hi = np.full(n, np.inf), np.full(n, -np.inf)
    np.minimum.at(lo, ci, al)
    np.maximum.at(hi, ci, al)
    cj, pj = shapely.get_coordinates(geoms[j], return_index=True)
    aj = cj[:, 0] * ux[i][pj] + cj[:, 1] * uy[i][pj]
    jlo, jhi = np.full(len(i), np.inf), np.full(len(i), -np.inf)
    np.minimum.at(jlo, pj, aj)
    np.maximum.at(jhi, pj, aj)
    olo, ohi = np.maximum(lo[i], jlo), np.minimum(hi[i], jhi)
    span = hi[i] - lo[i]
    frac = np.where(span > 0, (ohi - olo) / np.where(span > 0, span, 1.0), 0.0)
    keep = (ohi > olo) & (frac >= OVERLAP_MIN)
    i, j, olo, ohi, frac = i[keep], j[keep], olo[keep], ohi[keep], frac[keep]
    out_d = np.full(len(i), np.nan)
    fr = np.linspace(0.0, 1.0, SAMPLES)
    for a in range(0, len(i), 200_000):
        s = slice(a, a + 200_000)
        pts = shapely.line_interpolate_point(geoms[i[s]][:, None], fr[None, :], normalized=True)
        pal = shapely.get_x(pts) * ux[i[s]][:, None] + shapely.get_y(pts) * uy[i[s]][:, None]
        dist = shapely.distance(pts, geoms[j[s]][:, None]) * FT_PER_M
        dist[(pal < olo[s][:, None] - 1e-6) | (pal > ohi[s][:, None] + 1e-6)] = np.nan
        with np.errstate(all="ignore"):
            out_d[s] = np.nanmedian(dist, axis=1)
    t = pd.DataFrame({"i": i, "j": j, "d_ft": out_d, "overlap_frac": frac})
    return t[t["d_ft"].notna()].reset_index(drop=True)


def nearest(t: pd.DataFrame, n: int, floor_ft: float = SAME_SLOT_FT) -> tuple[np.ndarray, np.ndarray]:
    """Per line: (gap ft, neighbour index) of the nearest pair partner at >= floor_ft; NaN / -1 when none."""
    q = t[t["d_ft"] >= floor_ft].sort_values("d_ft").drop_duplicates("i")
    gap, nb = np.full(n, np.nan), np.full(n, -1)
    gap[q["i"].to_numpy()], nb[q["i"].to_numpy()] = q["d_ft"].to_numpy(), q["j"].to_numpy()
    return gap, nb


def method_check(u: pd.DataFrame, gap_any: np.ndarray) -> list[dict]:
    """dealintake.spacing.neighbour_gaps_ft (the original, WGS84 -> local frame) vs pair_table, focus benches."""
    from dealintake import spacing as sp
    from dealintake.geo import LocalFrame

    rows = []
    for basin, code in FOCUS:
        g = u[(u["basin"] == basin) & (u["live"] == code)]
        ll = [shapely.from_wkt(x) for x in g["wkt_ll"]]
        ref = sp.neighbour_gaps_ft(ll, LocalFrame.around(shapely.GeometryCollection(ll)), parallel_tol_deg=TOL_DEG, overlap_min_frac=OVERLAP_MIN,
                                   same_slot_ft=SAME_SLOT_FT, search_ft=SEARCH_FT, samples=SAMPLES)
        ref = np.array([np.nan if v is None else v for v in ref], float)
        mine = gap_any[g.index.to_numpy()]
        both = np.isfinite(ref) & np.isfinite(mine)
        same_none = np.isfinite(ref) == np.isfinite(mine)
        close = np.abs(ref[both] - mine[both]) <= np.maximum(5.0, 0.005 * ref[both])
        agree = (same_none.sum() - both.sum() + close.sum()) / len(g) * 100
        rows.append({"basin": basin, "code": code, "wells": len(g), "with_gap_original": int(np.isfinite(ref).sum()), "with_gap_here": int(np.isfinite(mine).sum()),
                     "agree_pct": agree, "max_abs_diff_ft": float(np.abs(ref[both] - mine[both]).max()) if both.any() else np.nan,
                     "median_diff_ft": float(np.median(mine[both] - ref[both])) if both.any() else np.nan, "pass": bool(agree >= CHECK_REPRO_PCT)})
    return rows


# ----------------------------------------------------------------------------
# Populations and per-well measurement
# ----------------------------------------------------------------------------


def universe(d: dict, wg: pd.DataFrame, cache: Path | None) -> pd.DataFrame:
    w = sb.evidence_depth(d["wells"], "best")
    ev = p0.evidence(d["wells"], d["rule"])
    f = cache / "p2a_screen.pkl" if cache else None
    if f and f.exists():
        scr = pd.read_pickle(f)
    else:
        scr = p1c.two_part_screen(ev, d["extents"])[["api10", "screen"]]
        if f:
            scr.to_pickle(f)
    u = w.merge(wg, on="api10", how="inner").merge(scr, on="api10", how="left")
    u["screen"] = u["screen"].fillna("not_evidence")
    u = u[u["live"].notna() & u["wkt"].notna()].reset_index(drop=True)
    u["geom"] = shapely.from_wkt(u["wkt"].to_numpy())
    u = u[shapely.length(u["geom"].to_numpy()) > 1.0].reset_index(drop=True)
    u["fp"] = pd.to_datetime(u["first_production_date"])
    mid = shapely.line_interpolate_point(u["geom"].to_numpy(), 0.5, normalized=True)
    u["x"], u["y"] = shapely.get_x(mid), shapely.get_y(mid)
    u["measured_pop"] = (u["screen"] == "keep") & (u["fp"] >= SINCE)
    return u


def measure(u: pd.DataFrame, t: pd.DataFrame) -> pd.DataFrame:
    n = len(u)
    fp = u["fp"].to_numpy()
    gap_any, nb = nearest(t, n)
    has = (nb >= 0) & (gap_any < UNBOUNDED_FT)
    nbs = np.where(has, nb, 0)
    days = np.abs((fp - fp[nbs]) / np.timedelta64(1, "D"))
    m = u[["api10", "basin", "live", "county", "fp", "x", "y", "depth_ft", "screen", "measured_pop", "lateral_closer_xy_ft"]].copy()
    m["gap_any_ft"] = np.where(has, gap_any, np.nan)
    m["nb_api10"] = np.where(has, u["api10"].to_numpy()[nbs], None)
    m["nb_days"] = np.where(has, days, np.nan)
    m["nb_measured_pop"] = has & u["measured_pop"].to_numpy()[nbs]
    m["nb_pre2016"] = has & (fp[nbs] < np.datetime64(SINCE))
    m["dz_ft"] = np.where(has, np.abs(u["depth_ft"].to_numpy(float) - u["depth_ft"].to_numpy(float)[nbs]), np.nan)
    reason = np.where(~has, "no_neighbour_within_2800ft",
                      np.where(m["nb_pre2016"], "nearest_neighbour_pre_2016",
                               np.where(~m["nb_measured_pop"], "nearest_neighbour_not_evidence",
                                        np.where(days > CODEV_DAYS, "nearest_neighbour_other_campaign", "measured"))))
    m["status"] = np.where(m["measured_pop"], reason, "not_in_population")
    m["gap_ft"] = np.where(m["status"] == "measured", m["gap_any_ft"], np.nan)
    for dd in CODEV_SENS_DAYS:
        m[f"gap_{dd}d_ft"] = np.where(m["measured_pop"] & has & m["nb_measured_pop"] & (days <= dd), m["gap_any_ft"], np.nan)
    m["stacked_same_slot"] = False
    m.loc[t.loc[t["d_ft"] < SAME_SLOT_FT, "i"].unique(), "stacked_same_slot"] = True
    # as of first production: nearest neighbour already on when this well came on (for the Novi cross-check)
    ta = t[fp[t["j"].to_numpy()] <= fp[t["i"].to_numpy()] + np.timedelta64(ASOF_SLACK_DAYS, "D")]
    m["asof_ft"] = nearest(ta, n, 0.0)[0]
    m["asof_floor_ft"] = nearest(ta, n, SAME_SLOT_FT)[0]
    return m


def q(v: pd.Series, p: float) -> float:
    return float(v.quantile(p)) if len(v) else np.nan


def bench_table(m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (basin, code), g in m[m["measured_pop"]].groupby(["basin", "live"]):
        v = g["gap_ft"].dropna()
        mm = g[g["gap_ft"].notna()]
        pairs = len({tuple(sorted(p)) for p in zip(mm["api10"], mm["nb_api10"], strict=True)})
        same = mm.loc[mm["dz_ft"] <= STAGGER_FT, "gap_ft"]
        cx = g.loc[g["lateral_closer_xy_ft"].notna() & (g["lateral_closer_xy_ft"] != SENTINEL_FT), "lateral_closer_xy_ft"]
        o = {"basin": basin, "code": code, "wells_2016plus": len(g), "wells_measured": len(v), "pairs": pairs,
             "median_ft": q(v, .5), "p10_wide_ft": q(v, .9), "p90_tight_ft": q(v, .1), "p25_ft": q(v, .25), "p75_ft": q(v, .75),
             "median_wps": 5280 / q(v, .5) if len(v) else np.nan, "p10_tight_wps": 5280 / q(v, .1) if len(v) else np.nan, "p90_wide_wps": 5280 / q(v, .9) if len(v) else np.nan,
             "under_660_pct": 100 * float((v < 660).mean()) if len(v) else np.nan, "under_500_pct": 100 * float((v < 500).mean()) if len(v) else np.nan,
             "over_1386_pct": 100 * float((v > 1.05 * FLOOR_FT).mean()) if len(v) else np.nan,
             "near_1320_pct": 100 * float(v.between(0.95 * FLOOR_FT, 1.05 * FLOOR_FT).mean()) if len(v) else np.nan,
             "near_1540_pct": 100 * float(v.between(0.95 * FLOOR_ALT_FT, 1.05 * FLOOR_ALT_FT).mean()) if len(v) else np.nan,
             "two_landings_pct": 100 * float((mm["dz_ft"] > STAGGER_FT).mean()) if len(mm) else np.nan,
             "median_same_landing_ft": q(same, .5), "median_any_neighbour_ft": q(g["gap_any_ft"].dropna(), .5),
             "novi_closer_xy_wells": len(cx), "novi_closer_xy_median_ft": q(cx, .5)}
        for dd in CODEV_SENS_DAYS:
            o[f"median_{dd}d_ft"] = q(g[f"gap_{dd}d_ft"].dropna(), .5)
        o |= {f"n_{s}": int((g["status"] == s).sum()) for s in ("no_neighbour_within_2800ft", "nearest_neighbour_pre_2016", "nearest_neighbour_not_evidence", "nearest_neighbour_other_campaign")}
        rows.append(o)
    return pd.DataFrame(rows)


def cross_check(m: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    g = m[m["measured_pop"]].copy()
    novi = g["lateral_closer_xy_ft"]
    g["novi_class"] = np.where(novi.isna(), "null", np.where(novi == SENTINEL_FT, "sentinel_2800", "bounded"))
    mine_b = g["asof_ft"].notna() & (g["asof_ft"] < SENTINEL_FT)
    g["here_class"] = np.where(mine_b, "bounded", "unbounded")
    conf = pd.crosstab([g["basin"], g["novi_class"]], g["here_class"]).reset_index()
    b = g[(g["novi_class"] == "bounded") & mine_b].copy()
    b["diff_ft"] = b["asof_ft"] - b["lateral_closer_xy_ft"]
    b["agree"] = b["diff_ft"].abs() <= np.maximum(100.0, 0.15 * b["lateral_closer_xy_ft"])
    rows, verdict = [], {}
    for key, s in [(("all", "all"), b)] + [((bs, "all"), s) for bs, s in b.groupby("basin")] + list(b.groupby(["basin", "live"])):
        rows.append({"basin": key[0], "code": key[1], "wells": len(s), "novi_median_ft": q(s["lateral_closer_xy_ft"], .5), "here_median_ft": q(s["asof_ft"], .5),
                     "median_diff_ft": q(s["diff_ft"], .5), "median_abs_diff_ft": q(s["diff_ft"].abs(), .5), "agree_pct": 100 * float(s["agree"].mean()),
                     "within_50ft_pct": 100 * float((s["diff_ft"].abs() <= 50).mean()),
                     "here_tighter_pct": 100 * float((~s["agree"] & (s["diff_ft"] < 0)).mean()), "here_wider_pct": 100 * float((~s["agree"] & (s["diff_ft"] > 0)).mean()),
                     "spearman": float(s[["asof_ft", "lateral_closer_xy_ft"]].corr(method="spearman").iloc[0, 1]) if len(s) > 2 else np.nan})
    tab = pd.DataFrame(rows)
    for r in tab[tab["code"] == "all"].itertuples():
        verdict[r.basin] = {"wells": r.wells, "median_diff_ft": r.median_diff_ft, "agree_pct": r.agree_pct,
                            "pass_median": bool(abs(r.median_diff_ft) <= CHECK_MEDIAN_DIFF_FT), "pass_agree": bool(r.agree_pct >= CHECK_AGREE_PCT)}
    verdict["unbounded_class"] = conf.to_dict("records")
    return tab, verdict


# ----------------------------------------------------------------------------
# Neighbourhoods: DSU polygon x bench
# ----------------------------------------------------------------------------


def extent_list(extents: pd.DataFrame) -> list[tuple[str, str, str, object]]:
    """(basin, extent bench, code, geometry) -- WCXY from the hand-drawn file, never the pooled WCA extent."""
    out = []
    for e in extents.itertuples():
        eg = shapely.make_valid(shapely.from_wkt(e.wkt))
        for code in ls.extent_codes(e.basin, e.bench):
            if (e.basin, code) != ("delaware", "WCXY"):
                out.append((e.basin, e.bench, code, eg))
    if WCXY_FILE.exists():
        from pyproj import Transformer

        gj = json.loads(WCXY_FILE.read_text(encoding="utf-8"))
        g = shapely.union_all([shapely.geometry.shape(f["geometry"]) for f in gj["features"] if f["properties"].get("layer") == "extent"])
        tr = Transformer.from_crs("EPSG:4326", "EPSG:3083", always_xy=True)
        out.append(("delaware", "WCXY (hand-drawn)", "WCXY", shapely.make_valid(shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1]))))))
    return out


def dsu_spacing(m: pd.DataFrame, pads: pd.DataFrame, ext: list) -> pd.DataFrame:
    parts = []
    for basin, bench, code, eg in ext:
        pb = pads[pads["basin"] == basin]
        geoms = pb["geom"].to_numpy()
        hit = np.sort(shapely.STRtree(geoms).query(eg, predicate="intersects"))
        r = pd.DataFrame({"basin": basin, "bench": bench, "code": code, "pad_id": pb["pad_id"].to_numpy()[hit], "acres": pb["acres"].to_numpy()[hit]})
        r["radius_mi"], r["n_gaps"], r["raw_median_ft"], r["p25_ft"], r["p75_ft"] = np.nan, 0, np.nan, np.nan, np.nan
        g = m[(m["basin"] == basin) & (m["live"] == code) & m["gap_ft"].notna()]
        if len(g):
            pts = shapely.points(g["x"].to_numpy(), g["y"].to_numpy())
            a, b = shapely.STRtree(pts).query(geoms[hit], predicate="dwithin", distance=RADII_MI[-1] * MI)
            pr = pd.DataFrame({"k": a, "gap": g["gap_ft"].to_numpy()[b], "dist_mi": shapely.distance(geoms[hit][a], pts[b]) / MI})
            for rad in RADII_MI:
                s = pr[pr["dist_mi"] <= rad].groupby("k")["gap"].agg(["size", "median", lambda v: v.quantile(.25), lambda v: v.quantile(.75)])
                s.columns = ["n", "med", "p25", "p75"]
                s = s[s["n"] >= MIN_GAPS]
                k = s.index.to_numpy()[np.isnan(r["radius_mi"].to_numpy()[s.index.to_numpy()])]
                r.loc[k, ["radius_mi", "n_gaps", "raw_median_ft", "p25_ft", "p75_ft"]] = np.column_stack([np.full(len(k), rad), s.loc[k, ["n", "med", "p25", "p75"]].to_numpy()])
        parts.append(r)
    ds = pd.concat(parts, ignore_index=True)
    ds["basis"] = np.where(ds["raw_median_ft"].notna(), "local", "default")
    ds["mixed"] = (ds["p75_ft"] - ds["p25_ft"]) / ds["raw_median_ft"] > SPREAD_FLAG
    return ds


def clamp(raw: pd.Series, cap: float, floor: float = FLOOR_FT) -> pd.Series:
    return raw.clip(lower=cap, upper=floor).fillna(floor)


def extent_table(ds: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (basin, bench, code), g in ds.groupby(["basin", "bench", "code"]):
        loc = g[g["basis"] == "local"]
        v = loc["raw_median_ft"]
        rows.append({"basin": basin, "bench": bench, "code": code, "dsu": len(g), "local_control_pct": 100 * len(loc) / len(g),
                     "local_control_area_pct": 100 * loc["acres"].sum() / g["acres"].sum(),
                     **{f"at_{int(r)}mi_pct": 100 * float((g["radius_mi"] == r).mean()) for r in RADII_MI},
                     "local_median_ft": q(v, .5), "local_p10_wide_ft": q(v, .9), "local_p90_tight_ft": q(v, .1),
                     "local_under_660_pct": 100 * float((v < 660).mean()) if len(v) else np.nan,
                     "local_under_500_pct": 100 * float((v < 500).mean()) if len(v) else np.nan,
                     "local_over_1320_pct": 100 * float((v > FLOOR_FT).mean()) if len(v) else np.nan,
                     "local_over_1430_pct": 100 * float((v > 1430).mean()) if len(v) else np.nan,
                     "mixed_pct": 100 * float(loc["mixed"].mean()) if len(loc) else np.nan,
                     "mean_spacing_cap660_ft": float(clamp(g["raw_median_ft"], CAP_GUESS_FT).mean())})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# 1,320 vs 1,540: what a 4-well section looks like
# ----------------------------------------------------------------------------


def section_test(u: pd.DataFrame, m: pd.DataFrame, pads: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """DSUs whose short side is one mile (+- 5 %), fully developed since 2016 on a bench (every same-tag well in the
    polygon is in the measured population): wells across the mile vs the gap between them, and how far the outer
    wells sit from the DSU edge. Uniform tiling predicts 5,280 / n; setback-packed predicts (5,280 - 660) / (n - 1)."""
    geoms = pads["geom"].to_numpy()
    pts = shapely.points(u["x"].to_numpy(), u["y"].to_numpy())
    a, b = shapely.STRtree(geoms).query(pts, predicate="within")
    first = pd.DataFrame({"w": a, "p": b}).drop_duplicates("w")
    x = m.assign(pad_ix=-1)
    x.loc[first["w"].to_numpy(), "pad_ix"] = first["p"].to_numpy()
    x = x[x["pad_ix"] >= 0]
    x["edge_ft"] = shapely.distance(shapely.boundary(geoms[x["pad_ix"].to_numpy()]), pts[x.index.to_numpy()]) * FT_PER_M   # lateral midpoint to the DSU line
    x["short_ft"] = pads["short_ft"].to_numpy()[x["pad_ix"].to_numpy()]
    rows = []
    for (basin, code, pix), g in x.groupby(["basin", "live", "pad_ix"]):
        if len(g) < 2 or not g["measured_pop"].all() or not 0.95 * 5280 <= g["short_ft"].iloc[0] <= 1.05 * 5280:
            continue
        gaps = g["gap_any_ft"].dropna()
        rows.append({"basin": basin, "code": code, "pad_id": pads["pad_id"].to_numpy()[pix], "n_wells": len(g), "median_gap_ft": q(gaps, .5),
                     "min_edge_ft": float(g["edge_ft"].min()), "fp_span_days": float((g["fp"].max() - g["fp"].min()).days)})
    s = pd.DataFrame(rows)
    s = s[s["fp_span_days"] <= CODEV_DAYS]
    agg = s.groupby(["basin", "n_wells"]).agg(dsu_benches=("pad_id", "size"), median_gap_ft=("median_gap_ft", "median"),
                                              p25_gap_ft=("median_gap_ft", lambda v: v.quantile(.25)), p75_gap_ft=("median_gap_ft", lambda v: v.quantile(.75)),
                                              median_outer_to_edge_ft=("min_edge_ft", "median")).reset_index()
    agg["uniform_ft"] = 5280 / agg["n_wells"]
    agg["setback_packed_ft"] = (5280 - 2 * SETBACK_FT) / (agg["n_wells"] - 1)
    return s, agg


def choice_table(ds: pd.DataFrame, pads: pd.DataFrame) -> pd.DataFrame:
    """What each tight cap / floor choice does: DSU x bench clamped, mean spacing, gross rows across the DSU short side
    (floor((short side - 2 x setback) / spacing) + 1; before existing wells and before any no-place cull)."""
    g = ds.merge(pads[["pad_id", "short_ft"]], on="pad_id")
    width = (g["short_ft"] - 2 * SETBACK_FT).clip(lower=0)
    rows = []
    for basin, b in [("all", g)] + list(g.groupby("basin")):
        w = width.loc[b.index]
        for cap in (440.0, 528.0, 587.0, 660.0):
            for floor in (FLOOR_FT, FLOOR_ALT_FT):
                sp_ = clamp(b["raw_median_ft"], cap, floor)
                rows.append({"basin": basin, "cap_ft": cap, "floor_ft": floor, "dsu_bench": len(b),
                             "clamped_up_to_cap_pct": 100 * float((b["raw_median_ft"] < cap).mean()),
                             "clamped_down_to_floor_pct": 100 * float((b["raw_median_ft"] > floor).mean()),
                             "no_control_at_floor_pct": 100 * float(b["raw_median_ft"].isna().mean()),
                             "mean_spacing_ft": float(sp_.mean()), "gross_rows": int((np.floor(w / sp_) + 1).sum())})
    t = pd.DataFrame(rows)
    base = t[(t["cap_ft"] == CAP_GUESS_FT) & (t["floor_ft"] == FLOOR_FT)].set_index("basin")["gross_rows"]
    t["rows_vs_660_1320_pct"] = 100 * (t["gross_rows"] / t["basin"].map(base) - 1)
    return t


# ----------------------------------------------------------------------------
# Novi sticks in the same DSUs
# ----------------------------------------------------------------------------


def novi_compare(d: dict, sg: pd.DataFrame, u: pd.DataFrame, pads: pd.DataFrame, ds: pd.DataFrame, cap: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s = d["sticks"].dropna(subset=["x", "y", "code"]).merge(sg, on="stick_id", how="inner").reset_index(drop=True)
    s["geom"] = shapely.from_wkt(s["wkt"].to_numpy())
    s = s[shapely.length(s["geom"].to_numpy()) > 1.0].reset_index(drop=True)
    t = pair_table(s["geom"].to_numpy(), (s["basin"] + "|" + s["code"]).to_numpy())
    gap, _ = nearest(t, len(s))
    s["gap_ft"] = np.where(gap < UNBOUNDED_FT, gap, np.nan)
    geoms = pads["geom"].to_numpy()
    tree = shapely.STRtree(geoms)

    def pad_of(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        a, b = tree.query(shapely.points(x, y), predicate="within")
        f = pd.DataFrame({"w": a, "p": b}).drop_duplicates("w")
        out = np.full(len(x), -1)
        out[f["w"].to_numpy()] = f["p"].to_numpy()
        return out

    pid = pads["pad_id"].to_numpy()
    sp_ = pad_of(s["x"].to_numpy(float), s["y"].to_numpy(float))
    s["pad_id"] = np.where(sp_ >= 0, pid[np.maximum(sp_, 0)], None)
    up = pad_of(u["x"].to_numpy(), u["y"].to_numpy())
    ex = pd.DataFrame({"basin": u["basin"], "code": u["live"], "pad_id": np.where(up >= 0, pid[np.maximum(up, 0)], None)}).dropna(subset=["pad_id"])
    ex = ex.groupby(["basin", "code", "pad_id"]).size().rename("existing_wells").reset_index()
    print("Novi sticks with midpoint in no polygon:", s[s["pad_id"].isna()].groupby("basin").size().to_dict(), "of", s.groupby("basin").size().to_dict(), flush=True)
    by_bench = s.groupby(["basin", "code"]).agg(sticks=("stick_id", "size"), with_gap=("gap_ft", "count"), novi_median_gap_ft=("gap_ft", "median"),
                                                novi_p25_ft=("gap_ft", lambda v: v.quantile(.25)), novi_p75_ft=("gap_ft", lambda v: v.quantile(.75))).reset_index()
    by_bench["novi_median_wps"] = 5280 / by_bench["novi_median_gap_ft"]
    nd = s[s["pad_id"].notna()].groupby(["basin", "code", "pad_id"]).agg(novi_sticks=("stick_id", "size"), novi_gaps=("gap_ft", "count"), novi_gap_ft=("gap_ft", "median")).reset_index()
    box = ds.drop_duplicates(["basin", "code", "pad_id"]).assign(box_ft=lambda f: clamp(f["raw_median_ft"], cap))
    c = nd.merge(box[["basin", "code", "pad_id", "basis", "raw_median_ft", "box_ft"]], on=["basin", "code", "pad_id"], how="left")
    c = c.merge(ex, on=["basin", "code", "pad_id"], how="left").merge(pads[["pad_id", "short_ft", "long_ft", "well_type"]], on="pad_id", how="left")
    c["existing_wells"] = c["existing_wells"].fillna(0).astype(int)
    c["in_box_extent"] = c["box_ft"].notna()
    c["diff_ft"] = c["box_ft"] - c["novi_gap_ft"]
    c["box_rows"] = np.floor((c["short_ft"] - 2 * SETBACK_FT).clip(lower=0) / c["box_ft"]) + 1
    c["novi_rows"] = c["novi_sticks"] + c["existing_wells"]
    rows = []
    cc = c[c["in_box_extent"]]
    for key, g in [(("all", "all", "all"), cc)] + [((b, "all", "all"), g) for b, g in cc.groupby("basin")] \
            + [((b, "all", bs), g) for (b, bs), g in cc.groupby(["basin", "basis"])] + [((b, cd, "all"), g) for (b, cd), g in cc.groupby(["basin", "code"])]:
        h = g[g["novi_gap_ft"].notna()]
        rows.append({"basin": key[0], "code": key[1], "box_basis": key[2], "dsu_benches": len(g), "with_novi_gap": len(h),
                     "novi_median_ft": q(h["novi_gap_ft"], .5), "box_median_ft": q(h["box_ft"], .5), "box_mean_ft": float(h["box_ft"].mean()) if len(h) else np.nan,
                     "novi_mean_ft": float(h["novi_gap_ft"].mean()) if len(h) else np.nan,
                     "box_tighter_10pct": 100 * float((h["diff_ft"] < -0.10 * h["novi_gap_ft"]).mean()) if len(h) else np.nan,
                     "within_10pct": 100 * float((h["diff_ft"].abs() <= 0.10 * h["novi_gap_ft"]).mean()) if len(h) else np.nan,
                     "box_wider_10pct": 100 * float((h["diff_ft"] > 0.10 * h["novi_gap_ft"]).mean()) if len(h) else np.nan,
                     "novi_rows": int(g["novi_rows"].sum()), "box_rows": int(g["box_rows"].sum()),
                     "rows_change_pct": 100 * (g["box_rows"].sum() / g["novi_rows"].sum() - 1)})
    return by_bench, c, pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------


def _polys(ax, geoms, vals, cmap, vmin, vmax):
    pc = PolyCollection([np.asarray(g.exterior.coords) / MI for g in geoms], array=np.asarray(vals, float), cmap=cmap, linewidths=0.1, edgecolors="#9ca3af")
    pc.set_clim(vmin, vmax)
    ax.add_collection(pc)
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    return pc


def focus_maps(ds: pd.DataFrame, cmp_: pd.DataFrame, m: pd.DataFrame, pads: pd.DataFrame, ext: list, cap: float, out: Path) -> list[str]:
    files = []
    pg = pads.set_index("pad_id")["geom"]
    pg = pg[pg.map(lambda g: g.geom_type == "Polygon")]
    for basin, code in FOCUS:
        g = ds[(ds["basin"] == basin) & (ds["code"] == code) & ds["pad_id"].isin(pg.index)]
        eg = next(e[3] for e in ext if e[0] == basin and e[2] == code)
        fig, axes = plt.subplots(1, 3, figsize=(21, 8))
        loc, dfl = g[g["basis"] == "local"], g[g["basis"] == "default"]
        ax = axes[0]
        ax.add_collection(PolyCollection([np.asarray(x.exterior.coords) / MI for x in pg.loc[dfl["pad_id"]]], facecolors="#e5e7eb", linewidths=0.1, edgecolors="#9ca3af"))
        pc = _polys(ax, pg.loc[loc["pad_id"]], clamp(loc["raw_median_ft"], cap), "viridis_r", cap, FLOOR_FT)
        w = m[(m["basin"] == basin) & (m["live"] == code) & m["gap_ft"].notna()]
        ax.scatter(w["x"] / MI, w["y"] / MI, s=2, c="black", linewidths=0)
        fig.colorbar(pc, ax=ax, shrink=0.6).set_label("BOX spacing, ft (local median, clamped)")
        ax.set_title(f"BOX spacing: {len(loc):,} of {len(g):,} DSUs with local control ({100 * len(loc) / len(g):.0f} %)\n"
                     f"grey = no control -> {FLOOR_FT:,.0f} ft (4 WPS); dots = {len(w):,} measured wells", fontsize=10)
        c = cmp_[(cmp_["basin"] == basin) & (cmp_["code"] == code) & cmp_["novi_gap_ft"].notna() & cmp_["pad_id"].isin(pg.index)]
        ax = axes[1]
        pc = _polys(ax, pg.loc[c["pad_id"]], c["novi_gap_ft"].clip(cap, 1760), "viridis_r", cap, 1760)
        fig.colorbar(pc, ax=ax, shrink=0.6).set_label("Novi stick gap in the DSU, ft")
        ax.set_title(f"Novi 2026Q3 stick gap: {len(c):,} DSUs with >= 1 measurable gap\nmedian {c['novi_gap_ft'].median():,.0f} ft", fontsize=10)
        ax = axes[2]
        cb = c[c["box_ft"].notna()]
        pc = _polys(ax, pg.loc[cb["pad_id"]], cb["diff_ft"].clip(-660, 660), "RdBu", -660, 660)
        fig.colorbar(pc, ax=ax, shrink=0.6).set_label("BOX minus Novi spacing, ft (red = BOX tighter, more wells)")
        ax.set_title(f"BOX minus Novi: median {cb['diff_ft'].median():+,.0f} ft over {len(cb):,} DSUs", fontsize=10)
        for ax in axes:
            for poly in shapely.get_parts(eg):
                if poly.geom_type == "Polygon":
                    ex, ey = poly.exterior.xy
                    ax.plot(np.asarray(ex) / MI, np.asarray(ey) / MI, color="#111827", lw=0.8)
            ax.autoscale()
        fig.suptitle(f"{basin} {code}: realized spacing by DSU (tight cap {cap:,.0f} ft shown; black outline = BOX record extent)", fontsize=13)
        f = out / f"spacing_map_{basin}_{code}.png"
        fig.savefig(f, dpi=110, bbox_inches="tight")
        plt.close(fig)
        files.append(f.name)
    return files


def hist_fig(m: pd.DataFrame, ds: pd.DataFrame, out: Path) -> str:
    fig, axes = plt.subplots(2, 2, figsize=(15, 9))
    bins = np.arange(300, 2820, 20)
    for k, basin in enumerate(("delaware", "midland")):
        v = m.loc[(m["basin"] == basin) & m["gap_ft"].notna(), "gap_ft"]
        ax = axes[0, k]
        ax.hist(v, bins=bins, color="#2563eb")
        ax.set_title(f"{basin}: per-well gap to the nearest co-developed same-bench neighbour ({len(v):,} wells)", fontsize=10)
        r = ds.loc[(ds["basin"] == basin) & ds["raw_median_ft"].notna(), "raw_median_ft"]
        ax = axes[1, k]
        ax.hist(r, bins=bins, color="#059669")
        ax.set_title(f"{basin}: local median per DSU x bench, before clamping ({len(r):,})", fontsize=10)
        for ax in axes[:, k]:
            for x, lab in ((440, "12"), (528, "10"), (660, "8"), (880, "6"), (1056, "5"), (1320, "4"), (1540, "1,540 ft"), (1760, "3"), (2640, "2")):
                ax.axvline(x, color="#dc2626", lw=0.6, ls="--")
                ax.text(x, ax.get_ylim()[1] * 0.95, lab, color="#dc2626", fontsize=7, ha="center")
            ax.set_xlabel("ft (dashed: wells per section = 5,280 / spacing)")
    f = out / "gap_histograms.png"
    fig.savefig(f, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f.name


# ----------------------------------------------------------------------------


def run(out: Path, cache: Path, cap: float) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    wg, sg = pull_geoms(cache)
    u = universe(d, wg, cache)
    print(f"universe {len(u):,}; measured population {int(u['measured_pop'].sum()):,}", flush=True)
    t = pair_table(u["geom"].to_numpy(), (u["basin"] + "|" + u["live"]).to_numpy())
    print(f"pair table {len(t):,}", flush=True)
    repro = method_check(u, nearest(t, len(u))[0])
    print(json.dumps(repro, indent=1), flush=True)
    m = measure(u, t)
    bt = bench_table(m)
    bt.to_csv(out / "spacing_by_bench.csv", index=False)
    xc, verdict = cross_check(m)
    xc.to_csv(out / "crosscheck_closer_xy.csv", index=False)
    m.drop(columns=["x", "y"]).to_csv(out / "well_gaps.csv.gz", index=False, compression="gzip")

    pads = p0.pad_frame(d["pads"])
    ext = extent_list(d["extents"])
    ds = dsu_spacing(m, pads, ext)
    ds.to_csv(out / "spacing_dsu_bench.csv.gz", index=False, compression="gzip")
    et = extent_table(ds)
    et.to_csv(out / "spacing_by_extent.csv", index=False)
    choice_table(ds, pads).to_csv(out / "cap_floor_choices.csv", index=False)
    sec, sec_agg = section_test(u, m, pads)
    sec.to_csv(out / "one_mile_dsu_benches.csv", index=False)
    sec_agg.to_csv(out / "one_mile_dsu_wells_vs_gap.csv", index=False)
    nb, cmp_, cmp_tab = novi_compare(d, sg, u, pads, ds, cap)
    nb.to_csv(out / "novi_stick_gap_by_bench.csv", index=False)
    cmp_.to_csv(out / "novi_vs_box_dsu_bench.csv.gz", index=False, compression="gzip")
    cmp_tab.to_csv(out / "novi_vs_box_summary.csv", index=False)
    maps = focus_maps(ds, cmp_, m, pads, ext, cap, out) + [hist_fig(m, ds, out)]

    def basin_summary(g: pd.DataFrame, dsg: pd.DataFrame) -> dict:
        v, r = g["gap_ft"].dropna(), dsg["raw_median_ft"].dropna()
        mm = g[g["gap_ft"].notna()]
        return {"wells_2016plus_in_population": int(g["measured_pop"].sum()), "wells_measured": len(v),
                "pairs": len({tuple(sorted(p)) for p in zip(mm["api10"], mm["nb_api10"], strict=True)}),
                "status": g.loc[g["measured_pop"], "status"].value_counts().to_dict(),
                "median_ft": q(v, .5), "p10_wide_ft": q(v, .9), "p90_tight_ft": q(v, .1),
                "gap_quantiles_ft": {str(p): q(v, p) for p in (.01, .02, .05, .10, .25, .5, .75, .9, .95)},
                "under_660_pct": 100 * float((v < 660).mean()), "under_500_pct": 100 * float((v < 500).mean()), "under_440_pct": 100 * float((v < 440).mean()),
                "under_660_two_landings_pct": 100 * float((mm.loc[mm["gap_ft"] < 660, "dz_ft"] > STAGGER_FT).mean()),
                "all_two_landings_pct": 100 * float((mm["dz_ft"] > STAGGER_FT).mean()),
                "near_1320_pct": 100 * float(v.between(1254, 1386).mean()), "near_1540_pct": 100 * float(v.between(1463, 1617).mean()),
                "between_1386_1463_pct": 100 * float(v.between(1386, 1463).mean()), "over_1617_pct": 100 * float((v > 1617).mean()),
                "dsu_bench": len(dsg), "dsu_bench_local_pct": 100 * float((dsg["basis"] == "local").mean()),
                "local_median_quantiles_ft": {str(p): q(r, p) for p in (.01, .02, .05, .10, .25, .5, .75, .9, .95)},
                "local_under_660_pct": 100 * float((r < 660).mean()), "local_under_600_pct": 100 * float((r < 600).mean()),
                "local_under_500_pct": 100 * float((r < 500).mean()), "local_under_440_pct": 100 * float((r < 440).mean()),
                "local_over_1320_pct": 100 * float((r > 1320).mean()), "local_1254_1386_pct": 100 * float(r.between(1254, 1386).mean()),
                "local_1463_1617_pct": 100 * float(r.between(1463, 1617).mean()), "local_over_1617_pct": 100 * float((r > 1617).mean()),
                "mixed_pct_of_local": 100 * float(dsg.loc[dsg["basis"] == "local", "mixed"].mean())}

    summary = {"generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "code_sha": p0._git_sha(), "tags": "live",
               "params": {"parallel_tol_deg": TOL_DEG, "overlap_min_frac": OVERLAP_MIN, "same_slot_ft": SAME_SLOT_FT, "search_ft": SEARCH_FT, "min_gaps": MIN_GAPS,
                          "radii_mi": RADII_MI, "codev_days": CODEV_DAYS, "unbounded_ft": UNBOUNDED_FT, "stagger_ft": STAGGER_FT, "cap_shown_ft": cap},
               "universe_wells": len(u), "geometry_check": {"median_line_len_over_lateral_length": float((shapely.length(u["geom"].to_numpy()) * FT_PER_M / u["lateral_length_ft"]).median())},
               "method_reproduction": repro, "crosscheck": verdict,
               "basins": {b: basin_summary(g, ds[ds["basin"] == b]) for b, g in m.groupby("basin")}, "figures": maps}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--cap", type=float, default=CAP_GUESS_FT, help="tight cap used for the maps and the Novi comparison")
    a = ap.parse_args(argv)
    run(a.out, a.cache, a.cap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
