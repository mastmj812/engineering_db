"""BOX step 3 — geology round-trip I/O (pure; DB-free).

D7: geology reviews extents as SHAPEFILES in NAD83 / UTM zone 14N, US-survey feet (GGX cannot read
gpkg). There is no standard EPSG code for that combination, so the .prj is written from the exact
ESRI definition below (verified equal to ``+proj=utm +zone=14 +datum=NAD83 +units=us-ft``), and the
coordinates are already projected because GGX may ignore the .prj. Reading assumes the same frame
whatever the returned .prj says, and checks the coordinates fall where the generated extent was.

Frames: the BOX pure modules work in UTM 13N feet (box.edge_gap); lon/lat is the bridge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import shapefile  # pyshp
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Point,
    Polygon,
    shape,
)

from box import edge_gap as eg

ESRI_WKT = (
    'PROJCS["NAD_1983_UTM_Zone_14N_ftUS",GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",'
    'SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
    'PROJECTION["Transverse_Mercator"],PARAMETER["False_Easting",1640416.666666667],PARAMETER["False_Northing",0.0],'
    'PARAMETER["Central_Meridian",-99.0],PARAMETER["Scale_Factor",0.9996],PARAMETER["Latitude_Of_Origin",0.0],'
    'UNIT["Foot_US",0.3048006096012192]]'
)
GEOLOGY_CRS = CRS.from_wkt(ESRI_WKT)


def _tr(a: Any, b: Any) -> Transformer:
    return Transformer.from_crs(a, b, always_xy=True)


def _apply(g: Any, tr: Transformer) -> Any:
    return shapely.transform(g, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])))


def lonlat_to_geology(geoms: list[Any]) -> list[Any]:
    tr = _tr("EPSG:4269", GEOLOGY_CRS)
    return [_apply(g, tr) for g in geoms]


def geology_to_lonlat(geoms: list[Any]) -> list[Any]:
    tr = _tr(GEOLOGY_CRS, "EPSG:4269")
    return [_apply(g, tr) for g in geoms]


def ft13_to_geology(geoms: list[Any]) -> list[Any]:
    return lonlat_to_geology(eg.to_lonlat(geoms))


def geology_to_ft13(geoms: list[Any]) -> list[Any]:
    return eg.to_ft(geology_to_lonlat(geoms))


# ----------------------------------------------------------------------------
# Write
# ----------------------------------------------------------------------------


def _rings(poly: Polygon) -> list[list[tuple[float, float]]]:
    """Shapefile ring order: exterior clockwise, holes counter-clockwise."""
    p = shapely.geometry.polygon.orient(poly, sign=-1.0)
    return [list(p.exterior.coords)] + [list(h.coords) for h in p.interiors]


def write_layer(stem: Path, kind: str, geoms: list[Any], fields: list[tuple[str, str, int, int]], records: list[list[Any]]) -> list[Path]:
    """Write <stem>.shp/.shx/.dbf/.prj/.cpg. kind = polygon | line | point. Field names <= 10
    chars (dBASE); C fields <= 254. Geometries are already in the geology frame."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    st = {"polygon": shapefile.POLYGON, "line": shapefile.POLYLINE, "point": shapefile.POINT}[kind]
    with shapefile.Writer(str(stem), shapeType=st, encoding="utf-8") as w:
        for name, typ, size, dec in fields:
            assert len(name) <= 10, name
            w.field(name, typ, size=size, decimal=dec)
        for g, rec in zip(geoms, records):
            if kind == "polygon":
                parts = [r for p in eg._as_multi(g).geoms for r in _rings(p)]
                w.poly(parts)
            elif kind == "line":
                ls = list(g.geoms) if isinstance(g, MultiLineString) else [g]
                w.line([list(x.coords) for x in ls])
            else:
                w.point(g.x, g.y)
            w.record(*[_clip(v, f) for v, f in zip(rec, fields)])
    stem.with_suffix(".prj").write_text(ESRI_WKT, encoding="ascii")
    stem.with_suffix(".cpg").write_text("UTF-8", encoding="ascii")
    return [stem.with_suffix(s) for s in (".shp", ".shx", ".dbf", ".prj", ".cpg")]


def _clip(v: Any, f: tuple[str, str, int, int]) -> Any:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    if f[1] == "C":
        return str(v)[: f[2]]
    if f[1] == "N" and f[3] == 0:
        return round(float(v))
    if f[1] == "N":
        return round(float(v), f[3])
    return v


# ----------------------------------------------------------------------------
# Read
# ----------------------------------------------------------------------------


def read_layer(path: Path) -> list[tuple[Any, dict[str, Any]]]:
    """[(shapely geometry in the geology frame, attributes)] — any shape type pyshp can read."""
    out = []
    with shapefile.Reader(str(path), encoding="utf-8", encodingErrors="replace") as r:
        names = [f[0] for f in r.fields[1:]]
        for sr in r.iterShapeRecords():
            if sr.shape.shapeType == shapefile.NULL:
                continue
            out.append((shape(sr.shape.__geo_interface__), dict(zip(names, list(sr.record)))))
    return out


def read_extent(path: Path, bench: str | None = None) -> MultiPolygon:
    """Union of the polygon features (optionally only those whose BENCH attribute matches),
    repaired with make_valid, in the geology frame."""
    polys = []
    for g, a in read_layer(path):
        if bench is not None and "BENCH" in a and str(a["BENCH"]).strip() and str(a["BENCH"]).strip() != bench:
            continue
        if isinstance(g, (Polygon, MultiPolygon)):
            polys.append(shapely.make_valid(g))
    u = shapely.union_all(polys) if polys else Polygon()
    return eg._as_multi(u)


def check_frame(edited: Any, generated: Any, tol_ft: float = 26_400.0) -> str:
    """'' if the edited geometry sits where the generated one does (bbox centres within tol, 5 mi);
    else a message — the usual cause is GGX exporting in a different CRS/unit."""
    if edited.is_empty:
        return "edited layer has no polygons"
    a, b = edited.bounds, generated.bounds
    ca = Point((a[0] + a[2]) / 2, (a[1] + a[3]) / 2)
    cb = Point((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    d = ca.distance(cb)
    if d > tol_ft:
        return f"edited extent centre is {d / eg.FT_PER_MI:,.1f} mi from the generated one — wrong CRS or units? (expected NAD83 UTM 14N US-ft)"
    return ""


def lines_from_paths(segs: list[np.ndarray]) -> list[LineString]:
    return [LineString(s) for s in segs if len(s) >= 2]
