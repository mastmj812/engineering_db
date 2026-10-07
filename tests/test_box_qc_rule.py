"""DB-free tests for the ratified QC rule (box/qc_rule.py) and the GOR vote."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import bench_qc as q
from box import qc_rule as r


def _row(**kw):
    base = {
        "formation_blueox": "WCB_1", "cons_status": "flag", "cons_suggest": "WCA_2", "planned": False,
        "cons_witness": True, "sql23_nearest": "WCA_2", "cons_gor_vote": "none",
    }
    base.update(kw)
    return pd.Series(base)


def test_accepted_class_with_sql23_concurrence_reassigns():
    bench, action, witness, _ = r.decide(_row())
    assert (bench, action, witness) == ("WCA", "reassign", True)


def test_accepted_class_without_sql23_concurrence_keeps():
    bench, action, _, why = r.decide(_row(sql23_nearest="WCB_1"))
    assert (bench, action) == ("WCB_1", "keep") and "does not concur" in why


def test_gor_veto_keeps_tag():
    bench, action, _, why = r.decide(_row(cons_gor_vote="own"))
    assert (bench, action) == ("WCB_1", "keep") and "GOR" in why


def test_rejected_and_hold_classes_keep_tag():
    assert r.decide(_row(formation_blueox="WCA_1", cons_suggest="BS3_S", sql23_nearest="BS3_S"))[1] == "keep"
    assert r.decide(_row(formation_blueox="BS2_S", cons_suggest="BS1_S", sql23_nearest="BS1_S"))[1] == "keep"


def test_planned_survey_flag_is_tvd_suspect_not_retag():
    bench, action, witness, _ = r.decide(_row(planned=True))
    assert (bench, action, witness) == ("WCB_1", "tvd_suspect", False)


def test_bone_spring_to_wolfcamp_never_applied():
    bench, action, witness, _ = r.decide(_row(formation_blueox="BS2_S", cons_suggest="WCA_1", sql23_nearest="WCA_1"))
    assert (bench, action, witness) == ("BS2_S", "tvd_suspect", False)


def test_in_pool_swap_and_into_wcxy_are_moot():
    assert r.decide(_row(formation_blueox="WCA_1", cons_suggest="WCA_2"))[:2] == ("WCA", "keep")
    assert r.decide(_row(formation_blueox="WCA_1", cons_suggest="WCXY"))[:2] == ("WCA", "keep")


def test_card_verdict_outranks_class_rule():
    v = {"X": "AGREE", "Y": "REJECT", "Z": "REJECT"}
    # AGREE on a rejected class -> reassign; AGREE on a planned-survey well -> reassign (he judged it)
    assert r.decide(_row(api10="X", formation_blueox="WCA_1", cons_suggest="BS3_S", sql23_nearest="BS3_S"), v)[:2] == ("BS3_S", "reassign")
    assert r.decide(_row(api10="X", planned=True), v)[:2] == ("WCA", "reassign")
    # REJECT on an accepted class -> keep; REJECT on Bone Spring -> Wolfcamp -> tvd_suspect
    assert r.decide(_row(api10="Y"), v)[:2] == ("WCB_1", "keep")
    assert r.decide(_row(api10="Z", formation_blueox="BS2_S", cons_suggest="WCA_1", sql23_nearest="WCA_1"), v)[1:3] == ("tvd_suspect", False)
    # unknown api10 falls through to the class rule
    assert r.decide(_row(api10="Q"), v)[1] == "reassign"


def test_load_verdicts(tmp_path):
    p = tmp_path / "cards_sample.csv"
    pd.DataFrame({"api10": ["1", "2", "3", "4"], "verdict": ["AGREE", "REJECT. TVD wrong", "no conviction", None]}).to_csv(p, index=False)
    assert r.load_verdicts(p) == {"1": "AGREE", "2": "REJECT"}


def test_unflagged_well_keeps_pool_and_witness_status():
    assert r.decide(_row(cons_status="agree", cons_witness=False)) == ("WCB_1", "keep", False, "")


def test_gor_vote_rules():
    gors = {"WCA_1": (2000.0, 5), "WCB_1": (6000.0, 4)}
    assert q.gor_vote(2300.0, "WCA_1", "WCB_1", gors)["cons_gor_vote"] == "own"
    assert q.gor_vote(5500.0, "WCA_1", "WCB_1", gors)["cons_gor_vote"] == "suggest"
    assert q.gor_vote(np.nan, "WCA_1", "WCB_1", gors)["cons_gor_vote"] == "none"
    assert q.gor_vote(2300.0, "WCA_1", None, gors)["cons_gor_vote"] == "none"
    close = {"WCA_1": (2000.0, 5), "WCB_1": (2300.0, 4)}  # < 25 % apart: not separable
    assert q.gor_vote(2100.0, "WCA_1", "WCB_1", close)["cons_gor_vote"] == "none"


def test_apply_rule_and_summary_counts():
    df = pd.DataFrame([
        {"api10": "1", "formation_blueox": "WCB_1", "cons_status": "flag", "cons_suggest": "WCA_2", "planned": False, "cons_witness": True, "sql23_nearest": "WCA_2", "cons_gor_vote": "none", "cohort": True},
        {"api10": "2", "formation_blueox": "WCA_1", "cons_status": "agree", "cons_suggest": None, "planned": False, "cons_witness": True, "sql23_nearest": "WCA_1", "cons_gor_vote": "none", "cohort": True},
        {"api10": "3", "formation_blueox": "WCA_2", "cons_status": "flag", "cons_suggest": "WCB_1", "planned": True, "cons_witness": False, "sql23_nearest": "WCB_1", "cons_gor_vote": "none", "cohort": False},
    ])
    out = r.apply_rule(df)
    s = r.rule_summary(out, ("WCA",))
    assert s["WCA"]["n_tagged"] == 2 and s["WCA"]["n_after_rule"] == 3
    assert s["WCA"]["reassigned_in"] == 1 and s["WCA"]["tvd_suspect"] == 1
    assert s["WCA"]["depth_witnesses"] == 2
    assert s["unknown_classes"] == []
