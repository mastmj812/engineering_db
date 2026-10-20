"""Load Novi Intelligence overlay shapefiles (pads / land grid / basin outline)
into raw_novi_intel via pyshp + PostGIS ST_GeomFromGeoJSON. No GDAL dependency.

OVERLAYS ONLY: the stick/economics loader was retired when the data moved to the
Snowflake share (etl/intel_sf -> raw_intel). These three layers are the display
geometries the share does not carry.

All Novi layers are EPSG:4326; geometry is forced 2D for spatial selection.
Loaders are idempotent per (basin, report_version): they DELETE that slice first,
so older vintages stay alongside (pads: 3Q25 + 2026Q3 rows coexist).

Pads load at paths.PADS_REPORT_VERSION (2026Q3, nested Mid-Cycle pad summary),
grid/outline at paths.REPORT_VERSION (3Q25). Every pad polygon is kept, including
WellCnt = 0 (the Pad Summary layer counts only wells with Novi NPV25 >= 0, so 0 is
not an empty DSU): the raw table is the DSU geometry of record (future DSU infill);
curated.intel_pad_geom (sql/67) is only the stick-membership view.

Run as a module:
    python -m etl.novi_intel.load_shapefiles            # all basins, pads+grid+outline
    python -m etl.novi_intel.load_shapefiles --basin midland
    python -m etl.novi_intel.load_shapefiles --pads-only
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path

import shapefile  # pyshp

from etl.db import get_connection, log_etl_run
from etl.novi_intel import paths

logger = logging.getLogger(__name__)

CHUNK = 5000


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _open_reader(zip_path: Path, member: str | None = None) -> shapefile.Reader:
    """Open a pyshp Reader from the .shp/.dbf/.shx inside a zip (case-insensitive).

    member: a zip nested inside zip_path (the 2026Q3 pad layout); the inner zip
    is read into memory, nothing is extracted to disk.
    """
    z = zipfile.ZipFile(zip_path)
    if member is not None:
        z = zipfile.ZipFile(io.BytesIO(z.read(member)))
    names = z.namelist()
    shp_name = next(n for n in names if n.lower().endswith(".shp"))
    stem = shp_name[:-4].lower()

    def grab(ext):
        for n in names:
            if n.lower() == stem + ext:
                return io.BytesIO(z.read(n))
        return None

    return shapefile.Reader(shp=io.BytesIO(z.read(shp_name)), dbf=grab(".dbf"), shx=grab(".shx"))


def _geojson(shape) -> str | None:
    try:
        gj = shape.__geo_interface__
    except Exception:
        return None
    if not gj or not gj.get("coordinates"):
        return None
    return json.dumps(gj)


def _insert_chunk(cur, table: str, cols: list[str], rows: list[tuple]) -> None:
    placeholders = ", ".join(["%s"] * len(cols))
    sql = (
        f"INSERT INTO raw_novi_intel.{table} ({', '.join(cols)}, geom) "
        f"VALUES ({placeholders}, ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)))"
    )
    cur.executemany(sql, rows)


# -----------------------------------------------------------------------------
# pads
# -----------------------------------------------------------------------------
PAD_COLS = ["basin", "report_version", "pad_name", "operator", "npv0", "npv5", "npv10",
            "npv15", "npv20", "npv25", "ll_sum_ft", "well_cnt"]


def _field(rec: dict, *names: str):
    """First present field, matched case-insensitively (Novi renames between drops:
    'Pad Name' / 'PadName' in 3Q25, 'padName' in 2026Q3)."""
    low = {k.lower(): v for k, v in rec.items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def pad_row(basin: str, version: str, rec: dict) -> tuple:
    """DBF record -> raw_novi_intel.pads values (PAD_COLS order), as shipped.

    3Q25: Pad Name / NPV5..NPV25 (Delaware SUM_NPV25). 2026Q3: padName, Operator,
    NPV0_Sum (Delaware only)..NPV25_Sum, LL_Sum, WellCnt. Absent fields -> NULL.
    """
    pad_name = _field(rec, "Pad Name", "PadName")
    operator = _field(rec, "Operator")
    well_cnt = _safe_float(_field(rec, "WellCnt"))

    def npv(k: int):
        return _safe_float(_field(rec, f"NPV{k}_Sum", f"NPV{k}", f"SUM_NPV{k}"))

    return (
        basin, version,
        None if pad_name is None else str(pad_name).strip(),
        (str(operator).strip() or None) if operator is not None else None,
        npv(0), npv(5), npv(10), npv(15), npv(20), npv(25),
        _safe_float(_field(rec, "LL_Sum")),
        None if well_cnt is None else int(well_cnt),
    )


def pad_record_count(basin: str) -> int:
    """Polygons in the basin's pad shapefile on disk (the load's identity check)."""
    src = paths.pad_source(basin)
    if not src:
        return 0
    return len(_open_reader(*src))


def load_pads(basin: str, version: str = paths.PADS_REPORT_VERSION) -> int:
    src = paths.pad_source(basin)
    if not src:
        logger.warning("No pad zip for %s", basin)
        return 0
    with log_etl_run("novi_intel", f"pads:{basin}") as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM raw_novi_intel.pads WHERE basin=%s AND report_version=%s",
                (basin, version),
            )
            r = _open_reader(*src)
            batch, n = [], 0
            for sr in r.iterShapeRecords():
                batch.append(pad_row(basin, version, sr.record.as_dict()) + (_geojson(sr.shape),))
                if len(batch) >= CHUNK:
                    _insert_chunk(cur, "pads", PAD_COLS, batch); n += len(batch); batch = []
            if batch:
                _insert_chunk(cur, "pads", PAD_COLS, batch); n += len(batch)
            conn.commit()
        run.rows_inserted = n
        logger.info("pads %s %s: %d rows", basin, version, n)
        return n


# -----------------------------------------------------------------------------
# generic polygon overlays (land grid, basin outline) -> attrs JSONB + geom
# -----------------------------------------------------------------------------
def _load_overlay(basin: str, table: str, zip_path: Path | None, version: str) -> int:
    if not zip_path:
        logger.warning("No %s zip for %s", table, basin)
        return 0
    cols = ["basin", "report_version", "attrs"]
    with log_etl_run("novi_intel", f"{table}:{basin}") as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM raw_novi_intel.{table} WHERE basin=%s AND report_version=%s",
                (basin, version),
            )
            r = _open_reader(zip_path)
            batch, n = [], 0
            for sr in r.iterShapeRecords():
                rec = {k: (v if isinstance(v, (int, float, str)) or v is None else str(v))
                       for k, v in sr.record.as_dict().items()}
                batch.append((basin, version, json.dumps(rec), _geojson(sr.shape)))
                if len(batch) >= CHUNK:
                    _insert_chunk(cur, table, cols, batch); n += len(batch); batch = []
            if batch:
                _insert_chunk(cur, table, cols, batch); n += len(batch)
            conn.commit()
        run.rows_inserted = n
        logger.info("%s %s: %d rows", table, basin, n)
        return n


def load_grid(basin: str, version: str = paths.REPORT_VERSION) -> int:
    return _load_overlay(basin, "land_grid", paths.grid_zip(basin), version)


def load_outline(basin: str, version: str = paths.REPORT_VERSION) -> int:
    return _load_overlay(basin, "basin_outline", paths.outline_zip(basin), version)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Load Novi Intelligence overlay shapefiles into raw_novi_intel.")
    ap.add_argument("--basin", choices=["delaware", "midland"], default=None)
    ap.add_argument("--pads-only", action="store_true", help="load DSU pad polygons only")
    args = ap.parse_args()
    basins = [args.basin] if args.basin else ["delaware", "midland"]
    for b in basins:
        load_pads(b)
        if not args.pads_only:
            load_grid(b)
            load_outline(b)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
