"""The reviewer's picture: one self-contained review.html per run (Gates 1-2).

Per DSU — a map (unit, offset PDP laterals by bench, Novi BASE_CASE sticks
inside vs crossing, the planned chord), a TVD strip (local bench medians
against the rights window — declared depths, or a formation span resolved by
stratigraphic order), and a bench table with the proposed scope and why.
This page IS the review surface; benches.yaml is the record behind it.
"""

from __future__ import annotations

import html
import io
import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from shapely import wkt as shp_wkt
from shapely.geometry import shape

from dealintake import spacing
from dealintake.geo import positive_offset_bearing
from dealintake.select_wells import bench_code

# Mirror of narvi's FORMATION_COLORS (src/narvi/viz.py) — keep in step.
BENCH_COLOR = {
    "WCA_1": "#f97316", "WCB_1": "#22c55e", "WCB_2": "#ec4899", "WCC": "#8b5cf6",
    "WCD": "#0ea5e9", "STRN": "#78716c", "BRNT": "#2563eb", "MISS": "#dc2626",
    "WDFD": "#4d7c0f", "OTHER": "#9ca3af",
    "AVA_0": "#06b6d4", "AVA_1": "#f43f5e", "AVA_2": "#84cc16",
    "BS1_S": "#eab308", "BS2_C": "#a855f7", "BS2_S": "#14b8a6",
    "BS3_C": "#fb923c", "BS3_S": "#d946ef", "WCXY": "#65a30d", "WCA_2": "#e11d48",
    "US": "#06b6d4", "MS": "#f43f5e", "JM": "#a855f7", "LSSH": "#eab308", "DEAN": "#14b8a6", "MRMC": "#d946ef",
}
CLASS_COLORS = ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#db2777", "#0891b2"]
FT_PER_DEG_LAT = 364_000.0
INK = "#111827"
NEAR_MISS = "#d97706"


def _prox_summaries(gb: dict[str, Any]) -> list[dict[str, Any]]:
    return ([pl["proximity"] for pl in gb.get("planned", {}).values() if pl.get("proximity")]
            + list((gb.get("culled_benches") or {}).values()))


def culled_rows(gb: dict[str, Any]) -> list[tuple[str, float, list[float], bool]]:
    """(bench, tvd, culled offsets, whole bench seeded off) for the gunbarrel ×s:
    rows the PDP-proximity rule removed from a drawn bench, plus the benches the
    seed turned off because every row was culled."""
    out = []
    for b, pl in gb.get("planned", {}).items():
        c = (pl.get("proximity") or {}).get("culled") or []
        if c and not pl.get("error"):
            out.append((b, float(pl["tvd_ft"]), [x["offset_ft"] for x in c], False))
    for b, s in (gb.get("culled_benches") or {}).items():
        out.append((b, float(s["tvd_ft"]), [x["offset_ft"] for x in s.get("culled") or []], True))
    return out


def proximity_cell(b: str, gb: dict[str, Any]) -> str:
    """The bench table's PDP-proximity column."""
    s = (gb.get("culled_benches") or {}).get(b) or (gb.get("planned", {}).get(b) or {}).get("proximity")
    if not s:
        return "—"
    parts = []
    if s.get("n_culled"):
        parts.append(f"{s['n_culled']} of {s['n_rows']} culled · nearest {s['culled'][0]['text']}")
    if s.get("would_cull"):
        parts.append(f"OVERRIDDEN: {len(s['would_cull'])} would cull ({s['would_cull'][0]['text']})")
    if s.get("near"):
        parts.append(f"near-miss {len(s['near'])} ({s['near'][0]['text']})")
    if s.get("permit"):
        parts.append(f"permit-TVD producer, not culled ({s['permit'][0]['text']})")
    return "; ".join(parts) or "clear"


def proximity_look(gb: dict[str, Any]) -> list[str]:
    """Benches the reviewer should look at for PDP proximity: near-misses,
    permit-TVD producers, overrides, every row culled."""
    out = []
    for b, pl in gb.get("planned", {}).items():
        s = pl.get("proximity") or {}
        if s.get("near") or s.get("permit") or s.get("would_cull") or (s.get("n_culled") and not pl.get("offsets_ft")):
            out.append(b)
    return out


def _color(bench: str) -> str:
    return BENCH_COLOR.get(bench_code(bench), "#9ca3af")


def _svg(fig) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    body = buf.getvalue()
    return body[body.index("<svg"):]


def _draw_poly(ax, g, **kw) -> None:
    for p in getattr(g, "geoms", [g]):
        x, y = p.exterior.xy
        ax.fill(x, y, **kw)


def _lines(ax, geom, **kw) -> None:
    for part in getattr(geom, "geoms", [geom]):
        x, y = part.xy
        ax.plot(x, y, **kw)


def unit_map(u: dict[str, Any], others: list[dict[str, Any]], layers: dict[str, Any]) -> str:
    """Plan view: the unit, the offset PDP of its local benches, Novi sticks and
    OUR PROPOSED sticks (the narvi preview at the reviewed benches — bold, by
    bench; a U-turn draws both legs; rows the row rules / PDP proximity removed
    are faint dotted). Novi sticks are drawn only for the benches proposed on
    this unit (all benches when none is) — ten stacked benches drawn on top of
    each other hid the plan (RIP Harambe, 2026-10-22). The dashed long-axis
    chord shows only when nothing is proposed."""
    g = shape(u["geometry"])
    planned = {b: pl for b, pl in ((u.get("gunbarrel") or {}).get("planned") or {}).items()
               if not pl.get("error") and pl.get("sticks_wkt")}
    lat0 = g.centroid.y
    fig, ax = plt.subplots(figsize=(6.4, 6.4), dpi=100)
    for o in others:
        _draw_poly(ax, shape(o["geometry"]), facecolor="#f3f4f6", edgecolor="#9ca3af", linewidth=0.8)
    _draw_poly(ax, g, facecolor="#e5e7eb", edgecolor=INK, linewidth=2.0, alpha=0.7, zorder=2)
    seen: set[str] = set()
    target = {bench_code(r["bench"]) for r in u["bench_proposal"]} - {"OTHER"}
    near = g.buffer(0.45 / 69.0)                         # ~0.45 mi ring: the offsets that matter here
    for w in layers.get("pdp", []):
        line = shp_wkt.loads(w["wkt"])
        if bench_code(w["bench"]) not in target or not line.intersects(near):
            continue
        _lines(ax, line, color=_color(w["bench"]), linewidth=0.9, alpha=0.6, zorder=3)
        seen.add(w["bench"])
    for s in layers.get("novi", []):
        if planned and bench_code(s["bench"]) not in planned:
            continue
        base = s["category"] == "PUD"
        _lines(ax, shp_wkt.loads(s["wkt"]), color=_color(s["bench"]), linewidth=2.6 if base else 1.2,
               linestyle="-" if s["relation"] == "inside" else ("--" if base else ":"),
               alpha=(0.55 if planned else 1.0) if base else 0.5, zorder=5 if base else 4)
        seen.add(s["bench"])
    pl = u["planned_lateral"]
    for b, p in planned.items():
        for w in p.get("culled_wkt") or []:
            _lines(ax, shp_wkt.loads(w), color=_color(b), linewidth=1.2, linestyle=":", alpha=0.8, zorder=6)
        for w in p["sticks_wkt"]:
            _lines(ax, shp_wkt.loads(w), color=_color(b), linewidth=3.4, solid_capstyle="round", zorder=8,
                   path_effects=[pe.withStroke(linewidth=5.6, foreground="white")])
        for w in p.get("turns_wkt") or []:            # a U-turn's arc ties its two legs into one well
            _lines(ax, shp_wkt.loads(w), color=_color(b), linewidth=2.0, zorder=8,
                   path_effects=[pe.withStroke(linewidth=4.0, foreground="white")])
        seen.add(b)
    if not planned:
        # nothing proposed yet: the long-axis median chord drawn through the centroid
        az = math.radians(pl["azimuth_deg"])
        half = (pl["median_ft"] / 2) / FT_PER_DEG_LAT
        dx, dy = math.sin(az) * half / math.cos(math.radians(lat0)), math.cos(az) * half
        ax.plot([g.centroid.x - dx, g.centroid.x + dx], [g.centroid.y - dy, g.centroid.y + dy],
                color=INK, linewidth=1.4, linestyle=(0, (6, 3)), zorder=6)
    minx, miny, maxx, maxy = g.bounds
    pad_y = 0.35 / 69.0                                 # ~0.35 mi beyond the unit
    pad_x = pad_y / math.cos(math.radians(lat0))
    ax.set_xlim(minx - pad_x, maxx + pad_x)
    ax.set_ylim(miny - pad_y, maxy + pad_y)
    ax.set_aspect(1 / math.cos(math.radians(lat0)))
    handles = [plt.Line2D([], [], color=_color(b), linewidth=2, label=b) for b in sorted(seen)]
    if planned:
        n = sum(len(p["sticks_wkt"]) for p in planned.values())
        handles += [plt.Line2D([], [], color=INK, linewidth=3.4, label=f"PROPOSED ({n} well{'s' * (n != 1)}, narvi preview)"),
                    plt.Line2D([], [], color=INK, linewidth=1.2, linestyle=":", label="removed by row rules / PDP proximity")]
    handles += [plt.Line2D([], [], color=INK, linewidth=2.6, label="Novi BASE_CASE inside"),
                plt.Line2D([], [], color=INK, linewidth=2.6, linestyle="--", label="BASE_CASE crossing"),
                plt.Line2D([], [], color=INK, linewidth=1.2, linestyle=":", label="Novi RES"),
                plt.Line2D([], [], color=INK, linewidth=0.9, alpha=0.6, label="offset PDP (≤0.45 mi, target benches)"),
                ] + ([] if planned else [plt.Line2D([], [], color=INK, linewidth=1.4, linestyle=(0, (6, 3)),
                                                    label=f"planned chord {pl['median_ft']:,.0f} ft @ {pl['azimuth_deg']:.0f}°")])
    ax.legend(handles=handles, fontsize=6.5, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    ax.tick_params(labelsize=6)
    ax.set_title(u["label"], fontsize=9)
    return _svg(fig)


def tvd_strip(u: dict[str, Any]) -> str:
    """Local bench medians on a TVD axis against the rights window."""
    rows = [r for r in u["bench_proposal"] if r["median_tvd_ft"] is not None and bench_code(r["bench"]) != "OTHER"]
    seed = u.get("bench_seed") or {}
    fig, ax = plt.subplots(figsize=(3.6, 6.4), dpi=100)
    if not rows:
        ax.text(0.5, 0.5, "no local offset control", ha="center", va="center", fontsize=8)
        ax.axis("off")
        return _svg(fig)
    solid = [r for r in rows if "thin control" not in (r.get("note") or "")] or rows
    tvds = [r["median_tvd_ft"] for r in solid]
    lo, hi = min(tvds) - 500, max(tvds) + 500
    rows = [r for r in rows if lo <= r["median_tvd_ft"] <= hi]   # a lone thin bench far off-axis stays in the table only
    b = u.get("bounds") or {}
    bmin, bmax = b.get("min") or {}, b.get("max") or {}
    kmin, kmax = bmin.get("kind"), bmax.get("kind")
    # Depth bounds shade real (declared) TVD; formation bounds shade the span of
    # the benches allowed by stratigraphic order; open ends run off the axis.
    if kmin == "depth":
        top = bmin["depth_ft"]
    elif kmin == "strat":
        inside = [r["median_tvd_ft"] for r in rows if "stratigraphic order" not in seed.get(bench_code(r["bench"]), {}).get("why", "")]
        top = min(inside) - 150 if inside else None
    else:
        top = lo
    if kmax == "depth":
        bot = bmax["depth_ft"]
    elif kmax == "strat":
        inside = [r["median_tvd_ft"] for r in rows if "stratigraphic order" not in seed.get(bench_code(r["bench"]), {}).get("why", "")]
        bot = max(inside) + 150 if inside else None
    else:
        bot = hi
    if top is not None and bot is not None:
        ax.axhspan(top, bot, color="#fef3c7", zorder=0)
        for v, kind in ((top, kmin), (bot, kmax)):
            if kind == "depth":
                ax.axhline(v, color="#b45309", linewidth=1.2, linestyle="--")
                ax.text(0.99, v, f"{v:,.0f}' declared", fontsize=6.5, color="#b45309", va="bottom", ha="right")
    # labels: sorted by TVD, pushed apart to a minimum gap, leader line back to the bar
    gap = (hi - lo) / 26
    ordered = sorted(rows, key=lambda r: r["median_tvd_ft"])
    label_y: list[float] = []
    for r in ordered:
        y = r["median_tvd_ft"]
        if label_y and y < label_y[-1] + gap:
            y = label_y[-1] + gap
        label_y.append(y)
    for r, ly in zip(ordered, label_y):
        code = bench_code(r["bench"])
        st = seed.get(code, {})
        on = bool(st.get("evaluate"))
        tv = r["median_tvd_ft"]
        ax.barh(tv, 0.22, height=55, color=_color(code), alpha=1.0 if on else 0.35, left=0)
        ax.plot([0.22, 0.30], [tv, ly], color="#9ca3af", linewidth=0.6)
        mark = "●" if on else ("◐" if r["status"] == "edge" else "○")
        ax.text(0.31, ly, f"{mark} {code}  {tv:,.0f}'  n={r['wells']}", fontsize=7, va="center",
                color=INK if on else "#6b7280", fontweight="bold" if on else "normal")
    ax.set_ylim(hi, lo)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_ylabel("local median TVD, ft (offset wells)", fontsize=7)
    ax.tick_params(labelsize=6.5)
    ax.set_title("benches vs rights   ● on  ◐ edge  ○ off", fontsize=7.5)
    for sp in ("top", "right", "bottom"):
        ax.spines[sp].set_visible(False)
    return _svg(fig)


def cross_section_ends(azimuth_deg: float) -> tuple[bool, str, str]:
    """(flip, left, right) so a gunbarrel reads W->E (or S->N when the cross
    axis runs mostly north-south). Since sign rule v2 (Michael, 2026-10-08)
    the rule-16 +offset itself points that way (into the NE half — the old
    90-deg-clockwise frame drew 36-37 east-to-west, 2026-09-30), so flip is
    always False; only the end labels depend on the plan azimuth."""
    d = math.radians(positive_offset_bearing(azimuth_deg))
    east, north = math.sin(d), math.cos(d)
    if abs(east) >= abs(north):
        return east < 0, "W", "E"
    return north < 0, "S", "N"


def spacing_cell(b: str, u: dict[str, Any], on: bool) -> Any:
    """Bench-table cell: the row spacing a generated bench uses and where it came from."""
    s = (u.get("spacing") or {}).get(b)
    pl = ((u.get("gunbarrel") or {}).get("planned") or {}).get(b) or {}
    if pl.get("spacing_source") == "reviewer":
        return _Raw(f"<b>{pl['spacing_ft']:,.0f} ft</b> (reviewer)"
                    + (f'<br><span class="meta">nearby: {_esc(spacing.short_text(s))}'
                       + (f" → {s['spacing_ft']:,.0f} ft" if s and s.get("spacing_ft") else "") + "</span>" if s else ""))
    if not s:
        return "—"
    if s.get("needs_reviewer"):
        return _Raw(f'<span class="{"flagtxt" if on else "meta"}">none nearby — set spacing_ft</span>'
                    f'<br><span class="meta">{_esc("; ".join(s.get("tried") or []))}</span>')
    return _Raw(f'<b>{s["spacing_ft"]:,.0f} ft</b>' + (' <span class="flagtxt">mixed</span>' if s.get("mixed") else "")
                + f'<br><span class="meta">{_esc(s["text"])}</span>')


def spacing_look(u: dict[str, Any]) -> list[str]:
    """'Needs a look' entries: seeded-ON benches without a reviewer spacing whose
    nearby pattern is missing or mixed."""
    out = []
    planned = (u.get("gunbarrel") or {}).get("planned") or {}
    for b, row in (u.get("bench_seed") or {}).items():
        if row.get("evaluate") and (planned.get(b) or {}).get("spacing_source") != "reviewer":
            t = spacing.flag_text(b, (u.get("spacing") or {}).get(b))
            if t:
                out.append(t)
    return out


def gunbarrel(u: dict[str, Any]) -> str:
    """Cross-section perpendicular to the planned azimuth: the PROPOSED rows
    (narvi preview at the reviewed benches — hollow squares on each bench's
    local median TVD) against the EXISTING producers (filled, by bench; faded
    outside the unit). Novi BASE_CASE sticks are not drawn (Michael,
    2026-09-28: our proposal vs PDP, nothing out of scope). The TVD window is
    the proposed benches ± a margin, so a shallow unmapped or a Woodford well
    does not flatten the picture. +offset = rule-16 sign rule v2 (W -> E for
    N-S-ish plans, S -> N for E-W-ish)."""
    gb = u.get("gunbarrel")
    if not gb:
        return ""
    rows = {b: pl for b, pl in gb["planned"].items() if not pl.get("error") and pl.get("offsets_ft")}
    ghosts = culled_rows(gb)
    if not rows and not gb["existing"] and not ghosts:
        return ""
    if rows or ghosts:
        t = [pl["tvd_ft"] for pl in rows.values()] + [g[1] for g in ghosts]
        y_lo, y_hi = min(t) - 1500.0, max(t) + 1500.0
    else:
        t = [w["tvd_ft"] for w in gb["existing"]]
        y_lo, y_hi = min(t) - 500.0, max(t) + 500.0
    shown = [w for w in gb["existing"] if y_lo <= w["tvd_ft"] <= y_hi]
    hidden = len(gb["existing"]) - len(shown)
    fig, ax = plt.subplots(figsize=(10.5, 5.0), dpi=100)
    c_lo, c_hi = gb["cross_extent_ft"]
    ax.axvspan(c_lo, c_hi, color="#f3f4f6", zorder=0)
    for x in (c_lo, c_hi):
        ax.axvline(x, color="#9ca3af", linestyle="--", linewidth=0.9)
    seen: set[str] = set()
    n_permit = 0
    for w in shown:
        permit = float(w["tvd_ft"]) % 100 == 0           # round-100 TVD = permit depth, not a survey (rule 10)
        n_permit += permit
        ax.scatter(w["offset_ft"], w["tvd_ft"], s=46, color="white" if permit else _color(w["bench"]),
                   edgecolors=_color(w["bench"]) if permit else INK, linewidths=1.4 if permit else 0.5,
                   alpha=1.0 if w["inside"] else 0.4, zorder=3)
        seen.add(w["bench"])
    row_labels: list[str] = []
    n_near = 0
    for b, pl in rows.items():
        ax.axhline(pl["tvd_ft"], color=_color(b), linewidth=0.7, alpha=0.6)
        legs_x = pl.get("leg_offsets_ft") or pl["offsets_ft"]          # a U-turn plots both legs
        ax.scatter(legs_x, [pl["tvd_ft"]] * len(legs_x), s=110, marker="s", facecolors="white",
                   edgecolors=_color(b), linewidths=2.0, zorder=5)
        near = [n["offset_ft"] for n in ((pl.get("proximity") or {}).get("near") or [])]
        if near:
            n_near += len(near)
            ax.scatter(near, [pl["tvd_ft"]] * len(near), s=260, marker="s", facecolors="none",
                       edgecolors=NEAR_MISS, linewidths=1.8, zorder=6)
        rules = [r for r in pl.get("rules") or [] if "culled by PDP proximity" not in r]
        n_cull = (pl.get("proximity") or {}).get("n_culled") or 0
        uturn = pl.get("well_type") == "uturn"
        row_labels.append(f"{b}: {len(pl['offsets_ft'])} {'U-turn wells (' + str(len(legs_x)) + ' legs)' if uturn else 'sticks'}"
                          f" @ {pl['spacing_ft']:,.0f} ft{' leg-to-leg' if uturn else ''}, TVD {pl['tvd_ft']:,.0f}"
                          + (" [reviewer TVD]" if pl.get("tvd_source") == "reviewer" else "")
                          + (" [UPSIDE]" if pl.get("role") == "upside" else "")
                          + (" [winerack]" if pl.get("winerack") else "")
                          + (f" [pinned at {pl['pin_offset_ft']:+,.0f} ft]" if pl.get("pin_offset_ft") is not None else "")
                          + (" [reviewer spacing]" if pl.get("spacing_source") == "reviewer"
                             else f" [{spacing.short_text((u.get('spacing') or {}).get(b))}]")
                          + (f" — {n_cull} culled by PDP proximity" if n_cull else "")
                          + (f" — {'; '.join(rules)}" if rules else ""))
    for b, tv, offs, whole in ghosts:
        ax.scatter(offs, [tv] * len(offs), s=80, marker="x", color=_color(b), linewidths=2.0, alpha=0.9, zorder=5)
        if whole:
            ax.axhline(tv, color=_color(b), linewidth=0.7, alpha=0.3, linestyle=":")
            row_labels.append(f"{b}: all {len(offs)} rows culled by PDP proximity — seeded OFF, TVD {tv:,.0f}")
    ax.set_ylim(y_hi, y_lo)
    flip, left, right = cross_section_ends(float(gb["azimuth_deg"]))
    ax.set_xlim((c_hi + 1500, c_lo - 1500) if flip else (c_lo - 1500, c_hi + 1500))
    ax.set_xlabel(f"{left}  ←   offset from unit centroid, ft (+ toward {right}; "
                  f"{gb['azimuth_deg']:.0f}° plan)   →  {right}", fontsize=8)
    ax.set_ylabel("TVD ft", fontsize=8)
    ax.grid(True, linewidth=0.3, alpha=0.5)
    ax.tick_params(labelsize=7)
    handles = [plt.Line2D([], [], marker="o", linestyle="", color=_color(b), markeredgecolor=INK,
                          label=f"existing {b}") for b in sorted(seen)]
    handles += [plt.Line2D([], [], marker="o", linestyle="", color="#9ca3af",
                           label="faded = < 30 % of the lateral in the unit (side / partial neighbour)")]
    if n_permit:
        handles += [plt.Line2D([], [], marker="o", linestyle="", markerfacecolor="white", markeredgecolor="#6b7280",
                               label=f"hollow = round-100 TVD (permit depth, suspect) x{n_permit}")]
    handles += [plt.Line2D([], [], marker="x" if "seeded OFF" in lbl else "s", linestyle="", markerfacecolor="white",
                           markeredgecolor=_color(lbl.split(":")[0]), color=_color(lbl.split(":")[0]),
                           markersize=8, label=("" if "seeded OFF" in lbl else "proposed ") + lbl) for lbl in row_labels]
    if ghosts:
        rule = next((s["rule"] for s in _prox_summaries(gb) if s.get("rule")), "the PDP-proximity rule")
        handles += [plt.Line2D([], [], marker="x", linestyle="", color="#6b7280", markersize=8,
                               label=f"× = culled: {rule} of a producer (PROVISIONAL)")]
    if n_near:
        handles += [plt.Line2D([], [], marker="s", linestyle="", markerfacecolor="none", markeredgecolor=NEAR_MISS,
                               markersize=11, label=f"amber = near-miss, kept (inside the flag band) x{n_near}")]
    ax.legend(handles=handles, fontsize=6.8, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    src = gb.get("benches_source", "seed")
    ax.set_title(f"{u.get('dsu_name') or u['label']} — gunbarrel: proposed rows at the "
                 f"{'reviewed' if src != 'seed' else 'seeded'} benches vs existing producers"
                 + (f"  ({hidden} producer{'s' if hidden != 1 else ''} outside the shown TVD window)" if hidden else ""),
                 fontsize=9)
    return _svg(fig)


def overview_map(prop: dict[str, Any], classes: list[list[str]]) -> str:
    fig, ax = plt.subplots(figsize=(9, 6), dpi=100)
    cls_of = {u: i for i, c in enumerate(classes) for u in c}
    name = {u["label"]: u.get("dsu_name") or u["label"] for u in prop["units"]}
    lat0 = None
    labelled: list[Any] = []          # one label per footprint (stacked DSUs share one)
    for u in prop["units"]:
        g = shape(u["geometry"])
        lat0 = lat0 or g.centroid.y
        c = CLASS_COLORS[cls_of.get(u["label"], 0) % len(CLASS_COLORS)]
        _draw_poly(ax, g, facecolor=c, edgecolor=INK, linewidth=0.8, alpha=0.35)
        twins = [v["label"] for v in prop["units"] if shape(v["geometry"]).equals(g)]
        if not any(g.equals(x) for x in labelled):
            labelled.append(g)
            ax.annotate("\n".join(name[t] for t in twins), (g.centroid.x, g.centroid.y),
                        ha="center", va="center", fontsize=6)
    if lat0:
        ax.set_aspect(1 / math.cos(math.radians(lat0)))
    handles = [plt.Line2D([], [], marker="s", linestyle="", markersize=8, alpha=0.6,
                          color=CLASS_COLORS[i % len(CLASS_COLORS)],
                          label=f"class {i + 1} ({sum(float(u['planned_lateral']['median_ft']) for u in prop['units'] if u['label'] in c) / len(c):,.0f} ft): "
                                + ", ".join(name[x] for x in c))
               for i, c in enumerate(classes)]
    ax.legend(handles=handles, fontsize=6, loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False)
    ax.tick_params(labelsize=6)
    ax.set_title("Deal units by planned lateral (stacked DSUs overlap)", fontsize=9)
    return _svg(fig)


class _Raw(str):
    """Pre-escaped HTML cell."""


def _esc(v: Any) -> str:
    return html.escape("—" if v is None else str(v))


def _cell(v: Any) -> str:
    return v if isinstance(v, _Raw) else _esc(v)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    h = "".join(f"<th>{_esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"


def _chip(text: str, color: str) -> _Raw:
    return _Raw(f'<span class="chip" style="background:{color}">{html.escape(text)}</span>')


_CSS = """
body{font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#111827;margin:0 24px 48px;max-width:1500px}
h1{font-size:20px;margin:18px 0 4px} h2{font-size:16px;margin:36px 0 6px;border-top:2px solid #e5e7eb;padding-top:14px}
.meta{color:#6b7280;font-size:12px} .warn{background:#fef2f2;border-left:4px solid #dc2626;padding:6px 10px;margin:6px 0}
.row{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap} .row svg{max-width:100%;height:auto}
table{border-collapse:collapse;font-size:12px;margin:8px 0} th,td{border:1px solid #e5e7eb;padding:3px 7px;text-align:left;vertical-align:top}
th{background:#f9fafb} .chip{display:inline-block;color:#fff;border-radius:3px;padding:0 6px;font-weight:600;font-size:11px}
.rights{font-weight:600} .why{display:inline-block;max-width:520px} .toc a{margin-right:12px;font-size:12px}
details{margin:6px 0} summary{cursor:pointer;color:#374151;font-size:12px} li.disagree{color:#b45309} .flagtxt{color:#b45309;font-weight:600}
"""


def render(run_dir: Path) -> Path:
    from dealintake.pipeline import lateral_classes  # noqa: I001 — pipeline never imports review, no cycle

    prop = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    gp = run_dir / "review_geoms.json"
    geoms = json.loads(gp.read_text(encoding="utf-8")) if gp.exists() else {}
    units = prop["units"]
    ll = {u["label"]: float(u["planned_lateral"]["median_ft"]) for u in units}
    classes = lateral_classes(ll, 1.10)      # map colouring only — pools are per bench since config v8
    cls_ft = {u: sum(ll[x] for x in c) / len(c) for c in classes for u in c}
    shapes = {u["label"]: shape(u["geometry"]) for u in units}
    twins = {a["label"]: [b["label"] for b in units if b is not a and shapes[a["label"]].equals(shapes[b["label"]])]
             for a in units}
    name = {u["label"]: u.get("dsu_name") or u["label"] for u in units}

    title = _esc(Path(prop["deal_file"]).stem)
    p: list[str] = [(f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Deal review — {title}</title>"
                     f"<style>{_CSS}</style></head><body>"),
                    f"<h1>Deal review — {_esc(Path(prop['deal_file']).stem)}</h1>",
                    f"<div class=\"meta\">config v{_esc(prop['config_version'])} · strat v{_esc(prop.get('strat_version'))} · "
                    + " · ".join(f"{_esc(k)} {_esc(v)}" for k, v in prop["snapshot"].items()) + "</div>"]
    for w in prop.get("warnings", []):
        p.append(f'<div class="warn">{_esc(w)}</div>')
    p.append("<p>Per DSU: the map (offset PDP laterals and Novi BASE_CASE sticks coloured by bench, the planned chord), "
             "the TVD strip (local offset-well medians against the rights window — <b>declared depths are not local "
             "depths</b>; formation phrases are resolved by stratigraphic order, never into a depth), and the bench "
             "table with the proposed scope and why. Tell me the exceptions; <code>benches.yaml</code> is the record "
             "behind this page.</p>")
    if prop.get("pdp_proximity"):
        p.append(f"<p><b>PDP proximity (PROVISIONAL):</b> a generated row within {_esc(prop['pdp_proximity'])} of an "
                 "existing producer (any bench; share of OUR stick alongside it) is culled — drawn as × on the gunbarrel; "
                 "a bench with every row culled seeds off. Amber squares are near-misses (kept, flagged). "
                 "<code>pdp_proximity: false</code> on a bench keeps its rows.</p>")
    p.append("<p><b>Row spacing (config v15):</b> a generated bench takes the spacing of the SAME bench's Novi sticks "
             "near the unit — each stick's gap to its nearest parallel neighbour, median within 1 → 2 → 3 mi (Novi PUD, "
             "then RES), else the offset PDP's closer-XY. The IQR is beside it; a wide IQR (mixed pattern) or no "
             "number at all goes to Needs a look. A reviewer <code>spacing_ft</code> overrides it.</p>")
    p.append(overview_map(prop, classes))
    p.append('<div class="toc">' + " ".join(f'<a href="#{_esc(u["label"])}">{_esc(name[u["label"]])}</a>' for u in units) + "</div>")
    summary = []
    for u in units:
        seed = u.get("bench_seed") or {}
        on = [b for b, r in seed.items() if r["evaluate"]]
        look = [b for b, r in seed.items() if r["why"].startswith(("edge", "thin", "PDP proximity"))]
        look += [f"{b} (PDP proximity)" for b in proximity_look(u.get("gunbarrel") or {}) if b not in look]
        look += spacing_look(u)
        summary.append([_Raw(f'<a href="#{_esc(u["label"])}">{_esc(name[u["label"]])}</a>'), f"{u['area_ac']:,.0f}",
                        u.get("rights"), f"{ll[u['label']]:,.0f}", f"{cls_ft[u['label']]:,.0f}",
                        ", ".join(on) or "— (not evaluated)", ", ".join(look) or "—"])
    p.append(_table(["DSU", "ac", "Rights", "Planned lateral ft", "Lateral class ft", "Proposed benches", "Needs a look"], summary))

    for u in units:
        lb, seed, g2 = u["label"], u.get("bench_seed") or {}, u.get("gate2") or {}
        pdp3 = u.get("offset_pdp_3mi") or {}
        in_unit: dict[str, int] = {}
        for w in u.get("pdp_in_unit", []):
            in_unit[w["bench"]] = in_unit.get(w["bench"], 0) + 1
        pl, raw = u["planned_lateral"], u.get("declared_window_raw") or {}
        p.append(f'<h2 id="{_esc(lb)}">{_esc(name[lb])} <span class="meta">({_esc(lb)}, {u["area_ac"]:,.0f} ac)</span></h2>')
        p.append(f'<div>Rights: land file Min <code>{_esc(raw.get("Min_Depth"))}</code> / Max <code>{_esc(raw.get("Max_Depth"))}</code> → '
                 f'<span class="rights">{_esc(u.get("rights"))}</span> · basin {_esc(u.get("basin"))}'
                 + (f' · <b>same footprint as {_esc(", ".join(name[t] for t in twins[lb]))}</b> (depth-severed)' if twins[lb] else "")
                 + f' · planned lateral {ll[lb]:,.0f} ft ({pl["min_ft"]:,.0f}–{pl["max_ft"]:,.0f}) at {pl["azimuth_deg"]}° '
                   f'({_esc(pl["azimuth_source"])})</div>')
        tws = u.get("tract_windows") or []
        if tws:
            items = "".join(
                f'<li{" class=\"disagree\"" if tw["disagrees"] else ""}>{_esc(tw["tract"])}: '
                f'<code>{_esc(tw["raw"].get("Min_Depth"))}</code> → <code>{_esc(tw["raw"].get("Max_Depth")) }</code>'
                f' ({_esc(tw["rights"])}; {_esc(tw.get("net_ac"))} net ac)'
                + (" — <b>differs from the DSU window</b>" if tw["disagrees"]
                   else f" — {_esc(tw['twin'])}'s window (stacked DSU)" if tw.get("twin") else "") + "</li>"
                for tw in tws)
            n_bad = sum(1 for tw in tws if tw["disagrees"])
            p.append(f'<details{" open" if n_bad else ""}><summary>Tracts attached ({len(tws)}; '
                     f'{n_bad} declare a different window — the DSU row governs, tracts are shown for the reviewer)</summary>'
                     f"<ul>{items}</ul></details>")
        p.append('<div class="row">' + unit_map(u, [o for o in units if o is not u], geoms.get(lb, {})) + tvd_strip(u) + "</div>")
        gbs = gunbarrel(u)
        if gbs:
            p.append('<div class="row">' + gbs + "</div>")
            for b, v in (u.get("gunbarrel") or {}).get("planned", {}).items():
                if v.get("error"):
                    p.append(f'<div class="warn">{_esc(b)}: '
                             f'{"" if v.get("spacing_needed") else "preview failed — "}{_esc(v["error"])}</div>')
        byb = {bench_code(r["bench"]): r for r in u["bench_proposal"]}
        order = list(byb) + [b for b in seed if b not in byb]
        rows = []
        for b in order:
            if b == "OTHER":
                continue
            r, st, gg = byb.get(b, {}), seed.get(b), g2.get(b, {})
            if st is None and not gg:
                continue
            on = bool(st and st["evaluate"])
            tvd = f"{r['median_tvd_ft']:,.0f}' (n={r['wells']})" if r.get("median_tvd_ft") is not None else "no local control"
            novi = "none nearby"
            if gg:
                res = (gg.get("res_inside") or 0) + (gg.get("res_crossing") or 0)
                novi = f"{gg.get('pud_inside', 0)} in / {gg.get('pud_crossing', 0)} crossing" + (f" · {res} RES" if res else "")
                if gg.get("novi_azimuth_deg") is not None:
                    novi += (f" · az {gg['novi_azimuth_deg']:.0f}°"
                             + (f" ({gg['azimuth_diff_deg']:.0f}° off)" if gg.get("azimuth_diff_deg") else "")
                             + (f" · {gg['novi_ll_ft']:,.0f} ft" if gg.get("novi_ll_ft") else ""))
            loc = "—"
            if on:
                loc = _Raw(str(_chip("Novi", "#7c3aed") if gg.get("source") == "novi" else _chip("generate", "#db2777"))
                           + (f'<br><span class="meta">{_esc(gg.get("reason"))}</span>' if gg.get("reason") else ""))
            rows.append([_chip(b, _color(b)), tvd, r.get("status", "—"), pdp3.get(b, 0), in_unit.get(b, 0), novi, loc,
                         spacing_cell(b, u, on), proximity_cell(b, u.get("gunbarrel") or {}),
                         _chip("ON", "#059669") if on else _chip("off", "#9ca3af"),
                         _Raw(f'<span class="why">{_esc(st["why"] if st else "not a target bench")}</span>')])
        p.append(_table(["Bench", "Local TVD", "vs window", "Offset PDP ≤3 mi", "PDP in unit", "Novi BASE_CASE",
                         "Locations", "Row spacing", "PDP proximity", "Scope", "Why"], rows))
    p.append("</body></html>")
    out = run_dir / "review.html"
    out.write_text("\n".join(p), encoding="utf-8")
    return out
