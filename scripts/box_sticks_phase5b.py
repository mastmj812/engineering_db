"""BOX sticks gate 5b: the authored nightly reconciliation measured (docs/box_sticks/phase5b-2026-11-19/BARS.md).

    python -m scripts.box_sticks_phase5b live  --run <dir> --out <dir>                 # E1 to E3: etl.box_recon's SQL, read-only, against the reference
    python -m scripts.box_sticks_phase5b stale --before <run> --truth <run> --out <dir>   # E4: the stale estimate against a regeneration

Read-only: `live` runs etl.box_recon.run(write=False) (SET TRANSACTION READ ONLY) and reads the record sets and today's
wells; `stale` reads files only. Nothing is written to the warehouse. `reference` is the Python statement of the rule the
module's SQL implements (EPSG:3083 metres), built on the 5a reference.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from box.sticks.core import well_legs
from etl import box_recon
from scripts import box_sticks_phase5a as p5

DOC = Path(__file__).resolve().parent.parent / "docs" / "box_sticks" / "phase5b-2026-11-19"
OUT = ("producing", "conflict")


def wells_frame(run: Path) -> pd.DataFrame:
    """Today's wells, classed, on the line the nightly reads: a surface step-out dropped; a real U-turn on its survey path."""
    w = p5.classify(p5.cmd_wells(run))
    w["geom"] = [g if u else well_legs(g)[0] for g, u in zip(w["geom"], w["is_uturn"].fillna(False), strict=True)]
    return w


def reference(sticks: pd.DataFrame, wells: pd.DataFrame, gen: dict, mirror: dict) -> pd.DataFrame:
    """One row per stick: status (open / permitted / pending / producing / conflict), crowded, the wells. Only a producing
    well takes a stick out; a drilled-not-producing well sets pending, a permit sets permitted."""
    a, _ = p5.judge(sticks, wells[wells["cls"].isin(["producing", "permit"])], gen, mirror, flat=True)
    pend = wells[wells["cls"] == "drilled"].assign(cls="permit")
    if pend.empty:
        s = a.assign(pending_api10=None)
    else:
        b, _ = p5.judge(sticks, pend, gen, mirror, flat=True)
        s = a.merge(b[["key", "permit_api10"]].rename(columns={"permit_api10": "pending_api10"}), on="key", how="left")
    s["status"] = np.where(s["status"].isin(OUT), s["status"], np.where(s["pending_api10"].notna(), "pending", s["status"]))
    s["crowded"] = s["crowd_api10"].notna() & ~s["status"].isin(OUT)
    s["counts_as_inventory"] = ~s["status"].isin(OUT) & ~s["crowded"]
    return s


def record_mirror() -> dict:
    dsu = p5._read("SELECT d.pad_id FROM box.location_set_dsu d JOIN box.location_set t USING (set_id) WHERE t.is_record AND d.wca_class = 'co-developed'")
    bl = p5._read("SELECT b.pad_id, b.formation_blueox, b.target_tvd_ft FROM box.location_set_bench b JOIN box.location_set t USING (set_id) "
                  "WHERE t.is_record AND b.no_row_reason = '' AND b.target_tvd_ft IS NOT NULL")
    return {"codev": set(dsu["pad_id"].astype(int)), "landing": {(int(r.pad_id), r.formation_blueox): float(r.target_tvd_ft) for r in bl.itertuples()}}


def cmd_live(run: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    res = box_recon.run(write=False)
    secs = time.time() - t0
    Q = pd.DataFrame(res["rows"], columns=box_recon.STATUS_COLS)
    Q["key"] = Q["location_id"].astype(int)
    stale = pd.DataFrame(res["stale_rows"], columns=box_recon.STALE_COLS)
    plan = "\n".join(p5._read("EXPLAIN " + box_recon.JUDGE_SQL).iloc[:, 0])
    (out / "judge_explain.txt").write_text(plan, encoding="utf-8")

    rec = p5._read(p5._REC_SQL)
    gen = {r.basin: r.gen for r in rec.itertuples()}
    st = p5._read(p5._STICKS_SQL)
    st["key"] = st["location_id"].astype(int)
    st["geom"] = shapely.from_wkt(st["wkt"].to_numpy())
    w = wells_frame(run)
    R = reference(st, w, gen, record_mirror())
    c = R[["key", "basin", "status", "crowded", "matched_api10"]].merge(Q[["key", "status", "crowded", "matched_api10"]], on="key", suffixes=("_py", "_sql"))
    agree = c.groupby("basin").apply(lambda d: pd.Series({
        "sticks": len(d), "same_status_pct": round(100 * float((d["status_py"] == d["status_sql"]).mean()), 3),
        "same_crowded_pct": round(100 * float((d["crowded_py"].astype(bool) == d["crowded_sql"].astype(bool)).mean()), 3),
        "status_differs": int((d["status_py"] != d["status_sql"]).sum()),
        "crowded_differs": int((d["crowded_py"].astype(bool) != d["crowded_sql"].astype(bool)).sum())}), include_groups=False).reset_index()
    c[(c["status_py"] != c["status_sql"]) | (c["crowded_py"].astype(bool) != c["crowded_sql"].astype(bool))].to_csv(out / "live_sql_vs_reference_diff.csv", index=False)
    day0 = Q.groupby("basin").apply(lambda d: pd.Series({
        "sticks": len(d), **{s: int((d["status"] == s).sum()) for s in ("open", "permitted", "pending", "producing", "conflict")},
        "crowded": int(d["crowded"].astype(bool).sum()), "inventory": int(d["counts_as_inventory"].astype(bool).sum()),
        "producing_or_conflict_pct": round(100 * float(d["status"].isin(OUT).mean()), 3), "crowded_pct": round(100 * float(d["crowded"].astype(bool).mean()), 3)}),
        include_groups=False).reset_index()
    day0.to_csv(out / "live_day0_status_counts.csv", index=False)
    Q[Q["status"].isin(OUT) | Q["crowded"].astype(bool) | Q["status"].isin(["pending"])].drop(columns=["key"]).to_csv(out / "live_day0_not_open.csv", index=False)
    stale.to_csv(out / "live_day0_stale.csv", index=False)
    summ = {"record_sets": json.loads(rec.drop(columns=["gen"]).to_json(orient="records", date_format="iso")), "predicate_version": box_recon.VERSION,
            "wells_pulled_at": p5.cmd_wells(run).attrs.get("pulled_at"), "seconds_read_only_pass": round(secs, 1),
            "uses_stick_index": "box_location_stick_geog_gix" in plan, "agreement": agree.to_dict("records"), "day0": day0.to_dict("records"),
            "stale_dsu_bench": len(stale)}
    (out / "live_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    print(agree.to_string(index=False), "\n", day0.T.to_string(), "\n", f"seconds {secs:.1f}; stale rows {len(stale)}; index {summ['uses_stick_index']}", flush=True)


def cmd_stale(before: Path, truth: Path, out: Path) -> None:
    """E4. `before` = a hindcast with later wells hidden; `truth` = the same inputs regenerated with the hidden producers back."""
    out.mkdir(parents=True, exist_ok=True)
    st, gen = p5.hind_sticks(before)
    mirror = p5.hind_mirror(before)
    w = wells_frame(before)
    hid = set(pd.read_csv(before / "hidden.csv", dtype={"api10": str})["api10"])
    prod = w[w["cls"] == "producing"]
    new = prod[prod["api10"].astype(str).isin(hid)]
    S = reference(st, prod, gen, mirror)                                   # every producer, as the nightly sees them
    S["by_new"] = S["matched_api10"].fillna(S["crowd_api10"]).astype(str).isin(set(new["api10"].astype(str))) & ~S["counts_as_inventory"]
    taken = S[S["by_new"]].groupby(["pad_id", "bench"]).size().rename("sticks_out")

    def bench_counts(r: Path) -> pd.DataFrame:
        rows = []
        for b in p5.BASINS:
            art = pd.read_pickle(r / f"set_{b}.pkl")
            rows += [{"basin": b, "pad_id": int(x["pad_id"]), "bench": x["formation_blueox"], "sticks": int(x["sticks"])} for x in art["bench_rows"]]
        return pd.DataFrame(rows)

    h, t = bench_counts(before), bench_counts(truth)
    d = h.merge(t, on=["basin", "pad_id", "bench"], how="outer", suffixes=("_h", "_t")).fillna({"sticks_h": 0, "sticks_t": 0})
    pads = pd.read_pickle(before / "cache" / "pads.pkl")
    pads["geom"] = shapely.from_wkt(pads["wkt"].to_numpy())
    lat, pg = new["geom"].to_numpy(), pads["geom"].to_numpy()
    a, k = shapely.STRtree(pg).query(lat, predicate="intersects")
    sh = shapely.length(shapely.intersection(lat[a], pg[k])) / shapely.length(lat[a])
    ok = (sh >= box_recon.MEMBER) & (pads["basin"].to_numpy()[k] == new["basin"].to_numpy()[a])
    mem = pd.DataFrame({"pad_id": pads["pad_id"].to_numpy()[k[ok]].astype(int), "bench": new["code"].to_numpy()[a[ok]]})
    sig = mem.groupby(["pad_id", "bench"]).size().rename("new_producers")
    d = d.merge(sig.reset_index(), on=["pad_id", "bench"], how="left").merge(taken.reset_index(), on=["pad_id", "bench"], how="left")
    d = d.fillna({"new_producers": 0, "sticks_out": 0})
    d["est_stick_level"] = d["sticks_h"] - d["sticks_out"]
    d["est_subtraction"] = (d["sticks_h"] - d["new_producers"]).clip(lower=0)
    d["est_sticks"] = np.minimum(d["est_stick_level"], d["est_subtraction"])           # the stale row's estimate
    d.to_csv(out / "stale_dsu_bench.csv", index=False)
    rows = []
    for b in p5.BASINS:
        T = d[(d["basin"] == b) & (d["new_producers"] > 0) & (d["sticks_h"] > 0)]
        r = {"basin": b, "touched_dsu_bench": len(T), "new_producers": int(T["new_producers"].sum()), "sticks_before": int(T["sticks_h"].sum()),
             "sticks_regenerated": int(T["sticks_t"].sum())}
        for e in ("sticks", "stick_level", "subtraction"):
            err = T[f"est_{e}"] - T["sticks_t"]
            r |= {f"{e}_total": int(T[f"est_{e}"].sum()), f"{e}_total_err_pct": round(100 * float(err.sum()) / max(float(T["sticks_t"].sum()), 1.0), 1),
                  f"{e}_mae": round(float(err.abs().mean()), 3), f"{e}_exact_pct": round(100 * float((err == 0).mean()), 1)}
        rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(out / "stale_bars.csv", index=False)
    (out / "stale_summary.json").write_text(json.dumps(res.to_dict("records"), indent=1, default=str), encoding="utf-8")
    print(res.T.to_string(), flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("live", "stale"))
    ap.add_argument("--run", type=Path)
    ap.add_argument("--before", type=Path)
    ap.add_argument("--truth", type=Path)
    ap.add_argument("--out", type=Path, default=DOC)
    a = ap.parse_args(argv)
    if a.step == "live":
        cmd_live(a.run, a.out)
    else:
        cmd_stale(a.before, a.truth, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
