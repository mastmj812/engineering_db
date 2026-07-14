"""Surface Novi WellSpacing.LateralCloserXY on curated.wells_enriched (in-place).

Recreates ONLY the wells_enriched view (adding lateral_closer_xy_ft +
wellspacing_vintage from raw_novi."WellSpacing"), then curated.erebor_locations
(cascaded by the view drop) and the sql/26 geography indexes — WITHOUT
rebuilding the 4.9M-row production_normalized / type_curve_cohorts matviews
that a wholesale sql/06 run would, and WITHOUT touching curated.wells (whose
DROP-CASCADE would force the ~22M-row production_forecast rebuild). The
wells_enriched DDL is EXTRACTED from the canonical sql/06 (single source of
truth); erebor_locations from sql/22.

LateralCloserXY semantics: as-of-first-production, confirmed with Novi
2026-07-14 (the sql/06 comment tracks the same).

Run from repo root in the venv:
    python -m scripts.apply_lateral_closer_xy
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"


def _slice(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[i:j]


def main() -> None:
    t0 = time.monotonic()
    s06 = (SQL / "06_curated_derived.sql").read_text(encoding="utf-8")
    we_block = _slice(
        s06,
        "DROP VIEW IF EXISTS curated.wells_enriched CASCADE;",
        "auto-syncs with wells.';",
    )
    erebor = (SQL / "22_erebor_locations.sql").read_text(encoding="utf-8")
    geog = (SQL / "26_geography_indexes.sql").read_text(encoding="utf-8")

    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("[1/3] recreate curated.wells_enriched (+LateralCloserXY) "
                  "— drops erebor_locations via CASCADE", flush=True)
            cur.execute(we_block)
            print("[2/3] recreate curated.erebor_locations (sql/22)", flush=True)
            cur.execute(erebor)
            print("[3/3] re-run sql/26 geography indexes (idempotent)", flush=True)
            cur.execute(geog)
    finally:
        conn.close()
    print(f"  applied in {time.monotonic() - t0:.0f}s", flush=True)

    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("  lateral_closer_xy_ft coverage:", flush=True)
            n_total, n_ls, n_vint = cur.execute(
                "SELECT COUNT(*), COUNT(lateral_closer_xy_ft), "
                "COUNT(DISTINCT wellspacing_vintage) "
                "FROM curated.wells_enriched"
            ).fetchone()
            print(f"    wells {n_total}, with LateralCloserXY {n_ls}, "
                  f"distinct vintages {n_vint} (expect 1 after a clean nightly)",
                  flush=True)
            lo, med, hi = cur.execute(
                "SELECT percentile_cont(0.1) WITHIN GROUP (ORDER BY lateral_closer_xy_ft), "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY lateral_closer_xy_ft), "
                "percentile_cont(0.9) WITHIN GROUP (ORDER BY lateral_closer_xy_ft) "
                "FROM curated.wells_enriched WHERE lateral_closer_xy_ft IS NOT NULL"
            ).fetchone()
            print(f"    P10/P50/P90 lateral_closer_xy_ft: {lo:.0f} / {med:.0f} / "
                  f"{hi:.0f} ft (sanity: Permian development spacing ~400-1500 ft)",
                  flush=True)
            n_ereb = cur.execute(
                "SELECT COUNT(*) FROM curated.erebor_locations"
            ).fetchone()[0]
            print(f"    erebor_locations rows: {n_ereb} (expect ~262k)", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t0:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
