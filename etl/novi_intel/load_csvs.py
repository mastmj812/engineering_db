"""COPY the Novi Intelligence CSVs (analytics / arps / forecast) into raw_novi_intel.

Fast path: raw block streaming COPY. basin / report_version are not in the CSVs, so
we set them as a per-load column DEFAULT just before COPY (the column list passed to
COPY omits them, so they take the default) and drop the default afterward. This keeps
the multi-GB forecast COPY at full speed (no per-row Python).

Idempotent per (basin, report_version): DELETE that slice before COPY.

    python -m etl.novi_intel.load_csvs                 # both basins, all three CSVs
    python -m etl.novi_intel.load_csvs --basin midland --kind forecast
"""

from __future__ import annotations

import logging

from psycopg import sql

from etl.db import get_connection, log_etl_run
from etl.novi_intel import paths

logger = logging.getLogger(__name__)

# table -> CSV column list IN FILE ORDER (basin/report_version/ingested_at excluded)
CSV_COLS: dict[str, list[str]] = {
    "analytics": [
        "well_name", "tvd", "midpoint_lat", "midpoint_lon", "bh_lat", "bh_lon",
        "heel_lat", "heel_lon", "target_formation", "lateral_length",
        "proppant_loading", "fluid_loading", "county", "subbasin",
        "proppant_mass", "fluid_volume", "md", "pad_name",
    ],
    "arps": [
        "job_name", "well_inventory_name", "planned_well_id", "production_stream",
        "segment", "segment_curve_type", "b", "d_nom", "d_eff_secant",
        "d_eff_tangent", "q_start", "q_stop", "terminal_day", "day_start",
        "day_stop", "novi_wellname",
    ],
    "forecast": ["ip_day", "novi_wellname", "oil", "gas", "water", "pad_name"],
}
KIND_TO_TABLE = {"analytics": "analytics", "arps": "arps", "forecast": "forecast"}
BLOCK = 1 << 20  # 1 MiB


def load_csv(basin: str, kind: str, version: str = paths.REPORT_VERSION) -> int:
    table = KIND_TO_TABLE[kind]
    path = paths.csv_path(basin, kind)
    if not path:
        logger.warning("No %s CSV for %s", kind, basin)
        return 0
    cols = CSV_COLS[table]
    col_list = ", ".join(f'"{c}"' for c in cols)

    with log_etl_run("novi_intel", f"{table}:{basin}") as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                sql.SQL("DELETE FROM raw_novi_intel.{} WHERE basin=%s AND report_version=%s")
                .format(sql.Identifier(table)),
                (basin, version),
            )
            cur.execute(
                sql.SQL(
                    "ALTER TABLE raw_novi_intel.{} "
                    "ALTER COLUMN basin SET DEFAULT {}, "
                    "ALTER COLUMN report_version SET DEFAULT {}"
                ).format(sql.Identifier(table), sql.Literal(basin), sql.Literal(version))
            )
            copy_sql = (
                f"COPY raw_novi_intel.{table} ({col_list}) "
                f"FROM STDIN WITH (FORMAT CSV, HEADER)"
            )
            logger.info("COPY %s <- %s (%.0f MB)", table, path.name, path.stat().st_size / 1e6)
            with open(path, "rb") as f, cur.copy(copy_sql) as copy:
                while data := f.read(BLOCK):
                    copy.write(data)
            cur.execute(
                sql.SQL(
                    "ALTER TABLE raw_novi_intel.{} "
                    "ALTER COLUMN basin DROP DEFAULT, "
                    "ALTER COLUMN report_version DROP DEFAULT"
                ).format(sql.Identifier(table))
            )
            cur.execute(
                sql.SQL("SELECT count(*) FROM raw_novi_intel.{} WHERE basin=%s AND report_version=%s")
                .format(sql.Identifier(table)),
                (basin, version),
            )
            n = int(cur.fetchone()[0])
            conn.commit()
        run.rows_inserted = n
    logger.info("%s %s: %d rows", table, basin, n)
    return n


def load_all(basin: str, version: str = paths.REPORT_VERSION) -> dict[str, int]:
    return {k: load_csv(basin, k, version) for k in ("analytics", "arps", "forecast")}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="COPY Novi Intelligence CSVs into raw_novi_intel.")
    ap.add_argument("--basin", choices=["delaware", "midland"], default=None)
    ap.add_argument("--kind", choices=["analytics", "arps", "forecast"], default=None)
    args = ap.parse_args()
    basins = [args.basin] if args.basin else ["delaware", "midland"]
    kinds = [args.kind] if args.kind else ["analytics", "arps", "forecast"]
    for b in basins:
        for k in kinds:
            load_csv(b, k)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
