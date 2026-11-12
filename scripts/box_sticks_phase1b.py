"""BOX sticks, phase 1b: landing depth far from a bench's own wells (read-only).

    python -m scripts.box_sticks_phase1b --out docs/box_sticks/phase1b-<date> --cache <phase 0 cache>

Phase 1 left 35 % of the DSU x bench pairs without a depth: the thickness method needs the bench's own wells within
5 mi. This tests depths that need NO same-bench well nearby, only the surfaces of other benches at the location:

  offset   one neighbour bench's direct surface + the thickness to the code;
  bracket  (Michael, 2026-11-12) the code sits in the window between a bench above and a bench below:
           depth = upper + f * (lower - upper), f = the code's fractional position in the window.

The thickness / fraction is learned two ways: from the K nearest same-code wells BEYOND the held-out distance
("nearest"), or as one extent-wide number ("regional"). Held-out test: every same-code well within E mi of the well
is removed (E = 1, 5, 10), so E = 10 is a location with no same-bench control for 10 miles. Every other bench of the
basin is tried as the neighbour, and every above x below pair as the bracket.

Coverage: at each DSU polygon centroid, the best-ranked method (by held-out median error at E = 5 mi) whose neighbour
surfaces exist there. Neighbour surfaces are DIRECT only (>= 3 of their wells within 2 mi), never carried.
Today's tags (live). Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import landing_surfaces as ls
from box import tag_scoreboard as sb
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1 as p1
from scripts.tag_landing_crossings import build_surfaces

P = ls.PARAMS
MI = ls.M_PER_MI
EXCLUDE_MI = (1.0, 5.0, 10.0)
K_NEAREST = 30
MIN_SAMPLES = 5
MIN_SPAN_FT = 50.0
RANK_AT_MI = 5.0
MIN_PREDICTED = 50


def field_at(bw: pd.DataFrame, codes: tuple[str, ...], pts: np.ndarray) -> np.ndarray:
    """A bench's direct landing depth at arbitrary points (>= n_min of its wells within r_mi), else NaN."""
    a = bw[bw["live"].isin(codes)]
    out = np.full(len(pts), np.nan)
    if len(a) < P.n_min or not len(pts):
        return out
    axy, az = a[["x", "y"]].to_numpy(float), a["depth_ft"].to_numpy(float)
    for i, js in enumerate(cKDTree(axy).query_ball_point(pts, P.r_mi * MI)):
        if len(js) >= P.n_min:
            out[i] = ls.estimate(axy[js], az[js], pts[i], P)[0]
    return out


def methods_for(code: str, sets: dict[str, tuple[str, ...]], rank: dict[str, int]) -> list[tuple[str, str, str | None]]:
    """(kind, upper-or-anchor, lower) for every neighbour and every above x below pair."""
    others = [n for n, cs in sets.items() if code not in cs]
    above = [n for n in others if rank[sets[n][0]] < rank[code]]
    below = [n for n in others if rank[sets[n][0]] > rank[code]]
    return [("offset", n, None) for n in others] + [("bracket", u, lo) for u in above for lo in below]


def columns(z: np.ndarray, F: dict[str, np.ndarray], methods: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """rel (the sample each well contributes), base and span per method, so that depth = base + rel * span."""
    rel, base, span = [], [], []
    for kind, a, b in methods:
        if kind == "offset":
            rel.append(z - F[a])
            base.append(F[a])
            span.append(np.ones(len(z)))
        else:
            s = np.where(F[b] - F[a] > MIN_SPAN_FT, F[b] - F[a], np.nan)
            rel.append((z - F[a]) / s)
            base.append(F[a])
            span.append(s)
    return np.column_stack(rel), np.column_stack(base), np.column_stack(span)


def far_holdout(xy: np.ndarray, z: np.ndarray, rel: np.ndarray, base: np.ndarray, span: np.ndarray, exclude_mi: float) -> tuple[np.ndarray, np.ndarray]:
    """|error| per well x method: (nearest-K samples beyond exclude_mi, regional median of all samples)."""
    n, m = rel.shape
    k = min(K_NEAREST, n - 1)
    e_near = np.full((n, m), np.nan)
    regional = np.nanmedian(rel, axis=0) if n else np.full(m, np.nan)
    enough = np.isfinite(rel).sum(axis=0) >= MIN_SAMPLES
    e_reg = np.abs(z[:, None] - (base + np.where(enough, regional, np.nan)[None, :] * span))
    for s in range(0, n, 256):
        d = np.hypot(xy[s:s + 256, 0, None] - xy[None, :, 0], xy[s:s + 256, 1, None] - xy[None, :, 1])
        d[d < exclude_mi * MI] = np.inf
        idx = np.argpartition(d, k - 1, axis=1)[:, :k]
        ok = np.isfinite(np.take_along_axis(d, idx, axis=1))
        r = np.where(ok[:, :, None], rel[idx], np.nan)
        cnt = np.isfinite(r).sum(axis=1)
        with np.errstate(all="ignore"):
            med = np.nanmedian(r, axis=1)
        med[cnt < MIN_SAMPLES] = np.nan
        e_near[s:s + 256] = np.abs(z[s:s + 256, None] - (base[s:s + 256] + med * span[s:s + 256]))
    return e_near, e_reg


def run(out: Path, cache: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    w = p0.evidence(d["wells"], d["rule"])
    extents, order = d["extents"], sb.bench_order()
    pads = p0.pad_frame(d["pads"])
    surf, _ = build_surfaces(w, extents)
    dsu = p1.dsu_samples(pads, extents, surf)
    cen = shapely.centroid(pads["geom"].to_numpy())
    pads = pads.assign(cx=shapely.get_x(cen), cy=shapely.get_y(cen))

    rows, chain = [], []
    for basin in sorted(extents["basin"].unique()):
        bw = w[w["basin"] == basin].reset_index(drop=True)
        sets = p1.anchor_sets(extents, basin)
        rank = {c: i for i, c in enumerate(order[basin])}
        wxy = bw[["x", "y"]].to_numpy(float)
        Fw = {n: field_at(bw, cs, wxy) for n, cs in sets.items()}
        pb = pads[pads["basin"] == basin].set_index("pad_id")
        Fp = {n: pd.Series(field_at(bw, cs, pb[["cx", "cy"]].to_numpy(float)), index=pb.index) for n, cs in sets.items()}
        print(f"{basin}: neighbour fields built", flush=True)
        for e in extents[extents["basin"] == basin].itertuples():
            geom = shapely.make_valid(shapely.from_wkt(e.wkt))
            for code in ls.extent_codes(basin, e.bench):
                m = ((bw["live"] == code) & shapely.contains_xy(geom, wxy[:, 0], wxy[:, 1])).to_numpy()
                if m.sum() < 10:
                    continue
                xy, z = wxy[m], bw.loc[m, "depth_ft"].to_numpy(float)
                methods = methods_for(code, sets, rank)
                rel, base, span = columns(z, {n: f[m] for n, f in Fw.items()}, methods)
                res = []
                for ex_mi in EXCLUDE_MI:
                    e_near, e_reg = far_holdout(xy, z, rel, base, span, ex_mi)
                    for j, (kind, a, b) in enumerate(methods):
                        for learn, err in (("nearest", e_near[:, j]), ("regional", e_reg[:, j])):
                            r = p1._err(pd.Series(err))
                            res.append({"basin": basin, "code": code, "kind": kind, "upper_or_anchor": a, "lower": b, "learn": learn,
                                        "exclude_mi": ex_mi, "wells": int(m.sum()), "predicted_pct": 100 * r["predicted"] / m.sum(), **r})
                res = pd.DataFrame(res)
                rows.append(res)
                # rank the methods at RANK_AT_MI and walk them at every DSU of this bench with no direct depth
                rk = res[(res["exclude_mi"] == RANK_AT_MI) & (res["predicted"] >= MIN_PREDICTED)].sort_values("median_ft")
                dd = dsu[(dsu["basin"] == basin) & (dsu["code"] == code)].copy()
                dd["method"], dd["expected_median_ft"], dd["expected_p90_ft"] = None, np.nan, np.nan
                open_ = (dd["basis"] != "direct").to_numpy()
                for q in rk.itertuples():
                    have = Fp[q.upper_or_anchor].reindex(dd["pad_id"]).notna().to_numpy()
                    if q.kind == "bracket":
                        lo, up = Fp[q.lower].reindex(dd["pad_id"]).to_numpy(), Fp[q.upper_or_anchor].reindex(dd["pad_id"]).to_numpy()
                        have = have & np.isfinite(lo) & (lo - up > MIN_SPAN_FT)
                    take = open_ & have & dd["method"].isna().to_numpy()
                    label = f"{q.kind}:{q.upper_or_anchor}" + (f"/{q.lower}" if q.kind == "bracket" else "") + f" ({q.learn})"
                    dd.loc[take, ["method", "expected_median_ft", "expected_p90_ft"]] = [label, q.median_ft, q.p90_ft]
                dd["method"] = np.where(dd["basis"] == "direct", "direct", dd["method"].fillna("none"))
                chain.append(dd)
            print(f"  {basin} {e.bench} done", flush=True)
    res = pd.concat(rows, ignore_index=True)
    res.to_csv(out / "holdout_far.csv", index=False)
    ch = pd.concat(chain, ignore_index=True)
    ch["kind"] = ch["method"].str.split(":").str[0]
    ch.drop(columns=["z", "near_mi"]).to_csv(out / "dsu_chain.csv.gz", index=False, compression="gzip")

    def cov(g: pd.DataFrame) -> dict:
        car = g[~g["kind"].isin(["direct", "none"])]
        return {"dsu": len(g), "direct_pct": 100 * float((g["kind"] == "direct").mean()), "phase1_thickness_pct": 100 * float((g["basis"] == "thickness").mean()),
                "bracket_pct": 100 * float((g["kind"] == "bracket").mean()), "offset_pct": 100 * float((g["kind"] == "offset").mean()),
                "none_pct": 100 * float((g["kind"] == "none").mean()),
                "none_centroid_outside_pct": 100 * float(((g["kind"] == "none") & ~g["centroid_in_extent"]).mean()),
                "carried_expected_median_ft": float(car["expected_median_ft"].median()) if len(car) else np.nan,
                "carried_expected_p90_ft": float(car["expected_p90_ft"].median()) if len(car) else np.nan,
                "top_method": car["method"].mode().iat[0] if len(car) else None}

    coverage = pd.DataFrame([{"basin": b, "code": c, **cov(g)} for (b, c), g in ch.groupby(["basin", "code"])])
    coverage.to_csv(out / "coverage_chain.csv", index=False)
    best = (res[res["predicted"] >= MIN_PREDICTED].sort_values("median_ft").groupby(["basin", "code", "kind", "learn", "exclude_mi"]).head(1)
            .sort_values(["basin", "code", "exclude_mi", "median_ft"]))
    best.to_csv(out / "best_by_kind.csv", index=False)
    summary = {"code_sha": p0._git_sha(), "tags": "live", "k_nearest": K_NEAREST, "rank_at_mi": RANK_AT_MI, "all": cov(ch),
               "by_basin": {b: cov(g) for b, g in ch.groupby("basin")}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
