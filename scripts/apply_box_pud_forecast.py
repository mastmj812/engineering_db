"""Apply sql/60 (BOX step 7b: locations, crosswalk, production runs, coverage-classed PUD forecasts, analogs) and verify it.

  1. sql/60: box.location, location_source, forecast_run, pud_forecast, pud_forecast_stream, pud_forecast_month,
     location_analog; indexes; the analyst_ro grant; comments; the D66 SUPERSEDED prefix on the step-4/5 tables.
     Needs sql/54 (+ 57 / 58 for the D66 prefix) live.
  2. Validate by identity:
       - every table, PK and named index exists; analyst_ro reads all seven
       - anon / authenticated have no USAGE on box, and the ETL never names schema box
       - the D66 prefix sits exactly once on each superseded table (re-applying doesn't stack it)
       - EXPLAIN: a geography DWithin on box.location can use box_location_geog_gix
  3. Smoke inside a transaction that is ROLLED BACK, on a throwaway bench + extent: one covered and one
     not-covered location, with stream, month and analog rows. Then each guard has to refuse what it should:
       - a covered row with no analog count (the NULL trap)
       - a covered row with 2 analogs
       - a WCXY row that carries a search
       - a radius class that disagrees with the radius
       - a stream row or an analog row for a not-covered location
       - eur != eur_raw x eur_haircut
       - month 601
       - a run without a gas haircut
       - a second record run
       - the same Novi stick twice in one run or one vintage
       - a covered row outside the extent
     Deleting a run cascades through every child table.

!! DDL on the shared warehouse: explicit authorization ("go apply") required. From repo root:
    python -m scripts.apply_box_pud_forecast
"""

from __future__ import annotations

import sys
from pathlib import Path

from psycopg import errors
from psycopg.types.json import Jsonb

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "60_box_pud_forecast.sql"
TABLES = {
    "box.location": ("box_location_geom_gix", "box_location_geog_gix", "box_location_bench_ix"),
    "box.location_source": ("box_location_source_stick_uq",),
    "box.forecast_run": ("box_forecast_run_record_uq",),
    "box.pud_forecast": ("box_pud_forecast_stick_uq", "box_pud_forecast_cov_uq", "box_pud_forecast_location_ix", "box_pud_forecast_coverage_ix"),
    "box.pud_forecast_stream": (),
    "box.pud_forecast_month": (),
    "box.location_analog": ("box_location_analog_rank_uq", "box_location_analog_api10_ix"),
}
SUPERSEDED = ("box.tc_area", "box.type_curve", "box.tc_member", "box.risk_factor")
_TAG = "SUPERSEDED (D54/D57/D66"
_SQUARE = "MULTIPOLYGON(((-103.9 31.9,-103.8 31.9,-103.8 32.0,-103.9 32.0,-103.9 31.9)))"
_STICK = "LINESTRING(-103.88 31.95,-103.82 31.95)"

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(conn) -> None:
    print("[1/3] sql/60: box locations, runs, coverage-classed PUD forecasts, analogs", flush=True)
    with conn.cursor() as cur:
        cur.execute(SQL.read_text(encoding="utf-8"))
    conn.commit()


def validate(conn) -> None:
    print("[2/3] validate", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        for t, ixs in TABLES.items():
            _check(q("SELECT to_regclass(%s) IS NOT NULL", (t,)).fetchone()[0], f"{t} exists")
            _check(q("SELECT has_table_privilege('analyst_ro', %s, 'SELECT')", (t,)).fetchone()[0], f"analyst_ro reads {t}")
            _check(q("SELECT count(*) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'p'", (t,)).fetchone()[0] == 1, f"{t} has a primary key")
            have = {r[0] for r in q("SELECT indexname FROM pg_indexes WHERE schemaname = 'box' AND tablename = %s", (t.split(".")[1],)).fetchall()}
            for ix in ixs:
                _check(ix in have, f"index {ix}")
        for api_role in ("anon", "authenticated"):
            if q("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (api_role,)).fetchone()[0]:
                _check(not q("SELECT has_schema_privilege(%s, 'box', 'USAGE')", (api_role,)).fetchone()[0], f"{api_role} (Data API) has no USAGE on box")
        for t in SUPERSEDED:
            if q("SELECT to_regclass(%s) IS NOT NULL", (t,)).fetchone()[0]:
                c = q("SELECT coalesce(obj_description(%s::regclass, 'pg_class'), '')", (t,)).fetchone()[0]
                _check(c.count(_TAG) == 1, f"{t} carries the D66 SUPERSEDED prefix exactly once")
        q("SET LOCAL enable_seqscan = off")
        plan = "\n".join(r[0] for r in q("EXPLAIN SELECT location_id FROM box.location WHERE extensions.ST_DWithin(geom::extensions.geography, "
                                          "extensions.ST_GeogFromText('POINT(-103.85 31.95)'), 1609)").fetchall())
        _check("box_location_geog_gix" in plan, "EXPLAIN: geography DWithin on box.location uses box_location_geog_gix")
    conn.rollback()
    etl = (Path(__file__).resolve().parent.parent / "etl" / "db.py").read_text(encoding="utf-8")
    _check("box." not in etl, "etl/db.py never names schema box (ETL never touches it)")


_RUN = ("INSERT INTO box.forecast_run (spec, code_sha, engine_sha, dealintake_config, report_version, data_through, haircut, calendar_factor, disclosure, is_record) "
        "VALUES ('box_v2_wf', 'smoke', 'smoke', 11, '_SMOKE', '2026-07-01', %s, %s, %s, %s) RETURNING run_id")
_PF = ("INSERT INTO box.pud_forecast (run_id, location_id, stick_id, basin, bench, formation_blueox, recon_status, coverage, inside_extent, extent_id, "
       "completed_lateral_ft, planned_spacing_ft, spacing_source, search_mode, radius_mi, radius_class, n_analogs) "
       "VALUES (%s, %s, %s, 'delaware', '_APPLY_SMOKE', %s, 'remaining_pud', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
_ST = ("INSERT INTO box.pud_forecast_stream (run_id, location_id, stream, params, lateral_mult, eur_haircut, eur_raw, eur, eur_per_kft) "
       "VALUES (%s, %s, %s, '{}'::jsonb, 10.0, %s, %s, %s, %s / 10.0)")


def _refused(q, sql: str, params: tuple, err: type[Exception] | tuple[type[Exception], ...], msg: str) -> None:
    q("SAVEPOINT s")
    try:
        q(sql, params)
        _check(False, f"{msg} was ALLOWED")
    except err:
        q("ROLLBACK TO SAVEPOINT s")
        _check(True, f"{msg} is refused")


def smoke(conn) -> None:
    print("[3/3] smoke (rolled back)", flush=True)
    hc, cf = Jsonb({"oil": {"12": -0.05, "48": -0.10}, "gas": {"12": 0.02, "48": 0.0}}), Jsonb({"oil": [0.9], "gas": [0.9]})
    disc = Jsonb({"hindcast_bias": {}, "radius_ranges": {}})
    with conn.cursor() as cur:
        q = cur.execute
        try:
            q("INSERT INTO box.bench_scope (basin, bench, in_scope, reason, decided_on) VALUES ('delaware', '_APPLY_SMOKE', true, 'apply smoke', current_date)")
            eid = q("INSERT INTO box.extent (basin, bench, version, source, geom) "
                    "VALUES ('delaware', '_APPLY_SMOKE', 999, 'generated', extensions.ST_GeomFromText(%s, 4326)) RETURNING extent_id", (_SQUARE,)).fetchone()[0]
            loc = [q("INSERT INTO box.location (basin, formation_blueox, geom, lateral_ft, first_seen_vintage, last_seen_vintage) "
                     "VALUES ('delaware', %s, extensions.ST_GeomFromText(%s, 4326), 10000, '_SMOKE', '_SMOKE') RETURNING location_id", (f, _STICK)).fetchone()[0]
                   for f in ("WCA_1", "WCXY", "WCA_2")]
            q("INSERT INTO box.location_source (location_id, report_version, stick_id, match_method) VALUES (%s, '_SMOKE', -1, 'seed')", (loc[0],))
            _refused(q, "INSERT INTO box.location_source (location_id, report_version, stick_id, match_method) VALUES (%s, '_SMOKE', -1, 'seed')", (loc[1],),
                     errors.UniqueViolation, "one Novi stick on two locations in one vintage")
            _refused(q, "INSERT INTO box.location_source (location_id, report_version, stick_id, match_method) VALUES (%s, '_SMOKE', -2, 'overlap')", (loc[1],),
                     errors.CheckViolation, "an overlap match without its overlap share")
            has_record = q("SELECT EXISTS (SELECT 1 FROM box.forecast_run WHERE is_record)").fetchone()[0]
            run = q(_RUN, (hc, cf, disc, not has_record)).fetchone()[0]
            _refused(q, _RUN, (hc, cf, disc, True), errors.UniqueViolation, "a second record run")
            _refused(q, _RUN, (Jsonb({"oil": {}}), cf, disc, False), errors.CheckViolation, "a run without a gas haircut")
            # covered WCA_1 location + a WCXY not-covered location
            q(_PF, (run, loc[0], -1, "WCA_1", "covered", True, eid, 10000, 880, "neighbour_gap", "circle", 5.0, "5 mi ring", 12))
            q(_PF, (run, loc[1], -2, "WCXY", "not_covered_wcxy", True, eid, None, None, None, None, None, None, None))
            _check(q("SELECT count(*) FROM box.pud_forecast WHERE run_id = %s", (run,)).fetchone()[0] == 2, "a covered and a not-covered row insert")
            _refused(q, _PF, (run, loc[2], -3, "WCA_2", "covered", True, eid, 10000, 880, "neighbour_gap", "circle", 5.0, "5 mi ring", None),
                     errors.CheckViolation, "a covered row with no analog count (NULL trap)")
            _refused(q, _PF, (run, loc[2], -3, "WCA_2", "covered", True, eid, 10000, 880, "neighbour_gap", "circle", 5.0, "5 mi ring", 2),
                     errors.CheckViolation, "a covered row with 2 analogs")
            _refused(q, _PF, (run, loc[2], -3, "WCA_2", "covered", False, eid, 10000, 880, "neighbour_gap", "circle", 5.0, "5 mi ring", 12),
                     errors.CheckViolation, "a covered row outside the extent")
            _refused(q, _PF, (run, loc[2], -3, "WCXY", "not_covered_wcxy", True, eid, None, None, None, "circle", 5.0, "5 mi ring", 12),
                     errors.CheckViolation, "a WCXY row that carries a search")
            _refused(q, _PF, (run, loc[2], -3, "WCA_2", "covered", True, eid, 10000, 880, "neighbour_gap", "strike", 7.5, "5 mi ring", 12),
                     errors.CheckViolation, "a radius class that disagrees with the radius")
            _refused(q, _PF, (run, loc[2], -1, "WCA_2", "not_covered_outside_extent", False, None, None, None, None, None, None, None, None),
                     errors.UniqueViolation, "the same Novi stick twice in one run")
            q(_ST, (run, loc[0], "oil", 0.9, 500000.0, 450000.0, 450000.0))
            q(_ST, (run, loc[0], "gas", 1.0, 900000.0, 900000.0, 900000.0))
            _refused(q, _ST, (run, loc[1], "oil", 0.9, 500000.0, 450000.0, 450000.0), errors.ForeignKeyViolation, "a stream row for a not-covered location")
            _refused(q, _ST, (run, loc[0], "water", 1.0, 1.0, 1.0, 1.0), errors.CheckViolation, "a water stream (not in the frozen spec)")
            q("DELETE FROM box.pud_forecast_stream WHERE run_id = %s AND location_id = %s AND stream = 'gas'", (run, loc[0]))
            _refused(q, _ST, (run, loc[0], "gas", 0.9, 500000.0, 500000.0, 500000.0), errors.CheckViolation, "eur != eur_raw x eur_haircut")
            q("INSERT INTO box.pud_forecast_month (run_id, location_id, stream, month_no, volume) SELECT %s, %s, 'oil', m, 100 FROM generate_series(1, 600) m",
              (run, loc[0]))
            _refused(q, "INSERT INTO box.pud_forecast_month (run_id, location_id, stream, month_no, volume) VALUES (%s, %s, 'oil', 601, 1)", (run, loc[0]),
                     errors.CheckViolation, "month 601")
            q("INSERT INTO box.location_analog (run_id, location_id, api10, rank, dist_ft) VALUES (%s, %s, '3002500001', 1, 1200)", (run, loc[0]))
            _refused(q, "INSERT INTO box.location_analog (run_id, location_id, api10, rank) VALUES (%s, %s, '3002500002', 1)", (run, loc[1]),
                     errors.ForeignKeyViolation, "an analog row for a not-covered location")
            q("DELETE FROM box.forecast_run WHERE run_id = %s", (run,))
            left = sum(q(f"SELECT count(*) FROM {t} WHERE run_id = %s", (run,)).fetchone()[0]
                       for t in ("box.pud_forecast", "box.pud_forecast_stream", "box.pud_forecast_month", "box.location_analog"))
            _check(left == 0, "deleting a run cascades through pud_forecast / stream / month / analog")
        finally:
            conn.rollback()


def main() -> None:
    conn = get_connection()
    try:
        apply_sql(conn)
        validate(conn)
        smoke(conn)
    finally:
        conn.close()
    if _failures:
        sys.exit(f"{len(_failures)} check(s) FAILED")
    print("all checks passed", flush=True)


if __name__ == "__main__":
    main()
