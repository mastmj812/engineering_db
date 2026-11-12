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
MOAT_FT = 50.0       # empty band that separates two landings
MOAT_LEVELS = (40.0, 50.0, 60.0, 75.0)
NEAR_MI = 1.0        # neighbourhood for the landing test
DIP_MI = 2.0         # neighbourhood for the local dip
LOOK_FT = 300.0      # how far below the well to look for a deeper landing
MIN_BELOW = 3
COLORS = {"distinct_upper": "#16a34a", "single_landing": "#dc2626", "undetermined": "#f59e0b"}
ORDER = ("distinct_upper", "single_landing", "undetermined")


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


def landings(bw: pd.DataFrame, x: pd.DataFrame, moat_ft: float = MOAT_FT) -> pd.DataFrame:
    """Tag-blind test (Michael 2026-11-12: ST BRIDES 76 3031 112H is a real shallower landing above WCA_1; POLARIS 7
    702H is just a WCA_1 landing with no differentiated shallower landing in the area). A fixed distance from the
    WCA_1 surface split the Polaris pad in two, so the question is asked the way a gunbarrel answers it:

    Take every WCXY- or WCA_1-tagged evidence well within NEAR_MI of the well, whatever its tag, with the local dip
    removed (plane through those within DIP_MI). Walking DOWN from the well, is there an empty band of >= moat_ft
    with >= MIN_BELOW wells beyond it, all within LOOK_FT?
      distinct_upper   yes: the well is in a landing clearly separated from a deeper one;
      single_landing   no, though >= MIN_BELOW wells lie within LOOK_FT below: one continuous landing;
      undetermined     fewer than MIN_BELOW wells below it within LOOK_FT: nothing to separate from.
    """
    fam = bw[bw["live"].isin(["WCXY", "WCA_1"])]
    fxy, fz, fid = fam[["x", "y"]].to_numpy(float), fam["depth_ft"].to_numpy(float), fam["api10"].to_numpy()
    tree = cKDTree(fxy)
    pts, zs, ids = x[["x", "y"]].to_numpy(float), x["depth_ft"].to_numpy(float), x["api10"].to_numpy()
    out, moat, lower, n_below = [], [], [], []
    for i, (js_dip, js) in enumerate(zip(tree.query_ball_point(pts, DIP_MI * MI), tree.query_ball_point(pts, NEAR_MI * MI), strict=True)):
        gx = gy = 0.0
        if len(js_dip) >= 6:
            _, gx, gy = ls._plane_fit(fxy[js_dip], fz[js_dip], pts[i])
            if np.hypot(gx, gy) > ls.PARAMS.max_dip_ft_per_mi:
                gx = gy = 0.0
        js = np.asarray([j for j in js if fid[j] != ids[i]], int)
        adj = fz[js] - (gx * (fxy[js, 0] - pts[i, 0]) + gy * (fxy[js, 1] - pts[i, 1])) / MI
        below = np.sort(adj[(adj >= zs[i]) & (adj <= zs[i] + LOOK_FT)])
        n_below.append(len(below))
        gaps = np.diff(np.concatenate([[zs[i]], below]))
        k = next((k for k, g in enumerate(gaps) if g >= moat_ft and len(below) - k >= MIN_BELOW), None)
        if k is not None:
            out.append("distinct_upper")
            moat.append(float(gaps[k]))
            lower.append(float(np.median(below[k:]) - zs[i]))
        else:
            out.append("single_landing" if len(below) >= MIN_BELOW else "undetermined")
            moat.append(float(gaps.max()) if len(gaps) else np.nan)
            lower.append(np.nan)
    return pd.DataFrame({"landing": out, "moat_ft": moat, "lower_landing_below_ft": lower, "wells_below_300ft": n_below}, index=x.index)


def table(x: pd.DataFrame, by: str) -> pd.DataFrame:
    t = pd.crosstab(x[by], x["landing"]).reindex(columns=list(ORDER), fill_value=0)
    t["wells"] = t.sum(axis=1)
    t["distinct_upper_pct"] = 100 * t["distinct_upper"] / t["wells"]
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
        g = x[x["landing"] == c]
        axes[0].scatter(g["x"] / MI, g["y"] / MI, s=7, c=COLORS[c], linewidths=0, label=f"{c} ({len(g):,})")
    axes[0].legend(fontsize=8, markerscale=2, loc="lower left")
    axes[0].set_title("WCXY-tagged wells: a landing distinct from a deeper one? (black = pooled WCA extent)", fontsize=10)
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
    x = x.join(landings(bw, x))
    sens = {str(int(m)): landings(bw, x, m)["landing"].value_counts().to_dict() for m in MOAT_LEVELS}
    x["group"] = x["operator"].astype(str) + "|" + (x["midpoint_lat"] / 0.01).round().astype(str) + "|" + (x["midpoint_lon"] / 0.01).round().astype(str)
    grp = x[x["landing"] != "undetermined"].groupby("group")["landing"].agg(["size", "nunique"])
    grp = grp[grp["size"] >= 3]
    x["lat_band"] = (np.floor(x["midpoint_lat"] * 10) / 10).map(lambda v: f"{v:.1f}-{v + 0.1:.1f} N")
    x["rule_moves_to"] = np.where(x["shadow"] != x["live"], x["shadow"], "")
    cols = ["api10", "well_name", "operator", "county", "state_code", "midpoint_lat", "midpoint_lon", "first_production_date", "live_source",
            "vendor", "vendor_raw", "rule_moves_to", "depth_ft", "depth_source", "landing", "moat_ft", "lower_landing_below_ft",
            "wells_below_300ft", "cls", "above_wca1_ft", "wca1_surface_ft", "nearest_wca1_mi",
            "wca1_within_1mi", "above_wca2_ft", "below_bs3s_ft"]
    x[cols].sort_values(["landing", "county"]).to_csv(out / "wcxy_wells.csv", index=False)
    table(x, "county").sort_values("wells", ascending=False).to_csv(out / "by_county.csv", index=False)
    table(x, "lat_band").sort_values("lat_band", ascending=False).to_csv(out / "by_lat_band.csv", index=False)
    table(x, "live_source").to_csv(out / "by_tag_source.csv", index=False)
    table(x, "vendor_raw").sort_values("wells", ascending=False).to_csv(out / "by_vendor_raw.csv", index=False)
    table(x.assign(state=x["state_code"]), "state").to_csv(out / "by_state.csv", index=False)
    has = x["above_wca1_ft"].notna()
    summary = {"code_sha": p0._git_sha(), "tags": "live", "min_sep_ft": MIN_SEP_FT, "wcxy_evidence_wells": len(x),
               "landing": x["landing"].value_counts().to_dict(), "moat_ft": MOAT_FT, "landing_by_moat_ft": sens,
               "groups_of_3plus": len(grp), "groups_with_mixed_landing": int((grp["nunique"] > 1).sum()),
               "lower_landing_below_ft_median": float(x["lower_landing_below_ft"].median()),
               "first_test_fixed_75ft": x["cls"].value_counts().to_dict(),
               "first_vs_landing": pd.crosstab(x["cls"], x["landing"]).to_dict(),
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
