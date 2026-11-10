"""box.tag_precedence — rule v5 on synthetic wells (no DB)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import tag_precedence as tp

MI = 1609.344


def _w(rows: list[tuple[str, str, float, float, float]], county: str = "Reeves", basin: str = "delaware") -> pd.DataFrame:
    """(novi_code, env_code, depth, x_mi, y_mi); sql16 = Novi unless Novi is None."""
    d = pd.DataFrame(rows, columns=["novi_code", "env_code", "depth_ft", "x", "y"])
    d["x"], d["y"] = d["x"] * MI, d["y"] * MI
    d["basin"], d["county"], d["evidence"] = basin, county, True
    d["sql16"] = d["novi_code"].where(d["novi_code"].notna(), d["env_code"])
    d["novi_raw"], d["env_raw"] = d["novi_code"], d["env_code"]  # one string per code unless a test says otherwise
    return d


def _ring(code: str, z: float, cx: float = 0.0, n: int = 6, rad: float = 0.6) -> list:
    return [(code, code, z + k, cx + rad * np.cos(2 * np.pi * k / n), rad * np.sin(2 * np.pi * k / n)) for k in range(n)]


def test_units_and_span():
    assert tp.unit("delaware", "BS3_C") == "BS3" and tp.unit("delaware", "WCA_2") == "WCA" and tp.unit("midland", "WCA_1") == "WCA_1"
    assert tp.unit("delaware", "OTHER") is None and tp.unit("delaware", None) is None
    assert tp.span("delaware", "AVA", "WCB") == 5 and tp.span("midland", "LSSH", "JM") == 1


def test_cases_a_b_c():
    d = _w([("WCA_1", None, 12_000, 9, 9), ("WCB_1", "WCB_1", 12_300, 9, 9.1), ("WCA_1", "WCA_2", 12_050, 9, 9.2)])
    out, _ = tp.assign(d)
    assert out["basis"].tolist() == ["single_vendor", "agree", "subbench_vendor"]
    assert out["v5"].tolist() == ["WCA_1", "WCB_1", "WCA_1"] and out.loc[1, "confidence"] == "high"


def test_magnolia_case_depth_sides_with_novi():
    # Novi Wolfcamp B, Enverus Middle Avalon, at Wolfcamp B depth; witnesses of both units around it
    rows = _ring("WCB_1", 12_900) + _ring("AVA_1", 9_800) + [("WCB_1", "AVA_1", 12_880, 0, 0)]
    d = _w(rows)
    d.loc[d.index[-1], "sql16"] = "AVA_1"  # sql/16 took Enverus (coarse Novi)
    out, _ = tp.assign(d)
    x = out.iloc[-1]
    assert x["case"] == "D" and x["call"] == "Novi" and x["v5"] == "WCB_1" and x["basis"] == "depth"


def test_conflict_wells_are_never_witnesses():
    # a cluster of mis-named wells (Novi WCB, Enverus AVA, at WCB depth) must not build an AVA reference
    rows = _ring("WCB_1", 12_900) + [("WCB_1", "AVA_1", 12_880 + k, 0.1 * k, 0) for k in range(5)]
    out, _ = tp.assign(_w(rows))
    assert out.iloc[-5:]["z_env"].isna().all()  # no AVA witnesses -> no AVA depth


def test_pattern_learned_and_applied_where_depth_cannot_decide():
    rows = []
    for k in range(25):  # 25 decided Midland LSSH(Novi)-vs-JM(Enverus) wells, all at JM depth
        cx = 10.0 * k
        rows += _ring("JM", 8_000, cx) + _ring("LSSH", 8_400, cx) + [("LSSH", "JM", 8_005, cx, 0)]
    rows += [("LSSH", "JM", 8_005, 900.0, 0)]  # far from any witness: no control
    out, table = tp.assign(_w(rows, basin="midland", county="Martin"))
    t = table[(table["u_novi"] == "LSSH") & (table["u_env"] == "JM")].iloc[0]
    assert t["winner"] == "Enverus" and t["decided"] == 25
    x = out.iloc[-1]
    assert x["call"] == "no control" and x["basis"] == "pattern" and x["v5"] == "JM"


def test_unlearned_conflict_is_unresolved():
    d = _w([("WCB_1", "AVA_1", 12_900, 0, 0), ("WCA_1", "WCB_1", 12_100, 50, 0)])
    out, _ = tp.assign(d)
    assert (out["basis"] == "unresolved").all() and out["v5"].tolist() == ["WCB_1", "WCA_1"]


def test_other_vendor_needs_depth():
    rows = _ring("AVA_0", 9_600) + [(None, "AVA_0", 9_610, 0, 0), (None, "AVA_0", 8_000, 0.05, 0)]
    d = _w(rows)
    d.loc[d.index[-2:], "novi_code"] = "OTHER"
    d.loc[d.index[-2:], "sql16"] = "OTHER"
    out, _ = tp.assign(d)
    assert out.iloc[-2]["basis"] == "depth_vs_other" and out.iloc[-2]["v5"] == "AVA_0"
    assert out.iloc[-1]["basis"] == "other_vendor_kept" and out.iloc[-1]["v5"] == "OTHER"


def test_sql23_correction_kept_unless_depth_decides():
    d = _w([("WCA_1", None, 12_000, 0, 0)])
    d["sql23_code"] = ["BS2_S"]
    out, _ = tp.assign(d)
    assert out.loc[0, "v5"] == "BS2_S" and out.loc[0, "basis"] == "sql23_kept"


def test_guards():
    d = _w([("WDFD", "BRNT_X", 14_000, 0, 0)])
    d.loc[0, "env_code"] = "BRNT"
    out, _ = tp.assign(d)
    assert out.loc[0, "basis"] == "guard" and out.loc[0, "flag"] == "protected"
    d = _w([("BS3_S", "WCA_1", 11_000, 0, 0)], county="Lea")
    out, _ = tp.assign(d)
    assert out.loc[0, "flag"] == "rule_b_pending" and out.loc[0, "v5"] == "BS3_S"


def test_other_case_respects_the_protected_guard():
    rows = _ring("BRNT", 14_000) + [(None, "BRNT", 14_010, 0, 0)]
    d = _w(rows)
    d.loc[d.index[-1], ["novi_code", "sql16"]] = "OTHER"
    out, _ = tp.assign(d)
    assert out.iloc[-1]["basis"] == "guard" and out.iloc[-1]["v5"] == "OTHER"


def test_v5_card_counting_is_unit_level():
    from scripts.tag_v5_score import unit_verdict

    assert unit_verdict("delaware", "WCA_1", "WCA_2") == ("agree", "WCA_2")  # same unit, other sub-bench
    assert unit_verdict("delaware", "WCA_1", "WCA_1") == ("agree", None)
    assert unit_verdict("delaware", "WCA_1", "WCB_1") == ("reject", None)
    assert unit_verdict("midland", "WCB_1", "WCA_1") == ("reject", None)  # Midland WCA_1 is its own unit
    assert unit_verdict("midland", "JM", "reject, too far") == ("reject", None)
    assert unit_verdict("delaware", "WCA_1", float("nan")) == ("", None)  # a skipped card is a hold
    assert unit_verdict("delaware", "WCA_1", "can't tell from this") == ("", None)


# --- v5.1 sub-bench step (box.tag_subbench) ---------------------------------------------------------------------

def _sb(rows, basin="delaware"):
    """(novi_raw, novi_code, env_raw, env_code, depth, x_mi, y_mi, tag)"""
    d = pd.DataFrame(rows, columns=["novi_raw", "novi_code", "env_raw", "env_code", "depth_ft", "x", "y", "tag"])
    d["x"], d["y"] = d["x"] * MI, d["y"] * MI
    d["basin"], d["evidence"], d["src"] = basin, True, None
    return d


def _wring(env_raw, env_code, z, n=6, rad=0.6):
    return [("WOLFCAMP A", "WCA_1", env_raw, env_code, z + k, rad * np.cos(2 * np.pi * k / n), rad * np.sin(2 * np.pi * k / n), env_code)
            for k in range(n)]


def test_subbench_placeholder_list_is_pinned():
    from box import tag_subbench as ts1

    assert ts1.PLACEHOLDER == {("delaware", "novi", "WOLFCAMP A"), ("delaware", "novi", "WOLFCAMP B"), ("midland", "novi", "WOLFCAMP B"),
                               ("delaware", "env", "2ND BONE SPRING"), ("delaware", "env", "3RD BONE SPRING")}
    assert ts1.unit_codes("delaware")["WCA"] == ["WCA_1", "WCA_2", "WCXY"] and "WCA_1" not in ts1.unit_codes("midland")


def test_card_62_placeholder_goes_to_wca2_by_depth():
    from box import tag_subbench as ts1

    # witnesses: Novi coarse WOLFCAMP A + Enverus specific UPPER (WCA_1, 9,226) / LOWER (WCA_2, 9,381)
    rows = _wring("WOLFCAMP A UPPER", "WCA_1", 9_226) + _wring("WOLFCAMP A LOWER", "WCA_2", 9_381)
    rows += [("WOLFCAMP A", "WCA_1", "WOLFCAMP B UPPER", "WCB_1", 9_461, 0, 0, "WCA_1")]  # v5 kept Novi's placeholder
    out = ts1.assign(_sb(rows), "tag").iloc[-1]
    assert out["placeholder"] and out["sb_basis"] == "subbench_depth" and out["sb_code"] == "WCA_2"


def test_specific_or_human_codes_are_not_placeholders():
    from box import tag_subbench as ts1

    d = _sb([("WOLFCAMP A", "WCA_1", "WOLFCAMP A UPPER", "WCA_1", 9_300, 0, 0, "WCA_1"),   # Enverus names WCA_1
             ("WOLFCAMP A", "WCA_1", None, None, 9_300, 0, 0, "WCA_1"),                     # placeholder, single vendor
             ("WOLFCAMP A", "WCA_1", None, None, 9_300, 0, 0, "WCA_1"),                     # same, but carded
             ("SECOND BONE SPRING", "BS2_S", "2ND BONE SPRING", "BS2_S", 9_000, 0, 0, "BS2_S")])  # Novi names the sand
    d.loc[2, "src"] = "carded_call"
    out = ts1.assign(d, "tag")
    assert out["placeholder"].tolist() == [False, True, False, False]
    assert out.loc[1, "sb_basis"] == "subbench_default" and out.loc[1, "sb_code"] == "WCA_1"  # no witnesses -> kept, flagged


def test_thin_split_without_margin_keeps_the_placeholder():
    from box import tag_subbench as ts1

    rows = _wring("WOLFCAMP A UPPER", "WCA_1", 9_300) + _wring("WOLFCAMP A LOWER", "WCA_2", 9_380)
    rows += [("WOLFCAMP A", "WCA_1", None, None, 9_345, 0, 0, "WCA_1")]
    out = ts1.assign(_sb(rows), "tag").iloc[-1]
    assert out["sb_basis"] == "subbench_default" and out["sb_code"] == "WCA_1"


def test_inverted_subbench_references_withdraw_the_call():
    from box import tag_subbench as ts1

    # WCA_2 witnesses SHALLOWER than WCA_1 (card 22, STATE NEAL LETHCO 3405A-142 2H): no depth call
    rows = _wring("WOLFCAMP A UPPER", "WCA_1", 9_062) + _wring("WOLFCAMP A LOWER", "WCA_2", 8_772)
    rows += [("WOLFCAMP A", "WCA_1", None, None, 8_708, 0, 0, "WCA_1")]
    out = ts1.assign(_sb(rows), "tag").iloc[-1]
    assert out["sb_basis"] == "subbench_inverted" and out["sb_code"] == "WCA_1"


def test_string_keyed_patterns_do_not_pool_strings_of_one_unit():
    # Two Novi strings both map to LSSH. Against Enverus JM, depth backs string S1 every time and S2 about half the
    # time. Pooled by unit, Novi's share is 37/50 = 0.74 < 0.75: no winner. Keyed by string, S1 learns Novi.
    rows, raw = [], []
    for k in range(50):
        cx = 10.0 * k
        s1 = k < 25
        z = 8_395 if s1 or k >= 38 else 8_005  # S1: 25 Novi; S2: 13 Enverus (k 25..37) + 12 Novi (k 38..49)
        block = _ring("JM", 8_000, cx) + _ring("LSSH", 8_400, cx) + [("LSSH", "JM", z, cx, 0)]
        rows += block
        raw += [("W", "W")] * (len(block) - 1) + [("S1" if s1 else "S2", "JM-STR")]
    rows += [("LSSH", "JM", 9_000, 900.0, 0)]  # no control, string S1
    raw += [("S1", "JM-STR")]
    d = _w(rows, basin="midland", county="Martin")
    d["novi_raw"], d["env_raw"] = [a for a, _ in raw], [b for _, b in raw]
    by_unit, t_unit = tp.assign(d, tp.V5(pattern_key="unit"))
    by_str, t_str = tp.assign(d)
    assert t_unit.loc[(t_unit["u_novi"] == "LSSH") & (t_unit["u_env"] == "JM"), "winner"].isna().all()
    assert by_unit.iloc[-1]["basis"] == "unresolved"
    s = t_str.set_index("novi_raw")
    assert s.loc["S1", "winner"] == "Novi" and pd.isna(s.loc["S2", "winner"])
    assert by_str.iloc[-1]["basis"] == "pattern" and by_str.iloc[-1]["v5"] == "LSSH"


def test_pattern_key_is_validated():
    import pytest
    with pytest.raises(ValueError):
        tp.pattern_keys(tp.V5(pattern_key="county"))


def test_policy_v1_is_string_keyed_and_complete():
    p = tp.load_policy()
    assert tp.RULE.pattern_key == "string" and len(p) == 19
    assert set(tp.pattern_keys()) <= set(p.columns) and p["winner"].isin(["Novi", "Enverus"]).all()
    assert not p.duplicated(tp.pattern_keys()).any()


def test_frozen_policy_wins_over_the_data_and_drift_reports_it():
    rows = []
    for k in range(25):  # the data learns Enverus (JM) for LSSH vs JM ...
        cx = 10.0 * k
        rows += _ring("JM", 8_000, cx) + _ring("LSSH", 8_400, cx) + [("LSSH", "JM", 8_005, cx, 0)]
    rows += [("LSSH", "JM", 8_005, 900.0, 0)]
    d = _w(rows, basin="midland", county="Martin")
    frozen = pd.DataFrame([{"basin": "midland", "novi_raw": "LSSH", "env_raw": "JM", "u_novi": "LSSH", "u_env": "JM",
                            "winner": "Novi"}])  # ... but the frozen policy says Novi
    out, learned = tp.assign(d, policy=frozen)
    assert out.iloc[-1]["basis"] == "pattern" and out.iloc[-1]["v5"] == "LSSH"
    dr = tp.drift(learned, frozen)
    assert len(dr) == 1 and dr.iloc[0]["change"] == "flipped" and dr.iloc[0]["learned"] == "Enverus"
    assert len(tp.drift(learned, frozen.iloc[0:0])) == 1 and tp.drift(learned, frozen.iloc[0:0]).iloc[0]["change"] == "gained"
