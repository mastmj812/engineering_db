"""BOX D104 — keep the record run plus every run Steven has priced; delete the rest.

    python -m scripts.box_prune_runs            dry run: lists what would go and what stays (read-only)
    python -m scripts.box_prune_runs --apply    deletes in ONE transaction, with checks before COMMIT (any failure rolls back)

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
_CHILDREN = ("pud_forecast", "pud_forecast_stream", "pud_forecast_month", "location_analog")


def select_prune(runs: list[tuple[Any, ...]]) -> list[int]:
    """D104: not the record and never priced."""
    return [int(r[0]) for r in runs if not r[1] and int(r[5]) == 0]


def _counts(q: Any, rid: int) -> dict[str, int]:
    return {t: q(f"SELECT count(*) FROM box.{t} WHERE run_id = %s", (rid,)).fetchone()[0] for t in _CHILDREN}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
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
            prune = select_prune(runs)
            keep = [int(r[0]) for r in runs if int(r[0]) not in prune]
            print(f"record {rec[0]}; prune {prune}; keep {keep}", flush=True)
            if not a.apply or not prune:
                print("dry run: nothing deleted" if not a.apply else "nothing to prune")
                conn.rollback()
                return 0
            before_keep = {k: _counts(q, k) for k in keep}
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
            if q("SELECT run_id FROM box.forecast_run WHERE is_record").fetchall() != [(rec[0],)]:
                fails.append("record run changed")
            if fails:
                conn.rollback()
                raise SystemExit(f"checks FAILED, rolled back: {fails}")
        conn.commit()
    finally:
        conn.close()
    print(f"pruned runs {prune}; kept {keep}; record {rec[0]} unchanged; no orphan rows ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
