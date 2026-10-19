"""BOX step 12b — water on the record run (D107 / D108 / D110; sql/62).

    python -m scripts.box_water_run build --run-pkl runs/box9/run.pkl --out runs/box12b [--groups ...] [--workers N]
        READ-ONLY vs the warehouse: for every forecast location of the run artifact, the measured-water cohort (box/water11 selection
        as of the run's data-through), its WOR ratio, and 600 water months on the location's RAW box_v2 oil (run.pkl months_raw);
        writes <out>/water.pkl.
    python -m scripts.box_water_run store --out runs/box12b [--run-id N]
        Writes the water to the DB the DB_* env points at (default: the record run): pud_forecast_stream water rows (tier per D110),
        pud_forecast_month (COPY), location_water_analog (COPY), forecast_run.disclosure -> 'water' + notes, in ONE transaction with
        identity checks before COMMIT (any failure rolls back). Oil / gas rows are never touched (checked by identity).

Steps 11 / 12a: docs/box/step11-2026-10-19, docs/box/step12a-2026-10-19. Container first; live only on Michael's go.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from psycopg.types.json import Jsonb

from box import tc_curve_report as rep
from box import water11 as w
from box import water_production as wp
from etl.db import get_connection
from scripts import box_water11 as bw

DISCLOSURE = Path("docs") / "box" / "step12a-2026-10-19" / "disclosure_water.csv"
WCA_TX_CAVEAT = ("WCA in TX: the one-time holdout measured water ~15-17 % HIGH at cum-12 / 24 / 36 (TX -16.7 / -14.6 / -15.7 %; NM -5.1 / -0.9 / "
                 "-0.1 %); workup text only (D110)")


def _git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True).stdout.strip()
    return sha + ("-dirty" if dirty else "")


def cmd_build(a: argparse.Namespace) -> int:
    t0 = time.time()
    with open(a.run_pkl, "rb") as fh:
        A = pickle.load(fh)
    run = A["run"]
    asof = run["data_through"]
    if asof != w.LAST:
        raise SystemExit(f"run data-through {asof} != the water spec's {w.LAST}")
    cov = dict(zip(A["universe"]["stick_id"].astype(int), A["universe"]["coverage"], strict=True))
    out: dict[int, dict[str, Any]] = {}
    groups = tuple(a.groups.split(",")) if a.groups else w.GROUPS
    conn = get_connection()
    try:
        vdr = bw.pull_vdr(conn)
        for g in groups:
            t1 = time.time()
            pairs = [(loc, r) for loc, r in zip(A["locs"], A["results"], strict=True) if loc["prod_bench"] == g and "oil" in r.get("streams", {})]
            wells = bw.group_frame(conn, g)
            cls = bw.pull_cls(conn, list(wells["api10"]))
            labels = w.labels_asof(wells, cls, asof, w.vdr_months_asof(vdr, asof))
            pm, pa, pf = bw.pool_asof(wells, labels, asof, None)
            locs = [{k: loc[k] for k in ("api10", "x", "y", "lateral_ft", "spacing_ft", "fp_max")} for loc, _ in pairs]
            sel = w.select_many(locs, pm, pa, w.ac_label(g), a.workers)
            need = sorted({x for s in sel for x in s["api10s"]})
            prod = rep.pull_production(conn, need, asof)
            fits = rep.fit_wells(prod, rep.pull_meta(conn, need), a.workers)
            keys = {s["loc"]: tuple(s["api10s"]) for s in sel}
            uniq = sorted(set(keys.values()))
            cur = bw.cohort_curves([(str(i), list(k)) for i, k in enumerate(uniq)], pf, fits, a.workers)
            by_key = {k: cur[str(i)] for i, k in enumerate(uniq)}
            pool = pf.set_index("api10")[["x", "y", "state_code", "label", "first_production_date"]].to_dict("index")
            n_fail = 0
            for (loc, r), s in zip(pairs, sel, strict=True):
                c = by_key[keys[s["loc"]]]
                stick = int(loc["stick_id"])
                rec: dict[str, Any] = {"group": g, "coverage": cov[stick], "sel": {k: v for k, v in s.items() if k != "loc"},
                                       "analogs": wp.analog_rows(loc, s["api10s"], {x: {**pool[x], "x": float(pool[x]["x"]), "y": float(pool[x]["y"])}
                                                                                    for x in s["api10s"]})}
                if not c["ratio"]:
                    n_fail += 1
                    rec["failed"] = "WOR ratio fit failed on the measured cohort"
                else:
                    m = wp.water_months(r["streams"]["oil"]["months_raw"], float(loc["lateral_ft"]), c["ratio"])
                    rec.update({"months": m, "params": wp.params(c["ratio"], s), "flags": wp.flags(s),
                                "row": wp.stream_row(m, float(loc["lateral_ft"]), float(r["lateral_mult"])), "tier": wp.water_tier(g, cov[stick])})
                out[stick] = rec
            print(f"[{g}] {len(pairs)} locations, {len(uniq)} distinct cohorts, {len(need)} analogs fitted, {n_fail} ratio failures "
                  f"({time.time() - t1:.0f} s)", flush=True)
    finally:
        conn.close()
    a.out.mkdir(parents=True, exist_ok=True)
    meta = {"built_at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"), "code_sha": _git_sha(), "run_built_from": run["code_sha"],
            "data_through": str(asof), "groups": list(groups), "n": len(out)}
    with open(a.out / "water.pkl", "wb") as fh:
        pickle.dump({"meta": meta, "water": out}, fh)
    print(f"wrote {a.out / 'water.pkl'}: {len(out)} locations ({time.time() - t0:.0f} s)", flush=True)
    return 0


def disclosure_json() -> dict[str, Any]:
    d = pd.read_csv(DISCLOSURE)
    by = {}
    for g, x in d.groupby("group"):
        by[g] = {"tier": "validated" if g in wp.VALIDATED_WATER_GROUPS else "provisional",
                 "lines": {str(int(r.horizon)): {k: (None if pd.isna(getattr(r, k)) else float(getattr(r, k)))
                                                 for k in ("tuning_bias", "tuning_packages", "holdout_bias", "holdout_packages", "pooled_bias", "pooled_packages")}
                           for r in x.itertuples()}}
    by["WCA"]["caveat"] = WCA_TX_CAVEAT
    for g in ("AVA_0", "AVA_1", "AVA_2", "BS2_C"):
        by[g]["caveat"] = "tuning-only water disclosure: no holdout oil run exists for this D105 bench (D110)"
    return {"method": wp.METHOD, "oil_basis": wp.OIL_BASIS, "decisions": "D107 / D108 / D109 / D110", "error": "actual / forecast - 1 (negative = forecast HIGH)",
            "sources": ["docs/box/step11-2026-10-19", "docs/box/step12a-2026-10-19"], "by_bench": by}


# exact, plan-independent identity of the oil / gas stream rows (a float sum() is not bit-reproducible across query plans)
_OILGAS = ("SELECT stream, count(*), md5(string_agg(concat_ws(':', location_id, coverage, tier, params::text, lateral_mult, eur_haircut, eur_raw, eur, "
           "eur_per_kft, cum12, cum24), ',' ORDER BY location_id)) FROM box.pud_forecast_stream WHERE run_id = %s AND stream <> 'water' GROUP BY 1 ORDER BY 1")


def cmd_store(a: argparse.Namespace) -> int:
    t0 = time.time()
    with open(a.out / "water.pkl", "rb") as fh:
        W = pickle.load(fh)
    if W["meta"]["code_sha"].endswith("-dirty"):
        raise SystemExit(f"refusing: water was built from uncommitted code ({W['meta']['code_sha']})")
    water = W["water"]
    conn = get_connection()
    fails: list[str] = []

    def chk(ok: bool, msg: str) -> None:
        print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
        if not ok:
            fails.append(msg)

    try:
        with conn.cursor() as cur:
            q = cur.execute
            print(f"target {q('select inet_server_addr(), inet_server_port(), current_database()').fetchone()}", flush=True)
            rid = a.run_id or q("SELECT run_id FROM box.forecast_run WHERE is_record").fetchone()[0]
            if q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'water'", (rid,)).fetchone()[0]:
                raise SystemExit(f"run {rid} already carries water")
            pf = {int(s): (int(lid), c) for s, lid, c in q("SELECT stick_id, location_id, coverage FROM box.pud_forecast WHERE run_id = %s "
                                                           "AND coverage IN ('covered', 'covered_provisional')", (rid,)).fetchall()}
            before = q(_OILGAS, (rid,)).fetchall()
            mbefore = q("SELECT count(*) FROM box.pud_forecast_month WHERE run_id = %s", (rid,)).fetchone()[0]
            missing = sorted(set(pf) - set(water))
            extra = sorted(set(water) - set(pf))
            if missing or extra:
                raise SystemExit(f"water artifact does not match run {rid}: {len(missing)} forecast locations without water, {len(extra)} unknown sticks")
            st, an, mo, nf = [], [], [], 0
            for stick, (lid, cov) in pf.items():
                rec = water[stick]
                if rec["coverage"] != cov:
                    raise SystemExit(f"stick {stick}: coverage {rec['coverage']} in the artifact vs {cov} stored")
                if "failed" in rec:
                    nf += 1
                    continue
                r = rec["row"]
                st.append((rid, lid, cov, "water", rec["tier"], Jsonb(w_json(rec["params"] | {"flags": rec["flags"]})), r["lateral_mult"], r["eur_haircut"],
                           r["eur_raw"], r["eur"], r["eur_per_kft"], r["cum12"], r["cum24"]))
                mo.append((lid, rec["months"]))
                for x in rec["analogs"]:
                    an.append((rid, lid, cov, x["api10"], x["rank"], x["dist_ft"], x["state_code"], x["water_label"], x["first_production"]))
            cur.executemany("INSERT INTO box.pud_forecast_stream (run_id, location_id, coverage, stream, tier, params, lateral_mult, eur_haircut, eur_raw, eur, "
                            "eur_per_kft, cum12, cum24) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", st)
            with cur.copy("COPY box.pud_forecast_month (run_id, location_id, stream, month_no, volume) FROM STDIN") as cp:
                for lid, v in mo:
                    for m, x in enumerate(v, start=1):
                        cp.write_row((rid, lid, "water", m, float(x)))
            with cur.copy("COPY box.location_water_analog (run_id, location_id, coverage, api10, rank, dist_ft, state_code, water_label, first_production) "
                          "FROM STDIN") as cp:
                for row in an:
                    cp.write_row(row)
            q("UPDATE box.forecast_run SET disclosure = disclosure || jsonb_build_object('water', %s::jsonb), "
              "notes = replace(notes, 'no water (D72)', 'water: WOR vs cum oil on measured analogs, raw box_v2 oil (D107 / D108), tier per group (D110); D72 retired') "
              "WHERE run_id = %s", (Jsonb(disclosure_json()), rid))
            for t in ("pud_forecast_stream", "pud_forecast_month", "location_water_analog"):
                q(f"ANALYZE box.{t}")
            print(f"rows written ({len(st)} water streams, {len(an)} water analogs, {nf} without water) ({time.time() - t0:.0f} s); identity", flush=True)
            # identity
            after = q(_OILGAS, (rid,)).fetchall()
            chk(after == before, f"oil / gas stream rows unchanged (count + ordered md5 of every row): {after}")
            ma = q("SELECT count(*) FROM box.pud_forecast_month WHERE run_id = %s AND stream <> 'water'", (rid,)).fetchone()[0]
            chk(ma == mbefore, f"oil / gas month rows unchanged ({ma} = {mbefore})")
            nw = q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'water'", (rid,)).fetchone()[0]
            chk(nw == len(pf) - nf and nf == 0, f"water rows = covered + covered_provisional ({nw} = {len(pf)}; {nf} locations without water)")
            grp, bad = q("""WITH m AS MATERIALIZED (SELECT location_id, count(*) n, sum(volume) v FROM box.pud_forecast_month
                                                 WHERE run_id = %s AND stream = 'water' GROUP BY 1)
                            SELECT count(*), count(*) FILTER (WHERE m.n <> 600 OR abs(m.v - s.eur) > 1e-3 * s.eur)
                            FROM m JOIN box.pud_forecast_stream s ON s.run_id = %s AND s.location_id = m.location_id AND s.stream = 'water'""",
                         (rid, rid)).fetchone()
            chk(grp == nw and bad == 0, f"every water stream has 600 months summing to its eur within 0.1 % ({grp} groups, {bad} off)")
            tiers = dict(q("SELECT tier, count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'water' GROUP BY 1", (rid,)).fetchall())
            val_expected = sum(1 for s, (_, c) in pf.items() if water[s]["group"] in wp.VALIDATED_WATER_GROUPS and c == "covered")
            chk(tiers.get("validated", 0) == val_expected, f"validated water = WCA + BS2_S covered rows ({tiers.get('validated', 0)} = {val_expected}); tiers {tiers}")
            na = q("SELECT min(c), max(c), count(*) FROM (SELECT count(*) c FROM box.location_water_analog WHERE run_id = %s GROUP BY location_id) x",
                   (rid,)).fetchone()
            chk(na[0] is not None and na[0] >= 3 and na[2] == nw, f"every water location has >= 3 named water analogs (min {na[0]}, max {na[1]}, {na[2]} locations)")
            fb = q("SELECT count(*) FROM box.pud_forecast_stream WHERE run_id = %s AND stream = 'water' AND params->>'source' = 'calculated_fallback'",
                   (rid,)).fetchone()[0]
            print(f"    info calculated-fallback water locations: {fb}", flush=True)
            if fails:
                conn.rollback()
                raise SystemExit(f"identity FAILED, rolled back: {fails}")
        conn.commit()
    finally:
        conn.close()
    print(f"stored water on run_id {rid}: {nw} streams, tiers {tiers} ({time.time() - t0:.0f} s)", flush=True)
    return 0


def w_json(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: w_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [w_json(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    return x


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--run-pkl", type=Path, default=Path("runs") / "box9" / "run.pkl")
    b.add_argument("--out", type=Path, default=Path("runs") / "box12b")
    b.add_argument("--groups", default=None)
    b.add_argument("--workers", type=int, default=None)
    s = sub.add_parser("store")
    s.add_argument("--out", type=Path, default=Path("runs") / "box12b")
    s.add_argument("--run-id", type=int, default=None)
    a = ap.parse_args(argv)
    return cmd_build(a) if a.cmd == "build" else cmd_store(a)


if __name__ == "__main__":
    sys.exit(main())
