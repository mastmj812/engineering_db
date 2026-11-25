"""BOX sticks phase 8, step 3 (sql/80): the three retired Novi-stick matviews and the vintage date per basin. DB-free."""

import re
from pathlib import Path

from scripts import apply_formation_tag_overrides as afo
from scripts import apply_reconciled_inventory as ari
from scripts import apply_retire_novi_sticks as rns

ROOT = Path(__file__).resolve().parent.parent
SQL80 = (ROOT / "sql" / "80_retire_novi_stick_relations.sql").read_text(encoding="utf-8")
SQL68 = (ROOT / "sql" / "68_reconcile_all_sticks.sql").read_text(encoding="utf-8")
CODE80 = re.sub(r"--[^\n]*", "", SQL80)


def test_the_drop_names_exactly_the_retired_three_and_never_cascades():
    dropped = re.findall(r"DROP MATERIALIZED VIEW IF EXISTS (curated\.\w+)", CODE80)
    assert set(dropped) == set(rns.RETIRED) == set(afo.RETIRED) and len(dropped) == 3
    assert dropped[0] == "curated.novi_stick_locations"          # the reader goes before what it reads
    assert "CASCADE" not in CODE80                                 # an unknown dependent makes the file fail, not vanish
    assert "DROP FUNCTION" not in CODE80 and "pdp_support_for_geom" not in CODE80      # the score of record is untouched


def test_an_unknown_dependent_refuses_and_the_three_depending_on_each_other_do_not():
    own = [("curated.intel_pdp_support", "curated.novi_stick_locations")]
    assert rns.dependents_problems(own) == []
    assert rns.dependents_problems([*own, ("curated.intel_pdp_support", "curated.some_land_view")]) == [
        "curated.some_land_view depends on curated.intel_pdp_support"]


def test_nothing_the_apps_read_is_in_the_drop_or_the_rebuild():
    for r in rns.PROTECTED:
        assert r not in rns.RETIRED and r not in rns.REBUILT, r
    assert "curated.erebor_locations" in rns.PROTECTED and "curated.box_scout_locations" in rns.PROTECTED
    steps = [" ".join(c[1:]) for c in rns.STEPS]
    assert steps[0].endswith("scripts.apply_reconciled_inventory")              # the default (checking) path: no --rebuild-reference
    assert steps[1].endswith("scripts.apply_intel_forecast_accuracy") and steps[2].endswith("--after-reload")
    assert "26_geography_indexes.sql" in steps[3]


def test_the_reconciliation_splits_drift_at_the_date_of_the_sticks_own_basin():
    body = SQL68[SQL68.index("CREATE MATERIALIZED VIEW curated.reconciled_inventory AS"):SQL68.index("CREATE UNIQUE INDEX")]
    code = re.sub(r"--[^\n]*", "", body)
    assert "WITH vint AS MATERIALIZED (" in code and "FROM curated.intel_vintage_date_by_basin()" in code
    assert "m.matched_first_prod > v.vintage_date" in code and "LEFT JOIN vint v ON v.basin = pud.basin" in code
    assert "curated.intel_vintage_date()" not in code               # the one-date function is no longer the split
    assert "RETURNS TABLE (basin text, report_version text, vintage_date date)" in SQL80
    assert "FROM curated.intel_locations il" in CODE80 and "GROUP BY il.basin" in CODE80


def test_sql80_runs_before_sql68_wherever_the_reconciliation_is_built():
    src = Path(ari.__file__).read_text(encoding="utf-8")
    main = src[src.index("def main("):]
    assert main.index("80_retire_novi_stick_relations.sql") < main.index("68_reconcile_all_sticks.sql")
