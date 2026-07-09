"""ETL run-logging contract: `log_etl_run` must not leak 'running' rows.

The 2026-06/07 incident: `log_etl_run` held ONE connection open across the
whole step and finalized the row on it. A Supabase restart mid-pull killed the
step's connection AND that logging connection, so the failure UPDATE died too
and the row was stranded at status='running' — one orphan per night, and any
monitoring that counts 'running' rows was unusable.

These tests pin the fix, DB-free (a fake connection factory stands in for
`etl.db._open_connection`):
  1. the finish UPDATE runs on a FRESH connection, not one opened at entry;
  2. the finish is retried through `_retry_on_conn_loss`, so a restart window
     that kills the first finish attempt doesn't strand the row;
  3. a bookkeeping failure never masks the step's own exception;
  4. `sweep_stale_runs` reconciles rows a hard-killed process left behind.
"""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from etl import db as etl_db
from etl.db import log_etl_run, sweep_stale_runs


@pytest.fixture(autouse=True)
def _fast_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(etl_db.time, "sleep", lambda *_: None)
    monkeypatch.setenv("DB_CONNECT_RETRIES", "4")
    monkeypatch.setenv("DB_CONNECT_RETRY_BASE", "0")
    monkeypatch.setenv("DB_CONNECT_RETRY_MAX", "0")


class FakeCursor:
    """Records executed statements; returns a fixed etl_log_id on fetchone."""

    def __init__(self, conn: "FakeConn") -> None:
        self.conn = conn

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def execute(self, statement: Any, params: Any = None) -> None:
        if self.conn.fail_on_execute is not None:
            raise self.conn.fail_on_execute
        self.conn.statements.append((str(statement), params))

    def fetchone(self) -> tuple[int]:
        return (self.conn.run_id,)

    @property
    def rowcount(self) -> int:
        return self.conn.sweep_rowcount


class FakeConn:
    """One fake connection; the factory tracks every instance it hands out."""

    def __init__(
        self,
        run_id: int = 77,
        fail_on_execute: Exception | None = None,
        sweep_rowcount: int = 0,
    ) -> None:
        self.run_id = run_id
        self.fail_on_execute = fail_on_execute
        self.sweep_rowcount = sweep_rowcount
        self.statements: list[tuple[str, Any]] = []
        self.committed = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def _install_factory(
    monkeypatch: pytest.MonkeyPatch, plan: list[FakeConn]
) -> list[FakeConn]:
    """Patch _open_connection to hand out `plan` in order; return the log."""
    handed_out: list[FakeConn] = []

    def _fake_open() -> FakeConn:
        conn = plan[len(handed_out)]
        handed_out.append(conn)
        return conn

    monkeypatch.setattr(etl_db, "_open_connection", _fake_open)
    return handed_out


def test_success_finishes_on_a_fresh_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = [FakeConn(), FakeConn()]
    handed_out = _install_factory(monkeypatch, plan)

    with log_etl_run("enverus", "wells") as run:
        run.rows_inserted = 123

    # One connection to open the row, a SECOND to finish it — no connection
    # survives the step, so no shared-fate failure is possible.
    assert len(handed_out) == 2
    assert all(c.closed and c.committed for c in handed_out)
    open_sql = handed_out[0].statements[0][0]
    finish_sql, finish_params = handed_out[1].statements[0]
    assert "INSERT INTO meta.etl_log" in open_sql
    assert "UPDATE meta.etl_log" in finish_sql
    assert finish_params == ("success", 123, 0, None, 77)


def test_failure_records_original_error_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handed_out = _install_factory(monkeypatch, [FakeConn(), FakeConn()])

    with pytest.raises(RuntimeError, match="pull exploded"):
        with log_etl_run("enverus", "wells"):
            raise RuntimeError("pull exploded")

    _, params = handed_out[1].statements[0]
    assert params[0] == "failed"
    assert params[3] == "pull exploded"


def test_finish_is_retried_through_a_restart_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # First finish connection dies like a Supabase restart (AdminShutdown is
    # an OperationalError); the retry's fresh connection succeeds. This is
    # the exact scenario that used to strand the row at 'running'.
    dying = FakeConn(
        fail_on_execute=psycopg.OperationalError(
            "terminating connection due to administrator command"
        )
    )
    handed_out = _install_factory(monkeypatch, [FakeConn(), dying, FakeConn()])

    with log_etl_run("enverus", "wells"):
        pass

    assert len(handed_out) == 3
    assert dying.closed and not dying.committed
    assert handed_out[2].statements[0][1][0] == "success"


def test_bookkeeping_failure_never_masks_the_step_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Every finish attempt fails (outage outlasts the retry budget); the
    # step's own exception must still be what propagates.
    def _always_dying() -> FakeConn:
        return FakeConn(
            fail_on_execute=psycopg.OperationalError("still restarting")
        )

    opened = FakeConn()
    conns = iter([opened])

    def _fake_open() -> FakeConn:
        return next(conns, None) or _always_dying()

    monkeypatch.setattr(etl_db, "_open_connection", _fake_open)

    with pytest.raises(RuntimeError, match="the real failure"):
        with log_etl_run("enverus", "wells"):
            raise RuntimeError("the real failure")


def test_sweep_marks_stale_running_rows_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConn(sweep_rowcount=21)
    handed_out = _install_factory(monkeypatch, [conn])

    assert sweep_stale_runs(max_age_hours=12) == 21

    sql_text, params = handed_out[0].statements[0]
    assert "status = 'running'" in sql_text
    assert "status = 'failed'" in sql_text
    assert params == (12,)
    assert conn.committed and conn.closed
