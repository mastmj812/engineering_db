"""Materialize curated.erebor_locations + wire its nightly refresh (Supabase).

Converts curated.erebor_locations from a plain VIEW (re-joined on every map tile)
to a MATERIALIZED VIEW with a GiST/btree index set, then updates
curated.refresh_all() so the nightly run keeps it current. See
docs/erebor_locations_materialization.md for rationale + measured before/after.

  1. recreate curated.erebor_locations as a matview WITH DATA + indexes (sql/22).
     The type-aware drop in sql/22 handles the one-time VIEW -> matview flip. Its
     CASCADE drops the land-facing view curated.box_scout_locations, so sql/69 is
     re-run right after.
  2. CREATE OR REPLACE curated.refresh_all() extracted from the canonical sql/06
     (now ending with `REFRESH ... CONCURRENTLY curated.erebor_locations`).
  3. re-apply sql/31 data-dictionary comments: the quarterly CASCADE drops the
     intel-derived matviews and their COMMENTs with them (sql/26-index pattern).
  4. validate: row counts by category, stick_id uniqueness (CONCURRENTLY needs it),
     a CONCURRENTLY refresh smoke test, and an index-usage check on the tile query.

Quarterly Novi reload (.claude/skills/novi-quarterly-reload/SKILL.md): its LAST curated step is

    python -m scripts.apply_erebor_locations --after-reload

which re-applies the sql/31 comments and checks curated.erebor_locations still stands. That relation reads no Novi
Intelligence relation since phase 7 item 2 (docs/box_sticks_plan.md) and is NOT dropped by a reload, so it is not touched
and erebor stays up. (The Novi stick table sql/78 this step used to rebuild is retired, phase 8.)

The full run (no flag) is for a structural rebuild that did drop curated.erebor_locations: curated.wells (sql/04) or
curated.producing_reference (sql/20, e.g. apply_reconciled_inventory --rebuild-reference) rebuilt from scratch.

Run from repo root in the venv:
    python -m scripts.apply_erebor_locations [--after-reload]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from etl.db import get_connection
from scripts.apply_box_scout_locations import recreate as recreate_box_scout

SQL = Path(__file__).resolve().parent.parent / "sql"


def _slice(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i) + len(end)
    return text[i:j]


def after_reload() -> int:
    """The quarterly reload's last curated step: the sql/31 comments (the reload's CASCADE takes the intel matviews'
    comments with them). curated.erebor_locations must be standing and is not touched. Until BOX sticks phase 8 this
    step also rebuilt curated.novi_stick_locations (sql/78), which is retired."""
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            q = cur.execute
            el = q("SELECT c.relispopulated FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                   "WHERE n.nspname = 'curated' AND c.relname = 'erebor_locations' AND c.relkind = 'm'").fetchone()
            if el is None or not el[0]:
                raise SystemExit("curated.erebor_locations is missing or empty: something dropped it (a from-scratch rebuild of "
                                 "curated.wells or curated.producing_reference?). Run the full python -m scripts.apply_erebor_locations.")
            before = q("SELECT category, count(*) FROM curated.erebor_locations GROUP BY 1 ORDER BY 1").fetchall()
            print("[1/2] re-apply data-dictionary comments (sql/31)", flush=True)
            q((SQL / "31_comments.sql").read_text(encoding="utf-8"))
            print("[2/2] validation", flush=True)
            after = q("SELECT category, count(*) FROM curated.erebor_locations GROUP BY 1 ORDER BY 1").fetchall()
            ok = after == before
            print(f"    curated.erebor_locations untouched: {before} -> {after}: {ok}", flush=True)
    finally:
        conn.close()
    print(f"=== {'DONE' if ok else 'FAILED'} in {time.monotonic() - t0:.0f}s ===", flush=True)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--after-reload", action="store_true",
                    help="the quarterly reload's last step: sql/31 comments only; curated.erebor_locations is checked, not touched")
    a = ap.parse_args(argv)
    if a.after_reload:
        return after_reload()
    t0 = time.monotonic()
    erebor = (SQL / "22_erebor_locations.sql").read_text(encoding="utf-8")
    s06 = (SQL / "06_curated_derived.sql").read_text(encoding="utf-8")
    refresh_block = _slice(
        s06,
        "CREATE OR REPLACE FUNCTION curated.refresh_all()",
        "$$ LANGUAGE plpgsql;",
    )

    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print("[1/4] materialize curated.erebor_locations (sql/22: BOX sticks + producing wells) — WITH DATA + indexes", flush=True)
            t = time.monotonic()
            cur.execute(erebor)
            print(f"    built in {time.monotonic() - t:.0f}s", flush=True)
            recreate_box_scout(cur)  # sql/22's CASCADE drops the dependent sql/69 view
            print("    re-created curated.box_scout_locations (sql/69)", flush=True)

            print("[2/4] update curated.refresh_all() (sql/06)", flush=True)
            cur.execute(refresh_block)

            comments = SQL / "31_comments.sql"
            if comments.exists():
                print("[3/4] re-apply data-dictionary comments (sql/31)",
                      flush=True)
                cur.execute(comments.read_text(encoding="utf-8"))
            else:
                print("[3/4] sql/31_comments.sql missing - skipped", flush=True)
    finally:
        conn.close()

    print("[4/4] validation", flush=True)
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            relkind = cur.execute(
                "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='curated' AND c.relname='erebor_locations'"
            ).fetchone()[0]
            print(f"    relkind={relkind!r} (expect 'm' = materialized view)", flush=True)

            print("    rows by category:", flush=True)
            for cat, n in cur.execute(
                "SELECT category, COUNT(*) FROM curated.erebor_locations GROUP BY 1 ORDER BY 1"
            ).fetchall():
                print(f"      {cat:4} {n}", flush=True)

            dups = cur.execute(
                "SELECT COUNT(*) FROM (SELECT stick_id FROM curated.erebor_locations "
                "GROUP BY 1 HAVING COUNT(*) > 1) x"
            ).fetchone()[0]
            nulls = cur.execute(
                "SELECT COUNT(*) FROM curated.erebor_locations WHERE stick_id IS NULL"
            ).fetchone()[0]
            print(f"    stick_id duplicates={dups} nulls={nulls} "
                  f"(both must be 0 for CONCURRENTLY refresh)", flush=True)

            print("    CONCURRENTLY refresh smoke test:", flush=True)
            t = time.monotonic()
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.erebor_locations")
            print(f"      ok in {time.monotonic() - t:.1f}s", flush=True)

            # Confirm the tile predicate now rides the GiST index (no Seq Scan).
            plan = cur.execute(
                "EXPLAIN (FORMAT TEXT) "
                "SELECT stick_id FROM curated.erebor_locations "
                "WHERE basin='delaware' AND wellstick_geom IS NOT NULL "
                "AND ST_Intersects(wellstick_geom, "
                "  ST_Transform(ST_TileEnvelope(12, 862, 1661), 4326))"
            ).fetchall()
            used_gist = any("idx_erebor_locations_geom" in row[0] for row in plan)
            print(f"    tile query uses GiST index: {used_gist}", flush=True)
            for row in plan:
                print(f"      {row[0]}", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t0:.0f}s ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
