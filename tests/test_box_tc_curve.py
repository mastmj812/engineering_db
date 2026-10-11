"""BOX step 5b — DB-free tests for the curve math (box/tc_curve.py) and the report's pure helpers."""

from __future__ import annotations

import datetime as dt
import math

import numpy as np
import pandas as pd
import pytest
from boxfit.ramp_arps import build_ramp_arps_rate, trapezoid_eur

from box import tc_curve as tc
from box import tc_curve_report as rep

OIL = {"qi": 1500.0, "Di": 2.5, "b": 1.05, "Df": 0.08, "qo": 700.0, "peak_index_months": 2}
GAS = {"qi": 3000.0, "Di": 1.8, "b": 1.1, "Df": 0.08, "qo": 1200.0, "peak_index_months": 3}
WAT = {"qi": 4000.0, "Di": 3.5, "b": 1.0, "Df": 0.08, "qo": 3000.0, "peak_index_months": 1}


def _member(i: int, scale: float = 1.0, lateral: float = 10_000.0) -> tc.Member:
    sc = lambda p: {**p, "qi": p["qi"] * scale, "qo": p["qo"] * scale}
    return tc.Member(api10=f"42{i:08d}", lateral_ft=lateral, params={"oil": sc(OIL), "gas": sc(GAS), "water": sc(WAT)})


def _grid(p: dict, n: int = tc.N_MONTHS) -> list[float]:
    return build_ramp_arps_rate(n_months=n, qo=p["qo"], qi=p["qi"], peak_index=p["peak_index_months"], Di=p["Di"], b=p["b"], Df=p["Df"])


def test_effective_decline() -> None:
    assert tc.effective_decline(2.0, 1.0) == pytest.approx(1 - 1 / 3)
    assert tc.effective_decline(1.0, 0.0) == pytest.approx(1 - math.exp(-1.0))
    # Permian nominal 3/yr at b = 1.1 is ~ 70 % effective year one (rule 1's talking point)
    assert 0.65 < tc.effective_decline(3.0, 1.1) < 0.75
    assert tc.effective_decline(None, 1.0) is None


def test_cum_months_is_truncated_trapezoid() -> None:
    r = list(np.linspace(100, 10, 50))
    assert tc.cum_months(r, 49) + r[-1] * tc.DAYS_PER_MONTH == pytest.approx(trapezoid_eur(r))
    assert tc.cum_months([10.0, 10.0], 12) == pytest.approx(10.0 * 12 * tc.DAYS_PER_MONTH)


def test_identical_wells_recover_the_well_curve_per_kft() -> None:
    curve = tc.fit_curve([_member(i) for i in range(12)])
    assert curve["n_wells"] == 12 and curve["anchors"] == {"oil": 2, "gas": 3, "water": 1}
    want = trapezoid_eur(_grid(OIL)) / 10.0  # per 1,000 ft of a 10,000-ft lateral
    row = tc.curve_row(curve, "oil", "mean")
    assert row["eur_per_kft"] == pytest.approx(want, rel=0.01)
    assert abs(row["reconcile"]) < tc.RECONCILE_TOL
    assert row["Di_eff_1yr"] == pytest.approx(tc.effective_decline(row["Di_nominal"], row["b"]))
    # mean and P50 coincide when every well is the same
    assert tc.curve_row(curve, "oil", "p50")["eur_per_kft"] == pytest.approx(row["eur_per_kft"], rel=1e-9)


def test_mean_exceeds_p50_on_a_skewed_cohort() -> None:
    rng = np.random.default_rng(5)
    mem = [_member(i, float(s)) for i, s in enumerate(rng.lognormal(0.0, 0.5, 40))]
    curve = tc.fit_curve(mem)
    assert tc.curve_row(curve, "oil", "mean")["eur_per_kft"] > 1.05 * tc.curve_row(curve, "oil", "p50")["eur_per_kft"]


def test_gas_ratio_and_level_shift_keep_shape_move_level() -> None:
    curve = tc.fit_curve([_member(i) for i in range(12)])
    g = curve["gas_ratio"]
    assert g is not None and g["mode"] == "ratio"
    row = tc.gas_ratio_row(curve)
    assert row["fit_ok"] and row["mode"] == "ratio"
    tc12 = row["gor12_scf_bbl"]
    sh = tc.shift_gor_level(curve, 2.0 * tc12)
    assert sh["gor12_check"] == pytest.approx(2.0 * tc12, rel=1e-9)
    assert sh["beta"] == g["beta"]
    assert sh["alpha_shift"] == pytest.approx(math.log(2.0))
    # the ratio scales by exactly 2 at every month, so the gas EUR doubles
    assert sh["eur_per_kft"] == pytest.approx(2.0 * g["eur_per_unit"], rel=1e-9)
    assert tc.shift_gor_level(curve, 0.0) is None


def test_climb_follows_the_ladder_and_flags_thin() -> None:
    few = [_member(i) for i in range(4)]
    many = [_member(i) for i in range(12)]
    rung, mem, thin = tc.climb([(1, few), (2, few), (4, many), (5, many)], "oil")
    assert (rung, len(mem), thin) == (4, 12, False)
    rung, mem, thin = tc.climb([(1, few), (5, few)], "oil")
    assert (rung, thin) == (5, True)
    with pytest.raises(ValueError):
        tc.climb([(4, many), (1, many)], "oil")
    # a well without a stream fit does not count toward that stream
    nogas = [tc.Member(api10=m.api10, lateral_ft=m.lateral_ft, params={**m.params, "gas": None}) for m in many]
    assert tc.climb([(1, nogas), (5, many)], "gas")[0] == 5


def test_within_slope_removes_group_levels() -> None:
    rng = np.random.default_rng(1)
    g = np.repeat(np.arange(8), 30)
    x = rng.normal(size=g.size) + g  # x correlated with the group
    y = 5.0 * g + 0.5 * x + rng.normal(scale=0.1, size=g.size)
    r = tc.within_slope(y, x, g)
    assert r["slope"] == pytest.approx(0.5, abs=0.02) and r["n_groups"] == 8


def test_observed_panel_uses_the_forecast_alignment() -> None:
    p = {**OIL, "peak_index_months": 2, "onset_index_months": 1}
    m = tc.Member(api10="1", lateral_ft=1000.0, params={"oil": p, "gas": None, "water": None}, rates={"oil": [0.0, 5.0, 8.0, 10.0, 9.0]})
    late = tc.observed_panel([m], {"oil": 3}, 6)[0].oil_rates  # shift +1: onset month lands on panel 1
    assert late[:5] == [None, 5.0, 8.0, 10.0, 9.0]
    early = tc.observed_panel([m], {"oil": 1}, 6)[0].oil_rates  # shift -1: first onset month drops off
    assert early[:3] == [8.0, 10.0, 9.0]


def test_last_full_month_stops_at_the_reporting_lag() -> None:
    c = [(dt.date(2026, m, 1), n) for m, n in ((5, 60_000), (6, 58_000), (7, 63_500), (8, 34_000), (9, 3_300))]
    assert rep.last_full_month(c) == dt.date(2026, 7, 1)


def test_sub_bench_views() -> None:
    df = pd.DataFrame({
        "formation_blueox": ["WCA_1", "WCA_2", "WCXY", "WCB_1", "WCA_1", "WCXY"],
        "cons_suggest": [None, "WCA_1", None, "WCA_2", "WCXY", "WCA_2"],
        "cons_status": ["agree", "flag", "agree", "flag", "flag", "flag"],
        "box_action": ["keep", "keep", "keep", "reassign", "keep", "keep"],
    })
    assert list(rep.sub_bench(df, "tag")) == ["WCA_1", "WCA_2", "WCA_1", "WCA_2", "WCA_1", "WCA_1"]
    # consensus flips the in-pool swap; a WCXY suggestion is moot (D20)
    assert list(rep.sub_bench(df, "consensus")) == ["WCA_1", "WCA_1", "WCA_1", "WCA_2", "WCA_1", "WCA_2"]


def test_actuals_windows_and_gor() -> None:
    dates = [dt.date(2025, 1, 1) + pd.DateOffset(months=k) for k in range(14)]
    prod = pd.DataFrame({"api10": "1", "prod_date": [d.date() for d in dates], "oil_bbl": 100.0, "gas_mcf": 200.0, "water_bbl": 50.0,
                         "producing_days": 30, "rate_calday_bopd": 3.0, "rate_calday_mcfd": 6.0, "rate_calday_bwpd": 1.5})
    a = rep.actuals(prod, dt.date(2026, 2, 1)).iloc[0]
    assert a["months"] == 14 and a["oil12"] == pytest.approx(1200.0) and math.isnan(a["oil24"])
    assert a["gor12"] == pytest.approx(2000.0)


def test_at_bound_uses_the_stream_cap() -> None:
    assert rep.at_bound("oil", {"Di": 4.0, "b": 1.0}, 12.0)["di_at_bound"]
    assert not rep.at_bound("water", {"Di": 4.0, "b": 1.0}, 12.0)["di_at_bound"]
    assert rep.at_bound("water", {"Di": 12.0, "b": 0.9}, 12.0) == {"di_at_bound": True, "b_at_bound": True}
