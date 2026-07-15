"""Apply the wellstick degeneracy fix (sql/32) — full curated CASCADE rebuild.

sql/04's wellstick_geom change requires DROP MATERIALIZED VIEW curated.wells
CASCADE, which takes down everything downstream of curated.wells — including
the intel chain (curated.intel_locations LEFT JOINs curated.wells since
sql/29). Only curated.production (raw-only sources) survives. This script
rebuilds the whole graph in dependency order:

  wells branch                          intel branch
  ------------                          ------------
   1. sql/04  curated.wells              8. sql/29  intel_locations (+views)
   2. wells geography expression         9. sql/26  geography indexes
      index + ANALYZE (see below)           (both, idempotent) + ANALYZE
   3. sql/16  formation_blueox          10. apply_intel_formation_blueox
   4. sql/20  producing_reference           (sql/14 crosswalk + sql/18
   5. sql/23  formation_blueox_tvd           bench_reference + sql/19)
   6. sql/06  wells_enriched +          11. sql/21  reconciled_inventory
      production_normalized +           12. sql/25  net_new_pdp
      type_curve_cohorts                13. apply_intel_pdp_support (sql/30)
   7. sql/10  production_forecast +     14. apply_erebor_locations (sql/22,
      production_combined                   FINAL: restores refresh_all() +
                                            re-applies sql/31 comments)

Steps 4-6 make apply_reconciled_inventory's own 20→23→wells_enriched preamble
unnecessary, so step 11 runs sql/21 directly (same topological order as that
script — keep the two in sync if either changes).

INDEX ORDERING IS LOAD-BEARING (learned on the 2026-07-14 first run): the
expression geography indexes must exist BEFORE the spatial builders that
filter with ST_DWithin(geom::geography, ...), or those builds seq-scan —
sql/23 ran 49 min instead of ~3, and sql/30 was cancelled after ~15 h (it
rebuilt in minutes once indexed). Hence step 2 creates the curated.wells
geography index immediately after sql/04 (sql/26 can't run yet — it also
indexes intel_locations, which doesn't exist until sql/29), and step 9 runs
the full sql/26 right after sql/29, before every intel spatial builder.

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

# Recreated inline right after sql/04 so sql/23's ST_DWithin(::geography)
# pass is indexed (sql/26 also covers it, idempotently, at step 9 — it can't
# run this early because it additionally indexes curated.intel_locations).
_WELLS_GEOG_INDEX = """
CREATE INDEX IF NOT EXISTS idx_curated_wells_wellstick_geog
    ON curated.wells USING GIST ((wellstick_geom::geography));
ANALYZE curated.wells;
"""

# (label, sql file) pairs executed verbatim, in order.
_WELLS_BRANCH: tuple[tuple[str, str], ...] = (
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

    # Invariant-based checks, not point-in-time constants (2026-07-15 lesson:
    # a stale "~183k" expectation sent us chasing a phantom defect).
    prod = _scalar("SELECT COUNT(*) FROM curated.production")
    norm = _scalar("SELECT COUNT(*) FROM curated.production_normalized")
    print(f"    production_normalized {norm} vs production {prod} "
          f"(INNER JOIN wells + MoP filter: expect within a few % of production)",
          flush=True)
    if norm < prod * 0.9:
        raise SystemExit(f"FAILED: production_normalized {norm} lost >10% of "
                         f"curated.production {prod}")
    puds = _scalar(
        "SELECT COUNT(*) FROM curated.intel_locations il "
        "JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id "
        "WHERE il.category = 'PUD' AND il.wellstick_geom IS NOT NULL "
        "  AND fb.formation_blueox IS NOT NULL"
    )
    recon = _scalar("SELECT COUNT(*) FROM curated.reconciled_inventory")
    print(f"    reconciled_inventory {recon} vs mapped PUD universe {puds} "
          f"(grain: one row per mapped PUD — must be EQUAL)", flush=True)
    if recon != puds:
        raise SystemExit(f"FAILED: reconciled_inventory {recon} != mapped PUD "
                         f"universe {puds}")
    print(f"    erebor_locations: {_scalar('SELECT COUNT(*) FROM curated.erebor_locations')} "
          f"rows (~262k as of 2026-07)", flush=True)


def _exec_raw(label: str, statements: str) -> None:
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(statements)
    finally:
        conn.close()
    print(f"    {label} done in {time.monotonic() - t0:.0f}s", flush=True)


def main() -> None:
    t = time.monotonic()
    n = 14
    print(f"[1/{n}] curated.wells (sql/04 — the CASCADE drop + new wellstick)", flush=True)
    _exec("curated.wells", "04_curated.sql")

    print(f"[2/{n}] wells geography expression index (sql/23 and sql/30 seq-scan "
          "without it)", flush=True)
    _exec_raw("wells geog index + ANALYZE", _WELLS_GEOG_INDEX)

    for i, (label, fname) in enumerate(_WELLS_BRANCH, start=3):
        print(f"[{i}/{n}] {label}", flush=True)
        _exec(label, fname)

    print(f"[8/{n}] intel_locations + intel views (sql/29)", flush=True)
    _exec("intel_locations", "29_curated_intel_sf.sql")

    print(f"[9/{n}] geography expression indexes (sql/26 — BEFORE the intel "
          "spatial builders)", flush=True)
    _exec("geography indexes", "26_geography_indexes.sql")

    print(f"[10/{n}] intel_formation_blueox chain (sql/14 + sql/18 + sql/19)", flush=True)
    apply_intel_formation_blueox.main()

    print(f"[11/{n}] reconciled_inventory (sql/21 — producing_reference/tvd/"
          "wells_enriched already rebuilt in steps 4-6)", flush=True)
    _exec("reconciled_inventory", "21_reconciled_inventory.sql")

    print(f"[12/{n}] net_new_pdp (sql/25)", flush=True)
    _exec("net_new_pdp", "25_net_new_pdp.sql")

    # build()/validate() directly, not main() — its argparse would re-parse
    # THIS script's argv.
    print(f"[13/{n}] intel_pdp_support (sql/30)", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        apply_intel_pdp_support.build(conn)
        apply_intel_pdp_support.validate(conn)
    finally:
        conn.close()

    print(f"[14/{n}] erebor_locations — FINAL step (sql/22 + refresh_all() + sql/31)",
          flush=True)
    apply_erebor_locations.main()

    validate()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
