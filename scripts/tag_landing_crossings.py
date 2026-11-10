"""Step A: landing-surface crossing map per BOX extent (read-only) — docs/formation_tag_redesign.

    python -m scripts.tag_landing_crossings --cache <scoreboard cache> --out docs/formation_tag_redesign/stepA-crossings-<date>

Builds a landing surface for every code inside its BOX record extent (box.landing_surfaces: direct within 1 mi of the
code's own control, structure + thickness to 5 mi, nothing beyond). It then compares every pair of codes in
stratigraphic order wherever both surfaces exist. The outputs are where they cross or merge (< 50 ft) and the
evidence wells sitting there, ranked with BOX record-pool members first, then the extent fringe.

Inputs (nothing is written to the warehouse): the scoreboard pull (wells.pkl), the record extents (extents.pkl), and
the BOX record runs' analog pools from the committed docs/box wells_final_*.csv sets (record_pools()).
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely

from box import landing_surfaces as ls
from box import tag_scoreboard as sb
from scripts.tag_surface_density import wells_frame

P = ls.PARAMS
STEP_M = P.node_mi * ls.M_PER_MI
NODE_SQMI = P.node_mi ** 2
COLORS = {"separated": "#d1d5db", "merged": "#f59e0b", "crossing": "#dc2626"}


def build_surfaces(w: pd.DataFrame, ex: pd.DataFrame) -> tuple[dict, dict]:
    """{(basin, code): node frame indexed (ix, iy) with z, basis, near_mi, edge_mi}, {(basin, code): extent geom}."""
    surf, geoms = {}, {}
    for e in ex.itertuples():
        geom = shapely.from_wkt(e.wkt)
        keys, xy = ls.lattice(geom.bounds, STEP_M)
        inside = shapely.contains_xy(geom, xy[:, 0], xy[:, 1])
        keys, xy = keys[inside], xy[inside]
        edge = shapely.distance(shapely.points(xy), geom.boundary) / ls.M_PER_MI
        bw = w[w["basin"] == e.basin]
        for code in ls.extent_codes(e.basin, e.bench):
            c = bw[bw["live"] == code]
            acodes = ls.ANCHOR.get(e.basin, {}).get(code)
            a = bw[bw["live"].isin(acodes)] if acodes and code not in acodes else None
            s = ls.surface(xy, c[["x", "y"]].to_numpy(float), c["depth_ft"].to_numpy(float),
                           a[["x", "y"]].to_numpy(float) if a is not None else None, a["depth_ft"].to_numpy(float) if a is not None else None, P)
            s.index = pd.MultiIndex.from_arrays([keys[:, 0], keys[:, 1]], names=["ix", "iy"])
            s["edge_mi"] = edge
            surf[(e.basin, code)] = s.dropna(subset=["z"])
            geoms[(e.basin, code)] = geom
            print(f"  {e.basin} {code}: {len(surf[(e.basin, code)]):,} of {len(s):,} nodes "
                  f"({(s['basis'] == 'direct').sum():,} direct, {(s['basis'] == 'thickness').sum():,} thickness)", flush=True)
    return surf, geoms


def pair_table(surf: dict, order: dict[str, list[str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, flagged = [], []
    for b, cs in order.items():
        have = [c for c in cs if (b, c) in surf]
        for i, up in enumerate(have):
            for lo in have[i + 1:]:
                c = ls.compare(surf[(b, up)], surf[(b, lo)], P.merge_ft)
                if c.empty:
                    continue
                edge = np.minimum(surf[(b, up)]["edge_mi"].reindex(c.index).to_numpy(), surf[(b, lo)]["edge_mi"].reindex(c.index).to_numpy())
                fr = edge <= P.fringe_mi
                st = c["state"].to_numpy()
                gap_rank = cs.index(lo) - cs.index(up)
                rows.append({"basin": b, "upper": up, "lower": lo, "benches_apart": gap_rank, "shared_sqmi": len(c) * NODE_SQMI,
                             "median_gap_ft": float(c["gap_ft"].median()),
                             "crossing_sqmi": float((st == "crossing").sum() * NODE_SQMI), "merged_sqmi": float((st == "merged").sum() * NODE_SQMI),
                             "crossing_pct": 100 * float((st == "crossing").mean()), "merged_pct": 100 * float((st == "merged").mean()),
                             "fringe_shared_sqmi": float(fr.sum() * NODE_SQMI),
                             "fringe_crossing_pct": 100 * float((st[fr] == "crossing").mean()) if fr.any() else np.nan,
                             "interior_crossing_pct": 100 * float((st[~fr] == "crossing").mean()) if (~fr).any() else np.nan})
                f = c[c["state"] != "separated"].copy()
                if len(f):
                    f["basin"], f["upper"], f["lower"] = b, up, lo
                    f["edge_mi"] = edge[(c["state"] != "separated").to_numpy()]
                    flagged.append(f.reset_index())
    return pd.DataFrame(rows), (pd.concat(flagged, ignore_index=True) if flagged else pd.DataFrame())


def wells_in_zones(w: pd.DataFrame, surf: dict, flagged: pd.DataFrame, pools: pd.DataFrame) -> pd.DataFrame:
    if flagged.empty:
        return pd.DataFrame()
    w = w.assign(ix=np.rint(w["x"] / STEP_M).astype(int), iy=np.rint(w["y"] / STEP_M).astype(int))
    out = []
    for side, other in (("upper", "lower"), ("lower", "upper")):
        m = w.merge(flagged, left_on=["basin", "live", "ix", "iy"], right_on=["basin", side, "ix", "iy"], how="inner")
        if m.empty:
            continue
        m["other_code"] = m[other]
        own = np.where(side == "upper", m["z_u"], m["z_l"])
        oth = np.where(side == "upper", m["z_l"], m["z_u"])
        m["own_surface_ft"], m["other_surface_ft"] = own, oth
        m["closer_to_other"] = np.abs(m["depth_ft"] - oth) < np.abs(m["depth_ft"] - own)
        out.append(m)
    r = pd.concat(out, ignore_index=True)
    pk = pools.assign(api10=pools["api10"].astype(str)).groupby(["basin", "api10"])["pool"].agg(lambda s: ",".join(sorted(set(s)))).rename("box_pool")
    r = r.join(pk, on=["basin", "api10"])
    r["in_box_pool"] = r["box_pool"].notna()
    r["zone"] = np.where(r["edge_mi"] <= 1, "fringe 0-1 mi", np.where(r["edge_mi"] <= 2, "1-2 mi", "interior"))
    r["pair"] = r["upper"] + " | " + r["lower"]
    # suspect: a well closer to the OTHER bench's surface than to its own is the likely mis-tag; a well on its own
    # surface points at the other bench's control there instead. Ranked: fringe first, then likely mis-tags, then
    # crossings before merges, then the deepest crossings. (Inside the extents nearly every well is in a record analog
    # pool, so pool membership does not rank.)
    r["suspect"] = np.where(r["closer_to_other"], "this well", "other bench here")
    r["zone_rank"] = r["edge_mi"].clip(upper=2.0).round(0)
    r = r.sort_values(["zone_rank", "closer_to_other", "state", "gap_ft"], ascending=[True, False, True, True])
    cols = ["api10", "well_name", "operator", "county", "basin", "live", "other_code", "pair", "state", "gap_ft", "zone", "edge_mi",
            "suspect", "in_box_pool", "box_pool", "depth_ft", "depth_source", "own_surface_ft", "other_surface_ft", "closer_to_other",
            "first_production_date"]
    return r[cols].drop_duplicates(subset=["api10", "pair"])


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=72, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def pair_map(b: str, up: str, lo: str, surf: dict, geoms: dict, zw: pd.DataFrame, row: pd.Series) -> str:
    c = ls.compare(surf[(b, up)], surf[(b, lo)], P.merge_ft)
    k = np.array(c.index.to_list(), float) * STEP_M / ls.M_PER_MI
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    for st in ("separated", "merged", "crossing"):
        m = (c["state"] == st).to_numpy()
        ax.scatter(k[m, 0], k[m, 1], s=1.2, c=COLORS[st], marker="s", linewidths=0, label=f"{st} ({m.sum() * NODE_SQMI:,.0f} sq mi)")
    for code, ls_ in ((up, "-"), (lo, "--")):
        g = geoms[(b, code)]
        for poly in getattr(g, "geoms", [g]):
            x, y = poly.exterior.xy
            ax.plot(np.asarray(x) / ls.M_PER_MI, np.asarray(y) / ls.M_PER_MI, ls_, color="#111827", lw=0.6)
    z = zw[(zw["basin"] == b) & (zw["pair"] == f"{up} | {lo}")]
    if len(z):
        ww = z.merge(WELLS_XY, on="api10", how="left")
        ax.scatter(ww["x"] / ls.M_PER_MI, ww["y"] / ls.M_PER_MI, s=5, c="#111827", label=f"wells in zone ({len(z):,})")
    ax.set_aspect("equal")
    ax.set_xlabel("mi (EPSG:3083 easting)")
    ax.set_ylabel("mi (northing)")
    ax.set_title(f"{b.title()} {up} (above) vs {lo}: {row.crossing_pct:.1f} % crossing, {row.merged_pct:.1f} % < {P.merge_ft:.0f} ft "
                 f"of {row.shared_sqmi:,.0f} sq mi shared", fontsize=9)
    ax.legend(fontsize=7, markerscale=6, loc="best")
    return _png(fig)


WELLS_XY = pd.DataFrame()

# The record runs' analog pools (docs/box/step23-2026-11-03/RECORD_PLAN.md 3.1): Delaware record run 32 = run 19's sets
# (pool-2026-10-15 WCA + BS2_S, the step-15 / 15a sets); Midland record run 30 = pool-midland-2026-10-31. A member is a
# well whose box_action is keep or reassign; its pool is its box_bench. (box.tc_member holds only the Delaware WCA pool.)
RECORD_POOL_DIRS = {"delaware": ("pool-2026-10-15", "step15-AVA-2026-10-16", "step15-BS1-2026-10-16", "step15-BS2C-2026-10-16",
                                 "step15-WCB-2026-10-16", "step15-WCC-2026-10-16", "step15-WCD-2026-10-16", "step15a-2026-10-16"),
                    "midland": ("pool-midland-2026-10-31",)}


def record_pools(root: Path = sb.ROOT) -> pd.DataFrame:
    parts = []
    for basin, dirs in RECORD_POOL_DIRS.items():
        for d in dirs:
            for f in sorted((root / "docs" / "box" / d).glob("wells_final_*.csv")):
                t = pd.read_csv(f, dtype={"api10": str}, usecols=["api10", "box_bench", "box_action"])
                t = t[t["box_action"].isin(["keep", "reassign"])]
                parts.append(pd.DataFrame({"api10": t["api10"], "basin": basin, "pool": t["box_bench"]}))
    return pd.concat(parts, ignore_index=True).drop_duplicates()


def run(cache: Path, out: Path) -> dict:
    global WELLS_XY
    out.mkdir(parents=True, exist_ok=True)
    w = wells_frame(cache)
    w["api10"] = w["api10"].astype(str)
    WELLS_XY = w[["api10", "x", "y"]]
    ex = pd.read_pickle(cache / "extents.pkl")
    pools = record_pools()
    print(pools.groupby("basin")["api10"].nunique().to_dict(), flush=True)
    order = sb.bench_order()
    surf, geoms = build_surfaces(w, ex)
    pt, flagged = pair_table(surf, order)
    pt.sort_values(["basin", "crossing_sqmi"], ascending=[True, False]).to_csv(out / "pairs.csv", index=False)
    if not flagged.empty:
        flagged.to_csv(out / "flagged_nodes.csv.gz", index=False)
    zw = wells_in_zones(w, surf, flagged, pools)
    zw.to_csv(out / "wells_in_zones.csv", index=False)
    cov = pd.DataFrame([{"basin": b, "code": c, "nodes": len(s), "sqmi": len(s) * NODE_SQMI,
                         "direct_pct": 100 * float((s["basis"] == "direct").mean()), "thickness_pct": 100 * float((s["basis"] == "thickness").mean())}
                        for (b, c), s in surf.items()])
    cov.to_csv(out / "surface_coverage.csv", index=False)
    adj = pt[pt["benches_apart"] == 1]
    summary = {"built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "params": P.__dict__,
               "by_basin": {b: {"adjacent_shared_sqmi": round(float(g["shared_sqmi"].sum())),
                                "adjacent_crossing_sqmi": round(float(g["crossing_sqmi"].sum())),
                                "adjacent_merged_sqmi": round(float(g["merged_sqmi"].sum())),
                                "nonadjacent_crossing_sqmi": round(float(pt[(pt["basin"] == b) & (pt["benches_apart"] > 1)]["crossing_sqmi"].sum())),
                                "wells_in_zones": int(zw[zw["basin"] == b]["api10"].nunique()) if len(zw) else 0,
                                "wells_in_zones_in_box_pool": int(zw[(zw["basin"] == b) & zw["in_box_pool"]]["api10"].nunique()) if len(zw) else 0}
                            for b, g in adj.groupby("basin")}}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    # page
    show = pt[(pt["benches_apart"] == 1) | (pt["crossing_sqmi"] >= 1)].sort_values(["basin", "benches_apart", "crossing_sqmi"], ascending=[True, True, False])
    secs = []
    for b, g in show.groupby("basin"):
        tbl = g[["upper", "lower", "benches_apart", "shared_sqmi", "median_gap_ft", "crossing_pct", "merged_pct", "fringe_crossing_pct",
                 "interior_crossing_pct"]].round(1).to_html(index=False, border=0)
        imgs = "".join(f"<img src=\"{pair_map(b, r.upper, r.lower, surf, geoms, zw, r)}\">" for r in g.itertuples() if r.shared_sqmi >= 5)
        secs.append(f"<h2>{b.title()}</h2>{tbl}<div class=maps>{imgs}</div>")
    css = ("body{font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#111827;background:#fff;margin:0 24px 48px;max-width:1600px}"
           "table{border-collapse:collapse;margin:8px 0}td,th{padding:2px 8px;border-bottom:1px solid #e5e7eb;text-align:right}"
           ".maps img{width:48%;margin:1%}.meta{color:#6b7280}")
    page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Landing surface crossings</title><style>{css}</style></head><body>"
            "<h1>Landing-surface crossings, BOX record extents (step A)</h1>"
            f"<div class=meta>Built {summary['built_at']}, read-only. One landing surface per extent and code from live-tagged evidence wells "
            "(survey depth else clean tvd_ft, no planned survey, >= 4,000 ft): the code's own wells within 2 mi where its nearest well is "
            "within 1 mi; structure from a thick anchor bench + local thickness out to 5 mi; nothing beyond. Red = the deeper bench's "
            f"surface at or above the shallower one; amber = within {P.merge_ft:.0f} ft. Solid outline = upper code's extent, dashed = "
            "lower. The wells sitting in red/amber nodes are listed in wells_in_zones.csv (fringe first, then wells sitting closer to the other bench's surface).</div>"
            + "".join(secs) + "</body></html>")
    (out / "crossings.html").write_text(page, encoding="utf-8")
    print(json.dumps(summary["by_basin"], indent=1))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.cache, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
