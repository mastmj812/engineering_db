"""ETL pure-function test: the per-batch resilient upsert in etl.db.

``upsert_batch_resilient`` upserts + commits ONE batch and, on a connection-level
``psycopg.OperationalError`` (the Supabase restart/dropped-socket window that
was killing the nightly enverus.wells pull mid-`executemany`), discards the dead
connection, reconnects, and replays the SAME idempotent batch. This pins that
contract: transient connection loss is ridden out, a data error is not retried,
and each successful batch commits on its own. No database is opened — the upsert
is stubbed and the reconnect callable hands back a fake connection.
"""

from __future__ import annotations

import psycopg
import pytest

from etl import db as etl_db
from etl.db import upsert_batch_resilient


class _FakeConn:
    """Records rollback/commit/close so we can assert on connection lifecycle."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1

    def close(self) -> None:
        self.closed += 1


_ROWS = [{"wellid": "1", "completionid": "1", "x": "a"}]
_ARGS = ("raw_enverus", "wells", _ROWS, ["wellid", "completionid"], ["x"])


@pytest.fixture(autouse=True)
def _fast_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    # No real backoff sleeping, and a small, deterministic attempt budget.
    monkeypatch.setattr(etl_db.time, "sleep", lambda *_: None)
    monkeypatch.setenv("DB_UPSERT_BATCH_RETRIES", "4")
    monkeypatch.setenv("DB_CONNECT_RETRY_BASE", "0")
    monkeypatch.setenv("DB_CONNECT_RETRY_MAX", "0")


def test_happy_path_commits_and_returns_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(etl_db, "bulk_upsert", lambda *a, **k: len(a[3]))
    conn = _FakeConn("orig")

    out_conn, n = upsert_batch_resilient(conn, *_ARGS, reconnect=lambda: conn)

    assert (out_conn, n) == (conn, 1)
    assert conn.committed == 1
    assert conn.rolled_back == 0 and conn.closed == 0


def test_transient_conn_loss_reconnects_and_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def flaky(*a: object, **k: object) -> int:
        calls["n"] += 1
        if calls["n"] < 3:  # fail the first two executemany attempts
            raise psycopg.OperationalError(
                "consuming input failed: could not receive data from server "
                "(0x00002745/10053)"
            )
        return len(a[3])  # type: ignore[arg-type]

    monkeypatch.setattr(etl_db, "bulk_upsert", flaky)
    orig = _FakeConn("orig")
    fresh = [_FakeConn("fresh-1"), _FakeConn("fresh-2")]

    def reconnect() -> _FakeConn:
        return fresh.pop(0)

    out_conn, n = upsert_batch_resilient(orig, *_ARGS, reconnect=reconnect)

    assert calls["n"] == 3  # failed twice, succeeded on the third
    assert n == 1
    # The two dead connections were discarded (rolled back + closed); the batch
    # committed exactly once, on the surviving connection handed back to caller.
    assert (orig.rolled_back, orig.closed) == (1, 1)
    assert out_conn.tag == "fresh-2" and out_conn.committed == 1


def test_absorbs_a_failed_reconnect_then_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # executemany drops once; the first reconnect still can't reach the
    # recovering server (get_connection exhausts its own budget and raises),
    # but that is absorbed — the loop backs off and the next reconnect succeeds.
    calls = {"upsert": 0}

    def flaky_upsert(*a: object, **k: object) -> int:
        calls["upsert"] += 1
        if calls["upsert"] == 1:
            raise psycopg.OperationalError("could not receive data (10053)")
        return len(a[3])  # type: ignore[arg-type]

    monkeypatch.setattr(etl_db, "bulk_upsert", flaky_upsert)

    reconnect_calls = {"n": 0}

    def flaky_reconnect() -> _FakeConn:
        reconnect_calls["n"] += 1
        if reconnect_calls["n"] == 1:  # server still refusing connections
            raise psycopg.OperationalError("the database system is not accepting")
        return _FakeConn("recovered")

    out_conn, n = upsert_batch_resilient(
        _FakeConn("orig"), *_ARGS, reconnect=flaky_reconnect
    )

    assert n == 1 and out_conn.tag == "recovered"
    assert reconnect_calls["n"] == 2  # first reconnect failed, second succeeded


def test_protocol_desync_databaseerror_is_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A mid-restart drop can surface as a DatabaseError protocol desync
    # ("lost synchronization with server"), NOT an OperationalError. Because
    # DatabaseError is the *parent* of OperationalError, a naive
    # `except OperationalError` misses it — this pins that it IS retried.
    calls = {"n": 0}

    def desync(*a: object, **k: object) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise psycopg.DatabaseError(
                'lost synchronization with server: got message type "F", '
                "length 1096040780"
            )
        return len(a[3])  # type: ignore[arg-type]

    monkeypatch.setattr(etl_db, "bulk_upsert", desync)

    out_conn, n = upsert_batch_resilient(
        _FakeConn("orig"), *_ARGS, reconnect=lambda: _FakeConn("fresh")
    )

    assert n == 1 and calls["n"] == 2  # desync retried, not aborted
    assert out_conn.tag == "fresh"


def test_gives_up_after_attempt_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def always_drop(*a: object, **k: object) -> int:
        calls["n"] += 1
        raise psycopg.OperationalError("AdminShutdown")

    monkeypatch.setattr(etl_db, "bulk_upsert", always_drop)

    with pytest.raises(psycopg.OperationalError):
        upsert_batch_resilient(
            _FakeConn("orig"), *_ARGS, reconnect=lambda: _FakeConn("fresh")
        )
    assert calls["n"] == 4  # exactly DB_CONNECT_RETRIES attempts, no more


def test_data_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def bad_data(*a: object, **k: object) -> int:
        calls["n"] += 1
        raise psycopg.errors.UniqueViolation("duplicate key")

    monkeypatch.setattr(etl_db, "bulk_upsert", bad_data)

    with pytest.raises(psycopg.errors.UniqueViolation):
        upsert_batch_resilient(
            _FakeConn("orig"), *_ARGS, reconnect=lambda: _FakeConn("fresh")
        )
    assert calls["n"] == 1  # propagates immediately, no reconnect/replay
