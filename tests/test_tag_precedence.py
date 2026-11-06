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
