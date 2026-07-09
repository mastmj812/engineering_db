"""Novi Intelligence ingestion from the Snowflake secure data share (raw_intel).

Replaces the quarterly file-drop loaders in `etl/novi_intel/`. The share is a
Novi-provisioned READER account: database NOVI_DATA_ACCESS, schema NOVI_INTEL,
role DATA_READER, warehouse NOVI_WH; auth is user + PAT (programmatic access
token) via SNOWFLAKE_* env vars.

Modules:
    config    env access + the registry of INTEL views we mirror
    client    Snowflake connection factory (PAT auth, retry, QUERY_TAG)
    profile   read-only profiling report (phase-1 gate: grain, counts, keys)
    extract   view -> raw_intel.* streaming COPY loads (per-report idempotent)
    detect    nightly new-report check against meta.intel_report_watermark

The share hides superseded quarters automatically (latest report per basin
family); `NOVI_INTEL.SOURCE.collection` lists what is currently visible.
"""
