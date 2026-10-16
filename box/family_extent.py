"""BOX step 15 — D27 development-envelope extents for a bench family (read-only; nothing stored).

Plan docs/box_type_curves_plan.md §5 step 15: after the family's bench QC + pooling gate, build each bench's extent
with the step-3 method of record, unchanged:

  * edge metric D23 (r = 2,640 ft pin radius, c = 3,960 ft closing — one value per basin, tuned on WCA);
  * buffer rule + calibration of record: the step-3 pick (k, cap, floor, perf reference) read from the step-3
    summary.json — NOT re-calibrated (a per-bench re-pick would be a new decision); the D27 envelope (development
    always in, gaps < 8 mi bridged, no voids, generalized edge), D24 potash ignore-gap, D26 legacy fill, no updip limit;
  * box/extent_report.build_pool / envelope_backtest, box/extent_package (geology shapefiles NAD83 UTM 14N US-ft),
    box/extent_pages.pool_page — the same code that built the record extents.

Regression guard (``reproduce``): the same code + params rebuilt from the frozen gate-1 sets reproduce the record
extents' areas (WCA 6,168.65 / BS2_S 3,358.45 sq mi, step-3 summary.json), so generalising the tooling moved nothing.
Gate 15a decision (2026-10-16): BS3_S and BS3_C are NOT pooled — one extent per bench.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Polygon, shape

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import extent as ex
from box import extent_package as pkg
from box import extent_pages as pages
from box import extent_report as er
from box import geology_io as gio

STEP3_DIR = Path("docs") / "box" / "step3-2026-10-07"


def record_params(step3_dir: Path = STEP3_DIR) -> ex.BufferParams:
    """The buffer parameters the record extents were built with (step-3 summary.json)."""
    s = json.loads((step3_dir / "summary.json").read_text(encoding="utf-8"))
    names = {f.name for f in fields(ex.BufferParams)}
    return ex.BufferParams(**{k: v for k, v in s["buffer_params"].items() if k in names})


def record_extents(step3_dir: Path = STEP3_DIR) -> dict[str, Any]:
    """Record extents (v1 generated = box.extent ids 6 / 7 within 0.005 sq mi) as UTM 13N ft polygons."""
    out = {}
    for f in sorted(step3_dir.glob("extent_*_v1.geojson")):
        gj = json.loads(f.read_text(encoding="utf-8"))
        feat = next(x for x in gj["features"] if x["properties"].get("layer") == "extent")
        out[feat["properties"]["pool"]] = eg.to_ft([shape(feat["geometry"])])[0]
    return out


def reproduce(conn: Any, bp: ex.BufferParams, gate1_dir: Path, step3_dir: Path = STEP3_DIR) -> dict[str, Any]:
    """Rebuild the record pools from the frozen gate-1 sets with ``bp``; compare areas with the step-3 summary."""
    s = json.loads((step3_dir / "summary.json").read_text(encoding="utf-8"))
    pools = tuple(s["pools"])
    df = egr.load_final_sets(gate1_dir, pools)
    df = egr.attach_geometry(df, egr.pull_laterals(conn, sorted(df["api10"].unique())))
    sopa = er.load_sopa()
    out = {}
    for pool in pools:
        b = er.build_pool(df[df.pool == pool], pool, bp, sopa, None)
        rec = float(s["pools"][pool]["extent_sqmi"])
        got = float(b["stats"]["extent_sqmi"])
        out[pool] = {"record_sqmi": rec, "rebuilt_sqmi": got, "rel_diff": got / rec - 1}
    return out


def overlap_table(builds: dict[str, dict[str, Any]], rec: dict[str, Any]) -> pd.DataFrame:
    """Area shared by every pair of extents (this family + the record pools), sq mi."""
    polys = {**{p: b["extent"] for p, b in builds.items()}, **{f"{p} (record)": g for p, g in rec.items()}}
    rows = []
    for a in builds:
        for k, g in polys.items():
            if k == a:
                continue
            inter = polys[a].intersection(g).area / eg.FT_PER_MI**2
            rows.append({"extent": a, "other": k, "shared_sqmi": inter, "share_of_extent": inter / (polys[a].area / eg.FT_PER_MI**2)})
    return pd.DataFrame(rows)


def overview_png(builds: dict[str, dict[str, Any]], rec: dict[str, Any], sopa: Any) -> str:
    cols = {"BS3_S": "#0891b2", "BS3_C": "#c2410c", "WCA": "#1e3a8a", "BS2_S": "#16a34a"}
    fig, axes = plt.subplots(1, len(builds), figsize=(8 * len(builds), 8.5))
    for ax, (pool, b) in zip(np.atleast_1d(axes), builds.items()):
        for p, g in rec.items():
            for part in ex.as_multi(g).geoms:
                c = np.asarray(part.exterior.coords)
                ax.plot(c[:, 0], c[:, 1], color=cols.get(p, "#6b7280"), lw=0.8, ls=":", label=f"{p} record extent" if part is ex.as_multi(g).geoms[0] else None)
        for other, ob in builds.items():
            if other == pool:
                continue
            for part in ob["extent"].geoms:
                c = np.asarray(part.exterior.coords)
                ax.plot(c[:, 0], c[:, 1], color=cols.get(other, "#6b7280"), lw=1.0, ls="--", label=f"{other} proposed" if part is ob["extent"].geoms[0] else None)
        for part in ex.as_multi(sopa).geoms:
            c = np.asarray(part.exterior.coords)
            ax.fill(c[:, 0], c[:, 1], color="#0ea5e9", alpha=0.08, lw=0)
        pr = b["prep"]
        for ln in pr.r["old"].geom:
            c = np.asarray(ln.coords)
            ax.plot(c[:, 0], c[:, 1], color="#9ca3af", lw=0.4)
        for ln in pr.r["ev"].geom:
            c = np.asarray(ln.coords)
            ax.plot(c[:, 0], c[:, 1], color=cols.get(pool, "#111827"), lw=0.6)
        for part in b["extent"].geoms:
            c = np.asarray(part.exterior.coords)
            ax.plot(c[:, 0], c[:, 1], color="#111827", lw=1.8, label=f"{pool} proposed extent" if part is b["extent"].geoms[0] else None)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        st = b["stats"]
        ax.set_title(f"{pool}: {st['extent_sqmi']:,.0f} sq mi, {st['n_parts']} part(s); laterals ≥ 2016 coloured (n={st['n_evidence']:,}), pre-2016 grey", fontsize=10)
        ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    return egr._png(fig, dpi=90)


def index_html(builds: dict[str, dict[str, Any]], ctx: dict[str, Any]) -> str:
    bp = ctx["bp"]
    rows = []
    for p, b in builds.items():
        st = b["stats"]
        rows.append({"bench": f"<a href=extent_{p}.html>{p}</a>", "extent sq mi": st["extent_sqmi"], "drilled core sq mi": st["core_sqmi"], "parts": st["n_parts"],
                     "holes": st["n_holes"], "evidence laterals (≥ 2016)": st["n_evidence"], "pre-2016": st["n_pre2016"], "interior median oil12 / kft": st["interior_median_oil12_kft"],
                     "live fronts": ", ".join(st["fronts"]) or "none", "isolated tests out": st["n_isolated_tests"], "≥ 2016 laterals outside": st["developed_outside"],
                     "bridged sq mi": st["bridged_sqmi"], "pinned+strong flag mi": st["flagged_pinned_strong_mi"]})
    tab = pd.DataFrame(rows)
    reg = pd.DataFrame([{"pool": k, **v} for k, v in ctx["regression"].items()]) if ctx.get("regression") else pd.DataFrame()
    parts = [
        f"<!doctype html><html><head><meta charset=utf-8><title>BOX 15a — BS3 extents</title><style>{egr._CSS}</style></head><body>",
        "<h1>BOX step 15a — proposed D27 extents: BS3_S and BS3_C (v1, generated, NOT stored)</h1>",
        (f"<div class=meta>Built {ctx['built']} at {ctx['git_sha']}. Read-only. Well sets = the gate-15a QC sets (<code>../wells_final_BS3_*.csv</code>; not pooled, gate 15a 2026-10-16). "
         f"Method of record unchanged: edge metric D23 (r = 2,640 ft, c = 3,960 ft), buffer k = {bp.k:g}, cap = {bp.cap_ft:,.0f} ft, floor = {bp.floor_ft:,.0f} ft, {bp.perf_ref} reference "
         f"(step-3 calibration of record, not re-picked), D27 envelope ({bp.min_cluster}-lateral development clusters within {bp.bridge_mi:g} mi in, gaps < {bp.bridge_mi:g} mi bridged, no voids), "
         "D24 potash, D26 legacy fill, no updip limit. Gate summary: <code>FINDINGS.md</code>. Geology package: <code>geology/</code>.</div>"),
        "<h2>Extents</h2>" + egr._table(tab, {"extent sq mi": ",.0f", "drilled core sq mi": ",.0f", "interior median oil12 / kft": ",.0f", "bridged sq mi": ",.0f", "pinned+strong flag mi": ",.1f"}).replace("&lt;a href", "<a href").replace("&gt;", ">").replace("&lt;/a", "</a"),
        f"<img src='{ctx['overview_png']}' style='max-width:100%'>",
        "<h2>Overlap with each other and with the record extents</h2>" + egr._table(ctx["overlap"], {"shared_sqmi": ",.0f", "share_of_extent": ".0%"}),
        "<h2>D1 PUD universe inside (read-only count; ≥ 50 % of the stick inside)</h2>" + egr._table(ctx["pud_summary"], {}),
        "<h2>Envelope backtest on these benches (check, not a re-calibration)</h2><div class=meta>Same test as step 3: the extent rebuilt from laterals online before each cutoff; later wells ≥ 50 % outside the cutoff core and within 3 mi of it, 12-mo known: share of performing (≥ 0.70× interior) vs rolled ones it contains.</div>"
        + egr._table(ctx["env_bt"], {"area_sqmi": ",.0f", "tpr": ".2f", "fpr": ".2f", "j": ".2f", "precision": ".2f"}),
        "<h2>Regression guard: record extents rebuilt with this code</h2>" + (egr._table(reg, {"record_sqmi": ",.2f", "rebuilt_sqmi": ",.2f", "rel_diff": ".2e"}) if len(reg) else "<div class=meta>skipped</div>"),
        "</body></html>",
    ]
    return "\n".join(parts)


def run(conn: Any, wells_dir: Path, out: Path, pools: tuple[str, ...], version: int = 1, gate1_dir: Path | None = None, git_sha: str = "") -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    geo_dir = out / "geology"
    bp = record_params()
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    df = egr.load_final_sets(wells_dir, pools)
    df = egr.attach_geometry(df, egr.pull_laterals(conn, sorted(df["api10"].unique())))
    n_nogeom = df.groupby("pool")["geom"].apply(lambda s: int(s.isna().sum())).to_dict()
    sopa = er.load_sopa()
    builds = {pool: er.build_pool(df[df.pool == pool], pool, bp, sopa, None) for pool in pools}
    env_bt = pd.DataFrame([r for pool in pools for r in er.envelope_backtest(df[df.pool == pool], pool, bp, sopa, None)])
    rec = record_extents()
    # D1 PUD universe (read-only)
    pud_tabs: dict[str, pd.DataFrame] = {}
    for pool, b in builds.items():
        env = eg.to_lonlat([shapely.box(*b["extent"].bounds).buffer(eg.FT_PER_MI)])[0].bounds
        pu = er.pull_puds(conn, [pool], env)
        pud_tabs[pool] = er.pud_counts(pu, {"in extent": b["extent"], "in drilled core": b["prep"].core, "in step-2 outline": Polygon(b["prep"].r["body"].exterior)})
    pud_summary = pd.concat([t[t.status == "D1 universe"].assign(pool=p) for p, t in pud_tabs.items()], ignore_index=True)
    # geology package
    files: list[Path] = pkg.write_sopa(geo_dir, sopa)
    for pool, b in builds.items():
        clip = gio.ft13_to_geology([shapely.box(*b["extent"].bounds).buffer(10 * eg.FT_PER_MI)])[0]
        cont = pkg.context_contours(pool, clip)
        files += pkg.write_pool(geo_dir, pool, version, built, b, bp, cont)
        pkg.legend_png(geo_dir / f"BOX_{pool}_legend.png", pool, b, sopa, bp, version)
        b["stats"]["n_contours"] = {k: len(v) for k, v in cont.items()}
    rule_txt = (
        f"  pinned edge: floor = {bp.floor_ft:,.0f} ft (rolled) / {1.5 * bp.floor_ft:,.0f} (unknown) / {2 * bp.floor_ft:,.0f} (strong)\n"
        f"  gap: k x gap length x perf (strong 1.0 / unknown 0.75 / rolled 0.5), k = {bp.k:g}, within [floor, cap = {bp.cap_ft:,.0f} ft]\n"
        "  pre-2016 laterals beyond a gap -> floor; live-front side -> cap; potash area -> floor; no updip depth limit\n"
        f"  D27 envelope: development (step-out clusters >= {bp.min_cluster} laterals within {bp.bridge_mi:g} mi) always in; gaps < {bp.bridge_mi:g} mi bridged; no voids\n"
        f"  edge generalized: {bp.gen_tol_mi:g}-mi simplification, bulges over development, {bp.gen_round_mi:g}-mi rounding"
    )
    (geo_dir / "README.txt").write_text(pkg.README.format(built=built, pools=", ".join(pools), version=version, rule=rule_txt), encoding="utf-8")
    regression = reproduce(conn, bp, gate1_dir) if gate1_dir is not None else {}
    ctx = {"env_bt": env_bt, "built": built, "bp": bp, "version": version, "puds": pud_tabs, "sopa_ll": eg.to_lonlat([sopa.simplify(200.0)])[0], "git_sha": git_sha,
           "overlap": overlap_table(builds, rec), "overview_png": overview_png(builds, rec, sopa), "pud_summary": pud_summary, "regression": regression}
    for pool, b in builds.items():
        (out / f"extent_{pool}.html").write_text(pages.pool_page(pool, b, ctx), encoding="utf-8")
        (out / f"extent_{pool}_v{version}.geojson").write_text(json.dumps(er._geojson(b, pool, version, bp, built)), encoding="utf-8")
        b["edges"].drop(columns=["geom"]).to_csv(out / f"edges_{pool}.csv", index=False)
        b["prep"].stepouts.drop(columns=["ix"]).to_csv(out / f"stepouts_{pool}.csv", index=False)
        b["holes"].drop(columns=["geom"]).to_csv(out / f"holes_{pool}.csv", index=False)
        pud_tabs[pool].assign(pool=pool).to_csv(out / f"pud_counts_{pool}.csv", index=False)
    (out / "index.html").write_text(index_html(builds, ctx), encoding="utf-8")
    env_bt.to_csv(out / "backtest_envelope.csv", index=False)
    ctx["overlap"].to_csv(out / "overlap.csv", index=False)
    summary = {
        "built_at": built, "git_sha": git_sha, "wells_dir": str(wells_dir), "version": version, "edge_params": asdict(er.EDGE), "buffer_params": asdict(bp),
        "params_source": str(STEP3_DIR / "summary.json"), "laterals_without_geometry": n_nogeom,
        "pools": {p: b["stats"] for p, b in builds.items()}, "envelope_backtest": env_bt.to_dict(orient="records"),
        "overlap": ctx["overlap"].to_dict(orient="records"), "pud_d1": pud_summary.to_dict(orient="records"), "regression": regression,
        "geology_files": [str(f.relative_to(out)) for f in files],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else str(x)), encoding="utf-8")
    return {"summary": summary, "builds": builds, "bp": bp}


# ----------------------------------------------------------------------------
# Visual check: extent over the bench's structure grid + PDP laterals (Michael 2026-10-16)
# ----------------------------------------------------------------------------


def visual_check_png(pool: str, wells: pd.DataFrame, extent_ft13: Any, sopa: Any, path: Path, dpi: int = 110, label: str = "one-body D27 extent as is") -> dict[str, Any]:
    """One static map in the geology frame (NAD83 UTM 14N US-ft): filled structure of the bench top (Holden HCA grid,
    D25 context), 250-ft contours, PDP laterals (>= 2016 coloured by 12-mo oil / kft, pre-2016 grey), the extent,
    the potash area and the 32 N / -103 state lines."""
    top_f, _ = pkg.GRIDS[pool]
    xs, ys, Z = pkg._grid(pkg.GRID_DIR / top_f)
    ev = wells[wells["evidence"] & wells["geom"].notna()]
    old = wells[~wells["evidence"] & wells["geom"].notna()]
    ev_g = gio.ft13_to_geology(list(ev["geom"]))
    old_g = gio.ft13_to_geology(list(old["geom"]))
    ext_g = gio.ft13_to_geology([extent_ft13])[0]
    sopa_g = gio.ft13_to_geology([sopa])[0]
    allb = shapely.total_bounds(np.asarray(ev_g + old_g, dtype=object))
    pad = 5 * 5280.0
    x0, y0, x1, y1 = allb[0] - pad, allb[1] - pad, allb[2] + pad, allb[3] + pad
    fig, ax = plt.subplots(figsize=(13, 13))
    mx = (xs >= x0) & (xs <= x1)
    my = (ys >= y0) & (ys <= y1)
    Zc = Z[np.ix_(my, mx)]
    finite = Zc[np.isfinite(Zc)]
    if finite.size:
        lv = np.arange(np.floor(finite.min() / 250) * 250, np.ceil(finite.max() / 250) * 250 + 250, 250)
        cf = ax.contourf(xs[mx], ys[my], np.ma.masked_invalid(Zc), levels=lv, cmap="terrain_r", alpha=0.55)
        cs = ax.contour(xs[mx], ys[my], np.ma.masked_invalid(Zc), levels=lv[::2], colors="#374151", linewidths=0.35)
        ax.clabel(cs, fmt="%d", fontsize=6)
        cb = fig.colorbar(cf, ax=ax, shrink=0.55, pad=0.01)
        cb.set_label(f"{top_f.split('_STRUCTURE')[0]} structure (grid Z, ft ~ KB TVD)")
    for g in ex.as_multi(sopa_g).geoms:
        c = np.asarray(g.exterior.coords)
        ax.fill(c[:, 0], c[:, 1], color="#0ea5e9", alpha=0.10, lw=0.6, ec="#0ea5e9")
    for g in old_g:
        c = np.asarray(g.coords)
        ax.plot(c[:, 0], c[:, 1], color="#6b7280", lw=0.5, alpha=0.7)
    oil = ev["oil12_kft"].to_numpy(float)
    lo, hi = np.nanpercentile(oil, [5, 95]) if np.isfinite(oil).any() else (0, 1)
    cmap = plt.get_cmap("RdYlBu_r")
    for g, v in zip(ev_g, oil):
        c = np.asarray(g.coords)
        col = "#111827" if not np.isfinite(v) else cmap((min(max(v, lo), hi) - lo) / (hi - lo))
        ax.plot(c[:, 0], c[:, 1], color=col, lw=1.1)
    for g in ex.as_multi(ext_g).geoms:
        c = np.asarray(g.exterior.coords)
        ax.plot(c[:, 0], c[:, 1], color="#111827", lw=2.2)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(lo, hi))
    cb2 = fig.colorbar(sm, ax=ax, shrink=0.55, pad=0.06, location="left")
    cb2.set_label(">= 2016 laterals: 12-mo oil, bbl / 1,000 ft (p5-p95; black = < 12 mo)")
    # state lines (32 N, -103 W) in the geology frame
    from shapely.geometry import LineString

    sl = gio.ft13_to_geology(eg.to_ft([LineString([(-105.0, 32.0), (-103.0, 32.0)]), LineString([(-103.0, 31.0), (-103.0, 33.5)])]))
    for g in sl:
        c = np.asarray(g.coords)
        ax.plot(c[:, 0], c[:, 1], color="#111827", lw=0.8, ls="--")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    area = extent_ft13.area / eg.FT_PER_MI**2
    ax.set_title(f"{pool}: {label} ({area:,.0f} sq mi, black) over {top_f.split('_STRUCTURE')[0]} structure; "
                 f">= 2016 laterals coloured (n={len(ev):,}), pre-2016 grey (n={len(old):,}); potash area blue; dashed = TX/NM line", fontsize=9)
    fig.tight_layout()
    fig.set_dpi(dpi)
    fig.canvas.draw()
    # pixel frame of the saved PNG (origin top-left) for reading hand edits drawn over it (pptx_edits)
    (px0, py0), (px1, py1) = ax.transData.transform([(x0, y0), (x1, y1)])
    H = fig.get_size_inches()[1] * dpi
    frame = {"data": [x0, y0, x1, y1], "pix": [float(px0), float(H - py0), float(px1), float(H - py1)], "size": [fig.get_size_inches()[0] * dpi, H]}
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    inside = shapely.length(shapely.intersection(np.asarray(list(ev["geom"]), dtype=object), extent_ft13)) / shapely.length(np.asarray(list(ev["geom"]), dtype=object)) >= 0.5
    return {"pool": pool, "n_evidence": len(ev), "n_inside": int(inside.sum()), "n_outside": int((~inside).sum()), "extent_sqmi": area, "frame": frame}


# ----------------------------------------------------------------------------
# Hand edits drawn over the visual-check PNG in PowerPoint (Michael 2026-10-16, bs3_extents.pptx)
# ----------------------------------------------------------------------------



def _bezier(p0: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float], n: int = 12) -> list[tuple[float, float]]:
    t = np.linspace(0, 1, n + 1)[1:]
    a, b, c, d = (np.asarray(p, float) for p in (p0, p1, p2, p3))
    pts = ((1 - t) ** 3)[:, None] * a + (3 * (1 - t) ** 2 * t)[:, None] * b + (3 * (1 - t) * t**2)[:, None] * c + (t**3)[:, None] * d
    return [tuple(x) for x in pts]


def pptx_freeforms(pptx: Path) -> dict[int, dict[str, Any]]:
    """slide no -> {'picture': (off_x, off_y, cx, cy) EMU, 'image': media name, 'lines': [[(x, y) EMU], ...]} for every
    freeform shape (moveTo / lnTo / cubicBezTo, beziers sampled) drawn over the slide's picture."""
    import re
    import zipfile

    out: dict[int, dict[str, Any]] = {}
    with zipfile.ZipFile(pptx) as z:
        slides = sorted(n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
        for name in slides:
            k = int(re.search(r"(\d+)\.xml$", name).group(1))
            xml = z.read(name).decode("utf-8")
            rels = z.read(f"ppt/slides/_rels/slide{k}.xml.rels").decode("utf-8")
            pic = xml[xml.index("<p:pic>"):xml.index("</p:pic>")]
            rid = re.search(r'r:embed="(rId\d+)"', pic).group(1)
            media = re.search(rf'Id="{rid}"[^>]*Target="\.\./media/([^"]+)"', rels) or re.search(rf'Target="\.\./media/([^"]+)"[^>]*Id="{rid}"', rels)
            po = tuple(int(v) for v in re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(\d+)" cy="(\d+)"/>', pic).groups())
            if "<a:srcRect" in pic and re.search(r'<a:srcRect [^/]*[ltrb]="', pic):
                raise ValueError(f"slide {k}: cropped picture not supported")
            lines = []
            for sp in re.findall(r"<p:sp>.*?</p:sp>", xml, flags=re.DOTALL):
                if "<a:custGeom>" not in sp:
                    continue
                if re.search(r'<a:xfrm[^>]*(rot|flipH|flipV)=', sp):
                    raise ValueError(f"slide {k}: rotated / flipped freeform not supported")
                ox, oy, cx, cy = (int(v) for v in re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(\d+)" cy="(\d+)"/>', sp).groups())
                for pw, ph, body in re.findall(r'<a:path w="(\d+)" h="(\d+)"[^>]*>(.*?)</a:path>', sp, flags=re.DOTALL):
                    sx, sy = cx / int(pw), cy / int(ph)
                    pts: list[tuple[float, float]] = []
                    for tag, inner in re.findall(r"<a:(moveTo|lnTo|cubicBezTo)>(.*?)</a:\1>", body, flags=re.DOTALL):
                        q = [(ox + int(a) * sx, oy + int(b) * sy) for a, b in re.findall(r'<a:pt x="(-?\d+)" y="(-?\d+)"/>', inner)]
                        if tag == "cubicBezTo" and pts:
                            pts += _bezier(pts[-1], q[0], q[1], q[2])
                        else:
                            pts += q
                    lines.append(pts)
            out[k] = {"picture": po, "image": media.group(1) if media else None, "lines": lines}
    return out


def emu_to_geology(pts: list[tuple[float, float]], picture: tuple[int, int, int, int], frame: dict[str, Any]) -> list[tuple[float, float]]:
    """Slide EMU -> PNG pixel (the picture is the uncropped PNG) -> axes data (NAD83 UTM 14N US-ft)."""
    ox, oy, cx, cy = picture
    W, H = frame["size"]
    x0, y0, x1, y1 = frame["data"]
    px0, py0, px1, py1 = frame["pix"]  # pixel of (x0, y0) and (x1, y1), origin top-left
    out = []
    for ex_, ey in pts:
        px = (ex_ - ox) / cx * W
        py = (ey - oy) / cy * H
        out.append((x0 + (px - px0) / (px1 - px0) * (x1 - x0), y0 + (py - py0) / (py1 - py0) * (y1 - y0)))
    return out


def apply_hand_edit(generated_ft13: Any, edit_line_geo: list[tuple[float, float]]) -> tuple[Any, Any]:
    """An open hand-drawn line whose ends sit on (or near) the generated extent: close it with a straight chord, take
    the enclosed area, union with the generated extent, fill voids (D27). Returns (edited extent, added polygon), UTM 13N ft."""
    from shapely.geometry import LineString as _LS
    from shapely.validation import make_valid

    line = gio.geology_to_ft13([_LS(edit_line_geo)])[0]
    ring = list(line.coords) + [line.coords[0]]
    poly = make_valid(Polygon(ring))
    polys = [g for g in getattr(poly, "geoms", [poly]) if g.geom_type == "Polygon"]
    add = shapely.union_all(polys)
    edited = ex.as_multi(shapely.union_all([generated_ft13, add]).buffer(0))
    edited = ex.as_multi(shapely.union_all([Polygon(g.exterior) for g in edited.geoms]))  # no voids (D27)
    return edited, add.difference(generated_ft13)


def run_edits(conn: Any, pptx: Path, slide_pool: dict[int, str], wells_dir: Path, ext_dir: Path, version: int = 1, git_sha: str = "") -> dict[str, Any]:
    """Michael's hand edits -> edited extents (v1 edited, NOT stored): shapefile in the geology round-trip format, the
    step-3 diff page, the visual check redrawn with the edited outline, laterals + D1 PUDs inside generated vs edited."""
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    ff = pptx_freeforms(pptx)
    df = egr.load_final_sets(wells_dir, tuple(slide_pool.values()))
    df = egr.attach_geometry(df, egr.pull_laterals(conn, sorted(df["api10"].unique())))
    sopa = er.load_sopa()
    edit_dir = ext_dir / "edited"
    edit_dir.mkdir(parents=True, exist_ok=True)
    res: dict[str, Any] = {"built_at": built, "git_sha": git_sha, "source": str(pptx), "pools": {}}
    for k, pool in slide_pool.items():
        gj = json.loads((ext_dir / f"extent_{pool}_v{version}.geojson").read_text(encoding="utf-8"))
        feat = next(x for x in gj["features"] if x["properties"].get("layer") == "extent")
        gen = ex.as_multi(eg.to_ft([shape(feat["geometry"])])[0])
        w = df[df.pool == pool]
        tmp = visual_check_png(pool, w, gen, sopa, edit_dir / f"_frame_{pool}.png")
        (edit_dir / f"_frame_{pool}.png").unlink()
        if len(ff[k]["lines"]) != 1:
            raise ValueError(f"slide {k}: expected one freeform, found {len(ff[k]['lines'])}")
        geo_line = emu_to_geology(ff[k]["lines"][0], ff[k]["picture"], tmp["frame"])
        edited, _added = apply_hand_edit(gen, geo_line)
        # shapefile in the geology round-trip format (D7 / D28) + the step-3 diff page
        params = f"hand edit by Michael 2026-10-16 ({pptx.name} slide {k}) on generated v{version}"
        gio.write_layer(edit_dir / f"BOX_{pool}_extent_v{version}_edited", "polygon", gio.ft13_to_geology([edited]), pkg.EXTENT_FIELDS,
                        [[pool, "delaware", version, "geology_edited", edited.area / eg.FT_PER_MI**2, built, params]])
        d = ex.diff(gen, edited, shapely.centroid(gen))
        ev = w[w["evidence"] & w["geom"].notna()]
        L = np.asarray(list(ev["geom"]), dtype=object)

        def inside(g: Any, L: np.ndarray = L) -> np.ndarray:
            return shapely.length(shapely.intersection(L, g)) / shapely.length(L) >= 0.5

        env = eg.to_lonlat([shapely.box(*edited.bounds).buffer(eg.FT_PER_MI)])[0].bounds
        pu = er.pull_puds(conn, [pool], env)
        pt = er.pud_counts(pu, {"in generated": gen, "in edited": edited})
        (edit_dir / f"diff_{pool}_v{version}.html").write_text(pages.diff_page(pool, version, d, gen, edited, built, f"{pptx.name} slide {k}", pt), encoding="utf-8")
        pt.assign(pool=pool).to_csv(edit_dir / f"pud_counts_{pool}.csv", index=False)
        (edit_dir / f"extent_{pool}_v{version}_edited.geojson").write_text(json.dumps({
            "type": "FeatureCollection", "name": f"box_extent_{pool}_v{version}_edited", "crs_note": "EPSG:4326",
            "features": [{"type": "Feature", "properties": {"layer": "extent", "pool": pool, "version": version, "source": "geology_edited", "note": params},
                          "geometry": shapely.geometry.mapping(shapely.set_precision(eg.to_lonlat([edited])[0], 1e-6))}]}), encoding="utf-8")
        vis = visual_check_png(pool, w, edited, sopa, edit_dir / f"visual_{pool}_edited.png", label=f"extent v{version} EDITED by Michael (hand edit, {pptx.name})")
        ig, ie = inside(gen), inside(edited)
        d1 = pt[pt.status == "D1 universe"]
        res["pools"][pool] = {
            "slide": k, "generated_sqmi": gen.area / eg.FT_PER_MI**2, "edited_sqmi": edited.area / eg.FT_PER_MI**2, "added_sqmi": d["added_sqmi"], "removed_sqmi": d["removed_sqmi"],
            "n_parts": len(edited.geoms), "n_evidence": len(ev), "inside_generated": int(ig.sum()), "inside_edited": int(ie.sum()), "outside_edited": int((~ie).sum()),
            "d1_in_generated": int(d1["in generated"].sum()) if len(d1) else 0, "d1_in_edited": int(d1["in edited"].sum()) if len(d1) else 0,
            "outside_by_county": ev.loc[~ie, "county"].value_counts().head(8).to_dict(), "visual": str(vis["pool"]),
        }
    (edit_dir / "summary.json").write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    return res
