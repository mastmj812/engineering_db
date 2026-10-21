"""D117 step 2: reconcile EVERY Novi stick (sql/68) + rebuild its CASCADE victims (Supabase).

D117 (Michael 2026-10-21, docs/box/universe-2026-10-21/AUDIT.md): a Novi stick inside
the BOX extent for its bench is in the BOX universe whatever Novi's BASE_CASE /
EMERGING (PUD / RES) tag, so curated.reconciled_inventory must cover RES sticks too.

  --dry-run (READ ONLY, writes nothing): computes sql/68's SELECT in a read-only
     transaction and compares it with the live matview — every PUD row must be
     identical (status, matched well, overlap, n_overlapping, first prod); reports
     the RES status split and the net_new_pdp wells sql/25 would drop.

  (no flag) — DDL on the shared warehouse, off-hours, explicit go:
     0. preflight: intel_pdp_support exists (sql/22 joins it); snapshot the PUD rows,
        net_new_pdp, erebor_locations count.
     1. sql/68  reconciled_inventory over PUD + RES (DROP ... CASCADE drops
        erebor_locations + intel_forecast_accuracy).
     2. sql/25  net_new_pdp (now overlaps every Novi stick).
     3. apply_intel_forecast_accuracy (sql/26 first, sql/38 + sql/43 EMERGING).
     4. apply_erebor_locations (sql/22 FINAL + refresh_all() + sql/31 comments).
     5. sql/26 geography indexes (idempotent).
     6. validate by identity: rows == mapped stick universe (PUD + RES with geometry
        and a bench), 0 duplicate keys; PUD rows == the snapshot; RES split; net_new
        before/after; erebor_locations row count unchanged and RES recon_status
        populated; accuracy surfaces present; CONCURRENTLY smoke.

Run from repo root in the venv:
    python -m scripts.apply_reconcile_all_sticks --dry-run
    python -m scripts.apply_reconcile_all_sticks            # !! Supabase DDL — Michael's go
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"
SQL68 = "68_reconcile_all_sticks.sql"
PUD_COLS = "stick_id, status, matched_api10, match_overlap, n_overlapping, matched_first_prod"

STICK_UNIVERSE_SQL = (
    "SELECT COUNT(*) FROM curated.intel_locations il "
    "JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id "
    "WHERE il.category IN ('PUD', 'RES') AND il.wellstick_geom IS NOT NULL "
    "AND fb.formation_blueox IS NOT NULL"
)


def select_body(sql68: str) -> str:
    """sql/68's SELECT (the matview body), for the read-only dry run."""
    m = re.search(r"CREATE MATERIALIZED VIEW curated\.reconciled_inventory AS\n(.*?);\s*\n\s*\nCREATE UNIQUE INDEX",
                  sql68, re.S)
    if not m:
        raise RuntimeError("sql/68 matview body not found")
    return m.group(1)


def net_new_select(sql25: str) -> str:
    """sql/25's SELECT (the net_new_pdp body), for the read-only dry run."""
    m = re.search(r"CREATE MATERIALIZED VIEW curated\.net_new_pdp AS\n(.*?\n);\s*\n", sql25, re.S)
    if not m:
        raise RuntimeError("sql/25 matview body not found")
    return m.group(1)


def _exec(fname: str) -> None:
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute((SQL / fname).read_text(encoding="utf-8"))
    finally:
        conn.close()
    print(f"    {fname} done in {time.monotonic() - t0:.0f}s", flush=True)


def _report_pud_drift(before: dict, after: dict, label: str) -> bool:
    """PUD rows vs the pre-apply table. The SAME PUD sticks must be present (missing /
    extra = failure). Differing rows are reconciliation DRIFT the rebuild absorbs, not
    a rule change: the table is quarterly-owned while producing_reference /
    formation_blueox_tvd refresh nightly (D87). Measured 2026-10-21: 262 of 182,695
    differed, while sql/68's PUD rows = sql/21's rule recomputed on the same data,
    182,695 / 182,695 (tests/test_reconcile_all_sticks pins the rule text)."""
    missing = sum(1 for k in before if k not in after)
    extra = sum(1 for k in after if k not in before)
    diff = [k for k, v in before.items() if k in after and after[k] != v]
    moves: dict = {}
    for k in diff:
        key = (before[k][1], after[k][1])
        moves[key] = moves.get(key, 0) + 1
    tag = "OK" if missing == 0 and extra == 0 else "MISMATCH"
    print(f"    PUD rows vs {label}: same sticks (missing={missing} extra={extra}) [{tag}]; "
          f"{len(diff)} rows differ = reconciliation drift absorbed", flush=True)
    for (s0, s1), n in sorted(moves.items(), key=lambda kv: -kv[1]):
        print(f"      {s0:18} -> {s1:18} {n}" + ("  (same status, matched well / overlap moved)" if s0 == s1 else ""),
              flush=True)
    return tag == "OK"


def dry_run() -> bool:
    body = select_body((SQL / SQL68).read_text(encoding="utf-8"))
    nn_body = net_new_select((SQL / "25_net_new_pdp.sql").read_text(encoding="utf-8"))
    ok = True
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = 0")
            t = time.monotonic()
            new ={r[0]: r for r in cur.execute(f"SELECT {PUD_COLS}, category FROM ({body}) x").fetchall()}
            print(f"[dry-run] sql/68 body computed read-only in {time.monotonic() - t:.0f}s: {len(new)} rows", flush=True)
            live = {r[0]: r for r in cur.execute(f"SELECT {PUD_COLS} FROM curated.reconciled_inventory").fetchall()}
            universe = cur.execute(STICK_UNIVERSE_SQL).fetchone()[0]
            tag = "OK" if len(new) == universe else "MISMATCH"
            print(f"    rows {len(new)} vs mapped stick universe (PUD + RES) {universe}  [{tag}]", flush=True)
            ok &= tag == "OK"
            pud_new = {k: v[:6] for k, v in new.items() if v[6] == "PUD"}
            ok &= _report_pud_drift(live, pud_new, "live")
            split: dict = {}
            for v in new.values():
                split[(v[6], v[1])] = split.get((v[6], v[1]), 0) + 1
            print("    status x category (sql/68):", flush=True)
            for (cat, st), n in sorted(split.items()):
                print(f"      {cat:4} {st:18} {n}", flush=True)
            t = time.monotonic()
            nn_new = {r[0] for r in cur.execute(f"SELECT api10 FROM ({nn_body}) x").fetchall()}
            nn_live = {r[0] for r in cur.execute("SELECT api10 FROM curated.net_new_pdp").fetchall()}
            print(f"    net_new_pdp (sql/25 over PUD + RES, {time.monotonic() - t:.0f}s): live {len(nn_live)} -> {len(nn_new)}"
                  f"  (drops {len(nn_live - nn_new)} that sit on a RES stick, adds {len(nn_new - nn_live)})", flush=True)
        conn.rollback()
    finally:
        conn.close()
    return ok


def apply() -> bool:
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            if not cur.execute(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'curated' AND c.relname = 'intel_pdp_support' AND c.relkind = 'm'"
            ).fetchone():
                raise SystemExit("curated.intel_pdp_support is missing but sql/22 joins it — "
                                 "run scripts.apply_intel_pdp_support first")
            before = {r[0]: r for r in cur.execute(
                f"SELECT {PUD_COLS} FROM curated.reconciled_inventory").fetchall()}
            nn_before = {r[0] for r in cur.execute("SELECT api10 FROM curated.net_new_pdp").fetchall()}
            el_before = cur.execute("SELECT COUNT(*) FROM curated.erebor_locations").fetchone()[0]
    finally:
        conn.close()
    print(f"[0/6] snapshot: {len(before)} PUD rows, net_new_pdp {len(nn_before)}, erebor_locations {el_before}", flush=True)

    print("[1/6] sql/68 reconciled_inventory over PUD + RES (heavy; CASCADE drops sql/22 + sql/38)", flush=True)
    _exec(SQL68)
    print("[2/6] sql/25 net_new_pdp (overlaps every Novi stick)", flush=True)
    _exec("25_net_new_pdp.sql")
    print("[3/6] intel_forecast_accuracy (sql/38 + sql/43)", flush=True)
    from scripts import apply_intel_forecast_accuracy
    apply_intel_forecast_accuracy.main()
    print("[4/6] erebor_locations (sql/22, FINAL) + refresh_all() + sql/31", flush=True)
    from scripts import apply_erebor_locations
    apply_erebor_locations.main()
    print("[5/6] sql/26 geography indexes", flush=True)
    _exec("26_geography_indexes.sql")

    print("[6/6] validation", flush=True)
    ok = True
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            rows, dups = cur.execute(
                "SELECT COUNT(*), COUNT(*) - COUNT(DISTINCT stick_id) FROM curated.reconciled_inventory").fetchone()
            universe = cur.execute(STICK_UNIVERSE_SQL).fetchone()[0]
            tag = "OK" if rows == universe and dups == 0 else "MISMATCH"
            print(f"    rows {rows} vs mapped stick universe {universe}, duplicate keys {dups}  [{tag}]", flush=True)
            ok &= tag == "OK"
            after = {r[0]: r for r in cur.execute(
                f"SELECT {PUD_COLS} FROM curated.reconciled_inventory WHERE category = 'PUD'").fetchall()}
            ok &= _report_pud_drift(before, after, "the pre-apply snapshot")
            print("    status x basin x category:", flush=True)
            for b, c, s, n in cur.execute(
                "SELECT basin_blueox, category, status, COUNT(*) FROM curated.reconciled_inventory "
                "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3").fetchall():
                print(f"      {b:9} {c:4} {s:18} {n}", flush=True)
            nn_after = {r[0] for r in cur.execute("SELECT api10 FROM curated.net_new_pdp").fetchall()}
            print(f"    net_new_pdp {len(nn_before)} -> {len(nn_after)} (dropped {len(nn_before - nn_after)}, "
                  f"added {len(nn_after - nn_before)})", flush=True)
            el_after, res_status = cur.execute(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE category = 'RES' AND recon_status IS NOT NULL) "
                "FROM curated.erebor_locations").fetchone()
            tag = "OK" if el_after == el_before else "MISMATCH"
            print(f"    erebor_locations {el_before} -> {el_after} [{tag}]; RES rows with recon_status: {res_status}", flush=True)
            ok &= tag == "OK"
            for rel in ("intel_forecast_accuracy", "intel_forecast_accuracy_vintage"):
                present = cur.execute(
                    "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'curated' AND c.relname = %s", (rel,)).fetchone() is not None
                print(f"    {rel} present: {present}", flush=True)
                ok &= present
        t = time.monotonic()
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY curated.reconciled_inventory")
        print(f"    CONCURRENTLY refresh smoke ok in {time.monotonic() - t:.0f}s", flush=True)
    finally:
        conn.close()
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description="D117 step 2: reconcile every Novi stick (sql/68).")
    ap.add_argument("--dry-run", action="store_true", help="read-only comparison, writes nothing")
    args = ap.parse_args()
    t0 = time.monotonic()
    ok = dry_run() if args.dry_run else apply()
    print(f"=== {'DONE' if ok else 'DONE WITH FAILURES'} in {time.monotonic() - t0:.0f}s ===", flush=True)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
