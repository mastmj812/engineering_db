"""Apply the §6 reconciliation follow-ups on Supabase:

  1. reconciled_inventory (sql/68; supersedes sql/21) — every Novi stick (PUD + RES, D117)
     matched to producers on the TVD-CORRECTED bench (sql/23).
  2. net_new_pdp (sql/25) — reverse pass: post-vintage producers that realized no Novi stick.
  3. intel_forecast_accuracy (sql/38 + sql/43) — the reconciliation CASCADE drops sql/38;
     rebuilt here (it used to stay dropped after a standalone run).
  4. erebor_locations (sql/22) — CASCADE victim, rebuilt last.

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
    print("[1/4] rebuild curated.reconciled_inventory (corrected-bench match — heavy)", flush=True)
    _exec("reconciled_inventory", "68_reconcile_all_sticks.sql")
    print("[2/4] build curated.net_new_pdp", flush=True)
    _exec("net_new_pdp", "25_net_new_pdp.sql")
    # The sql/68 rebuild DROP ... CASCADE drops curated.erebor_locations (it joins
    # reconciled_inventory for recon_status), so recreate it.
    # sql/22 now also joins curated.intel_pdp_support (sql/30). The sql/68 rebuild
    # does NOT drop it (it depends on intel_locations, not reconciled_inventory),
    # but a full quarterly reload WOULD — fail clearly here rather than let the
    # sql/22 CREATE error deep inside on a missing relation.
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            has_support = cur.execute(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'curated' AND c.relname = 'intel_pdp_support' "
                "AND c.relkind = 'm'"
            ).fetchone()
    finally:
        conn.close()
    if not has_support:
        raise RuntimeError(
            "curated.intel_pdp_support is missing but sql/22 joins it. Run "
            "`python -m scripts.apply_intel_pdp_support` first (it is dropped by a "
            "quarterly intel_locations CASCADE)."
        )
    # The same CASCADE drops curated.intel_forecast_accuracy (sql/38); restore it
    # (and sql/43, which matches every Novi stick too since D117) before sql/22.
    print("[3a/4] rebuild intel_forecast_accuracy (sql/38 + sql/43; CASCADE victim)", flush=True)
    from scripts import apply_intel_forecast_accuracy
    apply_intel_forecast_accuracy.main()
    print("[3/4] recreate curated.erebor_locations (CASCADE-dropped by the rebuild)", flush=True)
    _exec("erebor_locations", "22_erebor_locations.sql")
    _exec("box_scout_locations", "69_box_scout_locations.sql")  # sql/22's CASCADE drops the dependent sql/69 view

    print("[4/4] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("  reconciled_inventory status x basin x category (D117: audit split only):", flush=True)
            for b, c, s, n in cur.execute(
                "SELECT basin_blueox, category, status, COUNT(*) FROM curated.reconciled_inventory "
                "GROUP BY 1,2,3 ORDER BY 1,2,3"
            ).fetchall():
                print(f"    {b:9} {c:4} {s:22} {n}", flush=True)

            print("  net_new_pdp by basin:", flush=True)
            for b, n in cur.execute(
                "SELECT basin_blueox, COUNT(*) FROM curated.net_new_pdp GROUP BY 1 ORDER BY 1"
            ).fetchall():
                print(f"    {b:9} {n}", flush=True)

            print("  new-well anchor (since 3Q25 = realized_drift distinct + net_new?):", flush=True)
            for b in ("delaware", "midland"):
                drift = cur.execute(
                    "SELECT COUNT(DISTINCT matched_api10) FROM curated.reconciled_inventory "
                    "WHERE basin_blueox=%s AND status='realized_drift'", (b,)
                ).fetchone()[0]
                netnew = cur.execute(
                    "SELECT COUNT(*) FROM curated.net_new_pdp WHERE basin_blueox=%s", (b,)
                ).fetchone()[0]
                newwells = cur.execute(
                    "SELECT COUNT(*) FROM curated.producing_reference "
                    "WHERE basin=%s AND first_production_date > DATE '2025-09-30'", (b,)
                ).fetchone()[0]
                print(f"    {b:9} new={newwells}  drift_distinct={drift}  net_new={netnew}  "
                      f"(drift+net_new={drift + netnew})", flush=True)

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
