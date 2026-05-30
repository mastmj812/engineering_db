"""Daily-run notification: email summary + healthchecks.io dead-man's-switch.

Two channels, both opt-in via env vars (missing values = channel disabled):

  1. **Email summary** (NOTIFY_EMAIL_TO + SMTP creds): a 10-line plain-text
     table sent at end of every run_daily, success or failure. Tells you
     *what happened*: per-step status, row counts, curated.* freshness.

  2. **Healthchecks.io ping** (HEALTHCHECKS_PING_URL): a "still alive"
     beacon. ``ping_healthcheck("/start")`` at start, then ``""`` on
     success or ``"/fail"`` on completion. Closes the failure mode email
     can't catch: *the scheduled task never fired at all* (laptop asleep,
     user not logged in, Windows Task Scheduler silently failing).

All operations swallow errors and log them rather than raising — a
broken notification path should not poison the ETL run itself. Every
function is a no-op when its config is missing.

Gmail SMTP setup (one-time):
    1. Enable 2-factor auth on the Gmail account.
    2. Generate an app password at https://myaccount.google.com/apppasswords
       (16 chars, no spaces in the value).
    3. Use that app password as NOTIFY_SMTP_PASS. Regular Gmail
       passwords don't work with SMTP since the 2022 deprecation.

Healthchecks.io setup (free tier handles this comfortably):
    1. Sign up at https://healthchecks.io.
    2. Create a check; set schedule to "daily at 06:00" with a grace
       period of ~2 hours to cover slow runs.
    3. Copy the unique ping URL (looks like
       https://hc-ping.com/<uuid>). Set HEALTHCHECKS_PING_URL to it.
    4. Add an email/Slack/SMS integration on the check so missed pings
       reach you.
"""

from __future__ import annotations

import logging
import os
import smtplib
import socket
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from etl.db import get_connection

logger = logging.getLogger(__name__)

# Timeout for healthcheck pings + SMTP connect. Keep short so a hung
# notification doesn't extend the run by minutes.
_HTTP_TIMEOUT_S = 10
_SMTP_TIMEOUT_S = 30


def _env(name: str) -> str | None:
    """Return env var value, or None if unset/empty."""
    return os.getenv(name) or None


def ping_healthcheck(suffix: str = "") -> None:
    """Ping the configured healthchecks.io URL.

    ``suffix`` should be ``"/start"`` at run start, ``""`` on full
    success, or ``"/fail"`` on completion-with-failures.

    No-op when ``HEALTHCHECKS_PING_URL`` is unset. Swallows network
    errors — a missed ping is a noisy day, not a broken ETL.
    """
    load_dotenv()
    url = _env("HEALTHCHECKS_PING_URL")
    if not url:
        return
    target = url.rstrip("/") + suffix
    try:
        requests.get(target, timeout=_HTTP_TIMEOUT_S)
        logger.info("healthcheck pinged: %s", target)
    except Exception:
        logger.exception("healthcheck ping failed (non-fatal): %s", target)


def collect_freshness() -> dict[str, Any]:
    """Read freshness signals from curated.*.

    The most important is ``MAX(prod_date) FROM curated.production`` —
    that's how you tell upstream actually shipped new data even when
    the ETL itself reports success.

    Returns an empty dict on any DB error (notification still tries to
    go out, just without freshness numbers).
    """
    out: dict[str, Any] = {}
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(prod_date) FROM curated.production")
                row = cur.fetchone()
                if row:
                    out["max_prod_date"] = row[0]

                cur.execute("SELECT COUNT(*) FROM curated.wells")
                row = cur.fetchone()
                if row:
                    out["curated_wells_count"] = row[0]

                cur.execute("SELECT COUNT(*) FROM curated.production")
                row = cur.fetchone()
                if row:
                    out["curated_production_count"] = row[0]
        finally:
            conn.close()
    except Exception:
        logger.exception("freshness collection failed (non-fatal)")
    return out


def collect_novi_export_date() -> str | None:
    """Read the Novi export date from ExportDate.txt on disk.

    Tells you which Novi snapshot the curated layer is built from. Path
    follows the SDK's directory convention; if the scope changes from
    ``us-horizontals`` the .env's NOVI_SCOPE drives this too.

    Returns None when the file is missing (e.g. before first sync) or
    unreadable.
    """
    load_dotenv()
    scope = os.getenv("NOVI_SCOPE", "us-horizontals")
    candidate = (
        Path("data")
        / scope
        / "All basins"
        / "All subbasins"
        / "ExportDate.txt"
    )
    if not candidate.exists():
        return None
    try:
        return candidate.read_text(encoding="utf-8").strip() or None
    except Exception:
        logger.exception("read of %s failed (non-fatal)", candidate)
        return None


def build_email(
    report_steps: list[Any],
    freshness: dict[str, Any],
    novi_export_date: str | None,
    log_path: Path | None,
) -> tuple[str, str]:
    """Build the subject + plain-text body.

    ``report_steps`` is the list of StepResult dataclasses from the
    orchestrator. Status comes from ``status``; ``duration_s`` and
    ``rows`` are formatted for the table.
    """
    overall_ok = all(s.status == "success" for s in report_steps)
    today_iso = date.today().isoformat()
    host = socket.gethostname()

    if overall_ok:
        subject = f"[engineering_db] daily ETL OK — {today_iso}"
    else:
        failed_names = [s.name for s in report_steps if s.status != "success"]
        subject = (
            f"[engineering_db] daily ETL FAILED — {today_iso} "
            f"({', '.join(failed_names)})"
        )

    lines: list[str] = []
    lines.append(f"engineering_db daily ETL — {today_iso}")
    lines.append(f"Host: {host}")
    lines.append("")
    header = f"{'STEP':<28} {'STATUS':<9} {'DURATION':>10} {'ROWS':>14}"
    sep = "-" * len(header)
    lines.append(header)
    lines.append(sep)
    for s in report_steps:
        duration_str = f"{s.duration_s:.1f}s"
        rows_str = f"{s.rows:,}" if s.rows else "0"
        lines.append(
            f"{s.name:<28} {s.status:<9} {duration_str:>10} {rows_str:>14}"
        )
        if s.status != "success" and s.error:
            # Indent the error so it groups with its step row.
            lines.append(f"    error: {s.error}")
    lines.append("")

    # Freshness signals — answer "did upstream ship new data?"
    lines.append("Freshness:")
    max_prod = freshness.get("max_prod_date")
    if max_prod:
        days_behind = (date.today() - max_prod).days
        lines.append(
            f"  curated.production.MAX(prod_date) = {max_prod} "
            f"({days_behind} days behind today)"
        )
    else:
        lines.append("  curated.production.MAX(prod_date) = (unknown)")
    if "curated_wells_count" in freshness:
        lines.append(
            f"  curated.wells row count = {freshness['curated_wells_count']:,}"
        )
    if "curated_production_count" in freshness:
        lines.append(
            f"  curated.production row count = "
            f"{freshness['curated_production_count']:,}"
        )
    if novi_export_date:
        lines.append(f"  Novi ExportDate = {novi_export_date}")

    if log_path is not None:
        lines.append("")
        lines.append(f"Log file: {log_path}")

    return subject, "\n".join(lines)


def send_email(subject: str, body: str) -> None:
    """Send a plain-text email via SMTP (STARTTLS on port 587 by default).

    No-op when any of the SMTP env vars are missing. Swallows send
    errors — a Gmail outage shouldn't crash the run summary path.
    """
    load_dotenv()
    to_addr = _env("NOTIFY_EMAIL_TO")
    sender = _env("NOTIFY_EMAIL_FROM")
    host = _env("NOTIFY_SMTP_HOST") or "smtp.gmail.com"
    try:
        port = int(os.getenv("NOTIFY_SMTP_PORT", "587"))
    except ValueError:
        port = 587
    user = _env("NOTIFY_SMTP_USER")
    password = _env("NOTIFY_SMTP_PASS")

    required = {
        "NOTIFY_EMAIL_TO": to_addr,
        "NOTIFY_EMAIL_FROM": sender,
        "NOTIFY_SMTP_USER": user,
        "NOTIFY_SMTP_PASS": password,
    }
    missing = [name for name, val in required.items() if not val]
    if missing:
        logger.info("email skipped — missing env: %s", missing)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT_S) as smtp:
            smtp.starttls()
            smtp.login(user, password)  # type: ignore[arg-type]
            smtp.send_message(msg)
        logger.info("notification email sent to %s", to_addr)
    except Exception:
        logger.exception("email send failed (non-fatal)")


def notify_run(report_steps: list[Any], log_path: Path | None = None) -> None:
    """High-level: collect freshness + Novi date, build email, send +
    ping healthcheck.

    ``report_steps`` is the orchestrator's list of StepResult items.
    ``log_path`` is the day's log file (included in the email so a
    human can pull it for forensics).
    """
    freshness = collect_freshness()
    novi_date = collect_novi_export_date()
    subject, body = build_email(report_steps, freshness, novi_date, log_path)

    all_ok = all(s.status == "success" for s in report_steps)
    ping_healthcheck("" if all_ok else "/fail")
    send_email(subject, body)
