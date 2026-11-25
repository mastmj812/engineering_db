"""Step 13b: the refresh contract's rules as code (D126), DB-free."""

import datetime as dt

from box import refresh13 as r13


def test_due_on_a_production_lag_over_four_months_never_on_a_novi_vintage():
    """BOX sticks phase 8 (Michael 2026-11-25): locations are ours, so a Novi Intelligence vintage is no trigger.
    D126's lag rule is unchanged and is now the only one."""
    d = dt.date
    assert r13.LAG_MONTHS == 4
    assert r13.due(d(2026, 7, 1), d(2026, 8, 1)) == (False, [])
    assert r13.due(d(2026, 7, 1), d(2026, 11, 1))[0] is False          # 4 months: inside the rule
    ok, why = r13.due(d(2026, 7, 1), d(2026, 12, 1))
    assert ok and "5 months" in why[0]
    assert "intel_locations" not in r13.STATE_SQL and "report_version" not in r13.STATE_SQL


def test_extent_trigger_is_n_10():
    assert r13.EXTENT_N == 10 and r13.EXTENT_X_MI == 2.0
    assert r13.extent_trigger({"BS2_S": 9, "BS3_C": 10, "WCA": 0}) == ["BS3_C"]


def test_chain_runs_the_r2_build_on_all_13_groups_and_every_write_is_a_go():
    c = r13.chain("docs/box/pool-x", "runs/x", 14)
    build = next(s for s in c if s["step"].startswith("build"))
    assert "--selection r2" in build["cmd"] and "--wells docs/box/pool-x" in build["cmd"]
    assert "--source box_sticks" in build["cmd"]  # never the Novi sticks again by default (BOX sticks cutover, 2026-11-24)
    assert not any("--record" in s["cmd"] for s in c) and sum("box_record23 flip" in s["cmd"] for s in c) == 1  # the flip is its own go
    assert [s["go"] for s in c if "box_record23" in s["cmd"]] == [False, True, True]  # measure, derived store, flip
    assert build["cmd"].split("--benches ")[1].split()[0].split(",") == list(r13.GROUPS) and len(r13.GROUPS) == 13
    writes = [s for s in c if "store" in s["cmd"] or "prune" in s["cmd"]]
    assert writes and all(s["go"] for s in writes)
    assert any("--include-priced" in s["cmd"] for s in c)  # D123
    assert not any(s["go"] for s in c if s["step"].startswith(("pool refresh", "build", "water build", "proximity re-measure")))


def test_groups_match_the_prospective_definition():
    from box import prospective16 as ps

    assert set(r13.GROUPS) == set(ps.GROUPS)
    assert all(list(r13.GROUPS[g][0]) == ps.DEFINITION["cohort"]["groups"][g]["formations"] for g in r13.GROUPS)
