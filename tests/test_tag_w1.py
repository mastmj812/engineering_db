"""W1 pieces: the vendor-only input identity check, multi-round class decisions, and ACCEPT on Step 1 cards."""

from __future__ import annotations

import pandas as pd

from box.tag_rule_inputs import SQL16_TRIGGERS, check_identity
from scripts.tag_v5_accepted import accepted_tags, class_decisions


def test_identity_check_counts_frame_and_code_differences():
    wells = pd.DataFrame({"api10": ["1", "2", "3"], "pre_sql23": ["WCA_1", None, "BS2_S"]})
    ident = pd.DataFrame({"api10": ["1", "2", "4"], "sql16": ["WCA_1", None, "WCB_1"]})
    assert check_identity(wells, ident) == {"wells": 3, "only_vendor_frame": 1, "only_enriched_frame": 1,
                                            "pre_sql23_differs_from_sql16": 0}
    ident.loc[0, "sql16"] = "WCXY"
    assert check_identity(wells, ident)["pre_sql23_differs_from_sql16"] == 1


def test_sql16_triggers_match_sql16():
    from box import tag_scoreboard as sb

    sql = (sb.ROOT / "sql" / "16_formation_blueox.sql").read_text(encoding="utf-8")
    for t in SQL16_TRIGGERS:
        assert f"'{t}'" in sql


def test_class_decisions_later_round_wins(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for f in (a, b, c):
        f.mkdir()
    pd.DataFrame({"class": ["x", "y"], "decision": ["round 2", "accept"]}).to_csv(a / "class_decisions.csv", index=False)
    pd.DataFrame({"class": ["x"], "decision": ["reject"]}).to_csv(b / "class_decisions.csv", index=False)
    d = class_decisions([a, b, c]).set_index("class")["decision"]
    assert d.to_dict() == {"y": "accept", "x": "reject"}


def test_accept_verdict_takes_the_proposal():
    d = pd.DataFrame({"api10": ["1", "2", "3"], "basin": ["delaware"] * 3, "live": ["BS3_C"] * 3,
                      "final": ["BS2_S"] * 3, "basis": ["pattern"] * 3})
    cards = pd.DataFrame({"api10": ["1", "2", "3"], "proposed": ["BS2_S"] * 3, "verdict": ["ACCEPT", "BS3_C", "REJECT"]})
    dec = pd.DataFrame({"class": ["delaware BS3_C->BS2_S (pattern)"], "decision": ["accept"]})
    a = accepted_tags(d, cards, dec).set_index("api10")
    assert a.loc["1", "accepted"] == "BS2_S" and a.loc["1", "accepted_basis"] == "carded_call"
    assert a.loc["2", "accepted"] == "BS3_C"
    assert a.loc["3", "accepted"] == "BS2_S" and a.loc["3", "accepted_basis"] == "class_accepted"  # REJECT is not a code
