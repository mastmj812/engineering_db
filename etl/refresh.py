"""Refresh curated materialized views.

Runs `refresh_curated()`, which refreshes each matview individually and SKIPS a
gated one (e.g. curated.production_forecast) when its source raw table hasn't
changed since its last successful refresh — avoiding the memory-heavy rebuild on
no-change nights.

Run as a module:
    python -m etl.refresh              # gated (nightly): skip unchanged matviews
    python -m etl.refresh --force      # refresh everything (use after a reconcile)
"""

from __future__ import annotations

import argparse
import logging

from etl.db import refresh_curated

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Refresh curated matviews (gated by default) and log success/failure."""
    parser = argparse.ArgumentParser(description="Refresh curated matviews")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh every matview regardless of the change gate (e.g. after a "
        "full_reconcile_table, whose deletions the incremental watermark misses).",
    )
    args = parser.parse_args(argv)
    try:
        refresh_curated(force=args.force)
        logger.info("Curated refresh complete")
    except Exception:
        logger.exception("Curated refresh failed")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
