"""BOX run retention — D123 (supersedes D104): keep ONLY the record run; every earlier run is pruned once a new record is published.

    python -m scripts.box_prune_runs                            dry run: lists what would go and what stays (read-only)
    python -m scripts.box_prune_runs --apply                    deletes every non-record run Steven has NOT priced
    python -m scripts.box_prune_runs --apply --include-priced   D123: also deletes priced runs, their box_econ.box_pud_econ rows
                                                                first, in the same transaction (Steven's econ for a superseded run)

Everything happens in ONE transaction, with checks before COMMIT (any failure rolls back).

A run is pruned when it is NOT the record and has no box_econ.box_pud_econ row. Its pud_forecast / _stream / _month /
location_analog rows cascade (sql/60); box.location rows are shared across runs and stay. box_econ's FK is NO ACTION, so a
priced run could never be deleted even if the selection were wrong. The superseded_by chain is cleared on rows that point at a
pruned run (only another pruned run can, since the record is never superseded by an older run).
!! Deletes on the shared warehouse: Michael's explicit go (D104, 2026-10-17).
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from etl.db import get_connection

_RUNS_SQL = """
SELECT f.run_id, f.is_record, f.superseded_by,
       (SELECT count(*) FROM box.pud_forecast p WHERE p.run_id = f.run_id) AS n_pud,
       (SELECT count(*) FROM box.pud_forecast_month m WHERE m.run_id = f.run_id) AS n_month,
       (SELECT count(*) FROM box_econ.box_pud_econ e WHERE e.run_id = f.run_id) AS n_priced
FROM box.forecast_run f ORDER BY f.run_id
"""
_CHILDREN = ("pud_forecast", "pud_forecast_stream", "pud_forecast_month", "location_analog", "location_water_analog", "pud_proximity",
             "pud_proximity_parent")


def select_prune(runs: list[tuple[Any, ...]], include_priced: bool = False) -> list[int]:
    """Not the record; priced runs only with include_priced (D123: the record is the only run worth keeping)."""
    return [int(r[0]) for r in runs if not r[1] and (include_priced or int(r[5]) == 0)]


def _counts(q: Any, rid: int) -> dict[str, int]:
    return {t: q(f"SELECT count(*) FROM box.{t} WHERE run_id = %s", (rid,)).fetchone()[0] for t in _CHILDREN}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-priced", action="store_true", help="D123: prune priced runs too, deleting their box_econ rows first")
    a = ap.parse_args(argv)
    t0 = time.time()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            q = cur.execute
            print(f"target {q('select inet_server_addr(), inet_server_port(), current_database()').fetchone()}", flush=True)
            runs = q(_RUNS_SQL).fetchall()
            for r in runs:
                print(f"  run {r[0]}: record={r[1]} superseded_by={r[2]} pud_forecast={r[3]:,} months={r[4]:,} priced_rows={r[5]:,}")
            rec = [int(r[0]) for r in runs if r[1]]
            if len(rec) != 1:
                raise SystemExit(f"expected exactly one record run, found {rec}")
            prune = select_prune(runs, a.include_priced)
            priced = {int(r[0]): int(r[5]) for r in runs if int(r[0]) in prune and int(r[5])}
            held = [int(r[0]) for r in runs if not r[1] and int(r[5]) and int(r[0]) not in prune]
            if held:
                print(f"held (priced; D123 prunes them with --include-priced): {held}", flush=True)
            if priced:
                print(f"priced runs to prune, box_econ rows deleted first: {priced}", flush=True)
            keep = [int(r[0]) for r in runs if int(r[0]) not in prune]
            print(f"record {rec[0]}; prune {prune}; keep {keep}", flush=True)
            if not a.apply or not prune:
                print("dry run: nothing deleted" if not a.apply else "nothing to prune")
                conn.rollback()
                return 0
            before_keep = {k: _counts(q, k) for k in keep}
            econ_keep = q("SELECT count(*) FROM box_econ.box_pud_econ WHERE NOT (run_id = ANY(%s))", (prune,)).fetchone()[0]
            if priced:
                q("DELETE FROM box_econ.box_pud_econ WHERE run_id = ANY(%s)", (list(priced),))
            q("UPDATE box.forecast_run SET superseded_by = NULL WHERE superseded_by = ANY(%s)", (prune,))
            q("DELETE FROM box.forecast_run WHERE run_id = ANY(%s)", (prune,))
            fails = []
            left = q("SELECT count(*) FROM box.forecast_run WHERE run_id = ANY(%s)", (prune,)).fetchone()[0]
            if left:
                fails.append(f"{left} pruned runs still present")
            for t in _CHILDREN:
                n = q(f"SELECT count(*) FROM box.{t} WHERE run_id = ANY(%s)", (prune,)).fetchone()[0]
                if n:
                    fails.append(f"{n} orphan rows in box.{t}")
            for k, c in before_keep.items():
                if _counts(q, k) != c:
                    fails.append(f"kept run {k} rows changed")
            if q("SELECT count(*) FROM box_econ.box_pud_econ WHERE run_id = ANY(%s)", (prune,)).fetchone()[0]:
                fails.append("box_econ rows left on a pruned run")
            if q("SELECT count(*) FROM box_econ.box_pud_econ").fetchone()[0] != econ_keep:
                fails.append("box_econ rows of a kept run changed")
            if q("SELECT run_id FROM box.forecast_run WHERE is_record").fetchall() != [(rec[0],)]:
                fails.append("record run changed")
            if fails:
                conn.rollback()
                raise SystemExit(f"checks FAILED, rolled back: {fails}")
        conn.commit()
    finally:
        conn.close()
    print(f"pruned runs {prune}; kept {keep}; record {rec[0]} unchanged; no orphan rows"
          + (f"; box_econ rows deleted {priced}" if priced else "") + f" ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
