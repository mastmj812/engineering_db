"""BOX step 23 (box/record23): the Midland record's method block IS the 21d definition, D150 / D151 read from their gate files,
the derive arithmetic, and the production-path Midland groups."""

from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

from box import basin as bsn
from box import production as pr
from box import prospective21 as p21
from box import prox_cont as pc
from box import record23 as rc
from box import step21 as st21


def test_method_block_is_the_21d_definition():
    """The 2028 record-run check (prospective21.DEFINITION['method']['record_run_check']) passes by construction."""
    assert rc.check_method(rc.method_block()) == []


def test_method_block_reads_the_frozen_owners_not_21d():
    b = rc.method_block()
    assert b["base"]["digest"] == st21.DIGEST == st21.digest()
    assert b["proximity"]["digest"] == pc.DIGEST == pc.digest()
    assert b["base"]["frozen_sha"] == rc.gate_21b()["frozen_sha"]
    assert b["proximity"]["frozen_sha"] == rc.gate_24a()["frozen_sha"]
    assert b["proximity"]["curve"]["level"] == rc.gate_24a()["curves"]["midland"]["level"]


@pytest.mark.parametrize("path, value", [
    (("base", "digest"), "0" * 64),
    (("proximity", "digest"), "0" * 64),
    (("proximity", "curve", "level"), 1.0),
    (("proximity", "curve", "rule"), "R2"),
    (("tiers", "MID_WCB_2"), "validated"),
    (("extents", "MID_DEAN"), 48),
])
def test_check_method_catches_any_drift(path, value):
    b = copy.deepcopy(rc.method_block())
    x = b
    for k in path[:-1]:
        x = x[k]
    x[path[-1]] = value
    assert rc.check_method(b)


def test_haircut_either_way_passes_and_wrong_shape_fails():
    recomputed = {12: 0.97, 24: 0.96, 36: 0.94, 48: 0.93}
    assert rc.check_method(rc.method_block(recomputed, "recomputed_d150")) == []
    b = rc.method_block()
    b["haircut"]["MID_WCA_1"]["factor"].pop("48")
    assert rc.check_method(b)
    b = rc.method_block()
    b["haircut"]["MID_WCB_1"] = {"stream": "oil", "factor": {}}
    assert rc.check_method(b)


def test_d102_as_delivered_is_gate_21c():
    assert rc.d102_as_delivered() == {int(k): v for k, v in p21.D102_WCA_1_OIL_AT_21C.items()}


def test_tiers_are_d151_everywhere():
    t = {g: v["tier"] for g, v in rc.midland_groups().items()}
    assert t == {g: x[2] for g, x in p21.GROUPS.items()}
    assert pr.MIDLAND_PROVISIONAL == frozenset(g for g, v in t.items() if v == "provisional")
    for g, v in t.items():
        assert pr.covered_class(g) == ("covered" if v == "validated" else "covered_provisional")
        assert pr.PRODUCTION_BENCHES[g] == (bsn.MIDLAND, st21.GROUPS[g][0], frozenset({st21.GROUPS[g][0]}))


def test_delaware_groups_unchanged():
    for g, (b, _bench, _f) in pr.PRODUCTION_BENCHES.items():
        if not g.startswith("MID_"):
            assert b == bsn.DELAWARE
    assert pr.covered_class("WCA") == "covered" and pr.covered_class("BS1_S") == "covered_provisional"


def _row(**kw):
    base = {"basin": bsn.MIDLAND, "bench": "WCA_1", "formation_blueox": "WCA_1", "in_scope": True, "inside_extent": True,
            "recon_status": "remaining_pud"}
    return pd.Series(base | kw)


def test_d145_conflict_sticks_midland_only():
    groups = ("MID_WCA_1",)
    assert pr.classify(_row(), groups) == "covered"
    assert pr.classify(_row(recon_status="conflict"), groups) == pr.NOT_COVERED_CONFLICT
    assert pr.classify(_row(recon_status="conflict", in_scope=False), groups) == "not_covered_emerging"
    d = _row(basin=bsn.DELAWARE, bench="WCA", formation_blueox="WCA_1", recon_status="conflict")
    assert pr.classify(d, ("WCA",)) == "covered"


def test_d150_models_from_gate():
    for basin, rule in ((bsn.DELAWARE, "R2"), (bsn.MIDLAND, "R3")):
        m, r = rc.d150(basin)
        c = rc.gate_24a()["curves"][basin]
        assert r == rule and m.level == c["level"] and m.curve.f_min == c["f_min"]
        f = m.factor(np.array([0.0, 1e9]), np.zeros(2), np.array(["same", "same"]))
        assert f[0] == pytest.approx(c["f_min"]) and f[1] == pytest.approx(1.0)


def _links(rows):
    cols = ["child", "parent", "rel", "overlap", "dv_ft", "dh_ft", "dz_ft", "dxy_ft", "permit", "age_days", "parent_bench"]
    return pd.DataFrame(rows, columns=cols)


def test_stick_factors_and_outcomes():
    L = _links([["1", "p1", "parent", 0.9, 10, 300, 10, 300, False, 900, "WCA_1"],
                ["1", "p2", "parent", 0.9, 10, 600, 10, -600, False, 900, "WCA_1"],
                ["2", "p3", "parent", 0.9, 10, 500, 10, 500, False, 900, "WCA_1"],
                ["3", "p4", "parent", 0.1, 10, 300, 10, 300, False, 900, "WCA_1"]])  # under 30 % alongside: not a parent
    f = rc.stick_factors(L, bsn.MIDLAND, ["1", "2", "3", "4"])
    m, _ = rc.d150(bsn.MIDLAND)
    assert list(f["n_parents"]) == [2, 1, 0, 0]
    assert f.loc["3", "factor"] == pytest.approx(m.level) and f.loc["4", "factor"] == pytest.approx(m.level)
    f1 = m.factor(np.array([300.0, 600.0]), np.array([10.0, 10.0]), np.array(["same", "same"]))
    assert f.loc["1", "factor"] == pytest.approx(m.level * f1[0] * f1[1])  # R3: left and right each a side
    inc = pd.DataFrame({"outcome": ["haircut", "as_is_single_parent", "as_is_unexposed", "no_forecast_spacing"]}, index=["1", "2", "3", "4"])
    oc = rc.outcomes(inc, f)
    assert list(oc["outcome"]) == [rc.MULTI, rc.SINGLE, rc.LEVEL_UNEXPOSED, "no_forecast_spacing"]
    assert list(oc["keep"]) == [True, True, True, False]


def test_rescale_divides_the_source_factor_out():
    old = np.array([1.0, 0.8, 0.9])
    new = np.array([1.046, 0.95, 0.7])
    eur = np.array([100.0, 80.0, 90.0])
    out = eur * rc.rescale(old, new)
    assert out == pytest.approx(eur / old * new)
    with pytest.raises(ValueError):
        rc.rescale(np.array([0.0]), np.array([1.0]))


def test_expected_oil_by_bench():
    src = pd.DataFrame({"formation_blueox": ["A", "A", "B"], "oil_eur": [100.0, 80.0, 50.0], "prox_factor": [1.0, 0.8, 1.0]},
                       index=["1", "2", "3"])
    oc = pd.DataFrame({"keep": [True, True, False], "factor": [1.05, 0.9, 0.7]}, index=["1", "2", "3"])
    e = rc.expected_oil(src, oc)
    assert e.loc["A", "oil_new"] == pytest.approx(105.0 + 90.0) and "B" not in e.index


def test_d154_haircut_of_record_is_the_recomputed_one():
    """Gate 23a (a): the record ships WCA_1's D102 recomputed on D150; the stored block says so and still passes 21d's check."""
    import json

    h = rc.d102_shipped()
    assert rc.HAIRCUT_BASIS == "recomputed_d150" and h == rc.d102_recomputed() != rc.d102_as_delivered()
    assert h == pytest.approx({12: 0.95761, 24: 0.95257, 36: 0.93249, 48: 0.92687}, abs=1e-5)
    assert all(a >= b for a, b in zip(list(h.values()), list(h.values())[1:], strict=False))  # monotone (D106 table half)
    b = rc.method_block()
    assert b["haircut"]["MID_WCA_1"]["basis"] == "recomputed_d150" and rc.check_method(b) == []
    gate = json.loads((rc.ROOT / rc.DOCS / "GATE_23A.json").read_text(encoding="utf-8"))
    assert {int(k): v for k, v in gate["answers"]["a_wca1_haircut"]["factor"].items()} == pytest.approx(h, rel=1e-12)
    pack = json.loads((rc.ROOT / rc.DOCS / "midland_pack_recomputed.json").read_text(encoding="utf-8"))
    assert {int(k): v["factor"] for k, v in pack["groups"]["MID_WCA_1"]["haircut"]["oil"].items()} == pytest.approx(h, rel=1e-12)


class _FakeBox:
    """Just enough of box.forecast_run / pud_forecast / box_pud_econ for priced()."""

    def __init__(self, runs: dict[int, tuple[str, bool]], n: dict[int, int], econ: dict[int, dict[str, int]]):
        self.runs, self.n, self.econ = runs, n, econ

    def __call__(self, sql: str, p: tuple = ()):
        class R:
            def __init__(self, rows): self.rows = rows
            def fetchone(self): return self.rows[0] if self.rows else None
            def fetchall(self): return self.rows
        if "count(*) FROM box.pud_forecast" in sql:
            return R([(self.n[p[0]],)])
        if "basin <> %s AND is_record" in sql:
            return R(sorted((r,) for r, (b, rec) in self.runs.items() if b != p[0] and rec)[:1])
        if "basin = %s AND is_record" in sql:
            return R([(r,) for r, (b, rec) in self.runs.items() if b == p[0] and rec])
        if "SELECT DISTINCT deck_id" in sql:
            return R([(d,) for d in self.econ.get(p[0], {})])
        if "GROUP BY 1" in sql:
            return R(list(self.econ.get(p[0], {}).items()))
        raise AssertionError(sql)


def test_priced_first_midland_record_needs_the_delaware_decks():
    """23b: with no Midland record, a one-deck Midland run must NOT pass (it would flip and show nothing in sql/69)."""
    from scripts import box_record23 as sr

    decks = {"wti60_hh2": 10, "wti70_hh3": 10}
    box = _FakeBox({1: (bsn.DELAWARE, True), 2: (bsn.MIDLAND, False)}, {1: 10, 2: 5}, {1: decks, 2: {"wti60_hh2": 5}})
    p = sr.priced(box, 2, bsn.MIDLAND)
    assert not p["ok"] and p["deck_reference_run"] == 1 and p["decks_required"] == sorted(decks)
    box.econ[2] = {"wti60_hh2": 5, "wti70_hh3": 5}
    assert sr.priced(box, 2, bsn.MIDLAND)["ok"]
    box.econ[2] = {"wti60_hh2": 5, "wti70_hh3": 4}  # one location short on one deck
    assert not sr.priced(box, 2, bsn.MIDLAND)["ok"]


def test_priced_with_no_record_anywhere_needs_the_default_deck():
    from scripts import box_record23 as sr

    box = _FakeBox({2: (bsn.MIDLAND, False)}, {2: 5}, {2: {"wti60_hh2": 5}})
    assert not sr.priced(box, 2, bsn.MIDLAND)["ok"]
    box.econ[2][sr.DEFAULT_DECK] = 5
    assert sr.priced(box, 2, bsn.MIDLAND)["ok"]
    assert not sr.priced(_FakeBox({3: (bsn.MIDLAND, False)}, {3: 0}, {3: {}}), 3, bsn.MIDLAND)["ok"]
