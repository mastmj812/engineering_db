"""BOX sticks: prune superseded location sets. Deletes the rows of the named sets from box.location_stick,
box.location_set_dsu, box.location_set_bench and box.location_set_well, and KEEPS their box.location_set header row (config,
input manifest, counts, crosswalk) with a note. box.location is never touched: location ids and slot numbers are never
reused, and box.location.first_seen_set / last_seen_set keep pointing at the header rows.

Refuses a record set. Nothing here is a nightly step: every live prune is an explicit go.

    python -m scripts.box_sticks_prune --set-id 6 7 16 17 21          # rehearsal: everything runs, then ROLLBACK
    python -m scripts.box_sticks_prune --set-id 6 7 16 17 21 --go     # the same, then COMMIT and a check on a second connection
"""
from __future__ import annotations

import argparse
from datetime import UTC, date, datetime

from etl.db import get_connection

CHILD_TABLES = ("box.location_set_bench", "box.location_set_well", "box.location_stick", "box.location_set_dsu")   # delete order (bench references dsu)
_FINGERPRINT = ("SELECT count(*), md5(string_agg(k.set_id::text || k.location_id::text || k.well_name || k.target_tvd_ft::text, '' ORDER BY k.set_id, k.location_id)) "
                "FROM box.location_stick k JOIN box.location_set t USING (set_id) WHERE t.is_record")
_LOCATIONS = "SELECT count(*), max(location_id), md5(string_agg(location_id::text || COALESCE(slot_no::text, ''), '' ORDER BY location_id)) FROM box.location"
_INBOUND = """
SELECT c.conrelid::regclass::text, c.conname, c.confrelid::regclass::text
FROM pg_constraint c
WHERE c.contype = 'f' AND c.confrelid = ANY (%s::regclass[]) AND c.conrelid <> ALL (%s::regclass[]) AND c.conrelid <> 'box.location_set'::regclass
"""


def note(today: date) -> str:
    return f"pruned {today.isoformat()}: stick, dsu, bench and well rows deleted; header kept"


def child_counts(q, sets: list[int]) -> dict[str, dict[int, int]]:
    return {t: {int(s): int(n) for s, n in q(f"SELECT set_id, count(*) FROM {t} WHERE set_id = ANY (%s) GROUP BY 1", (sets,)).fetchall()} for t in CHILD_TABLES}


def prune(cur, sets: list[int], today: date) -> tuple[list[str], dict]:
    """Prune `sets` inside the caller's transaction. Returns (failed checks, what was deleted)."""
    q, bad = cur.execute, []

    def ck(ok: bool, msg: str) -> None:
        print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
        if not ok:
            bad.append(msg)

    head = {int(r[0]): r for r in q("SELECT set_id, basin, is_record, superseded_by, generator_version, notes FROM box.location_set WHERE set_id = ANY (%s)", (sets,)).fetchall()}
    missing = [s for s in sets if s not in head]
    if missing:
        raise SystemExit(f"box.location_set has no set {missing}")
    records = [s for s in sets if head[s][2]]
    if records:
        raise SystemExit(f"refused: {records} is a record set")
    ck(all(head[s][3] is not None for s in sets), f"every set to prune was superseded ({ {s: head[s][3] for s in sets} })")
    inbound = q(_INBOUND, (list(CHILD_TABLES), list(CHILD_TABLES))).fetchall()
    ck(not inbound, f"no table outside the set tables references a row to be deleted ({inbound})")
    all_sets = q("SELECT count(*) FROM box.location_set").fetchone()[0]
    rec_before = q(_FINGERPRINT).fetchone()
    loc_before = q(_LOCATIONS).fetchone()
    status_before = q("SELECT count(*) FROM curated.box_location_status s JOIN box.location_stick k ON k.set_id = s.set_id AND k.location_id = s.location_id").fetchone()[0]
    before = child_counts(q, sets)
    for t in CHILD_TABLES:
        print(f"    {t}: " + ", ".join(f"set {s} {before[t].get(s, 0):,}" for s in sets) + f"  (total {sum(before[t].values()):,})", flush=True)

    deleted = {}
    for t in CHILD_TABLES:
        q(f"DELETE FROM {t} WHERE set_id = ANY (%s)", (sets,))
        deleted[t] = cur.rowcount
    q("UPDATE box.location_set SET notes = CASE WHEN notes IS NULL OR notes = '' THEN %s ELSE notes || '; ' || %s END WHERE set_id = ANY (%s)", (note(today), note(today), sets))

    for t in CHILD_TABLES:
        ck(deleted[t] == sum(before[t].values()), f"{t}: deleted {deleted[t]:,} = the rows counted before")
    ck(all(not v for v in child_counts(q, sets).values()), "no row of a pruned set is left in the four tables")
    ck(q("SELECT count(*) FROM box.location_set").fetchone()[0] == all_sets, f"box.location_set still has its {all_sets} header rows")
    ck(q("SELECT count(*) FROM box.location_set WHERE set_id = ANY (%s) AND notes LIKE %s", (sets, "%pruned%")).fetchone()[0] == len(sets), "every pruned header carries the note")
    rec_after = q(_FINGERPRINT).fetchone()
    ck(tuple(rec_after) == tuple(rec_before), f"the record sets' stick rows are unchanged ({rec_after[0]:,} rows, same fingerprint)")
    ck(tuple(q(_LOCATIONS).fetchone()) == tuple(loc_before), f"box.location is unchanged ({loc_before[0]:,} rows, same ids and slot numbers)")
    ck(q("SELECT count(*) FROM curated.box_location_status s JOIN box.location_stick k ON k.set_id = s.set_id AND k.location_id = s.location_id").fetchone()[0] == status_before,
       f"every nightly status row still finds its record stick ({status_before:,})")
    left = q("SELECT count(*), array_agg(DISTINCT set_id ORDER BY set_id) FROM box.location_stick").fetchone()
    ck(left[0] == rec_before[0], f"box.location_stick now holds the record sets only ({left[0]:,} rows, sets {left[1]})")
    return bad, {"sets": sets, "deleted": deleted}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set-id", type=int, nargs="+", required=True)
    ap.add_argument("--go", action="store_true", help="COMMIT. Without it the transaction is rolled back.")
    a = ap.parse_args(argv)
    sets = sorted(set(a.set_id))
    conn = get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '600s'")
            cur.execute("SET LOCAL lock_timeout = '30s'")
            print(f"prune sets {sets} ({'GO' if a.go else 'rehearsal, rolled back'})", flush=True)
            bad, what = prune(cur, sets, datetime.now(tz=UTC).date())
        if bad or not a.go:
            conn.rollback()
            print(f"ROLLED BACK. {len(bad)} failed check(s)." if bad else f"ROLLED BACK (rehearsal). All checks pass. Would delete {what['deleted']}.", flush=True)
            return 1 if bad else 0
        conn.commit()
        print(f"COMMITTED. Deleted {what['deleted']}.", flush=True)
    finally:
        conn.close()
    with get_connection() as c2, c2.cursor() as cur:        # a second connection reads what was committed
        left = cur.execute("SELECT count(*) FROM box.location_stick WHERE set_id = ANY (%s)", (sets,)).fetchone()[0]
        rec = cur.execute(_FINGERPRINT).fetchone()
        print(f"second connection: {left} stick rows left in the pruned sets; record sticks {rec[0]:,}", flush=True)
        return 0 if left == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
