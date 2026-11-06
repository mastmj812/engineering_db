"""Landing surfaces at the extent fringe (read-only) — formation_tag_redesign step A prep, part 2.

    python -m scripts.tag_surface_fringe --cache <scoreboard cache> --out docs/formation_tag_redesign/surface-fringe-<date>

Same grain and hold-out as scripts.tag_surface_density (evidence wells of a BOX record extent's code, live tag, midpoint
inside the extent; each well held out with every same-code well within 1/4 mi). Everything is split by DISTANCE IN
FROM THE EXTENT BOUNDARY (0-1, 1-2, 2-4, > 4 mi): Michael's opportunity set is the fringe between the core and the
extent bound.

Two predictions of a held-out well's depth:
  direct     the code's own surface: robust plane of same-code wells within 2 mi (>= 3; median below 4 wells).
  thickness  structure from a thick, well-drilled neighbouring bench plus the local thickness down (or up) to the code:
             A(p) = robust plane of the anchor bench's wells within 2 mi of p (>= 3), at p;
             t    = median over same-code wells within 5 mi (hold-out applied) of (their depth - A at them);
             prediction = A(well) + t.   (Needs >= 3 thickness samples.)
             Anchors: Delaware AVA_*, BS1_S, BS2_C, BS3_C -> BS2_S (BS2_S itself -> BS3_C); BS3_S and WCXY / WCA_1 /
             WCA_2 / WCB_1 / WCB_2 / WCC -> the WCA family. The WCA codes themselves are the anchor, so they get no
             thickness prediction (it would reuse the held-out well). Midland MS / JM / DEAN -> LSSH (LSSH -> JM); WCA_1 -> LSSH; WCB_1 / WCB_2 /
             WCC / WCD -> WCA_1.
Reported per basin, code and zone: wells, share predictable, median / P90 |error| ft for each method, and node
coverage (direct >= 3 wells within 2 mi). Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import tag_scoreboard as sb
from scripts.tag_surface_density import (
    EXTENT_OF,
    HOLDOUT_MI,
    NODE_MI,
    robust_predict,
    wells_frame,
)

R_MI, N_MIN, THICK_R_MI, THICK_N = 2.0, 3, 5.0, 3
ZONES = (0.0, 1.0, 2.0, 4.0, np.inf)
ZONE_LABELS = ("0-1 mi", "1-2 mi", "2-4 mi", "> 4 mi")
WCA_FAM = ("WCXY", "WCA_1", "WCA_2")
ANCHOR = {
    "delaware": {"AVA_0": ("BS2_S",), "AVA_1": ("BS2_S",), "AVA_2": ("BS2_S",), "BS1_S": ("BS2_S",), "BS2_C": ("BS2_S",),
                 "BS2_S": ("BS3_C",), "BS3_C": ("BS2_S",), "BS3_S": WCA_FAM, "WCXY": WCA_FAM, "WCA_1": WCA_FAM, "WCA_2": WCA_FAM,
                 "WCB_1": WCA_FAM, "WCB_2": WCA_FAM, "WCC": WCA_FAM},
    "midland": {"MS": ("LSSH",), "JM": ("LSSH",), "DEAN": ("LSSH",), "LSSH": ("JM",), "WCA_1": ("LSSH",),
                "WCB_1": ("WCA_1",), "WCB_2": ("WCA_1",), "WCC": ("WCA_1",), "WCD": ("WCA_1",)},
}


def zone(d_mi: np.ndarray) -> np.ndarray:
    return np.array(ZONE_LABELS, dtype=object)[np.clip(np.searchsorted(ZONES, d_mi, side="right") - 1, 0, len(ZONE_LABELS) - 1)]


def plane_at(tree: cKDTree, xy: np.ndarray, z: np.ndarray, at: np.ndarray, r_m: float, n_min: int,
             exclude_near: np.ndarray | None = None, hold_m: float = 0.0) -> float:
    js = np.asarray(tree.query_ball_point(at, r_m), int)
    if exclude_near is not None and len(js):
        js = js[np.hypot(xy[js, 0] - exclude_near[0], xy[js, 1] - exclude_near[1]) >= hold_m]
    return robust_predict(xy[js], z[js], at) if len(js) >= n_min else np.nan


def run(cache: Path, out: Path) -> pd.DataFrame:
    out.mkdir(parents=True, exist_ok=True)
    w = wells_frame(cache)
    ex = pd.read_pickle(cache / "extents.pkl")
    rm, hold, trm = R_MI * sb.M_PER_MI, HOLDOUT_MI * sb.M_PER_MI, THICK_R_MI * sb.M_PER_MI
    rows, cov = [], []
    for e in ex.itertuples():
        geom = shapely.from_wkt(e.wkt)
        edge = geom.boundary
        codes = [c for (b, c), xb in EXTENT_OF.items() if b == e.basin and xb == e.bench] or [e.bench]
        minx, miny, maxx, maxy = geom.bounds
        step = NODE_MI * sb.M_PER_MI
        gx, gy = np.meshgrid(np.arange(minx, maxx, step), np.arange(miny, maxy, step))
        inside = shapely.contains_xy(geom, gx.ravel(), gy.ravel())
        nodes = np.column_stack([gx.ravel()[inside], gy.ravel()[inside]])
        nz = zone(shapely.distance(shapely.points(nodes), edge) / sb.M_PER_MI)
        bw = w[w["basin"] == e.basin]
        for code in codes:
            c = bw[(bw["live"] == code) & shapely.contains_xy(geom, bw["x"].to_numpy(), bw["y"].to_numpy())].reset_index(drop=True)
            if len(c) < 3:
                continue
            xy, z = c[["x", "y"]].to_numpy(float), c["depth_ft"].to_numpy(float)
            tree = cKDTree(xy)
            cnt = tree.query_ball_point(nodes, rm, return_length=True)
            for zl in ZONE_LABELS:
                m = nz == zl
                cov.append({"basin": e.basin, "code": code, "zone": zl, "nodes": int(m.sum()),
                            "coverage_pct": 100 * float((cnt[m] >= N_MIN).mean()) if m.any() else np.nan})
            # anchor bench (all of its wells in the basin, any extent: the thick bench may reach farther)
            acodes = ANCHOR.get(e.basin, {}).get(code)
            a = bw[bw["live"].isin(acodes)] if acodes else bw.iloc[0:0]
            axy, az = a[["x", "y"]].to_numpy(float), a["depth_ft"].to_numpy(float)
            atree = cKDTree(axy) if len(a) >= N_MIN else None
            same_fam = acodes is not None and code in acodes
            if same_fam:  # WCXY / WCA_1 / WCA_2 ARE the anchor: the held-out well would leak into its own thickness samples
                atree = None
            # A at every code well (for the thickness samples); for a WCA code the family includes the well itself
            A = np.array([plane_at(atree, axy, az, xy[k], rm, N_MIN, xy[k] if same_fam else None, hold) if atree else np.nan
                          for k in range(len(c))])
            dz = shapely.distance(shapely.points(xy), edge) / sb.M_PER_MI
            zw = zone(dz)
            for i in range(len(c)):
                js = np.asarray(tree.query_ball_point(xy[i], rm), int)
                js = js[np.hypot(xy[js, 0] - xy[i, 0], xy[js, 1] - xy[i, 1]) >= hold]
                direct = robust_predict(xy[js], z[js], xy[i]) if len(js) >= N_MIN else np.nan
                near = np.inf
                if len(js):
                    near = float(np.min(np.hypot(xy[js, 0] - xy[i, 0], xy[js, 1] - xy[i, 1]))) / sb.M_PER_MI
                thick = np.nan
                if atree is not None:
                    Ai = plane_at(atree, axy, az, xy[i], rm, N_MIN, xy[i] if same_fam else None, hold)
                    ks = np.asarray(tree.query_ball_point(xy[i], trm), int)
                    ks = ks[(np.hypot(xy[ks, 0] - xy[i, 0], xy[ks, 1] - xy[i, 1]) >= hold) & np.isfinite(A[ks])]
                    if np.isfinite(Ai) and len(ks) >= THICK_N:
                        thick = Ai + float(np.median(z[ks] - A[ks]))
                rows.append({"basin": e.basin, "code": code, "zone": zw[i], "edge_mi": dz[i], "nearest_same_mi": near,
                             "z": z[i], "direct_err": abs(z[i] - direct) if np.isfinite(direct) else np.nan,
                             "thick_err": abs(z[i] - thick) if np.isfinite(thick) else np.nan})
    r = pd.DataFrame(rows)
    r.to_csv(out / "held_out_wells.csv.gz", index=False)
    pd.DataFrame(cov).to_csv(out / "node_coverage_by_zone.csv", index=False)
    return r


def summarize(r: pd.DataFrame, cov: pd.DataFrame, out: Path) -> None:
    def agg(g: pd.DataFrame) -> pd.Series:
        both = g["direct_err"].notna() & g["thick_err"].notna()
        return pd.Series({
            "wells": len(g),
            "direct_ok_pct": 100 * g["direct_err"].notna().mean(), "thick_ok_pct": 100 * g["thick_err"].notna().mean(),
            "either_ok_pct": 100 * (g["direct_err"].notna() | g["thick_err"].notna()).mean(),
            "direct_med": g["direct_err"].median(), "direct_p90": g["direct_err"].quantile(0.9),
            "thick_med": g["thick_err"].median(), "thick_p90": g["thick_err"].quantile(0.9),
            "both_n": int(both.sum()), "both_direct_med": g.loc[both, "direct_err"].median(), "both_thick_med": g.loc[both, "thick_err"].median(),
        })
    by_zone = r.groupby(["basin", "zone"]).apply(agg, include_groups=False).reset_index()
    by_zone.to_csv(out / "by_basin_zone.csv", index=False)
    r.groupby(["basin", "code", "zone"]).apply(agg, include_groups=False).reset_index().to_csv(out / "by_code_zone.csv", index=False)
    c = cov.groupby(["basin", "zone"]).apply(lambda g: np.average(g["coverage_pct"].fillna(0), weights=g["nodes"].clip(lower=1)),
                                             include_groups=False).rename("node_coverage_pct").reset_index()
    c.to_csv(out / "node_coverage_basin_zone.csv", index=False)
    r.assign(near_band=pd.cut(r["nearest_same_mi"], [0, 0.5, 1, 2, np.inf], labels=["0.25-0.5", "0.5-1", "1-2", "> 2 (none in 2 mi)"])) \
        .groupby(["basin", "near_band"], observed=True).apply(agg, include_groups=False).reset_index().to_csv(out / "by_nearest_distance.csv", index=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    r = run(a.cache, a.out)
    summarize(r, pd.read_csv(a.out / "node_coverage_by_zone.csv"), a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
