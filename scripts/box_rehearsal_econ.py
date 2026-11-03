"""Step 23b: SYNTHETIC placeholder econ rows in the box-rehearsal container — so the record flips can be rehearsed end to end.

    python -m scripts.box_rehearsal_econ price --run N [--decks all | --drop-deck wti70_hh3]   # container only
    python -m scripts.box_rehearsal_econ clear --run N

Writes box_econ.box_pud_econ rows for every forecast location of container run N on the decks the live record is priced on (the
16 deck ids, read from live, read-only). Every row is labelled synthetic (assumption_set_id / build_id / schema_version =
'synthetic-23b', unpriced_reason says so) and carries one constant placeholder (pv10_mm = 1.0) so erebor's econ screens and
curated.box_scout_locations have something to show. NOTHING is computed: no price deck, no LOE, no capex, no economic limit (the
no-economics scope rule). Refuses any database but the container (localhost:5437); Steven's real rows stay live-only.
"""

from __future__ import annotations

import argparse
import sys

from etl.db import get_connection
from scripts import box_rehearsal as reh

LABEL = "synthetic-23b"
REASON = "SYNTHETIC 23b rehearsal placeholder (container only; not Steven's econ; nothing computed)"
PLACEHOLDER_PV10_MM = 1.0


def live_decks() -> list[str]:
    """The deck ids the live Delaware record is priced on (read-only)."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SET TRANSACTION READ ONLY")
        rows = cur.execute("SELECT DISTINCT e.deck_id FROM box_econ.box_pud_econ e JOIN box.forecast_run r ON r.run_id = e.run_id "
                           "WHERE r.is_record ORDER BY 1").fetchall()
        conn.rollback()
    return [r[0] for r in rows]


def _container() -> object:
    conn = reh._box_conn()
    port = conn.info.port
    if conn.info.host not in ("localhost", "127.0.0.1", "::1") or port != reh.PORT:
        conn.close()
        raise SystemExit(f"REFUSING: {conn.info.host}:{port} is not the rehearsal container")
    return conn


def cmd_price(a: argparse.Namespace) -> int:
    decks = [d for d in live_decks() if d != a.drop_deck]
    conn = _container()
    try:
        with conn.cursor() as cur:  # type: ignore[attr-defined]
            n = 0
            for d in decks:
                cur.execute(
                    "INSERT INTO box_econ.box_pud_econ (run_id, location_id, coverage, deck_id, assumption_set_id, downtime_basis, pv10_mm, "
                    "unpriced_reason, build_id, schema_version, built_at) "
                    "SELECT pf.run_id, pf.location_id, pf.coverage, %(d)s, %(l)s, 'steven_downtime_factor', %(pv)s, %(r)s, %(l)s, %(l)s, now() "
                    "FROM box.pud_forecast pf WHERE pf.run_id = %(run)s AND pf.coverage IN ('covered', 'covered_provisional') "
                    "ON CONFLICT DO NOTHING",
                    {"d": d, "l": LABEL, "pv": PLACEHOLDER_PV10_MM, "r": REASON, "run": a.run})
                n += cur.rowcount
        conn.commit()  # type: ignore[attr-defined]
    finally:
        conn.close()  # type: ignore[attr-defined]
    print(f"container run {a.run}: {n:,} synthetic econ rows on {len(decks)} decks" + (f" (dropped {a.drop_deck})" if a.drop_deck else ""))
    return 0


def cmd_clear(a: argparse.Namespace) -> int:
    conn = _container()
    try:
        with conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute("DELETE FROM box_econ.box_pud_econ WHERE run_id = %s AND build_id = %s", (a.run, LABEL))
            n = cur.rowcount
        conn.commit()  # type: ignore[attr-defined]
    finally:
        conn.close()  # type: ignore[attr-defined]
    print(f"container run {a.run}: {n:,} synthetic econ rows removed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("price")
    p.add_argument("--run", type=int, required=True)
    p.add_argument("--drop-deck", default=None, help="leave one deck unpriced (the partial-pricing refusal check)")
    c = sub.add_parser("clear")
    c.add_argument("--run", type=int, required=True)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    return {"price": cmd_price, "clear": cmd_clear}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
