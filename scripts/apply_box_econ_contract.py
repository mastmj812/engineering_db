"""Apply sql/61 (BOX step 7d: box_econ.box_pud_econ contract table + tie-out view) and verify it.

  1. sql/61: the table, its indexes, the writer / reader grants, the tie-out view, comments. Needs sql/52 + sql/60 live.
  2. Validate by identity:
       - the table, its PK and named indexes exist; analyst_ro reads the table and the view
       - box_econ_writer can INSERT / UPDATE / DELETE / SELECT, and owns nothing here (no DDL on the contract table)
       - anon / authenticated have no USAGE on box_econ; nothing in schema box depends on box_econ (D13: econ never flows back)
  3. Smoke inside a transaction that is ROLLED BACK, acting AS the writer login (SET ROLE), on a throwaway bench + run:
       - a priced row for a covered location inserts, and the tie view reports its gap
       - each of these is refused:
           - a row for a not-covered location
           - a row without downtime_basis
           - a duplicate key
           - an unknown downtime basis
           - ALTER TABLE by the writer
       - deleting a priced run is refused (no cascade into the econ)

!! DDL on the shared warehouse: explicit authorization ("go apply") required. From repo root:
    python -m scripts.apply_box_econ_contract [--writer steven]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from psycopg import errors, sql
from psycopg.types.json import Jsonb

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "61_box_econ_contract.sql"
TABLE = "box_econ.box_pud_econ"
VIEW = "box_econ.box_pud_econ_tie"
INDEXES = ("box_pud_econ_location_ix", "box_pud_econ_deck_ix")
_SQUARE = "MULTIPOLYGON(((-103.9 31.9,-103.8 31.9,-103.8 32.0,-103.9 32.0,-103.9 31.9)))"
_STICK = "LINESTRING(-103.88 31.95,-103.82 31.95)"

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(conn) -> None:
    print("[1/3] sql/61: box_econ.box_pud_econ + tie-out view", flush=True)
    with conn.cursor() as cur:
        cur.execute(SQL.read_text(encoding="utf-8"))
    conn.commit()


def validate(conn) -> None:
    print("[2/3] validate", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        _check(q("SELECT to_regclass(%s) IS NOT NULL", (TABLE,)).fetchone()[0], f"{TABLE} exists")
        _check(q("SELECT to_regclass(%s) IS NOT NULL", (VIEW,)).fetchone()[0], f"{VIEW} exists")
        _check(q("SELECT count(*) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'p'", (TABLE,)).fetchone()[0] == 1, "primary key")
        have = {r[0] for r in q("SELECT indexname FROM pg_indexes WHERE schemaname = 'box_econ' AND tablename = 'box_pud_econ'").fetchall()}
        for ix in INDEXES:
            _check(ix in have, f"index {ix}")
        for rel in (TABLE, VIEW):
            _check(q("SELECT has_table_privilege('analyst_ro', %s, 'SELECT')", (rel,)).fetchone()[0], f"analyst_ro reads {rel}")
        for p in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            _check(q("SELECT has_table_privilege('box_econ_writer', %s, %s)", (TABLE, p)).fetchone()[0], f"box_econ_writer can {p}")
        _check(q("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = %s::regclass", (TABLE,)).fetchone()[0] == "postgres",
               "postgres owns the contract table (the writer cannot alter or drop it)")
        for api_role in ("anon", "authenticated"):
            if q("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (api_role,)).fetchone()[0]:
                _check(not q("SELECT has_schema_privilege(%s, 'box_econ', 'USAGE')", (api_role,)).fetchone()[0], f"{api_role} (Data API) has no USAGE on box_econ")
        back = q("""SELECT count(*) FROM pg_depend d
                    JOIN pg_class c ON c.oid = d.objid JOIN pg_namespace n ON n.oid = c.relnamespace
                    JOIN pg_class rc ON rc.oid = d.refobjid JOIN pg_namespace rn ON rn.oid = rc.relnamespace
                    WHERE n.nspname = 'box' AND rn.nspname = 'box_econ'""").fetchone()[0]
        rw = q("""SELECT count(*) FROM pg_rewrite r JOIN pg_class c ON c.oid = r.ev_class JOIN pg_namespace n ON n.oid = c.relnamespace
                  JOIN pg_depend d ON d.objid = r.oid JOIN pg_class rc ON rc.oid = d.refobjid JOIN pg_namespace rn ON rn.oid = rc.relnamespace
                  WHERE n.nspname = 'box' AND rn.nspname = 'box_econ'""").fetchone()[0]
        _check(back == 0 and rw == 0, "nothing in schema box depends on box_econ (D13: econ never flows back)")
    conn.rollback()


_ROW = ("INSERT INTO box_econ.box_pud_econ (run_id, location_id, deck_id, assumption_set_id, downtime_basis, wti, hh, pv10_mm, oil_eur, gas_eur, "
        "build_id, schema_version, built_at) VALUES (%s, %s, %s, 'smoke', %s, 70, 3, 5.0, %s, %s, 'smoke', '1.0.0', now())")


def _refused(q, stmt: str, params: tuple, err, msg: str) -> None:
    q("SAVEPOINT s")
    try:
        q(stmt, params)
        _check(False, f"{msg} was ALLOWED")
    except err:
        q("ROLLBACK TO SAVEPOINT s")
        _check(True, f"{msg} is refused")


def smoke(conn, writer: str) -> None:
    print(f"[3/3] smoke as {writer!r} (rolled back)", flush=True)
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
            q("INSERT INTO box.pud_forecast (run_id, location_id, stick_id, basin, bench, formation_blueox, recon_status, coverage, inside_extent, extent_id, "
              "completed_lateral_ft, planned_spacing_ft, spacing_source, search_mode, radius_mi, radius_class, n_analogs) "
              "VALUES (%s, %s, -1, 'delaware', '_APPLY_SMOKE', 'WCA_1', 'remaining_pud', 'covered', true, %s, 10000, 880, 'neighbour_gap', 'circle', 5, '5 mi ring', 12)",
              (run, loc[0], eid))
            q("INSERT INTO box.pud_forecast (run_id, location_id, stick_id, basin, bench, formation_blueox, recon_status, coverage, inside_extent, extent_id) "
              "VALUES (%s, %s, -2, 'delaware', '_APPLY_SMOKE', 'WCA_1', 'remaining_pud', 'not_covered_outside_extent', false, %s)", (run, loc[1], eid))
            q("INSERT INTO box.pud_forecast_stream (run_id, location_id, stream, params, lateral_mult, eur_haircut, eur_raw, eur, eur_per_kft) "
              "VALUES (%s, %s, 'oil', '{}'::jsonb, 10, 1.0, 600000, 600000, 60000)", (run, loc[0]))
            q(sql.SQL("SET ROLE {}").format(sql.Identifier(writer)))
            q(_ROW, (run, loc[0], "wti70", "steven_downtime_factor", 603000.0, None))
            _check(q("SELECT count(*) FROM box_econ.box_pud_econ WHERE run_id = %s", (run,)).fetchone()[0] == 1, f"{writer} prices a covered location")
            gap = q("SELECT oil_eur_gap FROM box_econ.box_pud_econ_tie WHERE run_id = %s", (run,)).fetchone()[0]
            _check(gap is not None and abs(gap - 0.005) < 1e-9, f"tie view reports the priced-vs-BOX gap ({gap:+.3%})")
            _refused(q, _ROW, (run, loc[1], "wti70", "steven_downtime_factor", 1.0, None), errors.ForeignKeyViolation, "pricing a not-covered location")
            _refused(q, _ROW, (run, loc[0], "wti70", "steven_downtime_factor", 1.0, None), errors.UniqueViolation, "a duplicate (run, location, deck, assumptions) row")
            _refused(q, _ROW, (run, loc[0], "wti80", None, 1.0, None), errors.NotNullViolation, "a row without downtime_basis")
            _refused(q, _ROW, (run, loc[0], "wti80", "both", 1.0, None), errors.CheckViolation, "an unknown downtime basis")
            _refused(q, "ALTER TABLE box_econ.box_pud_econ ADD COLUMN x int", (), errors.InsufficientPrivilege, f"ALTER TABLE by {writer}")
            q("RESET ROLE")
            _refused(q, "DELETE FROM box.forecast_run WHERE run_id = %s", (run,), errors.ForeignKeyViolation, "deleting a run that has been priced")
        finally:
            conn.rollback()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--writer", default="steven", help="existing box_econ writer LOGIN role the smoke acts as")
    a = ap.parse_args()
    conn = get_connection()
    try:
        apply_sql(conn)
        validate(conn)
        smoke(conn, a.writer)
    finally:
        conn.close()
    if _failures:
        sys.exit(f"{len(_failures)} check(s) FAILED")
    print("all checks passed", flush=True)


if __name__ == "__main__":
    main()
