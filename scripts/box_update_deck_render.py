"""Maps + deck for scripts.box_update_deck (pure: reads the frame / extents / artifact written by `frame`; no database access).

Maps per bench (PNG, UTM 13N ft, north up): oil EUR/ft BOX | Novi on ONE shared binned blue ramp, GOR12 BOX | Novi on one shared
orange ramp, and BOX / Novi oil EUR on a diverging red | grey | blue scale (red = BOX below Novi). Context: TX/NM survey blocks,
the state line, the bench's extent of record. Deck: the Blue Ox brand template (anduin deal_slide.pptx: top / bottom bars,
CONFIDENTIAL footer), slides added on its "Title Only" layout.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

from box import production_run9 as p9r  # noqa: E402
from scripts import box_update_deck as bud  # noqa: E402

BLUE = ["#86b6ef", "#5598e7", "#3987e5", "#2a78d6", "#1c5cab", "#184f95", "#0d366b"]  # sequential blue, steps 250-700 (ordinal, >= 2:1)
ORANGE = ["#f7b899", "#f29a72", "#ee804f", "#eb6834", "#c4521f", "#9a3e15", "#6e2a0b"]  # one-hue orange ramp (second sequential context)
DIVERGE = ["#a3201d", "#e34948", "#f2a3a2", "#c9c7c1", "#9ec5f4", "#3987e5", "#104281"]  # red | grey midpoint | blue
RATIO_EDGES = [0.0, 0.6, 0.75, 0.9, 1.11, 1.33, 1.67, np.inf]  # symmetric in log around 1
INK, MUTED, GRID = "#111827", "#6b7280", "#d9d9d9"
FIG_W, FIG_H, DPI = 6.2, 5.0, 220
MI = 5280.0


def nice(x: float) -> float:
    if x <= 0:
        return 0.0
    p = 10 ** np.floor(np.log10(x))
    return float(round(x / p * 2) / 2 * p)  # 2 significant-ish figures on a 0.5 step


def shared_edges(a: np.ndarray, b: np.ndarray, n: int = 7) -> list[float]:
    """n bins from the pooled values of both maps (quantiles, rounded, strictly increasing); open-ended outer bins."""
    v = np.concatenate([a[np.isfinite(a)], b[np.isfinite(b)]])
    qs = [nice(float(np.quantile(v, q))) for q in np.linspace(0, 1, n + 1)[1:-1]]
    out: list[float] = []
    for q in qs:
        if not out or q > out[-1]:
            out.append(q)
    return [-np.inf, *out, np.inf]


class Context:
    def __init__(self, out: Path) -> None:
        self.ext = {b: shapely.from_wkt(w) for b, w in json.loads((out / "extents.json").read_text(encoding="utf-8")).items()}
        self.ext_ft = dict(zip(self.ext, bud.eg.to_ft(list(self.ext.values())), strict=True))
        gj = json.loads(bud.BLOCKS.read_text(encoding="utf-8"))
        geoms = [shapely.geometry.shape(f["geometry"]).boundary for f in gj["features"] if f.get("geometry")]
        self.blocks = bud.eg.to_ft(geoms)
        self.tree = shapely.STRtree(self.blocks)
        self.state = bud.eg.to_ft([shapely.LineString([(-106.65, 32.0), (-103.064, 32.0), (-103.064, 36.5)])])[0]


def _lines(geoms: list[Any]) -> list[np.ndarray]:
    out = []
    for g in geoms:
        for part in getattr(g, "geoms", [g]):
            if part.geom_type == "LineString":
                out.append(np.asarray(part.coords))
            elif part.geom_type == "Polygon":
                out.append(np.asarray(part.exterior.coords))
    return out


def draw(ctx: Context, bench_ext: str, sticks: list[np.ndarray], vals: np.ndarray, edges: list[float], colors: list[str], title: str,
         cbar_label: str, ticklabels: list[str], fname: Path, note: str) -> None:
    ext = ctx.ext_ft[bench_ext]
    x0, y0, x1, y1 = ext.bounds
    pad = 0.04 * max(x1 - x0, y1 - y0)
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    ax = fig.add_axes((0.01, 0.17, 0.98, 0.75))
    box = shapely.box(x0, y0, x1, y1)
    bl = [ctx.blocks[i] for i in ctx.tree.query(box)]
    ax.add_collection(LineCollection(_lines([b.intersection(box) for b in bl]), colors=GRID, linewidths=0.25, zorder=1))
    ax.add_collection(LineCollection(_lines([ctx.state.intersection(box)]), colors=MUTED, linewidths=0.8, linestyles="--", zorder=2))
    ax.add_collection(LineCollection(_lines([ext.boundary]), colors=INK, linewidths=0.9, zorder=3))
    order = np.argsort(np.nan_to_num(vals, nan=-np.inf))
    cmap, norm = ListedColormap(colors), BoundaryNorm(edges, len(colors))
    lc = LineCollection([sticks[i] for i in order], array=np.asarray(vals)[order], cmap=cmap, norm=norm, linewidths=1.0, zorder=4,
                        capstyle="round")
    ax.add_collection(lc)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_axis_off()
    sb = 10 * MI if (x1 - x0) > 40 * MI else 5 * MI
    ax.plot([x0 + pad * 0.5, x0 + pad * 0.5 + sb], [y0 + pad * 0.5] * 2, color=INK, lw=2, solid_capstyle="butt", zorder=5)
    ax.text(x0 + pad * 0.5, y0 + pad * 0.5 + 0.012 * (y1 - y0), f"{sb / MI:.0f} mi", fontsize=7, color=INK, zorder=5)
    fig.text(0.015, 0.955, title, fontsize=11, fontweight="bold", color=INK, va="center")
    fig.text(0.985, 0.955, note, fontsize=7.5, color=MUTED, va="center", ha="right")
    cax = fig.add_axes((0.10, 0.075, 0.80, 0.035))
    for i, c in enumerate(colors):
        cax.add_patch(plt.Rectangle((i, 0), 0.97, 1, color=c))
    cax.set_xlim(0, len(colors))
    cax.set_ylim(0, 1)
    cax.set_yticks([])
    cax.set_xticks(np.arange(1, len(colors)))
    cax.set_xticklabels(ticklabels, fontsize=7, color=INK)
    cax.tick_params(length=0, pad=2)
    for s in cax.spines.values():
        s.set_visible(False)
    fig.text(0.5, 0.012, cbar_label, fontsize=7.5, color=MUTED, ha="center", va="bottom")
    fig.savefig(fname, dpi=DPI, facecolor="white")
    plt.close(fig)


def _fmt(e: float) -> str:
    return f"{e:,.0f}" if e >= 10 else f"{e:g}"


def cmd_maps(a: Any) -> int:
    f = pd.read_csv(a.out / "frame.csv")
    ctx = Context(a.out)
    md = a.out / "maps"
    md.mkdir(exist_ok=True)
    meta = {}
    for g in p9r.GROUPS:
        x = f[f["group"] == g].reset_index(drop=True)
        sticks = [np.asarray(s.coords) for s in bud.project(list(x["wkt"]))]
        be = bud.EXTENT_OF[g]
        n = f"{len(x):,} PUD locations"
        e_eur = shared_edges(x["box_eur_ft"].to_numpy(), x["novi_eur_ft"].to_numpy())
        e_gor = shared_edges(x["box_gor12"].to_numpy(), x["novi_gor12"].to_numpy())
        lab_eur, lab_gor = [_fmt(e) for e in e_eur[1:-1]], [_fmt(e) for e in e_gor[1:-1]]
        ce, cg = BLUE[: len(e_eur) - 1], ORANGE[: len(e_gor) - 1]
        L = bud.label(g)
        jobs = [("eur_box", x["box_eur_ft"], e_eur, ce, f"{L} — BOX run 9 oil EUR / ft", "Oil EUR, bbl per ft of lateral, 30-yr basis (shared scale)", lab_eur),
                ("eur_novi", x["novi_eur_ft"], e_eur, ce, f"{L} — Novi BASE_CASE oil EUR / ft", "Oil EUR, bbl per ft of lateral, 30-yr basis (shared scale)", lab_eur),
                ("gor_box", x["box_gor12"], e_gor, cg, f"{L} — BOX run 9 GOR, first 12 months", "12-month cumulative GOR, scf/bbl (shared scale)", lab_gor),
                ("gor_novi", x["novi_gor12"], e_gor, cg, f"{L} — Novi BASE_CASE GOR, first 12 months", "12-month cumulative GOR, scf/bbl (shared scale)", lab_gor),
                ("ratio", x["ratio"], RATIO_EDGES, DIVERGE, f"{L} — BOX ÷ Novi oil EUR", "BOX ÷ Novi oil EUR (30-yr): red = BOX below Novi, blue = BOX above",
                 [f"{e:g}" for e in RATIO_EDGES[1:-1]])]
        for key, v, edges, cols, title, cl, tl in jobs:
            draw(ctx, be, sticks, v.to_numpy(float), edges, cols, title, cl, tl, md / f"{g}_{key}.png", n)
        meta[g] = {"eur_edges": e_eur[1:-1], "gor_edges": e_gor[1:-1]}
        print(f"{g}: 5 maps", flush=True)
    (md / "edges.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return 0


# ----------------------------------------------------------------------------
# deck
# ----------------------------------------------------------------------------


def cmd_deck(a: Any) -> int:
    from scripts import box_update_slides as sl

    with open(a.artifact / "run.pkl", "rb") as fh:
        A = pickle.load(fh)
    f = pd.read_csv(a.out / "frame.csv")
    out = a.pptx or (a.out / "BOX_update_2026-10-19.pptx")
    sl.build(A, f, a.out / "maps", out)
    print(f"wrote {out}")
    return 0
