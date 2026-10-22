"""box/cohort_review — binding-rule buckets and the far-with-local-control class on a synthetic pool (DB-free)."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import cohort_review as cr
from dealintake import config as di_config

MI = 5280.0


def _pool() -> dict:
    # (x mi, lateral ft, months, spacing ft, oil12/kft) — PUD at the origin, 7,720 ft, planned spacing 1,000 ft
    rows = [
        (1.5, 10_000.0, 16, 1_100.0, 20_000.0),   # lateral only (above 9,650)
        (1.8, 10_100.0, 16, 1_100.0, 22_000.0),   # lateral only
        (2.0, 12_500.0, 16, 2_800.0, 18_000.0),   # lateral + standalone sentinel -> multiple
        (2.5, 8_000.0, 4, 1_100.0, np.nan),       # months only (< 6), not local (< 12 months)
        (2.8, 8_000.0, 30, 400.0, 21_000.0),      # spacing tight only (< 0.65 x 1,000)
        (15.0, 7_800.0, 40, 1_000.0, 30_000.0),   # far analogs (record cohort)
        (16.0, 7_700.0, 40, 1_000.0, 28_000.0),
        (17.0, 7_600.0, 40, 1_000.0, 29_000.0),
    ]
    a = np.array(rows, dtype=float)
    return {"api10": np.array([f"30025{i:05d}" for i in range(len(rows))]), "x": a[:, 0] * MI, "y": np.zeros(len(rows)),
            "fp": [dt.date(2022, 1, 1)] * len(rows), "lateral": a[:, 1], "months": a[:, 2], "spacing": a[:, 3], "oil12_kft": a[:, 4]}


def _loc() -> dict:
    return {"api10": "pud1", "stick_id": 1, "x": 0.0, "y": 0.0, "lateral_ft": 7_720.0, "lateral_eff": 7_720.0, "spacing_ft": 1_000.0}


def _res(radius: float) -> dict:
    return {"radius_mi": radius, "search_mode": "circle", "analogs": [{"api10": f"30025{i:05d}"} for i in (5, 6, 7)]}


def test_reason_buckets():
    assert cr.bucket(cr.reason_set(None)) == "eligible"
    assert cr.bucket(cr.reason_set("lateral_outside_5790-9650")) == "lateral"
    assert cr.bucket(cr.reason_set("lateral_outside_5790-9650;spacing_standalone")) == "multiple"
    assert cr.reason_set("months<6;first_prod<2016-01-01") == {"months", "first_prod"}


def test_lateral_band_matches_box_v2():
    assert cr.lateral_band(5_080.0) == (7_500.0, 12_500.0)  # short completed lateral -> SHORT_BAND_FT (Cui-translated)
    assert cr.lateral_band(7_720.0) is None  # classify's +/-25 % Delaware tolerance


def test_pud_row_names_binding_rules_and_flags_far_with_local():
    p = _pool()
    r = cr.pud_row(_loc(), _res(20.0), p, cKDTree(np.column_stack([p["x"], p["y"]])), di_config.load(), "BS1_S")
    assert r["near_pool"] == 5 and r["near_eligible"] == 0
    assert (r["near_lateral"], r["near_multiple"], r["near_months"], r["near_spacing_tight"]) == (2, 1, 1, 1)
    assert (r["near_any_lateral"], r["near_any_spacing_standalone"], r["near_any_months"]) == (3, 1, 1)
    assert (r["rescue_lateral"], r["rescue_spacing"], r["rescue_lateral_spacing"], r["rescue_months"]) == (2, 1, 4, 1)
    assert r["n_local"] == 4  # >= 12 months with a known year-1; the 4-month well is not local evidence
    assert r["far_with_local"]
    assert abs(r["cohort_y1_kft"] - 29_000.0) < 1e-9 and abs(r["local_y1_kft"] - 20_250.0) < 1e-9
    assert abs(r["gap_cohort_vs_local"] - (29_000.0 / 20_250.0 - 1)) < 1e-12
    assert abs(r["analog_dist_med_mi"] - 16.0) < 1e-9


def test_close_record_is_not_flagged():
    p = _pool()
    r = cr.pud_row(_loc(), _res(5.0), p, cKDTree(np.column_stack([p["x"], p["y"]])), di_config.load(), "BS1_S")
    assert not r["far_with_local"]


def test_lateral_class_and_summary():
    assert list(cr.lateral_class_mi(pd.Series([5_080, 7_720, 10_360, 13_000, 15_640]))) == [1.0, 1.5, 2.0, 2.5, 3.0]
    d = pd.DataFrame({"group": ["G"] * 4, "tier": ["provisional"] * 4, "stick_id": range(4), "lateral_ft": [7_720.0] * 4,
                      "radius_mi": [5.0, 7.5, 20.0, 20.0], "far_with_local": [False, False, True, False],
                      "gap_cohort_vs_local": [np.nan, np.nan, 0.4, np.nan],
                      **{f"near_{k}": [0, 0, 3, 0] if k == "lateral" else [0] * 4 for k in (*cr.REASONS, "multiple")},
                      **{f"near_any_{k}": [0, 0, 3, 0] if k == "lateral" else [0] * 4 for k in cr.REASONS},
                      **{f"rescue_{k}": [0, 0, 3, 0] if k in ("lateral", "lateral_spacing") else [0] * 4 for k in cr.RESCUE}})
    s = cr.summarize(d).iloc[0]
    assert s["far_with_local"] == 1 and s["pct_5mi"] == 25.0 and s["pct_15plus"] == 50.0
    assert abs(s["gap_med_pct"] - 40.0) < 1e-9 and s["fails_lateral"] == 100.0 and s["rescued_by_lateral"] == 100.0 and s["rescued_by_months"] == 0.0


def test_measured_spacing_reselection_closes_in_first_ring():
    # 10 near wells whose pool spacing is NaN (the build only fetched spacing for the F(k) training cohort) + 3 far wells with a
    # measured spacing: the record reaches 20 mi with the 3 far wells; with measured spacing the 10 near wells close the 5-mi ring
    n_near, far_x = 10, (15.0, 16.0, 17.0)
    x = np.r_[np.linspace(1.0, 2.0, n_near), far_x] * MI
    k = len(x)
    p = {"api10": np.array([f"42301{i:05d}" for i in range(k)]), "x": x, "y": np.zeros(k), "fp": [dt.date(2022, 1, 1)] * k,
         "lateral": np.full(k, 10_000.0), "months": np.full(k, 30.0), "spacing": np.r_[np.full(n_near, np.nan), np.full(3, 1_000.0)],
         "oil12_kft": np.r_[np.full(n_near, 20_000.0), np.full(3, 30_000.0)], "tvd": np.full(k, 10_000.0),
         "params": {}}
    fix = {**p, "spacing": np.full(k, 1_000.0)}
    tree = cKDTree(np.column_stack([p["x"], p["y"]]))
    loc = {**_loc(), "lateral_ft": 10_360.0, "lateral_eff": 10_360.0}
    res = {"radius_mi": 20.0, "search_mode": "circle", "analogs": [{"api10": a} for a in p["api10"][n_near:]]}
    r = cr.pud_row(loc, res, p, tree, di_config.load(), "BS1_S", pool_fix=fix)
    assert r["repro_ok"]
    assert r["near_spacing_standalone"] == n_near and r["far_with_local"]
    assert (r["fix_radius_mi"], r["fix_n"], r["fix_overlap"]) == (5.0, n_near, 0)
    assert abs(r["fix_gap_vs_local"]) < 1e-12 and abs(r["gap_cohort_vs_local"] - 0.5) < 1e-12
