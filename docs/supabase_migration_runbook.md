# Supabase Migration Runbook — `oilgas` warehouse

Migrate the `oilgas` Postgres warehouse from the local server to Supabase
(managed Postgres), then re-point the ETL and downstream apps at it.

---

## 0. Strategy & artifacts

- **Source:** local PostgreSQL **18.4**, database `oilgas` (~27 GB).
- **Target:** Supabase project (managed Postgres — confirm version, see §1).
- **Dump artifact:** `C:\Users\MichaelMast\db_dumps\oilgas_20260622.dump`
  — **3.7 GB**, custom format, `--no-owner --no-privileges`, verified readable via
  `pg_restore -l` (5 schemas, 16 table-data entries). Scope = **source data
  only**: schemas `raw_novi`, `raw_enverus`, `raw_novi_intel`, `ref`, `meta`.
  Produced with:
  ```
  pg_dump -h localhost -U postgres -d oilgas -Fc --no-owner --no-privileges \
    --no-tablespaces --schema=raw_novi --schema=raw_enverus \
    --schema=raw_novi_intel --schema=ref --schema=meta -f <out>.dump
  ```
- **`curated.*` is deliberately NOT in the dump.** Those matviews (~10.8 GB:
  `production_forecast` 7 GB, `production_normalized` 2 GB, `production` 1.4 GB,
  …) are 100% rebuildable from raw+ref via the repo SQL + `curated.refresh_all()`.
  Rebuilding them natively on Supabase avoids restoring complex objects across a
  **Postgres-version downgrade** (source is 18; Supabase is almost certainly 15
  or 17) — the single riskiest part of a pg_dump/restore.
- **`public` is NOT dumped** — it holds only PostGIS system objects
  (`spatial_ref_sys`, `geometry_columns`, `geography_columns`); Supabase supplies
  its own when PostGIS is enabled.

Net: restore the source data, then **build curated on Supabase** from the
version-portable `sql/*.sql` files.

---

## 0b. Operational notes — VALIDATED on the 2026-06-23 migration

The migration succeeded; these are the real gotchas (the abstract steps below
assume they're handled):

- **Supabase = PG 17.6; PostGIS 3.3.7 in the `extensions` schema (not relocatable).**
  The dump hard-qualifies `public.geometry` (4 refs). Fix: `sed 's/public\.geometry/
  extensions.geometry/g'` on the pre-data SQL, and `SET search_path TO public,
  extensions` on every build session.
- **`statement_timeout = 2min`** is a Supabase platform-config default. It kills big
  COPYs and the matview builds. `ALTER ROLE … SET statement_timeout=0` registers but
  is **NOT applied on pooler connections** (the pooler reuses server conns);
  `PGOPTIONS` is **stripped by the pooler** too. Two ways that DO work:
  - **Direct connection** (`db.<ref>.supabase.co:5432`, user `postgres`): honors
    `ALTER ROLE … statement_timeout=0`, and supports parallel `pg_restore -j`. BUT it
    is **IPv6-only** — needs working IPv6 from the client (was up, then went
    unreachable mid-migration; unreliable).
  - **Pooler** (`…pooler.supabase.com:5432`, user `postgres.<ref>`, IPv4, stable):
    **session-level `SET statement_timeout=0` works.** `pg_restore` can't inject it,
    so **stream the dump through psql** with a leading SET (single session):
    ```
    { echo "SET statement_timeout=0;"; \
      pg_restore --no-owner --no-privileges --section=data -f - oilgas_….dump; } \
      | psql "<pooler-uri>" -v ON_ERROR_STOP=1
    ```
    Single-threaded but reliable. Same pattern for `--section=post-data`.
- **Disk:** the default 8 GB project disk **crashed** mid-restore ("database system is
  not accepting connections / Hot standby disabled"). The ~27 GB warehouse needs
  **~50–60 GB disk** (60 GB used, ~27 GB consumed). Resize disk+compute in the
  dashboard BEFORE restoring; resizing also recovers a disk-full instance.
- **`refresh_all()` over the pooler stalls** — it's one long *silent* statement
  (~15 min of CONCURRENTLY refreshes, no network traffic), and the pooler drops it.
  Run the nightly `refresh_all` from a host with a **stable/direct connection** or add
  libpq TCP keepalives (`keepalives=1&keepalives_idle=30&keepalives_interval=10`). The
  matviews are populated on build, so this only affects the *nightly* refresh.
- **Don't trust `pg_restore`'s `|| echo` exit masking** — check the log for
  `pg_restore: error`, not just the shell rc.

---

## 1. Preconditions & decisions

- [ ] **Confirm Supabase Postgres major version.** Source is 18; Supabase is
  likely 15/17. This runbook is built for that downgrade: only **plain tables**
  (raw/ref/meta) restore from the pg_dump 18 archive (§3) — that DDL is version-
  safe — while the **complex objects** (the `curated` matviews + `refresh_all()`
  function) are rebuilt from the version-portable repo SQL (§4), never restored
  across the gap. Still provision the **highest version Supabase offers** to
  minimize it.
- [ ] **Use the direct/session connection for ALL migration steps** — host
  `db.<project-ref>.supabase.co`, port **5432**. `COPY`, `\copy`, `CREATE
  MATERIALIZED VIEW`, and `REFRESH MATERIALIZED VIEW` need a real session; the
  **transaction pooler (port 6543)** does not support them and is for the *apps*,
  not the migration.
- [ ] **Repo checked out** on the machine running the restore — the `sql/*.sql`
  files and `seeds/formation_crosswalk.csv` are required to build curated + ref.
- [ ] Keep the local `oilgas` DB running and untouched until Supabase is verified
  (it is the rollback).

---

## 2. Prepare Supabase

1. Create the project; record the connection string and PG version.
2. **Enable PostGIS in the `public` schema** (this is load-bearing — see below):
   ```sql
   create extension if not exists postgis with schema public;
   create extension if not exists pg_trgm with schema public;
   ```
   **Why `public` specifically:** the dump hard-qualifies the geometry type as
   `public.geometry(Geometry,4326)` on the `raw_novi_intel` geom columns (verified
   in the 2026-06-22 dump). If PostGIS lands in Supabase's default `extensions`
   schema instead, the §3 restore fails with `type "public.geometry" does not
   exist`. So PostGIS **must** be resolvable as `public.geometry`.
   - If Supabase already provisioned PostGIS into `extensions`, move it:
     ```sql
     alter extension postgis set schema public;
     ```
     (The Supabase `postgres` role can do this.)
   - Last-resort fallback if it cannot live in `public`: extract the archive to
     SQL, rewrite the type, and load via psql:
     ```
     pg_restore -f restore.sql oilgas_20260622.dump
     sed -i 's/public\.geometry/extensions.geometry/g' restore.sql
     psql <session-conn> -f restore.sql
     ```
   Optionally also widen the search path so the curated rebuild (§4, unqualified
   `geometry`) resolves regardless:
   ```sql
   alter database postgres set search_path to "$user", public, extensions;
   ```
   (Reconnect after, so it takes effect.)

---

## 3. Restore source data (raw + ref + meta)

These three schemas are **all plain tables** (+ indexes, a BIGSERIAL sequence, and
PostGIS geometry columns in `raw_novi_intel`) — standard DDL that restores cleanly
even from a newer pg_dump into an older server. So restore the dump **in full**
(schema + data + sequence state) in one step:

```
pg_restore --no-owner --no-privileges -j 4 \
  -h db.<project-ref>.supabase.co -p 5432 -U postgres -d postgres \
  "C:\Users\MichaelMast\db_dumps\oilgas_20260622.dump"
```

This creates the `raw_novi`, `raw_enverus`, `raw_novi_intel`, `ref`, and `meta`
schemas, all their tables/indexes/data, and the `meta.etl_log` sequence state (so
the ETL cursor is preserved — no manual `setval` needed).

> If you hit `type "public.geometry" does not exist` on the `raw_novi_intel`
> tables, PostGIS isn't in `public` — go back and fix §2 (install/move PostGIS
> into `public`, or use the sed fallback). This is the #1 expected snag.

---

## 4. Build the curated layer (native rebuild)

`curated` is excluded from the dump and rebuilt here from the version-portable
repo SQL. Run from the **repo root** (so `\ir` / `\copy` relative paths resolve),
session connection, in order:

```
psql <session-conn> -c "create schema if not exists curated;"
psql <session-conn> -f sql/04_curated.sql               # curated.wells (+ formation_blueox)
psql <session-conn> -f sql/05_curated_production.sql    # curated.production
psql <session-conn> -f sql/06_curated_derived.sql       # wells_enriched, production_normalized, type_curve_cohorts
psql <session-conn> -f sql/10_curated_forecast.sql      # production_forecast, production_combined
psql <session-conn> -f sql/12_curated_intel.sql         # intel_locations, intel_arps, intel_forecast
psql <session-conn> -c "select curated.refresh_all();"
```

Notes:
- `curated.wells` (sql/04) `LEFT JOIN`s `ref.formation_crosswalk`, which was
  restored in §3 — so `formation_blueox` populates on rebuild. (The CSV under
  `seeds/` remains the source of truth; to re-seed instead of trusting the restore,
  run `psql -f sql/14_formation_crosswalk.sql` from the repo root first.)
- Each `CREATE MATERIALIZED VIEW … AS` populates on creation; the trailing
  `refresh_all()` is belt-and-suspenders and confirms the function resolves.

---

## 5. Verify

Run on **both** source and Supabase; everything must match.

### 5a. Row-count parity (the 16 dumped tables) — source baseline 2026-06-22:

| table | rows |
|---|---|
| raw_novi.Wells | 91,312 |
| raw_novi.WellDetails | 91,312 |
| raw_novi.WellMonths | 4,916,217 |
| raw_novi.WellSpacing | 59,784 |
| raw_novi.ForecastWellMonths | 22,112,213 |
| raw_enverus.wells | 635,758 |
| raw_novi_intel.forecast | 73,864,609 |
| raw_novi_intel.arps | 1,851,759 |
| raw_novi_intel.sticks | 248,618 |
| raw_novi_intel.analytics | 205,751 |
| raw_novi_intel.pud_attrs | 131,465 |
| raw_novi_intel.land_grid | 42,668 |
| raw_novi_intel.pads | 9,040 |
| raw_novi_intel.basin_outline | 2 |
| ref.formation_crosswalk | 155 |
| meta.etl_log | 173 |

> Re-run the source counts at migration time if the daily ETL has run since
> 2026-06-22 — the warehouse is live, so these grow.

### 5b. Curated rebuilt correctly:
```sql
select (select count(*) from curated.wells)          as wells,       -- 91,312
       (select count(*) from curated.wells_enriched) as enriched,    -- must EQUAL wells
       (select count(*) from curated.production)     as production,  -- ~4.9M
       (select count(*) from curated.type_curve_cohorts) as cohorts; -- ~171k
```

### 5c. `formation_blueox` present + populated:
```sql
select formation_blueox, count(*)
from curated.wells group by 1 order by 2 desc nulls last limit 10;
```

### 5d. PostGIS working (geometry resolves, spatial query runs):
```sql
select postgis_full_version();
select count(*) from curated.wells where wellstick_geom is not null;   -- non-zero
```

### 5e. ETL cursor preserved (so the first incremental pull resumes correctly):
```sql
select source, table_name, max(run_finished_at)
from meta.etl_log group by 1,2 order by 1,2;
```

### 5f. `refresh_all()` runs clean (no missing-dependency errors):
```sql
select curated.refresh_all();
```

---

## 6. Re-point ETL + apps

- **ETL (`engineering_db`):** update `.env` — `DB_HOST`, `DB_PORT`, `DB_NAME`,
  `DB_USER`, `DB_PASSWORD` → Supabase **session** connection (5432). `etl/db.py`
  reads these via `_db_kwargs()`; **no code change**. Decide where `run_daily.py`
  runs (it still downloads Novi bulk TSVs to disk + needs DB access): pg_cron can
  only do the SQL refresh — the Novi/Enverus pulls need an external runner
  (Replit / GitHub Actions / the current Windows box).
- **Apps (`permian_type_curve`, `erebor`):** point their DB config at Supabase.
  The **transaction pooler (6543)** is appropriate for app query load.

---

## 7. Rollback

- The local `oilgas` DB is untouched throughout — it remains the source of truth
  until Supabase passes §5. Re-restore from
  `C:\Users\MichaelMast\db_dumps\oilgas_20260622.dump` if needed.
