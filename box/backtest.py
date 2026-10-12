"""BOX step 6 (fail branch) — rolling-origin backtest + the development-density term (pure).

Michael 2026-10-12: score BOX against actuals, Novi-agnostic, over several cutoffs (is the oil miss stable or
a one-year draw?), and test whether package tightness explains what the scenario classes cannot (Burton Flat
3 1: four 15,000-ft WCA_1 laterals in a ~13-well, ~700-ft-thick co-developed cube, factor 1.00).

Density, measured at first production (no later wells), two pre-registered measures:
  * n_near  — co-extent neighbour laterals within +-500 ft TVD, parents + codev, any bench
              (box.dev_factor.near_neighbours on sql/47's bench_context);
  * spacing — same-bench lateral_closer_xy_ft (wells_enriched; 2,800.0 is Novi's no-neighbour sentinel).
The density multiplier is fitted on the TRAINING wells as a Poisson PML with the BOX prediction as an offset
(E[actual] = pred x exp(X b), a ratio of means like D47), then normalised so the training cohort's total is
unchanged — F(k) keeps the level, the density term only redistributes it between tight and loose wells.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

NEAR_BINS: tuple[tuple[str, float, float], ...] = (("0-1", 0, 1), ("2-3", 2, 3), ("4-5", 4, 5), ("6+", 6, math.inf))
SPACING_BINS: tuple[tuple[str, float, float], ...] = (("<660", 0, 660), ("660-880", 660, 880), ("880-1320", 880, 1320), (">=1320", 1320, 2800))
NO_NEIGHBOUR = "none"
SENTINEL_FT = 2800.0
LATERAL_BINS: tuple[tuple[str, float, float], ...] = (("<8k", 0, 8000), ("8-11k", 8000, 11000), ("11-13.5k", 11000, 13500), (">=13.5k", 13500, math.inf))


# Cui & Cross (Novi Labs), URTeC 3723784 (2022), Figure 8, Delaware Wolfcamp A: 3-yr oil per ft relative to a
# 5,000-ft lateral, by completion size (lb/ft - bbl/ft). 10,000-ft values are the paper's labels; 7,500 / 12,500
# read off the figure (+-0.005). docs/box/ref/3723784.pdf.
CUI_DELAWARE: dict[str, tuple[tuple[float, float], ...]] = {
    "1000-30": ((5000, 1.000), (7500, 1.000), (10000, 0.94), (12500, 0.896)),
    "1350-40": ((5000, 1.000), (7500, 0.949), (10000, 0.89), (12500, 0.851)),
    "1700-50": ((5000, 1.000), (7500, 0.910), (10000, 0.85), (12500, 0.820)),
    "2000-60": ((5000, 1.000), (7500, 0.888), (10000, 0.83), (12500, 0.801)),
}


def lateral_efficiency(lateral_ft: float, curve: str = "2000-60") -> float:
    """Per-ft efficiency vs a 5,000-ft lateral: linear between the paper's points, 1.0 below 5,000 ft, and the
    last segment's slope extended past 12,500 ft (the paper's Delaware range ends there; flagged)."""
    pts = CUI_DELAWARE[curve]
    x = float(lateral_ft)
    if not np.isfinite(x):
        return float("nan")
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in itertools.pairwise(pts):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    (x0, y0), (x1, y1) = pts[-2], pts[-1]
    return y1 + (y1 - y0) * (x - x1) / (x1 - x0)


def near_bin(n: float | None) -> str | None:
    if n is None or not np.isfinite(n):
        return None
    return next(lab for lab, lo, hi in NEAR_BINS if lo <= n <= hi)


def spacing_bin(ft: float | None) -> str:
    """Same-bench spacing class; NULL or the 2,800 sentinel = no same-bench neighbour."""
    if ft is None or not np.isfinite(ft) or ft == SENTINEL_FT or ft >= SENTINEL_FT:
        return NO_NEIGHBOUR
    return next(lab for lab, lo, hi in SPACING_BINS if lo <= ft < hi)


def lateral_bin(ft: float | None) -> str | None:
    if ft is None or not np.isfinite(ft):
        return None
    return next(lab for lab, lo, hi in LATERAL_BINS if lo <= ft < hi)


def dummies(df: pd.DataFrame, cols: Sequence[str], reference: dict[str, str]) -> pd.DataFrame:
    """0/1 columns per non-reference level of each categorical column (NaN level -> the reference)."""
    out = {}
    for c in cols:
        v = df[c].astype(object).where(df[c].notna(), reference[c])
        for lv in sorted(set(v) - {reference[c]}):
            out[f"{c}={lv}"] = (v == lv).astype(float).to_numpy()
    return pd.DataFrame(out, index=df.index)


def ppml_offset(X: np.ndarray, y: np.ndarray, offset: np.ndarray, iters: int = 100, tol: float = 1e-10) -> np.ndarray:
    """Poisson PML (IRLS) for E[y] = exp(offset + c + X b); returns [c, b...]. Rows need y >= 0, finite offset."""
    Z = np.column_stack([np.ones(len(y)), X]) if X.size else np.ones((len(y), 1))
    b = np.zeros(Z.shape[1])
    b[0] = math.log(max(float(y.sum()), 1e-12) / float(np.exp(offset).sum()))
    for _ in range(iters):
        eta = np.clip(offset + Z @ b, -50, 50)
        mu = np.exp(eta)
        z = (eta - offset) + (y - mu) / mu
        sw = np.sqrt(mu)
        b_new, *_ = np.linalg.lstsq(Z * sw[:, None], z * sw, rcond=None)
        if np.max(np.abs(b_new - b)) < tol:
            return b_new
        b = b_new
    return b


def fit_density(train: pd.DataFrame, actual_col: str, pred_col: str, cols: Sequence[str], reference: dict[str, str]) -> dict[str, float]:
    """Density multipliers per level (reference = 1) from training wells: actual ~ pred x exp(X b)."""
    ok = np.isfinite(train[actual_col].astype(float)) & np.isfinite(train[pred_col].astype(float)) & (train[pred_col].astype(float) > 0)
    t = train[ok]
    X = dummies(t, cols, reference)
    b = ppml_offset(X.to_numpy(float), t[actual_col].to_numpy(float), np.log(t[pred_col].to_numpy(float)))
    return {name: float(math.exp(v)) for name, v in zip(X.columns, b[1:], strict=True)}


def density_multiplier(df: pd.DataFrame, factors: dict[str, float], cols: Sequence[str], reference: dict[str, str]) -> np.ndarray:
    """Un-normalised exp(X b) per row (levels unseen in training get 1)."""
    m = np.ones(len(df))
    for c in cols:
        v = df[c].astype(object).where(df[c].notna(), reference[c])
        m *= np.array([factors.get(f"{c}={lv}", 1.0) for lv in v])
    return m


def normaliser(weights: np.ndarray, mult: np.ndarray) -> float:
    """1 / (Σ w m / Σ w): keeps the training total unchanged so F(k) still carries the level."""
    w, m = np.asarray(weights, float), np.asarray(mult, float)
    ok = np.isfinite(w) & np.isfinite(m) & (w > 0)
    return float(w[ok].sum() / (w[ok] * m[ok]).sum())
