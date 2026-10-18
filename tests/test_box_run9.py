"""DB-free tests for BOX run 9 (box/production_run9.py + the run-9 coverage classes in box/production.py)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from box import acceptance as ac
from box import production as pr
from box import production9c as p9
from box import production_run9 as p9r


def _row(**kw):
    base = {"basin": "delaware", "bench": "WCA", "in_scope": True, "formation_blueox": "WCA_1", "inside_extent": True}
    return SimpleNamespace(**(base | kw))


def test_groups_are_production_benches_and_tiers_match_bench_specs():
    assert set(p9r.GROUPS) <= set(pr.PRODUCTION_BENCHES) and p9r.GROUPS[0] == "WCA"
    prov = {g for g in p9r.GROUPS if ac.BENCH_SPECS[g].get("provisional")}
    assert prov == set(p9r.D105_BENCHES) | set(p9r.HOLDOUT_FAIL)
    assert {g for g in p9r.GROUPS if p9r.tier(g) == "validated"} == {"WCA", "BS2_S", "WCXY_WCA1", "WCB_1", "WCC"}
    for g in p9r.GROUPS[3:]:  # every step-15 group: own bench_scope bench, formation and extent; raw box_v2 record
        assert pr.PRODUCTION_BENCHES[g] == ("delaware", g, frozenset({g})) and p9.record_variant(g) == "box_v2"
        assert (p9r.wells_dir(g, p9r.DOCS) / f"wells_final_{g}.csv").exists()
    assert p9r.wells_dir("WCA", p9r.DOCS / "pool-2026-10-15") == p9r.DOCS / "pool-2026-10-15"


@pytest.mark.parametrize("kw,want", [
    ({}, "covered"),
    ({"bench": "WCB_1", "formation_blueox": "WCB_1"}, "covered"),
    ({"bench": "BS3_S", "formation_blueox": "BS3_S"}, "covered_provisional"),
    ({"bench": "AVA_1", "formation_blueox": "AVA_1"}, "covered_provisional"),
    ({"bench": "BS3_S", "formation_blueox": "BS3_S", "inside_extent": False}, "not_covered_outside_extent"),
    ({"bench": "WCD", "formation_blueox": "WCD", "in_scope": False, "inside_extent": None}, "not_covered_emerging"),
])
def test_classify_run9(kw, want):
    assert pr.classify(_row(**kw), p9r.GROUPS) == want


def test_classify_without_the_group_is_unvalidated():
    assert pr.classify(_row(bench="BS3_S", formation_blueox="BS3_S"), ("WCA", "BS2_S", "WCXY_WCA1")) == "not_covered_unvalidated"


def _tab(oil, gas):
    return {s: {k: {"factor": f} for k, f in zip(pr.HORIZONS, fs, strict=True)} for s, fs in (("oil", oil), ("gas", gas))}


def test_guard_table_passes_the_record_haircuts():
    assert p9r.guard_table(p9.haircut_for("WCA")) == []  # WCA gas 1.002 / 1.021 / 1.019 / 1.059: reversal 0.002 inside the 0.01 tolerance
    assert p9r.guard_table(p9.haircut_for("BS2_S")) == []


def test_guard_table_refuses_a_reversal():
    bad = p9r.guard_table(_tab([0.975, 0.969, 0.867, 0.742], [1.114, 1.189, 1.354, 1.252]))  # WCB_1 tuning-gate D62 table
    assert len(bad) == 1 and bad[0].startswith("gas") and "0.102" in bad[0]
    assert p9r.guard_table(_tab([0.9, 0.9, 0.9, 0.9], [1.0, 1.0, 1.0, 1.0])) == []


def test_guard_tail_on_the_median_location():
    ok, stat = p9r.guard_tail({"oil": np.array([0.55, 0.68, 0.70]), "gas": np.array([1.1, 1.12, 1.15])})
    assert ok == [] and stat["oil"]["min"] == 0.55 and stat["oil"]["share_outside"] == pytest.approx(1 / 3)
    bad, _ = p9r.guard_tail({"oil": np.array([0.40, 0.41, 0.9])})  # WCB_1-style oil tail 0.40
    assert bad and "0.410" in bad[0]
    assert p9r.guard_tail({"gas": np.array([1.48])})[0]  # BS3_C-style tail inflation


def test_validated15_disclosure_d100_numbers():
    d = p9r.validated15_disclosure("WCB_1")
    o36 = d["hindcast_bias"]["oil"]["36"]
    assert d["tier"] == "validated" and o36["d99_judged"] and o36["disclosed_bias"] == pytest.approx(-0.1328, abs=5e-4)
    assert o36["holdout_bias"] == pytest.approx(-0.1317, abs=5e-4) and o36["haircut_factor"] == 1.0
    assert not d["hindcast_bias"]["oil"]["48"]["d99_judged"] and d["radius_ranges"]


@pytest.mark.parametrize("g,stream,k,hold", [("BS3_C", "oil", 12, -0.141), ("WCB_2", "gas", 12, 0.206), ("BS1_S", "oil", 12, -0.209),
                                            ("BS3_S", "oil", 12, 0.055)])
def test_provisional_holdout_fail_lines(g, stream, k, hold):
    d = p9r.provisional_disclosure(g)
    b = d["hindcast_bias"][stream][str(k)]
    assert d["tier"] == "provisional" and d["holdout"].startswith("FAIL")
    assert b["holdout_bias"] == pytest.approx(hold, abs=1e-3) and b["disclosed_basis"] == f"{g}, tuning + holdout"
    scopes = {(x["scope"]) for x in d["lines"] if x["stream"] == stream and x["horizon"] == k}
    assert scopes == {"tuning", "holdout", "tuning + holdout"}  # never the pooled figure alone
    assert d["latest_vintage"][0]["cutoff"].startswith("2024")


def test_provisional_d105_ava_leads_with_the_pool_and_the_accepted_line():
    d = p9r.provisional_disclosure("AVA_1")
    assert d["lead"]["label"] == "AVA (0+1+2 pooled)" and d["hindcast_bias"]["oil"]["12"]["disclosed_bias"] == pytest.approx(-0.071, abs=1e-3)
    assert d["latest_vintage_text"] == p9r.D105_LATEST["AVA"] and d["hindcast_bias"]["oil"]["12"]["holdout_bias"] is None
    assert {x["label"] for x in d["lines"]} == {"AVA (0+1+2 pooled)", "AVA_1"}
    assert p9r.provisional_disclosure("BS2_C")["latest_vintage_text"] == p9r.D105_LATEST["BS2_C"]


def test_group_flags():
    f = p9r.group_flags("WCB_2", p9r.provisional_disclosure("WCB_2"), "S")
    assert f[0].startswith("D105 PROVISIONAL WCB_2 (holdout FAIL") and "+20.6%" in f[0]
    assert f[1].startswith("WCB_2 S-edge caveat") and "-13%" in f[1]
    assert p9r.group_flags("WCB_2", p9r.provisional_disclosure("WCB_2"), "N")[1:] == []  # no N caveat decided for WCB_2
    w = p9r.group_flags("WCC", p9r.validated15_disclosure("WCC"), "E")
    assert w[0].startswith("WCC (validated, weak evidence") and w[1].startswith("WCC E-edge caveat")
    assert p9r.group_flags("WCB_1", p9r.validated15_disclosure("WCB_1"), None) == [p9r.CALLOUTS["WCB_1"]]


def test_inputs_cover_every_step15_group():
    for g in p9r.GROUPS[3:]:
        rr = pd.read_csv(p9r.RUN9_INPUTS / f"spread_by_radius_{g}.csv")
        assert set(rr["radius_class"]) <= {"5 mi ring", "past 5 mi"} and len(rr)
        assert "interior" in set(pd.read_csv(p9r.RUN9_INPUTS / f"edge_regions_{g}.csv")["region"])
