"""BOX — render the fixed-in-time rock proxy used by the drift decomposition (read-only).

    python -m scripts.box_rock_map [--wells docs/box/step1-2026-10-06] [--out docs/box/step6-2026-10-12/decomp]

Same definition as box/drift_decomp.rock_proxy: on a 1/2-mi grid inside the WCA extent of record, the median 12-mo oil per
1,000 ft (Novi pass-through) of the 15 nearest REFERENCE wells (gate-1 WCA, first production 2016–2019, lateral 6,000–13,000 ft,
midpoint in a TC area of record). Coverage = distance to the 15th reference well (<= 3 mi used in the decomposition; 3–5 mi =
the sensitivity run). Writes rock_map.png + rock_grid.csv. Reads only box.extent / box.tc_area (READ ONLY).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.colors import BoundaryNorm, ListedColormap
from scipy.spatial import cKDTree

from box import drift_decomp as dd
from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import tc_area_report as tar
from box import tc_curve_report as rep
from etl.db import get_connection

CELL_FT = 2640.0
MI = 5280.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, default=Path("docs") / "box" / "step1-2026-10-06")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step6-2026-10-12" / "decomp")
    a = ap.parse_args(argv)
    with get_connection() as conn:
        ext = tar.pull_extent(conn)["geom_ft"]
        areas = rep.pull_areas(conn)["geoms"]
    w, _ = exclusions.drop(egr.load_final_sets(a.wells, ("WCA",)))
    w["lateral_ft"] = pd.to_numeric(w["lateral_length_ft"], errors="coerce")
    x, y = eg._transformer().transform(w["mid_lon"].to_numpy(float), w["mid_lat"].to_numpy(float))
    w["x"], w["y"] = np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT
    w["area_no"] = rep.assign_area(np.column_stack([w["x"], w["y"]]), areas)
    w["fy"] = w["first_production_date"].map(lambda f: f.year)
    w["oil12_kft"] = pd.to_numeric(w["oil12_kft"], errors="coerce")
    ref = w[(w.area_no > 0) & w.fy.between(*dd.REF_YEARS) & w.lateral_ft.between(*dd.REF_LAT) & (w.oil12_kft > 0)]
    new = w[(w.area_no > 0) & w.fy.between(2021, 2024) & (w.lateral_ft > 0)]
    # grid inside the extent
    x0, y0, x1, y1 = ext.bounds
    gx, gy = np.meshgrid(np.arange(x0, x1, CELL_FT) + CELL_FT / 2, np.arange(y0, y1, CELL_FT) + CELL_FT / 2)
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    shapely.prepare(ext)
    inside = shapely.contains_xy(ext, pts[:, 0], pts[:, 1])
    dist, j = cKDTree(ref[["x", "y"]].to_numpy()).query(pts, k=dd.K_ROCK)
    prox = np.median(ref["oil12_kft"].to_numpy(float)[j], axis=1)
    dk = dist[:, -1]
    grid = pd.DataFrame({"x_ft": pts[:, 0], "y_ft": pts[:, 1], "inside": inside, "rock_proxy_bbl_kft": prox, "dist_15th_mi": dk / MI})
    grid[grid.inside].to_csv(a.out / "rock_grid.csv", index=False)

    fig, axs = plt.subplots(1, 2, figsize=(17, 9.5))
    shape = gx.shape
    # left: proxy, faded 3-5 mi, blank > 5 mi
    P = np.where(inside & (dk <= 5 * MI), prox, np.nan).reshape(shape)
    lo, hi = np.nanpercentile(P, [2, 98])
    ext_extent = (x0, x0 + shape[1] * CELL_FT, y0, y0 + shape[0] * CELL_FT)
    near = np.where(inside & (dk <= 3 * MI), prox, np.nan).reshape(shape)
    mid = np.where(inside & (dk > 3 * MI) & (dk <= 5 * MI), prox, np.nan).reshape(shape)
    axs[0].imshow(mid, origin="lower", extent=ext_extent, cmap="Blues", vmin=lo, vmax=hi, alpha=0.35, interpolation="nearest")  # 3-5 mi: same scale, faint
    im = axs[0].imshow(near, origin="lower", extent=ext_extent, cmap="Blues", vmin=lo, vmax=hi, interpolation="nearest")
    axs[0].scatter(ref["x"], ref["y"], s=1.5, c="#111827", alpha=0.35, linewidths=0, label=f"2016–19 reference wells (n {len(ref):,})")
    fig.colorbar(im, ax=axs[0], shrink=0.55, label="rock proxy: median 12-mo oil, bbl per 1,000 ft (15 nearest 2016–19 wells)")
    axs[0].set_title("Rock proxy, fixed in time (solid = 15th reference well <= 3 mi; faint = 3–5 mi; blank = > 5 mi)", fontsize=10)
    # right: coverage classes + new wells
    C = np.where(inside, np.digitize(dk / MI, [3.0, 5.0]), np.nan).reshape(shape)
    cmap = ListedColormap(["#dbe9f6", "#f6e3c7", "#efc7c7"])
    axs[1].imshow(C, origin="lower", extent=ext_extent, cmap=cmap, norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3), interpolation="nearest")
    for k, (lab, col) in enumerate((("≤ 3 mi (decomposition)", "#dbe9f6"), ("3–5 mi (sensitivity)", "#f6e3c7"), ("> 5 mi (no proxy)", "#efc7c7"))):
        axs[1].scatter([], [], marker="s", s=80, c=col, label=f"15th reference well {lab}")
    axs[1].scatter(new["x"], new["y"], s=3, c="#eb6834", linewidths=0, label=f"2021–24 wells (n {len(new):,})")
    axs[1].set_title("Where the proxy is trustworthy, and where new drilling went", fontsize=10)
    for ax in axs:
        for g in areas:
            for poly in getattr(g, "geoms", [g]):
                ax.plot(*poly.exterior.xy, color="#6b7280", lw=0.5)
        for poly in getattr(ext, "geoms", [ext]):
            ax.plot(*poly.exterior.xy, color="#111827", lw=1.2)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.legend(loc="lower left", fontsize=8, markerscale=3)
    fig.suptitle(f"BOX drift decomposition — derived rock map (Delaware WCA, TC areas of record outlined) · built {dt.datetime.now(tz=dt.UTC).date()}", fontsize=11)
    fig.tight_layout()
    fig.savefig(a.out / "rock_map.png", dpi=110)
    cov = grid[grid.inside]
    print(f"grid cells {len(cov):,}: <=3 mi {np.mean(cov.dist_15th_mi <= 3):.0%}, 3-5 mi {np.mean((cov.dist_15th_mi > 3) & (cov.dist_15th_mi <= 5)):.0%}, >5 mi {np.mean(cov.dist_15th_mi > 5):.0%}")
    print(f"proxy P10/P50/P90 (covered <=5 mi): {np.nanpercentile(P, [10, 50, 90]).round(0)}")
    print(f"wrote {a.out / 'rock_map.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
