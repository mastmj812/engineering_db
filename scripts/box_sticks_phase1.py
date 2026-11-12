"""BOX sticks, phase 1: landing surfaces per BOX extent, coverage and held-out error (read-only).

    python -m scripts.box_sticks_phase1 --out docs/box_sticks/phase1-<date> --cache <phase 0 cache>

Builds the landing surface of every code inside its BOX record extent with box.landing_surfaces (unchanged: direct
within 1 mi of the code's own control, thickness from an anchor bench to 5 mi, nothing beyond) and reports what the
BOX stick generator needs to know before a surface is stored (docs/box_sticks_plan.md, phase 1):

  coverage   per code: share of the extent, and of the Novi DSU polygons that intersect it, with a direct depth, a
             thickness-carried depth, or none (sampled at the polygon centroid's lattice node).
  direct     held-out error: each evidence well held out with every same-code well within 1/4 mi, predicted from the
             rest within 2 mi (>= 3), as the surface does.
  thickness  held-out error under the condition thickness is USED: every same-code well within E mi of the well is
             held out (E = 1, 2, 3), the depth is the anchor bench's surface at the well plus the local thickness from
             the remaining same-code wells within 5 mi (>= 3, on more than one side). Every other bench of the basin is
             tried as the anchor, and a two-anchor "sandwich" (fractional position between a bench above and one below).
  order      per DSU polygon: adjacent-bench depths out of stratigraphic order or closer than MIN_SEP_FT.

Today's tags (live). Nothing is written to the warehouse.
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
from box import tag_scoreboard as sb
from scripts import box_sticks_phase0 as p0
from scripts.tag_landing_crossings import build_surfaces

P = ls.PARAMS
MI = ls.M_PER_MI
STEP_M = P.node_mi * MI
NODE_SQMI = P.node_mi ** 2
HOLDOUT_MI = 0.25
EXCLUDE_MI = (1.0, 2.0, 3.0)
MIN_SEP_FT = 75.0
LITH_PAIRS = {("BS2_C", "BS2_S"), ("BS3_C", "BS3_S")}
FOCUS = (("delaware", "BS1_S"), ("midland", "DEAN"))
POOLED_DIRECT_ONLY = {("delaware", c) for c in ls.WCA_FAM}


def _err(e: pd.Series) -> dict:
    e = e.dropna()
    if not len(e):
        return {"predicted": 0, "median_ft": np.nan, "p90_ft": np.nan, "p99_ft": np.nan, "over_150_pct": np.nan, "over_300_pct": np.nan}
    return {"predicted": len(e), "median_ft": float(e.median()), "p90_ft": float(e.quantile(0.9)), "p99_ft": float(e.quantile(0.99)),
            "over_150_pct": 100 * float((e > 150).mean()), "over_300_pct": 100 * float((e > 300).mean())}


def anchor_sets(extents: pd.DataFrame, basin: str) -> dict[str, tuple[str, ...]]:
    return {e.bench: ls.extent_codes(basin, e.bench) for e in extents[extents["basin"] == basin].itertuples()}


def anchor_field(bw: pd.DataFrame, codes: tuple[str, ...]) -> np.ndarray:
    """The anchor bench's landing depth at every well of the basin (>= n_min anchor wells within r_mi), else NaN."""
    a = bw[bw["live"].isin(codes)]
    out = np.full(len(bw), np.nan)
    if len(a) < P.n_min:
        return out
    axy, az = a[["x", "y"]].to_numpy(float), a["depth_ft"].to_numpy(float)
    xy = bw[["x", "y"]].to_numpy(float)
    for i, js in enumerate(cKDTree(axy).query_ball_point(xy, P.r_mi * MI)):
        if len(js) >= P.n_min:
            out[i] = ls.estimate(axy[js], az[js], xy[i], P)[0]
    return out


def direct_holdout(xy: np.ndarray, z: np.ndarray) -> np.ndarray:
    err = np.full(len(z), np.nan)
    for i, js in enumerate(cKDTree(xy).query_ball_point(xy, P.r_mi * MI)):
        js = np.asarray(js, int)
        js = js[np.hypot(xy[js, 0] - xy[i, 0], xy[js, 1] - xy[i, 1]) >= HOLDOUT_MI * MI]
        if len(js) >= P.n_min:
            err[i] = abs(z[i] - ls.estimate(xy[js], z[js], xy[i], P)[0])
    return err


def carried_holdout(xy: np.ndarray, z: np.ndarray, rel: np.ndarray, at_up: np.ndarray, span: np.ndarray | None, exclude_mi: float) -> np.ndarray:
    """|error| of a carried depth. ``rel`` is each well's sample (thickness z - A, or the fractional position);
    the prediction is at_up + median(rel) [* span]. Same-code wells within ``exclude_mi`` are held out."""
    err = np.full(len(z), np.nan)
    ok = np.isfinite(rel)
    for i, ks in enumerate(cKDTree(xy).query_ball_point(xy, P.thick_max_mi * MI)):
        if not np.isfinite(at_up[i]) or (span is not None and not np.isfinite(span[i])):
            continue
        ks = np.asarray(ks, int)
        d = np.hypot(xy[ks, 0] - xy[i, 0], xy[ks, 1] - xy[i, 1])
        keep = (d >= exclude_mi * MI) & ok[ks]
        ks, d = ks[keep], d[keep] / MI
        if len(ks) < P.n_min or ls.max_angular_gap_deg(xy[ks], xy[i]) >= 180.0:
            continue
        t = ls.weighted_median(rel[ks], np.exp(-0.5 * (d / (2 * P.wmed_sigma_mi)) ** 2) + 1e-9)
        err[i] = abs(z[i] - (at_up[i] + t * (span[i] if span is not None else 1.0)))
    return err


def holdouts(w: pd.DataFrame, extents: pd.DataFrame, order: dict[str, list[str]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    direct, thick, sand = [], [], []
    for basin in sorted(extents["basin"].unique()):
        bw = w[w["basin"] == basin].reset_index(drop=True)
        sets = anchor_sets(extents, basin)
        fields = {name: anchor_field(bw, codes) for name, codes in sets.items()}
        print(f"{basin}: anchor fields built ({len(fields)})", flush=True)
        rank = {c: i for i, c in enumerate(order[basin])}
        for e in extents[extents["basin"] == basin].itertuples():
            geom = shapely.make_valid(shapely.from_wkt(e.wkt))
            for code in ls.extent_codes(basin, e.bench):
                m = ((bw["live"] == code) & shapely.contains_xy(geom, bw["x"].to_numpy(), bw["y"].to_numpy())).to_numpy()
                if m.sum() < 4:
                    continue
                xy, z = bw.loc[m, ["x", "y"]].to_numpy(float), bw.loc[m, "depth_ft"].to_numpy(float)
                direct.append({"basin": basin, "code": code, "wells": int(m.sum()), **_err(pd.Series(direct_holdout(xy, z)))})
                configured = ls.ANCHOR.get(basin, {}).get(code)
                best = {}
                for name, acodes in sets.items():
                    if code in acodes:
                        continue
                    A = fields[name][m]
                    side = "above" if rank[acodes[0]] < rank[code] else "below"
                    for ex_mi in EXCLUDE_MI:
                        r = _err(pd.Series(carried_holdout(xy, z, z - A, A, None, ex_mi)))
                        thick.append({"basin": basin, "code": code, "anchor": name, "anchor_side": side,
                                      "configured": configured == acodes, "exclude_mi": ex_mi, "wells": int(m.sum()),
                                      "predicted_pct": 100 * r["predicted"] / m.sum(), **r})
                        if ex_mi == 1.0 and r["predicted"] >= 0.25 * m.sum() and r["median_ft"] < best.get(side, (np.inf,))[0]:
                            best[side] = (r["median_ft"], name)
                if "above" in best and "below" in best:
                    up, lo = fields[best["above"][1]][m], fields[best["below"][1]][m]
                    span = np.where(lo - up > 50.0, lo - up, np.nan)
                    for ex_mi in EXCLUDE_MI:
                        r = _err(pd.Series(carried_holdout(xy, z, (z - up) / span, up, span, ex_mi)))
                        sand.append({"basin": basin, "code": code, "above": best["above"][1], "below": best["below"][1], "exclude_mi": ex_mi,
                                     "wells": int(m.sum()), "predicted_pct": 100 * r["predicted"] / m.sum(), **r})
            print(f"  {basin} {e.bench} done", flush=True)
    return pd.DataFrame(direct), pd.DataFrame(thick), pd.DataFrame(sand)


def dsu_samples(pads: pd.DataFrame, extents: pd.DataFrame, surf: dict) -> pd.DataFrame:
    """One row per (DSU polygon, code whose extent the polygon intersects): the surface at the centroid's node."""
    rows = []
    for basin, pb in pads.groupby("basin"):
        geoms = pb["geom"].to_numpy()
        cen = shapely.centroid(geoms)
        cx, cy = shapely.get_x(cen), shapely.get_y(cen)
        keys = pd.MultiIndex.from_arrays([np.rint(cx / STEP_M).astype(int), np.rint(cy / STEP_M).astype(int)])
        tree = shapely.STRtree(geoms)
        for e in extents[extents["basin"] == basin].itertuples():
            eg = shapely.make_valid(shapely.from_wkt(e.wkt))
            hit = tree.query(eg, predicate="intersects")
            cin = shapely.contains_xy(eg, cx[hit], cy[hit])
            for code in ls.extent_codes(basin, e.bench):
                s = surf.get((basin, code))
                if s is None:
                    continue
                at = s.reindex(keys[hit])
                rows.append(pd.DataFrame({"basin": basin, "code": code, "pad_id": pb["pad_id"].to_numpy()[hit], "centroid_in_extent": cin,
                                          "z": at["z"].to_numpy(), "basis": at["basis"].fillna("none").to_numpy(),
                                          "near_mi": at["near_mi"].to_numpy()}))
    return pd.concat(rows, ignore_index=True)


def coverage(extents: pd.DataFrame, surf: dict, dsu: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for e in extents.itertuples():
        nodes = shapely.area(shapely.make_valid(shapely.from_wkt(e.wkt))) / MI ** 2 / NODE_SQMI
        for code in ls.extent_codes(e.basin, e.bench):
            s = surf.get((e.basin, code))
            if s is None:
                continue
            d = dsu[(dsu["basin"] == e.basin) & (dsu["code"] == code)]
            rows.append({"basin": e.basin, "extent": e.bench, "code": code, "extent_sqmi": nodes * NODE_SQMI,
                         "area_direct_pct": 100 * float((s["basis"] == "direct").sum()) / nodes,
                         "area_thickness_pct": 100 * float((s["basis"] == "thickness").sum()) / nodes,
                         "dsu": len(d), "dsu_direct_pct": 100 * float((d["basis"] == "direct").mean()),
                         "dsu_thickness_pct": 100 * float((d["basis"] == "thickness").mean()),
                         "dsu_none_pct": 100 * float((d["basis"] == "none").mean()),
                         "dsu_none_centroid_outside_pct": 100 * float(((d["basis"] == "none") & ~d["centroid_in_extent"]).mean())})
    out = pd.DataFrame(rows)
    out["area_none_pct"] = 100 - out["area_direct_pct"] - out["area_thickness_pct"]
    return out


def order_check(dsu: pd.DataFrame, order: dict[str, list[str]]) -> tuple[pd.DataFrame, dict]:
    rows, per_basin = [], {}
    have = dsu[dsu["z"].notna()]
    for basin, g in have.groupby("basin"):
        rank = {c: i for i, c in enumerate(order[basin])}
        g = g.assign(rank=g["code"].map(rank)).sort_values(["pad_id", "rank"])
        nxt = g.groupby("pad_id")[["code", "z", "basis"]].shift(-1)
        pr = g.assign(lower=nxt["code"], z_lower=nxt["z"], basis_lower=nxt["basis"]).dropna(subset=["lower"])
        pr["gap_ft"] = pr["z_lower"] - pr["z"]
        pr["lith_pair"] = [(a, b) in LITH_PAIRS for a, b in zip(pr["code"], pr["lower"], strict=True)]
        pr["any_thickness"] = (pr["basis"] == "thickness") | (pr["basis_lower"] == "thickness")
        pr["state"] = np.where(pr["gap_ft"] < 0, "out_of_order", np.where(pr["gap_ft"] < MIN_SEP_FT, "under_min_sep", "ok"))
        bad = pr[(pr["state"] != "ok") & ~pr["lith_pair"]]
        per_basin[basin] = {"dsu_with_2plus_benches": int(pr["pad_id"].nunique()), "dsu_with_violation": int(bad["pad_id"].nunique()),
                            "dsu_with_out_of_order": int(bad.loc[bad["state"] == "out_of_order", "pad_id"].nunique())}
        for (up, lo), q in pr.groupby(["code", "lower"]):
            rows.append({"basin": basin, "upper": up, "lower": lo, "lith_pair": (up, lo) in LITH_PAIRS, "dsu": len(q),
                         "median_gap_ft": float(q["gap_ft"].median()), "p10_gap_ft": float(q["gap_ft"].quantile(0.1)),
                         "out_of_order_pct": 100 * float((q["state"] == "out_of_order").mean()),
                         "under_min_sep_pct": 100 * float((q["state"] == "under_min_sep").mean()),
                         "violations": int((q["state"] != "ok").sum()),
                         "violations_with_thickness_pct": 100 * float(q.loc[q["state"] != "ok", "any_thickness"].mean()) if (q["state"] != "ok").any() else np.nan})
    return pd.DataFrame(rows), per_basin


def focus_map(basin: str, code: str, surf: dict, extents: pd.DataFrame, w: pd.DataFrame, out: Path) -> str:
    s = surf[(basin, code)]
    k = np.array(s.index.to_list(), float) * P.node_mi
    c = w[(w["basin"] == basin) & (w["live"] == code)]
    fig, axes = plt.subplots(1, 2, figsize=(15, 8))
    for ax in axes:
        for e in extents[extents["basin"] == basin].itertuples():
            if code in ls.extent_codes(basin, e.bench):
                for poly in shapely.get_parts(shapely.make_valid(shapely.from_wkt(e.wkt))):
                    if poly.geom_type == "Polygon":
                        x, y = poly.exterior.xy
                        ax.plot(np.asarray(x) / MI, np.asarray(y) / MI, color="#111827", lw=0.8)
        ax.set_aspect("equal")
        ax.set_xlabel("mi (EPSG:3083 easting)")
    for basis, color in (("direct", "#2563eb"), ("thickness", "#f59e0b")):
        m = (s["basis"] == basis).to_numpy()
        axes[0].scatter(k[m, 0], k[m, 1], s=1.4, c=color, marker="s", linewidths=0, label=f"{basis} ({m.sum() * NODE_SQMI:,.0f} sq mi)")
    axes[0].scatter(c["x"] / MI, c["y"] / MI, s=2, c="#111827", linewidths=0, label=f"{code} evidence wells ({len(c):,})")
    axes[0].legend(fontsize=8, markerscale=5, loc="best")
    axes[0].set_title(f"{basin} {code}: where the landing depth comes from (white inside the outline = none)", fontsize=10)
    sc = axes[1].scatter(k[:, 0], k[:, 1], s=1.4, c=s["z"], cmap="viridis_r", marker="s", linewidths=0)
    fig.colorbar(sc, ax=axes[1], shrink=0.7).set_label("landing TVD, ft")
    axes[1].set_title(f"{basin} {code}: landing surface", fontsize=10)
    f = out / f"surface_{basin}_{code}.png"
    fig.savefig(f, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return f.name


def run(out: Path, cache: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    w = p0.evidence(d["wells"], d["rule"])
    extents, order = d["extents"], sb.bench_order()
    surf, _ = build_surfaces(w, extents)
    pads = p0.pad_frame(d["pads"])
    dsu = dsu_samples(pads, extents, surf)
    cov = coverage(extents, surf, dsu)
    cov.to_csv(out / "coverage.csv", index=False)
    pairs, order_summary = order_check(dsu, order)
    pairs.to_csv(out / "order_pairs.csv", index=False)
    direct, thick, sand = holdouts(w, extents, order)
    direct.to_csv(out / "holdout_direct.csv", index=False)
    thick.to_csv(out / "holdout_thickness.csv", index=False)
    sand.to_csv(out / "holdout_sandwich.csv", index=False)
    maps = [focus_map(b, c, surf, extents, w, out) for b, c in FOCUS if (b, c) in surf]
    summary = {"code_sha": p0._git_sha(), "tags": "live", "params": P.__dict__, "min_sep_ft": MIN_SEP_FT, "order": order_summary, "maps": maps,
               "dsu_bench_rows": len(dsu), "dsu_bench_basis_pct": (100 * dsu["basis"].value_counts(normalize=True)).round(1).to_dict()}
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
