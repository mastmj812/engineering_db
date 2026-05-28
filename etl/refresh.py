"""Refresh curated materialized views by calling `curated.refresh_all()`.

Run as a module:
    python -m etl.refresh
"""

from __future__ import annotations

import logging

from etl.db import refresh_curated

logger = logging.getLogger(__name__)


def main() -> None:
    """Invoke `curated.refresh_all()` and log success/failure."""
    try:
        refresh_curated()
        logger.info("Curated refresh complete")
    except Exception:
        logger.exception("Curated refresh failed")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
