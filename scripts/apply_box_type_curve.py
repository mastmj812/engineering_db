"""Apply sql/58 (BOX step 5d: box.type_curve, box.tc_member, box.risk_factor) and verify it.

  1. sql/58 — the three tables, their indexes, the analyst_ro grant, comments (needs sql/54 + sql/57 live).
  2. validate by identity:
       - every table + named index exists; PKs present; analyst_ro reads all three
       - anon / authenticated have no USAGE on box; the ETL never names schema box
  3. smoke inside a transaction that is ROLLED BACK, on a throwaway bench + extent + area: insert an oil
     and a gas curve with members and factors, then check each guard refuses what it should:
     rung 3 (D37), a gas curve not in ratio mode (D30), a non-thin curve under 10 wells (D9 / D10), a
     second record curve per (area, stream), a dropped member without a reason, a reference factor off
     rung 0, a second record factor per key; and that deleting a curve cascades to its members.

!! DDL on the shared warehouse — explicit authorization ("go apply") required. From repo root:
    python -m scripts.apply_box_type_curve
"""

from __future__ import annotations

import sys
from pathlib import Path

from psycopg import errors

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "58_box_type_curve.sql"
TABLES = {
    "box.type_curve": ("box_type_curve_version_uq", "box_type_curve_record_uq"),
    "box.tc_member": ("box_tc_member_api10_ix",),
    "box.risk_factor": ("box_risk_factor_version_uq", "box_risk_factor_record_uq"),
}
_SQUARE = "MULTIPOLYGON(((-103.9 31.9,-103.8 31.9,-103.8 32.0,-103.9 32.0,-103.9 31.9)))"

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(conn) -> None:
    print("[1/3] sql/58 — box.type_curve, box.tc_member, box.risk_factor", flush=True)
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
    conn.rollback()
    etl = (Path(__file__).resolve().parent.parent / "etl" / "db.py").read_text(encoding="utf-8")
    _check("box." not in etl, "etl/db.py never names schema box (ETL never touches it)")


_TC = ("INSERT INTO box.type_curve (area_id, version, stream, mode, relaxation_step, relaxation_label, thin, n_wells, params, eur_per_kft, "
       "engine_sha, data_asof, is_record) VALUES (%s, %s, %s, %s, %s, 'strict', %s, %s, '{}'::jsonb, 50000, 'smoke', '2026-07-01', %s) RETURNING tc_id")
_RF = ("INSERT INTO box.risk_factor (version, basin, bench, stream, metric, level, term, dev_scenario, n_pairs, factor, rung, rung_label, n_basis, is_record) "
       "VALUES (%s, 'delaware', '_APPLY_SMOKE', 'oil', 'oil_cum12', %s, %s, %s, 40, %s, %s, 'x', 40, %s)")


def _refused(q, sql: str, params: tuple, err: type[Exception], msg: str) -> None:
    q("SAVEPOINT s")
    try:
        q(sql, params)
        _check(False, f"{msg} was ALLOWED")
    except err:
        q("ROLLBACK TO SAVEPOINT s")
        _check(True, f"{msg} is refused")


def smoke(conn) -> None:
    print("[3/3] smoke (rolled back)", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        try:
            q("INSERT INTO box.bench_scope (basin, bench, in_scope, reason, decided_on) VALUES ('delaware', '_APPLY_SMOKE', false, 'apply smoke', current_date)")
            eid = q("INSERT INTO box.extent (basin, bench, version, source, geom) "
                    "VALUES ('delaware', '_APPLY_SMOKE', 999, 'generated', extensions.ST_GeomFromText(%s, 4326)) RETURNING extent_id", (_SQUARE,)).fetchone()[0]
            aid = q("INSERT INTO box.tc_area (extent_id, version, area_no, geom, n_wells) VALUES (%s, 1, 1, extensions.ST_GeomFromText(%s, 4326), 20) RETURNING area_id",
                    (eid, _SQUARE)).fetchone()[0]
            oil = q(_TC, (aid, 1, "oil", "arps", 1, False, 20, True)).fetchone()[0]
            q(_TC, (aid, 1, "gas", "ratio", 1, False, 20, True))
            q(_TC, (aid, 1, "water", "arps", 4, True, 6, True))
            _check(q("SELECT count(*) FROM box.type_curve WHERE area_id = %s", (aid,)).fetchone()[0] == 3, "three curves insert (oil / gas ratio / thin water on rung 4)")
            _refused(q, _TC, (aid, 2, "oil", "arps", 3, False, 20, False), errors.CheckViolation, "a curve stamped rung 3 (D37)")
            _refused(q, _TC, (aid, 2, "gas", "arps", 1, False, 20, False), errors.CheckViolation, "a gas curve not in ratio mode (D30)")
            _refused(q, _TC, (aid, 2, "oil", "arps", 1, False, 9, False), errors.CheckViolation, "a non-thin curve under 10 wells")
            _refused(q, _TC, (aid, 2, "oil", "arps", 1, False, 20, True), errors.UniqueViolation, "a second record curve per (area, stream)")
            q("INSERT INTO box.tc_member (tc_id, api10, included) VALUES (%s, '3002500001', true)", (oil,))
            _refused(q, "INSERT INTO box.tc_member (tc_id, api10, included) VALUES (%s, '3002500002', false)", (oil,), errors.CheckViolation,
                     "a dropped member without a drop_reason")
            _refused(q, "INSERT INTO box.tc_member (tc_id, api10, included) VALUES (%s, '30025', true)", (oil,), errors.CheckViolation, "a malformed api10")
            q(_RF, (1, "reference", "codev_stack", "codev_stack", 1.0, 0, True))
            q(_RF, (1, "pair", "infill", "infill", 0.92, 1, True))
            _refused(q, _RF, (1, "reference", "codev_x", "codev_stack", 1.0, 1, False), errors.CheckViolation, "a reference factor off rung 0")
            _refused(q, _RF, (1, "pair", "topfill|X", "topfill", 0.9, 4, False), errors.CheckViolation, "a factor on rung 4 (D45 has 3)")
            _refused(q, _RF, (2, "pair", "infill", "infill", 0.93, 1, True), errors.UniqueViolation, "a second record factor per key")
            q("DELETE FROM box.type_curve WHERE tc_id = %s", (oil,))
            _check(q("SELECT count(*) FROM box.tc_member WHERE tc_id = %s", (oil,)).fetchone()[0] == 0, "deleting a curve cascades to its members")
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
