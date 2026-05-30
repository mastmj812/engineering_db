-- =============================================================================
-- 07 — Cutover prep: add wellstick_geom to curated.wells
--
-- One-time migration to apply the wellstick_geom addition baked into
-- sql/04_curated.sql. Required because curated.wells is a MATERIALIZED VIEW
-- — PostgreSQL has no ALTER MATERIALIZED VIEW ADD COLUMN, so the only way
-- to introduce a new column is DROP + CREATE. The DROP cascades through:
--
--     curated.wells
--       └─ curated.wells_enriched          (regular view)
--       └─ curated.production_normalized   (matview, JOINs wells)
--             └─ curated.type_curve_cohorts (matview, aggregates prod_norm)
--
-- So we drop curated.wells CASCADE and re-run the whole curated chain.
-- sql/04 is now the authoritative definition (it includes wellstick_geom
-- and its GIST index); sql/05 and sql/06 are unchanged.
--
-- Run order: after sql/04 has been updated; from project root:
--   psql -d oilgas -f sql/07_cutover_prep.sql
--
-- After this runs once, the bootstrap order (sql/04 → sql/05 → sql/06) is
-- self-consistent again, and sql/07 should not need to be run again.
--
-- Rationale: per the engineering_db memory, "raw DDL is generated, not
-- hand-written" — but the curated layer is hand-written. New curated
-- columns are added by editing the source file (sql/04 here) and shipping
-- a migration script that rebuilds the affected matviews.
-- =============================================================================


\echo
\echo --- 1. Drop curated.wells with CASCADE (also drops wells_enriched, ---
\echo ---    production_normalized, type_curve_cohorts).                  ---

DROP MATERIALIZED VIEW IF EXISTS curated.wells CASCADE;


\echo
\echo --- 2. Re-build curated.wells with wellstick_geom column ---
\ir 04_curated.sql


\echo
\echo --- 3. Re-build curated.production (no schema change) ---
\ir 05_curated_production.sql


\echo
\echo --- 4. Re-build curated.wells_enriched + production_normalized +     ---
\echo ---    type_curve_cohorts. wells_enriched picks up wellstick_geom    ---
\echo ---    automatically via SELECT w.*; the others do not surface it.   ---
\ir 06_curated_derived.sql


-- =============================================================================
-- DONE.
-- Sanity checks (run interactively after this script completes):
--
--   -- Coverage in the 4-county type-curve scope:
--   SELECT
--     COUNT(*)                                              AS n,
--     COUNT(wellstick_geom)                                 AS has_wellstick,
--     ROUND(100.0 * COUNT(wellstick_geom) / COUNT(*), 2)    AS pct
--   FROM curated.wells
--   WHERE county_code IN ('48301','48389','48475','48495')
--     AND first_completion_date >= DATE '2010-01-01';
--
--   -- Inspect one well's wellstick coordinates (Reeves Wolfcamp, recent):
--   SELECT api10, well_name, ST_AsText(wellstick_geom)
--   FROM curated.wells
--   WHERE county_code = '48389'
--     AND wellstick_geom IS NOT NULL
--     AND ST_NPoints(wellstick_geom) = 4
--   LIMIT 3;
-- =============================================================================
