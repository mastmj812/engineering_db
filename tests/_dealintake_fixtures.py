"""Shared synthetic geometry for the dealintake tests (DB-free)."""

from shapely.geometry import LineString, Point, Polygon, box

from dealintake.geo import M_PER_FT, LocalFrame

# Reeves Co.-ish reference point.
FRAME = LocalFrame(lon0=-103.6, lat0=31.4)


def rect_ft(x0: float, y0: float, x1: float, y1: float) -> Polygon:
    """Axis-aligned rectangle given in local FEET (x east, y north) -> WGS84."""
    return FRAME.to_wgs84(box(x0 * M_PER_FT, y0 * M_PER_FT, x1 * M_PER_FT, y1 * M_PER_FT))


def line_ft(*pts: tuple[float, float]) -> LineString:
    return FRAME.to_wgs84(LineString([(x * M_PER_FT, y * M_PER_FT) for x, y in pts]))


def point_lonlat_ft(x: float, y: float) -> tuple[float, float]:
    p = FRAME.to_wgs84(Point(x * M_PER_FT, y * M_PER_FT))
    return p.x, p.y
