"""Thin wrapper: pull Enverus `wells` via the generic `pull_dataset()`.

Run as a module:
    python -m etl.enverus.pull_wells
"""

from __future__ import annotations

import logging

from etl.enverus.pull import pull_dataset

# Confirmed against sql/03_raw_enverus_ddl.sql: wells has a composite PK on
# (wellid, completionid) — one row per completion event. Note these are
# lowercase to match Postgres's case-folded storage of unquoted columns.
CONFLICT_COLS: list[str] = ["wellid", "completionid"]

# Scope to the entire Permian Basin via Enverus's `ENVRegion` field. The
# narrower `ENVBasin` field splits the Permian into 'Midland', 'Delaware',
# and 'Permian Other' — using ENVRegion='Permian' captures all three in
# one filter.
PERMIAN_FILTERS: dict[str, str] = {
    "envregion": "PERMIAN",
}


def main() -> int:
    """Pull Enverus wells (Permian scope); returns rows upserted."""
    return pull_dataset(
        "wells",
        conflict_cols=CONFLICT_COLS,
        extra_filters=PERMIAN_FILTERS,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
