"""Pure-function tests for scripts/check_drift.py — SQL parsing on fixture
strings, whitelist logic, report formatting, and the never-raise degradation
of the email entry points. No database, no network, no gh."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from scripts import check_drift as cd

_NOW = datetime(2026, 8, 17, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# SQL parsing
# ---------------------------------------------------------------------------

FIXTURE_SQL = """
-- CREATE MATERIALIZED VIEW curated.commented_out AS SELECT 1;  (comment: ignored)
CREATE SCHEMA IF NOT EXISTS curated;

CREATE TABLE meta.etl_log (
    etl_log_id BIGSERIAL PRIMARY KEY
);
CREATE INDEX idx_etl_log_started ON meta.etl_log (run_started_at DESC);

CREATE MATERIALIZED VIEW curated.wells AS
SELECT 1 AS api10;

CREATE UNIQUE INDEX IF NOT EXISTS idx_curated_wells_api10
    ON curated.wells (api10);

CREATE INDEX IF NOT EXISTS idx_curated_wells_wellstick_geog
  ON curated.wells USING GIST ((wellstick_geom::geography));

CREATE OR REPLACE VIEW curated.wells_enriched AS SELECT 1;

CREATE OR REPLACE FUNCTION curated.intel_representative_sticks(
    p_basin text
) RETURNS TABLE (stick_id bigint) AS $$
    SELECT 1::bigint
$$ LANGUAGE sql;

CREATE TABLE raw_novi."Wells" (x int);
CREATE INDEX idx_out_of_scope ON raw_enverus.wells (api10);
"""


def test_parse_extracts_every_kind() -> None:
    found = set(cd.parse_sql_objects(FIXTURE_SQL))
    assert ("matview", "curated.wells") in found
    assert ("view", "curated.wells_enriched") in found
    assert ("table", "meta.etl_log") in found
    assert ("function", "curated.intel_representative_sticks") in found
    # Index names are qualified with the target table's schema.
    assert ("index", "curated.idx_curated_wells_api10") in found
    assert ("index", "curated.idx_curated_wells_wellstick_geog") in found
    assert ("index", "meta.idx_etl_log_started") in found


def test_parse_ignores_comments_and_normalizes_quotes() -> None:
    found = set(cd.parse_sql_objects(FIXTURE_SQL))
    assert ("matview", "curated.commented_out") not in found
    # Quoted identifiers are unquoted + lowercased (raw schemas only).
    assert ("table", "raw_novi.wells") in found


def test_matview_not_double_counted_as_view() -> None:
    found = cd.parse_sql_objects("CREATE MATERIALIZED VIEW curated.m AS SELECT 1;")
    assert ("view", "curated.m") not in found
    assert ("matview", "curated.m") in found


def test_collect_declared_filters_to_scope(tmp_path: Path) -> None:
    (tmp_path / "01_a.sql").write_text(FIXTURE_SQL, encoding="utf-8")
    (tmp_path / "02_b.sql").write_text(
        "CREATE OR REPLACE VIEW curated.wells_enriched AS SELECT 2;",
        encoding="utf-8",
    )
    declared = cd.collect_declared(tmp_path)
    names = set(declared)
    assert ("table", "raw_novi.wells") not in names  # out of scope
    assert ("index", "raw_enverus.idx_out_of_scope") not in names
    assert ("table", "meta.etl_log") in names
    # Redeclared in a later file: union dedupes, both files recorded.
    assert declared[("view", "curated.wells_enriched")] == {"01_a.sql", "02_b.sql"}


# ---------------------------------------------------------------------------
# Comparison + whitelist
# ---------------------------------------------------------------------------

def _declared() -> dict[tuple[str, str], set[str]]:
    return {
        ("matview", "curated.wells"): {"04_curated.sql"},
        ("matview", "curated.gone"): {"12_old.sql"},
        ("matview", "curated.retired"): {"13_old.sql"},
        ("function", "curated.intel_representative_sticks"): {"35_x.sql"},
        ("view", "curated.now_a_matview"): {"06_x.sql"},
    }


def _live() -> dict[str, set[str]]:
    return {
        "matview": {"curated.wells", "curated.now_a_matview", "curated.surprise"},
        "view": set(),
        "table": set(),
        "function": {"curated.intel_representative_sticks"},
        "index": {"curated.idx_x", "meta.etl_log_pkey"},
    }


def test_missing_live_flags_absent_and_kind_mismatch() -> None:
    lines, skipped = cd.missing_live_lines(_declared(), _live(), frozenset())
    text = "\n".join(lines)
    assert "matview curated.gone" in text and "ABSENT live" in text
    assert "matview curated.retired" in text
    # Function found in pg_proc, not flagged.
    assert "intel_representative_sticks" not in text
    # Declared view live as a matview: reported as kind mismatch, not absent.
    assert "view curated.now_a_matview" in text and "as a matview" in text
    assert skipped == 0


def test_whitelist_suppresses_known_retired() -> None:
    wl = frozenset({("matview", "curated.retired")})
    lines, skipped = cd.missing_live_lines(_declared(), _live(), wl)
    assert skipped == 1
    assert not any("curated.retired" in line for line in lines)
    assert any("curated.gone" in line for line in lines)  # still flagged


def test_undeclared_live_skips_pkey_indexes() -> None:
    lines = cd.undeclared_live_lines(_declared(), _live())
    text = "\n".join(lines)
    assert "matview curated.surprise" in text
    assert "curated.idx_x" in text
    assert "etl_log_pkey" not in text


def test_build_drift_lines_no_drift_message() -> None:
    declared = {("matview", "curated.wells"): {"04_curated.sql"}}
    live = {k: set() for k in cd.KINDS}
    live["matview"] = {"curated.wells"}
    lines = cd.build_drift_lines(declared, live, frozenset())
    text = "\n".join(lines)
    assert "no drift: every declared object verified live" in text
    assert "1 matviews" in text
    assert "MISSING LIVE" not in text


# ---------------------------------------------------------------------------
# Estate hygiene (pure formatting/classification)
# ---------------------------------------------------------------------------

def test_stale_pr_lines_threshold() -> None:
    prs = [
        {"number": 41, "title": "old one", "created_at": "2026-08-01T00:00:00Z"},
        {"number": 42, "title": "fresh", "created_at": "2026-08-16T00:00:00Z"},
    ]
    lines = cd.stale_pr_lines(prs, _NOW)
    assert lines == ["PR #41 open 16d: old one"]


def test_orphan_branch_line_ages() -> None:
    old = datetime(2026, 8, 10, tzinfo=timezone.utc)
    fresh = datetime(2026, 8, 17, 5, 0, tzinfo=timezone.utc)
    assert "orphan branch b1" in cd.orphan_branch_line("b1", old, _NOW)
    assert "likely in-flight" in cd.orphan_branch_line("b2", fresh, _NOW)
    assert "unknown" in cd.orphan_branch_line("b3", None, _NOW)


def test_collect_repo_hygiene_with_fake_gh() -> None:
    def fake_gh(path: str):
        if path == "repos/o/r":
            return {"default_branch": "main"}
        if path.startswith("repos/o/r/pulls"):
            return [
                {
                    "number": 7,
                    "title": "stale pr",
                    "created_at": "2026-08-01T00:00:00Z",
                    "head": {"ref": "feat/with-pr"},
                }
            ]
        if path.startswith("repos/o/r/branches"):
            return [
                {"name": "main", "commit": {"sha": "aaa"}},
                {"name": "feat/with-pr", "commit": {"sha": "bbb"}},
                {"name": "claude/orphan", "commit": {"sha": "ccc"}},
            ]
        if path == "repos/o/r/commits/ccc":
            return {"commit": {"committer": {"date": "2026-08-10T00:00:00Z"}}}
        raise AssertionError(f"unexpected gh path: {path}")

    lines = cd.collect_repo_hygiene("o/r", _NOW, run_gh=fake_gh)
    text = "\n".join(lines)
    assert "PR #7 open 16d" in text
    assert "orphan branch claude/orphan" in text
    assert "feat/with-pr" not in text.replace("PR #7 open 16d: stale pr", "")


def test_hygiene_lines_collapses_when_all_repos_fail() -> None:
    def dead_gh(path: str):
        raise RuntimeError("gh CLI not installed")

    lines = cd.hygiene_lines(["o/a", "o/b"], now=_NOW, run_gh=dead_gh)
    assert lines == ["  gh unavailable: gh CLI not installed"]


def test_hygiene_lines_partial_failure_reports_per_repo() -> None:
    def flaky_gh(path: str):
        if path.startswith("repos/o/good"):
            if path == "repos/o/good":
                return {"default_branch": "main"}
            return []
        raise RuntimeError("HTTP 404")

    lines = cd.hygiene_lines(["o/good", "o/bad"], now=_NOW, run_gh=flaky_gh)
    text = "\n".join(lines)
    assert "clean: 1 repo(s)" in text
    assert "o/bad: check errored (HTTP 404)" in text


# ---------------------------------------------------------------------------
# Never-raise degradation of the email entry points
# ---------------------------------------------------------------------------

def test_drift_email_section_degrades_on_total_failure(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("no db from here")

    monkeypatch.setattr(cd, "collect_declared", boom)
    monkeypatch.setattr(cd, "hygiene_lines", boom)
    lines = cd.drift_email_section()  # must not raise
    text = "\n".join(lines)
    assert "drift check errored: no db from here" in text
    assert "hygiene check errored: no db from here" in text


def test_notify_collect_drift_lines_guards_everything(monkeypatch) -> None:
    from etl import notify

    monkeypatch.setenv("DRIFT_CHECK_DISABLED", "1")
    assert notify.collect_drift_lines() == []

    monkeypatch.delenv("DRIFT_CHECK_DISABLED")
    monkeypatch.setattr(
        cd, "drift_email_section", lambda: (_ for _ in ()).throw(RuntimeError("x"))
    )
    lines = notify.collect_drift_lines()
    assert lines == ["drift check errored: x"]


def test_build_email_appends_drift_section() -> None:
    from types import SimpleNamespace

    from etl import notify

    steps = [
        SimpleNamespace(
            name="novi.sync", status="success", duration_s=1.0, rows=0, error=None
        )
    ]
    drift = ["Drift check (repo sql/ vs live warehouse):", "  no drift"]
    _, body = notify.build_email(steps, {}, None, None, drift_lines=drift)
    assert "Drift check (repo sql/ vs live warehouse):" in body
    assert "  no drift" in body
    # Omitted -> section absent (backwards compatible).
    _, body_none = notify.build_email(steps, {}, None, None)
    assert "Drift check" not in body_none
