"""Apply sql/77 (BOX sticks generator 0.13: the `grid` rung and two stick flags) and verify it.

  1. sql/77, twice (idempotent): three CHECK constraints of sql/73 widened; one column comment.
  2. Validate: the three constraints exist and list the new values; the old values are still accepted; row counts of
     box.location_set, box.location_stick, box.location_set_bench and the record sets are unchanged.
  3. Smoke inside a savepoint that is ROLLED BACK: an existing stick row takes tvd_rung 'grid' and the two new flags;
     an unknown rung and an unknown flag are still refused.

--dry-run runs all three steps in ONE transaction and rolls it back; nothing persists.

!! DDL on the shared warehouse (schema box): explicit authorization ("go apply") required, with or without --dry-run.
The swap of a CHECK constraint locks the table briefly and re-validates its rows. From repo root:
    python -m scripts.apply_box_sticks_grid_rung [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from psycopg import errors

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "77_box_sticks_grid_rung.sql"
CONSTRAINTS = {"box.location_stick": ("location_stick_tvd_rung_check", "location_stick_flags_check"), "box.location_set_bench": ("location_set_bench_tvd_rung_check",)}
NEW = {"location_stick_tvd_rung_check": ("'grid'",), "location_stick_flags_check": ("'grid_bounded'", "'outside_grid'"), "location_set_bench_tvd_rung_check": ("'grid'", "'none'")}
_COUNTS = ("SELECT (SELECT count(*) FROM box.location_set), (SELECT count(*) FROM box.location_stick), (SELECT count(*) FROM box.location_set_bench), "
           "(SELECT string_agg(set_id::text, ',' ORDER BY set_id) FROM box.location_set WHERE is_record)")
_fail = 0


def _check(ok: bool, msg: str) -> None:
    global _fail
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    _fail += 0 if ok else 1


def _refused(cur, sql: str) -> bool:
    cur.execute("SAVEPOINT t")
    try:
        cur.execute(sql)
    except errors.CheckViolation:
        cur.execute("ROLLBACK TO SAVEPOINT t")
        return True
    cur.execute("ROLLBACK TO SAVEPOINT t")
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="one transaction, rolled back at the end: nothing persists")
    a = ap.parse_args(argv)
    ddl = SQL.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            print(f"[1/3] sql/77 (run twice) on {conn.info.host}:{conn.info.port}", flush=True)
            before = cur.execute(_COUNTS).fetchone()
            cur.execute(ddl)
            cur.execute(ddl)
            print("[2/3] validate", flush=True)
            for table, names in CONSTRAINTS.items():
                for n in names:
                    row = cur.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s", (table, n)).fetchone()
                    _check(row is not None and all(v in row[0] for v in NEW[n]), f"{table}.{n} lists {', '.join(NEW[n])}")
                    _check(row is not None and all(v in row[0] for v in ("'direct'", "'offset'") if "rung" in n), f"{n} still accepts the existing values")
            _check(cur.execute(_COUNTS).fetchone() == before, f"row counts and record sets unchanged {before}")
            print("[3/3] smoke (savepoints, rolled back)", flush=True)
            one = cur.execute("SELECT set_id, location_id FROM box.location_stick LIMIT 1").fetchone()
            if one is None:
                _check(True, "no stick row to try (empty table)")
            else:
                key = f"set_id = {int(one[0])} AND location_id = {int(one[1])}"
                cur.execute("SAVEPOINT s")
                cur.execute(f"UPDATE box.location_stick SET tvd_rung = 'grid', tvd_anchor = ARRAY['grid 5-15 mi'], flags = flags || ARRAY['grid_bounded', 'outside_grid'] WHERE {key}")
                cur.execute("ROLLBACK TO SAVEPOINT s")
                _check(True, "a stick row takes tvd_rung 'grid' and both new flags")
                _check(_refused(cur, f"UPDATE box.location_stick SET tvd_rung = 'guess', tvd_anchor = ARRAY['x'] WHERE {key}"), "an unknown rung is still refused")
                _check(_refused(cur, f"UPDATE box.location_stick SET flags = ARRAY['made_up'] WHERE {key}"), "an unknown flag is still refused")
            _check(cur.execute(_COUNTS).fetchone() == before, "nothing left behind by the smoke")
        if a.dry_run or _fail:
            conn.rollback()
            print("ROLLED BACK: nothing persisted" + (f" ({_fail} FAILED)" if _fail else ""), flush=True)
        else:
            conn.commit()
            print("COMMITTED", flush=True)
    print("all checks passed" if not _fail else f"{_fail} check(s) FAILED", flush=True)
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
