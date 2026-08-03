-- =============================================================================
-- 38 — curated.intel_pdp_cliff_date() + curated.intel_forecast_accuracy
--      (Novi Intelligence forecast vs realized actuals — the accuracy/bias
--       measurement the deal-intake inflation_ratio_band wants to calibrate on)
--
-- POPULATION — "Novi-blind producers": producing horizontals (delaware/midland,
-- curated.producing_reference) whose first_production_date is on/after the
-- vendor's empirical PDP RECOGNITION CLIFF and whose api10 is absent from the
-- Novi Intelligence PDP class. Novi never saw these wells, yet forecast the
-- acreage they landed on — so their actuals vs the local Novi forecast is a
-- clean out-of-sample read on forecast bias.
--
-- THE CLIFF vs THE VINTAGE DATE. curated.intel_vintage_date() (sql/29) is the
-- report-label month-end (2025-09-30 for 2025Q3) and remains the boundary of
-- record for reconciled_inventory's realized_drift/realized_phantom split —
-- UNTOUCHED here. Empirically the 2025Q3 vintage's PDP class covers 82% of
-- producers with first prod 2024-11 and <1% from 2024-12 onward: the true
-- data cut trails the label by ~10 months. intel_pdp_cliff_date() detects that
-- cliff (first fp-month where PDP coverage of producing_reference drops below
-- 10%, after the last month at >=50%) so the accuracy population includes the
-- whole blind window, and recomputes itself on the next vintage.
--
-- TWO COMPARISON TIERS (column: tier)
--   'direct' — the well co-extent-realized a PUD stick (reconciled_inventory
--       matched_api10, status realized_drift OR realized_phantom; phantoms in
--       the blind window are genuinely blind forecasts — Novi carried the slot
--       as undrilled inventory while the well was already producing). Forecast
--       side = that stick's own intel_forecast series; best match_overlap wins
--       when one well realizes several sticks (kept, flagged via
--       n_sticks_for_well — a planned-vs-drilled count miss is itself signal).
--       Raw AND per-ft errors.
--   'proxy'  — no co-extent stick: Novi infilled the area with sticks that do
--       not coincide with the drilled lateral. Forecast side = the per-ft
--       MEDIAN across curated.intel_representative_sticks (sql/35 — the SSOT
--       selector: same bench, 1 mi, lateral tol 25% delaware / 40% midland per
--       the Blue Ox ledger §9). Per-ft errors only (raw is undefined — the rep
--       sticks are not the well). n_rep carried; n_rep < 3 = low-n (report
--       thinness, never hide it). n_rep = 0 rows keep NULL forecast columns so
--       the well still maps (rendered grey downstream).
--
-- GRAIN (api10, mop): one row per blind well per aligned production month,
-- mop 1..24. intel_forecast.mop is 1-based (min forecast_day = 30, verified
-- 2026-08-03) and aligns 1:1 with production.months_on_production.
--
-- MEASUREMENT CONVENTIONS
--   * Cum-based percent errors: (actual_cum - fcst_cum) / fcst_cum. Forecast
--     cums are windowed sum(rate*30) — the share's cumulative columns are
--     deliberately not extracted (etl/intel_sf EXCLUDE_COLS).
--   * 30-day forecast months vs calendar actual months: ~1.6%/yr drift
--     (30 vs 30.44 d) ≈ 0.8% at mop 6 — accepted, not corrected.
--   * Month 1 of actuals is a PARTIAL calendar month (first-prod mid-month):
--     systematic low bias on actual cums, largest at mop 1-2, ~3-8% residual
--     at mop 6, decaying. Included (dropping the highest-rate month would be
--     worse); producing_day_frac is the diagnostic; display layers mute
--     mop 1-2.
--   * is_latest_reported flags each well's newest posted month (reporting lag
--     -> often incomplete). Aggregates must exclude it.
--   * Novi forecast is P50: bias (mean pct error) is the calibration number;
--     MAE is dispersion and is nonzero even for a perfectly calibrated P50.
--
-- DEPENDS ON: curated.producing_reference (sql/20), formation_blueox_tvd
--   (sql/23), reconciled_inventory (sql/21), intel_locations + intel_forecast
--   (sql/29), intel_representative_sticks (sql/35), curated.production
--   (sql/05), sql/26 geography indexes (the rep-stick ST_DWithin).
-- REFRESH: nightly (etl.refresh — actuals accrue monthly and the population
--   grows as wells come online). Registered in _OPTIONAL_MATVIEWS: the
--   quarterly intel reload DROP-CASCADEs this view; rebuild via
--   scripts/apply_intel_forecast_accuracy.py after apply_reconciled_inventory
--   and before apply_erebor_locations (SKILL.md §5).
-- RUN: python -m scripts.apply_intel_forecast_accuracy   (or psql -f this file)
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Part 1: the recognition-cliff detector. Companion to intel_vintage_date().
-- Earliest first-prod month whose Novi-PDP coverage of producing_reference is
-- below 10%, restricted to months after the last month at >=50% coverage (so
-- a sparse early month can't fire it). STABLE, planner-inlinable.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION curated.intel_pdp_cliff_date() RETURNS date AS $$
    WITH cov AS (
        SELECT date_trunc('month', pr.first_production_date)::date AS fp_month,
               count(*) FILTER (WHERE il.api10 IS NOT NULL)::numeric
                 / count(*) AS pdp_frac
        FROM curated.producing_reference pr
        LEFT JOIN (
            SELECT DISTINCT api10 FROM curated.intel_locations
            WHERE category = 'PDP' AND api10 IS NOT NULL
        ) il ON il.api10 = pr.api10
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

COMMENT ON FUNCTION curated.intel_pdp_cliff_date() IS
'Empirical Novi Intelligence PDP recognition cliff: earliest first-prod month where the loaded vintage''s PDP class covers <10% of producing_reference wells (after the last month covered >=50%). 2024-12-01 on the 2025Q3 vintage — ~10 months before the report-label vintage date. Companion to intel_vintage_date(), which stays the reconciled_inventory drift/phantom boundary of record; this function bounds the forecast-accuracy population (sql/38) instead. Recomputes per vintage.';


-- ---------------------------------------------------------------------------
-- Part 2: the accuracy matview.
-- ---------------------------------------------------------------------------

DROP MATERIALIZED VIEW IF EXISTS curated.intel_forecast_accuracy CASCADE;


CREATE MATERIALIZED VIEW curated.intel_forecast_accuracy AS
WITH blind AS (
    -- Novi-blind producers: on/after the cliff, absent from the PDP class.
    SELECT pr.api10,
           pr.basin,
           COALESCE(t.corrected_code, pr.code) AS formation_blueox,
           pr.first_production_date,
           pr.operator,
           pr.ll_ft::double precision          AS drilled_ll_ft,
           pr.geom
    FROM curated.producing_reference pr
    LEFT JOIN curated.formation_blueox_tvd t ON t.api10 = pr.api10
    WHERE pr.first_production_date >= (SELECT curated.intel_pdp_cliff_date())
      AND NOT EXISTS (
            SELECT 1 FROM curated.intel_locations il
            WHERE il.category = 'PDP' AND il.api10 = pr.api10
          )
),
direct AS (
    -- Best co-extent stick per blind well (drift or blind-window phantom).
    SELECT DISTINCT ON (ri.matched_api10)
           ri.matched_api10 AS api10,
           ri.stick_id,
           ri.match_overlap,
           count(*) OVER (PARTITION BY ri.matched_api10) AS n_sticks_for_well
    FROM curated.reconciled_inventory ri
    JOIN blind b ON b.api10 = ri.matched_api10
    WHERE ri.status IN ('realized_drift', 'realized_phantom')
    ORDER BY ri.matched_api10, ri.match_overlap DESC, ri.stick_id
),
rep AS (
    -- Proxy tier membership: representative sticks per non-direct blind well,
    -- via the SSOT selector (per-basin lateral tolerance, Blue Ox ledger §9).
    SELECT b.api10, r.stick_id, il.ll_ft::double precision AS rep_ll_ft
    FROM blind b
    LEFT JOIN direct d ON d.api10 = b.api10
    CROSS JOIN LATERAL curated.intel_representative_sticks(
        b.geom, b.formation_blueox, b.drilled_ll_ft, 1609.0,
        CASE WHEN b.basin = 'midland' THEN 0.40 ELSE 0.25 END
    ) r
    JOIN curated.intel_locations il ON il.stick_id = r.stick_id
    WHERE d.api10 IS NULL
),
needed_sticks AS (
    SELECT stick_id FROM direct
    UNION
    SELECT stick_id FROM rep
),
fcst_cum AS (
    -- Windowed forecast cums per stick: rates are bbl/d (oil, water) and
    -- Mcf/d (gas) over 30-day months; mop is 1-based.
    SELECT f.stick_id, f.mop,
           SUM(f.oil   * 30) OVER w AS cum_oil,
           SUM(f.gas   * 30) OVER w AS cum_gas,
           SUM(f.water * 30) OVER w AS cum_water
    FROM curated.intel_forecast f
    JOIN needed_sticks ns ON ns.stick_id = f.stick_id
    -- ip_day bound is the sargable twin of the mop bound (mop = ip_day/30 is
    -- computed in the view; raw index is (planned_well_id, forecast_day)).
    WHERE f.ip_day BETWEEN 30 AND 720
      AND f.mop BETWEEN 1 AND 24
    WINDOW w AS (PARTITION BY f.stick_id ORDER BY f.mop)
),
fcst_direct AS (
    SELECT d.api10, fc.mop,
           fc.cum_oil, fc.cum_gas, fc.cum_water,
           il.ll_ft::double precision AS novi_ll_ft,
           il.pad_name
    FROM direct d
    JOIN fcst_cum fc ON fc.stick_id = d.stick_id
    JOIN curated.intel_locations il ON il.stick_id = d.stick_id
),
fcst_proxy AS (
    -- Per-ft median across each well's rep set, computed per (well, mop).
    -- Each stick normalized by its OWN lateral before the median.
    SELECT rep.api10, fc.mop,
           count(*)                             AS n_rep,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY fc.cum_oil   / NULLIF(rep.rep_ll_ft, 0)) AS med_cum_oil_perft,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY fc.cum_gas   / NULLIF(rep.rep_ll_ft, 0)) AS med_cum_gas_perft,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY fc.cum_water / NULLIF(rep.rep_ll_ft, 0)) AS med_cum_water_perft,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY rep.rep_ll_ft) AS rep_median_ll_ft
    FROM rep
    JOIN fcst_cum fc ON fc.stick_id = rep.stick_id
    WHERE rep.rep_ll_ft > 0
    GROUP BY rep.api10, fc.mop
),
rep_counts AS (
    -- Rep-set size per proxy well (independent of forecast coverage, so a
    -- well whose rep sticks lack forecast rows still reports its n_rep).
    SELECT api10, count(*) AS n_rep_total
    FROM rep
    GROUP BY api10
),
actual AS (
    -- Novi repeats months_on_production when a well's first calendar month has
    -- zero producing days (403 duplicate (api10, mop) pairs as of 2026-08):
    -- keep the LATEST calendar row per mop — its cumulative columns include
    -- the dead month's zeros, which is the cum-through-month the comparison
    -- wants.
    SELECT DISTINCT ON (p.api10, p.months_on_production)
           p.api10,
           p.months_on_production AS mop,
           p.cumulative_oil_bbl::double precision   AS actual_cum_oil,
           p.cumulative_gas_mcf::double precision   AS actual_cum_gas,
           p.cumulative_water_bbl::double precision AS actual_cum_water,
           -- producing-day cum, self-computed: Novi's cumulative_producing_days
           -- is 0 on ~74% of well-months (producing_days reported sparsely by
           -- state). Guard: valid only when every month to date reported it.
           sum(p.producing_days) OVER w_cum         AS cum_producing_days,
           count(*) FILTER (WHERE p.producing_days IS NULL) OVER w_cum
                                                    AS n_pd_null,
           (p.months_on_production =
              max(p.months_on_production) OVER (PARTITION BY p.api10))
                                            AS is_latest_reported
    FROM curated.production p
    JOIN blind b ON b.api10 = p.api10
    WHERE p.months_on_production BETWEEN 1 AND 24
    WINDOW w_cum AS (PARTITION BY p.api10 ORDER BY p.prod_date)
    ORDER BY p.api10, p.months_on_production, p.prod_date DESC
)
SELECT
    b.api10,
    a.mop,
    CASE WHEN d.api10 IS NOT NULL THEN 'direct' ELSE 'proxy' END AS tier,
    b.basin,
    b.formation_blueox,
    b.operator,
    b.first_production_date,
    -- direct-tier match provenance
    d.stick_id,
    d.match_overlap,
    d.n_sticks_for_well,
    fd.pad_name,
    -- proxy-tier provenance
    COALESCE(fp.n_rep, rc.n_rep_total, 0)::int    AS n_rep,
    (d.api10 IS NULL AND COALESCE(fp.n_rep, rc.n_rep_total, 0) < 3) AS low_n,
    -- laterals
    b.drilled_ll_ft,
    fd.novi_ll_ft,
    fp.rep_median_ll_ft,
    b.drilled_ll_ft / NULLIF(fd.novi_ll_ft, 0)    AS ll_ratio,
    -- oil ------------------------------------------------------------------
    fd.cum_oil                                    AS fcst_cum_oil,
    a.actual_cum_oil,
    (a.actual_cum_oil - fd.cum_oil) / NULLIF(fd.cum_oil, 0)          AS pct_err_oil,
    COALESCE(fd.cum_oil / NULLIF(fd.novi_ll_ft, 0), fp.med_cum_oil_perft)
                                                  AS fcst_cum_oil_perft,
    a.actual_cum_oil / NULLIF(b.drilled_ll_ft, 0) AS actual_cum_oil_perft,
    (a.actual_cum_oil / NULLIF(b.drilled_ll_ft, 0))
      / NULLIF(COALESCE(fd.cum_oil / NULLIF(fd.novi_ll_ft, 0), fp.med_cum_oil_perft), 0) - 1
                                                  AS pct_err_oil_perft,
    -- gas ------------------------------------------------------------------
    fd.cum_gas                                    AS fcst_cum_gas,
    a.actual_cum_gas,
    (a.actual_cum_gas - fd.cum_gas) / NULLIF(fd.cum_gas, 0)          AS pct_err_gas,
    COALESCE(fd.cum_gas / NULLIF(fd.novi_ll_ft, 0), fp.med_cum_gas_perft)
                                                  AS fcst_cum_gas_perft,
    a.actual_cum_gas / NULLIF(b.drilled_ll_ft, 0) AS actual_cum_gas_perft,
    (a.actual_cum_gas / NULLIF(b.drilled_ll_ft, 0))
      / NULLIF(COALESCE(fd.cum_gas / NULLIF(fd.novi_ll_ft, 0), fp.med_cum_gas_perft), 0) - 1
                                                  AS pct_err_gas_perft,
    -- water ----------------------------------------------------------------
    fd.cum_water                                  AS fcst_cum_water,
    a.actual_cum_water,
    (a.actual_cum_water - fd.cum_water) / NULLIF(fd.cum_water, 0)    AS pct_err_water,
    COALESCE(fd.cum_water / NULLIF(fd.novi_ll_ft, 0), fp.med_cum_water_perft)
                                                  AS fcst_cum_water_perft,
    a.actual_cum_water / NULLIF(b.drilled_ll_ft, 0) AS actual_cum_water_perft,
    (a.actual_cum_water / NULLIF(b.drilled_ll_ft, 0))
      / NULLIF(COALESCE(fd.cum_water / NULLIF(fd.novi_ll_ft, 0), fp.med_cum_water_perft), 0) - 1
                                                  AS pct_err_water_perft,
    -- diagnostics ----------------------------------------------------------
    CASE WHEN a.n_pd_null = 0
         THEN a.cum_producing_days / NULLIF(a.mop * 30.44, 0)
    END                                           AS producing_day_frac,
    a.is_latest_reported
FROM blind b
JOIN actual a       ON a.api10  = b.api10
LEFT JOIN direct d  ON d.api10  = b.api10
LEFT JOIN fcst_direct fd ON fd.api10 = b.api10 AND fd.mop = a.mop
LEFT JOIN fcst_proxy  fp ON fp.api10 = b.api10 AND fp.mop = a.mop
LEFT JOIN rep_counts  rc ON rc.api10 = b.api10
;


CREATE UNIQUE INDEX idx_intel_forecast_accuracy_pk
    ON curated.intel_forecast_accuracy (api10, mop);   -- REFRESH CONCURRENTLY

CREATE INDEX idx_intel_forecast_accuracy_tier
    ON curated.intel_forecast_accuracy (tier);

CREATE INDEX idx_intel_forecast_accuracy_grp
    ON curated.intel_forecast_accuracy (basin, formation_blueox);


COMMENT ON MATERIALIZED VIEW curated.intel_forecast_accuracy IS
'Novi Intelligence forecast vs realized actuals, one row per Novi-blind producer per aligned month (api10, mop 1-24). Population: producing horizontals with first prod >= curated.intel_pdp_cliff_date() (2024-12-01 on 2025Q3 — the vendor''s empirical PDP data cut, ~10 months before the report-label vintage) absent from the Novi PDP class. tier=direct compares against the co-extent-realized stick''s own forecast (raw + per-ft errors); tier=proxy against the per-ft median of intel_representative_sticks (per-ft only; n_rep<3 = low_n). Cum-based percent errors; 30-day forecast months vs calendar actual months (~0.8% drift at mop 6) and the partial first calendar month are documented, accepted biases — mute mop 1-2 in displays and exclude is_latest_reported rows from aggregates. Novi forecast is P50: mean error = bias is the calibration number. Refreshed nightly; DROP-CASCADEd + rebuilt by the quarterly intel reload (apply_intel_forecast_accuracy, before apply_erebor_locations). Calibration target for deal-intake inflation_ratio_band. sql/38.';

COMMENT ON COLUMN curated.intel_forecast_accuracy.api10 IS 'Well key (universal 10-digit API). One blind producer per api10.';
COMMENT ON COLUMN curated.intel_forecast_accuracy.mop IS 'Aligned month index, 1-based: production.months_on_production = intel_forecast.mop (forecast months are 30-day; ~1.6%/yr drift vs calendar, accepted).';
COMMENT ON COLUMN curated.intel_forecast_accuracy.tier IS 'direct = well co-extent-realized a PUD stick (its own forecast; raw + per-ft errors). proxy = no co-extent stick; forecast is the per-ft median of the representative infill set (per-ft errors only).';
COMMENT ON COLUMN curated.intel_forecast_accuracy.stick_id IS 'Direct tier: the matched Novi stick (best match_overlap when the well realizes several). NULL on proxy rows.';
COMMENT ON COLUMN curated.intel_forecast_accuracy.match_overlap IS 'Direct tier: co-extent overlap fraction of the matched stick (reconciled_inventory).';
COMMENT ON COLUMN curated.intel_forecast_accuracy.n_sticks_for_well IS 'Direct tier: number of realized sticks matching this well; >1 = Novi planned more sticks than were drilled (kept on the best match, flagged not summed).';
COMMENT ON COLUMN curated.intel_forecast_accuracy.n_rep IS 'Proxy tier: representative sticks in the benchmark set (same bench, 1 mi, lateral tol 25% delaware / 40% midland). 0 = no benchmark -> NULL errors.';
COMMENT ON COLUMN curated.intel_forecast_accuracy.low_n IS 'Proxy tier with n_rep < 3: benchmark is thin — flag in displays, never hide.';
COMMENT ON COLUMN curated.intel_forecast_accuracy.ll_ratio IS 'Direct tier: drilled_ll_ft / novi_ll_ft. Decomposition identity: pct_err_perft = (1 + pct_err)/ll_ratio - 1.';
COMMENT ON COLUMN curated.intel_forecast_accuracy.pct_err_oil IS 'Direct tier raw cum error: (actual_cum_oil - fcst_cum_oil)/fcst_cum_oil. NULL on proxy rows (rep sticks are not the well).';
COMMENT ON COLUMN curated.intel_forecast_accuracy.pct_err_oil_perft IS 'Per-1,000-ft-basis cum error (actually per-ft; the ratio is scale-free): actual bbl/ft vs forecast bbl/ft. The primary bias metric — valid on both tiers.';
COMMENT ON COLUMN curated.intel_forecast_accuracy.producing_day_frac IS 'sum(producing_days through this month) / (mop x 30.44): uptime + partial-first-month diagnostic. Low values explain low actual cums without a forecast miss. NULL when any month to date lacks reported producing_days (~74% of Novi well-months).';
COMMENT ON COLUMN curated.intel_forecast_accuracy.is_latest_reported IS 'This is the well''s newest posted production month — often incomplete under reporting lag. EXCLUDE from aggregates.';
