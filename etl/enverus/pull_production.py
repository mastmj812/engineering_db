"""Thin wrapper: pull Enverus `production` for non-vertical wells only.

Enverus's `production` dataset doesn't have a `trajectory` column to filter
on, so we restrict the pull at query time by reading the `wellid`s of wells
with at least one non-vertical completion event from `raw_enverus.wells`
and passing them through `pull_dataset`'s chunked filter. This skips
vertical-only-well production entirely (saves ~70% of rows in a typical
Permian pull).

Note: we use `api_uwi_unformatted` (10-digit wellbore identifier) rather
than `wellid` or `completionid` because those internal surrogate IDs are
not on Enverus's list of filterable columns for the production dataset
(confirmed via DAQueryException 2026-05-28 and the API docs screenshot).
Filterable per-well columns on production are: api_uwi_14_unformatted,
api_uwi_unformatted, productionid. We pick api_uwi_unformatted because it
keys to the wellbore — pulling production for the whole wellbore is the
right behavior even if a non-vertical well historically also had a
vertical perforation.

Run as a module:
    python -m etl.enverus.pull_production
"""

from __future__ import annotations

import logging

from etl.db import get_connection
from etl.enverus.pull import pull_dataset

logger = logging.getLogger(__name__)

# Confirmed against sql/03_raw_enverus_ddl.sql: production uses a single
# surrogate PK on `productionid`. `ProducingMonth` exists as a column but
# is not part of the PK. Lowercase to match Postgres's case-folded storage
# of unquoted columns.
CONFLICT_COLS: list[str] = ["productionid"]

# Same ENVRegion='PERMIAN' filter as pull_wells.py. Duplicated here
# intentionally (audit item #3 — centralize later if it spreads further).
PERMIAN_FILTERS: dict[str, str] = {
    "envregion": "PERMIAN",
}


def _non_vertical_api_uwi_unformatted() -> list[str]:
    """Read DISTINCT api_uwi_unformatted of wells with at least one
    non-vertical completion event from `raw_enverus.wells`.

    Includes HORIZONTAL, DIRECTIONAL, and UNDETERMINED (NULL trajectories
    too) — anything that isn't explicitly VERTICAL. Run after
    `pull_wells.main()` has populated `raw_enverus.wells`.

    Returns the 10-digit wellbore identifier as a list of strings (the
    column is TEXT in the DDL).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT api_uwi_unformatted
                  FROM raw_enverus.wells
                 WHERE (trajectory IS NULL OR trajectory != 'VERTICAL')
                   AND api_uwi_unformatted IS NOT NULL
                """
            )
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main() -> int:
    """Pull Enverus production for non-vertical Permian wells only.

    Returns the number of rows upserted.
    """
    api_uwis = _non_vertical_api_uwi_unformatted()
    if not api_uwis:
        logger.warning(
            "No non-vertical api_uwi_unformatted values in raw_enverus.wells; "
            "run pull_wells first. Skipping."
        )
        return 0

    logger.info(
        "Enverus production: pulling for %d non-vertical wellbores",
        len(api_uwis),
    )
    return pull_dataset(
        "production",
        conflict_cols=CONFLICT_COLS,
        extra_filters=PERMIAN_FILTERS,
        chunked_filter=("api_uwi_unformatted", api_uwis),
        chunk_size=250,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
