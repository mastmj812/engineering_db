"""Delete production rows for wellbores whose completion events are all VERTICAL.

The daily incremental production pull (in `etl/enverus/pull.py`) skips the
per-wellbore chunked filter when an incremental cursor exists — the
`updateddate=gt(...)` cutoff is doing the scoping. The side effect is that
a small number of vertical-well production rows can land in
`raw_enverus.production` whenever Enverus updates a vertical well.

Run this periodically (weekly is a reasonable cadence) to scrub them out.
The query is idempotent — running it twice does nothing the second time.

Semantics: deletes production rows whose `api_uwi_unformatted` (wellbore)
matches at least one row in `raw_enverus.wells` AND every matching wells
row has `trajectory = 'VERTICAL'`. Production rows for wellbores with at
least one non-vertical completion (HORIZONTAL, DIRECTIONAL, or
UNDETERMINED/NULL) are preserved.

Run as a module:
    python -m scripts.cleanup_vertical_production
"""

from __future__ import annotations

import logging

from etl.db import get_connection, log_etl_run

logger = logging.getLogger(__name__)

# Wellbores in `raw_enverus.wells` whose every completion-event row has
# trajectory='VERTICAL' are the ones whose production we don't want. The
# IN-subquery returns only those wellbores. Wellbores with mixed
# trajectories or NULL trajectories are left alone (HAVING bool_and(...)
# on a NULL trajectory yields NULL, which fails the HAVING).
DELETE_VERTICAL_PRODUCTION_SQL = """
DELETE FROM raw_enverus.production
WHERE api_uwi_unformatted IN (
    SELECT api_uwi_unformatted
      FROM raw_enverus.wells
     WHERE api_uwi_unformatted IS NOT NULL
     GROUP BY api_uwi_unformatted
    HAVING bool_and(trajectory = 'VERTICAL')
)
"""


def main() -> int:
    """Delete vertical-only-wellbore production rows. Returns rows deleted."""
    with log_etl_run("enverus", "production_vertical_cleanup") as run:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(DELETE_VERTICAL_PRODUCTION_SQL)
                deleted = cur.rowcount
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        run.rows_deleted = deleted
        logger.info(
            "Deleted %d vertical-only-wellbore production rows", deleted
        )
        return deleted


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
