"""BOX — 3-D well-spacing measure (pure geometry + features). Prototype of docs/box/step6-2026-10-12/SPACING_3D_SCOPE.md.

Coordinates: laterals in projected feet (UTM 13N, box.edge_gap.to_ft); depth = one TVD per well (v1). For a subject
lateral S and a neighbour lateral N (any bench, producing horizontal):

  * overlap    — |locate(N.start) − locate(N.end)| along S (normalised), >= 0.30 to count (rule 9 co-extent, sql/47);
  * dxy        — SIGNED mean perpendicular offset of N from S over the overlapped span (S sampled at 11 points;
                 + = left of S's LP -> BHL heading); gunbarrel offset, not closest approach;
  * dz         — N.tvd − S.tvd (negative = shallower);
  * relation   — by first-production gap: parent (N earlier by > 180 d), codev (within 180 d), child (later).

Per-subject features AS OF FIRST PRODUCTION (parents + codev; children excluded — they are future to the subject):
  nn_left_ft / nn_right_ft   nearest |dxy| on each side among neighbours with |dz| <= SAME_DZ (250 ft); None = unbounded
  lat_spacing_ft             mean of the two sides, an unbounded side counted at GATE (2,640 ft)
  xsec_ft2                   drainage cross-section: area of the subject's Voronoi cell in the (dxy, A*dz) plane among
                             overlapped neighbours, bounded at +-GATE horizontally and +-GATE/A vertically; true ft2
                             (divided by A). Bigger = more rock per well.
  n_ellipse                  neighbours with (dxy/660)^2 + (dz/300)^2 <= 1
  parent_cum_kbbl_per_kft    sum over parents with |dz| <= 500 ft of overlap x parent cum oil at the subject's first
                             production, per 1,000 ft of subject lateral (depletion the subject actually saw)
Diagnostic only (NOT knowable at first production): n_child_24mo — children inside the ellipse that came online
within the subject's first 24 months (infill arriving during the decline window).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box

GATE = 2640.0
MIN_OVERLAP = 0.30
SAME_DZ = 250.0
ANISO = 2.0  # A: 1 ft of TVD weighs as A ft of horizontal offset
ELLIPSE = (660.0, 300.0)
PARENT_DZ = 500.0
CODEV_DAYS = 180
N_SAMPLES = 11


@dataclass(frozen=True)
class Pair:
    nbr: str
    overlap: float
    dxy: float
    dz: float
    dfp_days: int

    @property
    def relation(self) -> str:
        return "parent" if self.dfp_days < -CODEV_DAYS else ("codev" if self.dfp_days <= CODEV_DAYS else "child")


def pair_geometry(s: LineString, n: LineString, s_tvd: float, n_tvd: float, dfp_days: int, nbr: str) -> Pair | None:
    """Co-extent pair facts, or None when the overlap is below MIN_OVERLAP or the geometry is degenerate."""
    if s.length <= 0 or n.length <= 0:
        return None
    a = s.project(Point(n.coords[0]), normalized=True)
    b = s.project(Point(n.coords[-1]), normalized=True)
    lo, hi = min(a, b), max(a, b)
    ov = hi - lo
    if ov < MIN_OVERLAP:
        return None
    ts = np.linspace(lo, hi, N_SAMPLES)
    offs = []
    for t in ts:
        p = s.interpolate(t, normalized=True)
        q = n.interpolate(n.project(p))
        # side: sign of the cross product of S's local heading with (q - p)
        t2 = min(1.0, t + 1e-3)
        t1 = max(0.0, t - 1e-3)
        p1, p2 = s.interpolate(t1, normalized=True), s.interpolate(t2, normalized=True)
        hx, hy = p2.x - p1.x, p2.y - p1.y
        cross = hx * (q.y - p.y) - hy * (q.x - p.x)
        offs.append(math.copysign(p.distance(q), cross if cross != 0 else 1.0))
    if not (math.isfinite(s_tvd) and math.isfinite(n_tvd)):
        return None
    return Pair(nbr=nbr, overlap=float(ov), dxy=float(np.mean(offs)), dz=float(n_tvd - s_tvd), dfp_days=int(dfp_days))


def voronoi_xsec(pairs: Sequence[Pair], gate: float = GATE, aniso: float = ANISO) -> float:
    """Area (true ft2) of the subject's cell in the (dxy, aniso*dz) plane: bounded box, cut by the perpendicular
    bisector half-plane of every neighbour."""
    cell: Polygon = box(-gate, -gate, gate, gate)
    for p in pairs:
        x, y = p.dxy, aniso * p.dz
        if x == 0 and y == 0:
            continue
        # half-plane {u: u . (x, y) <= |(x, y)|^2 / 2} as a big polygon
        nx, ny = x, y
        c = (x * x + y * y) / 2.0
        L = 1e6
        norm = math.hypot(nx, ny)
        ux, uy = nx / norm, ny / norm  # unit normal
        px, py = ux * c / norm, uy * c / norm  # point on the bisector
        tx, ty = -uy, ux
        half = Polygon([(px + tx * L, py + ty * L), (px - tx * L, py - ty * L),
                        (px - tx * L - ux * L, py - ty * L - uy * L), (px + tx * L - ux * L, py + ty * L - uy * L)])
        cell = cell.intersection(half)
        if cell.is_empty:
            return 0.0
    return float(cell.area / aniso)


def features(pairs: Sequence[Pair], lateral_ft: float, parent_cum: Mapping[str, float] | None = None, child_24: Sequence[Pair] = ()) -> dict[str, Any]:
    """Per-subject features from its co-extent pairs (children are dropped here; pass them separately as child_24)."""
    known = [p for p in pairs if p.relation != "child"]
    same = [p for p in known if abs(p.dz) <= SAME_DZ]
    left = [abs(p.dxy) for p in same if p.dxy > 0]
    right = [abs(p.dxy) for p in same if p.dxy < 0]
    nl = min(left) if left else None
    nr = min(right) if right else None
    lat_sp = (min(nl if nl is not None else GATE, GATE) + min(nr if nr is not None else GATE, GATE)) / 2.0
    ex, ez = ELLIPSE
    inside = [p for p in known if (p.dxy / ex) ** 2 + (p.dz / ez) ** 2 <= 1.0]
    pc = None
    if parent_cum is not None and lateral_ft and lateral_ft > 0:
        pc = sum(p.overlap * float(parent_cum.get(p.nbr, 0.0) or 0.0) for p in known if p.relation == "parent" and abs(p.dz) <= PARENT_DZ) / 1000.0 / (lateral_ft / 1000.0)
    return {"n_pairs": len(known), "nn_left_ft": nl, "nn_right_ft": nr, "lat_spacing_ft": lat_sp, "xsec_ft2": voronoi_xsec(known),
            "n_ellipse": len(inside), "n_parent_ellipse": sum(1 for p in inside if p.relation == "parent"),
            "parent_cum_kbbl_per_kft": pc, "n_child_24mo": sum(1 for p in child_24 if (p.dxy / ex) ** 2 + (p.dz / ez) ** 2 <= 1.0),
            "bounded_sides": int(nl is not None) + int(nr is not None)}


def candidates(lines: Sequence[LineString], gate: float = GATE) -> list[np.ndarray]:
    """For each line, indices of lines within `gate` (excluding itself)."""
    tree = shapely.STRtree(list(lines))
    out = []
    for i, ln in enumerate(lines):
        j = tree.query(ln, predicate="dwithin", distance=gate)
        out.append(j[j != i])
    return out
