"""Unit geometry: local metric frame, planned-lateral estimate, stick-inside test.

All inputs/outputs at the module boundary are WGS84 (EPSG:4326) shapely
geometries; distances are computed in a unit-centred azimuthal-equidistant
frame (metres internally, feet at the API). Azimuths are AXIAL compass
bearings folded to [0, 180) — workspace rule 16.
"""

from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import dataclass

from pyproj import Proj, Transformer
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

FT_PER_M = 3.280839895
M_PER_FT = 1.0 / FT_PER_M


def fold_azimuth(az: float) -> float:
    """Axial bearing folded to [0, 180). A float hair below 180 (e.g. -1e-15
    from atan2) is 0, not 179.999..."""
    a = az % 180.0
    return 0.0 if a >= 180.0 - 1e-6 else a


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


def stick_azimuth(stick: BaseGeometry) -> float | None:
    """Axial compass bearing of a stick (first -> last vertex), folded."""
    coords = list(getattr(stick, "coords", [])) or [c for part in getattr(stick, "geoms", []) for c in part.coords]
    if len(coords) < 2:
        return None
    frame = LocalFrame.around(stick)
    a = frame.to_local(LineString([coords[0], coords[-1]]))
    (x0, y0), (x1, y1) = a.coords[0], a.coords[-1]
    if math.hypot(x1 - x0, y1 - y0) < 1.0:
        return None
    return fold_azimuth(math.degrees(math.atan2(x1 - x0, y1 - y0)))


def mean_axial_azimuth(azimuths: list[float]) -> float | None:
    """Circular mean of axial bearings (double the angle first — rule 16)."""
    vals = [a for a in azimuths if a is not None]
    if not vals:
        return None
    sx = sum(math.cos(math.radians(2 * a)) for a in vals)
    sy = sum(math.sin(math.radians(2 * a)) for a in vals)
    if math.hypot(sx, sy) < 1e-9:
        return None
    return fold_azimuth(math.degrees(math.atan2(sy, sx)) / 2.0)


def stick_length_ft(stick: BaseGeometry) -> float:
    return LocalFrame.around(stick).to_local(stick).length * FT_PER_M


def stick_spacing_ft(sticks: list[BaseGeometry], azimuth_deg: float) -> float | None:
    """Median gap between ADJACENT sticks measured perpendicular to
    `azimuth_deg` (midpoints projected on the normal). The de-facto spacing
    of a Novi BASE_CASE bench — orientation of the individual sticks does not
    matter, only how far apart they sit. None below two sticks."""
    if len(sticks) < 2:
        return None
    frame = LocalFrame.around(sticks[0])
    az = math.radians(azimuth_deg)
    nx, ny = math.cos(az), -math.sin(az)          # unit normal to the bearing (dx=sin az, dy=cos az)
    offs = sorted(
        (m.x * nx + m.y * ny) * FT_PER_M
        for m in (frame.to_local(stick_midpoint(st)) for st in sticks)
    )
    # < 300 ft apart = the same slot (stacked/staggered or digitizing), not a spacing
    gaps = [b - a for a, b in itertools.pairwise(offs) if b - a >= 300.0]
    return round(statistics.median(gaps), 0) if gaps else None


NARVI_WORK_EPSG = 32613   # narvi's work CRS (UTM 13N): its azimuth_deg values are GRID bearings
_UTM13 = Proj(f"EPSG:{NARVI_WORK_EPSG}")


def grid_convergence_deg(lon: float, lat: float) -> float:
    """UTM 13N meridian convergence at a point: true bearing = grid bearing +
    convergence. About +0.9° across the Delaware (east of the -105° central
    meridian). The runner works in TRUE bearings (aeqd frame); narvi in UTM
    grid — every azimuth crossing that boundary goes through these two."""
    return float(_UTM13.get_factors(lon, lat).meridian_convergence)


def true_to_grid(az_true: float, lon: float, lat: float) -> float:
    return fold_azimuth(az_true - grid_convergence_deg(lon, lat))


def grid_to_true(az_grid: float, lon: float, lat: float) -> float:
    return fold_azimuth(az_grid + grid_convergence_deg(lon, lat))


def gunbarrel_frame(unit: Polygon, azimuth_deg: float):
    """Cross-section frame of record (workspace rule 16, sign rule v2):
    origin = unit centroid, +offset toward positive_offset_bearing (W -> E for
    N-S-ish laterals, S -> N for E-W-ish), along-axis = the azimuth. Returns a
    function geom -> (offset_ft, along_ft) of the geometry's mid-lateral
    point, plus the unit's own cross/along extents (ft)."""
    frame = LocalFrame.around(unit)
    az = math.radians(fold_azimuth(azimuth_deg))
    pb = math.radians(positive_offset_bearing(azimuth_deg))
    cx, cy = math.sin(pb), math.cos(pb)           # cross-axis unit vector
    ax_, ay_ = math.sin(az), math.cos(az)         # along-axis unit vector

    def project(g: BaseGeometry) -> tuple[float, float]:
        m = frame.to_local(stick_midpoint(g))
        return (m.x * cx + m.y * cy) * FT_PER_M, (m.x * ax_ + m.y * ay_) * FT_PER_M

    def along_span(g: BaseGeometry) -> tuple[float, float]:
        """Along-axis extent (ft) of a stick — for 'does it overlap the unit
        along the laterals', which a midpoint cannot answer."""
        pts = [frame.to_local(g).coords] if hasattr(g, "coords") else [part.coords for part in getattr(frame.to_local(g), "geoms", [])]
        vals = [(x * ax_ + y * ay_) * FT_PER_M for cs in pts for x, y in cs]
        return (min(vals), max(vals)) if vals else (0.0, 0.0)

    project.along_span = along_span          # type: ignore[attr-defined]
    ring = frame.to_local(unit).exterior.coords
    offs = [(x * cx + y * cy) * FT_PER_M for x, y in ring]
    alongs = [(x * ax_ + y * ay_) * FT_PER_M for x, y in ring]
    return project, (min(offs), max(offs)), (min(alongs), max(alongs))


GUNBARREL_SEAM_DEG = 45.0


def positive_offset_bearing(azimuth_deg: float) -> float:
    """Compass bearing of the +offset direction of the rule-16 frame, sign
    rule v2 (Michael, 2026-10-08): with a = the folded azimuth, a + 90 when
    a <= 45 else a - 90 — + always points into the NE half, so N-S-ish units
    read W -> E and E-W-ish units S -> N; an exact 45 deg lateral gets SE. The
    side is decided on a rounded to 0.1 deg (the precision narvi persists).
    Copy of narvi placement.plus_offset_bearing_deg — change every copy or
    none. NB the runner works in TRUE bearings and narvi in UTM-13N GRID
    (~0.9 deg apart): within ~1 deg of the 45 deg seam the two can land on
    different sides — near_seam() flags it."""
    a = azimuth_deg % 180.0
    if round(a, 1) >= 180.0:          # 179.96 rounds onto the 0 deg side of the fold
        a -= 180.0
    b = a + 90.0 if round(a, 1) <= GUNBARREL_SEAM_DEG else a - 90.0
    return b % 360.0


def near_seam(azimuth_deg: float, tol_deg: float = 3.0) -> bool:
    """TRUE when a plan azimuth sits within `tol_deg` (axial) of the 45 deg
    gunbarrel seam: neighbouring units either side of it plot mirrored, and a
    TRUE vs GRID bearing can land on different sides."""
    return axial_diff(azimuth_deg, GUNBARREL_SEAM_DEG) <= tol_deg


def side_sign(side: str, azimuth_deg: float) -> int:
    """+1 when the named compass side of a unit lies on the +offset side of the
    rule-16 frame, else -1 (a 162 deg plan: +offset points 72 deg = ENE, so
    'east' -> +1 and 'west' -> -1)."""
    b = positive_offset_bearing(azimuth_deg)
    towards = {"north": 0.0, "east": 90.0, "south": 180.0, "west": 270.0}[side]
    d = abs((b - towards + 180.0) % 360.0 - 180.0)          # angular distance
    return 1 if d <= 90.0 else -1


def apply_row_rules(
    rows: list[dict],
    azimuth_deg: float,
    *,
    n_wells: int | None = None,
    keep_side: str | None = None,
    drop_rows: dict[str, int] | None = None,
    min_leg_ft: float | None = None,
) -> tuple[list[dict], list[str]]:
    """Reviewer row rules on generated legs — each row has offset_ft and
    lateral_ft. Order of application: min_leg_ft (drop stubs), keep_side,
    drop_<side>_rows (nearest that side first), n_wells (trim the outermost
    rows alternately from each side). Returns (kept rows, notes)."""
    notes: list[str] = []
    kept = sorted(rows, key=lambda r: r["offset_ft"])
    if min_leg_ft:
        short = [r for r in kept if (r.get("lateral_ft") or 0) < min_leg_ft]
        if short:
            notes.append(f"{len(short)} leg(s) shorter than {min_leg_ft:,.0f} ft dropped")
            kept = [r for r in kept if r not in short]
    if keep_side:
        sgn = side_sign(keep_side, azimuth_deg)
        before = len(kept)
        kept = [r for r in kept if r["offset_ft"] * sgn >= 0]
        if len(kept) != before:
            notes.append(f"{before - len(kept)} row(s) not on the {keep_side} side dropped")
    for side, n in (drop_rows or {}).items():
        if not n or not kept:
            continue
        sgn = side_sign(side, azimuth_deg)
        order = sorted(kept, key=lambda r: -r["offset_ft"] * sgn)       # nearest that side first (largest projection on it)
        drop = order[:n]
        kept = [r for r in kept if r not in drop]
        notes.append(f"{len(drop)} {side}-most row(s) dropped")
    if n_wells is not None and len(kept) > n_wells:
        extra = len(kept) - n_wells
        left = True
        while len(kept) > n_wells:
            kept = kept[1:] if left else kept[:-1]
            left = not left
        notes.append(f"{extra} outermost row(s) trimmed to n_wells {n_wells}")
    return kept, notes
