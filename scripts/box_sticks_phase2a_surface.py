"""BOX sticks, phase 2a addendum: a smooth spacing surface against the radius chain (read-only).

    python -m scripts.box_sticks_phase2a_surface --out docs/box_sticks/phase2a-<date> --cache <phase 0 cache>

Michael 2026-11-12: wells per section should follow reservoir quality, densest in the core of a bench and thinning
outward, so the spacing map should be a gradient, not the step the radius chain makes (local median or 1,320 ft).

  chain    the decided rule: median gap of same-bench wells within 1 -> 2 -> 3 mi of the DSU, first radius with
           >= min_gaps; none -> FLOOR_FT.
  surface  Gaussian-weighted median of the bench's per-well gaps (weight exp(-0.5 (d / sigma)^2), d = DSU polygon
           to well, cut at CUT_SIGMA sigma), relaxed toward FLOOR_FT as control thins:
               spacing = FLOOR - c (FLOOR - weighted median),  c = n_eff / (n_eff + k),  n_eff = sum of weights.
Both clamped to [CAP, FLOOR].

Hold-out: targets are DSU x bench with their own value (>= min_gaps gaps within 1 mi). Each method predicts the
target from wells FARTHER than an exclusion distance (1, 2, 3 mi) from the polygon. At 3 mi the chain can only answer
FLOOR_FT, which is the "hole in the core" case. sigma and k are picked on the pad_id-even half of the targets and
every reported number is from the pad_id-odd half. The adoption test (ADOPT_*) was fixed before the first run.
Gaps are the per-landing gaps of scripts/box_sticks_phase2a.py. Nothing is written to the warehouse.
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

from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase2a as p2

MI = p2.MI
FLOOR, CAP = p2.FLOOR_FT, p2.CAP_GUESS_FT
SIGMAS_MI = (1.0, 2.0, 3.0)
KS = (0.0, 2.0, 4.0)
CUT_SIGMA = 2.5
EXCLUDE_MI = (1.0, 2.0, 3.0)
EDGE_BINS = ([-1e9, 2, 5, 10, 1e9], ["0-2 mi", "2-5 mi", "5-10 mi", "10+ mi"])
REACH_MI = CUT_SIGMA * max(SIGMAS_MI)
# adoption test, fixed before the first run (test half, each basin):
#   1. median abs error below the chain's at exclusion 1 mi AND 2 mi;
#   2. P90 abs error no more than 10 % above the chain's at both;
#   3. in the fringe bin (0-2 mi inside the extent edge), median abs error no worse than the chain's + 10 ft at 1 mi.
ADOPT_P90_SLACK = 1.10
ADOPT_FRINGE_SLACK_FT = 10.0


def measured(cache: Path) -> pd.DataFrame:
    f = cache / "p2a_measure.pkl"
    if f.exists():
        return pd.read_pickle(f)
    d = p0.pull(cache)
    wg, _ = p2.pull_geoms(cache)
    u = p2.universe(d, wg, cache)
    m = p2.measure(u, p2.pair_table(u["geom"].to_numpy(), (u["basin"] + "|" + u["live"]).to_numpy()))
    m = m.loc[m["gap_ft"].notna(), ["api10", "basin", "live", "x", "y", "gap_ft"]].reset_index(drop=True)
    m.to_pickle(f)
    return m


def wmedian(k: np.ndarray, gap: np.ndarray, w: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Weighted median of gap per group k (0..n-1) and the weight sum. NaN where a group has no weight."""
    med, tot = np.full(n, np.nan), np.bincount(k, weights=w, minlength=n)
    if not len(k):
        return med, tot
    o = np.lexsort((gap, k))
    k, gap, w = k[o], gap[o], w[o]
    cw = np.cumsum(w)
    start = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    base = np.repeat(np.r_[0.0, cw[start[1:] - 1]], np.diff(np.r_[start, len(k)]))
    hit = np.where((cw - base) >= 0.5 * tot[k] - 1e-12, np.arange(len(k)), len(k))
    first = np.minimum.reduceat(hit, start)
    ok = first < len(k)
    med[k[start][ok]] = gap[first[ok]]
    return med, tot


def chain_predict(pr: pd.DataFrame, n: int, exclude_mi: float) -> np.ndarray:
    out = np.full(n, np.nan)
    for rad in p2.RADII_MI:
        if rad <= exclude_mi:
            continue
        q = pr[(pr["d"] > exclude_mi) & (pr["d"] <= rad)] if exclude_mi > 0 else pr[pr["d"] <= rad]
        s = q.groupby("k")["gap"].agg(["size", "median"])
        s = s[s["size"] >= p2.MIN_GAPS]
        kk = s.index.to_numpy()
        kk = kk[np.isnan(out[kk])]
        out[kk] = s.loc[kk, "median"].to_numpy()
    return np.clip(np.where(np.isnan(out), FLOOR, out), CAP, FLOOR)


def surface_predict(pr: pd.DataFrame, n: int, exclude_mi: float, sigma: float, kk: float) -> tuple[np.ndarray, np.ndarray]:
    q = pr[(pr["d"] > exclude_mi) & (pr["d"] <= CUT_SIGMA * sigma)] if exclude_mi > 0 else pr[pr["d"] <= CUT_SIGMA * sigma]
    med, neff = wmedian(q["k"].to_numpy(), q["gap"].to_numpy(), np.exp(-0.5 * (q["d"].to_numpy() / sigma) ** 2), n)
    with np.errstate(invalid="ignore"):
        c = np.where(neff > 0, neff / (neff + kk), 0.0)
    return np.clip(FLOOR - c * (FLOOR - np.where(np.isnan(med), FLOOR, np.clip(med, CAP, FLOOR))), CAP, FLOOR), neff


def build(m: pd.DataFrame, pads: pd.DataFrame, ext: list) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Per DSU x bench: hold-out predictions (targets only), the tuning grid, and the no-exclusion application."""
    hold, grid, app = [], [], []
    cen = shapely.centroid(pads["geom"].to_numpy())
    for basin, bench, code, eg in ext:
        sel = (pads["basin"] == basin).to_numpy()
        geoms, pid, cpt = pads["geom"].to_numpy()[sel], pads["pad_id"].to_numpy()[sel], cen[sel]
        hit = np.sort(shapely.STRtree(geoms).query(eg, predicate="intersects"))
        n = len(hit)
        inside = shapely.contains(eg, cpt[hit])
        edge = np.where(inside, shapely.distance(shapely.boundary(eg), cpt[hit]) / MI, -0.5)
        g = m[(m["basin"] == basin) & (m["live"] == code)]
        base = pd.DataFrame({"basin": basin, "bench": bench, "code": code, "pad_id": pid[hit], "edge_mi": edge})
        if len(g):
            pts = shapely.points(g["x"].to_numpy(), g["y"].to_numpy())
            a, b = shapely.STRtree(pts).query(geoms[hit], predicate="dwithin", distance=REACH_MI * MI)
            pr = pd.DataFrame({"k": a, "gap": g["gap_ft"].to_numpy()[b], "d": shapely.distance(geoms[hit][a], pts[b]) / MI})
        else:
            pr = pd.DataFrame({"k": np.array([], int), "gap": np.array([], float), "d": np.array([], float)})
        near = pr[pr["d"] <= 1.0].groupby("k")["gap"].agg(["size", "median"])
        truth = np.full(n, np.nan)
        tk = near.index.to_numpy()[near["size"].to_numpy() >= p2.MIN_GAPS]
        truth[tk] = np.clip(near.loc[tk, "median"].to_numpy(), CAP, FLOOR)
        a0 = base.assign(chain_ft=chain_predict(pr, n, 0.0), own_1mi_ft=truth)
        for sg in SIGMAS_MI:
            for kk in KS:
                a0[f"surf_s{sg:g}_k{kk:g}"], a0[f"neff_s{sg:g}"] = surface_predict(pr, n, 0.0, sg, kk)
        app.append(a0)
        if len(tk):
            for ex in EXCLUDE_MI:
                h = base.iloc[tk].assign(exclude_mi=ex, truth_ft=truth[tk], chain_ft=chain_predict(pr, n, ex)[tk])
                for sg in SIGMAS_MI:
                    for kk in KS:
                        h[f"surf_s{sg:g}_k{kk:g}"] = surface_predict(pr, n, ex, sg, kk)[0][tk]
                hold.append(h)
    hold_, app_ = pd.concat(hold, ignore_index=True), pd.concat(app, ignore_index=True)
    train = hold_[hold_["pad_id"] % 2 == 0]
    for sg in SIGMAS_MI:
        for kk in KS:
            c = f"surf_s{sg:g}_k{kk:g}"
            e = (train[c] - train["truth_ft"]).abs()
            grid.append({"sigma_mi": sg, "k": kk, "col": c,
                         "train_score_ft": float(e.groupby([train["basin"], train["exclude_mi"]]).median().mean()),
                         **{f"{b}_{ex:g}mi": float(e[(train["basin"] == b) & (train["exclude_mi"] == ex)].median()) for b in ("delaware", "midland") for ex in EXCLUDE_MI}})
    return hold_, pd.DataFrame(grid).sort_values("train_score_ft").reset_index(drop=True), app_


def score(test: pd.DataFrame, col: str) -> pd.DataFrame:
    test = test.assign(edge_bin=pd.cut(test["edge_mi"], EDGE_BINS[0], labels=EDGE_BINS[1]))
    rows = []
    groups = [(("all", b, ex), g) for (b, ex), g in test.groupby(["basin", "exclude_mi"])]
    groups += [((eb, b, ex), g) for (eb, b, ex), g in test.groupby(["edge_bin", "basin", "exclude_mi"], observed=True)]
    groups += [((f"code {cd}", b, ex), g) for (cd, b, ex), g in test.groupby(["code", "basin", "exclude_mi"])]
    for (where, basin, ex), g in groups:
        if len(g) < 30:
            continue
        o = {"basin": basin, "where": where, "exclude_mi": ex, "dsu_bench": len(g), "chain_at_floor_pct": 100 * float((g["chain_ft"] == FLOOR).mean())}
        for name, c in (("chain", "chain_ft"), ("surface", col)):
            e = g[c] - g["truth_ft"]
            o |= {f"{name}_median_err_ft": float(e.abs().median()), f"{name}_p90_err_ft": float(e.abs().quantile(.9)), f"{name}_bias_ft": float(e.median()),
                  f"{name}_within_15pct": 100 * float((e.abs() <= 0.15 * g["truth_ft"]).mean())}
        o["surface_closer_pct"] = 100 * float(((g[col] - g["truth_ft"]).abs() < (g["chain_ft"] - g["truth_ft"]).abs()).mean())
        o["chain_closer_pct"] = 100 * float(((g[col] - g["truth_ft"]).abs() > (g["chain_ft"] - g["truth_ft"]).abs()).mean())
        rows.append(o)
    return pd.DataFrame(rows)


def verdict(sc: pd.DataFrame) -> dict:
    out = {}
    for basin in ("delaware", "midland"):
        a = sc[(sc["basin"] == basin) & (sc["where"] == "all")].set_index("exclude_mi")
        fr = sc[(sc["basin"] == basin) & (sc["where"] == EDGE_BINS[1][0]) & (sc["exclude_mi"] == 1.0)]
        t1 = all(a.at[ex, "surface_median_err_ft"] < a.at[ex, "chain_median_err_ft"] for ex in (1.0, 2.0))
        t2 = all(a.at[ex, "surface_p90_err_ft"] <= ADOPT_P90_SLACK * a.at[ex, "chain_p90_err_ft"] for ex in (1.0, 2.0))
        t3 = bool(len(fr)) and float(fr["surface_median_err_ft"].iloc[0]) <= float(fr["chain_median_err_ft"].iloc[0]) + ADOPT_FRINGE_SLACK_FT
        out[basin] = {"median_better_1_and_2mi": bool(t1), "p90_within_slack": bool(t2), "fringe_no_worse": bool(t3), "pass": bool(t1 and t2 and t3)}
    return out


def smoothness(app: pd.DataFrame, pads: pd.DataFrame, col: str) -> pd.DataFrame:
    """Spacing difference between DSUs that share a boundary, same bench: the step the chain makes vs the surface."""
    geoms = pads["geom"].to_numpy()
    a, b = shapely.STRtree(geoms).query(geoms, predicate="intersects")
    keep = a < b
    adj = pd.DataFrame({"pad_a": pads["pad_id"].to_numpy()[a[keep]], "pad_b": pads["pad_id"].to_numpy()[b[keep]]})
    rows = []
    x = app[["basin", "code", "pad_id", "chain_ft", col]]
    j = adj.merge(x, left_on="pad_a", right_on="pad_id").merge(x, left_on=["pad_b", "basin", "code"], right_on=["pad_id", "basin", "code"], suffixes=("_a", "_b"))
    for basin, g in j.groupby("basin"):
        o = {"basin": basin, "adjacent_dsu_bench_pairs": len(g)}
        for name, c in (("chain", "chain_ft"), ("surface", col)):
            dlt = (g[f"{c}_a"] - g[f"{c}_b"]).abs()
            o |= {f"{name}_mean_step_ft": float(dlt.mean()), f"{name}_p90_step_ft": float(dlt.quantile(.9)), f"{name}_step_over_200ft_pct": 100 * float((dlt > 200).mean())}
        rows.append(o)
    return pd.DataFrame(rows)


def application(app: pd.DataFrame, pads: pd.DataFrame, col: str) -> pd.DataFrame:
    g = app.merge(pads[["pad_id", "short_ft"]], on="pad_id")
    g["edge_bin"] = pd.cut(g["edge_mi"], EDGE_BINS[0], labels=EDGE_BINS[1])
    width = (g["short_ft"] - 2 * p2.SETBACK_FT).clip(lower=0)
    g["chain_rows"], g["surface_rows"] = np.floor(width / g["chain_ft"]) + 1, np.floor(width / g[col]) + 1
    rows = []
    for key, s in [((b, "all"), s) for b, s in g.groupby("basin")] + list(g.groupby(["basin", "edge_bin"], observed=True)) \
            + [((b, f"code {c}"), s) for (b, c), s in g.groupby(["basin", "code"])]:
        rows.append({"basin": key[0], "where": key[1], "dsu_bench": len(s), "chain_at_floor_pct": 100 * float((s["chain_ft"] == FLOOR).mean()),
                     "surface_at_floor_pct": 100 * float((s[col] >= FLOOR - 1).mean()), "surface_within_50ft_of_floor_pct": 100 * float((s[col] >= FLOOR - 50).mean()),
                     "chain_mean_ft": float(s["chain_ft"].mean()), "surface_mean_ft": float(s[col].mean()),
                     "chain_rows": int(s["chain_rows"].sum()), "surface_rows": int(s["surface_rows"].sum()),
                     "rows_change_pct": 100 * (s["surface_rows"].sum() / s["chain_rows"].sum() - 1),
                     "abs_diff_median_ft": float((s[col] - s["chain_ft"]).abs().median()), "differ_over_100ft_pct": 100 * float(((s[col] - s["chain_ft"]).abs() > 100).mean())})
    return pd.DataFrame(rows)


def maps(app: pd.DataFrame, m: pd.DataFrame, pads: pd.DataFrame, ext: list, col: str, label: str, out: Path) -> list[str]:
    pg = pads.set_index("pad_id")["geom"]
    files = []
    for basin, code in p2.FOCUS:
        g = app[(app["basin"] == basin) & (app["code"] == code)]
        eg = next(e[3] for e in ext if e[0] == basin and e[2] == code)
        w = m[(m["basin"] == basin) & (m["live"] == code)]
        fig, axes = plt.subplots(1, 3, figsize=(21, 8))
        polys = [np.asarray(x.exterior.coords) / MI for x in pg.loc[g["pad_id"]]]
        for ax, vals, cmap, lim, title, cb in (
                (axes[0], g["chain_ft"], "viridis_r", (CAP, FLOOR), "Radius chain (decided 2026-11-12)", "spacing, ft"),
                (axes[1], g[col], "viridis_r", (CAP, FLOOR), f"Smooth surface ({label})", "spacing, ft"),
                (axes[2], g[col] - g["chain_ft"], "RdBu", (-400, 400), "Surface minus chain", "ft (red = surface tighter, more wells)")):
            pc = PolyCollection(polys, array=np.asarray(vals, float), cmap=cmap, linewidths=0)
            pc.set_clim(*lim)
            ax.add_collection(pc)
            if ax is not axes[2]:
                ax.scatter(w["x"] / MI, w["y"] / MI, s=1.5, c="black", linewidths=0)
            for poly in shapely.get_parts(eg):
                if poly.geom_type == "Polygon":
                    ex, ey = poly.exterior.xy
                    ax.plot(np.asarray(ex) / MI, np.asarray(ey) / MI, color="#111827", lw=0.8)
            ax.autoscale()
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(title, fontsize=11)
            fig.colorbar(pc, ax=ax, shrink=0.6).set_label(cb)
        fig.suptitle(f"{basin} {code}: spacing by DSU, radius chain vs smooth surface (dots = measured wells; outline = BOX extent)", fontsize=13)
        f = out / f"surface_map_{basin}_{code}.png"
        fig.savefig(f, dpi=110, bbox_inches="tight")
        plt.close(fig)
        files.append(f.name)
    return files


def run(out: Path, cache: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    m = measured(cache)
    d = p0.pull(cache)
    pads = p0.pad_frame(d["pads"])
    ext = p2.extent_list(d["extents"])
    hold, grid, app = build(m, pads, ext)
    grid.to_csv(out / "surface_tuning.csv", index=False)
    best = grid.iloc[0]
    col, label = best["col"], f"sigma {best['sigma_mi']:g} mi, k {best['k']:g}"
    test = hold[hold["pad_id"] % 2 == 1]
    sc = score(test, col)
    sc.to_csv(out / "surface_holdout.csv", index=False)
    v = verdict(sc)
    sm = smoothness(app, pads, col)
    sm.to_csv(out / "surface_smoothness.csv", index=False)
    ap = application(app, pads, col)
    ap.to_csv(out / "surface_vs_chain.csv", index=False)
    app[["basin", "bench", "code", "pad_id", "edge_mi", "own_1mi_ft", "chain_ft", col, f"neff_s{best['sigma_mi']:g}"]].to_csv(
        out / "spacing_dsu_bench_surface.csv.gz", index=False, compression="gzip")
    files = maps(app, m, pads, ext, col, label, out)
    # the best-ranked variant that DOES relax toward the floor as control thins (k > 0): not the picked one, reported
    # beside it because the hold-out cannot see undrilled ground, where the relaxation acts
    alt = grid[grid["k"] > 0].iloc[0]
    sc2 = score(test, alt["col"])
    sc2.to_csv(out / "surface_holdout_relaxed.csv", index=False)
    application(app, pads, alt["col"]).to_csv(out / "surface_vs_chain_relaxed.csv", index=False)
    smoothness(app, pads, alt["col"]).to_csv(out / "surface_smoothness_relaxed.csv", index=False)
    summary = {"code_sha": p0._git_sha(), "picked": {"sigma_mi": float(best["sigma_mi"]), "k": float(best["k"]), "train_score_ft": float(best["train_score_ft"])},
               "targets": {"train": int((hold["pad_id"] % 2 == 0).sum() / len(EXCLUDE_MI)), "test": int(len(test) / len(EXCLUDE_MI))},
               "verdict": v,
               "relaxed_variant": {"sigma_mi": float(alt["sigma_mi"]), "k": float(alt["k"]), "train_score_ft": float(alt["train_score_ft"]), "verdict": verdict(sc2)},
               "figures": files}
    (out / "surface_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
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
