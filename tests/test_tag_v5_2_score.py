"""scripts.tag_v5_2_score — verdict vocabulary and class acceptance (no DB)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scripts import tag_v5_2_score as s


def test_read_verdict():
    assert s.read_verdict("ACCEPT", "WCA_1", "BS2_S") == ("agree", "WCA_1")
    assert s.read_verdict("accept. looks right", "WCA_1", "BS2_S") == ("agree", "WCA_1")
    assert s.read_verdict("REJECT", "WCA_1", "BS2_S") == ("reject", "BS2_S")      # keeps the INPUT code
    assert s.read_verdict("WCC", "WCA_2", "BS2_S") == ("call", "WCC")
    assert s.read_verdict("WCA_2", "WCA_2", "BS2_S") == ("agree", "WCA_2")
    assert s.read_verdict("SUSPECT TVD", "BS3_S", "BS2_S") == ("suspect_depth", "BS2_S")
    assert s.read_verdict("can't find", "WCA_1", np.nan)[0] == "hold"
    assert s.read_verdict(np.nan, "WCA_1", "OTHER") == ("hold", "OTHER")


def _cards(verdicts: list[str]) -> pd.DataFrame:
    n = len(verdicts)
    return pd.DataFrame({"card": range(1, n + 1), "section": "A", "basin": "delaware", "api10": [str(i) for i in range(n)],
                         "well_name": "W", "county": "Eddy", "input": "OTHER", "proposed": "AVA_0", "check": "agrees",
                         "verdict": verdicts})


def _changes(n: int) -> pd.DataFrame:
    return pd.DataFrame({"api10": [str(i) for i in range(n)], "basin": "delaware", "county": "Eddy", "well_name": "W",
                         "base52": "OTHER", "gm_code": "AVA_0", "in_box_extents": True})


def test_class_accepted_at_7_of_10_applies_to_uncarded_wells():
    _, fin, sc = s.score(_cards(["ACCEPT"] * 7 + ["REJECT"] * 3), _changes(25))
    assert sc["classes"]["delaware OTHER -> AVA_0"]["accepted"]
    assert (fin["basis"] == "v5_2_class_accepted").sum() == 15             # the 15 uncarded wells
    assert fin.loc[fin["basis"] == "carded_reject", "final_code"].eq("OTHER").all()


def test_class_rejected_at_6_of_10():
    _, fin, sc = s.score(_cards(["ACCEPT"] * 6 + ["REJECT"] * 4), _changes(25))
    assert not sc["classes"]["delaware OTHER -> AVA_0"]["accepted"]
    assert (fin["basis"] == "v5_2_class_accepted").sum() == 0
