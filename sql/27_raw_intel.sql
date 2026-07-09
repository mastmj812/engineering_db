-- =============================================================================
-- 27 — raw_intel: 1:1 mirror of the Novi INTEL Snowflake share
--
-- Replaces the static-file raw layer (sql/11 raw_novi_intel) as the source for
-- the curated intel chain (sql/29 supersedes sql/12). Loaded by
-- etl/intel_sf/extract.py from NOVI_DATA_ACCESS.NOVI_INTEL secure views
-- (reader account; latest-report-per-family filtering happens on Novi's side).
--
-- Conventions:
--   * Table = secure view, lowercased; columns = Snowflake names lowercased,
--     types mapped mechanically from the LIVE INFORMATION_SCHEMA (2026-07-08;
--     the PDF data dictionary is stale — e.g. only EUR_*_30YR exists).
--   * Snowflake GEOGRAPHY columns (GEOMETRY_GEO, SHL_GEO) are NOT mirrored:
--     they are derived server-side from GEOMETRY_WKT / lat-lon, which we land
--     and convert to PostGIS ourselves (geom, populated post-COPY per slice).
--   * Report-scoped tables (they all carry report_name from the share) also
--     get loader-derived `basin_slug` ('delaware'/'midland', parsed from
--     report_name) and `report_version` ('2025Q3') so the curated layer keeps
--     the old (basin, report_version) idiom, plus ingested_at.
--     Slice idempotency: the extractor DELETEs WHERE report_name = X before
--     each COPY — same contract as the old loaders.
--   * Global dimensions (operator, basin, source) have no report_name in the
--     share; they are small and loaded full-replace (DELETE all + COPY).
--   * stick_id_map is APPEND-ONLY and survives re-runs (CREATE IF NOT EXISTS,
--     never dropped here): it pins a stable positive bigint stick_id per
--     well_ref across quarterly reloads, seeded above the legacy
--     raw_novi_intel.sticks maximum so ids never collide with history and
--     never overlap erebor's negative PDP ids (-api10).
--
-- Idempotent: DROP ... IF EXISTS then CREATE (except stick_id_map).
-- RUN: scripts/load_intel_sf.py --ddl   (requires explicit authorization —
--      this is Supabase DDL).
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw_intel;

-- -----------------------------------------------------------------------------
-- Global dimensions (no report_name in the share; full-replace load)
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.source CASCADE;
CREATE TABLE raw_intel.source (
    source_id       BIGINT NOT NULL,
    system          TEXT,
    collection      TEXT,               -- basin_research__<Basin>__<yyyyQq>; feeds new-report detection
    source_file     TEXT,
    source_path     TEXT,
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_source_pk ON raw_intel.source (source_id);
CREATE INDEX idx_ri_source_collection ON raw_intel.source (collection);

DROP TABLE IF EXISTS raw_intel.basin CASCADE;
CREATE TABLE raw_intel.basin (
    basin_id        BIGINT NOT NULL,
    basin           TEXT,               -- 'Permian'
    subbasin        TEXT,               -- 'Delaware' / 'Midland'
    source_id       BIGINT,
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_basin_pk ON raw_intel.basin (basin_id);

DROP TABLE IF EXISTS raw_intel.operator CASCADE;
CREATE TABLE raw_intel.operator (
    operator_id          BIGINT NOT NULL,
    reporting_state      TEXT,
    external_operator_id TEXT,
    name_reported        TEXT,
    name_normalized      TEXT,
    address              TEXT,
    address2             TEXT,
    zip                  TEXT,
    city                 TEXT,
    state                TEXT,
    country              TEXT,
    phone                TEXT,
    emergency_phone      TEXT,
    email                TEXT,
    website              TEXT,
    comments             TEXT,
    source_id            BIGINT,
    verified             BOOLEAN,
    created_at           TIMESTAMPTZ,   -- TIMESTAMP_LTZ in the share
    updated_at           TIMESTAMPTZ,
    ingested_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_operator_pk ON raw_intel.operator (operator_id);
CREATE INDEX idx_ri_operator_name ON raw_intel.operator (name_normalized);

-- -----------------------------------------------------------------------------
-- Report-scoped dimensions
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.pad CASCADE;
CREATE TABLE raw_intel.pad (
    pad_id              BIGINT NOT NULL,
    name                TEXT,
    latitude            DOUBLE PRECISION,   -- unpopulated as of 2025Q3 (verified)
    longitude           DOUBLE PRECISION,   -- unpopulated
    crs                 TEXT,
    operator_name       TEXT,
    surface_location_id BIGINT,
    source_id           BIGINT,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    basin               TEXT,               -- share value, e.g. 'Permian'
    report_name         TEXT NOT NULL,
    basin_slug          TEXT NOT NULL,      -- loader-derived: 'delaware'/'midland'
    report_version      TEXT NOT NULL,      -- loader-derived: '2025Q3'
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_pad_pk ON raw_intel.pad (pad_id, report_name);
CREATE INDEX idx_ri_pad_name ON raw_intel.pad (basin_slug, name);
CREATE INDEX idx_ri_pad_report ON raw_intel.pad (report_name);

DROP TABLE IF EXISTS raw_intel.econ_price_assumption CASCADE;
CREATE TABLE raw_intel.econ_price_assumption (
    price_deck_id          TEXT NOT NULL,   -- hash of deck contents; repeats across reports by design
    name                   TEXT,
    detail                 TEXT,
    effective_date         DATE,
    currency               TEXT,
    oil_price              DOUBLE PRECISION,
    gas_price              DOUBLE PRECISION,
    ngl_price              DOUBLE PRECISION,
    oil_price_differential DOUBLE PRECISION,
    gas_price_differential DOUBLE PRECISION,
    oil_price_node         TEXT,
    gas_price_node         TEXT,
    oil_price_units        TEXT,
    gas_price_units        TEXT,
    ngl_price_units        TEXT,
    source_id              BIGINT,
    created_at             TIMESTAMP,
    updated_at             TIMESTAMP,
    report_name            TEXT NOT NULL,
    basin_slug             TEXT NOT NULL,
    report_version         TEXT NOT NULL,
    ingested_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_price_deck_pk
    ON raw_intel.econ_price_assumption (price_deck_id, report_name);

-- -----------------------------------------------------------------------------
-- Entities: existing wells (PDP)
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.well CASCADE;
CREATE TABLE raw_intel.well (
    well_id                     BIGINT NOT NULL,
    well_name                   TEXT,
    uwi_api                     TEXT,        -- api10 on every row (verified: all length 10)
    operator_id                 BIGINT,
    lease_name                  TEXT,
    basin_id                    BIGINT,
    county                      TEXT,
    well_type                   TEXT,
    state                       TEXT,
    field_name                  TEXT,
    offshore_region             TEXT,
    country                     TEXT,
    status_reported             TEXT,
    status_reported_normalized  TEXT,
    status                      TEXT,
    first_production_date       DATE,
    source_id                   BIGINT,
    created_at                  TIMESTAMP,
    updated_at                  TIMESTAMP,
    basin                       TEXT,
    subbasin                    TEXT,
    report_name                 TEXT NOT NULL,
    basin_slug                  TEXT NOT NULL,
    report_version              TEXT NOT NULL,
    ingested_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_well_pk ON raw_intel.well (well_id, report_name);
CREATE INDEX idx_ri_well_api10 ON raw_intel.well (uwi_api);
CREATE INDEX idx_ri_well_report ON raw_intel.well (report_name);

-- -----------------------------------------------------------------------------
-- Entities: planned wells (Base Case + Emerging)
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.planned_well CASCADE;
CREATE TABLE raw_intel.planned_well (
    planned_well_id        BIGINT NOT NULL,
    name                   TEXT,        -- = legacy sticks.unique_id for BASE_CASE (verified 50/50)
    operator_id            BIGINT,
    basin_id               BIGINT,
    county                 TEXT,
    pad_id                 BIGINT,
    drilling_template_id   TEXT,
    completion_template_id TEXT,
    target_formation       TEXT,
    lateral_length         DOUBLE PRECISION,
    azimuth_deg            DOUBLE PRECISION,
    status                 TEXT,
    inventory_class        TEXT,        -- BASE_CASE | EMERGING
    planned_spud_date      DATE,
    planned_til_date       DATE,
    materialized_well_id   BIGINT,
    source_id              BIGINT,
    created_at             TIMESTAMP,
    updated_at             TIMESTAMP,
    basin                  TEXT,
    subbasin               TEXT,
    report_name            TEXT NOT NULL,
    basin_slug             TEXT NOT NULL,
    report_version         TEXT NOT NULL,
    ingested_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_planned_well_pk
    ON raw_intel.planned_well (planned_well_id, report_name);
CREATE INDEX idx_ri_planned_well_name ON raw_intel.planned_well (name);
CREATE INDEX idx_ri_planned_well_pad ON raw_intel.planned_well (pad_id);
CREATE INDEX idx_ri_planned_well_report
    ON raw_intel.planned_well (report_name, inventory_class);

-- -----------------------------------------------------------------------------
-- Entities: wellbores + geometry + surface + completion
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.wellbore CASCADE;
CREATE TABLE raw_intel.wellbore (
    wellbore_id                   BIGINT NOT NULL,
    well_id                       BIGINT,      -- exactly one of well_id / planned_well_id set
    planned_well_id               BIGINT,
    wellbore_name                 TEXT,
    wellbore_type                 TEXT,
    tvd_td                        DOUBLE PRECISION,
    md_td                         DOUBLE PRECISION,
    lateral_length                DOUBLE PRECISION,
    azimuth_deg                   DOUBLE PRECISION,
    midpoint_latitude             DOUBLE PRECISION,
    midpoint_longitude            DOUBLE PRECISION,
    bottom_hole_latitude          DOUBLE PRECISION,
    bottom_hole_longitude         DOUBLE PRECISION,
    heelpoint_latitude            DOUBLE PRECISION,
    heelpoint_longitude           DOUBLE PRECISION,
    formation_reported            TEXT,
    formation_reported_normalized TEXT,
    formation                     TEXT,
    formation_calculated          TEXT,
    sequence_number               INTEGER,
    status                        TEXT,
    spud_date                     DATE,
    td_date                       DATE,
    pa_date                       DATE,
    source_id                     BIGINT,
    created_at                    TIMESTAMP,
    updated_at                    TIMESTAMP,
    basin                         TEXT,
    subbasin                      TEXT,
    report_name                   TEXT NOT NULL,
    basin_slug                    TEXT NOT NULL,
    report_version                TEXT NOT NULL,
    ingested_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_wellbore_pk ON raw_intel.wellbore (wellbore_id, report_name);
CREATE INDEX idx_ri_wellbore_well ON raw_intel.wellbore (well_id);
CREATE INDEX idx_ri_wellbore_planned ON raw_intel.wellbore (planned_well_id);
CREATE INDEX idx_ri_wellbore_report ON raw_intel.wellbore (report_name);

DROP TABLE IF EXISTS raw_intel.wellbore_trajectory CASCADE;
CREATE TABLE raw_intel.wellbore_trajectory (
    trajectory_id   BIGINT NOT NULL,
    wellbore_id     BIGINT,
    planned_well_id BIGINT,
    geometry_wkt    TEXT,                       -- LINESTRING, EPSG:4326 (verified)
    crs             TEXT,
    source_id       BIGINT,
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP,
    basin           TEXT,
    subbasin        TEXT,
    report_name     TEXT NOT NULL,
    basin_slug      TEXT NOT NULL,
    report_version  TEXT NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- populated post-COPY per slice:
    --   UPDATE ... SET geom = ST_Force2D(ST_SetSRID(ST_GeomFromText(geometry_wkt), 4326))
    geom            geometry(Geometry, 4326)
);
CREATE UNIQUE INDEX idx_ri_trajectory_pk
    ON raw_intel.wellbore_trajectory (trajectory_id, report_name);
CREATE INDEX idx_ri_trajectory_wellbore ON raw_intel.wellbore_trajectory (wellbore_id);
CREATE INDEX idx_ri_trajectory_planned ON raw_intel.wellbore_trajectory (planned_well_id);
CREATE INDEX idx_ri_trajectory_geom ON raw_intel.wellbore_trajectory USING GIST (geom);
CREATE INDEX idx_ri_trajectory_report ON raw_intel.wellbore_trajectory (report_name);

DROP TABLE IF EXISTS raw_intel.surface_location CASCADE;
CREATE TABLE raw_intel.surface_location (
    surface_location_id BIGINT NOT NULL,
    well_id             BIGINT,
    planned_well_id     BIGINT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    crs                 TEXT,
    legal_description   TEXT,
    block_township      TEXT,
    section             TEXT,
    tx_survey           TEXT,
    abstract_lot        TEXT,
    source_id           BIGINT,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    basin               TEXT,
    subbasin            TEXT,
    report_name         TEXT NOT NULL,
    basin_slug          TEXT NOT NULL,
    report_version      TEXT NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_surface_pk
    ON raw_intel.surface_location (surface_location_id, report_name);
CREATE INDEX idx_ri_surface_well ON raw_intel.surface_location (well_id);
CREATE INDEX idx_ri_surface_planned ON raw_intel.surface_location (planned_well_id);

DROP TABLE IF EXISTS raw_intel.well_completion CASCADE;
CREATE TABLE raw_intel.well_completion (
    well_completion_id    BIGINT NOT NULL,
    well_id               BIGINT,      -- zero PDP rows as of 2025Q3 (planned wells only; verified)
    wellbore_id           BIGINT,
    planned_well_id       BIGINT,
    completion_sequence   INTEGER,
    completion_state      TEXT,
    completion_start_date DATE,
    completion_end_date   DATE,
    proppant_mass         DOUBLE PRECISION,
    fluid_volume          DOUBLE PRECISION,
    proppant_loading      DOUBLE PRECISION,    -- lb/ft
    fluid_loading         DOUBLE PRECISION,    -- gal/ft
    lateral_length_ft     DOUBLE PRECISION,
    source_id             BIGINT,
    created_at            TIMESTAMP,
    updated_at            TIMESTAMP,
    basin                 TEXT,
    subbasin              TEXT,
    report_name           TEXT NOT NULL,
    basin_slug            TEXT NOT NULL,
    report_version        TEXT NOT NULL,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_completion_pk
    ON raw_intel.well_completion (well_completion_id, report_name);
CREATE INDEX idx_ri_completion_planned ON raw_intel.well_completion (planned_well_id);
CREATE INDEX idx_ri_completion_well ON raw_intel.well_completion (well_id);

-- -----------------------------------------------------------------------------
-- ML scores (replaces raw_novi_intel.pud_attrs)
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.well_ml_score CASCADE;
CREATE TABLE raw_intel.well_ml_score (
    well_ml_score_id      BIGINT NOT NULL,
    well_id               BIGINT,
    planned_well_id       BIGINT,
    external_id           TEXT,        -- api10 or inventory label (fallback key)
    external_id_system    TEXT,
    well_class            TEXT,        -- PDP | BASE_CASE | EMERGING | UNKNOWN
    stream                TEXT,        -- oil | gas | ngl | condensate | water
    operator_id           BIGINT,
    operator_name         TEXT,
    formation             TEXT,
    spacing_score         DOUBLE PRECISION,
    spacing_tier          TEXT,        -- 'Tier-1'..'Tier-4'
    prior_depletion_score DOUBLE PRECISION,
    prior_depletion_tier  TEXT,        -- 'Tier-1'..'Tier-4' + 'No Depletion'
    completion_score      DOUBLE PRECISION,
    completion_tier       TEXT,
    source_id             BIGINT,
    created_at            TIMESTAMP,
    updated_at            TIMESTAMP,
    basin                 TEXT,
    subbasin              TEXT,
    report_name           TEXT NOT NULL,
    basin_slug            TEXT NOT NULL,
    report_version        TEXT NOT NULL,
    ingested_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_ml_score_pk
    ON raw_intel.well_ml_score (well_ml_score_id, report_name);
CREATE INDEX idx_ri_ml_score_planned ON raw_intel.well_ml_score (planned_well_id, stream);
CREATE INDEX idx_ri_ml_score_external ON raw_intel.well_ml_score (external_id);

DROP TABLE IF EXISTS raw_intel.well_rock_quality CASCADE;
CREATE TABLE raw_intel.well_rock_quality (
    well_rock_quality_id BIGINT NOT NULL,
    well_id              BIGINT,
    planned_well_id      BIGINT,
    trajectory_id        BIGINT,
    external_id          TEXT,
    external_id_system   TEXT,
    well_class           TEXT,
    stream               TEXT,
    operator_id          BIGINT,
    operator_name        TEXT,
    formation            TEXT,
    rock_quality_score   DOUBLE PRECISION,
    rock_quality_tier    TEXT,
    source_id            BIGINT,
    created_at           TIMESTAMP,
    updated_at           TIMESTAMP,
    basin                TEXT,
    subbasin             TEXT,
    report_name          TEXT NOT NULL,
    basin_slug           TEXT NOT NULL,
    report_version       TEXT NOT NULL,
    ingested_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_rock_quality_pk
    ON raw_intel.well_rock_quality (well_rock_quality_id, report_name);
CREATE INDEX idx_ri_rock_quality_planned
    ON raw_intel.well_rock_quality (planned_well_id, stream);
CREATE INDEX idx_ri_rock_quality_external ON raw_intel.well_rock_quality (external_id);

-- -----------------------------------------------------------------------------
-- Economics
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.well_cost_summary CASCADE;
CREATE TABLE raw_intel.well_cost_summary (
    well_cost_summary_id        BIGINT NOT NULL,
    well_id                     BIGINT,
    planned_well_id             BIGINT,
    currency                    TEXT,
    total_dc_cost               NUMERIC(28,7),
    total_dcet_cost             NUMERIC(28,7),
    normalized_dc_cost_per_ft   NUMERIC(28,7),
    normalized_dcet_cost_per_ft NUMERIC(28,7),
    source_id                   BIGINT,
    created_at                  TIMESTAMP,
    updated_at                  TIMESTAMP,
    basin                       TEXT,
    subbasin                    TEXT,
    report_name                 TEXT NOT NULL,
    basin_slug                  TEXT NOT NULL,
    report_version              TEXT NOT NULL,
    ingested_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_cost_pk
    ON raw_intel.well_cost_summary (well_cost_summary_id, report_name);
CREATE INDEX idx_ri_cost_well ON raw_intel.well_cost_summary (well_id);
CREATE INDEX idx_ri_cost_planned ON raw_intel.well_cost_summary (planned_well_id);

DROP TABLE IF EXISTS raw_intel.well_economics_summary CASCADE;
CREATE TABLE raw_intel.well_economics_summary (
    well_economics_summary_id BIGINT NOT NULL,
    well_id                   BIGINT,
    planned_well_id           BIGINT,
    npv5                      NUMERIC(28,7),
    npv10                     NUMERIC(28,7),
    npv15                     NUMERIC(28,7),
    npv20                     NUMERIC(28,7),
    npv25                     NUMERIC(28,7),
    pv5                       NUMERIC(28,7),
    pv10                      NUMERIC(28,7),
    pv15                      NUMERIC(28,7),
    pv20                      NUMERIC(28,7),
    pv25                      NUMERIC(28,7),
    npv                       NUMERIC(28,7),
    irr                       DOUBLE PRECISION,   -- FRACTION (median |irr| 0.118; verified)
    pvi                       DOUBLE PRECISION,
    payback_months            INTEGER,
    double_payback_months     INTEGER,
    breakeven_1yr             DOUBLE PRECISION,
    breakeven_2yr             DOUBLE PRECISION,
    breakeven_3yr             DOUBLE PRECISION,
    npv5_breakeven            DOUBLE PRECISION,
    npv10_breakeven           DOUBLE PRECISION,
    npv15_breakeven           DOUBLE PRECISION,
    npv20_breakeven           DOUBLE PRECISION,
    npv25_breakeven           DOUBLE PRECISION,
    lifetime_months           INTEGER,
    eur_oil_30yr              DOUBLE PRECISION,   -- 30yr is the ONLY horizon in the share;
    eur_gas_30yr              DOUBLE PRECISION,   -- matches legacy sticks.oil_eur exactly
    eur_ngl_30yr              DOUBLE PRECISION,   -- (median ratio 1.0000, n=431)
    eur_dry_gas_30yr          DOUBLE PRECISION,
    eur_water_30yr            DOUBLE PRECISION,
    ip_oil                    DOUBLE PRECISION,
    ip_ngl                    DOUBLE PRECISION,
    ip_gas                    DOUBLE PRECISION,
    ip_dry_gas                DOUBLE PRECISION,
    ip_water                  DOUBLE PRECISION,
    ngl_yield                 DOUBLE PRECISION,
    ngl_shrink                DOUBLE PRECISION,
    stream                    TEXT,
    currency                  TEXT,
    price_deck_id             TEXT,
    source_id                 BIGINT,
    created_at                TIMESTAMP,
    updated_at                TIMESTAMP,
    basin                     TEXT,
    subbasin                  TEXT,
    report_name               TEXT NOT NULL,
    basin_slug                TEXT NOT NULL,
    report_version            TEXT NOT NULL,
    ingested_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_econ_pk
    ON raw_intel.well_economics_summary (well_economics_summary_id, report_name);
CREATE INDEX idx_ri_econ_well ON raw_intel.well_economics_summary (well_id);
CREATE INDEX idx_ri_econ_planned ON raw_intel.well_economics_summary (planned_well_id);

-- -----------------------------------------------------------------------------
-- Arps decline segments (replaces raw_novi_intel.arps)
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.arps_forecast CASCADE;
CREATE TABLE raw_intel.arps_forecast (
    well_ref                       TEXT NOT NULL,   -- PW-{id} (planned only as of 2025Q3)
    inventory_class                TEXT,
    stream                         TEXT,            -- oil | gas | water; 3 segments each
    segment_number                 INTEGER,
    kind                           TEXT,
    segment_curve_type             TEXT,
    b_factor                       DOUBLE PRECISION,
    nominal_decline_rate           DOUBLE PRECISION,   -- Di, NOMINAL per-year
    effective_decline_rate_secant  DOUBLE PRECISION,
    effective_decline_rate_tangent DOUBLE PRECISION,
    segment_start_rate             DOUBLE PRECISION,   -- qi
    segment_end_rate               DOUBLE PRECISION,
    terminal_transition_day        INTEGER,
    day_start                      INTEGER,
    day_stop                       INTEGER,
    basin                          TEXT,
    subbasin                       TEXT,
    report_name                    TEXT NOT NULL,
    created_at                     TIMESTAMP,
    basin_slug                     TEXT NOT NULL,
    report_version                 TEXT NOT NULL,
    ingested_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_ri_arps_pk
    ON raw_intel.arps_forecast (well_ref, stream, segment_number, report_name);
CREATE INDEX idx_ri_arps_report ON raw_intel.arps_forecast (report_name);

-- -----------------------------------------------------------------------------
-- WELL_MASTER — the spine (replaces raw_novi_intel.sticks as the union of
-- PDP + BASE_CASE + EMERGING). Grain: (well_ref, report_name, inventory_class).
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.well_master CASCADE;
CREATE TABLE raw_intel.well_master (
    well_ref               TEXT NOT NULL,   -- UWI_API (PDP) | PW-{id} (planned)
    inventory_class        TEXT NOT NULL,   -- PDP | BASE_CASE | EMERGING
    uwi_api                TEXT,            -- PDP only
    name                   TEXT,            -- planned only (= legacy unique_id for BASE_CASE)
    wellbore_type          TEXT,
    status                 TEXT,
    spud_date              DATE,
    td_date                DATE,
    pa_date                DATE,
    first_production_date  DATE,
    planned_til_date       DATE,
    lateral_length         DOUBLE PRECISION,
    azimuth_deg            DOUBLE PRECISION,
    tvd_td                 DOUBLE PRECISION,
    md_td                  DOUBLE PRECISION,
    formation              TEXT,
    latitude               DOUBLE PRECISION,
    longitude              DOUBLE PRECISION,
    midpoint_latitude      DOUBLE PRECISION,
    midpoint_longitude     DOUBLE PRECISION,
    bottom_hole_latitude   DOUBLE PRECISION,
    bottom_hole_longitude  DOUBLE PRECISION,
    geometry_wkt           TEXT,
    operator_name          TEXT,
    basin                  TEXT,
    subbasin               TEXT,
    county                 TEXT,
    pad_name               TEXT,
    report_name            TEXT NOT NULL,
    created_at             TIMESTAMP,
    updated_at             TIMESTAMP,
    basin_slug             TEXT NOT NULL,
    report_version         TEXT NOT NULL,
    ingested_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- populated post-COPY per slice (avg WKT 177 chars — cheap to duplicate
    -- here; saves the curated layer a 3-way union back through trajectory)
    geom                   geometry(Geometry, 4326)
);
CREATE UNIQUE INDEX idx_ri_well_master_pk
    ON raw_intel.well_master (well_ref, report_name, inventory_class);
CREATE INDEX idx_ri_well_master_api10 ON raw_intel.well_master (uwi_api)
    WHERE uwi_api IS NOT NULL;
CREATE INDEX idx_ri_well_master_class
    ON raw_intel.well_master (basin_slug, inventory_class);
CREATE INDEX idx_ri_well_master_geom ON raw_intel.well_master USING GIST (geom);
CREATE INDEX idx_ri_well_master_report ON raw_intel.well_master (report_name);

-- -----------------------------------------------------------------------------
-- PRODUCTION_FORECAST — monthly P50 forecast, planned wells only, 30-day
-- FORECAST_DAY steps (verified 2026-07-08; identical shape to the legacy
-- raw_novi_intel.forecast). LOAD IS DEFERRED to the phase-4 forecast gate:
-- the table exists so the DDL is complete, but --forecast is a separate
-- loader flag and the cutover sequence loads it AFTER the legacy 7.7 GB
-- forecast table is dropped (disk headroom on the 2 GB instance).
-- condensate columns are all-NULL for Permian; the extractor may skip them.
-- -----------------------------------------------------------------------------

DROP TABLE IF EXISTS raw_intel.production_forecast CASCADE;
CREATE TABLE raw_intel.production_forecast (
    production_forecast_id BIGINT,
    well_id                BIGINT,      -- NULL as of 2025Q3 (planned wells only)
    planned_well_id        BIGINT,
    period_granularity     TEXT,        -- 'monthly' (only value as of 2025Q3)
    forecast_day           INTEGER,     -- 30-day steps (= legacy ip_day)
    year                   INTEGER,
    month                  INTEGER,
    scenario               TEXT,        -- 'P50' (only value as of 2025Q3)
    oil_per_day            DOUBLE PRECISION,
    cumulative_oil         DOUBLE PRECISION,
    gas_per_day            DOUBLE PRECISION,
    cumulative_gas         DOUBLE PRECISION,
    ngl_per_day            DOUBLE PRECISION,
    cumulative_ngl         DOUBLE PRECISION,
    water_per_day          DOUBLE PRECISION,
    cumulative_water       DOUBLE PRECISION,
    condensate_per_day     DOUBLE PRECISION,
    cumulative_condensate  DOUBLE PRECISION,
    source_id              BIGINT,
    created_at             TIMESTAMP,
    basin                  TEXT,
    subbasin               TEXT,
    report_name            TEXT NOT NULL,
    basin_slug             TEXT NOT NULL,
    report_version         TEXT NOT NULL
    -- no ingested_at: 73M rows x 8 bytes matters; report_name slice is enough
);
CREATE INDEX idx_ri_forecast_planned
    ON raw_intel.production_forecast (planned_well_id, forecast_day);
CREATE INDEX idx_ri_forecast_report ON raw_intel.production_forecast (report_name);

-- -----------------------------------------------------------------------------
-- stick_id_map — APPEND-ONLY stable id registry. NEVER dropped by re-runs of
-- this file. Pins one positive bigint stick_id per well_ref forever, so the
-- rewritten curated.intel_locations keeps a stable key across quarterly
-- reloads (sql/19/21/25/22 and erebor promoteId all key on stick_id; erebor
-- PDP rows use -(api10), so these stay positive and disjoint). Seeded above
-- the legacy raw_novi_intel.sticks maximum so history never collides.
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_intel.stick_id_map (
    well_ref    TEXT PRIMARY KEY,
    stick_id    BIGINT GENERATED ALWAYS AS IDENTITY,
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ri_stick_id_map_id
    ON raw_intel.stick_id_map (stick_id);

-- Seed the identity above legacy stick_id space, once (no-op if already seeded
-- or if the map has rows). Falls back to 10_000_000 if the legacy table is gone.
DO $$
DECLARE
    seed BIGINT;
BEGIN
    IF (SELECT COUNT(*) FROM raw_intel.stick_id_map) = 0 THEN
        BEGIN
            SELECT COALESCE(MAX(stick_id), 0) + 1000000 INTO seed
            FROM raw_novi_intel.sticks;
        EXCEPTION WHEN undefined_table THEN
            seed := 10000000;
        END;
        PERFORM setval(pg_get_serial_sequence('raw_intel.stick_id_map', 'stick_id'),
                       seed, false);
        RAISE NOTICE 'stick_id_map identity seeded at %', seed;
    END IF;
END $$;

COMMENT ON SCHEMA raw_intel IS
  '1:1 mirror of the Novi INTEL Snowflake share (NOVI_DATA_ACCESS.NOVI_INTEL). '
  'Loaded per report_name slice by etl/intel_sf/extract.py. Supersedes the '
  'static-file raw_novi_intel layer (sql/11) except the frozen display '
  'geometries (pads / land_grid / basin_outline), which the share lacks.';
COMMENT ON TABLE raw_intel.stick_id_map IS
  'Append-only well_ref -> stable positive stick_id registry; survives DDL '
  're-runs and quarterly reloads. Do NOT drop or truncate: downstream matviews '
  'and erebor selections key on stick_id.';
