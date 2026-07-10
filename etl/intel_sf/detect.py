"""Nightly new-report detection against meta.intel_report_watermark.

Notify-only: check_new_reports() records every basin_research__* collection
visible in NOVI_INTEL.SOURCE and returns how many ENTITLED collections are
awaiting a load. The quarterly reload itself stays manual (user go-ahead).

Semantics:
  * watermark row exists        -> collection has been seen (historical record)
  * acknowledged_at IS NULL     -> not yet loaded into raw_intel
  * acknowledged_at set         -> loaded (auto-acknowledged: a row is acked
    when its report_name shows up in raw_intel.well_master, so running the
    reload clears the alert on the next nightly — no manual ack step)
  * "entitled" = report families we actually hold data for (families present
    in raw_intel.well_master). Other basins' collections are recorded but
    never alerted — the row-access policy wouldn't let us load them anyway.

Wired as a run_daily step (after enverus, before the curated refresh); a
Snowflake outage fails the step visibly without blocking the rest of the
night. Wrapped in log_etl_run("intel_sf", "report_check").

    python -m etl.intel_sf.detect      # manual check, prints the verdict
"""

from __future__ import annotations

import logging

from etl.db import get_connection, log_etl_run
from etl.intel_sf.client import get_sf_connection

logger = logging.getLogger(__name__)


def _report_family(report_name: str) -> str | None:
    """'basin_research__Midland_Basin__2025Q3' -> 'Midland_Basin'."""
    parts = report_name.split("__")
    return parts[1] if len(parts) == 3 and parts[0] == "basin_research" else None


def check_new_reports() -> int:
    """Record newly visible INTEL collections; return count awaiting load."""
    with log_etl_run("intel_sf", "report_check") as run:
        sf = get_sf_connection()
        try:
            with sf.cursor() as cur:
                cur.execute("SELECT DISTINCT collection FROM SOURCE ORDER BY 1")
                collections = [str(r[0]) for r in cur.fetchall()]
        finally:
            sf.close()
        seen = [(c, _report_family(c)) for c in collections]
        seen = [(c, f) for c, f in seen if f]  # drop non-report rows ('basins')

        pg = get_connection()
        try:
            with pg.cursor() as cur:
                # record anything new
                cur.executemany(
                    "INSERT INTO meta.intel_report_watermark (report_name, report_family) "
                    "VALUES (%s, %s) ON CONFLICT (report_name) DO NOTHING",
                    seen,
                )
                # auto-acknowledge whatever is already loaded
                cur.execute(
                    "UPDATE meta.intel_report_watermark w "
                    "SET acknowledged_at = NOW() "
                    "WHERE w.acknowledged_at IS NULL "
                    "AND EXISTS (SELECT 1 FROM raw_intel.well_master m "
                    "            WHERE m.report_name = w.report_name)"
                )
                # alert set: unloaded collections in families we hold data for
                cur.execute(
                    "SELECT w.report_name FROM meta.intel_report_watermark w "
                    "WHERE w.acknowledged_at IS NULL "
                    "AND w.report_family IN (SELECT DISTINCT split_part(report_name, '__', 2) "
                    "                        FROM raw_intel.well_master) "
                    "ORDER BY w.report_name"
                )
                pending = [r[0] for r in cur.fetchall()]
            pg.commit()
        finally:
            pg.close()

        run.rows_inserted = len(pending)
        if pending:
            logger.warning(
                "NEW NOVI INTEL REPORT(S) AVAILABLE: %s — on go-ahead run "
                "`python -m scripts.load_intel_sf --all` then the curated rebuild "
                "sequence (see .claude/skills/novi-quarterly-reload/SKILL.md)",
                ", ".join(pending),
            )
        else:
            logger.info("intel report check: no new entitled collections "
                        "(%d visible, all loaded or out of entitlement)", len(seen))
        return len(pending)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    n = check_new_reports()
    print(f"pending entitled reports: {n}")
