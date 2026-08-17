-- =============================================================================
-- 41 — curated.water_data_quality  (per-well water-stream provenance:
--      measured vs vendor-calculated water)
--
-- PROBLEM. Texas RRC does not collect monthly well-level water; vendors
-- backfill it as a static WOR from an initial operator filing, so reported
-- water is often literally water = k * oil every month. New Mexico (C-115)
-- reports real well-level water. Novi's operator-production-share wells carry
-- real measured water regardless of state, flagged per-month by
-- production.is_water_proprietary. A water type curve built over calculated
-- wells inherits the frozen filing WOR: measured-vs-calculated medians
-- (2026-08-17 analysis, horizontals FP>=2019, mop 1-24) put the calculated
-- Midland WOR 15-47% ABOVE measured mid-life (2.40 flat vs 1.63-2.11), while
-- the real WOR's late-life rise means calculated tails run LOW. Delaware level
-- bias is small (~4% at mop 12) but the shape distortion is universal.
--
-- EVIDENCE for the classification (same analysis): share of wells with
-- dead-flat WOR (CV < 2% over mop 1-24): TX public 83.6%, TX proprietary
-- 0.1%, NM public 0.0%, NM proprietary 0.0%. The proprietary flag and the
-- flatness signature agree almost perfectly, so both are used as signals.
--
-- CLASSIFICATION (convention of record, Michael 2026-08-17; surfacing is
-- FLAG-ONLY — apps badge/filter, nothing is excluded by default):
--   insufficient  n_wor_months < 6 (not enough oil>0 & water>0 months in
--                 mop 1-24 to judge)
--   measured      water_prop_share >= 0.9 (operator share)  OR  wor_cv >= 0.15
--                 (real month-to-month variance)
--   calculated    water_prop_share <= 0.1 AND wor_cv < 0.05 (public + flat)
--   indeterminate everything between the bands
-- KNOWN LIMIT (v1, accepted): a re-filed WOR produces a piecewise-flat series
-- whose CV can exceed the bands — such wells land indeterminate (or measured
-- when the step is large). Report thinness, don't over-claim.
--
-- GRAIN: one row per distinct api10 in curated.production (row-count identity
-- for verification). Stats window is mop 1-24 with oil>0 AND water>0 — the
-- early life a type-curve fit actually consumes. No state column here on
-- purpose: provenance derives from the data itself; join wells_enriched for
-- state/subbasin.
--
-- DEPENDS ON: curated.production (nightly).
-- REFRESH: nightly via etl/db.py:_CURATED_MATVIEWS (after production).
--          Aggregate-only, no PostGIS, cheap (~wells grain).
-- RUN:     python -m scripts.apply_water_data_quality
-- SANITY:  count(*) == count(DISTINCT api10) FROM curated.production;
--          TX 'calculated' share of classifiable wells ~0.8 (2026-08-17);
--          NM 'calculated' share ~0.
-- =============================================================================

-- Type-aware drop (IF EXISTS does not suppress wrong-relkind errors).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'curated' AND c.relname = 'water_data_quality'
          AND c.relkind = 'v'
    ) THEN
        DROP VIEW curated.water_data_quality CASCADE;
    END IF;
END $$;

DROP MATERIALIZED VIEW IF EXISTS curated.water_data_quality CASCADE;

CREATE MATERIALIZED VIEW curated.water_data_quality AS
WITH stats AS (
    SELECT
        p.api10,
        COUNT(*)                                            AS n_prod_months,
        COUNT(*)                    FILTER (WHERE p.ok)     AS n_wor_months,
        AVG(p.water_prop::int)      FILTER (WHERE p.ok)     AS water_prop_share,
        AVG(p.wor)                  FILTER (WHERE p.ok)     AS wor_mean,
        STDDEV_SAMP(p.wor)          FILTER (WHERE p.ok)     AS wor_sd,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.wor)
                                    FILTER (WHERE p.ok)     AS wor_median
    FROM (
        SELECT
            api10,
            COALESCE(is_water_proprietary, FALSE) AS water_prop,
            water_per_month_bbl::double precision
                / NULLIF(oil_per_month_bbl, 0)    AS wor,
            (months_on_production BETWEEN 1 AND 24
             AND oil_per_month_bbl   > 0
             AND water_per_month_bbl > 0)         AS ok
        FROM curated.production
    ) p
    GROUP BY p.api10
)
SELECT
    s.api10,
    s.n_prod_months,
    s.n_wor_months,
    s.water_prop_share,
    s.wor_mean,
    s.wor_median,
    s.wor_sd / NULLIF(s.wor_mean, 0) AS wor_cv,
    CASE
        WHEN s.n_wor_months < 6                          THEN 'insufficient'
        WHEN s.water_prop_share >= 0.9                   THEN 'measured'
        WHEN s.water_prop_share <= 0.1
             AND s.wor_sd / NULLIF(s.wor_mean, 0) < 0.05 THEN 'calculated'
        WHEN s.wor_sd / NULLIF(s.wor_mean, 0) >= 0.15    THEN 'measured'
        ELSE 'indeterminate'
    END AS water_source
FROM stats s;

CREATE UNIQUE INDEX uq_water_data_quality_api10
    ON curated.water_data_quality (api10);

-- Comments here AND in sql/31 (part E) so either file restores the catalog
-- entries after a rebuild (sql/39 precedent).
COMMENT ON MATERIALIZED VIEW curated.water_data_quality IS
'Per-well water-stream provenance: measured vs vendor-calculated water, one row per api10 in curated.production. TX RRC has no monthly well-level water -- vendors backfill a static WOR from an initial filing (water = k*oil; 83.6% of TX public-water horizontals FP>=2019 have WOR CV < 2% over mop 1-24), while operator-share months (production.is_water_proprietary) and NM C-115 water are real. Signals: water_prop_share + wor_cv over mop 1-24 (oil>0 AND water>0 months). Labels: insufficient (<6 usable months) / measured (prop_share>=0.9 OR cv>=0.15) / calculated (prop_share<=0.1 AND cv<0.05) / indeterminate. Convention 2026-08-17: FLAG-ONLY surfacing -- apps badge and filter, nothing excluded by default. Piecewise-flat re-filed WORs can escape to indeterminate/measured (known v1 limit). No state column by design -- join wells_enriched. Nightly refresh after curated.production. sql/41.';
COMMENT ON COLUMN curated.water_data_quality.api10 IS
'10-digit API well key; one row per distinct api10 in curated.production. PK / unique index.';
COMMENT ON COLUMN curated.water_data_quality.n_prod_months IS
'All production months on file for the well (any mop, any volumes) — context only.';
COMMENT ON COLUMN curated.water_data_quality.n_wor_months IS
'Months usable for WOR stats: months_on_production 1-24 with oil>0 AND water>0. <6 => water_source=insufficient.';
COMMENT ON COLUMN curated.water_data_quality.water_prop_share IS
'Share of usable months flagged is_water_proprietary (Novi operator production share = real measured water). NULL when n_wor_months=0.';
COMMENT ON COLUMN curated.water_data_quality.wor_mean IS
'Mean monthly WOR (water_per_month_bbl / oil_per_month_bbl) over usable months, bbl/bbl.';
COMMENT ON COLUMN curated.water_data_quality.wor_median IS
'Median monthly WOR over usable months, bbl/bbl.';
COMMENT ON COLUMN curated.water_data_quality.wor_cv IS
'Coefficient of variation of monthly WOR (stddev/mean) over usable months. ~0 = water is a fixed multiple of oil (vendor-calculated); measured water runs ~0.4-0.5.';
COMMENT ON COLUMN curated.water_data_quality.water_source IS
'Classification of record (2026-08-17): insufficient | measured | calculated | indeterminate. Flag-only convention -- consumers badge/filter, never auto-exclude.';
