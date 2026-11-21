"""BOX sticks: the grid rung and the grid bound scored against their bars (docs/box_sticks/grid-rung-2026-11-20/BARS.md).

    python -m scripts.box_sticks_grid_rung score   --cache <run>/cache --out <dir>            # G1, G2: held-out wells
    python -m scripts.box_sticks_grid_rung compare --before <run> --after <run> --out <dir>   # G3 to G7: two generated sets

Files only: reads a run's cache (one pull) and the grid files, and two generated sets. Nothing is read from or written to
the warehouse. Hold-out is the generator's own far-rung design (scripts.box_sticks_phase1b): a well is predicted from
samples beyond the exclusion radius (5 miles for bracket / offset / grid; 1 mile for the thickness approximation).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from box import tag_scoreboard as sb
from box.sticks import grid_rung as gr
from box.sticks import identity
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1 as p1
from scripts import box_sticks_phase1b as p1b
from scripts import box_sticks_phase1c as p1c

MI = gr.MI
EXCL_FAR_MI, EXCL_THICK_MI = 5.0, 1.0


def held_out_pred(xy: np.ndarray, rel: np.ndarray, base: np.ndarray, span: np.ndarray, exclude_mi: float) -> np.ndarray:
    """Signed twin of p1b.far_holdout: the PREDICTION per well x method from the K nearest samples beyond exclude_mi."""
    n, m = rel.shape
    k = min(p1b.K_NEAREST, n - 1)
    pred = np.full((n, m), np.nan)
    for s in range(0, n, 256):
        d = np.hypot(xy[s:s + 256, 0, None] - xy[None, :, 0], xy[s:s + 256, 1, None] - xy[None, :, 1])
        d[d < exclude_mi * MI] = np.inf
        idx = np.argpartition(d, k - 1, axis=1)[:, :k]
        ok = np.isfinite(np.take_along_axis(d, idx, axis=1))
        r = np.where(ok[:, :, None], rel[idx], np.nan)
        cnt = np.isfinite(r).sum(axis=1)
        with np.errstate(all="ignore"):
            med = np.nanmedian(r, axis=1)
        med[cnt < p1b.MIN_SAMPLES] = np.nan
        pred[s:s + 256] = base[s:s + 256] + med * span[s:s + 256]
    return pred


def first_finite(pred: np.ndarray, cols: list[int]) -> np.ndarray:
    """Walk the methods in rank order, as the chain does: the first that predicts."""
    out = np.full(len(pred), np.nan)
    for j in cols:
        take = np.isnan(out) & np.isfinite(pred[:, j])
        out[take] = pred[take, j]
    return out


def _stats(e: np.ndarray) -> tuple[float | None, float | None]:
    e = e[np.isfinite(e)]
    return (round(float(np.median(e)), 1), round(float(np.quantile(e, 0.9)), 1)) if len(e) else (None, None)


def cmd_score(cache: Path, out: Path, basin: str = gr.BASIN) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    ev = p0.evidence(d["wells"], d["rule"]).merge(pd.read_pickle(cache / "p2a_screen.pkl"), on="api10", how="left")
    ev = ev[ev["screen"] == "keep"].reset_index(drop=True)
    table, sample = gr.BASINS[basin], gr.samplers().get(basin)
    if sample is None:
        raise SystemExit(f"grid files not available for {basin}")
    extents, order = d["extents"], sb.bench_order()
    thick, far = p1c.rankings()
    bw = ev[ev["basin"] == basin].reset_index(drop=True)
    sets = p1.anchor_sets(extents, basin)
    rank = {c: i for i, c in enumerate(order[basin])}
    wxy = bw[["x", "y"]].to_numpy(float)
    Fw = {n: p1b.field_at(bw, cs, wxy) for n, cs in sets.items()}
    G = sample(wxy[:, 0], wxy[:, 1])
    g1, g2, per = [], [], []
    for code in table.intervals:
        m = (bw["live"] == code).to_numpy()
        if m.sum() < 30:
            continue
        xy, z = wxy[m], bw.loc[m, "depth_ft"].to_numpy(float)
        g = {s: v[m] for s, v in G.items()}
        methods = p1b.methods_for(code, sets, rank)
        rel, base, span = p1b.columns(z, {n: f[m] for n, f in Fw.items()}, methods)
        pred = held_out_pred(xy, rel, base, span, EXCL_FAR_MI)
        pos = {(k, a, b if isinstance(b, str) else None): j for j, (k, a, b) in enumerate(methods)}
        ranked = [(k, a, b if isinstance(b, str) else None) for k, a, b, _, _ in far.get((basin, code), [])]
        p_off = first_finite(pred, [pos[q] for q in ranked if q[0] == "offset" and q in pos])
        p_brk = first_finite(pred, [pos[q] for q in ranked if q[0] == "bracket" and q in pos])
        # thickness, approximated: the ranked anchors, nearest same-bench wells beyond 1 mile
        t_methods = [("offset", a, None) for a, _, _ in thick.get((basin, code), []) if a in Fw]
        p_thk = np.full(len(z), np.nan)
        if t_methods:
            r2, b2, s2 = p1b.columns(z, {n: f[m] for n, f in Fw.items()}, t_methods)
            p_thk = first_finite(held_out_pred(xy, r2, b2, s2, EXCL_THICK_MI), list(range(len(t_methods))))
        gp = gr.predict(code, xy, g, xy, z, g, exclude_self=True, intervals=table.intervals)
        p_grid, top, bot = gp["z"].to_numpy(), gp["top"].to_numpy(), gp["base"].to_numpy()
        both = np.isfinite(p_off) & np.isfinite(p_grid)
        eg, eo = np.abs(z - p_grid)[both], np.abs(z - p_off)[both]
        (gm, g9), (om, o9) = _stats(eg), _stats(eo)
        ok = bool(both.sum() >= 30 and gm is not None and gm <= om and g9 <= o9 + 10)
        g1.append({"bench": code, "wells": int(m.sum()), "wells_scored": int(both.sum()), "grid_median_ft": gm, "grid_p90_ft": g9, "offset_median_ft": om,
                   "offset_p90_ft": o9, "grid_predicts_pct": round(100 * float(np.isfinite(p_grid).mean()), 1),
                   "offset_predicts_pct": round(100 * float(np.isfinite(p_off).mean()), 1), "basis": gp["basis"].value_counts().to_dict(), "passes": ok})
        for name, pr in (("thickness (approximated)", p_thk), ("bracket", p_brk), ("offset", p_off)):
            miss = np.where(pr < top, pr - top, np.where(pr > bot, pr - bot, 0.0))
            sel = np.isfinite(miss) & (np.abs(miss) > gr.BOUND_FT) & np.isfinite(p_grid)
            g2.append({"bench": code, "rung": name, "wells_predicted": int(np.isfinite(pr).sum()), "outside_by_more_than_150": int(sel.sum()),
                       "before": np.abs(z - pr)[sel], "after": np.abs(z - p_grid)[sel]})
        per.append(pd.DataFrame({"bench": code, "api10": bw.loc[m, "api10"].to_numpy(), "z": z, "grid": p_grid, "offset": p_off, "bracket": p_brk, "thickness": p_thk,
                                 "top": top, "base": bot, "basis": gp["basis"].to_numpy()}))
    G1 = pd.DataFrame(g1)
    G1.drop(columns=["basis"]).to_csv(out / "g1_by_bench.csv", index=False)
    rows = []
    for rung, grp in pd.DataFrame(g2).groupby("rung"):
        b, a = np.concatenate(grp["before"].to_list()), np.concatenate(grp["after"].to_list())
        rows.append({"rung": rung, "wells_predicted": int(grp["wells_predicted"].sum()), "outside_by_more_than_150": len(b),
                     "median_before_ft": round(float(np.median(b)), 1) if len(b) else None, "median_after_ft": round(float(np.median(a)), 1) if len(a) else None,
                     "closer_pct": round(100 * float((a < b).mean()), 1) if len(b) else None,
                     "passes": bool(len(b) and np.median(a) < np.median(b) and (a < b).mean() >= 0.6)})
    G2 = pd.DataFrame(rows)
    G2.to_csv(out / "g2_by_rung.csv", index=False)
    by = pd.DataFrame([{"bench": r["bench"], "rung": r["rung"], "outside": r["outside_by_more_than_150"],
                        "median_before_ft": round(float(np.median(r["before"])), 1) if len(r["before"]) else None,
                        "median_after_ft": round(float(np.median(r["after"])), 1) if len(r["after"]) else None} for r in g2])
    by.to_csv(out / "g2_by_bench_rung.csv", index=False)
    pd.concat(per, ignore_index=True).round(1).to_csv(out / "held_out_wells.csv", index=False)
    pd.set_option("display.width", 250)
    print(G1.drop(columns=["basis"]).to_string(index=False), "\n", G2.to_string(index=False), "\n", by.to_string(index=False), flush=True)
    summ = {"basin": basin, "g1": G1.to_dict("records"), "g2": G2.to_dict("records"), "evidence_wells": len(bw)}
    (out / "score_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    return summ


def _set(run: Path, basin: str) -> dict:
    return pd.read_pickle(run / f"set_{basin}.pkl")


def _id_sticks(art: dict) -> list[identity.Stick]:
    from scripts import box_sticks_phase5a as p5

    out = []
    for s in art["sticks"]:
        legs = tuple((p5.TO_3083.transform(*leg["heel_lonlat"]), p5.TO_3083.transform(*leg["toe_lonlat"])) for leg in s["legs"])
        out.append(identity.Stick(key=s["well_name"], pad_id=int(s["pad_id"]), bench=s["bench"], legs=legs, slot=1))
    return out


def cmd_compare(before: Path, after: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    summ: dict = {}
    for basin in ("delaware", "midland"):
        if not (after / f"set_{basin}.pkl").exists():
            continue
        a, b = _set(before, basin), _set(after, basin)
        ba = pd.DataFrame(a["bench_rows"]).set_index(["pad_id", "formation_blueox"])
        bb = pd.DataFrame(b["bench_rows"]).set_index(["pad_id", "formation_blueox"])
        j = ba[["tvd_rung", "target_tvd_ft", "no_row_reason", "sticks"]].join(bb[["tvd_rung", "target_tvd_ft", "no_row_reason", "sticks"]], lsuffix="_a", rsuffix="_b", how="outer")
        moved = (j["target_tvd_ft_a"].fillna(-1) - j["target_tvd_ft_b"].fillna(-1)).abs() > 0.05
        direct_changed = int((moved & (j["tvd_rung_a"] == "direct")).sum())
        cw = identity.crosswalk(_id_sticks(a), _id_sticks(b))
        sa = {s["well_name"]: s for s in a["sticks"]}
        sbk = {s["well_name"]: s for s in b["sticks"]}
        same = sum(1 for k, (pk, *_r) in cw["carried"].items() if abs(float(sbk[k]["target_tvd_ft"]) - float(sa[pk]["target_tvd_ft"])) <= 0.05)
        shift = (j["target_tvd_ft_b"] - j["target_tvd_ft_a"])[moved & j["target_tvd_ft_a"].notna() & j["target_tvd_ft_b"].notna()]
        tab = j[moved].groupby(["tvd_rung_a", "tvd_rung_b"], dropna=False).size().rename("dsu_bench").reset_index()
        tab.to_csv(out / f"compare_rungs_{basin}.csv", index=False)
        j[moved].reset_index().to_csv(out / f"compare_moved_{basin}.csv", index=False)
        summ[basin] = {"sticks_before": len(a["sticks"]), "sticks_after": len(b["sticks"]), "ids_carried": len(cw["carried"]),
                       "ids_carried_pct": round(100 * len(cw["carried"]) / max(len(a["sticks"]), 1), 2), "sticks_new": len(cw["new"]), "sticks_stopped": len(cw["stopped"]),
                       "carried_same_depth": same, "dsu_bench_landing_changed": int(moved.sum()), "direct_landings_changed": direct_changed,
                       "reconciled_out_before": int((ba["no_row_reason"] == "reconciled_out").sum()), "reconciled_out_after": int((bb["no_row_reason"] == "reconciled_out").sum()),
                       "rung_after": bb["tvd_rung"].value_counts().to_dict(), "rung_before": ba["tvd_rung"].value_counts().to_dict(),
                       "shift_median_abs_ft": round(float(shift.abs().median()), 1) if len(shift) else None,
                       "shift_p90_abs_ft": round(float(shift.abs().quantile(0.9)), 1) if len(shift) else None,
                       "identical": bool(len(a["sticks"]) == len(b["sticks"]) == same and not moved.any())}
        print(basin, json.dumps(summ[basin], indent=1, default=str), "\n", tab.to_string(index=False), flush=True)
    (out / "compare_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    return summ


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("score", "compare"))
    ap.add_argument("--cache", type=Path)
    ap.add_argument("--before", type=Path)
    ap.add_argument("--after", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--basin", default=gr.BASIN, choices=sorted(gr.BASINS))
    a = ap.parse_args(argv)
    if a.step == "score":
        cmd_score(a.cache, a.out, a.basin)
    else:
        cmd_compare(a.before, a.after, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
