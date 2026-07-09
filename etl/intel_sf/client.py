"""Snowflake connection factory for the Novi INTEL reader account.

PAT (programmatic access token) auth: connector >=3.10 supports
`authenticator="PROGRAMMATIC_ACCESS_TOKEN"` with the PAT in `password`; on
older connectors passing the PAT as a plain password also works, so we try
the explicit authenticator first and fall back.

The share's warehouse (NOVI_WH) autosuspends — the first query after idle can
take 10-30 s to resume; that is expected, not an error. Connection attempts
are retried with backoff (network blips, warehouse resume timeouts).
"""

from __future__ import annotations

import logging

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import snowflake.connector
from snowflake.connector import SnowflakeConnection
from snowflake.connector.errors import DatabaseError, OperationalError

from etl.intel_sf.config import SnowflakeConfig, get_config

logger = logging.getLogger(__name__)

# Session tag so Novi (and we) can attribute warehouse usage in query history.
_QUERY_TAG = "oilgas-etl"

# Generous network timeouts: big result sets stream over WAN; warehouse
# resume adds tens of seconds to the first query.
_LOGIN_TIMEOUT_S = 60
_NETWORK_TIMEOUT_S = 300


def _connect(cfg: SnowflakeConfig, authenticator: str | None) -> SnowflakeConnection:
    kwargs: dict[str, object] = {
        "account": cfg.account,
        "user": cfg.user,
        "password": cfg.pat,
        "role": cfg.role,
        "warehouse": cfg.warehouse,
        "database": cfg.database,
        "schema": cfg.schema,
        "login_timeout": _LOGIN_TIMEOUT_S,
        "network_timeout": _NETWORK_TIMEOUT_S,
        "session_parameters": {"QUERY_TAG": _QUERY_TAG},
        # Client-side result cache off: the ETL never re-runs identical SQL in
        # one process, and cached result sets would just hold memory.
        "client_session_keep_alive": False,
    }
    if authenticator is not None:
        kwargs["authenticator"] = authenticator
    return snowflake.connector.connect(**kwargs)


@retry(
    retry=retry_if_exception_type(OperationalError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, max=30),
    reraise=True,
)
def get_sf_connection(cfg: SnowflakeConfig | None = None) -> SnowflakeConnection:
    """Open a Snowflake connection to the Novi INTEL share.

    Tries PAT-native auth first, falls back to PAT-as-password (older
    connectors / accounts where the explicit authenticator is rejected).
    Caller owns the connection; close it when done.
    """
    cfg = cfg or get_config()
    try:
        return _connect(cfg, authenticator="PROGRAMMATIC_ACCESS_TOKEN")
    except DatabaseError as exc:
        logger.warning(
            "PAT authenticator rejected (%s); retrying PAT as password", exc
        )
        return _connect(cfg, authenticator=None)


def fetch_all(conn: SnowflakeConnection, sql: str) -> list[tuple]:
    """Run one query, return all rows. For small metadata/profiling queries only."""
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()
