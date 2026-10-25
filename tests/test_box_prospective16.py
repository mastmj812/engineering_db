"""Step 13d: the 13-group r2 prospective definition is pinned (any edit after the freeze fails here) and matches run 19."""

from box import acceptance as ac
from box import production16 as p16prod
from box import prospective as d85
from box import prospective16 as ps


def test_definition_matches_the_pinned_digest():
    assert ps.digest() == ps.DIGEST, "box/prospective16.py DEFINITION changed after the freeze — that is tuning after the fact"


def test_d85_stays_frozen_alongside():
    assert d85.digest() == d85.DIGEST


def test_groups_are_run_19s_with_their_tier_and_extent():
    g = ps.DEFINITION["cohort"]["groups"]
    assert set(g) == {"WCA", "WCXY_WCA1", "BS2_S", "WCB_1", "WCC", "AVA_0", "AVA_1", "AVA_2", "BS1_S", "BS2_C", "BS3_C", "BS3_S", "WCB_2"}
    for name, x in g.items():
        spec = ac.BENCH_SPECS[name]
        assert x["tier_at_freeze"] == ("provisional" if spec.get("provisional") else "validated"), name
    assert g["WCA"]["formations"] == ["WCA_1", "WCA_2"] and g["WCXY_WCA1"]["formations"] == ["WCXY"]
    assert g["WCA"]["extent_id"] == g["WCXY_WCA1"]["extent_id"] == 6  # WCXY rides the WCA extent (D95)


def test_method_is_run_19s():
    m = ps.DEFINITION["method"]
    assert m["selection"] == p16prod.SELECTION and m["rules"] == repr(p16prod.RULES)
    assert m["haircut"]["streams"] == {g: list(s) for g, s in p16prod.HAIRCUT_STREAMS.items()}  # WCA gas none (D122)


def test_tags_are_read_at_scoring_time_and_merges_need_an_amendment_first():
    t = ps.DEFINITION["tags"]
    assert t["governing"] == "scoring_time" and "never the verdict" in t["sensitivity"]
    assert "before any score is read" in t["merge_or_split"]


def test_one_judgment_per_horizon_on_a_fixed_date():
    s, v = ps.DEFINITION["schedule"], ps.DEFINITION["verdict"]
    assert "2028-01-01" in s["cum12_judged_once"] and "2029-01-01" in s["cum24_judged_once"]
    assert "never judged" in s["early_reads"] and v["horizons_judged"] == [12, 24] and v["min_packages"] == 30
