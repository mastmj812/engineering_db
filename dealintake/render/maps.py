"""Static per-bench PNG maps (matplotlib, no tile fetch).

Draws: deal units, planned locations (Novi inside vs narvi preview), TC wells
coloured by codev tier, eligible-not-selected wells hollow. Lon/lat with the
x-axis scaled by cos(lat) so distances read true.
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


def bench_map(path: Path, bench: str, units: list[dict[str, Any]], B: dict[str, Any]) -> None:
    fig, ax = plt.subplots(figsize=(8, 8), dpi=120)
    lat0 = None
    for u in units:
        g = shape(u["geometry"])
        lat0 = lat0 or g.centroid.y
        polys = getattr(g, "geoms", [g])
        for p in polys:
            x, y = p.exterior.xy
            ax.fill(x, y, facecolor="#e5e7eb", edgecolor="#111827", linewidth=1.2, alpha=0.6)
        ax.annotate(u["label"], (g.centroid.x, g.centroid.y), ha="center", fontsize=8)
    for ub in B["units"].values():
        for loc in ub.get("locations", []):
            line = shp_wkt.loads(loc["wkt"])
            x, y = line.xy
            ax.plot(x, y, color="#7c3aed" if loc["src"] == "novi" else "#db2777", linewidth=1.6)
    for w in B.get("eligible_not_selected", []):
        if w.get("lon") is not None:
            ax.scatter(w["lon"], w["lat"], s=18, facecolors="none",
                       edgecolors=TIER_COLOR.get(w["tier"], "#6b7280"), linewidths=0.8)
    for w in B.get("tc_wells", []):
        if w.get("lon") is not None:
            ax.scatter(w["lon"], w["lat"], s=26, color=TIER_COLOR.get(w["tier"], "#6b7280"), zorder=3)
    handles = [plt.Line2D([], [], color=c, marker="o", linestyle="", label=f"TC well â€” {t}")
               for t, c in TIER_COLOR.items()]
    handles += [plt.Line2D([], [], color="#7c3aed", label="Novi BASE_CASE (inside)"),
                plt.Line2D([], [], color="#db2777", label="narvi preview stick"),
                plt.Line2D([], [], color="#6b7280", marker="o", markerfacecolor="none",
                           linestyle="", label="eligible, not selected")]
    ax.legend(handles=handles, fontsize=7, loc="upper right")
    if lat0:
        ax.set_aspect(1 / math.cos(math.radians(lat0)))
    ax.set_title(f"{bench} â€” TC wells by co-development tier", fontsize=10)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
