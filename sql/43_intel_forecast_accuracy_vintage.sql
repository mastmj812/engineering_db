-- =============================================================================
-- 43 — curated.intel_pdp_cliff_date(report_version, basin) +
--      curated.intel_forecast_accuracy_vintage
--      (Novi Intelligence forecast accuracy scored PER RETAINED VINTAGE)
--
-- WHY. sql/38 scores the LATEST loaded vintage through the curated intel views,
-- which (post the sql/29 latest-report filter) serve only the newest report per
-- basin family. A fresh vintage therefore has ~no blind-well population for
-- months (the 2026Q3 reload rebuilt sql/38 ~empty; usable ~Q1-2027). The
-- superseded raw slices are deliberately RETAINED in raw_intel for exactly this
-- reason: an old vintage keeps accruing out-of-sample actuals after it is
-- superseded. This matview reads raw_intel DIRECTLY, one accuracy slice per
-- (report_version, basin) present in raw_intel.well_master, so a vintage's
-- calibration keeps improving after the vintage itself is replaced — the
-- vintage-over-vintage record Michael's standing question needs.
--
-- DIRECT TIER ONLY — a deliberate scope cut vs sql/38:
--   * 'direct'    — the blind well co-extent-realized a BASE_CASE stick of that
--                   vintage. Match re-derived inline per vintage with sql/21's
--                   predicates (corridor overlap >= 0.5 + same-bench hybrid:
--                   code within 500 ft TVD, or <= 150 ft depth arbiter). Stick
--                   bench codes are re-derived per vintage (sql/19 tiers 2+3:
--                   TVD-aware k=1 inference off curated.bench_reference for
--                   coarse parents, else ref.formation_crosswalk) because
--                   curated.intel_formation_blueox is latest-vintage-only.
--   * 'unmatched' — blind well with no qualifying stick. Kept (NULL forecast
--                   columns) so every blind producer maps per vintage.
--   * NO proxy tier: the rep-stick SSOT selector (sql/35) and its curated
--     inputs are latest-vintage by design; duplicating them per vintage doubles
--     the contract surface. The direct tier is the calibration number of record
--     (2025Q3: mop-6 oil per-ft bias -11.8%). sql/38 remains the surface of
--     record for the live vintage (erebor Accuracy tab, proxy tier included).
--
-- Novi renumbers planned_well_id AND regenerates stick names every vintage
-- (verified 2026-09-17: zero id or name carryover 2025Q3 -> 2026Q3; the 47,929
-- carried well_refs are all PDP/api10), so cross-vintage same-stick comparison
-- is impossible — vintages are compared via their blind-well error
-- distributions here, never by joining sticks.
--
-- GRAIN: (report_version, api10, mop 1..24). The same well may be blind under
-- several vintages and is scored against each. Measurement conventions
-- (cum-based percent errors, 30-day forecast months, partial first calendar
-- month, is_latest_reported exclusion, P50 bias-vs-MAE reading) are sql/38's —
-- see its header; they are not repeated here.
--
-- DEPENDS ON: raw_intel.well_master / production_forecast / stick_id_map
--   (sql/27), curated.producing_reference (sql/20), formation_blueox_tvd
--   (sql/23), bench_reference (sql/18), ref.formation_crosswalk (sql/14),
--   curated.production (sql/05).
-- REFRESH: nightly (etl.refresh — actuals accrue; registered in
--   _OPTIONAL_MATVIEWS: the quarterly reload's sql/20 rebuild DROP-CASCADEs
--   this view; scripts/apply_intel_forecast_accuracy rebuilds it with sql/38).
-- RUN: python -m scripts.apply_intel_forecast_accuracy   (applies 38 + 43)
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Part 1: the recognition-cliff detector, parameterized by vintage AND basin.
-- Same detection rule as the zero-arg sql/38 function (earliest fp-month with
-- PDP coverage < 10%, after the last month at >= 50%), but against the NAMED
-- vintage's PDP class read straight from raw_intel, per basin — basin families
-- can decouple (a quarter may land for one basin only), so the cliff is a
-- (vintage, basin) property here. The zero-arg function stays the boundary for
-- sql/38. Body fully schema-qualified: it re-parses under PG17's restricted
-- search_path at every REFRESH of the matview below.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION curated.intel_pdp_cliff_date(
    p_report_version text, p_basin text
) RETURNS date AS $$
    WITH cov AS (
        SELECT date_trunc('month', pr.first_production_date)::date AS fp_month,
               count(*) FILTER (WHERE w.api10 IS NOT NULL)::numeric
                 / count(*) AS pdp_frac
        FROM curated.producing_reference pr
        LEFT JOIN (
            SELECT DISTINCT wm.uwi_api AS api10
            FROM raw_intel.well_master wm
            WHERE wm.report_version = p_report_version
              AND wm.basin_slug = p_basin
              AND wm.inventory_class = 'PDP'
              AND wm.uwi_api IS NOT NULL
        ) w ON w.api10 = pr.api10
        WHERE pr.basin = p_basin
        GROUP BY 1
    ),
    last_covered AS (
        SELECT max(fp_month) AS m FROM cov WHERE pdp_frac >= 0.5
    )
    SELECT min(cov.fp_month)
    FROM cov, last_covered
    WHERE cov.pdp_frac < 0.1
      AND cov.fp_month > last_covered.m
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION curated.intel_pdp_cliff_date(text, text) IS
'Per-(vintage, basin) Novi Intelligence PDP recognition cliff, read from raw_intel directly (works for superseded vintages the curated views no longer serve). Same detection rule as the zero-arg sql/38 function, which remains the boundary for the live-vintage accuracy matview. 2024-12-01 on 2025Q3 for both basins. Bounds the per-vintage blind population of curated.intel_forecast_accuracy_vintage (sql/43).';


-- ---------------------------------------------------------------------------
-- Part 2: the per-vintage accuracy matview.
-- ---------------------------------------------------------------------------

DROP MATERIALIZED VIEW IF EXISTS curated.intel_forecast_accuracy_vintage CASCADE;


CREATE MATERIALIZED VIEW curated.intel_forecast_accuracy_vintage AS
WITH vintages AS (
    -- One slice per (vintage, basin) that ships a PDP class (blindness is
    -- undefined without one).
    SELECT DISTINCT report_version, basin_slug AS basin
    FROM raw_intel.well_master
    WHERE inventory_class = 'PDP'
),
cliff AS MATERIALIZED (
    -- MATERIALIZED is load-bearing (sql/21's lesson): this CTE is referenced
    -- once, so the planner would otherwise inline it into the blind join and
    -- re-evaluate the cliff function per candidate row instead of once per
    -- (vintage, basin) — the difference between seconds and hours.
    SELECT v.report_version, v.basin,
           curated.intel_pdp_cliff_date(v.report_version, v.basin) AS cliff_date
    FROM vintages v
),
blind AS (
    -- Novi-blind producers per vintage: on/after that vintage's cliff, absent
    -- from that vintage's PDP class.
    SELECT c.report_version, c.cliff_date,
           pr.api10, pr.basin,
           COALESCE(t.corrected_code, pr.code) AS formation_blueox,
           pr.first_production_date, pr.operator,
           pr.tvd AS well_tvd, pr.corridor,
           pr.ll_ft::double precision          AS drilled_ll_ft
    FROM cliff c
    JOIN curated.producing_reference pr
      ON pr.basin = c.basin
     AND pr.first_production_date >= c.cliff_date
    LEFT JOIN curated.formation_blueox_tvd t ON t.api10 = pr.api10
    WHERE c.cliff_date IS NOT NULL
      AND NOT EXISTS (
            SELECT 1 FROM raw_intel.well_master wmx
            WHERE wmx.report_version = c.report_version
              AND wmx.basin_slug     = c.basin
              AND wmx.inventory_class = 'PDP'
              AND wmx.uwi_api = pr.api10
          )
),
cand AS (
    -- Co-extent candidates: that vintage's BASE_CASE sticks intersecting the
    -- well's ±150 ft corridor (GiST both sides). Overlap = stick length inside
    -- the corridor / stick length (sql/21's definition).
    SELECT b.report_version, b.api10, b.basin, b.well_tvd,
           b.formation_blueox AS well_code,
           wm.well_ref, wm.report_name, wm.formation, wm.geom AS stick_geom,
           wm.tvd_td, wm.lateral_length,
           ST_Length(ST_Intersection(wm.geom, b.corridor)::geography)
             / NULLIF(ST_Length(wm.geom::geography), 0) AS overlap
    FROM blind b
    JOIN raw_intel.well_master wm
      ON wm.report_version  = b.report_version
     AND wm.basin_slug      = b.basin
     AND wm.inventory_class = 'BASE_CASE'
     AND wm.tvd_td IS NOT NULL
     AND wm.geom IS NOT NULL
     AND ST_Intersects(wm.geom, b.corridor)
    WHERE b.well_tvd IS NOT NULL
),
strong AS (
    SELECT *,
           -- Coarse parents that split (sql/19): re-derive the sub-bench by
           -- inference; everything else crosswalks.
           CASE UPPER(formation)
               WHEN 'WOLFCAMP A' THEN CASE WHEN basin = 'delaware' THEN 'WCA' END
               WHEN 'WOLFCAMP B' THEN 'WCB'
               WHEN 'AVALON'     THEN CASE WHEN basin = 'delaware' THEN 'AVA' END
           END AS parent
    FROM cand
    WHERE overlap >= 0.5
),
coded AS (
    -- Vintage-scoped bench code: sql/19 tier-2 TVD-aware k=1 (12 nearest
    -- same-parent curated laterals, then TVD-nearest bench), else tier-3
    -- crosswalk. No pdp_join tier: these sticks are planned by definition.
    SELECT s.*,
           COALESCE(inf.code, cx.canonical_code) AS stick_code
    FROM strong s
    LEFT JOIN ref.formation_crosswalk cx
           ON cx.basin = s.basin AND cx.raw_value = UPPER(s.formation)
    LEFT JOIN LATERAL (
        SELECT cand2.bench AS code
        FROM (
            SELECT br.bench, br.tvd
            FROM curated.bench_reference br
            WHERE s.parent IS NOT NULL
              AND br.basin = s.basin
              AND br.parent = s.parent
            ORDER BY br.geom <-> s.stick_geom
            LIMIT 12
        ) cand2
        ORDER BY abs(cand2.tvd - s.tvd_td)
        LIMIT 1
    ) inf ON TRUE
),
matched AS (
    -- Best qualifying stick per (vintage, well); n_sticks_for_well counts the
    -- qualifiers (a planned-vs-drilled count miss is itself signal, sql/38).
    SELECT DISTINCT ON (report_version, api10)
           report_version, api10,
           well_ref, report_name,
           substring(well_ref FROM 4)::bigint AS pw_id,
           lateral_length AS novi_ll_ft,
           overlap        AS match_overlap,
           count(*) OVER (PARTITION BY report_version, api10) AS n_sticks_for_well
    FROM coded
    WHERE (stick_code = well_code AND abs(well_tvd - tvd_td) <= 500)
       OR abs(well_tvd - tvd_td) <= 150
    ORDER BY report_version, api10, overlap DESC, well_ref
),
fcst_cum AS (
    -- Windowed forecast cums for matched sticks, read from the RAW slice
    -- (rates bbl/d / Mcf/d over 30-day months; forecast_day is 1-based x30).
    SELECT m.report_version, m.api10,
           (pf.forecast_day / 30)::int AS mop,
           SUM(pf.oil_per_day   * 30) OVER w AS cum_oil,
           SUM(pf.gas_per_day   * 30) OVER w AS cum_gas,
           SUM(pf.water_per_day * 30) OVER w AS cum_water
    FROM matched m
    JOIN raw_intel.production_forecast pf
      ON pf.planned_well_id = m.pw_id
     AND pf.report_name     = m.report_name    -- pw ids are per-family; report_name disambiguates
     AND pf.forecast_day BETWEEN 30 AND 720
    WINDOW w AS (PARTITION BY m.report_version, m.api10 ORDER BY pf.forecast_day)
),
blind_wells AS (
    SELECT DISTINCT api10 FROM blind
),
actual AS (
    -- Identical to sql/38's actual CTE (dedup keep-latest-calendar-row per
    -- (api10, mop); self-computed producing-day cum with completeness guard),
    -- computed once across vintages.
    SELECT DISTINCT ON (p.api10, p.months_on_production)
           p.api10,
           p.months_on_production AS mop,
           p.cumulative_oil_bbl::double precision   AS actual_cum_oil,
           p.cumulative_gas_mcf::double precision   AS actual_cum_gas,
           p.cumulative_water_bbl::double precision AS actual_cum_water,
           sum(p.producing_days) OVER w_cum         AS cum_producing_days,
           count(*) FILTER (WHERE p.producing_days IS NULL) OVER w_cum
                                                    AS n_pd_null,
           (p.months_on_production =
              max(p.months_on_production) OVER (PARTITION BY p.api10))
                                            AS is_latest_reported
    FROM curated.production p
    JOIN blind_wells b ON b.api10 = p.api10
    WHERE p.months_on_production BETWEEN 1 AND 24
    WINDOW w_cum AS (PARTITION BY p.api10 ORDER BY p.prod_date)
    ORDER BY p.api10, p.months_on_production, p.prod_date DESC
)
SELECT
    b.report_version,
    b.api10,
    a.mop,
    CASE WHEN m.api10 IS NOT NULL THEN 'direct' ELSE 'unmatched' END AS tier,
    b.basin,
    b.formation_blueox,
    b.operator,
    b.first_production_date,
    b.cliff_date,
    -- match provenance
    m.well_ref                                    AS novi_well_ref,
    sid.stick_id,
    m.match_overlap,
    m.n_sticks_for_well,
    -- laterals
    b.drilled_ll_ft,
    m.novi_ll_ft,
    b.drilled_ll_ft / NULLIF(m.novi_ll_ft, 0)     AS ll_ratio,
    -- oil ------------------------------------------------------------------
    fc.cum_oil                                    AS fcst_cum_oil,
    a.actual_cum_oil,
    (a.actual_cum_oil - fc.cum_oil) / NULLIF(fc.cum_oil, 0)          AS pct_err_oil,
    fc.cum_oil / NULLIF(m.novi_ll_ft, 0)          AS fcst_cum_oil_perft,
    a.actual_cum_oil / NULLIF(b.drilled_ll_ft, 0) AS actual_cum_oil_perft,
    (a.actual_cum_oil / NULLIF(b.drilled_ll_ft, 0))
      / NULLIF(fc.cum_oil / NULLIF(m.novi_ll_ft, 0), 0) - 1
                                                  AS pct_err_oil_perft,
    -- gas ------------------------------------------------------------------
    fc.cum_gas                                    AS fcst_cum_gas,
    a.actual_cum_gas,
    (a.actual_cum_gas - fc.cum_gas) / NULLIF(fc.cum_gas, 0)          AS pct_err_gas,
    fc.cum_gas / NULLIF(m.novi_ll_ft, 0)          AS fcst_cum_gas_perft,
    a.actual_cum_gas / NULLIF(b.drilled_ll_ft, 0) AS actual_cum_gas_perft,
    (a.actual_cum_gas / NULLIF(b.drilled_ll_ft, 0))
      / NULLIF(fc.cum_gas / NULLIF(m.novi_ll_ft, 0), 0) - 1
                                                  AS pct_err_gas_perft,
    -- water ----------------------------------------------------------------
    fc.cum_water                                  AS fcst_cum_water,
    a.actual_cum_water,
    (a.actual_cum_water - fc.cum_water) / NULLIF(fc.cum_water, 0)    AS pct_err_water,
    fc.cum_water / NULLIF(m.novi_ll_ft, 0)        AS fcst_cum_water_perft,
    a.actual_cum_water / NULLIF(b.drilled_ll_ft, 0) AS actual_cum_water_perft,
    (a.actual_cum_water / NULLIF(b.drilled_ll_ft, 0))
      / NULLIF(fc.cum_water / NULLIF(m.novi_ll_ft, 0), 0) - 1
                                                  AS pct_err_water_perft,
    -- diagnostics ----------------------------------------------------------
    CASE WHEN a.n_pd_null = 0
         THEN a.cum_producing_days / NULLIF(a.mop * 30.44, 0)
    END                                           AS producing_day_frac,
    a.is_latest_reported
FROM blind b
JOIN actual a        ON a.api10 = b.api10
LEFT JOIN matched m  ON m.report_version = b.report_version AND m.api10 = b.api10
LEFT JOIN fcst_cum fc ON fc.report_version = b.report_version
                     AND fc.api10 = b.api10 AND fc.mop = a.mop
LEFT JOIN raw_intel.stick_id_map sid ON sid.well_ref = m.well_ref
;


CREATE UNIQUE INDEX idx_intel_forecast_accuracy_vintage_pk
    ON curated.intel_forecast_accuracy_vintage (report_version, api10, mop);   -- REFRESH CONCURRENTLY

CREATE INDEX idx_intel_forecast_accuracy_vintage_tier
    ON curated.intel_forecast_accuracy_vintage (report_version, tier);

CREATE INDEX idx_intel_forecast_accuracy_vintage_grp
    ON curated.intel_forecast_accuracy_vintage (report_version, basin, formation_blueox);


COMMENT ON MATERIALIZED VIEW curated.intel_forecast_accuracy_vintage IS
'Novi Intelligence forecast accuracy per RETAINED vintage: one row per (report_version, api10, mop 1-24) over each vintage''s own blind-producer population (first prod >= that vintage''s per-basin recognition cliff, absent from its PDP class), read from raw_intel directly — superseded vintages keep accruing out-of-sample actuals after the curated views stop serving them. DIRECT TIER ONLY (co-extent BASE_CASE stick, sql/21 predicates, bench codes re-derived per vintage); tier=unmatched rows keep NULL forecasts; no proxy tier by design (the rep-stick SSOT is latest-vintage). Measurement conventions = sql/38 (cum-based errors, 30-day months, exclude is_latest_reported from aggregates, bias = mean pct error on the per-ft columns). sql/38 remains the live-vintage surface of record (erebor Accuracy tab). Refreshed nightly; DROP-CASCADEd by the quarterly reload''s sql/20 rebuild and restored by apply_intel_forecast_accuracy. sql/43.';

COMMENT ON COLUMN curated.intel_forecast_accuracy_vintage.report_version IS
'Novi report vintage this row scores, e.g. 2025Q3. The same well may be blind under several vintages and is scored against each.';
COMMENT ON COLUMN curated.intel_forecast_accuracy_vintage.tier IS
'direct = co-extent-realized BASE_CASE stick of this vintage (raw + per-ft errors). unmatched = no qualifying stick; forecast columns NULL. No proxy tier (sql/38 only).';
COMMENT ON COLUMN curated.intel_forecast_accuracy_vintage.cliff_date IS
'This (vintage, basin)''s empirical PDP recognition cliff (curated.intel_pdp_cliff_date(report_version, basin)); lower bound of the blind population.';
COMMENT ON COLUMN curated.intel_forecast_accuracy_vintage.novi_well_ref IS
'Matched stick''s well_ref (PW-<planned_well_id>) in raw_intel for this vintage. Novi renumbers planned wells every vintage — never join sticks across vintages.';
COMMENT ON COLUMN curated.intel_forecast_accuracy_vintage.stick_id IS
'Stable stick_id of the matched well_ref via raw_intel.stick_id_map (append-only, so superseded vintages keep their ids).';
COMMENT ON COLUMN curated.intel_forecast_accuracy_vintage.pct_err_oil_perft IS
'Per-ft cum error at this mop: (actual bbl/ft)/(forecast bbl/ft) - 1. The primary bias metric; mean = bias, cf. sql/38.';
COMMENT ON COLUMN curated.intel_forecast_accuracy_vintage.is_latest_reported IS
'Well''s newest posted production month (often incomplete under reporting lag). EXCLUDE from aggregates.';
