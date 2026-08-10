---
name: etl-nightly-triage
description: Diagnose and clear a failed etl-nightly GitHub Actions run — red run, missing summary email, or healthchecks.io dead-man alert. Classifies by known failure signature (vendor schema drift, connection flap, Enverus hang, Snowflake PAT, infra flake), applies the standing-authorized fix where one exists, re-runs, and verifies the warehouse advanced. Use when the nightly failed or its notifications went quiet.
---

# Nightly ETL failure triage (etl-nightly on GitHub Actions)

The nightly of record: `.github/workflows/etl-nightly.yml`, cron 11:15 UTC (~06:15 CT),
`concurrency: etl-nightly` (never two runs vs prod), 180-min timeout, Python 3.12, `DB_PORT=5432`
(session pooler — the direct host is IPv6-only and unreachable from runners). Step order inside
`scripts/run_daily.py`, each isolated in its own try/except:
`sweep_stale → novi.sync → novi.load → settle → enverus.pull_wells → intel_sf.report_check →
curated.refresh`. Three independent failure signals: the summary email (per-step status/rows/
error), the healthchecks.io dead-man switch, and the red Actions run with a 30-day `logs/*.log`
artifact.

**Ground rules:**
- Read-only diagnosis first. The only standing-authorized write is the additive Novi drift
  auto-add (already executed by the loader, not by you); every other DDL/write against Supabase
  needs explicit authorization.
- A normal night is ~15–18 min; a new Novi vintage adds ~45 min (`production_forecast` refresh).
  Don't call a 60-min run hung.
- Never retime the cron to "avoid" a failure window — the 17-night enverus streak tracked the
  post-`novi.load` memory spike, not a clock window.
- The nightly "PAT invalid; retrying PAT as password" log line is NORMAL (the reader account
  rejects the native PAT authenticator).

## 1. Pull the evidence

```powershell
gh run list --workflow etl-nightly.yml --limit 5
gh run view <run-id> --log-failed
gh run download <run-id> --dir "$env:TEMP\etl-logs"    # the logs artifact
```

Read the `run_daily` summary table (always printed, even on failure) — which step failed, error
text, rows. Then check the preflight: **a failed preflight means secrets/connectivity broke, not
the ETL** (it runs a read-only `meta.etl_log` + `curated.wells` query before anything writes).

If there's no red run at all but the email/healthchecks went quiet: check the run actually
scheduled (GitHub cron can skip), then check SMTP/healthchecks env — `notify_run` swallows its own
exceptions by design.

## 2. Classify by signature

| Signature | Diagnosis | Action |
|---|---|---|
| `UndefinedColumn` on `novi.load`, or the drift preflight `RuntimeError` naming a NEW column | Vendor drift, additive | If `reconcile_schema_drift()` auto-added it (loud WARNING in the log): the load already healed. **Follow-up required:** regen sql/02 (`python -m scripts.generate_novi_ddl`) and commit a numbered mirror `ALTER` so repo DDL matches live. If it did NOT auto-add (type off-whitelist / column absent from shipped schema): manual gate — sample the TSV/schema, write the numbered `ALTER`, **ask before applying**, then regen sql/02 |
| Drift preflight raises on a **removed** column | Vendor contract change | Hard stop by design — never widen `_SAFE_TYPE_RE` or auto-drop. Surface to Michael; this needs eyes and possibly a Novi ticket |
| `UndefinedColumn` on `enverus.pull_wells` | Enverus drift | Same pattern: numbered additive migration (sql/33 precedent), lowercase column names, nullable |
| `OperationalError` / connection reset mid-load, possibly repeating | Supabase restart/failover flap | `upsert_batch_resilient` rides most of these (10-retry budget, catches the `DatabaseError` protocol desync too). If it still died: plain re-run. Recurring at the same *step* (not time) → memory-pressure adjacency, not scheduling |
| Enverus step silent for 20+ min then killed | Half-open socket read hang | Verify `client.py` still injects the read timeout via the re-mounted adapter (`ENVERUS_READ_TIMEOUT`, default 120 s) and that the mount preserves the SDK `Retry`. The init token POST is NOT covered — a hang there is a different (rarer) animal |
| Snowflake auth failure on `intel_sf.report_check` | PAT expired | Michael rotates it in the Novi reader account; update the `SNOWFLAKE_PAT` Actions secret (21 secrets mirror `.env`) |
| Job stuck/failed at exactly **15:00** with "log not found" / "not acquired by runner" | Dead runner / GitHub outage | Re-run. Do not debug |
| `curated.refresh` failed on one matview | Usually transient or a missing optional matview | `erebor_locations` / `intel_forecast_accuracy` are `_OPTIONAL_MATVIEWS` — missing logs a warning and continues (expected mid-quarterly-reload). A real failure self-heals the gate: the next refresh re-attempts |
| `intel_sf.report_check` WARNING: new report detected | Not a failure | Notify-only. The quarterly reload is manual on Michael's go-ahead → `novi-quarterly-reload` skill. The alert self-clears once the report_name lands in `raw_intel.well_master` |

## 3. Re-run

```powershell
gh workflow run etl-nightly.yml
```

Concurrency-locked, so it's safe alongside nothing. `run_daily` steps are independently
idempotent (watermark upserts; DELETE-slice-then-COPY), so a partial night re-runs clean.

## 4. Verify the warehouse actually advanced

Read-only, via `etl.db.get_connection()` (5432):

- `SELECT source, table_name, status, run_finished_at, rows_inserted FROM meta.etl_log ORDER BY
  run_started_at DESC LIMIT 15` — the failed step now shows `success` with plausible rows.
- Freshness: `MAX(prod_date) FROM curated.production` days-behind, and the summary email's
  freshness block — this is how you tell the vendor actually shipped data even when every step
  reports success.
- healthchecks.io back to green; summary email arrived.
- If a drift fix was applied: `information_schema.columns` shows the new column live, AND the
  numbered migration + regenerated sql/02 are committed (PR, `etl` check) — **verify live and
  repo separately; a committed migration is not an applied one and vice versa.**

## Traps

- `meta.etl_log` has historically stranded `'running'` rows — `sweep_stale_runs` (12 h) runs
  first each night for exactly this; never gate anything on a count of `status='running'`.
- **The Enverus incremental cursor advances on ANY success, including 0 rows** (`MAX(run_finished_at)
  WHERE status='success'`, matched by `table_name = dataset` exactly). After touching any Enverus
  filter, verify rows landed — a silently-zeroing filter permanently skips its window.
- Renaming a `table_name` label breaks the `production_forecast` refresh gate
  (`LIKE 'ForecastWellMonths%'`) and/or the cursor. Labels are load-bearing; don't tidy them.
- Deletions never trip the refresh gate — after a `--reconcile`, run
  `python -m etl.refresh --force`.
- Don't kill a run mid-`curated.refresh` if avoidable; if you must, the gate records no success
  and the next run rebuilds — but a mid-`REFRESH CONCURRENTLY` kill leaves nothing broken, which
  is the one mercy here.
- Local `python -m scripts.run_daily` is the fallback, not the norm — it needs the laptop `.env`
  (5432 session pooler) and competes with nothing only because of the Actions concurrency group,
  which does NOT cover local runs. Check no Actions run is live first.
