"""BOX sticks: how the thickness rung should choose its anchor bench (read-only).

    python -m scripts.box_sticks_anchor_rule --out docs/box_sticks/<folder>/anchor_rule --cache <phase 0 cache>

The thickness rung carries a bench's depth from another bench's direct surface plus the local thickness. Until
2026-11-18 the anchor was the first available bench in a basin-wide order of held-out medians
(phase 1 holdout_thickness.csv); after the tag cutover that order flipped for Midland WCD on a 0.03 ft margin.

This scores anchor-selection rules on the hold-out the rung is used under: for every screened evidence well inside
its extent, the same-bench wells within EXCLUDE_MI are hidden and the depth is predicted from each eligible anchor
(the anchor's direct surface at the well + the weighted-median thickness of the remaining same-bench wells within
5 mi, >= 3, on more than one side). Rules, all on the same wells:

  rank_new / rank_old  first available anchor in the basin-wide order (cutover file / 2026-11-12 file);
  spread               the anchor whose local thickness sample is tightest (weighted MAD);
  median               the median of the predictions from every eligible anchor;
  adjacent             the nearest bench in the stack (above on a tie);
  oracle               the best anchor per well (headroom only, not a rule).

Eligible anchors = those the chain already walks (predicted on >= 25 % of the bench's wells in the phase 1 hold-out);
``pool=all`` drops that filter as a sensitivity. Nothing is written to the warehouse.
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
from scripts import box_sticks_phase1b as p1b
from scripts import box_sticks_phase1c as p1c

P = ls.PARAMS
MI = ls.M_PER_MI
EXCLUDE_MI = 1.0
OLD_RANK = p1c.DOCS / "phase1-2026-11-12" / "holdout_thickness.csv"
RULES = ("rank_new", "rank_old", "spread", "median", "adjacent", "oracle")


def rank_lists(path: Path) -> dict[tuple[str, str], list[str]]:
    t = pd.read_csv(path)
    t = t[(t["exclude_mi"] == 1.0) & (t["predicted_pct"] >= 25)].sort_values("median_ft")
    return {k: list(g["anchor"]) for k, g in t.groupby(["basin", "code"])}


def anchor_predictions(xy: np.ndarray, z: np.ndarray, at: dict[str, np.ndarray]) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Per anchor: the held-out prediction at every well and the weighted MAD of the local thickness sample."""
    n = len(z)
    pred = {a: np.full(n, np.nan) for a in at}
    mad = {a: np.full(n, np.nan) for a in at}
    for i, ks in enumerate(cKDTree(xy).query_ball_point(xy, P.thick_max_mi * MI)):
        ks = np.asarray(ks, int)
        d = np.hypot(xy[ks, 0] - xy[i, 0], xy[ks, 1] - xy[i, 1])
        ks, d = ks[d >= EXCLUDE_MI * MI], d[d >= EXCLUDE_MI * MI] / MI
        for a, A in at.items():
            if not np.isfinite(A[i]):
                continue
            ok = np.isfinite(A[ks])
            kk = ks[ok]
            if len(kk) < P.n_min or ls.max_angular_gap_deg(xy[kk], xy[i]) >= 180.0:
                continue
            wt = np.exp(-0.5 * (d[ok] / (2 * P.wmed_sigma_mi)) ** 2) + 1e-9
            rel = z[kk] - A[kk]
            t = ls.weighted_median(rel, wt)
            pred[a][i], mad[a][i] = A[i] + t, ls.weighted_median(np.abs(rel - t), wt)
    return pred, mad


def apply_rules(code: str, z: np.ndarray, pred: dict, mad: dict, pool: list[str], new: list[str], old: list[str], pos: dict[str, int]) -> pd.DataFrame:
    pool = [a for a in pool if a in pred]
    Pm = np.column_stack([pred[a] for a in pool]) if pool else np.empty((len(z), 0))
    Mm = np.column_stack([mad[a] for a in pool]) if pool else np.empty((len(z), 0))
    have = np.isfinite(Pm)
    out = pd.DataFrame({"z": z, "n_anchors": have.sum(axis=1)})

    def first(seq: list[str]) -> tuple[np.ndarray, np.ndarray]:
        val, who = np.full(len(z), np.nan), np.full(len(z), None, dtype=object)
        for a in [s for s in seq if s in pool]:
            take = np.isnan(val) & np.isfinite(pred[a])
            val[take], who[take] = pred[a][take], a
        return val, who

    out["rank_new"], out["anchor_rank_new"] = first(new)
    out["rank_old"], out["anchor_rank_old"] = first(old)
    out["adjacent"], out["anchor_adjacent"] = first(sorted(pool, key=lambda a: (abs(pos[a] - pos[code]), pos[a])))
    any_ = have.any(axis=1)
    out["median"] = np.nan
    out["spread"], out["anchor_spread"] = np.nan, None
    out["oracle"] = np.nan
    if any_.any():
        out.loc[any_, "median"] = np.nanmedian(Pm[any_], axis=1)
        j = np.argmin(np.where(have[any_], Mm[any_], np.inf), axis=1)
        out.loc[any_, "spread"] = Pm[any_][np.arange(int(any_.sum())), j]
        out.loc[any_, "anchor_spread"] = np.asarray(pool, dtype=object)[j]
        e = np.where(have[any_], np.abs(Pm[any_] - z[any_][:, None]), np.inf)
        out.loc[any_, "oracle"] = Pm[any_][np.arange(int(any_.sum())), np.argmin(e, axis=1)]
    return out


def score(w: pd.DataFrame, extents: pd.DataFrame, all_pool: bool) -> pd.DataFrame:
    new, old, order = rank_lists(p1c.THICK_RANK), rank_lists(OLD_RANK), sb.bench_order()
    parts = []
    for basin in sorted(extents["basin"].unique()):
        bw = w[w["basin"] == basin].reset_index(drop=True)
        sets = p1.anchor_sets(extents, basin)
        bxy = bw[["x", "y"]].to_numpy(float)
        F = {n: p1b.field_at(bw, cs, bxy) for n, cs in sets.items()}
        print(f"  {basin} anchor fields built", flush=True)
        for e in extents[extents["basin"] == basin].itertuples():
            geom = shapely.make_valid(shapely.from_wkt(e.wkt))
            for code in ls.extent_codes(basin, e.bench):
                m = ((bw["live"] == code) & shapely.contains_xy(geom, bxy[:, 0], bxy[:, 1])).to_numpy()
                if m.sum() < 4:
                    continue
                at = {n: f[m] for n, f in F.items() if code not in sets[n]}
                pred, mad = anchor_predictions(bxy[m], bw.loc[m, "depth_ft"].to_numpy(float), at)
                pool = list(at) if all_pool else new.get((basin, code), [])
                t = apply_rules(code, bw.loc[m, "depth_ft"].to_numpy(float), pred, mad, pool, new.get((basin, code), []), old.get((basin, code), []),
                                {code: order[basin].index(code)} | {n: order[basin].index(cs[0]) for n, cs in sets.items()})
                t.insert(0, "api10", bw.loc[m, "api10"].astype(str).to_numpy())
                t.insert(0, "code", code)
                t.insert(0, "basin", basin)
                parts.append(t)
    return pd.concat(parts, ignore_index=True)


def tables(t: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Errors on the wells every rule predicts (rank_old can lack an anchor the new pool has; those wells are left out)."""
    k = t[list(RULES)].notna().all(axis=1)
    e = t.loc[k, ["basin", "code"]].copy()
    for r in RULES:
        e[r] = (t.loc[k, r] - t.loc[k, "z"]).abs()

    def agg(g: pd.DataFrame) -> pd.Series:
        row = {"wells": len(g)}
        for r in RULES:
            row |= {f"{r}_median_ft": g[r].median(), f"{r}_p90_ft": g[r].quantile(0.9), f"{r}_over_150_pct": 100 * (g[r] > 150).mean()}
        return pd.Series(row)

    by_basin = e.groupby("basin").apply(agg, include_groups=False).reset_index()
    by_code = e.groupby(["basin", "code"]).apply(agg, include_groups=False).reset_index()
    kk = t[k]
    moved = {b: {"wells": len(g), "rank_order_changed_anchor_pct": round(100 * float((g["anchor_rank_new"] != g["anchor_rank_old"]).mean()), 1),
                 "rank_moved_ft_median_when_changed": round(float((g["rank_new"] - g["rank_old"]).abs()[g["anchor_rank_new"] != g["anchor_rank_old"]].median()), 1),
                 "one_anchor_only_pct": round(100 * float((g["n_anchors"] == 1).mean()), 1)} for b, g in kk.groupby("basin")}
    return by_basin, by_code, moved


def run(out: Path, cache: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    w = p1c.two_part_screen(p0.evidence(d["wells"], d["rule"]), d["extents"])
    w = w[w["screen"] == "keep"].reset_index(drop=True)
    summary = {"code_sha": p0._git_sha(), "tags": "live", "exclude_mi": EXCLUDE_MI, "evidence_wells": len(w), "pools": {}}
    for label, all_pool in (("chain_pool", False), ("all_anchors", True)):
        t = score(w, d["extents"], all_pool)
        by_basin, by_code, moved = tables(t)
        t.to_csv(out / f"wells_{label}.csv.gz", index=False, compression="gzip")
        by_basin.round(2).to_csv(out / f"by_basin_{label}.csv", index=False)
        by_code.round(2).to_csv(out / f"by_bench_{label}.csv", index=False)
        summary["pools"][label] = {"by_basin": by_basin.round(2).to_dict("records"), "rank_order": moved}
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
