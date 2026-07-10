-- =============================================================================
-- 11 — raw_novi_intel: Novi Intelligence OVERLAY geometries (frozen trio)
--
-- TRIMMED 2026-07-10 (Snowflake-share migration, phase 8). This schema once
-- held the full quarterly file drop (sticks / pud_attrs / analytics / arps /
-- forecast); those tables were superseded by the raw_intel mirror of the Novi
-- INTEL Snowflake share (sql/27, loaded by scripts/load_intel_sf.py) and
-- DROPPED from Supabase on 2026-07-10 (~800 MB + the 7.7 GB forecast
-- reclaimed). Their DDL lived here through commit 2989c92 if archaeology is
-- ever needed.
--
-- What remains is the display-geometry trio the share does NOT carry:
--   pads          — DSU pad polygons + pad-level NPV rollup
--   land_grid     — Novi-supplied land grid polygons (raw DBF attrs in JSONB)
--   basin_outline — basin outline polygons
-- Novi is expected to keep shipping these as shapefiles outside the share;
-- etl/novi_intel/load_shapefiles.py is their only ingest route. Currently
-- frozen at the 3Q25 drop.
--
-- Geometry: all Novi layers are EPSG:4326, stored as generic
-- geometry(Geometry,4326) polygons.
--
-- RUN: executed by scripts/load_novi_intel.py --ddl via psycopg.
-- Idempotent BUT DESTRUCTIVE: DROP ... IF EXISTS then CREATE wipes the loaded
-- geometries — only re-run ahead of a fresh --shapefiles load from disk.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw_novi_intel;

-- -----------------------------------------------------------------------------
-- pads — Novi DSU pad polygons (+ pad-level NPV rollup; columns differ by basin)
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS raw_novi_intel.pads CASCADE;
CREATE TABLE raw_novi_intel.pads (
    pad_id          BIGSERIAL PRIMARY KEY,
    basin           TEXT NOT NULL,          -- 'delaware' | 'midland'
    report_version  TEXT NOT NULL,          -- e.g. '3Q25'
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

CREATE INDEX IF NOT EXISTS idx_rni_pads_geom ON raw_novi_intel.pads USING GIST (geom);
