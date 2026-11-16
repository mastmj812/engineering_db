"""BOX sticks, after gate 3b: trials of three generator changes, each measured against the generator of record.

Read-only; nothing is stored and no switch is turned on by this script.

    python -m scripts.box_sticks_phase3_trials --out docs/box_sticks/phase3c-<date> --cache <cache>

  wcxy_chain     Delaware WCXY takes the full landing-depth chain (today: direct control only)
  check_carried  a carried depth implausibly far from a direct bench in the same DSU gets no row (Cfg.check_carried)
  two_levels     a straight DSU x bench whose own wells show two landings alternates rows between them (Cfg.two_levels)
plus a count of short polygons whose wells run past the polygon (classed U-turn today).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from box import tag_scoreboard as sb
from box.sticks import reads
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1c as p1c
from scripts import box_sticks_phase3_backtest as bt
from scripts import box_sticks_phase3_pilot as p3

CHAIN_COLS = ["z", "rung", "how", "expected_median_ft", "expected_p90_ft", "near_mi"]


def wcxy_frame(F: dict, cache: Path, before: pd.Timestamp | None) -> dict:
    """The frame with WCXY's landing depth rebuilt on the full chain (evidence before `before`, if given)."""
    d = p0.pull(cache)
    ev = p0.evidence(d["wells"], d["rule"]).merge(pd.read_pickle(cache / "p2a_screen.pkl"), on="api10", how="left")
    ev = ev[ev["screen"] == "keep"]
    if before is not None:
        ev = ev[ev["api10"].astype(str).isin(set(F["u"]["api10"].astype(str)))]
    thick, far = p1c.rankings()
    old = p1c.CHAIN_DIRECT_ONLY
    p1c.CHAIN_DIRECT_ONLY = set()
    try:
        ch = p1c.build_chain(ev.reset_index(drop=True), d["extents"], F["pads"], sb.bench_order(), thick, far)
    finally:
        p1c.CHAIN_DIRECT_ONLY = old
    new = ch[ch["code"] == "WCXY"].set_index(["basin", "pad_id"])[CHAIN_COLS]
    db = F["db"].copy()
    m = (db["code"] == "WCXY").to_numpy()
    key = pd.MultiIndex.from_frame(db.loc[m, ["basin", "pad_id"]])
    for c in CHAIN_COLS:
        db.loc[m, c] = new[c].reindex(key).to_numpy()
    db["rung"] = db["rung"].fillna("none")
    return dict(F) | {"db": db}


def tally(runs: dict, area: dict | None = None) -> dict:
    st = pd.DataFrame([{"pad_id": p, "bench": s["bench"], "legs": s["n_legs"]} for p, (_d, r) in runs.items() for s in r.sticks])
    b = pd.DataFrame([x for _p, (_d, r) in runs.items() for x in r.benches])
    out = {"sticks": len(st), "legs": int(st["legs"].sum()) if len(st) else 0,
           "bench_no_row": b.loc[b["no_row_reason"] != "", "no_row_reason"].value_counts().to_dict(),
           "sticks_by_bench": st.groupby("bench").size().to_dict() if len(st) else {}}
    if area and len(st):
        out["sticks_by_area"] = st.groupby(st["pad_id"].map(area)).size().to_dict()
    return out


def bars_short(B: dict) -> dict:
    return {"T1_pct": B["T1"]["pct"], "T1_by_area": {r["area"]: r["pct"] for r in B["T1"]["by_area"]}, "T2_pct": B["T2"]["pct"],
            "T3_within_1_pct": B["T3"]["within_1_pct"], "T3_ratio": B["T3"]["ratio"], "T4_pct": B["T4"]["pct"],
            "T5_direct": [B["T5"]["direct"]["pairs"], B["T5"]["direct"]["median_abs_ft"], B["T5"]["direct"]["within_150_pct"]],
            "T5_carried": {k: [v["pairs"], v["median_abs_ft"], v["ratio"]] for k, v in B["T5"]["carried"].items()}}


def depth_hit(S: dict, units: set) -> dict:
    """Hidden wells with depth evidence in the given DSU x bench: share with a leg inside the sideways tolerance AND within 150 ft."""
    P, Wk = S["pairs"], S["Wk"]
    w = Wk[Wk["depth_ft"].notna() & np.array([(p, c) in units for p, c in zip(Wk["pad_id"], Wk["code"], strict=True)], bool)]
    q = P[P["well"].isin(set(w["api10"])) & P["ok_side"]].copy()
    q["near"] = q["dz_raw"].astype(float).abs() <= 150.0
    got = q.groupby("well")["near"].any()
    return {"wells": len(w), "with_a_leg_alongside": int(len(got)), "leg_within_150_ft": int(got.sum()),
            "median_abs_dz_nearest_level_ft": round(float(q.groupby("well")["dz_raw"].apply(lambda v: v.astype(float).abs().min()).median()), 1) if len(q) else None}


def crossing(F: dict, runs_meta: pd.DataFrame) -> dict:
    """U-turn DSUs whose own wells are much longer than the DSU's straight row: a short polygon drilled across its line."""
    out = {}
    for name, df, mem in (("producer", F["u"], F["wm"]), ("preprod", F["pre"], F["pm"])):
        ln = shapely.length(df["geom"].to_numpy()) * bt.FT
        m = mem.assign(len_ft=ln[mem["i"].to_numpy()])
        out[name] = m
    m = pd.concat(out.values(), ignore_index=True).merge(runs_meta[["pad_id", "basin", "well_type", "straight_ft", "sticks"]], on="pad_id")
    m = m[m["well_type"] == "uturn"]
    m["long"] = m["len_ft"] >= 1.3 * m["straight_ft"]
    g = m.groupby(["basin", "pad_id"]).agg(wells=("i", "size"), long=("long", "sum"), sticks=("sticks", "first")).reset_index()
    res = {}
    for b, x in g.groupby("basin"):
        k = x[x["long"] >= 2]
        res[b] = {"uturn_dsus_with_wells": len(x), "with_2plus_wells_30pct_longer_than_the_dsu_row": len(k), "wells_in_them": int(k["wells"].sum()),
                  "long_wells_in_them": int(k["long"].sum()), "box_sticks_in_them": int(k["sticks"].sum()),
                  "with_5plus": int((x["long"] >= 5).sum())}
    return res


def _plain(x):
    """JSON keys must be strings: a (basin, code) key becomes 'basin / code'."""
    if isinstance(x, dict):
        return {(" / ".join(map(str, k)) if isinstance(k, tuple) else str(k)): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    return x


def run(out: Path, cache: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    full = p3.build_frame(cache)
    Fb, mb = bt.backtest_frame(cache)
    area = {int(p): n for n, a in p3.AREAS.items() for p in p3.area_pads(full, a)}
    ids = sorted(area)
    ctx, ctx_bt = reads.Context(cache), reads.Context(cache, frame=Fb, measured=mb)
    R: dict = {"generator": "box_sticks_0.7_pilot + switches", "tags": full["tags"], "pulled": full["pulled"]}

    base_today, base_bt = bt.generate(ctx, ids), bt.generate(ctx_bt, ids)
    S0 = bt.score(full, ctx, base_bt, area)
    R["base"] = {"pilot_today": tally(base_today, area), "backtest": bars_short(bt.bars(S0)[0])}

    # ---- two levels
    t_today, t_bt = bt.generate(ctx, ids, two_levels=True), bt.generate(ctx_bt, ids, two_levels=True)
    S1 = bt.score(full, ctx, t_bt, area)
    used_bt = {(p, b["code"]) for p, (_d, r) in t_bt.items() for b in r.benches if b.get("levels")}
    used_today = {(p, b["code"]) for p, (_d, r) in t_today.items() for b in r.benches if b.get("levels")}
    flagged = {k for k in ctx.levels if k[0] in area}
    R["two_levels"] = {"pilot_today": tally(t_today, area), "backtest": bars_short(bt.bars(S1)[0]),
                       "pilot_units_flagged_today": len(flagged), "pilot_units_using_two_levels_today": len(used_today),
                       "backtest_units_using_two_levels": len(used_bt),
                       "hidden_wells_depth_in_those_units": {"single_landing": depth_hit(S0, used_bt), "two_levels": depth_hit(S1, used_bt)},
                       "pilot_sticks_in_units_today": {"single_landing": sum(b["legs_placed"] for p, (_d, r) in base_today.items() for b in r.benches if (p, b["code"]) in used_today),
                                                       "two_levels": sum(b["legs_placed"] for p, (_d, r) in t_today.items() for b in r.benches if (p, b["code"]) in used_today)}}
    basin_two = {}
    for basin in ("delaware", "midland"):
        pids = sorted({k[0] for k in ctx.levels if ctx.pads.loc[k[0], "basin"] == basin})
        a, b = bt.generate(ctx, pids), bt.generate(ctx, pids, two_levels=True)
        used = {(p, x["code"]) for p, (_d, r) in b.items() for x in r.benches if x.get("levels")}
        basin_two[basin] = {"dsus_with_a_flagged_bench": len(pids), "flagged_dsu_bench": sum(1 for k in ctx.levels if k[0] in set(pids)),
                            "using_two_levels": len(used),
                            "legs_in_those_units_single": sum(x["legs_placed"] for p, (_d, r) in a.items() for x in r.benches if (p, x["code"]) in used),
                            "legs_in_those_units_two_levels": sum(x["legs_placed"] for p, (_d, r) in b.items() for x in r.benches if (p, x["code"]) in used),
                            "sticks_all_benches_single": tally(a)["sticks"], "sticks_all_benches_two_levels": tally(b)["sticks"]}
    R["two_levels"]["basin_wide_flagged_dsus"] = basin_two

    # ---- carried depth check
    c_today, c_bt = bt.generate(ctx, ids, check_carried=True), bt.generate(ctx_bt, ids, check_carried=True)
    R["check_carried"] = {"pilot_today": tally(c_today, area), "backtest": bars_short(bt.bars(bt.score(full, ctx, c_bt, area))[0])}
    db = full["db"]
    car = db[db["rung"].isin(["thickness", "bracket", "offset"])]
    pids = sorted(set(car["pad_id"]))
    hit = []
    for pid in pids:
        d = ctx.dsu(int(pid))
        hit += [(int(pid), d.basin, b.code, b.rung, b.depth_check) for b in d.benches if b.depth_check]
    H = pd.DataFrame(hit, columns=["pad_id", "basin", "code", "rung", "why"])
    H.to_csv(out / "carried_implausible.csv", index=False)
    aff = sorted(set(H["pad_id"]))
    a, b = bt.generate(ctx, aff), bt.generate(ctx, aff, check_carried=True)
    R["check_carried"]["basin_wide"] = {"carried_dsu_bench": len(car), "flagged_implausible": len(H), "dsus_affected": len(aff),
                                        "flagged_by_basin_code": H.groupby(["basin", "code"]).size().sort_values(ascending=False).head(14).to_dict(),
                                        "in_affected_dsus_before": tally(a), "in_affected_dsus_after": tally(b)}

    # ---- WCXY on the full chain
    Fw, Fwb = wcxy_frame(full, cache, None), wcxy_frame(Fb, cache, bt.CUTOFF)
    ctx_w, ctx_wb = reads.Context(cache, frame=Fw), reads.Context(cache, frame=Fwb, measured=mb)
    w_today, w_bt = bt.generate(ctx_w, ids), bt.generate(ctx_wb, ids)
    R["wcxy_chain"] = {"pilot_today": tally(w_today, area), "backtest": bars_short(bt.bars(bt.score(Fw, ctx_w, w_bt, area))[0])}
    x0, x1 = full["db"][full["db"]["code"] == "WCXY"], Fw["db"][Fw["db"]["code"] == "WCXY"]
    wp = sorted(set(x0["pad_id"]))
    a, b = bt.generate(ctx, wp), bt.generate(ctx_w, wp)
    car = x1[x1["rung"].isin(["thickness", "bracket", "offset"])]
    R["wcxy_chain"]["basin_wide"] = {"wcxy_dsu_bench": len(x0), "rung_before": x0["rung"].value_counts().to_dict(), "rung_after": x1["rung"].value_counts().to_dict(),
                                     "carried_expected_median_ft": round(float(car["expected_median_ft"].median()), 0) if len(car) else None,
                                     "carried_expected_p90_ft": round(float(car["expected_p90_ft"].median()), 0) if len(car) else None,
                                     "in_wcxy_dsus_before": tally(a), "in_wcxy_dsus_after": tally(b)}

    # ---- short polygons drilled across their line
    meta = pd.concat([pd.read_csv(f) for f in sorted((cache.parent / "basin").glob("dsus_*.csv"))], ignore_index=True) if (cache.parent / "basin").exists() else None
    if meta is not None:
        R["short_polygons_drilled_across"] = crossing(full, meta)

    R = _plain(R)
    (out / "trials_summary.json").write_text(json.dumps(R, indent=1, default=str), encoding="utf-8")
    print(json.dumps(R, indent=1, default=str))
    return R


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


