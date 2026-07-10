"""Build curated.intel_pdp_support (sql/30) + validate (Supabase oilgas).

Clone of scripts/apply_reconciled_inventory.py / apply_erebor_locations.py:
exec the DDL on the 5432 session (statement_timeout=0), then validate.

  1. exec sql/30 — DROP ... CASCADE + CREATE MATERIALIZED VIEW ... WITH DATA +
     the UNIQUE index (basin-wide, PUD+RES; ~25-45 min on the 2 GB instance).
  2. validate: row count == PUD/RES count; 0 duplicate/NULL stick_id; per-basin
     scored / unscorable / unsupported / NULL-ratio shape; EXPLAIN index
     assertion (idx_curated_wells_wellstick_geog, no Seq Scan); CONCURRENTLY
     refresh smoke test.
  3. optional --bitcompare: re-run the Phase-1 Loving+Winkler exploration scan and
     assert the matview's L+W PUD rows match it (SAME-DAY only — the current_date
     6-month gate makes cross-day content differ). ~2 min extra.

STEP in the quarterly Novi reload — runs AFTER apply_reconciled_inventory and
BEFORE apply_erebor_locations (the FINAL step); see the sql/30 header. This
matview DROP-CASCADEs with curated.intel_locations, so it must be rebuilt on
every quarterly reload.

⚠ DDL on the shared warehouse. Run from repo root in the venv:
    python -m scripts.apply_intel_pdp_support [--bitcompare]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from etl.db import get_connection
# Reuse the exploration's exact scan + EXPLAIN so the bit-compare and the index
# assertion stay in lockstep with the productionized gate in sql/30.
from scripts.explore_pdp_support import COLS, EXPLAIN_SQL, SCAN_SQL

SQL = Path(__file__).resolve().parent.parent / "sql"

# Score columns shared by the exploration TEMP table and the matview (bit-compare).
_SCORE_COLS = [c for c in COLS if c not in (
    "stick_id", "unique_id", "basin", "county", "formation_blueox",
    "tvd", "oil_eur", "ll_ft",
)]


def build(conn) -> None:
    print("[1/3] exec sql/30 — build curated.intel_pdp_support (basin-wide, heavy)", flush=True)
    t = time.monotonic()
    with conn.cursor() as cur:
        cur.execute((SQL / "30_intel_pdp_support.sql").read_text(encoding="utf-8"))
    print(f"    built in {time.monotonic() - t:.0f}s", flush=True)


def validate(conn) -> None:
    print("[2/3] validation", flush=True)
    with conn.cursor() as cur:
        # relkind + row count vs the PUD/RES universe (LEFT JOIN keeps every stick).
        relkind = cur.execute(
            "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='curated' AND c.relname='intel_pdp_support'"
        ).fetchone()[0]
        n = cur.execute("SELECT COUNT(*) FROM curated.intel_pdp_support").fetchone()[0]
        expected = cur.execute(
            "SELECT COUNT(*) FROM curated.intel_locations WHERE category IN ('PUD','RES')"
        ).fetchone()[0]
        ok = "OK" if n == expected else "MISMATCH"
        print(f"    relkind={relkind!r} (expect 'm')  rows={n}  PUD/RES universe={expected}  [{ok}]", flush=True)

        # stick_id uniqueness (CONCURRENTLY needs it).
        dups = cur.execute(
            "SELECT COUNT(*) FROM (SELECT stick_id FROM curated.intel_pdp_support "
            "GROUP BY 1 HAVING COUNT(*) > 1) x"
        ).fetchone()[0]
        nulls = cur.execute(
            "SELECT COUNT(*) FROM curated.intel_pdp_support WHERE stick_id IS NULL"
        ).fetchone()[0]
        print(f"    stick_id duplicates={dups} nulls={nulls} (both must be 0)", flush=True)

        # Per-basin x category shape — sanity-check vs Phase-1 (L+W PUD was
        # ~10.7% unsupported@3mi, ~6% NULL inflation).
        print("    per basin x category: n / unscorable(NULL) / unsupported@3mi / NULL-ratio", flush=True)
        for basin, cat, tot, unscore, unsup, nullr in cur.execute("""
            SELECT il.basin, il.category,
                   COUNT(*),
                   COUNT(*) FILTER (WHERE s.pdp_count_3mi IS NULL),
                   COUNT(*) FILTER (WHERE s.pdp_count_3mi = 0),
                   COUNT(*) FILTER (WHERE s.inflation_ratio IS NULL)
            FROM curated.intel_pdp_support s
            JOIN curated.intel_locations il USING (stick_id)
            GROUP BY 1,2 ORDER BY 1,2
        """).fetchall():
            scored = tot - unscore
            up = f"{100*unsup/scored:.1f}%" if scored else "  -  "
            nr = f"{100*nullr/tot:.1f}%"
            print(f"      {basin:9} {cat:4} n={tot:>7}  unscorable={unscore:>5}  "
                  f"unsupported@3mi={unsup:>6} ({up} of scored)  NULL-ratio={nullr:>6} ({nr})", flush=True)

        # EXPLAIN the lateral body for one scorable stick — assert the geography
        # expression index (no Seq Scan of curated.wells).
        stick = cur.execute(
            "SELECT stick_id FROM curated.intel_pdp_support "
            "WHERE pdp_count_5mi IS NOT NULL ORDER BY pdp_count_5mi DESC LIMIT 1"
        ).fetchone()[0]
        plan = "\n".join(r[0] for r in cur.execute(EXPLAIN_SQL, (stick, stick)).fetchall())
        hit = "idx_curated_wells_wellstick_geog" in plan
        print(f"    EXPLAIN(stick {stick}) uses idx_curated_wells_wellstick_geog: "
              f"{'YES' if hit else 'NO -- SEQ SCAN, investigate'}", flush=True)
        if not hit:
            for line in plan.splitlines():
                print(f"      {line}", flush=True)

    # CONCURRENTLY refresh smoke test (autocommit; UNIQUE index + WITH DATA path).
    print("    CONCURRENTLY refresh smoke test:", flush=True)
    t = time.monotonic()
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.intel_pdp_support")
    print(f"      ok in {time.monotonic() - t:.1f}s", flush=True)


def bitcompare(conn) -> None:
    """Re-run the Phase-1 L+W exploration scan and diff its rows against the
    matview. Only valid SAME-DAY as the build (current_date 6-month gate)."""
    print("[3/3] bit-compare vs Phase-1 Loving+Winkler exploration (same-day only)", flush=True)
    t = time.monotonic()
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS pdp_support")
        cur.execute(SCAN_SQL)  # TEMP pdp_support, L+W PUD, identical gate
        e_n = cur.execute("SELECT COUNT(*) FROM pdp_support").fetchone()[0]

        # Every explored stick must be present in the matview.
        missing = cur.execute(
            "SELECT COUNT(*) FROM pdp_support e "
            "LEFT JOIN curated.intel_pdp_support m ON m.stick_id = e.stick_id "
            "WHERE m.stick_id IS NULL"
        ).fetchone()[0]

        # Cell-level diff on the shared score columns. round() floats to 6 dp to
        # avoid float-repr noise; IS DISTINCT FROM makes NULLs compare equal.
        conds = []
        for c in _SCORE_COLS:
            if c in ("pdp_count_1mi", "pdp_count_3mi", "pdp_count_5mi", "n_offsets_5mi",
                     "support_lateral_ft_5mi"):
                conds.append(f"e.{c} IS DISTINCT FROM m.{c}")
            else:
                conds.append(f"round(e.{c}::numeric, 6) IS DISTINCT FROM round(m.{c}::numeric, 6)")
        where = " OR ".join(conds)
        mism = cur.execute(
            f"SELECT COUNT(*) FROM pdp_support e "
            f"JOIN curated.intel_pdp_support m ON m.stick_id = e.stick_id "
            f"WHERE {where}"
        ).fetchone()[0]
    ok = "OK" if (missing == 0 and mism == 0) else "MISMATCH"
    print(f"    explored L+W PUDs={e_n}  missing_from_matview={missing}  "
          f"cell_mismatches={mism}  [{ok}]  ({time.monotonic() - t:.0f}s)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bitcompare", action="store_true",
                    help="re-scan Loving+Winkler and diff vs the matview (same-day only, ~2 min)")
    args = ap.parse_args()

    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        build(conn)
        validate(conn)
        if args.bitcompare:
            bitcompare(conn)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t0:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
