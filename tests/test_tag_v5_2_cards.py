"""Listed follow-up cards (scripts.tag_v5_2_cards.select_listed): the optional input and also_show columns."""

from __future__ import annotations

import pandas as pd

from scripts import tag_v5_2_cards as t


def test_select_listed_keeps_order_input_and_also_show():
    d = pd.DataFrame({"api10": ["1", "2", "3"], "base52": ["BS3_S", "OTHER", "WCA_1"]})
    listed = pd.DataFrame({"api10": ["3", "1"], "proposed": ["WCXY", "BS3_C"], "note": ["n3", "n1"],
                           "input": [None, "BS3_S"], "also_show": [None, "BS2_S"]})
    ch = t.select_listed(d, listed, first_card=5)
    assert ch["api10"].tolist() == ["3", "1"]
    assert ch["card"].tolist() == [5, 6]
    assert ch["base52"].tolist() == ["WCA_1", "BS3_S"]          # input falls back to the frame's tag
    assert ch["also_show"].isna().tolist() == [True, False]
    assert ch.loc[ch["api10"] == "1", "also_show"].item() == "BS2_S"
