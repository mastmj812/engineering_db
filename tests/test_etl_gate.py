"""Pure-function tests for scripts/etl_gate.py, the etl-nightly dedupe gate.
No network: the runs/jobs listings are fixtures shaped like the GitHub API."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from scripts import etl_gate as g

UTC = timezone.utc
WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "etl-nightly.yml"
)


def _run(
    run_id: int, created: str, conclusion: str = "success", status: str = "completed"
) -> dict:
    return {
        "id": run_id,
        "created_at": created,
        "status": status,
        "conclusion": conclusion,
    }


# The real listing around 2026-11-04, newest first. 41817957708 is the 11:00 UTC
# primary dispatch that the API's status=success filter dropped.
RUNS_1104 = [
    _run(41889183748, "2026-11-04T18:38:42Z", status="in_progress", conclusion=None),
    _run(41817957708, "2026-11-04T11:00:12Z"),
    _run(41693948151, "2026-11-03T18:27:11Z"),
    _run(41623893654, "2026-11-03T11:00:11Z"),
]
JOBS = {
    41817957708: [
        {"name": "gate", "conclusion": "success"},
        {"name": "etl", "conclusion": "success"},
    ],
    41693948151: [
        {"name": "gate", "conclusion": "success"},
        {"name": "etl", "conclusion": "skipped"},
    ],
    41623893654: [
        {"name": "gate", "conclusion": "success"},
        {"name": "etl", "conclusion": "success"},
    ],
}


def _pages(runs: list[dict]):
    return lambda page: runs if page == 1 else []


def test_window_start_after_and_before_0900():
    assert g.window_start(datetime(2026, 11, 4, 18, 38, tzinfo=UTC)) == datetime(
        2026, 11, 4, 9, tzinfo=UTC
    )
    assert g.window_start(datetime(2026, 11, 5, 8, 59, tzinfo=UTC)) == datetime(
        2026, 11, 4, 9, tzinfo=UTC
    )
    assert g.window_start(datetime(2026, 11, 5, 9, 0, tzinfo=UTC)) == datetime(
        2026, 11, 5, 9, tzinfo=UTC
    )


def test_backstop_1104_skips_on_primary_dispatch():
    """The 2026-11-04 defect: the backstop must find the 11:00 primary run."""
    since = datetime(2026, 11, 4, 9, tzinfo=UTC)
    done = g.find_completed_run(
        _pages(RUNS_1104), JOBS.__getitem__, since, self_id=41889183748
    )
    assert done == 41817957708


def test_skipped_etl_run_does_not_count():
    """11-03 18:27 concluded success with etl skipped; it is not a completed ETL."""
    since = datetime(2026, 11, 3, 18, 0, tzinfo=UTC)
    runs = [_run(41693948151, "2026-11-03T18:27:11Z")]
    assert (
        g.find_completed_run(_pages(runs), JOBS.__getitem__, since, self_id=0) is None
    )


def test_failed_primary_does_not_count():
    since = datetime(2026, 11, 4, 9, tzinfo=UTC)
    runs = [_run(1, "2026-11-04T11:00:12Z", conclusion="failure")]
    assert g.find_completed_run(_pages(runs), lambda _id: [], since, self_id=0) is None


def test_runs_before_window_and_self_are_ignored():
    since = datetime(2026, 11, 4, 9, tzinfo=UTC)
    runs = [_run(7, "2026-11-04T12:00:00Z"), _run(41623893654, "2026-11-03T11:00:11Z")]
    jobs = {7: [{"name": "etl", "conclusion": "success"}], **JOBS}
    assert (
        g.find_completed_run(_pages(runs), jobs.__getitem__, since, self_id=7) is None
    )


def test_until_bound_for_replay():
    since = datetime(2026, 11, 4, 9, tzinfo=UTC)
    until = datetime(2026, 11, 4, 10, 59, tzinfo=UTC)
    assert g.candidate_run_ids(RUNS_1104, since, self_id=0, until=until) == []


def test_paging_continues_until_window_is_passed():
    since = datetime(2026, 11, 4, 9, tzinfo=UTC)
    page1 = [
        _run(1000 + i, "2026-11-04T20:00:00Z", conclusion="failure")
        for i in range(g.PER_PAGE)
    ]
    page2 = [
        _run(41817957708, "2026-11-04T11:00:12Z"),
        _run(41623893654, "2026-11-03T11:00:11Z"),
    ]
    pages = {1: page1, 2: page2}
    done = g.find_completed_run(
        lambda p: pages.get(p, []), JOBS.__getitem__, since, self_id=0
    )
    assert done == 41817957708


def test_workflow_uses_gate_script_without_server_side_run_filters():
    """Pin the fix: the gate runs the script, and nothing in the workflow or the
    script asks the list-runs API to filter by status/conclusion/created."""
    wf = WORKFLOW.read_text(encoding="utf-8")
    assert "python3 scripts/etl_gate.py" in wf
    src = Path(g.__file__).read_text(encoding="utf-8")
    code = src.split('"""', 2)[2]  # skip the module docstring, which names the filters
    for text in (wf, code):
        assert not re.search(r"[?&]\s*(status|conclusion|created)=", text)
        assert not re.search(r"-f\s+(status|conclusion|created)=", text)
