"""Apply the deal-intake v2 warehouse objects + validate (Supabase oilgas).

Pattern of scripts/apply_intel_pad_geom.py: exec DDL on the 5432 session
(statement_timeout=0), then validate by identity, never by constant.

  1. sql/48 — CREATE OR REPLACE VIEW curated.wells_enriched, appending
     stack_closer_z_ft / stagger_closer_tangent_ft / parent_days_online.
     Trailing-column add => no CASCADE; asserts erebor_locations and
     intel_pdp_support still exist afterwards.
  2. sql/46 — curated.codev_context (DROP ... CASCADE + CREATE ... WITH DATA;
     ~1.5 min basin-wide, measured by read-only dry run 2026-09-18).
  3. sql/47 — curated.pdp_support_for_geom(geometry, text, float8).
  4. sql/31 — full comment catalog (idempotent; carries the new columns).
  5. validate:
     - wells_enriched: new columns present, row count == curated.wells,
       sentinel shares printed; dependents intact.
     - codev_context: rows == producing horizontals (identity), 0 dup/NULL
       api10, scorable == producing horizontals with a stick; EXPLAIN of the
       body shows idx_curated_wells_wellstick_geog; CONCURRENTLY smoke.
     - pdp_support_for_geom: EXPLAIN with a literal geometry is inlined and
       shows idx_curated_wells_wellstick_geog; parity vs intel_pdp_support on
       a sample of Novi sticks (live-vs-quarterly drift tolerated, see below).

codev_context is NIGHTLY (etl/db.py:_CURATED_MATVIEWS) — apply this BEFORE the
PR carrying that registration merges, or the next nightly refresh fails on a
missing matview.

!! DDL on the shared warehouse — explicit authorization required. From repo
root in the venv:
    python -m scripts.apply_codev_context
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"
GEOG_INDEX = "idx_curated_wells_wellstick_geog"

# Producing-horizontal identity — must match sql/46's subj CTE predicate.
_HZ_WHERE = """
    COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%horizontal%'
    AND w.first_production_date IS NOT NULL
"""

_NEW_WE_COLS = ("stack_closer_z_ft", "stagger_closer_tangent_ft", "parent_days_online")


def _exec(conn, label: str, fname: str) -> None:
    print(f"  exec {fname} — {label}", flush=True)
    t = time.monotonic()
    with conn.cursor() as cur:
        cur.execute((SQL / fname).read_text(encoding="utf-8"))
    print(f"    done in {time.monotonic() - t:.1f}s", flush=True)


def _relkind(cur, schema: str, name: str) -> str | None:
    row = cur.execute(
        "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = %s AND c.relname = %s",
        (schema, name),
    ).fetchone()
    return row[0] if row else None


def build(conn) -> None:
    print("[1/5] sql/48 — wells_enriched WellSpacing pass-through", flush=True)
    _exec(conn, "CREATE OR REPLACE VIEW (trailing columns only)", "48_wellspacing_passthrough.sql")
    print("[2/5] sql/46 — curated.codev_context", flush=True)
    _exec(conn, "DROP + CREATE MATERIALIZED VIEW WITH DATA", "46_codev_context.sql")
    print("[3/5] sql/47 — curated.pdp_support_for_geom", flush=True)
    _exec(conn, "CREATE OR REPLACE FUNCTION", "47_pdp_support_for_geom.sql")
    print("[4/5] sql/31 — comment catalog", flush=True)
    _exec(conn, "COMMENT ON (idempotent)", "31_comments.sql")


def validate_wells_enriched(cur) -> bool:
    ok = True
    cols = {
        r[0]
        for r in cur.execute(
            "SELECT attname FROM pg_attribute WHERE attrelid = 'curated.wells_enriched'::regclass "
            "AND attnum > 0 AND NOT attisdropped"
        ).fetchall()
    }
    missing = [c for c in _NEW_WE_COLS if c not in cols]
    print(f"    wells_enriched new columns missing: {missing or 'none'}", flush=True)
    ok &= not missing

    n_we, n_w = cur.execute(
        "SELECT (SELECT COUNT(*) FROM curated.wells_enriched), (SELECT COUNT(*) FROM curated.wells)"
    ).fetchone()
    tag = "OK" if n_we == n_w else "MISMATCH"
    print(f"    wells_enriched rows={n_we} curated.wells rows={n_w}  [{tag}]", flush=True)
    ok &= tag == "OK"

    n, z_cap, st_cap, pdo_neg, pdo_neg_not_child = cur.execute("""
        SELECT COUNT(*) FILTER (WHERE stack_closer_z_ft IS NOT NULL),
               COUNT(*) FILTER (WHERE stack_closer_z_ft = 1000),
               COUNT(*) FILTER (WHERE stagger_closer_tangent_ft = 2973.21),
               COUNT(*) FILTER (WHERE parent_days_online = -1),
               COUNT(*) FILTER (WHERE parent_days_online = -1 AND is_child IS NOT TRUE)
        FROM curated.wells_enriched
    """).fetchone()
    print(
        f"    WellSpacing rows={n}: StackCloserZ=1000 cap {z_cap} ({z_cap / max(n, 1):.0%}), "
        f"StaggerCloserTangent=2973.21 cap {st_cap} ({st_cap / max(n, 1):.0%}), "
        f"ParentDaysOnline=-1 {pdo_neg} (of which not-child {pdo_neg_not_child})",
        flush=True,
    )
    if pdo_neg != pdo_neg_not_child:
        print("    WARN: ParentDaysOnline=-1 on child wells — sentinel semantics drifted; "
              "update sql/31 comment", flush=True)

    for schema, name in (("curated", "erebor_locations"), ("curated", "intel_pdp_support")):
        kind = _relkind(cur, schema, name)
        print(f"    dependent {schema}.{name} relkind={kind!r} (expect 'm' — no CASCADE)", flush=True)
        ok &= kind == "m"
    return ok


def validate_codev(cur) -> bool:
    ok = True
    kind = _relkind(cur, "curated", "codev_context")
    print(f"    codev_context relkind={kind!r} (expect 'm')", flush=True)
    ok &= kind == "m"

    n, scorable = cur.execute(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE scorable) FROM curated.codev_context"
    ).fetchone()
    exp_n, exp_scorable = cur.execute(f"""
        SELECT COUNT(*), COUNT(*) FILTER (WHERE w.wellstick_geom IS NOT NULL)
        FROM curated.wells w WHERE {_HZ_WHERE}
    """).fetchone()
    tag = "OK" if (n, scorable) == (exp_n, exp_scorable) else "MISMATCH"
    print(f"    rows={n} expected={exp_n}  scorable={scorable} expected={exp_scorable}  [{tag}]", flush=True)
    ok &= tag == "OK"

    dups, nulls = cur.execute("""
        SELECT (SELECT COUNT(*) FROM (SELECT 1 FROM curated.codev_context
                 GROUP BY api10 HAVING COUNT(*) > 1) x),
               (SELECT COUNT(*) FROM curated.codev_context WHERE api10 IS NULL)
    """).fetchone()
    print(f"    api10 duplicates={dups} NULL api10={nulls} (both must be 0)", flush=True)
    ok &= dups == 0 and nulls == 0

    p10, p50, p90, zero, codev_o, parent_o, child_o, standalone = cur.execute("""
        SELECT percentile_cont(0.1) WITHIN GROUP (ORDER BY n_neighbors),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY n_neighbors),
               percentile_cont(0.9) WITHIN GROUP (ORDER BY n_neighbors),
               COUNT(*) FILTER (WHERE n_neighbors = 0),
               COUNT(*) FILTER (WHERE n_codev_other_bench > 0),
               COUNT(*) FILTER (WHERE n_parent_other_bench > 0),
               COUNT(*) FILTER (WHERE n_child_other_bench > 0),
               COUNT(*) FILTER (WHERE n_codev_other_bench = 0 AND n_parent_other_bench = 0
                                  AND n_child_other_bench = 0)
        FROM curated.codev_context WHERE scorable
    """).fetchone()
    print(
        f"    neighbors P10/P50/P90 {p10:.0f}/{p50:.0f}/{p90:.0f}; none={zero}; other-bench "
        f"codev={codev_o} parent={parent_o} child={child_o}; no other-bench neighbor={standalone}",
        flush=True,
    )

    # EXPLAIN the matview body (from the file) — the build must be index-served.
    body = re.search(
        r"CREATE MATERIALIZED VIEW curated\.codev_context AS\n(.*?)\nWITH DATA;",
        (SQL / "46_codev_context.sql").read_text(encoding="utf-8"),
        re.DOTALL,
    ).group(1)
    plan = "\n".join(r[0] for r in cur.execute("EXPLAIN " + body).fetchall())
    hit = GEOG_INDEX in plan
    print(f"    EXPLAIN body uses {GEOG_INDEX}: {'YES' if hit else 'NO -- investigate'}", flush=True)
    ok &= hit

    print("    spot check — WCB_1 wells co-developed with WCA_2 (newest 5):", flush=True)
    for api10, fp, benches, ctx in cur.execute("""
        SELECT api10, first_production_date, codev_benches, bench_context -> 'WCA_2'
        FROM curated.codev_context
        WHERE bench = 'WCB_1' AND codev_benches @> ARRAY['WCA_2']
        ORDER BY first_production_date DESC LIMIT 5
    """).fetchall():
        print(f"      {api10} fp={fp} codev={benches} WCA_2={ctx}", flush=True)
    return ok


def validate_function(cur) -> bool:
    ok = True
    wkt, code, tvd = cur.execute("""
        SELECT extensions.ST_AsEWKT(il.wellstick_geom), fb.formation_blueox, il.tvd::float8
        FROM curated.intel_locations il JOIN curated.intel_formation_blueox fb USING (stick_id)
        WHERE il.category = 'PUD' AND fb.formation_blueox IS NOT NULL
          AND il.tvd IS NOT NULL AND il.wellstick_geom IS NOT NULL
        ORDER BY il.stick_id LIMIT 1
    """).fetchone()
    plan = "\n".join(r[0] for r in cur.execute(
        "EXPLAIN SELECT * FROM curated.pdp_support_for_geom(%s::geometry, %s, %s)", (wkt, code, tvd)
    ).fetchall())
    inlined, hit = "Function Scan" not in plan, GEOG_INDEX in plan
    print(f"    EXPLAIN literal-geom call: inlined={inlined} uses {GEOG_INDEX}={hit}", flush=True)
    ok &= inlined and hit

    null_row = cur.execute(
        "SELECT * FROM curated.pdp_support_for_geom(NULL, 'WCA_1', 9500)"
    ).fetchone()
    print(f"    NULL geometry -> all-NULL scores: {all(v is None for v in null_row)}", flush=True)
    ok &= all(v is None for v in null_row)

    # Parity vs the quarterly matview. Exact equality is NOT expected: the
    # function is live (new producers cross the 6-month gate daily; Novi EURs
    # move nightly). Gate on pdp_count_5mi within max(1, 5%) on >= 90%.
    rows = cur.execute("""
        WITH s AS (
            SELECT il.stick_id, il.wellstick_geom, fb.formation_blueox AS code, il.tvd::float8 AS tvd
            FROM curated.intel_locations il JOIN curated.intel_formation_blueox fb USING (stick_id)
            WHERE il.category IN ('PUD', 'RES') AND fb.formation_blueox IS NOT NULL
              AND il.tvd IS NOT NULL AND il.wellstick_geom IS NOT NULL
              AND abs(hashtext(il.stick_id::text)) % 2000 = 0
            LIMIT 60)
        SELECT f.pdp_count_5mi, p.pdp_count_5mi, f.pdp_count_3mi, p.pdp_count_3mi
        FROM s CROSS JOIN LATERAL curated.pdp_support_for_geom(s.wellstick_geom, s.code, s.tvd) f
        JOIN curated.intel_pdp_support p USING (stick_id)
    """).fetchall()
    close = sum(abs(f5 - p5) <= max(1, 0.05 * p5) for f5, p5, _, _ in rows)
    exact3 = sum(f3 == p3 for _, _, f3, p3 in rows)
    frac = close / max(len(rows), 1)
    print(
        f"    parity vs intel_pdp_support on {len(rows)} sticks: pdp_count_5mi within tol "
        f"{close} ({frac:.0%}, need >= 90%); pdp_count_3mi exact {exact3}",
        flush=True,
    )
    ok &= frac >= 0.90
    return ok


def main() -> None:
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        build(conn)
        print("[5/5] validation", flush=True)
        with conn.cursor() as cur:
            ok = validate_wells_enriched(cur)
            ok &= validate_codev(cur)
            ok &= validate_function(cur)
        print("    CONCURRENTLY refresh smoke test (codev_context):", flush=True)
        t = time.monotonic()
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.codev_context")
        print(f"      ok in {time.monotonic() - t:.1f}s", flush=True)
    finally:
        conn.close()
    print(f"=== {'DONE' if ok else 'DONE WITH FAILURES'} in {time.monotonic() - t0:.0f}s ===", flush=True)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
