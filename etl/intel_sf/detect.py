"""Nightly new-report detection against meta.intel_report_watermark.

STUB - implemented in phase 7 of the migration plan (after cutover).

Design of record:
  check_new_reports() -> int:
    - SELECT DISTINCT collection FROM NOVI_INTEL.SOURCE
    - INSERT unseen collections into meta.intel_report_watermark
    - return count of rows with acknowledged_at IS NULL
    - wrapped in etl.db.log_etl_run("intel_sf", "report_check")
  Wired as a _run_step in scripts/run_daily.py (after enverus, before the
  curated refresh). Notify-only: a nonzero count surfaces loudly in the
  nightly summary; the reload itself stays manual (user go-ahead).
"""

from __future__ import annotations


def check_new_reports() -> int:
    """Record newly visible INTEL collections; return unacknowledged count."""
    raise NotImplementedError(
        "phase 7 of the Snowflake intel migration - see the plan file"
    )
