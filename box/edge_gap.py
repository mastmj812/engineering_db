"""BOX step 2 — edge-gap prototype (read-only).

docs/box_type_curves_plan.md §5 step 2, D5/D6. Per bench pool (step-1 gate-1 final sets: pooled
WCA incl. WCXY one-way per D19/D20; BS2_S), from the >= 2016 horizontal laterals AS LINES:

  1. OUTLINE (the alpha shape in its union-of-discs form): every lateral is dilated by the pin
     radius ``r`` (a lateral "pins" ground within r of it), the discs are unioned into the drilled
     footprint, and a morphological closing of radius ``c`` bridges openings narrower than ~2c.
     ``c`` is the per-basin alpha, tuned as the smallest value that makes WCA one body; holes are
     listed, not walked.
  2. WALK the main body's outer ring every ``ring_step_ft``. A ring sample is PINNED by the
     nearest lateral within r (+ tolerance) — it sits on the footprint; otherwise it lies on ground
     the closing had to bridge. A GAP is the unpinned ring length between two consecutive pinning
     laterals; adjacent pinners hand over with no gap.
  3. Per ring segment: the side of the body it faces (bearing from the body centroid, 8 sectors),
     the edge wells' median 12-mo oil / 1,000 ft vs the pool's interior median -> perf_class
     (§6: >= 0.85 strong, < 0.70 rolled, else unknown), and the pre-2016 pool laterals just outside
     (negative evidence, D5: shown and counted, never used to extend anything).
  4. STEP-OUTS: >= 2016 pool laterals outside the main body, by side and distance — a front that
     is moving shows up as tests ahead of the body, which no single-body outline can see.

Why the disc form and not a Delaunay edge-length hull (the v1 prototype, rejected 2026-10-07):
with N-S laterals a Delaunay hull large enough to make WCA one body (L = 2.5 mi) cuts every DSU
stair-step on the diagonal flanks with a 1.5-2.5 mi chord, so 67 % of the WCA perimeter read as
gaps > 1 mi and gap p90 saturated at L — an orientation artifact, not maturity. The dilation
fills stair-step notches narrower than 2r, so a densely drilled flank reads as pinned.

Planar math in UTM 13N feet (the Delaware sits in zone 13; same frame as box.bench_qc).
Geometry: Enverus survey LateralLine (curated.enverus_lateral_lines) first, else the Novi LP->BHL
chord, else the sql/04 wellstick. Grain = one row per api10.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import substring

FT_PER_MI = 5280.0
EVIDENCE_FP_MIN = date(2016, 1, 1)  # D5
SECTORS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
PERF_STRONG, PERF_ROLLED = 0.85, 0.70  # §6
GAP_BINS_FT = (0.0, 1320.0, 2640.0, 5280.0, 10560.0, math.inf)  # map colour classes
GAP_LABELS = ("< 1/4 mi", "1/4-1/2 mi", "1/2-1 mi", "1-2 mi", "> 2 mi")


@dataclass(frozen=True)
class EdgeParams:
    pin_radius_ft: float = 2640.0  # r: a lateral pins ground within 1/2 mi of it
    close_ft: float = 5280.0  # c: closing radius = the per-basin alpha (tuned on WCA)
    quad_segs: int = 4  # buffer arc resolution
    ring_step_ft: float = 100.0  # ring walk resolution
    pin_slack_ft: float = 60.0  # tolerance over r for a ring sample to count as pinned
    edge_reach_ft: float = 2640.0  # edge wells: laterals within r + this of a segment
    interior_depth_ft: float = 5280.0  # interior: laterals >= r + this inside the body edge
    neg_evidence_ft: float = 2640.0  # pre-2016 laterals outside the body within this of a segment
    min_body_wells: int = 5  # a component with >= this many laterals is a body


DEFAULT = EdgeParams()


# ----------------------------------------------------------------------------
# Projection
# ----------------------------------------------------------------------------

_M_TO_FT = 3.280839895


def _transformer(inverse: bool = False) -> Any:
    from pyproj import Transformer

    a, b = ("EPSG:32613", "EPSG:4326") if inverse else ("EPSG:4326", "EPSG:32613")
    return Transformer.from_crs(a, b, always_xy=True)


def to_ft(geoms: list[Any]) -> list[Any]:
    """lon/lat geometries -> UTM 13N feet."""
    tr = _transformer()
    return [shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])) * _M_TO_FT) for g in geoms]


def to_lonlat(geoms: list[Any]) -> list[Any]:
    """UTM 13N feet -> lon/lat."""
    tr = _transformer(inverse=True)
    return [shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0] / _M_TO_FT, c[:, 1] / _M_TO_FT))) for g in geoms]


# ----------------------------------------------------------------------------
# Outline (pure)
# ----------------------------------------------------------------------------


def _as_multi(g: Any) -> MultiPolygon:
    if g.is_empty:
        return MultiPolygon()
    if isinstance(g, Polygon):
        return MultiPolygon([g])
    return MultiPolygon([x for x in g.geoms if isinstance(x, Polygon)])


def footprint(lines: list[LineString], p: EdgeParams = DEFAULT) -> Any:
    """Union of the laterals dilated by the pin radius."""
    return shapely.union_all(shapely.buffer(np.asarray(lines, dtype=object), p.pin_radius_ft, quad_segs=p.quad_segs))


def close(fp: Any, p: EdgeParams = DEFAULT) -> MultiPolygon:
    """Morphological closing of the footprint by the alpha radius c; polygons CCW-oriented."""
    o = fp.buffer(p.close_ft, quad_segs=p.quad_segs).buffer(-p.close_ft, quad_segs=p.quad_segs)
    return MultiPolygon([shapely.geometry.polygon.orient(g) for g in _as_multi(o).geoms])


def outline(lines: list[LineString], p: EdgeParams = DEFAULT) -> MultiPolygon:
    return close(footprint(lines, p), p)


def components(o: MultiPolygon, lines: list[LineString], p: EdgeParams = DEFAULT) -> pd.DataFrame:
    """One row per outline component: n laterals intersecting it, area, perimeter, holes."""
    tree = shapely.STRtree(np.asarray(lines, dtype=object))
    rows = []
    for k, g in enumerate(o.geoms):
        holes = [Polygon(r).area for r in g.interiors]
        rows.append(
            {
                "comp": k,
                "n_laterals": len(tree.query(g, predicate="intersects")),
                "area_sqmi": g.area / FT_PER_MI**2,
                "perimeter_mi": g.exterior.length / FT_PER_MI,
                "n_holes": len(holes),
                "holes_sqmi": sum(holes) / FT_PER_MI**2,
                "max_hole_sqmi": max(holes, default=0.0) / FT_PER_MI**2,
            }
        )
    df = pd.DataFrame(rows, columns=["comp", "n_laterals", "area_sqmi", "perimeter_mi", "n_holes", "holes_sqmi", "max_hole_sqmi"])
    df = df.sort_values("n_laterals", ascending=False, kind="stable").reset_index(drop=True)
    df["body"] = df["n_laterals"] >= p.min_body_wells
    return df


def sweep(lines: list[LineString], radii_ft: list[float], closes_ft: list[float], p: EdgeParams = DEFAULT) -> pd.DataFrame:
    """Outline shape vs (r, c): the alpha-tuning table on the page."""
    out = []
    n = len(lines)
    for r in radii_ft:
        pr = replace(p, pin_radius_ft=r)
        fp = footprint(lines, pr)
        for c in closes_ft:
            pc = replace(pr, close_ft=c)
            o = close(fp, pc)
            comps = components(o, lines, pc)
            main = o.geoms[int(comps.comp.iloc[0])] if len(comps) else Polygon()
            seg = walk(main, lines, pc) if not main.is_empty else pd.DataFrame()
            gaps = seg[seg.kind == "gap"] if len(seg) else seg
            out.append(
                {
                    "r_mi": r / FT_PER_MI,
                    "c_mi": c / FT_PER_MI,
                    "n_components": len(comps),
                    "n_bodies": int(comps.body.sum()),
                    "main_share": float(comps.n_laterals.iloc[0]) / n if n else float("nan"),
                    "n_holes": int(comps.n_holes.sum()),
                    "holes_sqmi": float(comps.holes_sqmi.sum()),
                    "max_hole_sqmi": float(comps.max_hole_sqmi.max()) if len(comps) else 0.0,
                    "main_perimeter_mi": main.exterior.length / FT_PER_MI if not main.is_empty else 0.0,
                    "pinned_share": float(seg.loc[seg.kind == "pinned", "length_ft"].sum() / seg.length_ft.sum()) if len(seg) else float("nan"),
                    "gap_p90_ft": float(gaps.length_ft.quantile(0.9)) if len(gaps) else float("nan"),
                }
            )
    return pd.DataFrame(out)


def tune_close(sw: pd.DataFrame, r_mi: float) -> float:
    """The per-basin alpha rule: smallest c (at the chosen r) that makes the pool one body."""
    s = sw[(np.isclose(sw.r_mi, r_mi)) & (sw.n_bodies == 1)]
    if s.empty:
        raise ValueError(f"no c in the sweep makes one body at r = {r_mi} mi")
    return float(s.c_mi.min()) * FT_PER_MI


# ----------------------------------------------------------------------------
# Ring walk (pure)
# ----------------------------------------------------------------------------


def ring_owners(ring: LineString, lines: list[LineString], p: EdgeParams = DEFAULT) -> tuple[np.ndarray, np.ndarray]:
    """Sample a closed ring every ring_step_ft; owner = index of the nearest lateral within
    r + slack, else -1. Returns (arc positions ft, owners)."""
    n = max(4, math.ceil(ring.length / p.ring_step_ft))
    s = np.linspace(0.0, ring.length, n, endpoint=False)
    pts = shapely.line_interpolate_point(ring, s)
    tree = shapely.STRtree(np.asarray(lines, dtype=object))
    idx = tree.query_nearest(pts, max_distance=p.pin_radius_ft + p.pin_slack_ft, all_matches=False)
    own = np.full(n, -1)
    own[idx[0]] = idx[1]
    return s, own


def runs_from_owners(s: np.ndarray, own: np.ndarray, ring_len: float) -> list[dict[str, Any]]:
    """Compress the cyclic owner sequence into runs along the ring.

    ``pinned``: consecutive samples owned by one lateral. ``gap``: the unpinned stretch between two
    consecutive pinned runs (``well_a`` -> ``well_b``; ``same_well`` when a lateral leaves the ring
    and comes back). Adjacent pinned runs of different laterals are a hand-over: no gap record.
    s0/s1 are arc positions (s1 < s0 means the run wraps the ring origin); lengths are ft."""
    n = len(own)
    step = ring_len / n
    if (own >= 0).sum() == 0:
        return [{"kind": "gap", "s0": 0.0, "s1": ring_len, "length_ft": ring_len, "well_a": -1, "well_b": -1, "same_well": False}]
    starts = [i for i in range(n) if own[i] >= 0 and own[i - 1] != own[i]]
    if not starts:  # the whole ring sits on one lateral
        return [{"kind": "pinned", "s0": 0.0, "s1": ring_len, "length_ft": ring_len, "well_a": int(own[0]), "well_b": int(own[0]), "same_well": True}]
    r0 = starts[0]
    o = np.r_[own[r0:], own[:r0]]
    runs: list[tuple[int, int, int]] = []  # (owner, i0, i1) in rotated index space
    i = 0
    while i < n:
        j = i
        while j + 1 < n and o[j + 1] == o[i]:
            j += 1
        runs.append((int(o[i]), i, j))
        i = j + 1
    base = s[r0] - step / 2  # arc position of the rotated origin's leading edge

    def arc(k: float) -> float:
        return (base + k * step) % ring_len

    out: list[dict[str, Any]] = []
    for owner, i0, i1 in runs:
        kind = "pinned" if owner >= 0 else "gap"
        rec = {"kind": kind, "s0": arc(i0), "s1": arc(i1 + 1), "length_ft": (i1 + 1 - i0) * step}
        if kind == "pinned":
            rec.update(well_a=owner, well_b=owner, same_well=True)
        out.append(rec)
    pinned_ix = [k for k, r in enumerate(out) if r["kind"] == "pinned"]
    for k, r in enumerate(out):
        if r["kind"] == "gap":  # bounded by the pinned runs either side (cyclic)
            prev = max((q for q in pinned_ix if q < k), default=pinned_ix[-1])
            nxt = min((q for q in pinned_ix if q > k), default=pinned_ix[0])
            r.update(well_a=out[prev]["well_a"], well_b=out[nxt]["well_a"], same_well=out[prev]["well_a"] == out[nxt]["well_a"])
    return out


def ring_piece(ring: LineString, s0: float, s1: float) -> LineString:
    """Sub-line of a closed ring from arc s0 to s1, wrapping through the origin when s1 <= s0."""
    L = ring.length
    if s1 > s0:
        return substring(ring, s0, s1)
    a, b = substring(ring, s0, L), substring(ring, 0.0, s1)
    ca, cb = list(a.coords), list(b.coords)
    return LineString(ca + cb[1:] if len(cb) > 1 else ca + cb)


def side_sector(pt: Point, centroid: Point) -> str:
    """Side of the body a point is on: compass bearing from the body centroid, 8 sectors."""
    b = (math.degrees(math.atan2(pt.x - centroid.x, pt.y - centroid.y)) + 360.0) % 360.0
    return SECTORS[int(((b + 22.5) % 360) // 45)]


def walk(body: Polygon, lines: list[LineString], p: EdgeParams = DEFAULT) -> pd.DataFrame:
    """Walk the body's outer ring: one row per pinned run / gap with its piece geometry and side."""
    ring = body.exterior
    s, own = ring_owners(ring, lines, p)
    cen = body.centroid
    rows = []
    for k, r in enumerate(runs_from_owners(s, own, ring.length)):
        piece = ring_piece(ring, r["s0"], r["s1"])
        rows.append({**r, "seg_no": k, "side": side_sector(piece.interpolate(0.5, normalized=True), cen), "geom": piece})
    return pd.DataFrame(rows)


def gap_class(length_ft: float) -> str:
    for lo, hi, lab in zip(GAP_BINS_FT[:-1], GAP_BINS_FT[1:], GAP_LABELS):
        if lo <= length_ft < hi:
            return lab
    return GAP_LABELS[-1]


# ----------------------------------------------------------------------------
# Edge performance + negative evidence (pure)
# ----------------------------------------------------------------------------


def perf_class(ratio: float | None) -> str:
    if ratio is None or not np.isfinite(ratio):
        return "unknown"
    if ratio >= PERF_STRONG:
        return "strong"
    if ratio < PERF_ROLLED:
        return "rolled"
    return "unknown"


def interior_mask(body: Polygon, lines: list[LineString], p: EdgeParams = DEFAULT) -> np.ndarray:
    """Laterals at least r + interior_depth inside the body's outer edge."""
    inner = Polygon(body.exterior).buffer(-(p.pin_radius_ft + p.interior_depth_ft), quad_segs=p.quad_segs)
    return np.asarray(shapely.within(np.asarray(lines, dtype=object), inner), dtype=bool)


def attach_edge_evidence(
    seg: pd.DataFrame,
    lines: list[LineString],
    oil12_kft: np.ndarray,
    cohort: np.ndarray,
    interior_median: float,
    old_lines: list[LineString],
    body: Polygon,
    p: EdgeParams = DEFAULT,
) -> pd.DataFrame:
    """Per segment: edge cohort wells (laterals within r + edge_reach) -> median oil12/kft, ratio to
    the interior median, perf_class; pre-2016 laterals outside the body within neg_evidence_ft."""
    d = seg.copy()
    tree = shapely.STRtree(np.asarray(lines, dtype=object))
    old_out = [ln for ln in old_lines if not ln.intersects(body)]
    old_tree = shapely.STRtree(np.asarray(old_out, dtype=object)) if old_out else None
    n_edge, med, ratio, pcl, n_old = [], [], [], [], []
    for g in d.geom:
        ix = tree.query(g, predicate="dwithin", distance=p.pin_radius_ft + p.edge_reach_ft)
        ix = ix[cohort[ix] & np.isfinite(oil12_kft[ix])]
        m = float(np.median(oil12_kft[ix])) if len(ix) else float("nan")
        rt = m / interior_median if len(ix) and interior_median > 0 else float("nan")
        n_edge.append(len(ix))
        med.append(m)
        ratio.append(rt)
        pcl.append(perf_class(rt))
        n_old.append(len(old_tree.query(g, predicate="dwithin", distance=p.neg_evidence_ft)) if old_tree is not None else 0)
    d["n_edge_cohort"], d["edge_oil12_kft_med"], d["perf_ratio"], d["perf_class"] = n_edge, med, ratio, pcl
    d["n_pre2016_outside"] = n_old
    return d


def stepouts(body: Polygon, lines: list[LineString]) -> pd.DataFrame:
    """Laterals outside the main body: distance to it (mi) and the side they are on."""
    cen = body.centroid
    rows = []
    for i, ln in enumerate(lines):
        if ln.intersects(body):
            continue
        mid = ln.interpolate(0.5, normalized=True)
        rows.append({"ix": i, "dist_mi": body.distance(ln) / FT_PER_MI, "side": side_sector(mid, cen)})
    return pd.DataFrame(rows, columns=["ix", "dist_mi", "side"])


# ----------------------------------------------------------------------------
# Summaries (pure)
# ----------------------------------------------------------------------------


def gap_stats(seg: pd.DataFrame) -> dict[str, Any]:
    """Gap distribution + perimeter per pinning well for one ring walk (or one side of it)."""
    tot = float(seg.length_ft.sum()) if len(seg) else 0.0
    pin = seg[seg.kind == "pinned"]
    g = seg[seg.kind == "gap"]
    n_pin = int(pin.well_a.nunique())
    return {
        "perimeter_mi": tot / FT_PER_MI,
        "n_pinning_wells": n_pin,
        "mi_per_pinning_well": (tot / FT_PER_MI / n_pin) if n_pin else float("inf"),
        "pinned_share": float(pin.length_ft.sum() / tot) if tot else float("nan"),
        "n_gaps": len(g),
        "gap_median_ft": float(g.length_ft.median()) if len(g) else 0.0,
        "gap_p90_ft": float(g.length_ft.quantile(0.9)) if len(g) else 0.0,
        "gap_max_ft": float(g.length_ft.max()) if len(g) else 0.0,
        "share_gap_gt_half_mi": float(g.loc[g.length_ft > FT_PER_MI / 2, "length_ft"].sum() / tot) if tot else float("nan"),
        "share_gap_gt_1_mi": float(g.loc[g.length_ft > FT_PER_MI, "length_ft"].sum() / tot) if tot else float("nan"),
    }


def side_table(seg: pd.DataFrame, so: pd.DataFrame) -> pd.DataFrame:
    """Per side of the body: gap stats + step-outs ahead of it (by distance band)."""
    rows = []
    for sec in SECTORS:
        st = gap_stats(seg[seg.side == sec])
        s = so[so.side == sec]
        st.update(
            side=sec,
            stepouts_le5mi=int((s.dist_mi <= 5).sum()),
            stepouts_5_20mi=int(((s.dist_mi > 5) & (s.dist_mi <= 20)).sum()),
            stepouts_gt20mi=int((s.dist_mi > 20).sum()),
        )
        rows.append(st)
    return pd.DataFrame(rows).set_index("side")
