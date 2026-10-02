"""dealintake.clients.anduin retry policy (no network)."""

import pytest
import requests

from dealintake.clients import anduin as mod


class _Resp:
    status_code = 200
    content = b"[]"

    def json(self):
        return []


class _FlakySession:
    """Raises ConnectionError on the first call, then succeeds."""

    def __init__(self):
        self.calls = 0
        self.headers = {}

    def request(self, method, url, **kw):
        self.calls += 1
        if self.calls == 1:
            raise requests.ConnectionError("Connection aborted: RemoteDisconnected")
        return _Resp()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    c = mod.Anduin("http://anduin.test")
    c._authed = True
    c.s = _FlakySession()
    return c


def test_get_retries_after_dropped_keepalive(client):
    assert client._req("GET", "/api/forecasts") == []
    assert client.s.calls == 2


def test_tc_preview_post_is_retried(client):
    client._req("POST", "/api/type-curves/compute", json={})
    assert client.s.calls == 2


def test_batch_post_is_not_retried(client):
    with pytest.raises(mod.AnduinError, match="not retried"):
        client._req("POST", "/api/forecasts/batch", json={})
    assert client.s.calls == 1
