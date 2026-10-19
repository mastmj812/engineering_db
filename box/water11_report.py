"""BOX step 11 — water report pieces (pure, DB-free): reach tables, pooled tuning cells under the PRE-REGISTERED water test, the
§4 method choice, the frozen consistency intervals for gate 12a, and judgeable-cell counts. See
docs/box/step11-2026-10-19/PREREGISTRATION.md (committed 51d589c before any water score)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import holdout as ho
from box import water11 as w

BIAS_TOL_W = 0.20  # pre-registered (PREREGISTRATION §3)
BAND_TOL_W = 0.10
MIN_PACKAGES = 30
MIN_HOLDOUT_PACKAGES = 10  # PREREGISTRATION §5.4
METHODS: tuple[str, ...] = ("ratio", "arps", "ratio_actoil")
CHOICE_METHODS: tuple[str, ...] = ("ratio", "arps")
N_DRAWS = 2000
SEED = 20261019
SCALES: tuple[float, ...] = (0.80, 0.85, 0.90, 1.0, 1.10, 1.15, 1.20)


def judge_water(bias: float, band: float, b_bias: float, b_band: float, n: int) -> str:
    if n < MIN_PACKAGES or not np.isfinite(bias):
        return "not judged"
    bb, rb = ac.scale_free(band, bias), ac.scale_free(b_band, b_bias)
    ok = abs(bias) <= BIAS_TOL_W and (not np.isfinite(rb) or bb <= rb + BAND_TOL_W)
    return "PASS" if ok else "FAIL"


# ----------------------------------------------------------------------------
# (a) reach
# ----------------------------------------------------------------------------

RADIUS_CLASSES = (("≤ 5 mi", 0, 5), ("7.5–10 mi", 5, 10), ("15–20 mi", 10, 20), ("30–50 mi (extension)", 20, 50))


def reach_table(r: pd.DataFrame) -> pd.DataFrame:
    """Per group x state: locations, the share reaching each radius class with measured analogs, median radius, thin, fallback,
    and for TX the NM-analog share."""
    rows = []
    for (g, st), d in r.groupby(["group", "state"]):
        m = d[d["source"] == "measured"]
        row = {"group": g, "state": st, "locations": len(d)}
        for name, lo, hi in RADIUS_CLASSES:
            row[name] = float(((m["radius_mi"] > lo) & (m["radius_mi"] <= hi)).sum() / len(d))
        row |= {"median_radius_mi": float(m["radius_mi"].median()) if len(m) else np.nan, "p90_radius_mi": float(m["radius_mi"].quantile(0.9)) if len(m) else np.nan,
                "thin_share": float((m["thin"].astype(bool)).sum() / len(d)), "fallback_share": float((d["source"] == "calculated_fallback").mean()),
                "median_analogs": float(d["n_analogs"].median()),
                "any_nm_analog_share": float((d["nm_share"] > 0).mean()) if st == "TX" else np.nan,
                "mean_nm_analog_share": float(d["nm_share"].mean()) if st == "TX" else np.nan,
                "majority_nm_share": float((d["nm_share"] > 0.5).mean()) if st == "TX" else np.nan}
        rows.append(row)
    return pd.DataFrame(rows)


def pool_table(p: pd.DataFrame) -> pd.DataFrame:
    """Per group x state: pool wells first producing >= 2016 by BOX-water label (as of 2026-07-01)."""
    p = p[pd.to_datetime(p["first_production_date"]) >= "2016-01-01"].copy()
    p["state"] = np.where(p["state_code"].astype(str).str.startswith("30"), "NM", "TX")
    t = p.pivot_table(index=["group", "state"], columns="label", values="api10", aggfunc="count", fill_value=0).reset_index()
    for c in ("measured", "calculated", "indeterminate", "insufficient"):
        if c not in t:
            t[c] = 0
    t["measured_share"] = t["measured"] / t[["measured", "calculated", "indeterminate", "insufficient"]].sum(axis=1)
    return t[["group", "state", "measured", "calculated", "indeterminate", "insufficient", "measured_share"]]


# ----------------------------------------------------------------------------
# (b) tuning cells
# ----------------------------------------------------------------------------


def cells(t: pd.DataFrame, by: Sequence[str] = ("group",), methods: Sequence[str] = METHODS) -> pd.DataFrame:
    """Pooled package statistics per `by` x horizon x method (packages keyed cutoff:package, so cutoffs pool, D99)."""
    t = t.copy()
    t["package"] = t["cutoff"].astype(str) + ":" + t["package"].astype(str)
    rows = []
    for key, d in t.groupby(list(by)):
        key = key if isinstance(key, tuple) else (key,)
        for k in w.HORIZONS:
            bst = w.package_stats(d, f"actual_w{k}", f"bench_w{k}")
            for m in methods:
                col = f"{m}_w{k}"
                if col not in d:
                    continue
                st = w.package_stats(d, f"actual_w{k}", col)
                rows.append(dict(zip(by, key, strict=True)) | {"horizon": k, "method": m, **{f"pkg_{a}": b for a, b in st.items()},
                            "bench_bias": bst["bias"], "bench_band": bst["band"], "bench_band_sf": bst["band_sf"],
                            "verdict": judge_water(st["bias"], st["band"], bst["bias"], bst["band"], st["n_packages"])})
    return pd.DataFrame(rows)


def choose_method(c: pd.DataFrame) -> dict[str, Any]:
    """PREREGISTRATION §4: ratio unless arps passes strictly more judged cells AND has a lower median |bias| over judged cells."""
    out: dict[str, Any] = {}
    for m in CHOICE_METHODS:
        j = c[(c["method"] == m) & (c["verdict"] != "not judged")]
        out[m] = {"judged": len(j), "passed": int((j["verdict"] == "PASS").sum()), "median_abs_bias": float(j["pkg_bias"].abs().median()) if len(j) else np.nan}
    a, r = out["arps"], out["ratio"]
    out["chosen"] = "arps" if (a["passed"] > r["passed"] and a["median_abs_bias"] < r["median_abs_bias"]) else "ratio"
    return out


# ----------------------------------------------------------------------------
# (c) frozen consistency intervals (rehearse9b method, water stream)
# ----------------------------------------------------------------------------


def package_sums(t: pd.DataFrame, method: str) -> dict[str, Any]:
    """Per package (cutoff:package) its 3-mi blocks and member sums per horizon for `method` and the benchmark."""
    t = t.copy()
    t["pkg"] = t["cutoff"].astype(str) + ":" + t["package"].astype(str)
    bx, by = ho.blocks(t["x"].to_numpy(float), t["y"].to_numpy(float))
    t["bx"], t["by"] = bx, by
    pk = sorted(t["pkg"].unique())
    idx = {p: i for i, p in enumerate(pk)}
    blk = t[["pkg", "bx", "by"]].drop_duplicates()
    blocks = sorted(set(zip(blk["bx"], blk["by"], strict=True)))
    bidx = {b: i for i, b in enumerate(blocks)}
    member = np.zeros((len(pk), len(blocks)), dtype=bool)
    member[[idx[p] for p in blk["pkg"]], [bidx[(a, b)] for a, b in zip(blk["bx"], blk["by"], strict=True)]] = True
    sums = {}
    for k in w.HORIZONS:
        a = t[f"actual_w{k}"].astype(float)
        p = t[f"{method}_w{k}"].astype(float) if f"{method}_w{k}" in t else pd.Series(np.nan, index=t.index)
        ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
        g = t[ok].assign(_a=a[ok], _p=p[ok]).groupby("pkg")[["_a", "_p"]].sum()
        A, P = np.full(len(pk), np.nan), np.full(len(pk), np.nan)
        ii = [idx[x] for x in g.index]
        A[ii], P[ii] = g["_a"].to_numpy(), g["_p"].to_numpy()
        sums[k] = (A, P)
    return {"pkg": pk, "member": member, "n_blocks": len(blocks), "sums": sums}


def _bias(sel: np.ndarray, s: dict[str, Any], k: int, scale: float = 1.0) -> tuple[float, int]:
    A, P = s["sums"][k]
    m = sel & np.isfinite(A)
    if not m.any():
        return float("nan"), 0
    return float(np.mean(A[m] / (P[m] * scale) - 1.0)), int(m.sum())


def consistency(s: dict[str, Any], n_draws: int = N_DRAWS, seed: int = SEED, share: float = ho.SHARE,
                scales: Sequence[float] = SCALES) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per horizon: the tuning pooled bias, the P2.5-P97.5 interval over 20 % block draws, expected holdout-size package count,
    and the rule's pass rate per horizon when the forecast is scaled (power: how often a forecast s x as large is caught)."""
    rng = np.random.default_rng(seed)
    draws = [(s["member"] & (rng.random(s["n_blocks"]) < share)[None, :]).any(axis=1) for _ in range(n_draws)]
    full = np.ones(len(s["pkg"]), dtype=bool)
    rows, prow = [], []
    for k in w.HORIZONS:
        b0, n0 = _bias(full, s, k)
        res = {sc: np.array([_bias(sel, s, k, sc) for sel in draws]) for sc in scales}
        b1 = res[1.0][:, 0]
        ns = res[1.0][:, 1]
        judged = ns >= MIN_HOLDOUT_PACKAGES
        lo, hi = (np.nanpercentile(b1[judged], 2.5), np.nanpercentile(b1[judged], 97.5)) if judged.any() else (np.nan, np.nan)
        rows.append({"horizon": k, "tuning_bias": b0, "tuning_packages": n0, "interval_lo": lo, "interval_hi": hi,
                     "draw_packages_p50": float(np.median(ns)), "share_draws_judged": float(judged.mean())})
        for sc in scales:
            bb, nn = res[sc][:, 0], res[sc][:, 1]
            j = nn >= MIN_HOLDOUT_PACKAGES
            prow.append({"horizon": k, "scale": sc, "pass_rate": float(np.mean((bb[j] >= lo) & (bb[j] <= hi))) if j.any() and np.isfinite(lo) else np.nan})
    return pd.DataFrame(rows), pd.DataFrame(prow)


def holdout_counts(c: pd.DataFrame) -> pd.DataFrame:
    """From the counts run: per group x side, measured-water packages pooled over cutoffs per horizon, and whether the pooled
    cell would be judged (tuning >= 30; holdout >= 10)."""
    g = c.groupby(["group", "side"])[["n_wells", "n_packages", "n_measured_wells", "n_measured_packages", "n_nm_measured_wells", *[f"pk_w{k}" for k in w.HORIZONS]]].sum().reset_index()
    for k in w.HORIZONS:
        floor = np.where(g["side"] == "holdout", MIN_HOLDOUT_PACKAGES, MIN_PACKAGES)
        g[f"judged_w{k}"] = g[f"pk_w{k}"] >= floor
    return g
