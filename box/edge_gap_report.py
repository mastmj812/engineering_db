"""BOX step 2 — edge-gap review pages (read-only; box/edge_gap.py holds the pure metric).

Reads the gate-1 final well sets (docs/box/step1-*/wells_final_<pool>.csv), pulls each well's
lateral line from the warehouse inside a READ ONLY transaction, runs the alpha sweep, tunes the
closing radius on WCA (one value for the Delaware), walks both pool outlines, and writes per pool:
an HTML review page (interactive map + static overview + tables), segments / pinning-wells /
step-outs / holes CSVs, the outline + segments as GeoJSON (EPSG:4326), plus index.html and
summary.json. Nothing is written to the warehouse.
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import io
import json
import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Polygon, mapping

from box import edge_gap as eg

POOLS: tuple[str, ...] = ("WCA", "BS2_S")
TUNE_POOL = "WCA"  # plan §5 step 2: alpha per basin, tuned on WCA
SWEEP_R_MI = (0.25, 0.5, 0.75)
SWEEP_C_MI = (0.5, 0.75, 1.0, 1.5, 2.0)
GAP_COLOURS = ("#a3e635", "#facc15", "#fb923c", "#ef4444", "#7f1d1d")  # by eg.GAP_LABELS
PINNED_COLOUR = "#15803d"
PERF_COLOURS = {"strong": "#2563eb", "unknown": "#9ca3af", "rolled": "#be123c"}
MOOT_REASONS = ("in-pool swap", "flag into WCXY")  # D19 / D20: flags that change nothing in an extent

# Lateral geometry, best source first: Enverus survey LateralLine (sql/39), the Novi LP->BHL chord,
# the sql/04 wellstick (SHL->LP->MP->BHL).
_SQL = """
SELECT w.api10,
       CASE WHEN ell.lateral_geom IS NOT NULL THEN 'enverus_lateralline'
            WHEN w.landing_point_lat IS NOT NULL AND w.bhl_lat IS NOT NULL
                 AND (w.landing_point_lat, w.landing_point_lon) IS DISTINCT FROM (w.bhl_lat, w.bhl_lon)
                 THEN 'novi_lp_bhl'
            WHEN w.wellstick_geom IS NOT NULL THEN 'wellstick' END                      AS geom_src,
       ST_AsText(COALESCE(
           ell.lateral_geom,
           CASE WHEN w.landing_point_lat IS NOT NULL AND w.bhl_lat IS NOT NULL
                     AND (w.landing_point_lat, w.landing_point_lon) IS DISTINCT FROM (w.bhl_lat, w.bhl_lon)
                THEN ST_SetSRID(ST_MakeLine(ST_Point(w.landing_point_lon, w.landing_point_lat),
                                            ST_Point(w.bhl_lon, w.bhl_lat)), 4326) END,
           w.wellstick_geom))                                                            AS wkt
FROM curated.wells_enriched w
LEFT JOIN curated.enverus_lateral_lines ell ON ell.api10 = w.api10
WHERE w.api10 = ANY(%(api10s)s)
"""


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------


def load_final_sets(wells_dir: Path, pools: tuple[str, ...] = POOLS) -> pd.DataFrame:
    frames = []
    for pool in pools:
        d = pd.read_csv(wells_dir / f"wells_final_{pool}.csv", dtype={"api10": str})
        d["pool"] = pool
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["first_production_date"] = pd.to_datetime(df["first_production_date"]).dt.date
    for c in ("planned", "tvd_round", "cohort"):
        df[c] = df[c].astype(str).str.lower().eq("true")
    return df


def pull_laterals(conn: Any, api10s: list[str]) -> pd.DataFrame:
    """api10 -> lateral WKT (4326) + source. READ ONLY."""
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_SQL, {"api10s": api10s})
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=["api10", "geom_src", "wkt"])


def attach_geometry(df: pd.DataFrame, geo: pd.DataFrame) -> pd.DataFrame:
    d = df.merge(geo, on="api10", how="left")
    ok = d["wkt"].notna()
    d["geom"] = None
    d.loc[ok, "geom"] = pd.Series(eg.to_ft(list(shapely.from_wkt(d.loc[ok, "wkt"]))), index=d.index[ok])
    d["evidence"] = [fp >= eg.EVIDENCE_FP_MIN for fp in d["first_production_date"]]
    return d


def qc_caveat(r: pd.Series) -> str:
    """Why an edge-pinning well deserves individual eyes at gate 2 ('' = clean)."""
    out = []
    if r.get("box_action") == "reassign":
        out.append(f"reassigned in from {r.get('formation_blueox')}")
    if r.get("box_action") == "tvd_suspect":
        out.append("TVD suspect (A-prime)")
    if bool(r.get("planned")):
        out.append("planned survey")
    if bool(r.get("tvd_round")):
        out.append("permit-round TVD")
    reason = str(r.get("box_reason") or "")
    if r.get("cons_status") == "flag" and r.get("box_action") == "keep" and not reason.startswith(MOOT_REASONS):
        out.append(f"flag kept: {reason}")
    return "; ".join(out)


# ----------------------------------------------------------------------------
# One pool
# ----------------------------------------------------------------------------


def analyse_pool(d: pd.DataFrame, p: eg.EdgeParams) -> dict[str, Any]:
    ev = d[d["evidence"] & d["geom"].notna()].reset_index(drop=True)
    old = d[~d["evidence"] & d["geom"].notna()].reset_index(drop=True)
    lines = list(ev["geom"])
    o = eg.outline(lines, p)
    comps = eg.components(o, lines, p)
    body = o.geoms[int(comps.comp.iloc[0])]
    oil = ev["oil12_kft"].to_numpy(float)
    coh = ev["cohort"].to_numpy(bool) & np.isfinite(oil)
    im = eg.interior_mask(body, lines, p)
    interior_median = float(np.median(oil[im & coh]))
    seg = eg.walk(body, lines, p)
    seg = eg.attach_edge_evidence(seg, lines, oil, coh, interior_median, list(old["geom"]), body, p)
    for k in ("a", "b"):
        seg[f"api10_{k}"] = [ev["api10"].iat[i] if i >= 0 else None for i in seg[f"well_{k}"]]
        seg[f"name_{k}"] = [ev["well_name"].iat[i] if i >= 0 else None for i in seg[f"well_{k}"]]
    seg["gap_class"] = [eg.gap_class(x) if k == "gap" else "pinned" for k, x in zip(seg.kind, seg.length_ft)]
    so = eg.stepouts(body, lines)
    so = so.join(ev[["api10", "well_name", "operator", "county", "first_production_date", "oil12_kft", "cohort", "formation_blueox"]], on="ix")
    so["perf_ratio"] = so["oil12_kft"] / interior_median
    sides = eg.side_table(seg, so)
    sides["stepout_vintage_median"] = [
        float(np.median([x.year for x in so.loc[so.side == s, "first_production_date"]])) if (so.side == s).any() else np.nan for s in sides.index
    ]
    sides["stepout_perf_median"] = [float(so.loc[(so.side == s) & so.cohort, "perf_ratio"].median()) if ((so.side == s) & so.cohort).any() else np.nan for s in sides.index]
    sides["edge_perf_median"] = [float(seg.loc[(seg.side == s), "perf_ratio"].median()) for s in sides.index]
    # pinning wells: one row per lateral that pins the outline
    pin = seg[seg.kind == "pinned"].groupby("well_a").agg(pinned_ft=("length_ft", "sum"), sides=("side", lambda x: "/".join(sorted(set(x), key=eg.SECTORS.index))))
    pw = ev.loc[pin.index].assign(pinned_ft=pin.pinned_ft.to_numpy(), sides=pin.sides.to_numpy())
    pw["qc_caveat"] = pw.apply(qc_caveat, axis=1)
    pw["perf_ratio"] = pw["oil12_kft"] / interior_median
    # holes of the main body (listed, never walked)
    old_tree = shapely.STRtree(np.asarray(list(old["geom"]), dtype=object)) if len(old) else None
    holes = []
    for h in body.interiors:
        hp = Polygon(h)
        c = eg.to_lonlat([hp.centroid])[0]
        holes.append(
            {
                "area_sqmi": hp.area / eg.FT_PER_MI**2,
                "lon": c.x,
                "lat": c.y,
                "n_pre2016_inside": len(old_tree.query(hp, predicate="intersects")) if old_tree is not None else 0,
            }
        )
    holes_df = pd.DataFrame(holes, columns=["area_sqmi", "lon", "lat", "n_pre2016_inside"]).sort_values("area_sqmi", ascending=False)
    stats = eg.gap_stats(seg)
    stats.update(
        n_evidence=len(ev),
        n_pre2016=len(old),
        n_components=len(comps),
        n_bodies=int(comps.body.sum()),
        main_share=float(comps.n_laterals.iloc[0]) / len(ev),
        main_area_sqmi=body.area / eg.FT_PER_MI**2,
        n_holes=len(holes_df),
        holes_sqmi=float(holes_df.area_sqmi.sum()) if len(holes_df) else 0.0,
        interior_median_oil12_kft=interior_median,
        n_interior_cohort=int((im & coh).sum()),
        n_edge_cohort_any=int(coh.sum()),
        n_stepouts=len(so),
        n_pinning_caveat=int((pw.qc_caveat != "").sum()),
        geom_src=ev["geom_src"].value_counts().to_dict(),
        perf_mi={f"{k}|{c}": float(v) / eg.FT_PER_MI for (k, c), v in seg.groupby(["kind", "perf_class"]).length_ft.sum().items()},
    )
    return {"ev": ev, "old": old, "outline": o, "comps": comps, "body": body, "seg": seg, "stepouts": so, "sides": sides, "pinning": pw, "holes": holes_df, "stats": stats}


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------


def _png(fig: Any, dpi: int = 80) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _seg_colour(kind: str, gap_class: str) -> str:
    return PINNED_COLOUR if kind == "pinned" else GAP_COLOURS[eg.GAP_LABELS.index(gap_class)]


def overview_png(r: dict[str, Any], pool: str, title: str) -> str:
    fig, ax = plt.subplots(figsize=(10, 11))
    for ln in r["old"]["geom"]:
        c = np.asarray(ln.coords)
        ax.plot(c[:, 0], c[:, 1], color="#9ca3af", lw=0.5, zorder=1)
    for ln in r["ev"]["geom"]:
        c = np.asarray(ln.coords)
        ax.plot(c[:, 0], c[:, 1], color="#1e3a8a", lw=0.25, zorder=2)
    for g in r["outline"].geoms:
        x, y = g.exterior.xy
        ax.plot(x, y, color="#6b7280", lw=0.6, zorder=3)
        for h in g.interiors:
            x, y = h.xy
            ax.plot(x, y, color="#6b7280", lw=0.6, ls=":", zorder=3)
    for _, s in r["seg"].iterrows():
        c = np.asarray(s.geom.coords)
        ax.plot(c[:, 0], c[:, 1], color=_seg_colour(s.kind, s.gap_class), lw=1.4 if s.kind == "pinned" else 2.6, zorder=4, solid_capstyle="butt")
    so = r["stepouts"]
    if len(so):
        for ln in r["ev"]["geom"].iloc[so.ix]:
            c = np.asarray(ln.coords)
            ax.plot(c[:, 0], c[:, 1], color="#c026d3", lw=1.4, zorder=5)
    handles = [plt.Line2D([], [], color=PINNED_COLOUR, lw=2, label="pinned")]
    handles += [plt.Line2D([], [], color=c, lw=3, label=f"gap {lab}") for c, lab in zip(GAP_COLOURS, eg.GAP_LABELS)]
    handles += [
        plt.Line2D([], [], color="#1e3a8a", lw=1, label=">= 2016 lateral (evidence)"),
        plt.Line2D([], [], color="#9ca3af", lw=1, label="pre-2016 lateral (negative evidence only)"),
        plt.Line2D([], [], color="#c026d3", lw=1.5, label="step-out (outside main body)"),
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.9)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=11)
    sb = 10 * eg.FT_PER_MI
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    ax.plot([x1 - sb - 0.03 * (x1 - x0), x1 - 0.03 * (x1 - x0)], [y0 + 0.03 * (y1 - y0)] * 2, color="k", lw=2)
    ax.text(x1 - sb / 2 - 0.03 * (x1 - x0), y0 + 0.045 * (y1 - y0), "10 mi", ha="center", fontsize=8)
    return _png(fig)


def gap_hist_png(results: dict[str, dict[str, Any]]) -> str:
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.4), sharey=False)
    bins = np.arange(0, 12_001, 500)
    for ax, (pool, r) in zip(axs, results.items()):
        g = r["seg"].loc[r["seg"].kind == "gap", "length_ft"].clip(upper=11_999)
        ax.hist(g, bins=bins, color="#f97316", edgecolor="white")
        st = r["stats"]
        ax.axvline(st["gap_median_ft"], color="k", lw=1)
        ax.axvline(st["gap_p90_ft"], color="k", lw=1, ls="--")
        ax.set_title(f"{pool}: n = {len(g)} gaps (median solid, p90 dashed)", fontsize=10)
        ax.set_xlabel("gap length along the outline, ft")
        ax.set_ylabel("gaps")
    fig.tight_layout()
    return _png(fig)


def side_png(results: dict[str, dict[str, Any]]) -> str:
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.6))
    x = np.arange(len(eg.SECTORS))
    for ax, (pool, r) in zip(axs, results.items()):
        s = r["sides"].reindex(list(eg.SECTORS))
        ax.bar(x - 0.2, s["share_gap_gt_1_mi"] * 100, 0.4, color="#ef4444", label="% of side's perimeter in gaps > 1 mi")
        ax2 = ax.twinx()
        so = s["stepouts_le5mi"] + s["stepouts_5_20mi"] + s["stepouts_gt20mi"]
        ax2.bar(x + 0.2, so, 0.4, color="#c026d3", label="step-outs beyond the body (n laterals)")
        ax.set_xticks(x, list(eg.SECTORS))
        ax.set_ylabel("% perimeter in gaps > 1 mi")
        ax2.set_ylabel("step-outs (n)")
        ax.set_title(f"{pool}: by side of the body (bearing from centroid)", fontsize=10)
        ax.set_ylim(0, max(40, float(np.nanmax(s["share_gap_gt_1_mi"] * 100)) + 5))
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left")
    fig.tight_layout()
    return _png(fig)


def sweep_png(lines_by_c: dict[float, Any], ev_lines: list[Any], pool: str) -> str:
    n = len(lines_by_c)
    fig, axs = plt.subplots(1, n, figsize=(4.2 * n, 5))
    for ax, (c_mi, o) in zip(np.atleast_1d(axs), lines_by_c.items()):
        for ln in ev_lines:
            q = np.asarray(ln.coords)
            ax.plot(q[:, 0], q[:, 1], color="#1e3a8a", lw=0.15)
        for g in o.geoms:
            x, y = g.exterior.xy
            ax.fill(x, y, color="#bfdbfe", alpha=0.6, lw=0)
            ax.plot(x, y, color="#1d4ed8", lw=0.6)
            for h in g.interiors:
                x, y = h.xy
                ax.plot(x, y, color="#dc2626", lw=0.6)
        ax.set_title(f"{pool}  c = {c_mi:g} mi", fontsize=10)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.tight_layout()
    return _png(fig, dpi=70)


def _lonlat_coords(g: Any, nd: int = 5) -> list[list[float]]:
    return [[round(x, nd), round(y, nd)] for x, y in g.coords]


def geojson(r: dict[str, Any], pool: str, p: eg.EdgeParams) -> dict[str, Any]:
    """Outline (all components) + walked segments, EPSG:4326, for the map and for step 3."""
    feats = []
    main = int(r["comps"].comp.iloc[0])
    for k, g in enumerate(eg.to_lonlat(list(r["outline"].geoms))):
        feats.append({"type": "Feature", "properties": {"layer": "outline", "pool": pool, "component": k, "main_body": k == main}, "geometry": mapping(g)})
    segs = eg.to_lonlat(list(r["seg"].geom))
    for (_, s), g in zip(r["seg"].iterrows(), segs):
        props = {
            "layer": "segment",
            "pool": pool,
            "seg_no": int(s.seg_no),
            "kind": s.kind,
            "length_ft": round(float(s.length_ft)),
            "gap_class": s.gap_class,
            "side": s.side,
            "api10_a": s.api10_a,
            "api10_b": s.api10_b,
            "n_edge_cohort": int(s.n_edge_cohort),
            "perf_ratio": None if not np.isfinite(s.perf_ratio) else round(float(s.perf_ratio), 3),
            "perf_class": s.perf_class,
            "n_pre2016_outside": int(s.n_pre2016_outside),
        }
        feats.append({"type": "Feature", "properties": props, "geometry": mapping(g)})
    return {"type": "FeatureCollection", "name": f"box_step2_{pool}", "crs_note": "EPSG:4326", "params": asdict(p), "features": feats}


def _map_data(r: dict[str, Any]) -> dict[str, Any]:
    """Compact payload for the Leaflet map (simplified laterals, rounded lon/lat)."""
    def lines_ll(geoms: list[Any]) -> list[list[list[float]]]:
        simp = [g.simplify(100.0) for g in geoms]
        return [_lonlat_coords(g) for g in eg.to_lonlat(simp)]

    ev, old, pw = r["ev"], r["old"], r["pinning"]
    so_ix = set(r["stepouts"].ix)
    ev_ll = lines_ll(list(ev.geom))

    def well_props(w: pd.Series) -> dict[str, Any]:
        o12 = w.oil12_kft
        return {
            "api10": w.api10,
            "name": w.well_name,
            "op": w.operator,
            "fp": str(w.first_production_date),
            "tag": w.formation_blueox,
            "oil12": None if not np.isfinite(o12) else round(float(o12)),
            "act": w.box_action,
        }

    wells = []
    for i, (_, w) in enumerate(ev.iterrows()):
        wells.append({"c": ev_ll[i], "p": well_props(w), "so": i in so_ix})
    pins = []
    for ix, w in pw.iterrows():
        pins.append({"i": int(ix), "cav": w.qc_caveat, "pin_ft": round(float(w.pinned_ft)), "sides": w.sides})
    segs = []
    for (_, s), g in zip(r["seg"].iterrows(), eg.to_lonlat(list(r["seg"].geom))):
        segs.append(
            {
                "c": _lonlat_coords(g.simplify(1e-5)),
                "k": s.kind,
                "col": _seg_colour(s.kind, s.gap_class),
                "len": round(float(s.length_ft)),
                "side": s.side,
                "a": s.name_a,
                "b": s.name_b,
                "n": int(s.n_edge_cohort),
                "pr": None if not np.isfinite(s.perf_ratio) else round(float(s.perf_ratio), 2),
                "pc": s.perf_class,
                "old": int(s.n_pre2016_outside),
            }
        )
    outline = []
    for g in eg.to_lonlat(list(r["outline"].geoms)):
        outline.append([_lonlat_coords(g.exterior.simplify(1e-5))] + [_lonlat_coords(h.simplify(1e-5)) for h in g.interiors])
    return {"wells": wells, "old": lines_ll(list(old.geom)), "pins": pins, "segs": segs, "outline": outline}


_CSS = """
body{font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#111827;background:#fff;margin:0 24px 48px;max-width:1500px}
h1{font-size:20px;margin:18px 0 4px} h2{font-size:16px;margin:32px 0 6px;border-top:2px solid #e5e7eb;padding-top:14px}
h3{font-size:14px;margin:16px 0 4px} .meta{color:#6b7280;font-size:12px}
.flag{background:#fffbeb;border-left:4px solid #d97706;padding:4px 10px;margin:6px 0} .bad{background:#fef2f2;border-left-color:#dc2626}
.ok{background:#f0fdf4;border-left-color:#16a34a}
.row{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap} img{max-width:100%;height:auto}
table{border-collapse:collapse;font-size:12px;margin:8px 0} th,td{border:1px solid #e5e7eb;padding:3px 7px;text-align:left;vertical-align:top}
th{background:#f9fafb} td.num,th.num{text-align:right}
details{margin:6px 0} summary{cursor:pointer;color:#374151;font-size:12px} .toc a{margin-right:10px;font-size:12px}
#map{height:760px;border:1px solid #d1d5db;margin:8px 0} .lg span{display:inline-block;width:22px;height:4px;margin:0 4px 2px 10px;vertical-align:middle}
"""


def _table(df: pd.DataFrame, fmt: dict[str, str] | None = None, max_rows: int | None = None) -> str:
    fmt = fmt or {}
    d = df if max_rows is None else df.head(max_rows)
    head = "".join(f"<th class={'num' if pd.api.types.is_numeric_dtype(d[c]) else ''}>{html.escape(str(c))}</th>" for c in d.columns)
    rows = []
    for _, r in d.iterrows():
        cells = []
        for c in d.columns:
            v = r[c]
            num = isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool)
            if num and not np.isfinite(v):
                s = "–"
            elif c in fmt and num:
                s = format(v, fmt[c])
            else:
                s = html.escape(str(v))
            cells.append(f"<td class={'num' if num else ''}>{s}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    more = f"<div class=meta>showing {len(d):,} of {len(df):,} rows — full list in the CSV</div>" if max_rows is not None and len(df) > max_rows else ""
    return f"<table><tr>{head}</tr>{''.join(rows)}</table>{more}"


_MAP_JS = """
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D = __DATA__;
const map = L.map('map', {preferCanvas: true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {maxZoom: 16, attribution: 'Tiles &copy; Esri'}).addTo(map);
const ll = c => c.map(p => [p[1], p[0]]);
const esc = s => String(s ?? '').replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
const outline = L.layerGroup(D.outline.map(rings => L.polygon(rings.map(ll), {color: '#6b7280', weight: 0.8, fillColor: '#bfdbfe', fillOpacity: 0.25, interactive: false}))).addTo(map);
const old = L.layerGroup(D.old.map(c => L.polyline(ll(c), {color: '#9ca3af', weight: 1, interactive: false}))).addTo(map);
const wpop = w => `<b>${esc(w.p.name)}</b><br>api10 ${w.p.api10} · ${esc(w.p.op)}<br>first prod ${w.p.fp} · tag ${w.p.tag} · ${w.p.act}<br>12-mo oil ${w.p.oil12 ?? '–'} bbl/1,000 ft`;
const ev = L.layerGroup(D.wells.map(w => L.polyline(ll(w.c), {color: w.so ? '#c026d3' : '#1e3a8a', weight: w.so ? 2.5 : 1}).bindPopup(wpop(w)))).addTo(map);
const segs = L.layerGroup(D.segs.map(s => L.polyline(ll(s.c), {color: s.col, weight: s.k === 'pinned' ? 2 : 4, opacity: 0.95}).bindPopup(
  `<b>${s.k === 'pinned' ? 'pinned run' : 'gap'}</b> ${s.len.toLocaleString()} ft · side ${s.side}<br>` +
  (s.k === 'pinned' ? `pinned by ${esc(s.a)}` : `between ${esc(s.a)} → ${esc(s.b)}`) +
  `<br>edge cohort wells ${s.n} · oil/ft vs interior ${s.pr ?? '–'} → <b>${s.pc}</b><br>pre-2016 laterals just outside: ${s.old}`))).addTo(map);
const pins = L.layerGroup(D.pins.filter(p => p.cav).map(p => { const w = D.wells[p.i]; return L.polyline(ll(w.c), {color: '#06b6d4', weight: 3}).bindPopup(
  wpop(w) + `<br><b>edge-pinning</b> ${p.pin_ft.toLocaleString()} ft (${p.sides})<br><span style="color:#b45309">${esc(p.cav)}</span>`); })).addTo(map);
L.control.layers(null, {'outline (closing)': outline, 'pre-2016 laterals': old, '≥2016 laterals (magenta = step-out)': ev, 'edge walk (pinned / gaps)': segs, 'edge-pinning wells with a QC caveat': pins}, {collapsed: false}).addTo(map);
const bounds = L.latLngBounds(D.outline.flatMap(rings => ll(rings[0])));
map.fitBounds(bounds);  // set a view immediately, then again once layout has settled
window.addEventListener('load', () => { map.invalidateSize(); map.fitBounds(bounds); });
</script>
"""


def pool_page(pool: str, r: dict[str, Any], ctx: dict[str, Any]) -> str:
    st = r["stats"]
    p: eg.EdgeParams = ctx["params"]
    sides = r["sides"].reindex(list(eg.SECTORS)).reset_index()
    side_cols = {
        "side": "side",
        "perimeter_mi": "perimeter mi",
        "n_pinning_wells": "pinning wells",
        "mi_per_pinning_well": "mi / pinning well",
        "pinned_share": "pinned share",
        "n_gaps": "gaps",
        "gap_median_ft": "gap median ft",
        "gap_p90_ft": "gap p90 ft",
        "share_gap_gt_1_mi": "share in gaps > 1 mi",
        "edge_perf_median": "edge oil/ft ÷ interior (median)",
        "stepouts_le5mi": "step-outs ≤ 5 mi",
        "stepouts_5_20mi": "5–20 mi",
        "stepouts_gt20mi": "> 20 mi",
        "stepout_vintage_median": "step-out first-prod yr (median)",
        "stepout_perf_median": "step-out oil/ft ÷ interior (median)",
    }
    st_tab = sides[list(side_cols)].rename(columns=side_cols)
    fmt = {"perimeter mi": ",.1f", "mi / pinning well": ".2f", "pinned share": ".2f", "gap median ft": ",.0f", "gap p90 ft": ",.0f", "share in gaps > 1 mi": ".2f",
           "edge oil/ft ÷ interior (median)": ".2f", "step-out first-prod yr (median)": ".0f", "step-out oil/ft ÷ interior (median)": ".2f"}
    perf = pd.DataFrame(
        [
            {"edge class": k, "perf_class": c, "perimeter mi": st["perf_mi"].get(f"{k}|{c}", 0.0)}
            for k in ("pinned", "gap")
            for c in ("strong", "unknown", "rolled")
        ]
    )
    pw = r["pinning"]
    cav = pw[pw.qc_caveat != ""].sort_values("pinned_ft", ascending=False)
    cav_tab = cav[["api10", "well_name", "operator", "county", "first_production_date", "formation_blueox", "pinned_ft", "sides", "perf_ratio", "qc_caveat"]]
    so = r["stepouts"].sort_values(["side", "dist_mi"])
    so_tab = so[["side", "dist_mi", "api10", "well_name", "operator", "county", "first_production_date", "formation_blueox", "perf_ratio"]]
    holes = r["holes"]
    sw = ctx["sweeps"][pool]
    data = json.dumps(_map_data(r), separators=(",", ":"))
    verdict = ctx["verdicts"][pool]
    parts = [
        f"<!doctype html><html><head><meta charset=utf-8><title>BOX step 2 — edge gap {pool}</title><style>{_CSS}</style></head><body>",
        f"<h1>BOX step 2 — edge-gap prototype: Delaware {pool}</h1>",
        (
            f"<div class=meta>Grain: one row per api10 lateral. Evidence = gate-1 final set <code>wells_final_{pool}.csv</code> with first production ≥ 2016-01-01 "
            f"(n = {st['n_evidence']:,}; {'WCA_1 + WCA_2 + WCXY one-way, D19/D20' if pool == 'WCA' else 'BS2_S after the gate-1 rule'}); pre-2016 pool laterals "
            f"(n = {st['n_pre2016']:,}) are negative evidence only (grey). Geometry: {', '.join(f'{k} {v:,}' for k, v in st['geom_src'].items())}. "
            f"Outline = laterals dilated by r = {p.pin_radius_ft:,.0f} ft, closed by c = {p.close_ft:,.0f} ft ({p.close_ft / eg.FT_PER_MI:g} mi, tuned on WCA). "
            f"12-mo oil = Novi cum_12m_oil_bbl ÷ lateral_length_ft × 1,000 (calendar basis as Novi computed it), D9 cohort wells only (first prod ≥ 2016, lateral 6,000–13,000 ft, 12 full months). "
            f"Built {ctx['built_at']}. Read-only; nothing written to the warehouse. Plan: docs/box_type_curves_plan.md §5 step 2.</div>"
        ),
        "<div class=toc><a href=index.html>← index</a><a href=#map>map</a><a href=#test>test</a><a href=#sides>by side</a><a href=#dist>distribution</a><a href=#perf>edge perf</a><a href=#pins>pinning wells</a><a href=#stepouts>step-outs</a><a href=#holes>holes</a><a href=#sweep>alpha sweep</a></div>",
        f"<h2 id=test>Expected-result test</h2>{verdict}",
        "<h2>Map</h2><div class=lg>"
        + f"<span style='background:{PINNED_COLOUR}'></span>pinned"
        + "".join(f"<span style='background:{c}'></span>gap {lab}" for c, lab in zip(GAP_COLOURS, eg.GAP_LABELS))
        + "<span style='background:#9ca3af'></span>pre-2016<span style='background:#c026d3'></span>step-out<span style='background:#06b6d4'></span>pinning well with QC caveat</div>"
        "<div id=map></div><div class=meta>Click a segment for its gap length, bounding wells, edge performance and pre-2016 count; click a lateral for the well. Layers toggle top-right.</div>",
        f"<details><summary>static overview (same data)</summary><img src='{ctx['overview'][pool]}'></details>",
        "<h2>Gap distribution (main body outer ring)</h2>"
        + _table(
            pd.DataFrame(
                [
                    {
                        "perimeter mi": st["perimeter_mi"],
                        "pinning wells": st["n_pinning_wells"],
                        "perimeter mi / pinning well": st["mi_per_pinning_well"],
                        "pinned share": st["pinned_share"],
                        "gaps": st["n_gaps"],
                        "gap median ft": st["gap_median_ft"],
                        "gap p90 ft": st["gap_p90_ft"],
                        "gap max ft": st["gap_max_ft"],
                        "share in gaps > 1/2 mi": st["share_gap_gt_half_mi"],
                        "share in gaps > 1 mi": st["share_gap_gt_1_mi"],
                    }
                ]
            ),
            {"perimeter mi": ",.1f", "perimeter mi / pinning well": ".2f", "pinned share": ".2f", "gap median ft": ",.0f", "gap p90 ft": ",.0f", "gap max ft": ",.0f",
             "share in gaps > 1/2 mi": ".2f", "share in gaps > 1 mi": ".2f"},
        )
        + f"<div class=meta>Main body holds {st['main_share']:.1%} of the evidence laterals ({st['n_components']} outline components, {st['n_bodies']} with ≥ {p.min_body_wells} laterals). "
        "A gap is unpinned outline between two consecutive pinning laterals; hand-overs between adjacent laterals have no gap record. "
        f"Gap length is bounded by the closing (an opening wider than ~2c = {2 * p.close_ft / eg.FT_PER_MI:g} mi is not bridged and leaves step-outs outside the body instead).</div>",
        f"<h2 id=sides>By side of the body</h2>{_table(st_tab, fmt)}<img src='{ctx['side_png']}'>",
        f"<h2 id=dist>Gap length histogram</h2><img src='{ctx['hist_png']}'>",
        f"<h2 id=perf>Edge performance (§6: edge cohort median 12-mo oil/ft ÷ interior median; ≥ 0.85 strong, < 0.70 rolled)</h2>"
        f"<div class=meta>Interior = D9 cohort laterals ≥ r + {p.interior_depth_ft / eg.FT_PER_MI:g} mi inside the outline (n = {st['n_interior_cohort']:,}); "
        f"interior median <b>{st['interior_median_oil12_kft']:,.0f} bbl / 1,000 ft</b> (median, not mean). Edge wells per segment = cohort laterals within "
        f"r + {p.edge_reach_ft:,.0f} ft of it. This is the 2×2 input for step 3; nothing here sets a buffer.</div>"
        + _table(perf, {"perimeter mi": ",.1f"}),
        f"<h2 id=pins>Edge-pinning wells with a QC caveat ({len(cav):,} of {len(pw):,} pinning wells)</h2>"
        "<div class=meta>The gate-1 agreement: well-by-well review is off the table except for edge-pinning wells, because they define the outline. "
        "Caveat = reassigned in by the gate-1 rule, TVD suspect (A′), planned survey, permit-round TVD, or a consensus flag kept (moot D19/D20 flags excluded). "
        "Highlighted cyan on the map.</div>"
        + _table(cav_tab, {"pinned_ft": ",.0f", "perf_ratio": ".2f"}, max_rows=150),
        f"<h2 id=stepouts>Step-outs: ≥ 2016 laterals outside the main body ({len(so):,})</h2>"
        "<div class=meta>A front that is moving shows up as tests ahead of the body; distance is lateral-to-body edge (the edge sits r outside the laterals). perf_ratio = 12-mo oil/ft ÷ interior median (blank = not in the D9 cohort yet).</div>"
        + _table(so_tab, {"dist_mi": ".1f", "perf_ratio": ".2f"}, max_rows=120),
        f"<h2 id=holes>Holes inside the main body ({len(holes):,}, {st['holes_sqmi']:,.0f} sq mi)</h2>"
        "<div class=meta>Listed, not walked: a hole is ground ≥ ~1 mi from any ≥ 2016 lateral that the closing did not bridge. Whether it is a geology hole or a surface "
        "constraint (potash, towns, the river — D8: Surface Land's problem) is geology's call in step 3.</div>"
        + _table(holes, {"area_sqmi": ",.1f", "lon": ".4f", "lat": ".4f"}, max_rows=40),
        "<h2 id=sweep>Alpha sweep (r = pin radius, c = closing radius = the per-basin alpha)</h2>"
        + _table(sw, {"r_mi": ".2f", "c_mi": ".2f", "main_share": ".3f", "holes_sqmi": ",.0f", "max_hole_sqmi": ",.1f", "main_perimeter_mi": ",.0f", "pinned_share": ".2f", "gap_p90_ft": ",.0f"})
        + f"<div class=meta>Tuning rule (WCA): the smallest c that makes WCA one body (one component with ≥ {p.min_body_wells} laterals) at r = {p.pin_radius_ft / eg.FT_PER_MI:g} mi. "
        "Larger c bridges more (fewer holes, longer gaps, lower pinned share); larger r pins more ground per lateral.</div>"
        f"<img src='{ctx['sweep_png'][pool]}'>",
        _MAP_JS.replace("__DATA__", data),
        "</body></html>",
    ]
    return "\n".join(parts)


def _verdict(pool: str, r: dict[str, Any]) -> str:
    s = r["sides"]
    st = r["stats"]
    lines = []
    if pool == "WCA":
        lo, hi = s["pinned_share"].min(), s["pinned_share"].max()
        g1lo, g1hi = s["share_gap_gt_1_mi"].min(), s["share_gap_gt_1_mi"].max()
        so = int(st["n_stepouts"])
        cls = "ok" if hi - lo <= 0.15 and g1hi <= 0.25 else "bad"
        lines.append(
            f"<div class='flag {cls}'><b>Expected: WCA uniformly pinned.</b> Every side is {lo:.0%}–{hi:.0%} pinned with {g1lo:.0%}–{g1hi:.0%} of its perimeter in gaps &gt; 1 mi "
            f"(overall {st['pinned_share']:.0%} pinned, gap median {st['gap_median_ft']:,.0f} ft, p90 {st['gap_p90_ft']:,.0f} ft, {st['mi_per_pinning_well']:.2f} perimeter-mi per pinning well); "
            f"{so} step-out laterals beyond the body. {'Reads as uniform: no side stands out.' if cls == 'ok' else 'Not uniform — see the side table.'}</div>"
        )
    else:
        def side_line(sec: str) -> str:
            x = s.loc[sec]
            n_so = int(x.stepouts_le5mi + x.stepouts_5_20mi + x.stepouts_gt20mi)
            yr = "" if not np.isfinite(x.stepout_vintage_median) else f", median {x.stepout_vintage_median:.0f}"
            pr = "" if not np.isfinite(x.stepout_perf_median) else f", oil/ft {x.stepout_perf_median:.2f}× interior"
            return f"<b>{sec}</b> {x.pinned_share:.0%} pinned, {x.share_gap_gt_1_mi:.0%} in gaps &gt; 1 mi, {n_so} step-outs{yr}{pr}"
        lines.append(
            "<div class='flag'><b>Expected: BS2_S pinned W / N / E, long S / SE gaps.</b><br>" + "<br>".join(side_line(sec) for sec in eg.SECTORS) + "</div>"
        )
    return "".join(lines)


def run(conn: Any, wells_dir: Path, out: Path, pools: tuple[str, ...] = POOLS, r_mi: float = 0.5) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    df = load_final_sets(wells_dir, pools)
    geo = pull_laterals(conn, sorted(df["api10"].unique()))
    df = attach_geometry(df, geo)
    base = replace(eg.DEFAULT, pin_radius_ft=r_mi * eg.FT_PER_MI)
    sweeps: dict[str, pd.DataFrame] = {}
    sweep_imgs: dict[str, str] = {}
    for pool in pools:
        ev_lines = list(df.loc[(df.pool == pool) & df.evidence & df.geom.notna(), "geom"])
        sweeps[pool] = eg.sweep(ev_lines, [x * eg.FT_PER_MI for x in SWEEP_R_MI], [x * eg.FT_PER_MI for x in SWEEP_C_MI], base)
    c_ft = eg.tune_close(sweeps[TUNE_POOL], r_mi)
    p = replace(base, close_ft=c_ft)
    results: dict[str, dict[str, Any]] = {}
    for pool in pools:
        results[pool] = analyse_pool(df[df.pool == pool], p)
        ev_lines = list(results[pool]["ev"].geom)
        fp = eg.footprint(ev_lines, p)
        show = sorted({0.5, c_ft / eg.FT_PER_MI, 1.5})
        sweep_imgs[pool] = sweep_png({c: eg.close(fp, replace(p, close_ft=c * eg.FT_PER_MI)) for c in show}, ev_lines, pool)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    ctx = {
        "params": p,
        "built_at": built,
        "sweeps": sweeps,
        "sweep_png": sweep_imgs,
        "hist_png": gap_hist_png(results),
        "side_png": side_png(results),
        "overview": {pool: overview_png(results[pool], pool, f"{pool}: outline coloured by gap (r = {p.pin_radius_ft / eg.FT_PER_MI:g} mi, c = {p.close_ft / eg.FT_PER_MI:g} mi)") for pool in pools},
        "verdicts": {pool: _verdict(pool, results[pool]) for pool in pools},
    }
    summary: dict[str, Any] = {"built_at": built, "wells_dir": str(wells_dir), "params": asdict(p), "tuned_on": TUNE_POOL, "pools": {}}
    for pool in pools:
        r = results[pool]
        (out / f"edge_{pool}.html").write_text(pool_page(pool, r, ctx), encoding="utf-8")
        seg = r["seg"].drop(columns=["geom", "well_a", "well_b"])
        seg.to_csv(out / f"segments_{pool}.csv", index=False)
        pw = r["pinning"].drop(columns=["geom", "wkt"])
        pw.sort_values("pinned_ft", ascending=False).to_csv(out / f"pinning_wells_{pool}.csv", index=False)
        r["stepouts"].drop(columns=["ix"]).to_csv(out / f"stepouts_{pool}.csv", index=False)
        r["holes"].to_csv(out / f"holes_{pool}.csv", index=False)
        sweeps[pool].to_csv(out / f"alpha_sweep_{pool}.csv", index=False)
        (out / f"outline_{pool}.geojson").write_text(json.dumps(geojson(r, pool, p)), encoding="utf-8")
        summary["pools"][pool] = {**r["stats"], "sides": r["sides"].round(4).to_dict(orient="index")}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else str(x)), encoding="utf-8")
    idx = [
        f"<!doctype html><html><head><meta charset=utf-8><title>BOX step 2 — edge gap</title><style>{_CSS}</style></head><body>",
        "<h1>BOX step 2 — edge-gap prototype (Delaware pilot)</h1>",
        f"<div class=meta>Built {built}. Read-only. Plan: docs/box_type_curves_plan.md §5 step 2. Gate summary: FINDINGS.md in this folder.</div>",
        "<ul>" + "".join(f"<li><a href=edge_{pool}.html>{pool}</a> — {results[pool]['stats']['n_evidence']:,} evidence laterals, "
                          f"{results[pool]['stats']['pinned_share']:.0%} of the outline pinned, gap median {results[pool]['stats']['gap_median_ft']:,.0f} ft / p90 {results[pool]['stats']['gap_p90_ft']:,.0f} ft, "
                          f"{results[pool]['stats']['n_stepouts']} step-outs</li>" for pool in pools) + "</ul>",
        f"<img src='{ctx['side_png']}'><img src='{ctx['hist_png']}'>",
        "</body></html>",
    ]
    (out / "index.html").write_text("\n".join(idx), encoding="utf-8")
    return {"summary": summary, "results": results, "params": p}
