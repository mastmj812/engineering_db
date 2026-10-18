"""BOX step 14 — thin-bench D2 evidence (pure; decision only, nothing stored).

Answers, per Delaware bench, the question the D2 build-vs-emerging decision turns on: could the bench ever pass the step-9
chain (9a tuning -> 9b one-time holdout -> 9c production) under the rules of record, and how far would its workups reach?

- Package counts per cutoff x horizon, split TUNING vs D52 HOLDOUT exactly as `box/acceptance.run` forms them (next 12
  months' wells inside the extent, lateral > 0, co-developed co-extent components, a package is held out when any member's
  midpoint sits in a holdout block). Only counts — no forecast, no error, no holdout performance is computed or read.
- What those counts allow:
    D53 judged cell      = a per-cutoff tuning cell with >= 30 packages;
    walk-forward (D57)   = a cutoff's box_v2_wf haircut exists only with >= 2 EARLIER cutoffs judged at that horizon
                           (`acceptance.apply_walk_forward` reads tuning cells with n_packages >= 30);
    D99 pooled holdout   = the one-time holdout scored pooled across cutoffs; the pre-9b rehearsal kept a cell only when its
                           pooled holdout reaches ~30 packages (BS2_S cum-36 at 17 was dropped);
    D102 production cut  = tuning + holdout packages merged per cutoff, then the >= 30 floor.
- Analog reach: distance from each in-extent PUD to the 1st and 10th nearest modern same-bench producer, and the deal-intake
  radius ring (5 / 7.5 / 10 / 15 / 20 mi, min_wells 10 — `box/analog.py`) the 10th falls in. Circle only (the D55 strike
  ellipse past 5 mi and the lateral band are ignored), so it is a lower bound on the radius the real search reaches.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

MIN_PACKAGES = 30  # D53 / D99 rehearsal / D102 floor
MIN_PRIOR = 2  # D57 walk-forward: >= 2 earlier judged cutoffs
RINGS_MI: tuple[float, ...] = (5.0, 7.5, 10.0, 15.0, 20.0)  # box/analog.py radius ladder
MIN_WELLS = 10  # deal-intake config v10 type_curve.min_wells
FT_PER_MI = 5280.0
# Horizons the analog fold cannot score at early cutoffs: F(k) needs training wells with cum-k known at the as-of date, and a
# training well's analogs must predate it (leave-self-out as-of cohorts), so on a pool without a deep 2016 base the 2016
# vintage gets no prediction. Observed on BS2_S in step 9a (cells_tuning_BS2_S.csv: 0 packages at these cells); every thin
# bench has a thinner 2016 base than BS2_S, so the cap is applied to all (WCXY on the big WCA_1 pool did score 2019 cum-36).
UNSCORED_EARLY: frozenset[tuple[str, int]] = frozenset({("2019-12-01", 36), ("2019-12-01", 48), ("2020-12-01", 48)})


def ring_reached(d_mi: np.ndarray, rings: Sequence[float] = RINGS_MI) -> np.ndarray:
    """Label of the first ring whose radius covers each distance; '>20 (cap)' past the last ring."""
    d = np.asarray(d_mi, float)
    out = np.full(d.shape, f">{rings[-1]:g} (cap)", dtype=object)
    for r in reversed(rings):
        out[d <= r] = f"<={r:g}"
    return out


def ring_shares(d_mi: np.ndarray, rings: Sequence[float] = RINGS_MI) -> dict[str, float]:
    lab = ring_reached(d_mi, rings)
    keys = [f"<={r:g}" for r in rings] + [f">{rings[-1]:g} (cap)"]
    n = max(len(lab), 1)
    return {k: float((lab == k).sum()) / n for k in keys}


def knn_distances_mi(pud_xy: np.ndarray, pool_xy: np.ndarray, k: int = MIN_WELLS) -> tuple[np.ndarray, np.ndarray]:
    """(1st, k-th) nearest pool distance in miles per PUD; NaN when the pool has fewer than k wells."""
    from scipy.spatial import cKDTree

    if len(pud_xy) == 0:
        return np.array([]), np.array([])
    if len(pool_xy) == 0:
        return np.full(len(pud_xy), np.nan), np.full(len(pud_xy), np.nan)
    kk = min(k, len(pool_xy))
    d, _ = cKDTree(pool_xy).query(pud_xy, k=kk)
    d = np.asarray(d, float).reshape(len(pud_xy), kk)
    d1 = d[:, 0] / FT_PER_MI
    dk = d[:, k - 1] / FT_PER_MI if kk == k else np.full(len(pud_xy), np.nan)
    return d1, dk


def package_counts(scored: pd.DataFrame, horizons: Sequence[int]) -> pd.DataFrame:
    """`scored`: one row per scored well with columns package, held_out (package-level), reached_<k> (bool, the well's cum-k
    is known). A package counts at horizon k when any member reached k (acceptance.package_errors keeps members with a
    finite actual). Returns one row per horizon: n_tuning, n_holdout, n_wells_tuning, n_wells_holdout."""
    rows = []
    for k in horizons:
        r = scored[scored[f"reached_{k}"]]
        t, h = r[~r["held_out"]], r[r["held_out"]]
        rows.append({"horizon": k, "n_tuning": int(t["package"].nunique()), "n_holdout": int(h["package"].nunique()),
                     "n_wells_tuning": len(t), "n_wells_holdout": len(h)})
    return pd.DataFrame(rows)


def judgeability(counts: pd.DataFrame, min_pkg: int = MIN_PACKAGES, min_prior: int = MIN_PRIOR) -> pd.DataFrame:
    """Per horizon from per-cutoff counts (columns cutoff, horizon, n_tuning, n_holdout): what the step-9 rules can do.

    d53_cells        tuning cells judged (>= min_pkg)
    wf_cutoffs       cutoffs whose box_v2_wf haircut exists (>= min_prior earlier judged cutoffs)
    pooled_holdout_wf   holdout packages pooled over wf_cutoffs (a box_v2_wf record's D99 cell)
    pooled_holdout_raw  holdout packages pooled over every cutoff (a raw box_v2 record's D99 cell, D97 pattern)
    d99_wf / d99_raw    that pooled cell reaches min_pkg
    d102_cutoffs     cutoffs whose merged tuning + holdout count reaches min_pkg (the production haircut's inputs)
    """
    counts = counts.copy()
    early = [(str(c), int(h)) in UNSCORED_EARLY for c, h in zip(counts["cutoff"], counts["horizon"], strict=True)]
    counts.loc[early, ["n_tuning", "n_holdout"]] = 0
    rows = []
    for k, g in counts.groupby("horizon", sort=True):
        g = g.sort_values("cutoff")
        judged = list(g.loc[g["n_tuning"] >= min_pkg, "cutoff"])
        wf = [c for c in g["cutoff"] if sum(j < c for j in judged) >= min_prior]
        p_wf = int(g.loc[g["cutoff"].isin(wf), "n_holdout"].sum())
        p_raw = int(g["n_holdout"].sum())
        d102 = list(g.loc[(g["n_tuning"] + g["n_holdout"]) >= min_pkg, "cutoff"])
        rows.append({"horizon": int(k), "d53_cells": len(judged), "wf_cutoffs": len(wf), "pooled_tuning": int(g["n_tuning"].sum()),
                     "pooled_holdout_wf": p_wf, "pooled_holdout_raw": p_raw, "d99_wf": p_wf >= min_pkg, "d99_raw": p_raw >= min_pkg,
                     "d102_cutoffs": len(d102)})
    return pd.DataFrame(rows)


def verdict_class(j: pd.DataFrame) -> str:
    """One-line read of a bench's judgeability table (cum-12 / cum-24 are the cells BS2_S was judged on)."""
    j = j.set_index("horizon")
    h12, h24 = j.loc[12], j.loc[24]
    if bool(h12["d99_wf"]) and bool(h24["d99_wf"]):
        return "judgeable as BS2_S was (box_v2_wf, D99 cum-12 + cum-24)"
    if bool(h12["d99_raw"]) and bool(h24["d99_raw"]):
        return "judgeable only as a raw box_v2 record (no walk-forward haircut, D97 pattern)"
    if bool(h12["d99_raw"]):
        return "cum-12 only (raw box_v2) - cum-24 holdout too thin"
    if int(h12["d102_cutoffs"]) > 0:
        return "not judgeable on its own holdout; a production haircut could still be measured"
    return "not judgeable under any rule of record"
