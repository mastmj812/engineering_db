"""COPY Novi bulk TSV files into `raw_novi.*` tables.

Strategy: TRUNCATE each target raw table then COPY the full TSV. Simple and
correct for our use case because Novi's SDK has already merged diffs on
disk — the TSV always represents the current state of that table.

The MVP table list below is intentionally small; expand it once the
curated layer needs more sources.

Run as a module:
    python -m etl.novi.load
"""

from __future__ import annotations

import logging
from pathlib import Path

from etl.db import get_connection, log_etl_run

logger = logging.getLogger(__name__)

# Load order matters when downstream FKs are added. Wells is the parent
# (keyed on API10); WellMonths, WellDetails, and WellSpacing all reference
# it. Keep Wells first.
MVP_TABLES: list[str] = ["Wells", "WellMonths", "WellDetails", "WellSpacing"]


def load_table(bulk_dir: Path, table_name: str) -> int:
    """COPY a single Novi TSV into `raw_novi."<TableName>"`.

    Args:
        bulk_dir: Directory containing Novi's `Database/<Table>.tsv` files
            (the path returned by `etl.novi.sync.sync_bulk()`).
        table_name: Novi table name, used both for the TSV filename and the
            quoted target table identifier.

    Returns:
        Row count in the target table after the COPY (also recorded in
        `meta.etl_log`).
    """
    tsv_path = bulk_dir / "Database" / f"{table_name}.tsv"
    if not tsv_path.exists():
        raise FileNotFoundError(f"Expected TSV missing: {tsv_path}")

    with log_etl_run("novi", table_name) as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(f'TRUNCATE raw_novi."{table_name}"')
            with open(tsv_path, "r", encoding="utf-8") as f:
                # The generated DDL adds an `ingested_at` column to every
                # raw_novi table that the TSV does not have. Pass an explicit
                # column list to COPY so PostgreSQL fills only the columns the
                # TSV actually carries; `ingested_at` (and any other defaulted
                # columns) take their DEFAULT.
                header_line = f.readline().rstrip("\r\n")
                if not header_line:
                    raise RuntimeError(f"TSV is empty: {tsv_path}")
                columns = header_line.split("\t")
                quoted_cols = ", ".join(f'"{c}"' for c in columns)
                f.seek(0)
                copy_sql = (
                    f'COPY raw_novi."{table_name}" ({quoted_cols}) '
                    f"FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', HEADER)"
                )
                with cur.copy(copy_sql) as copy:
                    while data := f.read(65536):
                        copy.write(data)
            cur.execute(f'SELECT COUNT(*) FROM raw_novi."{table_name}"')
            row = cur.fetchone()
            row_count = int(row[0]) if row else 0
            conn.commit()
        run.rows_inserted = row_count
    logger.info("Novi %s: %d rows loaded", table_name, row_count)
    return row_count


def load_all(bulk_dir: Path) -> dict[str, int]:
    """Load every MVP table from `bulk_dir`; returns {table: row_count}."""
    return {t: load_table(bulk_dir, t) for t in MVP_TABLES}


def main() -> int:
    """CLI entry point.

    Pass `--bulk-dir <path>` to use an already-synced tree, or omit it to
    call `etl.novi.sync.sync_bulk()` first (which is a near-no-op when
    the on-disk data is current).
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="COPY Novi TSVs into raw_novi.* tables."
    )
    parser.add_argument(
        "--bulk-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing Database/<Table>.tsv. If omitted, "
            "etl.novi.sync.sync_bulk() is called to locate it."
        ),
    )
    args = parser.parse_args()

    if args.bulk_dir is None:
        from etl.novi.sync import sync_bulk

        bulk_dir = sync_bulk()
    else:
        bulk_dir = args.bulk_dir

    results = load_all(bulk_dir)
    total = sum(results.values())
    for table, n in results.items():
        print(f"  {table:20s} {n:>12d} rows")
    print(f"  {'TOTAL':20s} {total:>12d} rows")
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
