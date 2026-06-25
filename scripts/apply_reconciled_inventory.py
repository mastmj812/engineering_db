"""Build curated.producing_reference + curated.reconciled_inventory (Supabase).

  1. producing_reference (sql/20) — producing wells, pre-buffered + GiST-indexed.
  2. reconciled_inventory (sql/21) — overlap-based PUD reconciliation (heavy).
  3. Validate: status distribution + realized count vs the new-well anchor.

Run from repo root in the venv:
    python -m scripts.apply_reconciled_inventory
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"


def _exec(label: str, fname: str) -> None:
    t0 = time.monotonic()
    text = (SQL / fname).read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(text)
    finally:
        conn.close()
    print(f"    {label} done in {time.monotonic() - t0:.0f}s", flush=True)


def main() -> None:
    t = time.monotonic()
    print("[1/3] build curated.producing_reference", flush=True)
    _exec("producing_reference", "20_producing_reference.sql")
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            n = cur.execute("SELECT COUNT(*) FROM curated.producing_reference").fetchone()[0]
        print(f"    {n} producing reference wells", flush=True)
    finally:
        conn.close()

    print("[2/3] build curated.reconciled_inventory (overlap matching — heavy)", flush=True)
    _exec("reconciled_inventory", "21_reconciled_inventory.sql")

    print("[3/3] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("  status x basin:", flush=True)
            for b, s, n in cur.execute(
                "SELECT basin_blueox, status, COUNT(*) "
                "FROM curated.reconciled_inventory GROUP BY 1,2 ORDER BY 1,2"
            ).fetchall():
                print(f"    {b:9} {s:22} {n}", flush=True)
            # realized count vs new-well anchor (Delaware)
            realized_del = cur.execute(
                "SELECT COUNT(*) FROM curated.reconciled_inventory "
                "WHERE basin_blueox='delaware' AND status='realized_pud_to_pdp'"
            ).fetchone()[0]
            distinct_wells = cur.execute(
                "SELECT COUNT(DISTINCT matched_api10) FROM curated.reconciled_inventory "
                "WHERE basin_blueox='delaware' AND status='realized_pud_to_pdp'"
            ).fetchone()[0]
            new_del = cur.execute(
                "SELECT COUNT(*) FROM curated.wells w JOIN curated.formation_blueox fb ON fb.api10=w.api10 "
                "WHERE fb.basin_blueox='delaware' AND w.first_production_date > DATE '2025-09-30'"
            ).fetchone()[0]
            print(f"  anchor: Delaware realized PUDs={realized_del} "
                  f"(distinct wells={distinct_wells}) vs wells online since 3Q25={new_del}", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
