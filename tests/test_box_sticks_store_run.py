"""A BOX forecast run on BOX sticks: the build provenance, the store's location path and sql/79, DB-free
(docs/box_sticks_plan.md phase 6).

Pins: a BOX stick IS its location (stick_id = location_id, no vintage crosswalk, no location_source row, box.location never
written); the run is tied to the record stick set it read; a base store never becomes the record; the Novi store path and a
Novi build's cache key are unchanged; the three constraints of sql/79 only widen.
"""
import argparse
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from box import production as pr
from scripts import apply_box_pud_forecast_box_sticks as app79
from scripts import box_pud_run as bpr
from scripts import box_record23_midland as mid

ROOT = Path(__file__).resolve().parent.parent
SQL79 = (ROOT / "sql" / "79_box_pud_forecast_box_sticks.sql").read_text(encoding="utf-8")
SQL60 = (ROOT / "sql" / "60_box_pud_forecast.sql").read_text(encoding="utf-8")


def _u(n=3, **over):
    d = pd.DataFrame({"stick_id": [10_000_001 + i for i in range(n)], "set_id": 24, "category": "BOX", "basin": "delaware",
                      "recon_status": ["open", "permitted", "crowded"][:n], "coverage": "covered", "prod_bench": "WCC"})
    for k, v in over.items():
        d[k] = v
    return d


def test_provenance_names_the_set_the_status_and_the_rules():
    p = bpr.box_stick_provenance(_u())
    assert p["location_source"] == "box_sticks" and p["location_set_id"] == 24
    assert p["location_status"] == {"open": 1, "permitted": 1, "crowded": 1}
    assert p["location_rules"]["not_drillable"] == ["conflict", "crowded"] and p["location_rules"]["spacing"] == "generator"
    assert bpr.box_stick_provenance(pd.DataFrame({"stick_id": [1], "category": ["PUD"]})) == {}      # a Novi run says nothing new
    assert bpr.box_stick_provenance(pd.DataFrame({"stick_id": [1]})) == {}                           # artifacts before D117 step 3
    with pytest.raises(SystemExit, match="one record set"):
        bpr.box_stick_provenance(_u(set_id=[24, 24, 25]))
    with pytest.raises(SystemExit, match="mixes BOX sticks and Novi sticks"):
        bpr.is_box_universe(_u(category=["BOX", "PUD", "BOX"]))


def test_run_notes_say_what_the_locations_are():
    note = bpr.box_stick_note({"location_source": "box_sticks", "location_set_id": 24, "location_status": {"open": 5}})
    assert "BOX sticks, record set 24" in note and "conflict and crowded sticks not forecast" in note and "producing sticks not in the run" in note
    assert bpr.box_stick_note({}) == ""


class _Q:
    def __init__(self, record, found):
        self.record, self.found, self.sqls = record, found, []

    def __call__(self, sql, params=None):
        self.sqls.append((sql, params))
        self.last = sql
        return self

    def fetchone(self):
        return (self.record,) if "FROM box.location_set" in self.last and self.record is not None else (None if "FROM box.location_set" in self.last else (self.found,))


def test_a_box_stick_is_its_location_and_the_run_is_tied_to_the_record_set():
    q = _Q(record=24, found=3)
    assert bpr.box_stick_location_ids(q, _u(), "delaware", 24) == {10_000_001: 10_000_001, 10_000_002: 10_000_002, 10_000_003: 10_000_003}
    assert all(not re.search(r"\b(INSERT|UPDATE|DELETE)\b", s) for s, _ in q.sqls)                  # box.location is only read
    assert "l.source = 'box_sticks'" in q.sqls[1][0] and "k.set_id = %s" in q.sqls[1][0]
    with pytest.raises(SystemExit, match="record set is now 31"):
        bpr.box_stick_location_ids(_Q(record=31, found=3), _u(), "delaware", 24)                    # the set was regenerated since the build
    with pytest.raises(SystemExit, match="record set is now None"):
        bpr.box_stick_location_ids(_Q(record=None, found=3), _u(), "delaware", 24)
    with pytest.raises(SystemExit, match="1 of 3 sticks are not BOX-stick locations"):
        bpr.box_stick_location_ids(_Q(record=24, found=2), _u(), "delaware", 24)


def test_the_store_branches_before_any_novi_crosswalk_and_never_records_a_base_run():
    src = inspect.getsource(bpr.cmd_store)
    assert src.index("box = is_box_universe(u)") < src.index("conn = get_connection()")
    assert src.index('if box and a.record:') < src.index("conn = get_connection()") and "scripts.box_record23 flip" in src
    i = src.index("if box:  # a BOX stick IS its location")
    assert src.index("have = box_stick_location_ids(q, u, basin, run[\"location_set_id\"])") > i
    assert src.index("pr.crosswalk(") > i and "if len(new) and prev_v is not None:" in src          # prev_v None + no `new` rows: both Novi blocks are skipped
    assert 'raise SystemExit(f"{len(new)} BOX sticks without a location: refused")' in src
    assert "run_notes(run) + box_stick_note(run)" in src
    # the Novi lookups are exactly what they were
    assert 'later = q(f"SELECT count(*) FROM {src_b} s.report_version > %s", (basin, rv)).fetchone()[0]' in src
    assert 'have = dict(q(f"SELECT s.stick_id, s.location_id FROM {src_b} s.report_version = %s", (basin, rv)).fetchall())' in src


def test_a_novi_builds_cache_key_is_unchanged_and_a_box_build_cannot_reuse_it():
    u = _u()
    base = {"selection": "r2", "pack_sha256": "abc", "wells": Path("w"), "limit": 0}
    novi = bpr.resume_meta("k", argparse.Namespace(**base, source="novi"), u)
    assert novi == bpr.resume_meta("k", argparse.Namespace(**base), u) and "source" not in novi
    assert bpr.resume_meta("k", argparse.Namespace(**base, source="box_sticks"), u) == {**novi, "source": "box_sticks"}


def test_both_builds_take_the_source_and_augment_refuses_a_box_run():
    assert 'pr.universe(conn, a.benches, source=getattr(a, "source", pr.SOURCE_NOVI))' in inspect.getsource(bpr.cmd_build)
    assert "run.update(box_stick_provenance(u))" in inspect.getsource(bpr.cmd_build)
    m = inspect.getsource(mid.cmd_build)
    assert "pr.universe(conn, a.groups, source=a.source)" in m and "run.update(pud.box_stick_provenance(u))" in m
    assert "does not apply to a run on BOX sticks" in inspect.getsource(bpr.cmd_augment)
    for mod in (bpr, mid):
        assert '"--source", choices=pr.BUILD_SOURCES, default=pr.SOURCE_BOX' in inspect.getsource(mod.main)
    assert (pr.SOURCE_NOVI, pr.SOURCE_BOX) == ("novi", "box_sticks")


def test_no_forecast_run_is_built_or_stored_on_novi_sticks():
    """BOX sticks phase 8 (Michael 2026-11-25): Novi Intelligence is comparison only. The Novi-stick universe stays
    readable for the comparison and history reports; a build, a base store and a derived store all refuse it."""
    import pytest

    from scripts import box_record23 as r23

    assert pr.BUILD_SOURCES == (pr.SOURCE_BOX,)
    for mod in (bpr, mid):
        with pytest.raises(SystemExit):                      # argparse rejects the choice
            mod.main(["build", "--source", "novi"])
    assert "refusing to store a run on Novi sticks" in inspect.getsource(bpr.cmd_store)
    src = inspect.getsource(r23)
    assert "is on Novi sticks: {prod.NOVI_RUN_REFUSED}" in src and "from box import production as prod" in src
    assert "comparison only" in pr.NOVI_RUN_REFUSED
    assert "FROM curated.intel_locations il" in pr._UNIVERSE_SQL          # still there for universe() readers (reports)


def _in_list(sql: str, con: str) -> set[str]:
    body = sql[sql.index(f"ADD CONSTRAINT {con} CHECK"):]
    return set(re.findall(r"'([a-z_0-9]+)'", body[:body.index(";")]))


def test_sql79_only_widens():
    old_recon = set(re.findall(r"'([a-z_]+)'", re.search(r"recon_status\s+text\s+NOT NULL CHECK \(recon_status IN \(([^)]*)\)", SQL60).group(1)))
    old_space = set(re.findall(r"'([a-z_0-9]+)'", re.search(r"spacing_source\s+text\s+CHECK \(spacing_source IN \(([^)]*)\)", SQL60).group(1)))
    assert old_recon == {"remaining_pud", "conflict", "not_reconciled"} and old_space == {"neighbour_gap", "default_880"}
    new_recon = _in_list(SQL79, "box_pud_forecast_recon_status_ck")
    assert old_recon < new_recon and new_recon - old_recon == {"open", "permitted", "pending", "crowded"}
    assert new_recon == old_recon | (set(pr.BOX_RECON_STATUSES))                                     # every status the universe can emit
    assert _in_list(SQL79, "box_pud_forecast_spacing_source_ck") == old_space | {pr.SPACING_GENERATOR}
    assert _in_list(SQL79, "box_pud_forecast_conflict_ck") == {"not_covered_conflict", "conflict", "crowded"}
    assert not re.search(r"\b(UPDATE|DELETE|INSERT|TRUNCATE|DROP TABLE)\b", SQL79)
    for c in app79.OLD:
        assert f"DROP CONSTRAINT IF EXISTS {c};" in SQL79
    assert set(app79.NEW) == {"box_pud_forecast_recon_status_ck", "box_pud_forecast_spacing_source_ck", "box_pud_forecast_conflict_ck"}
    src = Path(app79.__file__).read_text(encoding="utf-8")
    assert "if bad or not a.go:" in src and src.index("conn.rollback()") < src.index("conn.commit()")
