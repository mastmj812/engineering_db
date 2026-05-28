"""Singleton-ish factory for the Enverus Developer API v3 client.

The official `enverus-developer-api` PyPI package handles auth (exchanges
the secret key for a bearer token, auto-refreshes every 8h), pagination
(`v3.query(...)` is a generator), and retries (configured on the client).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from enverus_developer_api import DeveloperAPIv3

_client: DeveloperAPIv3 | None = None


def get_client() -> DeveloperAPIv3:
    """Return a process-wide `DeveloperAPIv3` instance, creating it on first call."""
    global _client
    if _client is None:
        load_dotenv()
        secret_key = os.getenv("ENVERUS_SECRET_KEY")
        if not secret_key:
            raise RuntimeError("ENVERUS_SECRET_KEY not set in .env")
        _client = DeveloperAPIv3(secret_key=secret_key, retries=5, backoff_factor=1)
    return _client
