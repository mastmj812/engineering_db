"""BOX step 6 — hindcast vs Novi 2025Q3: prediction assembly, error statistics, the §8 verdict (pure).

Plan §5 step 6, §8, D36, D41–D49. Every holdout well is predicted from objects rebuilt with pre-cutoff
data only (areas, curves, factors, F(k) — box/hindcast_report.py does the rebuild):

    oil cum-k = Σ_{m<k} oil_month_m(area mean curve, D39 exact) × ref_mult_oil(area, D43)
                × f_oil(well's scenario, D41/D42/D45) × lateral / 1,000 × F_oil(k)          (D36)
    gas cum-k = Σ_{m<k} gas_month_m(area ratio, alpha shifted to local GOR × f_GOR, D30/D46)
                × ref_mult_oil × f_oil × lateral / 1,000 × F_gas(k)

The gas ratio is evaluated on the curve's own per-1,000-ft Np: GOR vs TIME is the area shape at the
well's level, and the oil scale (lateral, ref_mult, factor) carries both streams. F(k) = Σ actual / Σ
prediction at month k over the pre-cutoff training cohort (D36: pooled per bench, stamped).

Error convention = sql/43: error = actual / predicted − 1 (positive = the forecast was LOW). Bias = mean
error; spread = the P10–P90 band of the errors, P10 = HIGH (SPE): band = 90th − 10th percentile.

Verdict (§8 + D48 + D49), per stream (oil, gas) × horizon (cum-6, cum-12):
  * a group PASSES when |BOX bias| <= 10 % AND |BOX bias| < |Novi bias| AND BOX band <= Novi band;
  * area test: TC areas with >= 10 scored holdout wells qualify; PASS when a strict majority of the
    qualifying areas pass (by area COUNT, D48); no qualifying area = INCONCLUSIVE;
  * bench test (D48): all scored holdout wells of the bench pooled, same criteria;
  * BOX passes only if every area test and every bench test passes, oil AND gas (D49).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import tc_curve as tc

HORIZONS: tuple[int, ...] = (6, 12)
SCORED_STREAMS: tuple[str, ...] = ("oil", "gas")
BIAS_TOL = 0.10  # §8.1
MIN_AREA_WELLS = 10  # §8.3
PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"


# ----------------------------------------------------------------------------
# Prediction
# ----------------------------------------------------------------------------


def curve_months(curve: Mapping[str, Any], gor_target: float | None, n: int = 24) -> dict[str, np.ndarray]:
    """Per-1,000-ft monthly volumes (months 1..n) of an as-built area curve at the location's GOR target
    (D30 level x D46 factor): oil = the record (mean) Arps fit, D39 exact months; gas = the area ratio with
    alpha shifted so the curve's 12-mo GOR equals the target. NaN gas when the curve has no ratio or the
    target is missing."""
    oil_fit = curve["fits"]["oil"].get(curve["record"])
    if not oil_fit:
        raise ValueError("curve has no record oil fit")
    ov = tc.monthly_volumes(oil_fit)[:n]
    sh = tc.shift_gor_level(curve, gor_target) if gor_target and math.isfinite(gor_target) and gor_target > 0 else None
    gv = np.asarray(sh["gas_volumes"][:n], float) if sh else np.full(n, np.nan)
    return {"oil": np.asarray(ov, float), "gas": gv}


def curve_cums(curve: Mapping[str, Any], gor_target: float | None, horizons: Sequence[int] = HORIZONS) -> dict[str, float]:
    """Per-1,000-ft cums at each horizon of curve_months (oil + gas)."""
    m = curve_months(curve, gor_target, max(horizons))
    return {f"{s}{k}": float(m[s][:k].sum()) for s in SCORED_STREAMS for k in horizons}


def predict(cums_kft: Mapping[str, float], lateral_ft: float, ref_mult: float, f_oil: float,
            F: Mapping[str, Mapping[int, float]] | None = None, horizons: Sequence[int] = HORIZONS) -> dict[str, float]:
    """Well prediction from the curve's per-kft cums: x lateral / 1,000 x ref_mult x f_oil (both streams;
    gas already carries f_GOR through its level) x F(k) when given (D36)."""
    scale = float(lateral_ft) / 1000.0 * float(ref_mult) * float(f_oil)
    out = {}
    for s in SCORED_STREAMS:
        for k in horizons:
            f = 1.0 if F is None else float(F[s][k])
            out[f"{s}{k}"] = float(cums_kft[f"{s}{k}"]) * scale * f
    return out


def calendar_factor(actual: pd.DataFrame, pred: pd.DataFrame, horizons: Sequence[int] = HORIZONS) -> dict[str, dict[int, dict[str, float]]]:
    """D36: F(k) = Σ actual cum-k / Σ predicted cum-k (prediction WITHOUT F) over wells that have k full
    months, per stream. Rows align by index; a well enters a (stream, k) only when both are finite."""
    out: dict[str, dict[int, dict[str, float]]] = {}
    for s in SCORED_STREAMS:
        out[s] = {}
        for k in horizons:
            a, p = actual[f"{s}{k}"].astype(float), pred[f"{s}{k}"].astype(float)
            ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
            out[s][k] = {"F": float(a[ok].sum() / p[ok].sum()) if ok.any() else float("nan"), "n": int(ok.sum())}
    return out


def calendar_factor_curve(actual_months: np.ndarray, pred_months: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """D36 F(k) for every month k = 1..K: Σ actual cum-k / Σ predicted cum-k over the wells whose cum-k is
    known (actual_months [wells, K], NaN from the first month not yet reported; pred_months without F).
    Returns (F, n wells) per k. At k = 6 / 12 this is calendar_factor on the same wells."""
    a = np.asarray(actual_months, float)
    p = np.asarray(pred_months, float)
    ca, cp = np.cumsum(a, axis=1), np.cumsum(p, axis=1)  # NaN propagates: cum-k unknown once a month is missing
    ok = np.isfinite(ca) & np.isfinite(cp) & (cp > 0)
    num = np.where(ok, ca, 0.0).sum(axis=0)
    den = np.where(ok, cp, 0.0).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        F = np.where(den > 0, num / den, np.nan)
    return F, ok.sum(axis=0)


# ----------------------------------------------------------------------------
# Errors + statistics
# ----------------------------------------------------------------------------


def pct_error(actual: Any, predicted: Any) -> np.ndarray:
    """actual / predicted − 1 (sql/43 sign: + = forecast LOW); NaN where either is missing or predicted <= 0."""
    a, p = np.asarray(actual, float), np.asarray(predicted, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        e = a / p - 1.0
    e[~(np.isfinite(a) & np.isfinite(p) & (p > 0))] = np.nan
    return e


def stats(err: Sequence[float]) -> dict[str, float]:
    """n, bias (mean), median, P10 (HIGH = 90th pct), P90 (LOW = 10th pct), band = P10 − P90."""
    e = np.asarray(err, float)
    e = e[np.isfinite(e)]
    if not len(e):
        return {"n": 0, "bias": math.nan, "median": math.nan, "p10_high": math.nan, "p90_low": math.nan, "band": math.nan}
    hi, lo = np.percentile(e, [90, 10])
    return {"n": len(e), "bias": float(e.mean()), "median": float(np.median(e)), "p10_high": float(hi), "p90_low": float(lo), "band": float(hi - lo)}


def judge(box: Mapping[str, float], novi: Mapping[str, float], tol: float = BIAS_TOL) -> dict[str, Any]:
    """§8.1 + §8.2 on one group (same wells for both)."""
    if not box["n"] or not novi["n"]:
        return {"bias_ok": False, "band_ok": False, "pass": False}
    bias_ok = abs(box["bias"]) <= tol and abs(box["bias"]) < abs(novi["bias"])
    band_ok = box["band"] <= novi["band"]
    return {"bias_ok": bool(bias_ok), "band_ok": bool(band_ok), "pass": bool(bias_ok and band_ok)}


def score_groups(df: pd.DataFrame, by: str | None, stream: str, k: int) -> pd.DataFrame:
    """One row per group (or one 'bench' row when by is None): BOX and Novi stats on the wells where BOX
    and Novi both have an error at cum-k, plus the §8 judgement."""
    be, ne = f"box_err_{stream}{k}", f"novi_err_{stream}{k}"
    d = df[np.isfinite(df[be].astype(float)) & np.isfinite(df[ne].astype(float))]
    groups = [("bench", d)] if by is None else list(d.groupby(by))
    rows = []
    for g, x in groups:
        b, n = stats(x[be]), stats(x[ne])
        j = judge(b, n)
        rows.append({"group": g, "stream": stream, "horizon": k, "n": b["n"], **{f"box_{c}": v for c, v in b.items() if c != "n"},
                     **{f"novi_{c}": v for c, v in n.items() if c != "n"}, **j})
    return pd.DataFrame(rows)


def area_test(rows: pd.DataFrame, min_wells: int = MIN_AREA_WELLS) -> dict[str, Any]:
    """§8.3 by area COUNT (D48): strict majority of qualifying areas pass; none qualifying = INCONCLUSIVE."""
    q = rows[rows["n"] >= min_wells]
    n_q, n_p = len(q), int(q["pass"].sum()) if len(q) else 0
    verdict = INCONCLUSIVE if n_q == 0 else (PASS if n_p * 2 > n_q else FAIL)
    return {"n_qualifying": n_q, "n_pass": n_p, "qualifying": [int(a) for a in q["group"]], "verdict": verdict,
            "n_wells_qualifying": int(q["n"].sum()) if n_q else 0, "n_wells_thin": int(rows.loc[rows["n"] < min_wells, "n"].sum())}


def verdict(df: pd.DataFrame, area_col: str = "area_no") -> dict[str, Any]:
    """The full §8 + D48 + D49 verdict: per stream x horizon an area test and a bench test; overall PASS
    only when every cell passes; FAIL when any cell fails; else INCONCLUSIVE."""
    cells = []
    for s in SCORED_STREAMS:
        for k in HORIZONS:
            ar = score_groups(df, area_col, s, k)
            at = area_test(ar)
            bt = score_groups(df, None, s, k).iloc[0].to_dict()
            cells.append({"stream": s, "horizon": k, "area": at, "bench": {**bt, "verdict": PASS if bt["pass"] else FAIL}})
    states = [c["area"]["verdict"] for c in cells] + [c["bench"]["verdict"] for c in cells]
    overall = FAIL if FAIL in states else (INCONCLUSIVE if INCONCLUSIVE in states else PASS)
    by_stream = {s: (FAIL if FAIL in (st := [c[t]["verdict"] for c in cells if c["stream"] == s for t in ("area", "bench")])
                     else INCONCLUSIVE if INCONCLUSIVE in st else PASS) for s in SCORED_STREAMS}
    return {"overall": overall, "by_stream": by_stream, "cells": cells}
