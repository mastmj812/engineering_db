"""dealintake.select_wells: spacing class, codev tiering, fill order (DB-free)."""

from datetime import date

import pytest

pytest.importorskip("yaml")

from dealintake.config import load
from dealintake.select_wells import (
    adjacent_benches,
    bench_code,
    codev_tier,
    select,
    spacing_class,
)

CFG = load()
STACK = ["WCA_1", "WCA_2", "WCB_1", "WCB_2"]

_ARRAYS = {
    "codev": {"codev_benches": ["WCA_2", "WCB_1"], "parent_benches": [], "child_benches": []},
    "standalone": {"codev_benches": ["WCB_1"], "parent_benches": [], "child_benches": []},
    "parent": {"codev_benches": ["WCA_2"], "parent_benches": ["WCA_2"], "child_benches": []},
    "child": {"codev_benches": [], "parent_benches": [], "child_benches": ["WCB_2"]},
}


def cand(api, kind="codev", dist=100.0, **kw):
    c = dict(api10=api, bench="WCB_1", first_production_date=date(2020, 1, 1),
             lateral_length_ft=9800.0, lateral_closer_xy_ft=900.0, months_produced=36,
             dist_ft=dist, eur_per_1000ft=50.0, **_ARRAYS[kind])
    c.update(kw)
    return c


def test_bench_code_strips_bimodal_suffix():
    assert bench_code("WCB_1_b") == "WCB_1"


def test_adjacent_benches():
    assert adjacent_benches("WCB_1", STACK) == ["WCA_2", "WCB_2"]
    assert adjacent_benches("WCA_1", STACK) == ["WCA_2"]
    assert adjacent_benches("WCA_1", ["WCA_1"]) == []


@pytest.mark.parametrize("xy,cls", [(None, "standalone"), (2800.0, "standalone"),
                                    (500.0, "tight"), (900.0, "representative")])
def test_spacing_class_sentinel_and_tight(xy, cls):
    assert spacing_class(xy, 880.0, CFG) == cls  # tight below 0.65 x 880 = 572


def test_tiers():
    adj = ["WCA_2", "WCB_2"]
    assert codev_tier(cand("a", "codev"), adj) == "codev"
    assert codev_tier(cand("a", "standalone"), adj) == "stack_standalone"  # only own-bench codev
    assert codev_tier(cand("a", "parent"), adj) == "topfill_underfill"  # parent beats codev
    assert codev_tier(cand("a", "child"), adj) == "topfill_underfill"


def _select(cands, pdp_adjacent=False):
    return select(cands, CFG, bench="WCB_1", planned_stack=STACK, planned_lateral_ft=9900,
                  basin="delaware", planned_spacing_ft=880,
                  deal_has_pdp_in_adjacent_bench=pdp_adjacent)


def test_fill_takes_first_tier_whole_then_nearest_of_next():
    cands = [cand(f"c{i}", "codev") for i in range(7)]
    cands += [cand(f"s{i}", "standalone", dist=1000 + i) for i in range(6)]
    cands += [cand(f"p{i}", "parent") for i in range(5)]
    sel = _select(cands)
    assert sel.tier_order[0] == "codev"
    assert len(sel.selected) == 10
    assert sel.tier_counts() == {"codev": 7, "stack_standalone": 3, "topfill_underfill": 0}
    assert [c["api10"] for c in sel.selected if c["tier"] == "stack_standalone"] == ["s0", "s1", "s2"]
    assert not any("first_tier_share" in f for f in sel.flags)  # 70% >= 50%


def test_order_flips_when_deal_has_adjacent_pdp():
    cands = [cand(f"p{i}", "parent") for i in range(10)] + [cand("c0", "codev")]
    sel = _select(cands, pdp_adjacent=True)
    assert sel.tier_order[0] == "topfill_underfill"
    assert sel.tier_counts()["topfill_underfill"] == 10


def test_exclusions_carry_reasons_and_undercount_flags():
    cands = [
        cand("old", first_production_date=date(2014, 1, 1)),
        cand("short", lateral_length_ft=5000.0),  # outside 7,425-12,375 (Delaware +/-25%)
        cand("young", months_produced=3),
        cand("sentinel", lateral_closer_xy_ft=2800.0),
        cand("ok"),
    ]
    sel = _select(cands)
    reasons = {c["api10"]: c["exclusion"] for c in sel.excluded}
    assert "first_prod" in reasons["old"]
    assert "lateral_outside_7425-12375" in reasons["short"]
    assert "months<6" in reasons["young"]
    assert "spacing_standalone" in reasons["sentinel"]
    assert [c["api10"] for c in sel.selected] == ["ok"]
    assert any(f.startswith("under_count") for f in sel.flags)


def test_low_first_tier_share_flag():
    cands = [cand("c0", "codev")] + [cand(f"s{i}", "standalone") for i in range(9)]
    sel = _select(cands)
    assert any("first_tier_share" in f for f in sel.flags)
