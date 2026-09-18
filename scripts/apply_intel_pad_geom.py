"""Build curated.intel_pad_geom (sql/45) + validate (Supabase oilgas).

Clone of scripts/apply_intel_pdp_support.py: exec the DDL on the 5432 session
(statement_timeout=0), then validate.

  1. exec sql/45 — DROP ... CASCADE + CREATE MATERIALIZED VIEW ... WITH DATA +
     UNIQUE (basin, pad_name) + GiST(geom) + COMMENTs. Small (~6k rows; the
     read-only dry run of the body took ~1.5 s).
  2. validate: rows == distinct (basin, pad_name) in intel_locations (identity,
     not a constant); every padded stick accounted for; 0 dup/NULL keys; all
     geoms valid POLYGONs; per-basin acreage shape; EXPLAIN index assertion
     (idx_intel_pad_geom_pk on the erebor gunbarrel lookup); CONCURRENTLY smoke.

STEP in the quarterly Novi reload — anywhere after `load_intel_sf --curated`
(depends only on curated.intel_locations, which DROP-CASCADEs it).

⚠ DDL on the shared warehouse. Run from repo root in the venv:
    python -m scripts.apply_intel_pad_geom
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"


def build(conn) -> None:
    print("[1/2] exec sql/45 — build curated.intel_pad_geom", flush=True)
    t = time.monotonic()
    with conn.cursor() as cur:
        cur.execute((SQL / "45_intel_pad_geom.sql").read_text(encoding="utf-8"))
    print(f"    built in {time.monotonic() - t:.1f}s", flush=True)


def validate(conn) -> bool:
    print("[2/2] validation", flush=True)
    ok = True
    with conn.cursor() as cur:
        relkind = cur.execute(
            "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='curated' AND c.relname='intel_pad_geom'"
        ).fetchone()[0]
        print(f"    relkind={relkind!r} (expect 'm')", flush=True)
        ok &= relkind == "m"

        # Identity: one row per distinct padded (basin, pad_name) with geometry,
        # and every padded stick lands in exactly one hull.
        n, sticks = cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(n_sticks), 0) FROM curated.intel_pad_geom"
        ).fetchone()
        exp_n, exp_sticks = cur.execute("""
            SELECT COUNT(DISTINCT (basin, pad_name)), COUNT(*)
            FROM curated.intel_locations
            WHERE pad_name IS NOT NULL AND pad_name <> '' AND wellstick_geom IS NOT NULL
        """).fetchone()
        tag = "OK" if (n, sticks) == (exp_n, exp_sticks) else "MISMATCH"
        print(f"    rows={n} expected={exp_n}  sticks={sticks} expected={exp_sticks}  [{tag}]", flush=True)
        ok &= tag == "OK"

        dups, nulls = cur.execute("""
            SELECT (SELECT COUNT(*) FROM (SELECT 1 FROM curated.intel_pad_geom
                     GROUP BY basin, pad_name HAVING COUNT(*) > 1) x),
                   (SELECT COUNT(*) FROM curated.intel_pad_geom
                     WHERE basin IS NULL OR pad_name IS NULL OR geom IS NULL)
        """).fetchone()
        print(f"    key duplicates={dups} NULL key/geom={nulls} (both must be 0)", flush=True)
        ok &= dups == 0 and nulls == 0

        types, invalid = cur.execute("""
            SELECT array_agg(DISTINCT GeometryType(geom)),
                   COUNT(*) FILTER (WHERE NOT ST_IsValid(geom))
            FROM curated.intel_pad_geom
        """).fetchone()
        print(f"    geometry types={types} invalid={invalid} (expect ['POLYGON'], 0)", flush=True)
        ok &= types == ["POLYGON"] and invalid == 0

        # Shape per basin. Legacy Novi DSU median was ~956 ac (Delaware 2025Q3);
        # sanity-check order of magnitude, don't pin constants. A basin missing
        # here = Novi shipped no pad_name for it this vintage (expected gap).
        print("    per basin: pads / sticks / acres P10-P50-P90", flush=True)
        for basin, pads, st, p10, p50, p90 in cur.execute("""
            SELECT basin, COUNT(*), SUM(n_sticks),
                   percentile_cont(0.1) WITHIN GROUP (ORDER BY acres),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY acres),
                   percentile_cont(0.9) WITHIN GROUP (ORDER BY acres)
            FROM curated.intel_pad_geom GROUP BY 1 ORDER BY 1
        """).fetchall():
            print(f"      {basin:9} pads={pads:>6} sticks={st:>7}  acres {p10:,.0f} / {p50:,.0f} / {p90:,.0f}", flush=True)
        for basin, in cur.execute("""
            SELECT DISTINCT basin FROM curated.intel_locations
            EXCEPT SELECT DISTINCT basin FROM curated.intel_pad_geom ORDER BY 1
        """).fetchall():
            print(f"      {basin:9} NO PADS — Novi shipped no pad_name for this basin (erebor shows a notice)", flush=True)

        # EXPLAIN the erebor gunbarrel lookup — assert the PK index, no Seq Scan.
        basin, pad = cur.execute(
            "SELECT basin, pad_name FROM curated.intel_pad_geom ORDER BY n_sticks DESC LIMIT 1"
        ).fetchone()
        plan = "\n".join(r[0] for r in cur.execute(
            "EXPLAIN SELECT geom FROM curated.intel_pad_geom WHERE basin = %s AND pad_name = %s",
            (basin, pad),
        ).fetchall())
        hit = "idx_intel_pad_geom_pk" in plan
        print(f"    EXPLAIN pad lookup uses idx_intel_pad_geom_pk: {'YES' if hit else 'NO -- investigate'}", flush=True)
        if not hit:
            for line in plan.splitlines():
                print(f"      {line}", flush=True)
        ok &= hit

    print("    CONCURRENTLY refresh smoke test:", flush=True)
    t = time.monotonic()
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.intel_pad_geom")
    print(f"      ok in {time.monotonic() - t:.1f}s", flush=True)
    return ok


def main() -> None:
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        build(conn)
        ok = validate(conn)
    finally:
        conn.close()
    print(f"=== {'DONE' if ok else 'DONE WITH FAILURES'} in {time.monotonic() - t0:.0f}s ===", flush=True)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
