-- =============================================================================
-- Curated layer - Phase 2: curated.production
--
-- Materialized view over Novi's WellMonths. Novi-only by design (see the
-- engineering_db memory for source-of-truth policy). Enverus volumes
-- could be joined in a Phase 2b later if cross-source debugging is ever
-- needed.
--
-- Primary key: (api10, prod_year, prod_month). The Novi PDF documents
-- this same three-column key on WellMonths; we preserve it for clean
-- joins back to curated.wells (on api10) and for type-curve analytical
-- queries that group/window by month.
--
-- Row count is approximately raw_novi."WellMonths" minus soft-deletes
-- (~5M rows). Concurrent refresh expected to take 30-60s.
--
-- Run order: apply after sql/04_curated.sql.
--   psql -d oilgas -f sql/05_curated_production.sql
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.production CASCADE;


CREATE MATERIALIZED VIEW curated.production AS
SELECT
    -- =========================================================================
    -- IDENTIFIERS / KEYS
    -- =========================================================================
    wm."API10"                          AS api10,
    wm."Year"                           AS prod_year,
    wm."Month"                          AS prod_month,
    wm."Date"                           AS prod_date,         -- 1st day of month

    -- =========================================================================
    -- OPERATOR (Novi tracks per-month, so a well's operator can change
    -- mid-history when it gets sold)
    -- =========================================================================
    wm."Operator"                       AS operator,
    wm."OperatorEntity"                 AS operator_entity,

    -- =========================================================================
    -- TIME-ON-PRODUCTION (critical for type-curve alignment)
    -- =========================================================================
    wm."MonthsOnProduction"             AS months_on_production,
    wm."ProducingDays"                  AS producing_days,
    wm."CumulativeProducingDays"        AS cumulative_producing_days,

    -- =========================================================================
    -- OIL VOLUMES
    -- =========================================================================
    wm."OilPerDay"                      AS oil_per_day_bbl,   -- calendar-day rate
    wm."OilPerMonth"                    AS oil_per_month_bbl,
    wm."CumulativeOil"                  AS cumulative_oil_bbl,

    -- =========================================================================
    -- GAS VOLUMES
    -- =========================================================================
    wm."GasPerDay"                      AS gas_per_day_mcf,   -- calendar-day rate
    wm."GasPerMonth"                    AS gas_per_month_mcf,
    wm."CumulativeGas"                  AS cumulative_gas_mcf,

    -- =========================================================================
    -- WATER VOLUMES
    -- =========================================================================
    wm."WaterPerDay"                    AS water_per_day_bbl, -- calendar-day rate
    wm."WaterPerMonth"                  AS water_per_month_bbl,
    wm."CumulativeWater"                AS cumulative_water_bbl,

    -- =========================================================================
    -- FLARED GAS
    -- =========================================================================
    wm."FlaredGasPerDay"                AS flared_gas_per_day_mcf,
    wm."FlaredGasPerMonth"              AS flared_gas_per_month_mcf,
    wm."CumulativeFlaredGas"            AS cumulative_flared_gas_mcf,

    -- =========================================================================
    -- BASIN CONTEXT (from WellMonths itself; not strictly needed since
    -- curated.wells has it too, but cheap to surface for filter-without-join)
    -- =========================================================================
    wm."Basin"                          AS basin,
    wm."Subbasin"                       AS subbasin,

    -- =========================================================================
    -- PROVENANCE FLAGS (Novi tells us when each volume came from a proprietary
    -- production-sharing source vs state filings)
    -- =========================================================================
    wm."IsOilFromProductionSharing"     AS is_oil_proprietary,
    wm."IsGasFromProductionSharing"     AS is_gas_proprietary,
    wm."IsGasFlaredFromProductionSharing" AS is_gas_flared_proprietary,
    wm."IsWaterFromProductionSharing"   AS is_water_proprietary

FROM raw_novi."WellMonths" wm
WHERE wm."DeletedAt" IS NULL
;


-- =============================================================================
-- Indexes
-- =============================================================================

-- Unique composite PK - required for CONCURRENTLY refresh
CREATE UNIQUE INDEX idx_curated_production_pk
    ON curated.production (api10, prod_year, prod_month);

-- Per-well queries (most common pattern: pull one well's full history)
CREATE INDEX idx_curated_production_api10
    ON curated.production (api10);

-- Time-range queries across the universe (e.g. monthly Permian totals)
CREATE INDEX idx_curated_production_prod_date
    ON curated.production (prod_date);

-- Months-on-production analysis (THE key index for type-curve work — wells
-- align by MoP not calendar date)
CREATE INDEX idx_curated_production_api10_mop
    ON curated.production (api10, months_on_production);


-- =============================================================================
-- Update the refresh function to include both materialized views
-- =============================================================================

CREATE OR REPLACE FUNCTION curated.refresh_all()
RETURNS void AS $$
BEGIN
    -- Wells refreshes first; production may want to JOIN against it during
    -- some user queries while production itself is mid-refresh, and the
    -- non-blocking CONCURRENTLY behavior means the previous snapshot stays
    -- readable until the new one is ready.
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.wells;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production;
    RAISE NOTICE 'curated.refresh_all() complete: wells + production refreshed';
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- DONE.
-- Next steps:
--   1. Apply this file: psql -d oilgas -f sql/05_curated_production.sql
--      (CREATE MATERIALIZED VIEW will take 30-60s on first build)
--   2. Verify row count: SELECT COUNT(*) FROM curated.production;
--      Expected: ~4,984,092 (matches raw_novi."WellMonths" minus soft-deletes)
--   3. Test the type-curve-style query pattern:
--      SELECT months_on_production,
--             percentile_cont(0.5) WITHIN GROUP (ORDER BY oil_per_day_bbl)
--               AS p50_oil_bblpd
--        FROM curated.production
--        WHERE api10 IN (<some cohort>)
--          AND months_on_production BETWEEN 1 AND 60
--        GROUP BY months_on_production
--        ORDER BY months_on_production;
-- =============================================================================
