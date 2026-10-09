"""BOX step 3 — extents = lateral lines + variable buffer (pure; DB-free).

docs/box_type_curves_plan.md §5 step 3, D5/D6/D21–D24. Builds on the step-2 edge metric of record
(box/edge_gap.py, D23): the walked outline segments carry gap length, the 2×2 performance class and
the pre-2016 negative-evidence count; this module turns them into a per-segment buffer and an
extent polygon.

  1. CORE (D21): the step-2 outline eroded back by the pin radius r, unioned with the laterals'
     own lines. On a pinned stretch the eroded outline lands on the last laterals; across a gap it
     sits r inside the closing's bridge. The r-dilated outline itself is never the extent — r is a
     measuring radius only. Selected step-outs join the core as islands.
  2. BUFFER per walked segment (D6 + the plan's 2×2):
        pinned  -> floor[perf]                  rolled 1×, unknown 1.5×, strong 2× floor_ft
        gap     -> clip(k × gap × m[perf], floor[perf], cap)    m: strong 1.0, unknown 0.75, rolled 0.5
     then, in priority order (last wins):
        pre-2016 laterals just beyond a gap -> floor (D5: tested, not followed up — tighten only)
        live-front side (D22, detected from the step-out table) -> cap
        segment inside the potash ignore-gap polygon (D24) -> floor (a gap there never widens)
     Holes of the body get the tightest floor and a geology flag — except legacy drilled-up holes
     (D26): a hole >= 90 % covered by the r-footprint of pre-2016 laterals is filled into the core
     (the bench is proven there and full; no room for a modern well). Potash holes included.
  3. SECTORS: each point outside the core takes the buffer of the nearest walked-ring sample (the
     Voronoi cell of the ring). A point lies in the extent when its distance to the core is within
     that buffer. Inside the potash polygon every point is held to its sector's floor (D24: the
     polygon never extends an extent).
  4. The polygon is assembled per distinct buffer value (quantised) as buffer(core, b) ∩ cells(b),
     then lightly smoothed. The same rule evaluated point-wise drives the calibration backtest.

  5. D27 (Michael 2026-10-09) — the extent is the bench's DEVELOPMENT envelope:
     - developed is always in: every >= 2016 pool lateral within the bridging width of the body
       joins the core whatever its performance; isolated tests beyond it are listed, not included;
     - no voids: the buffered extent is closed with radius bridge_mi / 2 (gaps between development
       trends narrower than bridge_mi are bridged) and every interior void is filled;
     - evidence only governs reach beyond the outermost development: an optional updip depth limit
       (BS2_S: 2BS sand top 7,000 ft) holds the buffer to the floor on the shallow side, like the
       potash polygon. Performance belongs to the TC areas (step 4), never to the extent.

Planar math in UTM 13N feet (box.edge_gap's frame).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiPolygon, Polygon

from box import edge_gap as eg

FT_PER_MI = eg.FT_PER_MI
FLOOR_MULT = {"rolled": 1.0, "unknown": 1.5, "strong": 2.0}  # pinned: rolled tightest, strong "tight + flag"
GAP_MULT = {"strong": 1.0, "unknown": 0.75, "rolled": 0.5}  # gap: strong max, rolled moderate
HOLE = -1  # seg index of hole-ring samples


@dataclass(frozen=True)
class BufferParams:
    k: float = 0.5  # buffer per ft of local gap
    cap_ft: float = 5280.0  # maximum buffer (also the live-front buffer)
    floor_ft: float = 880.0  # pinned + rolled buffer (the tightest class)
    perf_ref: str = "pool"  # 2×2 performance reference: "pool" interior median or "local"
    local_radius_ft: float = 10 * 5280.0  # local reference: interior cohort within this of the segment
    local_min_n: int = 15  # ... at least this many, else 2× radius, else the pool median
    sample_ft: float = 200.0  # ring sampling for sectors
    stepout_reach_mi: float = 5.0  # live-front detection: performing step-outs within this of the body
    front_min_ok: int = 3  # live front: >= this many performing step-outs within reach ...
    front_ok_over_rolled: float = 2.0  # ... and at least this many times the rolled ones
    lateral_core_ft: float = 50.0  # half-width of a lateral's own line in the core
    quantum_ft: float = 110.0  # buffer quantisation for polygon assembly (1/48 mi)
    smooth_ft: float = 330.0  # closing + opening of the assembled polygon
    legacy_fill_cover: float = 0.90  # D26: fill a hole this covered by the pre-2016 lateral footprint (r)
    bridge_mi: float = 8.0  # D27: bridge gaps between development trends narrower than this; also the step-out inclusion reach
    envelope: bool = True  # D27 envelope (closing + no voids); False = the pre-D27 buffered extent
    uniform: bool = False  # calibration baseline: floor_ft everywhere, no 2×2 / gap / front terms


DEFAULT = BufferParams()


# ----------------------------------------------------------------------------
# Core
# ----------------------------------------------------------------------------


def as_multi(g: Any) -> MultiPolygon:
    return eg._as_multi(g)


def core(body: Polygon, body_lines: list[LineString], island_lines: list[LineString], pin_radius_ft: float, bp: BufferParams = DEFAULT) -> MultiPolygon:
    """The drilled core: the step-2 body eroded by r, plus every lateral's own line (incl. islands)."""
    eroded = body.buffer(-pin_radius_ft, quad_segs=4)
    lines = list(body_lines) + list(island_lines)
    thin = shapely.union_all(shapely.buffer(np.asarray(lines, dtype=object), bp.lateral_core_ft, quad_segs=2)) if lines else Polygon()
    return as_multi(shapely.union_all([eroded, thin]).buffer(0))


def legacy_cover(body: Polygon, old_lines: list[LineString], pin_radius_ft: float) -> list[float]:
    """Per hole of the body (in body.interiors order): share of its area within r of a pre-2016 lateral."""
    holes = [Polygon(h) for h in body.interiors]
    if not holes or not old_lines:
        return [0.0] * len(holes)
    arr = np.asarray(old_lines, dtype=object)
    tree = shapely.STRtree(arr)
    out = []
    for h in holes:
        ix = tree.query(h, predicate="dwithin", distance=pin_radius_ft)
        if not len(ix):
            out.append(0.0)
            continue
        fp = shapely.union_all(shapely.buffer(arr[ix], pin_radius_ft, quad_segs=4))
        out.append(h.intersection(fp).area / h.area)
    return out


def fill_legacy_holes(body: Polygon, cover: list[float], threshold: float) -> tuple[Polygon, list[bool]]:
    """D26: the body with every hole whose legacy cover >= threshold filled; returns (body, filled flags)."""
    filled = [c >= threshold for c in cover]
    keep = [h for h, f in zip(body.interiors, filled) if not f]
    return Polygon(body.exterior, keep), filled


# ----------------------------------------------------------------------------
# Performance reference, step-outs, live fronts
# ----------------------------------------------------------------------------


def local_perf(seg: pd.DataFrame, lines: list[LineString], oil12_kft: np.ndarray, interior_cohort: np.ndarray, pool_median: float, bp: BufferParams = DEFAULT) -> pd.DataFrame:
    """Per segment: the interior median within local_radius (2× if thin, else the pool median) and
    the edge median's ratio to it -> perf_class_local."""
    mids = np.asarray([ln.interpolate(0.5, normalized=True).coords[0] for ln in lines])
    ix_int = np.flatnonzero(interior_cohort & np.isfinite(oil12_kft))
    tree = cKDTree(mids[ix_int]) if len(ix_int) else None
    ref, src = [], []
    for g in seg.geom:
        m = g.interpolate(0.5, normalized=True)
        val, how = pool_median, "pool"
        if tree is not None:
            for rad, lab in ((bp.local_radius_ft, "local"), (2 * bp.local_radius_ft, "local_2x")):
                hit = tree.query_ball_point([m.x, m.y], rad)
                if len(hit) >= bp.local_min_n:
                    val, how = float(np.median(oil12_kft[ix_int[hit]])), lab
                    break
        ref.append(val)
        src.append(how)
    d = seg.copy()
    d["local_ref"] = ref
    d["local_ref_src"] = src
    d["perf_ratio_local"] = d["edge_oil12_kft_med"] / d["local_ref"]
    d["perf_class_local"] = [eg.perf_class(x) for x in d["perf_ratio_local"]]
    return d


def stepout_class(so: pd.DataFrame) -> pd.Series:
    """ok / rolled by the 2×2 thresholds when the step-out has a 12-mo oil/ft; else no12. Any 12-mo
    counts (not only D9-cohort laterals): the D9 lateral window normalises type-curve cohorts, it is
    not a test of whether a single step-out worked."""
    pr = so["perf_ratio"].astype(float)
    known = np.isfinite(pr)
    return pd.Series(np.where(~known, "no12", np.where(pr >= eg.PERF_ROLLED, "ok", "rolled")), index=so.index)


def front_sides(so: pd.DataFrame, bp: BufferParams = DEFAULT) -> dict[str, dict[str, Any]]:
    """Live fronts (D22, generalised): sides whose step-outs within reach include >= front_min_ok
    performing tests and outnumber the rolled ones front_ok_over_rolled to one."""
    if so.empty:
        return {}
    c = stepout_class(so)
    near = so["dist_mi"] <= bp.stepout_reach_mi
    out = {}
    for side in eg.SECTORS:
        m = near & (so["side"] == side)
        ok, rolled, no12 = int((m & (c == "ok")).sum()), int((m & (c == "rolled")).sum()), int((m & (c == "no12")).sum())
        if ok >= bp.front_min_ok and ok >= bp.front_ok_over_rolled * rolled:
            out[side] = {"ok": ok, "rolled": rolled, "no12": no12, "perf_median": float(so.loc[m & (c == "ok"), "perf_ratio"].median())}
    return out


def stepout_roles(so: pd.DataFrame, fronts: dict[str, Any], bp: BufferParams = DEFAULT) -> pd.Series:
    """D27: developed is always in — a step-out within the bridging width joins the core (an island
    the envelope bridges) whatever its performance; beyond it, an isolated test, listed not included.
    (fronts no longer decide membership; they still set the cap on their side.)"""
    near = so["dist_mi"] <= bp.bridge_mi
    return pd.Series(np.where(near, "island", "excluded: isolated test (tested, not developed)"), index=so.index)


# ----------------------------------------------------------------------------
# Buffers per segment
# ----------------------------------------------------------------------------


def segment_buffers(seg: pd.DataFrame, bp: BufferParams, fronts: dict[str, Any] | None = None, sopa: Any = None, updip: Any = None) -> pd.DataFrame:
    """buffer_ft / floor_ft / rule per walked segment (rule = the clause that set the buffer)."""
    fronts = fronts or {}
    if bp.uniform:
        f = np.full(len(seg), bp.floor_ft)
        return pd.DataFrame({"perf_used": "uniform", "floor_ft": f, "buffer_ft": f, "rule": "uniform baseline", "in_sopa": False}, index=seg.index)
    pc = seg["perf_class_local"] if bp.perf_ref == "local" else seg["perf_class"]
    floor = bp.floor_ft * pc.map(FLOOR_MULT).to_numpy(float)
    gap = seg["kind"].eq("gap").to_numpy()
    raw = bp.k * seg["length_ft"].to_numpy(float) * pc.map(GAP_MULT).to_numpy(float)
    b = np.where(gap, np.clip(raw, floor, max(bp.cap_ft, 0.0)), floor)
    b = np.maximum(b, floor)  # a cap below a floor never undercuts the floor
    rule = np.where(gap, np.where(raw >= bp.cap_ft, "gap: capped", "gap: k × gap"), "pinned: floor")
    rule = rule.astype(object)
    neg = gap & (seg["n_pre2016_outside"].to_numpy() > 0)
    b = np.where(neg, floor, b)
    rule[neg] = "gap: pre-2016 beyond -> floor (D5)"
    fr = seg["side"].isin(list(fronts)).to_numpy()
    b = np.where(fr, np.maximum(bp.cap_ft, floor), b)
    rule[fr] = "live front -> cap (D22)"
    mids = shapely.line_interpolate_point(np.asarray(list(seg["geom"]), dtype=object), 0.5, normalized=True) if len(seg) else np.asarray([])
    if updip is not None and not updip.is_empty and len(seg):
        up = shapely.contains(updip, mids)
        b = np.where(up, floor, b)
        rule[up] = "updip of depth limit -> floor (D27)"
    if sopa is not None and not sopa.is_empty and len(seg):
        ins = shapely.contains(sopa, mids)
        b = np.where(ins, floor, b)
        rule[ins] = "potash ignore-gap -> floor (D24)"
    else:
        ins = np.zeros(len(seg), bool)
    return pd.DataFrame({"perf_used": pc.to_numpy(), "floor_ft": floor, "buffer_ft": b, "rule": rule, "in_sopa": ins}, index=seg.index)


def geology_flag(s: pd.Series) -> str:
    """Plain-language note per edge segment for the geology layer ('' = nothing to ask)."""
    out = []
    if s["kind"] == "pinned" and s["perf_used"] == "strong":
        out.append("pinned edge, strong wells: edge not explained by performance; what stops it?")
    if str(s["rule"]).startswith("live front"):
        out.append("live front: performing step-outs ahead of the body; buffered at the cap")
    if str(s["rule"]).startswith("potash"):
        out.append("inside the BLM Secretary's Potash Area: surface, not geology; gap not widened")
    if str(s["rule"]).startswith("updip"):
        out.append("updip of the depth limit (shallow side rolls over): no reach past the last wells")
    if str(s["rule"]).startswith("gap: pre-2016"):
        out.append("pre-2016 laterals beyond this gap were not followed up; held to the floor")
    return "; ".join(out)


# ----------------------------------------------------------------------------
# Ring samples -> sectors
# ----------------------------------------------------------------------------


def ring_samples(seg: pd.DataFrame, body: Polygon, step_ft: float) -> tuple[np.ndarray, np.ndarray]:
    """Points every step_ft along each walked segment (seg index) and along the body's hole rings
    (HOLE). Returns (xy, seg_ix)."""
    xy, ix = [], []
    for i, g in zip(seg.index, seg.geom):
        n = max(1, math.ceil(g.length / step_ft))  # end point = the next segment's start
        pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, n, endpoint=False))
        xy.append(shapely.get_coordinates(pts))
        ix.append(np.full(n, i))
    for h in body.interiors:
        r = LineString(h.coords)
        n = max(4, math.ceil(r.length / step_ft))
        pts = shapely.line_interpolate_point(r, np.linspace(0, r.length, n, endpoint=False))
        xy.append(shapely.get_coordinates(pts))
        ix.append(np.full(n, HOLE))
    xy_a, ix_a = np.vstack(xy), np.concatenate(ix)
    _, keep = np.unique(np.round(xy_a, 1), axis=0, return_index=True)  # Voronoi needs distinct sites
    keep.sort()
    return xy_a[keep], ix_a[keep]


def sample_buffers(seg_ix: np.ndarray, sb: pd.DataFrame, hole_ft: float) -> tuple[np.ndarray, np.ndarray]:
    """Per ring sample: (buffer, floor) from its segment; hole samples get hole_ft for both."""
    b = np.full(len(seg_ix), hole_ft)
    f = np.full(len(seg_ix), hole_ft)
    m = seg_ix != HOLE
    b[m] = sb["buffer_ft"].reindex(seg_ix[m]).to_numpy(float)
    f[m] = sb["floor_ft"].reindex(seg_ix[m]).to_numpy(float)
    return b, f


class CoreDistance:
    """Distance from points to a (multi)polygon core (0 inside), via an STRtree over its edges."""

    def __init__(self, core_mp: MultiPolygon):
        self.core = core_mp
        shapely.prepare(self.core)
        segs = []
        for poly in core_mp.geoms:
            for ring in [poly.exterior, *poly.interiors]:
                c = np.asarray(ring.coords)
                segs.append(shapely.linestrings(np.stack([c[:-1], c[1:]], axis=1)))
        self.edges = np.concatenate(segs) if segs else np.asarray([], dtype=object)
        self.tree = shapely.STRtree(self.edges)

    def distance(self, xy: np.ndarray, max_ft: float) -> np.ndarray:
        """inf beyond max_ft."""
        d = np.full(len(xy), np.inf)
        inside = shapely.contains_xy(self.core, xy[:, 0], xy[:, 1])
        d[inside] = 0.0
        out = np.flatnonzero(~inside)
        if len(out):
            pts = shapely.points(xy[out])
            (ip, _), dist = self.tree.query_nearest(pts, max_distance=max_ft, return_distance=True, all_matches=False)
            d[out[ip]] = dist
        return d


def point_buffer(nn: np.ndarray, in_sopa: np.ndarray, b: np.ndarray, f: np.ndarray) -> np.ndarray:
    """The buffer that applies at each point: its sector's buffer, held to the floor in SOPA."""
    return np.where(in_sopa, f[nn], b[nn])


# ----------------------------------------------------------------------------
# Polygon assembly
# ----------------------------------------------------------------------------


def _assemble(core_mp: MultiPolygon, cells: np.ndarray, vals: np.ndarray, quantum: float) -> Any:
    q = np.round(vals / quantum) * quantum
    pieces = [core_mp]
    for v in np.unique(q):
        if v <= 0:
            continue
        cu = shapely.union_all(cells[q == v])
        near = core_mp.intersection(cu.buffer(v + quantum, quad_segs=2))
        if near.is_empty:
            continue
        pieces.append(near.buffer(v, quad_segs=6).intersection(cu))
    return shapely.union_all(pieces)


def build_extent(core_mp: MultiPolygon, xy: np.ndarray, b: np.ndarray, f: np.ndarray, sopa: Any, bp: BufferParams = DEFAULT) -> tuple[MultiPolygon, np.ndarray]:
    """Extent polygon from the core and per-sample buffers; returns (extent, Voronoi cells).
    ``sopa`` is the floor-clamp polygon: the potash area, unioned with any updip zone (D27)."""
    env = shapely.box(*core_mp.bounds).buffer(4 * max(bp.cap_ft, float(b.max())))
    cells = np.asarray(shapely.voronoi_polygons(shapely.multipoints(xy), extend_to=env, ordered=True).geoms, dtype=object)
    # GEOS occasionally returns a self-intersecting cell for near-collinear ring sites (1-2 per
    # build); repair just those so the per-buffer unions node cleanly
    bad = ~shapely.is_valid(cells)
    if bad.any():
        cells[bad] = shapely.buffer(cells[bad], 0)
    ext = _assemble(core_mp, cells, b, bp.quantum_ft)
    if sopa is not None and not sopa.is_empty and ext.intersects(sopa):
        ext_f = _assemble(core_mp, cells, f, bp.quantum_ft)
        ext = shapely.union_all([ext.difference(sopa), ext_f.intersection(sopa), core_mp])
    s = bp.smooth_ft
    ext = ext.buffer(s, quad_segs=4).buffer(-s, quad_segs=4).buffer(-s, quad_segs=4).buffer(s, quad_segs=4)
    ext = shapely.union_all([ext, core_mp])
    if bp.envelope:
        ext = development_envelope(ext, bp.bridge_mi * FT_PER_MI / 2.0)
    ext = ext.simplify(25.0)
    return MultiPolygon([shapely.geometry.polygon.orient(g) for g in as_multi(ext).geoms]), cells


def development_envelope(ext: Any, close_ft: float) -> MultiPolygon:
    """D27: close by close_ft (bridges gaps between trends narrower than 2 x close_ft; never pushes a
    convex outer edge) and fill every interior void. Contains its input by construction."""
    g = ext.buffer(close_ft, quad_segs=16).buffer(-close_ft, quad_segs=16)
    filled = [Polygon(p.exterior) for p in as_multi(shapely.union_all([g, ext])).geoms]
    return as_multi(shapely.union_all(filled))


def edge_runs(extent: MultiPolygon, xy: np.ndarray, seg_ix: np.ndarray, step_ft: float = 100.0) -> list[dict[str, Any]]:
    """Split the extent's rings into runs by the walked segment whose sector they sit in
    (nearest ring sample). Returns [{'seg': ix, 'geom': LineString, 'hole_ring': bool}]."""
    tree = cKDTree(xy)
    out = []
    for poly in extent.geoms:
        for k, ring in enumerate([poly.exterior, *poly.interiors]):
            r = LineString(ring.coords)
            n = max(4, math.ceil(r.length / step_ft))
            pts = shapely.get_coordinates(shapely.line_interpolate_point(r, np.linspace(0, r.length, n + 1)))
            _, nn = tree.query(pts[:-1])
            own = seg_ix[nn]
            # rotate so the ring starts at an owner change (avoid a run split across the origin)
            ch = np.flatnonzero(own != np.roll(own, 1))
            r0 = int(ch[0]) if len(ch) else 0
            order = np.r_[np.arange(r0, n), np.arange(0, r0)]
            i = 0
            while i < n:
                j = i
                while j + 1 < n and own[order[j + 1]] == own[order[i]]:
                    j += 1
                idx = list(order[i : j + 1]) + [order[(j + 1) % n] if j + 1 < n else order[0]]
                coords = pts[idx]
                if len(coords) >= 2:
                    out.append({"seg": int(own[order[i]]), "geom": LineString(coords), "hole_ring": k > 0})
                i = j + 1
    return out


# ----------------------------------------------------------------------------
# Calibration (point-wise rule)
# ----------------------------------------------------------------------------


def captured(frac_inside: np.ndarray, min_frac: float = 0.5) -> np.ndarray:
    return frac_inside >= min_frac


def well_inside_fraction(well_of_pt: np.ndarray, inside_pt: np.ndarray, n_wells: int) -> np.ndarray:
    tot = np.bincount(well_of_pt, minlength=n_wells)
    ins = np.bincount(well_of_pt, weights=inside_pt.astype(float), minlength=n_wells)
    return np.divide(ins, tot, out=np.zeros(n_wells), where=tot > 0)


def score(good: np.ndarray, rolled: np.ndarray, cap: np.ndarray) -> dict[str, float]:
    """Capture of performing vs rolled later wells; J = TPR - FPR."""
    ng, nr = int(good.sum()), int(rolled.sum())
    tpr = float((cap & good).sum() / ng) if ng else float("nan")
    fpr = float((cap & rolled).sum() / nr) if nr else float("nan")
    return {"n_good": ng, "n_rolled": nr, "hit_good": int((cap & good).sum()), "hit_rolled": int((cap & rolled).sum()), "tpr": tpr, "fpr": fpr, "j": tpr - fpr}


# ----------------------------------------------------------------------------
# Diff (geology round-trip)
# ----------------------------------------------------------------------------


def diff(generated: Any, edited: Any, centroid: Any, min_sqmi: float = 0.01) -> dict[str, Any]:
    """Generated vs geology-edited extent (same planar frame): added / removed pieces with area and side."""
    add = as_multi(edited.difference(generated))
    rem = as_multi(generated.difference(edited))
    pieces = []
    for kind, mp in (("added", add), ("removed", rem)):
        for g in mp.geoms:
            a = g.area / FT_PER_MI**2
            if a >= min_sqmi:
                pieces.append({"kind": kind, "area_sqmi": a, "side": eg.side_sector(g.representative_point(), centroid), "geom": g})
    return {
        "generated_sqmi": generated.area / FT_PER_MI**2,
        "edited_sqmi": edited.area / FT_PER_MI**2,
        "added_sqmi": add.area / FT_PER_MI**2,
        "removed_sqmi": rem.area / FT_PER_MI**2,
        "pieces": pieces,
    }
