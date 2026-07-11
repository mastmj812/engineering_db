"""Load Novi Intelligence overlay shapefiles (pads / land grid / basin outline)
into raw_novi_intel via pyshp + PostGIS ST_GeomFromGeoJSON. No GDAL dependency.

OVERLAYS ONLY: the stick/economics loader was retired when the data moved to the
Snowflake share (etl/intel_sf -> raw_intel). These three layers are the display
geometries the share does not carry.

All Novi layers are EPSG:4326; geometry is forced 2D for spatial selection.
Loaders are idempotent per (basin, report_version): they DELETE that slice first.

Run as a module:
    python -m etl.novi_intel.load_shapefiles            # all basins, pads+grid+outline
    python -m etl.novi_intel.load_shapefiles --basin midland
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


def _open_reader(zip_path: Path) -> shapefile.Reader:
    """Open a pyshp Reader from the .shp/.dbf/.shx inside a zip (case-insensitive)."""
    z = zipfile.ZipFile(zip_path)
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
def load_pads(basin: str, version: str = paths.REPORT_VERSION) -> int:
    zp = paths.pad_zip(basin)
    if not zp:
        logger.warning("No pad zip for %s", basin)
        return 0
    cols = ["basin", "report_version", "pad_name", "npv5", "npv10", "npv15", "npv20", "npv25"]
    with log_etl_run("novi_intel", f"pads:{basin}") as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM raw_novi_intel.pads WHERE basin=%s AND report_version=%s",
                (basin, version),
            )
            r = _open_reader(zp)
            batch, n = [], 0
            for sr in r.iterShapeRecords():
                rec = sr.record.as_dict()
                pad_name = next((rec[s] for s in ("Pad Name", "PadName") if s in rec), None)
                npv25 = next((rec[s] for s in ("NPV25", "SUM_NPV25") if s in rec), None)
                row = (
                    basin, version,
                    None if pad_name is None else str(pad_name).strip(),
                    _safe_float(rec.get("NPV5")), _safe_float(rec.get("NPV10")),
                    _safe_float(rec.get("NPV15")), _safe_float(rec.get("NPV20")),
                    _safe_float(npv25), _geojson(sr.shape),
                )
                batch.append(row)
                if len(batch) >= CHUNK:
                    _insert_chunk(cur, "pads", cols, batch); n += len(batch); batch = []
            if batch:
                _insert_chunk(cur, "pads", cols, batch); n += len(batch)
            conn.commit()
        run.rows_inserted = n
        logger.info("pads %s: %d rows", basin, n)
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
    args = ap.parse_args()
    basins = [args.basin] if args.basin else ["delaware", "midland"]
    for b in basins:
        load_pads(b)
        load_grid(b)
        load_outline(b)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
