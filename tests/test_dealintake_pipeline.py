"""dealintake.pipeline pure helpers: Novi multi-segment summary, edge trigger."""

import pytest

pytest.importorskip("shapely")
pytest.importorskip("yaml")

from dealintake.config import load
from dealintake.pipeline import _edge_fired, _novi_summary

CFG = load()


def _p(stick, stream, seg, d, b=1.2, q=1000.0, ll=10_000.0, oil=400_000.0, gas=2_000_000.0):
    return {"stick_id": stick, "stream": stream, "segment": seg, "d_nom": d, "b": b, "q_start": q,
                "day_start": 0 if seg == 1 else 540, "day_stop": 540 if seg == 1 else 6000,
                "ll_ft": ll, "oil_eur": oil, "gas_eur": gas}


def test_novi_summary_reports_cap_share_and_segment2():
    params = [
        _p(1, "oil", 1, 3.65), _p(1, "oil", 2, 0.60),
        _p(2, "oil", 1, 3.65), _p(2, "oil", 2, 0.55),
        _p(3, "oil", 1, 2.10), _p(3, "oil", 2, 0.50),
    ]
    s = _novi_summary(params)["oil"]
    assert s["n"] == 3
    assert s["seg1_at_cap_frac"] == pytest.approx(2 / 3)
    assert s["seg2_di_nominal"] == pytest.approx(0.55)
    assert s["eur_per_1000ft"] == pytest.approx(40_000.0)   # 400k bbl / 10k ft x 1,000
    assert s["qi_per_1000ft"] == pytest.approx(100.0)
    assert 0.0 < s["di_effective"] < 1.0


def test_novi_summary_skips_streams_without_segment1():
    assert _novi_summary([_p(1, "gas", 2, 0.5)]) == {}


def test_edge_trigger():
    far = [{"dist_nearest_ft": 20_000, "pdp_count_1mi": 0, "pdp_count_5mi": 3}]
    near = [{"dist_nearest_ft": 800, "pdp_count_1mi": 4, "pdp_count_5mi": 40}]
    assert _edge_fired(far, CFG)[0] is True
    fired, sig = _edge_fired(near, CFG)
    assert fired is False and sig["ring_decay"] == pytest.approx(0.1)


def test_tc_groups_cli_parsing():
    from dealintake.cli import _tc_groups

    assert _tc_groups(["WCA_2=toucan_1"]) == {"WCA_2": [["toucan_1"]]}
    assert _tc_groups(["WCA_1=a,b;c"]) == {"WCA_1": [["a", "b"], ["c"]]}
    with pytest.raises(SystemExit):
        _tc_groups(["WCA_2"])
