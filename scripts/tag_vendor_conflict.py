"""When Novi and Enverus put a well in different stratigraphic units, which one does depth back? (read-only)

    python -m scripts.tag_vendor_conflict --cache <scoreboard cache> --out docs/formation_tag_redesign/vendor-conflict-<date>

The evidence for replacing sql/16's decision logic ("Novi, unless Novi's value is coarse, then Enverus").

* Population: clean producing horizontals (survey depth else clean tvd_ft, no planned survey, >= 4,000 ft) where BOTH
  vendor strings map through ref.formation_crosswalk and land in DIFFERENT units. A unit groups the codes a vendor
  name can mean at interval level: Delaware AVA (AVA_0/1/2), BS1, BS2 (BS2_C + BS2_S), BS3 (BS3_C + BS3_S), WCA
  (WCXY / WCA_1 / WCA_2), WCB (WCB_1 / WCB_2), WCC, WCD; Midland WCB (WCB_1 / WCB_2); every other code is its own
  unit. Lime-vs-sand naming inside one interval is therefore not a conflict here.
* Reference: per unit, the witnesses = clean wells whose two vendor codes map to that same unit. The unit's depth at a
  conflict well = box.landing_surfaces.estimate of the witnesses within 2 mi (>= 3). Conflict wells are never
  witnesses.
* Call: depth backs vendor X when the well is >= MARGIN_FT closer to X's unit depth than to the other's.
  'neither' = more than FAR_FT from both; 'cannot tell' = within the margin; 'no control' = a unit has no witness
  depth there.
Splits: Novi coarse (sql/16's list, box.tag_screen.NOVI_COARSE) or specific; unit pattern; which vendor the live tag
follows today; inside / outside the BOX record extents; operator.
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

from box import landing_surfaces as ls
from box import tag_screen as ts
from scripts.tag_surface_density import wells_frame

MARGIN_FT = 100.0
FAR_FT = 300.0
R_MI = 2.0
UNIT = {
    "delaware": {"AVA_0": "AVA", "AVA_1": "AVA", "AVA_2": "AVA", "BS1_S": "BS1", "BS2_C": "BS2", "BS2_S": "BS2", "BS3_C": "BS3",
                 "BS3_S": "BS3", "WCXY": "WCA", "WCA_1": "WCA", "WCA_2": "WCA", "WCB_1": "WCB", "WCB_2": "WCB"},
    "midland": {"WCB_1": "WCB", "WCB_2": "WCB"},
}


def unit(basin: str, code: object) -> str | None:
    return UNIT.get(basin, {}).get(code, code) if isinstance(code, str) and code not in ("OTHER",) else None


def run(cache: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    w = wells_frame(cache).assign(api10=lambda x: x["api10"].astype(str))
    v = pd.read_pickle(cache / "vendors.pkl").assign(api10=lambda x: x["api10"].astype(str))[["api10", "novi_raw", "env_raw", "novi_code", "env_code"]]
    d = w.merge(v, on="api10", how="left")
    d["u_novi"] = [unit(b, c) for b, c in zip(d["basin"], d["novi_code"], strict=True)]
    d["u_env"] = [unit(b, c) for b, c in zip(d["basin"], d["env_code"], strict=True)]
    d["u_live"] = [unit(b, c) for b, c in zip(d["basin"], d["live"], strict=True)]
    both = d["u_novi"].notna() & d["u_env"].notna()
    d["witness_unit"] = np.where(both & (d["u_novi"] == d["u_env"]), d["u_novi"], None)
    conf = d[both & (d["u_novi"] != d["u_env"])].copy()
    ex = pd.read_pickle(cache / "extents.pkl")
    inside = np.zeros(len(conf), bool)
    for b, g in ex.groupby("basin"):
        geom = shapely.union_all([shapely.from_wkt(t) for t in g["wkt"]])
        m = (conf["basin"] == b).to_numpy()
        inside[m] = shapely.contains_xy(geom, conf.loc[m, "x"].to_numpy(), conf.loc[m, "y"].to_numpy())
    conf["in_box_extents"] = inside
    rm = R_MI * ls.M_PER_MI
    for side in ("novi", "env"):
        conf[f"z_{side}"] = np.nan
    for (b, u), g in d[d["witness_unit"].notna()].groupby(["basin", "witness_unit"]):
        wxy, wz = g[["x", "y"]].to_numpy(float), g["depth_ft"].to_numpy(float)
        tree = cKDTree(wxy)
        for side in ("novi", "env"):
            m = (conf["basin"] == b) & (conf[f"u_{side}"] == u)
            if not m.any():
                continue
            pts = conf.loc[m, ["x", "y"]].to_numpy(float)
            vals = np.full(len(pts), np.nan)
            for k, js in enumerate(tree.query_ball_point(pts, rm)):
                if len(js) >= 3:
                    vals[k] = ls.estimate(wxy[js], wz[js], pts[k])[0]
            conf.loc[m, f"z_{side}"] = vals
    dn, de = (conf["depth_ft"] - conf["z_novi"]).abs(), (conf["depth_ft"] - conf["z_env"]).abs()
    conf["call"] = np.select(
        [conf["z_novi"].isna() | conf["z_env"].isna(), (dn > FAR_FT) & (de > FAR_FT), dn + MARGIN_FT <= de, de + MARGIN_FT <= dn],
        ["no control", "neither", "Novi", "Enverus"], default="cannot tell")
    conf["novi_coarse"] = conf["novi_raw"].isin(ts.NOVI_COARSE)
    conf["live_follows"] = np.where(conf["u_live"] == conf["u_novi"], "Novi", np.where(conf["u_live"] == conf["u_env"], "Enverus", "neither / override"))
    conf["pattern"] = conf["u_novi"] + " (Novi) vs " + conf["u_env"] + " (Enverus)"
    conf["live_backed"] = ((conf["call"] == "Novi") & (conf["live_follows"] == "Novi")) | ((conf["call"] == "Enverus") & (conf["live_follows"] == "Enverus"))
    keep = ["api10", "well_name", "operator", "county", "basin", "in_box_extents", "novi_raw", "env_raw", "novi_code", "env_code", "live", "live_source",
            "live_follows", "novi_coarse", "pattern", "depth_ft", "depth_source", "z_novi", "z_env", "call", "first_production_date"]
    conf[keep].to_csv(out / "conflict_wells.csv.gz", index=False)

    def tab(g: pd.DataFrame) -> pd.Series:
        dec = g["call"].isin(["Novi", "Enverus"])
        return pd.Series({"wells": len(g), "decided_pct": 100 * dec.mean(), "novi_pct_of_decided": 100 * (g["call"] == "Novi").sum() / max(dec.sum(), 1),
                          "cannot_tell_pct": 100 * (g["call"] == "cannot tell").mean(), "neither_pct": 100 * (g["call"] == "neither").mean(),
                          "no_control_pct": 100 * (g["call"] == "no control").mean(),
                          "live_right_pct_of_decided": 100 * g["live_backed"].sum() / max(dec.sum(), 1)})
    res = {}
    for name, keys in (("by_basin", ["basin"]), ("by_basin_coarse", ["basin", "novi_coarse"]), ("by_basin_extent", ["basin", "in_box_extents"]),
                       ("by_basin_coarse_follows", ["basin", "novi_coarse", "live_follows"]), ("by_pattern", ["basin", "novi_coarse", "pattern"])):
        t = conf.groupby(keys).apply(tab, include_groups=False).reset_index()
        if name == "by_pattern":
            t = t[t["wells"] >= 20].sort_values("wells", ascending=False)
        t.round(1).to_csv(out / f"{name}.csv", index=False)
        res[name] = t
    op = conf[conf["call"].isin(["Novi", "Enverus"])].groupby(["basin", "novi_coarse", "operator"]).apply(tab, include_groups=False).reset_index()
    op[op["wells"] >= 25].sort_values("wells", ascending=False).round(1).to_csv(out / "by_operator.csv", index=False)
    s = {"population": int(both.sum()), "conflicts": len(conf), "params": {"margin_ft": MARGIN_FT, "far_ft": FAR_FT, "r_mi": R_MI}}
    (out / "summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.cache, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
