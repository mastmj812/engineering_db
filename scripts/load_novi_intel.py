"""Orchestrate the Novi Intelligence (raw_novi_intel) load.

Phased so the multi-GB CSV COPY can be run separately from the fast shapefile load.
psql is not required — .sql files are executed via psycopg.

    python -m scripts.load_novi_intel --ddl --shapefiles      # schema + geometry/economics
    python -m scripts.load_novi_intel --csvs                  # analytics/arps/forecast (slow)
    python -m scripts.load_novi_intel --curated               # build/refresh curated.intel_*
    python -m scripts.load_novi_intel --all                   # everything, in order
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from etl.db import get_connection

logger = logging.getLogger(__name__)
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def run_sql_file(name: str) -> None:
    path = SQL_DIR / name
    sql_text = path.read_text(encoding="utf-8")
    logger.info("Executing %s", path)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(sql_text)
        conn.commit()
    logger.info("Done: %s", name)


def main() -> None:
    ap = argparse.ArgumentParser(description="Load Novi Intelligence into engineering_db.")
    ap.add_argument("--ddl", action="store_true", help="create/rebuild raw_novi_intel schema (sql/11)")
    ap.add_argument("--shapefiles", action="store_true", help="load sticks/pads/grid/outline")
    ap.add_argument("--csvs", action="store_true", help="load analytics/arps/forecast (slow)")
    ap.add_argument("--curated", action="store_true", help="build/refresh curated.intel_* (sql/12)")
    ap.add_argument("--all", action="store_true", help="ddl + shapefiles + csvs + curated")
    args = ap.parse_args()

    do_ddl = args.ddl or args.all
    do_shp = args.shapefiles or args.all
    do_csv = args.csvs or args.all
    do_cur = args.curated or args.all
    if not any((do_ddl, do_shp, do_csv, do_cur)):
        ap.error("specify at least one of --ddl/--shapefiles/--csvs/--curated/--all")

    if do_ddl:
        run_sql_file("11_raw_novi_intel.sql")
    if do_shp:
        from etl.novi_intel import load_shapefiles
        for b in ("delaware", "midland"):
            load_shapefiles.load_sticks(b)
            load_shapefiles.load_pads(b)
            load_shapefiles.load_grid(b)
            load_shapefiles.load_outline(b)
    if do_csv:
        from etl.novi_intel import load_csvs
        for b in ("delaware", "midland"):
            load_csvs.load_all(b)
    if do_cur:
        run_sql_file("12_curated_intel.sql")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
