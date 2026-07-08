"""Gate logic for the selective curated refresh.

`_needs_refresh` decides whether a gated matview (e.g. the ~7 GB
curated.production_forecast) must be rebuilt, from two meta.etl_log timestamps:
its last successful refresh, and its source table's last change. Pure function,
no database — the DB query wrapper (`_matview_is_stale`) just feeds it these two
values.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from etl.db import _needs_refresh

T = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)


def test_never_refreshed_always_refreshes() -> None:
    # No successful refresh on record -> must build, regardless of source.
    assert _needs_refresh(None, None) is True
    assert _needs_refresh(None, T) is True


def test_no_change_since_last_refresh_skips() -> None:
    # Source last changed BEFORE the last refresh, or never -> matview is fresh.
    assert _needs_refresh(T, T - timedelta(days=3)) is False
    assert _needs_refresh(T, None) is False


def test_change_after_last_refresh_refreshes() -> None:
    assert _needs_refresh(T, T + timedelta(hours=1)) is True


def test_change_at_same_instant_refreshes() -> None:
    # Ties break toward refreshing (>=): a spurious rebuild is safe, a miss isn't.
    assert _needs_refresh(T, T) is True


def test_failed_refresh_self_heals() -> None:
    # Model the OOM case: source changed (t1), refresh attempt failed so the last
    # *successful* refresh stays old (t0 < t1) -> the next run still sees stale
    # and rebuilds. This is why the gate keys on last-SUCCESSFUL refresh.
    t0 = T
    t1 = T + timedelta(hours=2)
    assert _needs_refresh(t0, t1) is True
