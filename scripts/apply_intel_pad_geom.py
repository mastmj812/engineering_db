"""Build curated.intel_pad_member + curated.intel_pad_geom (sql/46) + validate.

Clone of scripts/apply_intel_pdp_support.py: exec the DDL on the 5432 session
(statement_timeout=0), then validate.

  1. exec sql/46 — DROP ... CASCADE both + CREATE MATERIALIZED VIEW ... WITH DATA
     (member: UNIQUE stick_id; geom: UNIQUE (basin, pad_key) + GiST) + COMMENTs.
     Small (~320k member rows, ~16k pads; the read-only dry run took ~5 s).
  2. validate by identity, not constants: member rows == padded sticks with
     geometry in intel_locations; geom rows == distinct (basin, pad_key) in
     member and SUM(n_sticks) == member rows; 0 dup/NULL keys; all geoms valid
     POLYGONs; per-basin split count + acreage shape; EXPLAIN index assertion
     (idx_intel_pad_geom_pk on the erebor gunbarrel lookup); CONCURRENTLY smoke
     on both, member first.

STEP in the quarterly Novi reload — anywhere after `load_intel_sf --curated`
(depends only on curated.intel_locations, which DROP-CASCADEs both).

⚠ DDL on the shared warehouse. Run from repo root in the venv:
    python -m scripts.apply_intel_pad_geom
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"


def build(conn) -> None:
    print("[1/2] exec sql/46 — build curated.intel_pad_member + intel_pad_geom", flush=True)
    t = time.monotonic()
    with conn.cursor() as cur:
        cur.execute((SQL / "46_intel_pad_clusters.sql").read_text(encoding="utf-8"))
    print(f"    built in {time.monotonic() - t:.1f}s", flush=True)


def validate(conn) -> bool:
    print("[2/2] validation", flush=True)
    ok = True
    with conn.cursor() as cur:
        for rel in ("intel_pad_member", "intel_pad_geom"):
            relkind = cur.execute(
                "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='curated' AND c.relname=%s",
                (rel,),
            ).fetchone()[0]
            print(f"    {rel} relkind={relkind!r} (expect 'm')", flush=True)
            ok &= relkind == "m"

        # Identity: every padded stick with geometry lands in exactly one group...
        members = cur.execute("SELECT COUNT(*) FROM curated.intel_pad_member").fetchone()[0]
        exp_members = cur.execute("""
            SELECT COUNT(*) FROM curated.intel_locations
            WHERE pad_name IS NOT NULL AND pad_name <> '' AND wellstick_geom IS NOT NULL
        """).fetchone()[0]
        tag = "OK" if members == exp_members else "MISMATCH"
        print(f"    member rows={members} expected={exp_members}  [{tag}]", flush=True)
        ok &= tag == "OK"

        # ...and one polygon per distinct (basin, pad_key) whose hull holds them all.
        n, sticks = cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(n_sticks), 0) FROM curated.intel_pad_geom"
        ).fetchone()
        exp_n = cur.execute(
            "SELECT COUNT(DISTINCT (basin, pad_key)) FROM curated.intel_pad_member"
        ).fetchone()[0]
        tag = "OK" if (n, sticks) == (exp_n, members) else "MISMATCH"
        print(f"    geom rows={n} expected={exp_n}  sticks={sticks} expected={members}  [{tag}]", flush=True)
        ok &= tag == "OK"

        dups, nulls = cur.execute("""
            SELECT (SELECT COUNT(*) FROM (SELECT 1 FROM curated.intel_pad_geom
                     GROUP BY basin, pad_key HAVING COUNT(*) > 1) x),
                   (SELECT COUNT(*) FROM curated.intel_pad_geom
                     WHERE basin IS NULL OR pad_key IS NULL OR geom IS NULL)
                 + (SELECT COUNT(*) FROM curated.intel_pad_member WHERE pad_key IS NULL)
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

        # A split name = Novi reused a pad_name across separate stick groups
        # (sql/46 header). Report it; a new basin/vintage with many splits is a
        # finding to raise with Novi, not a build failure. Legacy Novi DSU median
        # was ~956 ac (Delaware 2025Q3) — sanity-check magnitude, don't pin.
        print("    per basin: names / split / pads / sticks / acres P10-P50-P90 / max", flush=True)
        for basin, names, split, pads, st, p10, p50, p90, mx in cur.execute("""
            SELECT basin, COUNT(DISTINCT pad_name),
                   COUNT(DISTINCT pad_name) FILTER (WHERE n_parts > 1),
                   COUNT(*), SUM(n_sticks),
                   percentile_cont(0.1) WITHIN GROUP (ORDER BY acres),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY acres),
                   percentile_cont(0.9) WITHIN GROUP (ORDER BY acres),
                   MAX(acres)
            FROM curated.intel_pad_geom GROUP BY 1 ORDER BY 1
        """).fetchall():
            print(f"      {basin:9} names={names:>6} split={split:>5} pads={pads:>6} sticks={st:>7}"
                  f"  acres {p10:,.0f} / {p50:,.0f} / {p90:,.0f} / {mx:,.0f}", flush=True)
        for basin, in cur.execute("""
            SELECT DISTINCT basin FROM curated.intel_locations
            EXCEPT SELECT DISTINCT basin FROM curated.intel_pad_geom ORDER BY 1
        """).fetchall():
            print(f"      {basin:9} NO PADS — Novi shipped no pad_name for this basin (erebor shows a notice)", flush=True)

        # EXPLAIN the erebor gunbarrel lookup — assert the PK index, no Seq Scan.
        basin, pad = cur.execute(
            "SELECT basin, pad_key FROM curated.intel_pad_geom ORDER BY n_sticks DESC LIMIT 1"
        ).fetchone()
        plan = "\n".join(r[0] for r in cur.execute(
            "EXPLAIN SELECT geom FROM curated.intel_pad_geom WHERE basin = %s AND pad_key = %s",
            (basin, pad),
        ).fetchall())
        hit = "idx_intel_pad_geom_pk" in plan
        print(f"    EXPLAIN pad lookup uses idx_intel_pad_geom_pk: {'YES' if hit else 'NO -- investigate'}", flush=True)
        if not hit:
            for line in plan.splitlines():
                print(f"      {line}", flush=True)
        ok &= hit

    print("    CONCURRENTLY refresh smoke test (member first — geom reads it):", flush=True)
    for rel in ("intel_pad_member", "intel_pad_geom"):
        t = time.monotonic()
        with conn.cursor() as cur:
            cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY curated.{rel}")
        print(f"      {rel} ok in {time.monotonic() - t:.1f}s", flush=True)
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
