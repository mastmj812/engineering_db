"""Generate docs/templates/dsu_tract_template.gpkg — the land-department
starting file for deal GeoPackages (see docs/gpkg_authoring_spec.md).

Stdlib only (sqlite3 + struct): a GeoPackage is a SQLite database with a few
registry tables and geometry blobs (GPKG header + WKB). No GDAL, no shapely —
this must run anywhere the repo runs.

    python -m scripts.make_gpkg_template

The template carries one polygon layer named "Template Deal" with the full
column set of the schema of record (Toucan v2 + Depth_Basis) and three example
rows: a 2-section DSU and its two tracts, placed in Reeves County. The land
team copies the file, renames it to the deal, deletes the examples, and
digitizes the real units in QGIS.
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "templates" / "dsu_tract_template.gpkg"

LAYER = "Template Deal"

# EPSG:4326 definition WKT — QGIS reads the CRS from gpkg_spatial_ref_sys.
WGS84_WKT = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,'
    'AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],'
    'PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
)

# ~1 mile in degrees near 31.7 N (longitude shrinks with cos(lat); close enough
# for an EXAMPLE polygon the land team deletes anyway)
_D_LAT = 1.0 / 69.0
_D_LON = 1.0 / 58.7


def _ring(lon: float, lat: float, nx: float = 1.0, ny: float = 1.0) -> list[tuple[float, float]]:
    """Closed rectangle ring, nx x ny miles with SW corner at (lon, lat)."""
    return [
        (lon, lat), (lon + nx * _D_LON, lat), (lon + nx * _D_LON, lat + ny * _D_LAT),
        (lon, lat + ny * _D_LAT), (lon, lat),
    ]


def _wkb_polygon(ring: list[tuple[float, float]]) -> bytes:
    """Little-endian ISO WKB POLYGON, one exterior ring."""
    out = struct.pack("<BII", 1, 3, 1)          # byte order LE, type=Polygon, 1 ring
    out += struct.pack("<I", len(ring))
    for x, y in ring:
        out += struct.pack("<2d", x, y)
    return out


def _gpkg_blob(ring: list[tuple[float, float]]) -> bytes:
    """GPKG geometry blob: 'GP', version 0, flags (LE byte order + 32-byte XY
    envelope), srs_id, envelope [minx maxx miny maxy], WKB."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    header = b"GP\x00" + bytes([0x01 | (1 << 1)]) + struct.pack("<i", 4326)
    header += struct.pack("<4d", min(xs), max(xs), min(ys), max(ys))
    return header + _wkb_polygon(ring)


# Column set of record (docs/gpkg_authoring_spec.md section 3)
COLUMNS: list[tuple[str, str]] = [
    ("Type", "TEXT(10)"),
    ("Section", "TEXT(10)"),
    ("Block", "TEXT(12)"),
    ("County", "TEXT(20)"),
    ("Aliquot", "TEXT(40)"),
    ("Min_Depth", "TEXT(40)"),
    ("Max_Depth", "TEXT(40)"),
    ("Depth_Basis", "TEXT(60)"),
    ("Gross_Ac", "REAL"),
    ("Net_Ac", "REAL"),
    ("Tract_WI", "REAL"),
    ("Tract_NRI", "REAL"),
    ("DSU_Num", "TEXT(30)"),
    ("DSU_WI", "REAL"),
    ("DSU_NRI", "REAL"),
]

# Example rows the land team deletes: a 2-section DSU (sections 12+13) and its
# two tracts. Depths demonstrate the guidance: numeric ft TVD + Depth_Basis.
_SW = (-103.75, 31.70)
EXAMPLES: list[tuple[dict[str, object], list[tuple[float, float]]]] = [
    (
        {"Type": "Tract", "Section": "12", "Block": "2", "County": "Reeves",
         "Aliquot": "All", "Min_Depth": "Surface", "Max_Depth": "9950",
         "Depth_Basis": "log-correlated",
         "Gross_Ac": 640.0, "Net_Ac": 640.0, "Tract_WI": 1.0, "Tract_NRI": 0.75},
        _ring(*_SW),
    ),
    (
        {"Type": "Tract", "Section": "13", "Block": "2", "County": "Reeves",
         "Aliquot": "All", "Min_Depth": "Surface",
         "Max_Depth": "100' above Top of Wolfcamp",
         "Depth_Basis": "lease-language",
         "Gross_Ac": 640.0, "Net_Ac": 320.0, "Tract_WI": 0.5, "Tract_NRI": 0.375},
        _ring(_SW[0] + _D_LON, _SW[1]),
    ),
    (
        {"Type": "DSU", "County": "Reeves", "Min_Depth": "Surface",
         "Max_Depth": "9950", "Depth_Basis": "log-correlated",
         "DSU_Num": "12-13", "DSU_WI": 0.75, "DSU_NRI": 0.5625},
        _ring(*_SW, nx=2.0),
    ),
]


def build(path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        # GPKG file signature: application_id "GPKG", spec version 1.3
        conn.execute("PRAGMA application_id = 0x47504B47")
        conn.execute("PRAGMA user_version = 10300")
        conn.executescript(
            """
            CREATE TABLE gpkg_spatial_ref_sys (
                srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY,
                organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
                definition TEXT NOT NULL, description TEXT);
            CREATE TABLE gpkg_contents (
                table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
                identifier TEXT UNIQUE, description TEXT DEFAULT '',
                last_change DATETIME NOT NULL DEFAULT
                    (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
                srs_id INTEGER);
            CREATE TABLE gpkg_geometry_columns (
                table_name TEXT NOT NULL, column_name TEXT NOT NULL,
                geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
                z TINYINT NOT NULL, m TINYINT NOT NULL,
                CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name));
            """
        )
        conn.execute(
            "INSERT INTO gpkg_spatial_ref_sys VALUES "
            "('Undefined Cartesian SRS', -1, 'NONE', -1, 'undefined', NULL),"
            "('Undefined geographic SRS', 0, 'NONE', 0, 'undefined', NULL),"
            "(?, 4326, 'EPSG', 4326, ?, 'WGS 84')",
            ("WGS 84", WGS84_WKT),
        )

        col_ddl = "".join(f', "{name}" {typ}' for name, typ in COLUMNS)
        conn.execute(
            f'CREATE TABLE "{LAYER}" ('
            f'"fid" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,'
            f' "geom" POLYGON{col_ddl})'
        )

        rings = [r for _, r in EXAMPLES]
        all_pts = [p for r in rings for p in r]
        conn.execute(
            "INSERT INTO gpkg_contents (table_name, data_type, identifier,"
            " description, min_x, min_y, max_x, max_y, srs_id)"
            " VALUES (?, 'features', ?, ?, ?, ?, ?, ?, 4326)",
            (LAYER, LAYER,
             "Blue Ox deal template - see docs/gpkg_authoring_spec.md",
             min(p[0] for p in all_pts), min(p[1] for p in all_pts),
             max(p[0] for p in all_pts), max(p[1] for p in all_pts)),
        )
        conn.execute(
            "INSERT INTO gpkg_geometry_columns VALUES (?, 'geom', 'POLYGON', 4326, 0, 0)",
            (LAYER,),
        )

        col_names = ", ".join(f'"{name}"' for name, _ in COLUMNS)
        placeholders = ", ".join(["?"] * (1 + len(COLUMNS)))
        for attrs, ring in EXAMPLES:
            conn.execute(
                f'INSERT INTO "{LAYER}" (geom, {col_names}) VALUES ({placeholders})',
                [_gpkg_blob(ring)] + [attrs.get(name) for name, _ in COLUMNS],
            )
        conn.commit()
    finally:
        conn.close()
    return path


if __name__ == "__main__":
    out = build()
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
