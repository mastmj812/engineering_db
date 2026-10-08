"""BOX step 3 — the geology package: shapefiles (NAD83 UTM 14N US-ft), context contours from
Holden's GGX grids (D25: context only), a one-page legend PNG per pool, and a README.

Layers per pool (``BOX_<pool>_*``):
  extent_v<N>   polygon   — THE layer geology edits (move vertices, cut, add); return it renamed *_edited
  edges_v<N>    polyline  — the extent boundary split by the walked segment that set its buffer
  laterals      polyline  — evidence / pre-2016 / island / excluded step-outs, with TVD + 12-mo oil
  flags         point     — holes and excluded step-outs (what geology is asked to look at)
  ctx_struct    polyline  — bench-top structure contours (from the grid)
  ctx_isopach   polyline  — bench interval isopach contours (base grid − top grid)
Shared: BOX_potash_SOPA (the D24 ignore-gap polygon).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.interpolate import RegularGridInterpolator
from shapely.geometry import LineString

from box import edge_gap as eg
from box import geology_io as gio

GRID_DIR = Path("C:/Users/MichaelMast/Blue Ox Resources/Engineering - General/Structure Grids/Delaware")
# (top grid, base grid) per pool — BS2 sand: 2BS sand top -> 3BS carbonate top; WCA: WCA top -> WCB1 top
GRIDS = {
    "BS2_S": ("HCA_2BSPGS_STRUCTURE_MDXYZ_grid.xyz", "HCA_3BSPGC_STRUCTURE_MDXYZ_grid.xyz"),
    "WCA": ("HCA_WOLFCAMP_A_STRUCTURE_MDXYZ_grid.xyz", "WOLFCAMP-B1-STRUCTUREXYZ_grid.xyz"),
}
STRUCT_STEP_FT, ISO_STEP_FT = 250.0, 25.0
RULE_COLOURS = {
    "pinned: floor": "#15803d",
    "gap: k × gap": "#f97316",
    "gap: capped": "#b91c1c",
    "gap: pre-2016 beyond -> floor (D5)": "#6b7280",
    "live front -> cap (D22)": "#c026d3",
    "potash ignore-gap -> floor (D24)": "#0ea5e9",
    "hole: tightest floor": "#a16207",
    "uniform baseline": "#000000",
}

EXTENT_FIELDS = [("BENCH", "C", 12, 0), ("BASIN", "C", 12, 0), ("VERSION", "N", 4, 0), ("SOURCE", "C", 16, 0), ("AREA_SQMI", "N", 12, 2), ("BUILT", "C", 25, 0), ("PARAMS", "C", 254, 0)]
EDGE_FIELDS = [
    ("BENCH", "C", 12, 0), ("VERSION", "N", 4, 0), ("EDGE_NO", "N", 8, 0), ("SEG_NO", "N", 8, 0), ("EDGE_CLS", "C", 8, 0), ("SIDE", "C", 3, 0),
    ("GAP_FT", "N", 10, 0), ("PERF_CLS", "C", 8, 0), ("PERF_RAT", "N", 8, 3), ("BUFFER_FT", "N", 10, 0), ("RULE", "C", 60, 0), ("FLAG", "C", 254, 0),
]
LAT_FIELDS = [
    ("API10", "C", 10, 0), ("WELL_NAME", "C", 60, 0), ("OPERATOR", "C", 40, 0), ("FP_DATE", "C", 10, 0), ("TAG", "C", 10, 0), ("ROLE", "C", 52, 0),
    ("TVD_FT", "N", 8, 0), ("LAT_FT", "N", 8, 0), ("OIL12KFT", "N", 10, 0), ("PERF_RAT", "N", 8, 3), ("QC_NOTE", "C", 80, 0),
]
FLAG_FIELDS = [("BENCH", "C", 12, 0), ("KIND", "C", 24, 0), ("TEXT", "C", 254, 0), ("AREA_SQMI", "N", 10, 2), ("API10", "C", 10, 0)]
CTX_FIELDS = [("SURFACE", "C", 40, 0), ("KIND", "C", 10, 0), ("LEVEL_FT", "N", 8, 0)]


def _grid(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = np.loadtxt(path, delimiter=",")
    xs, ys = np.unique(np.round(a[:, 0], 1)), np.unique(np.round(a[:, 1], 1))
    Z = np.full((len(ys), len(xs)), np.nan)
    z = a[:, 2].copy()
    z[z > 1e9] = np.nan
    Z[np.searchsorted(ys, np.round(a[:, 1], 1)), np.searchsorted(xs, np.round(a[:, 0], 1))] = z
    return xs, ys, Z


def _contours(xs: np.ndarray, ys: np.ndarray, Z: np.ndarray, step: float, clip: Any) -> list[tuple[LineString, float]]:
    finite = Z[np.isfinite(Z)]
    if not len(finite):
        return []
    levels = np.arange(np.floor(finite.min() / step) * step, np.ceil(finite.max() / step) * step + step, step)
    fig, ax = plt.subplots()
    cs = ax.contour(xs, ys, np.ma.masked_invalid(Z), levels=levels)
    out = []
    for lev, segs in zip(cs.levels, cs.allsegs):
        for s in segs:
            if len(s) < 2:
                continue
            ln = LineString(s)
            if clip is not None:
                ln = ln.intersection(clip)
            for g in getattr(ln, "geoms", [ln]):
                if isinstance(g, LineString) and not g.is_empty and g.length > 0:
                    out.append((g, float(lev)))
    plt.close(fig)
    return out


def context_contours(pool: str, clip_usft: Any, grid_dir: Path = GRID_DIR) -> dict[str, list[tuple[LineString, float]]]:
    """Structure (top) and isopach (base − top) contours in the geology frame; {} if grids absent."""
    top_f, base_f = GRIDS[pool]
    if not (grid_dir / top_f).exists() or not (grid_dir / base_f).exists():
        return {}
    xs, ys, top = _grid(grid_dir / top_f)
    bx, by, base = _grid(grid_dir / base_f)
    X, Y = np.meshgrid(xs, ys)
    b_on_top = RegularGridInterpolator((by, bx), base, bounds_error=False, fill_value=np.nan)(np.column_stack([Y.ravel(), X.ravel()])).reshape(X.shape)
    iso = b_on_top - top
    iso[iso <= 0] = np.nan
    return {"struct": _contours(xs, ys, top, STRUCT_STEP_FT, clip_usft), "isopach": _contours(xs, ys, iso, ISO_STEP_FT, clip_usft)}


# ----------------------------------------------------------------------------
# Write the package
# ----------------------------------------------------------------------------


def lateral_roles(pr: Any) -> pd.DataFrame:
    """Every pool lateral with its role in the extent (for the laterals layer and the map)."""
    ev, old, so = pr.r["ev"].copy(), pr.r["old"].copy(), pr.stepouts
    ev["role"] = "evidence (>= 2016)"
    ev.loc[so["ix"].to_numpy(), "role"] = ["step-out " + r for r in so["role"]]
    old["role"] = "pre-2016 (negative evidence only)"
    d = pd.concat([ev, old], ignore_index=True)
    d["perf_ratio"] = d["oil12_kft"] / pr.interior_median
    return d


def write_pool(out: Path, pool: str, version: int, built: str, b: dict[str, Any], bp: Any, contours: dict[str, Any]) -> list[Path]:
    """Write one pool's shapefile set; returns the files written."""
    pr = b["prep"]
    files: list[Path] = []
    ext_g = gio.ft13_to_geology([b["extent"]])[0]
    params = f"k={bp.k:g} cap={bp.cap_ft:.0f} floor={bp.floor_ft:.0f} ref={bp.perf_ref} r=2640 c=3960"
    files += gio.write_layer(out / f"BOX_{pool}_extent_v{version}", "polygon", [ext_g],
                             EXTENT_FIELDS, [[pool, "delaware", version, "generated", b["stats"]["extent_sqmi"], built, params]])
    e = b["edges"]
    eg_geoms = gio.ft13_to_geology(list(e.geom.map(lambda g: g.simplify(20.0))))
    files += gio.write_layer(out / f"BOX_{pool}_edges_v{version}", "line", eg_geoms, EDGE_FIELDS,
                             [[pool, version, r.edge_no, r.seg_no, r.edge_class, r.side, r.gap_ft, r.perf_class, r.perf_ratio, r.buffer_ft, r.rule, r.flag] for r in e.itertuples()])
    lat = lateral_roles(pr)
    lat_geoms = gio.ft13_to_geology(list(lat.geom.map(lambda g: g.simplify(20.0))))
    from box.edge_gap_report import qc_caveat

    files += gio.write_layer(out / f"BOX_{pool}_laterals", "line", lat_geoms, LAT_FIELDS, [
        [r.api10, r.well_name, r.operator, str(r.first_production_date), r.formation_blueox, r.role, r.tvd_ft, r.lateral_length_ft, r.oil12_kft, r.perf_ratio, qc_caveat(pd.Series(r._asdict()))]
        for r in lat.itertuples()
    ])
    flags_g, flags_r = [], []
    for h in b["holes"].itertuples():
        flags_g.append(h.geom.representative_point())
        if h.filled_D26:
            txt = f"legacy drilled-up hole {h.area_sqmi:.1f} sq mi FILLED (D26): {h.n_pre2016} pre-2016 laterals cover {h.legacy_cover:.0%}; no room for a modern well"
            flags_r.append([pool, "hole filled (D26)", txt, h.area_sqmi, ""])
        else:
            txt = f"hole {h.area_sqmi:.1f} sq mi inside the drilled body ({h.sopa_share:.0%} in the potash area, {h.legacy_cover:.0%} legacy cover): geology hole, surface, or fill?"
            flags_r.append([pool, "hole", txt, h.area_sqmi, ""])
    so = pr.stepouts
    ev = pr.r["ev"]
    for s in so[so.role != "island"].itertuples():
        g = ev.geom.iat[int(s.ix)]
        flags_g.append(g.interpolate(0.5, normalized=True))
        pr_txt = "" if not np.isfinite(s.perf_ratio) else f", {s.perf_ratio:.2f}× interior"
        flags_r.append([pool, "step-out excluded", f"{s.role} ({s.side}, {s.dist_mi:.1f} mi out, first prod {s.first_production_date}{pr_txt})", None, s.api10])
    if flags_g:
        files += gio.write_layer(out / f"BOX_{pool}_flags", "point", gio.ft13_to_geology(flags_g), FLAG_FIELDS, flags_r)
    top, base = GRIDS[pool]
    for kind, items in contours.items():
        if items:
            files += gio.write_layer(out / f"BOX_{pool}_ctx_{kind}", "line", [g for g, _ in items], CTX_FIELDS,
                                     [[top if kind == "struct" else f"{base} - {top}", kind, lev] for _, lev in items])
    return files


def write_sopa(out: Path, sopa_ft13: Any) -> list[Path]:
    return gio.write_layer(out / "BOX_potash_SOPA", "polygon", gio.ft13_to_geology([sopa_ft13]),
                           [("NAME", "C", 60, 0), ("SOURCE", "C", 120, 0)],
                           [["Secretary's Potash Area (1986 order boundary)", "BLM Carlsbad FO CFO_POTASH_SOPA_1986; D24 ignore-gap polygon"]])


# ----------------------------------------------------------------------------
# Legend PNG
# ----------------------------------------------------------------------------


def legend_png(path: Path, pool: str, b: dict[str, Any], sopa: Any, bp: Any, version: int) -> None:
    pr = b["prep"]
    fig = plt.figure(figsize=(11, 13))
    ax = fig.add_axes((0.02, 0.22, 0.96, 0.74))
    for ln in pr.r["old"].geom:
        c = np.asarray(ln.coords)
        ax.plot(c[:, 0], c[:, 1], color="#9ca3af", lw=0.4, zorder=1)
    for ln in pr.r["ev"].geom:
        c = np.asarray(ln.coords)
        ax.plot(c[:, 0], c[:, 1], color="#1e3a8a", lw=0.2, zorder=2)
    if sopa is not None:
        for g in eg._as_multi(sopa).geoms:
            x, y = g.exterior.xy
            ax.fill(x, y, facecolor="none", edgecolor="#0ea5e9", hatch="//", lw=0.6, zorder=1)
    for g in b["extent"].geoms:
        x, y = g.exterior.xy
        ax.fill(x, y, color="#fde68a", alpha=0.35, lw=0, zorder=0)
    for r in b["edges"].itertuples():
        c = np.asarray(r.geom.coords)
        ax.plot(c[:, 0], c[:, 1], color=RULE_COLOURS.get(r.rule, "#000"), lw=1.6, zorder=4, solid_capstyle="butt")
    so = pr.stepouts
    for s in so.itertuples():
        c = np.asarray(pr.r["ev"].geom.iat[int(s.ix)].coords)
        ax.plot(c[:, 0], c[:, 1], color="#c026d3" if s.role == "island" else "#111827", lw=1.2, zorder=5)
    x0, y0, x1, y1 = b["extent"].bounds
    pad = 5 * eg.FT_PER_MI
    ax.set_xlim(x0 - pad, x1 + pad)
    ax.set_ylim(y0 - pad, y1 + pad)
    xr = ax.get_xlim()
    yr = ax.get_ylim()
    sb = 10 * eg.FT_PER_MI
    ax.plot([xr[1] - sb - 0.03 * (xr[1] - xr[0]), xr[1] - 0.03 * (xr[1] - xr[0])], [yr[0] + 0.03 * (yr[1] - yr[0])] * 2, color="k", lw=2)
    ax.text(xr[1] - sb / 2 - 0.03 * (xr[1] - xr[0]), yr[0] + 0.045 * (yr[1] - yr[0]), "10 mi", ha="center", fontsize=8)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    st = b["stats"]
    ax.set_title(f"BOX {pool} extent v{version} (generated) — {st['extent_sqmi']:,.0f} sq mi; drilled core {st['core_sqmi']:,.0f} sq mi", fontsize=12)
    used = sorted(set(b["edges"].rule))
    h = [Line2D([], [], color=RULE_COLOURS.get(u, "#000"), lw=3, label=u) for u in used]
    h += [Patch(facecolor="#fde68a", alpha=0.5, label="extent"), Patch(facecolor="none", edgecolor="#0ea5e9", hatch="//", label="BLM Secretary's Potash Area (D24)"),
          Line2D([], [], color="#1e3a8a", lw=1, label=">= 2016 lateral"), Line2D([], [], color="#9ca3af", lw=1, label="pre-2016 lateral"),
          Line2D([], [], color="#c026d3", lw=1.5, label="step-out island (in)"), Line2D([], [], color="#111827", lw=1.5, label="step-out excluded (flags layer)")]
    lax = fig.add_axes((0.02, 0.01, 0.5, 0.2))
    lax.axis("off")
    lax.legend(handles=h, loc="upper left", fontsize=8, frameon=False, ncol=1)
    tax = fig.add_axes((0.52, 0.01, 0.46, 0.2))
    tax.axis("off")
    txt = (
        "Edge colour = the clause that set the buffer there.\n"
        f"pinned: floor  — rolled {bp.floor_ft:,.0f} / unknown {1.5 * bp.floor_ft:,.0f} / strong {2 * bp.floor_ft:,.0f} ft\n"
        f"gap: k × gap × perf — k = {bp.k:g}; perf m = strong 1.0, unknown 0.75, rolled 0.5;\n    clipped to [floor, cap = {bp.cap_ft:,.0f} ft]\n"
        "pre-2016 beyond a gap -> floor (D5: tighten only)\n"
        f"live front -> cap ({', '.join(st['fronts']) or 'none'}; D22)\n"
        "inside the potash area -> floor (D24)\n"
        "holes -> tightest floor (flagged)\n"
        "perf class = edge wells' 12-mo oil/ft vs the pool interior median\n    (>= 0.85 strong, < 0.70 rolled)\n"
        "CRS: NAD83 / UTM 14N, US-survey ft (.prj written; coords projected)"
    )
    tax.text(0, 1, txt, va="top", fontsize=8, family="monospace")
    fig.savefig(path, dpi=110)
    plt.close(fig)


README = """BOX extents for geology review — {built}
================================================================

What this is
  Generated extents for the Blue Ox (BOX) basin-wide type curves, Delaware pilot benches:
  {pools}. One extent = where BOX will forecast reconciled Novi PUDs from PDP data.
  Plan of record: engineering_db docs/box_type_curves_plan.md (step 3).

CRS
  NAD83 / UTM zone 14N, US-survey feet (no standard EPSG; .prj written from the ESRI definition
  NAD_1983_UTM_Zone_14N_ftUS — false easting 1,640,416.667 usft, CM -99). Coordinates are
  already projected, same frame as the HCA_* GGX grids.

What to edit
  BOX_<bench>_extent_v{version}.shp — the ONLY layer you edit. Move, cut or add polygon area.
  Keep the BENCH attribute. Save as BOX_<bench>_extent_v{version}_edited.shp (all side files).
  If you add a note for a change, put it in a new text field NOTE (any length up to 254).

What to look at (not edited)
  BOX_<bench>_edges_v{version}  boundary pieces; RULE = what set the buffer, FLAG = the question:
      "pinned edge, strong wells"  the edge is drilled up to and the last wells are strong:
                                   performance does not explain why it stops — what does?
      "live front"                 performing step-outs ahead of the body (buffer at the cap)
      "potash"                     inside the BLM Secretary's Potash Area: a surface constraint,
                                   not geology — the gap is not widened, never treated as a dry hole
      "pre-2016 ... not followed up" old laterals beyond a gap: buffer held to the floor
  BOX_<bench>_flags             holes in the drilled body (geology hole, surface, or fill?), legacy
                                drilled-up holes already filled (D26: >= 90 % covered by pre-2016 wells), and
                                step-outs left out of the extent (rolled / isolated / too new)
  BOX_<bench>_laterals          every pool lateral: ROLE, TVD_FT (producers' TVD — the W-edge
                                depth question), OIL12KFT (12-mo oil, bbl per 1,000 ft), QC_NOTE
  BOX_<bench>_ctx_struct / _ctx_isopach   contours from your HCA grids (context only)
  BOX_potash_SOPA               the potash ignore-gap polygon (1986 order boundary)

Buffer rule (parameters in the extent PARAMS attribute)
{rule}

Return
  The *_edited shapefile set (zip is fine) to Michael. It is re-imported, diffed against this
  version, and stored as the version of record; regeneration later produces a diff, never an
  overwrite of your edits.
"""
