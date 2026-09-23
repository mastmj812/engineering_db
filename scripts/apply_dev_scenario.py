"""Apply sql/47 (codev_context + parent-only bench_context keys) + sql/50
curated.dev_scenario + sql/31, then validate (Supabase oilgas).

Pattern of scripts/apply_codev_context.py (whose validate_codev is reused):
exec DDL on the 5432 session (statement_timeout=0), validate by identity.

  0. preflight — the only object depending on codev_context may be
     dev_scenario (sql/47's DROP ... CASCADE must not take anything else);
     snapshot the live bench_context into a session TEMP table.
  1. sql/47 — DROP ... CASCADE + CREATE ... WITH DATA (~90 s basin-wide,
     read-only dry run 2026-09-23). deal-intake reads codev_context: it is
     absent for the build window.
  2. sql/50 — DROP VIEW IF EXISTS + CREATE VIEW curated.dev_scenario.
  3. sql/31 — comment catalog (column comments die with the drop).
  4. validate:
     - codev_context identity/dups/EXPLAIN (apply_codev_context.validate_codev)
     - BACKWARD COMPAT: every pre-existing bench_context key is identical to
       the snapshot (only the four parent-only keys are new); deal-intake's
       reads are unchanged.
     - parent-only keys present exactly where n_parent > 0
     - dev_scenario rows == codev_context rows; class NULL <=> not scorable
     - class distribution + spot check (Pad C 233 area, one well per class)
     - CONCURRENTLY refresh smoke (dev_scenario survives it — plain view)

!! DDL on the shared warehouse — explicit authorization required. Outside the
nightly window (cron 11:15 UTC). From repo root in the venv:
    python -m scripts.apply_dev_scenario
"""

from __future__ import annotations

import time

from etl.db import get_connection
from scripts.apply_codev_context import _exec, _relkind, validate_codev

NEW_KEYS = ("parent_min_offset_ft", "parent_nearest_dtvd_ft",
            "parent_min_age_days", "parent_max_age_days")
PAD_C233 = (-101.816, 31.304)   # lon, lat — Developed Pad C 233 centroid (Upton)


def preflight(cur) -> None:
    deps = [r[0] for r in cur.execute("""
        SELECT DISTINCT n.nspname || '.' || dc.relname
        FROM pg_depend d
        JOIN pg_rewrite r   ON r.oid = d.objid
        JOIN pg_class dc    ON dc.oid = r.ev_class
        JOIN pg_namespace n ON n.oid = dc.relnamespace
        WHERE d.refobjid = 'curated.codev_context'::regclass
          AND dc.oid <> 'curated.codev_context'::regclass
    """).fetchall()]
    print(f"    dependents of codev_context: {deps or 'none'}", flush=True)
    extra = [d for d in deps if d != "curated.dev_scenario"]
    if extra:
        raise SystemExit(f"ABORT: sql/47 CASCADE would also drop {extra} — map them first")
    cur.execute("""
        CREATE TEMP TABLE _cc_before AS
        SELECT api10, bench_context FROM curated.codev_context
    """)
    n = cur.execute("SELECT COUNT(*) FROM _cc_before").fetchone()[0]
    print(f"    snapshot of live bench_context: {n} rows", flush=True)


def validate_compat(cur) -> bool:
    drift = cur.execute(f"""
        WITH a AS (
            SELECT b.api10, e.key AS bench, e.value AS v
            FROM _cc_before b CROSS JOIN LATERAL jsonb_each(b.bench_context) e),
        n AS (
            SELECT c.api10, e.key AS bench,
                   e.value - ARRAY[{", ".join(f"'{k}'" for k in NEW_KEYS)}] AS v
            FROM curated.codev_context c CROSS JOIN LATERAL jsonb_each(c.bench_context) e)
        SELECT COUNT(*) FILTER (WHERE a.api10 IS NULL),
               COUNT(*) FILTER (WHERE n.api10 IS NULL),
               COUNT(*) FILTER (WHERE a.v IS DISTINCT FROM n.v)
        FROM a FULL JOIN n USING (api10, bench)
    """).fetchone()
    new_only, gone, changed = drift
    # Rows can move only if the nightly base tables moved mid-apply.
    ok = drift == (0, 0, 0)
    print(f"    backward compat (old keys vs snapshot): new bench rows={new_only} "
          f"missing={gone} changed={changed}  [{'OK' if ok else 'DRIFT'}]", flush=True)

    bad_present, bad_missing = cur.execute("""
        SELECT COUNT(*) FILTER (WHERE (e.value->>'n_parent')::int = 0
                                  AND e.value->'parent_min_offset_ft' <> 'null'::jsonb),
               COUNT(*) FILTER (WHERE (e.value->>'n_parent')::int > 0
                                  AND (e.value->'parent_min_offset_ft' = 'null'::jsonb
                                       OR NOT e.value ? 'parent_min_age_days'))
        FROM curated.codev_context c CROSS JOIN LATERAL jsonb_each(c.bench_context) e
    """).fetchone()
    print(f"    parent keys: set without parents={bad_present}, "
          f"missing with parents={bad_missing} (both must be 0)", flush=True)
    return ok and bad_present == 0 and bad_missing == 0


def validate_view(cur) -> bool:
    ok = True
    kind = _relkind(cur, "curated", "dev_scenario")
    print(f"    dev_scenario relkind={kind!r} (expect 'v')", flush=True)
    ok &= kind == "v"

    t = time.monotonic()
    n_v, n_c, null_scorable, class_unscorable = cur.execute("""
        SELECT (SELECT COUNT(*) FROM curated.dev_scenario),
               (SELECT COUNT(*) FROM curated.codev_context),
               (SELECT COUNT(*) FROM curated.dev_scenario WHERE scorable AND scenario_class IS NULL),
               (SELECT COUNT(*) FROM curated.dev_scenario WHERE NOT scorable AND scenario_class IS NOT NULL)
    """).fetchone()
    tag = "OK" if n_v == n_c and null_scorable == 0 and class_unscorable == 0 else "MISMATCH"
    print(f"    rows={n_v} codev_context={n_c}; NULL class on scorable={null_scorable}, "
          f"class on unscorable={class_unscorable}  [{tag}]  ({time.monotonic() - t:.1f}s)", flush=True)
    ok &= tag == "OK"

    print("    class x basin (wells_enriched.basin_blueox):", flush=True)
    for basin, cls, n, cens in cur.execute("""
        SELECT we.basin_blueox, d.scenario_class, COUNT(*), COUNT(*) FILTER (WHERE d.child_censored)
        FROM curated.dev_scenario d JOIN curated.wells_enriched we USING (api10)
        GROUP BY 1, 2 ORDER BY 1, 2
    """).fetchall():
        print(f"      {basin or '-':10s} {cls or '(not scorable)':13s} {n:6d}  child_censored={cens}", flush=True)

    print("    spot check — WCA_1 / WCC within 3 mi of Pad C 233, newest well per class:", flush=True)
    for row in cur.execute("""
        SELECT DISTINCT ON (d.bench, d.scenario_class)
               d.api10, we.well_name, d.bench, d.first_production_date, d.scenario_class,
               d.parent_benches_below, d.parent_benches_above,
               d.nearest_parent_below_dtvd_ft, d.nearest_parent_above_dtvd_ft,
               d.nearest_parent_offset_ft, d.youngest_parent_age_days, d.codev_benches_other
        FROM curated.dev_scenario d
        JOIN curated.wells w USING (api10)
        JOIN curated.wells_enriched we USING (api10)
        WHERE d.bench IN ('WCA_1', 'WCC')
          AND extensions.ST_DWithin(w.wellstick_geom::extensions.geography,
                extensions.ST_SetSRID(extensions.ST_Point(%s, %s), 4326)::extensions.geography, 4828)
        ORDER BY d.bench, d.scenario_class, d.first_production_date DESC
    """, PAD_C233).fetchall():
        (api10, name, bench, fp, cls, below, above, dzb, dza, off, age, codev) = row
        print(f"      {api10} {name!s:28.28s} {bench:6s} fp={fp} {cls:11s} below={below} "
              f"above={above} dz={dzb}/{dza} off={off} youngest_parent={age}d codev={codev}",
              flush=True)
    return ok


def main() -> None:
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("[0/4] preflight", flush=True)
            preflight(cur)
        print("[1/4] sql/47 — curated.codev_context (+ parent-only keys)", flush=True)
        _exec(conn, "DROP + CREATE MATERIALIZED VIEW WITH DATA", "47_codev_context.sql")
        print("[2/4] sql/50 — curated.dev_scenario", flush=True)
        _exec(conn, "DROP + CREATE VIEW", "50_dev_scenario.sql")
        print("[3/4] sql/31 — comment catalog", flush=True)
        _exec(conn, "COMMENT ON (idempotent)", "31_comments.sql")
        print("[4/4] validation", flush=True)
        with conn.cursor() as cur:
            ok = validate_codev(cur)
            ok &= validate_compat(cur)
            ok &= validate_view(cur)
            print("    CONCURRENTLY refresh smoke test (codev_context):", flush=True)
            t = time.monotonic()
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.codev_context")
            survived = _relkind(cur, "curated", "dev_scenario") == "v"
            print(f"      ok in {time.monotonic() - t:.1f}s; dev_scenario survives: {survived}", flush=True)
            ok &= survived
    finally:
        conn.close()
    print(f"=== {'DONE' if ok else 'DONE WITH FAILURES'} in {time.monotonic() - t0:.0f}s ===", flush=True)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
