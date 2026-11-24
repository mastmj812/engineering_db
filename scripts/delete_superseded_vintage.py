"""FULLY delete one SUPERSEDED Novi Intelligence vintage from raw_intel (Michael-only; policy of record is the TRIM).

The retention policy of record (2026-09-18, scripts.trim_superseded_vintage) keeps a superseded vintage's accuracy core.
This script is the other choice, taken per vintage on Michael's explicit word (first use: Midland 2026Q3, 2026-11-24:
"i would rather dump the 2026Q3 data"). What it costs, permanently:

  * the vintage can never be scored in curated.intel_forecast_accuracy_vintage (sql/43): no "did Novi improve" record for it;
  * the dossier prior-vintage overlay loses it;
  * the share no longer serves a superseded collection and backups exclude forecast data: there is no way back.

What it never touches: any other report; raw_intel.stick_id_map (stick ids stay stable across vintages); and
raw_novi_intel.pads (the DSU polygons: the BOX stick sets were generated on a vintage's polygons, box.location_set.dsu_vintage).

It refuses a LATEST vintage (curated.intel_available_reports().is_latest): reload the successor first.

    python -m scripts.delete_superseded_vintage --report <report_name>          # dry run: counts only
    python -m scripts.delete_superseded_vintage --report <report_name> --go     # deletes (explicit go)

The forecast table is deleted in forecast_day bands with settle() between them (each band its own commit: a failure
leaves a partly deleted SUPERSEDED vintage, and a re-run finishes it); the small tables go in one transaction. A plain
VACUUM (ANALYZE) at the end makes the space reusable; the files on disk do not shrink.
"""

from __future__ import annotations

import argparse
import time

from etl.db import get_connection, settle

BAND_DAYS = 2100          # the trim's band: about 5 chunks across the 30-year horizon
FORECAST = "production_forecast"
_TABLES_SQL = """
SELECT c.table_name FROM information_schema.columns c JOIN pg_tables t ON t.schemaname = c.table_schema AND t.tablename = c.table_name
WHERE c.table_schema = 'raw_intel' AND c.column_name = 'report_name' ORDER BY 1
"""
_OTHERS_SQL = "SELECT report_name, count(*) FROM raw_intel.well_master WHERE report_name <> %s GROUP BY 1 ORDER BY 1"
_KEPT_SQL = "SELECT (SELECT count(*) FROM raw_intel.stick_id_map), (SELECT count(*) FROM raw_novi_intel.pads)"


def refusal(report: str, available: list[tuple[str, bool]]) -> str | None:
    """Why `report` must not be deleted, or None. `available` = (report_name, is_latest) of curated.intel_available_reports()."""
    known = dict(available)
    if report not in known:
        return f"{report} is not a report in raw_intel (known: {sorted(known)})"
    if known[report]:
        return f"{report} is the LATEST vintage of its basin: reload its successor first"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, help="the superseded report_name to delete in full")
    ap.add_argument("--go", action="store_true", help="DELETE. Without it: counts only.")
    ap.add_argument("--skip-vacuum", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            q = cur.execute
            why = refusal(a.report, [(r[0], bool(r[4])) for r in q("SELECT * FROM curated.intel_available_reports()").fetchall()])
            if why:
                raise SystemExit(f"REFUSED: {why}")
            tables = [r[0] for r in q(_TABLES_SQL).fetchall()]
            others, kept = q(_OTHERS_SQL, (a.report,)).fetchall(), q(_KEPT_SQL).fetchone()
            print(f"{a.report}: {'DELETE' if a.go else 'dry run'}; {len(tables)} raw_intel tables keyed by report_name", flush=True)
            counts = {}
            for t in tables:
                if t == FORECAST:
                    counts[t], max_day = q(f'SELECT count(*), max(forecast_day) FROM raw_intel."{t}" WHERE report_name = %s', (a.report,)).fetchone()
                else:
                    counts[t] = q(f'SELECT count(*) FROM raw_intel."{t}" WHERE report_name = %s', (a.report,)).fetchone()[0]
                print(f"    {t}: {counts[t]:,} rows", flush=True)
            print(f"    other reports kept: {others}; stick_id_map {kept[0]:,} rows and raw_novi_intel.pads {kept[1]:,} rows are not touched", flush=True)
            if not a.go:
                print("dry run: nothing deleted", flush=True)
                return 0

            lo = 0
            while counts.get(FORECAST) and lo <= (max_day or 0):
                t = time.monotonic()
                q(f'DELETE FROM raw_intel."{FORECAST}" WHERE report_name = %s AND forecast_day > %s AND forecast_day <= %s', (a.report, lo - 1, lo + BAND_DAYS))
                print(f"    {FORECAST} forecast_day {lo}..{lo + BAND_DAYS}: {cur.rowcount:,} rows deleted in {time.monotonic() - t:.0f} s", flush=True)
                lo += BAND_DAYS + 1
                settle()
            q(f'DELETE FROM raw_intel."{FORECAST}" WHERE report_name = %s', (a.report,))      # rows with a NULL forecast_day, if any
        conn.autocommit = False
        with conn.cursor() as cur:                                                        # the small tables: one transaction
            for t in tables:
                if t != FORECAST:
                    cur.execute(f'DELETE FROM raw_intel."{t}" WHERE report_name = %s', (a.report,))
                    print(f"    {t}: {cur.rowcount:,} rows deleted", flush=True)
            left = sum(cur.execute(f'SELECT count(*) FROM raw_intel."{t}" WHERE report_name = %s', (a.report,)).fetchone()[0] for t in tables)
            same = cur.execute(_OTHERS_SQL, (a.report,)).fetchall() == others and tuple(cur.execute(_KEPT_SQL).fetchone()) == tuple(kept)
            if left or not same:
                conn.rollback()
                raise SystemExit(f"ROLLED BACK the small tables: {left} rows of {a.report} left, other reports / kept tables unchanged = {same}")
        conn.commit()
        print(f"    0 rows of {a.report} left; every other report, stick_id_map and the DSU polygons unchanged", flush=True)
        if not a.skip_vacuum:
            conn.autocommit = True
            with conn.cursor() as cur:
                for t in tables:
                    cur.execute(f'VACUUM (ANALYZE) raw_intel."{t}"')
            print("    VACUUM (ANALYZE) done: the space is reusable, the files do not shrink", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t0:.0f} s. Rebuild what read it: python -m scripts.apply_intel_forecast_accuracy ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
