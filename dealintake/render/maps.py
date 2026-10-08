"""Static per-bench PNG maps (matplotlib, no tile fetch).

Two kinds, both keyed to the TYPE CURVE:

* a CURVE map per tc_group (`map_<bench>_curve_<a|b|..>.png`) — left panel: the
  curve's units + planned sticks in the curve colour, a thin link from each unit
  to every well that builds the curve, and those wells drawn as their own
  laterals coloured by anduin oil EUR per ft (the bench's other wells faint
  grey); right panel: a zoom on the units with every planned stick labelled
  (stick id, lateral ft) — which sticks take this curve.
* a bench OVERVIEW (`map_<bench>.png`) only when the bench has several curves —
  every curve's units, links and wells on one canvas, same EUR colour scale.

Well colour = anduin's own per-well oil fit, EUR (raw 50-yr technical integral)
/ lateral ft — never Novi's EUR; a well with no anduin fit is grey, not filled
from another source. The colour scale is shared by every map of a bench so the
curves read against each other. Laterals come from `well_sticks.json` (written
by evaluate, or `render --fetch-sticks` for an older run); without it a well is
a dot at its lateral midpoint. Lon/lat with the x-axis scaled by cos(lat).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from shapely import wkt as shp_wkt
from shapely.geometry import shape
from shapely.ops import unary_union

TIER_COLOR = {"codev": "#2563eb", "stack_standalone": "#16a34a", "topfill_underfill": "#d97706"}
CURVE_COLOR = ["#2563eb", "#d97706", "#059669", "#7c3aed", "#dc2626", "#0891b2", "#a16207", "#be185d"]
EUR_CMAP = matplotlib.colormaps["viridis"]
NO_FIT = "#9ca3af"
EUR_LABEL = "anduin oil EUR, bbl/ft (per-well fit, raw 50-yr)"
MAX_WELL_LABELS = 45      # beyond this the value labels bury the map
MAX_STICK_LABELS = 16
_HALO = [pe.withStroke(linewidth=2.2, foreground="white")]


_ROSE4 = ["N", "E", "S", "W"]
_ROSE8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def _safe(s: str) -> str:
    """No spaces in a curve name: `WCB_2 @ 10,000 ft` -> `WCB_2_10000ft`."""
    return s.replace(",", "").replace(" @ ", "_").replace(" ", "")


def curve_labels(key: str, B: dict[str, Any], units: list[dict[str, Any]] | None = None) -> list[str]:
    """A short NAME per TC group, in group order — no spaces, no letter suffixes
    (Michael 2026-10-08: `WCB_2_SE` socializes; `WCB_2-A` confuses). One group:
    the bench key. Several: `<bench>_<compass>` (N/NE/.../NW) = the bearing of the group's unit
    centroid from the centroid of all the bench's grouped units, on the coarsest
    rose (4- then 8-point) that names every group uniquely. Groups that still
    collide (interleaved units) — or a call without unit geometry — fall back to
    `<bench>_<first DSU name>`; the map colour stays the cross-reference."""
    groups = B.get("tc_groups") or []
    base = _safe(key)
    if len(groups) <= 1:
        return [base for _ in groups]
    geom = {u["label"]: u for u in units or [] if u.get("geometry")}

    def dsu(G: dict[str, Any]) -> str:
        u = geom.get(G["units"][0]) or {}
        return f"{base}_{_safe(u.get('dsu_name') or G['units'][0])}"

    if not all(lab in geom for G in groups for lab in G["units"]):
        return [dsu(G) for G in groups]
    cents = [unary_union([shape(geom[lab]["geometry"]) for lab in G["units"]]).centroid for G in groups]
    allc = unary_union([shape(geom[lab]["geometry"]) for G in groups for lab in G["units"]]).centroid
    k = math.cos(math.radians(allc.y))
    brg = [math.degrees(math.atan2((c.x - allc.x) * k, c.y - allc.y)) % 360 for c in cents]
    for rose in (_ROSE4, _ROSE8):
        step = 360 / len(rose)
        names = [rose[int((b + step / 2) // step) % len(rose)] for b in brg]
        if len(set(names)) == len(names):
            return [f"{base}_{n}" for n in names]
    return [f"{base}_{n}" if names.count(n) == 1 else dsu(G) for n, G in zip(names, groups, strict=True)]



def curve_png(overview: Path, gi: int) -> Path:
    """`map_<bench>.png` -> `map_<bench>_curve_<a..>.png` (one per tc_group)."""
    return overview.with_name(f"{overview.stem}_curve_{chr(97 + gi)}.png")


def load_sticks(run_dir: Path) -> dict[str, str]:
    """api10 -> lateral WKT, or {} for a run that predates well_sticks.json."""
    f = run_dir / "well_sticks.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def eur_ft(w: dict[str, Any]) -> float | None:
    v = w.get("anduin_oil_eur_per_1000ft")
    return v / 1000.0 if v else None


def _norm(B: dict[str, Any]) -> Normalize:
    vals = sorted(v for G in B.get("tc_groups") or [] for w in G["tc_wells"] if (v := eur_ft(w)) is not None)
    if not vals:
        return Normalize(0.0, 1.0)
    lo, hi = vals[int(0.05 * (len(vals) - 1))], vals[round(0.95 * (len(vals) - 1))]
    if hi - lo < 1.0:
        lo, hi = lo - 1.0, hi + 1.0
    return Normalize(lo, hi)


def _unit_name(u: dict[str, Any]) -> str:
    return u.get("dsu_name") or u["label"]


def _draw_units(ax, units: list[dict[str, Any]], col_of: dict[str, str], label: bool, B: dict[str, Any]) -> None:
    for u in units:
        g = shape(u["geometry"])
        col = col_of.get(u["label"], "#d1d5db")
        faint = u["label"] not in col_of
        for p in getattr(g, "geoms", [g]):
            x, y = p.exterior.xy
            ax.fill(x, y, facecolor=col, alpha=0.06 if faint else 0.2, zorder=1)
            ax.plot(x, y, color=col, linewidth=0.8 if faint else 1.4, zorder=1)
        if label and not faint:
            n = len((B["units"].get(u["label"]) or {}).get("locations", []))
            ax.annotate(f"{_unit_name(u)}\n{n} stick{'s' if n != 1 else ''}", (g.centroid.x, g.centroid.y),
                        ha="center", va="center", fontsize=7, fontweight="bold", zorder=6,
                        bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": col, "alpha": 0.85})


def _draw_planned(ax, B: dict[str, Any], col_of: dict[str, str], stick_labels: bool) -> None:
    for lb, ub in B["units"].items():
        if lb not in col_of:
            continue
        for loc in ub.get("locations", []):
            g = shp_wkt.loads(loc["wkt"])
            x, y = g.xy
            ax.plot(x, y, color=col_of[lb], linewidth=2.6, linestyle="-" if loc["src"] == "novi" else (0, (4, 2)),
                    zorder=4, path_effects=[pe.withStroke(linewidth=4.2, foreground="white")])
            if stick_labels:      # along the stick at its midpoint — toes line up across a unit and collide
                ll = f" · {loc['ll_ft']:,.0f} ft" if loc.get("ll_ft") else ""
                m = g.interpolate(0.5, normalized=True)
                ang = math.degrees(math.atan2(y[-1] - y[0], x[-1] - x[0]))
                ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
                ax.text(m.x, m.y, f"{'Novi ' if loc['src'] == 'novi' else ''}{loc['id']}{ll}", fontsize=6,
                        color=col_of[lb], fontweight="bold", zorder=7, rotation=ang, rotation_mode="anchor",
                        transform_rotates_text=True, ha="center", va="bottom", path_effects=_HALO)


def _well_geom(w: dict[str, Any], sticks: dict[str, str]):
    s = sticks.get(w["api10"])
    return shp_wkt.loads(s) if s else None


def _draw_well(ax, w: dict[str, Any], sticks: dict[str, str], color: str, lw: float, z: int,
               tier_marker: bool = True, alpha: float = 1.0) -> None:
    g = _well_geom(w, sticks)
    if g is not None:
        for part in getattr(g, "geoms", [g]):
            x, y = part.xy
            ax.plot(x, y, color=color, linewidth=lw, alpha=alpha, zorder=z, solid_capstyle="round",
                    path_effects=[pe.withStroke(linewidth=lw + 1.2, foreground="#374151", alpha=0.6 * alpha)])
    if w.get("lon") is None:
        return
    if g is None:
        ax.scatter(w["lon"], w["lat"], s=lw * 14, color=color, edgecolors="#374151", linewidths=0.4,
                   alpha=alpha, zorder=z, marker="^" if w.get("tier") == "topfill_underfill" else "o")
    elif tier_marker and w.get("tier") == "topfill_underfill":
        ax.scatter(w["lon"], w["lat"], s=22, color=color, edgecolors="black", linewidths=0.5, zorder=z + 1, marker="^")


def _draw_cohort(ax, G: dict[str, Any], units: list[dict[str, Any]], col: str, norm: Normalize,
                 sticks: dict[str, str], values: bool) -> None:
    """Link every unit the curve applies to with every well that builds it, then
    the wells themselves coloured by anduin EUR/ft (value printed when asked)."""
    cents = [shape(u["geometry"]).centroid for u in units if u["label"] in G["units"]]
    for w in G["tc_wells"]:
        if w.get("lon") is None:
            continue
        for c in cents:
            ax.plot([c.x, w["lon"]], [c.y, w["lat"]], color=col, linewidth=0.6, alpha=0.4, zorder=2)
    for w in G["tc_wells"]:
        v = eur_ft(w)
        _draw_well(ax, w, sticks, EUR_CMAP(norm(v)) if v is not None else NO_FIT, 2.6, 5)
        if values and w.get("lon") is not None:
            ax.annotate(f"{v:.0f}" if v is not None else "n/f", (w["lon"], w["lat"]), fontsize=6,
                        xytext=(4, -3), textcoords="offset points", zorder=8, path_effects=_HALO)


def _finish(ax, lat0: float | None) -> None:
    if lat0:
        ax.set_aspect(1 / math.cos(math.radians(lat0)))
    ax.tick_params(labelsize=7)
    ax.ticklabel_format(useOffset=False)


def _colorbar(fig, ax, norm: Normalize) -> None:
    fig.colorbar(ScalarMappable(norm=norm, cmap=EUR_CMAP), ax=ax, fraction=0.035, pad=0.02,
                 extend="both").set_label(EUR_LABEL, fontsize=7)


def _legend(ax, extra: list[Any]) -> None:
    ax.legend(handles=extra + [
        plt.Line2D([], [], color=EUR_CMAP(0.7), linewidth=2.6, label="type-curve well (colour = anduin oil EUR/ft)"),
        plt.Line2D([], [], color=NO_FIT, linewidth=2.6, label="type-curve well, no anduin fit (n/f)"),
        plt.Line2D([], [], color="#374151", marker="^", linestyle="", label="came on over/under a parent"),
        plt.Line2D([], [], color="#d1d5db", linewidth=1.2, label="other wells on this bench (not in this curve)"),
        plt.Line2D([], [], color="#374151", linewidth=2.4, linestyle="--", label="planned stick (generated)"),
        plt.Line2D([], [], color="#374151", linewidth=2.4, linestyle="-", label="planned stick (Novi location kept)"),
    ], fontsize=6.5, loc="upper right", framealpha=0.92)


def _curve_map(path: Path, label: str, gi: int, G: dict[str, Any], units: list[dict[str, Any]],
               B: dict[str, Any], norm: Normalize, sticks: dict[str, str]) -> None:
    col = CURVE_COLOR[gi % len(CURVE_COLOR)]
    col_of = {u: col for u in G["units"]}
    mine = [u for u in units if u["label"] in col_of]
    lat0 = shape(mine[0]["geometry"]).centroid.y if mine else None
    fig, (ax, az) = plt.subplots(1, 2, figsize=(15, 8.5), dpi=120, gridspec_kw={"width_ratios": [1.7, 1]})
    in_curve = {w["api10"] for w in G["tc_wells"]}
    others = {w["api10"]: w for H in B.get("tc_groups") or [] for w in H["tc_wells"]}
    others.update({w["api10"]: w for w in B.get("eligible_pool", [])})
    others = {a: w for a, w in others.items() if a not in in_curve}

    for a in (ax, az):
        for w in others.values():
            _draw_well(a, w, sticks, "#d1d5db", 1.2, 2, tier_marker=False, alpha=0.8)
    # left: the whole support picture, framed on this curve's units + wells
    _draw_units(ax, units, col_of, label=True, B=B)
    _draw_planned(ax, B, col_of, stick_labels=False)
    _draw_cohort(ax, G, units, col, norm, sticks, values=len(G["tc_wells"]) <= MAX_WELL_LABELS)
    xs = [w["lon"] for w in G["tc_wells"] if w.get("lon") is not None]
    ys = [w["lat"] for w in G["tc_wells"] if w.get("lat") is not None]
    frame = [shape(u["geometry"]) for u in mine] + [g for w in G["tc_wells"] if (g := _well_geom(w, sticks)) is not None]
    for f in frame:
        x0, y0, x1, y1 = f.bounds
        xs += [x0, x1]
        ys += [y0, y1]
    if xs:
        px, py = max(0.1 * (max(xs) - min(xs)), 0.01), max(0.1 * (max(ys) - min(ys)), 0.01)
        ax.set_xlim(min(xs) - px, max(xs) + px)
        ax.set_ylim(min(ys) - py, max(ys) + py)
    tc = ((G.get("tc_preview") or {}).get("oil") or {}).get("eur_per_unit")
    vals = sorted(v for w in G["tc_wells"] if (v := eur_ft(w)) is not None)
    med = vals[len(vals) // 2] if len(vals) % 2 else (sum(vals[len(vals) // 2 - 1:len(vals) // 2 + 1]) / 2 if vals else None)
    ax.set_title(f"Curve {label} — built from {len(G['tc_wells'])} wells"
                 + (f"; TC oil {tc / 1000:.1f} bbl/ft" if tc else "")
                 + (f"; well median {med:.1f} bbl/ft ({len(vals)} fitted)" if med is not None else ""), fontsize=10)
    _legend(ax, [plt.Line2D([], [], color=col, linewidth=0.8, label=f"link: unit → well that builds {label}")])
    _finish(ax, lat0)
    _colorbar(fig, ax, norm)

    # right: which sticks take this curve
    n_sticks = sum(len((B["units"].get(u) or {}).get("locations", [])) for u in G["units"])
    _draw_units(az, units, col_of, label=False, B=B)
    for w in G["tc_wells"]:
        v = eur_ft(w)
        _draw_well(az, w, sticks, EUR_CMAP(norm(v)) if v is not None else NO_FIT, 2.6, 5)
    roomy = False
    if mine:
        b = [shape(u["geometry"]).bounds for u in mine]
        x0, y0 = min(t[0] for t in b), min(t[1] for t in b)
        x1, y1 = max(t[2] for t in b), max(t[3] for t in b)
        pad = max(0.25 * max(x1 - x0, y1 - y0), 0.01)
        az.set_xlim(x0 - pad, x1 + pad)
        az.set_ylim(y0 - pad, y1 + pad)
        # per-stick labels only when a unit fills enough of the panel to carry
        # them; units miles apart -> one summary line per unit instead
        unit_span = max(max(t[2] - t[0], t[3] - t[1]) for t in b)
        roomy = n_sticks <= MAX_STICK_LABELS and unit_span / (max(x1 - x0, y1 - y0) + 2 * pad) >= 0.35
        for u in mine:
            g = shape(u["geometry"])
            locs = (B["units"].get(u["label"]) or {}).get("locations", [])
            lls = [loc["ll_ft"] for loc in locs if loc.get("ll_ft")]
            txt = _unit_name(u) if roomy else (
                f"{_unit_name(u)}: {len(locs)} stick{'s' if len(locs) != 1 else ''}"
                + (f", {min(lls):,.0f}–{max(lls):,.0f} ft" if lls else ""))
            az.annotate(txt, (g.centroid.x, g.bounds[3]), ha="center", va="bottom", fontsize=7,
                        fontweight="bold", color=col, zorder=7, xytext=(0, 3), textcoords="offset points",
                        path_effects=_HALO)
    _draw_planned(az, B, col_of, stick_labels=roomy)
    az.set_title(f"Sticks taking {label}: {n_sticks} in {len(G['units'])} unit{'s' if len(G['units']) != 1 else ''}",
                 fontsize=10)
    _finish(az, lat0)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _overview(path: Path, bench: str, units: list[dict[str, Any]], B: dict[str, Any], labels: list[str],
              norm: Normalize, sticks: dict[str, str]) -> None:
    groups = B.get("tc_groups") or []
    col_of = {u: CURVE_COLOR[i % len(CURVE_COLOR)] for i, G in enumerate(groups) for u in G["units"]}
    fig, ax = plt.subplots(figsize=(10.5, 9), dpi=120)
    used = {w["api10"] for G in groups for w in G["tc_wells"]}
    for w in B.get("eligible_pool", []):
        if w["api10"] not in used:
            _draw_well(ax, w, sticks, "#d1d5db", 1.2, 2, tier_marker=False, alpha=0.8)
    _draw_units(ax, units, col_of, label=True, B=B)
    _draw_planned(ax, B, col_of, stick_labels=False)
    for i, G in enumerate(groups):
        _draw_cohort(ax, G, units, CURVE_COLOR[i % len(CURVE_COLOR)], norm, sticks, values=False)
    lat0 = shape(units[0]["geometry"]).centroid.y if units else None
    _legend(ax, [plt.Line2D([], [], color=CURVE_COLOR[i % len(CURVE_COLOR)], linewidth=2.4,
                            label=f"{labels[i]} — units + links; built from {len(G['tc_wells'])} wells, "
                                  f"applied to {len(G['units'])} unit{'s' if len(G['units']) != 1 else ''}")
                 for i, G in enumerate(groups)])
    ax.set_title(f"{bench} — every curve: which units take it, which wells build it", fontsize=10)
    _finish(ax, lat0)
    _colorbar(fig, ax, norm)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def bench_map(path: Path, bench: str, units: list[dict[str, Any]], B: dict[str, Any],
              labels: list[str] | None = None, sticks: dict[str, str] | None = None) -> list[Path]:
    """Write one curve map per tc_group, plus the bench overview at `path` when
    the bench has more than one curve. Returns the paths written."""
    groups = B.get("tc_groups") or []
    labels = labels or curve_labels(bench, B, units)
    sticks = sticks or {}
    norm = _norm(B)
    out = []
    for gi, G in enumerate(groups):
        _curve_map(curve_png(path, gi), labels[gi], gi, G, units, B, norm, sticks)
        out.append(curve_png(path, gi))
    if len(groups) > 1:
        _overview(path, bench, units, B, labels, norm, sticks)
        out.append(path)
    return out
