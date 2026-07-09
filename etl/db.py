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
from datetime import datetime
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence, TypeVar
from urllib.parse import quote

import psycopg
from dotenv import load_dotenv
from psycopg import Connection as PGConnection
from psycopg import sql
from sqlalchemy import Engine, create_engine

load_dotenv()

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


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


def _open_connection() -> PGConnection:
    """One connection attempt (no retry): connect + apply session GUCs."""
    conn = psycopg.connect(**_db_kwargs())
    try:
        _apply_session_settings(conn)
    except Exception:
        conn.close()
        raise
    return conn


def _retry_on_conn_loss(fn: "Callable[[], _T]", *, what: str) -> "_T":
    """Call `fn()`, retrying on `psycopg.OperationalError` with exponential
    backoff. Covers a managed-Postgres restart/failover: the server refuses new
    connections (or drops an in-flight one) for tens of seconds, then recovers
    — exactly the `the database system is not accepting connections` /
    `AdminShutdown` window that fails a daily run mid-flight.

    Only connection-level `OperationalError`s are retried; anything else
    (programming errors, constraint violations) propagates immediately. Callers
    must therefore only wrap idempotent work — a fresh connect, or a
    `REFRESH MATERIALIZED VIEW CONCURRENTLY` — never a half-done multi-batch
    write. Tunable via env: DB_CONNECT_RETRIES (6), DB_CONNECT_RETRY_BASE (2s),
    DB_CONNECT_RETRY_MAX (30s).
    """
    attempts = int(os.getenv("DB_CONNECT_RETRIES", "6"))
    base = float(os.getenv("DB_CONNECT_RETRY_BASE", "2"))
    cap = float(os.getenv("DB_CONNECT_RETRY_MAX", "30"))
    last: psycopg.OperationalError | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except psycopg.OperationalError as exc:
            last = exc
            if i >= attempts:
                break
            delay = min(base * (2 ** (i - 1)), cap)
            logger.warning(
                "%s failed (attempt %d/%d): %s; retrying in %.0fs",
                what, i, attempts, exc, delay,
            )
            time.sleep(delay)
    assert last is not None
    logger.error("%s failed after %d attempts", what, attempts)
    raise last


def get_connection() -> PGConnection:
    """Return a raw psycopg (v3) connection with ETL session settings applied.

    Use this when you need `cursor.executemany()` for bulk upserts or COPY;
    SQLAlchemy is fine for everything else. The connect is retried with backoff
    so a brief Supabase restart/failover during the daily run is ridden out
    rather than failing the step instantly.
    """
    return _retry_on_conn_loss(_open_connection, what="db connect")


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


# settle() forces a CHECKPOINT before a memory-heavy step, but the Supabase
# `postgres` role isn't a superuser and (unless granted `pg_checkpoint`, PG15+)
# CHECKPOINT raises insufficient_privilege. Latch that so we warn ONCE and stop
# re-issuing a command the server logs as an error on every call. Reset each
# process, so a later `GRANT pg_checkpoint TO postgres` is picked up next run.
_checkpoint_unavailable = False


def settle(seconds: int | None = None) -> int:
    """Give a small managed instance a moment to flush before the next
    memory-heavy step: a best-effort CHECKPOINT (skipped if the role lacks the
    privilege) plus a short pause so the background writer/checkpointer can
    drain dirty buffers. Duration via ETL_SETTLE_SECONDS (default 20; 0 = off).
    Returns the seconds slept (so it can be used as a run_daily step)."""
    global _checkpoint_unavailable
    secs = int(os.getenv("ETL_SETTLE_SECONDS", "20")) if seconds is None else seconds
    if secs <= 0:
        return 0
    if not _checkpoint_unavailable:
        try:
            conn = get_connection()
            try:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("CHECKPOINT")
                logger.debug("settle: CHECKPOINT issued")
            finally:
                conn.close()
        except psycopg.errors.InsufficientPrivilege:
            _checkpoint_unavailable = True
            logger.warning(
                "settle(): CHECKPOINT denied for this role - forced flush is "
                "DISABLED; relying on the %ds pause + background writer. To "
                "enable it, GRANT pg_checkpoint TO the app role (see runbook).",
                secs,
            )
        except Exception:
            logger.warning(
                "settle: CHECKPOINT failed; relying on background flush",
                exc_info=True,
            )
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


# Matviews whose refresh is GATED on whether their source raw table changed
# since the matview's last successful refresh. Value is a LIKE pattern matched
# against meta.etl_log.table_name (covers both the "(incremental)" nightly load
# and the "(reconcile)" run). Only curated.production_forecast (~7 GB, built
# from raw_novi.ForecastWellMonths) is gated: it is the memory-heavy rebuild
# that OOMs a small managed instance, and ForecastWellMonths is a faithful
# change signal for it (a new well brings new forecast rows). The other matviews
# are small and/or have multi-table inputs, so they refresh every run.
_GATED_REFRESH: dict[str, str] = {
    "curated.production_forecast": "ForecastWellMonths%",
}


def _needs_refresh(
    last_refresh: datetime | None, last_source_change: datetime | None
) -> bool:
    """Pure gate decision: refresh a matview iff it has never been successfully
    refreshed, OR its source changed at/after the last successful refresh.

    Uses ``>=`` deliberately: a spurious extra refresh is safe (idempotent), a
    missed one leaves stale data — so ties break toward refreshing. Gating on
    last-*successful*-refresh (not "changed since last night") is what makes a
    failed refresh self-heal: the failure isn't recorded as success, so the
    source still reads as newer next run and the matview is rebuilt."""
    if last_refresh is None:
        return True
    return last_source_change is not None and last_source_change >= last_refresh


def _matview_is_stale(conn: PGConnection, matview: str, source_like: str) -> bool:
    """Read meta.etl_log for `matview`'s last successful refresh and its source's
    last change (rows inserted or deleted), then decide via _needs_refresh."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT max(run_finished_at) FROM meta.etl_log "
            "WHERE table_name = %s AND status = 'success'",
            (matview,),
        )
        last_refresh = cur.fetchone()[0]
        cur.execute(
            "SELECT max(run_finished_at) FROM meta.etl_log "
            "WHERE table_name LIKE %s AND status = 'success' "
            "AND (COALESCE(rows_inserted, 0) > 0 OR COALESCE(rows_deleted, 0) > 0)",
            (source_like,),
        )
        last_change = cur.fetchone()[0]
    return _needs_refresh(last_refresh, last_change)


def refresh_curated(*, force: bool = False) -> None:
    """Refresh the curated materialized views CONCURRENTLY, one at a time, in
    dependency order, with a settle between each.

    Refreshing individually (each in its own autocommit session) keeps the peak
    memory footprint lower than a single curated.refresh_all() call — important
    on a small managed instance — and means a failure part-way still leaves the
    earlier matviews refreshed. CONCURRENTLY can't run inside a transaction
    block, hence autocommit.

    Gated matviews (``_GATED_REFRESH``) are SKIPPED when their source raw table
    hasn't changed since the matview's last successful refresh — so the ~7 GB
    curated.production_forecast rebuild (the operation that OOMs a 2 GB Supabase
    box) does not run on the many nights ForecastWellMonths is unchanged. Each
    refresh is recorded in meta.etl_log ("curated", <matview>) so the gate can
    read the last successful refresh. Pass ``force=True`` to refresh everything
    regardless — do this after a full_reconcile_table (deletes aren't flagged by
    the incremental watermark) or a schema change."""
    n = len(_CURATED_MATVIEWS)
    for i, mv in enumerate(_CURATED_MATVIEWS):
        source_like = _GATED_REFRESH.get(mv)
        if source_like is not None and not force:
            def _probe(mv: str = mv, source_like: str = source_like) -> bool:
                conn = _open_connection()
                try:
                    return _matview_is_stale(conn, mv, source_like)
                finally:
                    conn.close()

            if not _retry_on_conn_loss(_probe, what=f"staleness check {mv}"):
                logger.info(
                    "skipped %s (%d/%d): source unchanged since last refresh",
                    mv, i + 1, n,
                )
                continue

        # Each matview is refreshed in its own connection, retried on connection
        # loss: a managed-Postgres restart between (or during) matviews is ridden
        # out rather than failing the whole step. REFRESH ... CONCURRENTLY is
        # idempotent, so re-running a matview after a dropped connection is safe.
        def _refresh_one(mv: str = mv) -> None:
            conn = _open_connection()
            try:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}")
            finally:
                conn.close()

        try:
            # log_etl_run records status=success on clean exit (the gate's
            # last-successful-refresh marker) or status=failed on exception.
            with log_etl_run("curated", mv):
                _retry_on_conn_loss(_refresh_one, what=f"refresh {mv}")
            logger.info("refreshed %s (%d/%d)", mv, i + 1, n)
        except Exception:
            logger.exception("failed refreshing %s (%d/%d)", mv, i + 1, n)
            raise
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


def upsert_batch_resilient(
    conn: PGConnection,
    schema: str,
    table: str,
    rows: Sequence[Mapping[str, Any]],
    conflict_cols: Sequence[str],
    update_cols: Sequence[str],
    *,
    reconnect: "Callable[[], PGConnection]" = get_connection,
) -> tuple[PGConnection, int]:
    """`bulk_upsert` + commit ONE batch, surviving a mid-pull connection drop.

    On a connection-level ``psycopg.OperationalError`` — the Supabase
    restart/failover / dropped-socket window (`consuming input failed ... could
    not receive data (10053)`, `AdminShutdown`, `the database system is not
    accepting connections`) that kills a long nightly pull mid-`executemany` —
    the poisoned connection is discarded, a fresh one obtained via ``reconnect``
    (``get_connection``, which already backs off across the restart), and the
    SAME batch replayed.

    This is the narrow case the ``_retry_on_conn_loss`` docstring's "callers must
    only wrap idempotent work" caveat permits for a *write*: the statement is
    ``INSERT ... ON CONFLICT DO UPDATE`` (idempotent), committed as a single
    self-contained unit, so replaying a batch that may have partially landed
    converges to the exact same row state. A half-done *multi*-batch transaction
    would NOT qualify — which is precisely why each batch is committed on its own
    here rather than in one commit at end-of-pull (so a drop costs the in-flight
    batch, not hours of streamed work).

    Only a *connection-level* failure is retried; a genuine data/constraint
    error is not transient and propagates immediately. A mid-restart drop
    surfaces two different psycopg exception types — an ``OperationalError``
    (`consuming input failed ... 10053`, `server closed the connection`) AND a
    ``DatabaseError`` protocol desync (`lost synchronization with server`,
    `message contents do not agree with length`) when the socket dies
    mid-result-message. ``DatabaseError`` is the *parent* of ``OperationalError``
    (not a subclass), so catching only ``OperationalError`` silently misses the
    desync — an observed real failure. Both are retried; a server-side data error
    (which carries a SQLSTATE and leaves the connection usable) is re-raised.
    Returns the (possibly reconnected) connection plus rows upserted, so the
    caller keeps streaming on a live connection.

    Budget is ``DB_UPSERT_BATCH_RETRIES`` (default 10) — deliberately more
    generous than the connect-level ``DB_CONNECT_RETRIES`` (6), because an
    observed Supabase restart is *flappy*: it accepts a connection, then drops it
    again mid-``executemany`` seconds later, and can churn like that for many
    minutes (a 2026-07-09 restart flapped >10 min). Each flap consumes one
    attempt, so the batch loop needs headroom the single connect budget lacks.
    Both failure points are absorbed: a dropped ``executemany`` AND a reconnect
    that can't yet reach the recovering server both back off and retry within
    this budget, so neither aborts the pull while the server is still coming up.
    """
    attempts = int(os.getenv("DB_UPSERT_BATCH_RETRIES", "10"))
    base = float(os.getenv("DB_CONNECT_RETRY_BASE", "2"))
    cap = float(os.getenv("DB_CONNECT_RETRY_MAX", "30"))
    live: PGConnection | None = conn
    last: psycopg.Error | None = None
    for i in range(1, attempts + 1):
        # Re-establish a connection if a prior attempt dropped or couldn't
        # reconnect. reconnect() (get_connection) has its own connect-level
        # backoff; if the server is still refusing connections it may exhaust
        # that and raise — absorbed here so the restart window is ridden out
        # rather than aborting the whole pull.
        if live is None:
            try:
                live = reconnect()
            except psycopg.OperationalError as exc:
                last = exc
                if i >= attempts:
                    break
                logger.warning(
                    "batch upsert to %s.%s: reconnect failed (attempt %d/%d): %s; "
                    "backing off",
                    schema, table, i, attempts, exc,
                )
                time.sleep(min(base * (2 ** (i - 1)), cap))
                continue
        try:
            n = bulk_upsert(live, schema, table, rows, conflict_cols, update_cols)
            live.commit()
            return live, n
        except psycopg.Error as exc:
            # Retry ONLY a connection-level failure. A server-side data/constraint
            # error carries a SQLSTATE (e.g. 22xxx/23xxx) and leaves the
            # connection usable — re-raise it, or we'd replay a non-transient
            # failure until the budget is exhausted. Everything else raised by
            # executemany during a restart is a broken connection: an
            # OperationalError, or a DatabaseError protocol desync (no SQLSTATE,
            # connection goes BAD). Guard on all three signals.
            conn_dead = (
                isinstance(exc, psycopg.OperationalError)
                or getattr(exc, "sqlstate", None) is None
                or getattr(live, "broken", False)
                or bool(getattr(live, "closed", False))
            )
            if not conn_dead:
                raise
            last = exc
            # The connection/transaction is dead; drop it before replaying.
            # rollback/close are best-effort — the socket may already be gone.
            for cleanup in (live.rollback, live.close):
                try:
                    cleanup()
                except Exception:
                    pass
            live = None
            if i >= attempts:
                break
            logger.warning(
                "batch upsert to %s.%s lost the connection (attempt %d/%d): %s; "
                "reconnecting and replaying the batch",
                schema, table, i, attempts, exc,
            )
            time.sleep(min(base * (2 ** (i - 1)), cap))
    logger.error(
        "batch upsert to %s.%s failed after %d attempts", schema, table, attempts
    )
    assert last is not None
    raise last


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
