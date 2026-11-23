"""BOX sticks cutover, warehouse half (docs/box_sticks_plan.md phase 6, step 4): the undrilled arm of
curated.erebor_locations becomes the record BOX stick set, and the Novi sticks move to curated.novi_stick_locations.

ONE transaction, so readers see the old relation until the commit and never a missing one:

  1. preflight on the record stick sets and the nightly status (nothing changes if a check fails)
  2. sql/78  curated.novi_stick_locations  (the Novi PUD / RES arm, for deal-intake)
  3. sql/22  curated.erebor_locations      (BOX sticks + producing wells; DROP ... CASCADE takes sql/69 with it)
  4. sql/69  curated.box_scout_locations   (re-created; empty for a basin until its record forecast run is on BOX sticks)
  5. sql/26  geography expression indexes  (idempotent)
  6. sql/31  comments
  7. checks by identity; then COMMIT (--go) or ROLLBACK (the default: a rehearsal)

After a commit: a REFRESH ... CONCURRENTLY smoke and an EXPLAIN that the tile predicate uses the GiST index, on a second
connection. The DROP in step 3 holds an exclusive lock on curated.erebor_locations until the commit: run it OFF-HOURS, outside
the nightly, and stop erebor's map from being used meanwhile (requests wait, they do not fail).

The record flips of the forecast runs are NOT done here (scripts.box_record23 flip, after this commit): until a basin's record
run is on BOX sticks the land team's view holds no row for it.

    python -m scripts.apply_box_stick_locations            # rehearsal: everything runs, then ROLLBACK
    python -m scripts.apply_box_stick_locations --go       # the cutover (explicit go only)
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from etl.db import get_connection
from scripts.apply_box_scout_locations import recreate as recreate_box_scout

SQL = Path(__file__).resolve().parent.parent / "sql"
FILES = ("78_novi_stick_locations.sql", "22_erebor_locations.sql", "26_geography_indexes.sql", "31_comments.sql")
TILE_SQL = ("EXPLAIN (FORMAT TEXT) SELECT stick_id FROM curated.erebor_locations WHERE basin = 'delaware' AND wellstick_geom IS NOT NULL "
            "AND extensions.ST_Intersects(wellstick_geom, extensions.ST_Transform(extensions.ST_TileEnvelope(12, 862, 1661), 4326))")
_BOX_EXPECT = """
SELECT k.basin, count(*) FILTER (WHERE COALESCE(s.status, 'open') <> 'producing') AS undrilled, count(*) AS sticks,
       count(*) FILTER (WHERE s.location_id IS NULL) AS not_judged
FROM box.location_stick k JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record
LEFT JOIN curated.box_location_status s ON s.location_id = k.location_id AND s.set_id = k.set_id
GROUP BY 1 ORDER BY 1
"""


class Checks:
    def __init__(self) -> None:
        self.bad: list[str] = []
        self.n = 0

    def __call__(self, ok: bool, msg: str) -> None:
        self.n += 1
        print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
        if not ok:
            self.bad.append(msg)


def preflight(q, ck: Checks) -> dict:
    """What the swap rests on. Returns the counts the post-checks compare against."""
    rec = q("SELECT basin, set_id FROM box.location_set WHERE is_record ORDER BY 1").fetchall()
    ck([r[0] for r in rec] == ["delaware", "midland"], f"one record BOX stick set per basin ({rec})")
    expect = {b: (int(u), int(n), int(nj)) for b, u, n, nj in q(_BOX_EXPECT).fetchall()}
    for b, (u, n, nj) in expect.items():
        ck(nj == 0, f"{b}: every record stick has a nightly status row ({n:,} sticks, {nj} not judged, {u:,} not producing)")
    odd = q("""SELECT count(*) FROM box.location_stick k JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record
               WHERE extensions.ST_GeometryType(CASE WHEN k.turn_geom IS NULL THEN extensions.ST_GeometryN(k.legs_geom, 1)
                     ELSE extensions.ST_LineMerge(extensions.ST_Collect(k.legs_geom, k.turn_geom)) END) <> 'ST_LineString'""").fetchone()[0]
    ck(odd == 0, f"every record stick's path is one LineString ({odd} are not)")
    low = q("SELECT min(k.location_id) FROM box.location_stick k JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record").fetchone()[0]
    ck(low is not None and low >= 10_000_001, f"BOX stick ids start at {low:,} (never a Novi id)")
    old = {c: int(n) for c, n in q("SELECT category, count(*) FROM curated.erebor_locations GROUP BY 1").fetchall()}
    novi = int(q("SELECT count(*) FROM curated.intel_locations WHERE category IN ('PUD', 'RES')").fetchone()[0])
    pdp_by_basin = {b: int(n) for b, n in q("SELECT basin, count(*) FROM curated.erebor_locations WHERE category = 'PDP' GROUP BY 1").fetchall()}
    print(f"    before: curated.erebor_locations by category {old}; Novi PUD + RES in curated.intel_locations {novi:,}", flush=True)
    return {"expect": expect, "old": old, "novi": novi, "pdp_by_basin": pdp_by_basin}


def swap(cur, ck: Checks, container: bool = False) -> dict:
    """Steps 1 to 7 inside the caller's transaction. `container` = the scripts.box_rehearsal database: curated objects are
    mirrored there as plain TABLES (so the mirrored curated.erebor_locations table is dropped first), and sql/26 / sql/31 are
    skipped because they name relations the container does not hold."""
    q = cur.execute
    if container:
        host = q("SELECT inet_server_port(), current_database()").fetchone()
        tab = q("SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'curated' AND c.relname = 'erebor_locations'").fetchone()
        if tab is None or tab[0] != "r":
            raise SystemExit(f"--container: curated.erebor_locations is not a mirrored table here ({host}, relkind {tab}); this is not the rehearsal container state")
    print("[1/7] preflight", flush=True)
    before = preflight(q, ck)
    if ck.bad:
        return before
    if container:
        q("DROP TABLE curated.erebor_locations CASCADE")           # the mirror's plain table; on live it is the matview sql/22 drops
        q("DROP VIEW IF EXISTS curated.box_scout_locations")
    for i, name in enumerate(FILES[:2], start=2):
        t = time.monotonic()
        print(f"[{i}/7] sql/{name}", flush=True)
        q((SQL / name).read_text(encoding="utf-8"))
        print(f"    done in {time.monotonic() - t:.0f} s", flush=True)
    print("[4/7] re-create curated.box_scout_locations (sql/69)", flush=True)
    recreate_box_scout(cur)
    for i, name in enumerate(FILES[2:], start=5):
        if container:
            print(f"[{i}/7] sql/{name}: skipped in the rehearsal container", flush=True)
            continue
        print(f"[{i}/7] sql/{name}", flush=True)
        q((SQL / name).read_text(encoding="utf-8"))

    print("[7/7] checks", flush=True)
    kind = dict(q("SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'curated' "
                  "AND c.relname IN ('erebor_locations', 'novi_stick_locations', 'box_scout_locations')").fetchall())
    ck(kind == {"erebor_locations": "m", "novi_stick_locations": "m", "box_scout_locations": "v"}, f"three relations exist with their kinds ({kind})")
    n_novi = int(q("SELECT count(*) FROM curated.novi_stick_locations").fetchone()[0])
    ck(n_novi == before["novi"], f"curated.novi_stick_locations rows = Novi PUD + RES sticks ({n_novi:,} = {before['novi']:,})")
    old_undrilled = sum(n for c, n in before["old"].items() if c in ("PUD", "RES"))
    if old_undrilled:      # the first cutover: the Novi arm moved, row for row
        ck(n_novi == old_undrilled, f"... and = the undrilled rows curated.erebor_locations carried before ({old_undrilled:,})")
    got = {(b, c): int(n) for b, c, n in q("SELECT basin, category, count(*) FROM curated.erebor_locations GROUP BY 1, 2").fetchall()}
    ck({c for _, c in got} == {"BOX", "PDP"}, f"categories are BOX and PDP only ({sorted({c for _, c in got})})")
    for b, (u, n, _) in before["expect"].items():
        ck(got.get((b, "BOX")) == u, f"{b}: BOX rows = record sticks not producing ({got.get((b, 'BOX'), 0):,} = {u:,} of {n:,})")
        ck(got.get((b, "PDP")) == before["pdp_by_basin"].get(b), f"{b}: producing-well rows unchanged ({got.get((b, 'PDP'), 0):,})")
    dup, nul = q("SELECT (SELECT count(*) FROM (SELECT stick_id FROM curated.erebor_locations GROUP BY 1 HAVING count(*) > 1) x), "
                 "(SELECT count(*) FROM curated.erebor_locations WHERE stick_id IS NULL)").fetchone()
    ck(dup == 0 and nul == 0, f"stick_id unique and never NULL ({dup} duplicates, {nul} NULL)")
    sign = q("SELECT count(*) FILTER (WHERE category = 'BOX' AND stick_id < 10000001), count(*) FILTER (WHERE category = 'PDP' AND stick_id >= 0) "
             "FROM curated.erebor_locations").fetchone()
    ck(tuple(sign) == (0, 0), f"BOX ids are 10,000,001 and up, PDP ids negative ({sign[0]} / {sign[1]} break it)")
    geo = dict(q("SELECT extensions.ST_GeometryType(wellstick_geom), count(*) FROM curated.erebor_locations WHERE category = 'BOX' GROUP BY 1").fetchall())
    ck(set(geo) == {"ST_LineString"}, f"every BOX geometry is a LineString ({geo})")
    miss = q("SELECT count(*) FILTER (WHERE tvd IS NULL), count(*) FILTER (WHERE ll_ft IS NULL), count(*) FILTER (WHERE pad_name IS NULL), "
             "count(*) FILTER (WHERE formation_blueox IS NULL), count(*) FILTER (WHERE pad_id IS NULL) FROM curated.erebor_locations WHERE category = 'BOX'").fetchone()
    ck(tuple(miss) == (0, 0, 0, 0, 0), f"every BOX row has a TVD, a lateral, a DSU name, a bench and a DSU id (missing: {tuple(miss)})")
    nopoly = q("SELECT count(DISTINCT (el.basin, el.pad_id)) FROM curated.erebor_locations el JOIN box.location_set t ON t.is_record AND t.basin = el.basin "
               "WHERE el.category = 'BOX' AND NOT EXISTS (SELECT 1 FROM raw_novi_intel.pads p WHERE p.report_version = t.dsu_vintage "
               "AND p.pad_id = el.pad_id AND p.basin = el.basin AND p.geom IS NOT NULL)").fetchone()[0]
    ck(nopoly == 0, f"every DSU of a BOX row has a polygon in raw_novi_intel.pads at the set's vintage ({nopoly} do not)")
    idx = {r[0] for r in q("SELECT indexname FROM pg_indexes WHERE schemaname = 'curated' AND tablename IN ('erebor_locations', 'novi_stick_locations')").fetchall()}
    need = {"idx_erebor_locations_pk", "idx_erebor_locations_geom", "idx_novi_stick_locations_pk", "idx_novi_stick_locations_geog"}
    ck(need <= idx, f"the unique and spatial indexes exist ({sorted(need - idx) or 'all'})")
    plan = [r[0] for r in q(TILE_SQL).fetchall()]
    ck(any("idx_erebor_locations_geom" in p for p in plan), "the tile predicate uses idx_erebor_locations_geom (EXPLAIN)")
    scout = {b: int(n) for b, n in q("SELECT basin, count(*) FROM curated.box_scout_locations GROUP BY 1").fetchall()}
    want = {b: int(n) for b, n in q(
        "SELECT r.basin, count(*) FROM box.forecast_run r JOIN box.pud_forecast p ON p.run_id = r.run_id AND p.coverage IN ('covered', 'covered_provisional') "
        "JOIN curated.erebor_locations el ON el.stick_id = p.stick_id AND el.category <> 'PDP' WHERE r.is_record GROUP BY 1").fetchall()}
    ck(scout == want, f"the land team's view = forecast rows of the record runs that are BOX sticks ({scout or 'no rows: no record run is on BOX sticks yet'})")
    com = q("SELECT obj_description('curated.erebor_locations'::regclass) LIKE '%%RECORD BOX stick set%%'").fetchone()[0]
    ck(bool(com), "the matview comment describes BOX sticks")
    return before


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--go", action="store_true", help="COMMIT. Without it the transaction is rolled back.")
    ap.add_argument("--container", action="store_true", help="the scripts.box_rehearsal database (DB_* point at it): see swap()")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    ck = Checks()
    conn = get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '60s'")
            print(f"BOX sticks cutover, warehouse half ({'GO' if a.go else 'rehearsal, rolled back'})", flush=True)
            swap(cur, ck, container=a.container)
        if ck.bad or not a.go:
            conn.rollback()
            print(f"ROLLED BACK in {time.monotonic() - t0:.0f} s. " + (f"{len(ck.bad)} of {ck.n} checks FAILED." if ck.bad else f"Rehearsal: {ck.n} of {ck.n} checks pass."), flush=True)
            return 1 if ck.bad else 0
        conn.commit()
        print(f"COMMITTED in {time.monotonic() - t0:.0f} s; {ck.n} of {ck.n} checks pass.", flush=True)
    finally:
        conn.close()
    with get_connection() as c2:                 # a second connection reads what was committed
        c2.autocommit = True
        with c2.cursor() as cur:
            t = time.monotonic()
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.erebor_locations")
            print(f"second connection: REFRESH ... CONCURRENTLY ok in {time.monotonic() - t:.1f} s", flush=True)
            plan = [r[0] for r in cur.execute(TILE_SQL).fetchall()]
            ok = any("idx_erebor_locations_geom" in p for p in plan)
            print(f"second connection: tile predicate uses the GiST index: {ok}", flush=True)
            return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
