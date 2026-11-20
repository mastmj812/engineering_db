"""Novi v4 (Snowflake share NOVI_DATA_ACCESS.NOVI_WELLS) -> the six v3-shaped `raw_novi` tables.

`queries` builds the Snowflake SQL that presents v4 in the v3 table shapes (pure, DB-free).
`sync` decides what to pull and writes it. `load` is the CLI. Study of record:
docs/novi_v4_parity.md.
"""
