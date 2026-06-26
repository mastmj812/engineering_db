"""Apply the §6 reconciliation follow-ups on Supabase:

  1. reconciled_inventory (sql/21) — rebuilt to match producers on the TVD-CORRECTED
     bench (sql/23), so recolored producers realize their true-bench PUDs.
  2. net_new_pdp (sql/25) — reverse pass: post-vintage producers that realized no PUD.

Validation: status distribution, the new-well anchor (new wells ≈ realized + net_new),
and the 3002550278 realization spot-check (was unmatched as BS2_S; should now match a
WCA_1 PUD).

Run from repo root in the venv:
    python -m scripts.apply_followups
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
    print("[1/3] rebuild curated.reconciled_inventory (corrected-bench match — heavy)", flush=True)
    _exec("reconciled_inventory", "21_reconciled_inventory.sql")
    print("[2/3] build curated.net_new_pdp", flush=True)
    _exec("net_new_pdp", "25_net_new_pdp.sql")

    print("[3/3] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("  reconciled_inventory status x basin:", flush=True)
            for b, s, n in cur.execute(
                "SELECT basin_blueox, status, COUNT(*) FROM curated.reconciled_inventory "
                "GROUP BY 1,2 ORDER BY 1,2"
            ).fetchall():
                print(f"    {b:9} {s:22} {n}", flush=True)

            print("  net_new_pdp by basin:", flush=True)
            for b, n in cur.execute(
                "SELECT basin_blueox, COUNT(*) FROM curated.net_new_pdp GROUP BY 1 ORDER BY 1"
            ).fetchall():
                print(f"    {b:9} {n}", flush=True)

            print("  new-well anchor (since 3Q25 = realized distinct + net_new?):", flush=True)
            for b in ("delaware", "midland"):
                realized = cur.execute(
                    "SELECT COUNT(DISTINCT matched_api10) FROM curated.reconciled_inventory "
                    "WHERE basin_blueox=%s AND status='realized_pud_to_pdp'", (b,)
                ).fetchone()[0]
                netnew = cur.execute(
                    "SELECT COUNT(*) FROM curated.net_new_pdp WHERE basin_blueox=%s", (b,)
                ).fetchone()[0]
                newwells = cur.execute(
                    "SELECT COUNT(*) FROM curated.producing_reference "
                    "WHERE basin=%s AND first_production_date > DATE '2025-09-30'", (b,)
                ).fetchone()[0]
                print(f"    {b:9} new={newwells}  realized_distinct={realized}  net_new={netnew}  "
                      f"(realized+net_new={realized + netnew})", flush=True)

            print("  3002550278 corrected-code win — PUDs it now realizes:", flush=True)
            rows = cur.execute(
                "SELECT stick_id, formation_blueox, status, match_overlap "
                "FROM curated.reconciled_inventory WHERE matched_api10='3002550278'"
            ).fetchall()
            if rows:
                for sid, code, st, ov in rows:
                    print(f"    stick {sid}: {code} {st} overlap={ov}", flush=True)
            else:
                print("    (none — still realizing no PUD)", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
