"""Apply sql/79: box.pud_forecast accepts a run on BOX sticks (three CHECK constraints widened; no row changes).

One transaction with checks; ROLLBACK unless --go. Live is an explicit go.

    python -m scripts.apply_box_pud_forecast_box_sticks          # rehearsal
    python -m scripts.apply_box_pud_forecast_box_sticks --go
"""
from __future__ import annotations

import argparse
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql" / "79_box_pud_forecast_box_sticks.sql"
NEW = ("box_pud_forecast_recon_status_ck", "box_pud_forecast_spacing_source_ck", "box_pud_forecast_conflict_ck")
OLD = ("pud_forecast_recon_status_check", "pud_forecast_spacing_source_check")
_FINGERPRINT = ("SELECT count(*), md5(string_agg(run_id::text || ':' || location_id::text || ':' || recon_status || ':' || COALESCE(spacing_source, '') "
                "|| ':' || coverage, ',' ORDER BY run_id, location_id)) FROM box.pud_forecast")
_DEFS = ("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'box.pud_forecast'::regclass AND contype = 'c' "
         "AND (conname = ANY (%s) OR conname = ANY (%s))")


def apply(cur) -> list[str]:
    q, bad = cur.execute, []

    def ck(ok: bool, msg: str) -> None:
        print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
        if not ok:
            bad.append(msg)

    before = q(_FINGERPRINT).fetchone()
    runs = q("SELECT count(*), count(*) FILTER (WHERE is_record) FROM box.forecast_run").fetchone()
    q(SQL.read_text(encoding="utf-8"))
    defs = dict(q(_DEFS, (list(NEW), list(OLD))).fetchall())
    ck(set(defs) == set(NEW), f"the three named constraints exist and the two auto-named ones are gone ({sorted(defs)})")
    for word, con in (("'crowded'", NEW[0]), ("'permitted'", NEW[0]), ("'remaining_pud'", NEW[0]), ("'generator'", NEW[1]), ("'default_880'", NEW[1]),
                      ("'crowded'", NEW[2])):
        ck(word in defs.get(con, ""), f"{con} admits {word}")
    ck(all(q("SELECT convalidated FROM pg_constraint WHERE conname = %s AND conrelid = 'box.pud_forecast'::regclass", (c,)).fetchone()[0] for c in NEW),
       "all three are validated against the stored rows")
    ck(tuple(q(_FINGERPRINT).fetchone()) == tuple(before), f"no row of box.pud_forecast changed ({before[0]:,} rows, same fingerprint)")
    ck(tuple(q("SELECT count(*), count(*) FILTER (WHERE is_record) FROM box.forecast_run").fetchone()) == tuple(runs), f"runs and records unchanged ({tuple(runs)})")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--go", action="store_true", help="COMMIT. Without it the transaction is rolled back.")
    a = ap.parse_args(argv)
    conn = get_connection()
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '30s'")
            print(f"sql/79 ({'GO' if a.go else 'rehearsal, rolled back'})", flush=True)
            bad = apply(cur)
        if bad or not a.go:
            conn.rollback()
            print(f"ROLLED BACK. {len(bad)} failed check(s)." if bad else "ROLLED BACK (rehearsal). All checks pass.", flush=True)
            return 1 if bad else 0
        conn.commit()
        print("COMMITTED.", flush=True)
    finally:
        conn.close()
    with get_connection() as c2, c2.cursor() as cur:
        n = cur.execute("SELECT count(*) FROM pg_constraint WHERE conrelid = 'box.pud_forecast'::regclass AND conname = ANY (%s)", (list(NEW),)).fetchone()[0]
        print(f"second connection: {n} of {len(NEW)} constraints present", flush=True)
        return 0 if n == len(NEW) else 1


if __name__ == "__main__":
    raise SystemExit(main())
