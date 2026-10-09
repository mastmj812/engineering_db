"""BOX step 3 — review pages (Michael's surface for the extents before they go to geology)."""

from __future__ import annotations

import json
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box import edge_gap as eg
from box import extent_package as pkg
from box.edge_gap_report import _CSS, _lonlat_coords, _png, _table

_MAP_JS = """
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D = __DATA__;
const map = L.map('map', {preferCanvas: true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {maxZoom: 16, attribution: 'Tiles &copy; Esri'}).addTo(map);
const ll = c => c.map(p => [p[1], p[0]]);
const esc = s => String(s ?? '').replace(/[&<>]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[ch]));
const poly = (P, o) => L.polygon(P.map(ll), o);
const extent = L.layerGroup(D.extent.map(P => poly(P, {color: '#a16207', weight: 0.6, fillColor: '#fde68a', fillOpacity: 0.35, interactive: false}))).addTo(map);
const core = L.layerGroup(D.core.map(P => poly(P, {color: '#1e3a8a', weight: 0.6, fill: false, interactive: false})));
const outline = L.layerGroup(D.outline.map(P => poly(P, {color: '#6b7280', weight: 1, dashArray: '4 4', fill: false, interactive: false})));
const sopa = L.layerGroup(D.sopa.map(P => poly(P, {color: '#0ea5e9', weight: 1.5, fillColor: '#0ea5e9', fillOpacity: 0.08, interactive: false}))).addTo(map);
const updip = L.layerGroup(D.updip.map(P => poly(P, {color: '#7c3aed', weight: 1.2, dashArray: '3 3', fillColor: '#7c3aed', fillOpacity: 0.07, interactive: false}))).addTo(map);
const old = L.layerGroup(D.old.map(c => L.polyline(ll(c), {color: '#9ca3af', weight: 1, interactive: false}))).addTo(map);
const ev = L.layerGroup(D.ev.map(c => L.polyline(ll(c), {color: '#1e3a8a', weight: 0.8, interactive: false}))).addTo(map);
const so = L.layerGroup(D.so.map(s => L.polyline(ll(s.c), {color: s.in ? '#c026d3' : '#111827', weight: 3}).bindPopup(
  `<b>${esc(s.name)}</b><br>api10 ${s.api10} · ${esc(s.op)}<br>first prod ${s.fp} · ${s.side}, ${s.dist} mi out<br>12-mo oil/ft ${s.pr ?? '–'}× interior<br><b>${esc(s.role)}</b>`))).addTo(map);
const edges = L.layerGroup(D.edges.map(e => L.polyline(ll(e.c), {color: e.col, weight: 4, opacity: 0.95}).bindPopup(
  `<b>${esc(e.rule)}</b><br>buffer ${e.buf.toLocaleString()} ft · side ${e.side}<br>edge ${e.cls}${e.gap ? ' · gap ' + e.gap.toLocaleString() + ' ft' : ''} · perf ${e.pc} (${e.pr ?? '–'}×)` +
  (e.flag ? `<br><span style="color:#b45309">${esc(e.flag)}</span>` : '')))).addTo(map);
const holes = L.layerGroup(D.holes.map(h => L.circleMarker([h.lat, h.lon], {radius: 6, color: h.fill ? '#15803d' : '#a16207', weight: 2, fillOpacity: 0.6}).bindPopup(
  `<b>${h.fill ? 'void FILLED (D26 / D27)' : 'hole'}</b> ${h.a} sq mi · ${h.sopa}% in the potash area · ${h.cov}% covered by pre-2016 laterals`))).addTo(map);
L.control.layers(null, {'extent (generated)': extent, 'drilled core': core, 'step-2 outline (measuring, dashed)': outline, 'BLM Secretary\\'s Potash Area': sopa, 'updip of the depth limit': updip,
  'pre-2016 laterals': old, '≥2016 laterals': ev, 'step-outs (magenta in / black out)': so, 'extent edge by rule': edges, 'holes': holes}, {collapsed: false}).addTo(map);
const bounds = L.latLngBounds(D.extent.flatMap(P => ll(P[0])));
map.fitBounds(bounds);
window.addEventListener('load', () => { map.invalidateSize(); map.fitBounds(bounds); });
</script>
"""


def _rings_ll(mp: Any, tol: float = 1e-5) -> list[list[list[list[float]]]]:
    return [[_lonlat_coords(g.exterior.simplify(tol))] + [_lonlat_coords(h.simplify(tol)) for h in g.interiors] for g in eg._as_multi(mp).geoms]


def map_data(b: dict[str, Any], sopa_ll: Any) -> dict[str, Any]:
    pr = b["prep"]
    ev, old, so = pr.r["ev"], pr.r["old"], pr.stepouts

    def lines(geoms: list[Any]) -> list[list[list[float]]]:
        return [_lonlat_coords(g) for g in eg.to_lonlat([x.simplify(150.0) for x in geoms])]

    so_ll = lines([ev.geom.iat[int(i)] for i in so.ix])
    sos = []
    for (_, s), c in zip(so.iterrows(), so_ll):
        sos.append({"c": c, "in": s.role == "island", "role": s.role, "name": s.well_name, "api10": s.api10, "op": s.operator, "fp": str(s.first_production_date),
                    "side": s.side, "dist": round(float(s.dist_mi), 1), "pr": None if not np.isfinite(s.perf_ratio) else round(float(s.perf_ratio), 2)})
    edges = []
    for (_, e), g in zip(b["edges"].iterrows(), eg.to_lonlat(list(b["edges"].geom))):
        edges.append({"c": _lonlat_coords(g.simplify(1e-5)), "col": pkg.RULE_COLOURS.get(e.rule, "#000"), "rule": e.rule, "buf": round(float(e.buffer_ft)), "side": e.side, "cls": e.edge_class,
                      "gap": None if not np.isfinite(e.gap_ft) or e.gap_ft == 0 else round(float(e.gap_ft)), "pc": e.perf_class,
                      "pr": None if not np.isfinite(e.perf_ratio) else round(float(e.perf_ratio), 2), "flag": e.flag})
    holes = [{"lat": round(h.lat, 5), "lon": round(h.lon, 5), "a": round(h.area_sqmi, 1), "sopa": round(100 * h.sopa_share), "cov": round(100 * h.legacy_cover), "fill": bool(h.filled_D26 or h.filled_D27)}
             for h in b["holes"].itertuples()]
    main = [g for g in pr.r["outline"].geoms if g.equals(pr.r["body"])] or [pr.r["body"]]
    return {
        "extent": _rings_ll(eg.to_lonlat([b["extent"]])[0]),
        "core": _rings_ll(eg.to_lonlat([pr.core.simplify(100.0)])[0]),
        "outline": _rings_ll(eg.to_lonlat(main)[0]),
        "sopa": _rings_ll(sopa_ll) if sopa_ll is not None else [],
        "updip": _rings_ll(eg.to_lonlat([b["updip"].simplify(200.0)])[0]) if b.get("updip") is not None and not b["updip"].is_empty else [],
        "old": lines(list(old.geom)),
        "ev": lines(list(ev.geom)),
        "so": sos,
        "edges": edges,
        "holes": holes,
    }


# ----------------------------------------------------------------------------
# Calibration evidence
# ----------------------------------------------------------------------------


def frontier_png(g: pd.DataFrame, pick: dict[str, Any]) -> str:
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2))
    rule = g[~g.uniform]
    uni = g[g.uniform]
    for ax, ycol, lab in ((axs[0], "tpr", "share of later PERFORMING wells inside"), (axs[1], "j", "J = TPR − FPR (rolled)")):
        ax.scatter(rule.added_sqmi, rule[ycol], s=12, c=np.where(rule.floor_ft >= 880, "#f97316", "#fdba74"), label="rule configs (pale = floor 660, ineligible)")
        ax.plot(uni.sort_values("added_sqmi").added_sqmi, uni.sort_values("added_sqmi")[ycol], "-o", color="#111827", ms=4, label="flat buffer baseline (660 … 5,280 ft)")
        ax.scatter([pick["added_sqmi"]], [pick[ycol]], s=120, facecolor="none", edgecolor="#b91c1c", lw=2, label="chosen")
        ax.set_xlabel("added area beyond the core, sq mi (2 pools × 2 cutoffs, summed)")
        ax.set_ylabel(lab)
        ax.grid(alpha=0.3)
    axs[0].legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    return _png(fig, dpi=85)


def predict_tables(w: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Later wells (scored + hole infill, 12-mo known): does where they landed predict performance?"""
    k = w[w.known & w.outside_core & (w.dist_ft <= 3 * eg.FT_PER_MI)].copy()
    k["good"] = k.perf_ratio >= 0.70  # over every later well with a 12-mo, incl. hole infill (not scored in J)
    k["band"] = pd.cut(k.dist_ft / eg.FT_PER_MI, [-0.01, 0.25, 0.5, 1, 1.5, 3], labels=["≤ ¼ mi", "¼–½", "½–1", "1–1½", "1½–3"])

    def agg(d: pd.DataFrame, by: list[str]) -> pd.DataFrame:
        x = d.groupby(by, observed=True).agg(wells=("good", "size"), share_performing=("good", "mean"), median_oil_ratio=("perf_ratio", "median")).reset_index()
        return x

    gapw = k[k.edge_kind == "gap"].copy()
    gapw["gap band"] = pd.cut(gapw.edge_gap_ft, [0, 1320, 2640, 5280, 1e9], labels=["< ¼ mi", "¼–½ mi", "½–1 mi", "> 1 mi"])
    return {
        "by edge class": agg(k, ["edge_kind", "edge_perf"]),
        "by distance": agg(k[~k.in_hole], ["band"]),
        "by gap length": agg(gapw, ["gap band"]),
        "front vs not": agg(k[~k.in_hole], ["front_side"]),
        "by pool": agg(k, ["pool", "in_hole"]),
    }


def calibration_html(ctx: dict[str, Any]) -> str:
    g, pick, infos, abl, wells = ctx["grid"], ctx["pick"], ctx["infos"], ctx["ablation"], ctx["wells"]
    info_tab = pd.DataFrame([{k: v for k, v in i.items() if k not in ("wells",)} | {"fronts": ", ".join(f"{s} ({v['ok']} ok / {v['rolled']} rolled)" for s, v in i["fronts"].items()) or "none"} for i in infos])
    cols = ["k", "cap_ft", "floor_ft", "perf_ref", "hit_good", "n_good", "hit_rolled", "n_rolled", "tpr", "fpr", "j", "precision", "added_sqmi"]
    fmt = {"tpr": ".3f", "fpr": ".3f", "j": ".3f", "precision": ".3f", "added_sqmi": ",.0f", "cap_ft": ",.0f", "floor_ft": ",.0f", "flat buffer ft": ",.0f",
           "hit_good": ",.0f", "n_good": ",.0f", "hit_rolled": ",.0f", "n_rolled": ",.0f"}
    top = g[~g.uniform].head(15)[cols]
    uni = g[g.uniform][["floor_ft", "hit_good", "n_good", "hit_rolled", "n_rolled", "tpr", "fpr", "j", "precision", "added_sqmi"]].rename(columns={"floor_ft": "flat buffer ft"}).sort_values("flat buffer ft")
    pt = predict_tables(wells)
    parts = [
        "<h2 id=calib>Calibration: k, cap, floor (WCA + BS2_S together, time-split backtest)</h2>",
        ("<div class=meta>For cutoffs T = 2021-01-01 and 2023-01-01 the step-2 metric (r = ½ mi, c = ¾ mi) is rebuilt from the pool laterals online before T, with 12-mo oil known only when 12 "
        "months had elapsed by T. Every config is scored on the wells online at/after T whose lateral sits ≥ 50 % outside the T core and within 3 mi of it, excluding infill of holes that were open at T. "
        "A well is <i>performing</i> at ≥ 0.70 × the T interior median 12-mo oil/ft (the 2×2 rolled threshold), <i>rolled</i> below it; wells without a cohort 12-mo are not scored. "
        "Captured = ≥ 50 % of the lateral inside the would-be extent. J = share of performing wells captured − share of rolled wells captured. "
        f"Selection rule (fixed before the run): best pooled J among configs with floor ≥ {ctx['min_floor']:,.0f} ft (next-row rule), §6 pool-wide reference unless local wins by > 0.02; "
        "ties within 0.02 go to the smaller added area.</div>"),
        _table(info_tab, {"interior_median": ",.0f", "core_sqmi": ",.0f"}),
        (f"<div class='flag ok'><b>Chosen:</b> k = {pick['k']:g}, cap = {pick['cap_ft']:,.0f} ft, floor = {pick['floor_ft']:,.0f} ft (rolled) / {1.5 * pick['floor_ft']:,.0f} (unknown) / "
        f"{2 * pick['floor_ft']:,.0f} (strong), perf reference = {pick['perf_ref']} — J {pick['j']:.3f}, captures {pick['tpr']:.0%} of later performing wells vs {pick['fpr']:.0%} of rolled ones "
        f"(precision {pick['precision']:.2f}), {pick['added_sqmi']:,.0f} sq mi added summed over the four backtests. Best pool-reference J {pick['best_j_pool']:.3f}, best local {pick['best_j_local']:.3f}.</div>"),
        f"<img src='{ctx['frontier_png']}'>",
        "<h3>Top rule configs (pooled)</h3>" + _table(top, fmt),
        "<h3>Flat-buffer baselines</h3>" + _table(uni, fmt),
        "<h3>Ablation at the chosen k / cap / floor: which term earns it</h3>"
        "<div class=meta>Same config scored with the live-front term switched off (every other clause unchanged), per pool, summed over cutoffs.</div>" + _table(abl, fmt),
        "<h3>Does the edge predict the next well? (later wells, 12-mo known, outside the T core within 3 mi)</h3>",
        "<div class=meta>Share performing = 12-mo oil/ft ≥ 0.70 × T interior median. Median oil ratio = later well ÷ T interior median. Grain: wells (one lateral per api10), both cutoffs pooled.</div>",
    ]
    for name, t in pt.items():
        parts.append(f"<h3>{name}</h3>" + _table(t, {"share_performing": ".2f", "median_oil_ratio": ".2f"}))
    eb = ctx.get("env_bt")
    if eb is not None and len(eb):
        parts.append("<h3 id=envbt>D27 check: the chosen config built as a polygon at each cutoff, before vs after the development envelope</h3>"
                     "<div class=meta>Later wells >= 50 % outside the T core and within 3 mi of it, 12-mo known (hole infill included this time; the envelope fills holes). "
                     "The envelope is a development statement, not a performance screen: it is expected to capture more of both.</div>"
                     + _table(eb[["pool", "cutoff", "construction", "area_sqmi", "n_good", "hit_good", "n_rolled", "hit_rolled", "tpr", "fpr", "j"]],
                              {"area_sqmi": ",.0f", "tpr": ".2f", "fpr": ".2f", "j": ".3f"}))
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------


def pool_page(pool: str, b: dict[str, Any], ctx: dict[str, Any]) -> str:
    st = b["stats"]
    bp = ctx["bp"]
    seg = b["seg"]
    by_rule = seg.groupby("rule").agg(walked_mi=("length_ft", lambda x: x.sum() / eg.FT_PER_MI), segments=("rule", "size"), buffer_ft_median=("buffer_ft", "median"),
                                      buffer_ft_max=("buffer_ft", "max")).reset_index().sort_values("walked_mi", ascending=False)
    by_side = pd.DataFrame([
        {
            "side": s,
            "walked_mi": x.length_ft.sum() / eg.FT_PER_MI,
            "buffer_ft_weighted": np.average(x.buffer_ft, weights=x.length_ft),
            "pinned_strong_mi (flag)": x.loc[(x.kind == "pinned") & (x.perf_used == "strong"), "length_ft"].sum() / eg.FT_PER_MI,
            "front": s in st["fronts"],
            "potash_mi": x.loc[x.in_sopa, "length_ft"].sum() / eg.FT_PER_MI,
        }
        for s in eg.SECTORS
        if len(x := seg[seg.side == s])
    ])
    by_class = seg.groupby(["kind", "perf_used"]).agg(walked_mi=("length_ft", lambda x: x.sum() / eg.FT_PER_MI), buffer_ft_median=("buffer_ft", "median")).reset_index()
    flagged = seg[(seg.kind == "pinned") & (seg.perf_used == "strong")].sort_values("length_ft", ascending=False)
    flag_tab = flagged[["seg_no", "side", "length_ft", "name_a", "perf_ratio", "buffer_ft"]].rename(columns={"length_ft": "pinned run ft", "name_a": "pinning lateral"})
    so = b["prep"].stepouts.sort_values(["role", "side", "dist_mi"])
    so_tab = so[["role", "side", "dist_mi", "api10", "well_name", "operator", "first_production_date", "class", "perf_ratio"]]
    holes = b["holes"].drop(columns=["geom"])
    puds = ctx["puds"].get(pool, pd.DataFrame())
    data = json.dumps(map_data(b, ctx["sopa_ll"]), separators=(",", ":"))
    fr = st["fronts"]
    front_txt = "; ".join(f"<b>{s}</b>: {v['ok']} performing / {v['rolled']} rolled / {v['no12']} too new step-outs within {bp.stepout_reach_mi:g} mi (performing median {v['perf_median']:.2f}× interior)" for s, v in fr.items()) or "none"
    parts = [
        f"<!doctype html><html><head><meta charset=utf-8><title>BOX step 3 — extent {pool}</title><style>{_CSS}</style></head><body>",
        f"<h1>BOX step 3 — extent: Delaware {pool} (v{ctx['version']}, generated)</h1>",
        (f"<div class=meta>Grain: one lateral per api10; gate-1 final set <code>wells_final_{pool}.csv</code>. Evidence = first prod ≥ 2016 (n = {st['n_evidence']:,}); pre-2016 n = {st['n_pre2016']:,} "
        f"(negative evidence only). Extent = drilled core (step-2 outline eroded by r = ½ mi back onto the laterals, D21) + per-segment buffer: k = {bp.k:g}, cap = {bp.cap_ft:,.0f} ft, "
        f"floor {bp.floor_ft:,.0f} / {1.5 * bp.floor_ft:,.0f} / {2 * bp.floor_ft:,.0f} ft (pinned rolled / unknown / strong), perf reference = {bp.perf_ref} interior median "
        f"({st['interior_median_oil12_kft']:,.0f} bbl / 1,000 ft, 12-mo calendar oil as Novi computed it, D9 cohort, median). Built {ctx['built']}. Read-only — nothing written to the warehouse.</div>"),
        ("<div class=toc><a href=index.html>← index</a><a href=#themap>map</a><a href=#numbers>numbers</a><a href=#rules>by rule</a><a href=#sides>by side</a><a href=#flags>geology flags</a>"
        "<a href=#stepouts>step-outs</a><a href=#holes>holes</a><a href=#puds>PUD universe</a><a href=index.html#calib>calibration</a></div>"),
        "<h2 id=numbers>Extent</h2>" + _table(pd.DataFrame([{
            "extent sq mi": st["extent_sqmi"], "drilled core sq mi": st["core_sqmi"], "step-2 outline sq mi (measuring)": st["outline_step2_sqmi"], "parts": st["n_parts"],
            "holes kept": st["n_holes"], "extent perimeter mi": st["perimeter_mi"], "buffer ft, perimeter-weighted mean": st["buffer_ft_weighted_mean"], "buffer ft, median segment": st["buffer_ft_median"],
            "pinned+strong flagged mi": st["flagged_pinned_strong_mi"]}]), {"extent sq mi": ",.0f", "drilled core sq mi": ",.0f", "step-2 outline sq mi (measuring)": ",.0f", "extent perimeter mi": ",.0f",
                                                                            "buffer ft, perimeter-weighted mean": ",.0f", "buffer ft, median segment": ",.0f", "pinned+strong flagged mi": ",.1f"}),
        (f"<div class='flag'><b>Live fronts (D22 rule, detected from the step-out table):</b> {front_txt}. Front sides are buffered at the cap.</div>"
        f"<div class='flag ok'><b>D27 development envelope (Michael 2026-10-09):</b> developed is always in; gaps between development trends narrower than {bp.bridge_mi:g} mi are bridged; no interior voids; "
        f"evidence governs reach beyond the outermost development only. Buffered extent before the envelope {st['pre_envelope_sqmi']:,.0f} sq mi, envelope {st['extent_sqmi']:,.0f} sq mi "
        f"({st['bridged_sqmi']:,.0f} sq mi bridged or filled; {st['bridge_edge_mi']:,.0f} mi of edge placed by a bridge). "
        f"Updip depth limit: {('2BS top ' + format(st['updip_limit'][1], ',.0f') + ' ft') if st['updip_limit'] else 'none'}. "
        f"Edge generalized ({bp.gen_tol_mi:g}-mi simplification, bulges where a developed lateral would fall out, {bp.gen_round_mi:g}-mi rounding): raw envelope {st['envelope_raw_sqmi']:,.0f} sq mi. "
        f">= 2016 laterals outside the extent: {st['developed_outside']} (all step-out tests: {st['n_isolated_tests']}, of which {st['n_tests_within_reach']} are 1-2-well tests within {bp.bridge_mi:g} mi; other {st['developed_outside_not_isolated']}).</div>"),
        "<h2 id=themap>Map</h2><div class=lg>" + "".join(f"<span style='background:{c}'></span>{r}" for r, c in pkg.RULE_COLOURS.items() if r in set(b['edges'].rule)) + "</div>",
        "<div id=map></div><div class=meta>Edge colour = the clause that set the buffer; click an edge for buffer, gap, performance and the geology flag. Magenta = step-out within the bridging width (developed, in), black = isolated test (out). Violet dashed = updip of the depth limit. Toggle the drilled core and the step-2 measuring outline top-right.</div>",
        f"<details><summary>static overview (the legend PNG shipped to geology)</summary><img src='geology/BOX_{pool}_legend.png'></details>",
        "<h2 id=rules>Perimeter by buffer rule (walked ring)</h2>" + _table(by_rule, {"walked_mi": ",.1f", "buffer_ft_median": ",.0f", "buffer_ft_max": ",.0f"}),
        "<h3>By 2×2 class</h3>" + _table(by_class, {"walked_mi": ",.1f", "buffer_ft_median": ",.0f"}),
        "<h2 id=sides>By side</h2>" + _table(by_side, {"walked_mi": ",.1f", "buffer_ft_weighted": ",.0f", "pinned_strong_mi (flag)": ",.1f", "potash_mi": ",.1f"}),
        f"<h2 id=flags>Geology flags: pinned edge with strong wells ({len(flagged):,} runs, {st['flagged_pinned_strong_mi']:,.1f} mi)</h2>"
        "<div class=meta>The plan's \"pinned + strong → tight + flag for geology\": the edge is drilled up to and the last wells perform ≥ 0.85× interior, so performance does not explain the stop. Longest first.</div>"
        + _table(flag_tab, {"pinned run ft": ",.0f", "perf_ratio": ".2f", "buffer_ft": ",.0f"}, max_rows=60),
        f"<h2 id=stepouts>Step-outs ({len(so):,}): development in, tests out</h2>"
        f"<div class=meta>D27: development is always in. Step-outs within {bp.bridge_mi:g} mi are grouped into clusters (laterals within {bp.cluster_link_mi:g} mi of each other); "
        f"a cluster of >= {bp.min_cluster} laterals is development and joins the extent whatever its performance (performance is the TC areas' job). "
        f"1-2-well step-outs and anything beyond {bp.bridge_mi:g} mi are tests: listed in the flags layer, not included.</div>"
        + _table(so_tab, {"dist_mi": ".1f", "perf_ratio": ".2f"}, max_rows=150),
        f"<h2 id=holes>Holes of the step-2 body ({len(holes):,}; {int(holes.filled_D26.sum())} filled by D26, {int(holes.filled_D27.sum())} by D27)</h2><div class=meta><b>D26 (Michael 2026-10-08):</b> a hole ≥ {ctx['bp'].legacy_fill_cover:.0%} covered by the ½-mi footprint of pre-2016 laterals is legacy drilled-up ground — "
        "the bench is proven and full, no room for a modern well — and is filled into the extent (potash holes included; the old wells are still never curve evidence). "
        "<b>D27 (2026-10-09):</b> every other void inside the development envelope is filled too; geology cuts one only for a structural or reservoir reason. "
        "Backtest note: holes open at T were later infilled with wells that performed like the interior.</div>"
        + _table(holes, {"area_sqmi": ",.1f", "sopa_share": ".0%", "legacy_cover": ".0%", "lon": ".4f", "lat": ".4f"}, max_rows=40),
        "<h2 id=puds>D1 PUD universe inside (read-only count)</h2>"
        "<div class=meta>Novi PUD category sticks (no RES/UPSIDE), mapped formation_blueox; inside = ≥ 50 % of the stick length (co-extent overlap, rule 9). D1 universe = remaining_pud ∪ conflict ∪ not-yet-reconciled. "
        "Columns compare the generated extent with the drilled core and the step-2 measuring outline. WCXY PUDs are listed apart (D20: WCXY is WCA evidence one-way; PUD membership is a step-7 call).</div>"
        + (_table(puds, {}) if len(puds) else "<div class=meta>not pulled</div>"),
        _MAP_JS.replace("__DATA__", data),
        "</body></html>",
    ]
    return "\n".join(parts)


_DIFF_JS = """
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D = __DATA__;
const map = L.map('dmap', {preferCanvas: true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {maxZoom: 16, attribution: 'Tiles &copy; Esri'}).addTo(map);
const ll = c => c.map(p => [p[1], p[0]]);
const poly = (P, o) => L.polygon(P.map(ll), o);
const gen = L.layerGroup(D.generated.map(P => poly(P, {color: '#6b7280', weight: 1.2, dashArray: '5 4', fill: false, interactive: false}))).addTo(map);
const edi = L.layerGroup(D.edited.map(P => poly(P, {color: '#1d4ed8', weight: 1.5, fillColor: '#bfdbfe', fillOpacity: 0.15, interactive: false}))).addTo(map);
const pcs = L.layerGroup(D.pieces.map(p => poly(p.c, {color: p.kind === 'added' ? '#15803d' : '#b91c1c', weight: 1, fillOpacity: 0.55}).bindPopup(
  `<b>${p.kind}</b> ${p.a} sq mi · side ${p.side}`))).addTo(map);
L.control.layers(null, {'generated (dashed)': gen, 'geology edited': edi, 'added (green) / removed (red)': pcs}, {collapsed: false}).addTo(map);
const bounds = L.latLngBounds(D.edited.concat(D.generated).flatMap(P => ll(P[0])));
map.fitBounds(bounds);
window.addEventListener('load', () => { map.invalidateSize(); map.fitBounds(bounds); });
</script>
"""


def diff_page(pool: str, version: int, d: dict[str, Any], gen_ft: Any, edi_ft: Any, built: str, src: str, puds: pd.DataFrame | None = None) -> str:
    pieces = pd.DataFrame([{k: v for k, v in p.items() if k != "geom"} for p in d["pieces"]], columns=["kind", "area_sqmi", "side"])
    by_side = pieces.pivot_table(index="side", columns="kind", values="area_sqmi", aggfunc="sum", fill_value=0.0).reset_index() if len(pieces) else pieces
    data = {
        "generated": _rings_ll(eg.to_lonlat([gen_ft])[0]),
        "edited": _rings_ll(eg.to_lonlat([edi_ft])[0]),
        "pieces": [{"c": _rings_ll(eg.to_lonlat([p["geom"]])[0])[0], "kind": p["kind"], "a": round(p["area_sqmi"], 2), "side": p["side"]} for p in d["pieces"]],
    }
    head = pd.DataFrame([{"generated sq mi": d["generated_sqmi"], "edited sq mi": d["edited_sqmi"], "added sq mi": d["added_sqmi"], "removed sq mi": d["removed_sqmi"],
                          "net sq mi": d["edited_sqmi"] - d["generated_sqmi"], "pieces ≥ 0.01 sq mi": len(pieces)}])
    return "\n".join([
        f"<!doctype html><html><head><meta charset=utf-8><title>BOX step 3 — geology diff {pool}</title><style>{_CSS}</style></head><body>",
        f"<h1>BOX step 3 — geology edit vs generated: Delaware {pool} v{version}</h1>",
        f"<div class=meta>Edited file: <code>{src}</code>. Both layers read in NAD83 UTM 14N US-ft, compared in UTM 13N ft. Built {built}. Pieces under 0.01 sq mi (sliver noise from vertex moves) are not listed.</div>",
        _table(head, {c: ",.2f" for c in head.columns if "sq mi" in c}),
        "<div id=dmap style='height:700px;border:1px solid #d1d5db;margin:8px 0'></div>",
        "<h2>By side</h2>" + (_table(by_side, {c: ",.2f" for c in by_side.columns if c != "side"}) if len(pieces) else "<div class=meta>no change</div>"),
        "<h2>Pieces</h2>" + (_table(pieces.sort_values("area_sqmi", ascending=False), {"area_sqmi": ",.2f"}, max_rows=200) if len(pieces) else "<div class=meta>no change</div>"),
        ("<h2>D1 PUD universe: generated vs edited (read-only)</h2>" + _table(puds, {}) if puds is not None and len(puds) else ""),
        _DIFF_JS.replace("__DATA__", json.dumps(data, separators=(",", ":"))),
        "</body></html>",
    ])


def index_page(ctx: dict[str, Any], builds: dict[str, dict[str, Any]]) -> str:
    rows = "".join(
        f"<li><a href=extent_{p}.html>{p}</a> — extent {b['stats']['extent_sqmi']:,.0f} sq mi (core {b['stats']['core_sqmi']:,.0f}), {b['stats']['n_parts']} parts, {b['stats']['n_holes']} holes, "
        f"fronts: {', '.join(b['stats']['fronts']) or 'none'}; flagged pinned+strong {b['stats']['flagged_pinned_strong_mi']:,.0f} mi</li>"
        for p, b in builds.items()
    )
    return "\n".join([
        f"<!doctype html><html><head><meta charset=utf-8><title>BOX step 3 — extents</title><style>{_CSS}</style></head><body>",
        "<h1>BOX step 3 — extents with buffers (Delaware pilot)</h1>",
        f"<div class=meta>Built {ctx['built']}. Read-only. Plan: docs/box_type_curves_plan.md §5 step 3. Gate summary: FINDINGS.md. Geology package: <code>geology/</code> (shapefiles, NAD83 UTM 14N US-ft).</div>",
        f"<ul>{rows}</ul>",
        calibration_html(ctx),
        "</body></html>",
    ])
