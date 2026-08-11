"""Apply sql/40 — U-turn is_horizontal fix + erebor_locations refresh.

CREATE OR REPLACE of the plain view curated.wells_enriched (no DROP, no
cascade; column list unchanged), then a CONCURRENTLY refresh of
curated.erebor_locations so its PDP universe picks up the newly-
horizontal horseshoe wells immediately instead of at the next nightly.
intel_pdp_support is quarterly-owned and is deliberately NOT refreshed
here.

Steps:
  1. sql/40  CREATE OR REPLACE curated.wells_enriched
  2. sql/31  re-apply comments (idempotent)
  3. validate the flag flip — identity-based:
       * zero u-turn wells with is_horizontal IS NOT TRUE
       * zero Vertical wells with is_horizontal = TRUE
       * horseshoe poster children 3001553276-79 are TRUE
  4. REFRESH MATERIALIZED VIEW CONCURRENTLY curated.erebor_locations
  5. validate the refresh — u-turn producing wells present as PDP rows
     (negative stick_id = -(api10) convention)

Run from repo root in the venv:
    python -m scripts.apply_uturn_is_horizontal
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"

_HORSESHOE_POSTER_CHILDREN = (
    "3001553276",
    "3001553277",
    "3001553278",
    "3001553279",
)


def _exec(label: str, statements: str) -> None:
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(statements)
    finally:
        conn.close()
    print(f"    {label} done in {time.monotonic() - t0:.0f}s", flush=True)


def _exec_file(label: str, fname: str) -> None:
    _exec(label, (SQL / fname).read_text(encoding="utf-8"))


def _scalar(q: str, params: tuple = ()) -> int:
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            # None when no params — psycopg parses %-placeholders whenever
            # a params sequence is supplied (even empty).
            return cur.execute(q, params or None).fetchone()[0]
    finally:
        conn.close()


def validate_flag() -> None:
    print("[validate] is_horizontal flip", flush=True)
    uturn_not_hz = _scalar(
        "SELECT COUNT(*) FROM curated.wells_enriched "
        "WHERE novi_slant_calculated ILIKE 'U-Turn%' AND is_horizontal IS NOT TRUE"
    )
    print(f"    u-turn wells not flagged horizontal: {uturn_not_hz} (expect 0)", flush=True)
    if uturn_not_hz:
        raise SystemExit(f"FAILED: {uturn_not_hz} u-turn wells still not horizontal")

    vertical_hz = _scalar(
        "SELECT COUNT(*) FROM curated.wells_enriched "
        "WHERE novi_slant_calculated = 'Vertical' AND is_horizontal = TRUE"
    )
    print(f"    Vertical wells flagged horizontal: {vertical_hz} (expect 0)", flush=True)
    if vertical_hz:
        raise SystemExit(f"FAILED: {vertical_hz} Vertical wells flagged horizontal")

    for api10 in _HORSESHOE_POSTER_CHILDREN:
        ok = _scalar(
            "SELECT COUNT(*) FROM curated.wells_enriched "
            "WHERE api10 = %s AND is_horizontal = TRUE",
            (api10,),
        )
        print(f"    horseshoe {api10}: is_horizontal={'TRUE' if ok else 'NOT TRUE'}", flush=True)
        if not ok:
            raise SystemExit(f"FAILED: horseshoe {api10} not flagged horizontal")

    uturn_total = _scalar(
        "SELECT COUNT(*) FROM curated.wells_enriched "
        "WHERE novi_slant_calculated ILIKE 'U-Turn%'"
    )
    print(f"    u-turn wells now horizontal: {uturn_total} (2026-08 baseline: 263)", flush=True)


def validate_erebor_locations() -> None:
    print("[validate] erebor_locations picked up u-turn PDP wells", flush=True)
    # PDP rows carry stick_id = -(api10) and unique_id = api10 (sign
    # convention of record — never abs()).
    missing = _scalar(
        "SELECT COUNT(*) FROM curated.wells_enriched w "
        "WHERE w.novi_slant_calculated ILIKE 'U-Turn%' "
        "  AND w.first_production_date IS NOT NULL "
        "  AND NOT EXISTS (SELECT 1 FROM curated.erebor_locations el "
        "                  WHERE el.unique_id = w.api10)"
    )
    present = _scalar(
        "SELECT COUNT(*) FROM curated.wells_enriched w "
        "WHERE w.novi_slant_calculated ILIKE 'U-Turn%' "
        "  AND EXISTS (SELECT 1 FROM curated.erebor_locations el "
        "              WHERE el.unique_id = w.api10)"
    )
    print(f"    u-turn wells present in erebor_locations: {present}", flush=True)
    print(f"    producing u-turn wells missing: {missing}", flush=True)
    # Not a hard identity: erebor_locations applies its own predicates
    # beyond is_horizontal (geometry, basin), so warn-only on nonzero,
    # fail only if NOTHING landed.
    if present == 0:
        raise SystemExit("FAILED: no u-turn wells landed in erebor_locations")
    if missing:
        print(f"    WARNING: {missing} producing u-turn wells still absent — "
              "check erebor_locations' other predicates before alarm", flush=True)


def main() -> None:
    t = time.monotonic()
    print("[1/5] wells_enriched CREATE OR REPLACE (sql/40)", flush=True)
    _exec_file("wells_enriched", "40_uturn_is_horizontal.sql")

    print("[2/5] comments (sql/31, idempotent)", flush=True)
    _exec_file("comments", "31_comments.sql")

    print("[3/5] validate flag", flush=True)
    validate_flag()

    print("[4/5] REFRESH erebor_locations (CONCURRENTLY)", flush=True)
    _exec(
        "erebor_locations refresh",
        "REFRESH MATERIALIZED VIEW CONCURRENTLY curated.erebor_locations;",
    )

    print("[5/5] validate erebor_locations", flush=True)
    validate_erebor_locations()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
