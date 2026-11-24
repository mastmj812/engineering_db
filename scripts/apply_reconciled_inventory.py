"""Build curated.reconciled_inventory (Supabase), the Novi-stick reconciliation of the quarterly reload.

  1. producing_reference (sql/20) and formation_blueox_tvd (sql/23): CHECKED, not rebuilt. Neither reads Novi
     Intelligence and the nightly refreshes both, so a Novi reload has no reason to rebuild them. Rebuilding sql/20 is a
     DROP ... CASCADE that takes formation_blueox_tvd, wells_enriched, codev_context, dev_scenario, erebor_locations and
     the land team's view with it: the apps go dark for a comparison-data reload (docs/box_sticks_plan.md phase 7, item 2).
  2. reconciled_inventory (sql/68; supersedes sql/21) — overlap-based reconciliation of
     EVERY Novi stick, PUD and RES (D117) (heavy).
  3. Validate: status distribution + realized count vs the new-well anchor.

Run from repo root in the venv:
    python -m scripts.apply_reconciled_inventory
    python -m scripts.apply_reconciled_inventory --rebuild-reference    # a reprovision, or sql/20 itself changed: rebuilds
                                                                        # sql/20 -> 23 -> wells_enriched -> 47 -> 50 first.
                                                                        # That drops curated.erebor_locations: finish with
                                                                        # python -m scripts.apply_erebor_locations
"""

from __future__ import annotations

import argparse
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


REFERENCE = ("producing_reference", "formation_blueox_tvd", "wells_enriched", "codev_context", "dev_scenario")
_REFERENCE_SQL = """
SELECT c.relname, c.relkind, CASE WHEN c.relkind = 'm' THEN c.relispopulated ELSE TRUE END
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'curated' AND c.relname = ANY (%s)
"""


def reference_problems(rows: list[tuple[str, str, bool]]) -> list[str]:
    """What is wrong with the producer objects sql/68 builds on: [] = all five exist and the matviews hold data."""
    have = {name: (kind, ok) for name, kind, ok in rows}
    return [f"curated.{r} is missing" if r not in have else f"curated.{r} is not populated" for r in REFERENCE if r not in have or not have[r][1]]


def check_reference() -> None:
    """The default path: the producer objects stand (the nightly keeps them), so nothing is dropped."""
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            bad = reference_problems(cur.execute(_REFERENCE_SQL, (list(REFERENCE),)).fetchall())
            if bad:
                raise SystemExit("; ".join(bad) + ". Run with --rebuild-reference (it drops curated.erebor_locations: finish "
                                 "with python -m scripts.apply_erebor_locations).")
            n, newest = cur.execute("SELECT count(*), max(first_production_date) FROM curated.producing_reference").fetchone()
        print(f"    {n} producing reference wells, newest first production {newest}; kept as the nightly left them", flush=True)
    finally:
        conn.close()


def rebuild_reference() -> None:
    """--rebuild-reference: sql/20 from scratch and everything its CASCADE takes that sql/68 or the nightly needs."""
    print("[1/3] build curated.producing_reference", flush=True)
    _exec("producing_reference", "20_producing_reference.sql")
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            n = cur.execute("SELECT COUNT(*) FROM curated.producing_reference").fetchone()[0]
        print(f"    {n} producing reference wells", flush=True)
    finally:
        conn.close()

    # sql/20's DROP ... CASCADE takes curated.formation_blueox_tvd (sql/23,
    # depends on producing_reference) and curated.wells_enriched (sql/06 view,
    # joins formation_blueox_tvd) down with it — and sql/68 below NEEDS
    # formation_blueox_tvd. Rebuild both before the reconciliation pass.
    print("[1b/3] rebuild formation_blueox_tvd (sql/23; cascade victim of sql/20)", flush=True)
    _exec("formation_blueox_tvd", "23_formation_blueox_tvd.sql")

    print("[1c/3] recreate curated.wells_enriched (sql/06 view block)", flush=True)
    import re
    sql06 = (SQL / "06_curated_derived.sql").read_text(encoding="utf-8")
    m = re.search(
        r"(DROP VIEW IF EXISTS curated\.wells_enriched CASCADE;.*?"
        r"COMMENT ON VIEW curated\.wells_enriched IS\s*'[^']*';)",
        sql06, re.DOTALL,
    )
    if not m:
        raise RuntimeError("wells_enriched block not found in sql/06")
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(m.group(1))
        conn.commit()
    finally:
        conn.close()

    # curated.codev_context (sql/47, nightly) reads formation_blueox_tvd, so
    # sql/20's CASCADE drops it too. Rebuild here (~1.5 min, needs the sql/26
    # wells geography index, which sql/20 does not touch) so the next nightly
    # refreshes it instead of skipping it as an absent optional matview.
    print("[1d/3] rebuild curated.codev_context (sql/47; cascade victim of sql/23)", flush=True)
    _exec("codev_context", "47_codev_context.sql")
    # curated.dev_scenario (sql/50) is a plain view on codev_context and died
    # with sql/47's DROP ... CASCADE. Column comments come back with the
    # skill's end-of-chain sql/31 re-run.
    print("[1e/3] recreate curated.dev_scenario (sql/50; view on codev_context)", flush=True)
    _exec("dev_scenario", "50_dev_scenario.sql")
    print("    NOTE: curated.erebor_locations and curated.box_scout_locations were dropped by this rebuild: "
          "finish with python -m scripts.apply_erebor_locations", flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild-reference", action="store_true",
                    help="rebuild sql/20 and its cascade victims first (drops curated.erebor_locations); default: check and keep them")
    a = ap.parse_args(argv)
    t = time.monotonic()
    if a.rebuild_reference:
        rebuild_reference()
    else:
        print("[1/3] curated.producing_reference and its dependents: checked, not rebuilt", flush=True)
        check_reference()

    print("[2/3] build curated.reconciled_inventory (overlap matching — heavy)", flush=True)
    _exec("reconciled_inventory", "68_reconcile_all_sticks.sql")

    print("[3/3] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # D117: every Novi stick is reconciled; split by Novi's tag for audit only.
            print("  status x basin x category:", flush=True)
            for b, c, s, n in cur.execute(
                "SELECT basin_blueox, category, status, COUNT(*) "
                "FROM curated.reconciled_inventory GROUP BY 1,2,3 ORDER BY 1,2,3"
            ).fetchall():
                print(f"    {b:9} {c:4} {s:22} {n}", flush=True)
            # NOTE: sql/21 (now sql/68) split the old 'realized_pud_to_pdp' status into
            # realized_drift (online after the vintage) / realized_phantom
            # (online before it); querying the retired name silently returns 0.
            print("  realized matches by matched_survey_planned (provisional TVD):", flush=True)
            for b, p, n in cur.execute(
                "SELECT basin_blueox, matched_survey_planned, COUNT(*) "
                "FROM curated.reconciled_inventory "
                "WHERE status IN ('realized_drift','realized_phantom') "
                "GROUP BY 1,2 ORDER BY 1,2"
            ).fetchall():
                print(f"    {b:9} survey_planned={p!s:5} {n}", flush=True)
            # drift count vs new-well anchor (Delaware); phantoms are
            # pre-vintage by definition, so the anchor uses drift only.
            realized_del = cur.execute(
                "SELECT COUNT(*) FROM curated.reconciled_inventory "
                "WHERE basin_blueox='delaware' AND status='realized_drift'"
            ).fetchone()[0]
            distinct_wells = cur.execute(
                "SELECT COUNT(DISTINCT matched_api10) FROM curated.reconciled_inventory "
                "WHERE basin_blueox='delaware' AND status='realized_drift'"
            ).fetchone()[0]
            res_drift = cur.execute(
                "SELECT COUNT(*) FROM curated.reconciled_inventory "
                "WHERE basin_blueox='delaware' AND status='realized_drift' AND category='RES'"
            ).fetchone()[0]
            new_del = cur.execute(
                "SELECT COUNT(*) FROM curated.wells w JOIN curated.formation_blueox fb ON fb.api10=w.api10 "
                "WHERE fb.basin_blueox='delaware' AND w.first_production_date > DATE '2025-09-30'"
            ).fetchone()[0]
            print(f"  anchor: Delaware realized_drift sticks={realized_del} (of which RES={res_drift}; "
                  f"distinct wells={distinct_wells}) vs wells online since 3Q25={new_del}", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
