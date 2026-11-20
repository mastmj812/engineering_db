"""CLI for the Novi v4 loader.

    python -m etl.novi_v4.load --compare                    # read-only diff against raw_novi
    python -m etl.novi_v4.load --schema raw_novi_v4 --dry-run   # census only, writes nothing
    python -m etl.novi_v4.load --schema raw_novi_v4         # load the side-by-side copy (sql/75)
    python -m etl.novi_v4.load --schema raw_novi --confirm-live # cutover: write the live tables

The nightly (`scripts/run_daily.py`) calls `nightly_load()` only when `NOVI_SOURCE=v4`; the
default is v3 (`etl/novi/load.py`). From the CLI, writing to `raw_novi` needs `--confirm-live`.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from etl.intel_sf.client import get_sf_connection
from etl.novi_v4 import compare, sync
from etl.novi_v4 import queries as q

logger = logging.getLogger(__name__)

# Wells first, as in etl/novi/load.py MVP_TABLES.
TABLES = ["Wells", "WellMonths", "WellDetails", "WellSpacing", "ForecastWellMonths", "DirectionalSurveys"]


def share_run_id(sf: Any) -> str | None:
    """Newest full-build run id on the share, e.g. '20261120_100520' (UTC). The share builds on
    weekdays around 10:05 UTC; a night that loads an old run id loaded yesterday's data."""
    with sf.cursor() as cur:
        cur.execute(f"SELECT MAX(RUN_ID) FROM {q.DB}.DOWNLOADS_FULL")
        row = cur.fetchone()
    return None if row is None or row[0] is None else str(row[0])


def nightly_load() -> int:
    """The nightly's Novi step on v4: bring the six live `raw_novi` tables in line with the
    share. Returns rows written. A table that fails (a tripped breaker included) does not stop
    the others; the step then fails with every table's error, and the failed table keeps its
    previous rows."""
    sf = get_sf_connection()
    rows, errors = 0, []
    try:
        logger.info("Novi v4 share run: %s", share_run_id(sf))
        for t in TABLES:
            try:
                if t in q.HEADER_TABLES:
                    rows += sync.load_header(sf, sync.LIVE_SCHEMA, t)
                else:
                    rows += sync.sync_child(sf, sync.LIVE_SCHEMA, t)["rows_inserted"]
            except Exception as exc:
                logger.exception("Novi v4 %s failed", t)
                errors.append(f"{t}: {exc}")
    finally:
        sf.close()
    if errors:
        raise RuntimeError("Novi v4 load failed for " + "; ".join(errors))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Load Novi v4 (Snowflake) into v3-shaped tables")
    ap.add_argument("--schema", default="raw_novi_v4", help="target schema (default: the side-by-side copy)")
    ap.add_argument("--tables", nargs="+", choices=TABLES, default=TABLES)
    ap.add_argument("--full", action="store_true", help="child tables: one full pull instead of the census diff")
    ap.add_argument("--dry-run", action="store_true", help="child tables: census and plan only; header tables skipped")
    ap.add_argument("--allow-breaker", action="store_true", help="accept a large drop in wells or header rows")
    ap.add_argument("--confirm-live", action="store_true", help="required to write schema raw_novi")
    ap.add_argument("--compare", action="store_true", help="read-only diff of v4-shaped rows against raw_novi")
    ap.add_argument("--diff", action="store_true", help="read-only full diff of --schema against raw_novi, inside Postgres")
    ap.add_argument("--sample-every", type=int, default=26, help="--compare: every k-th producing well for child tables")
    a = ap.parse_args(argv)

    if a.schema == sync.LIVE_SCHEMA and not (a.confirm_live or a.dry_run or a.compare):
        ap.error("writing raw_novi needs --confirm-live")
    if a.diff:
        from etl.novi_v4 import diff

        for t in a.tables:
            print(diff.format_diff(t, diff.diff_table(a.schema, t)), flush=True)
        return 0

    sf = get_sf_connection()
    try:
        if a.compare:
            wells = compare.sample_wells(a.sample_every)
            print(f"child-table sample: {len(wells):,} wells (every {a.sample_every}th producing well)")
            for t in a.tables:
                print(compare.format_report(t, compare.compare_table(sf, t, wells)), flush=True)
            return 0
        for t in a.tables:
            if t in q.HEADER_TABLES:
                if a.dry_run:
                    continue
                n = sync.load_header(sf, a.schema, t, allow_breaker=a.allow_breaker)
                print(f"  {t:20s} {n:>12,d} rows (replaced)")
            else:
                r = sync.sync_child(sf, a.schema, t, full=a.full, allow_breaker=a.allow_breaker, dry_run=a.dry_run)
                print(f"  {t:20s} mode={r['mode']:8s} wells remote={r['wells_remote']:,} local={r['wells_local']:,} "
                      f"changed={r['wells_changed']:,} gone={r['wells_gone']:,}  rows remote={r['rows_remote']:,} "
                      f"local={r['rows_local']:,}  in={r['rows_inserted']:,} out={r['rows_deleted']:,}"
                      + ("  BREAKER (needs --allow-breaker)" if r["breaker"] else ""), flush=True)
    finally:
        sf.close()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(main())
