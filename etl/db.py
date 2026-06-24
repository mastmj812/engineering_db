"""Database connection helpers, ETL run logging, and bulk-upsert utilities.

This module is the single point of contact between the ETL code and PostgreSQL.
Every pull script should:
    1. open an `log_etl_run(...)` context manager,
    2. obtain a connection via `get_connection()`,
    3. call `bulk_upsert(...)` to land rows,
    4. let the context manager record success/failure to `meta.etl_log`.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import quote

import psycopg
from dotenv import load_dotenv
from psycopg import Connection as PGConnection
from psycopg import sql
from sqlalchemy import Engine, create_engine

load_dotenv()

logger = logging.getLogger(__name__)


def _required_env(name: str) -> str:
    """Return an environment variable or raise if missing/empty."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return value


def _db_kwargs() -> dict[str, str]:
    """Collect DB connection parameters from environment variables.

    Beyond host/port/db/user/password, this carries SSL and TCP-keepalive
    settings so the ETL connects reliably to a managed Postgres endpoint
    (e.g. Supabase) as well as a local server:
      - `sslmode` (env DB_SSLMODE, default 'prefer'; set 'require' for Supabase).
      - keepalives so a long, quiet statement such as curated.refresh_all()
        isn't dropped by the connection pooler / NAT during silent periods.
    """
    return {
        "host": _required_env("DB_HOST"),
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": _required_env("DB_NAME"),
        "user": _required_env("DB_USER"),
        "password": os.getenv("DB_PASSWORD", ""),
        "sslmode": os.getenv("DB_SSLMODE", "prefer"),
        "connect_timeout": os.getenv("DB_CONNECT_TIMEOUT", "30"),
        "keepalives": "1",
        "keepalives_idle": "30",
        "keepalives_interval": "10",
        "keepalives_count": "5",
    }


# Applied to every new connection. statement_timeout=0 overrides Supabase's
# 2-minute platform default — which the pooler won't let us change via ALTER
# ROLE or startup options — so large COPYs and curated.refresh_all() can run.
# search_path includes `extensions` so PostGIS (geometry / ST_*) resolves; on
# Supabase, PostGIS lives in the extensions schema. Both are harmless locally.
_SESSION_SETTINGS: tuple[str, ...] = (
    "SET statement_timeout = 0",
    "SET search_path TO public, extensions",
)


def _apply_session_settings(conn: PGConnection) -> None:
    """Apply per-session GUCs (statement_timeout, search_path) and commit."""
    with conn.cursor() as cur:
        for stmt in _SESSION_SETTINGS:
            cur.execute(stmt)
    conn.commit()


def get_engine() -> Engine:
    """Return a SQLAlchemy engine built from `.env` credentials.

    Uses the psycopg (v3) driver, `pool_pre_ping=True` to recycle stale
    connections, and SSL + keepalives via connect_args. The password is
    URL-encoded so special characters in managed-DB passwords don't break the
    URL.
    """
    kw = _db_kwargs()
    url = (
        f"postgresql+psycopg://{kw['user']}:{quote(kw['password'], safe='')}"
        f"@{kw['host']}:{kw['port']}/{kw['dbname']}"
    )
    connect_args = {
        "sslmode": kw["sslmode"],
        "connect_timeout": int(kw["connect_timeout"]),
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
    return create_engine(
        url, pool_pre_ping=True, future=True, connect_args=connect_args
    )


def get_connection() -> PGConnection:
    """Return a raw psycopg (v3) connection with ETL session settings applied.

    Use this when you need `cursor.executemany()` for bulk upserts or COPY;
    SQLAlchemy is fine for everything else.
    """
    conn = psycopg.connect(**_db_kwargs())
    _apply_session_settings(conn)
    return conn


@contextmanager
def log_etl_run(source: str, table_name: str) -> Iterator["EtlRunHandle"]:
    """Context manager that records an ETL run to `meta.etl_log`.

    On entry, inserts a row with status='running' and returns a handle the
    caller can use to report `rows_inserted`. On exit, updates the row with
    `run_finished_at`, final status, row count, and (on failure) the
    exception message; the exception is then re-raised.

    Example:
        with log_etl_run("enverus", "wells") as run:
            ...
            run.rows_inserted = n
    """
    handle = EtlRunHandle()
    conn = get_connection()
    run_id: int | None = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.etl_log (source, table_name, run_started_at, status)
                VALUES (%s, %s, NOW(), 'running')
                RETURNING etl_log_id
                """,
                (source, table_name),
            )
            row = cur.fetchone()
            run_id = row[0] if row else None
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    try:
        yield handle
    except Exception as exc:
        logger.exception("ETL run failed: source=%s table=%s", source, table_name)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE meta.etl_log
                       SET run_finished_at = NOW(),
                           status = 'failed',
                           rows_inserted = %s,
                           rows_deleted = %s,
                           error_message = %s
                     WHERE etl_log_id = %s
                    """,
                    (handle.rows_inserted, handle.rows_deleted, str(exc), run_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Failed to record ETL failure in meta.etl_log")
        finally:
            conn.close()
        raise
    else:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE meta.etl_log
                       SET run_finished_at = NOW(),
                           status = 'success',
                           rows_inserted = %s,
                           rows_deleted = %s
                     WHERE etl_log_id = %s
                    """,
                    (handle.rows_inserted, handle.rows_deleted, run_id),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            logger.exception("Failed to record ETL success in meta.etl_log")
            raise
        finally:
            conn.close()


class EtlRunHandle:
    """Mutable handle yielded by `log_etl_run` so callers can record row counts.

    `rows_inserted` is the canonical counter for ingest steps. `rows_deleted`
    is reserved for cleanup-style steps that scrub rows out. Both land in
    their respective columns in `meta.etl_log`.
    """

    def __init__(self) -> None:
        self.rows_inserted: int = 0
        self.rows_deleted: int = 0


def settle(seconds: int | None = None) -> int:
    """Give a small managed instance a moment to flush before the next
    memory-heavy step: a best-effort CHECKPOINT (skipped if the role lacks the
    privilege) plus a short pause so the background writer/checkpointer can
    drain dirty buffers. Duration via ETL_SETTLE_SECONDS (default 20; 0 = off).
    Returns the seconds slept (so it can be used as a run_daily step)."""
    secs = int(os.getenv("ETL_SETTLE_SECONDS", "20")) if seconds is None else seconds
    if secs <= 0:
        return 0
    try:
        conn = get_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("CHECKPOINT")
        except Exception:
            logger.debug("CHECKPOINT unavailable; relying on background flush", exc_info=True)
        finally:
            conn.close()
    except Exception:
        logger.debug("settle: checkpoint connection failed", exc_info=True)
    time.sleep(secs)
    return secs


# Curated materialized views in dependency-refresh order (mirrors what
# curated.refresh_all() does internally). refresh_curated() refreshes them one
# at a time rather than via the single refresh_all() call.
_CURATED_MATVIEWS: tuple[str, ...] = (
    "curated.wells",
    "curated.formation_blueox",
    "curated.production",
    "curated.production_normalized",
    "curated.type_curve_cohorts",
    "curated.production_forecast",
    "curated.intel_locations",
)


def refresh_curated() -> None:
    """Refresh the curated materialized views CONCURRENTLY, one at a time, in
    dependency order, with a settle between each.

    Refreshing individually (each in its own autocommit session) keeps the peak
    memory footprint lower than a single curated.refresh_all() call — important
    on a small managed instance — and means a failure part-way still leaves the
    earlier matviews refreshed. CONCURRENTLY can't run inside a transaction
    block, hence autocommit.
    """
    n = len(_CURATED_MATVIEWS)
    for i, mv in enumerate(_CURATED_MATVIEWS):
        conn = get_connection()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}")
            logger.info("refreshed %s (%d/%d)", mv, i + 1, n)
        except Exception:
            logger.exception("failed refreshing %s (%d/%d)", mv, i + 1, n)
            raise
        finally:
            conn.close()
        if i < n - 1:
            settle()
    logger.info("curated refresh complete (%d matviews, individually)", n)


def bulk_upsert(
    conn: PGConnection,
    schema: str,
    table: str,
    rows: Sequence[Mapping[str, Any]],
    conflict_cols: Sequence[str],
    update_cols: Sequence[str],
) -> int:
    """Bulk INSERT ... ON CONFLICT DO UPDATE using psycopg3's `executemany`.

    psycopg3's `executemany` is genuinely fast (it pipelines the statements
    over the wire), so we don't need psycopg2's `execute_values` workaround.

    Args:
        conn: Open psycopg (v3) connection. Caller controls commit/rollback.
        schema: Target schema name. Composed via `sql.Identifier`, so safe.
        table: Target table name. Composed via `sql.Identifier`, so safe.
        rows: Sequence of dict-like rows. Column order is derived from the
            first row's keys; every row must share that key set.
        conflict_cols: Columns forming the ON CONFLICT target.
        update_cols: Columns to overwrite on conflict.

    Returns:
        Number of rows passed to the statement.
    """
    if not rows:
        logger.info("bulk_upsert: no rows for %s.%s; skipping", schema, table)
        return 0

    columns: list[str] = list(rows[0].keys())
    values: list[tuple[Any, ...]] = [tuple(row[c] for c in columns) for row in rows]

    stmt = sql.SQL(
        "INSERT INTO {schema}.{table} ({cols}) VALUES ({placeholders}) "
        "ON CONFLICT ({conflict}) DO UPDATE SET {set_clause}"
    ).format(
        schema=sql.Identifier(schema),
        table=sql.Identifier(table),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        conflict=sql.SQL(", ").join(sql.Identifier(c) for c in conflict_cols),
        set_clause=sql.SQL(", ").join(
            sql.SQL("{col} = EXCLUDED.{col}").format(col=sql.Identifier(c))
            for c in update_cols
        ),
    )

    with conn.cursor() as cur:
        cur.executemany(stmt, values)

    logger.info("bulk_upsert: %d rows -> %s.%s", len(values), schema, table)
    return len(values)


def iter_chunks(items: Iterable[Any], size: int) -> Iterator[list[Any]]:
    """Yield successive `size`-length chunks from an iterable.

    Useful for chunking API page results before handing them to `bulk_upsert`.
    """
    chunk: list[Any] = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
