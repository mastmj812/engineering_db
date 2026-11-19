"""Gate 5d shadow reports (scripts/box_recon_shadow.py): read-only by construction, and the pure helpers. DB-free."""
from __future__ import annotations

import re
from pathlib import Path

from scripts import box_recon_shadow as sh

SRC = (Path(__file__).resolve().parent.parent / "scripts" / "box_recon_shadow.py").read_text(encoding="utf-8")


def _row(loc, status="open", well=None, pad=1, bench="WCA_1", crowded=False, crowd=None, ov=None, basin="delaware"):
    return {"location_id": loc, "basin": basin, "pad_id": pad, "formation_blueox": bench, "status": status, "matched_api10": well,
            "match_overlap": ov, "crowded": crowded, "crowd_api10": crowd, "counts_as_inventory": status not in sh.OUT and not crowded}


def test_the_script_writes_nothing_to_the_warehouse():
    assert not re.search(r"\b(INSERT INTO|UPDATE |DELETE FROM|TRUNCATE|CREATE |DROP |ALTER |REFRESH )", SRC)
    assert "SET TRANSACTION READ ONLY" in SRC and "conn.rollback()" in SRC and "conn.commit()" not in SRC
    assert "run(write=False)" in SRC and "write=True" not in SRC                     # the nightly hook is the only writer


def test_sql68_per_well_keeps_sql68s_thresholds_and_guard():
    ddl = next((Path(__file__).resolve().parent.parent / "sql").glob("68_*.sql")).read_text(encoding="utf-8")
    for piece in ("il.category IN ('PUD', 'RES')", "abs(pr.tvd - pud.tvd) <= 500", "abs(pr.tvd - pud.tvd) <= 150", "COALESCE(t.corrected_code, pr.code)"):
        assert piece in ddl and piece in sh.SQL68_PER_WELL, piece
    assert sh.sql68_class(None) == "not_in_producing_reference"
    assert sh.sql68_class({"has_tvd": False, "best_overlap": None}) == "no_tvd"
    assert sh.sql68_class({"has_tvd": True, "best_overlap": None}) == "nothing"
    assert sh.sql68_class({"has_tvd": True, "best_overlap": 0.19}) == "nothing"
    assert sh.sql68_class({"has_tvd": True, "best_overlap": 0.2}) == "conflict"      # sql/68's floor is 0.2, the nightly's is 0.3
    assert sh.sql68_class({"has_tvd": True, "best_overlap": 0.5}) == "realizes"


def test_two_sticks_splits_same_dsu_from_across_dsus():
    s = [_row(1, "producing", "A", pad=1), _row(2, "producing", "A", pad=1, bench="WCA_2"),      # same DSU, two benches
         _row(3, "producing", "B", pad=1), _row(4, "producing", "B", pad=2),                     # across DSUs
         _row(5, "producing", "C", pad=3), _row(6, "producing", "C", pad=3),                     # same DSU, same bench
         _row(7, "producing", "D"), _row(8, "conflict", "D"), _row(9)]
    t = sh.two_sticks(s)
    assert (t["wells_matching_sticks"], t["wells_with_two_or_more"], t["same_dsu"], t["different_dsus_only"], t["same_dsu_same_bench"]) == (4, 3, 2, 1, 1)


def test_counts_and_identities():
    s = [_row(1), _row(2, "producing", "A"), _row(3, crowded=True, crowd="B"), _row(4, "permitted", basin="midland")]
    c = sh.counts(s)
    assert c["delaware"] == {"sticks": 3, "open": 2, "producing": 1, "crowded": 1, "inventory": 1} and c["midland"]["inventory"] == 1
    assert sh.identities(s, 4) == {"status_rows": 4, "distinct_locations": 4, "record_sticks": 4, "one_row_per_record_stick": True, "inventory_rule_breaks": 0}
    s[1]["counts_as_inventory"] = True
    i = sh.identities(s + [_row(1)], 4)
    assert not i["one_row_per_record_stick"] and i["inventory_rule_breaks"] == 1


def test_flapping_counts_a_return_to_an_earlier_status_and_ignores_set_changes():
    def lg(run, loc, old, new, cause="well"):
        return {"run_id": run, "location_id": loc, "cause": cause, "old_status": old, "new_status": new}

    log = [lg(2, 1, "open", "permitted"), lg(3, 1, "permitted", "open"),            # flaps
           lg(2, 2, "open", "pending"), lg(4, 2, "pending", "producing"),           # moves on, no flap
           lg(3, 3, "open", "open"),                                               # a crowded or well change at the same status
           lg(2, 4, "open", "producing", cause="set_change"), lg(3, 4, "producing", "open", cause="set_change")]
    f = sh.flapping(log)
    assert (f["locations_changed"], f["flapped"], f["location_ids"]) == (3, 1, [1])


def test_bar_limits_are_the_ones_written_before_the_week():
    bars = (Path(__file__).resolve().parent.parent / "docs" / "box_sticks" / "phase5d-2026-11-19" / "BARS.md").read_text(encoding="utf-8")
    assert f"<= {sh.CHURN_LIMIT} per night" in bars and f"`seconds` <= {sh.SECONDS_LIMIT}" in bars
    assert "<= 10 % return" in bars and sh.FLAP_LIMIT == 0.10 and "<= 0.5 %" in bars and sh.DAY0_LIMIT == 0.005
