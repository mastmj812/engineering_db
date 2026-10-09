"""Apply sql/57 (BOX step 4: box.tc_area) and verify it.

  1. sql/57 — box.tc_area, its indexes, the analyst_ro grant, comments (needs sql/54 live).
  2. validate by identity:
       - box.tc_area + every named index exists; PK present; analyst_ro reads it
       - anon / authenticated have no USAGE on box; the ETL never names schema box
  3. smoke inside a transaction that is ROLLED BACK, on a throwaway bench + extent: insert two
     areas, check the D9 floor CHECK refuses n_wells 9, the is_record partial unique index refuses
     a second record row for the same area_no, and EXPLAIN (seqscan off) shows
     box_tc_area_geom_gix and box_tc_area_geog_gix on spatial predicates.

!! DDL on the shared warehouse — explicit authorization ("go apply") required. From repo root:
    python -m scripts.apply_box_tc_area
"""

from __future__ import annotations

import sys
from pathlib import Path

from psycopg import errors

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "57_box_tc_area.sql"
TABLE = "box.tc_area"
INDEXES = ("box_tc_area_version_uq", "box_tc_area_record_uq", "box_tc_area_geom_gix", "box_tc_area_geog_gix")
_SQUARE = "MULTIPOLYGON(((-103.9 31.9,-103.8 31.9,-103.8 32.0,-103.9 32.0,-103.9 31.9)))"
_HALF = "MULTIPOLYGON(((-103.9 31.9,-103.85 31.9,-103.85 32.0,-103.9 32.0,-103.9 31.9)))"

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(conn) -> None:
    print("[1/3] sql/57 — box.tc_area", flush=True)
    with conn.cursor() as cur:
        cur.execute(SQL.read_text(encoding="utf-8"))
    conn.commit()


def validate(conn) -> None:
    print("[2/3] validate", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        _check(q("SELECT to_regclass(%s) IS NOT NULL", (TABLE,)).fetchone()[0], f"{TABLE} exists")
        _check(q("SELECT has_table_privilege('analyst_ro', %s, 'SELECT')", (TABLE,)).fetchone()[0], f"analyst_ro reads {TABLE}")
        _check(q("SELECT count(*) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'p'", (TABLE,)).fetchone()[0] == 1, f"{TABLE} has a primary key")
        have = {r[0] for r in q("SELECT indexname FROM pg_indexes WHERE schemaname = 'box' AND tablename = 'tc_area'").fetchall()}
        for ix in INDEXES:
            _check(ix in have, f"index {ix}")
        for api_role in ("anon", "authenticated"):
            if q("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (api_role,)).fetchone()[0]:
                _check(not q("SELECT has_schema_privilege(%s, 'box', 'USAGE')", (api_role,)).fetchone()[0], f"{api_role} (Data API) has no USAGE on box")
    conn.rollback()
    etl = (Path(__file__).resolve().parent.parent / "etl" / "db.py").read_text(encoding="utf-8")
    _check("box." not in etl, "etl/db.py never names schema box (ETL never touches it)")


def smoke(conn) -> None:
    print("[3/3] smoke (rolled back)", flush=True)
    ins = ("INSERT INTO box.tc_area (extent_id, version, area_no, geom, n_wells, is_record) "
           "VALUES (%s, %s, %s, extensions.ST_GeomFromText(%s, 4326), %s, %s)")
    with conn.cursor() as cur:
        q = cur.execute
        try:
            q("INSERT INTO box.bench_scope (basin, bench, in_scope, reason, decided_on) VALUES ('delaware', '_APPLY_SMOKE', false, 'apply smoke', current_date)")
            eid = q("INSERT INTO box.extent (basin, bench, version, source, geom) "
                    "VALUES ('delaware', '_APPLY_SMOKE', 999, 'generated', extensions.ST_GeomFromText(%s, 4326)) RETURNING extent_id", (_SQUARE,)).fetchone()[0]
            q(ins, (eid, 1, 1, _HALF, 10, True))
            q(ins, (eid, 1, 2, _HALF, 25, True))
            _check(q("SELECT count(*) FROM box.tc_area WHERE extent_id = %s", (eid,)).fetchone()[0] == 2, "two areas insert")
            q("SAVEPOINT s")
            try:
                q(ins, (eid, 1, 3, _HALF, 9, False))
                _check(False, "an area with 9 wells was ALLOWED (D9 floor)")
            except errors.CheckViolation:
                q("ROLLBACK TO SAVEPOINT s")
                _check(True, "an area with < 10 wells is refused (D9 floor)")
            q("SAVEPOINT s2")
            try:
                q(ins, (eid, 2, 1, _HALF, 10, True))
                _check(False, "a second record row for one (extent, area_no) was ALLOWED")
            except errors.UniqueViolation:
                q("ROLLBACK TO SAVEPOINT s2")
                _check(True, "a second record row for one (extent, area_no) is refused")
            q("SET LOCAL enable_seqscan = off")
            q("SET LOCAL search_path = public, extensions")  # && lives with PostGIS in extensions
            plan = "\n".join(r[0] for r in q(
                "EXPLAIN SELECT area_id FROM box.tc_area WHERE geom && extensions.ST_MakeEnvelope(-104, 31.8, -103.7, 32.1, 4326)").fetchall())
            _check("box_tc_area_geom_gix" in plan, "EXPLAIN uses box_tc_area_geom_gix")
            plan = "\n".join(r[0] for r in q(
                "EXPLAIN SELECT area_id FROM box.tc_area WHERE extensions.ST_DWithin(geom::extensions.geography, "
                "extensions.ST_SetSRID(extensions.ST_MakePoint(-103.85, 31.95), 4326)::extensions.geography, 1000)").fetchall())
            _check("box_tc_area_geog_gix" in plan, "EXPLAIN uses box_tc_area_geog_gix")
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
