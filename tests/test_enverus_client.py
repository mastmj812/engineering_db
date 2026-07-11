"""Unit tests for the Enverus client's read-timeout hardening (no network).

The SDK issues `session.get(...)` with no timeout, so a half-open connection
hangs a streaming query forever. `apply_read_timeout` re-mounts the session's
HTTPS adapter with a default (connect, read) timeout while preserving the SDK's
urllib3 Retry. These pin: the timeout is injected into requests that omit one,
an explicit timeout is left alone, and the re-mount keeps the Retry config.
"""

from __future__ import annotations

import types

import requests
import pytest
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from etl.enverus import client as client_mod


def _session_with_retry(total: int = 5) -> tuple[requests.Session, Retry]:
    sess = requests.Session()
    retry = Retry(total=total, backoff_factor=1)
    sess.mount("https://", HTTPAdapter(max_retries=retry))
    return sess, retry


def test_send_injects_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        HTTPAdapter, "send",
        lambda self, request, **kw: captured.update(kw) or "resp",
    )
    adapter = client_mod._TimeoutHTTPAdapter(timeout=(3, 7))

    assert adapter.send(object()) == "resp"
    assert captured["timeout"] == (3, 7)  # injected because caller omitted it


def test_send_preserves_explicit_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        HTTPAdapter, "send",
        lambda self, request, **kw: captured.update(kw) or "resp",
    )
    adapter = client_mod._TimeoutHTTPAdapter(timeout=(3, 7))

    adapter.send(object(), timeout=99)
    assert captured["timeout"] == 99  # caller's explicit value wins


def test_apply_read_timeout_defaults_and_preserves_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENVERUS_CONNECT_TIMEOUT", raising=False)
    monkeypatch.delenv("ENVERUS_READ_TIMEOUT", raising=False)
    sess, retry = _session_with_retry(total=5)
    fake_client = types.SimpleNamespace(session=sess)

    out = client_mod.apply_read_timeout(fake_client)  # type: ignore[arg-type]

    adapter = sess.get_adapter("https://")
    assert isinstance(adapter, client_mod._TimeoutHTTPAdapter)
    assert adapter._timeout == (30.0, 120.0)   # env defaults
    assert adapter.max_retries is retry        # SDK Retry preserved, not reset
    assert out is fake_client


def test_apply_read_timeout_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVERUS_CONNECT_TIMEOUT", "5")
    monkeypatch.setenv("ENVERUS_READ_TIMEOUT", "45")
    sess, _ = _session_with_retry()
    fake_client = types.SimpleNamespace(session=sess)

    client_mod.apply_read_timeout(fake_client)  # type: ignore[arg-type]

    assert sess.get_adapter("https://")._timeout == (5.0, 45.0)
