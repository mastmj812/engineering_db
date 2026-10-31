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
