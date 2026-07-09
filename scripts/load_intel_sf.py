"""Orchestrate the Novi INTEL Snowflake share load into raw_intel.

Phased like scripts/load_novi_intel.py (which this replaces at cutover):

    python -m scripts.load_intel_sf --ddl        # sql/27 + sql/28 (Supabase DDL — needs authorization)
    python -m scripts.load_intel_sf --core       # spine + entities + dims (11 views)
    python -m scripts.load_intel_sf --ml         # WELL_ML_SCORE + WELL_ROCK_QUALITY
    python -m scripts.load_intel_sf --econ       # cost/economics/price decks
    python -m scripts.load_intel_sf --arps       # ARPS_FORECAST
    python -m scripts.load_intel_sf --forecast   # PRODUCTION_FORECAST (deferred to the phase-4 gate)
    python -m scripts.load_intel_sf --curated    # locked until phase-6 cutover
    python -m scripts.load_intel_sf --report basin_research__Midland_Basin__2025Q3   # restrict slice

Default report set = every report with visible (entitled) data in WELL_MASTER.
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
    ap = argparse.ArgumentParser(description="Load the Novi INTEL share into raw_intel.")
    ap.add_argument("--ddl", action="store_true", help="run sql/27 + sql/28 (Supabase DDL)")
    ap.add_argument("--core", action="store_true", help="spine + entity + dimension views")
    ap.add_argument("--ml", action="store_true", help="ML score views")
    ap.add_argument("--econ", action="store_true", help="cost / economics / price deck views")
    ap.add_argument("--arps", action="store_true", help="Arps decline segments")
    ap.add_argument("--forecast", action="store_true", help="PRODUCTION_FORECAST (deferred)")
    ap.add_argument("--curated", action="store_true", help="rebuild curated intel layer (locked)")
    ap.add_argument("--all", action="store_true", help="core + ml + econ + arps")
    ap.add_argument("--report", default=None, help="restrict to one report_name")
    args = ap.parse_args()

    groups = [g for g in ("core", "ml", "econ", "arps") if getattr(args, g) or args.all]
    if not any((args.ddl, groups, args.forecast, args.curated)):
        ap.error("specify at least one of --ddl/--core/--ml/--econ/--arps/--forecast/--curated/--all")

    if args.ddl:
        run_sql_file("27_raw_intel.sql")
        run_sql_file("28_meta_intel_watermark.sql")

    if args.curated:
        # Blast radius = the quarterly-reload CASCADE: intel_formation_blueox,
        # reconciled_inventory, net_new_pdp, erebor_locations all drop with
        # intel_locations. Follow with the apply_* rebuild sequence + sql/26.
        run_sql_file("29_curated_intel_sf.sql")

    if args.forecast:
        from etl.intel_sf.extract import load_views
        counts = load_views(["PRODUCTION_FORECAST"],
                            [args.report] if args.report else None)
        logger.info("forecast load complete: %s", counts)

    if groups:
        from etl.intel_sf.config import MIRRORED_VIEWS
        from etl.intel_sf.extract import load_views

        reports = [args.report] if args.report else None
        views = [v for g in groups for v in MIRRORED_VIEWS[g]]
        counts = load_views(views, reports)
        logger.info("=== load complete ===")
        for table, n in counts.items():
            logger.info("  %-28s %12d rows", table, n)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
