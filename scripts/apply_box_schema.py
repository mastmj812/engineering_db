"""Apply sql/54 + sql/56 (BOX schema: bench_scope, extent, extent_edge) and verify it.

  1. sql/54 — schema box, the three tables, indexes, grants, the D2 bench_scope seed
     (ON CONFLICT DO NOTHING: Michael's later edits survive a re-apply); sql/56 — edge_class
     'bridge' (D27 envelope bridges).
  2. validate by identity:
       - every table + named index exists; PKs present
       - bench_scope holds every seeded (basin, bench) key with the seeded in_scope
       - analyst_ro reads every box table; anon / authenticated have no USAGE on box
       - the ETL never names schema box (etl/db.py _CURATED_MATVIEWS) — app-owned like narvi.*
  3. smoke inside a transaction that is ROLLED BACK: insert a generated extent + one edge, check the
     is_record partial unique index refuses a second record, and EXPLAIN (seqscan off) shows
     box_extent_geom_gix and box_extent_geog_gix on spatial predicates.

!! DDL on the shared warehouse — explicit authorization ("go apply") required. From repo root:
    python -m scripts.apply_box_schema
"""

from __future__ import annotations

import sys
from pathlib import Path

from psycopg import errors

from etl.db import get_connection

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
SQL_FILES = ("54_box_schema.sql", "56_box_extent_edge_bridge.sql")
TABLES = ("box.bench_scope", "box.extent", "box.extent_edge")
INDEXES = ("box_extent_version_uq", "box_extent_record_uq", "box_extent_geom_gix", "box_extent_geog_gix", "box_extent_edge_geom_gix")
SEED = {
    ("delaware", "WCA"): True,
    ("delaware", "BS2_S"): True,
    ("delaware", "WDFD"): False,
    ("midland", "MISS"): False,
    ("midland", "BRNT"): False,
    ("midland", "MRMC"): False,
    ("midland", "WDFD"): False,
}
_SQUARE = "MULTIPOLYGON(((-103.9 31.9,-103.8 31.9,-103.8 32.0,-103.9 32.0,-103.9 31.9)))"

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_schema(conn) -> None:
    print("[1/3] sql/54 + sql/56 — box schema", flush=True)
    with conn.cursor() as cur:
        for f in SQL_FILES:
            cur.execute((SQL_DIR / f).read_text(encoding="utf-8"))
    conn.commit()


def validate(conn) -> None:
    print("[2/3] validate", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        for t in TABLES:
            _check(q("SELECT to_regclass(%s) IS NOT NULL", (t,)).fetchone()[0], f"{t} exists")
            _check(q("SELECT has_table_privilege('analyst_ro', %s, 'SELECT')", (t,)).fetchone()[0], f"analyst_ro reads {t}")
            _check(q("SELECT count(*) FROM pg_constraint WHERE conrelid = %s::regclass AND contype = 'p'", (t,)).fetchone()[0] == 1, f"{t} has a primary key")
        have = {r[0] for r in q("SELECT indexname FROM pg_indexes WHERE schemaname = 'box'").fetchall()}
        for ix in INDEXES:
            _check(ix in have, f"index {ix}")
        rows = {(b, s): i for b, s, i in q("SELECT basin, bench, in_scope FROM box.bench_scope").fetchall()}
        for k, v in SEED.items():
            _check(rows.get(k) is v, f"bench_scope {k} in_scope={v} (got {rows.get(k)})")
        for api_role in ("anon", "authenticated"):
            exists = q("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (api_role,)).fetchone()[0]
            if exists:
                _check(not q("SELECT has_schema_privilege(%s, 'box', 'USAGE')", (api_role,)).fetchone()[0], f"{api_role} (Data API) has no USAGE on box")
    conn.rollback()
    etl = (Path(__file__).resolve().parent.parent / "etl" / "db.py").read_text(encoding="utf-8")
    _check("box." not in etl, "etl/db.py never names schema box (ETL never touches it)")


def smoke(conn) -> None:
    print("[3/3] smoke (rolled back)", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        try:
            # a throwaway bench inside the rolled-back transaction: real benches may already hold a
            # version-of-record row, which the partial unique index would (correctly) refuse
            q("INSERT INTO box.bench_scope (basin, bench, in_scope, reason, decided_on) VALUES ('delaware', '_APPLY_SMOKE', false, 'apply smoke', current_date)")
            eid = q(
                "INSERT INTO box.extent (basin, bench, version, source, geom, is_record) "
                "VALUES ('delaware', '_APPLY_SMOKE', 999, 'generated', extensions.ST_GeomFromText(%s, 4326), true) RETURNING extent_id",
                (_SQUARE,),
            ).fetchone()[0]
            q(
                "INSERT INTO box.extent_edge (extent_id, edge_no, seg_no, geom, buffer_ft, edge_class, rule) "
                "VALUES (%s, 0, 0, extensions.ST_GeomFromText('LINESTRING(-103.9 31.9,-103.8 31.9)', 4326), 880, 'pinned', 'pinned: floor')",
                (eid,),
            )
            _check(q("SELECT count(*) FROM box.extent_edge WHERE extent_id = %s", (eid,)).fetchone()[0] == 1, "extent + edge insert")
            q(
                "INSERT INTO box.extent_edge (extent_id, edge_no, seg_no, geom, buffer_ft, edge_class, rule) "
                "VALUES (%s, 1, 0, extensions.ST_GeomFromText('LINESTRING(-103.8 31.9,-103.8 32.0)', 4326), 880, 'bridge', 'envelope bridge (D27)')",
                (eid,),
            )
            _check(True, "edge_class 'bridge' accepted (sql/56)")
            q("SAVEPOINT s")
            try:
                q(
                    "INSERT INTO box.extent (basin, bench, version, source, geom, is_record) "
                    "VALUES ('delaware', '_APPLY_SMOKE', 998, 'generated', extensions.ST_GeomFromText(%s, 4326), true)",
                    (_SQUARE,),
                )
                _check(False, "a second is_record row per bench was ALLOWED")
            except errors.UniqueViolation:
                q("ROLLBACK TO SAVEPOINT s")
                _check(True, "a second is_record row per bench is refused")
            q("SET LOCAL enable_seqscan = off")
            q("SET LOCAL search_path = public, extensions")  # && lives with PostGIS in extensions
            plan = "\n".join(r[0] for r in q(
                "EXPLAIN SELECT extent_id FROM box.extent WHERE geom && extensions.ST_MakeEnvelope(-104, 31.8, -103.7, 32.1, 4326)").fetchall())
            _check("box_extent_geom_gix" in plan, "EXPLAIN uses box_extent_geom_gix")
            plan = "\n".join(r[0] for r in q(
                "EXPLAIN SELECT extent_id FROM box.extent WHERE extensions.ST_DWithin(geom::extensions.geography, "
                "extensions.ST_SetSRID(extensions.ST_MakePoint(-103.85, 31.95), 4326)::extensions.geography, 1000)").fetchall())
            _check("box_extent_geog_gix" in plan, "EXPLAIN uses box_extent_geog_gix")
        finally:
            conn.rollback()


def main() -> None:
    conn = get_connection()
    try:
        apply_schema(conn)
        validate(conn)
        smoke(conn)
    finally:
        conn.close()
    if _failures:
        sys.exit(f"{len(_failures)} check(s) FAILED")
    print("all checks passed", flush=True)


if __name__ == "__main__":
    main()
