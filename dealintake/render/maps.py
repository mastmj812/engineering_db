"""Static per-bench PNG maps (matplotlib, no tile fetch).

One map per bench, coloured by TYPE CURVE: every unit is filled in the colour
of the curve it takes and labelled with its DSU name + stick count; the wells
that BUILD each curve are solid dots in the same colour (a triangle when the
well came on over/under a parent); the rest of the eligible pool is hollow
grey. Lon/lat with the x-axis scaled by cos(lat) so distances read true.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely import wkt as shp_wkt
from shapely.geometry import shape

TIER_COLOR = {"codev": "#2563eb", "stack_standalone": "#16a34a", "topfill_underfill": "#d97706"}
CURVE_COLOR = ["#2563eb", "#d97706", "#059669", "#7c3aed", "#dc2626", "#0891b2", "#a16207", "#be185d"]


def curve_labels(key: str, B: dict[str, Any], units: list[dict[str, Any]] | None = None) -> list[str]:
    """A short NAME per TC group, in group order. One group: the bench key.
    Several: `<bench>-A`, `-B`, ... — letters only. The split test groups units
    by how their offsets PERFORM, so a group's units can interleave on the map
    (VaULt BS3_C-B = 25-26-27 + 35-38-47, eight miles apart); a compass word in
    the name would mislead. The map colour is what tells them apart."""
    groups = B.get("tc_groups") or []
    if len(groups) <= 1:
        return [key for _ in groups]
    return [f"{key}-{chr(65 + i)}" for i in range(len(groups))]


def bench_map(path: Path, bench: str, units: list[dict[str, Any]], B: dict[str, Any],
              labels: list[str] | None = None) -> None:
    groups = B.get("tc_groups") or []
    labels = labels or curve_labels(bench, B, units)
    curve_of = {u: i for i, G in enumerate(groups) for u in G["units"]}
    fig, ax = plt.subplots(figsize=(9, 9), dpi=120)
    lat0 = None
    for u in units:
        g = shape(u["geometry"])
        lat0 = lat0 or g.centroid.y
        i = curve_of.get(u["label"])
        col = CURVE_COLOR[i % len(CURVE_COLOR)] if i is not None else "#9ca3af"
        for p in getattr(g, "geoms", [g]):
            x, y = p.exterior.xy
            ax.fill(x, y, facecolor=col, edgecolor=col, linewidth=1.4, alpha=0.22)
            ax.plot(x, y, color=col, linewidth=1.4)
        n = len((B["units"].get(u["label"]) or {}).get("locations", []))
        ax.annotate(f"{u.get('dsu_name') or u['label']}\n{n} stick{'s' if n != 1 else ''}",
                    (g.centroid.x, g.centroid.y), ha="center", va="center", fontsize=7, fontweight="bold",
                    bbox={"boxstyle": "round,pad=0.2", "facecolor": "white", "edgecolor": col, "alpha": 0.85})
    for lb, ub in B["units"].items():
        i = curve_of.get(lb)
        col = CURVE_COLOR[i % len(CURVE_COLOR)] if i is not None else "#6b7280"
        for loc in ub.get("locations", []):
            x, y = shp_wkt.loads(loc["wkt"]).xy
            ax.plot(x, y, color=col, linewidth=1.3, linestyle="-" if loc["src"] == "novi" else "--", alpha=0.9)
    used: set[str] = set()
    for i, G in enumerate(groups):
        col = CURVE_COLOR[i % len(CURVE_COLOR)]
        for w in G["tc_wells"]:
            if w.get("lon") is None:
                continue
            used.add(w["api10"])
            ax.scatter(w["lon"], w["lat"], s=34, color=col, edgecolors="black", linewidths=0.4, zorder=3,
                       marker="^" if w.get("tier") == "topfill_underfill" else "o")
    for w in B.get("eligible_pool", []):
        if w["api10"] not in used and w.get("lon") is not None:
            ax.scatter(w["lon"], w["lat"], s=14, facecolors="none", edgecolors="#9ca3af", linewidths=0.7, zorder=2)
    handles = []
    for i, G in enumerate(groups):
        col = CURVE_COLOR[i % len(CURVE_COLOR)]
        handles.append(plt.Line2D([], [], color=col, marker="o", markeredgecolor="black", linestyle="", markersize=7,
                                  label=f"{labels[i]} — built from {len(G['tc_wells'])} wells, "
                                        f"applied to {len(G['units'])} unit{'s' if len(G['units']) != 1 else ''}"))
    handles += [plt.Line2D([], [], color="#374151", marker="^", linestyle="", label="curve well that came on over/under a parent"),
                plt.Line2D([], [], color="#9ca3af", marker="o", markerfacecolor="none", linestyle="",
                           label="eligible pool well, not in a curve"),
                plt.Line2D([], [], color="#374151", linestyle="--", label="planned stick (generated)"),
                plt.Line2D([], [], color="#374151", linestyle="-", label="planned stick (Novi location kept)")]
    ax.legend(handles=handles, fontsize=7, loc="upper right", framealpha=0.92)
    if lat0:
        ax.set_aspect(1 / math.cos(math.radians(lat0)))
    ax.set_title(f"{bench} — which wells build each curve, and which units take it", fontsize=10)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
