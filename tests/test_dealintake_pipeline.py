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


def test_dossier_shows_gas_arps_and_ratio_side_by_side():
    from dealintake.render.dossier import _stream_rows

    G = {
        "tc_preview_n_wells": 20,
        "tc_preview": {"gas": {"qi": 500.0, "Di": 1.2, "b": 1.0, "eur_per_unit": 400_000.0}},
        "tc_preview_gas_ratio": {"mode": "ratio", "sub_mode": "exp_cum", "r2": 0.71,
                                 "eur_per_unit": 600_000.0, "implied_effective_decline_yr1": 0.52},
    }
    rows = [r for r in _stream_rows(G) if r[0] == "gas"]
    assert [r[1].split(" (")[0] for r in rows] == ["anduin TC preview", "anduin TC — ratio to cum oil"]
    assert "1.50x Arps EUR" in rows[1][1] and "R² 0.71" in rows[1][1]
    assert rows[1][4] == "52.0%" and rows[1][6] == 600_000.0


class _FakeAnduin:
    def __init__(self, resp=None, err=None):
        self.resp, self.err, self.calls = resp, err, []

    def transfer_cohort(self, api10s, cutoff):
        self.calls.append((list(api10s), cutoff))
        if self.err:
            from dealintake.clients.anduin import AnduinError
            raise AnduinError(self.err)
        return self.resp


def _pool():
    from datetime import date
    old = [{"api10": f"L{i}", "first_production_date": date(2021, 6, 1), "proppant_lbs_per_ft": 2000.0} for i in range(6)]
    new = [{"api10": f"S{i}", "first_production_date": date(2025, 3, 1), "proppant_lbs_per_ft": 2800.0} for i in range(2)]
    return old + new


def test_transfer_summary_uses_whole_pool_and_flags_vintage_gap():
    from dealintake.pipeline import _transfer

    fake = _FakeAnduin(resp={
        "written_api10s": ["S0", "S1"], "skipped_locked": [], "skipped_no_peak": [],
        "long_api10s": [f"L{i}" for i in range(6)], "short_api10s": ["S0", "S1"],
        "donors": [{"stream": "oil", "donor_count": 6, "cohort_di": 2.8, "cohort_b": 1.0}],
    })
    out = _transfer(fake, _pool(), 9)
    assert fake.calls == [([c["api10"] for c in _pool()], 9)]       # one batch = one donor pool
    assert (out["n_long"], out["n_short"], out["written"]) == (6, 2, ["S0", "S1"])
    assert out["long_proppant_lbs_ft_median"] == 2000.0 and out["short_proppant_lbs_ft_median"] == 2800.0
    assert "yr gap" in out["flag"]                                   # 2021.4 vs 2025.2 >= 3 yr


def test_transfer_thin_donors_is_recorded_not_fatal():
    from dealintake.pipeline import _transfer

    out = _transfer(_FakeAnduin(err="POST ... -> 422: insufficient_donor_cohort"), _pool(), 9)
    assert "NOT applied" in out["flag"] and "422" in out["error"]
