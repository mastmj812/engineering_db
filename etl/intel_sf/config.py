"""Configuration for the Novi INTEL Snowflake share.

Credentials come from `.env` (SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER /
SNOWFLAKE_PAT are required); role/warehouse/database/schema default to Novi's
reader-account provisioning and are env-overridable.

`MIRRORED_VIEWS` is the registry of INTEL secure views we replicate into
`raw_intel.*`, grouped for the phased loader flags (--core --ml --econ
--arps --forecast). PRODUCTION_FORECAST / INVENTORY_FORECAST stay out of the
registry until the phase-4 forecast decision (see the migration plan).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _required_env(name: str) -> str:
    """Return an environment variable or raise if missing/empty."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name!r} is not set")
    return value


@dataclass(frozen=True)
class SnowflakeConfig:
    account: str
    user: str
    pat: str
    role: str
    warehouse: str
    database: str
    schema: str


def _normalize_account(raw: str) -> str:
    """Reduce a pasted URL to the bare account identifier the connector wants.

    Accepts 'https://novilabs-<org>', 'novilabs-<org>.snowflakecomputing.com',
    or the bare 'novilabs-<org>' and returns the bare form.
    """
    acct = raw.strip().rstrip("/")
    if "://" in acct:
        acct = acct.split("://", 1)[1]
    return acct.split(".", 1)[0]


def get_config() -> SnowflakeConfig:
    """Assemble the Snowflake connection config from the environment."""
    return SnowflakeConfig(
        account=_normalize_account(_required_env("SNOWFLAKE_ACCOUNT")),
        user=_required_env("SNOWFLAKE_USER"),
        pat=_required_env("SNOWFLAKE_PAT"),
        role=os.getenv("SNOWFLAKE_ROLE", "DATA_READER"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "NOVI_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "NOVI_DATA_ACCESS"),
        schema=os.getenv("SNOWFLAKE_SCHEMA", "NOVI_INTEL"),
    )


# INTEL secure views mirrored into raw_intel, keyed by loader flag group.
# Target table = view name lowercased. Views absent here are deliberate skips:
#   ML_SCORE, WELL_ECONOMICS  presentation duplicates of the base views below
#   PRODUCTION_FORECAST, INVENTORY_FORECAST  deferred to the forecast gate
MIRRORED_VIEWS: dict[str, tuple[str, ...]] = {
    "core": (
        "WELL",
        "PLANNED_WELL",
        "WELLBORE",
        "WELLBORE_TRAJECTORY",
        "SURFACE_LOCATION",
        "WELL_COMPLETION",
        "PAD",
        "OPERATOR",
        "BASIN",
        "SOURCE",
        "WELL_MASTER",
    ),
    "ml": (
        "WELL_ML_SCORE",
        "WELL_ROCK_QUALITY",
    ),
    "econ": (
        "WELL_COST_SUMMARY",
        "WELL_ECONOMICS_SUMMARY",
        "ECON_PRICE_ASSUMPTION",
    ),
    "arps": (
        "ARPS_FORECAST",
    ),
}


# Share columns deliberately NOT extracted (mirror table has them as NULLs).
# Forecast cumulatives are derivable; condensate is all-NULL for Permian.
# Saves ~5 GB on the 73M-row fact.
EXCLUDE_COLS: dict[str, frozenset[str]] = {
    "PRODUCTION_FORECAST": frozenset({
        "cumulative_oil", "cumulative_gas", "cumulative_ngl",
        "cumulative_water", "condensate_per_day", "cumulative_condensate",
    }),
}


def all_mirrored_views() -> tuple[str, ...]:
    """Every mirrored view across all flag groups, load order preserved."""
    return tuple(v for group in MIRRORED_VIEWS.values() for v in group)
