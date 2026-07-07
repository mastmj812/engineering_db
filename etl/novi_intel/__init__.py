"""Novi Intelligence basin-report ingestion (raw_novi_intel).

The EXTRACT layer for the quarterly Novi Intelligence file drop. Designed so that
when the Novi Intelligence Snowflake API/share goes live (~July 2026), only these
modules are swapped for a Snowflake puller — `raw_novi_intel.*` and the curated
layer on top stay unchanged.
"""
