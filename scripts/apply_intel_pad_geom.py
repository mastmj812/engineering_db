"""Build curated.intel_pad_member + curated.intel_pad_geom (sql/67 v3) + validate.

Exec the DDL on the 5432 session (statement_timeout=0), then validate by identity.

  --load-pads (once per Novi pad drop; DB WRITE to raw_novi_intel):
     a. refuse unless etl.novi_intel.paths.PADS_REPORT_VERSION equals
        curated.intel_locations.report_version in every basin (sql/67 joins on it);
     b. exec sql/66 (additive raw_novi_intel.pads columns + name index);
     c. load every pad polygon per basin (load_shapefiles.load_pads) and assert
        loaded rows == shapefile records, 0 NULL names/geoms, 0 duplicate names.
  1. exec sql/67 — DROP ... CASCADE both + CREATE MATERIALIZED VIEW ... WITH DATA
     (member: UNIQUE stick_id; geom: UNIQUE (basin, pad_key) + GiST) + COMMENTs.
     Small (~256k member rows, ~17.5k pads; the read-only dry run took ~11 s).
  2. validate by identity, not constants: member rows == padded sticks with
     geometry in intel_locations; geom rows == distinct (basin, pad_key) in
     member and SUM(n_sticks) == member rows; 0 dup/NULL keys; all geoms valid
     (MULTI)POLYGONs; member_rule + geom_source mix and acreage per basin;
     EXPLAIN index assertion (idx_intel_pad_geom_pk on the erebor gunbarrel
     lookup); CONCURRENTLY smoke on both, member first.

STEP in the quarterly Novi reload — anywhere after `load_intel_sf --curated`
(depends on curated.intel_locations, which DROP-CASCADEs both). Without a pad
load for the new vintage every name falls back to sql/46 hulls
(member_rule = no_polygon_cluster); load that vintage's pads with --load-pads.

⚠ DDL on the shared warehouse. Run from repo root in the venv:
    python -m scripts.apply_intel_pad_geom               # rebuild + validate
    python -m scripts.apply_intel_pad_geom --load-pads   # load Novi pads, then rebuild
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from etl.db import get_connection
from etl.novi_intel import load_shapefiles, paths

SQL = Path(__file__).resolve().parent.parent / "sql"


def load_pads(conn) -> bool:
    print(f"[0/2] load Novi DSU pad polygons at report_version {paths.PADS_REPORT_VERSION!r}", flush=True)
    with conn.cursor() as cur:
        live = dict(cur.execute(
            "SELECT basin, MIN(report_version) FROM curated.intel_locations GROUP BY basin"
        ).fetchall())
    stale = {b: v for b, v in live.items() if v != paths.PADS_REPORT_VERSION}
    if stale:
        print(f"    REFUSED: intel_locations vintage {stale} != pads {paths.PADS_REPORT_VERSION!r}."
              " Point PADS_BASIN_DIRS / PADS_REPORT_VERSION at this vintage's drop.", flush=True)
        return False
    with conn.cursor() as cur:
        cur.execute((SQL / "66_novi_pad_polygons_2026q3.sql").read_text(encoding="utf-8"))
    ok = True
    for basin in sorted(live):
        expected = load_shapefiles.pad_record_count(basin)
        loaded = load_shapefiles.load_pads(basin)
        with conn.cursor() as cur:
            rows, null_rows, dup_names = cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE pad_name IS NULL OR pad_name = '' OR geom IS NULL),
                       COUNT(*) - COUNT(DISTINCT pad_name)
                FROM raw_novi_intel.pads WHERE basin = %s AND report_version = %s
            """, (basin, paths.PADS_REPORT_VERSION)).fetchone()
        good = bool(expected) and loaded == expected == rows and null_rows == 0 and dup_names == 0
        print(f"    {basin:9} shapefile={expected} loaded={loaded} in table={rows}"
              f" null name/geom={null_rows} dup names={dup_names}  [{'OK' if good else 'MISMATCH'}]",
              flush=True)
        ok &= good
    return ok


def build(conn) -> None:
    print("[1/2] exec sql/67 — build curated.intel_pad_member + intel_pad_geom", flush=True)
    t = time.monotonic()
    with conn.cursor() as cur:
        cur.execute((SQL / "67_intel_pad_geom_v3.sql").read_text(encoding="utf-8"))
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
        print(f"    geometry types={types} invalid={invalid} (expect POLYGON/MULTIPOLYGON, 0)", flush=True)
        ok &= set(types) <= {"POLYGON", "MULTIPOLYGON"} and invalid == 0

        # Which rule placed each stick (sql/67 header). Strays and no-polygon
        # names are expected to be off-scope benches (2026Q3: Delaware WDFD
        # name reuse, Midland BRNT names without a polygon) — report, don't pin.
        print("    member_rule per basin (sticks):", flush=True)
        for basin, rule, n in cur.execute("""
            SELECT basin, member_rule, COUNT(*) FROM curated.intel_pad_member
            GROUP BY 1, 2 ORDER BY 1, 2
        """).fetchall():
            print(f"      {basin:9} {rule:20} {n:>8}", flush=True)

        # A split name = Novi reused a pad_name across separate stick groups
        # (sql/67 header). Report it; a new basin/vintage with many splits is a
        # finding to raise with Novi, not a build failure. Legacy Novi DSU median
        # was ~956 ac (Delaware 2025Q3) — sanity-check magnitude, don't pin.
        print("    per basin/geom_source: names / split / pads / sticks / acres P10-P50-P90 / max", flush=True)
        for basin, src, names, split, pads, st, p10, p50, p90, mx in cur.execute("""
            SELECT basin, geom_source, COUNT(DISTINCT pad_name),
                   COUNT(DISTINCT pad_name) FILTER (WHERE n_parts > 1),
                   COUNT(*), SUM(n_sticks),
                   percentile_cont(0.1) WITHIN GROUP (ORDER BY acres),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY acres),
                   percentile_cont(0.9) WITHIN GROUP (ORDER BY acres),
                   MAX(acres)
            FROM curated.intel_pad_geom GROUP BY 1, 2 ORDER BY 1, 2
        """).fetchall():
            print(f"      {basin:9} {src:16} names={names:>6} split={split:>5} pads={pads:>6} sticks={st:>7}"
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
    ap = argparse.ArgumentParser(description="Build curated.intel_pad_member + intel_pad_geom (sql/67).")
    ap.add_argument("--load-pads", action="store_true",
                    help="exec sql/66 and load the Novi pad drop into raw_novi_intel.pads first")
    args = ap.parse_args()
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        if args.load_pads and not load_pads(conn):
            print("=== STOPPED: pad load failed its checks; intel_pad_* left untouched ===", flush=True)
            raise SystemExit(1)
        build(conn)
        ok = validate(conn)
    finally:
        conn.close()
    print(f"=== {'DONE' if ok else 'DONE WITH FAILURES'} in {time.monotonic() - t0:.0f}s ===", flush=True)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
