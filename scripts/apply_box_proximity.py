"""Apply sql/64 (D112-D116: BOX PDP-proximity layer) and verify it.

  1. sql/64: coverage value not_covered_no_precedent (+ its uncovered / no-precedent constraints), pud_forecast_stream.prox_factor
     with the amended eur identity, box.pud_proximity, box.pud_proximity_parent.
  2. Validate by identity: the named constraints / tables / column exist; every existing stream row reads prox_factor 1 and still
     satisfies eur = eur_raw x eur_haircut x prox_factor; stream and pud_forecast counts unchanged; the new tables are empty and
     analyst_ro can read them.
  3. Smoke inside a transaction that is ROLLED BACK, on a throwaway bench + run:
       - a haircut PUD (oil prox_factor 0.75, eur scaled) with its proximity + parent rows, and a no-precedent PUD (search provenance,
         no stream) with its proximity row, insert
       - each of these is refused:
           - a stream row for a not_covered_no_precedent location (FK)
           - prox_factor != 1 on a gas row
           - an oil eur that ignores prox_factor
           - a no-forecast proximity outcome on a covered location
           - a haircut proximity row without its label
           - a not_covered_no_precedent row without search provenance

!! DDL on the shared warehouse: explicit authorization ("go apply") required. From repo root:
    python -m scripts.apply_box_proximity
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from psycopg import errors
from psycopg.types.json import Jsonb

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "64_box_proximity.sql"
NAMED = {("box", "pud_forecast"): ("box_pud_forecast_coverage_tier_ck", "box_pud_forecast_uncovered_ck", "box_pud_forecast_no_precedent_ck"),
         ("box", "pud_forecast_stream"): ("box_pud_forecast_stream_prox_factor_ck", "box_pud_forecast_stream_eur_ck"),
         ("box", "pud_proximity"): ("box_pud_proximity_coverage_ck", "box_pud_proximity_as_is_ck", "box_pud_proximity_multi_ck",
                                    "box_pud_proximity_label_ck", "box_pud_proximity_unexposed_ck")}
_SQUARE = "MULTIPOLYGON(((-103.9 31.9,-103.8 31.9,-103.8 32.0,-103.9 32.0,-103.9 31.9)))"
_STICK = "LINESTRING(-103.88 31.95,-103.82 31.95)"
_COUNTS = ("SELECT 'pf', run_id::text, coverage, count(*) FROM box.pud_forecast GROUP BY 2, 3 "
           "UNION ALL SELECT 'st', run_id::text, stream, count(*) FROM box.pud_forecast_stream GROUP BY 2, 3 ORDER BY 1, 2, 3")

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(conn) -> list[tuple]:
    print("[1/3] sql/64: PDP-proximity layer", flush=True)
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
                _check(nm in have, f"{ns}.{rel}: {nm}")
        tier = q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'box_pud_forecast_coverage_tier_ck'").fetchone()
        _check(bool(tier) and "not_covered_no_precedent" in tier[0], "coverage CHECK admits not_covered_no_precedent")
        eur = q("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'box_pud_forecast_stream_eur_ck'").fetchone()
        _check(bool(eur) and "prox_factor" in eur[0], "eur identity includes prox_factor")
        _check(q("SELECT count(*) FROM box.pud_forecast_stream WHERE prox_factor <> 1").fetchone()[0] == 0, "every existing stream row reads prox_factor 1")
        for t in ("pud_proximity", "pud_proximity_parent"):
            _check(q(f"SELECT count(*) FROM box.{t}").fetchone()[0] == 0, f"box.{t} exists and is empty")
            _check(q("SELECT has_table_privilege('analyst_ro', %s, 'SELECT')", (f"box.{t}",)).fetchone()[0], f"analyst_ro can read box.{t}")
        _check(q(_COUNTS).fetchall() == before, "pud_forecast coverage + stream counts unchanged by identity")
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
       "VALUES (%s, %s, %s, 'delaware', '_APPLY_SMOKE', 'BS3_S', 'remaining_pud', %s, true, %s, %s, %s, %s, %s, %s, %s, %s)")
_ST = ("INSERT INTO box.pud_forecast_stream (run_id, location_id, stream, params, lateral_mult, eur_haircut, eur_raw, eur, eur_per_kft, prox_factor, coverage) "
       "VALUES (%s, %s, %s, '{}'::jsonb, 10, 1.0, 500000, %s, 50000, %s, %s)")
_PX = ("INSERT INTO box.pud_proximity (run_id, location_id, coverage, config_class, n_same, n_topfill, n_underfill, n_parents_total, flanked_topfill, "
       "outcome, factor, haircut_key, pair_key, prec_multi, prec_package, label, table_ref) "
       "VALUES (%s, %s, %s, 'topfill', 0, 3, 0, 3, true, %s, %s, 'k2:topfill|3+|F', 'BS3_S>topfill>WCA', 88, %s, %s, 'smoke')")


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
                     "VALUES ('delaware', 'BS3_S', extensions.ST_GeomFromText(%s, 4326), 10000, '_SMOKE', '_SMOKE') RETURNING location_id", (_STICK,)).fetchone()[0]
                   for _ in range(4)]
            run = q("INSERT INTO box.forecast_run (spec, code_sha, engine_sha, dealintake_config, report_version, data_through, haircut, calendar_factor, disclosure) "
                    "VALUES ('box_v2_wf', 'smoke', 'smoke', 11, '_SMOKE', '2026-07-01', %s, %s, %s) RETURNING run_id",
                    (Jsonb({"oil": {}, "gas": {}}), Jsonb({"oil": [], "gas": []}), Jsonb({"hindcast_bias": {}, "radius_ranges": {}}))).fetchone()[0]
            full = (10000, 880, "neighbour_gap", "circle", 5, "5 mi ring", 12)
            q(_PF, (run, loc[0], -1, "covered_provisional", eid, *full))
            q(_ST, (run, loc[0], "oil", 375000, 0.75, "covered_provisional"))
            q(_ST, (run, loc[0], "gas", 500000, 1.0, "covered_provisional"))
            q(_PX, (run, loc[0], "covered_provisional", "haircut", 0.75, 69, "validated_with_exception"))
            q("INSERT INTO box.pud_proximity_parent (run_id, location_id, api10, cls, parent_bench, dv_ft, dh_ft, dxy_ft, overlap, age_days) "
              "VALUES (%s, %s, '4238900000', 'topfill', 'WCA_1', 340, 450, -450, 0.92, 1400)", (run, loc[0]))
            q(_PF, (run, loc[1], -2, "not_covered_no_precedent", eid, *full))
            q(_PX, (run, loc[1], "not_covered_no_precedent", "no_forecast_package", 0.75, 13, None))
            _check(q("SELECT count(*) FROM box.pud_proximity WHERE run_id = %s", (run,)).fetchone()[0] == 2,
                   "a haircut PUD (oil x 0.75, proximity + parent rows) and a no-precedent PUD (search kept, no stream) insert")
            _refused(q, _ST, (run, loc[1], "oil", 500000, 1.0, "covered"), errors.ForeignKeyViolation,
                     "a stream row for a not_covered_no_precedent location")
            _refused(q, "UPDATE box.pud_forecast_stream SET prox_factor = 0.9, eur = 450000 WHERE run_id = %s AND location_id = %s AND stream = 'gas'",
                     (run, loc[0]), errors.CheckViolation, "prox_factor != 1 on a gas row")
            _refused(q, "UPDATE box.pud_forecast_stream SET eur = 500000 WHERE run_id = %s AND location_id = %s AND stream = 'oil'",
                     (run, loc[0]), errors.CheckViolation, "an oil eur that ignores prox_factor")
            q(_PF, (run, loc[2], -3, "covered_provisional", eid, *full))
            _refused(q, _PX, (run, loc[2], "covered_provisional", "no_forecast_package", 0.75, 13, None), errors.CheckViolation,
                     "a no-forecast proximity outcome on a covered location")
            _refused(q, _PX, (run, loc[2], "covered_provisional", "haircut", 0.75, 69, None), errors.CheckViolation,
                     "a haircut proximity row without its label")
            _refused(q, _PF, (run, loc[3], -4, "not_covered_no_precedent", eid, 10000, 880, "neighbour_gap", None, None, None, None),
                     errors.CheckViolation, "a not_covered_no_precedent row without search provenance")
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
