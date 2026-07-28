"""Load Novi bulk TSV files into `raw_novi.*` tables.

Two load strategies:

- **Full** (`load_table`): TRUNCATE then COPY the whole TSV. Simple; fine for
  the small tables (Wells / WellDetails / WellSpacing).

- **Incremental** (`load_table_incremental`): for the large time-series tables
  (`WellMonths`, `ForecastWellMonths`). Novi ships a full snapshot every sync
  but stamps `ModifiedAt` per change-batch, so most syncs change few/no rows.
  Rewriting all rows nightly (e.g. 22M for ForecastWellMonths) is wasteful and
  heavy enough to destabilise a managed Postgres (Supabase) instance. Instead we
  read the live `max(ModifiedAt)` watermark, stream the TSV, and UPSERT only the
  rows newer than the watermark — usually ~zero. Deletions are NOT detected here
  (forecasts/production aren't deleted in practice); run `full_reconcile_table()`
  on demand / periodically to catch deletions and any drift.

Run as a module:
    python -m etl.novi.load                     # nightly: incremental for big tables
    python -m etl.novi.load --full              # force full TRUNCATE+COPY for all
    python -m etl.novi.load --reconcile         # full staging+diff reconcile of big tables
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from etl.db import get_connection, log_etl_run

logger = logging.getLogger(__name__)

# Load order matters when downstream FKs are added. Wells is the parent
# (keyed on API10); WellMonths, WellDetails, WellSpacing, and
# ForecastWellMonths all reference it. Keep Wells first.
#
# ForecastWellMonths is a unified history + forecast time series — the
# IsForecasted boolean splits actuals from Novi's algorithmic forecast.
# Loaded so raw_novi mirrors the source exactly; the curated layer is where
# IsForecasted=TRUE filtering happens.
MVP_TABLES: list[str] = [
    "Wells",
    "WellMonths",
    "WellDetails",
    "WellSpacing",
    "ForecastWellMonths",
]

# Tables loaded incrementally (ModifiedAt watermark) instead of TRUNCATE+COPY.
# Maps table -> primary-key columns (the UPSERT conflict target).
_INCREMENTAL_KEYS: dict[str, list[str]] = {
    "WellMonths": ["API10", "Year", "Month"],
    "ForecastWellMonths": ["API10", "Date"],
}
_MODIFIED_COL = "ModifiedAt"


def _tsv_path(bulk_dir: Path, table_name: str) -> Path:
    p = bulk_dir / "Database" / f"{table_name}.tsv"
    if not p.exists():
        raise FileNotFoundError(f"Expected TSV missing: {p}")
    return p


def _read_header(tsv_path: Path) -> list[str]:
    """Return the TSV column names (first line, tab-split)."""
    with open(tsv_path, "r", encoding="utf-8") as f:
        header = f.readline().rstrip("\r\n")
    if not header:
        raise RuntimeError(f"TSV is empty: {tsv_path}")
    return header.split("\t")


def load_table(bulk_dir: Path, table_name: str) -> int:
    """Full load: TRUNCATE `raw_novi."<table>"` then COPY the whole TSV.

    Returns the row count after the COPY (also recorded in `meta.etl_log`).
    """
    tsv_path = _tsv_path(bulk_dir, table_name)
    with log_etl_run("novi", table_name) as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(f'TRUNCATE raw_novi."{table_name}"')
            with open(tsv_path, "r", encoding="utf-8") as f:
                # The generated DDL adds an `ingested_at` column the TSV lacks;
                # pass an explicit column list so it takes its DEFAULT.
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
    logger.info("Novi %s: %d rows loaded (full)", table_name, row_count)
    return row_count


def _upsert_newer(
    cur,
    table_name: str,
    columns: list[str],
    keys: list[str],
    tsv_path: Path,
    watermark: datetime,
) -> tuple[int, int]:
    """Stage TSV rows with ModifiedAt > watermark and UPSERT them onto `cur`.

    Filters client-side while streaming the TSV, so on a quiet sync ~zero rows
    reach the database. Does NOT commit — the caller controls the transaction
    (which also makes this testable via rollback). Returns (upserted, skipped),
    where `skipped` counts rows with an unparseable/empty ModifiedAt or a column
    count that doesn't match the header.
    """
    mod_idx = columns.index(_MODIFIED_COL)
    n_cols = len(columns)
    quoted = ", ".join(f'"{c}"' for c in columns)
    conflict = ", ".join(f'"{c}"' for c in keys)
    set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in columns if c not in keys)

    cur.execute("DROP TABLE IF EXISTS _stg_incr")
    cur.execute(
        f'CREATE TEMP TABLE _stg_incr (LIKE raw_novi."{table_name}" INCLUDING DEFAULTS) '
        f"ON COMMIT DROP"
    )
    copy_sql = f"COPY _stg_incr ({quoted}) FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t')"
    n_new = n_skip = 0
    with open(tsv_path, "r", encoding="utf-8") as f, cur.copy(copy_sql) as copy:
        f.readline()  # skip header
        for line in f:
            raw = line.rstrip("\n").rstrip("\r")
            if not raw:
                continue
            fields = raw.split("\t")
            if len(fields) != n_cols:
                n_skip += 1
                continue
            mod = fields[mod_idx]
            if not mod:
                n_skip += 1
                continue
            try:
                mdt = datetime.fromisoformat(mod)
            except ValueError:
                n_skip += 1
                continue
            if mdt > watermark:
                copy.write(line)  # pass the original CSV line straight through
                n_new += 1
    if n_new:
        cur.execute(
            f'INSERT INTO raw_novi."{table_name}" ({quoted}) '
            f"SELECT {quoted} FROM _stg_incr "
            f'ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}, "ingested_at" = now()'
        )
    return n_new, n_skip


def load_table_incremental(bulk_dir: Path, table_name: str) -> int:
    """Upsert only rows newer than the live max(ModifiedAt). First load (empty
    table) falls back to a full TRUNCATE+COPY. Returns rows upserted."""
    keys = _INCREMENTAL_KEYS[table_name]
    tsv_path = _tsv_path(bulk_dir, table_name)
    columns = _read_header(tsv_path)
    if _MODIFIED_COL not in columns:
        raise RuntimeError(
            f"{table_name} TSV has no {_MODIFIED_COL} column; cannot load incrementally"
        )

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f'SELECT max("{_MODIFIED_COL}") FROM raw_novi."{table_name}"')
        watermark = cur.fetchone()[0]
    if watermark is None:
        logger.info("Novi %s: empty table -> full load", table_name)
        return load_table(bulk_dir, table_name)

    with log_etl_run("novi", f"{table_name} (incremental)") as run:
        with get_connection() as conn, conn.cursor() as cur:
            n_new, n_skip = _upsert_newer(
                cur, table_name, columns, keys, tsv_path, watermark
            )
            conn.commit()
        run.rows_inserted = n_new
    if n_skip:
        logger.warning(
            "Novi %s incremental: skipped %d rows (bad column count / unparseable ModifiedAt)",
            table_name,
            n_skip,
        )
    logger.info(
        "Novi %s incremental: %d rows upserted (newer than %s)",
        table_name,
        n_new,
        watermark,
    )
    return n_new


def full_reconcile_table(bulk_dir: Path, table_name: str) -> dict[str, int]:
    """Full staging+diff reconcile: UPSERT every snapshot row and DELETE rows no
    longer present. Catches deletions/drift the incremental watermark misses.

    Loads the full snapshot into an UNLOGGED staging table (no WAL) and writes
    only the deltas to the live table, so it's far lighter than a TRUNCATE+COPY
    rewrite — but it still transfers the whole snapshot, so run it deliberately
    (on demand / periodically), not nightly. Returns {upserted, deleted}.
    """
    keys = _INCREMENTAL_KEYS[table_name]
    tsv_path = _tsv_path(bulk_dir, table_name)
    columns = _read_header(tsv_path)
    quoted = ", ".join(f'"{c}"' for c in columns)
    conflict = ", ".join(f'"{c}"' for c in keys)
    set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in columns if c not in keys)
    join_cond = " AND ".join(f'l."{k}" = s."{k}"' for k in keys)
    stg = "_recon_stg"

    with log_etl_run("novi", f"{table_name} (reconcile)") as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {stg}")
            cur.execute(
                f'CREATE UNLOGGED TABLE {stg} (LIKE raw_novi."{table_name}" INCLUDING DEFAULTS)'
            )
            copy_sql = (
                f"COPY {stg} ({quoted}) FROM STDIN "
                f"WITH (FORMAT CSV, DELIMITER E'\\t', HEADER)"
            )
            with open(tsv_path, "r", encoding="utf-8") as f, cur.copy(copy_sql) as copy:
                while data := f.read(65536):
                    copy.write(data)
            cur.execute(
                f'INSERT INTO raw_novi."{table_name}" ({quoted}) SELECT {quoted} FROM {stg} '
                f'ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}, "ingested_at" = now()'
            )
            upserted = cur.rowcount
            cur.execute(
                f'DELETE FROM raw_novi."{table_name}" l '
                f"WHERE NOT EXISTS (SELECT 1 FROM {stg} s WHERE {join_cond})"
            )
            deleted = cur.rowcount
            cur.execute(f"DROP TABLE {stg}")
            conn.commit()
        run.rows_inserted = upserted
        run.rows_deleted = deleted
    logger.info(
        "Novi %s reconcile: %d upserted, %d deleted", table_name, upserted, deleted
    )
    return {"upserted": upserted, "deleted": deleted}


# Column types the auto-add path will accept from Novi's shipped schema.
# Anything outside this list falls back to the manual sql/NN migration path.
_SAFE_TYPE_RE = re.compile(
    r"^(bool|date|text|uuid|int2|int4|int8|float4|float8"
    r"|numeric(\(\d+,\s*\d+\))?|varchar(\(\d+\))?"
    r"|timestamp(tz)?|timestamp with(out)? time zone)$"
)
_IDENT_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _shipped_column_types(bulk_dir: Path) -> dict[str, dict[str, str]]:
    """Parse Novi's shipped schema.postgres.sql into {table: {column: base_type}}.

    The base type is the declared type with NOT NULL / DEFAULT stripped —
    auto-added columns are always nullable (the raw layer is TRUNCATE+COPY'd
    nightly, so they are fully populated from the next load; sql/33 convention).
    """
    schema_path = bulk_dir / "schema.postgres.sql"
    if not schema_path.exists():
        return {}
    schema = schema_path.read_text(encoding="utf-8")
    out: dict[str, dict[str, str]] = {}
    for m in re.finditer(r'CREATE TABLE\s+"(\w+)"\s*\((.*?)\n\);', schema, re.S):
        cols: dict[str, str] = {}
        for line in m.group(2).splitlines():
            cm = re.match(r'\s*"(\w+)"\s+(.+?),?\s*$', line)
            if cm:
                base = re.sub(
                    r"\s+(NOT\s+NULL|NULL|DEFAULT\s+.*)$", "", cm.group(2), flags=re.I
                ).strip()
                cols[cm.group(1)] = base
        out[m.group(1)] = cols
    return out


def reconcile_schema_drift(bulk_dir: Path) -> dict[str, list[str]]:
    """Detect vendor schema drift up front and auto-apply additive columns.

    Novi adds columns to the bulk export without notice (IsSyntheticApi
    2026-07-24, LastRefracDate 2026-07-28). The COPY column list comes from
    the TSV header, so a missing column fails the load. Before any table is
    touched, compare every TSV header against the live raw_novi columns:

    - NEW column, declared in the shipped schema.postgres.sql with a
      whitelisted type -> ALTER TABLE ADD COLUMN IF NOT EXISTS, nullable,
      logged loudly. Returns {table: [added columns]}. Regenerate sql/02 and
      commit a numbered sql/NN mirror of the ALTER when convenient — the
      live DB is already correct.
    - NEW column absent from the shipped schema or with an unexpected
      type -> RuntimeError (manual sql/NN migration; sql/36 pattern).
    - Column REMOVED from the TSV -> RuntimeError. A vendor dropping a
      column is a contract change that needs eyes, not automation.
    """
    shipped = _shipped_column_types(bulk_dir)
    added: dict[str, list[str]] = {}
    problems: list[str] = []
    with get_connection() as conn, conn.cursor() as cur:
        for t in MVP_TABLES:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'raw_novi' AND table_name = %s",
                (t,),
            )
            live = {r[0] for r in cur.fetchall()}
            if not live:
                continue  # table not created yet; the load itself surfaces that
            header = _read_header(_tsv_path(bulk_dir, t))
            removed = live - set(header) - {"ingested_at"}
            if removed:
                problems.append(f"{t}: columns removed from export: {sorted(removed)}")
            for c in header:
                if c in live:
                    continue
                declared = shipped.get(t, {}).get(c)
                if declared is None:
                    problems.append(f"{t}.{c}: new in TSV but not in shipped schema")
                elif not _SAFE_TYPE_RE.match(declared) or not _IDENT_RE.match(c):
                    problems.append(f"{t}.{c}: unexpected declared type {declared!r}")
                else:
                    cur.execute(
                        f'ALTER TABLE raw_novi."{t}" '
                        f'ADD COLUMN IF NOT EXISTS "{c}" {declared}'
                    )
                    added.setdefault(t, []).append(c)
                    logger.warning(
                        "Novi schema drift: auto-added raw_novi.%s.%s (%s, nullable). "
                        "Regenerate sql/02 and commit a numbered ALTER to match.",
                        t,
                        c,
                        declared,
                    )
        conn.commit()
    if problems:
        raise RuntimeError(
            "Novi export drift needs manual review (" + "; ".join(problems) + "). "
            "Handle with a numbered sql/NN migration (sql/36 pattern) and "
            "regenerate sql/02 before loading."
        )
    return added


def load_all(bulk_dir: Path, *, force_full: bool = False) -> dict[str, int]:
    """Load every MVP table; incremental for the large tables (unless
    `force_full`), full TRUNCATE+COPY for the rest. Returns {table: rows}."""
    reconcile_schema_drift(bulk_dir)
    out: dict[str, int] = {}
    for t in MVP_TABLES:
        if t in _INCREMENTAL_KEYS and not force_full:
            out[t] = load_table_incremental(bulk_dir, t)
        else:
            out[t] = load_table(bulk_dir, t)
    return out


def reconcile_all(bulk_dir: Path) -> dict[str, dict[str, int]]:
    """Run `full_reconcile_table` for every incremental table."""
    return {t: full_reconcile_table(bulk_dir, t) for t in _INCREMENTAL_KEYS}


def main() -> int:
    """CLI entry point.

    Default: incremental load of the big tables + full load of the small ones.
    `--full` forces a full TRUNCATE+COPY of everything. `--reconcile` runs the
    staging+diff reconcile of the incremental tables (deliberate; off-peak).
    Pass `--bulk-dir <path>` to use an already-synced tree.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Load Novi TSVs into raw_novi.*")
    parser.add_argument("--bulk-dir", type=Path, default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--full", action="store_true", help="Force full TRUNCATE+COPY for all tables."
    )
    mode.add_argument(
        "--reconcile",
        action="store_true",
        help="Full staging+diff reconcile of the incremental tables (handles deletions).",
    )
    args = parser.parse_args()

    if args.bulk_dir is None:
        from etl.novi.sync import sync_bulk

        bulk_dir = sync_bulk()
    else:
        bulk_dir = args.bulk_dir

    if args.reconcile:
        results = reconcile_all(bulk_dir)
        for table, r in results.items():
            print(f"  {table:20s} upserted={r['upserted']:>10d}  deleted={r['deleted']:>8d}")
        return sum(r["upserted"] for r in results.values())

    results = load_all(bulk_dir, force_full=args.full)
    total = sum(results.values())
    for table, n in results.items():
        print(f"  {table:20s} {n:>12d} rows")
    print(f"  {'TOTAL':20s} {total:>12d} rows")
    return total


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
