"""BOX sticks phase 3a, step 1 follow-up: two read-only tables Michael asked for before deciding rules 4 and 8.

1. WCA_1 / WCA_2 co-development (Delaware): for every DSU where both members are eligible, how many depth-evidenced
   producers of each member lie within 3 mi, and how many nearby DSUs were actually drilled in both members.
2. Regional dominant lateral azimuth (true bearing, axial, folded to [0, 180)) by county and on a 6-mi grid, and how
   well each would pick the drilling direction of a near-square DSU, scored on near-square DSUs that have wells.

Nothing is written to the warehouse; inputs are the phase 3 pilot frame (cache built by box_sticks_phase3_pilot).

    python -m scripts.box_sticks_phase3_regional --out docs/box_sticks/phase3a-2026-11-14 --cache <cache>
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
from matplotlib.collections import PolyCollection
from pyproj import Geod

from scripts import box_sticks_phase3_pilot as p3

MI = p3.MI
RADIUS_MI = 3.0
MIN_LATERAL_FT = 4000.0       # azimuth population: real horizontals
CELL_MI = 6.0
SQUARE_ASPECT = p3.SQUARE_ASPECT
WCA = ("WCA_1", "WCA_2")
WCA_THRESHOLD = (8, 3, 0.25)  # rule 4 as decided 2026-11-15: each member >= 8 in 3 mi, >= 3 DSUs in both, >= 25 % of WCA-drilled DSUs
CODEV_MIN_EACH = 2            # a DSU is "drilled in both" with at least this many producers of each member inside
GEOD = Geod(ellps="WGS84")


def axial(a: np.ndarray) -> tuple[float, float]:
    """Axial mean (deg, [0, 180)) and resultant length R of folded azimuths."""
    r = np.radians(2 * np.asarray(a, float))
    c, s = np.cos(r).mean(), np.sin(r).mean()
    return float(np.degrees(np.arctan2(s, c)) / 2 % 180), float(np.hypot(c, s))


def axial_dist(a, b):
    d = np.abs(np.asarray(a, float) - np.asarray(b, float)) % 180
    return np.minimum(d, 180 - d)


def long_axis_true(pads: pd.DataFrame) -> np.ndarray:
    """True bearing of each DSU's long axis (the frame stores it as an EPSG:3083 grid bearing)."""
    a = shapely.get_coordinates(shapely.centroid(pads["geom"].to_numpy()))
    az = np.radians(pads["long_az_deg"].to_numpy())
    lon0, lat0 = p3.TO_LL.transform(a[:, 0], a[:, 1])
    lon1, lat1 = p3.TO_LL.transform(a[:, 0] + 1000 * np.sin(az), a[:, 1] + 1000 * np.cos(az))
    return np.asarray(GEOD.inv(lon0, lat0, lon1, lat1)[0]) % 180


def true_azimuth(wkt_ll: pd.Series) -> np.ndarray:
    g = shapely.from_wkt(wkt_ll.to_numpy())
    a = shapely.get_coordinates(shapely.get_point(g, 0))
    b = shapely.get_coordinates(shapely.get_point(g, -1))
    az, _, _ = GEOD.inv(a[:, 0], a[:, 1], b[:, 0], b[:, 1])
    return np.asarray(az) % 180


# ----------------------------------------------------------------------------
# 1. WCA_1 / WCA_2 co-development
# ----------------------------------------------------------------------------


def wca_table(F: dict) -> pd.DataFrame:
    u, pads, db, wm = F["u"], F["pads"], F["db"], F["wm"]
    d = db[(db["basin"] == "delaware") & db["code"].isin(WCA)]
    z = d.pivot(index="pad_id", columns="code", values="z")
    sp = d.pivot(index="pad_id", columns="code", values="spacing_ft")
    t = pads[pads["pad_id"].isin(z.dropna(how="all").index) & (pads["basin"] == "delaware")]
    t = t[t["pad_id"].isin(d.groupby("pad_id").size().loc[lambda s: s == 2].index)]
    t = t[["pad_id", "cx", "cy", "lon", "lat", "state", "geom"]].reset_index(drop=True)
    t["z1"], t["z2"] = t["pad_id"].map(z["WCA_1"]), t["pad_id"].map(z["WCA_2"])
    t["gap_ft"] = t["z2"] - t["z1"]
    t["spacing_1"], t["spacing_2"] = t["pad_id"].map(sp["WCA_1"]), t["pad_id"].map(sp["WCA_2"])

    planned = u["planned"].fillna(False).to_numpy(bool)
    ok = (u["basin"].to_numpy() == "delaware") & u["clean"].to_numpy(bool) & ~planned
    cen = shapely.points(t["cx"].to_numpy(), t["cy"].to_numpy())
    for k, code in enumerate(WCA, 1):
        ix = np.flatnonzero(ok & (u["live"].to_numpy() == code))
        tree = shapely.STRtree(shapely.points(u["x"].to_numpy()[ix], u["y"].to_numpy()[ix]))
        a, _ = tree.query(cen, predicate="dwithin", distance=RADIUS_MI * MI)
        t[f"n{k}_3mi"] = np.bincount(a, minlength=len(t))

    # DSUs drilled in WCA at all, and in both members, within 3 mi (the DSU itself included)
    w = wm.assign(code=u["live"].to_numpy()[wm["i"]], ok=ok[wm["i"]])
    w = w[w["ok"] & w["code"].isin(WCA)]
    c = w.groupby(["pad_id", "code"]).size().unstack(fill_value=0).reindex(columns=list(WCA), fill_value=0)
    P = pads[pads["basin"] == "delaware"].set_index("pad_id")
    c = c.join(P[["cx", "cy"]], how="inner")
    c["both"] = (c["WCA_1"] >= CODEV_MIN_EACH) & (c["WCA_2"] >= CODEV_MIN_EACH)
    c["any"] = (c["WCA_1"] + c["WCA_2"]) >= CODEV_MIN_EACH
    c = c[c["any"]]
    tree = shapely.STRtree(shapely.points(c["cx"].to_numpy(), c["cy"].to_numpy()))
    a, b = tree.query(cen, predicate="dwithin", distance=RADIUS_MI * MI)
    t["dsus_wca_3mi"] = np.bincount(a, minlength=len(t))
    t["dsus_both_3mi"] = np.bincount(a, weights=c["both"].to_numpy(float)[b], minlength=len(t)).astype(int)
    t["in_1"] = t["pad_id"].map(c["WCA_1"]).fillna(0).astype(int)
    t["in_2"] = t["pad_id"].map(c["WCA_2"]).fillna(0).astype(int)
    tot = t["n1_3mi"] + t["n2_3mi"]
    t["minority_share"] = np.where(tot > 0, np.minimum(t["n1_3mi"], t["n2_3mi"]) / tot.clip(lower=1), 0.0)
    t["both_share"] = np.where(t["dsus_wca_3mi"] > 0, t["dsus_both_3mi"] / t["dsus_wca_3mi"].clip(lower=1), 0.0)
    t["dominant"] = np.where(t["n1_3mi"] >= t["n2_3mi"], "WCA_1", "WCA_2")
    return t


def wca_class(t: pd.DataFrame, min_each: int, min_both_dsus: int, min_both_share: float) -> pd.Series:
    """Proposed classes. co-developed: each member has >= min_each producers within 3 mi AND at least min_both_dsus
    nearby DSUs (>= min_both_share of the WCA-drilled ones) carry both members. no control: under min_each in total."""
    tot = t["n1_3mi"] + t["n2_3mi"]
    co = ((t[["n1_3mi", "n2_3mi"]].min(axis=1) >= min_each) & (t["dsus_both_3mi"] >= min_both_dsus)
          & (t["both_share"] >= min_both_share))
    return pd.Series(np.select([co, tot < min_each], ["co-developed", "no control"], "one member"), index=t.index)


def wca_map(t: pd.DataFrame, out: Path) -> None:
    col = {"co-developed": "#dc2626", "one member": "#2563eb", "no control": "#a3a3a3"}
    fig, ax = plt.subplots(figsize=(11, 11))
    for k, c in col.items():
        g = t[t["cls"] == k]
        polys = [np.column_stack(p3.TO_LL.transform(*shapely.get_coordinates(x.exterior).T)) for x in g["geom"]]
        ax.add_collection(PolyCollection(polys, facecolors=c, edgecolors="none", alpha=0.8, label=f"{k} ({len(g):,} DSUs)"))
    for a in p3.AREAS.values():
        if a["basin"] == "delaware":
            h = a["size_mi"] / 2 / 69.0
            hx = h / np.cos(np.radians(a["lat"]))
            ax.plot([a["lon"] - hx, a["lon"] + hx, a["lon"] + hx, a["lon"] - hx, a["lon"] - hx],
                    [a["lat"] - h, a["lat"] - h, a["lat"] + h, a["lat"] + h, a["lat"] - h], color="k", lw=1.5)
    ax.autoscale()
    ax.set_aspect(1 / np.cos(np.radians(31.8)))
    ax.legend(loc="lower left")
    ax.set_title("Delaware DSUs with WCA_1 and WCA_2 both eligible: proposed class (black boxes = pilot areas)")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------
# 2. Regional dominant azimuth
# ----------------------------------------------------------------------------


def az_wells(F: dict) -> pd.DataFrame:
    u = F["u"]
    planned = u["planned"].fillna(False).to_numpy(bool)
    w = u[(u["lateral_length_ft"] >= MIN_LATERAL_FT) & ~planned & ~u["live"].isin(["OTHER"]) & u["wkt_ll"].notna()].copy()
    w["az"] = true_azimuth(w["wkt_ll"])
    w["cell_x"] = np.floor(w["x"] / (CELL_MI * MI)).astype(int)
    w["cell_y"] = np.floor(w["y"] / (CELL_MI * MI)).astype(int)
    return w


def az_summary(g: pd.DataFrame) -> pd.Series:
    m, r = axial(g["az"].to_numpy())
    a = g["az"].to_numpy()
    return pd.Series({"wells": len(g), "dominant_az_deg": round(m, 1), "R": round(r, 2),
                      "within_15_pct": round(100 * float((axial_dist(a, m) <= 15).mean()), 1),
                      "ns_pct": round(100 * float((axial_dist(a, 0) <= 22.5).mean()), 1),
                      "ew_pct": round(100 * float((axial_dist(a, 90) <= 22.5).mean()), 1)})


def square_test(F: dict, w: pd.DataFrame, county: pd.DataFrame, cell: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Near-square DSUs. With >= 3 wells inside: does each default pick the side the wells were drilled along?"""
    pads, wm, u = F["pads"], F["wm"], F["u"]
    sq = pads[pads["aspect"] < SQUARE_ASPECT].copy()
    idx = pd.Series(np.arange(len(u)), index=u.index)
    pos = pd.Series(np.arange(len(w)), index=idx.loc[w.index].to_numpy())
    m = wm[wm["pad_id"].isin(sq["pad_id"]) & wm["i"].isin(pos.index)]
    m = m.assign(az=w["az"].to_numpy()[pos.loc[m["i"]].to_numpy()], county=w["county"].to_numpy()[pos.loc[m["i"]].to_numpy()])
    g = m.groupby("pad_id").agg(n=("az", "size"), az=("az", lambda a: axial(a.to_numpy())[0]), R=("az", lambda a: axial(a.to_numpy())[1]),
                                county=("county", lambda s: s.mode().iloc[0]))
    sq = sq.merge(g, left_on="pad_id", right_index=True, how="left")
    sq["n"] = sq["n"].fillna(0).astype(int)
    # county of a DSU with no wells: the county of the nearest azimuth well
    tree = shapely.STRtree(shapely.points(w["x"].to_numpy(), w["y"].to_numpy()))
    near = tree.nearest(shapely.points(sq["cx"].to_numpy(), sq["cy"].to_numpy()))
    sq["county"] = sq["county"].fillna(pd.Series(w["county"].to_numpy()[near], index=sq.index))
    sq["side_a"] = sq["long_az_true"]
    sq["side_b"] = (sq["long_az_true"] + 90) % 180
    ck = county.set_index(["basin", "county"])
    sq["county_az"] = [ck["dominant_az_deg"].get((b, c), np.nan) for b, c in zip(sq["basin"], sq["county"])]
    sq["county_R"] = [ck["R"].get((b, c), np.nan) for b, c in zip(sq["basin"], sq["county"])]
    cx = np.floor(sq["cx"] / (CELL_MI * MI)).astype(int)
    cy = np.floor(sq["cy"] / (CELL_MI * MI)).astype(int)
    cc = cell.set_index(["basin", "cell_x", "cell_y"])
    sq["cell_az"] = [cc["dominant_az_deg"].get((b, x, y), np.nan) for b, x, y in zip(sq["basin"], cx, cy)]
    sq["cell_wells"] = [cc["wells"].get((b, x, y), 0) for b, x, y in zip(sq["basin"], cx, cy)]

    def pick(ref):
        return np.where(axial_dist(sq["side_a"], ref) <= axial_dist(sq["side_b"], ref), "a", "b")

    sq["pick_county"] = pick(sq["county_az"])
    sq["pick_cell"] = np.where(sq["cell_wells"] >= 10, pick(sq["cell_az"].fillna(sq["county_az"])), sq["pick_county"])
    sq["pick_long"] = "a"
    sq["pick_ns"] = pick(0.0)
    sq["truth"] = np.where(sq["n"] >= 3, pick(sq["az"]), None)
    sq["margin_county"] = np.abs(axial_dist(sq["side_a"], sq["county_az"]) - axial_dist(sq["side_b"], sq["county_az"]))
    v = sq[(sq["n"] >= 3) & (sq["R"] >= 0.85)]
    score = v.groupby("basin").apply(lambda d: pd.Series({
        "dsus": len(d), "county_pct": round(100 * (d["pick_county"] == d["truth"]).mean(), 1),
        "cell_pct": round(100 * (d["pick_cell"] == d["truth"]).mean(), 1),
        "north_south_pct": round(100 * (d["pick_ns"] == d["truth"]).mean(), 1),
        "long_axis_pct": round(100 * (d["pick_long"] == d["truth"]).mean(), 1)}), include_groups=False).reset_index()
    return sq, score


def az_map(cell: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 11))
    c = cell[cell["wells"] >= 10]
    x, y = (c["cell_x"] + 0.5) * CELL_MI * MI, (c["cell_y"] + 0.5) * CELL_MI * MI
    lon, lat = p3.TO_LL.transform(x.to_numpy(), y.to_numpy())
    th = np.radians(c["dominant_az_deg"].to_numpy())
    k = 0.035
    dx, dy = k * np.sin(th) / np.cos(np.radians(31.8)), k * np.cos(th)
    q = ax.quiver(lon - dx, lat - dy, 2 * dx, 2 * dy, c["R"].to_numpy(), cmap="viridis_r", angles="xy", scale_units="xy", scale=1,
                  headwidth=0, headlength=0, headaxislength=0, width=0.003, clim=(0.3, 1.0))
    fig.colorbar(q, ax=ax, shrink=0.6, label="R (1 = every lateral on one bearing)")
    ax.set_aspect(1 / np.cos(np.radians(31.8)))
    ax.set_title(f"Dominant lateral azimuth (true), {CELL_MI:g}-mi cells with at least 10 horizontals")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)


def run(out: Path, cache: Path) -> dict:
    F = p3.build_frame(cache)
    out.mkdir(parents=True, exist_ok=True)
    S: dict = {"tags": F["tags"], "pulled": F["pulled"]}

    t = wca_table(F)
    t["cls"] = wca_class(t, *WCA_THRESHOLD)
    t.drop(columns="geom").round(3).to_csv(out / "wca_codev.csv", index=False)
    wca_map(t, out / "wca_codev_map.png")
    S["wca"] = {"dsus": len(t), "by_class": t["cls"].value_counts().to_dict(),
                "by_class_state": t.groupby(["state", "cls"]).size().unstack(fill_value=0).to_dict("index"),
                "gap_by_class": {k: g["gap_ft"].describe()[["count", "25%", "50%", "75%"]].round(0).to_dict() for k, g in t.groupby("cls")},
                "sensitivity": {f"each>={a},both_dsus>={b},share>={c}": wca_class(t, a, b, c).value_counts().to_dict()
                                for a, b, c in ((4, 2, 0.25), (8, 3, 0.25), (8, 3, 0.5), (15, 5, 0.25), (15, 5, 0.5))}}

    w = az_wells(F)
    F["pads"]["long_az_true"] = long_axis_true(F["pads"])
    county = w.groupby(["basin", "county"]).apply(az_summary, include_groups=False).reset_index()
    county = county[county["wells"] >= 25].sort_values(["basin", "wells"], ascending=[True, False])
    county.to_csv(out / "azimuth_by_county.csv", index=False)
    cell = w.groupby(["basin", "cell_x", "cell_y"]).apply(az_summary, include_groups=False).reset_index()
    cell.to_csv(out / "azimuth_by_cell.csv", index=False)
    az_map(cell, out / "azimuth_map.png")
    sq, score = square_test(F, w, county, cell)
    sq.drop(columns=["geom", "wkt"]).round(3).to_csv(out / "azimuth_square_dsus.csv", index=False)
    S["azimuth"] = {"wells": len(w), "basin": w.groupby("basin").apply(az_summary, include_groups=False).to_dict("index"),
                    "square_dsus": sq.groupby("basin")["n"].agg(total="size", no_wells=lambda v: int((v == 0).sum()),
                                                                one_two=lambda v: int(((v > 0) & (v < 3)).sum())).to_dict("index"),
                    "score": score.to_dict("records"),
                    "no_well_square_margin_under_20": sq[sq["n"] == 0].groupby("basin")["margin_county"].apply(lambda v: int((v < 20).sum())).to_dict()}
    (out / "regional_summary.json").write_text(json.dumps(S, indent=1, default=float))
    print(json.dumps(S, indent=1, default=float))
    print(county.to_string(index=False))
    print(score.to_string(index=False))
    return S


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
