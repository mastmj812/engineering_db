"""BOX sticks, phase 1b (plan): WCXY evidence pass, Delaware (read-only).

    python -m scripts.box_sticks_wcxy --out docs/box_sticks/wcxy-<date> --cache <phase 0 cache>

Michael 2026-11-12: WCXY = a well landed in the XY sands of the Wolfcamp A, essentially only present north of the
Grisham fault complex. Vendors also write WCXY on wells that are merely shallow in the WCA where no XY sand exists.
The WCXY extent must therefore be controlled, not learned from the tag. This pass sorts every WCXY-tagged evidence
well by what the depths say:

  stacked      a WCA_1 surface exists at the well (>= 3 WCA_1 wells within 2 mi) and the well sits >= MIN_SEP_FT
               ABOVE it: two distinct landings, the signature of real XY development;
  same_depth   a WCA_1 surface exists and the well is within MIN_SEP_FT of it: a "WCXY" label on a WCA_1-depth well;
  below        a WCA_1 surface exists and the well is >= MIN_SEP_FT below it;
  no_wca1      no WCA_1 surface at the well: the depths cannot tell (gap to WCA_2 / BS3_S reported where they exist).

Evidence wells as everywhere in this work (planned surveys and round-100 permit depths excluded), live tags.
Nothing is written to the warehouse, and no extent is built here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import landing_surfaces as ls
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1b as p1b

MI = ls.M_PER_MI
MIN_SEP_FT = 75.0
COLORS = {"stacked": "#16a34a", "same_depth": "#dc2626", "below": "#7c3aed", "no_wca1": "#f59e0b"}
ORDER = ("stacked", "same_depth", "below", "no_wca1")


def classify(bw: pd.DataFrame) -> pd.DataFrame:
    x = bw[bw["live"] == "WCXY"].copy()
    pts = x[["x", "y"]].to_numpy(float)
    for name, codes in (("wca1", ("WCA_1",)), ("wca2", ("WCA_2",)), ("bs3s", ("BS3_S",)), ("wcb1", ("WCB_1",))):
        x[f"{name}_surface_ft"] = p1b.field_at(bw, codes, pts)
    a1 = bw[bw["live"] == "WCA_1"][["x", "y"]].to_numpy(float)
    tree = cKDTree(a1)
    x["nearest_wca1_mi"] = tree.query(pts, k=1)[0] / MI
    x["wca1_within_1mi"] = tree.query_ball_point(pts, MI, return_length=True)
    x["above_wca1_ft"] = x["wca1_surface_ft"] - x["depth_ft"]
    x["above_wca2_ft"] = x["wca2_surface_ft"] - x["depth_ft"]
    x["below_bs3s_ft"] = x["depth_ft"] - x["bs3s_surface_ft"]
    g = x["above_wca1_ft"]
    x["cls"] = np.where(g.isna(), "no_wca1", np.where(g >= MIN_SEP_FT, "stacked", np.where(g <= -MIN_SEP_FT, "below", "same_depth")))
    return x


def table(x: pd.DataFrame, by: str) -> pd.DataFrame:
    t = pd.crosstab(x[by], x["cls"]).reindex(columns=list(ORDER), fill_value=0)
    t["wells"] = t.sum(axis=1)
    t["stacked_pct"] = 100 * t["stacked"] / t["wells"]
    t["median_above_wca1_ft"] = x.groupby(by)["above_wca1_ft"].median()
    return t.reset_index()


def draw(x: pd.DataFrame, bw: pd.DataFrame, extents: pd.DataFrame, out: Path) -> str:
    fig, axes = plt.subplots(1, 2, figsize=(17, 10))
    wca = bw[bw["live"].isin(["WCA_1", "WCA_2"])]
    ext = extents[(extents["basin"] == "delaware") & (extents["bench"] == "WCA")]
    for ax in axes:
        ax.scatter(wca["x"] / MI, wca["y"] / MI, s=1, c="#d1d5db", linewidths=0, label=f"WCA_1 / WCA_2 wells ({len(wca):,})", rasterized=True)
        for e in ext.itertuples():
            for poly in shapely.get_parts(shapely.make_valid(shapely.from_wkt(e.wkt))):
                if poly.geom_type == "Polygon":
                    px, py = poly.exterior.xy
                    ax.plot(np.asarray(px) / MI, np.asarray(py) / MI, color="#111827", lw=0.8)
        for county, g in x.groupby("county"):
            if len(g) >= 15:
                ax.text(g["x"].median() / MI, g["y"].median() / MI, str(county).upper(), fontsize=8, color="#374151", ha="center",
                        bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.6})
        ax.set_aspect("equal")
        ax.set_xlabel("mi (EPSG:3083 easting)")
    axes[0].set_ylabel("mi (northing)")
    for c in ORDER:
        g = x[x["cls"] == c]
        axes[0].scatter(g["x"] / MI, g["y"] / MI, s=7, c=COLORS[c], linewidths=0, label=f"{c} ({len(g):,})")
    axes[0].legend(fontsize=8, markerscale=2, loc="lower left")
    axes[0].set_title("WCXY-tagged wells by what the depths say (black = pooled WCA extent)", fontsize=10)
    g = x[x["above_wca1_ft"].notna()]
    sc = axes[1].scatter(g["x"] / MI, g["y"] / MI, s=7, c=g["above_wca1_ft"].clip(-200, 400), cmap="RdYlGn", vmin=-200, vmax=400, linewidths=0)
    fig.colorbar(sc, ax=axes[1], shrink=0.6).set_label("ft the WCXY-tagged well sits ABOVE the local WCA_1 surface")
    axes[1].set_title("Separation from the WCA_1 surface (wells with WCA_1 control)", fontsize=10)
    f = out / "wcxy_evidence_map.png"
    fig.savefig(f, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f.name


def run(out: Path, cache: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    w = p0.evidence(d["wells"], d["rule"])
    bw = w[w["basin"] == "delaware"].reset_index(drop=True)
    x = classify(bw)
    x["lat_band"] = (np.floor(x["midpoint_lat"] * 10) / 10).map(lambda v: f"{v:.1f}-{v + 0.1:.1f} N")
    x["rule_moves_to"] = np.where(x["shadow"] != x["live"], x["shadow"], "")
    cols = ["api10", "well_name", "operator", "county", "state_code", "midpoint_lat", "midpoint_lon", "first_production_date", "live_source",
            "vendor", "vendor_raw", "rule_moves_to", "depth_ft", "depth_source", "cls", "above_wca1_ft", "wca1_surface_ft", "nearest_wca1_mi",
            "wca1_within_1mi", "above_wca2_ft", "below_bs3s_ft"]
    x[cols].sort_values(["cls", "county"]).to_csv(out / "wcxy_wells.csv", index=False)
    table(x, "county").sort_values("wells", ascending=False).to_csv(out / "by_county.csv", index=False)
    table(x, "lat_band").sort_values("lat_band", ascending=False).to_csv(out / "by_lat_band.csv", index=False)
    table(x, "live_source").to_csv(out / "by_tag_source.csv", index=False)
    table(x, "vendor_raw").sort_values("wells", ascending=False).to_csv(out / "by_vendor_raw.csv", index=False)
    table(x.assign(state=x["state_code"]), "state").to_csv(out / "by_state.csv", index=False)
    has = x["above_wca1_ft"].notna()
    summary = {"code_sha": p0._git_sha(), "tags": "live", "min_sep_ft": MIN_SEP_FT, "wcxy_evidence_wells": len(x),
               "classes": x["cls"].value_counts().to_dict(),
               "above_wca1_ft": {"wells": int(has.sum()), "p10": float(x.loc[has, "above_wca1_ft"].quantile(0.1)),
                                 "median": float(x.loc[has, "above_wca1_ft"].median()), "p90": float(x.loc[has, "above_wca1_ft"].quantile(0.9))},
               "rule_moves": x.loc[x["rule_moves_to"] != "", "rule_moves_to"].value_counts().to_dict(),
               "map": draw(x, bw, d["extents"], out)}
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
