"""BOX step 5b — baseline type curve per TC area per stream (pure; the math is boxfit's).

Plan §5 step 5b, D10, D15, D30. Every number here comes from the shared fitting engine
(`blueox-boxfit`, extracted from anduin in 5a) so a BOX curve is built exactly the way anduin builds a
saved type curve:

  1. each member well is fitted per stream by `boxfit.well.fit_well_streams` (own-peak anchoring,
     nominal Di bounds, water cap 12/yr, b prior, Delaware Df 0.08) — done by the caller;
  2. the panel is the members' ramp+Arps FORECASTS on a 600-month grid, peak_ramp aligned (each
     stream's peak slid to the cohort-median ramp length, `boxfit.tc.align`), per 1,000 ft of lateral;
  3. `boxfit.tc.aggregate` takes the cross-well percentiles (SPE: P10 = HIGH) and the MEAN per month;
  4. `boxfit.tc.fit_p50.fit_p50_series` fits ramp + modified-hyperbolic Arps to a chosen series
     (anduin fits every percentile and the mean this way; only the name says P50);
  5. gas = ratio mode (D30): ln(GOR) = alpha + beta * Np fitted on the cohort MEAN gas / oil series vs
     cumulative mean oil (`boxfit.tc.ratio_mode.build_ratio_fitted`), applied to the oil curve of
     record. The area supplies the shape (beta); a location's local GOR level shifts alpha
     (`shift_gor_level`).

Curve of record = the cohort MEAN series (labelled "mean", never P50). Reason: the step-6 acceptance
metric is the mean per-well error (actual / predicted - 1, sql/43 convention), and only the mean
curve predicts the cohort's mean cum without a built-in skew bias; the P50 fit is kept alongside.
Plan §9 left this to 5b; Michael confirms at gate 5.

Relaxation ladder (D10 as amended by D37), fixed and stamped per curve: (1) strict -> (2) relax lateral
-> (4) borrow neighbouring areas -> (5) transfer from the parent bench. Rung 3 (relax vintage) is
RETIRED (D37: pre-2016 wells are never curve evidence, D26); the numbers stay stable so a stamp means
the same thing in every version, and a pool stamped 3 is refused. The caller supplies the pools;
`climb` takes the first rung holding >= min_wells fitted wells for the stream.
"""

from __future__ import annotations

import functools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from boxfit.eur import DAYS_PER_YEAR
from boxfit.ramp_arps import build_ramp_arps_rate, model_cum_at_t, trapezoid_eur
from boxfit.tc.aggregate import TypeCurveAggregate, WellSeries, aggregate
from boxfit.tc.align import forecast_rates, peak_ramp_shift, ramp_anchor
from boxfit.tc.fit_p50 import fit_p50_series
from boxfit.tc.ratio_mode import build_ratio_fitted

STREAMS: tuple[str, ...] = ("oil", "gas", "water")
N_MONTHS = 600  # anduin _FORECAST_N_MONTHS: the 50-yr panel and the trapezoid_eur grid
DAYS_PER_MONTH = DAYS_PER_YEAR / 12.0  # the fit + trapezoid_eur month length
RECORD_STAT = "mean"  # curve of record (see module docstring); "p50" is fitted alongside
STATS: tuple[str, ...] = ("mean", "p50")
MIN_WELLS = 10  # D9 floor, reused as the curve floor per stream
RECONCILE_TOL = 0.001  # stored (closed form) vs the sum of BOX's monthly volumes, rule 6 (D39: exact months)

LADDER: tuple[tuple[int, str], ...] = (
    (1, "strict"),
    (2, "relax_lateral"),
    (4, "borrow_neighbour"),
    (5, "parent_bench"),
)
RUNG_LABEL = dict(LADDER)
RETIRED_RUNGS = {3: "relax_vintage (retired, D37)"}


@dataclass(frozen=True)
class Member:
    """One well's contribution: lateral (ft) and per-stream fitted params (None = no fit)."""

    api10: str
    lateral_ft: float | None
    params: Mapping[str, Mapping[str, Any] | None]
    # calendar-day rates by stream from the well's first reported month (observed overlay only)
    rates: Mapping[str, Sequence[float]] = field(default_factory=dict)


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------


def effective_decline(di_nominal: float | None, b: float | None) -> float | None:
    """1-yr effective (secant) decline from qi for a hyperbolic: 1 - (1 + b * Di)^(-1/b); b -> 0 is
    exponential 1 - exp(-Di). Di is NOMINAL per year (rule 1)."""
    if di_nominal is None or b is None or not math.isfinite(di_nominal) or not math.isfinite(b):
        return None
    if b < 1e-6:
        return 1.0 - math.exp(-di_nominal)
    return 1.0 - (1.0 + b * di_nominal) ** (-1.0 / b)


def cum_months(rates: Sequence[float | None], months: int) -> float:
    """Volume over the first `months` months of a point-sampled monthly grid (rates[i] = q(t = i mo)),
    trapezoid rule — the same rule as boxfit.ramp_arps.trapezoid_eur, truncated."""
    r = [0.0 if v is None or not math.isfinite(float(v)) else float(v) for v in rates[: months + 1]]
    if not r:
        return 0.0
    if len(r) <= months:
        r = r + [r[-1]] * (months + 1 - len(r))
    return float(sum((r[i] + r[i + 1]) / 2.0 for i in range(months)) * DAYS_PER_MONTH)


def oil_grid(fit: Mapping[str, Any], n_months: int = N_MONTHS) -> list[float]:
    """The ramp + Arps rate grid of a fit_p50_series result (the curve you see / export)."""
    return build_ramp_arps_rate(
        n_months=n_months, qo=fit["qo"], qi=fit["qi"], peak_index=int(fit["peak_index"]), Di=fit["Di"], b=fit["b"], Df=fit["Df"]
    )


def monthly_volumes(fit: Mapping[str, Any], n_months: int = N_MONTHS) -> np.ndarray:
    """D39: each month's volume as the EXACT integral of the fit's own ramp + Arps model,
    Cum(k/12) - Cum((k-1)/12) from boxfit's closed form (model_cum_at_t). Every BOX monthly number
    (Steven's D16 table, cum-k, the step-6 predictions, F(k)) comes from here, so the monthly rows
    sum to the stored EUR. The 600-month trapezoid (anduin's display convention) overstates a convex
    curve in months 2-12 (cum-12 +0.3 % on oil, up to +1.3 % on steep water)."""
    key = (float(fit["qo"]), int(fit["peak_index"]), float(fit["qi"]), float(fit["Di"]), float(fit["b"]), float(fit["Df"]), int(n_months))
    return np.array(_exact_months(key))


@functools.lru_cache(maxsize=4096)
def _exact_months(key: tuple[float, int, float, float, float, float, int]) -> tuple[float, ...]:
    """Cached core of monthly_volumes (~1.7 s per fit: boxfit's closed form runs per month; the same
    fit is integrated by the curve row, the gas ratio and the GOR shift)."""
    qo, pim, qi, di, b, df, n = key
    cum = [model_cum_at_t(qo=qo, peak_index_months=pim, qi=qi, Di=di, b=b, Df=df, t_years=k / 12.0) for k in range(n + 1)]
    return tuple(float(x) for x in np.diff(cum))


def ratio_monthly_volumes(oil_volumes: Sequence[float], alpha: float, beta: float) -> np.ndarray:
    """Ratio-mode gas month by month on exact oil months: the ratio at the month's mid-point Np x the
    month's oil volume (boxfit.ratio.derive_ratio_stream's rule, on D39's oil volumes)."""
    v = np.maximum(np.asarray(oil_volumes, dtype=float), 0.0)
    np_mid = np.concatenate(([0.0], np.cumsum(v)[:-1])) + v / 2.0
    return np.exp(alpha + beta * np_mid) * v


def reconcile(fit: Mapping[str, Any] | None, n_months: int = N_MONTHS) -> float | None:
    """Rule 6: the sum of BOX's monthly volumes (D39, exact per month) vs the stored EUR (closed form /
    quad ramp + Arps). Must stay < 0.1 %."""
    if not fit:
        return None
    stored = float(fit["eur_per_unit"])
    if stored <= 0:
        return None
    return float(monthly_volumes(fit, n_months).sum()) / stored - 1.0


def trapezoid_gap(fit: Mapping[str, Any] | None, n_months: int = N_MONTHS) -> float | None:
    """Diagnostic: the 600-month trapezoid (anduin's display / export rule) vs the stored EUR."""
    if not fit or float(fit["eur_per_unit"]) <= 0:
        return None
    return trapezoid_eur(oil_grid(fit, n_months)) / float(fit["eur_per_unit"]) - 1.0


# ----------------------------------------------------------------------------
# Panels
# ----------------------------------------------------------------------------


def anchors_for(members: Sequence[Member]) -> dict[str, int]:
    """peak_ramp anchors: per stream, the rounded median ramp length of the members that carry a fit
    for it (no ramp counts as 0) — anduin's cohort_ramp_anchors."""
    return {s: ramp_anchor(int((m.params.get(s) or {}).get("peak_index_months") or 0) for m in members if m.params.get(s)) for s in STREAMS}


def forecast_panel(members: Sequence[Member], anchors: Mapping[str, int], n_months: int = N_MONTHS) -> list[WellSeries]:
    """Per-well forecast rate arrays on the aligned panel (anduin load_wells_with_forecast, peak_ramp)."""
    out = []
    for m in members:
        rates = {}
        for s in STREAMS:
            p = m.params.get(s)
            rates[s] = forecast_rates(p, n_months, include_ramp=True, shift_months=peak_ramp_shift(p, s, anchors))
        out.append(WellSeries(api10=m.api10, lateral_ft=m.lateral_ft, proppant_lbs=None, oil_rates=rates["oil"], gas_rates=rates["gas"], water_rates=rates["water"]))
    return out


def observed_panel(members: Sequence[Member], anchors: Mapping[str, int], n_months: int = 240) -> list[WellSeries]:
    """Observed calendar-day rates on the SAME aligned panel as the forecasts (the QC overlay): a
    stream's forecast t = 0 is its onset month, so observed month k sits at panel month
    k - onset + (anchor - peak_index_months)."""
    out = []
    for m in members:
        rates = {}
        for s in STREAMS:
            p, obs = m.params.get(s), list(m.rates.get(s) or [])
            if not p or not obs:
                rates[s] = [None] * n_months
                continue
            onset = int(p.get("onset_index_months") or 0)
            shift = peak_ramp_shift(p, s, anchors)
            seq = obs[onset:]
            seq = [None] * shift + seq if shift >= 0 else seq[-shift:]
            rates[s] = (seq + [None] * n_months)[:n_months]
        out.append(WellSeries(api10=m.api10, lateral_ft=m.lateral_ft, proppant_lbs=None, oil_rates=rates["oil"], gas_rates=rates["gas"], water_rates=rates["water"]))
    return out


def n_fitted(members: Sequence[Member], stream: str) -> int:
    return sum(1 for m in members if m.params.get(stream) and (m.lateral_ft or 0) > 0)


# ----------------------------------------------------------------------------
# Curve
# ----------------------------------------------------------------------------


def fit_curve(members: Sequence[Member], *, df_terminal: float = 0.08, n_months: int = N_MONTHS, stats: Sequence[str] = STATS,
              record: str = RECORD_STAT) -> dict[str, Any]:
    """One type curve from a member list: aggregate, fit each requested statistic per stream, gas
    ratio mode on the record oil fit. Returns plain dicts (fits as fit_p50_series returns them)."""
    anchors = anchors_for(members)
    agg = aggregate(forecast_panel(members, anchors, n_months), normalization_basis="per_lateral_ft", alignment_method="peak_ramp", n_months=n_months)
    fits: dict[str, dict[str, Any]] = {}
    for s in STREAMS:
        st = agg.streams[s]
        fits[s] = {k: fit_p50_series(getattr(st, k), df_terminal_per_year=df_terminal, stream=s) for k in stats}  # own Di cap, D38
    oil_rec = fits["oil"].get(record)
    gas_ratio = None
    if oil_rec:
        gas_ratio = build_ratio_fitted(mean_oil=agg.streams["oil"].mean, mean_stream=agg.streams["gas"].mean, oil_fitted=oil_rec, n_months=n_months)
    return {"n_wells": agg.n_wells, "n_by_stream": {s: n_fitted(members, s) for s in STREAMS}, "anchors": anchors, "agg": agg, "fits": fits,
            "gas_ratio": gas_ratio, "record": record, "df_terminal": df_terminal}


def record_rates(curve: Mapping[str, Any], stream: str, n_months: int = N_MONTHS) -> list[float] | None:
    """The record curve's monthly rate grid per 1,000 ft: oil / water Arps, gas = ratio x oil."""
    if stream == "gas":
        g = curve.get("gas_ratio")
        return list(g["smoothed_rate"]) if g else None
    f = curve["fits"][stream].get(curve["record"])
    return oil_grid(f, n_months) if f else None


def curve_row(curve: Mapping[str, Any], stream: str, stat: str) -> dict[str, Any]:
    """Flat summary of one (stream, statistic) fit: params, nominal + effective Di, EUR per 1,000 ft,
    reconcile gap, cum-6/12/24 per 1,000 ft."""
    f = curve["fits"][stream].get(stat)
    row: dict[str, Any] = {"stream": stream, "stat": stat, "mode": "arps", "n_wells": curve["n_by_stream"][stream]}
    if not f:
        return {**row, "fit_ok": False}
    vol = monthly_volumes(f)
    row.update({"fit_ok": True, "qo": f["qo"], "qi": f["qi"], "peak_index": int(f["peak_index"]), "Di_nominal": f["Di"], "Di_eff_1yr": effective_decline(f["Di"], f["b"]),
                "b": f["b"], "Df": f["Df"], "eur_per_kft": f["eur_per_unit"], "r2": f["r2"], "reconcile": float(vol.sum()) / float(f["eur_per_unit"]) - 1.0,
                "trapezoid_gap": trapezoid_gap(f), "cum6_kft": float(vol[:6].sum()), "cum12_kft": float(vol[:12].sum()), "cum24_kft": float(vol[:24].sum())})
    return row


def gas_ratio_row(curve: Mapping[str, Any]) -> dict[str, Any]:
    g = curve.get("gas_ratio")
    row: dict[str, Any] = {"stream": "gas", "stat": curve["record"], "mode": "ratio", "n_wells": curve["n_by_stream"]["gas"]}
    if not g:
        return {**row, "fit_ok": False}
    ov = monthly_volumes(curve["fits"]["oil"][curve["record"]])
    gv = ratio_monthly_volumes(ov, float(g["alpha"]), float(g["beta"]))
    row.update({"fit_ok": True, "alpha": g["alpha"], "beta": g["beta"], "sub_mode": g["sub_mode"], "r2": g["r2"], "eur_per_kft": float(gv.sum()),
                "eur_per_kft_trapezoid": g["eur_per_unit"], "Di_eff_1yr": g["implied_effective_decline_yr1"],
                "cum6_kft": float(gv[:6].sum()), "cum12_kft": float(gv[:12].sum()), "cum24_kft": float(gv[:24].sum()),
                "gor12_scf_bbl": window_gor(ov, gv, 12), "gor24_scf_bbl": window_gor(ov, gv, 24)})
    return row


# ----------------------------------------------------------------------------
# Gas level (D30)
# ----------------------------------------------------------------------------


def window_gor(oil_volumes: Sequence[float], gas_volumes: Sequence[float], months: int) -> float | None:
    """Cum gas / cum oil over the first `months` months, scf/bbl (monthly volumes, bbl / mcf)."""
    o = float(np.sum(oil_volumes[:months]))
    return None if o <= 0 else 1000.0 * float(np.sum(gas_volumes[:months])) / o


def shift_gor_level(curve: Mapping[str, Any], target_gor12_scf_bbl: float, n_months: int = N_MONTHS) -> dict[str, Any] | None:
    """D30: keep the area's ratio SHAPE (beta), move its LEVEL (alpha) so the curve's 12-mo GOR equals
    the location's local 12-mo GOR. ln R = alpha + beta * Np, so alpha + ln(target / tc_gor12) scales
    the ratio — and the 12-mo GOR — by exactly target / tc_gor12 at every Np. Np stays per 1,000 ft:
    a PUD's rates are the curve x lateral / 1,000, so its ratio vs time is the curve's (the Np rescale
    to the PUD lateral cancels). Returns the shifted params, the shifted gas monthly volumes (D39)
    and their EUR."""
    g = curve.get("gas_ratio")
    oil_fit = curve["fits"]["oil"].get(curve["record"])
    if not g or not oil_fit or not (target_gor12_scf_bbl and target_gor12_scf_bbl > 0):
        return None
    ov = monthly_volumes(oil_fit, n_months)
    tc12 = window_gor(ov, ratio_monthly_volumes(ov, float(g["alpha"]), float(g["beta"])), 12)
    if not tc12:
        return None
    alpha = float(g["alpha"]) + math.log(target_gor12_scf_bbl / tc12)
    gv = ratio_monthly_volumes(ov, alpha, float(g["beta"]))
    return {"alpha": alpha, "beta": float(g["beta"]), "alpha_shift": alpha - float(g["alpha"]), "tc_gor12": tc12, "target_gor12": target_gor12_scf_bbl,
            "gas_volumes": gv, "eur_per_kft": float(gv.sum()), "gor12_check": window_gor(ov, gv, 12)}


# ----------------------------------------------------------------------------
# Relaxation ladder (D10)
# ----------------------------------------------------------------------------


def climb(pools: Sequence[tuple[int, Sequence[Member]]], stream: str, min_wells: int = MIN_WELLS) -> tuple[int, Sequence[Member], bool]:
    """First rung (in the fixed D10 order the caller passes) holding >= min_wells fitted wells for
    the stream. Returns (rung, members, thin): when no rung qualifies the LAST rung is returned with
    thin = True (never silently a short curve that looks like a full one)."""
    if not pools:
        raise ValueError("no pools")
    rungs = [r for r, _ in pools]
    if rungs != sorted(rungs) or len(set(rungs)) != len(rungs) or any(r not in RUNG_LABEL for r in rungs):
        raise ValueError(f"pools must follow the D10 ladder order (rung 3 retired, D37), got rungs {rungs}")
    for rung, mem in pools:
        if n_fitted(mem, stream) >= min_wells:
            return rung, mem, False
    return pools[-1][0], pools[-1][1], True


# ----------------------------------------------------------------------------
# Statistics for the gate questions
# ----------------------------------------------------------------------------


def within_slope(y: Sequence[float], x: Sequence[float], group: Sequence[Any]) -> dict[str, float] | None:
    """OLS slope of y on x with group fixed effects (both demeaned within group); classical SE.
    Answers 'does y move with x inside an area', free of between-area differences."""
    ya, xa, ga = np.asarray(y, float), np.asarray(x, float), np.asarray(group)
    ok = np.isfinite(ya) & np.isfinite(xa)
    ya, xa, ga = ya[ok], xa[ok], ga[ok]
    if len(ya) < 3:
        return None
    yd, xd = ya.copy(), xa.copy()
    groups = np.unique(ga)
    for g in groups:
        k = ga == g
        yd[k] -= ya[k].mean()
        xd[k] -= xa[k].mean()
    sxx = float((xd * xd).sum())
    dof = len(ya) - len(groups) - 1
    if sxx <= 0 or dof < 1:
        return None
    slope = float((xd * yd).sum() / sxx)
    resid = yd - slope * xd
    se = math.sqrt(float((resid * resid).sum()) / dof / sxx)
    return {"slope": slope, "se": se, "t": slope / se if se > 0 else float("inf"), "n": len(ya), "n_groups": len(groups),
            "x_iqr": float(np.subtract(*np.percentile(xa, [75, 25])))}


def aggregate_only(members: Sequence[Member], n_months: int = N_MONTHS) -> TypeCurveAggregate:
    a = anchors_for(members)
    return aggregate(forecast_panel(members, a, n_months), normalization_basis="per_lateral_ft", alignment_method="peak_ramp", n_months=n_months)
