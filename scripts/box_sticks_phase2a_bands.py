"""BOX sticks, phase 2a addendum 2: spacing by extent band against the radius chain (read-only).

    python -m scripts.box_sticks_phase2a_bands --out docs/box_sticks/phase2a-<date> --cache <phase 0 cache>

Michael 2026-11-13: the development envelope of a bench is governed by structure or reservoir, not by a circle around
a well. Contour each extent into bands by distance inside its edge; a well informs spacing ALONG its band, not in
every direction (LSSH at 6 WPS against the Central Basin Platform edge says 6 WPS north-south along that edge, not
basinward). Expected to hold best on the mature primary benches (the WCA) and least on add-on zones such as DEAN.

Bands: distance of the lateral midpoint (wells) or polygon centroid (DSUs) inside the bench's BOX record extent edge,
BANDS_MI; outside the extent counts as the outer band. Methods, all clamped to [CAP, FLOOR]:
  chain          decided rule: 1 -> 2 -> 3 mi local median (>= min_gaps), else FLOOR;
  band           median gap of the bench's wells in the DSU's band, whole extent (>= BAND_MIN wells, else FLOOR);
  band_local     same band, within ALONG_MI of the DSU (>= min_gaps), else band;
  chain_band     the chain where it has local control, else band (the band replaces the flat FLOOR default).
Hold-out as in box_sticks_phase2a_surface: targets have their own value inside 1 mi and are predicted from wells
farther than 1, 2 or 3 mi. Nothing here is tuned, so all targets are scored. The adoption test is the one fixed for
the surface (ADOPT_* there), applied to chain_band. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.collections import PolyCollection
from matplotlib.colors import ListedColormap

from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase2a as p2
from scripts import box_sticks_phase2a_surface as sf

MI = p2.MI
FLOOR, CAP = p2.FLOOR_FT, p2.CAP_GUESS_FT
BANDS_MI = (2.0, 5.0, 10.0)          # band limits, miles inside the extent edge
BAND_NAMES = ["0-2 mi", "2-5 mi", "5-10 mi", "10+ mi"]
BAND_MIN = 20
ALONG_MI = 10.0
METHODS = ("chain", "band", "band_local", "chain_band")


def _cl(v: np.ndarray) -> np.ndarray:
    return np.clip(np.where(np.isnan(v), FLOOR, v), CAP, FLOOR)


def band_of(edge_mi: np.ndarray) -> np.ndarray:
    return np.digitize(edge_mi, BANDS_MI)


def build(m: pd.DataFrame, pads: pd.DataFrame, ext: list) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    hold, app, bands = [], [], []
    cen = shapely.centroid(pads["geom"].to_numpy())
    for basin, bench, code, eg in ext:
        sel = (pads["basin"] == basin).to_numpy()
        geoms, pid, cpt = pads["geom"].to_numpy()[sel], pads["pad_id"].to_numpy()[sel], cen[sel]
        hit = np.sort(shapely.STRtree(geoms).query(eg, predicate="intersects"))
        n = len(hit)
        edge = np.where(shapely.contains(eg, cpt[hit]), shapely.distance(shapely.boundary(eg), cpt[hit]) / MI, -0.5)
        dband = band_of(edge)
        g = m[(m["basin"] == basin) & (m["live"] == code)]
        if len(g) < BAND_MIN:
            continue
        pts = shapely.points(g["x"].to_numpy(), g["y"].to_numpy())
        gap = g["gap_ft"].to_numpy()
        wband = band_of(np.where(shapely.contains(eg, pts), shapely.distance(shapely.boundary(eg), pts) / MI, -0.5))
        for bnd in range(len(BAND_NAMES)):
            v = gap[wband == bnd]
            bands.append({"basin": basin, "bench": bench, "code": code, "band": BAND_NAMES[bnd], "wells": len(v), "dsu": int((dband == bnd).sum()),
                          "median_ft": float(np.median(v)) if len(v) else np.nan, "p25_ft": float(np.quantile(v, .25)) if len(v) else np.nan,
                          "p75_ft": float(np.quantile(v, .75)) if len(v) else np.nan})
        a, b = shapely.STRtree(pts).query(geoms[hit], predicate="dwithin", distance=ALONG_MI * MI)
        pr = pd.DataFrame({"k": a, "w": b, "gap": gap[b], "d": shapely.distance(geoms[hit][a], pts[b]) / MI})
        pr["same_band"] = wband[b] == dband[a]
        near = pr[pr["d"] <= 1.0].groupby("k")["gap"].agg(["size", "median"])
        tk = near.index.to_numpy()[near["size"].to_numpy() >= p2.MIN_GAPS]
        truth = np.full(n, np.nan)
        truth[tk] = np.clip(near.loc[tk, "median"].to_numpy(), CAP, FLOOR)
        has_d = np.zeros(n, bool)
        has_d[np.unique(a)] = True

        def predict(ex: float, idx: np.ndarray, pr: pd.DataFrame = pr, n: int = n, dband: np.ndarray = dband, wband: np.ndarray = wband,
                    gap: np.ndarray = gap) -> pd.DataFrame:
            """Predictions for DSU positions idx with wells within ex mi of each hidden (ex = 0: nothing hidden)."""
            q = pr[pr["d"] > ex] if ex > 0 else pr
            chain_raw = np.full(n, np.nan)
            for rad in p2.RADII_MI:
                if rad <= ex:
                    continue
                s = q[q["d"] <= rad].groupby("k")["gap"].agg(["size", "median"])
                s = s[s["size"] >= p2.MIN_GAPS]
                kk = s.index.to_numpy()
                kk = kk[np.isnan(chain_raw[kk])]
                chain_raw[kk] = s.loc[kk, "median"].to_numpy()
            # band: exact, hiding each DSU's own wells within ex mi
            band = np.full(n, np.nan)
            hidden = pr[pr["d"] <= ex].groupby("k")["w"].apply(np.asarray) if ex > 0 else {}
            for bnd in range(len(BAND_NAMES)):
                wi = np.flatnonzero(wband == bnd)
                if len(wi) < BAND_MIN:
                    continue
                full = float(np.median(gap[wi]))
                for k in idx[dband[idx] == bnd]:
                    h = hidden.get(k) if ex > 0 else None
                    if h is None or not len(h):
                        band[k] = full
                    else:
                        keep = wi[~np.isin(wi, h)]
                        band[k] = float(np.median(gap[keep])) if len(keep) >= BAND_MIN else np.nan
            s = q[q["same_band"]].groupby("k")["gap"].agg(["size", "median"])
            s = s[s["size"] >= p2.MIN_GAPS]
            bl = band.copy()
            bl[s.index.to_numpy()] = s["median"].to_numpy()
            return pd.DataFrame({"chain": _cl(chain_raw), "band": _cl(band), "band_local": _cl(bl), "chain_band": _cl(np.where(np.isnan(chain_raw), band, chain_raw)),
                                 "chain_has_control": ~np.isnan(chain_raw), "band_has_value": ~np.isnan(band)}).iloc[idx]

        base = pd.DataFrame({"basin": basin, "bench": bench, "code": code, "pad_id": pid[hit], "edge_mi": edge, "edge_band": np.asarray(BAND_NAMES)[dband]})
        allk = np.arange(n)
        app.append(pd.concat([base, predict(0.0, allk).reset_index(drop=True)], axis=1))
        for ex in sf.EXCLUDE_MI:
            if len(tk):
                hold.append(pd.concat([base.iloc[tk].reset_index(drop=True).assign(exclude_mi=ex, truth_ft=truth[tk]), predict(ex, tk).reset_index(drop=True)], axis=1))
        print(f"  {basin} {code}", flush=True)
    return pd.concat(hold, ignore_index=True), pd.concat(app, ignore_index=True), pd.DataFrame(bands)


def score(h: pd.DataFrame) -> pd.DataFrame:
    rows = []
    groups = [(("all", b, ex), g) for (b, ex), g in h.groupby(["basin", "exclude_mi"])]
    groups += [((bd, b, ex), g) for (bd, b, ex), g in h.groupby(["edge_band", "basin", "exclude_mi"])]
    groups += [((f"code {cd}", b, ex), g) for (cd, b, ex), g in h.groupby(["code", "basin", "exclude_mi"])]
    groups += [(("chain has no control", b, ex), g) for (b, ex), g in h[~h["chain_has_control"]].groupby(["basin", "exclude_mi"])]
    for (where, basin, ex), g in groups:
        if len(g) < 30:
            continue
        o = {"basin": basin, "where": where, "exclude_mi": ex, "dsu_bench": len(g)}
        for mth in METHODS:
            e = g[mth] - g["truth_ft"]
            o |= {f"{mth}_median_err_ft": float(e.abs().median()), f"{mth}_p90_err_ft": float(e.abs().quantile(.9)), f"{mth}_bias_ft": float(e.median())}
        rows.append(o)
    return pd.DataFrame(rows)


def verdict(sc: pd.DataFrame, mth: str) -> dict:
    out = {}
    for basin in ("delaware", "midland"):
        a = sc[(sc["basin"] == basin) & (sc["where"] == "all")].set_index("exclude_mi")
        fr = sc[(sc["basin"] == basin) & (sc["where"] == BAND_NAMES[0]) & (sc["exclude_mi"] == 1.0)]
        t1 = all(a.at[ex, f"{mth}_median_err_ft"] < a.at[ex, "chain_median_err_ft"] for ex in (1.0, 2.0))
        t2 = all(a.at[ex, f"{mth}_p90_err_ft"] <= sf.ADOPT_P90_SLACK * a.at[ex, "chain_p90_err_ft"] for ex in (1.0, 2.0))
        t3 = bool(len(fr)) and float(fr[f"{mth}_median_err_ft"].iloc[0]) <= float(fr["chain_median_err_ft"].iloc[0]) + sf.ADOPT_FRINGE_SLACK_FT
        out[basin] = {"median_better_1_and_2mi": bool(t1), "p90_within_slack": bool(t2), "fringe_no_worse": bool(t3), "pass": bool(t1 and t2 and t3)}
    return out


def application(app: pd.DataFrame, pads: pd.DataFrame) -> pd.DataFrame:
    g = app.merge(pads[["pad_id", "short_ft"]], on="pad_id")
    width = (g["short_ft"] - 2 * p2.SETBACK_FT).clip(lower=0)
    for mth in ("chain", "chain_band"):
        g[f"{mth}_rows"] = np.floor(width / g[mth]) + 1
    rows = []
    for key, s in [((b, "all"), s) for b, s in g.groupby("basin")] + list(g.groupby(["basin", "edge_band"])) + [((b, f"code {c}"), s) for (b, c), s in g.groupby(["basin", "code"])]:
        nc = s[~s["chain_has_control"]]
        rows.append({"basin": key[0], "where": key[1], "dsu_bench": len(s), "chain_no_control_pct": 100 * len(nc) / len(s),
                     "no_control_band_value_mean_ft": float(nc["chain_band"].mean()) if len(nc) else np.nan,
                     "chain_mean_ft": float(s["chain"].mean()), "chain_band_mean_ft": float(s["chain_band"].mean()),
                     "chain_rows": int(s["chain_rows"].sum()), "chain_band_rows": int(s["chain_band_rows"].sum()),
                     "rows_change_pct": 100 * (s["chain_band_rows"].sum() / s["chain_rows"].sum() - 1)})
    return pd.DataFrame(rows)


def density_maps(app: pd.DataFrame, m: pd.DataFrame, pads: pd.DataFrame, ext: list, out: Path) -> list[str]:
    """Per basin, one panel per bench: wells per section by DSU under the rule of record (radius chain, then the
    extent-band median, then FLOOR), and a second figure showing which of the three each DSU's spacing came from."""
    pg = pads.set_index("pad_id")["geom"]
    app = app.assign(wps=5280.0 / app["chain_band"],
                     basis=np.where(app["chain_has_control"], 0, np.where(app["band_has_value"], 1, 2)))
    files = []
    for basin, gb in app.groupby("basin"):
        codes = list(dict.fromkeys(gb["code"]))
        ncol = 4
        nrow = int(np.ceil(len(codes) / ncol))
        for kind in ("wps", "basis"):
            fig, axes = plt.subplots(nrow, ncol, figsize=(5.2 * ncol, 5.6 * nrow), squeeze=False)
            pc = None
            for ax, code in zip(axes.ravel(), codes, strict=False):
                g = gb[gb["code"] == code]
                polys = [np.asarray(x.exterior.coords) / MI for x in pg.loc[g["pad_id"]]]
                if kind == "wps":
                    pc = PolyCollection(polys, array=g["wps"].to_numpy(float), cmap="viridis", linewidths=0)
                    pc.set_clim(5280 / FLOOR, 5280 / CAP)
                    w = m[(m["basin"] == basin) & (m["live"] == code)]
                    ax.add_collection(pc)
                    ax.scatter(w["x"] / MI, w["y"] / MI, s=0.6, c="black", linewidths=0, alpha=0.6)
                    title = f"{code}: mean {g['wps'].mean():.1f} WPS ({5280 / g['wps'].mean():,.0f} ft)" + chr(10) + f"{len(g):,} DSUs, {len(w):,} measured wells"
                else:
                    pc = PolyCollection(polys, array=g["basis"].to_numpy(float), cmap=ListedColormap(["#2563eb", "#f59e0b", "#d1d5db"]), linewidths=0)
                    pc.set_clim(-0.5, 2.5)
                    ax.add_collection(pc)
                    sh = [100 * float((g["basis"] == k).mean()) for k in range(3)]
                    title = f"{code}: wells within 3 mi {sh[0]:.0f} %, band {sh[1]:.0f} %, floor {sh[2]:.0f} %"
                eg = next(e[3] for e in ext if e[0] == basin and e[2] == code)
                for poly in shapely.get_parts(eg):
                    if poly.geom_type == "Polygon":
                        ex, ey = poly.exterior.xy
                        ax.plot(np.asarray(ex) / MI, np.asarray(ey) / MI, color="#111827", lw=0.7)
                ax.autoscale()
                ax.set_aspect("equal")
                ax.set_xticks([])
                ax.set_yticks([])
                ax.set_title(title, fontsize=9)
            for ax in axes.ravel()[len(codes):]:
                ax.axis("off")
            if kind == "wps":
                cb = fig.colorbar(pc, ax=axes, shrink=0.5, pad=0.01)
                cb.set_label("wells per section per landing (5,280 / spacing): 4 = 1,320 ft, 6 = 880 ft, 8 = 660 ft")
                fig.suptitle(f"{basin}: planned density by DSU and bench, rule of record 2026-11-13 (dots = measured wells, outline = BOX extent)", fontsize=13)
            else:
                cb = fig.colorbar(pc, ax=axes, shrink=0.3, pad=0.01, ticks=[0, 1, 2])
                cb.ax.set_yticklabels(["wells within 3 mi", "extent band", "floor 1,320 ft"])
                fig.suptitle(f"{basin}: where each DSU's spacing comes from", fontsize=13)
            f = out / f"density_{kind}_{basin}.png"
            fig.savefig(f, dpi=105, bbox_inches="tight")
            plt.close(fig)
            files.append(f.name)
    return files


def run(out: Path, cache: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    m = sf.measured(cache)
    d = p0.pull(cache)
    pads = p0.pad_frame(d["pads"])
    ext = p2.extent_list(d["extents"])
    hold, app, bands = build(m, pads, ext)
    bands.to_csv(out / "bands_spacing.csv", index=False)
    sc = score(hold)
    sc.to_csv(out / "bands_holdout.csv", index=False)
    application(app, pads).to_csv(out / "bands_vs_chain.csv", index=False)
    summary = {"code_sha": p0._git_sha(), "bands_mi": BANDS_MI, "band_min_wells": BAND_MIN, "along_mi": ALONG_MI, "targets": int(len(hold) / len(sf.EXCLUDE_MI)),
               "verdict": {mth: verdict(sc, mth) for mth in METHODS[1:]}, "figures": density_maps(app, m, pads, ext, out)}
    (out / "bands_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
