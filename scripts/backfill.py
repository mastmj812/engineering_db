"""One-time historical backfill of a single source/table.

This is *not* the daily pipeline — `run_daily.py` handles incremental loads.
Use this when you need to (re)load a wide date range, e.g. after the DDL
changes or when bringing a new source online.

Example:
    python -m scripts.backfill --source enverus --table production \
        --start-date 2010-01-01 --end-date 2025-12-31
"""

from __future__ import annotations

import argparse
import logging
from datetime import date


def _parse_date(s: str) -> date:
    return date.fromisoformat(s)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and return CLI arguments for the backfill script."""
    parser = argparse.ArgumentParser(
        description="Historical backfill loader for engineering_db."
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=["enverus", "novi"],
        help="Data source to backfill from.",
    )
    parser.add_argument(
        "--table",
        required=True,
        choices=["wells", "production"],
        help="Target table (within the source's raw schema).",
    )
    parser.add_argument(
        "--start-date",
        type=_parse_date,
        required=False,
        help="Earliest date (YYYY-MM-DD) to include. Applies to production loads.",
    )
    parser.add_argument(
        "--end-date",
        type=_parse_date,
        required=False,
        help="Latest date (YYYY-MM-DD) to include. Applies to production loads.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point. Currently a placeholder until the per-source clients are real."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger = logging.getLogger(__name__)
    logger.info(
        "backfill requested: source=%s table=%s start=%s end=%s",
        args.source,
        args.table,
        args.start_date,
        args.end_date,
    )
    raise NotImplementedError(
        "backfill is a stub until the Enverus/Novi clients are wired up. "
        "Implement once incremental pulls work end-to-end."
    )


if __name__ == "__main__":
    main()
