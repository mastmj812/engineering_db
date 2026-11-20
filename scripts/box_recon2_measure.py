"""box_recon_2 measured against its bars (docs/box_sticks/recon2-2026-11-20/BARS.md). READ-ONLY on the warehouse.

    python -m scripts.box_recon2_measure live --run <dir> --out <dir>                    # R1 to R4
    python -m scripts.box_recon2_measure pair --before <run> --truth <run> --out <dir>   # R5 to R7 (files only)
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import shapely

from box.sticks import identity
from etl import box_recon as br
from etl.db import get_connection
from scripts import box_sticks_phase5a as p5
from scripts import box_sticks_phase5b as p5b

OUT = ("producing", "conflict")


def _judge_ro(sql: str) -> pd.DataFrame:
    """One judge SQL in a READ ONLY transaction, rolled back."""
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET LOCAL statement_timeout = '{br.TIMEOUT}'")
            rows = cur.execute(sql).fetchall()
        conn.rollback()
    q = pd.DataFrame(rows, columns=br.STATUS_COLS)
    q["key"] = q["location_id"].astype(int)
    return q


def _day0(q: pd.DataFrame) -> list[dict]:
    rows = []
    for b, d in q.groupby("basin"):
        rows.append({"basin": b, "sticks": len(d), **{s: int((d["status"] == s).sum()) for s in ("open", "permitted", "pending", "producing", "conflict")},
                     "crowded": int(d["crowded"].astype(bool).sum()), "inventory": int(d["counts_as_inventory"].astype(bool).sum()),
                     "producing_or_conflict_pct": round(100 * float(d["status"].isin(OUT).mean()), 3),
                     "crowded_pct": round(100 * float(d["crowded"].astype(bool).mean()), 3)})
    return rows


def cmd_live(run: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    res = br.run(write=False)                                               # rule 2: status + stale, as the nightly evaluates it
    secs = round(time.monotonic() - t0, 1)
    q2 = pd.DataFrame(res["rows"], columns=br.STATUS_COLS)
    q2["key"] = q2["location_id"].astype(int)
    q1 = _judge_ro(br.RULE1_JUDGE_SQL)
    plan = "\n".join(p5._read("EXPLAIN " + br.JUDGE_SQL).iloc[:, 0])
    (out / "judge_explain.txt").write_text(plan, encoding="utf-8")

    rec = p5._read(p5._REC_SQL)
    gen = {r.basin: r.gen for r in rec.itertuples()}
    st = p5._read(p5._STICKS_SQL)
    st["key"] = st["location_id"].astype(int)
    st["geom"] = shapely.from_wkt(st["wkt"].to_numpy())
    ref = p5b.reference(st, p5b.wells_frame(run), gen, p5b.record_mirror(), rule=2)
    c = ref[["key", "basin", "status", "crowded"]].merge(q2[["key", "status", "crowded"]], on="key", suffixes=("_py", "_sql"))
    agree = [{"basin": b, "sticks": len(d), "same_status_pct": round(100 * float((d["status_py"] == d["status_sql"]).mean()), 3),
              "same_crowded_pct": round(100 * float((d["crowded_py"].astype(bool) == d["crowded_sql"].astype(bool)).mean()), 3),
              "status_differs": int((d["status_py"] != d["status_sql"]).sum()),
              "crowded_differs": int((d["crowded_py"].astype(bool) != d["crowded_sql"].astype(bool)).sum())} for b, d in c.groupby("basin")]
    c[(c["status_py"] != c["status_sql"]) | (c["crowded_py"].astype(bool) != c["crowded_sql"].astype(bool))].to_csv(out / "live_sql_vs_reference_diff.csv", index=False)

    # R4: every stick whose status differs between the two rules, with the rule-1 well's depth offset as the record set read it
    m = q1.merge(q2, on="key", suffixes=("_r1", "_r2"))
    diff = m[m["status_r1"] != m["status_r2"]].copy()
    dep = p5._read("SELECT w.set_id, w.api10, w.depth_ft FROM box.location_set_well w JOIN box.location_set t USING (set_id) WHERE t.is_record")
    diff = diff.merge(st[["key", "target_tvd_ft"]], on="key").merge(
        dep.rename(columns={"set_id": "set_id_r1", "api10": "matched_api10_r1"}), on=["set_id_r1", "matched_api10_r1"], how="left")
    diff["dz_ft"] = diff["depth_ft"].astype(float) - diff["target_tvd_ft"].astype(float)
    diff["explained"] = diff["status_r1"].isin(OUT) & (diff["dz_ft"].abs() > 150) & (diff["dz_ft"].abs() <= 500)
    diff["other_way"] = ~diff["status_r1"].isin(OUT) & diff["status_r2"].isin(OUT)
    cols = ["key", "basin_r1", "formation_blueox_r1", "status_r1", "status_r2", "matched_api10_r1", "match_basis_r1", "match_overlap_r1", "crowded_r1", "crowded_r2",
            "counts_as_inventory_r1", "counts_as_inventory_r2", "dz_ft", "explained", "other_way"]
    diff[cols].to_csv(out / "live_rule1_vs_rule2.csv", index=False)
    inv1, inv2 = m["counts_as_inventory_r1"].astype(bool), m["counts_as_inventory_r2"].astype(bool)
    summ = {"predicate_version": br.VERSION, "set_ids": res["set_ids"], "seconds_read_only_pass": secs, "uses_stick_index": "box_location_stick_geog_gix" in plan,
            "R1_agreement": agree, "R3_day0_rule2": _day0(q2), "day0_rule1": _day0(q1), "stale_dsu_bench": res["stale_dsu_bench"],
            "R4": {"sticks_differ": len(diff), "explained": int(diff["explained"].sum()), "other_way": int(diff["other_way"].sum()),
                   "unexplained": int((~diff["explained"]).sum()),
                   "transitions": diff.groupby(["basin_r1", "status_r1", "status_r2"]).size().rename("sticks").reset_index().to_dict("records"),
                   "crowded_flag_differs": int((m["crowded_r1"].astype(bool) != m["crowded_r2"].astype(bool)).sum()),
                   "inventory_back_in": int((~inv1 & inv2).sum()), "inventory_newly_out": int((inv1 & ~inv2).sum())}}
    (out / "live_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summ, indent=1, default=str), flush=True)
    print(diff[~diff["explained"]][cols].to_string(index=False), flush=True)


def _id_sticks(run: Path) -> list[identity.Stick]:
    out = []
    for b in p5.BASINS:
        for s in pd.read_pickle(run / f"set_{b}.pkl")["sticks"]:
            legs = tuple((p5.TO_3083.transform(*leg["heel_lonlat"]), p5.TO_3083.transform(*leg["toe_lonlat"])) for leg in s["legs"])
            out.append(identity.Stick(key=s["well_name"], pad_id=int(s["pad_id"]), bench=s["bench"], legs=legs, slot=1))
    return out


def cmd_pair(before: Path, truth: Path, out: Path) -> None:
    """R5 to R7. `before` = the hindcast with later producers hidden; `truth` = the same inputs regenerated with them back."""
    out.mkdir(parents=True, exist_ok=True)
    st, gen = p5.hind_sticks(before)
    mirror = p5.hind_mirror(before)
    w = p5b.wells_frame(before)
    hid = set(pd.read_csv(before / "hidden.csv", dtype={"api10": str})["api10"])
    prod = w[w["cls"] == "producing"]
    new = prod[prod["api10"].astype(str).isin(hid)]
    newset = set(new["api10"].astype(str))
    cw = identity.crosswalk(_id_sticks(before), _id_sticks(truth))
    survived = {v[0] for v in cw["carried"].values()}                        # before-sticks the regeneration still has
    # DSU x bench holding a hidden producer (>= 30 % of its lateral inside the DSU), as the stale row defines it
    pads = pd.read_pickle(before / "cache" / "pads.pkl")
    pads["geom"] = shapely.from_wkt(pads["wkt"].to_numpy())
    lat, pg = new["geom"].to_numpy(), pads["geom"].to_numpy()
    a, k = shapely.STRtree(pg).query(lat, predicate="intersects")
    sh = shapely.length(shapely.intersection(lat[a], pg[k])) / shapely.length(lat[a])
    ok = (sh >= br.MEMBER) & (pads["basin"].to_numpy()[k] == new["basin"].to_numpy()[a])
    touched = set(zip(pads["pad_id"].to_numpy()[k[ok]].astype(int), new["code"].to_numpy()[a[ok]], strict=True))
    res, per_rule, took_by = [], {}, {}
    for rule in (1, 2):
        s = p5b.reference(st, prod, gen, mirror, rule=rule)
        s["well"] = s["matched_api10"].fillna(s["crowd_api10"]).astype(str)
        s["by_new"] = ~s["counts_as_inventory"] & s["well"].isin(newset)
        s["touched"] = [(int(p), b) in touched for p, b in zip(s["pad_id"], s["bench"], strict=True)]
        s["survived"] = s["key"].isin(survived)
        per_rule[rule] = s
        for b in p5.BASINS:
            d = s[s["basin"] == b]
            out_new, kept = d[d["by_new"]], d[d["touched"] & d["counts_as_inventory"]]
            nb = set(new.loc[new["basin"] == b, "api10"].astype(str))
            took = set(out_new["well"]) & nb
            took_by[(rule, b)] = took
            res.append({"rule": rule, "basin": b, "taken_out_by_hidden": len(out_new), "of_those_gone_in_regen": int((~out_new["survived"]).sum()),
                        "taken_out_agree_pct": round(100 * float((~out_new["survived"]).mean()), 1) if len(out_new) else None,
                        "left_in_touched": len(kept), "of_those_still_in_regen": int(kept["survived"].sum()),
                        "left_in_agree_pct": round(100 * float(kept["survived"].mean()), 1) if len(kept) else None,
                        "hidden_producers": len(nb), "capture_wells": len(took), "capture_pct": round(100 * len(took) / max(len(nb), 1), 1)})
    r = pd.DataFrame(res)
    r.to_csv(out / "pair_bars.csv", index=False)
    j = per_rule[1][["key", "basin", "pad_id", "bench", "by_new", "survived", "well", "status"]].merge(
        per_rule[2][["key", "by_new", "status", "counts_as_inventory"]], on="key", suffixes=("_r1", "_r2"))
    back = j[j["by_new_r1"] & ~j["by_new_r2"]]
    back.to_csv(out / "pair_put_back_by_rule2.csv", index=False)
    put = [{"basin": b, "put_back": len(d), "still_in_regen": int(d["survived"].sum()),
            "still_in_regen_pct": round(100 * float(d["survived"].mean()), 1) if len(d) else None} for b, d in back.groupby("basin")]
    lost = [{"basin": b, "wells_lost": sorted(took_by[(1, b)] - took_by[(2, b)]), "wells_gained": sorted(took_by[(2, b)] - took_by[(1, b)])} for b in p5.BASINS]
    (out / "pair_summary.json").write_text(json.dumps({"bars": res, "put_back": put, "capture": lost, "stopped_in_regen": len(cw["stopped"]),
                                                       "carried": len(cw["carried"])}, indent=1, default=str), encoding="utf-8")
    pd.set_option("display.width", 250)
    print(r.T.to_string(), "\n", pd.DataFrame(put).to_string(index=False), "\n", [(x["basin"], len(x["wells_lost"]), len(x["wells_gained"])) for x in lost], flush=True)
    p5b.cmd_stale(before, truth, out)                                       # R7: the stale estimate under the module's rule (reference default = rule 2)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("live", "pair"))
    ap.add_argument("--run", type=Path)
    ap.add_argument("--before", type=Path)
    ap.add_argument("--truth", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.step == "live":
        cmd_live(a.run, a.out)
    else:
        cmd_pair(a.before, a.truth, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
