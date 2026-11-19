"""Gate 5b rehearsal of the nightly BOX sticks reconciliation, in the box-rehearsal CONTAINER only (bars E5 to E8 of
docs/box_sticks/phase5b-2026-11-19/BARS.md).

    python -m scripts.box_rehearsal up
    python -m scripts.box_rehearsal seed
    python -m scripts.box_rehearsal mirror curated.wells_enriched curated.well_lateral_survey raw_novi_intel.pads
    (set the DB_* lines of `python -m scripts.box_rehearsal env`)
    python -m scripts.box_recon_rehearsal --out docs/box_sticks/phase5b-2026-11-19

Refuses to run unless DB_HOST is localhost and DB_PORT is the container's port: it applies sql/74 and WRITES.
Steps: the hook before the tables exist; apply sql/74 twice through scripts.apply_box_recon; night 1; night 2 with
nothing changed; a forced SQL error through the hook; a real change behind the circuit breaker, then let through.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from etl import box_recon as br
from etl.db import get_connection
from scripts.box_rehearsal import PORT

_DIGEST = ("SELECT count(*), md5(string_agg(md5(ROW(location_id, set_id, status, counts_as_inventory, legs_matched, matched_api10, match_overlap, "
           "match_basis, conflict_reason, pending_api10, permit_api10, crowded, crowd_api10, status_since)::text), '' ORDER BY location_id)) "
           "FROM curated.box_location_status")
_results: list[dict] = []


def _check(bar: str, ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} [{bar}] {msg}", flush=True)
    _results.append({"bar": bar, "ok": bool(ok), "check": msg})


def _q(sql: str, params: tuple = ()) -> list:
    with get_connection() as conn, conn.cursor() as cur:
        rows = cur.execute(sql, params).fetchall() if sql.lstrip().upper().startswith(("SELECT", "WITH")) else (cur.execute(sql, params), [])[1]
        conn.commit()
    return rows


def _apply() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "scripts.apply_box_recon"], capture_output=True, text=True, check=False, env=os.environ)
    return r.returncode, r.stdout + r.stderr


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if os.environ.get("DB_HOST") != "localhost" or os.environ.get("DB_PORT") != str(PORT):
        raise SystemExit(f"refusing: DB_HOST / DB_PORT are not the rehearsal container (localhost:{PORT})")
    a.out.mkdir(parents=True, exist_ok=True)
    n_rec = _q("SELECT count(*) FROM box.location_stick s JOIN box.location_set t USING (set_id) WHERE t.is_record")[0][0]
    print(f"container: {n_rec:,} record sticks", flush=True)

    print("[E8a] the hook before sql/74", flush=True)
    for t in br.TABLES:
        _q(f"DROP TABLE IF EXISTS {t} CASCADE")
    _q("CREATE SCHEMA IF NOT EXISTS meta")
    _check("E8", br.run(write=True).get("status") == "absent", "run(write=True) returns absent with the tables missing")
    br.nightly_hook()
    _check("E8", len(br.missing_tables(get_connection())) == len(br.TABLES), "the hook created nothing")

    print("[E5] apply sql/74 through scripts.apply_box_recon, twice", flush=True)
    rc1, out1 = _apply()
    rc2, out2 = _apply()
    (a.out / "rehearsal_apply.log").write_text(out1 + "\n===== second apply =====\n" + out2, encoding="utf-8")
    _check("E5", rc1 == 0 and "all checks passed" in out1 and "FAIL" not in out1, f"first apply: {out1.count('    ok  ')} checks ok, COMMITTED")
    _check("E5", rc2 == 0 and "all checks passed" in out2 and "FAIL" not in out2, f"second apply over the existing tables: {out2.count('    ok  ')} checks ok")
    _check("E5", _q("SELECT count(*) FROM curated.box_location_status")[0][0] == 0, "the tables are empty after the apply")

    print("[E6] night 1", flush=True)
    n1 = br.run(write=True)
    st = _q("SELECT count(*), count(DISTINCT location_id) FROM curated.box_location_status")[0]
    _check("E6", n1["status"] == "written" and n1["cause"] == "first_run", f"run {n1['run_id']} written, cause first_run ({n1['seconds']} s)")
    _check("E6", st[0] == st[1] == n_rec, f"status rows = record sticks, one per location ({st[0]:,} = {n_rec:,})")
    miss = _q("SELECT count(*) FROM box.location_stick s JOIN box.location_set t USING (set_id) LEFT JOIN curated.box_location_status c "
              "USING (location_id) WHERE t.is_record AND (c.location_id IS NULL OR c.set_id <> s.set_id)")[0][0]
    _check("E6", miss == 0, "every record stick has its status row, on its own set")
    lg = _q("SELECT count(*), count(*) FILTER (WHERE cause = 'first_run' AND old_status IS NULL) FROM curated.box_location_status_log WHERE run_id = %s", (n1["run_id"],))[0]
    _check("E6", lg[0] == lg[1] == n_rec, f"log rows = status rows, all first_run ({lg[0]:,})")
    rr = _q("SELECT status, wrote, changed, predicate_version, set_ids FROM meta.box_recon_run WHERE run_id = %s", (n1["run_id"],))[0]
    _check("E6", rr[0] == "written" and rr[1] and rr[3] == br.VERSION, f"run row: {rr[0]}, changed {rr[2]:,}, sets {rr[4]}, {rr[3]}")
    d1 = _q(_DIGEST)[0]

    print("[E7] night 2, nothing changed", flush=True)
    n2 = br.run(write=True)
    d2 = _q(_DIGEST)[0]
    _check("E7", n2["status"] == "written" and n2["changed"] == 0 and n2["cause"] == "well", f"run {n2['run_id']} written, changed 0 ({n2['seconds']} s)")
    _check("E7", _q("SELECT count(*) FROM curated.box_location_status_log WHERE run_id = %s", (n2["run_id"],))[0][0] == 0, "0 log rows")
    _check("E7", d1 == d2, f"status table identical but for the run id (digest {d2[1][:12]}, {d2[0]:,} rows)")
    _check("E7", _q("SELECT count(DISTINCT run_id) FROM curated.box_location_status")[0][0] == 1, "every status row carries the night's run id")

    print("[E8b] a forced SQL error through the hook", flush=True)
    good = br.JUDGE_SQL
    br.JUDGE_SQL = "SELECT 1 / 0"
    try:
        br.nightly_hook()                                                  # must not raise
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
    finally:
        br.JUDGE_SQL = good
    _check("E8", not raised, "the hook did not raise")
    _check("E8", _q(_DIGEST)[0] == d2, "the status table is untouched")
    f = _q("SELECT status, wrote, error FROM meta.box_recon_run ORDER BY run_id DESC LIMIT 1")[0]
    _check("E8", f[0] == "failed" and not f[1] and "ZeroDivision" not in (f[2] or "") and "division by zero" in (f[2] or ""), f"a failed run row exists ({(f[2] or '')[:60]})")

    print("[E8c] a real change behind the circuit breaker", flush=True)
    wells = [r[0] for r in _q("SELECT matched_api10 FROM curated.box_location_status WHERE status = 'producing' ORDER BY location_id LIMIT 5")]
    _q("CREATE TABLE IF NOT EXISTS public._rehearsal_fp AS SELECT api10, first_production_date FROM curated.wells_enriched WHERE api10 = ANY (%s)", (wells,))
    _q("UPDATE curated.wells_enriched SET first_production_date = NULL WHERE api10 = ANY (%s)", (wells,))   # the container's copy: these wells 'stop producing'
    lim = (br.BREAKER_MIN, br.BREAKER_SHARE)
    br.BREAKER_MIN, br.BREAKER_SHARE = 1, 0.0
    try:
        n3 = br.run(write=True)
        _check("E8", n3["status"] == "breaker" and n3["changed"] > 1, f"run {n3['run_id']}: breaker, {n3['changed']} changed > limit {n3['breaker_limit']}")
        _check("E8", _q(_DIGEST)[0] == d2, "the status table is untouched by the breaker run")
        _check("E8", _q("SELECT count(*) FROM curated.box_location_status_log WHERE run_id = %s", (n3["run_id"],))[0][0] == 0, "the breaker run logged nothing")
        n4 = br.run(write=True, allow_breaker=True)
    finally:
        br.BREAKER_MIN, br.BREAKER_SHARE = lim
    lg4 = _q("SELECT old_status, new_status, count(*) FROM curated.box_location_status_log WHERE run_id = %s GROUP BY 1, 2 ORDER BY 3 DESC", (n4["run_id"],))
    _check("E8", n4["status"] == "written" and n4["cause"] == "well" and sum(r[2] for r in lg4) == n4["changed"],
           f"let through: run {n4['run_id']} written, {n4['changed']} log rows, cause well ({', '.join(f'{o}->{n_} {c}' for o, n_, c in lg4)})")
    _q("UPDATE curated.wells_enriched e SET first_production_date = r.first_production_date FROM public._rehearsal_fp r WHERE r.api10 = e.api10")
    _q("DROP TABLE public._rehearsal_fp")
    n5 = br.run(write=True, allow_breaker=True)
    _check("E8", _q(_DIGEST)[0][1] == d2[1] or n5["changed"] == n4["changed"],
           f"the wells produce again: {n5['changed']} locations heal, status back to night 2 except status_since")
    heal = _q("SELECT count(*) FROM curated.box_location_status WHERE status = 'producing'")[0][0]
    _check("E8", heal == _q("SELECT (counts -> 'delaware' ->> 'producing')::int + (counts -> 'midland' ->> 'producing')::int FROM meta.box_recon_run WHERE run_id = %s",
                             (n2["run_id"],))[0][0], f"producing sticks back to night 2's count ({heal})")
    box = _q("SELECT (SELECT count(*) FROM box.location_set), (SELECT count(*) FROM box.location_stick), (SELECT count(*) FROM box.location)")[0]
    _check("E6", box[1] >= n_rec, f"schema box as seeded (sets {box[0]}, stick rows {box[1]:,}, locations {box[2]:,})")

    runs = _q("SELECT run_id, status, wrote, changed, breaker_limit, stale_dsu_bench, seconds, counts FROM meta.box_recon_run ORDER BY run_id")
    summ = {"record_sticks": n_rec, "checks": _results, "failed": [r for r in _results if not r["ok"]],
            "runs": [dict(zip(("run_id", "status", "wrote", "changed", "breaker_limit", "stale_dsu_bench", "seconds", "counts"), r, strict=True)) for r in runs]}
    (a.out / "rehearsal_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    bad = len(summ["failed"])
    print(f"{len(_results) - bad} of {len(_results)} checks ok" + (f"; {bad} FAILED" if bad else ""), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
