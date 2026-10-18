"""Apply sql/63 (D105: BOX provisional coverage tier) and verify it.

  1. sql/63: coverage value covered_provisional on box.pud_forecast (+ its covered / uncovered / inside constraints), the child
     tables (pud_forecast_stream, location_analog) and box_econ.box_pud_econ; box.bench_scope.validation (validated | provisional).
  2. Validate by identity: the named constraints exist with the new value lists; no generated coverage CHECK from sql/60 / sql/61
     is left behind; bench_scope.validation exists, every existing row reads 'validated'; live coverage counts unchanged.
  3. Smoke inside a transaction that is ROLLED BACK, on a throwaway bench + run:
       - a covered_provisional location with a stream row, an analog row and a priced econ row (all stating the tier) inserts
       - each of these is refused:
           - a covered_provisional row without its search description
           - a stream row left at the default coverage 'covered' for a provisional location (FK)
           - an unknown coverage value
           - an unknown bench_scope.validation value

!! DDL on the shared warehouse: explicit authorization ("go apply") required. From repo root:
    python -m scripts.apply_box_provisional
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from psycopg import errors
from psycopg.types.json import Jsonb

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "63_box_provisional_coverage.sql"
NAMED = {("box", "pud_forecast"): ("box_pud_forecast_coverage_tier_ck", "box_pud_forecast_covered_ck", "box_pud_forecast_uncovered_ck",
                                    "box_pud_forecast_inside_ck"),
         ("box", "pud_forecast_stream"): ("box_pud_forecast_stream_coverage_tier_ck",),
         ("box", "location_analog"): ("box_location_analog_coverage_tier_ck",),
         ("box_econ", "box_pud_econ"): ("box_pud_econ_coverage_tier_ck",),
         ("box", "bench_scope"): ("box_bench_scope_validation_ck",)}
_SQUARE = "MULTIPOLYGON(((-103.9 31.9,-103.8 31.9,-103.8 32.0,-103.9 32.0,-103.9 31.9)))"
_STICK = "LINESTRING(-103.88 31.95,-103.82 31.95)"
_GENERATED = re.compile(r"^CHECK \(\(?coverage (=|= ANY)")  # the sql/60 / sql/61 inline column CHECKs (same test as sql/63)
_COUNTS = "SELECT run_id, coverage, count(*) FROM box.pud_forecast GROUP BY 1, 2 ORDER BY 1, 2"

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(conn) -> list[tuple]:
    print("[1/3] sql/63: covered_provisional tier", flush=True)
    with conn.cursor() as cur:
        before = cur.execute(_COUNTS).fetchall()
        cur.execute(SQL.read_text(encoding="utf-8"))
    conn.commit()
    return before


def validate(conn, before: list[tuple]) -> None:
    print("[2/3] validate", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        for (ns, rel), names in NAMED.items():
            have = {r[0]: r[1] for r in q("""SELECT k.conname, pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
                                             JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relname = %s AND k.contype = 'c'""",
                                          (ns, rel)).fetchall()}
            for nm in names:
                _check(nm in have and ("covered_provisional" in have[nm] or nm.endswith("validation_ck")), f"{ns}.{rel}: {nm}")
            stale = [k for k, d in have.items() if k not in names and _GENERATED.match(d)]
            _check(not stale, f"{ns}.{rel}: no generated coverage CHECK left ({stale or 'none'})")
        _check(q("SELECT count(*) FROM information_schema.columns WHERE table_schema = 'box' AND table_name = 'bench_scope' AND column_name = 'validation'")
               .fetchone()[0] == 1, "box.bench_scope.validation exists")
        _check(q("SELECT count(*) FROM box.bench_scope WHERE validation <> 'validated'").fetchone()[0] == 0, "every existing bench reads 'validated'")
        _check(q(_COUNTS).fetchall() == before, "box.pud_forecast coverage counts unchanged by identity")
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
       "VALUES (%s, %s, %s, 'delaware', '_APPLY_SMOKE', 'AVA_0', 'remaining_pud', %s, true, %s, %s, %s, %s, %s, %s, %s, %s)")
_ST = ("INSERT INTO box.pud_forecast_stream (run_id, location_id, stream, params, lateral_mult, eur_haircut, eur_raw, eur, eur_per_kft{c}) "
       "VALUES (%s, %s, '{s}', '{{}}'::jsonb, 10, 1.0, 500000, 500000, 50000{v})")


def smoke(conn) -> None:
    print("[3/3] smoke (rolled back)", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        try:
            q("INSERT INTO box.bench_scope (basin, bench, in_scope, reason, decided_on, validation) "
              "VALUES ('delaware', '_APPLY_SMOKE', true, 'apply smoke', current_date, 'provisional')")
            eid = q("INSERT INTO box.extent (basin, bench, version, source, geom) VALUES ('delaware', '_APPLY_SMOKE', 999, 'generated', "
                    "extensions.ST_GeomFromText(%s, 4326)) RETURNING extent_id", (_SQUARE,)).fetchone()[0]
            loc = [q("INSERT INTO box.location (basin, formation_blueox, geom, lateral_ft, first_seen_vintage, last_seen_vintage) "
                     "VALUES ('delaware', 'AVA_0', extensions.ST_GeomFromText(%s, 4326), 10000, '_SMOKE', '_SMOKE') RETURNING location_id", (_STICK,)).fetchone()[0]
                   for _ in range(3)]
            run = q("INSERT INTO box.forecast_run (spec, code_sha, engine_sha, dealintake_config, report_version, data_through, haircut, calendar_factor, disclosure) "
                    "VALUES ('box_v2_wf', 'smoke', 'smoke', 11, '_SMOKE', '2026-07-01', %s, %s, %s) RETURNING run_id",
                    (Jsonb({"oil": {}, "gas": {}}), Jsonb({"oil": [], "gas": []}), Jsonb({"hindcast_bias": {}, "radius_ranges": {}}))).fetchone()[0]
            full = (10000, 880, "neighbour_gap", "circle", 5, "5 mi ring", 12)
            q(_PF, (run, loc[0], -1, "covered_provisional", eid, *full))
            q(_ST.format(c=", coverage", v=", 'covered_provisional'", s="oil"), (run, loc[0]))
            q("INSERT INTO box.location_analog (run_id, location_id, api10, rank, coverage) VALUES (%s, %s, '3001500000', 1, 'covered_provisional')", (run, loc[0]))
            q("INSERT INTO box_econ.box_pud_econ (run_id, location_id, deck_id, assumption_set_id, downtime_basis, wti, hh, pv10_mm, oil_eur, gas_eur, "
              "build_id, schema_version, built_at, coverage) VALUES (%s, %s, 'wti70', 'smoke', 'steven_downtime_factor', 70, 3, 5.0, 500000, NULL, 'smoke', "
              "'1.0.0', now(), 'covered_provisional')", (run, loc[0]))
            _check(q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND coverage = 'covered_provisional'", (run,)).fetchone()[0] == 1,
                   "a covered_provisional location carries stream + analog + priced econ rows")
            _refused(q, _PF, (run, loc[1], -2, "covered_provisional", eid, 10000, 880, "neighbour_gap", None, None, None, None), errors.CheckViolation,
                     "a covered_provisional row without its search description")
            _refused(q, _ST.format(c="", v="", s="gas"), (run, loc[0]), errors.ForeignKeyViolation,
                     "a stream row left at coverage 'covered' for a provisional location")
            _refused(q, _PF, (run, loc[2], -3, "covered_maybe", eid, *full), errors.CheckViolation, "an unknown coverage value")
            _refused(q, "UPDATE box.bench_scope SET validation = 'sort_of' WHERE bench = '_APPLY_SMOKE'", (), errors.CheckViolation,
                     "an unknown bench_scope.validation value")
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
