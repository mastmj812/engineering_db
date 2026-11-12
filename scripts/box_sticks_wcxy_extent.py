"""BOX sticks: WCXY extent, evidence map for a hand-drawn outline (read-only).

    python -m scripts.box_sticks_wcxy_extent --out docs/box_sticks/wcxy-extent-<date> --cache <phase 0 cache>
                                             [--verdicts docs/box_sticks/wcxy-cards-2026-11-12]

Michael 2026-11-12: no automated rule reproduces his XY / one-landing calls, so the WCXY extent is drawn by hand.
This builds what he draws on, in the geology frame the BOX pen-edit reader already uses (NAD83 UTM 14N US-ft,
box/family_extent.pptx_freeforms / pptx_ink / emu_to_geology + the .frame.json written here):

  * the geologist's XY interval thickness: WOLFCAMP_A top minus WOLFCAMP_XY top (HCA structure grids, 10-19 set);
  * every WCXY-tagged evidence well, coloured by how far it sits above the local WCA_1 landing surface;
  * Michael's card calls (XY / one landing);
  * a candidate outline from ALL WCXY-tagged wells with the BOX construction of record (er.build_pool, the step-3
    buffer parameters). Performance is not supplied, so every edge takes the "unknown" class; it is a guide only.

Nothing is stored. The outline of record will be the red loop(s) Michael draws (his convention, 2026-10-16).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from scipy.interpolate import RegularGridInterpolator

from box import edge_gap as eg
from box import edge_gap_report as egr
from box import extent as ex
from box import extent_package as pkg
from box import extent_report as er
from box import family_extent as fe
from box import geology_io as gio
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_wcxy as wx
from scripts import box_sticks_wcxy_cards as wc

POOL = "WCXY"
ISO_LEVELS = np.arange(0, 451, 25)


def to_geology_xy(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    g = gio.ft13_to_geology(eg.to_ft(list(shapely.points(lon, lat))))
    return shapely.get_coordinates(np.asarray(g, dtype=object))


def isopach() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """XY interval thickness (ft) on the WOLFCAMP_XY grid's lattice: WOLFCAMP_A top minus WOLFCAMP_XY top."""
    xs, ys, zxy = pkg._grid(pkg.require_grid("WOLFCAMP_XY"))
    ax, ay, za = pkg._grid(pkg.require_grid("WOLFCAMP_A"))
    if len(ax) != len(xs) or len(ay) != len(ys) or not (np.allclose(ax, xs) and np.allclose(ay, ys)):
        f = RegularGridInterpolator((ay, ax), za, bounds_error=False, fill_value=np.nan)
        gx, gy = np.meshgrid(xs, ys)
        za = f(np.column_stack([gy.ravel(), gx.ravel()])).reshape(len(ys), len(xs))
    return xs, ys, np.abs(za - zxy)


def sample(xs: np.ndarray, ys: np.ndarray, Z: np.ndarray, pts: np.ndarray) -> np.ndarray:
    f = RegularGridInterpolator((ys, xs), np.nan_to_num(Z, nan=-9999.0), method="nearest", bounds_error=False, fill_value=-9999.0)
    v = f(pts[:, ::-1])
    return np.where(v < -9000, np.nan, v)


def candidate(x: pd.DataFrame) -> tuple[object | None, str]:
    from etl.db import get_connection

    d = pd.DataFrame({"api10": x["api10"].astype(str), "well_name": x["well_name"], "operator": x["operator"], "state_code": x["state_code"],
                      "county": x["county"], "formation_blueox": POOL, "box_bench": POOL, "tvd_ft": x["depth_ft"],
                      "lateral_length_ft": x["lateral_length_ft"], "mid_lon": x["midpoint_lon"], "mid_lat": x["midpoint_lat"], "pool": POOL, "planned": False, "tvd_round": False, "cohort": False,
                      "oil12_kft": np.nan, "first_production_date": pd.to_datetime(x["first_production_date"]).dt.date})
    try:
        with get_connection() as conn:
            geo = egr.pull_laterals(conn, sorted(d["api10"].unique()))
        d = egr.attach_geometry(d, geo)
        b = er.build_pool(d[d["geom"].notna()], POOL, fe.record_params(), er.load_sopa(), None, er.edge_params("delaware"))
        return b["extent"], "BOX construction of record (er.build_pool), performance class unknown on every edge"
    except Exception as e:  # noqa: BLE001  a guide only: fall back rather than block the map
        print(f"build_pool failed ({type(e).__name__}: {e}); falling back to a 1.5-mi buffer envelope", flush=True)
        ft = eg.to_ft(list(shapely.points(x["midpoint_lon"].to_numpy(), x["midpoint_lat"].to_numpy())))
        u = shapely.union_all(shapely.buffer(np.asarray(ft, dtype=object), 4 * eg.FT_PER_MI)).buffer(-2.5 * eg.FT_PER_MI)
        return ex.as_multi(u), "FALLBACK: wells buffered 4 mi, eroded 2.5 mi (not the construction of record)"


def draw(x: pd.DataFrame, cards: pd.DataFrame | None, ext, iso: tuple, out: Path) -> dict:
    xs, ys, Z = iso
    pad = 6 * 5280.0
    x0, y0, x1, y1 = x["gx"].min() - pad, x["gy"].min() - pad, x["gx"].max() + pad, x["gy"].max() + pad
    fig, ax = plt.subplots(figsize=(14, 14))
    mx, my = (xs >= x0) & (xs <= x1), (ys >= y0) & (ys <= y1)
    Zc = np.ma.masked_invalid(Z[np.ix_(my, mx)])
    cf = ax.contourf(xs[mx], ys[my], Zc, levels=ISO_LEVELS, cmap="YlGnBu", alpha=0.75, extend="max")
    cs = ax.contour(xs[mx], ys[my], Zc, levels=ISO_LEVELS[::2], colors="#374151", linewidths=0.35)
    ax.clabel(cs, fmt="%d", fontsize=6)
    fig.colorbar(cf, ax=ax, shrink=0.5, pad=0.01).set_label("geologist's XY interval: WOLFCAMP_A top minus WOLFCAMP_XY top, ft (white = no grid)")
    sc = ax.scatter(x["gx"], x["gy"], c=x["above_wca1_ft"].clip(-50, 300), cmap="RdYlGn", vmin=-50, vmax=300, s=9, linewidths=0.2, edgecolors="#111827", zorder=3)
    na = x[x["above_wca1_ft"].isna()]
    ax.scatter(na["gx"], na["gy"], c="#9ca3af", s=9, linewidths=0.2, edgecolors="#111827", zorder=3)
    fig.colorbar(sc, ax=ax, shrink=0.5, pad=0.06, location="left").set_label("WCXY-tagged well: ft above the local WCA_1 landing surface (grey = no WCA_1 control)")
    if ext is not None:
        for g in ex.as_multi(gio.ft13_to_geology([ext])[0]).geoms:
            c = np.asarray(g.exterior.coords)
            ax.plot(c[:, 0], c[:, 1], color="#111827", lw=1.8, ls="--", zorder=4)
    if cards is not None:
        for v, mk, col in (("XY", "o", "#16a34a"), ("ONE", "X", "#111827")):
            c = cards[cards["verdict"] == v]
            ax.scatter(c["gx"], c["gy"], marker=mk, s=150, c=col, edgecolors="white", linewidths=1.2, zorder=5, label=f"card call: {'XY' if v == 'XY' else 'one landing'} ({len(c)})")
        for r in cards.itertuples():
            ax.annotate(str(r.card), (r.gx, r.gy), textcoords="offset points", xytext=(8, 6), fontsize=8, weight="bold", zorder=6,
                        bbox={"boxstyle": "round,pad=0.1", "fc": "white", "ec": "none", "alpha": 0.7})
        ax.legend(loc="lower left", fontsize=9)
    for county, g in x.groupby("county"):
        if len(g) >= 15:
            ax.text(g["gx"].median(), g["gy"].max() + 1.2 * 5280, str(county).upper(), fontsize=9, color="#374151", ha="center")
    from shapely.geometry import LineString

    for g in gio.ft13_to_geology(eg.to_ft([LineString([(-105.0, 32.0), (-103.0, 32.0)]), LineString([(-103.064, 31.0), (-103.064, 33.5)])])):
        c = np.asarray(g.coords)
        ax.plot(c[:, 0], c[:, 1], color="#111827", lw=0.8, ls=":")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    area = ext.area / eg.FT_PER_MI ** 2 if ext is not None else float("nan")
    ax.set_title(f"WCXY evidence map for a hand-drawn extent. Dashed black = candidate from every WCXY-tagged well ({area:,.0f} sq mi, a guide only); "
                 f"dotted = TX / NM line.\nDraw the extent as one or more closed RED loops; the loops become the extent.", fontsize=10)
    fig.tight_layout()
    dpi = 110
    fig.set_dpi(dpi)
    fig.canvas.draw()
    (px0, py0), (px1, py1) = ax.transData.transform([(x0, y0), (x1, y1)])
    H = fig.get_size_inches()[1] * dpi
    frame = {"pool": POOL, "png": "visual_WCXY.png", "data": [x0, y0, x1, y1], "pix": [float(px0), float(H - py0), float(px1), float(H - py1)],
             "size": [fig.get_size_inches()[0] * dpi, H]}
    fig.savefig(out / "visual_WCXY.png", dpi=dpi)
    plt.close(fig)
    (out / "visual_WCXY.frame.json").write_text(json.dumps(frame, default=float), encoding="utf-8")
    return frame


def run(out: Path, cache: Path | None, verdict_dir: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    w = p0.evidence(d["wells"], d["rule"])
    bw = w[w["basin"] == "delaware"].reset_index(drop=True)
    x = wx.classify(bw)
    x = x[x["midpoint_lon"].notna()].join(wx.landings(bw, x))
    g = to_geology_xy(x["midpoint_lon"].to_numpy(), x["midpoint_lat"].to_numpy())
    x["gx"], x["gy"] = g[:, 0], g[:, 1]
    iso = isopach()
    x["xy_interval_ft"] = sample(*iso, g)
    ext, how = candidate(x)
    p, x = wc.pads(x)
    cards = None
    if verdict_dir:
        v = pd.read_csv(verdict_dir / "verdicts.csv")
        cards = wc.sample(p)[["card", "group", "name", "county"]].merge(v[["card", "verdict"]], on="card")
        c = x.groupby("group")[["gx", "gy", "xy_interval_ft", "above_wca1_ft"]].median()
        cards = cards.join(c, on="group")
        cards.drop(columns=["group"]).sort_values("card").to_csv(out / "cards_on_map.csv", index=False)
    draw(x, cards, ext, iso, out)
    if ext is not None:
        (out / "candidate_WCXY.geojson").write_text(json.dumps({"type": "FeatureCollection", "name": "box_extent_WCXY_candidate", "crs_note": "EPSG:4326",
            "features": [{"type": "Feature", "properties": {"layer": "extent", "pool": POOL, "source": "candidate, not stored", "note": how},
                          "geometry": shapely.geometry.mapping(shapely.set_precision(eg.to_lonlat([ext])[0], 1e-6))}]}), encoding="utf-8")
    x[["api10", "well_name", "operator", "county", "state_code", "midpoint_lat", "midpoint_lon", "depth_ft", "above_wca1_ft", "xy_interval_ft"]].to_csv(out / "wcxy_wells.csv", index=False)
    has = x["xy_interval_ft"].notna()
    summary = {"built_at": dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds"), "code_sha": p0._git_sha(), "wcxy_wells": len(x),
               "candidate": {"how": how, "sqmi": float(ext.area / eg.FT_PER_MI ** 2) if ext is not None else None},
               "xy_interval_at_wells_ft": {"wells_on_grid": int(has.sum()), "p10": float(x.loc[has, "xy_interval_ft"].quantile(0.1)),
                                           "median": float(x.loc[has, "xy_interval_ft"].median()), "p90": float(x.loc[has, "xy_interval_ft"].quantile(0.9))},
               "corr_interval_vs_separation": float(x[["xy_interval_ft", "above_wca1_ft"]].corr().iloc[0, 1])}
    if cards is not None:
        summary["cards"] = {"xy_interval_ft_median_by_verdict": cards.groupby("verdict")["xy_interval_ft"].median().to_dict(),
                            "best_interval_cutoff": max(((float(t), int(((cards["xy_interval_ft"] >= t) == (cards["verdict"] == "XY")).sum()))
                                                         for t in range(0, 401, 10)), key=lambda r: r[1])}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    if cards is not None:
        print(cards.sort_values("xy_interval_ft")[["card", "name", "county", "verdict", "xy_interval_ft", "above_wca1_ft"]].to_string(index=False))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None)
    ap.add_argument("--verdicts", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.out, a.cache, a.verdicts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
