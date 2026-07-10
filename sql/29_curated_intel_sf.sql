-- =============================================================================
-- 29 — curated.intel_* rebuilt on raw_intel (Novi INTEL Snowflake share)
--
-- Supersedes sql/12 (raw_novi_intel-based) at the phase-6 cutover. The OUTPUT
-- CONTRACT of curated.intel_locations is preserved column-for-column so
-- sql/19 (intel_formation_blueox), sql/20/21 (reconciled_inventory), sql/25
-- (net_new_pdp), sql/22 (erebor_locations) and the erebor/narvi apps re-run
-- unmodified. Deliberate deviations from the sql/12 values (all verified
-- against 2025Q3 data, see the migration plan):
--   * report_version is '2025Q3' (share format), was '3Q25'
--   * irr normalization: the share INHERITED the vendor unit inconsistency,
--     post-divided by 100 — Delaware PUD/RES are correct fractions (slice
--     median |irr| ~0.75) but PDP and Midland PUD/RES are fraction/100
--     (median ~0.005, verified 2026-07-08; raised with Novi). The per-slice
--     median self-calibration therefore SURVIVES with a new threshold:
--     med < 0.05 -> x10000, else x100. Self-heals if Novi fixes the share.
--   * pad_npv25 = SUM(npv25) over member sticks per (report, pad_name); the
--     old value was the pad shapefile's own rollup. Share gap: pad_name only
--     exists for Delaware BASE_CASE as of 2025Q3 (raised with Novi).
--   * conf_int has no share source -> NULL
--   * prop_load: share completion data covers planned wells only -> PDP NULL
--     (old sticks had it; gap raised with Novi)
--   * subbasin / county now populated where the old layer had NULLs
--   * ML scores/tiers may cover more than PUD (share scores PDP too)
--   * fp_year: PDP = year(first_production_date); planned = 2050 (the old
--     placeholder — the share's planned_til_date is entirely NULL)
--
-- stick_id comes from raw_intel.stick_id_map (append-only), so it is STABLE
-- across quarterly reloads — unlike the old BIGSERIAL which renumbered on
-- every reload. Positive and disjoint from erebor's -(api10) PDP ids.
--
-- RUN: scripts/load_intel_sf.py --curated   (phase-6 cutover only; DROPs
--      CASCADE through intel_formation_blueox, reconciled_inventory,
--      net_new_pdp, intel_pdp_support (sql/30), erebor_locations — rebuild order
--      per the runbook: apply_intel_pdp_support precedes apply_erebor_locations).
-- Idempotent: DROP ... IF EXISTS then CREATE.
-- =============================================================================

-- Vintage quarter-end of the loaded Novi Intelligence data, derived from
-- report_version ('2025Q3' -> 2025-09-30). Replaces the DATE literals that
-- sql/21 / sql/25 used to hardcode — future reloads no longer edit SQL.
CREATE OR REPLACE FUNCTION curated.intel_vintage_date() RETURNS date AS $$
    SELECT max((make_date(substring(report_version, 1, 4)::int,
                          substring(report_version, 6, 1)::int * 3, 1)
                + interval '1 month' - interval '1 day')::date)
    FROM raw_intel.well_master
$$ LANGUAGE sql STABLE;

DROP MATERIALIZED VIEW IF EXISTS curated.intel_locations CASCADE;

CREATE MATERIALIZED VIEW curated.intel_locations AS
-- BEGIN INTEL_LOCATIONS_SELECT (marker used by scripts/reconcile_intel_sf.py
-- to build the qa staging copy — keep markers intact)
WITH pdp_key AS (
    -- well_id -> api10 for normalizing PDP-side FKs onto well_ref
    SELECT well_id, report_name, uwi_api
    FROM raw_intel.well
),
econ AS (
    SELECT COALESCE('PW-' || es.planned_well_id::text, pk.uwi_api) AS well_ref,
           es.*
    FROM raw_intel.well_economics_summary es
    LEFT JOIN pdp_key pk
           ON pk.well_id = es.well_id AND pk.report_name = es.report_name
),
cost AS (
    SELECT COALESCE('PW-' || cs.planned_well_id::text, pk.uwi_api) AS well_ref,
           cs.report_name, cs.total_dc_cost, cs.total_dcet_cost,
           cs.normalized_dc_cost_per_ft, cs.normalized_dcet_cost_per_ft
    FROM raw_intel.well_cost_summary cs
    LEFT JOIN pdp_key pk
           ON pk.well_id = cs.well_id AND pk.report_name = cs.report_name
),
wb AS (
    SELECT COALESCE('PW-' || b.planned_well_id::text, pk.uwi_api) AS well_ref,
           b.report_name,
           b.heelpoint_latitude, b.heelpoint_longitude,
           b.midpoint_latitude, b.midpoint_longitude,
           b.bottom_hole_latitude, b.bottom_hole_longitude
    FROM raw_intel.wellbore b
    LEFT JOIN pdp_key pk
           ON pk.well_id = b.well_id AND pk.report_name = b.report_name
),
compl AS (
    SELECT 'PW-' || c.planned_well_id::text AS well_ref, c.report_name,
           c.proppant_loading
    FROM raw_intel.well_completion c
    WHERE c.planned_well_id IS NOT NULL          -- share has no PDP completions
),
ml AS (
    -- one row per well: oil-stream scores (matches the old pud_attrs source,
    -- which came from Novi's *_pud_oil files)
    SELECT DISTINCT ON (well_ref, report_name)
           COALESCE('PW-' || m.planned_well_id::text, pk.uwi_api, m.external_id) AS well_ref,
           m.report_name,
           m.spacing_score, m.spacing_tier,
           m.prior_depletion_score, m.prior_depletion_tier,
           m.completion_score, m.completion_tier
    FROM raw_intel.well_ml_score m
    LEFT JOIN pdp_key pk
           ON pk.well_id = m.well_id AND pk.report_name = m.report_name
    WHERE m.stream = 'oil'
    ORDER BY well_ref, report_name, m.well_ml_score_id
),
rq AS (
    SELECT DISTINCT ON (well_ref, report_name)
           COALESCE('PW-' || r.planned_well_id::text, pk.uwi_api, r.external_id) AS well_ref,
           r.report_name,
           r.rock_quality_score, r.rock_quality_tier
    FROM raw_intel.well_rock_quality r
    LEFT JOIN pdp_key pk
           ON pk.well_id = r.well_id AND pk.report_name = r.report_name
    WHERE r.stream = 'oil'
    ORDER BY well_ref, report_name, r.well_rock_quality_id
),
slice_irr AS (
    -- Per (basin, category) median |irr|. The share's IRR unit is inconsistent
    -- by slice (see header): correct-fraction slices have median ~0.75, the
    -- fraction/100 slices ~0.005. A 0.05 threshold separates them cleanly and
    -- yields x100 everywhere if Novi ever normalizes the share properly.
    SELECT wm.basin_slug, wm.inventory_class,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(e.irr)) AS med
    FROM raw_intel.well_master wm
    JOIN econ e ON e.well_ref = wm.well_ref AND e.report_name = wm.report_name
    WHERE e.irr IS NOT NULL
    GROUP BY wm.basin_slug, wm.inventory_class
),
pad_npv AS (
    -- pad rollup recomputed from member-stick economics (share has no
    -- pad-level rollup). Delaware BASE_CASE only as of 2025Q3.
    SELECT wm.report_name, wm.pad_name, SUM(e.npv25) AS pad_npv25
    FROM raw_intel.well_master wm
    JOIN econ e ON e.well_ref = wm.well_ref AND e.report_name = wm.report_name
    WHERE wm.pad_name IS NOT NULL
    GROUP BY wm.report_name, wm.pad_name
)
SELECT
    m0.stick_id,                                   -- stable across reloads (stick_id_map)
    wm.basin_slug                     AS basin,    -- 'delaware' | 'midland'
    wm.report_version,                             -- '2025Q3' (share format)
    CASE wm.inventory_class
        WHEN 'PDP'       THEN 'PDP'
        WHEN 'BASE_CASE' THEN 'PUD'
        WHEN 'EMERGING'  THEN 'RES'
    END                               AS category,
    wm.report_name                    AS src_layer,
    CASE WHEN wm.inventory_class = 'PDP' THEN wm.uwi_api ELSE wm.name END
                                      AS unique_id,
    wm.uwi_api                        AS api10,    -- non-null for PDP (all 10-digit)
    (w.api10 IS NOT NULL)             AS pdp_in_warehouse,
    -- identity / geology / completion
    'Oil'::text                       AS phase,    -- constant in the old layer too
    wm.operator_name                  AS operator,
    wm.formation,
    wm.county,
    wm.pad_name,
    CASE WHEN wm.inventory_class = 'PDP'
         THEN EXTRACT(YEAR FROM wm.first_production_date)::int
         ELSE 2050 END                AS fp_year,
    wm.tvd_td                         AS tvd,
    wm.md_td                          AS md,
    wm.lateral_length                 AS ll_ft,
    compl.proppant_loading            AS prop_load,   -- NULL for PDP (share gap)
    -- PUD ML highgrade attributes (oil stream; drives the erebor Highgrade tab)
    ml.spacing_score                  AS spacing_s,
    ml.spacing_tier                   AS spacing_t,
    ml.prior_depletion_score          AS deplet_s,
    ml.prior_depletion_tier           AS deplet_t,
    ml.completion_score               AS complet_s,
    ml.completion_tier                AS complet_t,
    rq.rock_quality_score             AS rqs,
    rq.rock_quality_tier              AS rqt,
    -- reserves / rates (30-yr horizon — verified identical to the old values)
    econ.eur_oil_30yr                 AS oil_eur,
    econ.eur_gas_30yr                 AS gas_eur,
    econ.eur_dry_gas_30yr             AS dgas_eur,
    econ.eur_ngl_30yr                 AS ngl_eur,
    econ.eur_water_30yr               AS water_eur,
    econ.ip_oil                       AS oil_ip,
    econ.ip_gas                       AS gas_ip,
    econ.ip_dry_gas                   AS dgas_ip,
    econ.ip_ngl                       AS ngl_ip,
    econ.ip_water                     AS water_ip,
    econ.ngl_yield,
    econ.ngl_shrink,
    -- economics (Novi pre-computed; SCREEN only)
    econ.npv5::double precision       AS npv5,
    econ.npv10::double precision      AS npv10,
    econ.npv15::double precision      AS npv15,
    econ.npv20::double precision      AS npv20,
    econ.npv25::double precision      AS npv25,
    econ.pv5::double precision        AS pv5,
    econ.pv10::double precision       AS pv10,
    econ.pv15::double precision       AS pv15,
    econ.pv20::double precision       AS pv20,
    econ.pv25::double precision       AS pv25,
    econ.npv5_breakeven               AS npv5_be,
    econ.npv10_breakeven              AS npv10_be,
    econ.npv15_breakeven              AS npv15_be,
    econ.npv20_breakeven              AS npv20_be,
    econ.npv25_breakeven              AS npv25_be,
    econ.breakeven_1yr                AS be_1yr,
    econ.breakeven_2yr                AS be_2yr,
    econ.breakeven_3yr                AS be_3yr,
    -- IRR normalized to PERCENT via slice_irr (see header — the share's IRR
    -- unit is inconsistent by slice, same disease as the old vendor files)
    CASE WHEN si.med < 0.05 THEN econ.irr * 10000 ELSE econ.irr * 100 END
                                      AS irr_pct,
    econ.irr                          AS irr_pct_raw,   -- source value for audit
    econ.payback_months::double precision        AS pp_months,
    econ.double_payback_months::double precision AS ttpt,
    cost.total_dc_cost::double precision              AS dc_cost,
    cost.total_dcet_cost::double precision            AS dcet_cost,
    cost.normalized_dc_cost_per_ft::double precision  AS norm_dc,
    cost.normalized_dcet_cost_per_ft::double precision AS norm_dcet,
    -- flat price deck (via econ price_deck_id)
    epa.oil_price                     AS wti_price,
    epa.gas_price                     AS hh_price,
    epa.ngl_price                     AS ngl_price,
    epa.oil_price_differential        AS wti_diff,
    epa.gas_price_differential        AS hh_diff,
    CASE WHEN econ.well_ref IS NOT NULL THEN 'Yes' ELSE 'No' END AS has_econ,
    NULL::double precision            AS conf_int,     -- no share source
    pn.pad_npv25,
    -- gunbarrel endpoints (now cover PDP too — the old analytics join was
    -- name-keyed and failed for PDP)
    wm.subbasin,
    wb.heelpoint_latitude             AS heel_lat,
    wb.heelpoint_longitude            AS heel_lon,
    wb.midpoint_latitude              AS midpoint_lat,
    wb.midpoint_longitude             AS midpoint_lon,
    wb.bottom_hole_latitude           AS bh_lat,
    wb.bottom_hole_longitude          AS bh_lon,
    wm.geom                           AS wellstick_geom
FROM raw_intel.well_master wm
JOIN raw_intel.stick_id_map m0 ON m0.well_ref = wm.well_ref
LEFT JOIN curated.wells w      ON w.api10 = wm.uwi_api
LEFT JOIN econ  ON econ.well_ref = wm.well_ref AND econ.report_name = wm.report_name
LEFT JOIN cost  ON cost.well_ref = wm.well_ref AND cost.report_name = wm.report_name
LEFT JOIN wb    ON wb.well_ref = wm.well_ref AND wb.report_name = wm.report_name
LEFT JOIN compl ON compl.well_ref = wm.well_ref AND compl.report_name = wm.report_name
LEFT JOIN ml    ON ml.well_ref = wm.well_ref AND ml.report_name = wm.report_name
LEFT JOIN rq    ON rq.well_ref = wm.well_ref AND rq.report_name = wm.report_name
LEFT JOIN slice_irr si
       ON si.basin_slug = wm.basin_slug AND si.inventory_class = wm.inventory_class
LEFT JOIN raw_intel.econ_price_assumption epa
       ON epa.price_deck_id = econ.price_deck_id AND epa.report_name = wm.report_name
LEFT JOIN pad_npv pn
       ON pn.report_name = wm.report_name AND pn.pad_name = wm.pad_name
-- END INTEL_LOCATIONS_SELECT
;

-- Unique key required for REFRESH ... CONCURRENTLY.
CREATE UNIQUE INDEX idx_intel_locations_pk ON curated.intel_locations (stick_id);
CREATE INDEX idx_intel_locations_geom      ON curated.intel_locations USING GIST (wellstick_geom);
CREATE INDEX idx_intel_locations_basin_cat ON curated.intel_locations (basin, category);
CREATE INDEX idx_intel_locations_formation ON curated.intel_locations (formation);
CREATE INDEX idx_intel_locations_uid       ON curated.intel_locations (unique_id);
CREATE INDEX idx_intel_locations_api10     ON curated.intel_locations (api10) WHERE api10 IS NOT NULL;
CREATE INDEX idx_intel_locations_pad       ON curated.intel_locations (basin, pad_name);

COMMENT ON MATERIALIZED VIEW curated.intel_locations IS
  'Novi Intelligence sticks (PDP/PUD/RES) for erebor deal valuation, sourced '
  'from the INTEL Snowflake share mirror (raw_intel, sql/27). Same output '
  'contract as the retired sql/12 version: irr_pct in percent, pad NPV rollup '
  '(SUM of member sticks), api10 crosswalk to curated.wells (PDP), gunbarrel '
  'points (all classes), GIST-indexed wellstick_geom, stable stick_id via '
  'raw_intel.stick_id_map. Economics are Novi pre-computed on a flat deck — '
  'a screen, not the authoritative deal value.';

-- -----------------------------------------------------------------------------
-- intel_arps — segmented decline parameters, old column names preserved.
-- novi_wellname resolves through planned_well (share arps covers planned wells
-- only, same as the old layer's effective coverage). planned_well_id exposes
-- the share's well_ref (text, lineage); well_inventory_name has no share
-- source -> NULL.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS curated.intel_arps CASCADE;
CREATE VIEW curated.intel_arps AS
SELECT af.basin_slug                     AS basin,
       pw.name                           AS novi_wellname,
       af.stream                         AS production_stream,
       af.segment_number                 AS segment,
       af.segment_curve_type,
       af.b_factor                       AS b,
       af.nominal_decline_rate           AS d_nom,
       af.effective_decline_rate_secant  AS d_eff_secant,
       af.effective_decline_rate_tangent AS d_eff_tangent,
       af.segment_start_rate             AS q_start,
       af.segment_end_rate               AS q_stop,
       af.terminal_transition_day        AS terminal_day,
       af.day_start,
       af.day_stop,
       af.well_ref                       AS planned_well_id,
       NULL::text                        AS well_inventory_name
FROM raw_intel.arps_forecast af
JOIN raw_intel.planned_well pw
  ON af.well_ref = 'PW-' || pw.planned_well_id::text
 AND af.report_name = pw.report_name;

-- -----------------------------------------------------------------------------
-- intel_forecast — monthly production forecast passthrough (planned wells).
-- Same shape as before: query pattern WHERE novi_wellname = ANY(...) pushes to
-- idx_ri_planned_well_name then idx_ri_forecast_planned. Empty until the
-- post-cutover forecast load (phase-4 option C).
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS curated.intel_forecast CASCADE;
CREATE VIEW curated.intel_forecast AS
SELECT pf.basin_slug        AS basin,
       pw.name              AS novi_wellname,
       pf.forecast_day      AS ip_day,
       (pf.forecast_day / 30)::int AS mop,
       pf.oil_per_day       AS oil,
       pf.gas_per_day       AS gas,
       pf.water_per_day     AS water
FROM raw_intel.production_forecast pf
JOIN raw_intel.planned_well pw
  ON pw.planned_well_id = pf.planned_well_id
 AND pw.report_name = pf.report_name;

-- -----------------------------------------------------------------------------
-- curated.refresh_all() is deliberately NOT redefined here (sql/12 used to,
-- with a body that predated sql/06's producing_reference / formation_blueox_tvd
-- / erebor_locations refreshes — redefining from this file would downgrade it).
-- The authoritative body lives in sql/06; scripts/apply_erebor_locations, the
-- canonical final step of the quarterly rebuild, reinstates it.
-- -----------------------------------------------------------------------------
