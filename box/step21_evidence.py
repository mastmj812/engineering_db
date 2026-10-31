"""BOX step 21a — evidence pieces for the Midland pre-registration (pure, no DB; scripts/box_step21a.py pulls and renders).

Nothing here forecasts or scores. The pieces measure what the pre-registration needs to state its cells and its reports:
  reach              distance from each in-extent undrilled stick to its 3rd / 10th nearest analog-eligible producer and the
                     radius class the 10th falls in (circle only: the D55 strike ellipse is ignored, so the real search reaches
                     at least this far) — oil (the D54 ladder) and measured water (the ladder + D107's 30 / 40 / 50 mi)
  top_operator_share the largest single operator's share of a stick's 10 nearest measured-water analogs (D133 concentration)
  per_ft_by_length   D129: observed 12-month oil per 1,000 ft by completed-lateral class relative to the 7,500-10,000 ft class,
                     within 3-mi block x first-production-year cells (location and vintage held fixed), next to what the Cui &
                     Cross curve implies for the same classes; run on producers in TUNING blocks only (the D52 holdout unread)
  ladder_fill        drilled multi-parent children per proximity ladder rung (k1..k4, box/prox_validate) — which rungs a
                     Midland factor table could fill at the 30-child floor
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import lateral as lat

FT_PER_MI = 5280.0
OIL_RINGS_MI: tuple[float, ...] = (5.0, 7.5, 10.0, 15.0, 20.0)  # box/analog.py radius ladder (D54)
WATER_RINGS_MI: tuple[float, ...] = (*OIL_RINGS_MI, 30.0, 40.0, 50.0)  # D107 water extension
MIN_WELLS = 10  # deal-intake min_wells (oil) = D107's measured-analog target
WATER_THIN_MIN = 3  # D107: 3-9 measured at 50 mi = thin; < 3 = vendor-calculated fallback
REF_CLASS = (7_500.0, 10_000.0)
LENGTH_EDGES_FT: tuple[float, ...] = (5_000.0, 7_500.0, 10_000.0, 12_500.0, 15_000.0, 17_500.0, 20_000.0, np.inf)


def ring_label(d_mi: float, rings: Sequence[float]) -> str:
    if not np.isfinite(d_mi):
        return "none"
    for r in rings:
        if d_mi <= r:
            return f"<={r:g}"
    return f">{rings[-1]:g}"


def knn(stick_xy: np.ndarray, pool_xy: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """(distances in MILES, indices) of the k nearest pool points per stick; inf / len(pool) where the pool is short."""
    if len(pool_xy) == 0 or len(stick_xy) == 0:
        return np.full((len(stick_xy), k), np.inf), np.full((len(stick_xy), k), 0, dtype=int)
    d, i = cKDTree(pool_xy).query(stick_xy, k=k)
    d, i = np.asarray(d, float).reshape(len(stick_xy), -1), np.asarray(i).reshape(len(stick_xy), -1)
    if d.shape[1] < k:
        d = np.pad(d, ((0, 0), (0, k - d.shape[1])), constant_values=np.inf)
        i = np.pad(i, ((0, 0), (0, k - i.shape[1])), constant_values=len(pool_xy))
    return d / FT_PER_MI, i


def reach(stick_xy: np.ndarray, pool_xy: np.ndarray, rings: Sequence[float], k: int = MIN_WELLS) -> pd.DataFrame:
    """Per stick: d1 / d3 / d10 (mi) and the ring the k-th analog falls in."""
    d, _ = knn(stick_xy, pool_xy, k)
    out = pd.DataFrame({"d1_mi": d[:, 0], "d3_mi": d[:, min(2, k - 1)], "d10_mi": d[:, k - 1]})
    out["ring"] = [ring_label(x, rings) for x in out["d10_mi"]]
    return out


def water_class(d3_mi: float, d10_mi: float, cap_mi: float = WATER_RINGS_MI[-1]) -> str:
    """D107 by circle: 'ring' (10 measured inside the cap), 'thin' (3-9 inside it), 'fallback' (< 3)."""
    if np.isfinite(d10_mi) and d10_mi <= cap_mi:
        return "ring"
    if np.isfinite(d3_mi) and d3_mi <= cap_mi:
        return "thin"
    return "fallback"


def top_operator_share(stick_xy: np.ndarray, pool_xy: np.ndarray, operators: Sequence[str], k: int = MIN_WELLS) -> np.ndarray:
    """The largest single operator's share among each stick's k nearest pool wells (NaN where the pool has < k wells)."""
    if len(pool_xy) < k:
        return np.full(len(stick_xy), np.nan)
    _, idx = knn(stick_xy, pool_xy, k)
    ops = np.asarray(list(operators), dtype=object)
    out = np.empty(len(stick_xy))
    for n, row in enumerate(idx):
        _, c = np.unique(ops[row].astype(str), return_counts=True)
        out[n] = c.max() / k
    return out


def length_class(x_ft: float, edges: Sequence[float] = LENGTH_EDGES_FT) -> str | None:
    if not np.isfinite(x_ft) or x_ft < edges[0]:
        return None
    for lo, hi in itertools.pairwise(edges):
        if x_ft < hi:
            return f"{lo / 1000:g}-{hi / 1000:g}k" if np.isfinite(hi) else f">={lo / 1000:g}k"
    return None


def _class_mid(lo: float, hi: float) -> float:
    return (lo + hi) / 2.0 if np.isfinite(hi) else lo + 1_250.0


def cui_ratio(lo: float, hi: float, ref: tuple[float, float] = REF_CLASS) -> float:
    """Cui & Cross per-ft efficiency of a class's midpoint over the reference class's (box/lateral, extension past 12,500 ft)."""
    return lat.lateral_efficiency(_class_mid(lo, hi)) / lat.lateral_efficiency(_class_mid(*ref))


def per_ft_by_length(d: pd.DataFrame, n_boot: int = 300, seed: int = 20261031, edges: Sequence[float] = LENGTH_EDGES_FT) -> pd.DataFrame:
    """`d`: one row per producer with block (hashable), fp_year, lateral_ft, oil12_kft (> 0). ln(oil12_kft) is demeaned
    within (block, fp_year) cells holding >= 2 wells; a class's ratio = exp(mean residual of the class - mean residual of the
    7,500-10,000 ft class). Block bootstrap (resample blocks) gives a 90 % interval. Returns one row per class with n wells,
    n cells, the observed ratio and interval, and the Cui-implied ratio."""
    x = d[np.isfinite(d["oil12_kft"]) & (d["oil12_kft"] > 0) & np.isfinite(d["lateral_ft"])].copy()
    x["cls"] = [length_class(v, edges) for v in x["lateral_ft"]]
    x = x[x["cls"].notna()]
    x["cell"] = list(zip(x["block"], x["fp_year"], strict=True))
    n_cell = x.groupby("cell")["cell"].transform("size")
    x = x[n_cell >= 2].copy()
    x["ly"] = np.log(x["oil12_kft"].astype(float))
    x["r"] = x["ly"] - x.groupby("cell")["ly"].transform("mean")
    ref = length_class(_class_mid(*REF_CLASS), edges)
    labels = [length_class(_class_mid(lo, hi), edges) for lo, hi in itertools.pairwise(edges)]

    def ratios(f: pd.DataFrame) -> dict[str, float]:
        m = f.groupby("cls")["r"].mean()
        if ref not in m.index:
            return {c: np.nan for c in labels}
        return {c: float(np.exp(m[c] - m[ref])) if c in m.index else np.nan for c in labels}

    point = ratios(x)
    rng = np.random.default_rng(seed)
    blocks = x["block"].unique()
    by_block = {b: g for b, g in x.groupby("block")}
    boot = []
    for _ in range(n_boot):
        pick = rng.choice(len(blocks), size=len(blocks), replace=True)
        boot.append(ratios(pd.concat([by_block[blocks[i]] for i in pick], ignore_index=True)))
    bt = pd.DataFrame(boot)
    rows = []
    for (lo, hi), c in zip(itertools.pairwise(edges), labels, strict=True):
        s = x[x["cls"] == c]
        q = bt[c].dropna() if c in bt else pd.Series(dtype=float)
        rows.append({"class": c, "n_wells": len(s), "n_cells": int(s["cell"].nunique()), "observed": point.get(c, np.nan),
                     "lo90": float(q.quantile(0.05)) if len(q) else np.nan, "hi90": float(q.quantile(0.95)) if len(q) else np.nan,
                     "cui": cui_ratio(lo, hi), "extrapolated": bool(_class_mid(lo, hi) > 12_500.0)})
    return pd.DataFrame(rows)


def body_or_addition(inside_body_share: float, inside: float = 0.5) -> str:
    """D143: a DEAN stick counts as BODY when >= 50 % of it lies in the generated body (rule 9, the in-extent test), else as
    the owner loop's ADDITION."""
    return "body" if np.isfinite(inside_body_share) and inside_body_share >= inside else "addition"


def ladder_fill(keys: pd.DataFrame, floor: int = 30) -> pd.DataFrame:
    """`keys`: box/prox_validate.ladder_keys output (k1..k4 per child). Children per rung key, and whether it reaches `floor`."""
    rows = []
    for rung in ("k1", "k2", "k3", "k4"):
        if rung not in keys:
            continue
        for key, n in keys[rung].dropna().value_counts().items():
            rows.append({"rung": rung, "key": key, "n_children": int(n), "fills": bool(n >= floor)})
    return pd.DataFrame(rows, columns=["rung", "key", "n_children", "fills"])
