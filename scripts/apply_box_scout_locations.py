"""curated.box_scout_locations (sql/69): the land-facing flat BOX + econ view (Supabase).

One row per stick location with its BOX record-run forecast and Steven's default-deck
(wti70_hh3) econ, for analyst_ro / GIS (Michael 2026-10-21). Plain VIEW: no storage, no
refresh, always current with the record run and Steven's latest push.

  --dry-run (READ ONLY, creates nothing): runs every validation below against sql/69's
     SELECT inline, inside a read-only transaction.

  (no flag) — DDL on the shared warehouse, explicit go (cheap: a view, no data built):
     1. sql/69  DROP VIEW IF EXISTS + CREATE VIEW + GRANT analyst_ro + COMMENTs.
     2. validate (same checks, on the view): row identity vs erebor_locations, unique
        stick_id, forecast rows == the record run's forecast PUDs on the map, EUR tie-out,
        no EUR on a location without a forecast, priced rows == Steven's case, class tally,
        analyst_ro SELECT, EXPLAIN bbox rides idx_erebor_locations_geom, timings.

`recreate(cur)` is the hook for every script that executes sql/22: that DROP ... CASCADE of
curated.erebor_locations drops this view too (tests/test_box_scout_locations.py enforces
the hook).

Run from repo root in the venv:
    python -m scripts.apply_box_scout_locations --dry-run
    python -m scripts.apply_box_scout_locations            # !! Supabase DDL — Michael's go
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"
SQL69 = "69_box_scout_locations.sql"
VIEW = "curated.box_scout_locations"
FORECAST = "('covered', 'covered_provisional')"
# ~1 township in Reeves County: the GIS bbox predicate the land team's tools issue
BBOX = "ST_MakeEnvelope(-103.75, 31.35, -103.65, 31.45, 4326)"


def sql69() -> str:
    return (SQL / SQL69).read_text(encoding="utf-8")


def recreate(cur) -> None:
    """Re-create the view after anything that DROP-CASCADEs curated.erebor_locations (sql/22)."""
    cur.execute(sql69())


def view_body(text: str) -> str:
    """sql/69's SELECT (the view body), for the read-only dry run."""
    m = re.search(rf"CREATE VIEW {re.escape(VIEW)} AS\n(.*?);\s*\n", text, re.DOTALL)
    if not m:
        raise RuntimeError("sql/69 view body not found")
    return m.group(1)


def checks(src: str) -> list[tuple[str, str]]:
    """(label, SQL) pairs over `src` (the view name, or the inline body as a subquery)."""
    rec = "(SELECT run_id FROM box.forecast_run WHERE is_record)"
    return [
        ("rows", f"SELECT count(*), count(DISTINCT stick_id) FROM {src} v"),
        ("map stick locations", "SELECT count(*) FROM curated.erebor_locations WHERE category <> 'PDP'"),
        ("forecast rows", f"SELECT count(*) FROM {src} v WHERE v.box_tier IS NOT NULL"),
        ("record-run forecast PUDs on the map",
         (f"SELECT count(*) FROM box.pud_forecast bp JOIN curated.erebor_locations el ON el.stick_id = bp.stick_id "
          f"WHERE bp.run_id = {rec} AND bp.coverage IN {FORECAST} AND el.category <> 'PDP'")),
        ("record-run forecast PUDs missing from the map",
         (f"SELECT count(*) FROM box.pud_forecast bp WHERE bp.run_id = {rec} AND bp.coverage IN {FORECAST} "
          "AND NOT EXISTS (SELECT 1 FROM curated.erebor_locations el WHERE el.stick_id = bp.stick_id)")),
        ("oil EUR view vs box (MMbbl)",
         (f"SELECT round((SELECT sum(oil_eur_bbl) FROM {src} v)::numeric / 1e6, 3), "
          f"round((SELECT sum(s.eur) FROM box.pud_forecast_stream s JOIN box.pud_forecast bp "
          f"ON bp.run_id = s.run_id AND bp.location_id = s.location_id "
          f"JOIN curated.erebor_locations el ON el.stick_id = bp.stick_id "
          f"WHERE s.run_id = {rec} AND s.stream = 'oil' AND el.category <> 'PDP')::numeric / 1e6, 3)")),
        ("EUR on a location without a forecast (must be 0)",
         (f"SELECT count(*) FROM {src} v WHERE v.box_tier IS NULL "
          "AND (v.oil_eur_bbl IS NOT NULL OR v.gas_eur_mcf IS NOT NULL OR v.water_eur_bbl IS NOT NULL)")),
        ("forecast location without oil EUR (must be 0)",
         f"SELECT count(*) FROM {src} v WHERE v.box_tier IS NOT NULL AND v.oil_eur_bbl IS NULL"),
        ("priced rows, deck, assumption set",
         (f"SELECT count(*) FILTER (WHERE v.econ_deck_id IS NOT NULL), min(v.econ_deck_id), "
          f"min(v.econ_assumption_set_id), count(DISTINCT v.econ_assumption_set_id) FROM {src} v")),
        ("class tally", f"SELECT v.basin, v.box_coverage, count(*) FROM {src} v GROUP BY 1, 2 ORDER BY 1, 3 DESC"),
    ]


def run_checks(cur, src: str) -> bool:
    ok = True
    res: dict[str, list] = {}
    for label, q in checks(src):
        t = time.monotonic()
        rows = cur.execute(q).fetchall()
        res[label] = rows
        print(f"    {label} ({time.monotonic() - t:.1f}s): {rows if len(rows) > 1 else rows[0]}", flush=True)

    def need(cond: bool, what: str) -> None:
        nonlocal ok
        print(f"    {'OK  ' if cond else 'FAIL'} {what}", flush=True)
        ok &= cond

    n, n_distinct = res["rows"][0]
    need(n == res["map stick locations"][0][0], "rows == erebor_locations stick locations (category <> 'PDP')")
    need(n == n_distinct, "stick_id unique")
    need(res["forecast rows"][0][0] == res["record-run forecast PUDs on the map"][0][0],
         "forecast rows == the record run's forecast PUDs on the map")
    v_oil, b_oil = res["oil EUR view vs box (MMbbl)"][0]
    need(v_oil == b_oil, "oil EUR ties to box.pud_forecast_stream exactly")
    need(res["EUR on a location without a forecast (must be 0)"][0][0] == 0, "no EUR without a forecast (never zero, D67)")
    need(res["forecast location without oil EUR (must be 0)"][0][0] == 0, "every forecast location carries oil EUR")
    priced, deck, _aset, n_aset = res["priced rows, deck, assumption set"][0]
    need(deck in (None, "wti70_hh3") and n_aset <= 1, "one econ case: wti70_hh3, one assumption set")
    print(f"    note: {priced:,} priced locations; record-run forecast PUDs missing from the map: "
          f"{res['record-run forecast PUDs missing from the map'][0][0]}", flush=True)

    plan = [r[0] for r in cur.execute(
        f"EXPLAIN SELECT stick_id, oil_eur_bbl_per_ft, pv10_mm FROM {src} v WHERE v.geom && {BBOX}").fetchall()]
    need(any("idx_erebor_locations_geom" in line for line in plan), "bbox filter rides idx_erebor_locations_geom")
    for label, q in (("full scan", f"SELECT count(*), count(pv10_mm) FROM {src} v"),
                     ("township bbox", f"SELECT count(*), count(pv10_mm) FROM {src} v WHERE v.geom && {BBOX}")):
        t = time.monotonic()
        r = cur.execute(q).fetchone()
        print(f"    timing {label}: {time.monotonic() - t:.2f}s {r}", flush=True)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="validate sql/69's body read-only; create nothing")
    args = ap.parse_args()
    t0 = time.monotonic()
    conn = get_connection()
    try:
        if args.dry_run:
            print("[dry-run] READ ONLY: sql/69 body inline, nothing created", flush=True)
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                ok = run_checks(cur, f"({view_body(sql69())})")
            conn.rollback()
        else:
            conn.autocommit = True
            with conn.cursor() as cur:
                print(f"[1/2] sql/69: create {VIEW} + grant + comments", flush=True)
                recreate(cur)
                print("[2/2] validate", flush=True)
                ok = run_checks(cur, VIEW)
                ro = cur.execute(f"SELECT has_table_privilege('analyst_ro', '{VIEW}', 'SELECT')").fetchone()[0]
                print(f"    {'OK  ' if ro else 'FAIL'} analyst_ro can SELECT", flush=True)
                ok &= bool(ro)
    finally:
        conn.close()
    print(f"=== {'OK' if ok else 'FAILED'} in {time.monotonic() - t0:.0f}s ===", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
