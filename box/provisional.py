"""BOX provisional benches (D105, Michael 2026-10-17): the disclosed bias for benches without an out-of-time test.

A provisional bench (AVA_0 / AVA_1 / AVA_2, BS2_C) is forecast with raw box_v2 (no haircut, no holdout). Its workups disclose
the bias MEASURED on its tuning packages (in-sample to the method's design, never out-of-time validated):
- pooled across every cutoff per stream x horizon (cum-12 / 24 / 36): package count and mean package bias, as D53 defines it
  (Σ actual / Σ forecast − 1 per package; + = forecast LOW);
- a 95 % range for that pooled bias from a cluster bootstrap over 3-mi blocks (resample blocks with replacement; a package
  belongs to the block of its first member) — the uncertainty of the number disclosed, not a holdout swing;
- the bias by cutoff (vintage), so a bias that changes sign over time is shown, not averaged away.
Pure: reads the step-9a-style view frames (box/rehearse9b.load_frames).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from box import acceptance as ac

HORIZONS = (12, 24, 36)
N_BOOT = 2000
SEED = 20261017


def package_frame(v: pd.DataFrame, variant: str = "box_v2", horizons: Sequence[int] = HORIZONS) -> pd.DataFrame:
    """One row per (package, stream, horizon): cutoff, cluster block, Σ actual, Σ forecast (members with both, forecast > 0)."""
    rows = []
    for s in ac.STREAMS:
        for k in horizons:
            a, p = v[f"actual_{s}{k}"].astype(float), v.get(f"pred_{variant}_{s}{k}", pd.Series(np.nan, index=v.index)).astype(float)
            ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
            if not ok.any():
                continue
            g = v[ok].assign(_a=a[ok], _p=p[ok]).groupby("pkg").agg(a=("_a", "sum"), p=("_p", "sum"), cutoff=("cutoff", "first"),
                                                                     bx=("bx", "first"), by=("by", "first")).reset_index()
            rows.append(g.assign(stream=s, horizon=k))
    out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["pkg", "a", "p", "cutoff", "bx", "by", "stream", "horizon"])
    out["err"] = out["a"] / out["p"] - 1.0
    out["block"] = out["bx"].astype(str) + ":" + out["by"].astype(str)
    return out


def bootstrap_bias(err: np.ndarray, block: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    """95 % range of the mean package error under a block (cluster) bootstrap."""
    blocks, inv = np.unique(block, return_inverse=True)
    if len(blocks) < 2:
        return float("nan"), float("nan")
    sums, counts = np.bincount(inv, weights=err), np.bincount(inv)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(blocks), size=(n_boot, len(blocks)))
    means = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


def disclosure(pk: pd.DataFrame, bench: str) -> pd.DataFrame:
    """Pooled disclosure rows per stream x horizon for one bench (or pooled group)."""
    rows = []
    for (s, k), g in pk.groupby(["stream", "horizon"], sort=True):
        lo, hi = bootstrap_bias(g["err"].to_numpy(float), g["block"].to_numpy())
        rows.append({"bench": bench, "stream": s, "horizon": int(k), "n_packages": len(g), "n_blocks": g["block"].nunique(),
                     "bias": float(g["err"].mean()), "range_lo": lo, "range_hi": hi, "cutoffs": len(g["cutoff"].unique())})
    return pd.DataFrame(rows)


def by_vintage(pk: pd.DataFrame, bench: str) -> pd.DataFrame:
    """Bias by cutoff (the next-12-months cohort it scores) per stream x horizon, with package counts."""
    g = pk.groupby(["stream", "horizon", "cutoff"]).agg(n_packages=("err", "size"), bias=("err", "mean")).reset_index()
    return g.assign(bench=bench)
