"""Singleton-ish factory for the Enverus Developer API v3 client.

The official `enverus-developer-api` PyPI package handles auth (exchanges
the secret key for a bearer token, auto-refreshes every 8h), pagination
(`v3.query(...)` is a generator), and retries (configured on the client).

The SDK never passes a `timeout` to its `requests.Session` (every
`session.get(...)` in its paging loop omits it), so a half-open connection
makes a streaming `query(...)` read block FOREVER — observed 2026-07-09, a
nightly `wells` pull hung ~26 min on a dead socket with the DB perfectly
healthy. We re-mount the session's HTTPS adapter with a default
`(connect, read)` timeout so a stalled read raises instead of hanging. The
SDK's urllib3 `Retry` (GET is idempotent, in its allowed_methods) then
retries a transient stall automatically; a persistently dead socket surfaces
as an exception that fails the run cleanly — per-batch commits in
`pull_dataset` preserve progress and the next run resumes from the cursor.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from enverus_developer_api import DeveloperAPIv3
from requests.adapters import HTTPAdapter

_client: DeveloperAPIv3 | None = None


class _TimeoutHTTPAdapter(HTTPAdapter):
    """`HTTPAdapter` that applies a default timeout to any request that doesn't
    set one. The Enverus SDK calls `session.get(...)` with no timeout, so this
    adapter's `send()` is the injection point that bounds an otherwise-infinite
    socket read without forking the vendored SDK."""

    def __init__(
        self,
        *args: object,
        timeout: tuple[float, float] | float | None = None,
        **kwargs: object,
    ) -> None:
        self._timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):  # type: ignore[override]
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return super().send(request, **kwargs)


def apply_read_timeout(client: DeveloperAPIv3) -> DeveloperAPIv3:
    """Re-mount the client session's HTTPS adapter with a default
    `(connect, read)` timeout, reusing the SDK's existing urllib3 `Retry` so its
    retry/backoff behaviour is preserved. Timeouts are env-configurable:
    ENVERUS_CONNECT_TIMEOUT (default 30s) and ENVERUS_READ_TIMEOUT (default
    120s — a page of ~1000 rows returns in seconds over the WAN, so 120s of
    dead air unambiguously means a half-open socket, not a merely-slow response).
    Returns the client for chaining."""
    connect_timeout = float(os.getenv("ENVERUS_CONNECT_TIMEOUT", "30"))
    read_timeout = float(os.getenv("ENVERUS_READ_TIMEOUT", "120"))
    existing = client.session.get_adapter("https://")
    client.session.mount(
        "https://",
        _TimeoutHTTPAdapter(
            # Reuse the SDK's Retry(total, backoff_factor, status_forcelist,
            # allowed_methods) so behaviour is unchanged apart from the timeout.
            max_retries=existing.max_retries,
            timeout=(connect_timeout, read_timeout),
        ),
    )
    return client


def get_client() -> DeveloperAPIv3:
    """Return a process-wide `DeveloperAPIv3` instance, creating it on first call."""
    global _client
    if _client is None:
        load_dotenv()
        secret_key = os.getenv("ENVERUS_SECRET_KEY")
        if not secret_key:
            raise RuntimeError("ENVERUS_SECRET_KEY not set in .env")
        _client = apply_read_timeout(
            DeveloperAPIv3(secret_key=secret_key, retries=5, backoff_factor=1)
        )
    return _client
