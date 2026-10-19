"""deal-intake screen water on measured-water analogs (dealintake/water.py; BOX D107 / D110, Option A) — pure pieces."""

from dealintake import handoff, water


def test_tier_is_bench_and_basin():
    v = ["WCA_1", "WCA_2", "BS2_S"]
    assert water.tier("WCA_1", "delaware", v) == "validated"
    assert water.tier("BS2_S", "Delaware", v) == "validated"
    assert water.tier("WCB_1", "delaware", v) == "provisional"
    assert water.tier("WCA_1", "midland", v) == "provisional"  # BOX never tested Midland
    assert water.tier("WCA_1", None, v) == "provisional"


def test_flags_name_fallback_thin_and_reach():
    assert "calculated" in water.flags({"source": "calculated_fallback"})[0]
    assert "Arps" in water.flags({"source": "none"})[0]
    f = water.flags({"source": "measured", "thin": True, "api10s": ["1"] * 4, "radius_mi": 40.0})
    assert len(f) == 2 and "40 mi" in f[1]
    assert water.flags({"source": "measured", "thin": False, "api10s": ["1"] * 12, "radius_mi": 7.5}) == []


def test_summary_keeps_the_ratio_fields():
    s = water.summary({"mode": "ratio", "alpha": 1.0, "beta": 0.0, "eur_per_unit": 1.0, "smoothed_rate": [1.0],
                       "ratio_cohort": {"n_wells": 8, "n_requested": 10}})
    assert s["ratio_cohort"] == {"n_wells": 8, "n_requested": 10} and "smoothed_rate" not in s
    assert water.summary(None) is None


def test_handoff_saves_ratio_water_only_when_switched_on():
    G = {"water_cohort": {"api10s": ["4230100001", "4230100002", "4230100003"], "tier": "validated", "source": "measured",
                          "radius_mi": 5.0, "thin": True, "nm_share": 0.0, "n_eligible": 3, "method": "m"},
         "tc_preview_water_ratio": {"eur_per_unit": 1.0}}
    assert handoff.water_save({"water_save_ratio": False}, G) is None  # config v12 default: off until ledger §14
    w = handoff.water_save({"water_save_ratio": True}, G)
    assert w["api10s"] == G["water_cohort"]["api10s"] and w["record"]["tier"] == "validated" and w["record"]["n_wells"] == 3
    assert handoff.water_save({"water_save_ratio": True}, {**G, "tc_preview_water_ratio": None}) is None  # preview failed
