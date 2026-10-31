"""BOX step 20b (Midland Spraberry): family wiring, the no-analogue card selection and the store's 20b rows (DB-free)."""

from __future__ import annotations

import pandas as pd

from box import basin as bsn
from box import family_qc as fq
from scripts import box_family_extent_store as st
from scripts.box_noanalogue_cards import judged_api10, noanalogue_classes


def test_spraberry_family_is_midland_in_stack_order_without_us() -> None:
    assert fq.FAMILIES["MID_SPR"] == ("MS", "JM", "LSSH", "DEAN")
    assert fq.FAMILY_BASIN["MID_SPR"] == bsn.MIDLAND
    assert "US" not in fq.FAMILIES["MID_SPR"]  # D127: emerging, no QC set, no extent


def _cmp() -> pd.DataFrame:
    return pd.DataFrame(
        {"n": [132, 54, 35, 21, 9, 30], "verdict": ["no analogue", "no analogue", "no analogue", "no analogue", "small", "unlike"]},
        index=pd.Index(["LSSH->JM", "WCA->DEAN", "LSSH->DEAN", "JM->MS", "JM->LSSH", "WCB_2->WCB_1"], name="swap_class"),
    )


def test_noanalogue_classes_needs_min_flags_and_no_analogue() -> None:
    assert noanalogue_classes(_cmp()) == ["LSSH->JM", "WCA->DEAN", "LSSH->DEAN", "JM->MS"]


def test_noanalogue_within_family_drops_the_wolfcamp_crossings() -> None:
    assert noanalogue_classes(_cmp(), within=fq.FAMILIES["MID_SPR"]) == ["LSSH->JM", "LSSH->DEAN", "JM->MS"]


def test_judged_api10_unions_every_file(tmp_path) -> None:
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    pd.DataFrame({"api10": ["4232900001", "4232900002"], "verdict": ["agree", ""]}).to_csv(a, index=False)
    pd.DataFrame({"api10": [" 4232900002", "4232900003"], "bench": ["WCD", "WCD"]}).to_csv(b, index=False)
    assert judged_api10([a, b]) == {"4232900001", "4232900002", "4232900003"}


def test_store_has_a_20b_row_per_spraberry_bench_with_an_extent_slot() -> None:
    assert set(st.MIDLAND_SCOPE_ROW_20B) == set(fq.FAMILIES["MID_SPR"])
    for bench, (members, reason) in st.MIDLAND_SCOPE_ROW_20B.items():
        assert members == "{" + bench + "}"  # D128: one bench each
        assert "{extent}" in reason
        assert "{extent}" not in reason.format(extent="generated v1 accepted")
    assert not set(st.MIDLAND_SCOPE_ROW_20B) & set(st.MIDLAND_SCOPE_ROW)  # the 20a rows are untouched


def test_midland_emerging_row_cites_d127() -> None:
    reason, decided = st.EMERGING_REASON["midland"]
    assert "D127" in reason and "never zero" in reason
    assert str(decided) == "2026-10-26"


def test_card_shows_own_tag_proposed_bench_and_adjacent_bands_only() -> None:
    from box.flag_cards import shown_benches

    bands = {"JM": (8175.0, 5, 35.0), "LSSH": (8506.0, 11, 30.0), "DEAN": (8700.0, 6, 40.0), "WCA_1": (8996.0, 10, 35.0),
             "BRNT": (9900.0, 8, 50.0), "MS": (7900.0, 6, 30.0)}
    assert shown_benches("DEAN", "LSSH", 8650.0, bands) == {"LSSH", "DEAN", "WCA_1"}  # Michael's example: no BRNT, no MS
    assert shown_benches("LSSH", "JM", 8290.0, bands) == {"JM", "LSSH", "DEAN"}
    # no own band: the subject's TVD picks the bands either side
    assert shown_benches("US", "MS", 8000.0, {k: v for k, v in bands.items() if k != "US"}) == {"US", "MS", "JM"}


def test_strike_section_keeps_laterals_crossing_the_line_and_signs_by_rule_v2() -> None:
    from box.flag_cards import strike_section

    lat0, lon0 = 32.0, -102.0
    dlon = 1.0 / (365_221.0 * 0.848)  # ft -> deg lon at 32 N

    def well(api: str, east_ft: float, north_ft: float, half_ft: float = 5000.0) -> dict:
        lon, lat = lon0 + east_ft * dlon, lat0 + north_ft / 365_221.0
        return {"api10": api, "mid_lon": lon, "mid_lat": lat, "surface_lon": lon, "surface_lat": lat + half_ft / 365_221.0,
                "bhl_lon": lon, "bhl_lat": lat - half_ft / 365_221.0}

    subj = pd.Series(well("S", 0, 0))
    nb = pd.DataFrame([well("E", 1500, 3000), well("W", -2000, -4000), well("FAR_N", 800, 12000), well("WIDE", 9000, 0)])
    sec, meta = strike_section(subj, nb)
    assert set(sec["api10"]) == {"E", "W"}  # FAR_N misses the line, WIDE is past 1.5 mi
    assert meta["reads"] == "W → E" and abs(meta["azimuth_deg"] % 180) < 1.0
    cx = dict(zip(sec["api10"], sec["cx_ft"]))
    assert cx["E"] > 1400 and cx["W"] < -1900  # + = east for a N-S lateral (sign rule v2)
    # no geometry on the subject -> radius view
    assert strike_section(pd.Series({"api10": "X", "mid_lon": lon0, "mid_lat": lat0}), nb) is None
