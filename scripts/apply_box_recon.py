"""Apply sql/74 (nightly BOX sticks reconciliation: the tables) and verify it.

  1. sql/74, twice (idempotent): meta.box_recon_run, curated.box_location_status, curated.box_location_status_log,
     curated.box_dsu_bench_stale.
  2. Validate: the four tables, their indexes, constraints, comments and analyst_ro grants exist; they are EMPTY after a
     first apply (the first nightly fills them) and unchanged by a second; schema box is untouched by identity (set,
     stick and location counts, the record sets); EXPLAIN of the nightly's judge names box_location_stick_geog_gix; the
     judge returns exactly one row per record stick (read-only evaluation).
  3. Smoke inside a savepoint that is ROLLED BACK: a run row and a status row insert; each of these is refused: a
     stick that is producing and counted as inventory, a producing stick without its well, a crowded stick that is
     producing, a stale row whose estimate is not the lower of the two, a run row that wrote without status written.

--dry-run runs all three steps in ONE transaction and rolls it back (PostgreSQL DDL is transactional); nothing persists.
--skip-judge leaves out the judge evaluation of step 2 (about a minute on live).

!! DDL on the shared warehouse: explicit authorization ("go apply") required, with or without --dry-run. Rehearsal
container first (python -m scripts.box_rehearsal env). The apply does NOT run the nightly step and adds nothing to
the nightly path: etl/refresh.py wires the hook, which is a no-op until these tables exist. From repo root:
    python -m scripts.apply_box_recon [--dry-run] [--skip-judge]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from psycopg import errors

from etl import box_recon
from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "74_box_recon.sql"
TABLES = box_recon.TABLES
INDEXES = ("box_recon_run_pkey", "box_location_status_pkey", "box_location_status_status_ix", "box_location_status_pad_ix",
           "box_location_status_api10_ix", "box_location_status_log_pkey", "box_location_status_log_location_ix", "box_dsu_bench_stale_pkey")
CONSTRAINTS = ("box_recon_run_wrote_ck", "box_location_status_inventory_ck", "box_location_status_match_ck", "box_location_status_crowd_ck",
               "box_dsu_bench_stale_wells_ck", "box_dsu_bench_stale_est_ck")
STICK_INDEX = "box_location_stick_geog_gix"
_BOX = ("SELECT (SELECT count(*) FROM box.location_set), (SELECT count(*) FROM box.location_stick), (SELECT count(*) FROM box.location), "
        "(SELECT string_agg(set_id::text, ',' ORDER BY set_id) FROM box.location_set WHERE is_record)")
_ROWS = " || ',' || ".join(f"(SELECT count(*) FROM {t})::text" for t in TABLES)

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(cur) -> tuple:
    print("[1/3] sql/74: nightly BOX sticks reconciliation tables (run twice)", flush=True)
    q = cur.execute
    print(f"    target {q('select inet_server_addr(), inet_server_port(), current_database()').fetchone()}", flush=True)
    existed = all(q("SELECT to_regclass(%s)", (t,)).fetchone()[0] is not None for t in TABLES)
    box = q(_BOX).fetchone()
    rows0 = q(f"SELECT {_ROWS}").fetchone()[0] if existed else None
    sql = SQL.read_text(encoding="utf-8")
    q(sql)
    rows1 = q(f"SELECT {_ROWS}").fetchone()[0]
    q(sql)
    return existed, box, rows0, rows1


def validate(cur, before: tuple, judge: bool) -> None:
    print("[2/3] validate", flush=True)
    q = cur.execute
    existed, box, rows0, rows1 = before
    for t in TABLES:
        _check(q("SELECT to_regclass(%s)", (t,)).fetchone()[0] is not None, f"{t} exists")
        _check(q("SELECT obj_description(%s::regclass) IS NOT NULL", (t,)).fetchone()[0], f"{t} is commented")
        _check(q("SELECT has_table_privilege('analyst_ro', %s, 'SELECT')", (t,)).fetchone()[0], f"analyst_ro can read {t}")
        _check(not q("SELECT has_table_privilege('analyst_ro', %s, 'INSERT')", (t,)).fetchone()[0], f"analyst_ro cannot write {t}")
    have = {r[0] for r in q("SELECT indexname FROM pg_indexes WHERE schemaname IN ('curated', 'meta')").fetchall()}
    _check(set(INDEXES) <= have, f"indexes exist ({len(INDEXES)}; missing {sorted(set(INDEXES) - have)})")
    cons = {r[0] for r in q("SELECT conname FROM pg_constraint").fetchall()}
    _check(set(CONSTRAINTS) <= cons, f"constraints exist ({len(CONSTRAINTS)}; missing {sorted(set(CONSTRAINTS) - cons)})")
    rows2 = q(f"SELECT {_ROWS}").fetchone()[0]
    _check(rows2 == rows1, f"the second apply changed no row ({rows1} -> {rows2}; run, status, log, stale)")
    if existed:
        _check(rows1 == rows0, f"re-applying over existing tables changed no row ({rows0} -> {rows1})")
    else:
        _check(rows1 == "0,0,0,0", f"the new tables are empty ({rows1}): the first nightly fills them")
    _check(q(_BOX).fetchone() == box, f"schema box untouched by identity (sets, stick rows, locations, record sets = {box})")
    _check(not box_recon.missing_tables(cur.connection), "etl.box_recon sees every table it writes")
    n_rec = q("SELECT count(*) FROM box.location_stick s JOIN box.location_set t USING (set_id) WHERE t.is_record").fetchone()[0]
    if n_rec == 0:
        _check(True, "no record set here: judge checks skipped")
        return
    plan = "\n".join(r[0] for r in q("EXPLAIN " + box_recon.JUDGE_SQL).fetchall())
    _check(STICK_INDEX in plan, f"EXPLAIN of the nightly judge names {STICK_INDEX}")
    if judge:
        q("SET LOCAL statement_timeout = '900s'")
        n, d = q(f"SELECT count(*), count(DISTINCT location_id) FROM ({box_recon.JUDGE_SQL}) j").fetchone()
        _check(n == d == n_rec, f"the judge returns one row per record stick ({n:,} rows, {d:,} locations, {n_rec:,} record sticks)")


def _refused(q, stmt: str, params: tuple, msg: str) -> None:
    q("SAVEPOINT s")
    try:
        q(stmt, params)
        _check(False, f"{msg} was ALLOWED")
        q("ROLLBACK TO SAVEPOINT s")
    except errors.CheckViolation:
        q("ROLLBACK TO SAVEPOINT s")
        _check(True, f"{msg} is refused")


_RUN = "INSERT INTO meta.box_recon_run (status, wrote, predicate_version) VALUES (%s, %s, 'smoke') RETURNING run_id"
_STATUS = ("INSERT INTO curated.box_location_status (location_id, set_id, basin, pad_id, formation_blueox, n_legs, status, counts_as_inventory, "
           "legs_matched, matched_api10, conflict_reason, crowded, crowd_api10, status_since, run_id) "
           "VALUES (%s, 0, 'delaware', 0, 'WCA_1', 1, %s, %s, %s, %s, %s, %s, %s, current_date, %s)")
_STALE = ("INSERT INTO curated.box_dsu_bench_stale (set_id, basin, pad_id, formation_blueox, new_producers, new_api10, sticks, sticks_out, est_sticks, "
          "stale_since, run_id) VALUES (0, 'delaware', %s, 'WCA_1', %s, %s, %s, %s, %s, current_date, %s)")


def smoke(cur) -> None:
    print("[3/3] smoke (inside a savepoint, rolled back)", flush=True)
    q = cur.execute
    q("SAVEPOINT smoke")
    rid = q(_RUN, ("written", True)).fetchone()[0]
    q(_STATUS, (-1, "open", True, 0, None, None, False, None, rid))
    q(_STATUS, (-2, "producing", False, 1, "0000000001", None, False, None, rid))
    q(_STATUS, (-3, "conflict", False, 0, "0000000001", "partial_overlap", False, None, rid))
    q(_STATUS, (-4, "pending", False, 0, None, None, True, "0000000002", rid))
    q(_STALE, (-1, 2, ["a", "b"], 5, 1, 3, rid))
    _check(q("SELECT count(*) FROM curated.box_location_status WHERE location_id < 0").fetchone()[0] == 4, "a run row and four status rows insert")
    _refused(q, _STATUS, (-5, "producing", True, 1, "0000000001", None, False, None, rid), "a producing stick counted as inventory")
    _refused(q, _STATUS, (-6, "producing", False, 1, None, None, False, None, rid), "a producing stick without its well")
    _refused(q, _STATUS, (-7, "producing", False, 1, "0000000001", None, True, "0000000002", rid), "a crowded stick that is producing")
    _refused(q, _STATUS, (-8, "open", True, 0, None, None, True, "0000000002", rid), "a crowded stick counted as inventory")
    _refused(q, _STALE, (-2, 2, ["a", "b"], 5, 1, 4, rid), "a stale estimate that is not the lower of the two")
    _refused(q, _STALE, (-3, 2, ["a"], 5, 1, 3, rid), "a stale row whose well list is not its count")
    _refused(q, _RUN, ("breaker", True), "a run row that wrote without status written")
    q("ROLLBACK TO SAVEPOINT smoke")
    _check(q("SELECT count(*) FROM curated.box_location_status WHERE location_id < 0").fetchone()[0] == 0, "the smoke rows are gone")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="one transaction, rolled back at the end: nothing persists")
    ap.add_argument("--skip-judge", action="store_true", help="skip the read-only judge evaluation (about a minute on live)")
    a = ap.parse_args()
    conn = get_connection()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            before = apply_sql(cur)
            validate(cur, before, not a.skip_judge)
            smoke(cur)
        if a.dry_run or _failures:
            conn.rollback()
            print("ROLLED BACK: nothing persisted" + ("" if a.dry_run else " (checks failed)"), flush=True)
        else:
            conn.commit()
            print("COMMITTED", flush=True)
    finally:
        conn.close()
    if _failures:
        sys.exit(f"{len(_failures)} check(s) FAILED")
    print("all checks passed", flush=True)


if __name__ == "__main__":
    main()
