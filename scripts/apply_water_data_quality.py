"""Build curated.water_data_quality (Supabase) — sql/41.

  1. sql/41 — the provenance matview (aggregate-only over curated.production;
     no PostGIS, no CASCADE reach — nothing else depends on it yet).
  2. Validate: row-count identity (== distinct api10 in curated.production),
     unique-key integrity, label distribution vs the 2026-08-17 analysis
     (TX 'calculated' ~0.8 of classifiable wells, NM ~0), and a
     REFRESH ... CONCURRENTLY smoke with timing.

Standalone nightly matview: refreshed via etl/db.py:_CURATED_MATVIEWS right
after curated.production; NOT part of the quarterly intel chain.

Run from repo root in the venv:
    python -m scripts.apply_water_data_quality
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
    print("[1/2] build curated.water_data_quality (sql/41)", flush=True)
    _exec("water_data_quality", "41_water_data_quality.sql")

    print("[2/2] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            n_mv = cur.execute(
                "SELECT COUNT(*) FROM curated.water_data_quality"
            ).fetchone()[0]
            n_src = cur.execute(
                "SELECT COUNT(DISTINCT api10) FROM curated.production"
            ).fetchone()[0]
            assert n_mv == n_src, (
                f"row-count identity broken: matview {n_mv} != "
                f"distinct production api10 {n_src}"
            )
            print(f"  rows: {n_mv} (== distinct api10 in production)", flush=True)

            dups = cur.execute(
                "SELECT COUNT(*) FROM (SELECT api10 FROM curated.water_data_quality "
                "GROUP BY 1 HAVING COUNT(*) > 1) d"
            ).fetchone()[0]
            nulls = cur.execute(
                "SELECT COUNT(*) FROM curated.water_data_quality WHERE api10 IS NULL"
            ).fetchone()[0]
            assert dups == 0 and nulls == 0, f"key integrity: {dups} dup / {nulls} null"
            print("  key integrity: 0 dup / 0 null api10", flush=True)

            print("  water_source x state (horizontals, FP >= 2019):", flush=True)
            for state, src, n in cur.execute(
                "SELECT w.state, q.water_source, COUNT(*) "
                "FROM curated.water_data_quality q "
                "JOIN curated.wells_enriched w USING (api10) "
                "WHERE w.is_horizontal AND w.first_production_date >= '2019-01-01' "
                "GROUP BY 1, 2 ORDER BY 1, 2"
            ).fetchall():
                print(f"    {state:12} {src:13} {n}", flush=True)

            # Sanity: among classifiable TX horizontals FP>=2019, 'calculated'
            # should dominate (~0.8 per the 2026-08-17 analysis); NM near zero.
            tx = dict(
                cur.execute(
                    "SELECT q.water_source, COUNT(*) "
                    "FROM curated.water_data_quality q "
                    "JOIN curated.wells_enriched w USING (api10) "
                    "WHERE w.state = 'Texas' AND w.is_horizontal "
                    "AND w.first_production_date >= '2019-01-01' "
                    "AND q.water_source IN ('calculated','measured','indeterminate') "
                    "GROUP BY 1"
                ).fetchall()
            )
            share = tx.get("calculated", 0) / max(sum(tx.values()), 1)
            assert 0.5 < share < 0.95, f"TX calculated share {share:.2f} outside sanity band"
            print(f"  TX calculated share (classifiable, hz, FP>=2019): {share:.3f}", flush=True)

            t0 = time.monotonic()
            cur.execute(
                "REFRESH MATERIALIZED VIEW CONCURRENTLY curated.water_data_quality"
            )
            print(
                f"  REFRESH CONCURRENTLY smoke: {time.monotonic() - t0:.0f}s",
                flush=True,
            )
    finally:
        conn.close()

    print(f"all done in {time.monotonic() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
