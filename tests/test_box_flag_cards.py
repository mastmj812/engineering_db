"""DB-free tests for the flag-class pooling and sampling rules (D19/D20)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import flag_cards as fc


def _flags(rows: list[tuple[str, str, str, float | None, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "api10": [f"42{i:08d}" for i in range(len(rows))],
            "cons_status": "flag",
            "formation_blueox": [r[1] for r in rows],
            "cons_suggest": [r[2] for r in rows],
            "cons_own_delta": [np.nan if r[3] is None else r[3] for r in rows],
            "cons_nearest_delta": [r[4] for r in rows],
            "state_code": 42,
            "planned": False,
        }
    )


def test_pool_and_never_into_wcxy():
    assert fc.pool("WCA_1") == fc.pool("WCA_2") == fc.pool("WCXY") == "WCA"
    assert fc.pool("WCB_1") == "WCB_1"
    f = fc.flag_classes(
        _flags([
            ("a", "WCA_1", "WCA_2", 200.0, 40.0),   # in-pool swap -> dropped
            ("b", "WCA_1", "WCXY", 200.0, 40.0),    # into WCXY -> dropped (D20)
            ("c", "WCXY", "WCB_1", 200.0, 40.0),    # WCA pool -> WCB_1 -> kept
            ("d", "WCB_1", "WCA_2", None, 40.0),    # inbound to WCA, own band absent -> kept, inf margin
            ("e", "BS2_S", "BS3_C", 300.0, 30.0),   # kept
            ("f", "WCB_1", "WCB_2", 300.0, 30.0),   # touches no pilot pool -> dropped
        ])
    )
    assert sorted(f["swap_class"]) == ["BS2_S->BS3_C", "WCA->WCB_1", "WCB_1->WCA"]
    assert np.isinf(f.loc[f["swap_class"] == "WCB_1->WCA", "margin_ratio"]).all()


def test_sample_class_is_deterministic_and_spans_margin():
    rows = [("x", "WCA_1", "WCB_1", float(10 * k + 50), 25.0) for k in range(40)]
    f = fc.flag_classes(_flags(rows))
    s1 = fc.sample_class(f)
    s2 = fc.sample_class(f)
    assert list(s1["api10"]) == list(s2["api10"])
    assert len(s1) == fc.CARDS_PER_CLASS
    assert s1["margin_ratio"].iloc[0] == f["margin_ratio"].min()
    assert s1["margin_ratio"].iloc[-1] == f["margin_ratio"].max()
    small = fc.flag_classes(_flags(rows[:5]))
    assert len(fc.sample_class(small)) == 5
