"""BOX sticks: read Michael's hand-drawn WCXY extent from the pptx (read-only; nothing stored).

    python -m scripts.box_sticks_wcxy_edit --dir docs/box_sticks/wcxy-extent-<date> --pptx <dir>/visual_wcxy.pptx
                                           --cache <phase 0 cache> [--verdicts docs/box_sticks/wcxy-cards-2026-11-12]

The loops drawn over visual_WCXY.png ARE the extent (Michael's convention, 2026-10-16; the same reading as
box/family_extent.run_edits outline mode): union of the closed loops, voids filled, clipped to the map shown, pieces
under 1 sq mi dropped. The picture in the pptx must be the PNG whose frame is in visual_WCXY.frame.json: checked
byte for byte before anything is read.
"""

from __future__ import annotations

import argparse
import json
import math
import zipfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, Polygon
from shapely.validation import make_valid

from box import edge_gap as eg
from box import extent as ex
from box import family_extent as fe
from box import geology_io as gio
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_wcxy as wx
from scripts import box_sticks_wcxy_cards as wc
from scripts import box_sticks_wcxy_extent as wxe

SQMI = eg.FT_PER_MI ** 2


def read_extent(pptx: Path, frame: dict) -> tuple[object, dict]:
    ff, ink = fe.pptx_freeforms(pptx), fe.pptx_ink(pptx)
    k = next(iter(ff))
    pic = ff[k]["picture"]
    marks = ff[k]["lines"] + ink.get(k, [])
    emu_per_px = pic[2] / frame["size"][0]
    gaps = [math.dist(m[0], m[-1]) / emu_per_px for m in marks]
    closed = [m for m, g in zip(marks, gaps, strict=True) if g <= fe.CLOSED_PX]
    loops = [Polygon(gio.geology_to_ft13([LineString(fe.emu_to_geology(m, pic, frame))])[0].coords) for m in closed]
    u = shapely.union_all([make_valid(q) for q in loops]).intersection(fe._clip_frame(frame))
    u = ex.as_multi(shapely.union_all([g for g in getattr(u, "geoms", [u]) if g.geom_type == "Polygon"]).buffer(0))
    ext = ex.as_multi(shapely.union_all([Polygon(g.exterior) for g in u.geoms if g.area >= SQMI]))
    ext = ex.as_multi(make_valid(ext).buffer(0))   # a pen loop can cross itself by a few feet
    return ext, {"slide": k, "marks": len(marks), "closed_loops": len(closed), "open_marks_ignored": len(marks) - len(closed),
                 "end_gap_px": [round(g, 1) for g in gaps], "picture_emu": list(pic)}


def run(d: Path, pptx: Path, cache: Path | None, verdict_dir: Path | None) -> dict:
    frame = json.loads((d / "visual_WCXY.frame.json").read_text(encoding="utf-8"))
    png = (d / "visual_WCXY.png").read_bytes()
    with zipfile.ZipFile(pptx) as z:
        same = any(z.read(n) == png for n in z.namelist() if n.startswith("ppt/media/"))
    if not same:
        raise SystemExit("the picture in the pptx is not the visual_WCXY.png this frame belongs to; refusing to read the loops")
    ext, how = read_extent(pptx, frame)

    data = p0.pull(cache)
    w = p0.evidence(data["wells"], data["rule"])
    bw = w[w["basin"] == "delaware"].reset_index(drop=True)
    x = wx.classify(bw)
    x = x[x["midpoint_lon"].notna()].join(wx.landings(bw, x))
    g = wxe.to_geology_xy(x["midpoint_lon"].to_numpy(), x["midpoint_lat"].to_numpy())
    x["gx"], x["gy"] = g[:, 0], g[:, 1]
    ext_g = gio.ft13_to_geology([ext])[0]
    x["inside"] = shapely.contains_xy(ext_g, x["gx"].to_numpy(), x["gy"].to_numpy())
    p, x = wc.pads(x)

    def tab(by: str) -> dict:
        return {str(k): {"inside": int(v["inside"].sum()), "outside": int((~v["inside"]).sum())} for k, v in x.groupby(by)}

    hi = x[x["above_wca1_ft"] >= 100]
    cand = shapely.geometry.shape(json.loads((d / "candidate_WCXY.geojson").read_text(encoding="utf-8"))["features"][0]["geometry"])
    cand_ft = ex.as_multi(eg.to_ft([cand])[0])
    wca = data["extents"]
    wca = wca[(wca["basin"] == "delaware") & (wca["bench"] == "WCA")]
    summary = {"code_sha": p0._git_sha(), "pptx": pptx.name, "picture_matches_png": True, "reading": how,
               "extent": {"sqmi": float(ext.area / SQMI), "parts": len(ext.geoms), "bounds_lonlat": [round(v, 4) for v in eg.to_lonlat([ext])[0].bounds]},
               "candidate_sqmi": float(cand_ft.area / SQMI), "shared_with_candidate_sqmi": float(ext.intersection(cand_ft).area / SQMI),
               "wcxy_tagged_wells": {"inside": int(x["inside"].sum()), "outside": int((~x["inside"]).sum())},
               "wells_100ft_plus_above_wca1": {"inside": int(hi["inside"].sum()), "outside": int((~hi["inside"]).sum())},
               "median_above_wca1_ft": {"inside": float(x.loc[x["inside"], "above_wca1_ft"].median()), "outside": float(x.loc[~x["inside"], "above_wca1_ft"].median())},
               "by_county": tab("county"), "by_state": tab("state_code")}
    cards = None
    if verdict_dir:
        v = pd.read_csv(verdict_dir / "verdicts.csv")
        cards = wc.sample(p)[["card", "group", "name", "county"]].merge(v[["card", "verdict"]], on="card")
        cards = cards.join(x.groupby("group")[["gx", "gy", "above_wca1_ft"]].median(), on="group")
        cards["inside"] = shapely.contains_xy(ext_g, cards["gx"].to_numpy(), cards["gy"].to_numpy())
        cards.drop(columns=["group"]).sort_values("card").to_csv(d / "cards_vs_edited.csv", index=False)
        summary["cards"] = {vv: {"inside": sorted(c.loc[c["inside"], "card"].tolist()), "outside": sorted(c.loc[~c["inside"], "card"].tolist())}
                            for vv, c in cards.groupby("verdict")}

    # the reading, drawn back on the reviewed PNG so Michael can see his loop was read where he drew it
    img = plt.imread(d / "visual_WCXY.png")
    fig = plt.figure(figsize=(frame["size"][0] / 110, frame["size"][1] / 110), dpi=110)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img)
    (x0, y0, x1, y1), (px0, py0, px1, py1) = frame["data"], frame["pix"]
    for gg in ex.as_multi(ext_g).geoms:
        c = np.asarray(gg.exterior.coords)
        ax.plot(px0 + (c[:, 0] - x0) / (x1 - x0) * (px1 - px0), py0 + (c[:, 1] - y0) / (y1 - y0) * (py1 - py0), color="#dc2626", lw=2.2)
    ax.set_xlim(0, frame["size"][0])
    ax.set_ylim(frame["size"][1], 0)
    ax.axis("off")
    fig.savefig(d / "reading_WCXY.png", dpi=110)
    plt.close(fig)

    (d / "extent_WCXY_edited.geojson").write_text(json.dumps({"type": "FeatureCollection", "name": "box_extent_WCXY_edited", "crs_note": "EPSG:4326",
        "features": [{"type": "Feature", "properties": {"layer": "extent", "pool": "WCXY", "source": "geology_edited, NOT stored",
                                                         "note": f"hand-drawn by Michael 2026-11-12 ({pptx.name})"},
                      "geometry": shapely.geometry.mapping(shapely.set_precision(make_valid(eg.to_lonlat([ext])[0]).buffer(0), 1e-6))}]}), encoding="utf-8")
    x.loc[~x["inside"], ["api10", "well_name", "operator", "county", "state_code", "depth_ft", "above_wca1_ft"]].to_csv(d / "wcxy_wells_outside_edited.csv", index=False)
    (d / "edited_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--pptx", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--verdicts", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.dir, a.pptx, a.cache, a.verdicts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
