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

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

NEAR_BINS: tuple[tuple[str, float, float], ...] = (("0-1", 0, 1), ("2-3", 2, 3), ("4-5", 4, 5), ("6+", 6, math.inf))
SPACING_BINS: tuple[tuple[str, float, float], ...] = (("<660", 0, 660), ("660-880", 660, 880), ("880-1320", 880, 1320), (">=1320", 1320, 2800))
NO_NEIGHBOUR = "none"
SENTINEL_FT = 2800.0
LATERAL_BINS: tuple[tuple[str, float, float], ...] = (("<8k", 0, 8000), ("8-11k", 8000, 11000), ("11-13.5k", 11000, 13500), (">=13.5k", 13500, math.inf))


from box.lateral import (  # noqa: F401  (D50; kept importable here)
    CUI_DELAWARE,
    lateral_efficiency,
)


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


def fit_numeric(train: pd.DataFrame, actual_col: str, pred_col: str, cols: Sequence[str]) -> dict[str, Any]:
    """Continuous multiplier from training wells: actual ~ pred x exp((x - mean_train) . b), PPML with the prediction
    as offset; a missing feature sits at the training mean (multiplier 1 for that term)."""
    ok = np.isfinite(train[actual_col].astype(float)) & np.isfinite(train[pred_col].astype(float)) & (train[pred_col].astype(float) > 0)
    t = train[ok]
    mean = t[list(cols)].astype(float).mean()
    X = (t[list(cols)].astype(float) - mean).fillna(0.0).to_numpy()
    b = ppml_offset(X, t[actual_col].to_numpy(float), np.log(t[pred_col].to_numpy(float)))
    return {"cols": list(cols), "mean": {c: float(mean[c]) for c in cols}, "b": {c: float(v) for c, v in zip(cols, b[1:], strict=True)},
            "sd": {c: float(t[c].astype(float).std()) for c in cols}}


def numeric_multiplier(df: pd.DataFrame, fit: dict[str, Any]) -> np.ndarray:
    z = np.zeros(len(df))
    for c in fit["cols"]:
        z += (df[c].astype(float) - fit["mean"][c]).fillna(0.0).to_numpy() * fit["b"][c]
    return np.exp(z)
