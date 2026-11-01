"""Step 21a revisions 1 + 3: same bench by depth, the tag-free D114 key and the neighbour-pattern precedent (DB-free)."""

import pandas as pd

from box import prox_pud as pp
from box import step21_prox as sp

HAIR = {"k4:mixed": 0.90, "k4:same": 0.90, "k4:topfill": 0.90, "k4:underfill": 0.90}


def _cfg(n_same=0, n_top=0, n_under=0, flanked=False, bench="MS", pb_top="JM", pb_under="US", api10="x"):
    present = [c for c, n in (("same", n_same), ("topfill", n_top), ("underfill", n_under)) if n > 0]
    cc = None if not present else ("mixed" if len(present) > 1 else present[0])
    return {"api10": api10, "bench": bench, "config_class": cc, "n_same": n_same, "n_topfill": n_top, "n_underfill": n_under,
            "n_parents_total": n_same + n_top + n_under, "flanked_same": flanked, "flanked_topfill": False, "flanked_underfill": False,
            "pb_same": bench if n_same else None, "pb_topfill": pb_top if n_top else None, "pb_underfill": pb_under if n_under else None}


def test_class_is_depth_not_tag():
    # card 14: LSSH-tagged wells 98 / 89 ft above a DEAN stick are same bench; card 18: a WCB_1-tagged well 217 ft above a WCB_1 is above
    L = pd.DataFrame({"cls": ["underfill", "underfill", "same", "same", "topfill"], "dv_ft": [98.0, 150.0, 217.0, 151.0, 120.0],
                      "dz_ft": [-98.0, 150.0, -217.0, 151.0, 120.0]})
    out = sp.by_depth(L)
    assert list(out["cls"]) == ["same", "same", "underfill", "topfill", "same"]  # + dz = parent deeper = below the stick
    assert list(L["cls"]) == ["underfill", "underfill", "same", "same", "topfill"]  # input untouched


def test_d114_key_drops_the_neighbour_tag():
    assert sp.pair_key("topfill", "JM", "WCB_1") == sp.pair_key("topfill", "JM", "WCA_1") == "JM>topfill"
    assert sp.pair_key("mixed", "WCA_1", None) == pp.pair_key("mixed", "WCA_1", None) == "WCA>mixed"
    kids = pd.DataFrame([_cfg(0, 2, 0, api10="a", pb_top="WCB_1"), _cfg(0, 2, 0, api10="b", pb_top="WCA_1")])
    assert sp.precedent(kids, pd.Series(dtype=float)) == {"MS>topfill": {"multi": 2, "package": 0}}
    assert set(pp.precedent(kids, pd.Series(dtype=float))) == {"MS>topfill>WCB_1", "MS>topfill>WCA"}  # Delaware path unchanged


def test_pattern_labels():
    c = pd.DataFrame([_cfg(2, 1, 1, flanked=True), _cfg(2, 0, 0, flanked=False), _cfg(1, 2, 0), _cfg(0, 1, 1), _cfg()])
    got = sp.pattern(c)
    assert list(got[:4]) == ["both sides+above+below", "one side", "one side+below", "none beside+above+below"]
    assert pd.isna(got.iloc[4])


def test_pattern_precedent_counts_multi_neighbour_wells_only():
    kids = pd.DataFrame([_cfg(1, 1, 0, api10="a"), _cfg(1, 1, 0, api10="b"), _cfg(1, 0, 0, api10="c")])
    prec = sp.pattern_precedent(kids, pd.Series({"a": 2, "b": 1}))
    assert prec == {"MS|one side+below": {"multi": 2, "package": 1}}  # the single-neighbour well is no precedent


def test_card13_sandwich_without_precedent_loses_its_forecast():
    cfg = pd.DataFrame([_cfg(2, 4, 1, flanked=True)], index=["13"])
    prec = {"MS>mixed": {"multi": 82, "package": 38}}  # D114 alone passes it
    d = sp.decide_all(cfg, HAIR, prec, {"MS|one side+below": {"multi": 81, "package": 40}})
    assert pp.decide_all(cfg, HAIR, prec).at["13", "outcome"] == "haircut"
    assert d.at["13", "outcome"] == "no_forecast_pattern" and d.at["13", "pattern_multi"] == 0
    ok = sp.decide_all(cfg, HAIR, prec, {"MS|both sides+above+below": {"multi": 30, "package": 0}})
    assert ok.at["13", "outcome"] == "haircut"  # factor 0.90 > 0.80: the package tier does not apply


def test_pattern_packages_are_reported_not_gated():
    cfg = pd.DataFrame([_cfg(1, 1, 0)], index=["s"])
    hair = {**HAIR, "k4:mixed": 0.75}  # severe: D114's own package tier applies (bench pair), the pattern's does not
    d = sp.decide_all(cfg, hair, {"MS>mixed": {"multi": 50, "package": 40}}, {"MS|one side+below": {"multi": 50, "package": 0}})
    assert d.at["s", "outcome"] == "haircut" and d.at["s", "pattern_package"] == 0
    d114 = sp.decide_all(cfg, hair, {"MS>mixed": {"multi": 50, "package": 29}}, {"MS|one side+below": {"multi": 50, "package": 50}})
    assert d114.at["s", "outcome"] == "no_forecast_package"


def test_never_forecasts_what_d114_refused_and_leaves_single_and_unexposed_alone():
    cfg = pd.DataFrame([_cfg(1, 1, 0), _cfg(1, 0, 0), _cfg()], index=["d114", "single", "none"])
    big = {"MS|one side+below": {"multi": 500, "package": 500}}
    d = sp.decide_all(cfg, HAIR, {"MS>mixed": {"multi": 5, "package": 5}}, big)
    assert list(d["outcome"]) == ["no_forecast_precedent", "as_is_single_parent", "as_is_unexposed"]
    assert pd.isna(d.at["single", "pattern_key"]) and pd.isna(d.at["none", "pattern"])


def test_every_existing_producer_is_a_parent_of_a_stick():
    # card 8: wells ~140 days on today are depleted parents by the time a BOX well is drilled (revision 4)
    L = pd.DataFrame({"rel": ["parent", "young", "codev"], "cls": ["same"] * 3})
    out = sp.existing_as_parents(L)
    assert list(out["rel"]) == ["parent"] * 3 and list(out["rel_asof"]) == ["parent", "young", "codev"]
    assert list(L["rel"]) == ["parent", "young", "codev"]  # input untouched
