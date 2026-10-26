"""Step 13b: the refresh contract's rules as code (D126), DB-free."""

import datetime as dt

from box import refresh13 as r13


def test_due_on_a_new_vintage_or_a_lag_over_four_months():
    d = dt.date
    assert r13.due("2026Q3", "2026Q4", d(2026, 7, 1), d(2026, 8, 1)) == (True, ["new Novi vintage 2026Q4 (record 2026Q3)"])
    assert r13.due("2026Q3", "2026Q3", d(2026, 7, 1), d(2026, 11, 1))[0] is False  # 4 months: inside the safety net
    ok, why = r13.due("2026Q3", "2026Q3", d(2026, 7, 1), d(2026, 12, 1))
    assert ok and "5 months" in why[0]


def test_extent_trigger_is_n_10():
    assert r13.EXTENT_N == 10 and r13.EXTENT_X_MI == 2.0
    assert r13.extent_trigger({"BS2_S": 9, "BS3_C": 10, "WCA": 0}) == ["BS3_C"]


def test_chain_runs_the_r2_build_on_all_13_groups_and_every_write_is_a_go():
    c = r13.chain("docs/box/pool-x", "runs/x", 14)
    build = next(s for s in c if s["step"].startswith("build"))
    assert "--selection r2" in build["cmd"] and "--wells docs/box/pool-x" in build["cmd"]
    assert build["cmd"].split("--benches ")[1].split()[0].split(",") == list(r13.GROUPS) and len(r13.GROUPS) == 13
    writes = [s for s in c if "store" in s["cmd"] or "prune" in s["cmd"]]
    assert writes and all(s["go"] for s in writes)
    assert any("--include-priced" in s["cmd"] for s in c)  # D123
    assert not any(s["go"] for s in c if s["step"].startswith(("pool refresh", "build", "water build", "proximity re-measure")))


def test_groups_match_the_prospective_definition():
    from box import prospective16 as ps

    assert set(r13.GROUPS) == set(ps.GROUPS)
    assert all(list(r13.GROUPS[g][0]) == ps.DEFINITION["cohort"]["groups"][g]["formations"] for g in r13.GROUPS)
