"""BOX step 20a follow-up — one vs two Wolfcamp B landings in the Midland, and what the WCB extents do about it (read-only).

    python -m scripts.box_wcb_split --wells docs/box/step20a-2026-10-26 [--cache <scored_midland.pkl>]

Reads the step-20a WCB_1 / WCB_2 sets + generated extents, pulls the laterals and the Novi WCB sticks (READ ONLY), measures
the landing depth below the local WCA_1 band (box/wcb_split.py), locates the demarcation, and writes <wells>/wcb_split/:
index.html (map, latitude profile, depth histograms, tables), wcb_line.geojson + geology/BOX_MID_WCB_split_line (NAD83
UTM 14N US-ft), profile / boundary / stick CSVs and summary.json. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, Polygon, mapping, shape

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import extent as ex
from box import extent_package as pkg
from box import extent_report as er
from box import family_extent as fe
from box import geology_io as gio
from box import wcb_split as ws
from box.bench_qc import pull_producers, score_consensus
from etl.db import get_connection

FT_MI = 5280.0
CELL_FT = 4 * FT_MI


def _git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=False).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def _png(fig) -> str:
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=95, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def _extent(wells_dir: Path, bench: str):
    gj = json.loads((wells_dir / "extents" / f"extent_{bench}_v1.geojson").read_text(encoding="utf-8"))
    return eg.to_ft([shape(next(f for f in gj["features"] if f["properties"]["layer"] == "extent")["geometry"])])[0]


def _rings(ax, g, **kw):
    for p in getattr(g, "geoms", [g]):
        c = np.asarray(p.exterior.coords)
        ax.plot(c[:, 0], c[:, 1], **kw)
        kw.pop("label", None)


def _table(df: pd.DataFrame, fmt: dict[str, str] | None = None) -> str:
    fmt = fmt or {}
    th = "".join(f"<th>{c}</th>" for c in df.columns)
    body = "".join("<tr>" + "".join(f"<td>{format(v, fmt[c]) if c in fmt and isinstance(v, (int, float)) and np.isfinite(v) else v}</td>" for c, v in r.items()) + "</tr>"
                   for _, r in df.iterrows())
    return f"<table><tr>{th}</tr>{body}</table>"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wells", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None, help="pickle of the scored Midland frame (box_family_qc --cache)")
    a = ap.parse_args(argv)
    t0 = time.time()
    out = a.wells / "wcb_split"
    out.mkdir(parents=True, exist_ok=True)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    sha = _git_sha()  # before anything is written (a re-run overwrites tracked outputs)
    scored = pd.read_pickle(a.cache) if a.cache and a.cache.exists() else None
    with get_connection() as conn:
        if scored is None:
            scored = score_consensus(pull_producers(conn, "midland"))
        fin = pd.concat([pd.read_csv(a.wells / f"wells_final_{b}.csv", dtype={"api10": str}, usecols=["api10", "box_bench"]) for b in ("WCB_1", "WCB_2")])
        w = fin.merge(scored.drop(columns=["box_bench"], errors="ignore"), on="api10")
        w = w[np.array([d is not None and d >= dt.date(2016, 1, 1) for d in w["first_production_date"]])].reset_index(drop=True)
        w = egr.attach_geometry(w, egr.pull_laterals(conn, sorted(w["api10"])))
        sticks = er.pull_sticks(conn, ["WCB_1", "WCB_2"], (-103.2, 30.5, -100.3, 33.6), "midland")
    w = w[w["geom"].notna()].reset_index(drop=True)
    w["below_wca1"] = ws.landing_depth(w)
    cut = ws.deep_cut(w)
    w["deep"] = w["below_wca1"] >= cut["cut_ft"]
    ref = w[w["below_wca1"].notna()].copy()
    ref["deep"] = ref["deep"].astype(bool)
    prof = ws.lat_profile(ref)
    bnd = ws.boundary(ref)
    ln = ws.line(bnd)
    north_ll = Polygon([*ln, (ln[-1][0], 34.0), (ln[0][0], 34.0)])
    north = eg.to_ft([north_ll])[0]
    xy = np.array([(g.centroid.x, g.centroid.y) for g in ref["geom"]])
    ref["north"] = shapely.contains_xy(north, xy[:, 0], xy[:, 1])
    side = ref.groupby("north").agg(n=("api10", "size"), deep=("deep", "sum"), deep_share=("deep", "mean"),
                                     tagged_wcb2=("box_bench", lambda s: int((s == "WCB_2").sum())),
                                     median_below_wca1_ft=("below_wca1", "median")).rename(index={False: "south of line", True: "north of line"})
    # extents and Novi sticks
    ext = {b: _extent(a.wells, b) for b in ("WCB_1", "WCB_2")}
    clipped = ext["WCB_2"].difference(north)
    G = np.asarray(eg.to_ft(list(shapely.from_wkt(sticks["wkt"]))), dtype=object)
    L = np.maximum(shapely.length(G), 1.0)
    sticks["undrilled"] = sticks["status"].isna() | sticks["status"].isin(["remaining_pud", "conflict"])
    cxy = np.array([(g.centroid.x, g.centroid.y) for g in G])
    sticks["north"] = shapely.contains_xy(north, cxy[:, 0], cxy[:, 1])
    for k, poly in (("in_WCB_1", ext["WCB_1"]), ("in_WCB_2", ext["WCB_2"]), ("in_WCB_2_clipped", clipped)):
        shapely.prepare(poly)
        sticks[k] = shapely.length(shapely.intersection(G, poly)) / L >= 0.5
    u = sticks[sticks["undrilled"]]
    st_tab = (u.groupby(["formation_blueox", "north"]).agg(undrilled=("stick_id", "size"), PUD=("category", lambda s: int((s == "PUD").sum())),
                                                          RES=("category", lambda s: int((s == "RES").sum())), in_own_extent_generated=("in_WCB_1", "sum"))
              .reset_index())
    st_tab.loc[st_tab.formation_blueox == "WCB_2", "in_own_extent_generated"] = [
        int(u[(u.formation_blueox == "WCB_2") & (u.north == n)]["in_WCB_2"].sum()) for n in st_tab.loc[st_tab.formation_blueox == "WCB_2", "north"]]
    st_tab["in_own_extent_clipped"] = st_tab["in_own_extent_generated"]
    st_tab.loc[st_tab.formation_blueox == "WCB_2", "in_own_extent_clipped"] = [
        int(u[(u.formation_blueox == "WCB_2") & (u.north == n)]["in_WCB_2_clipped"].sum()) for n in st_tab.loc[st_tab.formation_blueox == "WCB_2", "north"]]
    st_tab["north"] = st_tab["north"].map({True: "north of line", False: "south of line"})
    areas = pd.DataFrame([{"extent": b, "sq_mi": ext[b].area / FT_MI**2, "north_of_line_sq_mi": ext[b].intersection(north).area / FT_MI**2} for b in ext]
                         + [{"extent": "WCB_2 clipped at the line", "sq_mi": clipped.area / FT_MI**2, "north_of_line_sq_mi": 0.0}])
    # --- figures
    cx = (xy[:, 0] // CELL_FT).astype(int)
    cy = (xy[:, 1] // CELL_FT).astype(int)
    cells = pd.DataFrame({"cx": cx, "cy": cy, "deep": ref["deep"].values}).groupby(["cx", "cy"]).agg(n=("deep", "size"), deep=("deep", "mean")).reset_index()
    cells = cells[cells["n"] >= 8]
    lnft = eg.to_ft([LineString(ln)])[0]
    fig, ax = plt.subplots(figsize=(11, 13))
    sc = ax.scatter((cells["cx"] + 0.5) * CELL_FT, (cells["cy"] + 0.5) * CELL_FT, c=cells["deep"], cmap="RdYlBu_r", vmin=0, vmax=0.6, s=95, marker="s",
                    edgecolors="#374151", linewidths=0.3)
    fig.colorbar(sc, ax=ax, shrink=0.5).set_label("share of WCB laterals landed at WCB_2 depth (4-mi cells, >= 8 laterals)")
    _rings(ax, ext["WCB_1"], color="#dc2626", lw=1.4, label="WCB_1 extent (generated)")
    _rings(ax, ext["WCB_2"], color="#7f1d1d", lw=1.4, ls="--", label="WCB_2 extent (generated)")
    nw = u[(u.formation_blueox == "WCB_2") & u.north]
    for g in G[nw.index.values]:
        c = np.asarray(g.coords)
        ax.plot(c[:, 0], c[:, 1], color="#7c3aed", lw=0.6, alpha=0.6)
    ax.plot([], [], color="#7c3aed", lw=1, label=f"undrilled Novi WCB_2 sticks north of the line (n={len(nw):,})")
    c = np.asarray(lnft.coords)
    ax.plot(c[:, 0], c[:, 1], color="#111827", lw=2.4, label="demarcation (data-derived)")
    b0 = shapely.total_bounds(np.asarray([ext["WCB_1"], ext["WCB_2"]], dtype=object))
    ax.set_xlim(b0[0] - 10 * FT_MI, b0[2] + 10 * FT_MI)
    ax.set_ylim(b0[1] - 10 * FT_MI, b0[3] + 10 * FT_MI)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.legend(loc="lower left", fontsize=8)
    ax.set_title("Midland Wolfcamp B: where a second (WCB_2-depth) landing is developed", fontsize=10)
    img_map = _png(fig)
    fig, ax = plt.subplots(figsize=(9, 4))
    mid = [float(s.split("-")[0]) + 0.05 for s in prof.index]
    ax.plot(mid, prof["deep"], "o-", color="#7f1d1d", label="landed at WCB_2 depth (tag-free)")
    ax.plot(mid, prof["tagged_wcb2"], "s--", color="#9ca3af", label="tagged WCB_2")
    ax.set_xlabel("latitude, deg N (0.1-deg bands)")
    ax.set_ylabel("share of modern WCB laterals")
    ax.grid(alpha=0.3)
    ax.legend()
    img_prof = _png(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8), sharex=True)
    for axx, (lab, q) in zip(axes, (("south of the line", ref[~ref["north"]]), ("north of the line", ref[ref["north"]]))):
        for b, col in (("WCB_1", "#dc2626"), ("WCB_2", "#7f1d1d")):
            axx.hist(q.loc[q["box_bench"] == b, "below_wca1"].clip(0, 900), bins=np.arange(0, 925, 25), alpha=0.6, color=col, label=f"tagged {b}")
        axx.axvline(cut["cut_ft"], color="#111827", ls=":")
        axx.set_title(f"{lab} (n={len(q):,})", fontsize=10)
        axx.set_xlabel("TVD below the local WCA_1 band, ft")
        axx.legend(fontsize=8)
    img_hist = _png(fig)
    # --- files
    gj = {"type": "FeatureCollection", "name": "box_midland_wcb_split_line", "crs_note": "EPSG:4326",
          "features": [{"type": "Feature", "properties": {"layer": "wcb_split_line", "built": built, "rule": f">= {ws.DEEP_SHARE:.0%} at WCB_2 depth, north edge"},
                        "geometry": mapping(LineString(ln))}]}
    (out / "wcb_line.geojson").write_text(json.dumps(gj), encoding="utf-8")
    (out / "geology").mkdir(exist_ok=True)
    gio.write_layer(out / "geology" / "BOX_MID_WCB_split_line", "line", gio.ft13_to_geology([lnft]), [("NAME", "C", 60, 0), ("RULE", "C", 120, 0)],
                    [["Midland WCB one/two-landing demarcation (data-derived)", f">= {ws.DEEP_SHARE:.0%} laterals >= {cut['cut_ft']:.0f} ft below local WCA_1, north edge, {built[:10]}"]])
    # the proposal: the generated WCB_2 extent clipped at the line (NOT stored; geology round-trip format + a visual map with its
    # pixel frame, so the owner's WCB_2 loops are drawn on the clipped outline)

    clip_m = ex.as_multi(clipped)
    gio.write_layer(out / "geology" / "BOX_WCB_2_extent_v1_clipped", "polygon", gio.ft13_to_geology([clip_m]), pkg.EXTENT_FIELDS,
                    [["WCB_2", "midland", 1, "generated", clip_m.area / FT_MI**2, built, "generated v1 clipped at the WCB one/two-landing line (proposal)"]])
    (out / "extent_WCB_2_v1_clipped.geojson").write_text(json.dumps({
        "type": "FeatureCollection", "name": "box_extent_WCB_2_v1_clipped", "crs_note": "EPSG:4326",
        "features": [{"type": "Feature", "properties": {"layer": "extent", "pool": "WCB_2", "basin": "midland", "version": 1, "source": "generated_clipped"},
                      "geometry": mapping(shapely.set_precision(eg.to_lonlat([clip_m])[0], 1e-6))}]}), encoding="utf-8")
    with get_connection() as conn:
        w2 = egr.load_final_sets(a.wells, ("WCB_2",))
        w2 = egr.attach_geometry(w2, egr.pull_laterals(conn, sorted(w2["api10"].unique())))
    vis = fe.visual_check_png("WCB_2", w2, clip_m, er.load_sopa(), out / "visual_WCB_2_clipped.png", label="generated D27 extent CLIPPED at the WCB split line",
                              bodies_min=50, edge=er.edge_params("midland"), basin="midland")
    prof.to_csv(out / "profile.csv")
    bnd.to_csv(out / "boundary_by_strip.csv", index=False)
    st_tab.to_csv(out / "sticks.csv", index=False)
    summary = {"built_at": built, "git_sha": sha, "asof": str(scored.attrs.get("asof")), "n_wcb_modern": len(w), "n_with_wca1_ref": len(ref),
               "cut": cut, "line_lonlat": ln, "sides": side.reset_index().to_dict(orient="records"), "areas": areas.to_dict(orient="records"),
               "sticks": st_tab.to_dict(orient="records"), "boundary": bnd.to_dict(orient="records")}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    css = ("body{font-family:system-ui,Segoe UI,sans-serif;max-width:1150px;margin:24px auto;padding:0 16px;color:#111827}table{border-collapse:collapse;margin:8px 0}"
           "td,th{border:1px solid #d1d5db;padding:3px 8px;font-size:13px;text-align:right}th{background:#f3f4f6}.meta{color:#4b5563;font-size:13px}img{max-width:100%}")
    page = [f"<!doctype html><html><head><meta charset=utf-8><title>BOX 20a — Midland WCB split</title><style>{css}</style></head><body>",
            "<h1>BOX step 20a follow-up — one vs two Wolfcamp B landings (Midland)</h1>",
            (f"<div class=meta>Grain: modern (first production ≥ 2016) WCB_1 + WCB_2 laterals of the step-20a sets, n = {len(w):,}; {len(ref):,} with a coherent local WCA_1 band "
             f"(1.5-mi consensus neighbourhood) to measure from. Landing depth = TVD − local WCA_1 band median, so structure drops out; tags ignored. "
             f"WCB_2 depth = ≥ {cut['cut_ft']:.0f} ft below WCA_1, the midpoint of the southern (&lt; {ws.SOUTH_REF_LAT}°N) tag medians "
             f"({cut['wcb1_median_ft']:.0f} ft WCB_1 / {cut['wcb2_median_ft']:.0f} ft WCB_2). Demarcation: per {ws.LON_STRIP}° longitude strip, the north edge of the "
             f"northernmost {ws.LAT_BIN}° bin with ≥ {ws.DEEP_SHARE:.0%} of laterals at WCB_2 depth (≥ {ws.MIN_BIN} laterals per bin), held flat past the data. "
             f"Warehouse as-of {scored.attrs.get('asof')}; built {built} at {sha}. Read-only. Files: <code>wcb_line.geojson</code>, <code>geology/BOX_MID_WCB_split_line.shp</code> (NAD83 UTM 14N US-ft).</div>"),
            "<h2>Map</h2>", f"<img src='{img_map}'>",
            "<h2>Latitude profile</h2>", f"<img src='{img_prof}'>", _table(prof.reset_index().rename(columns={"index": "lat band"}), {"deep": ".2f", "tagged_wcb2": ".2f", "median_below_wca1_ft": ",.0f"}),
            "<h2>Landing depth, south vs north of the line</h2>", f"<img src='{img_hist}'>",
            _table(side.reset_index().rename(columns={"north": "side"}), {"deep_share": ".2f", "median_below_wca1_ft": ",.0f"}),
            "<h2>Demarcation by longitude strip</h2>", _table(bnd, {"deep_share_north": ".2f"}),
            "<h2>Extents and undrilled Novi sticks (D117: PUD + RES; ≥ 50 % of the stick inside)</h2>", f"<p>Proposal (not stored): <code>extent_WCB_2_v1_clipped.geojson</code>, <code>geology/BOX_WCB_2_extent_v1_clipped.shp</code>; <code>visual_WCB_2_clipped.png</code> (+ frame) for your WCB_2 loops. Modern WCB_2 laterals inside the clipped extent: {vis['n_inside']:,} of {vis['n_evidence']:,}.</p>",
            _table(areas, {"sq_mi": ",.0f", "north_of_line_sq_mi": ",.0f"}), _table(st_tab),
            "</body></html>"]
    (out / "index.html").write_text("".join(page), encoding="utf-8")
    print(json.dumps({"cut": cut, "sides": summary["sides"], "areas": summary["areas"], "sticks": summary["sticks"]}, indent=1, default=str))
    print(f"wrote {out / 'index.html'} ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
