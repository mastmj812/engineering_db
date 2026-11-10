"""Old vs new landing-surface estimator, held-out accuracy (read-only) — box/landing_surfaces estimator rev 1.

    python -m scripts.tag_surface_validate --cache <scoreboard cache> --out docs/formation_tag_redesign/surface-estimator-rev1-<date>

Same grain and hold-out as surface-density / surface-fringe: each evidence well of a BOX record extent's code is held
out together with every same-code well within 1/4 mi, then predicted from the remaining same-code wells within 2 mi
(>= 3):
  old  the first step-A estimator: a robust plane whenever >= 4 wells remain (else their median);
  new  box.landing_surfaces.estimate: the distance-weighted median, or a plane only with >= 6 surrounding wells, a dip
       <= 300 ft/mi and <= 150 ft off the weighted median.
Errors are split by distance in from the extent boundary and by whether the remaining wells SURROUND the held-out
well (largest empty sector < 180 deg). The one-sided case is where the old plane failed (ART SMITH STATE #130H).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import landing_surfaces as ls
from box import tag_scoreboard as sb
from scripts.tag_surface_density import (
    EXTENT_OF,
    HOLDOUT_MI,
    robust_predict,
    wells_frame,
)
from scripts.tag_surface_fringe import ZONE_LABELS, zone


def run(cache: Path, out: Path) -> pd.DataFrame:
    out.mkdir(parents=True, exist_ok=True)
    w = wells_frame(cache)
    ex = pd.read_pickle(cache / "extents.pkl")
    rm, hold = 2.0 * sb.M_PER_MI, HOLDOUT_MI * sb.M_PER_MI
    rows = []
    for e in ex.itertuples():
        geom = shapely.from_wkt(e.wkt)
        codes = [c for (b, c), xb in EXTENT_OF.items() if b == e.basin and xb == e.bench] or [e.bench]
        bw = w[w["basin"] == e.basin]
        for code in codes:
            c = bw[(bw["live"] == code) & shapely.contains_xy(geom, bw["x"].to_numpy(), bw["y"].to_numpy())].reset_index(drop=True)
            if len(c) < 4:
                continue
            xy, z = c[["x", "y"]].to_numpy(float), c["depth_ft"].to_numpy(float)
            tree = cKDTree(xy)
            zw = zone(shapely.distance(shapely.points(xy), geom.boundary) / sb.M_PER_MI)
            for i, js in enumerate(tree.query_ball_point(xy, rm)):
                js = np.asarray(js, int)
                js = js[np.hypot(xy[js, 0] - xy[i, 0], xy[js, 1] - xy[i, 1]) >= hold]
                if len(js) < 3:
                    continue
                old = robust_predict(xy[js], z[js], xy[i])
                new, how = ls.estimate(xy[js], z[js], xy[i])
                rows.append({"basin": e.basin, "code": code, "zone": zw[i], "n": len(js),
                             "surrounded": ls.max_angular_gap_deg(xy[js], xy[i]) < 180.0, "how": how,
                             "old_err": abs(z[i] - old), "new_err": abs(z[i] - new)})
    r = pd.DataFrame(rows)
    r.to_csv(out / "held_out.csv.gz", index=False)

    def agg(g: pd.DataFrame) -> pd.Series:
        return pd.Series({"wells": len(g), "old_med": g["old_err"].median(), "new_med": g["new_err"].median(),
                          "old_p90": g["old_err"].quantile(0.9), "new_p90": g["new_err"].quantile(0.9),
                          "old_p99": g["old_err"].quantile(0.99), "new_p99": g["new_err"].quantile(0.99),
                          "old_over_300_pct": 100 * (g["old_err"] > 300).mean(), "new_over_300_pct": 100 * (g["new_err"] > 300).mean()})
    for name, keys in (("by_basin", ["basin"]), ("by_basin_zone", ["basin", "zone"]), ("by_basin_surrounded", ["basin", "surrounded"]),
                       ("by_basin_code", ["basin", "code"])):
        t = r.groupby(keys).apply(agg, include_groups=False).reset_index()
        if "zone" in keys:
            t["zone"] = pd.Categorical(t["zone"], categories=list(ZONE_LABELS), ordered=True)
            t = t.sort_values(keys)
        t.to_csv(out / f"{name}.csv", index=False)
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.cache, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
