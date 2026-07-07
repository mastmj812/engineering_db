"""Wire the TVD-sanity correction into curated.wells_enriched (Supabase, in-place).

Recreates ONLY the wells_enriched view (now overriding formation_blueox with the
sql/23 correction), curated.erebor_locations (cascaded by the view drop), and
refresh_all() — WITHOUT rebuilding the 4.9M-row production_normalized /
type_curve_cohorts matviews that a wholesale sql/06 run would. The wells_enriched
+ refresh_all DDL is EXTRACTED from the canonical sql/06 (single source of truth);
erebor_locations from sql/22.

Run from repo root in the venv:
    python -m scripts.apply_tvd_override
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
    refresh_block = _slice(
        s06,
        "CREATE OR REPLACE FUNCTION curated.refresh_all()",
        "$$ LANGUAGE plpgsql;",
    )
    erebor = (SQL / "22_erebor_locations.sql").read_text(encoding="utf-8")

    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("[1/3] recreate curated.wells_enriched (override) "
                  "— drops erebor_locations via CASCADE", flush=True)
            cur.execute(we_block)
            print("[2/3] recreate curated.erebor_locations (sql/22)", flush=True)
            cur.execute(erebor)
            print("[3/3] update curated.refresh_all()", flush=True)
            cur.execute(refresh_block)
    finally:
        conn.close()
    print(f"  applied in {time.monotonic() - t0:.0f}s", flush=True)

    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("  wells_enriched override spot-checks "
                  "(formation_blueox, base, source, tvd_corrected, basin):", flush=True)
            for api in ("3002550278", "3002550282"):
                r = cur.execute(
                    "SELECT formation_blueox, formation_blueox_base, formation_blueox_source, "
                    "formation_blueox_tvd_corrected, basin_blueox "
                    "FROM curated.wells_enriched WHERE api10=%s", (api,)
                ).fetchone()
                print(f"    {api}: {r}", flush=True)
            print("  erebor_locations PDP spot-check (stick_id = -3002550278):", flush=True)
            r = cur.execute(
                "SELECT stick_id, category, formation_blueox, basin_blueox, formation_blueox_source "
                "FROM curated.erebor_locations WHERE stick_id = -3002550278"
            ).fetchone()
            print(f"    {r}", flush=True)
            n = cur.execute(
                "SELECT COUNT(*) FROM curated.wells_enriched WHERE formation_blueox_tvd_corrected"
            ).fetchone()[0]
            print(f"  wells_enriched rows flagged tvd_corrected: {n}", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t0:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
