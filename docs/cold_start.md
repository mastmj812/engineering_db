# ETL cold-start — stand up the `oilgas` nightly on any machine

The warehouse (`oilgas`) now lives on **Supabase** (managed Postgres). The
**nightly ETL runner** (`run_daily`) lives on **GitHub Actions** (see §6) —
nothing is tied to a physical machine anymore. This doc remains the runbook for
standing up a *manual/fallback* host (a clean box runs the nightly in an
afternoon), which you'd want if Actions is down, for the quarterly Novi
Intelligence reload, or for ad-hoc backfills.

> Scope: this stands up the *ETL runner* against the existing Supabase warehouse.
> It does **not** migrate or restore the database — for that see
> [`supabase_migration_runbook.md`](supabase_migration_runbook.md).

Estimated time: **~½ day** first time, **~1 hr/quarter** to re-verify.

---

## 0. What the host actually does

Windows Task Scheduler runs `python -m scripts.run_daily` once a day. `run_daily`:

1. Syncs Novi bulk TSVs to disk (`etl.novi.sync`).
2. COPYs Novi TSVs into `raw_novi.*` (`etl.novi.load`).
3. Pulls Enverus wells deltas into `raw_enverus.wells` (`etl.enverus.pull_wells`).
4. Refreshes the curated matviews (`etl.refresh` / `curated.refresh_all`).
5. Emails a summary and pings the healthchecks.io dead-man switch (`etl.notify`).

Everything reads config from `.env`. No machine-specific state lives in code.

---

## 1. Prerequisites

- **Python 3.12** on PATH (`python --version`).
- **git**.
- Outbound network to: Supabase (`*.supabase.co` / `*.pooler.supabase.com`),
  Enverus API, Novi API, `hc-ping.com`, and SMTP (if email is used).
- The **`.env` secrets** and **vendor credentials** (see §3–4). These are the only
  things you can't recreate from the repo — keep a copy in the password manager.

No local Postgres is needed on the ETL host — the DB is remote (Supabase).

---

## 2. Clone + Python env

```powershell
git clone https://github.com/mastmj812/engineering_db.git
cd engineering_db
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The scheduled task invokes this venv's python directly (`.venv\Scripts\python.exe`),
so it does not depend on an activated shell.

---

## 3. `.env` — copy `.env.example` and fill in

`cp .env.example .env`, then set:

| Var | What | Where to get it |
|---|---|---|
| `DB_HOST` | Supabase **session** host, e.g. `db.<ref>.supabase.co` | Supabase dashboard → Project Settings → Database → Connection (Session). The one-liner is cached at `C:\Users\MichaelMast\db_dumps\supabase.url`. |
| `DB_PORT` | `5432` (session pooler; **not** 6543) | ETL needs a real session for COPY/CONCURRENTLY — 6543 is the *apps'* transaction pooler and won't do those. |
| `DB_NAME` | `postgres` | Supabase default DB name. |
| `DB_USER` | `postgres.<ref>` (pooler) or `postgres` (direct) | Matches the chosen host. |
| `DB_PASSWORD` | DB password | Supabase dashboard (or password manager). |
| `ENVERUS_SECRET_KEY` | Enverus Developer API secret | Enverus Developer Portal → API keys. |
| `NOVI_EMAIL` / `NOVI_PASSWORD` | Novi login | Novi account owner. |
| `NOVI_SCOPE` / `NOVI_VERSION` | Novi API scope + version | Current values in the password-manager entry; unchanged since setup. |
| `NOTIFY_EMAIL_*` / `NOTIFY_SMTP_*` | End-of-run email (optional) | Gmail needs an **app password** (not the account password), 2FA on first. |
| `HEALTHCHECKS_PING_URL` | Dead-man switch (optional but recommended) | healthchecks.io check → ping URL (`https://hc-ping.com/<uuid>`). |

`.env` is gitignored — it never leaves the machine via git. Treat it as a secret.

---

## 4. Vendor credentials

- **Enverus**: `ENVERUS_SECRET_KEY` in `.env`. Rotated at the Enverus Developer
  Portal. The SDK (`enverus-developer-api`) reads it via `etl/enverus/client.py`.
- **Novi**: `NOVI_EMAIL` / `NOVI_PASSWORD` in `.env`. These drive the bulk-TSV
  sync (`etl/novi/sdk.py`). If Novi login changes, update `.env` — no code change.
- **Supabase**: `DB_*` in `.env` (§3).

All three live only in `.env` + the password manager. Losing the laptop loses no
credentials you can't re-fetch from those two places.

---

## 5. Smoke-test connectivity (read-only) before scheduling

```powershell
# DB reachable + ETL cursor visible (read-only):
.\.venv\Scripts\python.exe -c "from etl.db import get_connection; c=get_connection(); cur=c.cursor(); cur.execute('select max(run_finished_at) from meta.etl_log'); print('etl_log latest:', cur.fetchone()[0]); c.close()"
```

If that prints a timestamp, the host can reach the warehouse. (Enverus/Novi are
exercised by the first real run in §7.)

---

## 6. The nightly of record: GitHub Actions

Since 2026-07-21 the nightly runs as the **`etl-nightly` workflow**
(`.github/workflows/etl-nightly.yml`). Since 2026-11-02 its primary trigger
is an external scheduler (cron-job.org) that POSTs the `workflow_dispatch`
REST endpoint at 05:00 America/Chicago with a fine-grained PAT; the GitHub cron
(`15 11 * * *` UTC) fired 3-10 h late under GitHub's best-effort scheduler and
is now only a backstop that the `gate` job skips once an ETL has succeeded
since 09:00 UTC. The workflow header has the measured lag and vendor timing;
§6a below sets up the PAT and the cron-job.org job. Secrets live in
the repo's **Actions secrets** (`gh secret list`) and mirror `.env`; the full
run log is uploaded as a workflow artifact, and the email summary +
healthchecks.io dead-man switch work exactly as they did on the laptop.

- Manual/catch-up run: *Actions → etl-nightly → Run workflow* (or
  `gh workflow run etl-nightly.yml`).
- The rollout was phased: manual read-only preflight → manual full run →
  cron + laptop task disabled **in the same change** (so laptop and Actions
  never both ran against prod). The workflow file header records the history.
- The old Windows task (`engineering_db_daily_etl`) is **disabled, not
  deleted** — it is the tested fallback. Re-enable it (and disable the cron)
  only as a pair.

## 6a. The primary trigger: fine-grained PAT + cron-job.org

GitHub's `schedule:` cron is best-effort (it fired 2.6-9.5 h late on the 60
nights before 2026-11-02), but a `workflow_dispatch` API call starts a run in
seconds. So an always-on outside scheduler makes that call at a fixed local
hour. Two pieces, both created by Michael (the token value never goes into
chat, the repo, `.env` or a ticket):

**A. The token** (a fine-grained personal access token: a password that only
lets the holder do what its scope lists). GitHub → profile picture →
*Settings* → *Developer settings* → *Personal access tokens* → *Fine-grained
tokens* → *Generate new token*:

- Token name `etl-nightly-dispatch`; resource owner `mastmj812`.
- Expiration: the longest offered (1 year); put a reminder two weeks before.
- Repository access: *Only select repositories* → `engineering_db`.
- Repository permissions: **Actions → Read and write**. Nothing else
  (`Metadata: Read-only` is added automatically). With only this scope a leaked
  token can start, cancel or re-run this repo's workflows and delete run logs;
  it cannot read code or secrets, push, or change settings.
- *Generate token*, copy it (it is shown once) and paste it straight into B.

**B. The scheduler** (cron-job.org, free). *Create cronjob*:

- Title `engineering_db etl-nightly`.
- URL `https://api.github.com/repos/mastmj812/engineering_db/actions/workflows/etl-nightly.yml/dispatches`
- Schedule: every day at **05:00**, time zone **America/Chicago** (it follows
  DST, so the run stays at 05:00 CT year-round).
- *Advanced*: request method **POST**; headers
  `Accept: application/vnd.github+json`,
  `Authorization: Bearer <the token from A>`,
  `X-GitHub-Api-Version: 2022-11-28`,
  `Content-Type: application/json`; request body
  `{"ref":"main","inputs":{"only_if_needed":"true"}}`.
- Notifications: email on failure.
- Save, then *Test run*. Expect HTTP **204** and, within seconds, a new
  `workflow_dispatch` run under *Actions → etl-nightly*. If that day's ETL
  already succeeded, its `gate` job skips the `etl` job (green, etl skipped),
  so the test does not re-run the ETL.

Responses: 204 = dispatched; 401 = token expired or revoked (make a new one in
A, paste it into the header); 404 = wrong URL or token not scoped to this repo;
422 = the `only_if_needed` input is missing on `main` (the workflow change must
be merged first). While the primary is broken the backstop cron still runs the
ETL each day, just late.

## 6b. Fallback: register the nightly on a host (Windows Task Scheduler)

Matches the retired laptop task (`engineering_db_daily_etl`, daily 06:00):

```powershell
$py   = "C:\Users\MichaelMast\Projects\engineering_db\.venv\Scripts\python.exe"
$cwd  = "C:\Users\MichaelMast\Projects\engineering_db"
$action  = New-ScheduledTaskAction -Execute $py -Argument "-m scripts.run_daily" -WorkingDirectory $cwd
$trigger = New-ScheduledTaskTrigger -Daily -At 6am
# Run whether or not the user is logged on so a locked/asleep-then-woken laptop still fires:
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName "engineering_db_daily_etl" -Action $action -Trigger $trigger -Principal $principal
```

> **Laptop-asleep caveat (why the dead-man switch exists):** Task Scheduler
> silently skips a daily trigger if the machine is asleep at 06:00 and does not
> "catch up" by default. The healthchecks.io check (§3) is what tells you the run
> never fired. Consider enabling *"Run task as soon as possible after a scheduled
> start is missed"* and a wake timer in the task's settings.

---

## 7. First real run + verify

```powershell
cd C:\Users\MichaelMast\Projects\engineering_db
.\.venv\Scripts\python.exe -m scripts.run_daily
```

Watch the end-of-run summary table (per-step status/rows/duration). Then confirm:

- The summary email arrived (if configured) and the healthchecks check went green.
- `meta.etl_log` advanced: re-run the §5 smoke test — the timestamp should be today.

Once one manual run is green, the scheduled task will do the same nightly.

---

## 8. Backups & restore (pointers)

- **Backups:** the `oilgas` dump + offsite sync are covered by the backup job
  (see the backup runbook / `infra/backup` in the anduin repo for the pattern).
  Dumps land in `C:\Users\MichaelMast\db_dumps\` and are mirrored to the
  OneDrive `…\Engineering - General\Backup\oilgas\` folder on the same schedule.
- **Restore / rebuild:** [`supabase_migration_runbook.md`](supabase_migration_runbook.md)
  (restore raw+ref+meta from a dump, then rebuild `curated` from `sql/*.sql`).
  A validated local-scratch restore drill and its timing are recorded there.

---

## 9. Gotchas carried over from the live host

- **DB connection:** ETL uses the **session** connection (5432). The apps use the
  **transaction pooler** (6543) — do not point `run_daily` at 6543 (no COPY /
  `REFRESH … CONCURRENTLY`).
- **`refresh_all()` over a pooler stalls** (one long silent statement); run the
  refresh from a host with a stable/direct connection or with libpq TCP
  keepalives. See the migration runbook §0b.
- **PowerShell 5.1 encoding:** scripts other tools parse must be ASCII / UTF-8
  with care — a stray em-dash in a `.ps1` string breaks PS 5.1 parsing.
