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


def ref_mask(d: pd.DataFrame, ref: str) -> np.ndarray:
    """The reference population: 'control' (no parent — the physical haircut) or 'all' (every scored child — the mix
    BOX's analog pools and walk-forward calibration represent, so a haircut applied to a BOX forecast isn't double-counted)."""
    if ref == "control":
        return (d["group"] == "control").to_numpy()
    if ref == "all":
        return np.ones(len(d), bool)
    raise ValueError(ref)


def baseline_keys(d: pd.DataFrame, metric: str, ref: str = "control") -> np.ndarray:
    """Per child the key of the reference mean it is normalised by: (group, cutoff) -> group -> 'ALL' by MIN_CTRL."""
    ctrl = d[ref_mask(d, ref) & d[f"l_{metric}"].notna().to_numpy()]
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

    def __init__(self, d: pd.DataFrame, metric: str, W: np.ndarray, ref: str = "control") -> None:
        self.metric, self.ref = metric, ref
        l = d[f"l_{metric}"].to_numpy(float)
        self.ok = np.isfinite(l)
        self.l = np.where(self.ok, l, 0.0)
        self.W = W
        ctrl = ref_mask(d, ref) & self.ok
        keys = baseline_keys(d, metric, ref)
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


# ============================================================================
# Step 2b — configuration: how many depleted parents, which sides (Michael 2026-10-20: a PUD over a developed DSU is
# flanked by several parents; the step-2 averages were diluted by lone single-parent tests)
# ============================================================================

# Per-class envelope = where step 2's marginal effect had faded (FINDINGS §9): (max dv, max dh) ft
ENVELOPE = {"same": (EXPO_DV, 1400.0), "topfill": (800.0, 1400.0), "underfill": (500.0, 1400.0)}
BENEATH_FT = 100.0   # a parent within this signed offset sits beneath / above the child: it counts on BOTH sides
NPAR_BINS = ("1", "2", "3+")
GEOM_BANDS = {  # table order; geom_band() assigns them
    "same": ("dh<400", "dh400-800", "dh800-1400"),
    "topfill": ("dv<=300|dh<800", "dv<=300|dh800-1400", "dv300-800|dh<800", "dv300-800|dh800-1400"),
    "underfill": ("dv<=300|dh<800", "dv<=300|dh800-1400", "dv300-500|dh<800", "dv300-500|dh800-1400"),
}


def npar_bin(n: int) -> str:
    return "3+" if n >= 3 else str(n)


def geom_band(cls: str, dv: float, dh: float) -> str:
    """Band of the child's NEAREST parent in the class envelope (nearest by the v14 aspect)."""
    if cls == "same":
        return "dh<400" if dh < 400 else "dh400-800" if dh < 800 else "dh800-1400"
    near_v = dv <= 300
    lo_v = "dv<=300" if near_v else ("dv300-800" if cls == "topfill" else "dv300-500")
    return f"{lo_v}|{'dh<800' if dh < 800 else 'dh800-1400'}"


def configuration(children: Sequence[str], links: pd.DataFrame) -> pd.DataFrame:
    """Per child and class: n depleting parents inside the class envelope, nearest-parent geometry band, flanked (parents
    on both sides, a beneath/above parent counting for both). config_class = the single class with parents ('mixed' when
    more than one, None when none). Same parent filter as step 1/2 (>= 12 mo, >= 30 % alongside, no permit / shielded)."""
    q = links[(links["rel"] == "parent") & (links["overlap"] >= ps.MIN_OVERLAP) & ~links["permit"] & ~links["shielded"]]
    out = pd.DataFrame({"api10": list(children)}).set_index("api10")
    present = []
    for c, (vmax, hmax) in ENVELOPE.items():
        e = q[(q["cls"] == c) & (q["dv_ft"] <= vmax) & (q["dh_ft"] <= hmax)].copy()
        e["k"] = np.hypot(e["dh_ft"], e["dv_ft"] * ASPECT)
        g = e.groupby("child")
        n = g["parent"].nunique()
        near = e.loc[g["k"].idxmin()].set_index("child") if len(e) else e.set_index("child")
        left = g["dxy_ft"].max() > -BENEATH_FT     # some parent on the left (or beneath)
        right = g["dxy_ft"].min() < BENEATH_FT     # some parent on the right (or beneath)
        out[f"n_{c}"] = n.reindex(out.index).fillna(0).astype(int)
        out[f"dv_{c}"] = near["dv_ft"].reindex(out.index)
        out[f"dh_{c}"] = near["dh_ft"].reindex(out.index)
        out[f"pb_{c}"] = near["parent_bench"].reindex(out.index)
        out[f"flanked_{c}"] = ((left & right) & (n >= 2)).reindex(out.index).fillna(False).astype(bool)
        out[f"band_{c}"] = [geom_band(c, v, h) if k > 0 else None for v, h, k in zip(out[f"dv_{c}"], out[f"dh_{c}"], out[f"n_{c}"], strict=True)]
        present.append(out[f"n_{c}"] > 0)
    cnt = sum(p.astype(int) for p in present)
    cls = np.select([present[0], present[1], present[2]], list(ENVELOPE), default=None)
    out["config_class"] = np.where(cnt > 1, "mixed", cls)
    out.loc[cnt == 0, "config_class"] = None
    out["n_parents_total"] = sum(out[f"n_{c}"] for c in ENVELOPE)
    out["config"] = [(f"{c}|{npar_bin(int(r[f'n_{c}']))}|{r[f'band_{c}']}" if c in ENVELOPE else None)
                     for c, (_, r) in zip(out["config_class"], out.iterrows(), strict=True)]
    return out.reset_index()
