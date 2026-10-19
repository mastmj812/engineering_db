"""Apply sql/62 (BOX water stream, plan step 12b; D107-D110) and verify it.

  1. sql/62: box.pud_forecast_stream admits stream 'water' + a per-stream tier (validated | provisional; required on water; never
     above the location's coverage); new box.location_water_analog.
  2. Validate by identity: the named constraints exist; no generated stream CHECK from sql/60 is left; every existing stream row
     reads tier NULL; stream-row counts per (run, stream) unchanged; location_water_analog exists, empty, readable by analyst_ro.
  3. Smoke inside a transaction that is ROLLED BACK, on a throwaway bench + run:
       - a covered location with a validated water row, its 600 months and a water analog inserts; a covered_provisional location
         with a provisional water row inserts
       - each of these is refused:
           - a water row without a tier
           - a VALIDATED water row on a covered_provisional location
           - an unknown stream ('condensate') / an unknown tier value
           - a water analog with an unknown water_label

!! DDL on the shared warehouse: explicit authorization ("go apply") required. From repo root:
    python -m scripts.apply_box_water
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from psycopg import errors
from psycopg.types.json import Jsonb

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "62_box_water_stream.sql"
NAMED = ("box_pud_forecast_stream_stream_ck", "box_pud_forecast_stream_tier_ck", "box_pud_forecast_stream_water_tier_ck",
         "box_pud_forecast_stream_tier_le_coverage_ck")
_GENERATED = re.compile(r"^CHECK \(\(?stream (=|= ANY)")
_COUNTS = "SELECT run_id, stream, count(*) FROM box.pud_forecast_stream GROUP BY 1, 2 ORDER BY 1, 2"
_SQUARE = "MULTIPOLYGON(((-103.9 31.9,-103.8 31.9,-103.8 32.0,-103.9 32.0,-103.9 31.9)))"
_STICK = "LINESTRING(-103.88 31.95,-103.82 31.95)"

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(conn) -> list[tuple]:
    print("[1/3] sql/62: water stream", flush=True)
    with conn.cursor() as cur:
        before = cur.execute(_COUNTS).fetchall()
        cur.execute(SQL.read_text(encoding="utf-8"))
    conn.commit()
    return before


def validate(conn, before: list[tuple]) -> None:
    print("[2/3] validate", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        have = {r[0]: r[1] for r in q("""SELECT k.conname, pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                                         JOIN pg_namespace n ON n.oid = c.relnamespace
                                         WHERE n.nspname = 'box' AND c.relname = 'pud_forecast_stream' AND k.contype = 'c'""").fetchall()}
        for nm in NAMED:
            _check(nm in have, f"box.pud_forecast_stream: {nm}")
        _check("water" in have.get("box_pud_forecast_stream_stream_ck", ""), "stream CHECK admits water")
        stale = [k for k, d in have.items() if k not in NAMED and _GENERATED.match(d)]
        _check(not stale, f"no generated stream CHECK left ({stale or 'none'})")
        _check(q("SELECT count(*) FROM box.pud_forecast_stream WHERE tier IS NOT NULL").fetchone()[0] == 0, "every existing stream row reads tier NULL")
        _check(q(_COUNTS).fetchall() == before, "stream-row counts per (run, stream) unchanged by identity")
        _check(q("SELECT count(*) FROM box.location_water_analog").fetchone()[0] == 0, "box.location_water_analog exists and is empty")
        _check(q("SELECT has_table_privilege('analyst_ro', 'box.location_water_analog', 'SELECT')").fetchone()[0], "analyst_ro can read it")
    conn.rollback()


def _refused(q, stmt: str, params: tuple, err, msg: str) -> None:
    q("SAVEPOINT s")
    try:
        q(stmt, params)
        _check(False, f"{msg} was ALLOWED")
    except err:
        q("ROLLBACK TO SAVEPOINT s")
        _check(True, f"{msg} is refused")


_PF = ("INSERT INTO box.pud_forecast (run_id, location_id, stick_id, basin, bench, formation_blueox, recon_status, coverage, inside_extent, extent_id, "
       "completed_lateral_ft, planned_spacing_ft, spacing_source, search_mode, radius_mi, radius_class, n_analogs) "
       "VALUES (%s, %s, %s, 'delaware', '_APPLY_SMOKE', 'WCA_1', 'remaining_pud', %s, true, %s, 10000, 880, 'neighbour_gap', 'circle', 5, '5 mi ring', 12)")
_ST = ("INSERT INTO box.pud_forecast_stream (run_id, location_id, coverage, stream, tier, params, lateral_mult, eur_haircut, eur_raw, eur, eur_per_kft) "
       "VALUES (%s, %s, %s, %s, %s, '{}'::jsonb, 10, 1.0, 600, 600, 60)")
_WA = ("INSERT INTO box.location_water_analog (run_id, location_id, coverage, api10, rank, dist_ft, state_code, water_label) "
       "VALUES (%s, %s, %s, %s, %s, 1000, '30', %s)")


def smoke(conn) -> None:
    print("[3/3] smoke (rolled back)", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        try:
            q("INSERT INTO box.bench_scope (basin, bench, in_scope, reason, decided_on) VALUES ('delaware', '_APPLY_SMOKE', true, 'apply smoke', current_date)")
            eid = q("INSERT INTO box.extent (basin, bench, version, source, geom) VALUES ('delaware', '_APPLY_SMOKE', 999, 'generated', "
                    "extensions.ST_GeomFromText(%s, 4326)) RETURNING extent_id", (_SQUARE,)).fetchone()[0]
            loc = [q("INSERT INTO box.location (basin, formation_blueox, geom, lateral_ft, first_seen_vintage, last_seen_vintage) "
                     "VALUES ('delaware', 'WCA_1', extensions.ST_GeomFromText(%s, 4326), 10000, '_SMOKE', '_SMOKE') RETURNING location_id", (_STICK,)).fetchone()[0]
                   for _ in range(2)]
            run = q("INSERT INTO box.forecast_run (spec, code_sha, engine_sha, dealintake_config, report_version, data_through, haircut, calendar_factor, disclosure) "
                    "VALUES ('box_v2_wf', 'smoke', 'smoke', 11, '_SMOKE', '2026-07-01', %s, %s, %s) RETURNING run_id",
                    (Jsonb({"oil": {}, "gas": {}}), Jsonb({"oil": [], "gas": []}), Jsonb({"hindcast_bias": {}, "radius_ranges": {}}))).fetchone()[0]
            q(_PF, (run, loc[0], -1, "covered", eid))
            q(_PF, (run, loc[1], -2, "covered_provisional", eid))
            q(_ST, (run, loc[0], "covered", "water", "validated"))
            q("INSERT INTO box.pud_forecast_month (run_id, location_id, stream, month_no, volume) SELECT %s, %s, 'water', m, 1 FROM generate_series(1, 600) m",
              (run, loc[0]))
            q(_WA, (run, loc[0], "covered", "3001500000", 1, "measured"))
            q(_ST, (run, loc[1], "covered_provisional", "water", "provisional"))
            _check(q("SELECT count(*) FROM box.pud_forecast_month WHERE run_id = %s AND stream = 'water'", (run,)).fetchone()[0] == 600
                   and q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'water'", (run,)).fetchone()[0] == 2,
                   "validated water (covered) + provisional water (covered_provisional) insert, with 600 months and a water analog")
            q("DELETE FROM box.pud_forecast_stream WHERE run_id = %s AND location_id = %s AND stream = 'water'", (run, loc[1]))
            _refused(q, _ST, (run, loc[1], "covered_provisional", "water", None), errors.CheckViolation, "a water row without a tier")
            _refused(q, _ST, (run, loc[1], "covered_provisional", "water", "validated"), errors.CheckViolation,
                     "a VALIDATED water row on a covered_provisional location")
            _refused(q, _ST, (run, loc[1], "covered_provisional", "condensate", "provisional"), errors.CheckViolation, "an unknown stream")
            _refused(q, _ST, (run, loc[1], "covered_provisional", "water", "sort_of"), errors.CheckViolation, "an unknown tier value")
            _refused(q, _WA, (run, loc[0], "covered", "3001500001", 2, "guessed"), errors.CheckViolation, "a water analog with an unknown water_label")
        finally:
            conn.rollback()


def main() -> None:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    conn = get_connection()
    try:
        before = apply_sql(conn)
        validate(conn, before)
        smoke(conn)
    finally:
        conn.close()
    if _failures:
        sys.exit(f"{len(_failures)} check(s) FAILED")
    print("all checks passed", flush=True)


if __name__ == "__main__":
    main()
