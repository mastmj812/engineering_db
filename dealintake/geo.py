"""Unit geometry: local metric frame, planned-lateral estimate, stick-inside test.

All inputs/outputs at the module boundary are WGS84 (EPSG:4326) shapely
geometries; distances are computed in a unit-centred azimuthal-equidistant
frame (metres internally, feet at the API). Azimuths are AXIAL compass
bearings folded to [0, 180) — workspace rule 16.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from pyproj import Transformer
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

FT_PER_M = 3.280839895
M_PER_FT = 1.0 / FT_PER_M


def fold_azimuth(az: float) -> float:
    """Axial bearing folded to [0, 180)."""
    return az % 180.0


def axial_diff(a: float, b: float) -> float:
    """Smallest angle between two axial bearings, in [0, 90]."""
    d = abs(fold_azimuth(a) - fold_azimuth(b))
    return min(d, 180.0 - d)


@dataclass(frozen=True)
class LocalFrame:
    """Azimuthal-equidistant frame centred on a reference point (metres)."""

    lon0: float
    lat0: float

    @classmethod
    def around(cls, geom: BaseGeometry) -> LocalFrame:
        c = geom.centroid
        return cls(lon0=c.x, lat0=c.y)

    def _proj(self) -> str:
        return f"+proj=aeqd +lat_0={self.lat0} +lon_0={self.lon0} +datum=WGS84 +units=m +no_defs"

    def to_local(self, geom: BaseGeometry) -> BaseGeometry:
        t = Transformer.from_crs("EPSG:4326", self._proj(), always_xy=True)
        return transform(t.transform, geom)

    def to_wgs84(self, geom: BaseGeometry) -> BaseGeometry:
        t = Transformer.from_crs(self._proj(), "EPSG:4326", always_xy=True)
        return transform(t.transform, geom)


def long_axis_azimuth(unit: Polygon) -> float:
    """Compass azimuth (folded) of the unit's minimum-rotated-rectangle long side."""
    frame = LocalFrame.around(unit)
    rect = frame.to_local(unit).minimum_rotated_rectangle
    xs, ys = rect.exterior.coords.xy
    edges = [((xs[i + 1] - xs[i]), (ys[i + 1] - ys[i])) for i in range(4)]
    dx, dy = max(edges, key=lambda e: math.hypot(*e))
    return fold_azimuth(math.degrees(math.atan2(dx, dy)))


@dataclass(frozen=True)
class PlannedLateral:
    median_ft: float
    min_ft: float
    max_ft: float
    n_chords: int
    azimuth_deg: float
    azimuth_source: str
    setback_ft: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _longest_piece(g: BaseGeometry) -> float:
    if g.is_empty:
        return 0.0
    if isinstance(g, LineString):
        return g.length
    if isinstance(g, MultiLineString):
        return max(p.length for p in g.geoms)
    parts = [p for p in getattr(g, "geoms", []) if isinstance(p, LineString)]
    return max((p.length for p in parts), default=0.0)


def planned_lateral(
    unit: Polygon,
    azimuth_deg: float,
    *,
    setback_ft: float = 330.0,
    chord_step_ft: float = 100.0,
    azimuth_source: str = "given",
) -> PlannedLateral:
    """Achievable lateral length: median chord along `azimuth_deg` across the
    unit shrunk by a UNIFORM setback on every side (Michael, 2026-09-18).

    A perfect 2-mile x 1-mile DSU with a 330-ft setback returns 9,900 ft.
    Each chord is the longest single straight piece (a lateral cannot jump a
    concave notch). Mitre joins keep rectangular corners square, so edge
    chords are not shortened by buffer rounding.
    """
    frame = LocalFrame.around(unit)
    inner = frame.to_local(unit).buffer(-setback_ft * M_PER_FT, join_style="mitre")
    az = fold_azimuth(azimuth_deg)
    if inner.is_empty:
        return PlannedLateral(0.0, 0.0, 0.0, 0, az, azimuth_source, setback_ft)
    # Rotate CCW by az: a compass bearing az (angle 90-az from +x) lands on +y.
    rot = affinity.rotate(inner, az, origin=(0, 0))
    minx, miny, maxx, maxy = rot.bounds
    step = chord_step_ft * M_PER_FT
    n = max(1, int((maxx - minx) / step))
    chords: list[float] = []
    for i in range(n + 1):
        x = minx + (i + 0.5) * (maxx - minx) / (n + 1)
        piece = _longest_piece(rot.intersection(LineString([(x, miny - 1), (x, maxy + 1)])))
        if piece * FT_PER_M >= 1.0:
            chords.append(piece * FT_PER_M)
    if not chords:
        return PlannedLateral(0.0, 0.0, 0.0, 0, az, azimuth_source, setback_ft)
    return PlannedLateral(
        median_ft=round(statistics.median(chords), 0),
        min_ft=round(min(chords), 0),
        max_ft=round(max(chords), 0),
        n_chords=len(chords),
        azimuth_deg=round(az, 1),
        azimuth_source=azimuth_source,
        setback_ft=setback_ft,
    )


def stick_inside(stick: BaseGeometry, unit: Polygon, tolerance_ft: float = 50.0) -> bool:
    """TRUE when the whole stick lies inside the unit grown by `tolerance_ft`
    (Novi DSU vs Land polygon digitizing slack). Gate 2 v2 rule."""
    frame = LocalFrame.around(unit)
    grown = frame.to_local(unit).buffer(tolerance_ft * M_PER_FT)
    return grown.covers(frame.to_local(stick))


def stick_relation(stick: BaseGeometry, unit: Polygon, tolerance_ft: float = 50.0) -> str:
    """Gate 2 v2 classification of a Novi stick against the deal unit:
      inside    covered by the unit grown by `tolerance_ft`
      outside   does not reach into the unit shrunk by `tolerance_ft` (a
                neighbouring-DSU stick, at most grazing the line)
      crossing  everything else — partly inside: narvi generates the bench.
    """
    frame = LocalFrame.around(unit)
    u, s = frame.to_local(unit), frame.to_local(stick)
    tol = tolerance_ft * M_PER_FT
    if u.buffer(tol).covers(s):
        return "inside"
    core = u.buffer(-tol)
    if core.is_empty or not core.intersects(s):
        return "outside"
    return "crossing"


def outside_length_ft(stick: BaseGeometry, unit: Polygon) -> float:
    """Length of the stick outside the (un-grown) unit, ft — dossier evidence."""
    frame = LocalFrame.around(unit)
    return frame.to_local(stick).difference(frame.to_local(unit)).length * FT_PER_M


def stick_midpoint(stick: BaseGeometry) -> BaseGeometry:
    """Mid-lateral point (normalized interpolation) — well position for grouping."""
    if isinstance(stick, LineString):
        return stick.interpolate(0.5, normalized=True)
    return stick.centroid
