# engineering_db

A small analytical database / data warehouse for upstream oil & gas data.
Pulls from Enverus (delta query via their official Python SDK) and Novi
Labs (bulk TSV sync + `COPY`), lands raw payloads into schema-isolated
tables in a local PostgreSQL 16 + PostGIS instance, and later refreshes
curated materialized views that merge the two sources.

## Prerequisites

- Python 3.12
- PostgreSQL 16 with the PostGIS extension installed
- Network access to Enverus and Novi (credentials required)

## Setup

```powershell
# 1. Create and activate a virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # PowerShell on Windows
# or: source .venv/bin/activate  # bash / WSL

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy the env template and fill in real credentials
copy .env.example .env
# then edit .env

# 4. Create the database in pgAdmin (or psql):
#    CREATE DATABASE oilgas;
#    \c oilgas
#    CREATE EXTENSION IF NOT EXISTS postgis;

# 5. Apply the initial DDL (creates meta.etl_log + schemas)
psql -d oilgas -f sql/01_initial_ddl_v3.sql

# 6. First Novi sync — downloads schema.postgres.sql + all TSVs to ./data
python -m etl.novi.sync

# 7. Generate raw_novi DDL from Novi's own schema file
python -m scripts.generate_novi_ddl --schema-file "data/us-horizontals/All basins/All subbasins/Bulk/schema.postgres.sql"

# 8. Apply the generated Novi DDL
psql -d oilgas -f sql/02_raw_novi_ddl.sql

# 9. COPY the Novi TSVs into raw_novi.*
python -m etl.novi.load

# 10. Generate raw_enverus DDL by calling DeveloperAPIv3.ddl(...)
python -m scripts.generate_enverus_ddl

# 11. Apply the generated Enverus DDL
psql -d oilgas -f sql/03_raw_enverus_ddl.sql

# 12. Build the curated layer (after at least one Novi + Enverus load)
psql -d oilgas -f sql/04_curated.sql
psql -d oilgas -f sql/05_curated_production.sql
psql -d oilgas -f sql/06_curated_derived.sql

# 13. Kick off a daily cycle end-to-end
python -m scripts.run_daily
```

The two raw schemas are derived from authoritative upstream artifacts:
Novi ships `schema.postgres.sql` with the bulk download, and Enverus's SDK
exposes `v3.ddl(dataset, database="pg")`. The `curated.*` layer is built on
top of them in three phases:

- **04 — `curated.wells`** (matview): Novi `Wells` + `WellDetails` + `WellSpacing` joined to the latest Enverus completion per wellbore, with snake_case columns and a documented source-of-truth per field.
- **05 — `curated.production`** (matview): Novi `WellMonths` pass-through, indexed for the `(api10, months_on_production)` cohort-query pattern.
- **06 — derived analytical layer**:
  - `curated.wells_enriched` (regular view): adds per-well derived columns — `completion_vintage_bucket`, `lateral_length_class`, `is_horizontal`, `stages_per_1000ft`, per-stage intensity, `has_completion_intensity`.
  - `curated.production_normalized` (matview): production INNER JOIN wells with per-1000-ft normalized rates (oil/gas/water/boe, current and cumulative) and cohort keys carried forward.
  - `curated.type_curve_cohorts` (matview): pre-computed P10/P25/P50/P75/P90 of per-1000-ft rates by (state, county, formation, vintage bucket) × MoP 1-240, with `well_count` / `well_months` for sample-size filtering.

`curated.refresh_all()` refreshes all four matviews `CONCURRENTLY` in dependency order; `wells_enriched` is a regular view and auto-syncs.

## Running

Daily incremental pipeline:

```powershell
python -m scripts.run_daily
```

Order: Novi sync → Novi load → Enverus wells delta → Enverus production
delta → curated refresh. Each step is isolated; one failure does not block
the rest. A run log is written to `logs/run_daily_<YYYY-MM-DD>.log` and a
summary table is printed at the end.

Individual steps for debugging:

```powershell
python -m etl.novi.sync
python -m etl.novi.load                     # accepts --bulk-dir <path>
python -m etl.enverus.pull_wells
python -m etl.refresh
```

**Quarterly — Novi Intelligence.** A third source alongside the two nightly
ones: `raw_intel` mirrors the Novi INTEL Snowflake share (sql/27), loaded per
report vintage by `python -m scripts.load_intel_sf`; the curated intel layer
(`curated.intel_*`, sql/29) and the erebor/narvi matview chain rebuild on top.
A nightly `intel_sf.report_check` step alerts when a new report is visible in
the share; the reload itself is manual — full sequence in
`.claude/skills/novi-quarterly-reload/SKILL.md`. The share carries no
geometry, so the DSU pad / land-grid / basin-outline overlays still load from
Novi's shapefile drop into `raw_novi_intel` via
`python -m scripts.load_novi_intel --shapefiles`.

> **Note (2026-06-22):** Enverus *production* ingestion was removed. It was
> pulled daily into `raw_enverus.production` but never consumed —
> `curated.production` is built from Novi `WellMonths` only. The
> `pull_production` step, the weekly `cleanup_vertical_production`
> maintenance step, and the `raw_enverus.production` table were all
> dropped. Enverus *wells* (which feeds completion intensity and
> `formation_blueox`'s `env_interval`) is unaffected. To re-enable, re-add
> `"production"` to `MVP_DATASETS` in `scripts/generate_enverus_ddl.py`,
> regenerate `sql/03`, and restore the pull step in `run_daily.py`.

One-time historical backfill:

```powershell
# Enverus production: producingmonth between(start, end); requires both dates
python -m scripts.backfill --source enverus --table production `
    --start-date 2010-01-01 --end-date 2025-12-31

# Enverus wells: full non-incremental Permian pull (no date filter)
python -m scripts.backfill --source enverus --table wells

# Novi: TRUNCATE+COPY the current on-disk TSV (Novi has no "as-of" history)
python -m scripts.backfill --source novi --table production
```

## Architecture

```
                           ┌────────── Enverus ──────────┐
                           │ enverus-developer-api SDK   │
                           │  v3.query(...)  v3.ddl(...) │
                           └──────────────┬──────────────┘
                                          │
                                          ▼
                            etl/enverus/pull.pull_dataset()
                            ── batched upserts (5000/batch) ──
                                          │
                                          ▼
                                  raw_enverus.<dataset>


    ┌────────── Novi ──────────┐
    │ vendored novi sample SDK │
    │ NoviDataSdk(...).update_ │
    │   bulk_data() → TSV tree │
    └────────────┬─────────────┘
                 │
                 ▼
       etl/novi/load.load_all()
       ── TRUNCATE + COPY per ──
                 │
                 ▼
          raw_novi.<Table>


             raw_enverus.*  +  raw_novi.*
                       │
                       ▼
              curated.refresh_all()          (deferred; built after
                       │                      both raw schemas exist)
                       ▼
                  curated.*
```

Every ETL run is recorded in `meta.etl_log` via the `log_etl_run` context
manager in `etl/db.py` — start, end, status, row count, error if any.

## Scheduling

Windows Task Scheduler runs the daily pipeline:

- Program/script: `python`
- Arguments: `-m scripts.run_daily`
- Start in: the project directory (so `.env`, `data/`, `logs/` resolve)

Recommended cadence: daily, off-hours, after the upstream sources have
finished their nightly refresh.

## Notifications

The daily run can send a plain-text summary email at the end of every
run (success or failure) and ping a healthchecks.io dead-man's-switch.
Both are opt-in via env vars; leaving any of them unset disables that
channel cleanly. See `etl/notify.py` for implementation details.

**Email summary** (Gmail SMTP) — answers "did the run land, and what did
it touch?"

```ini
NOTIFY_EMAIL_TO=you@example.com
NOTIFY_EMAIL_FROM=sender@gmail.com
NOTIFY_SMTP_USER=sender@gmail.com
NOTIFY_SMTP_PASS=<16-char Gmail app password>
NOTIFY_SMTP_HOST=smtp.gmail.com   # default
NOTIFY_SMTP_PORT=587              # default
```

The Gmail account needs 2FA enabled, then generate an app password at
https://myaccount.google.com/apppasswords (regular Gmail passwords were
disabled for SMTP in 2022). The body is a fixed-width text table with
per-step status, row counts, curated.production freshness
(`MAX(prod_date)` + days behind today), curated.* row counts, and the
Novi `ExportDate.txt` snapshot tag.

**healthchecks.io dead-man's-switch** — answers "did the run actually
fire at all?" Catches the failure mode email can't: Windows Task
Scheduler silently failing to start the run when the laptop was asleep
or the user wasn't logged in.

```ini
HEALTHCHECKS_PING_URL=https://hc-ping.com/<your-check-uuid>
```

1. Sign up free at https://healthchecks.io.
2. Create a check with schedule "daily at 06:00" and a ~2-hour grace
   window (covers slow runs without false alarms).
3. Add an email/Slack/SMS integration on the check so missed pings reach
   you.
4. Copy the ping URL into the env var above.

The run pings `<url>/start` at the top of `run_daily.py` and either
`<url>` (success) or `<url>/fail` (any step failed) at the end.

## Conventions and defaults

- All modules use `logging.getLogger(__name__)`; nothing uses `print`
  outside of CLI entry points.
- **Enverus**: official `enverus-developer-api` PyPI SDK handles auth
  (8h bearer token, auto-refresh), pagination, and retries. We configure
  it once via `etl.enverus.client.get_client()` (process-wide singleton)
  with `retries=5, backoff_factor=1`.
- **Enverus incremental cutoff**: `pull_dataset` queries `meta.etl_log`
  for the last successful `run_finished_at` for that dataset and uses it
  as the `updateddate=gt(...)` filter. Always combined with
  `deleteddate='null'` to skip soft-deletes.
- **Enverus batching**: rows are buffered in batches of 5000 (`BATCH_SIZE`
  in `etl/enverus/pull.py`) and upserted via `etl.db.bulk_upsert`.
- **Enverus key columns** in `pull_wells.py` are best-guesses (`API14`);
  verify them against the generated DDL in `sql/03_raw_enverus_ddl.sql`.
- **Novi**: bulk-download model. The vendored SDK at `etl/novi/sdk.py`
  (see `NOTICE.md`) handles auth and downloads full + diff TSVs to
  `./data/`. `etl/novi/load.py` then `TRUNCATE`s and `COPY`s each TSV
  into `raw_novi."<TableName>"`. Simpler and faster than per-row REST.
- **Novi raw schemas** are generated from Novi's own
  `schema.postgres.sql` (ships with the bulk download) via
  `scripts/generate_novi_ddl.py`. Quoted, mixed-case identifiers
  (`raw_novi."WellMonths"`) preserve Novi's casing exactly.
- **Novi MVP tables**: `Wells`, `WellMonths`, `WellDetails`,
  `WellSpacing`. Wells is the parent (api10 PK); the other three
  reference it. Extend `MVP_TABLES` in BOTH `etl/novi/load.py` AND
  `scripts/generate_novi_ddl.py` to pull more (Subsurface,
  DirectionalSurveys, ForecastWellMonths, FracFocus*, PricesWeekly,
  etc.).
- **Novi temporal model**: every table has `CreatedAt` / `ModifiedAt` /
  `DeletedAt`. Curated views should filter `DeletedAt IS NOT NULL`. The
  SDK handles the diff/merge math on disk so we don't apply `ModifiedAt`
  filters ourselves.
- **API key reconciliation**: Novi keys on `API10` (10-digit), Enverus on
  `API14`. The curated layer joins via `LEFT(api14, 10) = api10`.
- `meta.etl_log` is expected to have columns `(id, source, table_name,
  run_started_at, run_finished_at, status, rows_inserted, error_message)`.
- `curated.refresh_all()` is invoked as `SELECT curated.refresh_all();`,
  so define it as a `FUNCTION` (not a `PROCEDURE`) — or change the call
  in `etl/db.refresh_curated` to `CALL` if you prefer a procedure.

## API references

- Enverus Developer API Python SDK: https://github.com/enverus-ea/enverus-developer-api
  (Explorer: https://app.enverus.com/direct/#/api/explorer/v3/gettingStarted)
- Novi REST sample code: https://gitlab.com/novipublic/rest-api-sample-code
  (vendored at `etl/novi/sdk.py`; see `NOTICE.md`)

## Layout

```
engineering_db/
├── README.md
├── NOTICE.md
├── .env.example
├── .gitignore
├── requirements.txt
├── sql/
│   ├── 01_initial_ddl_v3.sql        # meta schema + extensions (hand-written)
│   ├── 02_raw_novi_ddl.sql          # generated from Novi's schema.postgres.sql
│   ├── 03_raw_enverus_ddl.sql       # generated from DeveloperAPIv3.ddl()
│   ├── 04_curated.sql               # curated.wells (matview) — includes wellstick_geom + GIST index
│   ├── 05_curated_production.sql    # curated.production (matview)
│   ├── 06_curated_derived.sql       # wells_enriched + production_normalized + type_curve_cohorts
│   ├── 07_cutover_prep.sql          # one-time: drop+rebuild curated chain to pick up wellstick_geom
│   └── migrations/
├── scripts/
│   ├── generate_novi_ddl.py
│   ├── generate_enverus_ddl.py
│   ├── run_daily.py
│   └── backfill.py
├── etl/
│   ├── db.py
│   ├── refresh.py
│   ├── enverus/
│   │   ├── client.py                # DeveloperAPIv3 singleton factory
│   │   ├── pull.py                  # generic parameterized pull_dataset()
│   │   └── pull_wells.py            # thin wrapper
│   └── novi/
│       ├── sdk.py                   # vendored from Novi sample repo
│       ├── sync.py                  # SDK wrapper → TSV tree on disk
│       └── load.py                  # TRUNCATE + COPY into raw_novi.*
├── data/                            # Novi TSVs land here (gitignored)
└── logs/
```
