"""ETL pure-function test: the connection-loss retry wrapper in etl.db.

``_retry_on_conn_loss`` rides out a brief Supabase restart/failover during the
daily run — it retries a connection-level ``psycopg.OperationalError`` with
backoff, but must NOT retry programming/constraint errors (those aren't
transient and re-running half-done work would be wrong). This pins that
contract. No database is opened: the wrapped callable is a stub, and
``time.sleep`` is patched out so the backoff doesn't slow CI.
"""

from __future__ import annotations

import psycopg
import pytest

from etl import db as etl_db
from etl.db import _retry_on_conn_loss


@pytest.fixture(autouse=True)
def _fast_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    # No real sleeping, and a small, deterministic attempt budget.
    monkeypatch.setattr(etl_db.time, "sleep", lambda *_: None)
    monkeypatch.setenv("DB_CONNECT_RETRIES", "4")
    monkeypatch.setenv("DB_CONNECT_RETRY_BASE", "0")
    monkeypatch.setenv("DB_CONNECT_RETRY_MAX", "0")


def test_retries_transient_operational_error_then_succeeds() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise psycopg.OperationalError(
                "the database system is not accepting connections"
            )
        return "connected"

    assert _retry_on_conn_loss(fn, what="db connect") == "connected"
    assert calls["n"] == 3  # failed twice, succeeded on the third


def test_gives_up_after_the_configured_attempt_budget() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise psycopg.OperationalError("AdminShutdown")

    with pytest.raises(psycopg.OperationalError):
        _retry_on_conn_loss(fn, what="db connect")
    assert calls["n"] == 4  # exactly DB_CONNECT_RETRIES attempts, no more


def test_non_operational_error_is_not_retried() -> None:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        raise ValueError("programming error — not a connection loss")

    with pytest.raises(ValueError):
        _retry_on_conn_loss(fn, what="db connect")
    assert calls["n"] == 1  # propagates immediately, no retry
