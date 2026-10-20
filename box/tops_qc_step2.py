"""Tops-vs-tag QC — step 2: classify, attribute (structure vs tag), map, and build the geologist package.

READ ONLY against the warehouse. Scores against the 10-19 grids (box.extent_package.GRID_DIR) with the step-1
geology rules applied (tops_qc.apply_geology_rules). Writes into docs/box/tops-qc-<date>/:
  step2.html                 index: class + attribution tables, edge sensitivity, surface offset summary, links
  step2_<TAG>.html           one Leaflet map per scored bench
  wells_step2.csv            per well: class, attribution, band, offset, x/y in UTM 14N US-ft
  ggx/tops_qc_wells.*        GGX points (geology frame)       ggx/tops_qc_offset.*  GGX offset cells (polygons)
  summary_step2.json
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import subprocess
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from shapely.geometry import LineString, box

from box import extent_package as pkg
from box import geology_io as gio
from box import tops_qc as tq
from box import tops_qc_report as rep
from box.edge_gap_report import _CSS, _table

ROOT = Path(__file__).resolve().parent.parent
CLASS_COLOURS = {"agree": "#16a34a", "edge": "#eab308", "shallow": "#2563eb", "deep": "#dc2626", "gross": "#111827",
                 "no_evidence": "#9ca3af", "masked": "#d1d5db", "unmeasured": "#d1d5db"}
ATTR_COLOURS = {"structure_suspect": "#7c3aed", "tag_suspect": "#f97316"}
STRUCT_STEP_FT = 500.0
EXCLUDED_TAGS = tuple(sorted(tq.NO_SURFACE_TAGS | {t for t, s in tq.TAG_TOP.items() if s in tq.SUSPECT_SURFACES}))


# ----------------------------------------------------------------------------
# Build the per-well frame
# ----------------------------------------------------------------------------


def build(conn: Any) -> tuple[pd.DataFrame, dict[str, tq.Grid]]:
    w, st = rep.pull(conn)
    s, m = rep.station_inputs(w, st)
    stack = tq.load_stack(pkg.GRID_DIR)
    res = {"survey": tq.well_summary(tq.station_frame(s, stack)), "midpoint": tq.well_summary(tq.station_frame(m, stack))}
    p = rep.primary(w, res)
    p.index = w["api10"].to_numpy()
    p = rep.apply_rules(w, p)
    W = w.set_index("api10")[["well_name", "operator", "county", "state_code", "formation_blueox", "box_bench",
                               "evidence", "tvd_source", "tvd_ft", "lat_tvd_p50_ft", "lat_tvd_range_ft",
                               "first_production_date", "mid_lon", "mid_lat"]].copy()
    W = W.join(p[["verdict", "verdict_raw", "pct_in_tag", "miss_p50", "ft_below_top_p50", "ft_above_base_p50",
                  "frac_p50", "top_p50", "base_p50", "dom_interval"]])
    W = W[W["formation_blueox"].isin(tq.TAG_TOP) & W["mid_lon"].notna()].copy()
    W["x"], W["y"] = rep._to_geology(W["mid_lon"].to_numpy(), W["mid_lat"].to_numpy())
    W["tag"] = W["formation_blueox"]
    W["miss"] = W["miss_p50"].astype(float)
    W["cls"] = [tq.classify(v, mi) if ev else ("no_evidence" if v in tq.SCORED_VERDICTS else v)
                for v, mi, ev in zip(W["verdict"], W["miss"], W["evidence"], strict=True)]
    W["witness"] = W["evidence"] & W["cls"].isin(tq.WITNESS_CLASSES)
    W["api10"] = W.index
    W = W.join(tq.attribute(W[["api10", "tag", "x", "y", "cls", "miss", "witness"]]))
    tops = W["tag"].map(tq.TAG_TOP)
    W["dist_to_control_top_ft"] = np.nan
    for srf in tops.unique():
        ids = W.index[tops == srf]
        W.loc[ids, "dist_to_control_top_ft"] = pkg.dist_to_control(srf, W.loc[ids, ["x", "y"]].to_numpy(float))
    return W, stack


def offset_fields(W: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per surface (not suspect, bounding at least one scored tag): the median-residual offset cells."""
    rf = W.rename(columns={"ft_below_top_p50": "ft_below_top", "ft_above_base_p50": "ft_above_base"})
    used = {tq.TAG_TOP[t] for t in tq.TAG_TOP} | {tq.tag_base(t) for t in tq.TAG_TOP}
    out = {}
    for srf in tq.STACK:
        if srf in tq.SUSPECT_SURFACES or srf not in used:
            continue
        r = tq.surface_residuals(rf, srf)
        out[srf] = tq.offset_field(r)
        out[srf].attrs["n_resid"] = len(r)
    return out


def flagged(f: pd.DataFrame) -> pd.DataFrame:
    return f[f["flagged"].astype(bool)] if len(f) else f


# ----------------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------------


def class_table(W: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tag in tq.TAG_TOP:
        g = W[W["tag"] == tag]
        if g.empty:
            continue
        sc = g[g["cls"].isin(["agree", "edge", "shallow", "deep", "gross"])]
        dis = g[g["cls"].isin(tq.DISAGREE)]
        r: dict[str, Any] = {"tag": tag, "interval": f"{tq.TAG_TOP[tag]} → {tq.tag_base(tag)}", "wells": len(g), "scored": len(sc)}
        for c in ("agree", "edge", "shallow", "deep", "gross"):
            r[c] = float((sc["cls"] == c).mean()) if len(sc) else np.nan
        for a in ("structure_suspect", "tag_suspect", "unresolved_mixed", "unresolved_sparse"):
            r[a] = int((dis["attribution"] == a).sum())
        st = dis[dis["attribution"] == "structure_suspect"]
        r["structure offset p50 (ft)"] = float(st["grid_offset_ft"].median()) if len(st) else np.nan
        for c in ("masked", "no_surface", "surface_suspect", "no_evidence"):
            r[c] = int((g["cls"] == c).sum())
        rows.append(r)
    return pd.DataFrame(rows)


def sensitivity_table(W: pd.DataFrame) -> pd.DataFrame:
    rows = []
    ev = W[W["evidence"] & W["verdict"].isin(tq.SCORED_VERDICTS)]
    for tag in tq.TAG_TOP:
        g = ev[ev["tag"] == tag]
        if g.empty:
            continue
        r: dict[str, Any] = {"tag": tag, "scored": len(g)}
        for t in tq.EDGE_SENSITIVITY:
            c = pd.Series([tq.classify(v, mi, edge_ft=t) for v, mi in zip(g["verdict"], g["miss"], strict=True)])
            r[f"agree+edge @{t:.0f} ft"] = float(c.isin(["agree", "edge"]).mean())
            r[f"disagree @{t:.0f} ft"] = float(c.isin(tq.DISAGREE).mean())
        rows.append(r)
    return pd.DataFrame(rows)


def offset_table(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    cell_sqmi = (tq.OFFSET_CELL_FT / 5280.0) ** 2
    rows = []
    for srf, allc in fields.items():
        f = flagged(allc)
        a = f["offset_ft"].abs() if len(f) else pd.Series(dtype=float)
        rows.append({"surface": srf, "residual wells": int(allc.attrs.get("n_resid", 0)),
                     "cells with ≥3 wells": len(allc),
                     "flagged cells": len(f), "flagged sq mi": len(f) * cell_sqmi,
                     "wants up (cells)": int((f["offset_ft"] < 0).sum()) if len(f) else 0,
                     "wants down (cells)": int((f["offset_ft"] > 0).sum()) if len(f) else 0,
                     "|offset| p50 (ft)": float(a.median()) if len(a) else np.nan,
                     "|offset| p90 (ft)": float(a.quantile(0.9)) if len(a) else np.nan,
                     "conflict cells (≥2 each way)": int(((allc["n_up"] >= 2) & (allc["n_down"] >= 2)).sum()) if len(allc) else 0})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Map data (lon/lat)
# ----------------------------------------------------------------------------


def _ll(pts: np.ndarray) -> np.ndarray:
    tr = gio._tr(gio.GEOLOGY_CRS, "EPSG:4269")
    x, y = tr.transform(pts[:, 0], pts[:, 1])
    return np.column_stack([x, y])


def cells_ll(f: pd.DataFrame, cell_ft: float = tq.OFFSET_CELL_FT) -> list[dict[str, Any]]:
    if f.empty:
        return []
    h = cell_ft / 2
    out = []
    corners = np.array([[-h, -h], [h, -h], [h, h], [-h, h]])
    for r in f.itertuples(index=False):
        ring = _ll(corners + [r.cx, r.cy])
        out.append({"c": np.round(ring[:, ::-1], 5).tolist(), "v": round(float(r.offset_ft)), "n": int(r.n),
                    "u": int(r.n_up), "d": int(r.n_down)})
    return out


def contours_ll(g: tq.Grid, clip: Any, step: float = STRUCT_STEP_FT) -> list[dict[str, Any]]:
    out = []
    for ln, lev in pkg._contours(g.xs, g.ys, g.z, step, clip):
        s = ln.simplify(150.0)
        out.append({"c": np.round(_ll(np.asarray(s.coords))[:, ::-1], 5).tolist(), "z": int(lev)})
    return out


def dist_line_ll(surface: str, clip: Any, level: float = pkg.TRUST_MAX_FT) -> list[list[list[float]]]:
    path = pkg.grid_path(surface, kind="dist_to_control")
    if path is None:
        return []
    xs, ys, D = pkg._grid(path)
    fig, ax = plt.subplots()
    cs = ax.contour(xs, ys, np.ma.masked_invalid(D), levels=[level])
    segs = cs.allsegs[0]
    plt.close(fig)
    out = []
    for sg in segs:
        if len(sg) < 2:
            continue
        ln = LineString(sg).intersection(clip)
        for part in getattr(ln, "geoms", [ln]):
            if isinstance(part, LineString) and not part.is_empty:
                out.append(np.round(_ll(np.asarray(part.simplify(150.0).coords))[:, ::-1], 5).tolist())
    return out


def _f(v: Any, nd: int = 0) -> Any:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(x) else round(x, nd)


def wells_ll(g: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for api, r in g.iterrows():
        out.append({"a": api, "ll": [round(float(r["mid_lat"]), 5), round(float(r["mid_lon"]), 5)], "k": r["cls"],
                    "at": r["attribution"] if isinstance(r["attribution"], str) else None,
                    "nm": str(r["well_name"])[:40], "op": str(r["operator"])[:30], "src": r["tvd_source"],
                    "tvd": _f(r["lat_tvd_p50_ft"] if r["tvd_source"] == "survey" else r["tvd_ft"]),
                    "rng": _f(r["lat_tvd_range_ft"]), "m": _f(r["miss"]), "pin": _f(r["pct_in_tag"], 2),
                    "bt": _f(r["ft_below_top_p50"]), "fr": _f(r["frac_p50"], 2), "dom": r["dom_interval"],
                    "bn": int(r["band_n"]) if pd.notna(r["band_n"]) else 0, "bm": _f(r["band_miss"]),
                    "dc": _f(r["dist_to_control_top_ft"]), "bb": r["box_bench"] if isinstance(r["box_bench"], str) else None})
    return out


# ----------------------------------------------------------------------------
# Render
# ----------------------------------------------------------------------------

_MAP_JS = """
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D = __DATA__;
const map = L.map('map', {preferCanvas: true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {maxZoom: 16, attribution: 'Tiles &copy; Esri'}).addTo(map);
const esc = s => String(s ?? '').replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
const f = v => (v === null || v === undefined) ? '–' : v.toLocaleString();
const CC = D.cls_col, AC = D.attr_col;
const offCol = v => { const a = Math.abs(v); const up = v < 0;
  const ramp = up ? ['#dbeafe','#93c5fd','#3b82f6','#1e3a8a'] : ['#fee2e2','#fca5a5','#ef4444','#7f1d1d'];
  return ramp[a <= 50 ? 0 : a <= 100 ? 1 : a <= 200 ? 2 : 3]; };
const cellLayer = (cells, srf) => L.layerGroup(cells.map(c => L.polygon(c.c, {stroke: false, fillColor: offCol(c.v), fillOpacity: 0.55})
  .bindPopup(`<b>${srf}</b> wants to move <b>${c.v < 0 ? 'UP' : 'DOWN'} ~${Math.abs(c.v)} ft</b> here<br>median of ${c.n} wells within 1.5 mi · pulling up ${c.u} / down ${c.d}`)));
const topCells = cellLayer(D.cells_top, D.top).addTo(map);
const baseCells = cellLayer(D.cells_base, D.base);
const cont = L.layerGroup(D.contours.map(c => L.polyline(c.c, {color: '#6b7280', weight: 0.7, opacity: 0.8}).bindTooltip(`${D.top} ${c.z.toLocaleString()} ft`, {sticky: true}))).addTo(map);
const dist = L.layerGroup(D.dist.map(c => L.polyline(c, {color: '#a16207', weight: 1.2, dashArray: '4 3', interactive: false}))).addTo(map);
const pop = w => `<b>${esc(w.nm)}</b><br>api10 ${w.a} · ${esc(w.op)}<br>tag <b>${D.tag}</b>${w.bb ? ' · box_bench ' + w.bb : ''} · class <b>${w.k}</b>${w.at ? ' · <b>' + w.at.replace('_', ' ') + '</b>' : ''}` +
  `<br>${w.src === 'survey' ? 'survey lateral p50' : 'tvd_ft'} ${f(w.tvd)} ft${w.rng !== null ? ' · lateral TVD range ' + f(w.rng) + ' ft' : ''}` +
  `<br>${f(w.bt)} ft below ${D.top} · frac ${f(w.fr)} · ${w.pin !== null ? Math.round(w.pin * 100) + '% of lateral in tag interval' : ''}` +
  `<br>miss ${f(w.m)} ft · dominant interval ${esc(w.dom)}<br>same-tag band: ${w.bn} wells, median miss ${f(w.bm)} ft · dist to ${D.top} control ${f(w.dc)} ft`;
const groups = {};
for (const k of D.order) groups[k] = L.layerGroup();
for (const w of D.wells) {
  const ring = w.at ? AC[w.at] : null;
  L.circleMarker(w.ll, {radius: w.k === 'agree' ? 3 : 4.5, color: ring || CC[w.k], weight: ring ? 2.5 : 1,
    fillColor: CC[w.k], fillOpacity: (w.k === 'no_evidence' || w.k === 'masked') ? 0.15 : 0.85}).bindPopup(pop(w)).addTo(groups[w.k] || (groups[w.k] = L.layerGroup()));
}
const overlays = {};
overlays[`${D.top} offset cells (blue = up, red = down)`] = topCells;
overlays[`${D.base} offset cells`] = baseCells;
overlays[`${D.top} structure, ${D.step} ft`] = cont;
overlays[`${D.top} 1-mi-from-control line`] = dist;
for (const k of Object.keys(groups)) { overlays[`wells: ${k} (${D.counts[k] || 0})`] = groups[k]; if (k !== 'masked') groups[k].addTo(map); }
L.control.layers(null, overlays, {collapsed: false}).addTo(map);
const vis = D.wells.filter(w => w.k !== 'masked');
const b = L.latLngBounds((vis.length ? vis : D.wells).map(w => w.ll)).pad(0.02);
map.fitBounds(b);
window.addEventListener('load', () => { map.invalidateSize(); map.fitBounds(b); });
</script>
"""


def _legend() -> str:
    cls = "".join(f"<span style='background:{c}'></span>{k}" for k, c in CLASS_COLOURS.items() if k != "unmeasured")
    att = "".join(f"<span style='background:{c}'></span>{k.replace('_', ' ')} (ring)" for k, c in ATTR_COLOURS.items())
    return f"<div class=lg>{cls}</div><div class=lg>{att}</div>"


def tag_page(tag: str, W: pd.DataFrame, stack: dict[str, tq.Grid], fields: dict[str, pd.DataFrame], meta: str) -> str:
    g = W[W["tag"] == tag]
    top, base = tq.TAG_TOP[tag], tq.tag_base(tag)
    clip = box(*np.r_[g[["x", "y"]].min().to_numpy() - 26_400, g[["x", "y"]].max().to_numpy() + 26_400])
    order = ["structure", "agree", "edge", "shallow", "deep", "gross", "no_evidence", "masked"]
    data = {"tag": tag, "top": top, "base": base, "cls_col": CLASS_COLOURS, "attr_col": ATTR_COLOURS,
            "order": [k for k in order if k in set(g["cls"])], "counts": g["cls"].value_counts().to_dict(),
            "wells": wells_ll(g), "cells_top": cells_ll(flagged(fields.get(top, pd.DataFrame()))),
            "cells_base": cells_ll(flagged(fields.get(base, pd.DataFrame()))) if base not in tq.SUSPECT_SURFACES else [],
            "contours": contours_ll(stack[top], clip), "dist": dist_line_ll(top, clip), "step": int(STRUCT_STEP_FT)}
    c = class_table(W[W["tag"] == tag]).drop(columns=["interval"])
    pct = ["agree", "edge", "shallow", "deep", "gross"]
    for k in pct:
        c[k] = (c[k] * 100).round(1)
    js = _MAP_JS.replace("__DATA__", json.dumps(data, default=str).replace("</", "<\\/"))
    caveat = (f"<div class=flag>Pecos: {base if base in tq.MASKED_SURFACES_BY_COUNTY['Pecos'] else top} is masked there "
              "(zero picks) — those wells are grey and hidden by default.</div>"
              if (top in tq.MASKED_SURFACES_BY_COUNTY["Pecos"] or base in tq.MASKED_SURFACES_BY_COUNTY["Pecos"]) else "")
    return "\n".join([
        f"<meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'><title>Tops vs Tags · {tag}</title><style>{_CSS}</style>",
        f"<h1>{tag} — {top} → {base}</h1>", meta,
        ("<p><a href='step2.html'>← index</a> · Points = lateral midpoints coloured by class "
        f"(edge = within {tq.EDGE_FT:.0f} ft of a surface). Rings = attribution of shallow / deep wells against their "
        "same-tag band (≥ 3 clean wells within 1.5 mi): <b>purple = structure suspect</b> (the local cluster sits "
        "outside the interval too — surface, or a local naming convention), <b>orange = tag suspect</b> (neighbours "
        "agree; this well is the outlier). Cells = median residual of all wells bounding the surface "
        "(both sides) on half-mile cells, shown where it exceeds the edge tolerance: blue = surface wants to come UP, "
        "red = DOWN (ft). Dashed brown = 1 mi from the nearest pick for "
        f"{top} (outside it the grid is interpolating).</p>"),
        caveat, _legend(), "<div id=map></div>",
        _table(c, {"structure offset p50 (ft)": ".0f"}), js,
    ])


def index_page(W: pd.DataFrame, cls_t: pd.DataFrame, sens: pd.DataFrame, off: pd.DataFrame, meta: str) -> str:
    c = cls_t.copy()
    for k in ("agree", "edge", "shallow", "deep", "gross"):
        c[k] = (c[k] * 100).round(1)
    c["tag"] = [f"<a href='step2_{t}.html'>{t}</a>" if t not in EXCLUDED_TAGS else t for t in c["tag"]]
    s = sens.copy()
    for col in s.columns[2:]:
        s[col] = (s[col] * 100).round(1)
    table = _table(c, {"structure offset p50 (ft)": ".0f"}).replace("&lt;a href=", "<a href=").replace("&#x27;", "'").replace("&gt;", ">").replace("&lt;/a>", "</a>")
    return "\n".join([
        f"<meta charset=utf-8><meta name=viewport content='width=device-width, initial-scale=1'><title>Tops vs Tags · Step 2</title><style>{_CSS}</style>",
        "<h1>Tops vs tags — step 2: where the tag or the structure is wrong</h1>", meta,
        ("<p>10-19 grids, step-1 geology rules applied. Shares are over scored evidence wells; edge = a shallow / deep "
        f"call within {tq.EDGE_FT:.0f} ft of a surface (not a disagreement). Attribution counts are wells; "
        "structure offset p50 = median band miss of structure-suspect wells (− the surface should come up, + go down). "
        f"Excluded (no page): {', '.join(EXCLUDED_TAGS)} — suspect C / D surfaces and the missing Middle Avalon surface.</p>"),
        "<h2>1 · Class and attribution by bench (links = maps)</h2>", table,
        "<h2>2 · Edge tolerance sensitivity</h2>",
        ("<p>How much of the disagreement is within a few feet of a surface — the BS3_S/WCA_1-at-the-interface and "
        "WCB_1-just-below-the-top cases. Not a decision; step 3's landing histograms inform where the line goes.</p>"),
        _table(s),
        "<h2>3 · Where each surface wants to move (offset cells)</h2>",
        ("<p>Per surface: half-mile cells where the median residual of the wells bounding it exceeds the edge "
        "tolerance. Conflict cells have ≥ 2 wells pulling each way — the surface is probably fine there and the tags "
        "disagree with each other.</p>"),
        _table(off, {"flagged sq mi": ".1f", "|offset| p50 (ft)": ".0f", "|offset| p90 (ft)": ".0f"}),
        ("<div class=meta>Files: wells_step2.csv (per well, UTM 14N US-ft x/y), ggx/tops_qc_wells.shp + "
        "ggx/tops_qc_offset.shp (NAD83 UTM 14N US-ft, for GGX).</div>"),
    ])


GGX_WELL_FIELDS = [("API10", "C", 10, 0), ("TAG", "C", 8, 0), ("BOXBENCH", "C", 8, 0), ("CLASS", "C", 16, 0),
                   ("ATTRIB", "C", 20, 0), ("MISS_FT", "N", 8, 0), ("BANDMISS", "N", 8, 0), ("BAND_N", "N", 4, 0),
                   ("TVD_FT", "N", 8, 0), ("TVD_SRC", "C", 8, 0), ("PCT_IN", "N", 6, 2), ("FT_BLWTOP", "N", 8, 0),
                   ("DIST_CTL", "N", 9, 0), ("WELLNAME", "C", 40, 0), ("OPERATOR", "C", 30, 0)]
GGX_CELL_FIELDS = [("SURFACE", "C", 16, 0), ("OFFSET_FT", "N", 8, 0), ("N", "N", 5, 0), ("N_UP", "N", 5, 0), ("N_DOWN", "N", 5, 0)]


def write_ggx(out: Path, W: pd.DataFrame, fields: dict[str, pd.DataFrame]) -> list[Path]:
    from shapely.geometry import Point

    d = out / "ggx"
    g = W[W["cls"] != "unmeasured"]
    recs = [[api, r["tag"], r["box_bench"] if isinstance(r["box_bench"], str) else "", r["cls"],
             r["attribution"] if isinstance(r["attribution"], str) else "", _f(r["miss"]), _f(r["band_miss"]),
             int(r["band_n"]) if pd.notna(r["band_n"]) else 0,
             _f(r["lat_tvd_p50_ft"] if r["tvd_source"] == "survey" else r["tvd_ft"]), r["tvd_source"],
             _f(r["pct_in_tag"], 2), _f(r["ft_below_top_p50"]), _f(r["dist_to_control_top_ft"]),
             str(r["well_name"]), str(r["operator"])] for api, r in g.iterrows()]
    paths = gio.write_layer(d / "tops_qc_wells", "point", [Point(x, y) for x, y in zip(g["x"], g["y"], strict=True)],
                            GGX_WELL_FIELDS, recs)
    h = tq.OFFSET_CELL_FT / 2
    geoms, crecs = [], []
    for srf, f in fields.items():
        for r in flagged(f).itertuples(index=False):
            geoms.append(box(r.cx - h, r.cy - h, r.cx + h, r.cy + h))
            crecs.append([srf, round(float(r.offset_ft)), int(r.n), int(r.n_up), int(r.n_down)])
    paths += gio.write_layer(d / "tops_qc_offset", "polygon", geoms, GGX_CELL_FIELDS, crecs)
    return paths


CSV_COLS = ["well_name", "operator", "county", "state_code", "tag", "box_bench", "evidence", "tvd_source", "tvd_ft",
            "lat_tvd_p50_ft", "lat_tvd_range_ft", "first_production_date", "verdict_raw", "verdict", "cls",
            "attribution", "band_n", "band_miss", "grid_offset_ft", "miss", "pct_in_tag", "ft_below_top_p50",
            "ft_above_base_p50", "frac_p50", "top_p50", "base_p50", "dom_interval", "dist_to_control_top_ft",
            "mid_lon", "mid_lat", "x", "y"]


def run(conn: Any, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    W, stack = build(conn)
    fields = offset_fields(W)
    built = _dt.datetime.now(tz=_dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=False).stdout.strip()
    meta = (f"<div class=meta>built {built} · git {html.escape(sha)} · grids {html.escape(str(pkg.GRID_DIR))} · "
            f"edge {tq.EDGE_FT:.0f} ft · gross > {tq.GROSS_FT:.0f} ft · band radius 1.5 mi, ≥ {tq.BAND_MIN_N} wells · READ ONLY</div>")
    cls_t, sens, off = class_table(W), sensitivity_table(W), offset_table(fields)
    (out / "step2.html").write_text(index_page(W, cls_t, sens, off, meta), encoding="utf-8")
    for tag in tq.TAG_TOP:
        if tag in EXCLUDED_TAGS or not (W["tag"] == tag).any():
            continue
        (out / f"step2_{tag}.html").write_text(tag_page(tag, W, stack, fields, meta), encoding="utf-8")
    W[CSV_COLS].rename(columns={"x": "x_utm14_usft", "y": "y_utm14_usft"}).to_csv(out / "wells_step2.csv", index_label="api10")
    write_ggx(out, W, fields)
    summary = {"built": built, "git": sha, "grid_dir": str(pkg.GRID_DIR), "edge_ft": tq.EDGE_FT, "gross_ft": tq.GROSS_FT,
               "band_radius_ft": tq.BAND_RADIUS_FT, "band_min_n": tq.BAND_MIN_N, "excluded_tags": list(EXCLUDED_TAGS),
               "classes": cls_t.to_dict(orient="records"), "sensitivity": sens.to_dict(orient="records"),
               "offsets": off.to_dict(orient="records")}
    (out / "summary_step2.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    return {"classes": cls_t, "sensitivity": sens, "offsets": off, "W": W}
