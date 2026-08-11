"""Apply sql/39 — curated.enverus_lateral_lines (standalone, no cascade).

Creates the Enverus LateralLine matview that anduin COALESCEs over the
4-point wellstick_geom to fix u-turn/horseshoe stick rendering. Standalone
object over raw_enverus.wells only: nothing downstream exists, sql/04 is
untouched, no availability impact on any existing matview — safe during
working hours (still requires explicit authorization per the warehouse DDL
rule; this script does not decide that for you).

Steps:
  1. sql/39  DROP+CREATE curated.enverus_lateral_lines + unique index
  2. sql/31  re-apply data-dictionary comments (idempotent COMMENT ON)
  3. validate() — identity-based, no point-in-time constants:
       * matview rows  <= distinct api10 with a textual LINESTRING (the
         difference = post-parse rejects; warned at > 1%)
       * zero rows failing ST_IsValid / ST_NPoints >= 2 (belt & braces)
       * unique index exists by name (the assert-the-index pattern)
       * horseshoe poster children 3001553276-79 each have > 10 vertices
       * coverage fraction vs wells_enriched horizontals (warn < 95%)

Run from repo root in the venv:
    python -m scripts.apply_enverus_lateral_lines
"""

from __future__ import annotations

import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"

# The same textual predicates sql/39's CTE applies BEFORE parsing. Kept in
# lockstep with sql/39 — the validation identity depends on it.
_TEXTUAL_PREDICATES = """
    deleteddate IS NULL
    AND api_uwi_14_unformatted IS NOT NULL
    AND lateralline IS NOT NULL
    AND lateralline <> 'NULL'
    AND lateralline LIKE 'LINESTRING%'
"""

_HORSESHOE_POSTER_CHILDREN = (
    "3001553276",  # VANADIUM 32 STATE COM 004H — verified 81-93 vertex lines
    "3001553277",
    "3001553278",
    "3001553279",
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


def _scalar(q: str, params: tuple = ()) -> int:
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            return cur.execute(q, params).fetchone()[0]
    finally:
        conn.close()


def validate() -> None:
    print("[validate] enverus_lateral_lines identity + geometry sanity", flush=True)

    mv = _scalar("SELECT COUNT(*) FROM curated.enverus_lateral_lines")
    distinct_txt = _scalar(
        "SELECT COUNT(DISTINCT LEFT(api_uwi_14_unformatted, 10)) "
        f"FROM raw_enverus.wells WHERE {_TEXTUAL_PREDICATES}"
    )
    rejects = distinct_txt - mv
    print(f"    matview rows {mv} / distinct api10 with textual line {distinct_txt} "
          f"(post-parse rejects: {rejects})", flush=True)
    if mv == 0:
        raise SystemExit("FAILED: matview is empty")
    if mv > distinct_txt:
        raise SystemExit(
            f"FAILED: matview {mv} exceeds its source identity {distinct_txt}"
        )
    if rejects > distinct_txt * 0.01:
        print(f"    WARNING: {rejects} post-parse rejects (> 1%) — inspect "
              "raw LateralLine quality", flush=True)

    bad = _scalar(
        "SELECT COUNT(*) FROM curated.enverus_lateral_lines "
        "WHERE NOT extensions.ST_IsValid(lateral_geom) "
        "   OR extensions.ST_NPoints(lateral_geom) < 2"
    )
    print(f"    invalid/degenerate geometries: {bad} (expect 0)", flush=True)
    if bad:
        raise SystemExit(f"FAILED: {bad} invalid geometries survived the WHERE")

    idx = _scalar(
        "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'curated' "
        "AND indexname = 'idx_curated_enverus_lateral_lines_api10'"
    )
    if idx != 1:
        raise SystemExit("FAILED: unique index idx_curated_enverus_lateral_lines_api10 missing")
    print("    unique index present", flush=True)

    for api10 in _HORSESHOE_POSTER_CHILDREN:
        npts = _scalar(
            "SELECT COALESCE(MAX(extensions.ST_NPoints(lateral_geom)), 0) "
            "FROM curated.enverus_lateral_lines WHERE api10 = %s",
            (api10,),
        )
        print(f"    horseshoe {api10}: {npts} vertices (expect > 10)", flush=True)
        if npts <= 10:
            raise SystemExit(f"FAILED: horseshoe {api10} has {npts} vertices")

    hz = _scalar("SELECT COUNT(*) FROM curated.wells_enriched WHERE is_horizontal")
    covered = _scalar(
        "SELECT COUNT(*) FROM curated.wells_enriched w "
        "JOIN curated.enverus_lateral_lines ell ON ell.api10 = w.api10 "
        "WHERE w.is_horizontal"
    )
    frac = covered / hz if hz else 0.0
    print(f"    horizontal coverage: {covered}/{hz} = {frac:.1%} "
          "(2026-08 baseline 99.0%; warn-only below 95%)", flush=True)
    if frac < 0.95:
        print("    WARNING: coverage below 95% — check the Enverus load", flush=True)


def main() -> None:
    t = time.monotonic()
    print("[1/3] curated.enverus_lateral_lines (sql/39)", flush=True)
    _exec("enverus_lateral_lines", "39_enverus_lateral_lines.sql")

    print("[2/3] data-dictionary comments (sql/31, idempotent)", flush=True)
    _exec("comments", "31_comments.sql")

    print("[3/3] validate", flush=True)
    validate()
    print(f"=== DONE in {time.monotonic() - t:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
