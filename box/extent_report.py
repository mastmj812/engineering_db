"""BOX step 3 — extents build, calibration backtest, geology package and review pages.

Read-only against the warehouse (laterals + the D1 PUD universe count, READ ONLY transactions).
box/extent.py holds the pure rule; box/geology_io.py the shapefile round-trip.

Calibration (plan §5 step 3: "k and cap calibrated on WCA + BS2_S together"): a time-split
backtest. For each cutoff T, the step-2 metric is rebuilt from the laterals online before T only
(12-mo oil known only when 12 months had elapsed by T); every buffer config is then scored on the
wells that came online after T and landed outside the T core within 3 mi: share of PERFORMING ones
(12-mo oil/ft >= 0.70 × the T interior median) the extent would have contained, minus the share of
ROLLED ones it would have contained (J = TPR - FPR). The config with the best J pooled over both
pools and both cutoffs wins; ties within 0.02 go to the smaller added area.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiPolygon, Polygon

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import extent as ex
from box import geology_io as gio

POOLS = egr.POOLS
MEMBERS = {"WCA": ("WCA_1", "WCA_2"), "BS2_S": ("BS2_S",)}  # PUD benches per pool (WCXY PUDs reported apart, D20)
EDGE = eg.EdgeParams(pin_radius_ft=2640.0, close_ft=3960.0)  # D23: the metric of record
CUTOFFS = (dt.date(2021, 1, 1), dt.date(2023, 1, 1))
GRID = {
    "k": (0.25, 0.5, 0.75, 1.0),
    "cap_ft": (2640.0, 3960.0, 5280.0, 7920.0, 10560.0),
    "floor_ft": (660.0, 880.0, 1320.0),
    "perf_ref": ("pool", "local"),
}
EVAL_REACH_FT = 3 * eg.FT_PER_MI  # later wells scored only within 3 mi of the T core
EVAL_STEP_FT = 250.0
AREA_CELL_FT = 528.0  # 0.1-mi grid for the area estimate
J_TIE = 0.02
MIN_FLOOR_FT = 880.0  # next-row rule: the next development row beyond a producer (narvi's 880-ft fallback spacing) is always inside
UNIFORM_FT = (660.0, 1320.0, 1980.0, 2640.0, 3960.0, 5280.0)  # flat-buffer baselines
SOPA_DIR = Path("docs") / "box" / "ref" / "potash_sopa_1986"


# ----------------------------------------------------------------------------
# Inputs
# ----------------------------------------------------------------------------


def load_sopa(path: Path = SOPA_DIR / "CFO_POTASH_SOPA_1986.shp") -> Any:
    """BLM Carlsbad FO Secretary's Potash Area (1986 order boundary; EPSG:26913 metres) -> UTM 13N ft."""
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:26913", "EPSG:4326", always_xy=True)
    polys = [shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1]))) for g, _ in gio.read_layer(path)]
    return shapely.union_all(eg.to_ft(polys))


def at_cutoff(d: pd.DataFrame, T: dt.date | None) -> pd.DataFrame:
    """Pool wells as known at T: online before T; 12-mo oil / cohort only if 12 months elapsed."""
    if T is None:
        return d
    x = d[d["first_production_date"] < T].copy()
    late = x["first_production_date"] > (T - dt.timedelta(days=365))
    x.loc[late, "cohort"] = False
    x.loc[late, "oil12_kft"] = np.nan
    return x


# ----------------------------------------------------------------------------
# Prep (one pool, one cutoff)
# ----------------------------------------------------------------------------


@dataclass
class Prep:
    pool: str
    T: dt.date | None
    r: dict[str, Any]  # edge_gap_report.analyse_pool result
    seg: pd.DataFrame  # + local perf
    fronts: dict[str, Any]
    stepouts: pd.DataFrame  # + role
    core: MultiPolygon
    xy: np.ndarray
    seg_ix: np.ndarray
    interior_median: float


def prep(d: pd.DataFrame, pool: str, T: dt.date | None, bp: ex.BufferParams = ex.DEFAULT, p: eg.EdgeParams = EDGE) -> Prep:
    x = at_cutoff(d, T)
    r = egr.analyse_pool(x, p)
    ev, body = r["ev"], r["body"]
    lines = list(ev["geom"])
    oil = ev["oil12_kft"].to_numpy(float)
    coh = ev["cohort"].to_numpy(bool) & np.isfinite(oil)
    im = eg.interior_mask(body, lines, p)
    med = float(r["stats"]["interior_median_oil12_kft"])
    seg = ex.local_perf(r["seg"], lines, oil, im & coh, med, bp)
    so = r["stepouts"].copy()
    fronts = ex.front_sides(so, bp)
    so["role"] = ex.stepout_roles(so, fronts, bp)
    so["class"] = ex.stepout_class(so)
    islands = [lines[i] for i in so.loc[so.role == "island", "ix"]]
    body_lines = [ln for ln in lines if ln.intersects(body)]
    c = ex.core(body, body_lines, islands, p.pin_radius_ft, bp)
    xy, six = ex.ring_samples(seg, body, bp.sample_ft)
    return Prep(pool, T, r, seg, fronts, so, c, xy, six, med)


def configs(grid: dict[str, tuple[Any, ...]] = GRID, uniform: tuple[float, ...] = UNIFORM_FT) -> list[ex.BufferParams]:
    keys = list(grid)
    rule = [replace(ex.DEFAULT, **dict(zip(keys, v))) for v in itertools.product(*grid.values())]
    return rule + [replace(ex.DEFAULT, uniform=True, k=0.0, cap_ft=u, floor_ft=u, perf_ref="pool") for u in uniform]


# ----------------------------------------------------------------------------
# Backtest
# ----------------------------------------------------------------------------


def _sample_lines(lines: list[LineString], step: float) -> tuple[np.ndarray, np.ndarray]:
    xy, who = [], []
    for i, ln in enumerate(lines):
        n = max(2, math.ceil(ln.length / step) + 1)
        xy.append(shapely.get_coordinates(shapely.line_interpolate_point(ln, np.linspace(0, ln.length, n))))
        who.append(np.full(n, i))
    return np.vstack(xy), np.concatenate(who)


def backtest_pool(d: pd.DataFrame, pool: str, T: dt.date, sopa: Any, cfgs: list[ex.BufferParams]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score every config on the wells online at/after T (one pool, one cutoff)."""
    pr = prep(d, pool, T)
    new = d[(d["first_production_date"] >= T) & d["geom"].notna()].reset_index(drop=True)
    lines = list(new["geom"])
    cd = ex.CoreDistance(pr.core)
    pxy, who = _sample_lines(lines, EVAL_STEP_FT)
    dist = cd.distance(pxy, EVAL_REACH_FT)
    n = len(new)
    out_frac = ex.well_inside_fraction(who, dist > 0, n)
    dmin = np.full(n, np.inf)
    np.minimum.at(dmin, who, dist)
    tree = cKDTree(pr.xy)
    _, nn = tree.query(pxy)
    mid_xy = np.asarray([ln.interpolate(0.5, normalized=True).coords[0] for ln in lines])
    in_hole = pr.seg_ix[tree.query(mid_xy)[1]] == ex.HOLE  # infill of a hole open at T, not an edge test
    scored = (out_frac >= 0.5) & (dmin <= EVAL_REACH_FT) & ~in_hole
    ratio = new["oil12_kft"].to_numpy(float) / pr.interior_median
    known = new["cohort"].to_numpy(bool) & np.isfinite(ratio)
    good = scored & known & (ratio >= eg.PERF_ROLLED)
    rolled = scored & known & (ratio < eg.PERF_ROLLED)
    sop = shapely.contains_xy(sopa, pxy[:, 0], pxy[:, 1]) if sopa is not None else np.zeros(len(pxy), bool)
    # area grid: added area (outside the core, inside the extent)
    gmax = max(c.cap_ft for c in cfgs) * 1.0 + AREA_CELL_FT
    b0 = pr.core.bounds
    gx = np.arange(b0[0] - gmax, b0[2] + gmax, AREA_CELL_FT)
    gy = np.arange(b0[1] - gmax, b0[3] + gmax, AREA_CELL_FT)
    GX, GY = np.meshgrid(gx, gy)
    gxy = np.column_stack([GX.ravel(), GY.ravel()])
    gd = cd.distance(gxy, gmax)
    keep = np.isfinite(gd) & (gd > 0)
    gxy, gd = gxy[keep], gd[keep]
    _, gnn = tree.query(gxy)
    gsop = shapely.contains_xy(sopa, gxy[:, 0], gxy[:, 1]) if sopa is not None else np.zeros(len(gxy), bool)
    cell_sqmi = (AREA_CELL_FT / eg.FT_PER_MI) ** 2
    rows = []
    for c in cfgs:
        for with_fronts in (True, False):
            if c.uniform and not with_fronts:
                continue
            sb = ex.segment_buffers(pr.seg, c, pr.fronts if with_fronts else {}, sopa)
            b, f = ex.sample_buffers(pr.seg_ix, sb, c.floor_ft)
            inside = dist <= ex.point_buffer(nn, sop, b, f)
            cap = ex.captured(ex.well_inside_fraction(who, inside, n))
            s = ex.score(good, rolled, cap)
            s["added_sqmi"] = float((gd <= ex.point_buffer(gnn, gsop, b, f)).sum() * cell_sqmi)
            rows.append({"pool": pool, "cutoff": str(T), "uniform": c.uniform, "fronts": with_fronts, **{k: getattr(c, k) for k in GRID}, **s})
    # per later well: where it landed relative to the T edge, and how it performed (the "does the
    # edge class predict the next well" table)
    mix = pr.seg_ix[tree.query(mid_xy)[1]]
    segk = pr.seg.reindex(np.where(mix >= 0, mix, pr.seg.index[0]))
    wells = pd.DataFrame(
        {
            "pool": pool,
            "cutoff": str(T),
            "api10": new["api10"].to_numpy(),
            "first_production_date": new["first_production_date"].to_numpy(),
            "dist_ft": dmin,
            "outside_core": out_frac >= 0.5,
            "in_hole": in_hole,
            "edge_kind": np.where(mix >= 0, segk["kind"].to_numpy(), "hole"),
            "edge_perf": np.where(mix >= 0, segk["perf_class"].to_numpy(), "hole"),
            "edge_gap_ft": np.where(mix >= 0, np.where(segk["kind"].to_numpy() == "gap", segk["length_ft"].to_numpy(float), 0.0), np.nan),
            "side": np.where(mix >= 0, segk["side"].to_numpy(), "hole"),
            "front_side": np.where(mix >= 0, segk["side"].isin(list(pr.fronts)).to_numpy(), False),
            "in_sopa": shapely.contains_xy(sopa, mid_xy[:, 0], mid_xy[:, 1]) if sopa is not None else False,
            "known": known,
            "perf_ratio": ratio,
            "scored": scored,
            "good": good,
            "rolled": rolled,
        }
    )
    info = {
        "pool": pool,
        "cutoff": str(T),
        "n_before": len(pr.r["ev"]),
        "n_after": n,
        "n_after_outside_core": int(((out_frac >= 0.5)).sum()),
        "n_scored": int(scored.sum()),
        "n_hole_infill": int(((out_frac >= 0.5) & in_hole).sum()),
        "n_scored_no12": int((scored & ~known).sum()),
        "n_beyond_reach": int(((out_frac >= 0.5) & (dmin > EVAL_REACH_FT)).sum()),
        "interior_median": pr.interior_median,
        "fronts": pr.fronts,
        "core_sqmi": pr.core.area / eg.FT_PER_MI**2,
        "wells": wells,
    }
    return pd.DataFrame(rows), info


def choose(bt: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Pool the backtest over pools and cutoffs; best J, ties (within J_TIE) to the smaller area."""
    keys = ["uniform", *GRID]
    g = bt[bt["fronts"]].groupby(keys, as_index=False).agg(
        n_good=("n_good", "sum"), n_rolled=("n_rolled", "sum"), hit_good=("hit_good", "sum"), hit_rolled=("hit_rolled", "sum"), added_sqmi=("added_sqmi", "sum")
    )
    g["tpr"] = g.hit_good / g.n_good
    g["fpr"] = g.hit_rolled / g.n_rolled
    g["j"] = g.tpr - g.fpr
    g["precision"] = g.hit_good / (g.hit_good + g.hit_rolled)
    elig = ~g.uniform & (g.floor_ft >= MIN_FLOOR_FT)
    best_pool = g.loc[elig & (g.perf_ref == "pool"), "j"].max()
    best_local = g.loc[elig & (g.perf_ref == "local"), "j"].max()
    ref = "local" if best_local > best_pool + J_TIE else "pool"  # §6 pool-wide reference unless local clearly wins
    best = g.loc[elig & (g.perf_ref == ref), "j"].max()
    cand = g[elig & (g.perf_ref == ref) & (g.j >= best - J_TIE)].sort_values(["added_sqmi", "j"], ascending=[True, False])
    pick = cand.iloc[0].to_dict()
    pick.update(best_j_pool=best_pool, best_j_local=best_local)
    g = g.sort_values(["j", "added_sqmi"], ascending=[False, True]).reset_index(drop=True)
    return g, pick


# ----------------------------------------------------------------------------
# Final build (all data, the chosen config)
# ----------------------------------------------------------------------------


def edges_frame(pr: Prep, sb: pd.DataFrame, runs: list[dict[str, Any]], bp: ex.BufferParams) -> pd.DataFrame:
    """One row per extent-boundary run, carrying the walked segment's 2×2 + buffer + flag."""
    seg = pr.seg.join(sb)
    seg["flag"] = seg.apply(ex.geology_flag, axis=1)
    rows = []
    for k, r in enumerate(runs):
        if r["seg"] == ex.HOLE:
            rows.append({"edge_no": k, "seg_no": -1, "edge_class": "hole", "side": "", "gap_ft": np.nan, "perf_class": "", "perf_ratio": np.nan, "buffer_ft": bp.floor_ft,
                         "rule": "hole: tightest floor", "flag": "hole in the drilled body: geology hole or surface? (fill / keep)", "geom": r["geom"]})
            continue
        s = seg.loc[r["seg"]]
        rows.append(
            {
                "edge_no": k,
                "seg_no": int(s["seg_no"]),
                "edge_class": s["kind"],
                "side": s["side"],
                "gap_ft": float(s["length_ft"]) if s["kind"] == "gap" else 0.0,
                "perf_class": s["perf_used"],
                "perf_ratio": float(s["perf_ratio_local"] if bp.perf_ref == "local" else s["perf_ratio"]),
                "buffer_ft": float(s["buffer_ft"]),
                "rule": s["rule"],
                "flag": s["flag"],
                "geom": r["geom"],
            }
        )
    e = pd.DataFrame(rows)
    e["length_ft"] = [g.length for g in e.geom]
    return e


def build_pool(d: pd.DataFrame, pool: str, bp: ex.BufferParams, sopa: Any) -> dict[str, Any]:
    pr = prep(d, pool, None, bp)
    sb = ex.segment_buffers(pr.seg, bp, pr.fronts, sopa)
    b, f = ex.sample_buffers(pr.seg_ix, sb, bp.floor_ft)
    ext, _cells = ex.build_extent(pr.core, pr.xy, b, f, sopa, bp)
    runs = ex.edge_runs(ext, pr.xy, pr.seg_ix)
    edges = edges_frame(pr, sb, runs, bp)
    seg = pr.seg.join(sb)
    seg["flag"] = seg.apply(ex.geology_flag, axis=1)
    body = pr.r["body"]
    holes = []
    for h in body.interiors:
        hp = Polygon(h)
        c = eg.to_lonlat([hp.representative_point()])[0]
        holes.append({"area_sqmi": hp.area / eg.FT_PER_MI**2, "sopa_share": hp.intersection(sopa).area / hp.area if sopa is not None else 0.0, "lon": c.x, "lat": c.y,
                      "still_hole_in_extent": not ext.contains(hp.representative_point()), "geom": hp})
    holes_df = pd.DataFrame(holes, columns=["area_sqmi", "sopa_share", "lon", "lat", "still_hole_in_extent", "geom"]).sort_values("area_sqmi", ascending=False).reset_index(drop=True)
    per = seg.groupby("rule").length_ft.sum() / eg.FT_PER_MI
    stats = {
        "extent_sqmi": ext.area / eg.FT_PER_MI**2,
        "core_sqmi": pr.core.area / eg.FT_PER_MI**2,
        "outline_step2_sqmi": float(sum(g.area for g in pr.r["outline"].geoms) / eg.FT_PER_MI**2),
        "n_parts": len(ext.geoms),
        "n_holes": int(sum(len(g.interiors) for g in ext.geoms)),
        "perimeter_mi": float(sum(g.exterior.length for g in ext.geoms) / eg.FT_PER_MI),
        "walked_mi_by_rule": per.round(1).to_dict(),
        "buffer_ft_median": float(np.median(seg.buffer_ft)) if len(seg) else float("nan"),
        "buffer_ft_weighted_mean": float(np.average(seg.buffer_ft, weights=seg.length_ft)),
        "fronts": pr.fronts,
        "stepout_roles": pr.stepouts.role.value_counts().to_dict(),
        "n_evidence": len(pr.r["ev"]),
        "n_pre2016": len(pr.r["old"]),
        "interior_median_oil12_kft": pr.interior_median,
        "flagged_pinned_strong_mi": float(seg.loc[(seg.kind == "pinned") & (seg.perf_used == "strong"), "length_ft"].sum() / eg.FT_PER_MI),
    }
    return {"prep": pr, "seg": seg, "extent": ext, "edges": edges, "holes": holes_df, "stats": stats}


# ----------------------------------------------------------------------------
# D1 universe count (read-only)
# ----------------------------------------------------------------------------

_PUD_SQL = """
SELECT il.stick_id, fb.formation_blueox, ri.status, ST_AsText(il.wellstick_geom)
FROM curated.intel_locations il
JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
LEFT JOIN curated.reconciled_inventory ri ON ri.stick_id = il.stick_id
WHERE il.category = 'PUD'
  AND il.basin = 'delaware'
  AND fb.formation_blueox = ANY(%(benches)s)
  AND il.wellstick_geom IS NOT NULL
  AND il.wellstick_geom && ST_MakeEnvelope(%(x0)s, %(y0)s, %(x1)s, %(y1)s, 4326)
"""


def pull_puds(conn: Any, benches: list[str], bounds_ll: tuple[float, float, float, float]) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_PUD_SQL, {"benches": benches, "x0": bounds_ll[0], "y0": bounds_ll[1], "x1": bounds_ll[2], "y1": bounds_ll[3]})
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=["stick_id", "formation_blueox", "status", "wkt"])


def pud_counts(puds: pd.DataFrame, polys: dict[str, Any]) -> pd.DataFrame:
    """D1 universe (remaining_pud ∪ NULL ∪ conflict; Novi PUD category only, no RES) with >= 50 % of
    the stick inside each polygon (co-extent overlap, rule 9). Rows: bench × status class."""
    if puds.empty:
        return pd.DataFrame()
    g = eg.to_ft(list(shapely.from_wkt(puds["wkt"])))
    d = puds.assign(status=puds["status"].fillna("NULL (not yet reconciled)"))
    d["d1"] = d["status"].isin(["remaining_pud", "conflict", "NULL (not yet reconciled)"])
    L = np.asarray([x.length for x in g])
    for name, poly in polys.items():
        shapely.prepare(poly)
        inter = shapely.length(shapely.intersection(np.asarray(g, dtype=object), poly))
        d[name] = np.divide(inter, L, out=np.zeros(len(L)), where=L > 0) >= 0.5
    out = d.groupby(["formation_blueox", "status"])[list(polys)].sum().reset_index()
    tot = d[d.d1].groupby("formation_blueox")[list(polys)].sum().reset_index().assign(status="D1 universe")
    return pd.concat([out, tot], ignore_index=True).sort_values(["formation_blueox", "status"]).reset_index(drop=True)


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------


def _geojson(b: dict[str, Any], pool: str, version: int, bp: ex.BufferParams, built: str) -> dict[str, Any]:
    from shapely.geometry import mapping

    def rnd(g: Any) -> Any:
        return shapely.set_precision(g, 1e-6)

    feats = [{"type": "Feature", "properties": {"layer": "extent", "pool": pool, "basin": "delaware", "version": version, "source": "generated", "built": built},
              "geometry": mapping(rnd(eg.to_lonlat([b["extent"]])[0]))}]
    e = b["edges"]
    for (_, r), g in zip(e.iterrows(), eg.to_lonlat([x.simplify(20.0) for x in e.geom])):
        g = rnd(g)
        props = {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in r.drop(labels=["geom"]).items()}
        feats.append({"type": "Feature", "properties": {"layer": "edge", **props}, "geometry": mapping(g)})
    return {"type": "FeatureCollection", "name": f"box_extent_{pool}_v{version}", "crs_note": "EPSG:4326", "params": asdict(bp), "edge_params": asdict(EDGE), "features": feats}


def run(conn: Any, wells_dir: Path, out: Path, version: int = 1, df: pd.DataFrame | None = None, puds: bool = True) -> dict[str, Any]:
    import json

    from box import extent_package as pkg
    from box import extent_pages as pages

    out.mkdir(parents=True, exist_ok=True)
    geo_dir = out / "geology"
    if df is None:
        df = egr.load_final_sets(wells_dir, POOLS)
        df = egr.attach_geometry(df, egr.pull_laterals(conn, sorted(df["api10"].unique())))
    sopa = load_sopa()
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    # 1. calibration backtest
    cfgs = configs()
    bts, infos = [], []
    for pool in POOLS:
        for T in CUTOFFS:
            bt, info = backtest_pool(df[df.pool == pool], pool, T, sopa, cfgs)
            bts.append(bt)
            infos.append(info)
    bt = pd.concat(bts, ignore_index=True)
    grid, pick = choose(bt)
    bp = replace(ex.DEFAULT, k=float(pick["k"]), cap_ft=float(pick["cap_ft"]), floor_ft=float(pick["floor_ft"]), perf_ref=str(pick["perf_ref"]))
    sel = bt[~bt.uniform & np.isclose(bt.k, bp.k) & np.isclose(bt.cap_ft, bp.cap_ft) & np.isclose(bt.floor_ft, bp.floor_ft) & (bt.perf_ref == bp.perf_ref)]
    abl = sel.groupby(["pool", "fronts"], as_index=False)[["n_good", "n_rolled", "hit_good", "hit_rolled", "added_sqmi"]].sum()
    abl["tpr"] = abl.hit_good / abl.n_good
    abl["fpr"] = abl.hit_rolled / abl.n_rolled
    abl["j"] = abl.tpr - abl.fpr
    abl["precision"] = abl.hit_good / (abl.hit_good + abl.hit_rolled)
    wells = pd.concat([i["wells"] for i in infos], ignore_index=True)
    # 2. final extents
    builds = {pool: build_pool(df[df.pool == pool], pool, bp, sopa) for pool in POOLS}
    # 3. D1 universe count (read-only)
    pud_tabs: dict[str, pd.DataFrame] = {}
    if puds and conn is not None:
        for pool, b in builds.items():
            env = eg.to_lonlat([shapely.box(*b["extent"].bounds).buffer(eg.FT_PER_MI)])[0].bounds
            benches = list(MEMBERS[pool]) + (["WCXY"] if pool == "WCA" else [])
            pu = pull_puds(conn, benches, env)
            body_outline = b["prep"].r["body"]
            pud_tabs[pool] = pud_counts(pu, {"in extent": b["extent"], "in drilled core": b["prep"].core, "in step-2 outline": Polygon(body_outline.exterior)})
    # 4. geology package
    files: list[Path] = pkg.write_sopa(geo_dir, sopa)
    for pool, b in builds.items():
        clip = gio.ft13_to_geology([shapely.box(*b["extent"].bounds).buffer(10 * eg.FT_PER_MI)])[0]
        cont = pkg.context_contours(pool, clip)
        files += pkg.write_pool(geo_dir, pool, version, built, b, bp, cont)
        pkg.legend_png(geo_dir / f"BOX_{pool}_legend.png", pool, b, sopa, bp, version)
        b["stats"]["n_contours"] = {k: len(v) for k, v in cont.items()}
    rule_txt = (
        f"  pinned edge: floor = {bp.floor_ft:,.0f} ft (rolled) / {1.5 * bp.floor_ft:,.0f} (unknown) / {2 * bp.floor_ft:,.0f} (strong)\n"
        f"  gap: k x gap length x perf (strong 1.0 / unknown 0.75 / rolled 0.5), k = {bp.k:g}, within [floor, cap = {bp.cap_ft:,.0f} ft]\n"
        "  pre-2016 laterals beyond a gap -> floor; live-front side -> cap; inside the potash area -> floor; holes -> tightest floor"
    )
    (geo_dir / "README.txt").write_text(pkg.README.format(built=built, pools=", ".join(POOLS), version=version, rule=rule_txt), encoding="utf-8")
    # 5. pages + data
    ctx = {"built": built, "bp": bp, "version": version, "grid": grid, "pick": pick, "infos": infos, "ablation": abl, "wells": wells, "min_floor": MIN_FLOOR_FT,
           "frontier_png": pages.frontier_png(grid, pick), "puds": pud_tabs, "sopa_ll": eg.to_lonlat([sopa.simplify(200.0)])[0]}
    for pool, b in builds.items():
        (out / f"extent_{pool}.html").write_text(pages.pool_page(pool, b, ctx), encoding="utf-8")
        (out / f"extent_{pool}_v{version}.geojson").write_text(json.dumps(_geojson(b, pool, version, bp, built)), encoding="utf-8")
        b["edges"].drop(columns=["geom"]).to_csv(out / f"edges_{pool}.csv", index=False)
        b["prep"].stepouts.drop(columns=["ix"]).to_csv(out / f"stepouts_{pool}.csv", index=False)
        b["holes"].drop(columns=["geom"]).to_csv(out / f"holes_{pool}.csv", index=False)
        if pool in pud_tabs:
            pud_tabs[pool].assign(pool=pool).to_csv(out / f"pud_counts_{pool}.csv", index=False)
    (out / "index.html").write_text(pages.index_page(ctx, builds), encoding="utf-8")
    grid.to_csv(out / "backtest_grid.csv", index=False)
    bt.to_csv(out / "backtest_by_pool_cutoff.csv", index=False)
    wells.to_csv(out / "backtest_wells.csv", index=False)
    abl.to_csv(out / "backtest_ablation.csv", index=False)
    summary = {
        "built_at": built,
        "wells_dir": str(wells_dir),
        "version": version,
        "edge_params": asdict(EDGE),
        "buffer_params": asdict(bp),
        "pick": pick,
        "cutoffs": [str(c) for c in CUTOFFS],
        "backtest_info": [{k: v for k, v in i.items() if k != "wells"} for i in infos],
        "pools": {p: b["stats"] for p, b in builds.items()},
        "geology_files": [str(f.relative_to(out)) for f in files],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else str(x)), encoding="utf-8")
    return {"summary": summary, "builds": builds, "bp": bp, "grid": grid, "ablation": abl, "pud_tabs": pud_tabs}
