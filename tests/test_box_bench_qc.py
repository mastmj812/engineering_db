"""DB-free tests for the pure rules in box/bench_qc.py (consensus v2 rule,
state-line binning, cohort derivation)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from box import bench_qc as q

P = q.ConsensusParams()


def test_local_bands_need_three_witnesses_and_coherence():
    bands = q.local_bands(
        {"WCA_1": np.array([10_000, 10_020, 10_040]), "WCA_2": np.array([10_300, 10_310]), "WCB_1": np.array([10_500, 10_900, 11_300, 11_700])},
        P,
    )
    assert set(bands) == {"WCA_1"}  # WCA_2 thin, WCB_1 incoherent (IQR > 150)
    assert bands["WCA_1"][1] == 3


def test_band_complexes_chain_merge():
    bands = {"A": (10_000.0, 5, 10.0), "B": (10_080.0, 5, 10.0), "C": (10_160.0, 5, 10.0), "D": (10_600.0, 5, 10.0)}
    cid = q.band_complexes(bands, 100.0)
    assert cid["A"] == cid["B"] == cid["C"] != cid["D"]


def test_score_agree_when_own_band_nearest():
    bands = {"WCA_1": (10_000.0, 8, 30.0), "WCA_2": (10_400.0, 6, 40.0)}
    assert q.score_subject(10_030, "WCA_1", bands, P)["cons_status"] == "agree"


def test_score_flag_when_sits_in_other_band_and_own_far():
    bands = {"WCA_1": (10_000.0, 8, 30.0), "WCA_2": (10_400.0, 6, 40.0)}
    r = q.score_subject(10_380, "WCA_1", bands, P)
    assert r["cons_status"] == "flag" and r["cons_suggest"] == "WCA_2"


def test_score_flag_when_own_band_absent():
    bands = {"WCA_2": (10_400.0, 6, 40.0), "WCB_1": (10_900.0, 6, 40.0)}
    r = q.score_subject(10_410, "WCA_1", bands, P)
    assert r["cons_status"] == "flag" and r["cons_suggest"] == "WCA_2"


def test_score_ambiguous_when_own_not_twice_as_far():
    bands = {"WCA_1": (10_000.0, 8, 30.0), "WCA_2": (10_200.0, 6, 40.0)}
    # 70 ft from WCA_2, 130 ft from own: own/nearest = 1.86 < 2 -> not a flag
    assert q.score_subject(10_130, "WCA_1", bands, P)["cons_status"] == "ambiguous"


def test_score_ambiguous_within_same_complex():
    bands = {"WCA_1": (10_000.0, 8, 30.0), "WCA_2": (10_080.0, 6, 40.0)}
    assert q.score_subject(10_075, "WCA_1", bands, P)["cons_status"] == "ambiguous"


def test_score_lith_swap_is_never_a_flag():
    bands = {"BS2_S": (11_000.0, 8, 30.0), "BS2_C": (11_400.0, 6, 40.0)}
    r = q.score_subject(11_390, "BS2_S", bands, P)
    assert r["cons_status"] == "ambiguous_lith" and r["cons_suggest"] == "BS2_C"


def test_score_off_band_and_no_evidence():
    assert q.score_subject(10_000, "WCA_1", {}, P)["cons_status"] == "no_evidence"
    bands = {"WCA_2": (10_400.0, 6, 40.0)}
    assert q.score_subject(10_000, "WCA_1", bands, P)["cons_status"] == "off_band"


def _frame(n_tx: int, n_nm: int, oil_tx: float, oil_nm: float) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    lat = np.concatenate([32.0 - rng.uniform(0.01, 0.4, n_tx), 32.0 + rng.uniform(0.01, 0.4, n_nm)])
    lon = -103.6 + rng.uniform(0, 0.5, n_tx + n_nm)
    oil = np.concatenate([np.full(n_tx, oil_tx), np.full(n_nm, oil_nm)])
    return pd.DataFrame(
        {
            "api10": [f"42{i:08d}" for i in range(n_tx + n_nm)],
            "well_name": "w", "operator": "o", "county": "c",
            "state_code": [42] * n_tx + [30] * n_nm,
            "formation_blueox": "WCA_1", "formation_blueox_base": "WCA_1", "formation_blueox_source": "novi",
            "formation_blueox_tvd_corrected": False,
            "planned": [False] * n_tx + [True] * n_nm,
            "tvd_ft": 10_000 + np.arange(n_tx + n_nm) % 7 * 13,
            "lateral_length_ft": 10_000, "first_production_date": date(2020, 1, 1), "last_reported_month": date(2026, 8, 1),
            "cum_12m_oil_bbl": oil * 10, "cum_24m_oil_bbl": oil * 15, "has_production_sharing": False,
            "mid_lon": lon, "mid_lat": lat,
            "sql23_assigned": "WCA_1", "sql23_nearest": "WCA_1", "sql23_assigned_med": 10_000.0, "sql23_nearest_med": 10_000.0,
            "sql23_assigned_n": 10, "sql23_nearest_n": 10, "sql23_assigned_gap": 10.0, "sql23_nearest_gap": 10.0, "sql23_corrected": False,
        }
    )


def test_prepare_cohort_and_round_tvd():
    d = q.prepare(_frame(5, 5, 50, 50))
    assert d["cohort"].all()
    assert d.attrs["asof"] == date(2026, 8, 1)
    d2 = _frame(2, 0, 50, 50)
    d2.loc[0, "tvd_ft"] = 10_000
    d2.loc[1, "tvd_ft"] = 10_015
    d2 = q.prepare(d2)
    assert d2["tvd_round"].tolist() == [True, False]
    assert d2.loc[0, "oil12_kft"] == pytest.approx(50.0)


def test_state_line_bins_and_border_flag():
    d = q.prepare(_frame(200, 200, 50, 50))
    bins = q.state_line_bins(d)
    assert bins["n_prod_hz"].sum() == 400
    assert bins.loc[bins["bin_lo_mi"] == -10, "side"].item() == "TX"
    assert bins.loc[bins["bin_lo_mi"] == 0, "planned_share"].item() == pytest.approx(1.0)
    assert q.border_step_verdict(bins)["verdict"] == "no_step"
    d2 = q.prepare(_frame(200, 200, 50, 80))
    assert q.border_step_verdict(q.state_line_bins(d2))["verdict"] == "flag"


def test_score_consensus_end_to_end_flags_mis_tag():
    # 8 clean WCA_2 witnesses at ~10,400 ft and one WCA_1-tagged well sitting among them
    base = _frame(9, 0, 50, 50)
    base["planned"] = False
    base["formation_blueox"] = ["WCA_2"] * 8 + ["WCA_1"]
    base["tvd_ft"] = [10_400 + i * 7 for i in range(8)] + [10_415]
    base["mid_lon"] = -103.6
    base["mid_lat"] = 31.8
    d = q.score_consensus(q.prepare(base))
    assert d["cons_status"].iloc[-1] == "flag"
    assert d["cons_suggest"].iloc[-1] == "WCA_2"
    assert d["cons_status"].iloc[0] == "agree"
