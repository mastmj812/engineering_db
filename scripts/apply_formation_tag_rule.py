"""Apply the formation-tag rule's warehouse objects (sql/72) and flip it on or off — WAREHOUSE_STEP.md W3 / W5.

Every mode needs Michael's explicit go and runs OUTSIDE the nightly (05:00 CT dispatch, done ~06:30 CT; a late backstop
can run in the afternoon: `gh run list --workflow etl-nightly.yml`). Each mode refuses while an ETL run is in progress.

--structure  (W3: off-hours chain-rebuild window; erebor + narvi dark ~2 h; anduin unaffected)
    1. snapshot formation_blueox + wells_enriched tags;
    2. sql/72 (new tables, switch row inserted OFF);
    3. seeds, one transaction each: policy, classes, depth exclusions, overrides (human calls);
    4. sql/16 (rewritten: override > rule > crosswalk; DROP ... CASCADE), then the chain tail, in order:
         apply_intel_formation_blueox -> apply_reconciled_inventory (re-runs sql/20, sql/23 with its new guards,
         wells_enriched, 47, 50, 21) -> sql/25 -> apply_intel_pdp_support -> apply_intel_forecast_accuracy
         -> apply_erebor_locations (FINAL, re-applies sql/31) -> sql/26 -> sql/31;
    5. verify with the switch OFF: formation_blueox differs from the snapshot only on the override seed diff, and
       wells_enriched only there plus wells where sql/23 no longer flips a human call.
--seeds      reload the four seeds only (a reviewed seed PR), then REFRESH CONCURRENTLY down the chain.
--cutover    (W5) switch ON + REFRESH CONCURRENTLY down the chain (~1 h, apps stay up); verify.
--rollback   switch OFF + the same refresh.
--dry-run    with any mode: preflight, seed diffs and the plan, read-only.

    python -m scripts.apply_formation_tag_rule --structure --dry-run
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from etl.db import get_connection
from scripts import apply_formation_tag_overrides as afo
from scripts import tag_rule_seeds as seeds

REPO = Path(__file__).resolve().parent.parent
SQL = REPO / "sql"
PY = sys.executable

# (table, seed, columns) — overrides go through sql/44's loader.
SEED_TABLES: list[tuple[str, Path, str]] = [
    ("ref.formation_tag_policy", seeds.POLICY,
     "policy_version, basin, novi_raw, env_raw, u_novi, u_env, decided, novi_share, winner"),
    ("ref.formation_tag_class", seeds.CLASSES,
     "step, basin, from_code, to_code, basis, decision, agree, judged, class_wells, card_set"),
    ("ref.formation_tag_depth_exclusions", seeds.EXCLUSIONS, "api10, depth_ft, depth_source, tag_kept, card, note"),
]

TAIL: list[list[str]] = [
    [PY, "-m", "scripts.apply_intel_formation_blueox"],
    [PY, "-m", "scripts.apply_reconciled_inventory"],
    [PY, "-c", "from scripts.load_intel_sf import run_sql_file; run_sql_file('25_net_new_pdp.sql')"],
    [PY, "-m", "scripts.apply_intel_pdp_support"],
    [PY, "-m", "scripts.apply_intel_forecast_accuracy"],
    [PY, "-m", "scripts.apply_erebor_locations"],
    [PY, "-c", "from scripts.load_intel_sf import run_sql_file; run_sql_file('26_geography_indexes.sql')"],
    [PY, "-c", "from scripts.load_intel_sf import run_sql_file; run_sql_file('31_comments.sql')"],
]

_TAGS_SQL = {
    "blueox": "SELECT api10, formation_blueox, formation_blueox_source FROM curated.formation_blueox",
    "enriched": "SELECT api10, formation_blueox, formation_blueox_source FROM curated.wells_enriched",
}


def _p(msg: str) -> None:
    print(msg, flush=True)


def _rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def tag_diff(before: dict, after: dict) -> dict[str, set[str]]:
    """api10s whose (code, source) moved, appeared or vanished."""
    return {"moved": {k for k in before.keys() & after.keys() if before[k] != after[k]},
            "added": set(after) - set(before), "removed": set(before) - set(after)}


def unexplained(diff: dict[str, set[str]], allowed: set[str]) -> set[str]:
    return (diff["moved"] | diff["added"] | diff["removed"]) - allowed


def _snapshot(cur, which: str) -> dict:
    return {a: (c, s) for a, c, s in cur.execute(_TAGS_SQL[which]).fetchall()}


def _preflight(cur) -> list[str]:
    running = cur.execute("""
        SELECT source, table_name, run_started_at FROM meta.etl_log
        WHERE status = 'running' AND run_started_at > now() - interval '6 hours'
    """).fetchall()
    return [f"ETL run in progress: {s}/{t} since {ts:%H:%M} UTC" for s, t, ts in running]


def load_seeds(cur) -> None:
    """The three rule seeds (one transaction each) and the overrides (sql/44's loader, one transaction)."""
    conn = cur.connection
    for table, path, cols in SEED_TABLES:
        n_csv = len(_rows(path))
        with conn.transaction():
            cur.execute(f"TRUNCATE {table}")
            with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)") as cp, open(path, "rb") as fh:
                while chunk := fh.read(65536):
                    cp.write(chunk)
            n = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if n != n_csv:
                raise SystemExit(f"{table}: loaded {n} rows, csv {n_csv} - rolled back")
        _p(f"    {table}: {n} rows")
    with conn.transaction():
        afo._load_seed(cur, len(_rows(afo.SEED)))


def _seed_report(cur) -> set[str]:
    """Print the override seed diff; return every api10 it touches."""
    live = cur.execute(f"SELECT api10, corrected_code, was, note FROM {afo.TABLE}").fetchall()
    diff = afo.seed_diff(_rows(afo.SEED), live)
    _p(f"    overrides: add {len(diff['add'])}, change {len(diff['change'])}, remove {len(diff['remove'])}")
    for table, path, _ in SEED_TABLES:
        exists = cur.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0] is not None
        n_live = cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0] if exists else "absent"
        _p(f"    {table}: seed {len(_rows(path))} rows, live {n_live}")
    return set(diff["add"]) | set(diff["change"]) | set(diff["remove"])


def structure(dry_run: bool) -> None:
    conn = get_connection()
    t0 = time.monotonic()
    try:
        conn.autocommit = not dry_run
        conn.read_only = dry_run
        with conn.cursor() as cur:
            _p("[1/5] preflight + seed diff")
            problems = _preflight(cur)
            for p in problems:
                _p(f"    FAIL: {p}")
            if problems:
                raise SystemExit("preflight failed - nothing written")
            touched = _seed_report(cur)
            if dry_run:
                _p("=== DRY RUN - nothing written. Plan: sql/72 -> seeds -> sql/16 (DROP CASCADE) -> tail:")
                for cmd in TAIL:
                    _p(f"      {' '.join(cmd[1:])}")
                _p("    -> verify (switch OFF) ===")
                return
            before = {k: _snapshot(cur, k) for k in _TAGS_SQL}
            human_flipped = {a for (a,) in cur.execute(
                "SELECT t.api10 FROM curated.formation_blueox_tvd t JOIN ref.formation_tag_overrides o USING (api10) "
                "WHERE t.corrected").fetchall()}
            _p("[2/5] sql/72 (tables, switch OFF)")
            cur.execute((SQL / "72_formation_tag_rule.sql").read_text(encoding="utf-8"))
            _p("[3/5] seeds")
            load_seeds(cur)
            new_human = {a for (a,) in cur.execute(f"SELECT api10 FROM {afo.TABLE}").fetchall()}
            _p("[4/5] sql/16 (DROP ... CASCADE) + chain tail")
            t = time.monotonic()
            cur.execute((SQL / "16_formation_blueox.sql").read_text(encoding="utf-8"))
            _p(f"    sql/16 built in {time.monotonic() - t:.0f}s")
        for cmd in TAIL:
            t = time.monotonic()
            _p(f"    $ {' '.join(cmd[1:])}")
            subprocess.run(cmd, cwd=REPO, check=True)
            _p(f"      done in {time.monotonic() - t:.0f}s")
        with conn.cursor() as cur:
            _p("[5/5] verify (switch OFF: tags move only where the seeds say)")
            sw = cur.execute("SELECT use_rule FROM ref.formation_tag_switch").fetchone()[0]
            after = {k: _snapshot(cur, k) for k in _TAGS_SQL}
            # wells_enriched may also move where sql/23 no longer flips a (new) human call
            allowed = {"blueox": touched, "enriched": touched | (human_flipped & new_human) | {
                a for a, (_, s) in before["enriched"].items() if s == "tvd_corrected" and a in new_human}}
            bad = 0
            for k in _TAGS_SQL:
                d = tag_diff(before[k], after[k])
                u = unexplained(d, allowed[k])
                _p(f"    {k}: moved {len(d['moved'])}, added {len(d['added'])}, removed {len(d['removed'])}; "
                   f"unexplained {len(u)}  [{'OK' if not u else 'CHECK'}]")
                for a in sorted(u)[:20]:
                    _p(f"      {a}: {before[k].get(a)} -> {after[k].get(a)}")
                bad += len(u)
            _p(f"    switch use_rule = {sw}  [{'OK' if sw is False else 'CHECK'}]")
            if bad or sw is not False:
                raise SystemExit("verification needs a look - see above")
    finally:
        conn.close()
    _p(f"=== DONE in {time.monotonic() - t0:.0f}s - regenerate the data dictionary; the nightly now runs the rule in shadow ===")


def _chain_refresh(cur) -> None:
    problems = afo.chain_problems(afo.CHAIN, afo.matview_parents(cur.execute(afo._DEPS_SQL, {"root": afo.ROOT}).fetchall()))
    if problems:
        raise SystemExit("live dependency graph != CHAIN: " + "; ".join(problems))
    for i, mv in enumerate(afo.CHAIN, 1):
        t = time.monotonic()
        cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv}")
        _p(f"    ({i}/{len(afo.CHAIN)}) {mv}  {time.monotonic() - t:.0f}s")


_EXPECTED_RULE_SQL = """
SELECT count(*) FROM curated.formation_tag_rule rr
JOIN curated.wells w USING (api10)
LEFT JOIN ref.formation_tag_overrides o USING (api10)
WHERE rr.applied AND o.api10 IS NULL
  AND rr.novi_raw IS NOT DISTINCT FROM w.formation AND rr.env_raw IS NOT DISTINCT FROM w.env_interval
  AND ((rr.tvd_ft IS NULL AND w.tvd_ft IS NULL) OR abs(rr.tvd_ft - w.tvd_ft::numeric) <= 0.5)
  AND rr.planned = COALESCE(w.directional_survey_is_planned, FALSE)
"""


def switch(on: bool, dry_run: bool, also_seeds: bool = False) -> None:
    conn = get_connection()
    t0 = time.monotonic()
    try:
        conn.autocommit = not dry_run
        conn.read_only = dry_run
        with conn.cursor() as cur:
            _p("[1/4] preflight")
            problems = _preflight(cur)
            last = cur.execute("SELECT status, finished_at, judged, applied FROM meta.formation_tag_run "
                               "ORDER BY run_id DESC LIMIT 1").fetchone()
            _p(f"    last rule run: {last}")
            if on and (last is None or last[0] != "written"):
                problems.append("the last tag-rule run did not write - run `python -m etl.tag_rule --write` first")
            for p in problems:
                _p(f"    FAIL: {p}")
            if problems:
                raise SystemExit("preflight failed - nothing written")
            if also_seeds:
                _seed_report(cur)
            _p(f"    rule rows that would apply now (applied, inputs match, no human call): "
               f"{cur.execute(_EXPECTED_RULE_SQL).fetchone()[0]}")
            if dry_run:
                _p("=== DRY RUN - nothing written ===")
                return
            before = afo._snapshot(cur)
            if also_seeds:
                _p("[2/4] reload seeds")
                load_seeds(cur)
            else:
                _p(f"[2/4] switch use_rule -> {on}")
                with conn.transaction():
                    cur.execute("UPDATE ref.formation_tag_switch SET use_rule = %s, changed_at = now(), note = %s",
                                (on, f"apply_formation_tag_rule --{'cutover' if on else 'rollback'}"))
            _p(f"[3/4] REFRESH CONCURRENTLY x{len(afo.CHAIN)}")
            _chain_refresh(cur)
            _p("[4/4] verify")
            n_rule = cur.execute("SELECT count(*) FROM curated.formation_blueox "
                                 "WHERE formation_blueox_source LIKE 'rule_step%'").fetchone()[0]
            sw = cur.execute("SELECT use_rule FROM ref.formation_tag_switch").fetchone()[0]
            want = cur.execute(_EXPECTED_RULE_SQL).fetchone()[0] if sw else 0
            _p(f"    formation_blueox rule rows: {n_rule} (expected {want})  [{'OK' if n_rule == want else 'CHECK'}]")
            bad = afo._verify_overrides(cur) + (n_rule != want)
            if sw:
                n23 = cur.execute("SELECT count(*) FROM curated.formation_blueox_tvd WHERE corrected").fetchone()[0]
                _p(f"    sql/23 flips with the switch on: {n23}  [{'OK' if n23 == 0 else 'CHECK'}]")
                bad += n23 != 0
            after = afo._snapshot(cur)
            moved = afo.tag_moves(before["pdp"], after["pdp"])
            _p(f"    PDP tags moved: {sum(moved.values())}")
            for (a, b), n in Counter(moved).most_common(15):
                _p(f"      {a} -> {b}  {n}")
            sticks = afo.tag_moves(before["stick"], after["stick"])
            _p(f"    PUD/RES stick tags moved: {sum(sticks.values())}")
            recon = afo.tag_moves(before["recon"], after["recon"])
            _p(f"    reconciled_inventory status moves: {sum(recon.values())}")
            for (s0, s1), n in recon.most_common(10):
                _p(f"      {s0} -> {s1}  {n}")
            if bad:
                raise SystemExit("verification failed - see above (rollback: --rollback)")
    finally:
        conn.close()
    _p(f"=== DONE in {time.monotonic() - t0:.0f}s ===")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = ap.add_mutually_exclusive_group(required=True)
    m.add_argument("--structure", action="store_true")
    m.add_argument("--seeds", action="store_true")
    m.add_argument("--cutover", action="store_true")
    m.add_argument("--rollback", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.structure:
        structure(a.dry_run)
    elif a.seeds:
        switch(on=False, dry_run=a.dry_run, also_seeds=True)
    else:
        switch(on=a.cutover, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
