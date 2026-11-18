"""Apply sql/73 (BOX sticks storage and identity) and verify it.

  1. sql/73, twice (idempotent): box.location_set, six identity columns on box.location, box.location_stick,
     box.location_set_dsu / _bench / _well; the location id sequence restarted at 10,000,001.
  2. Validate by identity: every row box.location held before is still there with the same id, basin, bench, vintages
     and geometry digest, and reads source = 'novi'; box.location_source / forecast_run / pud_forecast counts unchanged;
     columns, constraints, indexes and analyst_ro grants exist; EXPLAIN of a geography DWithin on box.location_stick
     names box_location_stick_geog_gix.
  3. Smoke inside a transaction that is ROLLED BACK: a Novi-style insert (what box_pud_run store does) still works and
     reads source = 'novi'; a set, a BOX stick location (id >= 10,000,001) and its stick insert; each of these is
     refused: a second record set in a basin, a Novi row with a pad id, a BOX row without a slot, a slot used twice,
     an unknown flag, a second-level TVD without its flag, a direct rung with an anchor, a U-turn without its turn.

--dry-run runs all three steps in ONE transaction and rolls it back (PostgreSQL DDL is transactional); nothing persists.

!! DDL on the shared warehouse: explicit authorization ("go apply") required, with or without --dry-run (a dry run still
takes a brief ACCESS EXCLUSIVE lock on box.location). Container first: point the DB_* env at the `scripts.box_rehearsal`
container (python -m scripts.box_rehearsal env). From repo root:
    python -m scripts.apply_box_location_set [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from psycopg import errors
from psycopg.types.json import Jsonb

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "73_box_location_set.sql"
ID_START = 10_000_001
TABLES = ("location_set", "location_stick", "location_set_dsu", "location_set_bench", "location_set_well")
LOCATION_COLS = ("source", "dsu_vintage", "pad_id", "slot_no", "first_seen_set", "last_seen_set")
INDEXES = ("box_location_set_record_basin_uq", "box_location_slot_uq", "box_location_source_ix", "box_location_stick_slot_uq",
           "box_location_stick_location_ix", "box_location_stick_geom_gix", "box_location_stick_geog_gix", "box_location_set_well_geog_gix")
CONSTRAINTS = ("box_location_source_ck", "box_location_source_shape_ck", "box_location_stick_match_ck", "box_location_stick_turn_ck",
               "box_location_stick_second_ck", "box_location_stick_anchor_ck", "box_location_set_inputs_ck", "box_location_set_dsu_wells_ck")
# identity of the rows that existed before: count, id range, and a digest over id + basin + bench + vintages + geometry
_BEFORE = ("SELECT count(*), min(location_id), max(location_id), "
           "md5(string_agg(location_id::text || basin || formation_blueox || first_seen_vintage || last_seen_vintage || md5(extensions.ST_AsEWKB(geom)::text), "
           "'' ORDER BY location_id)) FROM box.location WHERE location_id < %s")
_OTHER = ("SELECT (SELECT count(*) FROM box.location_source), (SELECT count(*) FROM box.forecast_run), "
          "(SELECT array_agg(basin || ':' || run_id ORDER BY basin) FROM box.forecast_run WHERE is_record), (SELECT count(*) FROM box.pud_forecast)")

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def apply_sql(cur) -> tuple:
    print("[1/3] sql/73: BOX sticks storage and identity (run twice)", flush=True)
    q = cur.execute
    print(f"    target {q('select inet_server_addr(), inet_server_port(), current_database()').fetchone()}", flush=True)
    before = (q(_BEFORE, (ID_START,)).fetchone(), q(_OTHER).fetchone())
    sql = SQL.read_text(encoding="utf-8")
    q(sql)
    q(sql)
    return before


def validate(cur, before: tuple) -> None:
    print("[2/3] validate", flush=True)
    q = cur.execute
    loc, other = before
    _check(q(_BEFORE, (ID_START,)).fetchone() == loc, f"the {loc[0]:,} rows box.location held are unchanged by identity (ids {loc[1]} to {loc[2]}, digest equal)")
    _check(q(_OTHER).fetchone() == other, f"location_source / runs / record run per basin / pud_forecast unchanged {other}")
    by = dict(q("SELECT source, count(*) FROM box.location WHERE location_id < %s GROUP BY 1", (ID_START,)).fetchall())
    _check(by == {"novi": loc[0]} or (loc[0] == 0 and not by), f"every existing row reads source = 'novi' ({by})")
    cols = {r[0]: r[1] for r in q("SELECT column_name, is_nullable FROM information_schema.columns WHERE table_schema = 'box' AND table_name = 'location'").fetchall()}
    _check(all(c in cols for c in LOCATION_COLS), f"box.location has {', '.join(LOCATION_COLS)}")
    _check(cols.get("source") == "NO" and cols.get("first_seen_vintage") == "YES" and cols.get("last_seen_vintage") == "YES",
           "source is NOT NULL; the two vintage columns are nullable (the shape CHECK keeps them on Novi rows)")
    have = {r[0] for r in q("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'box'").fetchall()}
    _check(all(t in have for t in TABLES), f"tables exist: {', '.join(TABLES)}")
    _check(all(i in have for i in INDEXES), f"indexes exist: {', '.join(i for i in INDEXES)}")
    cons = {r[0] for r in q("SELECT conname FROM pg_constraint WHERE conname = ANY(%s)", (list(CONSTRAINTS),)).fetchall()}
    _check(cons == set(CONSTRAINTS), f"constraints exist ({len(cons)} of {len(CONSTRAINTS)})")
    d = dict(q("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'box' AND indexname = ANY(%s)", (list(INDEXES),)).fetchall())
    _check("UNIQUE" in d.get("box_location_set_record_basin_uq", "") and "WHERE is_record" in d.get("box_location_set_record_basin_uq", ""),
           "one record set per basin (box_location_set_record_basin_uq)")
    _check("UNIQUE" in d.get("box_location_slot_uq", "") and "box_sticks" in d.get("box_location_slot_uq", ""), "one location per DSU x bench x slot (box_location_slot_uq)")
    grants = {r[0] for r in q("SELECT table_name FROM information_schema.role_table_grants WHERE grantee = 'analyst_ro' AND table_schema = 'box' "
                              "AND privilege_type = 'SELECT'").fetchall()}
    _check(all(t in grants for t in TABLES), "analyst_ro can SELECT the five new tables")
    seq = q("SELECT last_value, is_called FROM box.location_location_id_seq").fetchone()
    _check(seq[0] >= ID_START, f"the location id sequence starts at {ID_START:,} or later (last_value {seq[0]:,}, called {seq[1]})")
    q("SAVEPOINT ex")
    q("SET LOCAL enable_seqscan = off")
    plan = "\n".join(r[0] for r in q("EXPLAIN SELECT location_id FROM box.location_stick WHERE extensions.ST_DWithin(legs_geom::extensions.geography, "
                                     "extensions.ST_SetSRID(extensions.ST_MakePoint(-103.5, 31.8), 4326)::extensions.geography, 1000)").fetchall())
    _check("box_location_stick_geog_gix" in plan, "EXPLAIN: geography DWithin on box.location_stick uses box_location_stick_geog_gix")
    q("ROLLBACK TO SAVEPOINT ex")


def _refused(q, stmt: str, params: tuple, err, msg: str) -> None:
    q("SAVEPOINT s")
    try:
        q(stmt, params)
        _check(False, f"{msg} was ALLOWED")
        q("ROLLBACK TO SAVEPOINT s")
    except err:
        q("ROLLBACK TO SAVEPOINT s")
        _check(True, f"{msg} is refused")


_SET = ("INSERT INTO box.location_set (basin, generator_version, code_sha, narvi_sha, dsu_vintage, pulled_at, tag_run_id, tag_policy_digest, cfg, inputs, is_record) "
        "VALUES (%s, 'smoke', 'smoke', 'smoke', '_SMOKE', now(), 0, 'smoke', '{}'::jsonb, %s, %s) RETURNING set_id")
_LOC = ("INSERT INTO box.location (basin, formation_blueox, geom, lateral_ft, source, dsu_vintage, pad_id, slot_no, first_seen_set, last_seen_set) "
        "VALUES ('delaware', 'WCA_1', extensions.ST_GeomFromText(%s, 4326), 10000, %s, %s, %s, %s, %s, %s) RETURNING location_id")
_LEGS1 = "MULTILINESTRING ((-103.5 31.80, -103.5 31.83))"
_LEGS2 = "MULTILINESTRING ((-103.5 31.80, -103.5 31.81), (-103.496 31.81, -103.496 31.80))"
_TURN = "LINESTRING (-103.5 31.81, -103.498 31.812, -103.496 31.81)"


def _stick(sid: int, lid: int, **kw) -> tuple[str, tuple]:
    r = {"well_type": "single", "n_legs": 1, "legs": _LEGS1, "turn": None, "rung": "direct", "anchor": [], "second": None, "flags": ["pinned"]} | kw
    sql = ("INSERT INTO box.location_stick (set_id, location_id, basin, pad_id, formation_blueox, slot_no, well_name, well_type, n_legs, legs_geom, turn_geom, "
            "completed_lateral_ft, drilled_lateral_ft, azimuth_deg, azimuth_grid_deg, azimuth_basis, gunbarrel_x_ft, setback_ft, target_tvd_ft, tvd_rung, tvd_anchor, "
            "tvd_err_median_ft, tvd_err_p90_ft, second_level_tvd_ft, spacing_ft, spacing_map_ft, spacing_grid, flags, match_method, detail) "
            "VALUES (%s, %s, 'delaware', 1, 'WCA_1', 1, '1-WCA_1-01', %s, %s, extensions.ST_GeomFromText(%s, 4326), extensions.ST_GeomFromText(%s, 4326), 10000, 10000, "
            "0, 179.1, 'smoke', '{0}', 330, 11000, %s, %s, 33, 99.5, %s, 880, 880, 'pinned', %s, 'seed', '{}'::jsonb)")
    return sql, (sid, lid, r["well_type"], r["n_legs"], r["legs"], r["turn"], r["rung"], r["anchor"], r["second"], r["flags"])


def smoke(cur) -> None:
    print("[3/3] smoke (rolled back)", flush=True)
    q = cur.execute
    inputs = Jsonb({"relations": {}, "extents": {}, "files": {}})
    q("SAVEPOINT smoke")
    try:
        novi = q("INSERT INTO box.location (basin, formation_blueox, geom, lateral_ft, first_seen_vintage, last_seen_vintage) VALUES ('delaware', 'WCA_1', "
                 "extensions.ST_GeomFromText('LINESTRING (-103.5 31.8, -103.5 31.83)', 4326), 10000, '_SMOKE', '_SMOKE') RETURNING location_id, source").fetchone()
        _check(novi[1] == "novi", f"a Novi-style insert (box_pud_run store) still works and reads source = 'novi' (id {novi[0]:,})")
        s1 = q(_SET, ("delaware", inputs, True)).fetchone()[0]
        _check(True, f"a record set inserts ({s1})")
        _refused(q, _SET, ("delaware", inputs, True), errors.UniqueViolation, "a second record set in the same basin")
        s2 = q(_SET, ("midland", inputs, True)).fetchone()[0]
        _check(True, f"a Midland record set inserts next to it ({s2})")
        _refused(q, _SET, ("delaware", Jsonb({"relations": {}}), False), errors.CheckViolation, "a set without its input manifest")
        lid = q(_LOC, (_LEGS1, "box_sticks", "_SMOKE", 1, 1, s1, s1)).fetchone()[0]
        _check(lid >= ID_START, f"a BOX stick location takes an id >= {ID_START:,} ({lid:,})")
        _refused(q, _LOC, (_LEGS1, "box_sticks", "_SMOKE", 1, 1, s1, s1), errors.UniqueViolation, "the same DSU x bench x slot twice")
        _refused(q, _LOC, (_LEGS1, "box_sticks", "_SMOKE", 1, None, s1, s1), errors.CheckViolation, "a BOX stick location without a slot")
        _refused(q, _LOC, (_LEGS1, "novi", None, 1, None, None, None), errors.CheckViolation, "a Novi location with a pad id (and no vintage)")
        _refused(q, _LOC, (_LEGS1, "other", "_SMOKE", 1, 2, s1, s1), errors.CheckViolation, "an unknown source")
        q(*_stick(s1, lid))
        _check(True, "a stick row inserts")
        q("DELETE FROM box.location_stick WHERE set_id = %s", (s1,))
        _refused(q, *_stick(s1, lid, flags=["pinned", "made_up"]), errors.CheckViolation, "an unknown flag")
        _refused(q, *_stick(s1, lid, second=11200.0), errors.CheckViolation, "a second-level TVD without the second_level_nearby flag")
        _refused(q, *_stick(s1, lid, anchor=["WCB_1"]), errors.CheckViolation, "a direct rung with an anchor")
        _refused(q, *_stick(s1, lid, rung="thickness"), errors.CheckViolation, "a carried rung without an anchor")
        _refused(q, *_stick(s1, lid, well_type="uturn", n_legs=2, legs=_LEGS2), errors.CheckViolation, "a U-turn without its turn geometry")
        q(*_stick(s1, lid, well_type="uturn", n_legs=2, legs=_LEGS2, turn=_TURN, rung="bracket", anchor=["BS3_S", "WCB_1"],
                  second=None, flags=["dsu_drilled_across"]))
        _check(True, "a U-turn on the bracket rung with two anchors inserts")
        q("DELETE FROM box.location_set WHERE set_id = %s", (s2,))
        _refused(q, "DELETE FROM box.location_set WHERE set_id = %s", (s1,), errors.ForeignKeyViolation, "deleting a set that locations were first seen in")
    finally:
        q("ROLLBACK TO SAVEPOINT smoke")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="one transaction, rolled back at the end: nothing persists")
    a = ap.parse_args()
    conn = get_connection()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            before = apply_sql(cur)
            validate(cur, before)
            smoke(cur)
        if a.dry_run or _failures:
            conn.rollback()
            print("ROLLED BACK: nothing persisted" + ("" if a.dry_run else " (checks failed)"), flush=True)
        else:
            conn.commit()
            print("COMMITTED", flush=True)
    finally:
        conn.close()
    if _failures:
        sys.exit(f"{len(_failures)} check(s) FAILED")
    print("all checks passed", flush=True)


if __name__ == "__main__":
    main()
