"""Apply sql/70 (D130: one BOX record run per basin) and verify it.

  1. sql/70: box.forecast_run.basin (NOT NULL, CHECK delaware | midland) + UNIQUE (basin) WHERE is_record, replacing sql/60's
     one-record index.
  2. Validate by identity: every existing run reads basin 'delaware'; the record run(s) are the same run_ids as before; the old
     index is gone and the new one is UNIQUE on (basin) WHERE is_record; EXPLAIN (seqscan off) of the per-basin record lookup
     names it; run / pud_forecast counts unchanged.
  3. Smoke inside a transaction that is ROLLED BACK:
       - a Midland record run inserts next to the Delaware record
       - the per-basin record flip (box_pud_run store) supersedes the Midland record only; the Delaware record is untouched
       - each of these is refused: a second Delaware record run; an unknown basin

!! DDL on the shared warehouse: explicit authorization ("go apply") required. Container first: point the DB_* env at the
`scripts.box_rehearsal` container (python -m scripts.box_rehearsal env). From repo root:
    python -m scripts.apply_box_run_basin
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from psycopg import errors
from psycopg.types.json import Jsonb

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "70_box_record_per_basin.sql"
INDEX = "box_forecast_run_record_basin_uq"
OLD_INDEX = "box_forecast_run_record_uq"
_STATE = ("SELECT (SELECT count(*) FROM box.forecast_run), "
          "(SELECT array_agg(run_id ORDER BY run_id) FROM box.forecast_run WHERE is_record), "
          "(SELECT count(*) FROM box.pud_forecast)")

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(conn) -> tuple:
    print("[1/3] sql/70: one record run per basin", flush=True)
    with conn.cursor() as cur:
        print(f"    target {cur.execute('select inet_server_addr(), inet_server_port(), current_database()').fetchone()}", flush=True)
        before = cur.execute(_STATE).fetchone()
        cur.execute(SQL.read_text(encoding="utf-8"))
    conn.commit()
    return before


def validate(conn, before: tuple) -> None:
    print("[2/3] validate", flush=True)
    with conn.cursor() as cur:
        q = cur.execute
        col = q("SELECT is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'box' "
                "AND table_name = 'forecast_run' AND column_name = 'basin'").fetchone()
        _check(col is not None and col[0] == "NO", f"box.forecast_run.basin exists, NOT NULL ({col})")
        _check(q("SELECT count(*) FROM pg_constraint WHERE conname = 'box_forecast_run_basin_ck'").fetchone()[0] == 1,
               "box_forecast_run_basin_ck exists")
        by = dict(q("SELECT basin, count(*) FROM box.forecast_run GROUP BY 1").fetchall())
        _check(set(by) <= {"delaware"}, f"every existing run reads basin 'delaware' ({by})")
        _check(q(_STATE).fetchone() == before, f"runs / record run_ids / pud_forecast rows unchanged by identity {before}")
        idx = dict(q("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'box' AND tablename = 'forecast_run'").fetchall())
        _check(OLD_INDEX not in idx, f"sql/60's {OLD_INDEX} is gone")
        d = idx.get(INDEX, "")
        _check("UNIQUE" in d and "(basin)" in d and "WHERE is_record" in d, f"{INDEX}: {d}")
        q("SET LOCAL enable_seqscan = off")
        plan = "\n".join(r[0] for r in q("EXPLAIN SELECT run_id FROM box.forecast_run WHERE is_record AND basin = 'delaware'").fetchall())
        _check(INDEX in plan, f"the per-basin record lookup uses {INDEX}")
    conn.rollback()


def _refused(q, stmt: str, params: tuple, err, msg: str) -> None:
    q("SAVEPOINT s")
    try:
        q(stmt, params)
        _check(False, f"{msg} was ALLOWED")
    except err:
        q("ROLLBACK TO SAVEPOINT s")
        _check(True, f"{msg} is refused")


_RUN = ("INSERT INTO box.forecast_run (basin, spec, code_sha, engine_sha, dealintake_config, report_version, data_through, haircut, "
        "calendar_factor, disclosure, is_record) VALUES (%s, 'box_v2_wf', 'smoke', 'smoke', 11, '_SMOKE', '2026-07-01', %s, %s, %s, %s) RETURNING run_id")


def smoke(conn) -> None:
    print("[3/3] smoke (rolled back)", flush=True)
    j = (Jsonb({"oil": {}, "gas": {}}), Jsonb({"oil": [], "gas": []}), Jsonb({"hindcast_bias": {}, "radius_ranges": {}}))
    with conn.cursor() as cur:
        q = cur.execute
        try:
            dela = [r[0] for r in q("SELECT run_id FROM box.forecast_run WHERE is_record AND basin = 'delaware'").fetchall()]
            m1 = q(_RUN, ("midland", *j, True)).fetchone()[0]
            _check(True, f"a Midland record run ({m1}) inserts next to the Delaware record {dela}")
            m2 = q(_RUN, ("midland", *j, False)).fetchone()[0]
            q("UPDATE box.forecast_run SET is_record = false, superseded_by = %s WHERE is_record AND basin = %s", (m2, "midland"))
            q("UPDATE box.forecast_run SET is_record = true WHERE run_id = %s", (m2,))
            rec = dict(q("SELECT basin, array_agg(run_id ORDER BY run_id) FROM box.forecast_run WHERE is_record GROUP BY 1").fetchall())
            _check(rec.get("midland") == [m2] and rec.get("delaware", []) == dela,
                   f"the per-basin flip superseded the Midland record only ({rec})")
            if dela:
                _refused(q, _RUN, ("delaware", *j, True), errors.UniqueViolation, "a second Delaware record run")
            else:
                d1 = q(_RUN, ("delaware", *j, True)).fetchone()[0]
                _refused(q, _RUN, ("delaware", *j, True), errors.UniqueViolation, f"a second Delaware record run (after {d1})")
            _refused(q, _RUN, ("permian", *j, False), errors.CheckViolation, "an unknown basin")
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
