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
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, Mapping, Sequence

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
    """Collect DB connection parameters from environment variables."""
    return {
        "host": _required_env("DB_HOST"),
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": _required_env("DB_NAME"),
        "user": _required_env("DB_USER"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


def get_engine() -> Engine:
    """Return a SQLAlchemy engine built from `.env` credentials.

    The engine uses the psycopg (v3) driver and `pool_pre_ping=True` so that
    stale connections get recycled transparently.
    """
    kw = _db_kwargs()
    url = (
        f"postgresql+psycopg://{kw['user']}:{kw['password']}"
        f"@{kw['host']}:{kw['port']}/{kw['dbname']}"
    )
    return create_engine(url, pool_pre_ping=True, future=True)


def get_connection() -> PGConnection:
    """Return a raw psycopg (v3) connection.

    Use this when you need `cursor.executemany()` for bulk upserts; SQLAlchemy
    is fine for everything else.
    """
    return psycopg.connect(**_db_kwargs())


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
    is set by cleanup-style steps that scrub rows out (e.g.,
    `scripts/cleanup_vertical_production.py`). Both land in their
    respective columns in `meta.etl_log`.
    """

    def __init__(self) -> None:
        self.rows_inserted: int = 0
        self.rows_deleted: int = 0


def refresh_curated() -> None:
    """Execute `SELECT curated.refresh_all();` to rebuild curated views."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT curated.refresh_all();")
        conn.commit()
        logger.info("curated.refresh_all() completed")
    except Exception:
        conn.rollback()
        logger.exception("curated.refresh_all() failed")
        raise
    finally:
        conn.close()


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
