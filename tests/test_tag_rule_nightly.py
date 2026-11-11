"""The nightly tag rule (W2): seeds reproduce the card folders, the rule gates on accepted classes keyed on the vendor
tag, human calls are never applied from the rule, the circuit breaker and the staleness guard, and the SQL wiring."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from box import tag_rule_run as tr
from box import tag_scoreboard as sb
from scripts import tag_rule_seeds as seeds

SQL = sb.ROOT / "sql"


# ---------------------------------------------------------------------------- seeds


def test_committed_seeds_match_the_card_folders():
    assert seeds.main(["--check"]) == 0


def test_seed_invariants():
    built = seeds.build()
    ov = built[seeds.OVERRIDES]
    assert not ov["api10"].duplicated().any()
    block = ov[ov["note"].str.startswith(seeds.BLOCK)]
    ex = built[seeds.EXCLUSIONS]
    assert set(block["api10"]).isdisjoint(ex["api10"])          # a SUSPECT TVD well is an exclusion, not a call
    assert len(ex) == 12
    assert {"4232943352", "4232945905", "4232946987", "4246139770"}.isdisjoint(ov["api10"])  # stale rows stay out
    sq = block.set_index("api10")["corrected_code"]
    assert sq["3001554499"] == "WCA_1" and sq["3002544497"] == "WCXY"  # later card sets win (SQUINTS, SALADO DRAW)
    cl = built[seeds.CLASSES]
    s1 = cl[cl["step"] == 1]
    assert len(s1) == 15 and (s1["decision"] == "accept").sum() == 13
    rej = set(zip(s1.loc[s1["decision"] == "reject", "from_code"], s1.loc[s1["decision"] == "reject", "to_code"],
                  s1.loc[s1["decision"] == "reject", "basis"], strict=True))
    assert rej == {("WCB_1", "WCA_1", "depth"), ("BS2_C", "BS1_S", "pattern")}
    assert cl[cl["step"] == 3][["from_code", "to_code", "decision"]].values.tolist() == [["OTHER", "AVA_0", "accept"]]
    assert len(built[seeds.POLICY]) == 19 and set(built[seeds.POLICY]["policy_version"]) == {1}


@pytest.mark.parametrize("text,kind,code", [
    ("ACCEPT", "call", "P"), ("agree", "call", "P"), ("WCB_2", "call", "WCB_2"), ("BS3_S. thin control", "call", "BS3_S"),
    ("REJECT", "call", "K"), ("SUSPECT TVD", "exclusion", None), ("can't find", "hold", None), (np.nan, "hold", None),
])
def test_verdict_reading(text, kind, code):
    assert seeds.read(text, "P", "K") == (kind, code)


# ---------------------------------------------------------------------------- the rule on a synthetic frame


def _well(api, x, depth, novi, env, novi_raw=None, env_raw=None, sql16=None):
    return {"api10": api, "basin": "delaware", "county": "Reeves", "x": float(x), "y": 0.0, "depth_ft": float(depth),
            "depth_source": "tvd_ft", "tvd_ft": float(depth), "planned": False, "in_frame": True, "in_box_extents": True,
            "novi_code": novi, "env_code": env, "novi_raw": novi_raw or novi, "env_raw": env_raw or env,
            "sql16": sql16 or novi, "pts": [(float(x), 0.0)]}


def _frame() -> pd.DataFrame:
    rows = [_well(f"W{i}", 100 * i, 8000 + i, "BS2_S", "BS2_S") for i in range(5)]
    rows += [_well(f"V{i}", 100 * i, 9000 + i, "BS3_C", "BS3_C") for i in range(5)]
    # Novi BS3_C (a non-trigger string, so sql/16 = BS3_C) vs Enverus BS2_S, landing on the BS2 witnesses
    rows += [_well("S1", 250, 8010, "BS3_C", "BS2_S", "THIRD BONE SPRING LIME", "2ND BONE SPRING SAND"),
             _well("S2", 260, 8012, "BS3_C", "BS2_S", "THIRD BONE SPRING LIME", "2ND BONE SPRING SAND")]
    return pd.DataFrame(rows)


def _policy(accept: bool = True, human: dict | None = None) -> tr.Policy:
    cls = pd.DataFrame([{"step": 1, "basin": "delaware", "from_code": "BS3_C", "to_code": "BS2_S", "basis": "depth",
                         "decision": "accept" if accept else "reject", "agree": 5, "judged": 5, "class_wells": 2, "card_set": "t"}])
    pat = pd.DataFrame(columns=["basin", "novi_raw", "env_raw", "u_novi", "u_env", "decided", "novi_share", "winner"])
    ov = pd.DataFrame({"api10": list((human or {}).keys()), "corrected_code": list((human or {}).values())})
    return tr.Policy(patterns=pat, classes=cls, overrides=ov,
                     exclusions=pd.DataFrame(columns=["api10", "depth_ft", "depth_source"]), version=1)


def test_accepted_class_applies_on_the_vendor_tag():
    d, _ = tr.run(_frame(), _policy(human={"S2": "BS3_C"}))
    s1, s2 = d.set_index("api10").loc["S1"], d.set_index("api10").loc["S2"]
    assert s1["v5"] == "BS2_S" and s1["basis"] == "depth"
    assert bool(s1["applied"]) and s1["applied_code"] == "BS2_S" and s1["applied_step"] == 1
    assert s1["applied_class"] == "delaware BS3_C->BS2_S (depth)"
    assert not bool(s2["applied"]) and s2["accepted_basis"] == "override"   # a human call is never a rule row's code
    rows = tr.rule_rows(d).set_index("api10")
    assert rows.loc["S2", "human_call"] == "BS3_C" and rows.loc["S2", "applied_code"] is None


def test_rejected_or_undecided_class_is_not_applied():
    d, _ = tr.run(_frame(), _policy(accept=False))
    s1 = d.set_index("api10").loc["S1"]
    assert not bool(s1["applied"]) and not bool(s1["step1_queue"])  # decided (rejected): no card needed
    p = _policy()
    p = tr.Policy(patterns=p.patterns, classes=p.classes.iloc[0:0], overrides=p.overrides, exclusions=p.exclusions, version=1)
    d, _ = tr.run(_frame(), p)
    s1 = d.set_index("api10").loc["S1"]
    assert not bool(s1["applied"]) and bool(s1["step1_queue"])


def test_depth_exclusion_takes_the_well_out_of_the_frame():
    f = _frame()
    wells = f.drop(columns=["in_frame", "x", "y", "depth_ft", "depth_source", "novi_code", "env_code", "novi_raw",
                            "env_raw", "in_box_extents"]).rename(columns={"sql16": "vendor"})
    wells["lat_tvd_p50_ft"] = np.nan
    vendors = f[["api10", "novi_raw", "env_raw", "novi_code", "env_code"]]
    extents = pd.DataFrame(columns=["basin", "wkt"])
    ex = pd.DataFrame({"api10": ["S1", "W1"], "depth_ft": [8010.0, 1.0], "depth_source": ["tvd_ft", "tvd_ft"]})
    w = tr.frame(wells, vendors, extents, ex)
    w = w.set_index("api10")
    assert bool(w.loc["S1", "depth_excluded"]) and not bool(w.loc["S1", "in_frame"])
    assert bool(w.loc["W1", "exclusion_lapsed"]) and bool(w.loc["W1", "in_frame"])   # the depth changed: judged again


# ---------------------------------------------------------------------------- breaker + staleness guard


def test_breaker():
    prev = pd.DataFrame({"api10": [str(i) for i in range(300)], "applied_code": ["A"] * 300})
    new = prev.copy()
    assert tr.breaker(None, new, set())["first_run"]
    new.loc[:250, "applied_code"] = "B"                    # 251 changes
    b = tr.breaker(prev, new, set(), floor=200)
    assert b["changed"] == 251 and b["tripped"] and b["limit"] == 200
    b = tr.breaker(prev, new, {str(i) for i in range(100)}, floor=200)  # wells whose own inputs moved don't count
    assert b["changed"] == 151 and not b["tripped"]
    assert tr.breaker(prev, new, set(), floor=200, share=0.9)["limit"] == 270


def test_inputs_match():
    rule = pd.DataFrame({"api10": ["1", "2", "3", "4"], "novi_raw": ["A", "A", "A", None], "env_raw": ["E", "E", "E", "E"],
                         "tvd_ft": [8000.0, 8000.0, 8000.0, None], "planned": [False] * 4})
    wells = pd.DataFrame({"api10": ["1", "2", "3", "4"], "tvd_ft": [8000, 8001, 8000, None], "planned": [False, False, True, None]})
    vendors = pd.DataFrame({"api10": ["1", "2", "3", "4"], "novi_raw": ["A", "A", "A", None], "env_raw": ["E"] * 4})
    assert tr.inputs_match(rule, wells, vendors).tolist() == [True, False, False, True]


# ---------------------------------------------------------------------------- SQL wiring


def test_sql16_reads_rule_behind_switch_and_guard():
    s = (SQL / "16_formation_blueox.sql").read_text(encoding="utf-8")
    assert "LEFT JOIN curated.formation_tag_rule rr" in s and "AND sw.use_rule" in s
    for guard in ("rr.novi_raw IS NOT DISTINCT FROM w.formation", "rr.env_raw  IS NOT DISTINCT FROM w.env_interval",
                  "abs(rr.tvd_ft - w.tvd_ft::numeric) <= 0.5", "rr.planned = COALESCE(w.directional_survey_is_planned, FALSE)"):
        assert guard in s
    i_ovr, i_rule = s.index("COALESCE(ovr.corrected_code,"), s.index("rr.applied_code,")
    assert i_ovr < i_rule                                     # override > rule > crosswalk


def test_sql23_guards():
    s = (SQL / "23_formation_blueox_tvd.sql").read_text(encoding="utf-8")
    assert "NOT EXISTS (SELECT 1 FROM ref.formation_tag_overrides o WHERE o.api10 = scored.api10)" in s
    assert "NOT COALESCE((SELECT sw.use_rule FROM ref.formation_tag_switch sw), FALSE)" in s


def test_sql72_tables_and_switch_default_off():
    s = (SQL / "72_formation_tag_rule.sql").read_text(encoding="utf-8")
    for t in ("ref.formation_tag_policy", "ref.formation_tag_class", "ref.formation_tag_depth_exclusions",
              "ref.formation_tag_switch", "curated.formation_tag_rule", "meta.formation_tag_run"):
        assert f"CREATE TABLE IF NOT EXISTS {t}" in s
    assert "VALUES (TRUE, FALSE," in s and "ON CONFLICT (id) DO NOTHING" in s
    assert "MATERIALIZED VIEW" not in s.split("-- =====")[-1]


def test_rule_columns_match_sql72():
    s = (SQL / "72_formation_tag_rule.sql").read_text(encoding="utf-8")
    body = s[s.index("CREATE TABLE IF NOT EXISTS curated.formation_tag_rule"):s.index("CREATE INDEX IF NOT EXISTS idx_formation_tag_rule")]
    cols = [ln.split()[0] for ln in body.splitlines()[1:] if ln.strip() and not ln.strip().startswith(("CHECK", ")", "--"))]
    assert cols == [*tr.RULE_COLUMNS, "run_id"]


def test_nightly_refreshes_survey_before_formation_blueox():
    from etl import db

    order = list(db._CURATED_MATVIEWS)
    assert order.index("curated.wells") < order.index("curated.well_lateral_survey") < order.index("curated.formation_blueox")


def test_refresh_hook_runs_before_its_matview(monkeypatch):
    from etl import db

    calls: list[str] = []
    monkeypatch.setattr(db, "_CURATED_MATVIEWS", ("a", "b"))
    monkeypatch.setattr(db, "_GATED_REFRESH", {})
    monkeypatch.setattr(db, "_retry_on_conn_loss", lambda fn, what: calls.append(what))
    monkeypatch.setattr(db, "settle", lambda: None)

    class _Log:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(db, "log_etl_run", _Log)
    db.refresh_curated(hooks={"b": lambda: calls.append("hook")})
    assert calls == ["refresh a", "hook", "refresh b"]


# ---------------------------------------------------------------------------- W3 verifier + CASCADE check


def test_sql23_ripple_is_only_an_enriched_move_with_formation_blueox_unchanged():
    from scripts import apply_formation_tag_rule as atr

    before = {"blueox": {"r1": ("BS2_S", "novi"), "r2": ("WCB_1", "enverus"), "x1": ("WCA_1", "novi"),
                         "x2": ("BS3_S", "novi"), "x3": ("WCB_1", "novi")},
              "enriched": {"r1": ("BS2_S", "tvd_corrected"), "r2": ("WCB_1", "enverus"), "x1": ("WCA_1", "novi"),
                           "x2": ("BS3_S", "tvd_corrected"), "x3": ("WCB_1", "novi")}}
    after = {"blueox": {"r1": ("BS2_S", "novi"), "r2": ("WCB_1", "enverus"), "x1": ("WCA_1", "novi"),
                        "x2": ("BS3_C", "ratified_override"), "x3": ("WCB_1", "novi")},
             "enriched": {"r1": ("BS3_C", "novi"),               # correction dropped (W3: SCOTER 6 FED #004H)
                          "r2": ("AVA_0", "tvd_corrected"),      # correction gained (W3: STREETCAR)
                          "x1": ("WCA_2", "novi"),               # moved with no sql/23 on either side
                          "x2": ("BS3_C", "ratified_override"),  # its formation_blueox row moved
                          }}                                     # x3 vanished
    assert atr.sql23_ripple({"r1", "r2", "x1", "x2", "x3"}, before, after) == {"r1", "r2"}


def _edges(*pairs):
    return [(c, ck, p, pk) for c, ck, p, pk in pairs]


def test_cascade_closure_and_problems():
    from scripts import apply_formation_tag_rule as atr

    root = "curated.formation_blueox"
    edges = _edges(("curated.formation_blueox_tvd", "m", root, "m"),
                   ("curated.wells_enriched", "v", "curated.formation_blueox_tvd", "m"),
                   ("curated.new_thing", "v", "curated.wells_enriched", "v"))
    closure = atr.cascade_closure(edges)
    assert closure == {root: "m", "curated.formation_blueox_tvd": "m", "curated.wells_enriched": "v",
                       "curated.new_thing": "v"}
    blocking, notes = atr.cascade_problems(closure)
    assert blocking == ["CASCADE drops curated.new_thing (view) but no tail step re-creates it"]
    assert len(notes) == len(atr.RECREATED_BY) - 3          # listed objects not below root in this toy graph


def test_recreated_by_covers_the_refresh_chain_and_the_three_views():
    from scripts import apply_formation_tag_overrides as afo
    from scripts import apply_formation_tag_rule as atr

    views = {"curated.wells_enriched", "curated.dev_scenario", "curated.box_scout_locations"}
    assert set(atr.RECREATED_BY) == set(afo.CHAIN) | views
    tail = " ".join(" ".join(c) for c in atr.TAIL)
    for step in set(atr.RECREATED_BY.values()) - {"sql/16", "sql/25"}:
        assert step in tail
    assert "25_net_new_pdp.sql" in tail
