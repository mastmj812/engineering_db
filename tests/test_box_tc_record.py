"""BOX step 5d — DB-free tests for the record rules (box/tc_record.py) and the sql/58 guards."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from box import tc_curve as tc
from box import tc_record as tr

WCA = ("WCA_1", "WCA_2", "WCXY")
SQL58 = Path(__file__).resolve().parent.parent / "sql" / "58_box_type_curve.sql"


# ----------------------------------------------------------------------------
# D42 pooled-bench view
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(("cls", "below", "above", "infill", "want"), [
    ("topfill", "WCA_2", None, False, ("codev_stack", None, True, True)),        # WCA_1 over WCA_2 = lateral infill
    ("underfill", None, "WCXY", False, ("codev_stack", None, True, True)),       # under a WCXY parent: same pool (D20 one-way doesn't bar it)
    ("topfill", "WCB_1", None, True, ("topfill", "WCB_1", True, False)),         # other-bench parent unchanged, own infill kept
    ("underfill", None, "BS3_S", False, ("underfill", "BS3_S", False, False)),
    ("sandwich", "WCA_2", "BS3_C", False, ("underfill", "BS3_C", True, True)),   # same-pool side -> infill, other side kept
    ("sandwich", "WCB_1", "WCA_1", False, ("topfill", "WCB_1", True, True)),
    ("sandwich", "WCA_2", "WCXY", False, ("codev_stack", None, True, True)),
    ("sandwich", "WCB_1", "BS3_S", False, ("sandwich", "WCB_1+BS3_S", False, False)),
    ("standalone", None, None, False, ("standalone", None, False, False)),
    ("codev_stack", None, None, True, ("codev_stack", None, True, False)),
])
def test_pooled_scenario(cls, below, above, infill, want) -> None:
    assert tr.pooled_scenario(cls, below, above, infill, WCA) == want


def test_pooled_scenario_bs2s_pool_and_blanks() -> None:
    # BS2_S's pool is itself: a parent is never the own bench, so nothing relabels
    assert tr.pooled_scenario("topfill", "BS3_S", None, False, ("BS2_S",)) == ("topfill", "BS3_S", False, False)
    # CSV blanks / NaN parents read as missing
    assert tr.pooled_scenario("topfill", "WCB_1", float("nan"), float("nan"), WCA) == ("topfill", "WCB_1", False, False)
    assert tr.pooled_scenario(None, None, None, None, WCA) == (None, None, False, False)


def test_raw_pair() -> None:
    assert tr.raw_pair("topfill", "WCB_1") == "topfill|WCB_1"
    assert tr.raw_pair("sandwich", "WCB_1+BS3_S") == "sandwich|all"
    assert tr.raw_pair("standalone", None) == "standalone"
    assert tr.raw_pair(None, None) is None


# ----------------------------------------------------------------------------
# D45 ladder
# ----------------------------------------------------------------------------

CLS = {"topfill": tr.Est(0.95, 0.9, 1.0, 188), "sandwich": tr.Est(1.2, 0.4, 2.0, 1), "infill": tr.Est(0.92, 0.9, 0.94, 1664)}
BASIN = {"topfill": tr.Est(0.96, 0.9, 1.0, 304), "sandwich": tr.Est(0.79, 0.6, 1.0, 10), "infill": tr.Est(0.92, 0.9, 0.94, 2150)}


def test_resolve_rungs() -> None:
    assert tr.resolve("topfill|WCB_1", tr.Est(0.952, 0.9, 1.0, 58), CLS, BASIN) == (0.952, 1, 58)
    assert tr.resolve("topfill|WCB_1", tr.Est(0.952, 0.9, 1.0, 30), CLS, BASIN)[1] == 1   # n >= 30 is rung 1
    assert tr.resolve("topfill|other", tr.Est(0.70, 0.5, 1.0, 29), CLS, BASIN) == (0.95, 2, 188)
    # sandwich: own n 1, class in bench n 1 -> across benches, terminal whatever its n (10)
    assert tr.resolve("sandwich|all", tr.Est(1.25, 0.4, 2.0, 1), CLS, BASIN) == (0.79, 3, 10)
    assert tr.resolve("infill", tr.Est(0.9227, 0.9, 0.94, 1664), CLS, BASIN) == (0.9227, 1, 1664)


def test_resolve_refuses_without_basin_class() -> None:
    with pytest.raises(ValueError):
        tr.resolve("underfill|X", tr.Est(0.9, None, None, 3), {}, {})


def test_resolve_class() -> None:
    assert tr.resolve_class("topfill", CLS["topfill"], BASIN) == (0.95, 2, 188)
    assert tr.resolve_class("sandwich", CLS["sandwich"], BASIN) == (0.79, 3, 10)


# ----------------------------------------------------------------------------
# Lookup (D41 x D44)
# ----------------------------------------------------------------------------

TAB = {("pair", "topfill|WCB_1"): 0.952, ("pair", "topfill|other"): 0.97, ("pair", "infill"): 0.923, ("pair", "standalone"): 1.046,
       ("class", "underfill"): 0.929, ("basin_class", "sandwich"): 0.786, ("basin_class", "underfill"): 0.93}


def test_lookup() -> None:
    assert tr.lookup(TAB, "WCA", "codev_stack", False) == 1.0
    assert tr.lookup(TAB, "WCA", "codev_stack", True) == pytest.approx(0.923)
    assert tr.lookup(TAB, "WCA", "topfill|WCB_1", True) == pytest.approx(0.952 * 0.923)   # factors combine (D41)
    assert tr.lookup(TAB, "WCA", "topfill|WCZ", False) == pytest.approx(0.97)             # rare pair -> its '|other' estimate
    assert tr.lookup(TAB, "WCA", "underfill|BS9", False) == pytest.approx(0.929)          # -> class in bench
    assert tr.lookup(TAB, "WCA", "sandwich|all", False) == pytest.approx(0.786)           # -> across benches
    assert tr.lookup(TAB, "WCA", None, False) == 1.0                                      # unscored well = reference
    with pytest.raises(KeyError):
        tr.lookup({}, "WCA", "topfill|WCB_1", False)


def test_lookup_d44_pud_standalone_is_reference() -> None:
    assert tr.lookup(TAB, "WCA", "standalone", False) == pytest.approx(1.046)             # an actual well (scoring)
    assert tr.lookup(TAB, "WCA", "standalone", False, pud=True) == 1.0                    # an unparented PUD
    assert tr.lookup(TAB, "WCA", "standalone", True, pud=True) == pytest.approx(0.923)


# ----------------------------------------------------------------------------
# D43 reference curve
# ----------------------------------------------------------------------------


def test_reference_params_is_a_uniform_scale() -> None:
    fit = {"qo": 26.7, "qi": 71.6, "peak_index": 2, "Di": 3.17, "b": 1.10, "Df": 0.08, "eur_per_unit": 1.0}
    ref = tr.reference_params(fit, 0.994)
    assert (ref["Di"], ref["b"], ref["Df"], ref["peak_index"]) == (3.17, 1.10, 0.08, 2)
    v0, v1 = tc.monthly_volumes(fit), tc.monthly_volumes(ref)
    assert np.allclose(v1 / v0, 0.994, rtol=1e-12)   # every exact month (D39) and hence EUR scale by ref_mult
    with pytest.raises(ValueError):
        tr.reference_params(fit, 0.0)


def test_weighted_ref_mult() -> None:
    # two equal-weight wells, one infill at 0.9: reference-equivalent mean = (1 + 1/0.9) / 2
    assert tr.weighted_ref_mult([10.0, 10.0], [1.0, 0.9]) == pytest.approx((1 + 1 / 0.9) / 2)
    assert tr.weighted_ref_mult([10.0, np.nan], [1.0, 0.9]) == pytest.approx(1.0)


# ----------------------------------------------------------------------------
# sql/58 guards stay in step with the decisions
# ----------------------------------------------------------------------------


def test_sql58_guards() -> None:
    s = SQL58.read_text(encoding="utf-8")
    assert re.search(r"relaxation_step\s+smallint NOT NULL CHECK \(relaxation_step IN \(1, 2, 4, 5\)\)", s)   # D37: no rung 3
    assert set(tc.RUNG_LABEL) == {1, 2, 4, 5}
    assert "CHECK (rung IN (0, 1, 2, 3))" in s and set(tr.RUNG_LABEL) == {0, 1, 2, 3}                          # D45: three rungs + reference
    assert "CHECK (statistic = 'mean')" in s and tc.RECORD_STAT == "mean"                                       # D32
    assert "(stream = 'gas') = (mode = 'ratio')" in s                                                           # D30
    assert "CHECK (thin OR n_wells >= 10)" in s and tc.MIN_WELLS == 10
