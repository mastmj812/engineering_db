-- =============================================================================
-- 12 — curated.intel_*: canonical Novi Intelligence layer for the erebor app
--
-- Built on raw_novi_intel.* (sql/11). Three objects:
--   curated.intel_locations  MATERIALIZED VIEW — the core. One row per stick
--       (248k), normalized across the Delaware/Midland schema drift, with:
--         * irr_pct normalized to PERCENT via a self-calibrating per-slice rule
--         * api10 crosswalk to curated.wells (PDP only)
--         * pad-level NPV rollup joined from raw_novi_intel.pads
--         * analytics-derived heel/mid/bh points + subbasin (PUD/RES; for gunbarrel)
--         * wellstick_geom (GIST-indexed) for AOI spatial selection
--   curated.intel_arps       VIEW — passthrough of segmented decline params
--   curated.intel_forecast   VIEW — passthrough of the ~74M-row monthly stream
--       (NOT materialized; the app filters by novi_wellname against the raw GIST/btree
--        indexes, so a 74M-row materialized join would be pure cost)
--
-- Economics here are Novi's pre-computed deal economics on a single flat price deck
-- ($75 WTI / $3 HH); the app surfaces them as a SCREEN, not the authoritative value.
--
-- RUN: scripts/load_novi_intel.py --curated  (executes this file via psycopg).
-- Idempotent: DROP ... IF EXISTS then CREATE.
-- =============================================================================

DROP MATERIALIZED VIEW IF EXISTS curated.intel_locations CASCADE;

CREATE MATERIALIZED VIEW curated.intel_locations AS
WITH slice_irr AS (
    -- Per (basin, category) median |irr_pct|. Delaware PUD/RES are stored as
    -- percent (median ~75); every other slice is a fraction (median <1). A
    -- threshold of 5 cleanly separates them and survives future drops.
    SELECT basin, category,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(irr_pct)) AS med
    FROM raw_novi_intel.sticks
    WHERE irr_pct IS NOT NULL
    GROUP BY basin, category
),
pad_npv AS (
    -- One NPV25 per (basin, pad_name); guard against any duplicate pad rows.
    SELECT basin, pad_name, max(npv25) AS pad_npv25
    FROM raw_novi_intel.pads
    WHERE pad_name IS NOT NULL
    GROUP BY basin, pad_name
)
SELECT
    s.stick_id,                                    -- unique key (for CONCURRENTLY refresh)
    s.basin,
    s.report_version,
    s.category,                                    -- PDP | PUD | RES
    s.src_layer,
    s.unique_id,                                   -- API10 (PDP) or Novi well name (PUD/RES)
    s.api10,                                       -- non-null for PDP
    (w.api10 IS NOT NULL)            AS pdp_in_warehouse,   -- PDP matched curated.wells?
    -- identity / geology / completion
    s.phase, s.operator, s.formation, s.county, s.pad_name,
    s.fp_year, s.tvd, s.md, s.ll_ft, s.prop_load,
    -- PUD ML highgrade attributes (sql/13; NULL for PDP/RES). Scores are signed
    -- ML floats; tiers are 'Tier-1'..'Tier-4'. Drives the erebor Highgrade tab.
    pa.spacing_s, pa.spacing_t, pa.deplet_s, pa.deplet_t,
    pa.complet_s, pa.complet_t, pa.rqs, pa.rqt,
    -- reserves / rates
    s.oil_eur, s.gas_eur, s.dgas_eur, s.ngl_eur, s.water_eur,
    s.oil_ip, s.gas_ip, s.dgas_ip, s.ngl_ip, s.water_ip,
    s.ngl_yield, s.ngl_shrink,
    -- economics (Novi pre-computed; SCREEN only)
    s.npv5, s.npv10, s.npv15, s.npv20, s.npv25,
    s.pv5, s.pv10, s.pv15, s.pv20, s.pv25,
    s.npv5_be, s.npv10_be, s.npv15_be, s.npv20_be, s.npv25_be,
    s.be_1yr, s.be_2yr, s.be_3yr,
    -- IRR normalized to PERCENT (see slice_irr)
    CASE WHEN si.med > 5 THEN s.irr_pct ELSE s.irr_pct * 100 END  AS irr_pct,
    s.irr_pct                        AS irr_pct_raw,       -- keep source value for audit
    s.pp_months, s.ttpt,
    s.dc_cost, s.dcet_cost, s.norm_dc, s.norm_dcet,
    -- flat price deck (per stick)
    s.wti_price, s.hh_price, s.ngl_price, s.wti_diff, s.hh_diff,
    s.has_econ, s.conf_int,
    -- pad-level NPV rollup (PUD/RES; PDP pad_name is a placeholder so NULL)
    pn.pad_npv25,
    -- analytics-derived geometry endpoints (PUD/RES; gunbarrel inputs). PDP joins
    -- by name fail (api-keyed) — use curated.wells.wellstick_geom for PDP instead.
    a.subbasin,
    a.heel_lat, a.heel_lon, a.midpoint_lat, a.midpoint_lon, a.bh_lat, a.bh_lon,
    s.geom                           AS wellstick_geom
FROM raw_novi_intel.sticks s
LEFT JOIN slice_irr si       ON si.basin = s.basin AND si.category = s.category
LEFT JOIN curated.wells w    ON w.api10 = s.api10
LEFT JOIN pad_npv pn         ON pn.basin = s.basin AND pn.pad_name = s.pad_name
LEFT JOIN raw_novi_intel.analytics a
                             ON a.basin = s.basin AND a.well_name = s.unique_id
LEFT JOIN raw_novi_intel.pud_attrs pa
                             ON pa.basin = s.basin
                            AND pa.report_version = s.report_version
                            AND pa.unique_id = s.unique_id;

-- Unique key required for REFRESH ... CONCURRENTLY.
CREATE UNIQUE INDEX idx_intel_locations_pk ON curated.intel_locations (stick_id);
CREATE INDEX idx_intel_locations_geom      ON curated.intel_locations USING GIST (wellstick_geom);
CREATE INDEX idx_intel_locations_basin_cat ON curated.intel_locations (basin, category);
CREATE INDEX idx_intel_locations_formation ON curated.intel_locations (formation);
CREATE INDEX idx_intel_locations_uid       ON curated.intel_locations (unique_id);
CREATE INDEX idx_intel_locations_api10     ON curated.intel_locations (api10) WHERE api10 IS NOT NULL;
CREATE INDEX idx_intel_locations_pad       ON curated.intel_locations (basin, pad_name);

COMMENT ON MATERIALIZED VIEW curated.intel_locations IS
  'Novi Intelligence sticks (PDP/PUD/RES) for erebor deal valuation: normalized economics '
  '(irr_pct in percent), pad NPV rollup, api10 crosswalk to curated.wells (PDP), gunbarrel '
  'points (PUD/RES), GIST-indexed wellstick_geom. Economics are Novi pre-computed on a flat '
  'deck — a screen, not the authoritative deal value.';

-- -----------------------------------------------------------------------------
-- intel_arps — segmented decline parameters (thin passthrough; raw is clean)
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS curated.intel_arps CASCADE;
CREATE VIEW curated.intel_arps AS
SELECT basin, novi_wellname, production_stream, segment, segment_curve_type,
       b, d_nom, d_eff_secant, d_eff_tangent, q_start, q_stop,
       terminal_day, day_start, day_stop, planned_well_id, well_inventory_name
FROM raw_novi_intel.arps;

-- -----------------------------------------------------------------------------
-- intel_forecast — ~74M-row monthly production stream (passthrough VIEW).
-- Query pattern: WHERE novi_wellname = ANY(<selected wells>) — pushes to the
-- raw btree index. mop = months-on-production (30-day step -> month index).
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS curated.intel_forecast CASCADE;
CREATE VIEW curated.intel_forecast AS
SELECT basin, novi_wellname, ip_day,
       (ip_day / 30)::int AS mop,
       oil, gas, water
FROM raw_novi_intel.forecast;

-- -----------------------------------------------------------------------------
-- Wire intel_locations into curated.refresh_all() (preserving the existing
-- refreshes from sql/10). intel_arps/intel_forecast are plain views — nothing
-- to refresh. The Intelligence data is quarterly, so this refresh is a cheap
-- no-op on nightly runs until the next drop.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION curated.refresh_all()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.wells;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.formation_blueox;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production_normalized;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.type_curve_cohorts;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.production_forecast;
    REFRESH MATERIALIZED VIEW CONCURRENTLY curated.intel_locations;
    RAISE NOTICE 'curated.refresh_all() complete: wells, formation_blueox, production, production_normalized, type_curve_cohorts, production_forecast, intel_locations';
END;
$$ LANGUAGE plpgsql;
