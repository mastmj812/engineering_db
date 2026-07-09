# Supabase Reprovision Runbook — move `oilgas` to a self-administered org

Move the warehouse from the current (admin-inaccessible, crash-looping) Supabase
project to a NEW Supabase org/project you own, on **Large compute**. Same
platform both sides — every pooler workaround and connection pattern in the
codebase carries over unchanged; only hosts/credentials change.

Derived from `docs/supabase_migration_runbook.md` (the validated 2026-06-23
local→Supabase migration + 2026-07-07 restore drill). Differences: this is
**Supabase→Supabase, PG 17→17** (no version downgrade), and the warehouse now
includes the `raw_intel` schema (Novi INTEL Snowflake mirror, sql/27) with the
curated layer rebuilt on it (sql/29).

---

## 0. Strategy

Two paths — pick based on whether the OLD instance can hold still long enough
for a dump:

- **A. Dump/restore (preferred, ~3–5 h wall clock):** `pg_dump` the source
  schemas from the old project (raw_novi, raw_enverus, raw_novi_intel,
  **raw_intel**, ref, meta), restore into the new project, rebuild `curated`
  from repo SQL. Preserves `meta.etl_log` (ETL cursors) and `raw_intel.stick_id_map`
  (stick_id stability) without any re-extraction.
- **B. Rebuild from source (fallback if the old instance won't stay up):**
  restore the latest offsite dump (predates `raw_intel`), then re-extract
  `raw_intel` from the Snowflake share (`load_intel_sf --ddl --all`, ~6 min)
  and re-run the cutover chain. Everything is re-derivable; you lose only
  `meta.etl_log` history newer than the offsite dump, and stick_ids get
  re-minted (erebor selections are session-ephemeral, so that's cosmetic).

**Run all migration steps on the session pooler (5432) or direct connection;
the transaction pooler (6543) is for apps only** — COPY/CREATE MATVIEW/REFRESH
need a real session.

---

## 1. Create the new org + project (dashboard, ~30 min)

- [ ] Create a new **organization** (not a personal default org) — company-ish
  name; this makes the eventual billing/ownership transfer to IT a settings
  change. Your card, you as Owner.
- [ ] New project: **region `us-east-1`** (same as current — keeps app latency
  parity and dump/restore traffic intra-region), Postgres **17**.
- [ ] **Before restoring anything** (validated the hard way in the 2026-06-23
  migration — an undersized disk crashed mid-restore):
  - Compute: **Large** (8 GB RAM).
  - Disk: **80 GB** (current DB ~48 GB post-forecast-drop; new forecast adds
    ~8–10 GB; leave rebuild headroom).
- [ ] Record: project ref `<NEWREF>`, database password, pooler host
  (`aws-1-us-east-1.pooler.supabase.com`), direct host (`db.<NEWREF>.supabase.co`).
- [ ] Session-pooler user is `postgres.<NEWREF>`.
- [ ] Extensions (SQL editor):
  ```sql
  create extension if not exists postgis;    -- lands in `extensions` — correct
  create extension if not exists pg_trgm;
  alter database postgres set search_path to "$user", public, extensions;
  ```
  Unlike the 2026-06 migration there is **no `public.geometry` sed needed**:
  the dump now comes FROM Supabase, whose geometry types are already qualified
  against the `extensions` schema, and the new project matches.

---

## 2. Dump the old project (strategy A)

Wait for a stable window (old instance currently restarts under load — try
off-hours; the dump is read-only and lighter than the loads that crashed it).

```powershell
# session pooler of the OLD project; -Fd directory format allows -j parallelism
pg_dump "postgresql://postgres.qrabpxeaepkwfdjymxab:<OLDPW>@aws-1-us-east-1.pooler.supabase.com:5432/postgres" `
  -Fd -j 2 --no-owner --no-privileges --no-tablespaces `
  --schema=raw_novi --schema=raw_enverus --schema=raw_novi_intel `
  --schema=raw_intel --schema=ref --schema=meta `
  -f C:\Users\MichaelMast\db_dumps\oilgas_reprov_<date>
```

- `curated` deliberately excluded — rebuilt from repo SQL (§4), same as always.
- `qa` excluded (scratch).
- If the pooler drops the parallel dump, fall back to `-Fc` single-stream.
- Verify: `pg_restore -l <dir>` lists 6 schemas; spot-check sizes.

---

## 3. Restore into the new project

```powershell
pg_restore --no-owner --no-privileges -j 4 `
  -d "postgresql://postgres.<NEWREF>:<NEWPW>@aws-1-us-east-1.pooler.supabase.com:5432/postgres" `
  C:\Users\MichaelMast\db_dumps\oilgas_reprov_<date>
```

- If long COPYs die at ~2 min: the platform `statement_timeout` default.
  Session-level `SET statement_timeout=0` works on the session pooler; stream
  through psql with a leading SET (pattern in the old runbook §0b) — or on
  Large this may simply not trigger. `etl/db.py` already sets it per-session
  for everything ETL-side afterward.
- Check the log for `pg_restore: error`, not just the exit code.

---

## 4. Rebuild `curated` (repo root, session connection, drill-verified order)

```powershell
psql <session-conn> -c "create schema if not exists curated;"
psql <session-conn> -f sql/14_formation_crosswalk.sql
psql <session-conn> -f sql/04_curated.sql
psql <session-conn> -f sql/16_formation_blueox.sql
psql <session-conn> -f sql/18_bench_reference.sql
psql <session-conn> -f sql/20_producing_reference.sql
psql <session-conn> -f sql/23_formation_blueox_tvd.sql   # ~50 min (40-NN); REQUIRED before sql/06
psql <session-conn> -f sql/05_curated_production.sql
psql <session-conn> -f sql/06_curated_derived.sql
psql <session-conn> -f sql/10_curated_forecast.sql
psql <session-conn> -f sql/29_curated_intel_sf.sql       # intel layer from raw_intel (replaces sql/12)
psql <session-conn> -f sql/19_intel_formation_blueox.sql
```

Then the erebor-facing tail (the apply script now handles the sql/20→23→
wells_enriched→21 CASCADE ordering internally — fixed 2026-07-09):

```powershell
python -m scripts.apply_reconciled_inventory
python -c "from scripts.load_intel_sf import run_sql_file; run_sql_file('25_net_new_pdp.sql')"
python -m scripts.apply_erebor_locations                  # FINAL — restores refresh_all()
python -c "from scripts.load_intel_sf import run_sql_file; run_sql_file('26_geography_indexes.sql')"
```

**Forecast fact** (not in curated; raw_intel table restores empty or partial):

```powershell
# oilgas .env must already point at the NEW project (§6 step 1)
python -m scripts.load_intel_sf --forecast    # 73.2M rows, chunked commits; ~60-90 min
```

Validate vs `qa.forecast_sample` if it was carried over, else spot-check 20
wells against the share (pattern in `scripts/reconcile_intel_sf.py::sec_forecast_sample`).

---

## 5. Verify

Counts on the new project (2026-07-09 baselines; re-count the live source at
migration time — raw_novi/raw_enverus grow nightly):

| table | rows |
|---|---|
| raw_intel.well_master | 251,902 |
| raw_intel.arps_forecast | 1,834,974 |
| raw_intel.stick_id_map | 251,902 (strategy A: max ≈ 1,500,520 preserved) |
| raw_intel.production_forecast | 73,195,074 (after §4 forecast load) |
| raw_novi_intel.pads / land_grid / basin_outline | 9,040 / 42,668 / 2 (frozen trio) |
| curated.intel_locations | 251,902 |
| curated.reconciled_inventory | 131,465 |
| curated.erebor_locations | ~262,600 (PDP arm grows nightly) |

Plus:
- `select postgis_full_version();` and a non-null-geom count on curated.wells.
- `select curated.intel_vintage_date();` → `2025-09-30`.
- erebor tile EXPLAIN hits `idx_erebor_locations_geom` (pattern printed by
  `apply_erebor_locations`).
- `select source, table_name, max(run_finished_at) from meta.etl_log group by 1,2;`
  (strategy A: cursors preserved → first nightly resumes incrementally).
- One manual `python -m scripts.run_daily` end-to-end, green.

---

## 6. Re-point ETL + apps (the complete list)

| consumer | file | key | new value |
|---|---|---|---|
| oilgas ETL | `engineering_db\.env` | `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` | pooler host / `5432` (session) / `postgres.<NEWREF>` / new pw |
| erebor | `erebor\backend\.env` | `DATABASE_URL` | `postgresql+psycopg://postgres.<NEWREF>:<pw>@aws-1-us-east-1.pooler.supabase.com:6543/postgres` |
| narvi | `narvi\.env` | `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` | pooler host / `6543` / `postgres.<NEWREF>` / new pw |
| anduin | `permian_type_curve\.env` | `WAREHOUSE_DATABASE_URL` | same shape as today but `postgres.<NEWREF>` — note it uses port **5432** (session) for batch sync; keep as-is |
| backups | `engineering_db\infra\backup\backup_oilgas.ps1` | connection string / env it reads | new project; run one manual backup to verify |
| healthchecks.io | n/a | nothing DB-side changes | untouched (pings from run_daily, not from the DB) |

Order: repoint the **ETL first** (needed for §4's forecast load), apps after §5
passes. Restart erebor/narvi backends and `docker restart permian-backend`
after their `.env` edits.

Task Scheduler (`engineering_db_daily_etl`, 6:00 AM) needs no change — it runs
`scripts.run_daily` which reads `.env`.

---

## 7. Parallel-run + decommission

- Keep the old project untouched for ≥1 week (it is the rollback: revert the
  `.env`s). Don't pause it until the first nightly + one manual backup have
  run green against the new project.
- Old project's nightly writes stop the moment the ETL `.env` is repointed —
  it goes stale, not corrupt.
- After sign-off: pause (don't delete) the old project if the role allows;
  otherwise just leave it — Jacob's problem to reap.

---

## 8. Open items this migration does NOT solve

- Novi share bugs (IRR units, pad_name coverage, PDP completions) — vendor-side.
- Phase 7 (nightly new-report detection) and Phase 8 (retire file-drop loaders)
  of the Snowflake migration — do them after the move; they're repo-side.
- The `enverus.wells` etl_log leak (separate fix session in flight).
