"""curated.box_scout_locations (sql/69): the land team's BOX locations view (Supabase).

One row per undrilled stick location that has a BOX record-run forecast AND Steven's
default-deck (wti70_hh3) econ — nothing else — for analyst_ro / QGIS (Michael 2026-10-21;
v2 trimmed to priced locations and a minimal column set). Plain VIEW: no storage, no
refresh, always current with the record run and Steven's latest push.

  --dry-run (READ ONLY, creates nothing): runs every validation below against sql/69's
     SELECT inline, inside a read-only transaction.

  (no flag) — DDL on the shared warehouse, explicit go (cheap: a view, no data built):
     1. sql/69  DROP VIEW IF EXISTS + CREATE VIEW + GRANT analyst_ro + COMMENTs.
     2. validate (same checks, on the view): rows == the record run's priced forecast
        locations on the map minus realized, unique stick_id, no blank EUR / PV10, one
        deck label, oil EUR tie-out, the per-ft lateral basis, tier tally, analyst_ro
        SELECT, bbox plan + timings.

`recreate(cur)` is the hook for every script that executes sql/22: that DROP ... CASCADE of
curated.erebor_locations drops this view too (tests/test_box_scout_locations.py enforces
the hook).

Run from repo root in the venv:
    python -m scripts.apply_box_scout_locations --dry-run
    python -m scripts.apply_box_scout_locations            # !! Supabase DDL — Michael's go
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"
SQL69 = "69_box_scout_locations.sql"
VIEW = "curated.box_scout_locations"
FORECAST = "('covered', 'covered_provisional')"
REALIZED = "('realized_drift', 'realized_phantom')"
NOT_REALIZED = ("AND el.recon_status IS DISTINCT FROM 'realized_drift' "
                "AND el.recon_status IS DISTINCT FROM 'realized_phantom'")
OIL_STREAM = ("JOIN box.pud_forecast_stream s ON s.run_id = bp.run_id "
              "AND s.location_id = bp.location_id AND s.stream = 'oil' ")
# ~1 township in Reeves County: the GIS bbox predicate the land team's tools issue
BBOX = "ST_MakeEnvelope(-103.75, 31.35, -103.65, 31.45, 4326)"


def sql69() -> str:
    return (SQL / SQL69).read_text(encoding="utf-8")


def recreate(cur) -> None:
    """Re-create the view after anything that DROP-CASCADEs curated.erebor_locations (sql/22)."""
    cur.execute(sql69())


def view_body(text: str) -> str:
    """sql/69's SELECT (the view body), for the read-only dry run."""
    m = re.search(rf"CREATE VIEW {re.escape(VIEW)} AS\n(.*?);\s*\n", text, re.DOTALL)
    if not m:
        raise RuntimeError("sql/69 view body not found")
    return m.group(1)


# per record run (one per basin since D130 / sql/70): the default deck's newest assumption set, computed once per run
_CASE = ("SELECT run_id, assumption_set_id FROM ("
         "  SELECT run_id, assumption_set_id, row_number() OVER (PARTITION BY run_id ORDER BY max(built_at) DESC NULLS LAST, "
         "         assumption_set_id DESC) AS k "
         "  FROM box_econ.box_pud_econ WHERE deck_id = 'wti70_hh3' "
         "  AND run_id IN (SELECT run_id FROM box.forecast_run WHERE is_record) GROUP BY 1, 2) x WHERE k = 1")


def _population(extra: str = "") -> str:
    """The rows the view must hold, computed independently of it: each record run's (one per basin, D130) forecast
    locations on the map (non-PDP), priced on that run's default-deck newest assumption set, minus realized."""
    return (
        "FROM box.pud_forecast bp "
        "JOIN box.forecast_run fr ON fr.run_id = bp.run_id AND fr.is_record "
        f"JOIN ({_CASE}) ec ON ec.run_id = bp.run_id "
        "JOIN curated.erebor_locations el ON el.stick_id = bp.stick_id AND el.category <> 'PDP' "
        "JOIN box_econ.box_pud_econ be ON be.run_id = bp.run_id AND be.location_id = bp.location_id "
        "AND be.deck_id = 'wti70_hh3' AND be.pv10_mm IS NOT NULL AND be.assumption_set_id = ec.assumption_set_id "
        f"{extra}"
        f"WHERE bp.coverage IN {FORECAST}"
    )


def checks(src: str) -> list[tuple[str, str]]:
    """(label, SQL) pairs over `src` (the view name, or the inline body as a subquery)."""
    return [
        ("rows", f"SELECT count(*), count(DISTINCT stick_id) FROM {src} v"),
        ("expected rows (priced forecast locations, not realized)",
         f"SELECT count(*) {_population()} {NOT_REALIZED}"),
        ("priced forecast locations left out as realized",
         f"SELECT count(*) {_population()} AND el.recon_status IN {REALIZED}"),
        ("blank oil EUR or PV10 (must be 0)",
         f"SELECT count(*) FROM {src} v WHERE v.oil_eur_bbl IS NULL OR v.pv10_mm IS NULL"),
        ("deck labels", f"SELECT econ_deck, count(*) FROM {src} v GROUP BY 1"),
        ("oil EUR view vs box (MMbbl)",
         (f"SELECT round((SELECT sum(oil_eur_bbl) FROM {src} v)::numeric / 1e6, 3), "
          f"round((SELECT sum(s.eur) {_population(OIL_STREAM)} {NOT_REALIZED})::numeric / 1e6, 3)")),
        ("per-ft basis: rows where oil EUR / per-ft differs from lateral_ft by > 1 ft",
         (f"SELECT count(*) FILTER (WHERE abs(v.oil_eur_bbl / NULLIF(v.oil_eur_bbl_per_ft, 0) - v.lateral_ft) > 1), "
          f"count(*) FROM {src} v")),
        ("tier tally", f"SELECT v.basin, v.box_tier, count(*) FROM {src} v GROUP BY 1, 2 ORDER BY 1, 2"),
        ("irr blank (informational)", f"SELECT count(*) FILTER (WHERE v.irr_pct IS NULL) FROM {src} v"),
    ]


def run_checks(cur, src: str) -> bool:
    ok = True
    res: dict[str, list] = {}
    for label, q in checks(src):
        t = time.monotonic()
        rows = cur.execute(q).fetchall()
        res[label] = rows
        print(f"    {label} ({time.monotonic() - t:.1f}s): {rows if len(rows) > 1 else rows[0]}", flush=True)

    def need(cond: bool, what: str) -> None:
        nonlocal ok
        print(f"    {'OK  ' if cond else 'FAIL'} {what}", flush=True)
        ok &= cond

    n, n_distinct = res["rows"][0]
    need(n == res["expected rows (priced forecast locations, not realized)"][0][0],
         "rows == priced record-run forecast locations on the map, minus realized")
    need(n == n_distinct, "stick_id unique")
    need(res["blank oil EUR or PV10 (must be 0)"][0][0] == 0, "every row carries oil EUR and PV10")
    need(len(res["deck labels"]) == 1, "one econ deck label")
    v_oil, b_oil = res["oil EUR view vs box (MMbbl)"][0]
    need(v_oil == b_oil, "oil EUR ties to box.pud_forecast_stream exactly")
    off, _ = res["per-ft basis: rows where oil EUR / per-ft differs from lateral_ft by > 1 ft"][0]
    print(f"    note: {off} rows where SUM(EUR)/SUM(lateral_ft) is not the stored per-ft basis", flush=True)

    plan = [r[0] for r in cur.execute(
        f"EXPLAIN SELECT stick_id, oil_eur_bbl_per_ft, pv10_mm FROM {src} v WHERE v.geom && {BBOX}").fetchall()]
    print(f"    note: bbox plan uses idx_erebor_locations_geom: "
          f"{any('idx_erebor_locations_geom' in line for line in plan)}", flush=True)
    for label, q in (("full scan", f"SELECT count(*), count(pv10_mm) FROM {src} v"),
                     ("township bbox", f"SELECT count(*), count(pv10_mm) FROM {src} v WHERE v.geom && {BBOX}")):
        t = time.monotonic()
        r = cur.execute(q).fetchone()
        print(f"    timing {label}: {time.monotonic() - t:.2f}s {r}", flush=True)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="validate sql/69's body read-only; create nothing")
    args = ap.parse_args()
    t0 = time.monotonic()
    conn = get_connection()
    try:
        if args.dry_run:
            print("[dry-run] READ ONLY: sql/69 body inline, nothing created", flush=True)
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                ok = run_checks(cur, f"({view_body(sql69())})")
            conn.rollback()
        else:
            conn.autocommit = True
            with conn.cursor() as cur:
                print(f"[1/2] sql/69: create {VIEW} + grant + comments", flush=True)
                recreate(cur)
                print("[2/2] validate", flush=True)
                ok = run_checks(cur, VIEW)
                ro = cur.execute(f"SELECT has_table_privilege('analyst_ro', '{VIEW}', 'SELECT')").fetchone()[0]
                print(f"    {'OK  ' if ro else 'FAIL'} analyst_ro can SELECT", flush=True)
                ok &= bool(ro)
    finally:
        conn.close()
    print(f"=== {'OK' if ok else 'FAILED'} in {time.monotonic() - t0:.0f}s ===", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
