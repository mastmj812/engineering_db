"""box_recon_2 rehearsal of the night the rule changes, in the box-rehearsal CONTAINER only (bar R8 of
docs/box_sticks/recon2-2026-11-20/BARS.md).

    python -m scripts.box_rehearsal up / seed / mirror curated.wells_enriched curated.well_lateral_survey raw_novi_intel.pads
    (set the DB_* lines of `python -m scripts.box_rehearsal env`)
    python -m scripts.box_recon2_rehearsal --out docs/box_sticks/recon2-2026-11-20

Refuses to run unless DB_HOST is localhost and DB_PORT is the container's port: it applies sql/74 and WRITES.
Steps: sql/74 through the apply script; two nights on box_recon_1 (the rule live today); the night box_recon_2 lands, with
the circuit breaker forced to its tightest; the night after.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from etl import box_recon as br
from scripts.box_recon_rehearsal import _DIGEST, _apply, _q
from scripts.box_rehearsal import PORT

_results: list[dict] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    _results.append({"ok": bool(ok), "check": msg})


def _out_counts() -> tuple:
    return _q("SELECT count(*) FILTER (WHERE status = 'producing'), count(*) FILTER (WHERE status = 'conflict'), count(*) FILTER (WHERE crowded), "
              "count(*) FILTER (WHERE counts_as_inventory), count(*) FROM curated.box_location_status")[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if os.environ.get("DB_HOST") != "localhost" or os.environ.get("DB_PORT") != str(PORT):
        raise SystemExit(f"refusing: DB_HOST / DB_PORT are not the rehearsal container (localhost:{PORT})")
    a.out.mkdir(parents=True, exist_ok=True)
    for t in br.TABLES:
        _q(f"DROP TABLE IF EXISTS {t} CASCADE")
    _q("CREATE SCHEMA IF NOT EXISTS meta")
    rc, out = _apply()
    (a.out / "rehearsal_apply.log").write_text(out, encoding="utf-8")
    _check(rc == 0 and "all checks passed" in out and "FAIL" not in out, f"sql/74 (with the box_recon_2 comment) applies: {out.count('    ok  ')} checks ok")

    rule2 = (br.VERSION, br.JUDGE_SQL)
    assert rule2[0] == "box_recon_2"
    print("[rule 1] two nights on the rule that is live today", flush=True)
    br.VERSION, br.JUDGE_SQL = "box_recon_1", br.RULE1_JUDGE_SQL
    try:
        n1 = br.run(write=True)
        n2 = br.run(write=True)
    finally:
        br.VERSION, br.JUDGE_SQL = rule2
    c1 = _out_counts()
    _check(n1["status"] == "written" and n1["cause"] == "first_run" and n2["status"] == "written" and n2["changed"] == 0,
           f"rule 1: run {n1['run_id']} first_run, run {n2['run_id']} changed 0; producing {c1[0]}, conflict {c1[1]}, crowded {c1[2]}, inventory {c1[3]:,} of {c1[4]:,}")

    print("[R8] the night box_recon_2 lands, breaker forced to its tightest", flush=True)
    lim = (br.BREAKER_MIN, br.BREAKER_SHARE)
    br.BREAKER_MIN, br.BREAKER_SHARE = 1, 0.0
    try:
        n3 = br.run(write=True)
    finally:
        br.BREAKER_MIN, br.BREAKER_SHARE = lim
    c3 = _out_counts()
    lg = _q("SELECT cause, old_status, new_status, count(*) FROM curated.box_location_status_log WHERE run_id = %s GROUP BY 1, 2, 3 ORDER BY 4 DESC", (n3["run_id"],))
    rr = _q("SELECT status, wrote, predicate_version, changed, breaker_limit FROM meta.box_recon_run WHERE run_id = %s", (n3["run_id"],))[0]
    _check(n3["status"] == "written" and rr[0] == "written" and rr[1] and rr[2] == "box_recon_2",
           f"run {n3['run_id']} written on {rr[2]}: changed {rr[3]} with the breaker limit forced to {rr[4]} (a rule change is not held)")
    _check(bool(lg) and all(r[0] == "rule_change" for r in lg) and sum(r[3] for r in lg) == n3["changed"],
           f"every log row says rule_change ({', '.join(f'{o}->{n} {c}' for _, o, n, c in lg)})")
    _check(c3[4] == c1[4], f"one row per record stick still ({c3[4]:,}); producing {c1[0]} -> {c3[0]}, conflict {c1[1]} -> {c3[1]}, crowded {c1[2]} -> {c3[2]}, "
                           f"inventory {c1[3]:,} -> {c3[3]:,}")
    d3 = _q(_DIGEST)[0]

    print("[R8] the night after", flush=True)
    n4 = br.run(write=True)
    _check(n4["status"] == "written" and n4["changed"] == 0 and n4["cause"] == "well", f"run {n4['run_id']} written, changed 0, cause well ({n4['seconds']} s)")
    _check(_q("SELECT count(*) FROM curated.box_location_status_log WHERE run_id = %s", (n4["run_id"],))[0][0] == 0, "0 log rows")
    _check(_q(_DIGEST)[0] == d3, "status table identical but for the run id")

    runs = _q("SELECT run_id, status, predicate_version, changed, breaker_limit, stale_dsu_bench, seconds, counts FROM meta.box_recon_run ORDER BY run_id")
    summ = {"checks": _results, "failed": [r for r in _results if not r["ok"]],
            "runs": [dict(zip(("run_id", "status", "predicate_version", "changed", "breaker_limit", "stale_dsu_bench", "seconds", "counts"), r, strict=True)) for r in runs]}
    (a.out / "rehearsal_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    bad = len(summ["failed"])
    print(f"{len(_results) - bad} of {len(_results)} checks ok" + (f"; {bad} FAILED" if bad else ""), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
