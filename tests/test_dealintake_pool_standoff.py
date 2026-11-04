"""Reviewer pool rule (config v16, benches.yaml `pools:`) — Michael 2026-11-04, Eggs Tyrone:
WCB_1 / WCB_2 tags are unreliable under a developed WCA, so the WCB_2 pool draws both tags
and keeps only wells >= ~400 ft below the local WCA median. DB-free."""

from datetime import date

import pytest

pytest.importorskip("yaml")
pytest.importorskip("shapely")

from dealintake import unit_benches
from dealintake.config import load
from dealintake.render.tables import BUILDUP_COLS, BUILDUP_HEADERS, buildup_rows
from dealintake.select_wells import classify, standoff_reasons
from dealintake.warehouse import _standoff_sql, resolve_standoff

CFG = load()
RULE = {"tags": ["WCB_1", "WCB_2"], "below": ["WCA_1", "WCA_2"], "min_standoff_ft": 400.0}


def cand(api, tvd, standoff, bench="WCB_2"):
    return {"api10": api, "bench": bench, "tvd_ft": tvd, "standoff_ft": standoff,
            "first_production_date": date(2020, 1, 1), "lateral_length_ft": 9900.0, "lateral_closer_xy_ft": 1300.0,
            "months_produced": 36, "dist_ft": 100.0, "codev_benches": [], "parent_benches": [], "child_benches": [],
            "parent_benches_below": [], "parent_benches_above": [], "scenario_class": "standalone"}


def test_config_v16_carries_the_measurement_settings():
    assert CFG.version >= 16
    assert [float(r) for r in CFG["pool_standoff"]["ref_radius_mi"]] == [1.0, 2.0]
    assert int(CFG["pool_standoff"]["ref_min_wells"]) == 3


def test_standoff_reasons():
    assert standoff_reasons(cand("a", 11145, 434), RULE) == []
    assert standoff_reasons(cand("b", 11140, 400), RULE) == []            # the threshold is inclusive
    assert standoff_reasons(cand("c", 11099, 399), RULE) == ["standoff<400"]
    assert standoff_reasons(cand("d", 12000, 1289), RULE) == ["permit_tvd"]  # rule 10: not a measurement
    assert standoff_reasons(cand("e", 11145, None), RULE) == ["no_standoff_ref"]
    assert standoff_reasons(cand("f", 11145, 10), None) == []             # no rule, no effect
    assert standoff_reasons(cand("g", 11145, 10), {"tags": ["WCB_1", "WCB_2"]}) == []  # tags-only rule


def test_classify_applies_the_rule_with_reasons_and_keeps_both_tags():
    cands = [cand("1", 11145, 434), cand("2", 11118, 407, bench="WCB_1"), cand("3", 10877, 280, bench="WCB_1"),
             cand("4", 12000, 1289)]
    eligible, excluded, _ = classify(cands, CFG, bench="WCB_2", planned_stack=["WCB_2"], planned_lateral_ft=9900.0,
                                     basin="delaware", planned_spacing_ft=1320.0, pool_rule=RULE)
    assert sorted(c["api10"] for c in eligible) == ["1", "2"]
    assert {c["api10"]: c["exclusion"] for c in excluded} == {"3": "standoff<400", "4": "permit_tvd"}


def test_resolve_standoff_first_radius_with_enough_wells():
    so = {"ref_radius_mi": [1.0, 2.0], "ref_min_wells": 3, "below": ["WCA_1"]}
    r = {"tvd_ft": 11145, "standoff_ref_n_0": 2, "standoff_ref_tvd_0": 10600.0,
         "standoff_ref_n_1": 9, "standoff_ref_tvd_1": 10711.0}
    resolve_standoff(r, so)
    assert (r["standoff_ref_radius_mi"], r["standoff_ref_n"], r["standoff_ft"]) == (2.0, 9, 434.0)
    assert not {"standoff_ref_n_0", "standoff_ref_n_1", "standoff_ref_tvd_0", "standoff_ref_tvd_1"} & set(r)
    r = {"tvd_ft": 11145, "standoff_ref_n_0": 1, "standoff_ref_tvd_0": 10600.0,
         "standoff_ref_n_1": 2, "standoff_ref_tvd_1": 10650.0}
    resolve_standoff(r, so)
    assert r["standoff_ft"] is None and r["standoff_ref_tvd_ft"] is None


def test_standoff_sql_shape():
    assert _standoff_sql(None) == ("", "")
    cols, join = _standoff_sql({"ref_radius_mi": [1.0, 2.0], "ref_min_wells": 3, "below": ["WCA_1"]})
    assert "standoff_ref_n_0" in cols and "standoff_ref_tvd_1" in cols
    assert "%(ref_benches)s" in join and "w2.tvd_ft::int %% 100 <> 0" in join   # permit TVDs never in the reference
    assert "w2.novi_slant_calculated" in join and " w.novi" not in join


def _yaml(tmp_path, text):
    (tmp_path / unit_benches.FILENAME).write_text(text, encoding="utf-8")


def test_read_pools(tmp_path):
    assert unit_benches.read_pools(tmp_path) == {}
    _yaml(tmp_path, "units: {}\npools:\n  WCB_2:\n    tags: [WCB_1, WCB_2]\n    below: [WCA_1, WCA_2]\n"
                    "    min_standoff_ft: 400\n")
    assert unit_benches.read_pools(tmp_path) == {"WCB_2": RULE}


@pytest.mark.parametrize("body, msg", [
    ("WCB_2: {below: [WCA_1]}", "go together"),
    ("WCB_2: {min_standoff_ft: 400}", "go together"),
    ("WCB_2: {tags: WCB_1}", "non-empty list"),
    ("WCB_2: {tags: [WCB_1], min_standoff_ft: -5, below: [WCA_1]}", "positive number"),
    ("WCB_2: {tags: [WCB_1], standoff: 400}", "unknown key"),
    ("WCB_2: {}", "empty rule"),
])
def test_read_pools_rejects(tmp_path, body, msg):
    _yaml(tmp_path, f"units: {{}}\npools:\n  {body}\n")
    with pytest.raises(ValueError, match=msg):
        unit_benches.read_pools(tmp_path)


def test_buildup_shows_tvd_and_standoff():
    row = buildup_rows([cand("1", 11145, 434.4)])[0]
    i = BUILDUP_HEADERS.index("Below ref ft")
    assert row[BUILDUP_HEADERS.index("TVD ft")] == 11145 and row[i] == 434
    assert len(row) == len(BUILDUP_HEADERS)
    assert {"tvd_ft", "standoff_ft"} <= set(BUILDUP_COLS)
