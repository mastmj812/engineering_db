"""BOX sticks: WCXY by landing tiers, Delaware (read-only).

    python -m scripts.box_sticks_wcxy_tiers --out docs/box_sticks/wcxy-tiers-<date> --cache <phase 0 cache>
                                            [--verdicts docs/box_sticks/wcxy-cards-2026-11-12]

Michael's reading of the review cards (2026-11-12, confirmed): a pad is XY when the Wolfcamp A shows THREE landings
there and the pad is in the top one; the upper of only two landings is just upper WCA (WCA_1 over WCA_2), whatever
the vendor wrote. On CORRAL BLUFF #033H he saw it only on a wider W-E section than the card showed.

So, per pad of WCXY-tagged wells, tag-blind:
  * take every WCXY / WCA_1 / WCA_2-tagged evidence well within ALONG_FT along the pad's laterals and HALF_WIDTH_FT
    across (wider than the cards);
  * fit PARALLEL PLANES: one common dip and one offset per tier, tiers = groups of dip-corrected depths separated by
    an empty band of at least gap_ft (iterated; tiers with fewer than min_n wells are ignored);
  * count the tiers BELOW the pad's own tier. XY when there are at least two (an upper and a lower WCA beneath it).
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_wcxy as wx
from scripts import box_sticks_wcxy_cards as wc

FT = p0.FT_PER_M
FAMILY = ("WCXY", "WCA_1", "WCA_2")
ALONG_FT = 5280.0
HALF_WIDTH_FT = 3 * 5280.0
GAP_FT = 60.0
MIN_N = 3
GRID = {"gap_ft": (40.0, 50.0, 60.0, 75.0, 90.0), "half_width_mi": (1.5, 3.0, 4.5), "min_n": (2, 3, 4)}


def frame(subj: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pad centre, unit vector along its laterals, unit vector across (W -> E, or S -> N for E-W laterals)."""
    c = subj[["x", "y"]].to_numpy(float).mean(axis=0)
    dirs = []
    for pts in subj["pts"]:
        s = np.asarray(pts, float) if pts else np.zeros((0, 2))
        if len(s) >= 2:
            v = s[-1] - s[0]
            v = v / (np.hypot(*v) or 1.0)
            dirs.append(v if not dirs or np.dot(v, dirs[0]) >= 0 else -v)
    u = np.mean(dirs, axis=0) if dirs else np.array([0.0, 1.0])
    u = u / (np.hypot(*u) or 1.0)
    nrm = np.array([u[1], -u[0]])
    if (abs(nrm[0]) >= abs(nrm[1]) and nrm[0] < 0) or (abs(nrm[0]) < abs(nrm[1]) and nrm[1] < 0):
        nrm = -nrm
    return c, u, nrm


def parallel_tiers(off: np.ndarray, along: np.ndarray, z: np.ndarray, gap_ft: float, min_n: int, iters: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """(tier label per well, dip-corrected depth). Label -1 = in a group smaller than min_n. Tiers numbered top down."""
    lab = np.zeros(len(z), int)
    adj = z.copy()
    for _ in range(iters):
        use = lab >= 0
        ks = np.unique(lab[use])
        X = np.column_stack([off[use], along[use]] + [(lab[use] == k).astype(float) for k in ks])
        coef, *_ = np.linalg.lstsq(X, z[use], rcond=None)
        adj = z - coef[0] * off - coef[1] * along
        order = np.argsort(adj)
        grp = np.concatenate([[0], np.cumsum(np.diff(adj[order]) >= gap_ft)])
        new = np.empty(len(z), int)
        new[order] = grp
        sizes = np.bincount(new)
        keep = np.where(sizes >= min_n)[0]
        remap = {k: i for i, k in enumerate(keep)}
        new = np.array([remap.get(k, -1) for k in new])
        if (new >= 0).sum() < 3:
            return new, adj
        if np.array_equal(new, lab):
            break
        lab = new
    return lab, adj


def pad_tiers(subj: pd.DataFrame, fam: pd.DataFrame, gap_ft: float, half_width_ft: float, min_n: int) -> dict:
    c, u, nrm = frame(subj)
    d = fam[["x", "y"]].to_numpy(float) - c
    along, off = d @ u * FT, d @ nrm * FT
    m = (np.abs(along) <= ALONG_FT) & (np.abs(off) <= half_width_ft)
    v = fam[m]
    out = {"family_wells": int(m.sum()), "tiers": 0, "pad_tier": np.nan, "tiers_below": np.nan, "tiers_above": np.nan,
           "gap_to_next_ft": np.nan, "pad_split": False}
    if m.sum() < 2 * min_n:
        return out
    lab, adj = parallel_tiers(off[m], along[m], v["depth_ft"].to_numpy(float), gap_ft, min_n)
    valid = np.unique(lab[lab >= 0])
    if not len(valid):
        return out
    med = {k: float(np.median(adj[lab == k])) for k in valid}
    is_subj = v["api10"].isin(subj["api10"]).to_numpy()
    sl = lab[is_subj]
    if not is_subj.any():
        return out
    z_pad = float(np.median(adj[is_subj]))
    sv = sl[sl >= 0]
    pad_tier = int(np.bincount(sv).argmax()) if len(sv) else min(med, key=lambda k: abs(med[k] - z_pad))
    below = sorted(med[k] for k in valid if med[k] > med[pad_tier])
    out |= {"tiers": len(valid), "pad_tier": pad_tier + 1, "tiers_below": len(below), "tiers_above": int(sum(med[k] < med[pad_tier] for k in valid)),
            "gap_to_next_ft": below[0] - med[pad_tier] if below else np.nan, "pad_split": bool(len(set(sv.tolist())) > 1)}
    return out


def evaluate(p: pd.DataFrame, x: pd.DataFrame, fam: pd.DataFrame, gap_ft: float, half_width_ft: float, min_n: int) -> pd.DataFrame:
    rows = [{"group": g, **pad_tiers(x[x["group"] == g], fam, gap_ft, half_width_ft, min_n)} for g in p["group"]]
    r = p.merge(pd.DataFrame(rows), on="group")
    r["call"] = np.where(r["tiers_below"].isna(), "UNDETERMINED", np.where(r["tiers_below"] >= 2, "XY", "ONE"))
    return r


def run(out: Path, cache: Path | None, verdict_dir: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    w = p0.evidence(d["wells"], d["rule"])
    bw = w[w["basin"] == "delaware"].reset_index(drop=True)
    x = wx.classify(bw)
    x = x.join(wx.landings(bw, x))
    p, x = wc.pads(x)
    fam = bw[bw["live"].isin(FAMILY)]
    summary: dict = {"code_sha": p0._git_sha(), "tags": "live", "pads": len(p), "wcxy_wells": len(x)}

    params = (GAP_FT, HALF_WIDTH_FT, MIN_N)
    if verdict_dir:
        key = pd.read_csv(verdict_dir / "key.csv").merge(pd.read_csv(verdict_dir / "verdicts.csv"), on="card")
        sample = wc.sample(p)[["card", "group"]].merge(key[["card", "verdict"]], on="card")
        lab = p[p["group"].isin(sample["group"])]
        grid = []
        for g, hw, mn in itertools.product(*GRID.values()):
            r = evaluate(lab, x, fam, g, hw * 5280.0, mn).merge(sample, on="group")
            grid.append({"gap_ft": g, "half_width_mi": hw, "min_n": mn, "agree": int((r["call"] == r["verdict"]).sum()), "cards": len(r),
                         "undetermined": int((r["call"] == "UNDETERMINED").sum()),
                         "xy_called_one": int(((r["verdict"] == "XY") & (r["call"] == "ONE")).sum()),
                         "one_called_xy": int(((r["verdict"] == "ONE") & (r["call"] == "XY")).sum())})
        grid = pd.DataFrame(grid).sort_values(["agree", "undetermined"], ascending=[False, True])
        grid.to_csv(out / "grid_vs_verdicts.csv", index=False)
        b = grid.iloc[0]
        params = (float(b["gap_ft"]), float(b["half_width_mi"]) * 5280.0, int(b["min_n"]))
        r = evaluate(lab, x, fam, *params).merge(sample, on="group").sort_values("card")
        r["agree"] = r["call"] == r["verdict"]
        r[["card", "name", "county", "verdict", "call", "agree", "tiers", "pad_tier", "tiers_below", "tiers_above", "gap_to_next_ft", "pad_split",
           "family_wells", "sep_median_ft"]].to_csv(out / "cards_scored.csv", index=False)
        summary["fit"] = {"gap_ft": params[0], "half_width_mi": params[1] / 5280.0, "min_n": params[2], "agree": int(r["agree"].sum()), "cards": len(r),
                          "misses": r.loc[~r["agree"], ["card", "name", "verdict", "call", "tiers", "pad_tier", "tiers_below"]].to_dict("records"),
                          "grid_top": grid.head(8).to_dict("records"), "grid_agree_range": [int(grid["agree"].min()), int(grid["agree"].max())]}
    allp = evaluate(p, x, fam, *params)
    allp.drop(columns=["group"]).to_csv(out / "pads_all.csv", index=False)
    wells = x.merge(allp[["group", "call", "tiers", "pad_tier", "tiers_below"]], on="group")
    wells[["api10", "well_name", "operator", "county", "state_code", "midpoint_lat", "midpoint_lon", "depth_ft", "call", "tiers", "pad_tier",
           "tiers_below", "above_wca1_ft"]].to_csv(out / "wells_all.csv", index=False)
    summary["all_pads"] = {"pads": allp["call"].value_counts().to_dict(), "wells": wells["call"].value_counts().to_dict(),
                           "wells_by_state": pd.crosstab(wells["state_code"], wells["call"]).to_dict("index"),
                           "wells_by_county": pd.crosstab(wells["county"], wells["call"]).to_dict("index")}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--verdicts", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.out, a.cache, a.verdicts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
