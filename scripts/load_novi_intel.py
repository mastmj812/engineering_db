"""Load the Novi Intelligence OVERLAY geometries (raw_novi_intel pads / land_grid /
basin_outline) from the shapefile drop.

Overlays only. The intel data itself (sticks, ML attrs, arps, forecast, economics)
loads from the Snowflake share via scripts/load_intel_sf.py; the file-drop loaders
for those were retired 2026-07-10 when their raw_novi_intel tables were dropped.
The share ships no DSU/pad/land-grid/basin-outline geometry, so this shapefile
route remains the only ingest path for the map overlays.

    python -m scripts.load_novi_intel --ddl          # (re)create the overlay trio (sql/11)
    python -m scripts.load_novi_intel --shapefiles   # load pads/land_grid/basin_outline

CAUTION: --ddl DROP+CREATEs the overlay tables, so it wipes the currently loaded
geometries — always follow with --shapefiles from a file drop on disk.
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
    ap = argparse.ArgumentParser(description="Load Novi Intelligence overlay shapefiles.")
    ap.add_argument("--ddl", action="store_true",
                    help="rebuild the raw_novi_intel overlay tables (sql/11 — wipes loaded geometry)")
    ap.add_argument("--shapefiles", action="store_true", help="load pads/land_grid/basin_outline")
    args = ap.parse_args()

    if not (args.ddl or args.shapefiles):
        ap.error("specify --ddl and/or --shapefiles")

    if args.ddl:
        run_sql_file("11_raw_novi_intel.sql")
    if args.shapefiles:
        from etl.novi_intel import load_shapefiles
        for b in ("delaware", "midland"):
            load_shapefiles.load_pads(b)
            load_shapefiles.load_grid(b)
            load_shapefiles.load_outline(b)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
