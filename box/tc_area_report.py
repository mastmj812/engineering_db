"""BOX step 4 — TC areas on WCA: inputs, the regionalization run, stats, review page (read-only).

Reads the gate-1 final WCA well set (docs/box/step1-2026-10-06/wells_final_WCA.csv: WCA_1 + WCA_2
pooled, WCXY one-way, D19/D20), the WCA extent of record from box.extent, the 24-mo / Novi 30-yr
columns from curated.wells_enriched, and the D1 PUD universe (count only) — all inside READ ONLY
transactions. box/tc_area.py holds the pure method.

Cohorts (plan D9; one filter, three responses — populations differ, so each map states its n):
  12-mo  the gate-1 `cohort` flag (fp >= 2016-01-01, lateral 6,000–13,000 ft, 12 full months,
         cum-12 > 0) with the lateral midpoint inside the extent — THE response the areas are built on
  24-mo  same filter, 24 full months as of the data's last reported month, cum-24 > 0
  bo/ft  same vintage + lateral filter, Novi 30-yr oil EUR / lateral (Novi WellDetails, a vendor
         forecast horizon, not the suite's 50-yr technical EUR); life-to-date cum where Novi has none
All rates are Novi WellDetails cum pass-throughs (calendar months from first production).
"""

from __future__ import annotations

import datetime as dt
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
from matplotlib.collections import PatchCollection
from matplotlib.patches import Polygon as MplPolygon

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import exclusions
from box import extent_report as er
from box import tc_area as ta
from box.edge_gap_report import _CSS, _lonlat_coords, _png, _table

POOL = "WCA"
BASIN = "delaware"
COHORT_FP_MIN = dt.date(2016, 1, 1)
LL_MIN, LL_MAX = 6000.0, 13000.0
PUD_BENCHES = ("WCA_1", "WCA_2", "WCXY")  # WCXY PUDs reported apart (D20: membership is a step-7 call)
SENS_KNN = (10, 15, 25)
SENS_CELL_MI = (1.0, 1.5)
LEVELS = (6, 10, 14, 20)  # coarser nested cuts shown next to the pick
PAD_SQMI = 25.0  # review flag only
OP_DOM = 0.70  # review flag only


# ----------------------------------------------------------------------------
# Inputs (read-only)
# ----------------------------------------------------------------------------

_EXTRA_SQL = """
SELECT api10, cum_24m_oil_bbl, eur_30yr_oil_bbl, cum_life_oil_bbl, last_reported_month
FROM curated.wells_enriched
WHERE api10 = ANY(%(api10s)s)
"""

_EXTENT_SQL = """
SELECT extent_id, version, source, area_sqmi, extensions.ST_AsText(geom)
FROM box.extent
WHERE basin = %(basin)s AND bench = %(bench)s AND is_record
"""


def _read(conn: Any, sql: str, params: dict[str, Any]) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.rollback()
    return rows


def pull_extent(conn: Any, bench: str = POOL) -> dict[str, Any]:
    rows = _read(conn, _EXTENT_SQL, {"basin": BASIN, "bench": bench})
    if len(rows) != 1:
        raise RuntimeError(f"expected exactly one extent of record for {BASIN}/{bench}, found {len(rows)}")
    eid, ver, src, a, wkt = rows[0]
    return {"extent_id": int(eid), "version": int(ver), "source": src, "area_sqmi": float(a), "geom_ft": eg.to_ft([shapely.from_wkt(wkt)])[0]}


def pull_extra(conn: Any, api10s: list[str]) -> pd.DataFrame:
    rows = _read(conn, _EXTRA_SQL, {"api10s": api10s})
    d = pd.DataFrame(rows, columns=["api10", "cum_24m_oil_bbl", "eur_30yr_oil_bbl", "cum_life_oil_bbl", "last_reported_month"])
    for c in ("cum_24m_oil_bbl", "eur_30yr_oil_bbl", "cum_life_oil_bbl"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


# ----------------------------------------------------------------------------
# Frame
# ----------------------------------------------------------------------------


def prepare(wells: pd.DataFrame, extra: pd.DataFrame, extent_ft: Any, asof: dt.date | None = None) -> pd.DataFrame:
    """Per-well responses (bbl/ft) and cohort flags; xy = lateral midpoint, UTM 13N ft (pure)."""
    d = wells.drop(columns=[c for c in extra.columns if c != "api10" and c in wells.columns]).merge(extra, on="api10", how="left")
    tr = eg._transformer()
    x, y = tr.transform(d["mid_lon"].to_numpy(float), d["mid_lat"].to_numpy(float))
    d["x"], d["y"] = np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT
    shapely.prepare(extent_ft)
    d["inside"] = shapely.contains_xy(extent_ft, d["x"].to_numpy(), d["y"].to_numpy())
    if asof is None:
        lrm = pd.to_datetime(d["last_reported_month"], errors="coerce")
        asof = lrm.max().date()
    d.attrs["asof"] = asof
    ll = pd.to_numeric(d["lateral_length_ft"], errors="coerce")
    base = pd.Series([fp >= COHORT_FP_MIN for fp in d["first_production_date"]], index=d.index) & ll.between(LL_MIN, LL_MAX)
    d["oil12_ft"] = pd.to_numeric(d["cum_12m_oil_bbl"], errors="coerce") / ll
    d["oil24_ft"] = d["cum_24m_oil_bbl"] / ll
    eur = d["eur_30yr_oil_bbl"].where(d["eur_30yr_oil_bbl"] > 0)
    d["eur_src"] = np.where(eur.notna(), "novi_30yr", np.where(d["cum_life_oil_bbl"] > 0, "cum_to_date", ""))
    d["bo_ft"] = eur.fillna(d["cum_life_oil_bbl"].where(d["cum_life_oil_bbl"] > 0)) / ll
    full24 = pd.Series([fp <= asof - dt.timedelta(days=760) for fp in d["first_production_date"]], index=d.index)
    d["c12"] = d["cohort"].astype(bool) & d["inside"] & (d["oil12_ft"] > 0)
    d["c24"] = base & d["inside"] & full24 & (d["cum_24m_oil_bbl"] > 0)
    d["ceur"] = base & d["inside"] & (d["bo_ft"] > 0)
    return d


# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------


def regionalize(extent_ft: Any, d: pd.DataFrame, p: ta.AreaParams) -> dict[str, Any]:
    cells, centres = ta.hex_cells(extent_ft, p.cell_ft)
    pairs = ta.adjacency(cells, centres, p.cell_ft)
    c = d[d["c12"]].reset_index(drop=True)
    wxy = c[["x", "y"]].to_numpy()
    wcell = ta.cell_of(cells, wxy)
    ok = wcell >= 0
    c, wxy, wcell = c[ok].reset_index(drop=True), wxy[ok], wcell[ok]
    yv = np.log(c["oil12_ft"].to_numpy(float))
    cv = ta.cross_validate(centres, pairs, wcell, wxy, yv, p)
    pick = ta.choose_k(cv["cv"])
    parts = ta.build(centres, pairs, wcell, wxy, yv, p)
    lab = parts[pick["k_1se"] - 1]
    geoms, cell_no = ta.dissolve(cells, lab, centres)
    sse = sum(float(np.sum((yv[cell_no[wcell] == a] - yv[cell_no[wcell] == a].mean()) ** 2)) for a in range(1, len(geoms) + 1))
    r2_in = 1.0 - sse / float(np.sum((yv - yv.mean()) ** 2))
    return {"cells": cells, "centres": centres, "pairs": pairs, "cell_no": cell_no, "geoms": geoms, "cv": cv, "pick": pick, "r2_in": r2_in,
            "n_cells": len(cells), "n_wells": len(c), "field": ta.knn_field(centres, wxy, yv, p.knn), "parts": parts, "wcell": wcell, "y": yv}


def sensitivity(extent_ft: Any, d: pd.DataFrame, p: ta.AreaParams) -> pd.DataFrame:
    """k pick and CV skill across the two geometry knobs (cell size, field kNN)."""
    rows = []
    for cell_mi in SENS_CELL_MI:
        for knn in SENS_KNN:
            q = replace(p, cell_ft=cell_mi * eg.FT_PER_MI, knn=knn)
            r = regionalize(extent_ft, d, q)
            cv, pk = r["cv"]["cv"], r["pick"]
            row = cv.loc[cv.k == pk["k_1se"]].iloc[0]
            rows.append({"cell_mi": cell_mi, "knn": knn, "k_1se": pk["k_1se"], "k_min": pk["k_min"], "cv_mse_at_pick": float(row.mse),
                         "cv_r2_at_pick": float(row.r2), "cv_r2_min": float(cv.r2.max()), "knn_local_cv_r2": 1.0 - r["cv"]["knn_mse"] / r["cv"]["var"]})
    return pd.DataFrame(rows)


def response_cv_24(extent_ft: Any, d: pd.DataFrame, p: ta.AreaParams) -> dict[str, Any]:
    """Would a 24-mo regionalization pick a different k? (same cells, its own cohort)."""
    dd = d.copy()
    dd["c12"], dd["oil12_ft"] = dd["c24"], dd["oil24_ft"]
    r = regionalize(extent_ft, dd, p)
    return {"n": r["n_wells"], **r["pick"], "cv_r2_at_pick": float(r["cv"]["cv"].loc[r["cv"]["cv"].k == r["pick"]["k_1se"], "r2"].iloc[0])}


def assign_area(d: pd.DataFrame, geoms: list[Any]) -> pd.Series:
    tree = shapely.STRtree(geoms)
    pts = shapely.points(d[["x", "y"]].to_numpy())
    pi, gi = tree.query(pts, predicate="intersects")
    out = pd.Series(0, index=d.index, dtype=int)
    out.iloc[pi] = gi + 1
    return out


def _q(v: pd.Series, q: float) -> float:
    return float(v.quantile(q)) if len(v) else float("nan")


def area_stats(d: pd.DataFrame, geoms: list[Any], puds: pd.DataFrame | None) -> pd.DataFrame:
    """One row per area. Percentiles in SPE orientation: P10 = HIGH (the 90th percentile)."""
    rows = []
    for no, g in enumerate(geoms, start=1):
        a = d[d["area_no"] == no]
        c12, c24, ce = a[a.c12], a[a.c24], a[a.ceur]
        top = c12["operator"].value_counts()
        mem = c12["formation_blueox"].value_counts()
        nx = c12[c12.formation_blueox != "WCXY"]
        fy = pd.to_datetime(c12["first_production_date"]).dt.year
        r = {
            "area_no": no, "area_sqmi": g.area / eg.FT_PER_MI**2,
            "n12": len(c12), "oil12_p50": _q(c12.oil12_ft, 0.5), "oil12_p10_high": _q(c12.oil12_ft, 0.9), "oil12_p90_low": _q(c12.oil12_ft, 0.1),
            "oil12_mean": float(c12.oil12_ft.mean()) if len(c12) else math.nan,
            "n24": len(c24), "oil24_p50": _q(c24.oil24_ft, 0.5),
            "n_eur": len(ce), "bo_ft_p50": _q(ce.bo_ft, 0.5), "n_eur_cum_fallback": int((ce.eur_src == "cum_to_date").sum()),
            "n_WCA_1": int(mem.get("WCA_1", 0)), "n_WCA_2": int(mem.get("WCA_2", 0)), "n_WCXY": int(mem.get("WCXY", 0)),
            "n_other_tag": int(len(c12) - mem.get("WCA_1", 0) - mem.get("WCA_2", 0) - mem.get("WCXY", 0)),
            "oil12_p50_exWCXY": _q(nx.oil12_ft, 0.5), "n12_exWCXY": len(nx),
            "fp_year_p50": float(fy.median()) if len(fy) else math.nan,
            "lateral_p50": float(c12.lateral_length_ft.median()) if len(c12) else math.nan,
            "top_operator": top.index[0] if len(top) else "", "top_operator_share": float(top.iloc[0] / len(c12)) if len(top) else math.nan,
        }
        r["flag"] = "; ".join(f for f, on in ((f"pad-scale (< {PAD_SQMI:g} sq mi)", r["area_sqmi"] < PAD_SQMI),
                                               (f"one operator >= {OP_DOM:.0%}", r["top_operator_share"] >= OP_DOM)) if on)
        rows.append(r)
    s = pd.DataFrame(rows)
    if puds is not None and len(puds):
        cnt = puds[puds.area_no > 0].groupby(["area_no", "bench_grp"]).size().unstack(fill_value=0)
        for col in ("WCA_1+2", "WCXY"):
            s[f"d1_puds_{col}"] = s["area_no"].map(cnt.get(col, {})).fillna(0).astype(int)
    return s


def pud_areas(puds: pd.DataFrame, extent_ft: Any, geoms: list[Any]) -> pd.DataFrame:
    """D1 universe sticks >= 50 % inside the extent (rule 9 co-extent), each to its max-overlap area."""
    if puds.empty:
        return puds.assign(area_no=[], bench_grp=[])
    d = puds.assign(status=puds["status"].fillna("NULL (not yet reconciled)"))
    d = d[d["status"].isin(["remaining_pud", "conflict", "NULL (not yet reconciled)"])].reset_index(drop=True)
    g = np.asarray(eg.to_ft(list(shapely.from_wkt(d["wkt"]))), dtype=object)
    L = shapely.length(g)
    inside = np.divide(shapely.length(shapely.intersection(g, extent_ft)), L, out=np.zeros(len(L)), where=L > 0) >= 0.5
    ov = np.column_stack([shapely.length(shapely.intersection(g, a)) for a in geoms])
    d["area_no"] = np.where(inside, ov.argmax(axis=1) + 1, 0)
    d["bench_grp"] = np.where(d["formation_blueox"] == "WCXY", "WCXY", "WCA_1+2")
    return d


# ----------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------

SEQ = "Blues"


def _poly_patches(geoms: list[Any]) -> list[tuple[int, Any]]:
    out = []
    for no, g in enumerate(geoms, start=1):
        for part in eg._as_multi(g).geoms:
            out.append((no, MplPolygon(np.asarray(part.exterior.coords) / eg.FT_PER_MI, closed=True)))
    return out


def gut_check_png(geoms: list[Any], s: pd.DataFrame, extent_ft: Any) -> str:
    panels = [("bo_ft_p50", "n_eur", "Novi 30-yr oil EUR / ft (cum where no Novi)"), ("oil12_p50", "n12", "12-mo oil / ft"), ("oil24_p50", "n24", "24-mo oil / ft")]
    fig, axes = plt.subplots(1, 3, figsize=(18, 7.2))
    pp = _poly_patches(geoms)
    cent = [g.representative_point() for g in geoms]
    for ax, (col, ncol, title) in zip(axes, panels):
        v = s.set_index("area_no")[col]
        vmin, vmax = np.nanpercentile(v, 5), np.nanpercentile(v, 95)
        pc = PatchCollection([p for _, p in pp], cmap=SEQ, edgecolor="white", linewidth=1.2)
        pc.set_array(np.asarray([v.get(no, np.nan) for no, _ in pp]))
        pc.set_clim(vmin, vmax)
        ax.add_collection(pc)
        for part in eg._as_multi(extent_ft).geoms:
            xy = np.asarray(part.exterior.coords) / eg.FT_PER_MI
            ax.plot(xy[:, 0], xy[:, 1], color="#374151", lw=0.8)
        for no, c in enumerate(cent, start=1):
            r = s.loc[s.area_no == no].iloc[0]
            val = r[col]
            dark = np.isfinite(val) and val > vmin + 0.6 * (vmax - vmin)
            ax.text(c.x / eg.FT_PER_MI, c.y / eg.FT_PER_MI, f"{no}\n{val:,.0f}\nn={int(r[ncol])}" if np.isfinite(val) else f"{no}\n–",
                    ha="center", va="center", fontsize=7, color="white" if dark else "#111827")
        ax.set_aspect("equal")
        ax.autoscale_view()
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_title(f"{title}\narea P50, bbl/ft; n per area (total n = {int(s[ncol].sum()):,})", fontsize=11)
        fig.colorbar(pc, ax=ax, shrink=0.55, label="bbl/ft (area P50)")
    fig.suptitle("WCA TC areas — gut check (UTM 13N). Vintage normalized by filter only (fp ≥ 2016, lateral 6–13 kft); operator / completion confounding NOT removed (D9).", fontsize=11, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    return _png(fig, dpi=80)


def cv_png(cv: pd.DataFrame, pick: dict[str, int], knn_r2: float) -> str:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(cv.k, cv.r2, color="#1d4ed8", lw=2, label="area-median predictor (blocked CV)")
    var = float((cv.mse / (1 - cv.r2)).iloc[0])
    best = float(cv.r2.max())
    ax.fill_between(cv.k, best - cv.se_paired / var, best, color="#1d4ed8", alpha=0.12, lw=0, label="within 1 paired SE of the best k")
    ax.axhline(knn_r2, color="#6b7280", ls="--", lw=1.2, label=f"local 15-well median, no areas (CV R² {knn_r2:.2f})")
    ax.axvline(pick["k_1se"], color="#111827", lw=1, label=f"pick k = {pick['k_1se']} (1-SE rule)")
    ax.axvline(pick["k_min"], color="#9ca3af", lw=1, ls=":", label=f"CV minimum k = {pick['k_min']}")
    ax.set_xlabel("number of areas k")
    ax.set_ylabel("held-out R² of log(12-mo oil/ft)")
    ax.grid(color="#e5e7eb", lw=0.6)
    ax.legend(fontsize=8, loc="lower right", frameon=False)
    ax.set_title("How many areas: 5-fold CV on 3-mi blocks (held-out ground)", fontsize=10)
    return _png(fig, dpi=85)


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------

_MAP_JS = """
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D = __DATA__;
const RAMP = ['#eff6ff','#dbeafe','#bfdbfe','#93c5fd','#60a5fa','#3b82f6','#1d4ed8','#1e3a8a'];
const map = L.map('map', {preferCanvas: true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {maxZoom: 16, attribution: 'Tiles &copy; Esri'}).addTo(map);
const ll = c => c.map(p => [p[1], p[0]]);
const f0 = (v) => v == null ? '–' : Math.round(v).toLocaleString();
const METRICS = {oil12: ['oil12_p50', 'n12', '12-mo oil/ft'], oil24: ['oil24_p50', 'n24', '24-mo oil/ft'], bo: ['bo_ft_p50', 'n_eur', 'Novi 30-yr EUR/ft']};
let metric = 'oil12';
let level = D.pick;
function col(v, lo, hi) { if (v == null) return '#f3f4f6'; const t = Math.max(0, Math.min(0.999, (v - lo) / (hi - lo))); return RAMP[Math.floor(t * RAMP.length)]; }
function range(key) { const v = D.levels[level].map(a => a.s[key]).filter(x => x != null).sort((a, b) => a - b); return [v[Math.floor(v.length * 0.05)], v[Math.floor(v.length * 0.95)]]; }
const areaLayer = L.layerGroup().addTo(map);
const labelLayer = L.layerGroup().addTo(map);
function popup(a) { const s = a.s; return `<b>Area ${s.area_no}</b> · ${s.area_sqmi.toFixed(0)} sq mi<br>` +
  `12-mo oil/ft P50 <b>${f0(s.oil12_p50)}</b> (P10 high ${f0(s.oil12_p10_high)} / P90 low ${f0(s.oil12_p90_low)}), n=${s.n12}<br>` +
  `24-mo oil/ft P50 ${f0(s.oil24_p50)}, n=${s.n24}<br>Novi 30-yr EUR/ft P50 ${f0(s.bo_ft_p50)}, n=${s.n_eur}<br>` +
  `members WCA_1 ${s.n_WCA_1} · WCA_2 ${s.n_WCA_2} · WCXY ${s.n_WCXY} · other tag ${s.n_other_tag}; ex-WCXY 12-mo P50 ${f0(s.oil12_p50_exWCXY)}<br>` +
  `median first prod ${s.fp_year_p50 ?? '–'} · lateral ${f0(s.lateral_p50)} ft · top operator ${s.top_operator} (${Math.round(100 * s.top_operator_share)}%)` +
  (s.d1_puds_WCA_1_2 != null ? `<br>D1 PUDs WCA_1+2 ${s.d1_puds_WCA_1_2} · WCXY ${s.d1_puds_WCXY}` : '') +
  (s.flag ? `<br><span style="color:#b45309">${s.flag}</span>` : ''); }
function draw() {
  areaLayer.clearLayers(); labelLayer.clearLayers();
  const [key, nkey, name] = METRICS[metric]; const [lo, hi] = range(key);
  D.levels[level].forEach(a => {
    a.p.forEach(P => L.polygon(ll(P), {color: '#ffffff', weight: 1.5, fillColor: col(a.s[key], lo, hi), fillOpacity: 0.85}).bindPopup(popup(a)).addTo(areaLayer));
    L.marker([a.lab[1], a.lab[0]], {icon: L.divIcon({className: 'albl', html: `<b>${a.s.area_no}</b><br>${f0(a.s[key])}<br>n=${a.s[nkey]}`, iconSize: [60, 36], iconAnchor: [30, 18]}), interactive: false}).addTo(labelLayer);
  });
  document.getElementById('legend').innerHTML = `<b>${name}</b>, area P50 bbl/ft: ` + RAMP.map((c, i) => `<span style="background:${c}"></span>${f0(lo + (hi - lo) * i / RAMP.length)}`).join(' ') + ` – ${f0(hi)}+`;
}
document.querySelectorAll('input[name=metric]').forEach(r => r.addEventListener('change', e => { metric = e.target.value; draw(); }));
document.querySelectorAll('input[name=level]').forEach(r => r.addEventListener('change', e => { level = e.target.value; draw(); }));
const ext = L.layerGroup(D.extent.map(P => L.polygon(ll(P), {color: '#111827', weight: 1.2, fill: false, interactive: false}))).addTo(map);
const wells = L.layerGroup(D.wells.map(w => L.circleMarker([w[1], w[0]], {radius: 2, weight: 0, fillColor: w[3] === 'WCXY' ? '#c026d3' : '#111827', fillOpacity: 0.55})
  .bindPopup(`api10 ${w[4]} · ${w[3]}<br>12-mo oil/ft ${f0(w[2])} · area ${w[5]}`)));
const cells = L.layerGroup(D.cells.map(c => L.polygon(ll(c.p), {weight: 0, fillColor: col(c.f, D.frange[0], D.frange[1]), fillOpacity: 0.8, interactive: false})));
L.control.layers(null, {'areas': areaLayer, 'labels': labelLayer, 'extent of record': ext, 'D9 12-mo cohort wells (magenta = WCXY)': wells, 'smoothed field (1-mi cells, 12-mo)': cells}, {collapsed: false}).addTo(map);
draw();
const bounds = L.latLngBounds(D.extent.flatMap(P => ll(P)));
map.fitBounds(bounds);
window.addEventListener('load', () => { map.invalidateSize(); map.fitBounds(bounds); });
</script>
"""


def map_data(ext: dict[str, Any], r: dict[str, Any], levels: dict[int, dict[str, Any]], pick: int, d: pd.DataFrame) -> dict[str, Any]:
    def rings(g: Any, tol: float = 1e-4) -> list[list[list[float]]]:
        return [_lonlat_coords(p.exterior.simplify(tol), 4) for p in eg._as_multi(g).geoms]

    lv = {}
    for k, L in levels.items():
        gl = eg.to_lonlat(L["geoms"])
        lab = eg.to_lonlat([g.representative_point() for g in L["geoms"]])
        rec = L["stats"].replace({np.nan: None}).rename(columns={"d1_puds_WCA_1+2": "d1_puds_WCA_1_2"}).to_dict("records")
        lv[str(k)] = [{"p": rings(g), "lab": [round(pt.x, 4), round(pt.y, 4)], "s": rr} for g, pt, rr in zip(gl, lab, rec)]
    c = d[d.c12]
    wl = [[round(a, 4), round(b, 4), round(v, 1), f, k, int(n)] for a, b, v, f, k, n in zip(c.mid_lon, c.mid_lat, c.oil12_ft, c.formation_blueox, c.api10, c.area_no)]
    field = np.exp(r["field"])
    cl = eg.to_lonlat(r["cells"])
    cells = [{"p": rings(g, 2e-4)[0], "f": round(float(v), 1)} for g, v in zip(cl, field)]
    return {"levels": lv, "pick": str(pick), "extent": rings(eg.to_lonlat([ext["geom_ft"]])[0]), "wells": wl, "cells": cells,
            "frange": [float(np.percentile(field, 5)), float(np.percentile(field, 95))]}


def render_page(ctx: dict[str, Any]) -> str:
    r, s, ext, summ = ctx["r"], ctx["stats"], ctx["extent"], ctx["summary"]
    cv = r["cv"]["cv"]
    pick = r["pick"]
    knn_r2 = 1.0 - r["cv"]["knn_mse"] / r["cv"]["var"]
    tab = s[["area_no", "area_sqmi", "n12", "oil12_p50", "oil12_p10_high", "oil12_p90_low", "n24", "oil24_p50", "n_eur", "bo_ft_p50",
             "n_WCA_1", "n_WCA_2", "n_WCXY", "oil12_p50_exWCXY", "fp_year_p50", "lateral_p50", "top_operator", "top_operator_share", "flag"]
            + [c for c in s.columns if c.startswith("d1_puds")]]
    fmt = {"area_sqmi": ",.0f", "oil12_p50": ",.1f", "oil12_p10_high": ",.1f", "oil12_p90_low": ",.1f", "oil24_p50": ",.1f", "bo_ft_p50": ",.0f",
           "oil12_p50_exWCXY": ",.1f", "fp_year_p50": ".0f", "lateral_p50": ",.0f", "top_operator_share": ".0%"}
    sens = ctx["sens"]
    parts = [
        "<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>WCA TC areas</title>",
        (f"<style>{_CSS} #map{{height:780px}} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}} .albl{{font:10px/1.15 sans-serif;text-align:center;color:#111827;text-shadow:0 0 3px #fff,0 0 3px #fff}} "
        "#legend span{display:inline-block;width:18px;height:10px;margin:0 3px 0 8px;vertical-align:middle;border:1px solid #e5e7eb}</style></head><body>"),
        f"<h1>BOX step 4 — TC areas on WCA (Delaware), {len(r['geoms'])} areas</h1>",
        (f"<div class=meta>built {summ['built_at']} · extent of record box.extent id {ext['extent_id']} (WCA v{ext['version']} {ext['source']}, {ext['area_sqmi']:,.1f} sq mi) · "
        f"well set docs/box/step1-2026-10-06/wells_final_WCA.csv (WCA_1 + WCA_2 pooled, WCXY one-way; D19/D20) minus docs/box/exclusions.csv ({summ['n_excluded']} wells) · data through {summ['asof']} · read-only</div>"),
        ("<div class='flag'>Response = Novi WellDetails cum-12 / cum-24 oil per lateral ft (calendar months from first production). Vintage is normalized <b>by filter only</b> "
        "(first prod ≥ 2016-01-01, lateral 6,000–13,000 ft); operator / completion confounding is accepted for v1 and NOT removed (D9). Percentiles are SPE: P10 = HIGH. "
        "bo/ft = Novi 30-yr oil EUR (vendor horizon, not the 50-yr technical EUR) — a screen, shown for the gut check only.</div>"),
        ("<h2>Area map</h2><div class=meta>Click an area for its card. Colour = area P50 of the selected response (5th–95th percentile of area values stretched over the ramp). "
        "Labels: area no, P50 bbl/ft, n wells behind that number.</div>"),
        ("<div><label><input type=radio name=metric value=oil12 checked> 12-mo oil/ft (built on)</label> "
        "<label><input type=radio name=metric value=oil24> 24-mo oil/ft</label> <label><input type=radio name=metric value=bo> Novi 30-yr EUR/ft</label></div>"),
        ("<div>areas: " + " ".join(f"<label><input type=radio name=level value={k}{' checked' if k == pick['k_1se'] else ''}> k = {k}{' (pick)' if k == pick['k_1se'] else ' (CV minimum)' if k == pick['k_min'] else ''}</label>" for k in ctx["levels"]) + "</div>"
        "<div class=meta>Levels are nested: every coarser area is a union of finer ones (one merge sequence). Cards and the table below are for the pick.</div>"),
        "<div id=legend class=meta></div><div id=map></div>",
        "<h2>Gut-check maps</h2>",
        f"<img src='{ctx['gut_png']}'>",
        "<h2>How many areas, and why</h2>",
        (f"<div class=meta>Method: contiguity-constrained Ward agglomeration of 1-mi hex cells ({r['n_cells']:,} cells tiling the extent) on log(12-mo oil/ft) of the "
        f"{r['n_wells']:,} D9 cohort wells, D9 floor of {ctx['params'].min_wells} wells per area met before any free merge. "
        "The number of areas is chosen by 5-fold cross-validation on 3-mi blocks: every fold rebuilds the areas without the held-out blocks and predicts each held-out well by "
        "its area's training median — the PUD situation (ground the areas never saw). Pick = smallest k whose CV error is within one <b>paired</b> standard error of the CV minimum (same held-out wells at both k, differences summed per 3-mi block, SE over blocks).</div>"),
        f"<img src='{ctx['cv_png']}'>",
        (f"<p><b>Pick k = {pick['k_1se']}</b> (CV minimum at k = {pick['k_min']}). Held-out R² at the pick {float(cv.loc[cv.k == pick['k_1se'], 'r2'].iloc[0]):.2f}; "
        f"one pool median (k = 1) {float(cv.loc[cv.k == 1, 'r2'].iloc[0]):.2f}; a local 15-well median with no areas at all {knn_r2:.2f}. "
        f"In-sample, the {len(r['geoms'])} areas explain {r['r2_in']:.0%} of the well-to-well variance in log(12-mo oil/ft).</p>"),
        "<h3>Sensitivity to the geometry knobs</h3><div class=meta>Cell size and the smoothing kNN only steer where boundaries can run. The k pick is NOT stable across them — the CV curve is flat past ~14 areas, so read the held-out R² columns (they barely move), not k.</div>",
        _table(sens, {"cv_mse_at_pick": ".4f", "cv_r2_at_pick": ".3f", "cv_r2_min": ".3f", "knn_local_cv_r2": ".3f", "cell_mi": ".1f"}),
        f"<p class=meta>24-mo response, same cells, its own cohort (n = {ctx['cv24']['n']:,}): pick k = {ctx['cv24']['k_1se']} (CV minimum {ctx['cv24']['k_min']}), held-out R² {ctx['cv24']['cv_r2_at_pick']:.2f}.</p>",
        ("<h2>Areas</h2><div class=meta>n12 / n24 / n_eur = wells behind each column (populations differ). oil per ft in bbl/ft. members = formation_blueox tags of the 12-mo cohort "
        "(D19: WCA_1 / WCA_2 split happens at the curve step; D20: WCXY counted one-way). D1 PUDs = remaining_pud ∪ conflict ∪ not-yet-reconciled Novi PUD sticks ≥ 50 % inside the extent, "
        "to the max-overlap area (count only; no RES/UPSIDE).</div>"),
        _table(tab, fmt),
        (f"<p class=meta>Cohort wells outside the extent (midpoint): {summ['n_c12_outside']:,} of {summ['n_c12_all']:,} (excluded, D9 'inside the extent'). "
        f"Excluded by docs/box/exclusions.csv before anything else: {summ['n_excluded']} wells ({summ['n_excluded_cohort']} in the D9 cohort) — "
        "El Campeon / Los Vaqueros (Permian Resources) state-line program, Novi allocation defect (Michael 2026-10-09).</p>"),
        _MAP_JS.replace("__DATA__", json.dumps(ctx["map"], separators=(",", ":"), default=lambda o: None)),
        "</body></html>",
    ]
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------


def run(conn: Any, wells_dir: Path, out: Path, p: ta.AreaParams = ta.DEFAULT, puds: bool = True) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    wells, excluded = exclusions.drop(egr.load_final_sets(wells_dir, (POOL,)))
    ext = pull_extent(conn)
    d = prepare(wells, pull_extra(conn, list(wells["api10"])), ext["geom_ft"])
    r = regionalize(ext["geom_ft"], d, p)
    d["area_no"] = assign_area(d, r["geoms"])
    pdf = None
    if puds:
        b = eg.to_lonlat([ext["geom_ft"]])[0].bounds
        pdf = pud_areas(er.pull_puds(conn, list(PUD_BENCHES), b), ext["geom_ft"], r["geoms"])
    s = area_stats(d, r["geoms"], pdf)
    levels: dict[int, dict[str, Any]] = {}
    pk = r["pick"]
    for k in sorted({*LEVELS, pk["k_1se"], pk["k_min"]}):
        if k > len(r["parts"]):
            continue
        if k == pk["k_1se"]:
            levels[k] = {"geoms": r["geoms"], "stats": s}
            continue
        g, _ = ta.dissolve(r["cells"], r["parts"][k - 1], r["centres"])
        dk = d.assign(area_no=assign_area(d, g))
        pk_ = None if pdf is None else pud_areas(pdf.drop(columns=["area_no", "bench_grp"]), ext["geom_ft"], g)
        levels[k] = {"geoms": g, "stats": area_stats(dk, g, pk_)}
    sens = sensitivity(ext["geom_ft"], d, p)
    cv24 = response_cv_24(ext["geom_ft"], d, p)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    coh = d[d["cohort"].astype(bool)]
    summ = {"built_at": built, "asof": str(d.attrs["asof"]), "extent_id": ext["extent_id"], "extent_version": ext["version"], "params": asdict(p),
            "n_areas": len(r["geoms"]), "pick": r["pick"], "n_cells": r["n_cells"], "n_c12": int(d.c12.sum()), "n_c24": int(d.c24.sum()), "n_ceur": int(d.ceur.sum()),
            "n_excluded": len(excluded), "n_excluded_cohort": int(excluded["cohort"].sum()), "excluded_api10": sorted(excluded["api10"]),
            "n_c12_all": int((coh["oil12_ft"] > 0).sum()), "n_c12_outside": int(((coh["oil12_ft"] > 0) & ~coh["inside"]).sum()),
            "r2_in": r["r2_in"], "cv_r2_pick": float(r["cv"]["cv"].loc[r["cv"]["cv"].k == r["pick"]["k_1se"], "r2"].iloc[0]),
            "cv_r2_k1": float(r["cv"]["cv"].loc[r["cv"]["cv"].k == 1, "r2"].iloc[0]), "knn_local_cv_r2": 1.0 - r["cv"]["knn_mse"] / r["cv"]["var"],
            "cv24": cv24, "pool_oil12_p50": float(d.loc[d.c12, "oil12_ft"].median()),
            "area_rank_agreement_spearman": {
                "oil12_vs_oil24": float(s[["oil12_p50", "oil24_p50"]].corr(method="spearman").iloc[0, 1]),
                "oil12_vs_bo_ft": float(s[["oil12_p50", "bo_ft_p50"]].corr(method="spearman").iloc[0, 1])},
            "d1_puds_inside": None if pdf is None else {k: int(v) for k, v in pdf[pdf.area_no > 0].groupby("bench_grp").size().items()}}
    summ["levels"] = {str(k): {"n_areas": len(L["geoms"]), "n_pad_scale": int((L["stats"].area_sqmi < PAD_SQMI).sum()),
                                "n_one_operator": int((L["stats"].top_operator_share >= OP_DOM).sum()),
                                "min_n12": int(L["stats"].n12.min()), "median_n12": float(L["stats"].n12.median())} for k, L in levels.items()}
    ctx = {"r": r, "stats": s, "extent": ext, "summary": summ, "sens": sens, "cv24": cv24, "params": p, "levels": list(levels),
           "gut_png": gut_check_png(r["geoms"], s, ext["geom_ft"]), "cv_png": cv_png(r["cv"]["cv"], r["pick"], summ["knn_local_cv_r2"]),
           "map": map_data(ext, r, levels, pk["k_1se"], d)}
    (out / f"areas_{POOL}.html").write_text(render_page(ctx), encoding="utf-8")
    s.to_csv(out / f"areas_{POOL}.csv", index=False)
    pd.concat([L["stats"].assign(k=k) for k, L in levels.items()]).to_csv(out / f"areas_levels_{POOL}.csv", index=False)
    r["cv"]["cv"].to_csv(out / f"cv_{POOL}.csv", index=False)
    sens.to_csv(out / f"sensitivity_{POOL}.csv", index=False)
    d.loc[d.c12 | d.c24 | d.ceur, ["api10", "well_name", "operator", "formation_blueox", "first_production_date", "lateral_length_ft", "oil12_ft", "oil24_ft", "bo_ft",
                                    "eur_src", "c12", "c24", "ceur", "area_no"]].to_csv(out / f"wells_area_{POOL}.csv", index=False)
    feats = [{"type": "Feature", "properties": {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in rr.items()},
              "geometry": shapely.geometry.mapping(shapely.set_precision(g, 1e-6))}
             for g, rr in zip(eg.to_lonlat(r["geoms"]), s.to_dict("records"))]
    (out / f"areas_{POOL}_v1.geojson").write_text(json.dumps({"type": "FeatureCollection", "name": f"box_tc_area_{POOL}_v1", "crs_note": "EPSG:4326",
                                                               "extent_id": ext["extent_id"], "features": feats}), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str), encoding="utf-8")
    return {"summary": summ, "stats": s, "r": r, "extent": ext, "frame": d}
