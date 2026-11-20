"""BOX sticks gate 5d: the shadow-week reports of the nightly reconciliation (docs/box_sticks/phase5d-2026-11-19/BARS.md).

    python -m scripts.box_recon_shadow baseline --out <dir>            # night 0: etl.box_recon's read-only pass, nothing written
    python -m scripts.box_recon_shadow night [--run-id N] --out <dir>  # one night, from the four sql/74 tables
    python -m scripts.box_recon_shadow week --out <dir>                # bars S1 to S8 over every night so far

READ-ONLY, every step: each query runs in a READ ONLY transaction that is rolled back. This script never fills the
sql/74 tables; their only writer is the nightly hook (etl.box_recon.nightly_hook). curated.reconciled_inventory is not
refreshed or touched: sql/68's SELECT is evaluated here per well.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from etl import box_recon as br
from etl.db import get_connection

OUT = ("producing", "conflict")
CHURN_LIMIT = 198            # S4: 0.25 % of 79,200 record sticks
FLAP_LIMIT = 0.10            # S5
SECONDS_LIMIT = 300          # S2
DAY0_LIMIT = 0.005           # S3
# Run rows written outside a nightly: kept in the tables, never counted as a night (Michael 2026-11-20: run 3, the first fill
# at 2026-11-19 16:44 UTC, came from no etl-nightly run; the nightly of 2026-11-20, run 4, is night 1 and the week ends 11-26).
# Run 5 (2026-11-20 16:03 UTC, 27 changed): the forced refresh of the Novi v4 cutover, run by hand in another session; also not a night.
OUT_OF_BAND_RUNS = frozenset({3, 5})

# sql/68's SELECT, per well: the same sticks, corridor, bench guard and thresholds, restricted to a list of wells.
SQL68_PER_WELL = """
WITH pud AS (
    SELECT il.stick_id, il.wellstick_geom AS geom, il.tvd, il.basin, fb.formation_blueox AS code
    FROM curated.intel_locations il
    JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
    WHERE il.category IN ('PUD', 'RES') AND il.wellstick_geom IS NOT NULL AND fb.formation_blueox IS NOT NULL
), pr AS (
    SELECT pr.api10, pr.basin, pr.tvd, pr.corridor, COALESCE(t.corrected_code, pr.code) AS code
    FROM curated.producing_reference pr
    LEFT JOIN curated.formation_blueox_tvd t ON t.api10 = pr.api10
    WHERE pr.api10 = ANY (%s)
), c AS (
    SELECT pr.api10, pud.stick_id,
           extensions.ST_Length(extensions.ST_Intersection(pud.geom, pr.corridor)::extensions.geography)
             / NULLIF(extensions.ST_Length(pud.geom::extensions.geography), 0) AS overlap
    FROM pr JOIN pud ON pud.basin = pr.basin AND extensions.ST_Intersects(pud.geom, pr.corridor)
    WHERE pr.tvd IS NOT NULL
      AND ((pr.code = pud.code AND abs(pr.tvd - pud.tvd) <= 500) OR abs(pr.tvd - pud.tvd) <= 150)
)
SELECT pr.api10, pr.tvd IS NOT NULL AS has_tvd, max(c.overlap) AS best_overlap,
       (array_agg(c.stick_id ORDER BY c.overlap DESC NULLS LAST))[1] AS best_stick
FROM pr LEFT JOIN c USING (api10)
GROUP BY 1, 2
"""

# S8: an independent read of each stick that went to producing: the well as the warehouse holds it (raw wellstick, flat 46 m corridor).
S8_SQL = """
SELECT s.location_id, e.api10, e.first_production_date, e.formation_blueox AS well_code, s.formation_blueox AS bench, s.target_tvd_ft,
       CASE WHEN COALESCE(e.directional_survey_is_planned, FALSE) THEN NULL ELSE COALESCE(sv.lat_tvd_p50_ft, e.tvd_ft) END AS well_tvd_ft,
       COALESCE(sv.is_uturn, FALSE) AS is_uturn,
       (SELECT max(extensions.ST_Length(extensions.ST_Intersection(g.geom,
                     extensions.ST_Buffer(COALESCE(CASE WHEN sv.is_uturn THEN sv.lateral_geom END, e.wellstick_geom)::extensions.geography,
                                          46, 'endcap=flat')::extensions.geometry)::extensions.geography)
                   / NULLIF(extensions.ST_Length(g.geom::extensions.geography), 0))
        FROM extensions.ST_Dump(s.legs_geom) g) AS best_leg_share
FROM unnest(%s::bigint[], %s::text[]) AS x (location_id, api10)
JOIN box.location_stick s ON s.location_id = x.location_id
JOIN box.location_set t ON t.set_id = s.set_id AND t.is_record
LEFT JOIN curated.wells_enriched e ON e.api10::text = x.api10
LEFT JOIN curated.well_lateral_survey sv ON sv.api10 = e.api10
"""

_DEPENDS = """
SELECT DISTINCT d.refobjid::regclass::text, v.relname
FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class v ON v.oid = r.ev_class
WHERE d.refobjid = ANY (%s::regclass[]) AND v.oid <> d.refobjid
"""


def _ro(sql: str, params: tuple = ()) -> list[dict]:
    """One query in a READ ONLY transaction, rolled back."""
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '600s'")
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
        conn.rollback()
    return rows


def sql68_class(row: dict | None) -> str:
    """What sql/68's rule says about one well against the Novi sticks."""
    if row is None:
        return "not_in_producing_reference"
    if not row["has_tvd"]:
        return "no_tvd"
    ov = row["best_overlap"]
    if ov is None or ov < 0.2:
        return "nothing"
    return "realizes" if ov >= 0.5 else "conflict"


def side_by_side(status: list[dict], wells: set[str]) -> list[dict]:
    """Per well: what it does to BOX sticks tonight, and what sql/68's rule says of it against Novi sticks."""
    box: dict[str, Counter] = defaultdict(Counter)
    for r in status:
        if r["status"] in OUT and r["matched_api10"]:
            box[str(r["matched_api10"])][r["status"]] += 1
        if r["crowded"] and r["crowd_api10"]:
            box[str(r["crowd_api10"])]["crowded"] += 1
    wells = {str(w) for w in wells if w}
    if not wells:
        return []
    got = {str(r["api10"]): r for r in _ro(SQL68_PER_WELL, (sorted(wells),))}
    out = []
    for w in sorted(wells):
        g = got.get(w)
        out.append({"api10": w, "box_producing": box[w]["producing"], "box_conflict": box[w]["conflict"], "box_crowded": box[w]["crowded"],
                    "sql68": sql68_class(g), "sql68_overlap": None if g is None or g["best_overlap"] is None else round(float(g["best_overlap"]), 3),
                    "sql68_stick": None if g is None else g["best_stick"]})
    return out


def two_sticks(status: list[dict]) -> dict:
    """Wells that are the matching well of two or more producing sticks."""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in status:
        if r["status"] == "producing" and r["matched_api10"]:
            by[str(r["matched_api10"])].append(r)
    multi = {w: v for w, v in by.items() if len(v) >= 2}
    same = {w: v for w, v in multi.items() if any(c >= 2 for c in Counter(x["pad_id"] for x in v).values())}
    return {"wells_matching_sticks": len(by), "wells_with_two_or_more": len(multi), "same_dsu": len(same), "different_dsus_only": len(multi) - len(same),
            "same_dsu_same_bench": sum(1 for v in same.values() if any(c >= 2 for c in Counter((x["pad_id"], x["formation_blueox"]) for x in v).values())),
            "detail": [{"api10": w, "sticks": [{"location_id": x["location_id"], "pad_id": x["pad_id"], "bench": x["formation_blueox"],
                                                "overlap": None if x["match_overlap"] is None else float(x["match_overlap"])} for x in v]}
                       for w, v in sorted(multi.items())]}


def counts(status: list[dict]) -> dict:
    c: dict[str, Counter] = defaultdict(Counter)
    for r in status:
        b = c[r["basin"]]
        b["sticks"] += 1
        b[r["status"]] += 1
        b["crowded"] += int(bool(r["crowded"]))
        b["inventory"] += int(bool(r["counts_as_inventory"]))
    return {k: dict(v) for k, v in sorted(c.items())}


def identities(status: list[dict], record_sticks: int) -> dict:
    """S6, the part that reads the status rows."""
    ids = [r["location_id"] for r in status]
    bad = [r["location_id"] for r in status if bool(r["counts_as_inventory"]) != (r["status"] not in OUT and not r["crowded"])]
    return {"status_rows": len(ids), "distinct_locations": len(set(ids)), "record_sticks": record_sticks,
            "one_row_per_record_stick": len(ids) == len(set(ids)) == record_sticks, "inventory_rule_breaks": len(bad)}


def flapping(log: list[dict]) -> dict:
    """S5 over `well`-caused log rows (ordered by run): locations that return to a status they held earlier."""
    seq: dict[int, list[str]] = defaultdict(list)
    for r in sorted(log, key=lambda x: x["run_id"]):
        if r["cause"] != "well":
            continue
        s = seq[r["location_id"]]
        if not s and r["old_status"]:
            s.append(r["old_status"])
        if not s or s[-1] != r["new_status"]:
            s.append(r["new_status"])
    flap = [k for k, s in seq.items() if len(set(s)) < len(s)]
    n = len(seq)
    return {"locations_changed": n, "flapped": len(flap), "share": round(len(flap) / n, 4) if n else 0.0, "location_ids": sorted(flap)[:50]}


def night_number(runs: list[dict], run_id: int) -> int | None:
    """Night number of a written nightly run: its rank among the written run rows that a nightly wrote."""
    nights = [r["run_id"] for r in runs if r["status"] == "written" and r["run_id"] not in OUT_OF_BAND_RUNS]
    return nights.index(run_id) + 1 if run_id in nights else None


def _nightly_runs() -> list[dict]:
    try:
        r = subprocess.run(["gh", "run", "list", "--workflow", "etl-nightly.yml", "--limit", "30", "--json", "databaseId,event,status,conclusion,createdAt"],
                           capture_output=True, text=True, check=True, timeout=60)
        return json.loads(r.stdout)
    except Exception as exc:  # noqa: BLE001 - the report still stands without it
        return [{"error": f"{type(exc).__name__}: {exc}"[:200]}]


def _box_state() -> dict:
    return _ro("SELECT (SELECT count(*) FROM box.location_set) AS sets, (SELECT count(*) FROM box.location_stick) AS stick_rows, "
               "(SELECT count(*) FROM box.location) AS locations, (SELECT array_agg(set_id ORDER BY set_id) FROM box.location_set WHERE is_record) AS record_sets, "
               "(SELECT count(*) FROM box.location_stick s JOIN box.location_set t USING (set_id) WHERE t.is_record) AS record_sticks")[0]


def _write(out: Path, name: str, rep: dict, md: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    (out / f"{name}.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(md), flush=True)


def _count_table(c: dict) -> list[str]:
    keys = ("sticks", "open", "permitted", "pending", "producing", "conflict", "crowded", "inventory")
    basins = list(c)
    lines = ["| sticks | " + " | ".join(basins) + " |", "|---|" + "---|" * len(basins)]
    lines += [f"| {k} | " + " | ".join(f"{int(c[b].get(k, 0)):,}" for b in basins) + " |" for k in keys]
    return lines


def _two_line(t: dict) -> str:
    return (f"One well, two sticks: {t['wells_with_two_or_more']} of {t['wells_matching_sticks']} matching wells ({t['same_dsu']} within one DSU, "
            f"of which {t['same_dsu_same_bench']} on one bench; {t['different_dsus_only']} across DSUs only).")


def _sbs_lines(sbs: list[dict]) -> list[str]:
    tab = Counter((("takes a stick out" if r["box_producing"] else "conflict" if r["box_conflict"] else "crowds only"), r["sql68"]) for r in sbs)
    lines = [f"Wells compared: {len(sbs):,}.", "", "| BOX nightly (well) | sql/68 rule on Novi sticks (well) | wells |", "|---|---|---|"]
    return lines + [f"| {a} | {b} | {n:,} |" for (a, b), n in sorted(tab.items())]


def cmd_baseline(out: Path) -> dict:
    res = br.run(write=False)
    if res.get("status") != "dry_run":
        raise SystemExit(f"read-only pass returned {res.get('status')}")
    status = [dict(zip(br.STATUS_COLS, r, strict=True)) for r in res["rows"]]
    box = _box_state()
    wells = {r["matched_api10"] for r in status if r["status"] in OUT} | {r["crowd_api10"] for r in status if r["crowded"]}
    sbs = side_by_side(status, wells)
    rep = {"kind": "baseline", "predicate_version": br.VERSION, "set_ids": res["set_ids"], "seconds": res["seconds"], "counts": counts(status),
           "identities": identities(status, box["record_sticks"]), "stale_dsu_bench": res["stale_dsu_bench"],
           "conflict_queue": sum(r["status"] == "conflict" for r in status), "two_sticks": two_sticks(status), "sql68_side_by_side": sbs, "box": box,
           "tables_rows": _ro("SELECT (SELECT count(*) FROM meta.box_recon_run) AS run, (SELECT count(*) FROM curated.box_location_status) AS status")[0]}
    t = rep["two_sticks"]
    md = ["# Night 0 (baseline): the read-only pass, nothing written", "",
          f"Rule `{br.VERSION}`, record sets {res['set_ids']}, {res['seconds']} s. Tables: {rep['tables_rows']['run']} run rows, {rep['tables_rows']['status']} status rows.", "",
          *_count_table(rep["counts"]), "",
          f"Stale DSU x bench: {rep['stale_dsu_bench']}. Conflict queue: {rep['conflict_queue']} sticks.",
          _two_line(t), "", "## Against sql/68, per well", "", *_sbs_lines(sbs)]
    _write(out, "night_0_baseline", rep, md)
    return rep


def cmd_night(out: Path, run_id: int | None) -> dict:
    runs = _ro("SELECT * FROM meta.box_recon_run ORDER BY run_id")
    if not runs:
        raise SystemExit("meta.box_recon_run is empty: the nightly hook has not run yet")
    run = next((r for r in runs if r["run_id"] == run_id), None) if run_id else runs[-1]
    if run is None:
        raise SystemExit(f"no run {run_id}")
    written = [r for r in runs if r["status"] == "written"]
    latest = bool(written) and run["run_id"] == written[-1]["run_id"]
    night_no = night_number(runs, run["run_id"])
    box = _box_state()
    log = _ro("SELECT * FROM curated.box_location_status_log WHERE run_id = %s", (run["run_id"],))
    rep: dict[str, Any] = {"kind": "night", "night": night_no, "run": run, "box": box, "log_rows": len(log),
                           "log_by_transition": [{"cause": k[0], "old": k[1], "new": k[2], "n": n} for k, n in
                                                 sorted(Counter((r["cause"], r["old_status"], r["new_status"]) for r in log).items(), key=lambda x: -x[1])],
                           "crowded_changes": sum(1 for r in log if r["old_crowded"] is not None and bool(r["old_crowded"]) != bool(r["new_crowded"])),
                           "depends": _ro(_DEPENDS, (list(br.TABLES),)), "nightly_runs": _nightly_runs()[:6]}
    head = "Out-of-band run (not a night)" if run["run_id"] in OUT_OF_BAND_RUNS else f"Shadow night {night_no if night_no else '(not written)'}"
    md = [f"# {head}: run {run['run_id']}, {run['status']}", "",
          f"Started {run['started_at']}, {run['seconds']} s, rule `{run['predicate_version']}`, sets {run['set_ids']}, wells read {run['wells_read']}, "
          f"changed {run['changed']}, breaker limit {run['breaker_limit']}, stale {run['stale_dsu_bench']}." + (f" Error: {run['error']}" if run["error"] else ""), ""]
    if run["status"] == "written" and latest:
        status = _ro("SELECT * FROM curated.box_location_status")
        stale = _ro("SELECT * FROM curated.box_dsu_bench_stale ORDER BY basin, pad_id, formation_blueox")
        rep |= {"counts": counts(status), "identities": identities(status, box["record_sticks"]), "stale": stale,
                "conflict_queue": [r for r in status if r["status"] == "conflict"], "two_sticks": two_sticks(status)}
        first = bool(log) and all(r["cause"] == "first_run" for r in log)
        wells = ({r["matched_api10"] for r in status if r["status"] in OUT} | {r["crowd_api10"] for r in status if r["crowded"]}) if first \
            else ({r["new_api10"] for r in log} | {r["old_api10"] for r in log})
        rep["sql68_side_by_side"] = side_by_side(status, wells)
        newly = [r for r in log if r["cause"] == "well" and r["new_status"] == "producing" and r["old_status"] != "producing" and r["new_api10"]]
        rep["s8"] = _ro(S8_SQL, ([r["location_id"] for r in newly], [str(r["new_api10"]) for r in newly])) if newly else []
        for r in rep["s8"]:
            dv = None if r["well_tvd_ft"] is None else abs(float(r["well_tvd_ft"]) - float(r["target_tvd_ft"]))
            r["ok"] = bool(r["first_production_date"] is not None and (r["best_leg_share"] or 0) >= br.MATCH
                           and (dv is None or dv <= br.ANY_TAG_FT or (r["well_code"] == r["bench"] and dv <= br.SAME_CODE_FT)))
        i, t = rep["identities"], rep["two_sticks"]
        md += [*_count_table(rep["counts"]), "",
               (f"Identities: {i['status_rows']:,} status rows, {i['distinct_locations']:,} locations, {i['record_sticks']:,} record sticks "
               f"({'ok' if i['one_row_per_record_stick'] else 'BROKEN'}); inventory rule breaks {i['inventory_rule_breaks']}; log rows {len(log):,} against changed {run['changed']}."),
               f"Schema box: {box['sets']} sets, {box['stick_rows']:,} stick rows, {box['locations']:,} locations, records {box['record_sets']}.",
               f"Objects reading the tables: {len(rep['depends'])}.", "", "## Changes tonight", "", "| cause | from | to | locations |", "|---|---|---|---|",
               *[f"| {x['cause']} | {x['old']} | {x['new']} | {x['n']:,} |" for x in rep["log_by_transition"][:20]], "",
               f"Crowded flag changes: {rep['crowded_changes']}. Stale DSU x bench: {len(stale)}. Conflict queue: {len(rep['conflict_queue'])} sticks.",
               _two_line(t),
               f"S8, sticks newly producing: {len(rep['s8'])}; independent read agrees on {sum(r['ok'] for r in rep['s8'])}.", "",
               "## Against sql/68, per well", "", *_sbs_lines(rep["sql68_side_by_side"])]
    elif run["status"] == "written":
        md += ["A later night has replaced the status table; this report carries the run row and its log only.", "",
               *[f"- {x['cause']}: {x['old']} -> {x['new']}: {x['n']:,}" for x in rep["log_by_transition"][:20]]]
    _write(out, f"night_run_{run['run_id']}", rep, md)
    return rep


def cmd_week(out: Path) -> dict:
    every = _ro("SELECT * FROM meta.box_recon_run ORDER BY run_id")
    runs = [r for r in every if r["run_id"] not in OUT_OF_BAND_RUNS]
    written = [r for r in runs if r["status"] == "written"]
    log = [r for r in _ro("SELECT run_id, location_id, cause, old_status, new_status FROM curated.box_location_status_log WHERE cause <> 'first_run'")
           if r["run_id"] not in OUT_OF_BAND_RUNS]
    days = Counter(str(r["started_at"])[:10] for r in runs)
    later = written[1:] if not OUT_OF_BAND_RUNS else [r for r in written if night_number(every, r["run_id"]) >= 2]
    fl = flapping(log)
    bars = {
        "S1": {"nights": len(days), "written": len(written), "failed_or_breaker": [r["run_id"] for r in runs if r["status"] != "written"],
               "days_with_more_than_one_row": [d for d, n in days.items() if n > 1],
               "pass": len(written) >= 7 and len(written) == len(runs) and all(n == 1 for n in days.values())},
        "S2": {"max_seconds": max((r["seconds"] or 0) for r in runs) if runs else None, "nightly_runs": _nightly_runs()[:12],
               "pass_seconds": bool(runs) and all((r["seconds"] or 0) <= SECONDS_LIMIT for r in runs)},
        "S4": {"changed_per_night": {r["run_id"]: r["changed"] for r in later}, "limit": CHURN_LIMIT,
               "pass": bool(later) and all((r["changed"] or 0) <= CHURN_LIMIT for r in later)},
        "S5": fl | {"limit": FLAP_LIMIT, "pass": fl["share"] <= FLAP_LIMIT},
        "S7": {"depends": _ro(_DEPENDS, (list(br.TABLES),))},
    }
    bars["S7"]["pass"] = not bars["S7"]["depends"]
    rep = {"kind": "week", "runs": runs, "out_of_band_runs": sorted(OUT_OF_BAND_RUNS), "bars": bars, "note": "S3, S6 and S8 are scored in each night's report; S2's nightly conclusions are in nightly_runs"}
    md = ["# Shadow week so far", "", f"{len(runs)} nightly run rows on {len(days)} days; {len(written)} written. Out-of-band run rows, not counted: {sorted(OUT_OF_BAND_RUNS)}.", "", "| bar | reading | verdict |", "|---|---|---|",
          f"| S1 | {len(written)} written of {len(runs)} rows, {len(days)} days | {'passes' if bars['S1']['pass'] else 'not yet / fails'} |",
          f"| S2 | max {bars['S2']['max_seconds']} s | {'passes on seconds' if bars['S2']['pass_seconds'] else 'not yet / fails'} |",
          f"| S4 | changed per night {list(bars['S4']['changed_per_night'].values())} | {'passes' if bars['S4']['pass'] else 'not yet / fails'} |",
          f"| S5 | {fl['flapped']} of {fl['locations_changed']} locations flapped ({100 * fl['share']:.1f} %) | {'passes' if bars['S5']['pass'] else 'fails'} |",
          f"| S7 | {len(bars['S7']['depends'])} dependent objects | {'passes' if bars['S7']['pass'] else 'fails'} |"]
    _write(out, "week", rep, md)
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("baseline", "night", "week"))
    ap.add_argument("--run-id", type=int)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.step == "baseline":
        cmd_baseline(a.out)
    elif a.step == "night":
        cmd_night(a.out, a.run_id)
    else:
        cmd_week(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
