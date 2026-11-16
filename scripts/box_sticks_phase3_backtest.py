"""BOX sticks phase 3a step 4: the back-test of docs/box_sticks/phase3a-2026-11-14/BARS.md and the pilot report.

Read-only: everything comes from the phase 3 cache; outputs are files. Nothing is written to the warehouse.

    python -m scripts.box_sticks_phase3_backtest --out docs/box_sticks/phase3a-2026-11-14/backtest --cache <cache>

Back-test: every producer with first production on or after the cutoff and every well not yet producing is hidden
from everything the generator reads. The spacing gaps (phase 2a measure), the blended spacing surface, the landing
chain (phase 1c) and the regional tables (azimuth, WCA co-development, two landings) are rebuilt without them. Not
hidden, as BARS.md states: live tags, the 2026Q3 DSU polygons, the BOX extents, the thickness tables, the two-part
depth screen and the constants.

Report (today's wells): per pilot area and bench, BOX against Novi.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from box import tag_scoreboard as sb
from box.sticks import checks, core, reads
from dealintake import geo
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1c as p1c
from scripts import box_sticks_phase2a as p2a
from scripts import box_sticks_phase2a_bands as bands
from scripts import box_sticks_phase3_pilot as p3

FT = geo.FT_PER_M
CUTOFF = p3.BACKTEST_CUTOFF
WCA_FAMILY = ("WCA_1", "WCA_2", "WCXY")
ONE_SET = ("wca_one_member", "wca_one_landing")
CARRIED = ("thickness", "bracket", "offset")


# ----------------------------------------------------------------------------
# The frame without the hidden wells
# ----------------------------------------------------------------------------


def backtest_frame(cache: Path) -> tuple[dict, pd.DataFrame]:
    f = cache / "p3_frame_bt.pkl"
    if f.exists():
        return pd.read_pickle(f)
    F = p3.build_frame(cache)
    d = p0.pull(cache)
    pads, ext = F["pads"], F["ext"]
    u = F["u"][F["u"]["fp"] < CUTOFF].reset_index(drop=True)
    seen = set(u["api10"].astype(str))

    db = F["db"][["basin", "bench", "code", "pad_id", "inside_frac"]].copy()
    ev = p0.evidence(d["wells"], d["rule"]).merge(pd.read_pickle(cache / "p2a_screen.pkl"), on="api10", how="left")
    ev = ev[(ev["screen"] == "keep") & ev["api10"].astype(str).isin(seen)].reset_index(drop=True)
    thick, far = p1c.rankings()
    ch = p1c.build_chain(ev, d["extents"], pads, sb.bench_order(), thick, far)
    db = db.merge(ch[["basin", "code", "pad_id", "z", "rung", "how", "expected_median_ft", "expected_p90_ft", "near_mi"]],
                  on=["basin", "code", "pad_id"], how="left")
    db["rung"] = db["rung"].fillna("none")

    m = p2a.measure(u, p2a.pair_table(u["geom"].to_numpy(), (u["basin"] + "|" + u["live"]).to_numpy()))
    m = m.loc[m["gap_ft"].notna(), ["api10", "basin", "live", "x", "y", "gap_ft"]].reset_index(drop=True)
    _, app, _ = bands.build(m, pads, ext)
    db = db.merge(app[["basin", "code", "pad_id", "edge_mi", "edge_band", p3.BLEND_COL]].rename(columns={p3.BLEND_COL: "spacing_ft"}),
                  on=["basin", "code", "pad_id"], how="left")

    out = dict(F) | {"u": u, "pre": F["pre"].iloc[0:0].reset_index(drop=True), "db": db,
                     "wm": p3.membership(u["geom"].to_numpy(), u["basin"].to_numpy(), pads),
                     "pm": F["pm"].iloc[0:0].reset_index(drop=True), "cutoff": str(CUTOFF.date())}
    pd.to_pickle((out, m), f)
    return out, m


# ----------------------------------------------------------------------------
# Generate
# ----------------------------------------------------------------------------


def generate(ctx: reads.Context, ids: list[int], **over) -> dict[int, tuple[core.Dsu, core.Result]]:
    link = reads.link_fn()
    cfg = {b: replace(reads.default_cfg(b), **over) for b in ("delaware", "midland")}
    out, viol = {}, {}
    for pid in ids:
        d = ctx.dsu(pid)
        res = core.generate_dsu(d, cfg[d.basin], link)
        for k, v in checks.run_all(res, d, cfg[d.basin], link).items():
            viol[k] = viol.get(k, 0) + len(v)
        out[pid] = (d, res)
    assert not any(viol.values()), viol
    return out


def _axes(d: core.Dsu, res: core.Result) -> tuple[np.ndarray, np.ndarray, tuple[float, float]]:
    az = math.radians(res.meta["azimuth_grid_deg"])
    b = math.radians(geo.positive_offset_bearing(res.meta["azimuth_grid_deg"]))
    o = d.polygon.centroid
    return np.array([math.sin(az), math.cos(az)]), np.array([math.sin(b), math.cos(b)]), (o.x, o.y)


def _proj(line, along, cross, o) -> tuple[np.ndarray, np.ndarray]:
    pts = np.array([line.interpolate(t, normalized=True).coords[0] for t in np.linspace(0, 1, 41)]) - np.array(o)
    return pts @ along * FT, pts @ cross * FT


# ----------------------------------------------------------------------------
# Back-test scoring
# ----------------------------------------------------------------------------


def score(full: dict, ctx_full: reads.Context, runs: dict, area: dict[int, str]) -> dict[str, pd.DataFrame]:
    u = full["u"]
    hidden = (u["fp"] >= CUTOFF).to_numpy()
    wm = full["wm"]
    wm = wm[hidden[wm["i"].to_numpy()] & wm["pad_id"].isin(runs)]
    elig = set(map(tuple, full["db"][["pad_id", "code"]].to_numpy()))
    two = ctx_full.two
    planned = u["planned"].fillna(False).to_numpy(bool)
    okz = u["clean"].to_numpy(bool) & ~planned & (u["screen"].to_numpy() != "bad_depth")
    depth, live, api, geom = u["depth_ft"].to_numpy(float), u["live"].to_numpy(), u["api10"].astype(str).to_numpy(), u["geom"].to_numpy()
    cfgs = {b: reads.default_cfg(b) for b in ("delaware", "midland")}

    wells, pairs_all, benchrows = [], [], []
    for pid, (d, res) in runs.items():
        along, cross, o = _axes(d, res)
        blog = {b["code"]: b for b in res.benches}
        legs = [(s, leg) for s in res.sticks for leg in s["legs"]]
        lg = []
        for n, (s, leg) in enumerate(legs):
            a = [((np.array(p) - np.array(o)) @ along) * FT for p in (leg["heel_xy"], leg["toe_xy"])]
            lg.append((min(a), max(a), leg["gunbarrel_x_ft"], s["target_tvd_ft"], s["bench"], f"{s['well_name']}/{n}",
                       s["spacing_basis"]["final_ft"]))
        poly_x = (np.array(d.polygon.exterior.coords) - np.array(o)) @ cross * FT
        lo, hi = poly_x.min() + 330.0, poly_x.max() - 330.0
        prior = {w.code for w in d.wells if w.member}                         # benches with a well before the cutoff in the DSU
        for i in wm.loc[wm["pad_id"] == pid, "i"].to_numpy():
            code = live[i]
            if (pid, code) not in elig:
                wells.append({"pad_id": pid, "area": area[pid], "api10": api[i], "code": code, "in_W": False})
                continue
            b = blog.get(code, {})
            fam = code in WCA_FAMILY and b.get("no_row_reason") in ONE_SET
            match_codes = set(WCA_FAMILY) if fam else {code}
            wa, wx = _proj(ctx_full.work(geom[i]), along, cross, o)
            z = float(depth[i]) if okz[i] and np.isfinite(depth[i]) else None
            skip_z = (pid, code) in two
            cand = []
            for k, (a0, a1, x, tvd, bc, name, sp) in enumerate(lg):
                if bc not in match_codes:
                    continue
                inside = (wa >= a0) & (wa <= a1)
                shared = min(a1, wa.max()) - max(a0, wa.min())
                if shared <= 0 or not inside.any():
                    continue
                cand.append({"well": api[i], "leg": name, "k": k, "shared_frac": shared / min(a1 - a0, wa.max() - wa.min()),
                             "dh_ft": float(np.median(np.abs(wx[inside] - x))), "dz_raw": None if z is None else z - tvd,
                             "dz_ft": None if z is None or skip_z else z - tvd, "spacing_ft": sp, "bench": bc})
            pairs_all += [c | {"pad_id": pid, "code": code} for c in cand]
            placed = sum(blog[c]["legs_placed"] for c in match_codes if c in blog)
            why = ""
            if not placed:
                own = b.get("no_row_reason") or ""
                why = own if own and not fam else ("all_rows_culled" if any(blog.get(c, {}).get("rows_considered") for c in match_codes) else own or "no_rows")
            wells.append({"pad_id": pid, "area": area[pid], "api10": api[i], "code": code, "in_W": True, "well_type": res.meta["well_type"],
                          "gb_x_ft": float(np.median(wx)), "depth_ft": z, "two_landing": skip_z, "family_match": fam, "bench_legs": placed,
                          "no_row_why": why, "rung": next((bb.rung for bb in d.benches if bb.code == code), ""),
                          "rung_median_ft": next((bb.tvd_err_median_ft for bb in d.benches if bb.code == code), None)})
        for b in res.benches:
            benchrows.append({"pad_id": pid, "area": area[pid], "well_type": res.meta["well_type"], "code": b["code"], "legs": b["legs_placed"],
                              "spacing_ft": b.get("spacing_final_ft"), "rung": b.get("rung", ""), "prior_same_bench": b["code"] in prior, "lo": lo, "hi": hi})

    W = pd.DataFrame(wells)
    P = pd.DataFrame(pairs_all)
    B = pd.DataFrame(benchrows)
    Wk = W[W["in_W"]].copy()

    # T1: one-to-one slot match per DSU (a missing depth is None, not NaN: match_slots skips the depth test on None)
    def recs(g: pd.DataFrame) -> list[dict]:
        return [r | {k: (None if r[k] is None or pd.isna(r[k]) else float(r[k])) for k in ("dz_ft", "dz_raw")} for r in g.to_dict("records")]

    hit: dict[str, str] = {}
    for _pid, g in P.groupby("pad_id"):
        hit |= checks.match_slots(recs(g))
    Wk["slot"] = Wk["api10"].map(hit)
    Wk["on_slot"] = Wk["slot"].notna()

    # why a well missed, first test that fails: no row on its bench, no leg alongside, sideways gap, depth, slot already taken
    lim = np.minimum(330.0, P["spacing_ft"] / 2.0)
    P["ok_len"] = P["shared_frac"] >= 0.5
    P["ok_side"] = P["ok_len"] & (P["dh_ft"] <= lim)
    P["ok_depth"] = P["ok_side"] & (P["dz_ft"].isna() | (P["dz_ft"].astype(float).abs() <= 150.0))
    best = P.groupby("well").agg(ok_len=("ok_len", "any"), ok_side=("ok_side", "any"), ok_depth=("ok_depth", "any"), min_dh=("dh_ft", "min"))
    Wk = Wk.merge(best, left_on="api10", right_index=True, how="left")
    for c in ("ok_len", "ok_side", "ok_depth"):
        Wk[c] = Wk[c].fillna(False).astype(bool)
    Wk["miss"] = np.where(Wk["on_slot"], "", np.where(Wk["bench_legs"] == 0, "bench_has_no_row", np.where(~Wk["ok_len"], "no_leg_alongside",
                          np.where(~Wk["ok_side"], "sideways_gap", np.where(~Wk["ok_depth"], "depth", "slot_taken")))))

    # T5: matched on bench and sideways gap only
    loose: dict[str, tuple[str, float]] = {}
    for _pid, g in P.groupby("pad_id"):
        m = checks.match_slots([r | {"dz_ft": None} for r in recs(g)])
        raw = {(r["well"], r["leg"]): r["dz_raw"] for r in recs(g)}
        loose |= {w: (leg, raw[(w, leg)]) for w, leg in m.items()}
    Wk["dz_loose_ft"] = [loose[a][1] if a in loose else None for a in Wk["api10"]]

    # T6: hidden wells inside the envelope of a well on production before the cutoff
    link = reads.link_fn()
    seen = np.flatnonzero(~hidden)
    env = []
    for basin, cfg in cfgs.items():
        hi_ = np.array([i for i in wm["i"].unique() if u["basin"].to_numpy()[i] == basin and okz[i]], int)
        si = seen[(u["basin"].to_numpy()[seen] == basin) & okz[seen]]
        if not len(hi_) or not len(si):
            continue
        t = link(geom[hi_], geom[si], same=False)
        t = t[t["overlap"] >= cfg.min_overlap]
        dz = depth[si[t["j"].to_numpy()]] - depth[hi_[t["i"].to_numpy()]]
        dh = t["dh_ft"].to_numpy()
        inside = ((np.abs(dz) <= cfg.same_dv_ft) & (dh <= cfg.same_dh_ft)) | np.any(
            [(dz > lo_) & (dz <= hi2) & (dh <= lim) for lo_, hi2, lim in cfg.stacked], axis=0)
        env += list(api[hi_[t["i"].to_numpy()[inside]]])
    Wk["in_prior_envelope"] = Wk["api10"].isin(set(env))

    # T3 / T4: drilled-across DSU x bench
    g = Wk.groupby(["pad_id", "code"]).agg(wells=("api10", "size"), matched=("on_slot", "sum"), xmin=("gb_x_ft", "min"), xmax=("gb_x_ft", "max"),
                                           actual_gap_ft=("gb_x_ft", lambda v: float(np.median(np.diff(np.sort(v)))) if len(v) > 1 else np.nan)).reset_index()
    X = B.merge(g, on=["pad_id", "code"], how="inner")
    X["drilled_across"] = (X["wells"] >= 3) & ~X["prior_same_bench"] & (X["xmin"] <= X["lo"] + X["spacing_ft"].fillna(np.inf)) & (
        X["xmax"] >= X["hi"] - X["spacing_ft"].fillna(np.inf))
    return {"W": W, "Wk": Wk, "pairs": P, "benches": B, "across": X}


def bars(S: dict[str, pd.DataFrame]) -> tuple[dict, pd.DataFrame]:
    Wk, X = S["Wk"], S["across"]
    st = Wk[Wk["well_type"] == "single"]
    ut = Wk[Wk["well_type"] == "uturn"]

    def pct(a, b):
        return None if not b else round(100.0 * a / b, 1)

    per = st.groupby("area").agg(W=("api10", "size"), on_slot=("on_slot", "sum")).reset_index()
    per["pct"] = (100 * per["on_slot"] / per["W"]).round(1)
    t1 = {"W_straight": len(st), "on_slot": int(st["on_slot"].sum()), "pct": pct(st["on_slot"].sum(), len(st)), "by_area": per.to_dict("records"),
          "pass": bool(len(st) and st["on_slot"].mean() >= 0.60 and (per["pct"] >= 50).all()),
          "uturn_context": {"W": len(ut), "on_slot": int(ut["on_slot"].sum()), "pct": pct(ut["on_slot"].sum(), len(ut))},
          "no_depth_evidence_wells": {"W": int(st["depth_ft"].isna().sum()), "on_slot": int(st.loc[st["depth_ft"].isna(), "on_slot"].sum())},
          "two_landing_wells": {"W": int(st["two_landing"].sum()), "on_slot": int(st.loc[st["two_landing"], "on_slot"].sum())},
          "misses_by_reason": st.loc[~st["on_slot"], "miss"].value_counts().to_dict(),
          "misses_by_area": st[~st["on_slot"]].groupby(["area", "miss"]).size().unstack(fill_value=0).to_dict("index"),
          "sideways_gap_of_misses_ft": {q: round(float(st.loc[st["miss"] == "sideways_gap", "min_dh"].quantile(v)), 0) for q, v in (("p25", .25), ("p50", .5), ("p75", .75))}
          if (st["miss"] == "sideways_gap").any() else {}}
    norow = Wk[Wk["bench_legs"] == 0]
    t2 = {"W": len(Wk), "on_bench_with_no_row": len(norow), "pct": pct(len(norow), len(Wk)), "by_reason": norow["no_row_why"].value_counts().to_dict(),
          "by_area": (100 * norow.groupby("area").size() / Wk.groupby("area").size()).round(1).fillna(0).to_dict(), "pass": bool(len(norow) / max(len(Wk), 1) <= 0.10)}
    A = X[X["drilled_across"] & (X["well_type"] == "single")]
    Au = X[X["drilled_across"] & (X["well_type"] == "uturn")]
    enough = len(A) >= 15
    within1 = float((np.abs(A["legs"] - A["wells"]) <= 1).mean()) if len(A) else None
    ratio = float(A["legs"].sum() / A["wells"].sum()) if len(A) else None
    diff = (A["legs"] - A["wells"])
    t3x = {"legs_minus_wells": diff.value_counts().sort_index().to_dict(), "by_area": A.assign(d=diff).groupby("area").agg(
        dsu_bench=("d", "size"), within_1=("d", lambda v: int((v.abs() <= 1).sum())), legs=("legs", "sum"), wells=("wells", "sum")).to_dict("index"),
           "generated_spacing_over_actual_gap_median": round(float((A["spacing_ft"] / A["actual_gap_ft"]).median()), 2) if len(A) else None,
           "generated_spacing_over_actual_gap_p25_p75": [round(float((A["spacing_ft"] / A["actual_gap_ft"]).quantile(q)), 2) for q in (.25, .75)] if len(A) else None}
    t3 = {"detail": t3x, "dsu_bench": len(A), "within_1_pct": None if within1 is None else round(100 * within1, 1), "legs": int(A["legs"].sum()), "wells": int(A["wells"].sum()),
          "ratio": None if ratio is None else round(ratio, 2), "judged": enough,
          "pass": bool(enough and within1 >= 0.70 and 0.85 <= ratio <= 1.20) if enough else None,
          "uturn_context": {"dsu_bench": len(Au), "legs": int(Au["legs"].sum()), "wells": int(Au["wells"].sum())}}
    unused = int((A["legs"] - A["matched"]).sum()) if len(A) else 0
    t4 = {"dsu_bench": len(A), "legs": int(A["legs"].sum()), "unmatched": unused, "pct": pct(unused, int(A["legs"].sum())), "judged": enough,
          "pass": bool(enough and unused / max(int(A["legs"].sum()), 1) <= 0.25) if enough else None}
    D = Wk[Wk["dz_loose_ft"].notna() & ~Wk["two_landing"]].copy()
    D["abs"] = D["dz_loose_ft"].abs().astype(float)
    dr = D[D["rung"] == "direct"]
    t5 = {"direct": {"pairs": len(dr), "median_abs_ft": None if dr.empty else round(float(dr["abs"].median()), 1),
                     "within_150_pct": None if dr.empty else round(100 * float((dr["abs"] <= 150).mean()), 1),
                     "pass": bool(len(dr) and dr["abs"].median() <= 75 and (dr["abs"] <= 150).mean() >= 0.80)},
          "direct_by_area": {a: {"pairs": len(g), "median_abs_ft": round(float(g["abs"].median()), 1), "within_150_pct": round(100 * float((g["abs"] <= 150).mean()), 1),
                                 "median_signed_ft": round(float(g["dz_loose_ft"].astype(float).median()), 1)} for a, g in dr.groupby("area")},
          "carried": {r: {"pairs": len(g), "median_abs_ft": round(float(g["abs"].median()), 1),
                          "held_out_median_ft": round(float(g["rung_median_ft"].astype(float).median()), 1),
                          "ratio": round(float(g["abs"].median() / g["rung_median_ft"].astype(float).median()), 2),
                          "pass": bool(g["abs"].median() <= 1.5 * g["rung_median_ft"].astype(float).median())}
                      for r, g in D[D["rung"].isin(CARRIED)].groupby("rung")},
          "two_landing_pairs_left_out": int((Wk["dz_loose_ft"].notna() & Wk["two_landing"]).sum())}
    zed = Wk[Wk["depth_ft"].notna()]
    t6 = {"W_with_depth": len(zed), "inside_prior_envelope": int(zed["in_prior_envelope"].sum()), "pct": pct(zed["in_prior_envelope"].sum(), len(zed)),
          "by_area": (100 * zed.groupby("area")["in_prior_envelope"].mean()).round(2).to_dict()}
    by = Wk.groupby(["area", "well_type", "code"]).agg(W=("api10", "size"), on_slot=("on_slot", "sum"), no_row=("bench_legs", lambda v: int((v == 0).sum())),
                                                     miss_sideways=("miss", lambda v: int((v == "sideways_gap").sum())), miss_depth=("miss", lambda v: int((v == "depth").sum())),
                                                     miss_slot_taken=("miss", lambda v: int((v == "slot_taken").sum())),
                                                     in_prior_envelope=("in_prior_envelope", "sum")).reset_index()
    return {"T1": t1, "T2": t2, "T3": t3, "T4": t4, "T5": t5, "T6": t6}, by


# ----------------------------------------------------------------------------
# Pilot report on today's wells: BOX against Novi
# ----------------------------------------------------------------------------


def report(full: dict, ctx: reads.Context, runs: dict, area: dict[int, str]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    u, wm, s, sm = full["u"], full["wm"], full["sticks"], full["sm"]
    okz = u["clean"].to_numpy(bool) & ~u["planned"].fillna(False).to_numpy(bool) & (u["screen"].to_numpy() != "bad_depth")
    w = wm.assign(code=u["live"].to_numpy()[wm["i"]], z=np.where(okz[wm["i"]], u["depth_ft"].to_numpy(float)[wm["i"]], np.nan))
    w = w[w["pad_id"].isin(runs)]
    prod = w.groupby(["pad_id", "code"]).agg(producers=("i", "size"), z_med=("z", "median"), z_n=("z", "count")).reset_index()
    nv = sm.assign(code=s["code"].to_numpy()[sm["i"]], tvd=s["tvd"].to_numpy(float)[sm["i"]], ll=s["ll_ft"].to_numpy(float)[sm["i"]],
                   rem=s["remaining"].to_numpy(bool)[sm["i"]])
    nv = nv[nv["pad_id"].isin(runs) & nv["rem"]]
    novi = nv.groupby(["pad_id", "code"]).agg(novi_sticks=("i", "size"), novi_ft=("ll", "sum"), novi_tvd=("tvd", "median")).reset_index()
    rows, reasons = [], []
    for pid, (_d, res) in runs.items():
        st = pd.DataFrame(res.sticks)
        for b in res.benches:
            k = st[st["bench"] == b["code"]] if len(st) else st
            rows.append({"pad_id": pid, "area": area[pid], "well_type": res.meta["well_type"], "code": b["code"], "no_row_reason": b["no_row_reason"],
                         "rows": b["rows_considered"], "legs": b["legs_placed"], "sticks": len(k),
                         "box_ft": float(k["completed_lateral_ft"].sum()) if len(k) else 0.0, "box_tvd": b.get("target_tvd_ft"), "rung": b.get("rung", ""),
                         "two_landing": "two_landings_observed" in str(b.get("flags", ""))})
        reasons += [{"pad_id": pid, "area": area[pid], "code": r["code"], "reason": r["reason"]} for r in res.ledger if r["status"] == "culled"]
    T = pd.DataFrame(rows).merge(prod, on=["pad_id", "code"], how="left").merge(novi, on=["pad_id", "code"], how="left")
    for c in ("producers", "z_n", "novi_sticks", "novi_ft"):
        T[c] = T[c].fillna(0)
    T["box_bust_ft"] = np.where((T["legs"] > 0) & (T["z_n"] >= 1), T["box_tvd"] - T["z_med"], np.nan)
    T["novi_bust_ft"] = np.where((T["novi_sticks"] > 0) & (T["z_n"] >= 1), T["novi_tvd"] - T["z_med"], np.nan)
    R = pd.DataFrame(reasons)
    piv = R.pivot_table(index=["area", "code"], columns="reason", values="pad_id", aggfunc="size", fill_value=0).reset_index() if len(R) else pd.DataFrame()

    def agg(g: pd.DataFrame) -> pd.Series:
        both = g[g["box_bust_ft"].notna() & g["novi_bust_ft"].notna() & ~g["two_landing"]]
        bb = g.loc[g["box_bust_ft"].notna() & ~g["two_landing"], "box_bust_ft"].abs()
        nb = g.loc[g["novi_bust_ft"].notna() & ~g["two_landing"], "novi_bust_ft"].abs()
        return pd.Series({"dsu_bench": len(g), "dsu_bench_with_sticks": int((g["sticks"] > 0).sum()), "no_row": int((g["no_row_reason"] != "").sum()),
                          "box_sticks": int(g["sticks"].sum()), "box_legs": int(g["legs"].sum()),
                          "box_straight": int(g.loc[g["well_type"] == "single", "sticks"].sum()), "box_uturn": int(g.loc[g["well_type"] == "uturn", "sticks"].sum()),
                          "rows_not_placed": int((g["rows"] - g["legs"]).sum()), "novi_sticks": int(g["novi_sticks"].sum()),
                          "box_ft": round(float(g["box_ft"].sum())), "novi_ft": round(float(g["novi_ft"].sum())), "producers": int(g["producers"].sum()),
                          "box_bust_n": len(bb), "box_bust_median_abs_ft": round(float(bb.median()), 0) if len(bb) else np.nan,
                          "box_bust_p90_abs_ft": round(float(bb.quantile(0.9)), 0) if len(bb) else np.nan,
                          "novi_bust_n": len(nb), "novi_bust_median_abs_ft": round(float(nb.median()), 0) if len(nb) else np.nan,
                          "novi_bust_p90_abs_ft": round(float(nb.quantile(0.9)), 0) if len(nb) else np.nan,
                          "paired_n": len(both), "paired_box_median_abs_ft": round(float(both["box_bust_ft"].abs().median()), 0) if len(both) else np.nan,
                          "paired_novi_median_abs_ft": round(float(both["novi_bust_ft"].abs().median()), 0) if len(both) else np.nan})

    by = T.groupby(["area", "code"]).apply(agg, include_groups=False).reset_index()
    if len(piv):
        by = by.merge(piv, on=["area", "code"], how="left").fillna({c: 0 for c in piv.columns if c not in ("area", "code")})
    tot = T.groupby("area").apply(agg, include_groups=False).reset_index()
    nv_other = nv[~nv.set_index(["pad_id", "code"]).index.isin(T.set_index(["pad_id", "code"]).index)]
    extra = {"novi_remaining_on_benches_with_no_box_extent_in_the_dsu": nv_other.assign(area=nv_other["pad_id"].map(area)).groupby("area").size().to_dict(),
             "bench_no_row_reasons": T[T["no_row_reason"] != ""].groupby(["area", "no_row_reason"]).size().unstack(fill_value=0).to_dict("index"),
             "dsu_by_type": pd.Series({pid: r.meta["well_type"] for pid, (_d, r) in runs.items()}).groupby([pd.Series(area), ]).value_counts().unstack(fill_value=0).to_dict("index")}
    return by, tot, extra


def run(out: Path, cache: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    full = p3.build_frame(cache)
    ctx_full = reads.Context(cache)
    area = {int(p): name for name, a in p3.AREAS.items() for p in p3.area_pads(full, a)}
    ids = sorted(area)

    today = generate(ctx_full, ids)
    by, tot, extra = report(full, ctx_full, today, area)
    by.to_csv(out / "report_area_bench.csv", index=False)
    tot.to_csv(out / "report_area.csv", index=False)

    Fb, mb = backtest_frame(cache)
    ctx_bt = reads.Context(cache, frame=Fb, measured=mb)
    bt = generate(ctx_bt, ids)
    S = score(full, ctx_full, bt, area)
    B, by_bt = bars(S)
    # diagnostic only, not a bar: the same back-test with every unpinned grid centred (no left-right alternation)
    Bc, _ = bars(score(full, ctx_full, generate(ctx_bt, ids, alternate=False), area))
    B["sensitivity_centred_grids"] = {"T1_pct": Bc["T1"]["pct"], "T1_by_area": {r["area"]: r["pct"] for r in Bc["T1"]["by_area"]},
                                      "T3_within_1_pct": Bc["T3"]["within_1_pct"], "T4_pct": Bc["T4"]["pct"]}
    S["Wk"].to_csv(out / "backtest_wells.csv", index=False)
    S["across"].to_csv(out / "backtest_dsu_bench.csv", index=False)
    by_bt.to_csv(out / "backtest_area_bench.csv", index=False)
    pd.DataFrame([r for _p, (_d, res) in bt.items() for r in res.benches]).to_csv(out / "backtest_benches.csv", index=False)
    W = S["W"]
    summ = {"generator_version": core.VERSION, "tags": full["tags"], "pulled": full["pulled"], "cutoff": str(CUTOFF.date()), "dsus": len(ids),
            "hidden_producers_in_pilot_dsus": len(W), "not_on_an_eligible_bench": int((~W["in_W"]).sum()),
            "not_eligible_by_code": W.loc[~W["in_W"], "code"].value_counts().to_dict(),
            "W": int(W["in_W"].sum()), "W_by_area": W[W["in_W"]].groupby("area").size().to_dict(),
            "producers_seen_by_generator": len(Fb["u"]), "spacing_gaps_seen": len(mb),
            "backtest_sticks": sum(len(r.sticks) for _d, r in bt.values()), "backtest_legs": sum(len(s["legs"]) for _d, r in bt.values() for s in r.sticks),
            "today_sticks": sum(len(r.sticks) for _d, r in today.values()), "bars": B, "report": extra}
    (out / "backtest_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summ, indent=1, default=str))
    return summ


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
