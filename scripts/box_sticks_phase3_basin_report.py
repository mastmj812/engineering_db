"""BOX sticks phase 3b: the basin-wide run against Novi, per DSU and bench (count, lateral footage, TVD bust).

Read-only. Reads the files scripts.box_sticks_phase3_basin wrote and the phase 3 cache frame.

    python -m scripts.box_sticks_phase3_basin_report --run <basin run dir> --cache <cache> --out docs/box_sticks/phase3b-<date>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from scripts import box_sticks_phase3_pilot as p3

BASINS = ("delaware", "midland")


def _bust(v: pd.Series) -> dict:
    v = v.dropna().abs()
    return {"n": len(v), "median_abs_ft": round(float(v.median()), 0) if len(v) else np.nan, "p90_abs_ft": round(float(v.quantile(0.9)), 0) if len(v) else np.nan}


def build(run: Path, cache: Path) -> tuple[pd.DataFrame, dict]:
    F = p3.build_frame(cache)
    u, wm, s, sm, pads = F["u"], F["wm"], F["sticks"], F["sm"], F["pads"].set_index("pad_id")
    B = pd.concat([pd.read_csv(run / f"benches_{b}.csv") for b in BASINS], ignore_index=True)
    K = pd.concat([pd.read_csv(run / f"sticks_{b}.csv") for b in BASINS], ignore_index=True)
    D = pd.concat([pd.read_csv(run / f"dsus_{b}.csv") for b in BASINS], ignore_index=True)
    L = pd.concat([pd.read_csv(run / f"ledger_{b}.csv") for b in BASINS], ignore_index=True)
    B["no_row_reason"] = B["no_row_reason"].fillna("")
    B = B.drop(columns=[c for c in ("sticks", "basin") if c in B.columns])
    k = K.groupby(["pad_id", "bench"]).agg(sticks=("well_name", "size"), box_ft=("completed_lateral_ft", "sum")).reset_index().rename(columns={"bench": "code"})
    T = B.merge(k, on=["pad_id", "code"], how="left").merge(D[["pad_id", "basin", "well_type"]], on="pad_id", how="left")
    T[["sticks", "box_ft"]] = T[["sticks", "box_ft"]].fillna(0)
    T["county"] = T["pad_id"].map(_county(F))

    okz = u["clean"].to_numpy(bool) & ~u["planned"].fillna(False).to_numpy(bool) & (u["screen"].to_numpy() != "bad_depth")
    w = wm.assign(code=u["live"].to_numpy()[wm["i"]], z=np.where(okz[wm["i"]], u["depth_ft"].to_numpy(float)[wm["i"]], np.nan))
    prod = w.groupby(["pad_id", "code"]).agg(producers=("i", "size"), z_med=("z", "median"), z_n=("z", "count")).reset_index()
    nv = sm.assign(code=s["code"].to_numpy()[sm["i"]], tvd=s["tvd"].to_numpy(float)[sm["i"]], ll=s["ll_ft"].to_numpy(float)[sm["i"]],
                   rem=s["remaining"].to_numpy(bool)[sm["i"]], basin=s["basin"].to_numpy()[sm["i"]])
    nv = nv[nv["rem"]]
    novi = nv.groupby(["pad_id", "code"]).agg(novi_sticks=("i", "size"), novi_ft=("ll", "sum"), novi_tvd=("tvd", "median")).reset_index()
    T = T.merge(prod, on=["pad_id", "code"], how="left").merge(novi, on=["pad_id", "code"], how="left")
    for c in ("producers", "z_n", "novi_sticks", "novi_ft"):
        T[c] = T[c].fillna(0)
    two = "two_landings_observed"
    T["two_landing"] = T["flags"].fillna("").astype(str).str.contains(two)
    T["box_bust_ft"] = np.where((T["legs_placed"] > 0) & (T["z_n"] >= 1) & ~T["two_landing"], T["target_tvd_ft"] - T["z_med"], np.nan)
    T["novi_bust_ft"] = np.where((T["novi_sticks"] > 0) & (T["z_n"] >= 1) & ~T["two_landing"], T["novi_tvd"] - T["z_med"], np.nan)

    # Novi sticks the comparison cannot see
    rem = s[s["remaining"]]
    in_dsu = set(sm["i"])
    has_bench = set(map(tuple, B[["pad_id", "code"]].to_numpy()))
    nvk = nv.assign(on_box_bench=[(p, c) in has_bench for p, c in zip(nv["pad_id"], nv["code"], strict=True)])
    ran = set(D["pad_id"])
    mid = shapely.points(rem["x"].to_numpy(), rem["y"].to_numpy())
    out_poly = {}
    for b in BASINS:
        pb = F["pads"][F["pads"]["basin"] == b]
        tree = shapely.STRtree(pb["geom"].to_numpy())
        sel = (rem["basin"] == b).to_numpy()
        inside = np.zeros(int(sel.sum()), bool)
        inside[np.unique(tree.query(mid[sel], predicate="within")[0])] = True
        r = rem[sel]
        no_dsu = ~r.index.isin(in_dsu)
        out_poly[b] = {"remaining_novi_sticks": int(sel.sum()), "midpoint_inside_a_polygon": int(inside.sum()), "midpoint_outside_every_polygon": int((~inside).sum()),
                       "under_30pct_in_any_dsu": int(no_dsu.sum()), "of_those_midpoint_outside": int((no_dsu & ~inside).sum()),
                       "no_dsu_by_category": r[no_dsu]["category"].value_counts().to_dict(),
                       "no_dsu_top_counties": r[no_dsu]["county"].value_counts().head(8).to_dict(),
                       "no_dsu_by_bench": r[no_dsu]["code"].value_counts().head(8).to_dict(),
                       "no_dsu_footage": float(r[no_dsu]["ll_ft"].sum()),
                       "in_a_dsu": int((~no_dsu).sum()), "in_a_dsu_that_ran": int(nvk[(nvk["basin"] == b) & nvk["pad_id"].isin(ran)].shape[0]),
                       "in_a_dsu_on_a_bench_with_box_extent": int(nvk[(nvk["basin"] == b) & nvk["on_box_bench"]].shape[0]),
                       "in_a_dsu_on_a_bench_with_no_box_extent": int(nvk[(nvk["basin"] == b) & ~nvk["on_box_bench"]].shape[0]),
                       "no_box_extent_by_bench": nvk[(nvk["basin"] == b) & ~nvk["on_box_bench"]]["code"].value_counts().head(10).to_dict(),
                       "polygons": len(pb), "polygons_with_a_box_bench": int(pb["pad_id"].isin(ran).sum()),
                       "polygon_area_acres": float(pb["acres"].sum())}
    reasons = L[L["status"] == "culled"].groupby(["pad_id", "code", "reason"]).size().unstack(fill_value=0).reset_index()
    T = T.merge(reasons, on=["pad_id", "code"], how="left")
    rcols = [c for c in reasons.columns if c not in ("pad_id", "code")]
    T[rcols] = T[rcols].fillna(0)
    extra = {"novi_coverage": out_poly, "reason_cols": rcols, "pads_total": {b: int((pads["basin"] == b).sum()) for b in BASINS}}
    return T, extra


def _county(F: dict) -> pd.Series:
    """County of each DSU: the county of the nearest producer midpoint (the cache carries no county polygons)."""
    u, pads = F["u"], F["pads"]
    out = {}
    for b in BASINS:
        ub, pb = u[u["basin"] == b], pads[pads["basin"] == b]
        tree = shapely.STRtree(shapely.points(ub["x"].to_numpy(), ub["y"].to_numpy()))
        j = tree.nearest(shapely.points(pb["cx"].to_numpy(), pb["cy"].to_numpy()))
        out |= dict(zip(pb["pad_id"].to_numpy(), ub["county"].to_numpy()[j], strict=True))
    return pd.Series(out)


def summarise(T: pd.DataFrame, by: list[str], rcols: list[str]) -> pd.DataFrame:
    def agg(g: pd.DataFrame) -> pd.Series:
        both = g[g["box_bust_ft"].notna() & g["novi_bust_ft"].notna()]
        bb, nb = _bust(g["box_bust_ft"]), _bust(g["novi_bust_ft"])
        d = {"dsu_bench": len(g), "with_box_sticks": int((g["sticks"] > 0).sum()), "with_novi_sticks": int((g["novi_sticks"] > 0).sum()),
             "no_row": int((g["no_row_reason"] != "").sum()), "box_sticks": int(g["sticks"].sum()), "box_legs": int(g["legs_placed"].sum()),
             "box_straight": int(g.loc[g["well_type"] == "single", "sticks"].sum()), "box_uturn": int(g.loc[g["well_type"] == "uturn", "sticks"].sum()),
             "rows_not_placed": int((g["rows_considered"] - g["legs_placed"]).sum()), "novi_sticks": int(g["novi_sticks"].sum()),
             "box_mm_ft": round(float(g["box_ft"].sum()) / 1e6, 2), "novi_mm_ft": round(float(g["novi_ft"].sum()) / 1e6, 2), "producers": int(g["producers"].sum()),
             "box_bust_n": bb["n"], "box_bust_median_abs_ft": bb["median_abs_ft"], "box_bust_p90_abs_ft": bb["p90_abs_ft"],
             "novi_bust_n": nb["n"], "novi_bust_median_abs_ft": nb["median_abs_ft"], "novi_bust_p90_abs_ft": nb["p90_abs_ft"],
             "paired_n": len(both), "paired_box_median_abs_ft": _bust(both["box_bust_ft"])["median_abs_ft"],
             "paired_novi_median_abs_ft": _bust(both["novi_bust_ft"])["median_abs_ft"]}
        return pd.Series(d | {c: int(g[c].sum()) for c in rcols})

    return T.groupby(by).apply(agg, include_groups=False).reset_index()


def run(run_dir: Path, cache: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    T, extra = build(run_dir, cache)
    rc = extra["reason_cols"]
    basin = summarise(T, ["basin"], rc)
    bench = summarise(T, ["basin", "code"], rc)
    county = summarise(T, ["basin", "county"], rc)
    basin.to_csv(out / "basin.csv", index=False)
    bench.to_csv(out / "basin_bench.csv", index=False)
    county.to_csv(out / "basin_county.csv", index=False)
    keep = ["pad_id", "basin", "county", "well_type", "code", "no_row_reason", "rows_considered", "legs_placed", "sticks", "box_ft", "target_tvd_ft", "rung",
            "spacing_map_ft", "spacing_final_ft", "grid", "producers", "novi_sticks", "novi_ft", "novi_tvd", "box_bust_ft", "novi_bust_ft", "two_landing"]
    T[[c for c in keep if c in T.columns]].round(1).to_csv(out / "dsu_bench.csv.gz", index=False, compression="gzip")
    dsu = T.groupby(["basin", "pad_id"]).agg(box_sticks=("sticks", "sum"), novi_sticks=("novi_sticks", "sum"), box_ft=("box_ft", "sum"), novi_ft=("novi_ft", "sum")).reset_index()
    diff = dsu["box_sticks"] - dsu["novi_sticks"]
    S = {"summaries": {b: json.loads((run_dir / f"summary_{b}.json").read_text(encoding="utf-8")) for b in BASINS},
         "novi_coverage": extra["novi_coverage"], "pads_total": extra["pads_total"],
         "bench_no_row_reasons": T[T["no_row_reason"] != ""].groupby(["basin", "no_row_reason"]).size().unstack(fill_value=0).to_dict("index"),
         "rung_of_dsu_bench_with_sticks": T[T["sticks"] > 0].groupby(["basin", "rung"]).size().unstack(fill_value=0).to_dict("index"),
         "dsu_box_minus_novi": {b: {"dsus": int((dsu["basin"] == b).sum()), "box_more": int(((diff > 0) & (dsu["basin"] == b)).sum()),
                                    "equal": int(((diff == 0) & (dsu["basin"] == b)).sum()), "novi_more": int(((diff < 0) & (dsu["basin"] == b)).sum()),
                                    "box_zero_novi_some": int(((dsu["box_sticks"] == 0) & (dsu["novi_sticks"] > 0) & (dsu["basin"] == b)).sum()),
                                    "novi_zero_box_some": int(((dsu["novi_sticks"] == 0) & (dsu["box_sticks"] > 0) & (dsu["basin"] == b)).sum()),
                                    "quartiles": [float(diff[dsu["basin"] == b].quantile(q)) for q in (.1, .25, .5, .75, .9)]} for b in BASINS},
         "two_landing_dsu_bench": T.groupby("basin")["two_landing"].sum().astype(int).to_dict()}
    (out / "basin_summary.json").write_text(json.dumps(S, indent=1, default=str), encoding="utf-8")
    pd.set_option("display.width", 320)
    pd.set_option("display.max_columns", 60)
    pd.set_option("display.max_rows", 200)
    print(basin.T.to_string())
    print(bench.to_string(index=False))
    print(json.dumps({k: v for k, v in S.items() if k != "summaries"}, indent=1, default=str))
    return S


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    run(a.run, a.cache, a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
