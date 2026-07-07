# ETL cold-start — stand up the `oilgas` nightly on any machine

The warehouse (`oilgas`) now lives on **Supabase** (managed Postgres). The only
thing tied to a physical machine is the **nightly ETL runner** (`run_daily`) —
currently a Windows laptop. This doc makes that host **a config, not a machine**:
follow it and a clean box is running the nightly in an afternoon.

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

## 6. Register the nightly (Windows Task Scheduler)

Matches the current host's task (`engineering_db_daily_etl`, daily 06:00):

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
