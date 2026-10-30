"""Load ref.formation_tag_overrides (sql/44) and carry the tags down the chain
(Supabase oilgas). Two modes; one must be named:

--refresh  (a SEED change — the normal case; sql/44 header "edit loop")
    1. reload the seed in ONE transaction (TRUNCATE + COPY + COMMENT), so the
       override table is never seen empty;
    2. REFRESH MATERIALIZED VIEW CONCURRENTLY every matview below
       curated.formation_blueox, in dependency order (CHAIN), erebor_locations
       last. Nothing is dropped, every object stays readable, no definition is
       re-created from the repo. ~55-60 min, almost all of it intel_pdp_support.
    Five CHAIN members are quarterly-owned (bench_reference,
    intel_formation_blueox, reconciled_inventory, net_new_pdp,
    intel_pdp_support): the nightly never refreshes them, so a seed reload left
    to the nightly would leave PDP tags and PUD/RES stick tags out of step.
    Before writing, the live pg_depend graph is checked against CHAIN (same
    matview set, order respects every edge) and a running nightly refuses the
    run. Afterwards: every override landed; every PDP tag change is an override
    row; stick-tag and recon-status moves are reported.
    --dry-run does the checks and the seed diff read-only and writes nothing.

--rebuild  (a sql/16 LOGIC change)
    Re-runs sql/16 in full. ⚠ sql/16 is DROP ... CASCADE: it drops every CHAIN
    matview plus wells_enriched / dev_scenario / box_scout_locations, and this
    script then STOPS. Run it INSIDE a chain-rebuild window, followed by the
    quarterly-skill tail:
        apply_intel_formation_blueox -> apply_reconciled_inventory -> sql/25
        (net_new_pdp; sql/22 reads it) -> apply_intel_pdp_support ->
        apply_intel_forecast_accuracy -> apply_erebor_locations (FINAL; re-applies
        sql/31) -> sql/26
    Standalone use outside a window leaves the apps dark until that tail runs.

Either mode: run outside the nightly (it lands ~15:00-17:30 UTC, not at the
11:15 cron), then regenerate the data dictionary.

Run from repo root in the venv:
    python -m scripts.apply_formation_tag_overrides --refresh --dry-run
    python -m scripts.apply_formation_tag_overrides --refresh
"""

from __future__ import annotations

import argparse
import csv
import time
from collections import Counter
from pathlib import Path

from etl.db import get_connection

REPO = Path(__file__).resolve().parent.parent
SQL = REPO / "sql"
SEED = REPO / "seeds" / "formation_tag_overrides.csv"
SQL44 = SQL / "44_formation_tag_overrides.sql"
TABLE = "ref.formation_tag_overrides"
COLUMNS = "api10, corrected_code, was, note"
ROOT = "curated.formation_blueox"

# Every matview below curated.formation_blueox, in refresh order (live pg_depend,
# 2026-10-28). Checked against the live graph before every --refresh run.
CHAIN: tuple[str, ...] = (
    "curated.formation_blueox",
    "curated.bench_reference",
    "curated.producing_reference",
    "curated.formation_blueox_tvd",
    "curated.intel_formation_blueox",
    "curated.codev_context",
    "curated.reconciled_inventory",
    "curated.net_new_pdp",
    "curated.intel_forecast_accuracy_vintage",
    "curated.intel_pdp_support",
    "curated.intel_forecast_accuracy",
    "curated.erebor_locations",
)

# Rule-dependency closure of ROOT: (child, child relkind, parent, parent relkind)
# for every rewrite edge whose child and parent both sit in the closure.
_DEPS_SQL = """
WITH RECURSIVE dep AS (
    SELECT %(root)s::regclass::oid AS oid
    UNION
    SELECT r.ev_class
    FROM dep d
    JOIN pg_depend pd ON pd.refobjid = d.oid AND pd.classid = 'pg_rewrite'::regclass
    JOIN pg_rewrite r ON r.oid = pd.objid
    WHERE r.ev_class <> d.oid
)
SELECT DISTINCT r.ev_class::regclass::text, c.relkind::text,
                pd.refobjid::regclass::text, p.relkind::text
FROM pg_depend pd
JOIN pg_rewrite r ON r.oid = pd.objid
JOIN pg_class c ON c.oid = r.ev_class
JOIN pg_class p ON p.oid = pd.refobjid
WHERE pd.classid = 'pg_rewrite'::regclass
  AND r.ev_class IN (SELECT oid FROM dep)
  AND pd.refobjid IN (SELECT oid FROM dep)
  AND pd.refobjid <> r.ev_class
"""


def split_copy(sql_text: str) -> tuple[str, str]:
    """sql/44 around its one psql \\copy meta-command -> (before, after)."""
    lines = sql_text.splitlines()
    idx = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("\\copy")]
    if len(idx) != 1:
        raise ValueError(f"expected exactly one \\copy line, found {len(idx)}")
    return "\n".join(lines[:idx[0]]), "\n".join(lines[idx[0] + 1:])


def matview_parents(edges, root: str = ROOT) -> dict[str, set[str]]:
    """Collapse plain views out of the rewrite graph: each matview -> the
    matviews it reads, directly or through views. `edges` are
    (child, child_kind, parent, parent_kind) rows from _DEPS_SQL."""
    kind: dict[str, str] = {}
    direct: dict[str, set[str]] = {}
    for child, ck, parent, pk in edges:
        kind[child], kind[parent] = ck, pk
        direct.setdefault(child, set()).add(parent)
    kind.setdefault(root, "m")

    def mv_ancestors(obj: str, seen: set[str]) -> set[str]:
        out: set[str] = set()
        for p in direct.get(obj, ()):
            if p in seen:
                continue
            seen.add(p)
            out |= {p} if kind[p] == "m" else mv_ancestors(p, seen)
        return out

    return {o: mv_ancestors(o, set()) for o, k in kind.items() if k == "m"}


def chain_problems(order, parents: dict[str, set[str]]) -> list[str]:
    """Why `order` is not a valid refresh of the live graph (empty = valid)."""
    out = [f"live matview missing from CHAIN: {m}" for m in sorted(set(parents) - set(order))]
    out += [f"CHAIN member not below {ROOT} live: {m}" for m in order if m not in parents]
    pos = {m: i for i, m in enumerate(order)}
    for child, ps in sorted(parents.items()):
        for p in sorted(ps):
            if child in pos and p in pos and pos[p] > pos[child]:
                out.append(f"{child} is refreshed before its parent {p}")
    return out


def seed_diff(seed_rows, live_rows) -> dict[str, list[str]]:
    """api10s the reload adds, changes (code or note) and removes."""
    seed = {r["api10"]: (r["corrected_code"], r["was"], r["note"]) for r in seed_rows}
    live = {r[0]: tuple(r[1:]) for r in live_rows}
    return {
        "add": sorted(seed.keys() - live.keys()),
        "change": sorted(a for a in seed.keys() & live.keys() if seed[a] != live[a]),
        "remove": sorted(live.keys() - seed.keys()),
    }


def tag_moves(before: dict, after: dict) -> Counter:
    """(was, now) counts over keys present in both snapshots whose value moved."""
    return Counter((before[k], after[k]) for k in before.keys() & after.keys()
                   if before[k] != after[k])


def _load_seed(cur, expected: int) -> None:
    before, after = split_copy(SQL44.read_text(encoding="utf-8"))
    cur.execute(before)
    with cur.copy(
        f"COPY {TABLE} ({COLUMNS}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    ) as cp, open(SEED, "rb") as fh:
        while data := fh.read(65536):
            cp.write(data)
    cur.execute(after)
    n = cur.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    print(f"    loaded {n} rows (csv {expected}) [{'OK' if n == expected else 'MISMATCH'}]",
          flush=True)
    if n != expected:
        raise SystemExit(f"seed row count {n} != csv {expected}")


def _verify_overrides(cur) -> int:
    rows = cur.execute(f"""
        SELECT o.api10, o.corrected_code, fb.formation_blueox, fb.formation_blueox_source
        FROM {TABLE} o
        LEFT JOIN curated.formation_blueox fb USING (api10)
    """).fetchall()
    bad = [r for r in rows if r[2] != r[1] or r[3] != "ratified_override"]
    print(f"    overrides applied: {len(rows) - len(bad)}/{len(rows)}"
          f"  [{'OK' if not bad else 'MISMATCH'}]", flush=True)
    for api, want, got, src in bad:
        print(f"      {api}: want {want}, got {got} (source {src})", flush=True)
    return len(bad)


def _snapshot(cur) -> dict:
    return {
        "pdp": dict(cur.execute(
            "SELECT api10, formation_blueox FROM curated.formation_blueox").fetchall()),
        "stick": {s: (b, t) for s, b, t in cur.execute(
            "SELECT stick_id, basin_blueox, formation_blueox "
            "FROM curated.intel_formation_blueox").fetchall()},
        "recon": dict(cur.execute(
            "SELECT stick_id, status FROM curated.reconciled_inventory").fetchall()),
        "counts": {mv: cur.execute(f"SELECT COUNT(*) FROM {mv}").fetchone()[0]
                   for mv in CHAIN},
    }


def _preflight(cur) -> list[str]:
    """Live checks that must pass before any write. Returns problems."""
    problems = chain_problems(CHAIN, matview_parents(cur.execute(_DEPS_SQL, {"root": ROOT}).fetchall()))
    running = cur.execute("""
        SELECT source, table_name, run_started_at FROM meta.etl_log
        WHERE status = 'running' AND run_started_at > now() - interval '6 hours'
    """).fetchall()
    problems += [f"ETL run in progress: {s}/{t} since {ts:%H:%M} UTC" for s, t, ts in running]
    return problems


def refresh(dry_run: bool) -> None:
    with open(SEED, encoding="utf-8") as fh:
        expected = list(csv.DictReader(fh))
    t0 = time.monotonic()
    conn = get_connection()
    try:
        # A dry run is one read-only transaction (rolled back on close); the real
        # run is autocommit because REFRESH CONCURRENTLY can't run in a block.
        conn.autocommit = not dry_run
        conn.read_only = dry_run
        with conn.cursor() as cur:
            print("[1/5] preflight: live dependency graph vs CHAIN, running ETL", flush=True)
            problems = _preflight(cur)
            for p in problems:
                print(f"    FAIL: {p}", flush=True)
            if problems:
                raise SystemExit("preflight failed — nothing written")
            print(f"    OK: {len(CHAIN)} matviews, order respects every live edge", flush=True)

            live = cur.execute(f"SELECT api10, corrected_code, was, note FROM {TABLE}").fetchall()
            diff = seed_diff(expected, live)
            print(f"    seed {len(expected)} rows vs live {len(live)}: add {len(diff['add'])}, "
                  f"change {len(diff['change'])}, remove {len(diff['remove'])}", flush=True)
            # Report-only: vendors revise tags in place, so a row's `was` (the tag when MM
            # ratified it) can drift from the live crosswalk tag before the apply.
            tags = dict(cur.execute(
                "SELECT api10, formation_blueox FROM curated.formation_blueox WHERE api10 = ANY(%s)",
                ([r["api10"] for r in expected],)).fetchall())
            drift = [r for r in expected if r["api10"] in tags and tags[r["api10"]] != r["was"]
                     and r["api10"] not in {x[0] for x in live}]
            agree = sum(tags[r["api10"]] == r["corrected_code"] for r in drift)
            print(f"    new rows whose `was` != live tag: {len(drift)} ({agree} already carry the corrected "
                  f"tag, {len(drift) - agree} carry another)", flush=True)
            for r in drift:
                if tags[r["api10"]] != r["corrected_code"]:
                    print(f"      {r['api10']}: was {r['was']}, live {tags[r['api10']]}, "
                          f"seed {r['corrected_code']}", flush=True)
            if dry_run:
                print("=== DRY RUN — nothing written. Refresh order: "
                      + " -> ".join(m.split(".")[1] for m in CHAIN) + " ===", flush=True)
                return

            print("[2/5] snapshot tags before (PDP, PUD/RES sticks, recon status, row counts)",
                  flush=True)
            before = _snapshot(cur)

            print(f"[3/5] reload {TABLE} in one transaction ({len(expected)} rows, sql/44)",
                  flush=True)
            with conn.transaction():
                _load_seed(cur, len(expected))

            print(f"[4/5] REFRESH CONCURRENTLY x{len(CHAIN)}", flush=True)
            for i, mv in enumerate(CHAIN, 1):
                t = time.monotonic()
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}")
                print(f"    ({i}/{len(CHAIN)}) {mv}  {time.monotonic() - t:.0f}s", flush=True)

            print("[5/5] verify", flush=True)
            n_bad = _verify_overrides(cur)
            after = _snapshot(cur)
            ovr = {r["api10"] for r in expected}
            pdp_moved = {k for k in before["pdp"].keys() & after["pdp"].keys()
                         if before["pdp"][k] != after["pdp"][k]}
            stray = sorted(pdp_moved - ovr)
            print(f"    PDP tags moved: {len(pdp_moved)}; not an override row: {len(stray)}"
                  f"  [{'OK' if not stray else 'CHECK'}]", flush=True)
            for a in stray[:20]:
                print(f"      {a}: {before['pdp'][a]} -> {after['pdp'][a]}", flush=True)
            moves = tag_moves(before["stick"], after["stick"])
            print(f"    PUD/RES stick tags moved: {sum(moves.values())}", flush=True)
            for ((basin, was), (_, now)), n in moves.most_common(20):
                print(f"      {basin}: {was} -> {now}  {n}", flush=True)
            recon = tag_moves(before["recon"], after["recon"])
            print(f"    reconciled_inventory status moves: {sum(recon.values())}", flush=True)
            for (s0, s1), n in recon.most_common(10):
                print(f"      {s0} -> {s1}  {n}", flush=True)
            print("    row counts before -> after:", flush=True)
            for mv in CHAIN:
                b, a = before["counts"][mv], after["counts"][mv]
                print(f"      {mv:42s} {b:>9,} -> {a:>9,}{'' if a == b else '  (changed)'}",
                      flush=True)
            if n_bad or stray:
                raise SystemExit("verification failed — see above")
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t0:.0f}s — now regenerate the data dictionary ===",
          flush=True)


def rebuild() -> None:
    with open(SEED, encoding="utf-8") as fh:
        expected = list(csv.DictReader(fh))
    t0 = time.monotonic()
    conn = get_connection()
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            print(f"[1/3] load {TABLE} ({len(expected)} rows, sql/44)", flush=True)
            with conn.transaction():
                _load_seed(cur, len(expected))

            print("[2/3] rebuild curated.formation_blueox (sql/16, DROP CASCADE — see header)", flush=True)
            t = time.monotonic()
            cur.execute((SQL / "16_formation_blueox.sql").read_text(encoding="utf-8"))
            print(f"    built in {time.monotonic() - t:.0f}s", flush=True)

            print("[3/3] verify every override landed", flush=True)
            _verify_overrides(cur)
            n_src = cur.execute(
                "SELECT COUNT(*) FROM curated.formation_blueox "
                "WHERE formation_blueox_source = 'ratified_override'"
            ).fetchone()[0]
            print(f"    rows with source=ratified_override: {n_src} (identity: = override rows "
                  f"whose api10 exists in curated.wells)", flush=True)
    finally:
        conn.close()
    print(f"=== DONE in {time.monotonic() - t0:.0f}s — now run the downstream chain "
          f"(see module docstring) ===", flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--refresh", action="store_true",
                      help="seed change: reload + REFRESH CONCURRENTLY down the chain")
    mode.add_argument("--rebuild", action="store_true",
                      help="sql/16 logic change: DROP CASCADE re-create (chain-rebuild window only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --refresh: preflight + seed diff, read-only")
    a = ap.parse_args(argv)
    if a.dry_run and not a.refresh:
        ap.error("--dry-run goes with --refresh")
    if a.refresh:
        refresh(a.dry_run)
    else:
        rebuild()


if __name__ == "__main__":
    main()
