"""BOX sticks: would a "two levels nearby" flag on thickness-carried depths mean anything? (read-only measurement)

    python -m scripts.box_sticks_second_landing --out docs/box_sticks/<folder>/second_landing --cache <phase 0 cache>
        --backtest docs/box_sticks/<folder>/phase3/backtest

The thickness rung carries a bench's depth as an anchor surface + the weighted-median thickness of the same-bench
wells within 5 mi. Where those wells sit at two levels the median takes one of them (pad 22309 LSSH, 2026-11-18).
The in-DSU flag ``two_landings_observed`` only fires where the DSU's own wells show two; this measures a flag for the
carried case, on the thickness rung only.

Definition (``box_sticks_phase1c.levels``, adopted as a flag 2026-11-18): smooth the thickness sample (depth - anchor surface, the rung's own distance
weights) with a BW_FT Gaussian; a second peak >= SEP_FT from the main one, holding >= SHARE of the weight and >= MIN_N
wells (each well to its nearest peak), with the dip between them <= VALLEY x the smaller peak.

Three measurements:
  dsu       today's frame: thickness-rung DSU x bench flagged, per basin and bench;
  holdout   every screened evidence well, same-bench wells within 1 mi hidden, anchor by the rank order of record:
            the error of the carried depth where the sample is flagged against where it is not;
  backtest  the 2023-01-01 frame: flagged against unflagged DSU x bench, scored on the hidden wells.
Nothing is generated and nothing is written to the warehouse.
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
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1 as p1
from scripts import box_sticks_phase1b as p1b
from scripts import box_sticks_phase1c as p1c
from scripts import box_sticks_phase3_backtest as bt
from scripts import box_sticks_phase3_pilot as p3
from scripts.box_sticks_phase1c import BW_FT, GRID_FT, SEPS, VALLEY, levels
from scripts.box_sticks_phase1c import LEVEL_MIN_N as MIN_N
from scripts.box_sticks_phase1c import SECOND_SEP_FT as SEP_FT
from scripts.box_sticks_phase1c import SECOND_SHARE as SHARE

P = ls.PARAMS
MI = ls.M_PER_MI
SHARES = (0.15, 0.25, 0.33)
EXCLUDE_MI = 1.0

def _weights(d_mi: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * (d_mi / (2 * P.wmed_sigma_mi)) ** 2) + 1e-9


def _main_peak(rel: np.ndarray, wt: np.ndarray) -> float:
    g = np.arange(rel.min() - 3 * BW_FT, rel.max() + 3 * BW_FT + GRID_FT, GRID_FT)
    return float(g[np.argmax((wt[None, :] * np.exp(-0.5 * ((g[:, None] - rel[None, :]) / BW_FT) ** 2)).sum(axis=1))])


def holdout(w: pd.DataFrame, extents: pd.DataFrame) -> pd.DataFrame:
    """One row per evidence well the thickness rung can predict with same-bench wells within EXCLUDE_MI hidden."""
    thick, _ = p1c.rankings()
    rows = []
    for basin in sorted(extents["basin"].unique()):
        bw = w[w["basin"] == basin].reset_index(drop=True)
        sets = p1.anchor_sets(extents, basin)
        bxy = bw[["x", "y"]].to_numpy(float)
        F = {n: p1b.field_at(bw, cs, bxy) for n, cs in sets.items()}
        print(f"  {basin} anchor fields built", flush=True)
        for e in extents[extents["basin"] == basin].itertuples():
            geom = shapely.make_valid(shapely.from_wkt(e.wkt))
            for code in ls.extent_codes(basin, e.bench):
                m = ((bw["live"] == code) & shapely.contains_xy(geom, bxy[:, 0], bxy[:, 1])).to_numpy()
                order = [a for a, _, _ in thick.get((basin, code), []) if a in F]
                if m.sum() < 4 or not order:
                    continue
                xy, z, api = bxy[m], bw.loc[m, "depth_ft"].to_numpy(float), bw.loc[m, "api10"].astype(str).to_numpy()
                for i, ks in enumerate(cKDTree(xy).query_ball_point(xy, P.thick_max_mi * MI)):
                    ks = np.asarray(ks, int)
                    d = np.hypot(xy[ks, 0] - xy[i, 0], xy[ks, 1] - xy[i, 1])
                    ks, d = ks[d >= EXCLUDE_MI * MI], d[d >= EXCLUDE_MI * MI] / MI
                    for a in order:
                        A = F[a][m]
                        ok = np.isfinite(A[ks])
                        kk = ks[ok]
                        if not np.isfinite(A[i]) or len(kk) < P.n_min or ls.max_angular_gap_deg(xy[kk], xy[i]) >= 180.0:
                            continue
                        rel, wt = z[kk] - A[kk], _weights(d[ok])
                        t = ls.weighted_median(rel, wt)
                        lv = levels(rel, wt)
                        rows.append({"basin": basin, "code": code, "api10": api[i], "anchor": a, "n": len(kk), "err_ft": abs(z[i] - (A[i] + t)),
                                     "signed_ft": z[i] - (A[i] + t), "main_minus_median_ft": _main_peak(rel, wt) - t, **lv})
                        break
    return pd.DataFrame(rows)


def dsu_flags(db: pd.DataFrame, ev: pd.DataFrame, pads: pd.DataFrame, extents: pd.DataFrame) -> pd.DataFrame:
    """The thickness sample of every thickness-rung DSU x bench of a frame, rebuilt as the chain builds it."""
    rows = []
    pc = pads.set_index("pad_id")[["cx", "cy"]]
    for basin in sorted(extents["basin"].unique()):
        bw = ev[ev["basin"] == basin].reset_index(drop=True)
        sets = p1.anchor_sets(extents, basin)
        bxy = bw[["x", "y"]].to_numpy(float)
        F = {n: p1b.field_at(bw, cs, bxy) for n, cs in sets.items()}
        print(f"  {basin} anchor fields built", flush=True)
        t = db[(db["basin"] == basin) & (db["rung"] == "thickness")]
        for code, g in t.groupby("code"):
            m = (bw["live"] == code).to_numpy()
            cxy, cz = bxy[m], bw.loc[m, "depth_ft"].to_numpy(float)
            tree = cKDTree(cxy)
            pts = pc.loc[g["pad_id"]].to_numpy(float)
            for r, pt, ks in zip(g.itertuples(), pts, tree.query_ball_point(pts, P.thick_max_mi * MI), strict=True):
                ks = np.asarray(ks, int)
                kk = ks[np.isfinite(F[r.how][m][ks])]
                d = np.hypot(cxy[kk, 0] - pt[0], cxy[kk, 1] - pt[1]) / MI
                rel, wt = cz[kk] - F[r.how][m][kk], _weights(d)
                tm = ls.weighted_median(rel, wt)
                rows.append({"basin": basin, "code": code, "pad_id": r.pad_id, "anchor": r.how, "z": r.z, "n": len(kk), "thickness_ft": tm,
                             "anchor_at_dsu_ft": r.z - tm, "main_minus_median_ft": _main_peak(rel, wt) - tm, **levels(rel, wt)})
    return pd.DataFrame(rows)


def _err(g: pd.DataFrame, col: str = "err_ft") -> dict:
    return {"n": len(g), "median_ft": round(float(g[col].median()), 1) if len(g) else None, "p90_ft": round(float(g[col].quantile(0.9)), 1) if len(g) else None,
            "over_150_pct": round(100 * float((g[col] > 150).mean()), 1) if len(g) else None}


def grid(t: pd.DataFrame, col: str | None) -> pd.DataFrame:
    """Share flagged, and the error of flagged against unflagged, for every (separation, share) variant."""
    rows = []
    for b, g in list(t.groupby("basin")) + [("both", t)]:
        for s in SEPS:
            for sh in SHARES:
                f = g[f"share_{int(s)}"] >= sh
                row = {"basin": b, "sep_ft": s, "share": sh, "n": len(g), "flagged": int(f.sum()), "flagged_pct": round(100 * float(f.mean()), 1)}
                if col:
                    row |= {f"flagged_{k}": v for k, v in _err(g[f], col).items() if k != "n"} | {f"unflagged_{k}": v for k, v in _err(g[~f], col).items() if k != "n"}
                rows.append(row)
    return pd.DataFrame(rows)


def run(out: Path, cache: Path, backtest: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    ev = p0.evidence(d["wells"], d["rule"]).merge(pd.read_pickle(cache / "p2a_screen.pkl"), on="api10", how="left")
    ev = ev[ev["screen"] == "keep"].reset_index(drop=True)
    F = p3.build_frame(cache)
    flag = f"share_{int(SEP_FT)}"

    print("dsu", flush=True)
    dsu = dsu_flags(F["db"], ev, F["pads"], d["extents"])
    dsu["flag"] = dsu[flag] >= SHARE
    dsu.to_csv(out / "dsu_thickness.csv.gz", index=False, compression="gzip")
    by = dsu.groupby(["basin", "code"]).agg(dsu_bench=("flag", "size"), flagged=("flag", "sum")).reset_index()
    by["flagged_pct"] = (100 * by["flagged"] / by["dsu_bench"]).round(1)
    by.to_csv(out / "dsu_by_bench.csv", index=False)
    grid(dsu, None).to_csv(out / "dsu_grid.csv", index=False)

    print("holdout", flush=True)
    ho = holdout(ev, d["extents"])
    ho["flag"] = ho[flag] >= SHARE
    # the second level's own miss: how far the held-out well is from the OTHER level (median shifted by the peak offset)
    ho["second_err_ft"] = (ho["signed_ft"] - ho["main_minus_median_ft"] - ho[f"off_{int(SEP_FT)}"]).abs()
    ho.to_csv(out / "holdout_wells.csv.gz", index=False, compression="gzip")
    grid(ho, "err_ft").to_csv(out / "holdout_grid.csv", index=False)
    hb = pd.DataFrame([{"basin": b, "code": c, **{f"flagged_{k}": v for k, v in _err(g[g["flag"]]).items()},
                        **{f"unflagged_{k}": v for k, v in _err(g[~g["flag"]]).items()}} for (b, c), g in ho.groupby(["basin", "code"])])
    hb.to_csv(out / "holdout_by_bench.csv", index=False)

    print("backtest", flush=True)
    Fb, _ = bt.backtest_frame(cache)
    seen = set(Fb["u"]["api10"].astype(str))
    bd = dsu_flags(Fb["db"], ev[ev["api10"].astype(str).isin(seen)].reset_index(drop=True), Fb["pads"], d["extents"])
    bd["flag"] = bd[flag] >= SHARE
    W = pd.read_csv(backtest / "backtest_wells.csv")
    W = W[W["depth_ft"].notna() & (W["rung"] == "thickness")].merge(bd, on=["pad_id", "code"], how="inner")
    W["err_ft"] = (W["depth_ft"] - W["z"]).abs()
    W["second_err_ft"] = (W["depth_ft"] - (W["z"] + W["main_minus_median_ft"] + W[f"off_{int(SEP_FT)}"])).abs()
    W.to_csv(out / "backtest_wells.csv", index=False)
    grid(W.assign(basin=W["area"]), "err_ft").to_csv(out / "backtest_grid.csv", index=False)

    def split(t: pd.DataFrame) -> dict:
        f = t[t["flag"]]
        return {"flagged": _err(f), "unflagged": _err(t[~t["flag"]]),
                "flagged_nearer_second_level_pct": round(100 * float((f["second_err_ft"] < f["err_ft"]).mean()), 1) if len(f) else None}

    one = W[~W["two_landing"]]
    summary = {"code_sha": p0._git_sha(), "tags": "live", "definition": {"bw_ft": BW_FT, "sep_ft": SEP_FT, "share": SHARE, "min_n": MIN_N, "valley": VALLEY},
               "dsu": {b: {"thickness_dsu_bench": len(g), "flagged": int(g["flag"].sum()), "flagged_pct": round(100 * float(g["flag"].mean()), 1)}
                       for b, g in dsu.groupby("basin")},
               "holdout": {b: split(g) for b, g in ho.groupby("basin")},
               "backtest": {"dsu_bench": int(W.groupby(["pad_id", "code"]).ngroups), "dsu_bench_flagged": int(W[W["flag"]].groupby(["pad_id", "code"]).ngroups),
                            "all_hidden_wells": split(W), "one_landing_pairs_only": split(one)}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--backtest", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.out, a.cache, a.backtest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
