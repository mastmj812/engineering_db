"""Build curated.intel_forecast_accuracy (Supabase) — sql/38.

  1. sql/26 geography indexes (idempotent) — the rep-stick ST_DWithin inside
     sql/38 seq-scans for hours without the intel_locations expression index
     (the sql/30 lesson: 15 h unindexed, minutes indexed).
  2. sql/38 — intel_pdp_cliff_date() + the accuracy matview.
  3. Validate: cliff date, tier x basin counts, mop-depth distribution,
     per-ft/raw decomposition identity on the direct tier.

Quarterly-reload position (SKILL.md §5): after apply_reconciled_inventory
(and apply_intel_formation_blueox / the intel matviews it reads), before
apply_erebor_locations — erebor_locations stays the FINAL step.

Run from repo root in the venv:
    python -m scripts.apply_intel_forecast_accuracy
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
    print("[1/3] geography indexes (sql/26, idempotent — required before sql/38)", flush=True)
    _exec("geography indexes", "26_geography_indexes.sql")

    print("[2/3] build curated.intel_forecast_accuracy (sql/38)", flush=True)
    _exec("intel_forecast_accuracy", "38_intel_forecast_accuracy.sql")

    print("[3/3] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cliff = cur.execute("SELECT curated.intel_pdp_cliff_date()").fetchone()[0]
            print(f"  recognition cliff: {cliff}", flush=True)
            print("  tier x basin (distinct wells):", flush=True)
            for tier, basin, n in cur.execute(
                "SELECT tier, basin, COUNT(DISTINCT api10) "
                "FROM curated.intel_forecast_accuracy GROUP BY 1,2 ORDER BY 1,2"
            ).fetchall():
                print(f"    {tier:7} {basin:9} {n}", flush=True)
            print("  wells with >= m aligned months:", flush=True)
            for m in (3, 6, 9, 12):
                n = cur.execute(
                    "SELECT COUNT(DISTINCT api10) FROM curated.intel_forecast_accuracy "
                    "WHERE mop >= %s AND pct_err_oil_perft IS NOT NULL", (m,)
                ).fetchone()[0]
                print(f"    mop>={m:2}  {n}", flush=True)
            # decomposition identity on the direct tier:
            #   pct_err_perft = (1 + pct_err)/ll_ratio - 1  (float tolerance)
            bad = cur.execute(
                "SELECT COUNT(*) FROM curated.intel_forecast_accuracy "
                "WHERE tier='direct' AND pct_err_oil IS NOT NULL "
                "  AND ll_ratio IS NOT NULL AND pct_err_oil_perft IS NOT NULL "
                "  AND abs(pct_err_oil_perft - ((1 + pct_err_oil)/ll_ratio - 1)) > 1e-9"
            ).fetchone()[0]
            print(f"  per-ft decomposition identity violations: {bad} (expect 0)", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
