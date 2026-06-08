-- =============================================================================
-- 11 — raw_novi_intel: Novi Intelligence basin-report ingestion (Delaware + Midland)
--
-- A THIRD source alongside raw_enverus (incremental API) and raw_novi (bulk TSV).
-- Source today = the quarterly Novi Intelligence file drop (shapefiles + CSVs);
-- ~July 2026 this is replaced by the Novi Intelligence Snowflake API/share — only
-- the EXTRACT step (etl/novi_intel/) changes, these tables and the curated layer
-- on top of them stay put.
--
-- Faithful-ish raw layer: the three economic stick shapefiles (PDP/PUD/Resource)
-- share one ~56-field economic schema with minor per-basin drift (Midland lacks
-- County, differing column order/types). We land them in ONE `sticks` table with
-- harmonized snake_case names; normalization/typing happens in the curated layer
-- (sql/12). Every row is tagged with `basin` and `report_version` so quarterly
-- drops accumulate rather than overwrite. `ingested_at` mirrors the raw_novi
-- convention.
--
-- Geometry: all Novi layers are EPSG:4326 (verified). Stored as generic
-- geometry(Geometry,4326) — sticks are laterals (LINESTRING), pads/grid/outline
-- are polygons.
--
-- RUN: executed by scripts/load_novi_intel.py via psycopg (psql not required).
-- Idempotent: DROP ... IF EXISTS then CREATE, so re-running rebuilds cleanly.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw_novi_intel;

-- -----------------------------------------------------------------------------
-- sticks — union of PDP_Oil / PUD_Oil / Resource economic shapefiles
--   unique_id : PDP -> API10 (numeric string); PUD/RES -> Novi well name
--   api10     : populated when category='PDP' (crosswalk to curated.wells)
--   category  : PDP | PUD | RES (from the "PUD/PDP/RE" attribute)
--   geom      : lateral geometry from the shapefile
-- All economic measures stored as double precision; see sql/12 for unit notes
-- (e.g. irr_pct unit inconsistency across files — normalized downstream).
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_novi_intel.sticks CASCADE;
CREATE TABLE raw_novi_intel.sticks (
    stick_id        BIGSERIAL PRIMARY KEY,
    basin           TEXT NOT NULL,          -- 'delaware' | 'midland'
    report_version  TEXT NOT NULL,          -- e.g. '3Q25'
    src_layer       TEXT NOT NULL,          -- source shapefile basename
    unique_id       TEXT,                   -- API10 (PDP) or well name (PUD/RES)
    api10           TEXT,                    -- set when category='PDP'
    category        TEXT,                   -- PDP | PUD | RES
    phase           TEXT,
    operator        TEXT,
    formation       TEXT,
    county          TEXT,                    -- NULL for Midland sticks
    pad_name        TEXT,
    fp_year         INTEGER,
    tvd             DOUBLE PRECISION,
    md              DOUBLE PRECISION,
    ll_ft           DOUBLE PRECISION,
    prop_load       DOUBLE PRECISION,
    -- reserves / rates (per phase)
    oil_eur         DOUBLE PRECISION,
    gas_eur         DOUBLE PRECISION,
    dgas_eur        DOUBLE PRECISION,
    ngl_eur         DOUBLE PRECISION,
    water_eur       DOUBLE PRECISION,
    oil_ip          DOUBLE PRECISION,
    gas_ip          DOUBLE PRECISION,
    dgas_ip         DOUBLE PRECISION,
    ngl_ip          DOUBLE PRECISION,
    water_ip        DOUBLE PRECISION,
    ngl_yield       DOUBLE PRECISION,
    ngl_shrink      DOUBLE PRECISION,
    -- economics (Novi pre-computed; in-app screen only)
    npv5            DOUBLE PRECISION,
    npv10           DOUBLE PRECISION,
    npv15           DOUBLE PRECISION,
    npv20           DOUBLE PRECISION,
    npv25           DOUBLE PRECISION,
    pv5             DOUBLE PRECISION,
    pv10            DOUBLE PRECISION,
    pv15            DOUBLE PRECISION,
    pv20            DOUBLE PRECISION,
    pv25            DOUBLE PRECISION,
    npv5_be         DOUBLE PRECISION,
    npv10_be        DOUBLE PRECISION,
    npv15_be        DOUBLE PRECISION,
    npv20_be        DOUBLE PRECISION,
    npv25_be        DOUBLE PRECISION,
    be_1yr          DOUBLE PRECISION,
    be_2yr          DOUBLE PRECISION,
    be_3yr          DOUBLE PRECISION,
    irr_pct         DOUBLE PRECISION,
    pp_months       DOUBLE PRECISION,
    ttpt            DOUBLE PRECISION,
    dc_cost         DOUBLE PRECISION,
    dcet_cost       DOUBLE PRECISION,
    norm_dc         DOUBLE PRECISION,
    norm_dcet       DOUBLE PRECISION,
    -- flat price deck (per stick)
    wti_price       DOUBLE PRECISION,
    hh_price        DOUBLE PRECISION,
    ngl_price       DOUBLE PRECISION,
    wti_diff        DOUBLE PRECISION,
    hh_diff         DOUBLE PRECISION,
    has_econ        TEXT,                    -- 'Yes' | 'No'
    conf_int        DOUBLE PRECISION,
    geom            geometry(Geometry, 4326),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- pads — Novi DSU pad polygons (+ pad-level NPV rollup; columns differ by basin)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_novi_intel.pads CASCADE;
CREATE TABLE raw_novi_intel.pads (
    pad_id          BIGSERIAL PRIMARY KEY,
    basin           TEXT NOT NULL,
    report_version  TEXT NOT NULL,
    pad_name        TEXT,
    npv5            DOUBLE PRECISION,
    npv10           DOUBLE PRECISION,
    npv15           DOUBLE PRECISION,
    npv20           DOUBLE PRECISION,
    npv25           DOUBLE PRECISION,        -- Delaware: SUM_NPV25
    geom            geometry(Geometry, 4326),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- analytics — Novi Analytics File CSV (well geometry endpoints + completion).
-- Columns in CSV order so COPY with an explicit column list maps positionally.
-- basin / report_version are filled via a per-load column DEFAULT (loader sets it).
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_novi_intel.analytics CASCADE;
CREATE TABLE raw_novi_intel.analytics (
    well_name         TEXT,
    tvd               DOUBLE PRECISION,
    midpoint_lat      DOUBLE PRECISION,
    midpoint_lon      DOUBLE PRECISION,
    bh_lat            DOUBLE PRECISION,
    bh_lon            DOUBLE PRECISION,
    heel_lat          DOUBLE PRECISION,
    heel_lon          DOUBLE PRECISION,
    target_formation  TEXT,
    lateral_length    DOUBLE PRECISION,
    proppant_loading  DOUBLE PRECISION,
    fluid_loading     DOUBLE PRECISION,
    county            TEXT,
    subbasin          TEXT,
    proppant_mass     DOUBLE PRECISION,
    fluid_volume      DOUBLE PRECISION,
    md                DOUBLE PRECISION,
    pad_name          TEXT,
    basin             TEXT,
    report_version    TEXT,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- arps — segmented decline parameters CSV (key: novi_wellname, stream, segment)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_novi_intel.arps CASCADE;
CREATE TABLE raw_novi_intel.arps (
    job_name           TEXT,
    well_inventory_name TEXT,
    planned_well_id    TEXT,
    production_stream  TEXT,
    segment            INTEGER,
    segment_curve_type TEXT,
    b                  DOUBLE PRECISION,
    d_nom              DOUBLE PRECISION,
    d_eff_secant       DOUBLE PRECISION,
    d_eff_tangent      DOUBLE PRECISION,
    q_start            DOUBLE PRECISION,
    q_stop             DOUBLE PRECISION,
    terminal_day       DOUBLE PRECISION,
    day_start          DOUBLE PRECISION,
    day_stop           DOUBLE PRECISION,
    novi_wellname      TEXT,
    basin              TEXT,
    report_version     TEXT,
    ingested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- forecast — production stream CSV (~29.5-yr monthly, 30-day steps). The big one
-- (Delaware 4.8 GB, Midland 2.86 GB) — loaded by streaming COPY.
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_novi_intel.forecast CASCADE;
CREATE TABLE raw_novi_intel.forecast (
    ip_day          INTEGER,
    novi_wellname   TEXT,
    oil             DOUBLE PRECISION,
    gas             DOUBLE PRECISION,
    water           DOUBLE PRECISION,
    pad_name        TEXT,
    basin           TEXT,
    report_version  TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- -----------------------------------------------------------------------------
-- land_grid / basin_outline — map overlays (Novi-supplied; polygons)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_novi_intel.land_grid CASCADE;
CREATE TABLE raw_novi_intel.land_grid (
    grid_id         BIGSERIAL PRIMARY KEY,
    basin           TEXT NOT NULL,
    report_version  TEXT NOT NULL,
    attrs           JSONB,                   -- raw DBF attributes (labels vary)
    geom            geometry(Geometry, 4326),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TABLE IF EXISTS raw_novi_intel.basin_outline CASCADE;
CREATE TABLE raw_novi_intel.basin_outline (
    outline_id      BIGSERIAL PRIMARY KEY,
    basin           TEXT NOT NULL,
    report_version  TEXT NOT NULL,
    attrs           JSONB,
    geom            geometry(Geometry, 4326),
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Spatial + key indexes (raw-level; curated adds its own).
CREATE INDEX IF NOT EXISTS idx_rni_sticks_geom   ON raw_novi_intel.sticks   USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_rni_sticks_uid     ON raw_novi_intel.sticks (unique_id);
CREATE INDEX IF NOT EXISTS idx_rni_sticks_api10   ON raw_novi_intel.sticks (api10) WHERE api10 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rni_sticks_cat     ON raw_novi_intel.sticks (basin, category);
CREATE INDEX IF NOT EXISTS idx_rni_pads_geom      ON raw_novi_intel.pads     USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_rni_arps_well      ON raw_novi_intel.arps (novi_wellname);
CREATE INDEX IF NOT EXISTS idx_rni_forecast_well  ON raw_novi_intel.forecast (novi_wellname);
CREATE INDEX IF NOT EXISTS idx_rni_analytics_well ON raw_novi_intel.analytics (well_name);
