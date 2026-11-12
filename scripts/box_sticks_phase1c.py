"""BOX sticks, phase 1c: the full landing-depth chain for every bench at every DSU, and the stack check (read-only).

    python -m scripts.box_sticks_phase1c --out docs/box_sticks/phase1c-<date> --cache <phase 0 cache>

The chain adopted 2026-11-12 (docs/box_sticks_plan.md), evaluated at each DSU polygon centroid for every bench whose
BOX extent the polygon intersects:
  1 direct     the bench's own evidence wells (>= 3 within 2 mi, nearest within 1 mi);
  2 thickness  own wells within 5 mi (>= 3, on more than one side) on a neighbour's DIRECT surface; neighbours in the
               order of their held-out error (phase 1 holdout_thickness.csv);
  3 bracket    between a bench above and a bench below, both DIRECT at the centroid; fraction from the 30 nearest
               same-bench wells (regional median when fewer than 5), clamped to the window; pairs in the order of
               their held-out error at 5 mi (phase 1b holdout_far.csv);
  4 offset     one neighbour's DIRECT surface + the thickness from the 30 nearest same-bench wells;
  5 none.
Delaware WCXY takes rung 1 only until it has its own extent; WCA_1 / WCA_2 take the full chain. A carried depth never rests on another
carried depth, so every bench is computed independently; the STACK is then checked per DSU: adjacent benches out of
stratigraphic order or closer than MIN_SEP_FT, by which rungs the two depths came from.

Run twice: all evidence wells, and with the two-part screen (two_part_screen: depths that fit no bench are dropped;
wells sitting on another bench's surface are removed from their tagged bench's evidence). Live tags. Nothing is written to the
warehouse.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import landing_surfaces as ls
from box import tag_scoreboard as sb
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1 as p1
from scripts import box_sticks_phase1b as p1b

P = ls.PARAMS
MI = ls.M_PER_MI
MIN_SEP_FT = 75.0
SCREEN_FT = 300.0
SCREEN_MIN_N = 5
MISTAG_MIN_FT = 150.0
DIRECT_ONLY = set(ls.WCA_FAM)                # the Delaware WCA family, for the stack tables
CHAIN_DIRECT_ONLY = {("delaware", "WCXY")}   # Michael 2026-11-12: WCA_1 / WCA_2 take the full chain; WCXY waits on its extent
DOCS = Path(__file__).resolve().parent.parent / "docs" / "box_sticks"
THICK_RANK = DOCS / "phase1-2026-11-12" / "holdout_thickness.csv"
FAR_RANK = DOCS / "phase1b-2026-11-12" / "holdout_far.csv"


def loo_residual(w: pd.DataFrame) -> pd.Series:
    """Each evidence well's depth minus the landing depth of its same-bench neighbours within r_mi (itself left out)."""
    res = pd.Series(np.nan, index=w.index)
    for _, g in w.groupby(["basin", "live"]):
        if len(g) <= SCREEN_MIN_N:
            continue
        xy, z = g[["x", "y"]].to_numpy(float), g["depth_ft"].to_numpy(float)
        out = np.full(len(g), np.nan)
        for i, js in enumerate(cKDTree(xy).query_ball_point(xy, P.r_mi * MI)):
            js = np.asarray([j for j in js if j != i], int)
            if len(js) >= SCREEN_MIN_N:
                out[i] = z[i] - ls.estimate(xy[js], z[js], xy[i], P)[0]
        res.loc[g.index] = out
    return res


def two_part_screen(w: pd.DataFrame, extents: pd.DataFrame) -> pd.DataFrame:
    """Adds ``screen`` = keep / bad_depth / mistag (Michael 2026-11-12, after JCF-DAVIDSON 11O 15H: an LSSH tag landed
    on the JM surface, 9 ft off it and about 300 ft above its LSSH neighbours).

    own    the leave-one-out landing depth of the well's same-bench neighbours (loo_residual);
    other  the nearest DIRECT surface of any other bench at the well (pooled-family members are not compared).
      mistag     closer to another bench's surface than to its own, and more than max(MISTAG_MIN_FT, half the local
                 gap between the two surfaces) off its own. Removed from its tagged bench's evidence; NOT re-tagged
                 here (the list goes to the formation-tag review queue).
      bad_depth  more than SCREEN_FT off its own surface and not a mistag: a depth that fits no bench. Dropped.
    Single pass: the surfaces used for the test are built from the unscreened wells.
    """
    w = w.copy()
    w["loo_resid_ft"] = loo_residual(w)
    w["own_surface_ft"] = w["depth_ft"] - w["loo_resid_ft"]
    w["other_bench"], w["other_surface_ft"], w["other_dist_ft"] = None, np.nan, np.nan
    for basin in sorted(extents["basin"].unique()):
        m = (w["basin"] == basin).to_numpy()
        bw = w[m]
        sets = p1.anchor_sets(extents, basin)
        F = pd.DataFrame({n: p1b.field_at(bw, cs, bw[["x", "y"]].to_numpy(float)) for n, cs in sets.items()}, index=bw.index)
        for n, cs in sets.items():
            F.loc[bw["live"].isin(cs), n] = np.nan
        dist = F.sub(bw["depth_ft"], axis=0).abs()
        has = dist.notna().any(axis=1)
        other = dist.fillna(np.inf).idxmin(axis=1).where(has)
        w.loc[bw.index, "other_bench"] = other
        w.loc[bw.index, "other_dist_ft"] = dist.min(axis=1)
        w.loc[bw.index[has], "other_surface_ft"] = [F.at[i, o] for i, o in other[has].items()]
        print(f"  {basin} screen fields built", flush=True)
    resid = w["loo_resid_ft"].abs()
    gap = (w["own_surface_ft"] - w["other_surface_ft"]).abs()
    mistag = (w["other_dist_ft"] < resid) & (resid > np.maximum(MISTAG_MIN_FT, 0.5 * gap))
    w["screen"] = np.where(mistag, "mistag", np.where(resid > SCREEN_FT, "bad_depth", "keep"))
    w["rule_moves"] = w["shadow"] != w["live"]
    return w


def rankings() -> tuple[dict, dict]:
    t = pd.read_csv(THICK_RANK)
    t = t[(t["exclude_mi"] == 1.0) & (t["predicted_pct"] >= 25)].sort_values("median_ft")
    thick = {k: list(g[["anchor", "median_ft", "p90_ft"]].itertuples(index=False, name=None)) for k, g in t.groupby(["basin", "code"])}
    f = pd.read_csv(FAR_RANK)
    f = f[(f["exclude_mi"] == p1b.RANK_AT_MI) & (f["predicted"] >= p1b.MIN_PREDICTED)].sort_values("median_ft")
    f = f.drop_duplicates(["basin", "code", "kind", "upper_or_anchor", "lower"])
    far = {k: list(g[["kind", "upper_or_anchor", "lower", "median_ft", "p90_ft"]].itertuples(index=False, name=None))
           for k, g in f.groupby(["basin", "code"])}
    return thick, far


def chain_for_code(direct_only: bool, pts: np.ndarray, cxy: np.ndarray, cz: np.ndarray, Fc: dict[str, np.ndarray], Fp: dict[str, np.ndarray],
                   thick_rank: list, far_rank: list) -> pd.DataFrame:
    n = len(pts)
    z, rung, how = np.full(n, np.nan), np.full(n, "none", dtype=object), np.full(n, None, dtype=object)
    exp_med, exp_p90 = np.full(n, np.nan), np.full(n, np.nan)
    near = np.full(n, np.inf)
    if len(cz) >= P.n_min:
        tree = cKDTree(cxy)
        near = tree.query(pts, k=1)[0] / MI
        for i, js in enumerate(tree.query_ball_point(pts, P.r_mi * MI)):
            if len(js) >= P.n_min and near[i] <= P.direct_max_mi:
                z[i], rung[i] = ls.estimate(cxy[js], cz[js], pts[i], P)[0], "direct"
        if not direct_only:
            # 2 local thickness
            todo = np.where((rung == "none") & (near <= P.thick_max_mi))[0]
            balls = tree.query_ball_point(pts[todo], P.thick_max_mi * MI) if len(todo) else []
            for i, ks in zip(todo, balls, strict=True):
                ks = np.asarray(ks, int)
                for a, med, p90 in thick_rank:
                    if a not in Fp or not np.isfinite(Fp[a][i]):
                        continue
                    kk = ks[np.isfinite(Fc[a][ks])]
                    if len(kk) < P.n_min or ls.max_angular_gap_deg(cxy[kk], pts[i]) >= 180.0:
                        continue
                    d = np.hypot(cxy[kk, 0] - pts[i, 0], cxy[kk, 1] - pts[i, 1]) / MI
                    t = ls.weighted_median(cz[kk] - Fc[a][kk], np.exp(-0.5 * (d / (2 * P.wmed_sigma_mi)) ** 2) + 1e-9)
                    z[i], rung[i], how[i], exp_med[i], exp_p90[i] = Fp[a][i] + t, "thickness", a, med, p90
                    break
            # 3 bracket, then 4 offset
            rels, regional = {}, {}
            for kind, a, b, _, _ in far_rank:
                if kind == "bracket":
                    span = np.where(Fc[b] - Fc[a] > p1b.MIN_SPAN_FT, Fc[b] - Fc[a], np.nan)
                    r = (cz - Fc[a]) / span
                else:
                    r = cz - Fc[a]
                rels[(kind, a, b)] = r
                regional[(kind, a, b)] = float(np.nanmedian(r)) if np.isfinite(r).sum() >= p1b.MIN_SAMPLES else np.nan
            todo = np.where(rung == "none")[0]
            order = tree.query(pts[todo], k=min(len(cz), 400))[1] if len(todo) else []
            for kind_pass in ("bracket", "offset"):
                for i, nn in zip(todo, order, strict=True):
                    if rung[i] != "none":
                        continue
                    for kind, a, b, med, p90 in far_rank:
                        if kind != kind_pass or not np.isfinite(Fp[a][i]):
                            continue
                        span_i = 1.0
                        if kind == "bracket":
                            span_i = Fp[b][i] - Fp[a][i]
                            if not np.isfinite(span_i) or span_i <= p1b.MIN_SPAN_FT:
                                continue
                        r = rels[(kind, a, b)][np.atleast_1d(nn)]
                        r = r[np.isfinite(r)][:p1b.K_NEAREST]
                        f = float(np.median(r)) if len(r) >= p1b.MIN_SAMPLES else regional[(kind, a, b)]
                        if not np.isfinite(f):
                            continue
                        if kind == "bracket":
                            f = min(max(f, 0.0), 1.0)
                        z[i], rung[i], exp_med[i], exp_p90[i] = Fp[a][i] + f * span_i, kind, med, p90
                        how[i] = a if kind == "offset" else f"{a}/{b}"
                        break
    return pd.DataFrame({"z": z, "rung": rung, "how": how, "expected_median_ft": exp_med, "expected_p90_ft": exp_p90, "near_mi": near})


def build_chain(w: pd.DataFrame, extents: pd.DataFrame, pads: pd.DataFrame, order: dict, thick: dict, far: dict) -> pd.DataFrame:
    parts = []
    for basin in sorted(extents["basin"].unique()):
        bw = w[w["basin"] == basin].reset_index(drop=True)
        sets = p1.anchor_sets(extents, basin)
        pb = pads[pads["basin"] == basin].reset_index(drop=True)
        ppts = pb[["cx", "cy"]].to_numpy(float)
        Fw = {n: p1b.field_at(bw, cs, bw[["x", "y"]].to_numpy(float)) for n, cs in sets.items()}
        Fp_all = {n: p1b.field_at(bw, cs, ppts) for n, cs in sets.items()}
        tree = shapely.STRtree(pb["geom"].to_numpy())
        for e in extents[extents["basin"] == basin].itertuples():
            eg = shapely.make_valid(shapely.from_wkt(e.wkt))
            hit = np.sort(tree.query(eg, predicate="intersects"))
            for code in ls.extent_codes(basin, e.bench):
                cm = (bw["live"] == code).to_numpy()
                r = chain_for_code((basin, code) in CHAIN_DIRECT_ONLY, ppts[hit], bw.loc[cm, ["x", "y"]].to_numpy(float), bw.loc[cm, "depth_ft"].to_numpy(float),
                                   {n: f[cm] for n, f in Fw.items()}, {n: f[hit] for n, f in Fp_all.items()},
                                   thick.get((basin, code), []), far.get((basin, code), []))
                r.insert(0, "pad_id", pb["pad_id"].to_numpy()[hit])
                r.insert(0, "code", code)
                r.insert(0, "basin", basin)
                r["centroid_in_extent"] = shapely.contains_xy(eg, ppts[hit, 0], ppts[hit, 1])
                parts.append(r)
        print(f"  {basin} chain built", flush=True)
    ch = pd.concat(parts, ignore_index=True)
    ch["rank"] = [order[b].index(c) for b, c in zip(ch["basin"], ch["code"], strict=True)]
    return ch


def stack_check(ch: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    g = ch[ch["z"].notna()].sort_values(["basin", "pad_id", "rank"])
    nxt = g.groupby(["basin", "pad_id"])[["code", "z", "rung", "expected_median_ft"]].shift(-1)
    pr = g.assign(lower=nxt["code"], z_lower=nxt["z"], rung_lower=nxt["rung"], exp_lower=nxt["expected_median_ft"]).dropna(subset=["lower"])
    pr["gap_ft"] = pr["z_lower"] - pr["z"]
    pr["state"] = np.where(pr["gap_ft"] < 0, "out_of_order", np.where(pr["gap_ft"] < MIN_SEP_FT, "under_min_sep", "ok"))
    cu, cl = pr["rung"] == "direct", pr["rung_lower"] == "direct"
    pr["rungs"] = np.where(cu & cl, "direct + direct", np.where(cu | cl, "direct + carried", "carried + carried"))
    pr["wca_family"] = (pr["basin"] == "delaware") & pr["code"].isin(DIRECT_ONLY) & pr["lower"].isin(DIRECT_ONLY)
    by_pair = pr.groupby(["basin", "code", "lower"]).agg(
        dsu=("gap_ft", "size"), median_gap_ft=("gap_ft", "median"), p10_gap_ft=("gap_ft", lambda v: v.quantile(0.1)),
        out_of_order=("state", lambda s: int((s == "out_of_order").sum())), under_min_sep=("state", lambda s: int((s == "under_min_sep").sum()))).reset_index()
    by_pair["violation_pct"] = 100 * (by_pair["out_of_order"] + by_pair["under_min_sep"]) / by_pair["dsu"]
    by_rungs = pr.groupby(["basin", "rungs"]).agg(
        pairs=("gap_ft", "size"), out_of_order=("state", lambda s: int((s == "out_of_order").sum())),
        under_min_sep=("state", lambda s: int((s == "under_min_sep").sum()))).reset_index()
    by_rungs["violation_pct"] = 100 * (by_rungs["out_of_order"] + by_rungs["under_min_sep"]) / by_rungs["pairs"]
    bad = pr[pr["state"] != "ok"]
    summ = {}
    for b, q in pr.groupby("basin"):
        qb = bad[bad["basin"] == b]
        non_fam = qb[~qb["wca_family"]]
        summ[b] = {"dsu_with_2plus_benches": int(q["pad_id"].nunique()), "adjacent_pairs": len(q),
                   "dsu_with_violation": int(qb["pad_id"].nunique()), "dsu_out_of_order": int(qb.loc[qb["state"] == "out_of_order", "pad_id"].nunique()),
                   "violating_pairs": len(qb), "violating_pairs_wca_family": int(qb["wca_family"].sum()),
                   "dsu_with_violation_outside_wca_family": int(non_fam["pad_id"].nunique()),
                   "violating_pairs_carried_involved": int((non_fam["rungs"] != "direct + direct").sum()),
                   "violating_pairs_direct_direct_outside_family": int((non_fam["rungs"] == "direct + direct").sum())}
    return by_pair, by_rungs, summ


def rung_table(ch: pd.DataFrame) -> pd.DataFrame:
    t = (100 * pd.crosstab([ch["basin"], ch["code"]], ch["rung"], normalize="index")).reset_index()
    for c in ("direct", "thickness", "bracket", "offset", "none"):
        if c not in t:
            t[c] = 0.0
    car = ch[ch["rung"].isin(["thickness", "bracket", "offset"])]
    e = car.groupby(["basin", "code"]).agg(carried_median_expected_ft=("expected_median_ft", "median"),
                                           low_conf_pct_of_carried=("expected_p90_ft", lambda v: 100 * float((v > 200).mean()))).reset_index()
    n = ch.groupby(["basin", "code"]).size().rename("dsu").reset_index()
    return n.merge(t[["basin", "code", "direct", "thickness", "bracket", "offset", "none"]], on=["basin", "code"]).merge(e, on=["basin", "code"], how="left")


def run(out: Path, cache: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    w = p0.evidence(d["wells"], d["rule"])
    extents, order = d["extents"], sb.bench_order()
    pads = p0.pad_frame(d["pads"])
    cen = shapely.centroid(pads["geom"].to_numpy())
    pads = pads.assign(cx=shapely.get_x(cen), cy=shapely.get_y(cen))
    thick, far = rankings()

    w = two_part_screen(w, extents)
    judged = w["loo_resid_ft"].notna()
    drop = (w["screen"] != "keep").to_numpy()
    cols = ["api10", "well_name", "operator", "county", "basin", "live", "shadow", "rule_moves", "depth_ft", "depth_source", "own_surface_ft",
            "loo_resid_ft", "other_bench", "other_surface_ft", "other_dist_ft"]
    for kind, name in (("bad_depth", "screen_bad_depth.csv"), ("mistag", "screen_mistag_candidates.csv")):
        listing = w.loc[w["screen"] == kind, cols].sort_values("loo_resid_ft", key=np.abs, ascending=False)
        try:
            listing.to_csv(out / name, index=False)
        except PermissionError:   # open in Excel
            print(f"{name} is open elsewhere; left as it is", flush=True)
    by_code = pd.crosstab([w["basin"], w["live"]], w["screen"]).reset_index()
    for c in ("keep", "bad_depth", "mistag"):
        if c not in by_code:
            by_code[c] = 0
    by_code["removed_pct"] = 100 * (by_code["bad_depth"] + by_code["mistag"]) / (by_code["keep"] + by_code["bad_depth"] + by_code["mistag"])
    by_code.to_csv(out / "screen_by_bench.csv", index=False)
    mt = w[w["screen"] == "mistag"]
    screen = {"evidence_wells": len(w), "judged": int(judged.sum()), "bad_depth": int((w["screen"] == "bad_depth").sum()),
              "mistag": len(mt), "mistag_rule_already_moves": int(mt["rule_moves"].sum()),
              "mistag_top_classes": {f"{b} {a} on {o}": int(n) for (b, a, o), n in mt.groupby(["basin", "live", "other_bench"]).size().nlargest(10).items()},
              "fixed_300ft_would_remove": int((w["loo_resid_ft"].abs() > SCREEN_FT).sum())}
    print(json.dumps(screen, indent=1), flush=True)

    summary = {"code_sha": p0._git_sha(), "tags": "live", "min_sep_ft": MIN_SEP_FT, "bad_depth_ft": SCREEN_FT, "mistag_min_ft": MISTAG_MIN_FT,
               "screen": screen, "runs": {}}
    for label, ww in (("all_wells", w), ("screened", w[~drop].reset_index(drop=True))):
        print(label, flush=True)
        ch = build_chain(ww, extents, pads, order, thick, far)
        by_pair, by_rungs, summ = stack_check(ch)
        rt = rung_table(ch)
        rt.to_csv(out / f"rungs_{label}.csv", index=False)
        by_pair.to_csv(out / f"order_pairs_{label}.csv", index=False)
        by_rungs.to_csv(out / f"order_by_rungs_{label}.csv", index=False)
        ch.drop(columns=["rank"]).to_csv(out / f"chain_dsu_{label}.csv.gz", index=False, compression="gzip")
        fam = ch[(ch["basin"] == "delaware") & ch["code"].isin(["WCA_1", "WCA_2"]) & ch["z"].notna()].pivot(index="pad_id", columns="code", values="z").dropna()
        gap = fam["WCA_2"] - fam["WCA_1"]
        summary["runs"][label] = {
            "rung_pct": (100 * ch["rung"].value_counts(normalize=True)).round(1).to_dict(),
            "low_conf_pct_of_all_pairs": 100 * float((ch["expected_p90_ft"] > 200).mean()), "stack": summ,
            "wca1_wca2": {"dsu_with_both": len(gap), "median_gap_ft": float(gap.median()), "out_of_order_pct": 100 * float((gap < 0).mean()),
                          **{f"under_{t}_ft_pct": 100 * float((gap < t).mean()) for t in (50, 75, 100)}}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
