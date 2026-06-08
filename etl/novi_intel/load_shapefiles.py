"""Load Novi Intelligence shapefiles (sticks / pads / land grid / outline) into
raw_novi_intel via pyshp + PostGIS ST_GeomFromGeoJSON. No GDAL dependency.

All Novi layers are EPSG:4326; geometry is forced 2D for spatial selection.
Loaders are idempotent per (basin, report_version): they DELETE that slice first.

Run as a module:
    python -m etl.novi_intel.load_shapefiles            # all basins, sticks+pads+grid+outline
    python -m etl.novi_intel.load_shapefiles --sticks-only
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

# target stick column -> candidate source DBF field names (handles per-basin drift)
STICK_SRC: dict[str, list[str]] = {
    "phase": ["Phase"], "operator": ["Operator"], "formation": ["Formation"],
    "county": ["County"], "pad_name": ["Pad Name", "PadName"], "has_econ": ["Has Econom"],
    "fp_year": ["FP_Year"], "tvd": ["TVD"], "md": ["MD"], "ll_ft": ["LL_ft"],
    "prop_load": ["Prop_Load"],
    "oil_eur": ["Oil_EUR"], "gas_eur": ["Gas_EUR"], "dgas_eur": ["DGas_EUR"],
    "ngl_eur": ["NGL_EUR"], "water_eur": ["Water_EUR"],
    "oil_ip": ["Oil_IP"], "gas_ip": ["Gas_IP"], "dgas_ip": ["DGas_IP"],
    "ngl_ip": ["NGL_IP"], "water_ip": ["Water_IP"],
    "ngl_yield": ["NGL_Yield"], "ngl_shrink": ["NGL_Shrink"],
    "npv5": ["NPV5"], "npv10": ["NPV10"], "npv15": ["NPV15"], "npv20": ["NPV20"], "npv25": ["NPV25"],
    "pv5": ["PV5"], "pv10": ["PV10"], "pv15": ["PV15"], "pv20": ["PV20"], "pv25": ["PV25"],
    "npv5_be": ["NPV5_B_e"], "npv10_be": ["NPV10_B_e"], "npv15_be": ["NPV15_B_e"],
    "npv20_be": ["NPV20_B_e"], "npv25_be": ["NPV25_B_e"],
    "be_1yr": ["1 Yr B_e"], "be_2yr": ["2 Yr B_e"], "be_3yr": ["3 Yr B_e"],
    "irr_pct": ["IRR_pct"], "pp_months": ["PP_Months"], "ttpt": ["TTPT"],
    "dc_cost": ["D_C_Cost"], "dcet_cost": ["DCET_Cost"], "norm_dc": ["Norm_DC"],
    "norm_dcet": ["Norm_DCET"],
    "wti_price": ["WTI_Price"], "hh_price": ["HH_Price"], "ngl_price": ["NGL_Price"],
    "wti_diff": ["WTI_Diff"], "hh_diff": ["HH_Diff"], "conf_int": ["Conf_Int", "Conf_int"],
}
TEXT_COLS = {"phase", "operator", "formation", "county", "pad_name", "has_econ"}
INT_COLS = {"fp_year"}
# full ordered column list written to raw_novi_intel.sticks (geom appended separately)
STICK_COLS = ["basin", "report_version", "src_layer", "unique_id", "api10", "category"] + list(STICK_SRC.keys())

CHUNK = 5000


def _safe_float(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v):
    f = _safe_float(v)
    return int(f) if f is not None else None


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
# sticks
# -----------------------------------------------------------------------------
def load_sticks(basin: str, version: str = paths.REPORT_VERSION) -> int:
    total = 0
    with log_etl_run("novi_intel", f"sticks:{basin}") as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM raw_novi_intel.sticks WHERE basin=%s AND report_version=%s",
                (basin, version),
            )
            for category in ("PDP", "PUD", "RES"):
                zp = paths.stick_zip(basin, category)
                if not zp:
                    logger.warning("No %s stick zip for %s", category, basin)
                    continue
                r = _open_reader(zp)
                src_layer = zp.stem
                batch: list[tuple] = []
                n = 0
                for sr in r.iterShapeRecords():
                    rec = sr.record.as_dict()
                    cat = (str(rec.get("PUD/PDP/RE")).strip() if rec.get("PUD/PDP/RE") else category)
                    uid_raw = rec.get("Unique ID")
                    uid = None if uid_raw is None else str(uid_raw).strip()
                    api10 = uid if (cat == "PDP" and uid and uid.isdigit()) else None
                    row = [basin, version, src_layer, uid, api10, cat]
                    for col, srcs in STICK_SRC.items():
                        val = next((rec[s] for s in srcs if s in rec and rec[s] not in (None, "")), None)
                        if col in TEXT_COLS:
                            row.append(None if val is None else str(val).strip())
                        elif col in INT_COLS:
                            row.append(_safe_int(val))
                        else:
                            row.append(_safe_float(val))
                    row.append(_geojson(sr.shape))
                    batch.append(tuple(row))
                    if len(batch) >= CHUNK:
                        _insert_chunk(cur, "sticks", STICK_COLS, batch)
                        n += len(batch); batch = []
                if batch:
                    _insert_chunk(cur, "sticks", STICK_COLS, batch)
                    n += len(batch)
                total += n
                logger.info("sticks %s/%s: %d rows from %s", basin, category, n, src_layer)
            conn.commit()
        run.rows_inserted = total
    return total


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
    ap = argparse.ArgumentParser(description="Load Novi Intelligence shapefiles into raw_novi_intel.")
    ap.add_argument("--sticks-only", action="store_true")
    ap.add_argument("--basin", choices=["delaware", "midland"], default=None)
    args = ap.parse_args()
    basins = [args.basin] if args.basin else ["delaware", "midland"]
    for b in basins:
        load_sticks(b)
        if not args.sticks_only:
            load_pads(b)
            load_grid(b)
            load_outline(b)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
