"""BOX sticks phase 8, step 3: drop the three retired Novi-stick matviews on live and move the
reconciliation to the Novi vintage date PER BASIN (sql/80, sql/68). docs/box_sticks_plan.md.

    python -m scripts.apply_retire_novi_sticks          # dry run: preflight + the plan, read-only
    python -m scripts.apply_retire_novi_sticks --go     # apply (Michael's explicit go only)

--go, in order:
  1. preflight (also in the dry run): nothing depends on the three matviews but each other; no ETL run in progress;
     snapshot of what must not move.
  2. apply_reconciled_inventory: sql/80 (DROP x3 without CASCADE, the per-basin vintage function) then sql/68.
     sql/68's DROP ... CASCADE takes curated.intel_forecast_accuracy; erebor's Accuracy tab is dark until step 3.
  3. apply_intel_forecast_accuracy (sql/38 + sql/43).
  4. apply_erebor_locations --after-reload (sql/31 comments; refuses if the location relation is gone), then sql/26.
  5. verify: the three are gone; the relations the apps serve are the SAME objects with the same rows; the
     reconciliation equals what the previous definition gives on today's data (the per-basin date changes no stick
     while production ends before the older vintage date); the accuracy matviews stand.

Not touched: curated.erebor_locations, the land team's view, wells_enriched, the dev-scenario views, box.*.
Run outside the nightly (05:00 CT dispatch; check `gh run list --workflow etl-nightly.yml` for a late backstop).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from etl.db import get_connection

PY = sys.executable
ROOT = Path(__file__).resolve().parent.parent
RETIRED = ("curated.novi_stick_locations", "curated.intel_pdp_support", "curated.net_new_pdp")
# what the apps and the land team read: must be the same objects, same rows, before and after
PROTECTED = ("curated.erebor_locations", "curated.box_scout_locations", "curated.wells_enriched", "curated.codev_context",
             "curated.dev_scenario", "curated.producing_reference", "curated.formation_blueox_tvd", "curated.formation_blueox",
             "curated.intel_locations", "curated.intel_formation_blueox", "curated.box_location_status")
REBUILT = ("curated.reconciled_inventory", "curated.intel_forecast_accuracy", "curated.intel_forecast_accuracy_vintage")
STEPS: list[list[str]] = [
    [PY, "-m", "scripts.apply_reconciled_inventory"],
    [PY, "-m", "scripts.apply_intel_forecast_accuracy"],
    [PY, "-m", "scripts.apply_erebor_locations", "--after-reload"],
    [PY, "-c", "from scripts.load_intel_sf import run_sql_file; run_sql_file('26_geography_indexes.sql')"],
]

# every dependency on a retired matview that is not one of its own indexes / its own rule
_DEPENDENTS_SQL = """
SELECT DISTINCT d.refobjid::regclass::text, COALESCE(rw.ev_class::regclass::text, d.classid::regclass::text || ':' || d.objid)
FROM pg_depend d LEFT JOIN pg_rewrite rw ON d.classid = 'pg_rewrite'::regclass AND rw.oid = d.objid
WHERE d.refobjid = ANY (%(oids)s) AND d.deptype = 'n' AND COALESCE(rw.ev_class, 0) <> d.refobjid
"""
_RECON_SQL = "SELECT basin_blueox, category, status, count(*) FROM curated.reconciled_inventory GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"


def dependents_problems(rows: list[tuple[str, str]], retired: tuple[str, ...] = RETIRED) -> list[str]:
    """A dependent that is not itself retired would be an object nobody knew of: refuse."""
    return [f"{dep} depends on {src}" for src, dep in sorted(rows) if dep not in retired]


def snapshot(cur) -> dict:
    q = cur.execute
    snap: dict = {"standing": [r for r in RETIRED if q("SELECT to_regclass(%s)", (r,)).fetchone()[0] is not None]}
    snap["protected"] = {r: (q("SELECT %s::regclass::oid", (r,)).fetchone()[0], q(f"SELECT count(*) FROM {r}").fetchone()[0])
                         for r in PROTECTED}
    snap["recon"] = q(_RECON_SQL).fetchall()
    snap["rebuilt"] = {r: q(f"SELECT count(*) FROM {r}").fetchone()[0] for r in REBUILT}
    return snap


def preflight(cur) -> tuple[dict, list[str]]:
    q = cur.execute
    snap = snapshot(cur)
    problems: list[str] = []
    oids = [q("SELECT %s::regclass::oid", (r,)).fetchone()[0] for r in snap["standing"]]
    if oids:
        problems += dependents_problems(q(_DEPENDENTS_SQL, {"oids": oids}).fetchall())
    running = q("SELECT source, table_name, run_started_at FROM meta.etl_log "
                "WHERE status = 'running' AND run_started_at > now() - interval '6 hours'").fetchall()
    problems += [f"ETL run in progress: {s}/{t} since {ts:%H:%M} UTC" for s, t, ts in running]
    print(f"    retired matviews standing: {snap['standing'] or 'none (already dropped)'}", flush=True)
    for r in snap["standing"]:
        size, n = q("SELECT pg_size_pretty(pg_total_relation_size(%s::regclass)), (SELECT reltuples::bigint FROM pg_class WHERE oid = %s::regclass)",
                    (r, r)).fetchone()
        print(f"      {r}: {size}, ~{n:,} rows", flush=True)
    print(f"    Novi vintage by basin now: {q('SELECT basin, max(report_version) FROM curated.intel_locations GROUP BY 1 ORDER BY 1').fetchall()}; "
          f"one-date function: {q('SELECT curated.intel_vintage_date()').fetchone()[0]}", flush=True)
    print(f"    reconciliation rows {sum(r[3] for r in snap['recon']):,}; accuracy rows {snap['rebuilt']}", flush=True)
    for p in problems:
        print(f"    FAIL: {p}", flush=True)
    return snap, problems


def verify(cur, before: dict) -> list[str]:
    q = cur.execute
    bad: list[str] = []

    def ck(ok: bool, msg: str) -> None:
        print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
        if not ok:
            bad.append(msg)

    gone = [r for r in RETIRED if q("SELECT to_regclass(%s)", (r,)).fetchone()[0] is None]
    ck(len(gone) == len(RETIRED), f"the three retired matviews are gone ({len(gone)} of {len(RETIRED)})")
    after = snapshot(cur)
    moved = {r: (before["protected"][r], after["protected"][r]) for r in PROTECTED if before["protected"][r] != after["protected"][r]}
    ck(not moved, f"{len(PROTECTED)} relations the apps read are the same objects with the same rows ({moved or 'none moved'})")
    vint = q("SELECT basin, report_version, vintage_date FROM curated.intel_vintage_date_by_basin() ORDER BY 1").fetchall()
    ck(len(vint) == 2, f"vintage date per basin: {[(b, v, str(d)) for b, v, d in vint]}")
    uses = q("SELECT pg_get_viewdef('curated.reconciled_inventory'::regclass) LIKE '%intel_vintage_date_by_basin%'").fetchone()[0]
    ck(bool(uses), "curated.reconciled_inventory reads the per-basin vintage function")
    n_b, n_a = sum(r[3] for r in before["recon"]), sum(r[3] for r in after["recon"])
    ck(n_a == n_b, f"reconciliation rows unchanged ({n_a:,} = {n_b:,})")
    mapped = q("SELECT count(*) FROM curated.intel_locations il JOIN curated.intel_formation_blueox fb USING (stick_id) "
               "WHERE il.category IN ('PUD', 'RES') AND il.wellstick_geom IS NOT NULL AND fb.formation_blueox IS NOT NULL").fetchone()[0]
    ck(n_a == mapped, f"... and = the mapped Novi stick universe ({mapped:,})")
    diff = sorted(set(after["recon"]) ^ set(before["recon"]))
    print(f"    status x basin x category cells that moved (the matview was last built at the 2026-11-25 reload; "
          f"wells loaded since move sticks): {diff or 'none'}", flush=True)
    for r in REBUILT:
        ck(q("SELECT relispopulated FROM pg_class WHERE oid = %s::regclass", (r,)).fetchone()[0], f"{r} stands and is populated "
           f"({after['rebuilt'][r]:,} rows; before {before['rebuilt'][r]:,})")
    dup = q("SELECT count(*) - count(DISTINCT stick_id) FROM curated.reconciled_inventory").fetchone()[0]
    ck(dup == 0, f"curated.reconciled_inventory stick_id unique ({dup} duplicates)")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--go", action="store_true", help="apply on the connected database (Michael's explicit go only)")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    print("[1/5] preflight", flush=True)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        before, problems = preflight(cur)
        conn.rollback()
    if problems:
        print("preflight failed - nothing written", flush=True)
        return 1
    if not a.go:
        print("=== DRY RUN - nothing written. Plan:", flush=True)
        for cmd in STEPS:
            print("      " + " ".join(cmd[1:]), flush=True)
        print("    apply_reconciled_inventory runs sql/80 (DROP x3 without CASCADE + the per-basin vintage function) before sql/68 ===", flush=True)
        return 0
    for i, cmd in enumerate(STEPS, 2):
        print(f"[{min(i, 4)}/5] {' '.join(cmd[1:])}", flush=True)
        subprocess.run(cmd, cwd=ROOT, check=True)
    print("[5/5] verify", flush=True)
    with get_connection() as conn, conn.cursor() as cur:
        bad = verify(cur, before)
        conn.rollback()
    print(f"=== {'DONE' if not bad else 'FAILED: ' + '; '.join(bad)} in {time.monotonic() - t0:.0f} s ===", flush=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
