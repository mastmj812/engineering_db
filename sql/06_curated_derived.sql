-- =============================================================================
-- Curated layer - Phase 3: derived analytical objects
--
-- Three new objects, in build order:
--
--   1. curated.wells_enriched (regular VIEW)
--      Cheap derived per-well columns over curated.wells:
--      - completion_vintage_bucket  ('pre-2017' / '2017-2019' / '2020-2022' / '2023+')
--      - lateral_length_class       ('<5000' / '5000-7499' / ...)
--      - is_horizontal              (bool from SlantCalculated / enverus trajectory)
--      - first_completion_year      (int)
--      - stages_per_1000ft, proppant_lbs_per_stage, fluid_bbl_per_stage
--      - has_completion_intensity   (bool: are key intensity cols all populated?)
--      Regular view; stays in sync with curated.wells automatically (no refresh).
--
--   2. curated.production_normalized (MATERIALIZED VIEW)
--      curated.production INNER JOIN curated.wells, adds per-1000-ft normalized
--      rates (oil/gas/water/boe, current and cumulative), boe synthetic
--      (oil + gas/6), and cohort keys (state_code, county_code, formation,
--      completion_vintage_bucket, completion_year, lateral_length_ft).
--      Used by type-curve apps that want one well's full normalized history.
--
--   3. curated.type_curve_cohorts (MATERIALIZED VIEW)
--      Aggregation over production_normalized. One row per
--      (state_code, county_code, formation, completion_vintage_bucket,
--       months_on_production) with P10/P25/P50/P75/P90 of per-1000-ft rates,
--      plus well_count and well_months. Capped at MoP 1-240 (20 years; past
--      that, cohort samples are too sparse for fitting).
--
-- Refresh order (encoded in updated curated.refresh_all()):
--    wells → production → production_normalized → type_curve_cohorts.
-- production_normalized depends on wells + production being current; cohorts
-- depend on production_normalized being current. All refreshes use
-- CONCURRENTLY (each matview has a UNIQUE index to support it).
--
-- Scope reminder: Permian-wide. Downstream apps filter at query time.
--
-- No economic-limit math anywhere. EUR is not computed here; the type-curve
-- app does the 50-yr integral on the rate-P50 curve.
--
-- Run order: apply after sql/04, sql/05.
--   psql -d oilgas -f sql/06_curated_derived.sql
-- =============================================================================


-- =============================================================================
-- 1. curated.wells_enriched
-- =============================================================================

DROP VIEW IF EXISTS curated.wells_enriched CASCADE;


CREATE VIEW curated.wells_enriched AS
SELECT
    w.*,

    -- ------------------------------------------------------------------
    -- Blue Ox standardized formation (curated.formation_blueox, sql/16), with
    -- the TVD-sanity correction (curated.formation_blueox_tvd, sql/23) applied
    -- ON TOP: for the ~0.4% of producing horizontals whose tag is a gross depth
    -- outlier (e.g. an Enverus-substitution mis-tag — Wolfcamp landed in the
    -- "2nd Bone Spring" band), formation_blueox becomes the depth-nearest bench
    -- and the source becomes 'tvd_corrected'. The pre-correction value is kept as
    -- formation_blueox_base for audit; non-producing wells and non-flips pass the
    -- base through unchanged. Joined here (not baked into curated.wells) so the
    -- whole mapping re-derives with a cheap REFRESH, not a DROP-CASCADE rebuild.
    -- ------------------------------------------------------------------
    CASE WHEN fbt.corrected THEN fbt.corrected_code
         ELSE fb.formation_blueox END               AS formation_blueox,
    fb.formation_blueox                             AS formation_blueox_base,
    fb.formation_blueox_raw,
    CASE WHEN fbt.corrected THEN 'tvd_corrected'
         ELSE fb.formation_blueox_source END        AS formation_blueox_source,
    fb.basin_blueox,
    fb.formation_blueox_is_mapped,
    COALESCE(fbt.corrected, FALSE)                  AS formation_blueox_tvd_corrected,

    -- ------------------------------------------------------------------
    -- Vintage
    -- ------------------------------------------------------------------
    EXTRACT(YEAR FROM w.first_completion_date)::int    AS first_completion_year,
    EXTRACT(QUARTER FROM w.first_completion_date)::int AS first_completion_quarter,
    EXTRACT(YEAR FROM w.first_production_date)::int    AS first_production_year,
    CASE
        WHEN w.first_completion_date IS NULL              THEN NULL
        WHEN w.first_completion_date <  DATE '2017-01-01' THEN 'pre-2017'
        WHEN w.first_completion_date <  DATE '2020-01-01' THEN '2017-2019'
        WHEN w.first_completion_date <  DATE '2023-01-01' THEN '2020-2022'
        ELSE                                                   '2023+'
    END                                                AS completion_vintage_bucket,

    -- ------------------------------------------------------------------
    -- Lateral length classification
    -- ------------------------------------------------------------------
    CASE
        WHEN w.lateral_length_ft IS NULL OR w.lateral_length_ft <= 0 THEN NULL
        WHEN w.lateral_length_ft <  5000                             THEN '<5000'
        WHEN w.lateral_length_ft <  7500                             THEN '5000-7499'
        WHEN w.lateral_length_ft < 10000                             THEN '7500-9999'
        WHEN w.lateral_length_ft < 15000                             THEN '10000-14999'
        ELSE                                                              '15000+'
    END                                                AS lateral_length_class,

    -- ------------------------------------------------------------------
    -- Horizontal flag (Novi SlantCalculated preferred; Enverus trajectory
    -- fallback). Both encode horizontal as a string starting with 'H'.
    -- ------------------------------------------------------------------
    CASE
        WHEN COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE 'H%' THEN TRUE
        WHEN COALESCE(w.novi_slant_calculated, w.enverus_trajectory) IS NULL    THEN NULL
        ELSE FALSE
    END                                                AS is_horizontal,

    -- ------------------------------------------------------------------
    -- Per-stage / per-1000-ft completion intensity
    -- (curated.wells already exposes proppant_lbs_per_ft and fluid_bbl_per_ft
    --  from Enverus; these complement those with stage-frequency views.)
    -- ------------------------------------------------------------------
    CASE
        WHEN w.lateral_length_ft IS NULL OR w.lateral_length_ft <= 0
          OR w.frac_stages IS NULL OR w.frac_stages <= 0
        THEN NULL
        ELSE (w.frac_stages::numeric * 1000.0 / w.lateral_length_ft)
    END                                                AS stages_per_1000ft,
    CASE
        WHEN w.frac_stages IS NULL OR w.frac_stages <= 0 THEN NULL
        ELSE (w.proppant_lbs::numeric / w.frac_stages)
    END                                                AS proppant_lbs_per_stage,
    CASE
        WHEN w.frac_stages IS NULL OR w.frac_stages <= 0 THEN NULL
        ELSE (w.fluid_bbl::numeric / w.frac_stages)
    END                                                AS fluid_bbl_per_stage,

    -- ------------------------------------------------------------------
    -- Completion-intensity completeness flag — useful for type-curve cohort
    -- filtering ("only include wells with reported completion intensity").
    -- ------------------------------------------------------------------
    (w.proppant_lbs IS NOT NULL
       AND w.fluid_bbl IS NOT NULL
       AND w.frac_stages IS NOT NULL
       AND w.lateral_length_ft IS NOT NULL
       AND w.lateral_length_ft > 0)                    AS has_completion_intensity

FROM curated.wells w
LEFT JOIN curated.formation_blueox fb
       ON fb.api10 = w.api10
LEFT JOIN curated.formation_blueox_tvd fbt
       ON fbt.api10 = w.api10;


COMMENT ON VIEW curated.wells_enriched IS
'curated.wells + per-well derived columns (vintage bucket, lateral length class, is_horizontal, per-stage intensity). Regular view; auto-syncs with wells.';


-- =============================================================================
-- 2. curated.production_normalized
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS curated.production_normalized CASCADE;


CREATE MATERIALIZED VIEW curated.production_normalized AS
SELECT
    -- ------------------------------------------------------------------
    -- Keys
    -- ------------------------------------------------------------------
    p.api10,
    p.prod_year,
    p.prod_month,
    p.prod_date,
    p.months_on_production,
    p.producing_days,

    -- ------------------------------------------------------------------
    -- Raw rates (pass-through from curated.production)
    -- ------------------------------------------------------------------
    p.oil_per_day_bbl,
    p.gas_per_day_mcf,
    p.water_per_day_bbl,
    p.oil_per_month_bbl,
    p.gas_per_month_mcf,
    p.water_per_month_bbl,
    p.cumulative_oil_bbl,
    p.cumulative_gas_mcf,
    p.cumulative_water_bbl,

    -- ------------------------------------------------------------------
    -- Synthetic BOE (oil + gas/6, industry-standard; water excluded)
    -- ------------------------------------------------------------------
    (p.oil_per_day_bbl + p.gas_per_day_mcf / 6.0)        AS boe_per_day_bbl,
    (p.oil_per_month_bbl + p.gas_per_month_mcf / 6.0)    AS boe_per_month_bbl,
    (p.cumulative_oil_bbl + p.cumulative_gas_mcf / 6.0)  AS cumulative_boe_bbl,

    -- ------------------------------------------------------------------
    -- Per-1000-ft normalized rates (NULL when lateral_length_ft is missing
    -- or non-positive)
    -- ------------------------------------------------------------------
    CASE WHEN w.lateral_length_ft > 0
         THEN p.oil_per_day_bbl * 1000.0 / w.lateral_length_ft
    END                                                  AS oil_per_day_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN p.gas_per_day_mcf * 1000.0 / w.lateral_length_ft
    END                                                  AS gas_per_day_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN p.water_per_day_bbl * 1000.0 / w.lateral_length_ft
    END                                                  AS water_per_day_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN (p.oil_per_day_bbl + p.gas_per_day_mcf / 6.0) * 1000.0
              / w.lateral_length_ft
    END                                                  AS boe_per_day_per_1000ft,

    CASE WHEN w.lateral_length_ft > 0
         THEN p.cumulative_oil_bbl * 1000.0 / w.lateral_length_ft
    END                                                  AS cumulative_oil_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN p.cumulative_gas_mcf * 1000.0 / w.lateral_length_ft
    END                                                  AS cumulative_gas_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN p.cumulative_water_bbl * 1000.0 / w.lateral_length_ft
    END                                                  AS cumulative_water_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN (p.cumulative_oil_bbl + p.cumulative_gas_mcf / 6.0) * 1000.0
              / w.lateral_length_ft
    END                                                  AS cumulative_boe_per_1000ft,

    -- ------------------------------------------------------------------
    -- Cohort keys (carried from curated.wells so aggregations don't re-JOIN)
    -- ------------------------------------------------------------------
    w.state_code,
    w.county_code,
    w.county,
    w.basin,
    w.subbasin,
    w.formation,
    w.lateral_length_ft,
    w.first_production_date,
    w.first_completion_date,
    EXTRACT(YEAR FROM w.first_completion_date)::int      AS first_completion_year,
    CASE
        WHEN w.first_completion_date IS NULL              THEN NULL
        WHEN w.first_completion_date <  DATE '2017-01-01' THEN 'pre-2017'
        WHEN w.first_completion_date <  DATE '2020-01-01' THEN '2017-2019'
        WHEN w.first_completion_date <  DATE '2023-01-01' THEN '2020-2022'
        ELSE                                                   '2023+'
    END                                                  AS completion_vintage_bucket,
    CASE
        WHEN w.lateral_length_ft IS NULL OR w.lateral_length_ft <= 0 THEN NULL
        WHEN w.lateral_length_ft <  5000                             THEN '<5000'
        WHEN w.lateral_length_ft <  7500                             THEN '5000-7499'
        WHEN w.lateral_length_ft < 10000                             THEN '7500-9999'
        WHEN w.lateral_length_ft < 15000                             THEN '10000-14999'
        ELSE                                                              '15000+'
    END                                                  AS lateral_length_class

FROM curated.production p
JOIN curated.wells w
  ON w.api10 = p.api10
WHERE p.months_on_production IS NOT NULL
  AND p.months_on_production BETWEEN 1 AND 600
;


COMMENT ON MATERIALIZED VIEW curated.production_normalized IS
'curated.production INNER JOIN curated.wells with per-1000-ft normalized rates and cohort keys. PK (api10, prod_year, prod_month). MoP capped at 1-600.';


-- ------------------------------------------------------------------
-- production_normalized indexes
-- ------------------------------------------------------------------

CREATE UNIQUE INDEX idx_curated_pn_pk
    ON curated.production_normalized (api10, prod_year, prod_month);

CREATE INDEX idx_curated_pn_api10_mop
    ON curated.production_normalized (api10, months_on_production);

CREATE INDEX idx_curated_pn_cohort_mop
    ON curated.production_normalized
       (county_code, formation, completion_vintage_bucket, months_on_production);

CREATE INDEX idx_curated_pn_formation
    ON curated.production_normalized (formation);

CREATE INDEX idx_curated_pn_vintage
    ON curated.production_normalized (completion_vintage_bucket);


-- =============================================================================
-- 3. curated.type_curve_cohorts
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS curated.type_curve_cohorts CASCADE;


CREATE MATERIALIZED VIEW curated.type_curve_cohorts AS
SELECT
    -- ------------------------------------------------------------------
    -- Cohort key
    -- ------------------------------------------------------------------
    state_code,
    county_code,
    formation,
    completion_vintage_bucket,
    months_on_production,

    -- ------------------------------------------------------------------
    -- Sample size (apps should filter on well_count for statistical floor)
    -- ------------------------------------------------------------------
    COUNT(*)                                                          AS well_months,
    COUNT(DISTINCT api10)                                             AS well_count,

    -- ------------------------------------------------------------------
    -- Oil per-1000-ft percentiles (the primary type-curve series)
    -- ------------------------------------------------------------------
    percentile_cont(0.10) WITHIN GROUP (ORDER BY oil_per_day_per_1000ft) AS p10_oil_per_day_per_1000ft,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY oil_per_day_per_1000ft) AS p25_oil_per_day_per_1000ft,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY oil_per_day_per_1000ft) AS p50_oil_per_day_per_1000ft,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY oil_per_day_per_1000ft) AS p75_oil_per_day_per_1000ft,
    percentile_cont(0.90) WITHIN GROUP (ORDER BY oil_per_day_per_1000ft) AS p90_oil_per_day_per_1000ft,
    AVG(oil_per_day_per_1000ft)                                          AS mean_oil_per_day_per_1000ft,

    -- ------------------------------------------------------------------
    -- BOE per-1000-ft percentiles (secondary, for gas-weighted cohorts)
    -- ------------------------------------------------------------------
    percentile_cont(0.10) WITHIN GROUP (ORDER BY boe_per_day_per_1000ft) AS p10_boe_per_day_per_1000ft,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY boe_per_day_per_1000ft) AS p25_boe_per_day_per_1000ft,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY boe_per_day_per_1000ft) AS p50_boe_per_day_per_1000ft,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY boe_per_day_per_1000ft) AS p75_boe_per_day_per_1000ft,
    percentile_cont(0.90) WITHIN GROUP (ORDER BY boe_per_day_per_1000ft) AS p90_boe_per_day_per_1000ft,
    AVG(boe_per_day_per_1000ft)                                          AS mean_boe_per_day_per_1000ft,

    -- ------------------------------------------------------------------
    -- Gas + water medians only (full percentile suite would bloat the
    -- matview; apps that need P10/P90 can compute on the fly from
    -- production_normalized.)
    -- ------------------------------------------------------------------
    percentile_cont(0.50) WITHIN GROUP (ORDER BY gas_per_day_per_1000ft)    AS p50_gas_per_day_per_1000ft,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY water_per_day_per_1000ft)  AS p50_water_per_day_per_1000ft,

    -- ------------------------------------------------------------------
    -- Cumulative medians — useful for cohort EUR sanity checks (still no
    -- economics; raw integral only).
    -- ------------------------------------------------------------------
    percentile_cont(0.50) WITHIN GROUP (ORDER BY cumulative_oil_per_1000ft) AS p50_cum_oil_per_1000ft,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY cumulative_boe_per_1000ft) AS p50_cum_boe_per_1000ft

FROM curated.production_normalized
WHERE months_on_production BETWEEN 1 AND 240
  AND formation IS NOT NULL
  AND county_code IS NOT NULL
  AND completion_vintage_bucket IS NOT NULL
  AND oil_per_day_per_1000ft IS NOT NULL          -- requires lateral_length_ft > 0
GROUP BY
    state_code,
    county_code,
    formation,
    completion_vintage_bucket,
    months_on_production
;


COMMENT ON MATERIALIZED VIEW curated.type_curve_cohorts IS
'Per-1000-ft rate percentiles by (state, county, formation, vintage bucket) x MoP 1-240. Pre-computed type-curve cohorts. Apps should filter on well_count for sample-size floor.';


-- ------------------------------------------------------------------
-- type_curve_cohorts indexes
-- ------------------------------------------------------------------

CREATE UNIQUE INDEX idx_curated_tcc_pk
    ON curated.type_curve_cohorts
       (state_code, county_code, formation, completion_vintage_bucket, months_on_production);

CREATE INDEX idx_curated_tcc_formation_vintage
    ON curated.type_curve_cohorts (formation, completion_vintage_bucket);

CREATE INDEX idx_curated_tcc_county_formation
    ON curated.type_curve_cohorts (county_code, formation);


-- =============================================================================
-- Update curated.refresh_all() to include the new objects.
-- Refresh order encodes dependency: production_normalized depends on
-- (wells, production); type_curve_cohorts depends on production_normalized.
-- wells_enriched is a regular view — no refresh — but erebor_locations (sql/22)
-- materializes over it, so it refreshes LAST (after every matview it reads).
-- =============================================================================

CREATE OR REPLACE FUNCTION curated.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.wells;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.formation_blueox;
    -- producing_reference + formation_blueox_tvd feed the wells_enriched view's
    -- corrected formation_blueox, so they refresh with the base mapping.
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.producing_reference;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.formation_blueox_tvd;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production_normalized;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.type_curve_cohorts;
    -- erebor display spine (sql/22). Its PDP arm reads wells_enriched (over the
    -- matviews just refreshed above), so it must come LAST. CONCURRENTLY keeps
    -- the erebor app readable during the refresh. The Novi PUD/RES arm only moves
    -- on the quarterly reload (which recreates this matview), so nightly this just
    -- folds in newly-online producers. Guard so a missing matview (mid-quarterly
    -- rebuild) degrades to a notice instead of failing the whole nightly run.
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY curated.erebor_locations;
    EXCEPTION WHEN undefined_table THEN
        RAISE NOTICE 'curated.erebor_locations absent (mid-rebuild?) - skipped';
    END;
    RAISE NOTICE 'curated.refresh_all() complete: wells, formation_blueox, producing_reference, formation_blueox_tvd, production, production_normalized, type_curve_cohorts, erebor_locations refreshed';
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- DONE.
-- Next steps:
--   1. Apply: psql -d oilgas -f sql/06_curated_derived.sql
--      First build of production_normalized: ~30-90s (5M-row JOIN).
--      First build of type_curve_cohorts:    ~30-60s (percentile aggregation).
--
--   2. Sanity-check row counts:
--      SELECT COUNT(*) FROM curated.wells_enriched;        -- = curated.wells (~90,816)
--      SELECT COUNT(*) FROM curated.production_normalized; -- <= curated.production
--      SELECT COUNT(*) FROM curated.type_curve_cohorts;    -- thousands
--
--   3. Spot-check one cohort against a known curve. Reeves Wolfcamp 2020-2022
--      should show a sharp peak around MoP 1-3 then exponential decline:
--        SELECT months_on_production,
--               well_count,
--               p50_oil_per_day_per_1000ft
--          FROM curated.type_curve_cohorts
--         WHERE county_code = '48389'
--           AND formation ILIKE 'WOLFCAMP%'
--           AND completion_vintage_bucket = '2020-2022'
--           AND well_count >= 10
--         ORDER BY months_on_production
--         LIMIT 36;
-- =============================================================================
