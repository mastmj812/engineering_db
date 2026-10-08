"""handoff.html — the reviewer's picture of what `handoff --apply` will write.

Rendered from handoff_plan.json (dealintake.handoff.plan). Top: status and
anything blocking; the curves = Blue Ox zones in tab order; the narvi
scenarios. Then one card per unit: plan view (kept sticks in their curve's
colour, culled rows dashed grey) + the row table. Nothing here is computed —
the page only shows the plan.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely import wkt as shp_wkt
from shapely.geometry import shape

from dealintake.render.dossier_html import _CSS, _chip, _esc, _Raw, _svg, _table
from dealintake.render.maps import CURVE_COLOR
from dealintake.render.tables import di_pair, num

CULL = "#9ca3af"


def _color_of(P: dict[str, Any]) -> dict[tuple[str, str], str]:
    """(unit label, bench) -> the colour of the curve that applies there."""
    return {(lb, c["bench"]): CURVE_COLOR[i % len(CURVE_COLOR)]
            for i, c in enumerate(P["curves"]) for lb in c["units"]}


def _unit_map(u: dict[str, Any], colors: dict[tuple[str, str], str]) -> str:
    g = shape(u["body"]["parcel"])
    fig, ax = plt.subplots(figsize=(3.6, 3.6))
    for part in getattr(g, "geoms", [g]):
        x, y = part.exterior.xy
        ax.fill(x, y, color="#f3f4f6", ec="#374151", lw=0.8)
    for r in u["rows"]:
        line = shp_wkt.loads(r["wkt"])
        x, y = line.xy
        if r["status"] == "culled":
            ax.plot(x, y, color=CULL, lw=1.2, ls="--")
        else:
            ax.plot(x, y, color=colors.get((u["label"], r["bench"]), "#111827"), lw=2.0,
                    alpha=1.0 if r["status"] == "kept" else 0.4)
    ax.set_aspect(1 / math.cos(math.radians(g.centroid.y)))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(u["dsu"], fontsize=9)
    return _svg(fig)


def _plus_side(u: dict[str, Any]) -> str:
    """Compass side the +offset points to, read off the rows themselves (narvi's
    frame follows its GRID azimuth folded to [0,180): a ~0-deg-true plan folds to
    ~179.4 grid and + flips to WEST — 1-12 on Rally Caps)."""
    pts = [(r["offset_ft"], shp_wkt.loads(r["wkt"]).interpolate(0.5, normalized=True))
           for r in u["rows"] if r.get("offset_ft") is not None]
    if len(pts) < 2:
        return "?"
    (_, a), (_, b) = min(pts, key=lambda p: p[0]), max(pts, key=lambda p: p[0])
    brg = math.degrees(math.atan2((b.x - a.x) * math.cos(math.radians(a.y)), b.y - a.y)) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((brg + 22.5) // 45) % 8]


def _gunbarrel(u: dict[str, Any], colors: dict[tuple[str, str], str]) -> str:
    """Cross-section: narvi gunbarrel offset (ft, +east for N-S laterals) vs TVD —
    stacked benches on the same rows are visible here, not in plan view."""
    fig, ax = plt.subplots(figsize=(3.6, 3.6))
    for r in u["rows"]:
        if r.get("offset_ft") is None:
            continue
        if r["status"] == "culled":
            ax.scatter(r["offset_ft"], r["tvd_ft"], marker="x", color=CULL, s=40, zorder=3)
        else:
            ax.scatter(r["offset_ft"], r["tvd_ft"], color=colors.get((u["label"], r["bench"]), "#111827"),
                       s=40, edgecolors="#111827", linewidths=0.5, zorder=3)
    for b in sorted({r["bench"] for r in u["rows"]}):
        t = next(r["tvd_ft"] for r in u["rows"] if r["bench"] == b)
        ax.annotate(f"{b} {t:,.0f} ft", (0.02, t), xycoords=("axes fraction", "data"), fontsize=7,
                    va="bottom", color="#374151")
    tv = [r["tvd_ft"] for r in u["rows"]]
    if tv:
        ax.set_ylim(max(tv) + 400, min(tv) - 400)
    ax.set_xlabel(f"narvi gunbarrel offset, ft (+ toward {_plus_side(u)})", fontsize=8)
    ax.set_ylabel("TVD, ft", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.3)
    return _svg(fig)


def render(run_dir: Path) -> Path:
    P = json.loads((run_dir / "handoff_plan.json").read_text(encoding="utf-8"))
    colors = _color_of(P)
    ready = P["status"] == "READY"
    out: list[str] = [
        (f'<!doctype html><html><head><meta charset="utf-8"><title>Handoff — {_esc(P["deal"])}</title>'
         f"<style>{_CSS}</style></head><body>"),
        (f"<h1>Handoff — {_esc(P['deal'])} "
         f"{_chip(P['status'], '#059669' if ready else '#dc2626')}</h1>"),
        (f'<p class="meta">Blue Ox codename {_esc(P["codename"])} · run {_esc(P["run_dir"])} · '
         f"config v{_esc(P['config_version'])} · planned {_esc(P['planned_at'][:16])} UTC · "
         "dry run: nothing written</p>"),
    ]
    for b in P["blocked"]:
        out.append(f'<div class="flag bad">{_esc(b)}</div>')
    n_wells = sum(1 for u in P["units"] for r in u["rows"] if r["status"] == "kept")
    n_cull = sum(len(u["body"]["culled_wells"]) for u in P["units"])
    out.append(
        "<h2>What <code>--apply</code> writes</h2><ol>"
        f"<li><b>narvi</b>: {len(P['units'])} scenarios (one per DSU), {n_wells} planned sticks, "
        f"{n_cull} generated row(s) culled by your row rules. narvi rebuilds the sticks from the recipe; "
        "the saved counts are checked against this page.</li>"
        f"<li><b>anduin</b>: {len(P['curves'])} type curves (dossier cohorts, peak_ramp, per lateral ft, Arps), "
        f"deal <b>{_esc(P['deal'])}</b>, curves assigned to it.</li>"
        f"<li><b>anduin Blue Ox config</b>: {len(P['blueox_zones'])} zones in the tab order below, "
        f"{len(P['narvi_selections'])} narvi scenarios pinned. Codename / levels / months are set at drop kickoff.</li>"
        "</ol><p class=\"meta\">Cohort culls happen in anduin after the save. A curve you edit in anduin is "
        "never overwritten by a re-run.</p>")

    rows = []
    for i, c in enumerate(P["curves"], 1):
        o = c["preview_oil"]
        di, eff = di_pair(o.get("Di"), o.get("b"))
        rows.append([i, _chip(c["name"], CURVE_COLOR[(i - 1) % len(CURVE_COLOR)]), c["bench"], c["reserve_category"],
                     ", ".join(c["dsus"]), c["n_wells"], num(o.get("qi"), ",.1f"), di, eff, num(o.get("b"), ".2f"),
                     num(o.get("eur_per_unit"), ",.0f")])
    out.append("<h2>Type curves = Blue Ox zones (tab order)</h2>" + _table(
        ["#", "curve / zone", "bench", "category", "DSUs (scenario scope)", "cohort wells",
         "oil qi bbl/d per 1,000 ft", "Di nominal /yr", "Di 1-yr effective", "b", "oil EUR bbl per 1,000 ft"], rows)
        + '<p class="meta">Oil figures are the dossier\'s anduin TC preview (EUR = raw 50-yr integral); '
          "the saved curve is checked against them.</p>")

    rows = []
    for u in P["units"]:
        per: dict[str, list[int]] = {}
        for r in u["rows"]:
            k = per.setdefault(r["bench"], [0, 0, 0])
            k[{"kept": 0, "culled": 1}.get(r["status"], 2)] += 1
        benches = "; ".join(f"{b} {k[0]}" + (f" (+{k[1]} culled)" if k[1] else "") + (f" {k[2]} MISSING" if k[2] else "")
                            for b, k in per.items())
        ex = u.get("existing")
        state = ("not checked" if not P["narvi_checked"] else
                 "new" if not ex else f"REPLACES saved {ex['updated_at'][:10]} ({ex['n_overrides']} overrides)")
        pins = ", ".join(f"{b} @ {v:,.0f} ft" for b, v in u["pins"].items()) or "—"
        rows.append([u["dsu"], u["body"]["scenario_id"], benches, pins, f"{u['azimuth_true_deg']:.1f}° true",
                     state, "; ".join(u["issues"]) or "ok"])
    out.append("<h2>narvi scenarios</h2>" + _table(
        ["DSU", "scenario_id", "planned sticks per bench", "pinned (gunbarrel offset)", "azimuth", "narvi today",
         "check"], rows)
        + '<p class="meta">Pins appear where the dossier placed benches one at a time — narvi\'s save would '
          "otherwise stagger them together; the pin holds each bench where you reviewed it.</p>")

    out.append("<h2>Per unit</h2>")
    for u in P["units"]:
        rows = [[r["bench"], r["well_name"] or "—", r["status"] if r["status"] != "MISSING" else _Raw(
                 '<b style="color:#dc2626">MISSING</b>'), num(r.get("offset_ft"), ",.0f"), num(r["lateral_ft"], ",.0f"),
                 "—" if r["match_ft"] is None else f"{r['match_ft']:.1f}", r.get("why") or ""] for r in u["rows"]]
        out.append(f'<h3>{_esc(u["dsu"])} <span class="meta">{_esc(u["label"])}</span></h3><div class="row">'
                   f"{_unit_map(u, colors)}{_gunbarrel(u, colors)}"
                   + _table(["bench", "narvi well", "status", "offset ft", "lateral ft", "match to dossier ft",
                             "why culled"], rows)
                   + "</div>")
    out.append("</body></html>")
    path = run_dir / "handoff.html"
    path.write_text("\n".join(out), encoding="utf-8")
    return path
