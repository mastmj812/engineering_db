"""Daily ETL orchestrator.

Intended to be invoked by Windows Task Scheduler:
    python -m scripts.run_daily

Sequence:
    1. Sync Novi bulk TSVs to disk (etl.novi.sync.sync_bulk)
    2. COPY Novi TSVs into raw_novi.* (etl.novi.load.load_all)
    3. Pull Enverus wells deltas into raw_enverus.wells (etl.enverus.pull_wells)
    4. Check the Novi INTEL share for new quarterly reports (notify-only;
       etl.intel_sf.detect — nonzero ROWS = reports awaiting a manual reload)
    5. Refresh curated materialized views (curated.refresh_all)

Each step is isolated in its own try/except so a single failure does not
block the rest. The end-of-run summary table reports per-step status,
duration, and rows touched.
"""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from etl import notify as notify_step
from etl import refresh as refresh_step
from etl.db import settle as db_settle
from etl.enverus import pull_wells as enverus_wells

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


@dataclass
class StepResult:
    """One row of the end-of-run summary table."""

    name: str
    status: str = "pending"
    duration_s: float = 0.0
    rows: int = 0
    error: str | None = None


@dataclass
class RunReport:
    """Aggregate of all step results for the current run."""

    started_at: datetime = field(default_factory=datetime.now)
    steps: list[StepResult] = field(default_factory=list)


def _configure_logging() -> Path:
    """Configure root logger to write to console and a dated log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"run_daily_{datetime.now().strftime('%Y-%m-%d')}.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_h = logging.FileHandler(log_path, encoding="utf-8")
    file_h.setFormatter(fmt)
    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setFormatter(fmt)
    root.addHandler(file_h)
    root.addHandler(stream_h)
    return log_path


def _run_step(
    name: str,
    fn: Callable[[], int | None],
    report: RunReport,
) -> None:
    """Run a single step, capture result, append to the report."""
    logger = logging.getLogger(__name__)
    logger.info("=== step start: %s ===", name)
    result = StepResult(name=name)
    started = time.monotonic()
    try:
        rv = fn()
        result.rows = int(rv) if isinstance(rv, int) else 0
        result.status = "success"
    except Exception as exc:
        result.status = "failed"
        result.error = str(exc)
        logger.exception("step failed: %s", name)
    finally:
        result.duration_s = time.monotonic() - started
        report.steps.append(result)
        logger.info(
            "=== step end: %s (status=%s, rows=%d, duration=%.1fs) ===",
            name,
            result.status,
            result.rows,
            result.duration_s,
        )


def _print_summary(report: RunReport) -> None:
    """Emit a formatted summary table to the configured logger."""
    logger = logging.getLogger(__name__)
    header = f"{'STEP':<28} {'STATUS':<9} {'DURATION':>10} {'ROWS':>10}"
    sep = "-" * len(header)
    lines = ["Run summary:", sep, header, sep]
    for s in report.steps:
        lines.append(
            f"{s.name:<28} {s.status:<9} {s.duration_s:>9.1f}s {s.rows:>10d}"
        )
        if s.error:
            lines.append(f"    error: {s.error}")
    lines.append(sep)
    logger.info("\n".join(lines))


def main() -> int:
    """Run the daily ETL pipeline. Returns 0 on full success, 1 if any step failed."""
    log_path = _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("run_daily starting; log file: %s", log_path)

    # Heartbeat: tell healthchecks.io the run actually started. The
    # success/"fail" ping at the end of notify_run distinguishes outcomes;
    # this /start ping resets the dead-man's-switch grace period so a
    # missed run alerts cleanly the next morning.
    notify_step.ping_healthcheck("/start")

    report = RunReport()
    state: dict[str, Path | None] = {"novi_bulk_dir": None}

    def step_novi_sync() -> int:
        # Imported lazily — module-level import would fail when sdk.py
        # has not been vendored yet, breaking the rest of the pipeline.
        from etl.novi.sync import sync_bulk

        state["novi_bulk_dir"] = sync_bulk()
        return 0

    def step_novi_load() -> int:
        if state["novi_bulk_dir"] is None:
            raise RuntimeError("novi.load skipped: novi.sync did not run successfully")
        from etl.novi.load import load_all

        return sum(load_all(state["novi_bulk_dir"]).values())

    # Wrap the per-step body in try/finally so the summary + notification
    # always fire — even if a bug in the orchestrator itself (not the
    # individual steps, which are already _run_step-guarded) raises.
    try:
        def step_settle() -> int:
            # Flatten the post-load memory spike before the next steps so a
            # small managed instance doesn't get pushed over (best-effort
            # CHECKPOINT + short pause). See etl.db.settle.
            db_settle()
            return 0

        def step_intel_report_check() -> int:
            # Notify-only: how many entitled Novi INTEL collections are visible
            # in the Snowflake share but not yet loaded into raw_intel. Nonzero
            # lands in the ROWS column + a loud WARNING in the log/email; the
            # quarterly reload itself stays manual. Lazy import so a missing
            # snowflake dependency can't break the rest of the pipeline.
            from etl.intel_sf.detect import check_new_reports

            return check_new_reports()

        _run_step("novi.sync", step_novi_sync, report)
        _run_step("novi.load", step_novi_load, report)
        _run_step("settle", step_settle, report)
        _run_step("enverus.pull_wells", enverus_wells.main, report)
        _run_step("intel_sf.report_check", step_intel_report_check, report)
        _run_step("curated.refresh", lambda: (refresh_step.main() or 0), report)
    finally:
        _print_summary(report)
        # notify_run pings the healthcheck (success or /fail) AND sends
        # the email summary. Both no-op cleanly when their env vars
        # are unset, so the notification path is opt-in per channel.
        try:
            notify_step.notify_run(report.steps, log_path=log_path)
        except Exception:
            # Defense in depth — notify_run already swallows its own
            # exceptions; this is the last guard against a notification
            # bug perturbing the orchestrator's exit code.
            logger.exception("notify_run raised (non-fatal)")

    failed = [s for s in report.steps if s.status == "failed"]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
