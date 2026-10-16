"""BOX step 7c review surface: an index page + one workup page per Novi pad (D65), rendered from the production-run artifact.

Every page carries the disclosure the decisions require: analog cohort P50 per stream (D57, labelled P50), the D62 walk-forward
haircut applied, the method's measured hindcast bias by horizon (D59 condition 3), the package range for the location's analog-radius
class (D69), uptime-free volumes with F(k) published, not applied (D63), no water (D72), technical forecast only (no economics).

Pages are written under <out>/workups (git-ignored runs/); the index + a handful of sample pads are copied into <docs> for review.
The record is the database (box.pud_forecast / _stream / location_analog) — pages are renders of it.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import edge_gap as eg
from box import production as pr
from box.edge_gap_report import _CSS, _table

N_SAMPLE = 6
K_CHART = 48


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:80] or "pad"


def _pct(x: float | None) -> str:
    return "–" if x is None or not np.isfinite(x) else f"{x:+.1%}"


def disclosure_html(run: dict[str, Any], radius_classes: set[str]) -> str:
    d, h = run["disclosure"], run["haircut"]
    rows = []
    for s in pr.STREAMS:
        for k in pr.HORIZONS:
            b = d["hindcast_bias"][s][str(k)]
            rows.append({"stream": s, "horizon": f"cum-{k}", "measured bias (box_v2, all cutoffs)": b["box_v2_pooled_bias"],
                         "packages": b["box_v2_pooled_packages"], "haircut factor applied": h[s][k]["factor"],
                         "after correction, held-out bias": b["box_v2_wf_holdout_bias"]})
    t = pd.DataFrame(rows)
    rr = []
    for key, v in d["radius_ranges"].items():
        rc, hz = key.split("|")
        if rc in radius_classes:
            rr.append({"analog radius": rc, "horizon": hz, "80 % of held-out packages within": f"{v['p90_low']:+.0%} … {v['p10_high']:+.0%}",
                       "packages": v["packages"]})
    return "\n".join([
        ("<div class='flag'><b>How to read this workup.</b> Forecast = the analog cohort's <b>P50</b> per 1,000 ft (deal-intake selection, "
        "same bench, nearest-first, lateral band, representative spacing; D57), scaled to the location's lateral (Cui &amp; Cross efficiency "
        "below 7,500 ft, D50), then corrected by a stated walk-forward haircut (D62): on held-out ground this method historically overstated "
        "oil, and the factor below was applied. Volumes are <b>uptime-free</b> (D63): apply F(k) or a downtime factor, never both. "
        "Oil and gas only — <b>no water</b> in BOX v1 (D72). Technical forecast: no economic limit, EUR = raw 50-yr integral; "
        "no economics anywhere. Error convention: actual / forecast − 1 (negative = the method forecast HIGH).</div>"),
        _table(t, {"measured bias (box_v2, all cutoffs)": "+.1%", "haircut factor applied": ".3f", "after correction, held-out bias": "+.1%"}),
        "<div class=meta>Measured spread for this pad's analog-radius class (D69, holdout-pooled, box_v2_wf):</div>",
        _table(pd.DataFrame(rr), {}) if rr else ""])


def _map_svg(sticks_ft: list[Any], analog_xy: np.ndarray) -> str:
    W = H = 360
    pts = [np.asarray(g.coords) for g in sticks_ft]
    allx = np.concatenate([p[:, 0] for p in pts] + ([analog_xy[:, 0]] if len(analog_xy) else []))
    ally = np.concatenate([p[:, 1] for p in pts] + ([analog_xy[:, 1]] if len(analog_xy) else []))
    x0, x1, y0, y1 = allx.min(), allx.max(), ally.min(), ally.max()
    span = max(x1 - x0, y1 - y0, 5280.0) * 1.08
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def X(x: float) -> float:
        return W / 2 + (x - cx) / span * W

    def Y(y: float) -> float:
        return H / 2 - (y - cy) / span * H

    out = [f"<svg viewBox='0 0 {W} {H}' width='100%' style='max-width:{W}px;border:1px solid #8884' role=img aria-label='pad map'>"]
    for x, y in analog_xy:
        out.append(f"<circle cx={X(x):.1f} cy={Y(y):.1f} r=2.6 fill='#888' fill-opacity=.7 />")
    for p in pts:
        d = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in p)
        out.append(f"<polyline points='{d}' fill=none stroke='#2c6fbb' stroke-width=2.2 stroke-dasharray='6 3' />")
    mi = W * 5280.0 / span
    out.append(f"<line x1=12 y1={H - 14} x2={12 + mi:.1f} y2={H - 14} stroke='currentColor' stroke-width=2 /><text x=12 y={H - 20} font-size=10 fill='currentColor'>1 mi</text>")
    out.append("</svg>")
    return "".join(out)


def _chart_svg(fc: list[np.ndarray], band: tuple[np.ndarray, np.ndarray, np.ndarray] | None, unit: str) -> str:
    W, Hh, pad = 440, 260, 44
    k = K_CHART
    ymax = max([float(np.nanmax(c[:k])) for c in fc] + ([float(np.nanmax(band[2]))] if band is not None and np.isfinite(band[2]).any() else [1.0])) * 1.08

    def X(m: float) -> float:
        return pad + (m - 1) / (k - 1) * (W - pad - 10)

    def Y(v: float) -> float:
        return Hh - pad + 10 - v / ymax * (Hh - pad - 10)

    out = [f"<svg viewBox='0 0 {W} {Hh}' width='100%' style='max-width:{W}px' role=img aria-label='cumulative oil per 1,000 ft'>"]
    if band is not None:
        lo, mid, hi = band
        ok = np.isfinite(lo) & np.isfinite(hi)
        ms = np.arange(1, k + 1)[ok]
        if len(ms) > 1:
            poly = " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in zip(ms, hi[ok], strict=True)) + " " + \
                   " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in zip(ms[::-1], lo[ok][::-1], strict=True))
            out.append(f"<polygon points='{poly}' fill='#888' fill-opacity=.22 />")
            out.append("<polyline points='" + " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in zip(ms, mid[ok], strict=True)) + "' fill=none stroke='#666' stroke-width=1.5 />")
    for c in fc:
        out.append("<polyline points='" + " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in zip(range(1, k + 1), c[:k], strict=True)) + "' fill=none stroke='#2c6fbb' stroke-width=1.4 stroke-opacity=.8 />")
    for t in (12, 24, 36, 48):
        out.append(f"<text x={X(t):.1f} y={Hh - pad + 26} font-size=10 text-anchor=middle fill='currentColor'>{t}</text>")
    for frac in (0.25, 0.5, 0.75, 1.0):
        v = ymax / 1.08 * frac
        out.append(f"<text x={pad - 4} y={Y(v) + 3:.1f} font-size=10 text-anchor=end fill='currentColor'>{v:,.0f}</text>")
    out.append(f"<text x={W / 2} y={Hh - 4} font-size=11 text-anchor=middle fill='currentColor'>months on production · cumulative {unit} per 1,000 ft</text></svg>")
    return "".join(out)


_ESC_A = re.compile(r"&lt;a href=&#x27;([^&]*)&#x27;&gt;(.*?)&lt;/a&gt;")


def _linked(table_html: str) -> str:
    """_table escapes every cell; restore the anchors this module put there (href is a slug path, text is already escaped once)."""
    return _ESC_A.sub(lambda m: f"<a href='{m.group(1)}'>{m.group(2)}</a>", table_html)


def _page(title: str, body: list[str]) -> str:
    return "\n".join([("<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                      f"<title>{html.escape(title)}</title><style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>"),
                      *body, "</body></html>"])


def render(A: dict[str, Any], out: Path, docs: Path) -> int:
    run, u, locs, res = A["run"], A["universe"], A["locs"], A["results"]
    meta = A["analog_meta"].set_index("api10")
    cum = A["analog_cum_kft"]
    by_stick = {loc["stick_id"]: (loc, r) for loc, r in zip(locs, res, strict=True)}
    cov = u[u["coverage"] == "covered"].copy()
    lines = dict(zip(cov["stick_id"], pr.project_ft(list(cov["wkt"])), strict=True))
    wdir = out / "workups"
    wdir.mkdir(parents=True, exist_ok=True)
    pads = []
    for pad, g in cov.groupby(cov["pad_name"].fillna("(no pad)")):
        rows, fc, an_ids = [], [], {}
        for r in g.sort_values("stick_id").itertuples():
            loc, fit = by_stick[int(r.stick_id)]
            st = fit.get("streams", {})
            if "oil" not in st:
                rows.append({"stick_id": int(r.stick_id), "formation": r.formation_blueox, "lateral ft": loc["lateral_ft"], "status": "NO FORECAST", "flags": "; ".join(fit["flags"])})
                continue
            L = loc["lateral_ft"] / 1000.0
            o, gs = st["oil"], st.get("gas")
            rows.append({"stick_id": int(r.stick_id), "formation": r.formation_blueox, "lateral ft": loc["lateral_ft"], "planned spacing ft": loc["planned_spacing_ft"],
                         "spacing source": loc["spacing_source"], "search": fit["search_mode"], "radius mi": fit["radius_mi"],
                         "radius class": pr.radius_class(fit["radius_mi"]), "analogs": fit["n_analogs"],
                         "oil EUR bbl": o["eur"], "oil EUR/kft": o["eur"] / L, "oil cum-12": float(np.sum(o["months"][:12])),
                         "gas EUR mcf": gs["eur"] if gs else np.nan, "oil Di nominal": o["params"]["Di_nominal"], "oil Di eff 1-yr": o["params"]["Di_eff_1yr"],
                         "oil b": o["params"]["b"], "flags": "; ".join(list(fit["flags"]) + pr.bound_flags(st, loc.get("near_pdp_ft")))})
            fc.append(np.cumsum(o["months"]) / L)
            for x in fit["analogs"]:
                an_ids.setdefault(x["api10"], []).append(x["dist_ft"])
        t = pd.DataFrame(rows)
        ids = list(an_ids)
        A_ = np.array([cum["oil"][x][:K_CHART] for x in ids if x in cum["oil"]]) if ids else np.empty((0, K_CHART))
        band = None
        if len(A_) >= 3:
            with np.errstate(all="ignore"):
                cnt = np.isfinite(A_).sum(axis=0)
                q = np.nanpercentile(A_, [10, 50, 90], axis=0)
            q[:, cnt < 3] = np.nan
            band = (q[0], q[1], q[2])
        am = meta.reindex(ids)
        at = pd.DataFrame({"api10": ids, "well": am.get("well_name"), "operator": am.get("operator"), "first production": am.get("first_production_date"),
                           "lateral ft": am.get("lateral_ft"), "nearest dist ft (to a pad location)": [min(an_ids[x]) for x in ids],
                           "used by locations": [len(an_ids[x]) for x in ids]}).sort_values("nearest dist ft (to a pad location)")
        axy = np.column_stack(eg._transformer().transform(am["mid_lon"].to_numpy(float), am["mid_lat"].to_numpy(float))) * eg._M_TO_FT if len(am) else np.empty((0, 2))
        axy = axy[np.isfinite(axy).all(axis=1)] if len(axy) else axy
        rcs = set(t.get("radius class", pd.Series(dtype=str)).dropna())
        slug = _slug(str(pad))
        body = [f"<h1>BOX workup — pad {html.escape(str(pad))}</h1>",
                (f"<div class=meta>Run built {run['built_at']} · spec {pr.SPEC} · code {run['code_sha'][:12]} · blueox-boxfit {run['engine_sha'][:7]} · deal-intake config v{run['dealintake_config']} · "
                f"Novi {', '.join(run['report_version'])} · production through {run['data_through']} · {len(g)} covered WCA locations · {len(ids)} named analogs.</div>"),
                disclosure_html(run, rcs),
                "<h2>Map</h2>", _map_svg([lines[s] for s in g["stick_id"]], axy),
                "<div class=meta>Dashed blue = the pad's proposed BOX locations (Novi sticks); grey dots = the named analogs' lateral midpoints.</div>",
                "<h2>Locations</h2>", _table(t, {"lateral ft": ",.0f", "planned spacing ft": ",.0f", "radius mi": ".1f", "oil EUR bbl": ",.0f", "oil EUR/kft": ",.0f",
                                                 "oil cum-12": ",.0f", "gas EUR mcf": ",.0f", "oil Di nominal": ".2f", "oil Di eff 1-yr": ".0%", "oil b": ".2f"}),
                "<h2>Forecast vs analog actuals (oil)</h2>", _chart_svg(fc, band, "bbl"),
                ("<div class=meta>Blue = each location's forecast cumulative per 1,000 ft (P50 x haircut, uptime-free). Grey = the named analogs' ACTUAL "
                "calendar cumulative per 1,000 ft (P10–P90 band and median; months with ≥ 3 analogs reporting). Calendar actuals carry downtime; "
                "the forecast does not (D63).</div>"),
                "<h2>Named analogs</h2>", _table(at, {"lateral ft": ",.0f", "nearest dist ft (to a pad location)": ",.0f"})]
        (wdir / f"{slug}.html").write_text(_page(f"BOX workup {pad}", body), encoding="utf-8")
        pads.append({"pad": pad, "page": f"workups/{slug}.html", "locations": len(g), "analogs": len(ids),
                     "oil EUR/kft median": float(t["oil EUR/kft"].median()) if "oil EUR/kft" in t else np.nan,
                     "past-5-mi share": float((t.get("radius class") == "past 5 mi").mean()) if "radius class" in t else np.nan,
                     "no forecast": int((t.get("status") == "NO FORECAST").sum()) if "status" in t else 0})
    P = pd.DataFrame(pads).sort_values("locations", ascending=False)
    counts = u["coverage"].value_counts().rename_axis("coverage").reset_index(name="rows")
    hc_rows = [{"stream": s, **{f"cum-{k}": run["haircut"][s][k]["factor"] for k in pr.HORIZONS}} for s in pr.STREAMS]
    if "method" in run["haircut"]:  # D92: the targets above are applied by the C1 rate shape; show what it realises
        hc_rows += [{"stream": f"{s} realised (median)", **{f"cum-{k}": run["haircut"][s][k]["realised_median"] for k in pr.HORIZONS}}
                    for s in pr.STREAMS]
    F_rows = [{"stream": s, **{f"F({k})": run["calendar_factor"][s]["F"][k - 1] for k in pr.HORIZONS}} for s in pr.STREAMS]
    P_link = P.assign(pad=[f"<a href='{p}'>{n}</a>" for n, p in zip(P["pad"], P["page"], strict=True)]).drop(columns=["page"])
    idx = _page("BOX production run", [
        "<h1>BOX production run — analog workups (step 7c)</h1>",
        (f"<div class=meta>Built {run['built_at']} · spec {pr.SPEC} · code {run['code_sha'][:12]} · production through {run['data_through']} · "
        f"analog pool {run['n_pool']:,} WCA wells · harness equivalence {json.dumps(run['equivalence'])}.</div>"),
        "<h2>Coverage (D67 universe)</h2>", _table(counts, {}),
        ("<h2>Haircut: D62 factors (targets) and the D92 C1 realised cum factor</h2>" if "method" in run["haircut"]
                 else "<h2>D62 haircut factors (applied; cum-48 held to month 600)</h2>"), _table(pd.DataFrame(hc_rows), {f"cum-{k}": ".3f" for k in pr.HORIZONS}),
        "<h2>D63 calendar factor F(k) (published, NOT applied)</h2>", _table(pd.DataFrame(F_rows), {f"F({k})": ".3f" for k in pr.HORIZONS}),
        disclosure_html(run, {"5 mi ring", "past 5 mi"}),
        f"<h2>Pads ({len(P)})</h2>", _linked(_table(P_link, {"oil EUR/kft median": ",.0f", "past-5-mi share": ".0%"}))])
    (out / "index.html").write_text(idx, encoding="utf-8")
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "workups").mkdir(exist_ok=True)
    rng = np.random.default_rng(7)
    sample = list(P.head(2)["page"]) + list(P.iloc[rng.choice(len(P), size=min(N_SAMPLE - 2, len(P)), replace=False)]["page"])
    for p in dict.fromkeys(sample):
        shutil.copy(out / p, docs / p)
    keep = set(dict.fromkeys(sample))
    P_doc = P.assign(pad=[f"<a href='{p}'>{n}</a>" if p in keep else str(n) for n, p in zip(P["pad"], P["page"], strict=True)]).drop(columns=["page"])
    fmt = {"oil EUR/kft median": ",.0f", "past-5-mi share": ".0%"}
    (docs / "index.html").write_text(idx.replace(_linked(_table(P_link, fmt)), _linked(_table(P_doc, fmt))), encoding="utf-8")
    P.to_csv(docs / "pads.csv", index=False)
    print(f"rendered {len(P)} pad pages under {wdir}; index + {len(keep)} sample pads in {docs}")
    return 0


