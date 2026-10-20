"""PDP-proximity study, step 2c — walk-forward validation of the configuration haircut (pure, no DB).

Pre-registered in docs/box/prox-2026-10-19/PREREG_2c.md (committed before scoring). In short: a child's relative
log-ratio l_rel = ln(actual / as-of box_v2) minus the mean of all scored children of its (bench group, cutoff); the
haircut f(key) = exp(mean l_rel) over TRAINING children (strictly earlier cutoffs) carrying the key, the key taken
from a ladder (bench pair x count -> class x count x flank -> class x count -> class) at the first rung with >= 30
training children. Test residual r = l_rel - ln f; without a haircut r0 = l_rel.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import prox_dose as pdz
from box import prox_study as ps

RUNG_MIN = 30
MATERIAL = 0.90
P1_BAND = (0.95, 1.05)
P3_TOL = 0.10
P3_SHARE = 0.80
CELL_MIN = 30
N_BOOT = 1000
SEED = 20261020
TEST_CUTOFFS = {"oil24": ("2021-12-01", "2022-12-01", "2023-12-01"), "oil12": ("2021-12-01", "2022-12-01", "2023-12-01", "2024-12-01"),
                "oil36": ("2021-12-01", "2022-12-01"), "gas24": ("2021-12-01", "2022-12-01", "2023-12-01")}
RUNGS = ("k1", "k2", "k3", "k4")


def ladder_keys(c: pd.DataFrame) -> pd.DataFrame:
    """k1..k4 per child from the configuration columns (config_class, n_<cls>, flanked_<cls>, pb_<cls>, bench,
    n_parents_total). None where a rung does not apply."""
    out = []
    for _, r in c.iterrows():
        cc = r["config_class"]
        if not isinstance(cc, str):
            out.append(("none", "none", "none", "none"))
        elif cc == "mixed":
            t = int(r["n_parents_total"])
            k = f"mixed|{'4+' if t >= 4 else t}"
            out.append((None, k, k, "mixed"))
        else:
            n = pdz.npar_bin(int(r[f"n_{cc}"]))
            fl = "-" if n == "1" else ("F" if bool(r[f"flanked_{cc}"]) else "S")
            out.append((f"{ps.pool(r['bench'])}>{cc}>{ps.pool(r[f'pb_{cc}'])}|{n}", f"{cc}|{n}|{fl}", f"{cc}|{n}", cc))
    return pd.DataFrame(out, columns=list(RUNGS), index=c.index)


def l_rel(d: pd.DataFrame, metric: str) -> pd.Series:
    """ln(actual / pred) minus the mean over ALL scored children of the same (bench group, cutoff) — fallbacks by MIN_CTRL."""
    l = d[f"l_{metric}"]
    ok = l.notna()
    m_gc = l[ok].groupby([d.loc[ok, "bench_group"], d.loc[ok, "cutoff"]]).agg(["mean", "size"])
    m_g = l[ok].groupby(d.loc[ok, "bench_group"]).agg(["mean", "size"])
    m_all = float(l[ok].mean())
    base = []
    for g, c in zip(d["bench_group"], d["cutoff"], strict=True):
        if (g, c) in m_gc.index and m_gc.at[(g, c), "size"] >= pdz.MIN_CTRL:
            base.append(m_gc.at[(g, c), "mean"])
        elif g in m_g.index and m_g.at[g, "size"] >= pdz.MIN_CTRL:
            base.append(m_g.at[g, "mean"])
        else:
            base.append(m_all)
    return l - np.array(base, float)


def fit(keys: pd.DataFrame, lr: pd.Series) -> dict[str, dict[str, tuple[float, int]]]:
    """Per rung: key -> (mean l_rel, n) over the rows given (training)."""
    ok = lr.notna()
    return {k: {kk: (float(v["mean"]), int(v["size"])) for kk, v in lr[ok].groupby(keys.loc[ok, k]).agg(["mean", "size"]).iterrows()}
            for k in RUNGS}


def assign(keys: pd.DataFrame, table: dict[str, dict[str, tuple[float, int]]], min_n: int = RUNG_MIN) -> pd.DataFrame:
    """ln factor + the key / rung used, first rung with >= min_n training children; no rung -> factor 1 (rung 'none-fit')."""
    rows = []
    for _, r in keys.iterrows():
        got = (0.0, None, "unfit")
        for k in RUNGS:
            key = r[k]
            if isinstance(key, str) and key in table[k] and table[k][key][1] >= min_n:
                got = (table[k][key][0], key, k)
                break
        rows.append(got)
    return pd.DataFrame(rows, columns=["ln_f", "key", "rung"], index=keys.index)


def walk_forward(d: pd.DataFrame, metric: str, test_cutoffs: Sequence[str]) -> pd.DataFrame:
    keys = ladder_keys(d)
    lr = l_rel(d, metric)
    parts = []
    for c in test_cutoffs:
        tr = d["cutoff"] < c
        te = (d["cutoff"] == c) & lr.notna()
        if not te.any():
            continue
        a = assign(keys[te], fit(keys[tr], lr[tr]))
        p = pd.DataFrame({"api10": d.loc[te, "api10"], "cutoff": c, "block": d.loc[te, "block"], "l_rel": lr[te]}).join(a)
        p["r"], p["r0"] = p["l_rel"] - p["ln_f"], p["l_rel"]
        p["f"] = np.exp(p["ln_f"])
        parts.append(p)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _boot_mean(x: np.ndarray, blocks: np.ndarray, n_boot: int, seed: int) -> tuple[float, float, float]:
    W = pdz.boot_weights(blocks, n_boot=n_boot, seed=seed)
    m = (W @ x) / W.sum(axis=1)
    lo, hi = np.percentile(m[1:], [5, 95])
    return float(m[0]), float(lo), float(hi)


def score(p: pd.DataFrame, n_boot: int = N_BOOT, seed: int = SEED) -> dict[str, Any]:
    mat = p[p["f"] <= MATERIAL]
    if len(mat):
        m, lo, hi = _boot_mean(mat["r"].to_numpy(float), mat["block"].to_numpy(), n_boot, seed)
        p1_eff, p1_lo, p1_hi = np.exp(m), np.exp(lo), np.exp(hi)
        p1 = bool(P1_BAND[0] <= p1_eff <= P1_BAND[1] or p1_lo <= 1.0 <= p1_hi)
        m0 = np.exp(mat["r0"].mean())
    else:
        p1_eff = p1_lo = p1_hi = m0 = np.nan
        p1 = False
    cells = (p.groupby("key", dropna=False).agg(n=("r", "size"), rung=("rung", "first"), f=("f", "mean"), mean_r=("r", "mean"), mean_r0=("r0", "mean"))
             .reset_index())
    cells["resid"] = np.exp(cells["mean_r"])
    cells["no_haircut_resid"] = np.exp(cells["mean_r0"])
    big = cells[cells["n"] >= CELL_MIN]
    w = big["n"].to_numpy(float)
    rms = float(np.sqrt((w * big["mean_r"] ** 2).sum() / w.sum())) if len(big) else np.nan
    rms0 = float(np.sqrt((w * big["mean_r0"] ** 2).sum() / w.sum())) if len(big) else np.nan
    p2 = bool(len(big) and rms < rms0)
    ok3 = (np.abs(big["resid"] - 1.0) <= P3_TOL) if len(big) else pd.Series(dtype=bool)
    p3_share = float(ok3.mean()) if len(big) else np.nan
    p3 = bool(len(big) and p3_share >= P3_SHARE)
    return {"n_test": len(p), "n_material": len(mat), "P1_resid": float(p1_eff), "P1_lo": float(p1_lo), "P1_hi": float(p1_hi),
            "P1_no_haircut": float(m0), "P1": p1, "P2_rms": rms, "P2_rms_no_haircut": rms0, "P2": p2, "n_cells": len(big),
            "P3_share": p3_share, "P3": p3, "verdict": "PASS" if (p1 and p2 and p3) else "FAIL", "cells": cells.sort_values("n", ascending=False)}
