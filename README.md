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

# 12. Kick off a daily cycle end-to-end
python -m scripts.run_daily
```

The two raw schemas are now derived from authoritative upstream artifacts:
Novi ships `schema.postgres.sql` with the bulk download, and Enverus's SDK
exposes `v3.ddl(dataset, database="pg")`. The `curated.*` layer is deferred
until both raw schemas exist (column names aren't pinned until step 11).

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
python -m etl.enverus.pull_production
python -m etl.refresh
```

Periodic maintenance (run weekly, not part of daily orchestrator):

```powershell
python -m scripts.cleanup_vertical_production
```

The incremental production pull skips the per-wellbore chunked filter on
non-cold runs (huge speedup), so vertical-well production rows occasionally
sneak in. This cleanup script deletes them.

One-time historical backfill (stub):

```powershell
python -m scripts.backfill --source enverus --table production \
    --start-date 2010-01-01 --end-date 2025-12-31
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
- **Enverus key columns** in `pull_wells.py` / `pull_production.py` are
  best-guesses (`API14`, `ProducingMonth`); verify them against the
  generated DDL in `sql/03_raw_enverus_ddl.sql`.
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
│   └── migrations/
├── scripts/
│   ├── generate_novi_ddl.py
│   ├── generate_enverus_ddl.py
│   ├── run_daily.py
│   ├── cleanup_vertical_production.py
│   └── backfill.py
├── etl/
│   ├── db.py
│   ├── refresh.py
│   ├── enverus/
│   │   ├── client.py                # DeveloperAPIv3 singleton factory
│   │   ├── pull.py                  # generic parameterized pull_dataset()
│   │   ├── pull_wells.py            # thin wrapper
│   │   └── pull_production.py       # thin wrapper
│   └── novi/
│       ├── sdk.py                   # vendored from Novi sample repo
│       ├── sync.py                  # SDK wrapper → TSV tree on disk
│       └── load.py                  # TRUNCATE + COPY into raw_novi.*
├── data/                            # Novi TSVs land here (gitignored)
└── logs/
```
