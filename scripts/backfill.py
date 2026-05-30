"""One-time historical backfill of a single source/table.

This is *not* the daily pipeline — `run_daily.py` handles incremental
loads. Use this when you need to (re)load a wide date range, e.g. after
DDL changes or when bringing a new source online.

Per-source semantics:

- **Enverus production** (the high-value case): pulls every Permian
  production row whose `ProducingMonth` falls in
  ``[--start-date, --end-date]``, bypassing the daily ``updateddate``
  incremental cursor. Both date flags are required. Reuses the chunked
  ``api_uwi_unformatted`` filter from ``pull_production.py`` so only
  non-vertical wellbores are pulled.

- **Enverus wells**: full non-incremental pull. Wells has no temporal
  column to bound on, so ``--start-date`` / ``--end-date`` are ignored
  (with a warning). Cheap enough to just refetch the whole Permian
  universe.

- **Novi wells / production**: Novi's bulk-download model only ever
  exposes the current snapshot — there is no historical "as of" query.
  Backfill here means "re-COPY the on-disk TSVs into ``raw_novi.*``,"
  which is exactly what ``etl.novi.load.load_table`` already does.
  ``--start-date`` / ``--end-date`` are ignored.

Idempotency: both paths upsert (Enverus) or TRUNCATE+COPY (Novi), so
running the same backfill twice yields the same end state. After a
production backfill, the next daily run's incremental cutoff is the
backfill's ``run_finished_at`` — no boundary double-processing.

Examples:
    # Pull 15 years of Permian production
    python -m scripts.backfill --source enverus --table production \\
        --start-date 2010-01-01 --end-date 2025-12-31

    # Refetch the full Permian wells universe
    python -m scripts.backfill --source enverus --table wells

    # Re-COPY the current Novi WellMonths TSV into raw_novi.WellMonths
    python -m scripts.backfill --source novi --table production
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Maps the CLI's source-agnostic --table values onto Novi's PascalCase
# raw table names. Novi has no separate "production" table; WellMonths is
# the closest analog (one row per well per month).
_NOVI_TABLE_MAP: dict[str, str] = {
    "wells": "Wells",
    "production": "WellMonths",
}


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
        help=(
            "Earliest ProducingMonth (YYYY-MM-DD) to include. Required for "
            "`enverus production`; ignored otherwise."
        ),
    )
    parser.add_argument(
        "--end-date",
        type=_parse_date,
        required=False,
        help=(
            "Latest ProducingMonth (YYYY-MM-DD) to include. Required for "
            "`enverus production`; ignored otherwise."
        ),
    )
    return parser.parse_args(argv)


def _backfill_enverus_wells() -> int:
    """Full non-incremental pull of Permian wells. Returns rows upserted."""
    from etl.enverus.pull import pull_dataset
    from etl.enverus.pull_wells import CONFLICT_COLS, PERMIAN_FILTERS

    logger.info("Enverus wells backfill: non-incremental full pull")
    return pull_dataset(
        "wells",
        conflict_cols=CONFLICT_COLS,
        incremental=False,
        extra_filters=PERMIAN_FILTERS,
    )


def _backfill_enverus_production(start: date, end: date) -> int:
    """Pull Permian production for ProducingMonth in [start, end].

    Bypasses the ``updateddate`` incremental cursor and adds a
    ``producingmonth=between(...)`` filter. Otherwise identical to the
    daily ``pull_production`` path — same Permian scope, same chunked
    api_uwi filter to skip vertical wellbores.
    """
    from etl.enverus.pull import pull_dataset
    from etl.enverus.pull_production import (
        CONFLICT_COLS,
        PERMIAN_FILTERS,
        _non_vertical_api_uwi_unformatted,
    )

    api_uwis = _non_vertical_api_uwi_unformatted()
    if not api_uwis:
        raise RuntimeError(
            "No non-vertical api_uwi_unformatted in raw_enverus.wells; "
            "run `enverus wells` (incremental or backfill) first."
        )

    filters: dict[str, str] = {
        **PERMIAN_FILTERS,
        "producingmonth": f"between({start.isoformat()},{end.isoformat()})",
    }
    logger.info(
        "Enverus production backfill: %d wellbores, ProducingMonth %s to %s",
        len(api_uwis),
        start,
        end,
    )
    return pull_dataset(
        "production",
        conflict_cols=CONFLICT_COLS,
        incremental=False,
        extra_filters=filters,
        chunked_filter=("api_uwi_unformatted", api_uwis),
        chunk_size=250,
    )


def _backfill_novi(novi_table: str) -> int:
    """TRUNCATE+COPY a single Novi raw table from its on-disk TSV.

    Path resolution mirrors ``etl.novi.sync.sync_bulk`` — driven by the
    ``NOVI_SCOPE`` env var (defaults to ``us-horizontals``). Assumes the
    TSVs are already on disk; run ``python -m etl.novi.sync`` first if
    the local tree is stale or absent.
    """
    from etl.novi.load import load_table

    load_dotenv()
    scope = os.getenv("NOVI_SCOPE", "us-horizontals")
    bulk_dir = Path("data") / scope / "All basins" / "All subbasins"
    if not (bulk_dir / "Database" / f"{novi_table}.tsv").exists():
        raise FileNotFoundError(
            f"Expected TSV missing under {bulk_dir / 'Database'}; "
            "run `python -m etl.novi.sync` first."
        )

    logger.info(
        "Novi backfill: TRUNCATE+COPY raw_novi.%s from %s",
        novi_table,
        bulk_dir / "Database" / f"{novi_table}.tsv",
    )
    return load_table(bulk_dir, novi_table)


def main(argv: list[str] | None = None) -> int:
    """Dispatch the backfill to the right per-source path. Returns rows touched."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info(
        "backfill requested: source=%s table=%s start=%s end=%s",
        args.source,
        args.table,
        args.start_date,
        args.end_date,
    )

    if args.source == "enverus":
        if args.table == "wells":
            if args.start_date or args.end_date:
                logger.warning(
                    "--start-date/--end-date ignored: wells has no "
                    "ProducingMonth column to bound on."
                )
            return _backfill_enverus_wells()
        # enverus production
        if args.start_date is None or args.end_date is None:
            raise SystemExit(
                "enverus production backfill requires both --start-date "
                "and --end-date."
            )
        if args.start_date > args.end_date:
            raise SystemExit(
                f"--start-date ({args.start_date}) must be <= --end-date "
                f"({args.end_date})."
            )
        return _backfill_enverus_production(args.start_date, args.end_date)

    # source == "novi"
    if args.start_date or args.end_date:
        logger.warning(
            "--start-date/--end-date ignored: Novi exports only the "
            "current snapshot — no historical 'as of' query exists."
        )
    return _backfill_novi(_NOVI_TABLE_MAP[args.table])


if __name__ == "__main__":
    main()
