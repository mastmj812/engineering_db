"""Thin anduin HTTP client (bearer JWT; default http://localhost:8000).

Endpoints used by Gates 5-6 (shapes verified against anduin backend/app
2026-09-18). Credentials come from ANDUIN_EMAIL / ANDUIN_PASSWORD in the
environment — never from config files or arguments, and never logged.

Respects the manual-override guard by construction: this client never
refits a row with manual_override=TRUE, locked=FALSE — `forecast()` checks
existing rows first and refuses, listing them for triage.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

DEFAULT_URL = os.environ.get("ANDUIN_URL", "http://localhost:8000")
BATCH_MAX = 500


class AnduinError(RuntimeError):
    pass


class Anduin:
    def __init__(self, base_url: str = DEFAULT_URL, timeout: float = 300.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self._authed = False

    def login(self) -> None:
        email, pw = os.environ.get("ANDUIN_EMAIL"), os.environ.get("ANDUIN_PASSWORD")
        if not email or not pw:
            raise AnduinError("set ANDUIN_EMAIL and ANDUIN_PASSWORD in the environment")
        r = self._req("POST", "/api/auth/login", json={"email": email, "password": pw}, auth=False)
        self.s.headers["Authorization"] = f"Bearer {r['access_token']}"
        self._authed = True

    # Paths safe to repeat after a dropped connection: reads, plus the TC
    # compute PREVIEW (persists nothing). /forecasts/batch is NOT here — a
    # repeat would enqueue a second job; login is cheap to redo by hand.
    _IDEMPOTENT_POST = ("/api/type-curves/compute",)

    def _req(self, method: str, path: str, *, auth: bool = True, **kw: Any) -> Any:
        if auth and not self._authed:
            self.login()
        retryable = method == "GET" or path in self._IDEMPOTENT_POST
        attempts = 3 if retryable else 1
        for i in range(attempts):
            try:
                r = self.s.request(method, f"{self.base}{path}", timeout=self.timeout, **kw)
                break
            except requests.ConnectionError as e:
                # uvicorn closes idle keep-alive sockets after 5 s; a request
                # that reuses one at that instant sees "Connection aborted"
                # (2026-09-18 incident) — not an outage. Retry the safe ones.
                if i + 1 < attempts:
                    time.sleep(1.0 + i)
                    continue
                raise AnduinError(
                    f"{method} {path}: connection to {self.base} failed ({e.__class__.__name__}: {e})"
                    + ("" if retryable else " — not retried (not idempotent); check GET /api/sync/status before re-running")
                ) from e
        if r.status_code >= 400:
            raise AnduinError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.content else None

    # -- forecasts ---------------------------------------------------------
    def forecasts(self, api10s: list[str]) -> list[dict[str, Any]]:
        """GET /api/forecasts?api10=..: one row per well x stream. di_initial is
        NOMINAL /yr; di_effective is anduin's 1-yr effective (same formula as
        dealintake.decline)."""
        out: list[dict[str, Any]] = []
        for i in range(0, len(api10s), 100):
            chunk = api10s[i:i + 100]
            out.extend(self._req("GET", "/api/forecasts", params=[("api10", a) for a in chunk]))
        return out

    def forecast(
        self,
        api10s: list[str],
        *,
        only_missing: bool = True,
        poll_s: float = 3.0,   # < uvicorn's 5 s keep-alive timeout
        max_wait_s: float = 3600.0,
    ) -> dict[str, Any]:
        """POST /api/forecasts/batch (<=500/call), poll GET /api/sync/jobs/{id}.

        only_missing (default): fit ONLY wells with no forecast row yet. A refit
        of an already-fitted well silently shifts every saved type curve that
        resolves to it without marking the curve stale (known override-loss
        path) — so existing fits are reused, never refreshed, unless the
        reviewer asks for it explicitly (only_missing=False).
        Always refuses when a target row is manual_override=TRUE, locked=FALSE.
        """
        existing = self.forecasts(api10s)
        have = {r["api10"] for r in existing}
        guarded = sorted({r["api10"] for r in existing if r.get("manual_override") and not r.get("locked")})
        targets = [a for a in api10s if a not in have] if only_missing else list(api10s)
        if not only_missing and guarded:
            raise AnduinError(
                f"{len(guarded)} well(s) have manual_override=TRUE, locked=FALSE — triage before refit: "
                + ", ".join(guarded[:20])
            )
        result = {"fitted": targets, "reused": sorted(have & set(api10s)) if only_missing else [],
                  "manual_override_unlocked": guarded, "job_ids": []}
        if not targets:
            return result
        job_ids = result["job_ids"]
        for i in range(0, len(targets), BATCH_MAX):
            r = self._req("POST", "/api/forecasts/batch", json={"api10s": targets[i:i + BATCH_MAX]})
            job_ids.append(r["job_id"])
        deadline = time.monotonic() + max_wait_s
        for jid in job_ids:
            while True:
                j = self._req("GET", f"/api/sync/jobs/{jid}")
                if j["status"] in ("succeeded", "failed", "cancelled"):
                    if j["status"] != "succeeded":
                        raise AnduinError(f"forecast job {jid} {j['status']}: {j.get('error')}")
                    break
                if time.monotonic() > deadline:
                    raise AnduinError(f"forecast job {jid} still {j['status']} after {max_wait_s:.0f}s")
                time.sleep(poll_s)
        return result

    # -- type curves -------------------------------------------------------
    def compute_type_curve(self, api10s: list[str], n_months: int | None = None) -> dict[str, Any]:
        """POST /api/type-curves/compute — PREVIEW, persists nothing. peak_ramp,
        per 1,000 ft of lateral. streams[s].fitted.Di is NOMINAL /yr."""
        body: dict[str, Any] = {
            "api10s": api10s, "normalization_basis": "per_lateral_ft", "alignment_method": "peak_ramp",
        }
        if n_months:
            body["n_months"] = n_months
        return self._req("POST", "/api/type-curves/compute", json=body)
