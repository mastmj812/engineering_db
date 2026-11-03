"""Step 21d: the Midland prospective definition is pinned, matches the method step 23 ships (step 21 rev 8 + D150 + D151), never
names a 2026 volume, and leaves every earlier frozen definition untouched."""

import json
import re
from pathlib import Path

import numpy as np

from box import prospective16 as p16
from box import prospective21 as ps
from box import prox_cont as pc
from box import step21 as st

GATE_21C = json.loads(Path("docs/box/step21c-2026-11-02/GATE_21C.json").read_text(encoding="utf-8"))
GATE_24A = json.loads(Path("docs/box/prox-continuous-2026-11-02/GATE_24A.json").read_text(encoding="utf-8"))


def test_definition_matches_the_pinned_digest():
    assert ps.digest() == ps.DIGEST, "box/prospective21.py DEFINITION changed after it was pinned — that is tuning after the fact"


def test_earlier_frozen_definitions_untouched():
    assert st.digest() == st.DIGEST == ps.DEFINITION["method"]["base"]["digest"]  # step 21 revision 8 at 5ceadc2
    assert pc.digest() == pc.DIGEST == ps.DEFINITION["method"]["proximity"]["digest"]  # step 24 revision 5 at 77d50a7
    assert p16.digest() == p16.DIGEST  # 13d (Delaware) frozen alongside
    assert ps.DEFINITION["method"]["base"]["frozen_sha"] == GATE_21C["frozen_sha"]
    assert ps.DEFINITION["method"]["proximity"]["frozen_sha"] == GATE_24A["frozen_sha"]


def test_groups_are_step21s_with_the_d151_tiers():
    g = ps.DEFINITION["cohort"]["groups"]
    assert list(g) == list(st.GROUPS)
    for name, x in g.items():
        bench, extent, _ = st.GROUPS[name]
        assert (x["bench"], x["extent_id"]) == (bench, extent), name
        assert x["tier_at_freeze"] == GATE_21C["tier"][name]["oil_gas"], name


def test_proximity_is_d150s_midland_curve():
    m = GATE_24A["curves"]["midland"]
    c = ps.D150_MIDLAND
    assert c["rule"] == m["rule"] == "R3"
    for k_ps, k_gate in (("f_min", "f_min"), ("d50_ft", "d50_ft"), ("k", "k"), ("level", "level")):
        assert c[k_ps] == m[k_gate], k_ps
    assert abs(c["a_below"] - m["a_below"]) < 1e-9 and abs(c["a_above"] - m["a_above"]) < 1e-9
    assert "oil" in ps.DEFINITION["method"]["proximity"]["form"] and "gas and water untouched" in ps.DEFINITION["method"]["proximity"]["form"]


def test_wca1_haircut_is_d151s_as_delivered():
    h = GATE_21C["haircut_step23"]["MID_WCA_1"]
    assert h["stream"] == "oil"
    assert {int(k): v for k, v in h["d102_factor"].items()} == ps.D102_WCA_1_OIL_AT_21C
    assert "AS DELIVERED" in ps.DEFINITION["method"]["haircut"]["MID_WCA_1"]["factor"]


def test_cohort_query_names_no_volume_column():
    sql = ps._COHORT_SQL
    named = set(re.findall(r"\bw\.([a-z_0-9]+)", sql))
    assert named <= set(ps.COHORT_COLUMNS_ALLOWED), named - set(ps.COHORT_COLUMNS_ALLOWED)
    for bad in ("cum_", "eur_", "peak_", "curated.production", "monthly"):
        assert bad not in sql


def test_verdict_and_schedule():
    v, s = ps.DEFINITION["verdict"], ps.DEFINITION["schedule"]
    assert v["graduation"] in ps.GRADUATION_OPTIONS and set(v["graduation_options"]) == set(ps.GRADUATION_OPTIONS)
    assert "consistency only" in v["keep_validated"]
    assert v["streams_judged"] == ["oil", "gas"] and ps.HORIZONS_JUDGED == (12, 24) and ps.MIN_PACKAGES == 30
    assert "2028-01-01" in s["cum12_judged_once"] and "2029-01-01" in s["cum24_judged_once"] and "never judged" in s["early_reads"]
    assert v["tier"]["NOT_JUDGED"] == "tier unchanged" and "never re-tune" in v["tier"]["validated_FAIL"]
    assert ps.DEFINITION["membership"]["governing"] == "scoring_time"


def test_a_uniform_haircut_cannot_change_the_consistency_verdict():
    """Package bias under forecasts x h is (1 + b) / h - 1 for the cohort AND every draw, so interval ends map the same way."""
    from scripts import box_prospective21_oc as oc

    rng = np.random.default_rng(0)
    e = rng.normal(-0.03, 0.25, 500)
    draws = rng.normal(-0.03, 0.02, 2000)
    for h in (0.979164, 0.95, 1.0):
        lo, hi = np.percentile(oc.scaled(draws, h), [2.5, 97.5])
        lo0, hi0 = np.percentile(draws, [2.5, 97.5])
        assert abs(lo - oc.scaled(lo0, h)) < 1e-12 and abs(hi - oc.scaled(hi0, h)) < 1e-12
        b = float(np.mean(e))
        assert (lo0 <= b <= hi0) == (lo <= oc.scaled(b, h) <= hi)


def test_gate_21d_answers_are_in_the_frozen_definition():
    d = ps.DEFINITION
    assert d["status"].startswith("FROZEN") and d["gate_21d"]["decision"] == "D152" and "D152" in d["decisions"]
    assert d["verdict"]["graduation"] == "consistency_or_accuracy" == ps.GRADUATION
    assert "+ 0.05" in d["verdict"]["accuracy"]["rule"] and "sampling error" in d["verdict"]["consistency"]["interval"]
    assert d["verdict"]["water"].startswith("reported only") and "drilled side" in d["method"]["proximity"]["configuration"]
    assert d["method"]["proximity"]["precedent"].startswith("every cohort well is scored")


def test_gate_21d_record_matches_the_frozen_digest():
    g = json.loads(Path("docs/box/step21d-2026-11-03/GATE_21D.json").read_text(encoding="utf-8"))
    assert g["decision"] == "D152" and g["definition_digest"] == ps.DIGEST and len(g["frozen_sha"]) == 40
