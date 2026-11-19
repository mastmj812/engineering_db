"""Pull Novi v4 from Snowflake and write it into v3-shaped tables.

Two strategies, mirroring `etl/novi/load.py`:

- **Header tables** (Wells, WellDetails, WellSpacing): the whole table every run, replaced
  inside ONE transaction (TRUNCATE + COPY + commit), so a failed pull leaves the old rows.
- **Child tables** (WellMonths, ForecastWellMonths, DirectionalSurveys): a per-well census
  (row count + newest stamp) is taken on both sides. A well whose census differs is re-pulled
  whole; a well that left the share is deleted. v4 has no deletion marker, so this key
  comparison is what finds deletions (it is also how Novi builds its own diff files).

The target schema is a parameter. Anything other than `raw_novi` is a side-by-side copy and
logs under a label that cannot trip the `production_forecast` refresh gate
(`etl/db.py`: `LIKE 'ForecastWellMonths%'`).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from etl.db import get_connection, log_etl_run
from etl.novi_v4 import queries as q

logger = logging.getLogger(__name__)

LIVE_SCHEMA = "raw_novi"

#: Wells per Snowflake pull when re-pulling changed wells (ids are inlined in the SQL).
WELL_BATCH = 2000
#: Above this share of wells changed, one unfiltered pull is cheaper than batches.
FULL_PULL_SHARE = 0.30
#: A header pull smaller than this share of the current table is refused.
MIN_HEADER_SHARE = 0.90
_FETCH = 50_000
_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

Census = dict[str, tuple[int, datetime | None]]


def etl_label(schema: str, table: str) -> str:
    """`meta.etl_log.table_name`. On the live schema the label starts with the table name, as
    the v3 loader's does, so the `ForecastWellMonths%` gate keeps firing. On a side-by-side
    schema it must NOT start with it, or a scratch load would force a production_forecast
    rebuild on the next nightly."""
    return f"{table} (v4)" if schema == LIVE_SCHEMA else f"v4 {schema}.{table}"


def breaker_limit(n_wells: int) -> int:
    """Wells that may disappear in one run before the load refuses: max(200, 1 %)."""
    return max(200, n_wells // 100)


def _naive_utc(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts.replace(microsecond=(ts.microsecond // 1000) * 1000)


def diff_census(remote: Census, local: Census) -> tuple[list[str], list[str]]:
    """(wells to re-pull, wells to delete). A well is re-pulled when it is new, its row count
    differs, or its newest stamp differs in either direction (to the millisecond)."""
    changed = sorted(
        a for a, (n, ts) in remote.items()
        if a not in local or local[a][0] != n or _naive_utc(local[a][1]) != _naive_utc(ts)
    )
    gone = sorted(a for a in local if a not in remote)
    return changed, gone


def plan_pull(n_changed: int, n_remote: int) -> str:
    """'none', 'batches' or 'full'."""
    if n_changed == 0:
        return "none"
    return "full" if n_changed > FULL_PULL_SHARE * max(n_remote, 1) else "batches"


def check_breaker(table: str, gone: int, n_local: int, allow: bool) -> None:
    limit = breaker_limit(n_local)
    if n_local and gone > limit and not allow:
        raise RuntimeError(
            f"{table}: {gone} wells would be deleted (limit {limit} of {n_local}); refusing. "
            f"Check the share's scope, then re-run with --allow-breaker if it is real."
        )


def check_header_rows(table: str, pulled: int, before: int, allow: bool) -> None:
    if pulled == 0:
        raise RuntimeError(f"{table}: Snowflake returned no rows; refusing to empty the table")
    if before and pulled < MIN_HEADER_SHARE * before and not allow:
        raise RuntimeError(
            f"{table}: pulled {pulled} rows against {before} held "
            f"(under {MIN_HEADER_SHARE:.0%}); refusing. Re-run with --allow-breaker if it is real."
        )


def _check_schema(schema: str) -> str:
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"bad schema name: {schema!r}")
    return schema


def _stream(sf: Any, sql: str) -> Iterator[tuple[list[str], list[tuple]]]:
    """Yield (column names, rows) batches of a Snowflake query."""
    with sf.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        while rows := cur.fetchmany(_FETCH):
            yield cols, rows


def _copy(sf: Any, sql: str, cur: Any, schema: str, table: str) -> int:
    """COPY a Snowflake result set into `schema."table"` on `cur`. Does not commit."""
    n = 0
    copy = None
    try:
        for cols, rows in _stream(sf, sql):
            if copy is None:
                quoted = ", ".join(f'"{c}"' for c in cols)
                copy = cur.copy(f'COPY {schema}."{table}" ({quoted}) FROM STDIN')
                copy.__enter__()
            for r in rows:
                copy.write_row(r)
            n += len(rows)
    except BaseException as exc:
        if copy is not None:
            copy.__exit__(type(exc), exc, exc.__traceback__)
        raise
    if copy is not None:
        copy.__exit__(None, None, None)
    return n


def load_header(sf: Any, schema: str, table: str, *, allow_breaker: bool = False) -> int:
    """Replace a header table with the current v4 rows, atomically."""
    schema = _check_schema(schema)
    builder, _ = q.HEADER_TABLES[table]
    with log_etl_run("novi", etl_label(schema, table)) as run:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM {schema}."{table}"')
            before = int(cur.fetchone()[0])
            cur.execute(f'TRUNCATE {schema}."{table}"')
            n = _copy(sf, builder(), cur, schema, table)
            check_header_rows(table, n, before, allow_breaker)  # raises -> rollback
            conn.commit()
        run.rows_inserted = n
    logger.info("Novi v4 %s.%s: %d rows (replaced %d)", schema, table, n, before)
    return n


def remote_census(sf: Any, table: str) -> Census:
    with sf.cursor() as cur:
        cur.execute(q.census_sql(table))
        return {str(a): (int(n), ts) for a, n, ts in cur.fetchall()}


def local_census(schema: str, table: str) -> Census:
    schema = _check_schema(schema)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(f'SELECT "API10", count(*), max("ModifiedAt") FROM {schema}."{table}" GROUP BY 1')
        out = {str(a).strip(): (int(n), ts) for a, n, ts in cur.fetchall()}
        conn.commit()
    return out


def sync_child(
    sf: Any,
    schema: str,
    table: str,
    *,
    full: bool = False,
    allow_breaker: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Bring a child table in line with v4. Returns what was (or, on `dry_run`, would be) done."""
    schema = _check_schema(schema)
    builder, _ = q.CHILD_TABLES[table]
    remote = remote_census(sf, table)
    if not remote:
        raise RuntimeError(f"{table}: empty census from Snowflake; refusing to touch the table")
    local = local_census(schema, table)
    changed, gone = diff_census(remote, local)
    mode = "full" if full or not local else plan_pull(len(changed), len(remote))
    out: dict[str, Any] = {
        "table": table, "mode": mode, "wells_remote": len(remote), "wells_local": len(local),
        "wells_changed": len(changed), "wells_gone": len(gone),
        "rows_remote": sum(n for n, _ in remote.values()), "rows_local": sum(n for n, _ in local.values()),
        "rows_inserted": 0, "rows_deleted": 0,
    }
    out["breaker"] = bool(local) and len(gone) > breaker_limit(len(local))
    if dry_run:
        return out  # a dry run reports a tripped breaker instead of raising
    check_breaker(table, len(gone), len(local), allow_breaker)
    if mode == "none" and not gone:
        return out

    with log_etl_run("novi", etl_label(schema, table)) as run:
        if mode == "full":
            with get_connection() as conn, conn.cursor() as cur:
                cur.execute(f'TRUNCATE {schema}."{table}"')
                out["rows_inserted"] = _copy(sf, builder(None), cur, schema, table)
                if out["rows_inserted"] == 0:
                    raise RuntimeError(f"{table}: full pull returned no rows; rolled back")
                conn.commit()
            out["rows_deleted"] = out["rows_local"]
        else:
            for i in range(0, len(changed), WELL_BATCH):
                batch = changed[i:i + WELL_BATCH]
                with get_connection() as conn, conn.cursor() as cur:
                    cur.execute(f'DELETE FROM {schema}."{table}" WHERE "API10" = ANY(%s)', (batch,))
                    out["rows_deleted"] += cur.rowcount
                    out["rows_inserted"] += _copy(sf, builder(batch), cur, schema, table)
                    conn.commit()
            if gone:
                with get_connection() as conn, conn.cursor() as cur:
                    cur.execute(f'DELETE FROM {schema}."{table}" WHERE "API10" = ANY(%s)', (gone,))
                    out["rows_deleted"] += cur.rowcount
                    conn.commit()
        run.rows_inserted = out["rows_inserted"]
        run.rows_deleted = out["rows_deleted"]
    logger.info(
        "Novi v4 %s.%s (%s): %d wells re-pulled, %d wells gone, %d rows in, %d rows out",
        schema, table, mode, len(changed), len(gone), out["rows_inserted"], out["rows_deleted"],
    )
    return out
