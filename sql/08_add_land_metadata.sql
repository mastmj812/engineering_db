-- =============================================================================
-- 08 — Add Novi land/admin metadata to curated.wells
--
-- One-time migration to apply seven new columns added to sql/04_curated.sql:
--
--   LAND METADATA (Novi WellDetails passthroughs)
--     section, township, range_, tx_block, tx_survey, tx_abstract
--
--   GEOLOGY trust flag (Novi WellDetails passthrough)
--     directional_survey_is_planned   ← see COMMENT ON COLUMN in sql/04;
--     it diagnoses provisional formation assignments (the survey is the
--     operator's pre-drill plan, not the actual post-drill survey).
--
-- Same drop-and-rebuild dance as sql/07_cutover_prep.sql — curated.wells is
-- a MATERIALIZED VIEW so there is no ALTER ADD COLUMN. CASCADE drops
-- wells_enriched / production_normalized / type_curve_cohorts; sql/04 → 05
-- → 06 rebuild them all.
--
-- Run order: after sql/04 has been updated; from project root:
--   psql -d oilgas -f sql/08_add_land_metadata.sql
-- =============================================================================


\echo
\echo --- 1. Drop curated.wells CASCADE ---
DROP MATERIALIZED VIEW IF EXISTS curated.wells CASCADE;


\echo
\echo --- 2. Re-build curated.wells with land metadata + survey-trust flag ---
\ir 04_curated.sql


\echo
\echo --- 3. Re-build curated.production ---
\ir 05_curated_production.sql


\echo
\echo --- 4. Re-build wells_enriched + production_normalized + cohorts ---
\ir 06_curated_derived.sql


-- =============================================================================
-- DONE.
-- Sanity checks (in psql / pgAdmin):
--
--   -- Coverage in the 4-county type-curve scope:
--   SELECT
--     COUNT(*)                                          AS n,
--     COUNT(section)                                    AS has_section,
--     COUNT(tx_block)                                   AS has_tx_block,
--     COUNT(*) FILTER (WHERE directional_survey_is_planned = TRUE)
--                                                       AS planned_survey_wells,
--     COUNT(*) FILTER (WHERE directional_survey_is_planned = FALSE)
--                                                       AS actual_survey_wells,
--     COUNT(*) FILTER (WHERE directional_survey_is_planned IS NULL)
--                                                       AS unknown_survey
--   FROM curated.wells
--   WHERE county_code IN ('48301','48389','48475','48495');
--
--   -- Same breakdown Permian-wide, to see if NM lag is visible:
--   SELECT state_code,
--          COUNT(*) FILTER (WHERE directional_survey_is_planned = TRUE)  AS planned,
--          COUNT(*) FILTER (WHERE directional_survey_is_planned = FALSE) AS actual,
--          ROUND(100.0 * COUNT(*) FILTER (WHERE directional_survey_is_planned = TRUE)
--                / NULLIF(COUNT(*) FILTER (WHERE directional_survey_is_planned IS NOT NULL), 0), 1)
--                                                       AS pct_planned
--   FROM curated.wells
--   WHERE env_region = 'PERMIAN'
--   GROUP BY state_code
--   ORDER BY state_code;
-- =============================================================================
