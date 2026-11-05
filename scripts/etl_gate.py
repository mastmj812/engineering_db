"""Dedupe gate for .github/workflows/etl-nightly.yml (the `gate` job).

A guarded trigger (the backstop `schedule:` cron, or a dispatch with
only_if_needed=true) must skip the ETL when an `etl` job already SUCCEEDED in a
run of this workflow created since the most recent 09:00 UTC. A plain manual
dispatch is never gated. See the workflow header and docs/cold_start.md §6a.

Every filter is applied HERE, client-side, on the unfiltered runs listing.
Never pass `status=` / `conclusion=` / `created=` to the list-runs API: those
filters go through a secondary index that can silently drop a run. On
2026-11-04 the 11:00 UTC primary dispatch (run 41817957708, completed/success)
was missing from every `status=` value while present in the plain listing, so
the 18:38 UTC backstop saw "no successful ETL" and ran a second full ETL.

Fails OPEN: if the GitHub API cannot be read, the ETL runs (a redundant run
costs hours; a missed nightly costs a day of data). Stdlib only, so the gate job
needs no setup-python / pip install.

Dry run from a workstation (prints the decision, writes nothing):

    GH_TOKEN=$(gh auth token) GUARDED=true EVENT=schedule \
      GITHUB_REPOSITORY=mastmj812/engineering_db GITHUB_RUN_ID=41889183748 \
      GATE_NOW=2026-11-04T18:38:45Z python scripts/etl_gate.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

WORKFLOW_FILE = "etl-nightly.yml"
ETL_JOB_NAME = "etl"
# 09:00 UTC = 03:00 CST / 04:00 CDT: before the 05:00 CT primary in both seasons.
WINDOW_HOUR_UTC = 9
PER_PAGE = 50  # ~2 runs/day, so one page is ~3 weeks of history
MAX_PAGES = 5
API_ROOT = "https://api.github.com"


def parse_ts(value: str) -> datetime:
    """GitHub ISO-8601 timestamp ('2026-11-04T11:00:12Z') -> aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def window_start(now: datetime) -> datetime:
    """The most recent 09:00 UTC at or before `now` (yesterday's before 09:00)."""
    now = now.astimezone(timezone.utc)
    start = now.replace(hour=WINDOW_HOUR_UTC, minute=0, second=0, microsecond=0)
    if start > now:
        start -= timedelta(days=1)
    return start


def candidate_run_ids(
    runs: Iterable[dict[str, Any]],
    since: datetime,
    self_id: int,
    until: datetime | None = None,
) -> list[int]:
    """Ids of OTHER runs created in [since, until] that completed with success.

    `until` (default: no bound) only matters for a GATE_NOW replay of a past
    night, where runs created after the replayed moment must not count.

    A run whose etl job was skipped also concludes "success", so a candidate is
    only a candidate; `etl_job_succeeded` on its jobs decides.
    """
    out: list[int] = []
    for run in runs:
        if int(run["id"]) == self_id:
            continue
        created = parse_ts(run["created_at"])
        if created < since or (until is not None and created > until):
            continue
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            continue
        out.append(int(run["id"]))
    return out


def etl_job_succeeded(jobs: Iterable[dict[str, Any]]) -> bool:
    return any(
        j.get("name") == ETL_JOB_NAME and j.get("conclusion") == "success" for j in jobs
    )


def find_completed_run(
    list_runs_page: Callable[[int], list[dict[str, Any]]],
    list_jobs: Callable[[int], list[dict[str, Any]]],
    since: datetime,
    self_id: int,
    until: datetime | None = None,
) -> int | None:
    """First run (newest first) since `since` whose etl job succeeded, else None.

    `list_runs_page(page)` returns one page of the UNFILTERED runs listing
    (newest first); paging stops once a page reaches back past `since`.
    """
    for page in range(1, MAX_PAGES + 1):
        runs = list_runs_page(page)
        for run_id in candidate_run_ids(runs, since, self_id, until):
            if etl_job_succeeded(list_jobs(run_id)):
                return run_id
        if len(runs) < PER_PAGE or any(parse_ts(r["created_at"]) < since for r in runs):
            break
    return None


def _api_get(path: str, token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{API_ROOT}/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _emit(run: bool, message: str) -> None:
    print(message)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"run={'true' if run else 'false'}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(message + "\n")


def main() -> int:
    event = os.environ.get("EVENT", "?")
    if os.environ.get("GUARDED") != "true":
        _emit(True, f"Unguarded trigger ({event}): running the ETL.")
        return 0

    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    self_id = int(os.environ.get("GITHUB_RUN_ID", "0"))
    now = (
        parse_ts(os.environ["GATE_NOW"])
        if os.environ.get("GATE_NOW")
        else datetime.now(timezone.utc)
    )
    since = window_start(now)
    since_s = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    base = f"repos/{repo}/actions"
    try:
        done_id = find_completed_run(
            lambda page: _api_get(
                f"{base}/workflows/{WORKFLOW_FILE}/runs?per_page={PER_PAGE}&page={page}",
                token,
            )["workflow_runs"],
            lambda run_id: _api_get(f"{base}/runs/{run_id}/jobs?per_page=100", token)[
                "jobs"
            ],
            since,
            self_id,
            until=now,
        )
    except Exception as exc:  # noqa: BLE001 - fail open: see module docstring
        print(
            f"::warning::etl gate could not read the GitHub API ({exc!r}); running the ETL."
        )
        _emit(
            True,
            f"Guarded trigger ({event}): GitHub API unreadable, running the ETL (fail open).",
        )
        return 0

    if done_id is not None:
        _emit(
            False,
            f"Guarded trigger ({event}): run {done_id} already completed the ETL since {since_s}. Skipping.",
        )
    else:
        _emit(
            True,
            f"Guarded trigger ({event}): no successful ETL since {since_s}. Running.",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
