-- =============================================================================
-- 10 — Curated forecast layer: production_forecast + production_combined
--
-- Surfaces Novi's ForecastWellMonths (already loaded into raw_novi, ~22M rows)
-- in the curated layer, WITHOUT duplicating or degrading the actuals we
-- already hold in curated.production_normalized. Two new objects:
--
--   1. curated.production_forecast  (MATERIALIZED VIEW)
--      Novi's projected tail only (IsForecasted = TRUE), INNER JOINed to
--      curated.wells, normalized per-1000-ft. Column-for-column identical in
--      name AND type to curated.production_normalized (verified against the
--      live catalog) so the two can be UNION'd cleanly. This is the only new
--      storage (~17M rows — the forecast tail; the ~5M actuals are NOT copied).
--
--   2. curated.production_combined  (regular VIEW)
--      production_normalized (actuals) UNION ALL production_forecast (forecast)
--      with an is_forecast flag, presenting one continuous per-well timeline.
--      Being a VIEW it adds no storage and is always fresh. Point Spotfire /
--      ad-hoc per-well review at this object: `WHERE api10 = '...'` returns a
--      well's actuals then Novi's projection as a single seamless series, and
--      both underlying matviews are indexed on api10 so it's fast.
--
-- Why actuals come from production_normalized (WellMonths) and NOT from
-- ForecastWellMonths' own IsForecasted=FALSE rows: ForecastWellMonths is a
-- thinner table (integer-truncated monthly/cumulative volumes; no
-- producing_days / operator / flared / provenance). Sourcing actuals from the
-- authoritative WellMonths-derived matview keeps one source of truth and full
-- fidelity; the seam to the forecast tail is clean because per well the MoP
-- ranges are disjoint and contiguous.
--
-- CAVEAT (analytical, not a bug): forecast rows begin the month AFTER each
-- well's last actual, so at any given months_on_production the forecast
-- population differs from the actuals population (and is sparse at low MoP).
-- Fine for per-well charts; mind it before treating forecast vs actual cohort
-- curves as apples-to-apples.
--
-- Run order: after sql/04 → 05 → 06. From the project root:
--   psql -h localhost -U postgres -d oilgas --single-transaction -f sql/10_curated_forecast.sql
-- Transaction-safe: no CONCURRENTLY or \ir at top level; all REFRESH
-- statements live inside the refresh_all() function body.
--
-- NOTE on refresh_all(): this file redefines curated.refresh_all() to add the
-- production_forecast refresh. sql/06 also defines refresh_all() (without it),
-- so if you ever re-run the 04→05→06 rebuild chain (e.g. sql/07 / sql/08),
-- RE-RUN THIS FILE afterward to restore the forecast refresh.
-- =============================================================================


-- Drop in dependency order (view depends on the matview).
DROP VIEW IF EXISTS curated.production_combined;
DROP MATERIALIZED VIEW IF EXISTS curated.production_forecast CASCADE;


-- =============================================================================
-- 1. curated.production_forecast  — Novi projection tail, normalized
-- =============================================================================

CREATE MATERIALIZED VIEW curated.production_forecast AS
SELECT
    -- ------------------------------------------------------------------
    -- Keys (ForecastWellMonths has only Date; derive year/month to match
    -- production_normalized. producing_days has no forecast analog -> NULL.)
    -- ------------------------------------------------------------------
    f."API10"::varchar(32)                               AS api10,
    EXTRACT(YEAR  FROM f."Date")::int                    AS prod_year,
    EXTRACT(MONTH FROM f."Date")::int                    AS prod_month,
    f."Date"                                             AS prod_date,
    f."MonthsOnProduction"::int                          AS months_on_production,
    NULL::int                                            AS producing_days,

    -- ------------------------------------------------------------------
    -- Raw rates (pass-through from ForecastWellMonths)
    -- ------------------------------------------------------------------
    f."OilPerDay"                                        AS oil_per_day_bbl,
    f."GasPerDay"                                        AS gas_per_day_mcf,
    f."WaterPerDay"                                       AS water_per_day_bbl,
    f."OilPerMonth"                                       AS oil_per_month_bbl,
    f."GasPerMonth"                                       AS gas_per_month_mcf,
    f."WaterPerMonth"                                     AS water_per_month_bbl,
    f."CumulativeOil"                                     AS cumulative_oil_bbl,
    f."CumulativeGas"                                     AS cumulative_gas_mcf,
    f."CumulativeWater"                                   AS cumulative_water_bbl,

    -- ------------------------------------------------------------------
    -- Synthetic BOE (oil + gas/6, industry standard; water excluded)
    -- ------------------------------------------------------------------
    (f."OilPerDay" + f."GasPerDay" / 6.0)                AS boe_per_day_bbl,
    (f."OilPerMonth" + f."GasPerMonth" / 6.0)            AS boe_per_month_bbl,
    (f."CumulativeOil" + f."CumulativeGas" / 6.0)        AS cumulative_boe_bbl,

    -- ------------------------------------------------------------------
    -- Per-1000-ft normalized rates (NULL when lateral_length_ft missing/<=0)
    -- ------------------------------------------------------------------
    CASE WHEN w.lateral_length_ft > 0
         THEN f."OilPerDay" * 1000.0 / w.lateral_length_ft
    END                                                  AS oil_per_day_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN f."GasPerDay" * 1000.0 / w.lateral_length_ft
    END                                                  AS gas_per_day_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN f."WaterPerDay" * 1000.0 / w.lateral_length_ft
    END                                                  AS water_per_day_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN (f."OilPerDay" + f."GasPerDay" / 6.0) * 1000.0 / w.lateral_length_ft
    END                                                  AS boe_per_day_per_1000ft,

    CASE WHEN w.lateral_length_ft > 0
         THEN f."CumulativeOil" * 1000.0 / w.lateral_length_ft
    END                                                  AS cumulative_oil_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN f."CumulativeGas" * 1000.0 / w.lateral_length_ft
    END                                                  AS cumulative_gas_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN f."CumulativeWater" * 1000.0 / w.lateral_length_ft
    END                                                  AS cumulative_water_per_1000ft,
    CASE WHEN w.lateral_length_ft > 0
         THEN (f."CumulativeOil" + f."CumulativeGas" / 6.0) * 1000.0 / w.lateral_length_ft
    END                                                  AS cumulative_boe_per_1000ft,

    -- ------------------------------------------------------------------
    -- Cohort keys (carried from curated.wells — identical derivation to
    -- production_normalized so the two align for any cohort comparison)
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

FROM raw_novi."ForecastWellMonths" f
JOIN curated.wells w
  ON w.api10 = f."API10"
WHERE f."IsForecasted" = TRUE
  AND f."DeletedAt" IS NULL
  AND f."MonthsOnProduction" BETWEEN 1 AND 600
;


COMMENT ON MATERIALIZED VIEW curated.production_forecast IS
'Novi ForecastWellMonths projection tail (IsForecasted=TRUE) JOINed to curated.wells, normalized per-1000-ft. Column-identical to curated.production_normalized. PK (api10, prod_year, prod_month). MoP capped 1-600. Forecast rows begin after each well''s last actual month.';


-- ------------------------------------------------------------------
-- production_forecast indexes (mirror production_normalized; UNIQUE PK
-- required for CONCURRENTLY refresh)
-- ------------------------------------------------------------------

CREATE UNIQUE INDEX idx_curated_pf_pk
    ON curated.production_forecast (api10, prod_year, prod_month);

CREATE INDEX idx_curated_pf_api10_mop
    ON curated.production_forecast (api10, months_on_production);

CREATE INDEX idx_curated_pf_cohort_mop
    ON curated.production_forecast
       (county_code, formation, completion_vintage_bucket, months_on_production);

CREATE INDEX idx_curated_pf_formation
    ON curated.production_forecast (formation);

CREATE INDEX idx_curated_pf_vintage
    ON curated.production_forecast (completion_vintage_bucket);


-- =============================================================================
-- 2. curated.production_combined  — actuals + forecast on one timeline
--
-- Explicit column lists (not SELECT *) so the UNION ALL contract is pinned:
-- if either matview's column order ever changes, this fails loudly instead of
-- silently misaligning. Both sides are column- and type-identical by design.
-- =============================================================================

CREATE VIEW curated.production_combined AS
SELECT
    pn.api10, pn.prod_year, pn.prod_month, pn.prod_date,
    pn.months_on_production, pn.producing_days,
    pn.oil_per_day_bbl, pn.gas_per_day_mcf, pn.water_per_day_bbl,
    pn.oil_per_month_bbl, pn.gas_per_month_mcf, pn.water_per_month_bbl,
    pn.cumulative_oil_bbl, pn.cumulative_gas_mcf, pn.cumulative_water_bbl,
    pn.boe_per_day_bbl, pn.boe_per_month_bbl, pn.cumulative_boe_bbl,
    pn.oil_per_day_per_1000ft, pn.gas_per_day_per_1000ft,
    pn.water_per_day_per_1000ft, pn.boe_per_day_per_1000ft,
    pn.cumulative_oil_per_1000ft, pn.cumulative_gas_per_1000ft,
    pn.cumulative_water_per_1000ft, pn.cumulative_boe_per_1000ft,
    pn.state_code, pn.county_code, pn.county, pn.basin, pn.subbasin, pn.formation,
    pn.lateral_length_ft, pn.first_production_date, pn.first_completion_date,
    pn.first_completion_year, pn.completion_vintage_bucket, pn.lateral_length_class,
    FALSE AS is_forecast
FROM curated.production_normalized pn
UNION ALL
SELECT
    pf.api10, pf.prod_year, pf.prod_month, pf.prod_date,
    pf.months_on_production, pf.producing_days,
    pf.oil_per_day_bbl, pf.gas_per_day_mcf, pf.water_per_day_bbl,
    pf.oil_per_month_bbl, pf.gas_per_month_mcf, pf.water_per_month_bbl,
    pf.cumulative_oil_bbl, pf.cumulative_gas_mcf, pf.cumulative_water_bbl,
    pf.boe_per_day_bbl, pf.boe_per_month_bbl, pf.cumulative_boe_bbl,
    pf.oil_per_day_per_1000ft, pf.gas_per_day_per_1000ft,
    pf.water_per_day_per_1000ft, pf.boe_per_day_per_1000ft,
    pf.cumulative_oil_per_1000ft, pf.cumulative_gas_per_1000ft,
    pf.cumulative_water_per_1000ft, pf.cumulative_boe_per_1000ft,
    pf.state_code, pf.county_code, pf.county, pf.basin, pf.subbasin, pf.formation,
    pf.lateral_length_ft, pf.first_production_date, pf.first_completion_date,
    pf.first_completion_year, pf.completion_vintage_bucket, pf.lateral_length_class,
    TRUE AS is_forecast
FROM curated.production_forecast pf;


COMMENT ON VIEW curated.production_combined IS
'Continuous per-well timeline: curated.production_normalized (actuals, is_forecast=FALSE) UNION ALL curated.production_forecast (Novi projection, is_forecast=TRUE). Regular view = no storage, always fresh. Query WHERE api10 = ... for a well''s actual-then-forecast series.';


-- =============================================================================
-- 3. Update curated.refresh_all() to also refresh production_forecast.
-- (Depends only on curated.wells, so it is safe anywhere after the wells
-- refresh. production_combined is a view and needs no refresh.)
-- =============================================================================

CREATE OR REPLACE FUNCTION curated.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.wells;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production_normalized;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.type_curve_cohorts;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production_forecast;
    RAISE NOTICE 'curated.refresh_all() complete: wells, production, production_normalized, type_curve_cohorts, production_forecast';
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- DONE.
-- Sanity checks (run interactively after applying):
--
--   -- Forecast rows materialized (expect millions):
--   SELECT COUNT(*) FROM curated.production_forecast;
--
--   -- Combined = actuals + forecast:
--   SELECT is_forecast, COUNT(*) FROM curated.production_combined GROUP BY is_forecast;
--
--   -- One well's seamless actual-then-forecast curve:
--   SELECT prod_date, months_on_production, is_forecast,
--          oil_per_day_bbl, oil_per_day_per_1000ft
--     FROM curated.production_combined
--    WHERE api10 = (SELECT api10 FROM curated.production_forecast LIMIT 1)
--    ORDER BY prod_date;
-- =============================================================================
