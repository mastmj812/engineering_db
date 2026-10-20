"""PDP-proximity study, step 2 — dose-response of drilled children vs the as-of BOX forecast (pure, no DB).

Yardstick (decision 2026-10-19): child actual ÷ BOX `box_v2` RAW forecast at the child's location, made at the harness
fold cutoff (Dec 1 before the child's first production; analogs = wells producing before the cutoff, so the child is
never its own analog). Those predictions are the per-well views the D53/D99 harness stored for every scored well of
every BOX bench group (tuning + holdout, folds Dec 2019-2024) — identical to the harness by construction.

Exposure (step-1 pair table, gate-1 definitions): each child takes its WORST depleting parent (age >= 12 months at its
first production, >= 30 % alongside, permit TVDs + shielded parents excluded) inside 1,000 ft vt / 2,640 ft hz, by the
v14 rule's aspect (min of hypot(dh, dv x 800/300)). Groups:
  exposed    a depleting parent inside 1,000 / 2,640 — cell = class x dv bin x dh bin
  young      no depleting parent there, but a 6-12-month-old one (reported, never control)
  ambiguous  only permit-TVD or shielded depleting parents there (reported, never control)
  control    none of the above (co-developed neighbours allowed — that is normal development)

Statistic: l = ln(actual / predicted) per child and metric (clipped to ln 0.1..ln 10). Each child is normalised by the
control mean of its (bench group, cutoff) — or its bench group when that has < MIN_CTRL controls, else all controls —
so BOX's own bench / vintage bias cancels. A cell's effect = exp(mean normalised l) = the typical child's production
relative to what BOX would forecast, after removing what BOX does on unexposed wells (0.80 = a 20 % haircut).
`<metric>_vs_box` = exp(mean l) with no normalisation: the cell against BOX as-is (BOX's analog pools already hold
exposed wells, so this is the over-forecast BOX would actually make there).
CIs: 3-mi block bootstrap (box.dev_factor.blocks), baselines re-estimated inside every draw.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from typing import Any

import numpy as np
import pandas as pd

from box import prox_study as ps

DV_EDGES = (0.0, 100.0, 200.0, 300.0, 500.0, 800.0, 1000.0)
DH_EDGES = (0.0, 400.0, 800.0, 1400.0, 2000.0, 2640.0)
EXPO_DV, EXPO_DH = 1000.0, 2640.0
ASPECT = ps.RULE_V14[1] / ps.RULE_V14[0]
METRICS = ("oil12", "oil24", "oil36", "gas12", "gas24", "gor12", "gor24")
L_CLIP = (np.log(0.1), np.log(10.0))
MIN_CTRL = 10
N_BOOT = 500
SEED = 20261019
PRECEDENT_FLOOR = 30  # gate 1: a geometry cell with fewer drilled children is "unprecedented"


def _label(edges: Sequence[float], v: float) -> str | None:
    for lo, hi in pairwise(edges):
        if (lo == 0 and v <= hi) or lo < v <= hi:
            return f"{lo:,.0f}-{hi:,.0f}"
    return None


DV_BINS = tuple(_label(DV_EDGES, (lo + hi) / 2) for lo, hi in pairwise(DV_EDGES))
DH_BINS = tuple(_label(DH_EDGES, (lo + hi) / 2) for lo, hi in pairwise(DH_EDGES))


def exposure(children: Sequence[str], links: pd.DataFrame) -> pd.DataFrame:
    """One row per child: group, and for exposed children the worst parent's class / geometry / bins / dose."""
    near = links[(links["dv_ft"] <= EXPO_DV) & (links["dh_ft"] <= EXPO_DH) & (links["overlap"] >= ps.MIN_OVERLAP)]
    dep = near[(near["rel"] == "parent") & ~near["permit"] & ~near["shielded"]].copy()
    dep["k"] = np.hypot(dep["dh_ft"], dep["dv_ft"] * ASPECT)
    worst = dep.loc[dep.groupby("child")["k"].idxmin()].set_index("child")
    young = set(near.loc[near["rel"] == "young", "child"])
    amb = set(near.loc[near["rel"] == "parent", "child"])
    out = pd.DataFrame({"api10": list(children)})
    out["group"] = [("exposed" if a in worst.index else "young" if a in young else "ambiguous" if a in amb else "control") for a in out["api10"]]
    cols = ["cls", "parent", "parent_bench", "dv_ft", "dh_ft", "dz_ft", "overlap", "age_days", "parent_cum_bbl_per_kft"]
    w = worst.reindex(out["api10"])[cols].reset_index(drop=True)
    out = pd.concat([out, w], axis=1)
    out["dv_bin"] = [_label(DV_EDGES, v) if np.isfinite(v) else None for v in out["dv_ft"].astype(float)]
    out["dh_bin"] = [_label(DH_EDGES, v) if np.isfinite(v) else None for v in out["dh_ft"].astype(float)]
    out["v14"] = (out["dv_ft"] <= ps.RULE_V14[0]) & (out["dh_ft"] <= ps.RULE_V14[1])
    return out


def log_ratios(v: pd.DataFrame) -> pd.DataFrame:
    """l_<metric> = ln(actual / box_v2) per child (NaN when either side is missing or non-positive)."""
    out = pd.DataFrame(index=v.index)
    for s in ("oil", "gas"):
        for k in (12, 24, 36):
            a, p = pd.to_numeric(v.get(f"actual_{s}{k}"), errors="coerce"), pd.to_numeric(v.get(f"pred_box_v2_{s}{k}"), errors="coerce")
            ok = (a > 0) & (p > 0)
            out[f"l_{s}{k}"] = np.where(ok, np.log(a.where(ok) / p.where(ok)), np.nan)
    for k in (12, 24):
        out[f"l_gor{k}"] = out[f"l_gas{k}"] - out[f"l_oil{k}"]
    return out.apply(lambda c: c.clip(*L_CLIP))


def baseline_keys(d: pd.DataFrame, metric: str) -> np.ndarray:
    """Per child the key of the control mean it is normalised by: (group, cutoff) -> group -> 'ALL' by MIN_CTRL."""
    ctrl = d[(d["group"] == "control") & d[f"l_{metric}"].notna()]
    n_gc = ctrl.groupby(["bench_group", "cutoff"]).size()
    n_g = ctrl.groupby("bench_group").size()
    keys = []
    for g, c in zip(d["bench_group"], d["cutoff"], strict=True):
        if n_gc.get((g, c), 0) >= MIN_CTRL:
            keys.append(f"{g}|{c}")
        elif n_g.get(g, 0) >= MIN_CTRL:
            keys.append(f"{g}|*")
        else:
            keys.append("ALL")
    return np.array(keys)


def _ctrl_mask_for_key(d: pd.DataFrame, key: str, ctrl: np.ndarray) -> np.ndarray:
    if key == "ALL":
        return ctrl
    g, c = key.split("|")
    m = ctrl & (d["bench_group"].to_numpy() == g)
    return m if c == "*" else m & (d["cutoff"].to_numpy() == c)


def boot_weights(blocks: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED) -> np.ndarray:
    """[n_boot + 1, n_rows] row weights; row 0 = the point estimate (all ones)."""
    rng = np.random.default_rng(seed)
    ub, inv = np.unique(blocks, return_inverse=True)
    draws = rng.multinomial(len(ub), np.full(len(ub), 1.0 / len(ub)), size=n_boot).astype(float)
    return np.vstack([np.ones(len(blocks)), draws[:, inv]])


class Effects:
    """Cell effects with block-bootstrap CIs for one metric. Built once per metric; `cell(mask)` is then cheap."""

    def __init__(self, d: pd.DataFrame, metric: str, W: np.ndarray) -> None:
        self.metric = metric
        l = d[f"l_{metric}"].to_numpy(float)
        self.ok = np.isfinite(l)
        self.l = np.where(self.ok, l, 0.0)
        self.W = W
        ctrl = (d["group"] == "control").to_numpy() & self.ok
        keys = baseline_keys(d, metric)
        self.ukeys, kinv = np.unique(keys, return_inverse=True)
        # per draw, per key: control mean of l
        base = np.zeros((W.shape[0], len(self.ukeys)))
        for j, key in enumerate(self.ukeys):
            m = _ctrl_mask_for_key(d, key, ctrl)
            den = W @ m.astype(float)
            base[:, j] = np.where(den > 0, (W @ (self.l * m)) / np.where(den > 0, den, 1.0), np.nan)
        self.base, self.kinv = base, kinv

    def cell(self, mask: np.ndarray) -> dict[str, Any]:
        idx = np.flatnonzero(mask & self.ok)
        n = len(idx)
        if n == 0:
            return {"n": 0, "effect": np.nan, "lo": np.nan, "hi": np.nan, "median_raw": np.nan, "vs_box": np.nan}
        w = self.W[:, idx]
        den = w.sum(axis=1)
        num = w @ self.l[idx] - (self.base[:, self.kinv[idx]] * w).sum(axis=1)
        mean = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
        draws = mean[1:][np.isfinite(mean[1:])]
        lo, hi = np.exp(np.percentile(draws, [5, 95])) if len(draws) else (np.nan, np.nan)
        return {"n": n, "effect": float(np.exp(mean[0])), "lo": float(lo), "hi": float(hi), "median_raw": float(np.exp(np.median(self.l[idx]))),
                "vs_box": float(np.exp(self.l[idx].mean()))}


def table(d: pd.DataFrame, effects: dict[str, Effects], masks: dict[str, np.ndarray], metrics: Sequence[str] = METRICS) -> pd.DataFrame:
    """Rows = named masks; columns n_<m> / <m> (effect) / <m>_lo / <m>_hi per metric, + precedent flag on oil12's n."""
    rows = []
    for name, mask in masks.items():
        r: dict[str, Any] = {"cell": name, "n_children": int(mask.sum())}
        for mt in metrics:
            c = effects[mt].cell(mask)
            r[f"n_{mt}"], r[mt], r[f"{mt}_lo"], r[f"{mt}_hi"], r[f"{mt}_vs_box"] = c["n"], c["effect"], c["lo"], c["hi"], c["vs_box"]
        r["below_floor"] = r["n_children"] < PRECEDENT_FLOOR
        rows.append(r)
    return pd.DataFrame(rows)
