"""Trim a SUPERSEDED Novi Intelligence vintage to its accuracy core.

Retention policy of record (Michael, 2026-09-18): when a vintage is
superseded, keep everything the vintage-accuracy matview (sql/43) and
lightweight vintage comparison need — all core/arps slices plus forecast
rows mop <= 24 (forecast_day <= 720) — and DELETE the long-horizon
forecast bulk (~93% of the vintage's ~16 GB). Effects:

  * sql/43 accuracy tracking keeps accruing for the vintage (mop 1-24
    grain untouched) — the "did Novi improve" record survives.
  * The dossier prior-vintage overlay DEGRADES, deliberately: its
    forecast rows end at mop 24 and the (anchored) Arps tail carries the
    rest — shape approximate beyond 2 years, levels anchored.
  * Disk: DELETE frees pages for internal reuse (the next vintage's load
    fills them instead of growing the provisioned disk). File size and
    the Supabase bill do NOT shrink — this controls future growth only.
  * IRREVERSIBLE for the deleted rows: superseded collections leave the
    share and backups exclude forecast data.

Deletes are chunked by forecast_day band with settle() between chunks so
a mid-day run stays civil on the pooler; a plain VACUUM (ANALYZE) at the
end makes the space reusable ahead of the next reload.

Usage (venv, repo root; 5432 session pooler via etl.db):
    python -m scripts.trim_superseded_vintage --report <report_name>
    python -m scripts.trim_superseded_vintage --all-superseded
    python -m scripts.trim_superseded_vintage --all-superseded --dry-run
"""

from __future__ import annotations

import argparse
import time

from etl.db import get_connection, settle

KEEP_MAX_DAY = 720  # mop 24 * 30-day grid — the sql/43 accuracy grain
BAND_DAYS = 2100  # ~5 delete chunks across the ~30-yr horizon


def superseded_reports(cur) -> list[str]:
    cur.execute(
        "SELECT report_name FROM curated.intel_available_reports() "
        "WHERE NOT is_latest ORDER BY report_name")
    return [r[0] for r in cur.fetchall()]


def trim_report(conn, report: str, dry_run: bool) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(MAX(forecast_day), 0),"
            "       COUNT(*) FILTER (WHERE forecast_day > %s),"
            "       COUNT(*) FILTER (WHERE forecast_day <= %s) "
            "FROM raw_intel.production_forecast WHERE report_name = %s",
            (KEEP_MAX_DAY, KEEP_MAX_DAY, report))
        max_day, n_drop, n_keep = cur.fetchone()
    print(f"  {report}: keep(mop<=24)={n_keep:,}  drop(mop>24)={n_drop:,}  max_day={max_day}",
          flush=True)
    if dry_run or n_drop == 0:
        return

    hi = max_day
    while hi > KEEP_MAX_DAY:
        lo = max(KEEP_MAX_DAY, hi - BAND_DAYS)
        t0 = time.monotonic()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM raw_intel.production_forecast "
                "WHERE report_name = %s AND forecast_day > %s AND forecast_day <= %s",
                (report, lo, hi))
            n = cur.rowcount
        conn.commit()
        print(f"    deleted forecast_day ({lo}, {hi}]: {n:,} rows in "
              f"{time.monotonic() - t0:.0f}s", flush=True)
        hi = lo
        settle(5)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE forecast_day > %s) "
            "FROM raw_intel.production_forecast WHERE report_name = %s",
            (KEEP_MAX_DAY, report))
        remaining, leftover = cur.fetchone()
    status = "[OK]" if leftover == 0 and remaining == n_keep else "[MISMATCH]"
    print(f"    remaining={remaining:,} (expect {n_keep:,}), mop>24 leftover={leftover} {status}",
          flush=True)
    if status != "[OK]":
        raise SystemExit(f"trim verification failed for {report}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--report", help="one report_name to trim")
    g.add_argument("--all-superseded", action="store_true",
                   help="every non-latest report per basin family")
    ap.add_argument("--dry-run", action="store_true", help="counts only, no deletes")
    ap.add_argument("--skip-vacuum", action="store_true")
    args = ap.parse_args()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            reports = [args.report] if args.report else superseded_reports(cur)
            if not reports:
                print("no superseded reports in raw_intel — nothing to trim")
                return
            latest_guard = superseded_reports(cur)
        for r in reports:
            if r not in latest_guard:
                raise SystemExit(
                    f"{r} is a LATEST vintage (or unknown) — refusing to trim")
        print(f"[1/3] trim {len(reports)} superseded report(s) to mop<=24", flush=True)
        for r in reports:
            trim_report(conn, r, args.dry_run)

        if args.dry_run:
            return

        print("[2/3] verify sql/43 accuracy grain unaffected (refresh + counts)", flush=True)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT report_version, COUNT(DISTINCT api10) "
                        "FROM curated.intel_forecast_accuracy_vintage "
                        "WHERE tier = 'direct' GROUP BY 1 ORDER BY 1")
            before = cur.fetchall()
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY "
                        "curated.intel_forecast_accuracy_vintage")
            cur.execute("SELECT report_version, COUNT(DISTINCT api10) "
                        "FROM curated.intel_forecast_accuracy_vintage "
                        "WHERE tier = 'direct' GROUP BY 1 ORDER BY 1")
            after = cur.fetchall()
        print(f"    direct wells per vintage before={before} after={after} "
              f"{'[OK]' if before == after else '[MISMATCH]'}", flush=True)
        if before != after:
            raise SystemExit("sql/43 counts changed after trim — investigate")

        if not args.skip_vacuum:
            print("[3/3] VACUUM (ANALYZE) raw_intel.production_forecast "
                  "(non-blocking; makes freed space reusable)", flush=True)
            t0 = time.monotonic()
            with conn.cursor() as cur:
                cur.execute("VACUUM (ANALYZE) raw_intel.production_forecast")
            print(f"    vacuum done in {time.monotonic() - t0:.0f}s", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
