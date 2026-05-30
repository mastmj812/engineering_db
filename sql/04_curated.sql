-- =============================================================================
-- Curated layer - Phase 1: curated.wells
--
-- Materialized view joining Novi (Wells + WellDetails + WellSpacing) to the
-- latest Enverus completion event per wellbore. Permian-wide scope (matches
-- the warehouse's raw_enverus filter `envregion='PERMIAN'`).
--
-- Key conventions:
-- - Primary key: api10 (from Novi, varchar). Unique index supports
--   CONCURRENTLY refresh.
-- - Source-of-truth per column documented in inline comments. See the
--   project's project_engineering_db memory for the full policy.
-- - Snake_case column names everywhere (curated lives independently of
--   each source's casing convention).
-- - Soft-deleted rows in either source are excluded (DeletedAt / deleteddate
--   IS NULL).
-- - Refreshed by curated.refresh_all() after every daily orchestrator run.
--
-- Run order: apply after sql/01, sql/02, sql/03.
--   psql -d oilgas -f sql/04_curated.sql
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.wells CASCADE;


CREATE MATERIALIZED VIEW curated.wells AS
WITH enverus_latest AS (
    -- Enverus's `wells` dataset has one row per completion event. Collapse
    -- to one row per wellbore (api10) by picking the latest completion via
    -- completiondate. DISTINCT ON is Postgres-specific but the cleanest
    -- expression of this pattern. Soft-deleted Enverus rows excluded.
    SELECT DISTINCT ON (LEFT(api_uwi_14_unformatted, 10))
        LEFT(api_uwi_14_unformatted, 10) AS api10_join,
        api_uwi_14,
        api_uwi_14_unformatted,
        wellid,
        completionid,
        wellname,
        wellpadid,
        envoperator,
        envregion,
        envbasin,
        envplay,
        envsubplay,
        envinterval,
        envwellstatus,
        envwelltype,
        envprodwelltype,
        county          AS env_county,
        stateprovince   AS env_state,
        trajectory,
        formation       AS env_formation,
        laterallength_ft,
        tvd_ft,
        md_ft,
        spuddate,
        drillingenddate,
        completiondate,
        firstproddate,
        lastproducingmonth,
        plugdate,
        proppant_lbs,
        totalfluidpumped_bbl,
        fracstages,
        proppantintensity_lbsperft,
        fluidintensity_bblperft,
        proppantloading_lbspergal,
        averagestagespacing_ft,
        clustersperstage           AS clusters_per_stage,
        clustersper1000ft          AS clusters_per_1000ft,
        latitude                   AS env_surface_lat,
        longitude                  AS env_surface_lon,
        latitude_bh                AS env_bhl_lat,
        longitude_bh               AS env_bhl_lon,
        monthstopeakproduction
    FROM raw_enverus.wells
    WHERE deleteddate IS NULL
      AND api_uwi_14_unformatted IS NOT NULL
    ORDER BY LEFT(api_uwi_14_unformatted, 10),
             completiondate DESC NULLS LAST,
             completionid DESC NULLS LAST
)
SELECT
    -- =========================================================================
    -- IDENTIFIERS
    -- =========================================================================
    n."API10"                                                  AS api10,
    e.api_uwi_14                                               AS api14,
    e.api_uwi_14_unformatted                                   AS api14_unformatted,
    e.wellid                                                   AS enverus_wellid,
    e.completionid                                             AS enverus_latest_completionid,
    -- Well name: Novi WellDetails is most current, fall back to Wells, then Enverus
    COALESCE(wd."WellName", n."WellName", e.wellname)          AS well_name,
    e.wellpadid                                                AS well_pad_id,

    -- =========================================================================
    -- OPERATOR (Novi authoritative - tracks current operator across changes)
    -- =========================================================================
    COALESCE(wd."CurrentOperator", n."CurrentOperator")        AS current_operator,
    COALESCE(wd."OriginalOperator", n."OriginalOperator")      AS original_operator,
    COALESCE(wd."CurrentOperatorEntity",
             n."CurrentOperatorEntity")                        AS operator_entity,

    -- =========================================================================
    -- GEOGRAPHIC (Novi authoritative - both sources, Novi has CountyCode/FIPS)
    -- =========================================================================
    COALESCE(wd."State", n."State")                            AS state,
    COALESCE(wd."StateCode", n."StateCode")                    AS state_code,
    COALESCE(wd."County", n."County")                          AS county,
    COALESCE(wd."CountyUnique", n."CountyUnique")              AS county_unique,
    COALESCE(wd."CountyCode", n."CountyCode")                  AS county_code,
    COALESCE(wd."Basin", n."Basin")                            AS basin,
    COALESCE(wd."Subbasin", n."Subbasin")                      AS subbasin,
    -- Enverus classifications kept alongside Novi's (different taxonomies)
    e.envregion                                                AS env_region,
    e.envbasin                                                 AS env_basin,
    e.envplay                                                  AS env_play,
    e.envsubplay                                               AS env_sub_play,
    e.envinterval                                              AS env_interval,

    -- =========================================================================
    -- LAND METADATA (Novi WellDetails — TX/NM land subdivision; useful for
    -- spatial filtering and unit reconstruction. TX wells use the Spanish
    -- grant system (Block / Survey / Abstract); NM wells use PLSS (Township
    -- / Range / Section). Section is populated for both systems.
    -- `range_` carries a trailing underscore because `range` is contextually
    -- reserved in PG window-function syntax.)
    -- =========================================================================
    wd."Section"                                               AS section,
    wd."Township"                                              AS township,
    wd."Range"                                                 AS range_,
    wd."TXBlock"                                               AS tx_block,
    wd."TXSurvey"                                              AS tx_survey,
    wd."TXAbstract"                                            AS tx_abstract,

    -- =========================================================================
    -- WELLBORE LOCATIONS (Novi WellDetails is richer - has LP/MP)
    -- =========================================================================
    COALESCE(wd."SHLLatitude", n."SHLLatitude",
             e.env_surface_lat)                                AS surface_lat,
    COALESCE(wd."SHLLongitude", n."SHLLongitude",
             e.env_surface_lon)                                AS surface_lon,
    COALESCE(wd."BHLLatitude", n."BHLLatitude", e.env_bhl_lat) AS bhl_lat,
    COALESCE(wd."BHLLongitude", n."BHLLongitude",
             e.env_bhl_lon)                                    AS bhl_lon,
    wd."LPLatitude"                                            AS landing_point_lat,
    wd."LPLongitude"                                           AS landing_point_lon,
    wd."MPLatitude"                                            AS midpoint_lat,
    wd."MPLongitude"                                           AS midpoint_lon,

    -- -------------------------------------------------------------------------
    -- Wellstick: 4-point LINESTRING built from the Novi locations
    -- (Surface Hole → Landing Point → Midpoint → Bottom Hole), in the
    -- well's natural traverse order. NULL points are skipped; result is
    -- NULL if fewer than two valid points exist. Replaces what Enverus's
    -- LateralLine WKT used to provide in the type-curve app.
    -- -------------------------------------------------------------------------
    CASE
        WHEN (
            (COALESCE(wd."SHLLatitude", n."SHLLatitude") IS NOT NULL)::int
          + (wd."LPLatitude"  IS NOT NULL)::int
          + (wd."MPLatitude"  IS NOT NULL)::int
          + (COALESCE(wd."BHLLatitude", n."BHLLatitude") IS NOT NULL)::int
        ) >= 2
        THEN ST_SetSRID(
            ST_MakeLine(
                ARRAY_REMOVE(ARRAY[
                    CASE WHEN COALESCE(wd."SHLLatitude",  n."SHLLatitude")  IS NOT NULL
                          AND COALESCE(wd."SHLLongitude", n."SHLLongitude") IS NOT NULL
                         THEN ST_Point(
                                COALESCE(wd."SHLLongitude", n."SHLLongitude"),
                                COALESCE(wd."SHLLatitude",  n."SHLLatitude"))
                    END,
                    CASE WHEN wd."LPLatitude" IS NOT NULL
                          AND wd."LPLongitude" IS NOT NULL
                         THEN ST_Point(wd."LPLongitude", wd."LPLatitude")
                    END,
                    CASE WHEN wd."MPLatitude" IS NOT NULL
                          AND wd."MPLongitude" IS NOT NULL
                         THEN ST_Point(wd."MPLongitude", wd."MPLatitude")
                    END,
                    CASE WHEN COALESCE(wd."BHLLatitude",  n."BHLLatitude")  IS NOT NULL
                          AND COALESCE(wd."BHLLongitude", n."BHLLongitude") IS NOT NULL
                         THEN ST_Point(
                                COALESCE(wd."BHLLongitude", n."BHLLongitude"),
                                COALESCE(wd."BHLLatitude",  n."BHLLatitude"))
                    END
                ], NULL)
            ),
            4326
        )
    END                                                        AS wellstick_geom,

    -- =========================================================================
    -- GEOLOGY (Novi authoritative - distinct Formation / Reported / Grid)
    -- =========================================================================
    COALESCE(wd."Formation", n."Formation")                    AS formation,
    COALESCE(wd."ReportedFormation", n."ReportedFormation")    AS reported_formation,
    COALESCE(wd."GridFormation", n."GridFormation")            AS grid_formation,
    -- Trust flag for formation assignment. When TRUE, the directional
    -- survey on file is the operator's pre-drill PLAN, not the actual
    -- post-drill survey — and both Novi and Enverus use that planned
    -- survey to "land" the well in their proprietary structure model,
    -- which often misassigns Formation / ENVInterval. Self-corrects when
    -- the operator uploads the actual survey; NM regulators are
    -- notoriously slow, so many NM wells carry provisional formations
    -- for an extended period after spud. See COMMENT ON COLUMN below.
    wd."DirectionalSurveyIsPlanned"                            AS directional_survey_is_planned,

    -- =========================================================================
    -- WELLBORE (Novi WellDetails primary, Enverus fallback)
    -- =========================================================================
    COALESCE(wd."TVD", n."TVD", e.tvd_ft::int)                 AS tvd_ft,
    COALESCE(wd."MD", n."MD", e.md_ft::int)                    AS md_ft,
    COALESCE(wd."LateralLength", n."LateralLength",
             e.laterallength_ft::int)                          AS lateral_length_ft,
    n."WellboreLateralLength"                                  AS wellbore_lateral_length_ft,
    e.trajectory                                               AS enverus_trajectory,
    COALESCE(wd."SlantCalculated", n."SlantCalculated")        AS novi_slant_calculated,

    -- =========================================================================
    -- DATES (Novi authoritative - FirstProductionDate is Novi-calculated)
    -- =========================================================================
    COALESCE(wd."SpudDate", n."SpudDate", e.spuddate::date)    AS spud_date,
    COALESCE(wd."DrillingEndDate", n."DrillingEndDate",
             e.drillingenddate::date)                          AS drilling_end_date,
    COALESCE(wd."FirstCompletionDate",
             n."FirstCompletionDate",
             e.completiondate::date)                           AS first_completion_date,
    COALESCE(wd."FirstProductionDate",
             n."FirstProductionDate",
             e.firstproddate::date)                            AS first_production_date,
    COALESCE(wd."HasAccurateFirstProductionDate",
             n."HasAccurateFirstProductionDate")               AS has_accurate_first_prod_date,
    COALESCE(wd."LastReportedMonth", n."LastReportedMonth",
             e.lastproducingmonth::date)                       AS last_reported_month,
    COALESCE(wd."PluggedDate", n."PluggedDate", e.plugdate::date)
                                                               AS plugged_date,

    -- =========================================================================
    -- COMPLETION INTENSITY (Enverus authoritative - richer column set;
    -- Novi FirstCompletion* as fallback)
    -- =========================================================================
    COALESCE(e.proppant_lbs::bigint,
             wd."FirstCompletionProppantMass"::bigint,
             n."FirstCompletionProppantMass"::bigint)          AS proppant_lbs,
    COALESCE(e.totalfluidpumped_bbl::bigint,
             (wd."FirstCompletionFluidVolume" / 42)::bigint,   -- Novi is gallons → bbl
             (n."FirstCompletionFluidVolume" / 42)::bigint)    AS fluid_bbl,
    COALESCE(e.fracstages,
             wd."FirstCompletionStages",
             n."FirstCompletionStages")                        AS frac_stages,
    e.proppantintensity_lbsperft                               AS proppant_lbs_per_ft,
    e.fluidintensity_bblperft                                  AS fluid_bbl_per_ft,
    COALESCE(e.proppantloading_lbspergal,
             wd."FirstCompletionProppantLbsPerGal")            AS proppant_lbs_per_gal,
    COALESCE(e.averagestagespacing_ft::int,
             wd."FirstCompletionStages_AvgSpacing")            AS avg_stage_spacing_ft,
    e.clusters_per_stage,
    e.clusters_per_1000ft,
    wd."SoakTimeDays"                                          AS soak_time_days,

    -- =========================================================================
    -- PRE-COMPUTED PRODUCTION SUMMARY (Novi WellDetails pass-through)
    -- =========================================================================
    wd."Cum12MOil"                                             AS cum_12m_oil_bbl,
    wd."Cum12MGas"                                             AS cum_12m_gas_mcf,
    wd."Cum12MWater"                                           AS cum_12m_water_bbl,
    wd."Cum12MBOE"                                             AS cum_12m_boe,
    wd."Cum24MOil"                                             AS cum_24m_oil_bbl,
    wd."Cum24MGas"                                             AS cum_24m_gas_mcf,
    wd."Cum24MWater"                                           AS cum_24m_water_bbl,
    wd."Cum24MBOE"                                             AS cum_24m_boe,
    wd."CumLifeOil"                                            AS cum_life_oil_bbl,
    wd."CumLifeGas"                                            AS cum_life_gas_mcf,
    wd."CumLifeWater"                                          AS cum_life_water_bbl,
    wd."CumLifeBOE"                                            AS cum_life_boe,
    wd."CumLifeGOR"                                            AS cum_life_gor,

    -- =========================================================================
    -- EUR (Novi WellDetails pass-through - forecasted)
    -- =========================================================================
    wd."EUR20YROil"                                            AS eur_20yr_oil_bbl,
    wd."EUR20YRGas"                                            AS eur_20yr_gas_mcf,
    wd."EUR20YRWater"                                          AS eur_20yr_water_bbl,
    wd."EUR20YRBOE"                                            AS eur_20yr_boe,
    wd."EUR30YROil"                                            AS eur_30yr_oil_bbl,
    wd."EUR30YRGas"                                            AS eur_30yr_gas_mcf,
    wd."EUR30YRWater"                                          AS eur_30yr_water_bbl,
    wd."EUR30YRBOE"                                            AS eur_30yr_boe,
    wd."EUR50YROil"                                            AS eur_50yr_oil_bbl,
    wd."EUR50YRGas"                                            AS eur_50yr_gas_mcf,
    wd."EUR50YRWater"                                          AS eur_50yr_water_bbl,
    wd."EUR50YRBOE"                                            AS eur_50yr_boe,

    -- =========================================================================
    -- PEAK RATES (Novi WellDetails - which month-on-prod was peak, what rate)
    -- =========================================================================
    wd."PeakMonthOil"                                          AS peak_month_oil,
    wd."PeakMonthGas"                                          AS peak_month_gas,
    wd."PeakMonthWater"                                        AS peak_month_water,
    wd."PeakMonthBOE"                                          AS peak_month_boe,
    wd."PeakMonthOilRate"                                      AS peak_oil_rate_bblpd,
    wd."PeakMonthGasRate"                                      AS peak_gas_rate_mcfpd,
    wd."PeakMonthWaterRate"                                    AS peak_water_rate_bblpd,
    wd."PeakMonthBOERate"                                      AS peak_boe_rate_boepd,
    e.monthstopeakproduction                                   AS months_to_peak_production,

    -- =========================================================================
    -- SPACING (Novi WellSpacing pass-through)
    -- =========================================================================
    ws."ClosestWellXY"                                         AS closest_well_xy_ft,
    ws."WellsInRadius"                                         AS wells_in_radius,
    ws."ClosestTwoAvgXY"                                       AS closest_two_avg_xy_ft,
    ws."IsChild"                                               AS is_child,
    ws."ParentCount"                                           AS parent_count,
    ws."BoundednessScore"                                      AS boundedness_score,

    -- =========================================================================
    -- STATUS & FLAGS
    -- =========================================================================
    COALESCE(wd."WellStatus", n."WellStatus", e.envwellstatus) AS well_status,
    COALESCE(wd."WellType", n."WellType", e.envwelltype)       AS well_type,
    COALESCE(wd."HasProductionSharing",
             n."HasProductionSharing")                         AS has_production_sharing,
    n."IsSyntheticApi"                                         AS novi_synthetic_api

FROM raw_novi."Wells" n
LEFT JOIN raw_novi."WellDetails" wd
       ON wd."API10" = n."API10"
      AND wd."DeletedAt" IS NULL
LEFT JOIN raw_novi."WellSpacing" ws
       ON ws."API10" = n."API10"
      AND ws."DeletedAt" IS NULL
LEFT JOIN enverus_latest e
       ON e.api10_join = n."API10"
WHERE n."DeletedAt" IS NULL
;


-- =============================================================================
-- Indexes
-- =============================================================================

-- Unique on api10 - required for CONCURRENTLY refresh
CREATE UNIQUE INDEX idx_curated_wells_api10
    ON curated.wells (api10);

-- Common filter columns
CREATE INDEX idx_curated_wells_county_code
    ON curated.wells (county_code);

CREATE INDEX idx_curated_wells_current_operator
    ON curated.wells (current_operator);

CREATE INDEX idx_curated_wells_formation
    ON curated.wells (formation);

CREATE INDEX idx_curated_wells_first_production_date
    ON curated.wells (first_production_date);

CREATE INDEX idx_curated_wells_basin_subbasin
    ON curated.wells (basin, subbasin);

-- Spatial index for map-overlay queries (ST_Intersects against viewport bbox).
-- NULL wellsticks are skipped by GIST natively.
CREATE INDEX idx_curated_wells_wellstick_geom
    ON curated.wells USING GIST (wellstick_geom);


-- =============================================================================
-- Column comments (visible in pgAdmin → Properties → Columns; survives
-- matview rebuilds because they're attached after CREATE.)
-- =============================================================================

COMMENT ON COLUMN curated.wells.directional_survey_is_planned IS
'TRUE = the directional survey is the operator''s pre-drill PLAN, not the actual post-drill survey. Both Novi and Enverus use planned surveys to assign Formation / ENVInterval via their proprietary structure models, which can mis-land the well. Self-corrects when the operator files the actual survey; NM regulators are notoriously slow, so NM wells often carry provisional formation assignments for an extended period.';

COMMENT ON COLUMN curated.wells.wellstick_geom IS
'LINESTRING (4326) built from the four Novi locations Surface Hole → Landing Point → Midpoint → Bottom Hole, in natural traverse order. NULL points are skipped; result is NULL if fewer than two valid points exist. Replaces what Enverus LateralLine WKT provided in the legacy type-curve app.';

COMMENT ON COLUMN curated.wells.range_ IS
'PLSS Range (NM-style land subdivision). Trailing underscore avoids the contextually-reserved SQL keyword. Populated only for PLSS states; ~0% in TX, ~20% Permian-wide.';


-- =============================================================================
-- Update the refresh function to actually do something now
-- =============================================================================

CREATE OR REPLACE FUNCTION curated.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.wells;
    RAISE NOTICE 'curated.refresh_all() complete: curated.wells refreshed';
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- DONE.
-- Next steps:
--   1. Apply this file: psql -d oilgas -f sql/04_curated.sql
--   2. Verify row count: SELECT COUNT(*) FROM curated.wells;  -- expect ~90k
--   3. Sanity-check the join: how many rows have an Enverus match?
--      SELECT COUNT(*) FROM curated.wells WHERE api14 IS NOT NULL;
--   4. Build Phase 2: curated.production (api10 + year_month PK, Novi volumes)
-- =============================================================================
