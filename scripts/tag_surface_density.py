"""How many wells, within what radius, does a landing surface need? (read-only) — formation_tag_redesign step A prep.

    python -m scripts.tag_surface_density --cache <scoreboard cache> --out docs/formation_tag_redesign/surface-density-<date>

For every BOX record extent and each formation_blueox code that belongs to it (the Delaware WCA extent holds WCXY /
WCA_1 / WCA_2; every other extent holds its own code), with evidence wells only (survey depth else clean tvd_ft, no
planned survey, >= 4,000 ft) whose LIVE tag is that code and whose lateral midpoint lies inside the extent:

  * coverage(R, N): the share of the extent's 1/4-mi lattice nodes with >= N such wells within R;
  * accuracy(R, N): hold each well out, together with every same-code well within 1/4 mi of it (a node is never
    closer than that to the wells it is estimated from), fit the surface from the remaining same-code wells within R,
    and predict the held-out depth. A robust plane (2.5-sigma MAD rejection, one refit) is used when 4 or more wells
    remain, else their median. Reported: the share of wells that qualify (>= N remain), and median / P90 |error| ft.
  * gap: the local median gap to the adjacent bench (baseline band separation), the scale the error is judged on.

Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import tag_scoreboard as sb

RADII_MI = (1.0, 1.5, 2.0, 3.0)
NS = (2, 3, 4, 5, 6, 8, 10)
NODE_MI = 0.25
HOLDOUT_MI = 0.25
EXTENT_OF = {("delaware", c): "WCA" for c in ("WCXY", "WCA_1", "WCA_2")}


def robust_predict(xy: np.ndarray, z: np.ndarray, at: np.ndarray) -> float:
    if len(z) < 4:
        return float(np.median(z))
    X = np.column_stack([np.ones(len(z)), (xy[:, 0] - at[0]) / 1609.344, (xy[:, 1] - at[1]) / 1609.344])
    c, *_ = np.linalg.lstsq(X, z, rcond=None)
    r = z - X @ c
    mad = np.median(np.abs(r - np.median(r))) or 1.0
    ok = np.abs(r) <= 2.5 * 1.4826 * mad
    if ok.sum() >= 4 and ok.sum() < len(z):
        c, *_ = np.linalg.lstsq(X[ok], z[ok], rcond=None)
    return float(c[0])


def wells_frame(cache: Path) -> pd.DataFrame:
    w = sb.evidence_depth(pd.read_pickle(cache / "wells.pkl"), "best")
    w = w[w["clean"]].reset_index(drop=True)
    mid = np.array([p[len(p) // 2] if p else (np.nan, np.nan) for p in w["pts"]], float)
    w["x"], w["y"] = mid[:, 0], mid[:, 1]
    return w[np.isfinite(w["x"])].reset_index(drop=True)


def run(cache: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    w = wells_frame(cache)
    ex = pd.read_pickle(cache / "extents.pkl")
    sep = pd.read_csv(sb.ROOT / "docs" / "formation_tag_redesign" / "baseline-2026-11-05" / "best_live_band_separation.csv")
    cov_rows, acc_rows = [], []
    for e in ex.itertuples():
        geom = shapely.from_wkt(e.wkt)
        codes = [c for (b, c), xb in EXTENT_OF.items() if b == e.basin and xb == e.bench] or [e.bench]
        minx, miny, maxx, maxy = geom.bounds
        step = NODE_MI * sb.M_PER_MI
        gx, gy = np.meshgrid(np.arange(minx, maxx, step), np.arange(miny, maxy, step))
        inside = shapely.contains_xy(geom, gx.ravel(), gy.ravel())
        nodes = np.column_stack([gx.ravel()[inside], gy.ravel()[inside]])
        for code in codes:
            c = w[(w["basin"] == e.basin) & (w["live"] == code)]
            c = c[shapely.contains_xy(geom, c["x"].to_numpy(), c["y"].to_numpy())].reset_index(drop=True)
            if len(c) < 3:
                continue
            xy, z = c[["x", "y"]].to_numpy(float), c["depth_ft"].to_numpy(float)
            tree = cKDTree(xy)
            g = sep[(sep["basin"] == e.basin) & ((sep["upper"] == code) | (sep["lower"] == code))]
            gap = float(g["median_gap_ft"].min()) if len(g) else np.nan
            for r in RADII_MI:
                rm = r * sb.M_PER_MI
                cnt = tree.query_ball_point(nodes, rm, return_length=True)
                for n in NS:
                    cov_rows.append({"basin": e.basin, "extent": e.bench, "code": code, "wells": len(c), "R_mi": r, "N": n,
                                     "nodes": len(nodes), "coverage_pct": 100 * float((cnt >= n).mean())})
                nb = tree.query_ball_point(xy, rm)
                pred, nrem = np.full(len(c), np.nan), np.zeros(len(c), int)
                for i, js in enumerate(nb):
                    js = np.asarray(js, int)
                    js = js[np.hypot(xy[js, 0] - xy[i, 0], xy[js, 1] - xy[i, 1]) >= HOLDOUT_MI * sb.M_PER_MI]
                    nrem[i] = len(js)
                    if len(js) >= min(NS):
                        pred[i] = robust_predict(xy[js], z[js], xy[i])
                err = np.abs(z - pred)
                for n in NS:
                    m = nrem >= n
                    acc_rows.append({"basin": e.basin, "extent": e.bench, "code": code, "wells": len(c), "R_mi": r, "N": n,
                                     "qualify_pct": 100 * float(m.mean()), "med_abs_err_ft": float(np.median(err[m])) if m.any() else np.nan,
                                     "p90_abs_err_ft": float(np.percentile(err[m], 90)) if m.any() else np.nan, "gap_ft": gap})
    cov, acc = pd.DataFrame(cov_rows), pd.DataFrame(acc_rows)
    cov.to_csv(out / "coverage.csv", index=False)
    acc.to_csv(out / "accuracy.csv", index=False)
    j = cov.merge(acc, on=["basin", "extent", "code", "wells", "R_mi", "N"])
    j["p90_over_gap"] = j["p90_abs_err_ft"] / j["gap_ft"]
    j.to_csv(out / "coverage_accuracy.csv", index=False)
    # basin-pooled curve, weighted by wells
    pooled = j.groupby(["basin", "R_mi", "N"]).apply(lambda g: pd.Series({
        "coverage_pct": np.average(g["coverage_pct"], weights=g["nodes"]),
        "qualify_pct": np.average(g["qualify_pct"], weights=g["wells"]),
        "med_abs_err_ft": np.average(g["med_abs_err_ft"].fillna(0), weights=g["wells"]),
        "p90_abs_err_ft": np.average(g["p90_abs_err_ft"].fillna(0), weights=g["wells"]),
        "p90_over_gap": np.average(g["p90_over_gap"].fillna(0), weights=g["wells"])}), include_groups=False).reset_index()
    pooled.to_csv(out / "pooled.csv", index=False)
    s = {"wells": len(w), "radii_mi": RADII_MI, "N": NS, "node_mi": NODE_MI, "holdout_mi": HOLDOUT_MI}
    (out / "summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.cache, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
