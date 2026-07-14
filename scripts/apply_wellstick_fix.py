"""Apply the wellstick degeneracy fix (sql/32) — full curated CASCADE rebuild.

sql/04's wellstick_geom change requires DROP MATERIALIZED VIEW curated.wells
CASCADE, which takes down everything downstream of curated.wells — including
the intel chain (curated.intel_locations LEFT JOINs curated.wells since
sql/29). Only curated.production (raw-only sources) survives. This script
rebuilds the whole graph in dependency order:

  wells branch                          intel branch
  ------------                          ------------
   1. sql/04  curated.wells              7. sql/29  intel_locations (+views)
   2. sql/16  formation_blueox           8. apply_intel_formation_blueox
   3. sql/20  producing_reference           (sql/14 crosswalk + sql/18
   4. sql/23  formation_blueox_tvd           bench_reference + sql/19)
   5. sql/06  wells_enriched +           9. sql/21  reconciled_inventory
      production_normalized +           10. sql/25  net_new_pdp
      type_curve_cohorts                11. apply_intel_pdp_support (sql/30)
   6. sql/10  production_forecast +     12. apply_erebor_locations (sql/22,
      production_combined                   FINAL: restores refresh_all() +
                                            re-applies sql/31 comments)
                                        13. sql/26  geography indexes

Steps 3-5 make apply_reconciled_inventory's own 20→23→wells_enriched preamble
unnecessary, so step 9 runs sql/21 directly (same topological order as that
script — keep the two in sync if either changes). Step 13 is non-negotiable
after any matview drop-recreate (expression geography indexes; without them
ST_DWithin(geom::geography, ...) seq-scans and erebor/narvi go multi-second).

Availability: the dropped objects DO NOT EXIST until their step completes —
erebor/narvi/anduin go dark for the duration (production_forecast alone is
~12 GB and the longest step). Run off-hours, outside the nightly ETL window,
with explicit user authorization (operating manual: warehouse DDL rule).

Run from repo root in the venv:
    python -m scripts.apply_wellstick_fix
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection
from scripts import apply_erebor_locations, apply_intel_formation_blueox
from scripts import apply_intel_pdp_support

SQL = Path(__file__).resolve().parent.parent / "sql"

# (label, sql file) pairs executed verbatim, in order.
_WELLS_BRANCH: tuple[tuple[str, str], ...] = (
    ("curated.wells (sql/04 — the CASCADE drop + new wellstick)", "04_curated.sql"),
    ("formation_blueox (sql/16)", "16_formation_blueox.sql"),
    ("producing_reference (sql/20)", "20_producing_reference.sql"),
    ("formation_blueox_tvd (sql/23)", "23_formation_blueox_tvd.sql"),
    ("wells_enriched + production_normalized + cohorts (sql/06)", "06_curated_derived.sql"),
    ("production_forecast + production_combined (sql/10 — LONGEST step, ~12 GB)", "10_curated_forecast.sql"),
)


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


def _scalar(q: str) -> int:
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            return cur.execute(q).fetchone()[0]
    finally:
        conn.close()


def validate() -> None:
    """Post-rebuild sanity: no degenerate sticks, coverage up, counts sane."""
    print("[validate] wellstick degeneracy + coverage", flush=True)
    degen = _scalar(
        "SELECT COUNT(*) FROM curated.wells WHERE wellstick_geom IS NOT NULL "
        "AND ST_GeometryType(ST_LineMerge(wellstick_geom)) <> 'ST_LineString'"
    )
    sticks = _scalar("SELECT COUNT(wellstick_geom) FROM curated.wells")
    wells = _scalar("SELECT COUNT(*) FROM curated.wells")
    print(f"    degenerate sticks: {degen} (expect 0)", flush=True)
    print(f"    sticks {sticks} / wells {wells} "
          f"(A/B baseline 2026-07: 92,544 / 92,908 — was 90,574 with 859 degenerate)",
          flush=True)
    if degen:
        raise SystemExit(f"FAILED: {degen} degenerate sticks survived the rebuild")
    for mv, expect in (
        ("curated.production_normalized", "~22M"),
        ("curated.reconciled_inventory", "~183k"),
        ("curated.erebor_locations", "~262k"),
    ):
        print(f"    {mv}: {_scalar(f'SELECT COUNT(*) FROM {mv}')} rows (expect {expect})",
              flush=True)


def main() -> None:
    t = time.monotonic()
    n = 13
    for i, (label, fname) in enumerate(_WELLS_BRANCH, start=1):
        print(f"[{i}/{n}] {label}", flush=True)
        _exec(label, fname)

    print(f"[7/{n}] intel_locations + intel views (sql/29)", flush=True)
    _exec("intel_locations", "29_curated_intel_sf.sql")

    print(f"[8/{n}] intel_formation_blueox chain (sql/14 + sql/18 + sql/19)", flush=True)
    apply_intel_formation_blueox.main()

    print(f"[9/{n}] reconciled_inventory (sql/21 — producing_reference/tvd/"
          "wells_enriched already rebuilt in steps 3-5)", flush=True)
    _exec("reconciled_inventory", "21_reconciled_inventory.sql")

    print(f"[10/{n}] net_new_pdp (sql/25)", flush=True)
    _exec("net_new_pdp", "25_net_new_pdp.sql")

    # build()/validate() directly, not main() — its argparse would re-parse
    # THIS script's argv.
    print(f"[11/{n}] intel_pdp_support (sql/30)", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        apply_intel_pdp_support.build(conn)
        apply_intel_pdp_support.validate(conn)
    finally:
        conn.close()

    print(f"[12/{n}] erebor_locations — FINAL step (sql/22 + refresh_all() + sql/31)",
          flush=True)
    apply_erebor_locations.main()

    print(f"[13/{n}] geography expression indexes (sql/26)", flush=True)
    _exec("geography indexes", "26_geography_indexes.sql")

    validate()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
