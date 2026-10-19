"""BOX step 11 water — pure pieces (labels as of a date, the amended NM rule, fallback choice, ratio water)."""

import datetime as dt

import numpy as np
import pandas as pd

from box import tc_curve as tc
from box import water11 as w


def test_sql41_label_order():
    assert w.sql41_label(5, 1.0, 0.5) == "insufficient"
    assert w.sql41_label(12, 0.95, 0.0) == "measured"  # operator share first
    assert w.sql41_label(12, 0.0, 0.01) == "calculated"
    assert w.sql41_label(12, 0.0, 0.2) == "measured"
    assert w.sql41_label(12, 0.0, 0.1) == "indeterminate"
    assert w.sql41_label(12, 0.5, 0.01) == "indeterminate"  # not public enough to call calculated


def test_amended_nm_rule_and_vdr():
    # NM: anything but insufficient is measured (amendment 2026-10-19); TX keeps sql/41
    assert w.water_label("30", 12, 0.0, 0.03) == "measured"
    assert w.water_label("30", 12, 0.0, 0.10) == "measured"
    assert w.water_label("30", 4, 0.0, 0.40) == "insufficient"
    assert w.water_label("42", 12, 0.0, 0.03) == "calculated"
    assert w.water_label("42", 12, 0.0, 0.10) == "indeterminate"
    assert w.water_label("42", 12, 0.0, 0.03, vdr_months=6) == "measured"
    assert w.water_label("42", 12, 0.0, 0.03, vdr_months=5) == "calculated"


def test_labels_asof_reads_only_through_asof():
    d0 = dt.date(2020, 1, 1)
    rows = []
    for i in range(12):
        d = dt.date(2020 + (i // 12), 1 + i % 12, 1)
        rows.append({"api10": "A", "prod_date": d, "oil": 1000.0, "water": 2000.0 if i < 6 else 2000.0 * (1 + 0.5 * (i % 2)), "prop": False})
    r = pd.DataFrame(rows)
    wells = pd.DataFrame({"api10": ["A", "B"], "state_code": ["42", "42"]})
    early = w.labels_asof(wells, r, dt.date(2020, 6, 1))
    late = w.labels_asof(wells, r, None)
    assert early["A"] == "calculated"  # six flat months as of June
    assert late["A"] == "measured"  # the later variance is not visible at the June cutoff
    assert early["B"] == "insufficient"
    assert d0 < dt.date(2020, 6, 1)


def test_choose_fallback():
    m = w.choose(([1, 2, 3, 4], 50.0, 4), lambda: ([9] * 12, 5.0, 12))
    assert m["source"] == "measured" and m["thin"]
    f = w.choose(([1, 2], 50.0, 2), lambda: (list(range(12)), 5.0, 12))
    assert f["source"] == "calculated_fallback" and not f["thin"] and f["n_measured_at_cap"] == 2


def test_ratio_water_scales_with_lateral():
    oil = np.array([10_000.0, 8_000.0, 6_000.0])
    r = {"alpha": np.log(2.0), "beta": 0.0}
    np.testing.assert_allclose(w.ratio_water(oil, 10_000.0, r), 2 * oil)
    # with beta the ratio reads cumulative oil PER 1,000 ft: a longer lateral with the same per-ft oil gives the same WOR path
    r2 = {"alpha": 0.0, "beta": 1e-4}
    a = w.ratio_water(oil, 10_000.0, r2) / oil
    b = w.ratio_water(oil * 2, 20_000.0, r2) / (oil * 2)
    np.testing.assert_allclose(a, b)
    np.testing.assert_allclose(a, tc.ratio_monthly_volumes(oil / 10.0, 0.0, 1e-4) / (oil / 10.0))


def test_group_of():
    assert w.group_of("WCA", "WCXY") == "WCXY_WCA1"
    assert w.group_of("WCA", "WCA_2") == "WCA"
    assert w.group_of("BS3_S", "BS3_S") == "BS3_S"


def test_water12a_tier_rule():
    import pandas as pd

    from box import water12a as wa

    tun = pd.DataFrame({"group": ["G"] * 3, "method": ["ratio"] * 3, "horizon": [12, 24, 36], "verdict": ["PASS", "PASS", "not judged"]})
    hold = pd.DataFrame({"group": ["G"] * 3, "horizon": [12, 24, 36], "consistency": ["INSIDE", "INSIDE", "not judged"]})
    assert wa.tier("G", True, tun, hold)["water_tier"] == "validated"
    assert wa.tier("G", False, tun, hold)["water_tier"] == "provisional"  # never above its oil
    assert wa.tier("G", True, tun, hold.assign(consistency=["INSIDE", "OUTSIDE", "not judged"]))["water_tier"] == "provisional"
    assert wa.tier("G", True, tun, hold.assign(consistency="not judged"))["water_tier"] == "provisional"  # needs one judged cell
    assert wa.tier("G", True, tun.assign(verdict=["PASS", "FAIL", "PASS"]), hold)["water_tier"] == "provisional"
    assert wa.tier("G", True, tun, None)["water_tier"] == "provisional"


def test_water12a_identity():
    import pandas as pd

    from box import water12a as wa

    a = pd.DataFrame({"group": ["G", "G"], "horizon": [12, 24], "method": ["ratio"] * 2, "pkg_n_packages": [40, 35], "pkg_bias": [0.01, 0.02],
                      "pkg_band": [1.0, 1.1], "bench_bias": [0.0, 0.0], "bench_band": [0.9, 0.9]})
    assert wa.identity(a, a)["identical"].all()
    assert not wa.identity(a, a.assign(pkg_bias=[0.01, 0.0201]))["identical"].all()
