-- =============================================================================
-- sql/31_comments.sql - warehouse data-dictionary comments
-- =============================================================================
-- COMMENT ON coverage for the consumer surface: column-level for all of
-- curated.*, table-level for raw_novi / raw_enverus / raw_intel /
-- raw_novi_intel / ref / meta. These comments ARE the data catalog: they
-- render in Supabase Studio, DBeaver, pgAdmin, QGIS, and feed
-- scripts/gen_data_dictionary.py (docs/DATA_DICTIONARY.md).
--
-- Idempotent (COMMENT ON overwrites). RE-RUN AFTER ANY MATVIEW DROP+CREATE:
-- the quarterly Novi intel reload CASCADE-drops the intel-derived matviews
-- and their comments with them - apply_erebor_locations.py re-applies this
-- file as its final step (same pattern as sql/26 geography indexes).
--
-- Maintenance: new column -> add its COMMENT here in the same change.
-- =============================================================================

-- =============================================================================
-- sql/31 (part A) -- generated COMMENT ON coverage for six curated relations:
--   curated.wells, curated.wells_enriched, curated.formation_blueox,
--   curated.formation_blueox_tvd, curated.bench_reference,
--   curated.producing_reference
-- Idempotent: COMMENT ON overwrites. Re-apply after any DROP/recreate of these
-- relations (comments do not survive a matview rebuild).
-- =============================================================================

-- curated.wells ------------------------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.wells IS 'One row per wellbore, keyed api10 (unique). Novi Wells + WellDetails + WellSpacing LEFT JOINed to the latest Enverus completion event via LEFT(api14, 10) = api10; per-column source precedence is Novi preferred, Enverus fallback unless noted. Permian-wide (~90k rows). Refreshed nightly by etl.refresh / curated.refresh_all() after the vendor loads.';
COMMENT ON COLUMN curated.wells.api10 IS '10-digit API wellbore id (Novi); the universal well key across the suite. PK / unique index. Novi-Enverus join convention: LEFT(api14, 10) = api10.';
COMMENT ON COLUMN curated.wells.api14 IS 'Formatted 14-digit API/UWI from the latest Enverus completion row; legacy cross-reference only (api10 is the key). NULL when no Enverus match.';
COMMENT ON COLUMN curated.wells.api14_unformatted IS 'Digits-only Enverus 14-digit API; LEFT(api14_unformatted, 10) is the join key back to api10.';
COMMENT ON COLUMN curated.wells.enverus_wellid IS 'Enverus WellID of the matched wellbore; NULL when the well has no Enverus row.';
COMMENT ON COLUMN curated.wells.enverus_latest_completionid IS 'Enverus CompletionID of the latest completion event per wellbore (DISTINCT ON api10 ordered by completiondate DESC).';
COMMENT ON COLUMN curated.wells.well_name IS 'Well name; Novi WellDetails preferred, then Novi Wells, then Enverus.';
COMMENT ON COLUMN curated.wells.well_pad_id IS 'Enverus WellPadID grouping wells drilled from a shared pad; NULL without an Enverus match.';
COMMENT ON COLUMN curated.wells.current_operator IS 'Current operator (Novi authoritative; tracks operator changes across A&D).';
COMMENT ON COLUMN curated.wells.original_operator IS 'Operator at drill time (Novi).';
COMMENT ON COLUMN curated.wells.operator_entity IS 'Parent operator entity (Novi CurrentOperatorEntity) for corporate-level rollups across subsidiary names.';
COMMENT ON COLUMN curated.wells.state IS 'State (Novi WellDetails preferred, Novi Wells fallback).';
COMMENT ON COLUMN curated.wells.state_code IS 'State FIPS code (Novi); 42 = TX, 30 = NM.';
COMMENT ON COLUMN curated.wells.county IS 'County name, title-cased per Novi convention (e.g. Reeves) - note Enverus filter values are UPPERCASE (LOVING), so do not reuse these strings in Enverus API filters.';
COMMENT ON COLUMN curated.wells.county_unique IS 'County name disambiguated across states (Novi CountyUnique).';
COMMENT ON COLUMN curated.wells.county_code IS '5-digit county FIPS code (Novi); a primary cohort key downstream.';
COMMENT ON COLUMN curated.wells.basin IS 'Novi basin classification (Novi WellDetails preferred). Vendor taxonomy; the standardized token is basin_blueox in wells_enriched.';
COMMENT ON COLUMN curated.wells.subbasin IS 'Novi sub-basin (Delaware / Midland / Central Basin Platform ...); the primary input for resolving basin_blueox.';
COMMENT ON COLUMN curated.wells.env_region IS 'Enverus ENVRegion (warehouse scope filter is envregion = PERMIAN).';
COMMENT ON COLUMN curated.wells.env_basin IS 'Enverus ENVBasin - sub-basin grain (DELAWARE / MIDLAND / PERMIAN OTHER; no umbrella PERMIAN value). Fallback for basin_blueox resolution.';
COMMENT ON COLUMN curated.wells.env_play IS 'Enverus ENVPlay classification (vendor taxonomy, UPPERCASE).';
COMMENT ON COLUMN curated.wells.env_sub_play IS 'Enverus ENVSubPlay classification (vendor taxonomy, UPPERCASE).';
COMMENT ON COLUMN curated.wells.env_interval IS 'Enverus ENVInterval landing-interval call from their structure model (UPPERCASE); the substitute source for formation_blueox when the Novi formation is coarse/unreliable.';
COMMENT ON COLUMN curated.wells.section IS 'Land-survey section number (Novi WellDetails); populated for both NM PLSS and TX survey systems.';
COMMENT ON COLUMN curated.wells.township IS 'PLSS Township (Novi WellDetails); NM-style land subdivision, empty in TX.';
COMMENT ON COLUMN curated.wells.range_ IS 'PLSS Range (NM-style land subdivision). Trailing underscore avoids the contextually-reserved SQL keyword. Populated only for PLSS states; ~0% in TX, ~20% Permian-wide.';
COMMENT ON COLUMN curated.wells.tx_block IS 'TX Spanish-grant land system: Block (Novi WellDetails); NULL for NM/PLSS wells.';
COMMENT ON COLUMN curated.wells.tx_survey IS 'TX Spanish-grant land system: Survey name (Novi WellDetails); NULL for NM/PLSS wells.';
COMMENT ON COLUMN curated.wells.tx_abstract IS 'TX Spanish-grant land system: Abstract number (Novi WellDetails); NULL for NM/PLSS wells.';
COMMENT ON COLUMN curated.wells.surface_lat IS 'Surface hole latitude, WGS84 deg (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells.surface_lon IS 'Surface hole longitude, WGS84 deg (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells.bhl_lat IS 'Bottom hole latitude, WGS84 deg (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells.bhl_lon IS 'Bottom hole longitude, WGS84 deg (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells.landing_point_lat IS 'Landing point latitude, WGS84 deg (Novi WellDetails only; Enverus has no LP).';
COMMENT ON COLUMN curated.wells.landing_point_lon IS 'Landing point longitude, WGS84 deg (Novi WellDetails only).';
COMMENT ON COLUMN curated.wells.midpoint_lat IS 'Lateral midpoint latitude, WGS84 deg (Novi WellDetails only).';
COMMENT ON COLUMN curated.wells.midpoint_lon IS 'Lateral midpoint longitude, WGS84 deg (Novi WellDetails only).';
COMMENT ON COLUMN curated.wells.wellstick_geom IS 'LINESTRING (4326) built from the four Novi locations Surface Hole -> Landing Point -> Midpoint -> Bottom Hole, in natural traverse order. NULL points are skipped; NULL if fewer than two valid points. Cast to geography only via the sql/26 expression GiST indexes.';
COMMENT ON COLUMN curated.wells.formation IS 'Novi formation call (WellDetails preferred, Wells fallback). RAW FREE-TEXT, inconsistent granularity - never group or filter on this; use formation_blueox (wells_enriched).';
COMMENT ON COLUMN curated.wells.reported_formation IS 'Operator-reported formation from the regulatory filing (Novi); free-text, often coarser than the model call.';
COMMENT ON COLUMN curated.wells.grid_formation IS 'Formation implied by Novi structure grids at the landing depth (Novi); free-text, model-derived.';
COMMENT ON COLUMN curated.wells.directional_survey_is_planned IS 'TRUE = the directional survey is the operator''s pre-drill PLAN, not the actual post-drill survey. Both Novi and Enverus land the well off that plan, so formation / env_interval are likely misassigned; ~46% of NM wells. Self-corrects when the actual survey is filed.';
COMMENT ON COLUMN curated.wells.tvd_ft IS 'True vertical depth, ft (Novi WellDetails > Novi Wells > Enverus). Exact multiples of 100 ft are usually permit/plan depths, not real landings - see curated.formation_blueox_tvd.';
COMMENT ON COLUMN curated.wells.md_ft IS 'Measured depth, ft (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells.lateral_length_ft IS 'Completed lateral length, ft (Novi preferred, Enverus fallback); the denominator for every per-1000-ft normalization downstream.';
COMMENT ON COLUMN curated.wells.wellbore_lateral_length_ft IS 'Novi WellboreLateralLength, ft - geometric wellbore lateral, as distinct from the completed lateral_length_ft.';
COMMENT ON COLUMN curated.wells.enverus_trajectory IS 'Enverus Trajectory string (e.g. HORIZONTAL); fallback source for wells_enriched.is_horizontal.';
COMMENT ON COLUMN curated.wells.novi_slant_calculated IS 'Novi SlantCalculated slant string (H... = horizontal); preferred source for wells_enriched.is_horizontal.';
COMMENT ON COLUMN curated.wells.spud_date IS 'Spud date (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells.drilling_end_date IS 'Drilling end (rig release) date (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells.first_completion_date IS 'First completion date (Novi preferred, Enverus fallback); drives completion_vintage_bucket.';
COMMENT ON COLUMN curated.wells.first_production_date IS 'First production date (Novi-calculated preferred, Enverus fallback). NULL = not yet producing; the producing_reference / reconciliation population keys on NOT NULL here.';
COMMENT ON COLUMN curated.wells.has_accurate_first_prod_date IS 'Novi confidence flag that first_production_date is accurate rather than inferred.';
COMMENT ON COLUMN curated.wells.last_reported_month IS 'Most recent month with reported production (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells.plugged_date IS 'Plug date (Novi preferred, Enverus fallback); NULL = not plugged.';
COMMENT ON COLUMN curated.wells.proppant_lbs IS 'Total proppant placed, lbs (Enverus preferred; Novi FirstCompletionProppantMass fallback).';
COMMENT ON COLUMN curated.wells.fluid_bbl IS 'Total frac fluid pumped, bbl (Enverus preferred; Novi FirstCompletionFluidVolume reported in gallons is divided by 42 in the fallback).';
COMMENT ON COLUMN curated.wells.frac_stages IS 'Frac stage count (Enverus preferred, Novi FirstCompletionStages fallback).';
COMMENT ON COLUMN curated.wells.proppant_lbs_per_ft IS 'Proppant intensity, lbs per lateral ft (Enverus only; no Novi fallback).';
COMMENT ON COLUMN curated.wells.fluid_bbl_per_ft IS 'Fluid intensity, bbl per lateral ft (Enverus only; no Novi fallback).';
COMMENT ON COLUMN curated.wells.proppant_lbs_per_gal IS 'Proppant loading, lbs per gallon of fluid (Enverus preferred, Novi fallback).';
COMMENT ON COLUMN curated.wells.avg_stage_spacing_ft IS 'Average frac stage spacing, ft (Enverus preferred, Novi fallback).';
COMMENT ON COLUMN curated.wells.clusters_per_stage IS 'Perforation clusters per frac stage (Enverus).';
COMMENT ON COLUMN curated.wells.clusters_per_1000ft IS 'Perforation clusters per 1000 ft of lateral (Enverus).';
COMMENT ON COLUMN curated.wells.soak_time_days IS 'Soak time, days, between stimulation and turn-in-line (Novi WellDetails SoakTimeDays).';
COMMENT ON COLUMN curated.wells.cum_12m_oil_bbl IS 'Cumulative oil through production month 12, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_12m_gas_mcf IS 'Cumulative gas through production month 12, Mcf (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_12m_water_bbl IS 'Cumulative water through production month 12, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_12m_boe IS 'Cumulative BOE through production month 12, bbl at 6:1 gas conversion (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_24m_oil_bbl IS 'Cumulative oil through production month 24, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_24m_gas_mcf IS 'Cumulative gas through production month 24, Mcf (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_24m_water_bbl IS 'Cumulative water through production month 24, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_24m_boe IS 'Cumulative BOE through production month 24, bbl at 6:1 (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_life_oil_bbl IS 'Life-to-date cumulative oil, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_life_gas_mcf IS 'Life-to-date cumulative gas, Mcf (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_life_water_bbl IS 'Life-to-date cumulative water, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_life_boe IS 'Life-to-date cumulative BOE, bbl at 6:1 (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells.cum_life_gor IS 'Life-to-date gas-oil ratio, Mcf/bbl (= cum_life_gas_mcf / cum_life_oil_bbl; multiply by 1000 for scf/bbl). Novi WellDetails CumLifeGOR pass-through.';
COMMENT ON COLUMN curated.wells.eur_20yr_oil_bbl IS 'Novi-forecast oil EUR at a 20-yr horizon, bbl (WellDetails pass-through). Vendor screen; the suite''s EUR of record is the raw 50-yr integral fit in anduin.';
COMMENT ON COLUMN curated.wells.eur_20yr_gas_mcf IS 'Novi-forecast gas EUR at a 20-yr horizon, Mcf (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells.eur_20yr_water_bbl IS 'Novi-forecast water EUR at a 20-yr horizon, bbl (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells.eur_20yr_boe IS 'Novi-forecast BOE EUR at a 20-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells.eur_30yr_oil_bbl IS 'Novi-forecast oil EUR at a 30-yr horizon, bbl (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells.eur_30yr_gas_mcf IS 'Novi-forecast gas EUR at a 30-yr horizon, Mcf (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells.eur_30yr_water_bbl IS 'Novi-forecast water EUR at a 30-yr horizon, bbl (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells.eur_30yr_boe IS 'Novi-forecast BOE EUR at a 30-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells.eur_50yr_oil_bbl IS 'Novi-forecast oil EUR at a 50-yr horizon, bbl (WellDetails pass-through). Same horizon as the suite convention, but this is Novi''s number, not the anduin fit.';
COMMENT ON COLUMN curated.wells.eur_50yr_gas_mcf IS 'Novi-forecast gas EUR at a 50-yr horizon, Mcf (WellDetails pass-through); vendor number, not the anduin fit.';
COMMENT ON COLUMN curated.wells.eur_50yr_water_bbl IS 'Novi-forecast water EUR at a 50-yr horizon, bbl (WellDetails pass-through); vendor number, not the anduin fit.';
COMMENT ON COLUMN curated.wells.eur_50yr_boe IS 'Novi-forecast BOE EUR at a 50-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor number, not the anduin fit.';
COMMENT ON COLUMN curated.wells.peak_month_oil IS 'Month-on-production index of the peak OIL month (Novi). Streams peak independently - gas typically ~4 months after oil, water in flowback - so each stream anchors on its own peak.';
COMMENT ON COLUMN curated.wells.peak_month_gas IS 'Month-on-production index of the peak GAS month (Novi); commonly ~4 months after the oil peak - never force gas to the oil peak.';
COMMENT ON COLUMN curated.wells.peak_month_water IS 'Month-on-production index of the peak WATER month (Novi); typically month 1 (flowback).';
COMMENT ON COLUMN curated.wells.peak_month_boe IS 'Month-on-production index of the peak BOE month (Novi).';
COMMENT ON COLUMN curated.wells.peak_oil_rate_bblpd IS 'Oil rate in the peak oil month, bbl/d (Novi PeakMonthOilRate pass-through).';
COMMENT ON COLUMN curated.wells.peak_gas_rate_mcfpd IS 'Gas rate in the peak gas month, Mcf/d (Novi PeakMonthGasRate pass-through).';
COMMENT ON COLUMN curated.wells.peak_water_rate_bblpd IS 'Water rate in the peak water month, bbl/d (Novi PeakMonthWaterRate pass-through).';
COMMENT ON COLUMN curated.wells.peak_boe_rate_boepd IS 'BOE rate in the peak BOE month, BOE/d at 6:1 (Novi PeakMonthBOERate pass-through).';
COMMENT ON COLUMN curated.wells.months_to_peak_production IS 'Months from first production to peak production (Enverus MonthsToPeakProduction).';
COMMENT ON COLUMN curated.wells.closest_well_xy_ft IS 'Horizontal (XY) distance to the closest neighbouring well, ft (Novi WellSpacing).';
COMMENT ON COLUMN curated.wells.wells_in_radius IS 'Count of wells inside Novi WellSpacing''s neighbourhood search radius.';
COMMENT ON COLUMN curated.wells.closest_two_avg_xy_ft IS 'Mean XY distance to the two closest neighbouring wells, ft (Novi WellSpacing).';
COMMENT ON COLUMN curated.wells.is_child IS 'Novi WellSpacing flag: TRUE = child well, offset to at least one pre-existing (parent) producer at drill time.';
COMMENT ON COLUMN curated.wells.parent_count IS 'Number of parent wells already producing in the neighbourhood when this well came online (Novi WellSpacing).';
COMMENT ON COLUMN curated.wells.boundedness_score IS 'Novi WellSpacing boundedness score - vendor score of how bounded the well is by neighbours; a rank, not footage.';
COMMENT ON COLUMN curated.wells.well_status IS 'Well status (Novi preferred, Enverus ENVWellStatus fallback); vendor strings, not standardized.';
COMMENT ON COLUMN curated.wells.well_type IS 'Well type, e.g. OIL / GAS (Novi preferred, Enverus ENVWellType fallback).';
COMMENT ON COLUMN curated.wells.has_production_sharing IS 'Novi flag: TRUE = production is shared/allocated across wells (allocation reporting), so per-well monthly volumes are allocated estimates, not measured.';
COMMENT ON COLUMN curated.wells.novi_synthetic_api IS 'TRUE = Novi minted a synthetic api10 (no state-assigned API on file yet); the key can change when the real API is assigned.';

-- curated.wells_enriched ---------------------------------------------------
COMMENT ON VIEW curated.wells_enriched IS 'Analytics view over curated.wells (one row per api10): joins the Blue Ox formation mapping (curated.formation_blueox) with the sql/23 TVD correction applied on top, and adds vintage, lateral-length-class, horizontal-flag and per-stage intensity derivations. Regular view - no refresh; current as of the nightly matview refreshes it reads.';
COMMENT ON COLUMN curated.wells_enriched.api10 IS '10-digit API wellbore id (Novi); the universal well key across the suite. PK / unique index. Novi-Enverus join convention: LEFT(api14, 10) = api10.';
COMMENT ON COLUMN curated.wells_enriched.api14 IS 'Formatted 14-digit API/UWI from the latest Enverus completion row; legacy cross-reference only (api10 is the key). NULL when no Enverus match.';
COMMENT ON COLUMN curated.wells_enriched.api14_unformatted IS 'Digits-only Enverus 14-digit API; LEFT(api14_unformatted, 10) is the join key back to api10.';
COMMENT ON COLUMN curated.wells_enriched.enverus_wellid IS 'Enverus WellID of the matched wellbore; NULL when the well has no Enverus row.';
COMMENT ON COLUMN curated.wells_enriched.enverus_latest_completionid IS 'Enverus CompletionID of the latest completion event per wellbore (DISTINCT ON api10 ordered by completiondate DESC).';
COMMENT ON COLUMN curated.wells_enriched.well_name IS 'Well name; Novi WellDetails preferred, then Novi Wells, then Enverus.';
COMMENT ON COLUMN curated.wells_enriched.well_pad_id IS 'Enverus WellPadID grouping wells drilled from a shared pad; NULL without an Enverus match.';
COMMENT ON COLUMN curated.wells_enriched.current_operator IS 'Current operator (Novi authoritative; tracks operator changes across A&D).';
COMMENT ON COLUMN curated.wells_enriched.original_operator IS 'Operator at drill time (Novi).';
COMMENT ON COLUMN curated.wells_enriched.operator_entity IS 'Parent operator entity (Novi CurrentOperatorEntity) for corporate-level rollups across subsidiary names.';
COMMENT ON COLUMN curated.wells_enriched.state IS 'State (Novi WellDetails preferred, Novi Wells fallback).';
COMMENT ON COLUMN curated.wells_enriched.state_code IS 'State FIPS code (Novi); 42 = TX, 30 = NM.';
COMMENT ON COLUMN curated.wells_enriched.county IS 'County name, title-cased per Novi convention (e.g. Reeves) - note Enverus filter values are UPPERCASE (LOVING), so do not reuse these strings in Enverus API filters.';
COMMENT ON COLUMN curated.wells_enriched.county_unique IS 'County name disambiguated across states (Novi CountyUnique).';
COMMENT ON COLUMN curated.wells_enriched.county_code IS '5-digit county FIPS code (Novi); a primary cohort key downstream.';
COMMENT ON COLUMN curated.wells_enriched.basin IS 'Novi basin classification (Novi WellDetails preferred). Vendor taxonomy; the standardized token is basin_blueox in wells_enriched.';
COMMENT ON COLUMN curated.wells_enriched.subbasin IS 'Novi sub-basin (Delaware / Midland / Central Basin Platform ...); the primary input for resolving basin_blueox.';
COMMENT ON COLUMN curated.wells_enriched.env_region IS 'Enverus ENVRegion (warehouse scope filter is envregion = PERMIAN).';
COMMENT ON COLUMN curated.wells_enriched.env_basin IS 'Enverus ENVBasin - sub-basin grain (DELAWARE / MIDLAND / PERMIAN OTHER; no umbrella PERMIAN value). Fallback for basin_blueox resolution.';
COMMENT ON COLUMN curated.wells_enriched.env_play IS 'Enverus ENVPlay classification (vendor taxonomy, UPPERCASE).';
COMMENT ON COLUMN curated.wells_enriched.env_sub_play IS 'Enverus ENVSubPlay classification (vendor taxonomy, UPPERCASE).';
COMMENT ON COLUMN curated.wells_enriched.env_interval IS 'Enverus ENVInterval landing-interval call from their structure model (UPPERCASE); the substitute source for formation_blueox when the Novi formation is coarse/unreliable.';
COMMENT ON COLUMN curated.wells_enriched.section IS 'Land-survey section number (Novi WellDetails); populated for both NM PLSS and TX survey systems.';
COMMENT ON COLUMN curated.wells_enriched.township IS 'PLSS Township (Novi WellDetails); NM-style land subdivision, empty in TX.';
COMMENT ON COLUMN curated.wells_enriched.range_ IS 'PLSS Range (NM-style land subdivision). Trailing underscore avoids the contextually-reserved SQL keyword. Populated only for PLSS states; ~0% in TX, ~20% Permian-wide.';
COMMENT ON COLUMN curated.wells_enriched.tx_block IS 'TX Spanish-grant land system: Block (Novi WellDetails); NULL for NM/PLSS wells.';
COMMENT ON COLUMN curated.wells_enriched.tx_survey IS 'TX Spanish-grant land system: Survey name (Novi WellDetails); NULL for NM/PLSS wells.';
COMMENT ON COLUMN curated.wells_enriched.tx_abstract IS 'TX Spanish-grant land system: Abstract number (Novi WellDetails); NULL for NM/PLSS wells.';
COMMENT ON COLUMN curated.wells_enriched.surface_lat IS 'Surface hole latitude, WGS84 deg (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells_enriched.surface_lon IS 'Surface hole longitude, WGS84 deg (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells_enriched.bhl_lat IS 'Bottom hole latitude, WGS84 deg (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells_enriched.bhl_lon IS 'Bottom hole longitude, WGS84 deg (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells_enriched.landing_point_lat IS 'Landing point latitude, WGS84 deg (Novi WellDetails only; Enverus has no LP).';
COMMENT ON COLUMN curated.wells_enriched.landing_point_lon IS 'Landing point longitude, WGS84 deg (Novi WellDetails only).';
COMMENT ON COLUMN curated.wells_enriched.midpoint_lat IS 'Lateral midpoint latitude, WGS84 deg (Novi WellDetails only).';
COMMENT ON COLUMN curated.wells_enriched.midpoint_lon IS 'Lateral midpoint longitude, WGS84 deg (Novi WellDetails only).';
COMMENT ON COLUMN curated.wells_enriched.wellstick_geom IS 'LINESTRING (4326) built from the four Novi locations Surface Hole -> Landing Point -> Midpoint -> Bottom Hole, in natural traverse order. NULL points are skipped; NULL if fewer than two valid points. Cast to geography only via the sql/26 expression GiST indexes.';
COMMENT ON COLUMN curated.wells_enriched.formation IS 'Novi formation call (WellDetails preferred, Wells fallback). RAW FREE-TEXT, inconsistent granularity - never group or filter on this; use formation_blueox (wells_enriched).';
COMMENT ON COLUMN curated.wells_enriched.reported_formation IS 'Operator-reported formation from the regulatory filing (Novi); free-text, often coarser than the model call.';
COMMENT ON COLUMN curated.wells_enriched.grid_formation IS 'Formation implied by Novi structure grids at the landing depth (Novi); free-text, model-derived.';
COMMENT ON COLUMN curated.wells_enriched.directional_survey_is_planned IS 'TRUE = the directional survey is the operator''s pre-drill PLAN, not the actual post-drill survey. Both Novi and Enverus land the well off that plan, so formation / env_interval are likely misassigned; ~46% of NM wells. Self-corrects when the actual survey is filed.';
COMMENT ON COLUMN curated.wells_enriched.tvd_ft IS 'True vertical depth, ft (Novi WellDetails > Novi Wells > Enverus). Exact multiples of 100 ft are usually permit/plan depths, not real landings - see curated.formation_blueox_tvd.';
COMMENT ON COLUMN curated.wells_enriched.md_ft IS 'Measured depth, ft (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells_enriched.lateral_length_ft IS 'Completed lateral length, ft (Novi preferred, Enverus fallback); the denominator for every per-1000-ft normalization downstream.';
COMMENT ON COLUMN curated.wells_enriched.wellbore_lateral_length_ft IS 'Novi WellboreLateralLength, ft - geometric wellbore lateral, as distinct from the completed lateral_length_ft.';
COMMENT ON COLUMN curated.wells_enriched.enverus_trajectory IS 'Enverus Trajectory string (e.g. HORIZONTAL); fallback source for wells_enriched.is_horizontal.';
COMMENT ON COLUMN curated.wells_enriched.novi_slant_calculated IS 'Novi SlantCalculated slant string (H... = horizontal); preferred source for wells_enriched.is_horizontal.';
COMMENT ON COLUMN curated.wells_enriched.spud_date IS 'Spud date (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells_enriched.drilling_end_date IS 'Drilling end (rig release) date (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells_enriched.first_completion_date IS 'First completion date (Novi preferred, Enverus fallback); drives completion_vintage_bucket.';
COMMENT ON COLUMN curated.wells_enriched.first_production_date IS 'First production date (Novi-calculated preferred, Enverus fallback). NULL = not yet producing; the producing_reference / reconciliation population keys on NOT NULL here.';
COMMENT ON COLUMN curated.wells_enriched.has_accurate_first_prod_date IS 'Novi confidence flag that first_production_date is accurate rather than inferred.';
COMMENT ON COLUMN curated.wells_enriched.last_reported_month IS 'Most recent month with reported production (Novi preferred, Enverus fallback).';
COMMENT ON COLUMN curated.wells_enriched.plugged_date IS 'Plug date (Novi preferred, Enverus fallback); NULL = not plugged.';
COMMENT ON COLUMN curated.wells_enriched.proppant_lbs IS 'Total proppant placed, lbs (Enverus preferred; Novi FirstCompletionProppantMass fallback).';
COMMENT ON COLUMN curated.wells_enriched.fluid_bbl IS 'Total frac fluid pumped, bbl (Enverus preferred; Novi FirstCompletionFluidVolume reported in gallons is divided by 42 in the fallback).';
COMMENT ON COLUMN curated.wells_enriched.frac_stages IS 'Frac stage count (Enverus preferred, Novi FirstCompletionStages fallback).';
COMMENT ON COLUMN curated.wells_enriched.proppant_lbs_per_ft IS 'Proppant intensity, lbs per lateral ft (Enverus only; no Novi fallback).';
COMMENT ON COLUMN curated.wells_enriched.fluid_bbl_per_ft IS 'Fluid intensity, bbl per lateral ft (Enverus only; no Novi fallback).';
COMMENT ON COLUMN curated.wells_enriched.proppant_lbs_per_gal IS 'Proppant loading, lbs per gallon of fluid (Enverus preferred, Novi fallback).';
COMMENT ON COLUMN curated.wells_enriched.avg_stage_spacing_ft IS 'Average frac stage spacing, ft (Enverus preferred, Novi fallback).';
COMMENT ON COLUMN curated.wells_enriched.clusters_per_stage IS 'Perforation clusters per frac stage (Enverus).';
COMMENT ON COLUMN curated.wells_enriched.clusters_per_1000ft IS 'Perforation clusters per 1000 ft of lateral (Enverus).';
COMMENT ON COLUMN curated.wells_enriched.soak_time_days IS 'Soak time, days, between stimulation and turn-in-line (Novi WellDetails SoakTimeDays).';
COMMENT ON COLUMN curated.wells_enriched.cum_12m_oil_bbl IS 'Cumulative oil through production month 12, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_12m_gas_mcf IS 'Cumulative gas through production month 12, Mcf (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_12m_water_bbl IS 'Cumulative water through production month 12, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_12m_boe IS 'Cumulative BOE through production month 12, bbl at 6:1 gas conversion (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_24m_oil_bbl IS 'Cumulative oil through production month 24, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_24m_gas_mcf IS 'Cumulative gas through production month 24, Mcf (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_24m_water_bbl IS 'Cumulative water through production month 24, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_24m_boe IS 'Cumulative BOE through production month 24, bbl at 6:1 (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_life_oil_bbl IS 'Life-to-date cumulative oil, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_life_gas_mcf IS 'Life-to-date cumulative gas, Mcf (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_life_water_bbl IS 'Life-to-date cumulative water, bbl (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_life_boe IS 'Life-to-date cumulative BOE, bbl at 6:1 (Novi WellDetails pass-through).';
COMMENT ON COLUMN curated.wells_enriched.cum_life_gor IS 'Life-to-date gas-oil ratio, Mcf/bbl (= cum_life_gas_mcf / cum_life_oil_bbl; multiply by 1000 for scf/bbl). Novi WellDetails CumLifeGOR pass-through.';
COMMENT ON COLUMN curated.wells_enriched.eur_20yr_oil_bbl IS 'Novi-forecast oil EUR at a 20-yr horizon, bbl (WellDetails pass-through). Vendor screen; the suite''s EUR of record is the raw 50-yr integral fit in anduin.';
COMMENT ON COLUMN curated.wells_enriched.eur_20yr_gas_mcf IS 'Novi-forecast gas EUR at a 20-yr horizon, Mcf (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells_enriched.eur_20yr_water_bbl IS 'Novi-forecast water EUR at a 20-yr horizon, bbl (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells_enriched.eur_20yr_boe IS 'Novi-forecast BOE EUR at a 20-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells_enriched.eur_30yr_oil_bbl IS 'Novi-forecast oil EUR at a 30-yr horizon, bbl (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells_enriched.eur_30yr_gas_mcf IS 'Novi-forecast gas EUR at a 30-yr horizon, Mcf (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells_enriched.eur_30yr_water_bbl IS 'Novi-forecast water EUR at a 30-yr horizon, bbl (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells_enriched.eur_30yr_boe IS 'Novi-forecast BOE EUR at a 30-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor screen.';
COMMENT ON COLUMN curated.wells_enriched.eur_50yr_oil_bbl IS 'Novi-forecast oil EUR at a 50-yr horizon, bbl (WellDetails pass-through). Same horizon as the suite convention, but this is Novi''s number, not the anduin fit.';
COMMENT ON COLUMN curated.wells_enriched.eur_50yr_gas_mcf IS 'Novi-forecast gas EUR at a 50-yr horizon, Mcf (WellDetails pass-through); vendor number, not the anduin fit.';
COMMENT ON COLUMN curated.wells_enriched.eur_50yr_water_bbl IS 'Novi-forecast water EUR at a 50-yr horizon, bbl (WellDetails pass-through); vendor number, not the anduin fit.';
COMMENT ON COLUMN curated.wells_enriched.eur_50yr_boe IS 'Novi-forecast BOE EUR at a 50-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor number, not the anduin fit.';
COMMENT ON COLUMN curated.wells_enriched.peak_month_oil IS 'Month-on-production index of the peak OIL month (Novi). Streams peak independently - gas typically ~4 months after oil, water in flowback - so each stream anchors on its own peak.';
COMMENT ON COLUMN curated.wells_enriched.peak_month_gas IS 'Month-on-production index of the peak GAS month (Novi); commonly ~4 months after the oil peak - never force gas to the oil peak.';
COMMENT ON COLUMN curated.wells_enriched.peak_month_water IS 'Month-on-production index of the peak WATER month (Novi); typically month 1 (flowback).';
COMMENT ON COLUMN curated.wells_enriched.peak_month_boe IS 'Month-on-production index of the peak BOE month (Novi).';
COMMENT ON COLUMN curated.wells_enriched.peak_oil_rate_bblpd IS 'Oil rate in the peak oil month, bbl/d (Novi PeakMonthOilRate pass-through).';
COMMENT ON COLUMN curated.wells_enriched.peak_gas_rate_mcfpd IS 'Gas rate in the peak gas month, Mcf/d (Novi PeakMonthGasRate pass-through).';
COMMENT ON COLUMN curated.wells_enriched.peak_water_rate_bblpd IS 'Water rate in the peak water month, bbl/d (Novi PeakMonthWaterRate pass-through).';
COMMENT ON COLUMN curated.wells_enriched.peak_boe_rate_boepd IS 'BOE rate in the peak BOE month, BOE/d at 6:1 (Novi PeakMonthBOERate pass-through).';
COMMENT ON COLUMN curated.wells_enriched.months_to_peak_production IS 'Months from first production to peak production (Enverus MonthsToPeakProduction).';
COMMENT ON COLUMN curated.wells_enriched.closest_well_xy_ft IS 'Horizontal (XY) distance to the closest neighbouring well, ft (Novi WellSpacing).';
COMMENT ON COLUMN curated.wells_enriched.wells_in_radius IS 'Count of wells inside Novi WellSpacing''s neighbourhood search radius.';
COMMENT ON COLUMN curated.wells_enriched.closest_two_avg_xy_ft IS 'Mean XY distance to the two closest neighbouring wells, ft (Novi WellSpacing).';
COMMENT ON COLUMN curated.wells_enriched.is_child IS 'Novi WellSpacing flag: TRUE = child well, offset to at least one pre-existing (parent) producer at drill time.';
COMMENT ON COLUMN curated.wells_enriched.parent_count IS 'Number of parent wells already producing in the neighbourhood when this well came online (Novi WellSpacing).';
COMMENT ON COLUMN curated.wells_enriched.boundedness_score IS 'Novi WellSpacing boundedness score - vendor score of how bounded the well is by neighbours; a rank, not footage.';
COMMENT ON COLUMN curated.wells_enriched.well_status IS 'Well status (Novi preferred, Enverus ENVWellStatus fallback); vendor strings, not standardized.';
COMMENT ON COLUMN curated.wells_enriched.well_type IS 'Well type, e.g. OIL / GAS (Novi preferred, Enverus ENVWellType fallback).';
COMMENT ON COLUMN curated.wells_enriched.has_production_sharing IS 'Novi flag: TRUE = production is shared/allocated across wells (allocation reporting), so per-well monthly volumes are allocated estimates, not measured.';
COMMENT ON COLUMN curated.wells_enriched.novi_synthetic_api IS 'TRUE = Novi minted a synthetic api10 (no state-assigned API on file yet); the key can change when the real API is assigned.';
COMMENT ON COLUMN curated.wells_enriched.formation_blueox IS 'Blue Ox canonical bench code WITH the TVD-outlier correction applied (sql/23 flips gross depth outliers). THE grouping/filter key - never raw formation. NULL = unmapped (report as (unmapped)); OTHER = CBP conventional shelf by design.';
COMMENT ON COLUMN curated.wells_enriched.formation_blueox_base IS 'Pre-correction Blue Ox code straight from curated.formation_blueox; kept for audit of TVD-corrected flips. Differs from formation_blueox only when formation_blueox_tvd_corrected.';
COMMENT ON COLUMN curated.wells_enriched.formation_blueox_raw IS 'Raw formation string that fed the crosswalk (Novi formation or Enverus ENVInterval, per the sql/16 precedence rule).';
COMMENT ON COLUMN curated.wells_enriched.formation_blueox_source IS 'Winning source for the bench code: novi, enverus, or tvd_corrected when the sql/23 depth audit overrode both.';
COMMENT ON COLUMN curated.wells_enriched.basin_blueox IS 'Blue Ox basin token: delaware, midland or cbp (from Novi Subbasin, Enverus ENVBasin fallback); NULL when the well is outside all three.';
COMMENT ON COLUMN curated.wells_enriched.formation_blueox_is_mapped IS 'TRUE = the raw string matched ref.formation_crosswalk. FALSE = genuine crosswalk gap in delaware/midland, but intentional OTHER bucketing in cbp (not a gap).';
COMMENT ON COLUMN curated.wells_enriched.formation_blueox_tvd_corrected IS 'TRUE = curated.formation_blueox_tvd flipped the bench because the well is a gross local depth outlier (~0.4% of producers); base value preserved in formation_blueox_base.';
COMMENT ON COLUMN curated.wells_enriched.first_completion_year IS 'Calendar year of first_completion_date.';
COMMENT ON COLUMN curated.wells_enriched.first_completion_quarter IS 'Calendar quarter (1-4) of first_completion_date.';
COMMENT ON COLUMN curated.wells_enriched.first_production_year IS 'Calendar year of first_production_date.';
COMMENT ON COLUMN curated.wells_enriched.completion_vintage_bucket IS 'Completion vintage cohort: pre-2017 / 2017-2019 / 2020-2022 / 2023+ (from first_completion_date); a standard type-curve cohort key.';
COMMENT ON COLUMN curated.wells_enriched.lateral_length_class IS 'Lateral length bin, ft: <5000 / 5000-7499 / 7500-9999 / 10000-14999 / 15000+; NULL when lateral_length_ft is missing or non-positive.';
COMMENT ON COLUMN curated.wells_enriched.is_horizontal IS 'TRUE when the slant string starts with H (Novi SlantCalculated preferred, Enverus trajectory fallback); NULL when both sources are missing.';
COMMENT ON COLUMN curated.wells_enriched.stages_per_1000ft IS 'Frac stages per 1000 ft of lateral (frac_stages * 1000 / lateral_length_ft); NULL when either input is missing/non-positive.';
COMMENT ON COLUMN curated.wells_enriched.proppant_lbs_per_stage IS 'Proppant per frac stage, lbs (proppant_lbs / frac_stages).';
COMMENT ON COLUMN curated.wells_enriched.fluid_bbl_per_stage IS 'Frac fluid per stage, bbl (fluid_bbl / frac_stages).';
COMMENT ON COLUMN curated.wells_enriched.has_completion_intensity IS 'TRUE when proppant_lbs, fluid_bbl, frac_stages and a positive lateral_length_ft are all populated - the cohort filter for completion-intensity studies.';

-- curated.formation_blueox -------------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.formation_blueox IS 'Blue Ox standardized formation mapping, one row per curated.wells api10 (~90k rows). Sources: Novi formation preferred, Enverus ENVInterval substituted for coarse Novi values; mapped via ref.formation_crosswalk. Factored out of curated.wells so crosswalk edits are a cheap REFRESH, not a production-chain DROP CASCADE. Refreshed nightly by etl.refresh / curated.refresh_all().';
COMMENT ON COLUMN curated.formation_blueox.api10 IS 'Universal well key (Novi 10-digit API); unique index supports REFRESH CONCURRENTLY.';
COMMENT ON COLUMN curated.formation_blueox.formation_blueox_raw IS 'Raw formation string selected by the precedence rule - Novi formation normally, Enverus ENVInterval when the Novi value is coarse/unreliable - before crosswalk mapping.';
COMMENT ON COLUMN curated.formation_blueox.formation_blueox_source IS 'Source of the selected raw string: novi or enverus. Enverus wins on trigger values (WOLFCAMP A/B variants, LOWER SPRABERRY SAND, generic WOLFCAMP/BONE SPRING(S)/SPRABERRY/UNKNOWN, SUB-WOODFORD); NULL when both sources are empty.';
COMMENT ON COLUMN curated.formation_blueox.basin_blueox IS 'Blue Ox basin token: delaware, midland or cbp - from Novi Subbasin, falling back to Enverus ENVBasin; NULL outside the three nomenclature basins.';
COMMENT ON COLUMN curated.formation_blueox.formation_blueox IS 'Blue Ox canonical bench code mapped via ref.formation_crosswalk on (basin_blueox, raw_value). NULL = crosswalk gap (delaware/midland, review); OTHER = unmapped CBP conventional shelf by design. Group/filter on this, never raw formation.';
COMMENT ON COLUMN curated.formation_blueox.formation_blueox_is_mapped IS 'TRUE = the crosswalk matched the raw string. FALSE rows are genuine gaps in delaware/midland but intentional in cbp (bucketed to OTHER).';

-- curated.formation_blueox_tvd ---------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.formation_blueox_tvd IS 'TVD-sanity audit, one row per producing horizontal (api10): local 40-NN per-bench depth bands vs the assigned formation_blueox, flipping only gross depth outliers (e.g. Enverus-substitution mis-tags). Audit object - the override is applied downstream in curated.wells_enriched. Refreshed nightly by etl.refresh / curated.refresh_all() after producing_reference.';
COMMENT ON COLUMN curated.formation_blueox_tvd.api10 IS 'Universal well key (Novi 10-digit API); one row per producing horizontal in curated.producing_reference with TVD and a bench code.';
COMMENT ON COLUMN curated.formation_blueox_tvd.basin IS 'Blue Ox basin token (delaware/midland) carried from curated.producing_reference.';
COMMENT ON COLUMN curated.formation_blueox_tvd.assigned_code IS 'Blue Ox bench assigned by curated.formation_blueox (sql/16) BEFORE this depth audit.';
COMMENT ON COLUMN curated.formation_blueox_tvd.tvd IS 'Well true vertical depth, ft (curated.wells.tvd_ft).';
COMMENT ON COLUMN curated.formation_blueox_tvd.assigned_med IS 'Local median TVD, ft, of the well''s assigned bench among its 40 nearest producing neighbours (same basin; permit-round x100 depths excluded from the band).';
COMMENT ON COLUMN curated.formation_blueox_tvd.assigned_n IS 'Neighbour count behind assigned_med; a flip requires >= 5 so the home band is well established.';
COMMENT ON COLUMN curated.formation_blueox_tvd.nearest_code IS 'Bench whose local median TVD is closest to the well''s TVD, among neighbour bands with >= 3 wells.';
COMMENT ON COLUMN curated.formation_blueox_tvd.nearest_med IS 'Local median TVD, ft, of the depth-nearest bench (nearest_code).';
COMMENT ON COLUMN curated.formation_blueox_tvd.nearest_n IS 'Neighbour count behind nearest_med; a flip requires >= 3.';
COMMENT ON COLUMN curated.formation_blueox_tvd.survey_planned IS 'TRUE = the directional survey on file is the operator''s pre-drill plan (DirectionalSurveyIsPlanned), so the TVD is provisional; ~44% of NM producers, ~0% TX.';
COMMENT ON COLUMN curated.formation_blueox_tvd.tvd_round IS 'TRUE = TVD is an exact multiple of 100 ft - the permit/plan-depth tell (a real survey reads 12415 ft, not 12000); ~3% of wells, the only tell in TX.';
COMMENT ON COLUMN curated.formation_blueox_tvd.permit_suspect IS 'tvd_round OR survey_planned: the depth is likely a permit number, so the outlier gap required to flip widens to 1000 ft (vs 600 ft for a trusted survey depth).';
COMMENT ON COLUMN curated.formation_blueox_tvd.assigned_gap IS 'abs(tvd - assigned_med), ft: how far the well sits from its own bench''s local depth band.';
COMMENT ON COLUMN curated.formation_blueox_tvd.nearest_gap IS 'abs(tvd - nearest_med), ft: distance to the depth-nearest bench''s local band.';
COMMENT ON COLUMN curated.formation_blueox_tvd.corrected IS 'TRUE = all flip guards passed: gap > 600/1000 ft, target band >= 400 ft closer, band support (5/3), no flips into/out of WDFD/BRNT/MISS or to OTHER, no sand<->carb swaps.';
COMMENT ON COLUMN curated.formation_blueox_tvd.corrected_code IS 'Bench of record after the audit: nearest_code when corrected, else assigned_code. Consumed by curated.wells_enriched as the canonical formation_blueox.';

-- curated.bench_reference --------------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.bench_reference IS 'Candidate pool for TVD-aware sub-bench inference: curated laterals in the splitting benches (Delaware AVA/WCA/WCB, Midland WCB; ~30k rows), one row per api10, pre-joined to formation_blueox and GiST-indexed on geom. Feeds curated.intel_formation_blueox (sql/19). Not in the nightly etl.refresh list - refresh manually alongside curated.formation_blueox / on the quarterly intel rebuild.';
COMMENT ON COLUMN curated.bench_reference.api10 IS 'Universal well key (Novi 10-digit API); unique index supports REFRESH CONCURRENTLY.';
COMMENT ON COLUMN curated.bench_reference.geom IS 'Wellstick LINESTRING (4326) from curated.wells; GiST-indexed as the <-> KNN driver for sub-bench inference.';
COMMENT ON COLUMN curated.bench_reference.tvd IS 'True vertical depth, ft (curated.wells.tvd_ft); NOT NULL by filter - the depth discriminator between stacked benches.';
COMMENT ON COLUMN curated.bench_reference.basin IS 'Blue Ox basin token (delaware or midland) from curated.formation_blueox.';
COMMENT ON COLUMN curated.bench_reference.bench IS 'Blue Ox sub-bench code: one of WCA_1, WCA_2, WCB_1, WCB_2, AVA_0, AVA_1, AVA_2 (only the parents that split).';
COMMENT ON COLUMN curated.bench_reference.parent IS '3-char parent group = left(bench, 3): WCA, WCB or AVA; the KNN recheck filter alongside basin.';

-- curated.producing_reference ----------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.producing_reference IS 'Producing curated wells (first_production_date NOT NULL, delaware/midland, mapped bench), one row per api10, pre-buffered into a +/-150 ft corridor and GiST-indexed. The spatial system of record for PUD reconciliation (curated.reconciled_inventory) and the sql/23 TVD audit: realized = co-extent overlap in-corridor, same bench, TVD-guarded. Refreshed nightly by etl.refresh / curated.refresh_all().';
COMMENT ON COLUMN curated.producing_reference.api10 IS 'Universal well key (Novi 10-digit API); unique index supports REFRESH CONCURRENTLY.';
COMMENT ON COLUMN curated.producing_reference.geom IS 'Wellstick LINESTRING (4326) from curated.wells; GiST-indexed to drive the <-> KNN depth profile in sql/23.';
COMMENT ON COLUMN curated.producing_reference.corridor IS 'Lateral buffered +/-150 ft (46 m on the geography, stored as geometry), GiST-indexed. Realization is co-extent OVERLAP of a PUD inside this corridor - never min distance, which false-positives on toe-to-heel laterals.';
COMMENT ON COLUMN curated.producing_reference.basin IS 'Blue Ox basin token (delaware or midland) from curated.formation_blueox.';
COMMENT ON COLUMN curated.producing_reference.code IS 'Blue Ox bench code from curated.formation_blueox (pre-TVD-correction); NOT NULL by filter - same-bench is required for a reconciliation match.';
COMMENT ON COLUMN curated.producing_reference.tvd IS 'True vertical depth, ft (curated.wells.tvd_ft); input to the sql/21 TVD guard and the sql/23 depth bands.';
COMMENT ON COLUMN curated.producing_reference.survey_planned IS 'TRUE = directional survey on file is the pre-drill plan, so tvd is provisional and will move when the actual survey lands; ~44% of NM producers, ~0% TX. Flags matches resting on permit depths.';
COMMENT ON COLUMN curated.producing_reference.first_production_date IS 'First production date (Novi preferred, Enverus fallback); NOT NULL by definition - this matview is the producing population.';
COMMENT ON COLUMN curated.producing_reference.operator IS 'Current operator (curated.wells.current_operator).';
COMMENT ON COLUMN curated.producing_reference.ll_ft IS 'Completed lateral length, ft (curated.wells.lateral_length_ft); denominator context for overlap fractions.';

-- =============================================================================
-- sql/31 (part B) - catalog COMMENTs for the curated production family:
--   curated.production, curated.production_normalized, curated.production_combined,
--   curated.type_curve_cohorts, curated.production_forecast
-- Sources of truth: sql/05_curated_production.sql, sql/06_curated_derived.sql,
-- sql/10_curated_forecast.sql. Idempotent: COMMENT ON overwrites in place.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- curated.production (matview; sql/05)
-- ---------------------------------------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.production IS 'Well-month production actuals from raw_novi.WellMonths (soft-deleted rows excluded), ~5M rows. Grain: one row per well-month; key (api10, prod_year, prod_month). Refreshed nightly by etl.refresh via curated.refresh_all(), per-view with settle().';
COMMENT ON COLUMN curated.production.api10 IS '10-digit API wellbore id (Novi convention) - the universal well key across the suite. Joins curated.wells.api10; Novi-Enverus join is LEFT(api14,10) = api10.';
COMMENT ON COLUMN curated.production.prod_year IS 'Calendar year of the production month; part of the composite key (api10, prod_year, prod_month).';
COMMENT ON COLUMN curated.production.prod_month IS 'Calendar month (1-12) of the production month; part of the composite key.';
COMMENT ON COLUMN curated.production.prod_date IS 'First day of the production month (date form of prod_year/prod_month).';
COMMENT ON COLUMN curated.production.operator IS 'Operator of record for THIS month. Novi tracks operator per-month, so a well''s operator changes mid-history when it is sold.';
COMMENT ON COLUMN curated.production.operator_entity IS 'Novi parent-entity roll-up of the monthly operator (aggregates subsidiaries to the corporate parent).';
COMMENT ON COLUMN curated.production.months_on_production IS 'Months since first production, 1-indexed (MoP 1 = first-production month). The type-curve alignment axis - wells align on MoP, not calendar date.';
COMMENT ON COLUMN curated.production.producing_days IS 'Days the well actually produced in the month. Month-1 exception: the partial first-prod month uses producing_days as the rate denominator; later months use calendar days.';
COMMENT ON COLUMN curated.production.cumulative_producing_days IS 'Running total of producing_days since first production, days.';
COMMENT ON COLUMN curated.production.oil_per_day_bbl IS 'Oil rate, bbl/d, CALENDAR-day denominator (Novi OilPerDay) - the fitting/aggregation convention; month-1 exception uses producing_days for the partial first month.';
COMMENT ON COLUMN curated.production.oil_per_month_bbl IS 'Oil volume produced in the month, bbl.';
COMMENT ON COLUMN curated.production.cumulative_oil_bbl IS 'Cumulative oil from first production through this month, bbl.';
COMMENT ON COLUMN curated.production.gas_per_day_mcf IS 'Gas rate, Mcf/d, calendar-day denominator (month-1 exception: producing_days). Gas commonly peaks ~4 months after oil - anchor gas fits on the gas peak, not the oil peak.';
COMMENT ON COLUMN curated.production.gas_per_month_mcf IS 'Gas volume produced in the month, Mcf.';
COMMENT ON COLUMN curated.production.cumulative_gas_mcf IS 'Cumulative gas from first production through this month, Mcf.';
COMMENT ON COLUMN curated.production.water_per_day_bbl IS 'Water rate, bbl/d, calendar-day denominator (month-1 exception: producing_days). Water typically peaks in flowback - anchor water fits on its own peak.';
COMMENT ON COLUMN curated.production.water_per_month_bbl IS 'Water volume produced in the month, bbl.';
COMMENT ON COLUMN curated.production.cumulative_water_bbl IS 'Cumulative water from first production through this month, bbl.';
COMMENT ON COLUMN curated.production.flared_gas_per_day_mcf IS 'Flared gas rate, Mcf/d, calendar-day denominator (Novi FlaredGasPerDay).';
COMMENT ON COLUMN curated.production.flared_gas_per_month_mcf IS 'Flared gas volume in the month, Mcf.';
COMMENT ON COLUMN curated.production.cumulative_flared_gas_mcf IS 'Cumulative flared gas from first production through this month, Mcf.';
COMMENT ON COLUMN curated.production.basin IS 'Novi basin label carried from WellMonths for filter-without-join (duplicated on curated.wells).';
COMMENT ON COLUMN curated.production.subbasin IS 'Novi sub-basin label (e.g. DELAWARE, MIDLAND, CENTRAL BASIN PLATFORM) carried from WellMonths.';
COMMENT ON COLUMN curated.production.is_oil_proprietary IS 'TRUE when the month''s oil volume came from Novi''s proprietary production-sharing source rather than state filings.';
COMMENT ON COLUMN curated.production.is_gas_proprietary IS 'TRUE when the month''s gas volume came from Novi''s proprietary production-sharing source rather than state filings.';
COMMENT ON COLUMN curated.production.is_gas_flared_proprietary IS 'TRUE when the month''s flared-gas volume came from Novi''s proprietary production-sharing source rather than state filings.';
COMMENT ON COLUMN curated.production.is_water_proprietary IS 'TRUE when the month''s water volume came from Novi''s proprietary production-sharing source rather than state filings.';

-- ---------------------------------------------------------------------------
-- curated.production_normalized (matview; sql/06)
-- ---------------------------------------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.production_normalized IS 'Actuals well-months: curated.production INNER JOIN curated.wells, adding BOE (oil + gas/6) and per-1,000-ft normalized rates plus cohort keys. Grain well-month; key (api10, prod_year, prod_month); MoP filtered 1-600. Refreshed nightly by etl.refresh after wells and production.';
COMMENT ON COLUMN curated.production_normalized.api10 IS '10-digit API wellbore id - universal well key; joins curated.wells.api10.';
COMMENT ON COLUMN curated.production_normalized.prod_year IS 'Calendar year of the production month; part of the composite key.';
COMMENT ON COLUMN curated.production_normalized.prod_month IS 'Calendar month (1-12) of the production month; part of the composite key.';
COMMENT ON COLUMN curated.production_normalized.prod_date IS 'First day of the production month.';
COMMENT ON COLUMN curated.production_normalized.months_on_production IS 'Months since first production, 1-indexed (MoP 1 = first-prod month); the type-curve alignment axis. Rows restricted to MoP 1-600.';
COMMENT ON COLUMN curated.production_normalized.producing_days IS 'Days actually produced in the month. Month-1 exception: partial first-prod month uses producing_days as the rate denominator.';
COMMENT ON COLUMN curated.production_normalized.oil_per_day_bbl IS 'Oil rate, bbl/d, calendar-day denominator (pass-through from curated.production; month-1 exception uses producing_days).';
COMMENT ON COLUMN curated.production_normalized.gas_per_day_mcf IS 'Gas rate, Mcf/d, calendar-day denominator (pass-through; month-1 exception uses producing_days).';
COMMENT ON COLUMN curated.production_normalized.water_per_day_bbl IS 'Water rate, bbl/d, calendar-day denominator (pass-through; month-1 exception uses producing_days).';
COMMENT ON COLUMN curated.production_normalized.oil_per_month_bbl IS 'Oil volume in the month, bbl.';
COMMENT ON COLUMN curated.production_normalized.gas_per_month_mcf IS 'Gas volume in the month, Mcf.';
COMMENT ON COLUMN curated.production_normalized.water_per_month_bbl IS 'Water volume in the month, bbl.';
COMMENT ON COLUMN curated.production_normalized.cumulative_oil_bbl IS 'Cumulative oil through this month, bbl.';
COMMENT ON COLUMN curated.production_normalized.cumulative_gas_mcf IS 'Cumulative gas through this month, Mcf.';
COMMENT ON COLUMN curated.production_normalized.cumulative_water_bbl IS 'Cumulative water through this month, bbl.';
COMMENT ON COLUMN curated.production_normalized.boe_per_day_bbl IS 'Synthetic BOE rate, bbl/d: oil_per_day_bbl + gas_per_day_mcf/6 (6:1 Mcf:bbl basis; water excluded).';
COMMENT ON COLUMN curated.production_normalized.boe_per_month_bbl IS 'Synthetic BOE volume in the month, bbl (oil + gas/6).';
COMMENT ON COLUMN curated.production_normalized.cumulative_boe_bbl IS 'Cumulative synthetic BOE through this month, bbl (cum oil + cum gas/6).';
COMMENT ON COLUMN curated.production_normalized.oil_per_day_per_1000ft IS 'Oil rate normalized per lateral length, bbl/d per 1,000 ft (rate x 1000 / lateral_length_ft); NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_normalized.gas_per_day_per_1000ft IS 'Gas rate normalized per lateral length, Mcf/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_normalized.water_per_day_per_1000ft IS 'Water rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_normalized.boe_per_day_per_1000ft IS 'BOE rate (oil + gas/6) normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_normalized.cumulative_oil_per_1000ft IS 'Cumulative oil normalized per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_normalized.cumulative_gas_per_1000ft IS 'Cumulative gas normalized per lateral length, Mcf per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_normalized.cumulative_water_per_1000ft IS 'Cumulative water normalized per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_normalized.cumulative_boe_per_1000ft IS 'Cumulative BOE (oil + gas/6) normalized per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_normalized.state_code IS 'State FIPS code - cohort key carried from curated.wells so aggregations avoid a re-JOIN.';
COMMENT ON COLUMN curated.production_normalized.county_code IS 'County FIPS code (5-char state+county), carried from curated.wells.';
COMMENT ON COLUMN curated.production_normalized.county IS 'County name, carried from curated.wells.';
COMMENT ON COLUMN curated.production_normalized.basin IS 'Novi basin label, carried from curated.wells.';
COMMENT ON COLUMN curated.production_normalized.subbasin IS 'Novi sub-basin label (DELAWARE / MIDLAND / CENTRAL BASIN PLATFORM), carried from curated.wells.';
COMMENT ON COLUMN curated.production_normalized.formation IS 'RAW Novi formation string (free-text UPPERCASE, e.g. SPRABERRY - no Y). For grouping/filtering use formation_blueox (via curated.wells_enriched), never this column.';
COMMENT ON COLUMN curated.production_normalized.lateral_length_ft IS 'Completed lateral length, ft, from curated.wells; the denominator of every per-1,000-ft column.';
COMMENT ON COLUMN curated.production_normalized.first_production_date IS 'Well-level first production date, from curated.wells.';
COMMENT ON COLUMN curated.production_normalized.first_completion_date IS 'Well-level first completion date, from curated.wells; basis for the vintage columns.';
COMMENT ON COLUMN curated.production_normalized.first_completion_year IS 'Calendar year of first_completion_date.';
COMMENT ON COLUMN curated.production_normalized.completion_vintage_bucket IS 'Completion vintage cohort bucket: pre-2017 / 2017-2019 / 2020-2022 / 2023+; NULL when first_completion_date is NULL.';
COMMENT ON COLUMN curated.production_normalized.lateral_length_class IS 'Lateral length bucket, ft: <5000 / 5000-7499 / 7500-9999 / 10000-14999 / 15000+; NULL when lateral_length_ft is missing or <= 0.';

-- ---------------------------------------------------------------------------
-- curated.type_curve_cohorts (matview; sql/06)
-- ---------------------------------------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.type_curve_cohorts IS 'Pre-aggregated type-curve cohorts over production_normalized: one row per (state_code, county_code, formation, completion_vintage_bucket, months_on_production), MoP 1-240. SPE percentile orientation (P10 = HIGH case, P90 = LOW; flipped 2026-07-10). Nightly etl.refresh.';
COMMENT ON COLUMN curated.type_curve_cohorts.state_code IS 'Cohort key: state FIPS code.';
COMMENT ON COLUMN curated.type_curve_cohorts.county_code IS 'Cohort key: county FIPS code (5-char state+county).';
COMMENT ON COLUMN curated.type_curve_cohorts.formation IS 'Cohort key: RAW Novi formation string (free-text) - NOT formation_blueox; blueox-grain cohorts must be computed upstream via wells_enriched.';
COMMENT ON COLUMN curated.type_curve_cohorts.completion_vintage_bucket IS 'Cohort key: completion vintage bucket (pre-2017 / 2017-2019 / 2020-2022 / 2023+).';
COMMENT ON COLUMN curated.type_curve_cohorts.months_on_production IS 'Cohort key: months since first production, 1-indexed; capped at 1-240 (20 yr) - beyond that samples are too sparse for fitting.';
COMMENT ON COLUMN curated.type_curve_cohorts.well_months IS 'Sample size: count of well-month rows aggregated in this cohort x MoP cell.';
COMMENT ON COLUMN curated.type_curve_cohorts.well_count IS 'Sample size: distinct wells contributing at this MoP. Filter on this for a statistical floor (e.g. >= 10) before treating the cell as a type curve.';
COMMENT ON COLUMN curated.type_curve_cohorts.p10_oil_per_day_per_1000ft IS 'P10 oil rate (SPE: HIGH case, 10% chance of exceeding), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.p25_oil_per_day_per_1000ft IS 'P25 oil rate (SPE: upper quartile), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.p50_oil_per_day_per_1000ft IS 'Median oil rate, bbl/d per 1,000 ft - the primary type-curve series.';
COMMENT ON COLUMN curated.type_curve_cohorts.p75_oil_per_day_per_1000ft IS 'P75 oil rate (SPE: lower quartile), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.p90_oil_per_day_per_1000ft IS 'P90 oil rate (SPE: LOW case, 90% chance of exceeding), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.mean_oil_per_day_per_1000ft IS 'Arithmetic mean oil rate, bbl/d per 1,000 ft; skews above p50 in right-tailed cohorts.';
COMMENT ON COLUMN curated.type_curve_cohorts.p10_boe_per_day_per_1000ft IS 'P10 BOE rate (oil + gas/6; SPE: HIGH case), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.p25_boe_per_day_per_1000ft IS 'P25 BOE rate (SPE: upper quartile), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.p50_boe_per_day_per_1000ft IS 'Median BOE rate (oil + gas/6), bbl/d per 1,000 ft - secondary series for gas-weighted cohorts.';
COMMENT ON COLUMN curated.type_curve_cohorts.p75_boe_per_day_per_1000ft IS 'P75 BOE rate (SPE: lower quartile), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.p90_boe_per_day_per_1000ft IS 'P90 BOE rate (SPE: LOW case), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.mean_boe_per_day_per_1000ft IS 'Arithmetic mean BOE rate (oil + gas/6), bbl/d per 1,000 ft.';
COMMENT ON COLUMN curated.type_curve_cohorts.p50_gas_per_day_per_1000ft IS 'Median gas rate, Mcf/d per 1,000 ft. Median only by design; other gas percentiles compute on the fly from production_normalized.';
COMMENT ON COLUMN curated.type_curve_cohorts.p50_water_per_day_per_1000ft IS 'Median water rate, bbl/d per 1,000 ft. Median only by design.';
COMMENT ON COLUMN curated.type_curve_cohorts.p50_cum_oil_per_1000ft IS 'Median cumulative oil at this MoP, bbl per 1,000 ft - cohort EUR sanity check (raw technical integral; no economic limit anywhere).';
COMMENT ON COLUMN curated.type_curve_cohorts.p50_cum_boe_per_1000ft IS 'Median cumulative BOE (oil + gas/6) at this MoP, bbl per 1,000 ft.';

-- ---------------------------------------------------------------------------
-- curated.production_forecast (matview; sql/10)
-- ---------------------------------------------------------------------------
COMMENT ON MATERIALIZED VIEW curated.production_forecast IS 'Novi ML P50 forecast tail (raw_novi.ForecastWellMonths, IsForecasted=TRUE, ~17M rows) JOINed to curated.wells and normalized per 1,000 ft; column-identical to production_normalized for clean UNION. Key (api10, prod_year, prod_month); MoP 1-600. Nightly refresh is gated on ForecastWellMonths source change and runs LAST.';
COMMENT ON COLUMN curated.production_forecast.api10 IS '10-digit API wellbore id - universal well key; joins curated.wells.api10.';
COMMENT ON COLUMN curated.production_forecast.prod_year IS 'Calendar year of the forecast month, derived from ForecastWellMonths Date; part of the composite key.';
COMMENT ON COLUMN curated.production_forecast.prod_month IS 'Calendar month (1-12) of the forecast month, derived from Date; part of the composite key.';
COMMENT ON COLUMN curated.production_forecast.prod_date IS 'First day of the forecast month.';
COMMENT ON COLUMN curated.production_forecast.months_on_production IS 'Months since first production, 1-indexed, continuing the actuals count; forecast rows start the month AFTER the well''s last actual, so low-MoP forecast population is sparse.';
COMMENT ON COLUMN curated.production_forecast.producing_days IS 'Always NULL - ForecastWellMonths has no producing-days analog; column kept for parity with production_normalized so the UNION in production_combined stays clean.';
COMMENT ON COLUMN curated.production_forecast.oil_per_day_bbl IS 'Forecast oil rate, bbl/d, calendar-day basis - Novi ML P50 projection, not an actual.';
COMMENT ON COLUMN curated.production_forecast.gas_per_day_mcf IS 'Forecast gas rate, Mcf/d, calendar-day basis - Novi ML P50 projection.';
COMMENT ON COLUMN curated.production_forecast.water_per_day_bbl IS 'Forecast water rate, bbl/d, calendar-day basis - Novi ML P50 projection.';
COMMENT ON COLUMN curated.production_forecast.oil_per_month_bbl IS 'Forecast oil volume in the month, bbl (integer-truncated in the Novi source).';
COMMENT ON COLUMN curated.production_forecast.gas_per_month_mcf IS 'Forecast gas volume in the month, Mcf (integer-truncated in the Novi source).';
COMMENT ON COLUMN curated.production_forecast.water_per_month_bbl IS 'Forecast water volume in the month, bbl (integer-truncated in the Novi source).';
COMMENT ON COLUMN curated.production_forecast.cumulative_oil_bbl IS 'Forecast cumulative oil through this month, bbl, continuing from the actuals history.';
COMMENT ON COLUMN curated.production_forecast.cumulative_gas_mcf IS 'Forecast cumulative gas through this month, Mcf, continuing from the actuals history.';
COMMENT ON COLUMN curated.production_forecast.cumulative_water_bbl IS 'Forecast cumulative water through this month, bbl, continuing from the actuals history.';
COMMENT ON COLUMN curated.production_forecast.boe_per_day_bbl IS 'Forecast synthetic BOE rate, bbl/d: oil + gas/6 (6:1 basis; water excluded).';
COMMENT ON COLUMN curated.production_forecast.boe_per_month_bbl IS 'Forecast synthetic BOE volume in the month, bbl (oil + gas/6).';
COMMENT ON COLUMN curated.production_forecast.cumulative_boe_bbl IS 'Forecast cumulative synthetic BOE, bbl (cum oil + cum gas/6).';
COMMENT ON COLUMN curated.production_forecast.oil_per_day_per_1000ft IS 'Forecast oil rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_forecast.gas_per_day_per_1000ft IS 'Forecast gas rate normalized per lateral length, Mcf/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_forecast.water_per_day_per_1000ft IS 'Forecast water rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_forecast.boe_per_day_per_1000ft IS 'Forecast BOE rate (oil + gas/6) per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_forecast.cumulative_oil_per_1000ft IS 'Forecast cumulative oil per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_forecast.cumulative_gas_per_1000ft IS 'Forecast cumulative gas per lateral length, Mcf per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_forecast.cumulative_water_per_1000ft IS 'Forecast cumulative water per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_forecast.cumulative_boe_per_1000ft IS 'Forecast cumulative BOE (oil + gas/6) per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_forecast.state_code IS 'State FIPS code, carried from curated.wells (identical derivation to production_normalized for cohort alignment).';
COMMENT ON COLUMN curated.production_forecast.county_code IS 'County FIPS code (5-char state+county), carried from curated.wells.';
COMMENT ON COLUMN curated.production_forecast.county IS 'County name, carried from curated.wells.';
COMMENT ON COLUMN curated.production_forecast.basin IS 'Novi basin label, carried from curated.wells.';
COMMENT ON COLUMN curated.production_forecast.subbasin IS 'Novi sub-basin label (DELAWARE / MIDLAND / CENTRAL BASIN PLATFORM), carried from curated.wells.';
COMMENT ON COLUMN curated.production_forecast.formation IS 'RAW Novi formation string (free-text UPPERCASE). For grouping/filtering use formation_blueox (via curated.wells_enriched), never this column.';
COMMENT ON COLUMN curated.production_forecast.lateral_length_ft IS 'Completed lateral length, ft, from curated.wells; denominator of every per-1,000-ft column.';
COMMENT ON COLUMN curated.production_forecast.first_production_date IS 'Well-level first production date, from curated.wells.';
COMMENT ON COLUMN curated.production_forecast.first_completion_date IS 'Well-level first completion date, from curated.wells; basis for the vintage columns.';
COMMENT ON COLUMN curated.production_forecast.first_completion_year IS 'Calendar year of first_completion_date.';
COMMENT ON COLUMN curated.production_forecast.completion_vintage_bucket IS 'Completion vintage cohort bucket: pre-2017 / 2017-2019 / 2020-2022 / 2023+; NULL when first_completion_date is NULL.';
COMMENT ON COLUMN curated.production_forecast.lateral_length_class IS 'Lateral length bucket, ft: <5000 / 5000-7499 / 7500-9999 / 10000-14999 / 15000+; NULL when lateral_length_ft is missing or <= 0.';

-- ---------------------------------------------------------------------------
-- curated.production_combined (regular VIEW; sql/10)
-- ---------------------------------------------------------------------------
COMMENT ON VIEW curated.production_combined IS 'Regular VIEW (no storage, always fresh): production_normalized actuals UNION ALL production_forecast (Novi ML P50 tail) with an is_forecast flag - one continuous per-well well-month timeline. Key (api10, prod_year, prod_month); actual and forecast months are disjoint per well.';
COMMENT ON COLUMN curated.production_combined.api10 IS '10-digit API wellbore id - universal well key; joins curated.wells.api10.';
COMMENT ON COLUMN curated.production_combined.prod_year IS 'Calendar year of the production/forecast month; part of the composite key.';
COMMENT ON COLUMN curated.production_combined.prod_month IS 'Calendar month (1-12); part of the composite key.';
COMMENT ON COLUMN curated.production_combined.prod_date IS 'First day of the month; per well, actuals then forecast form one contiguous date series.';
COMMENT ON COLUMN curated.production_combined.months_on_production IS 'Months since first production, 1-indexed; contiguous across the actual-to-forecast seam (forecast rows continue the actuals MoP count).';
COMMENT ON COLUMN curated.production_combined.producing_days IS 'Days actually produced in the month; populated on actual rows only, NULL on forecast rows.';
COMMENT ON COLUMN curated.production_combined.oil_per_day_bbl IS 'Oil rate, bbl/d, calendar-day basis; actual when is_forecast=FALSE (month-1 exception uses producing_days), Novi ML P50 projection when TRUE.';
COMMENT ON COLUMN curated.production_combined.gas_per_day_mcf IS 'Gas rate, Mcf/d, calendar-day basis; actual when is_forecast=FALSE, Novi ML P50 projection when TRUE.';
COMMENT ON COLUMN curated.production_combined.water_per_day_bbl IS 'Water rate, bbl/d, calendar-day basis; actual when is_forecast=FALSE, Novi ML P50 projection when TRUE.';
COMMENT ON COLUMN curated.production_combined.oil_per_month_bbl IS 'Oil volume in the month, bbl (actual or Novi ML P50 forecast per is_forecast).';
COMMENT ON COLUMN curated.production_combined.gas_per_month_mcf IS 'Gas volume in the month, Mcf (actual or Novi ML P50 forecast per is_forecast).';
COMMENT ON COLUMN curated.production_combined.water_per_month_bbl IS 'Water volume in the month, bbl (actual or Novi ML P50 forecast per is_forecast).';
COMMENT ON COLUMN curated.production_combined.cumulative_oil_bbl IS 'Cumulative oil through this month, bbl; forecast rows continue the actuals cumulative.';
COMMENT ON COLUMN curated.production_combined.cumulative_gas_mcf IS 'Cumulative gas through this month, Mcf; forecast rows continue the actuals cumulative.';
COMMENT ON COLUMN curated.production_combined.cumulative_water_bbl IS 'Cumulative water through this month, bbl; forecast rows continue the actuals cumulative.';
COMMENT ON COLUMN curated.production_combined.boe_per_day_bbl IS 'Synthetic BOE rate, bbl/d: oil + gas/6 (6:1 basis; water excluded); actual or forecast per is_forecast.';
COMMENT ON COLUMN curated.production_combined.boe_per_month_bbl IS 'Synthetic BOE volume in the month, bbl (oil + gas/6).';
COMMENT ON COLUMN curated.production_combined.cumulative_boe_bbl IS 'Cumulative synthetic BOE through this month, bbl (cum oil + cum gas/6).';
COMMENT ON COLUMN curated.production_combined.oil_per_day_per_1000ft IS 'Oil rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.gas_per_day_per_1000ft IS 'Gas rate normalized per lateral length, Mcf/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.water_per_day_per_1000ft IS 'Water rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.boe_per_day_per_1000ft IS 'BOE rate (oil + gas/6) per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.cumulative_oil_per_1000ft IS 'Cumulative oil per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.cumulative_gas_per_1000ft IS 'Cumulative gas per lateral length, Mcf per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.cumulative_water_per_1000ft IS 'Cumulative water per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.cumulative_boe_per_1000ft IS 'Cumulative BOE (oil + gas/6) per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.state_code IS 'State FIPS code, carried from curated.wells.';
COMMENT ON COLUMN curated.production_combined.county_code IS 'County FIPS code (5-char state+county), carried from curated.wells.';
COMMENT ON COLUMN curated.production_combined.county IS 'County name, carried from curated.wells.';
COMMENT ON COLUMN curated.production_combined.basin IS 'Novi basin label, carried from curated.wells.';
COMMENT ON COLUMN curated.production_combined.subbasin IS 'Novi sub-basin label (DELAWARE / MIDLAND / CENTRAL BASIN PLATFORM), carried from curated.wells.';
COMMENT ON COLUMN curated.production_combined.formation IS 'RAW Novi formation string (free-text UPPERCASE). For grouping/filtering use formation_blueox (via curated.wells_enriched), never this column.';
COMMENT ON COLUMN curated.production_combined.lateral_length_ft IS 'Completed lateral length, ft, from curated.wells; denominator of every per-1,000-ft column.';
COMMENT ON COLUMN curated.production_combined.first_production_date IS 'Well-level first production date, from curated.wells.';
COMMENT ON COLUMN curated.production_combined.first_completion_date IS 'Well-level first completion date, from curated.wells; basis for the vintage columns.';
COMMENT ON COLUMN curated.production_combined.first_completion_year IS 'Calendar year of first_completion_date.';
COMMENT ON COLUMN curated.production_combined.completion_vintage_bucket IS 'Completion vintage cohort bucket: pre-2017 / 2017-2019 / 2020-2022 / 2023+; NULL when first_completion_date is NULL.';
COMMENT ON COLUMN curated.production_combined.lateral_length_class IS 'Lateral length bucket, ft: <5000 / 5000-7499 / 7500-9999 / 10000-14999 / 15000+; NULL when lateral_length_ft is missing or <= 0.';
COMMENT ON COLUMN curated.production_combined.is_forecast IS 'FALSE = actual (production_normalized, from Novi WellMonths); TRUE = Novi ML P50 projection (production_forecast). Forecast rows begin the month after the well''s last actual.';

-- =============================================================================
-- 31 (part C) -- COMMENT ON statements: curated intel/reconciliation column
-- comments + raw_novi / raw_enverus / raw_intel / raw_novi_intel / ref / meta
-- table comments. Idempotent (COMMENT ON overwrites). One statement per line.
-- Skips relations whose table comment already exists (see catalog.json).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Part 1: column comments
-- ---------------------------------------------------------------------------

-- curated.intel_locations (matview, sql/29) -- read directly by the land team via GIS
COMMENT ON COLUMN curated.intel_locations.stick_id IS 'Stable unique id for this location. Always positive here (assigned from raw_intel.stick_id_map, so it survives quarterly Novi reloads). In erebor_locations, producing (PDP) rows instead use the negative of their API10.';
COMMENT ON COLUMN curated.intel_locations.basin IS 'Basin slug: delaware or midland.';
COMMENT ON COLUMN curated.intel_locations.report_version IS 'Novi Intelligence report vintage in share format, e.g. 2025Q3 (the old file-drop wrote 3Q25).';
COMMENT ON COLUMN curated.intel_locations.category IS 'Location class: PDP = producing well, PUD = Novi base-case undrilled location, RES = emerging/resource (more speculative) location.';
COMMENT ON COLUMN curated.intel_locations.src_layer IS 'Source report name in the Novi Snowflake share (e.g. basin_research__Delaware Basin__2025Q3); lineage only.';
COMMENT ON COLUMN curated.intel_locations.unique_id IS 'Row identifier for joins/exports: 10-digit API number for PDP rows, Novi well name for PUD/RES rows.';
COMMENT ON COLUMN curated.intel_locations.api10 IS '10-digit API well number; populated for PDP rows only (undrilled PUD/RES have no API). Universal well key across the suite.';
COMMENT ON COLUMN curated.intel_locations.pdp_in_warehouse IS 'TRUE when this PDP api10 also exists in curated.wells (the warehouse well header); FALSE/NULL means Novi lists a well the warehouse does not carry.';
COMMENT ON COLUMN curated.intel_locations.phase IS 'Target phase label; constant Oil for this inventory (carried from the legacy layer).';
COMMENT ON COLUMN curated.intel_locations.operator IS 'Operator name as reported by Novi (vendor spelling, not entity-normalized).';
COMMENT ON COLUMN curated.intel_locations.formation IS 'Novi target formation name (vendor free text, UPPERCASE-ish). For grouping/filtering use curated.intel_formation_blueox, not this.';
COMMENT ON COLUMN curated.intel_locations.county IS 'County name from the Novi share.';
COMMENT ON COLUMN curated.intel_locations.pad_name IS 'Novi DSU pad name. Share gap: populated only for Delaware PUD (BASE_CASE) as of 2025Q3; NULL elsewhere.';
COMMENT ON COLUMN curated.intel_locations.fp_year IS 'First-production year for PDP wells; 2050 placeholder for undrilled PUD/RES (the share has no planned TIL dates).';
COMMENT ON COLUMN curated.intel_locations.tvd IS 'True vertical depth at total depth, ft.';
COMMENT ON COLUMN curated.intel_locations.md IS 'Measured depth at total depth, ft.';
COMMENT ON COLUMN curated.intel_locations.ll_ft IS 'Lateral length, ft.';
COMMENT ON COLUMN curated.intel_locations.prop_load IS 'Planned proppant loading, lb per lateral ft. NULL for PDP (the share carries completion data for planned wells only).';
COMMENT ON COLUMN curated.intel_locations.spacing_s IS 'Novi ML spacing sensitivity SCORE (signed, unitless) -- NOT a spacing footage. Per-bench spacing footage is user-set in the apps.';
COMMENT ON COLUMN curated.intel_locations.spacing_t IS 'Novi ML spacing tier LABEL (Tier-1..Tier-4) -- NOT footage. Tier-1 = least spacing-degraded.';
COMMENT ON COLUMN curated.intel_locations.deplet_s IS 'Novi ML prior-depletion score (signed, unitless); how much offset production has drained this location.';
COMMENT ON COLUMN curated.intel_locations.deplet_t IS 'Novi depletion tier: Tier-1..Tier-4 where Tier-4 = most depleted (drained by offsets); also No Depletion. Drives the erebor depletion filter.';
COMMENT ON COLUMN curated.intel_locations.complet_s IS 'Novi ML completion-design score (signed, unitless).';
COMMENT ON COLUMN curated.intel_locations.complet_t IS 'Novi ML completion tier label (Tier-1..Tier-4).';
COMMENT ON COLUMN curated.intel_locations.rqs IS 'Novi ML rock-quality score (signed, unitless), oil stream.';
COMMENT ON COLUMN curated.intel_locations.rqt IS 'Novi ML rock-quality tier label (Tier-1..Tier-4).';
COMMENT ON COLUMN curated.intel_locations.oil_eur IS 'Novi 30-yr oil EUR, bbl (30-yr is the only horizon in the share). Vendor forecast, not the suite''s 50-yr technical EUR.';
COMMENT ON COLUMN curated.intel_locations.gas_eur IS 'Novi 30-yr wet-gas EUR, Mcf.';
COMMENT ON COLUMN curated.intel_locations.dgas_eur IS 'Novi 30-yr dry (residue) gas EUR, Mcf.';
COMMENT ON COLUMN curated.intel_locations.ngl_eur IS 'Novi 30-yr NGL EUR, bbl.';
COMMENT ON COLUMN curated.intel_locations.water_eur IS 'Novi 30-yr produced-water volume, bbl.';
COMMENT ON COLUMN curated.intel_locations.oil_ip IS 'Novi initial oil rate, bbl/d.';
COMMENT ON COLUMN curated.intel_locations.gas_ip IS 'Novi initial wet-gas rate, Mcf/d.';
COMMENT ON COLUMN curated.intel_locations.dgas_ip IS 'Novi initial dry-gas rate, Mcf/d.';
COMMENT ON COLUMN curated.intel_locations.ngl_ip IS 'Novi initial NGL rate, bbl/d.';
COMMENT ON COLUMN curated.intel_locations.water_ip IS 'Novi initial water rate, bbl/d.';
COMMENT ON COLUMN curated.intel_locations.ngl_yield IS 'Novi NGL yield assumption, bbl NGL per MMcf gas (basin-typical 100-150; an input, not derived from the EUR columns).';
COMMENT ON COLUMN curated.intel_locations.ngl_shrink IS 'Novi gas shrink assumption (fraction of wet gas lost to processing).';
COMMENT ON COLUMN curated.intel_locations.npv5 IS 'Novi pre-computed NPV at 5% discount, USD, flat price deck. Vendor SCREEN only -- never authoritative economics (economics live downstream of the export).';
COMMENT ON COLUMN curated.intel_locations.npv10 IS 'Novi pre-computed NPV at 10% discount, USD, flat deck. Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.npv15 IS 'Novi pre-computed NPV at 15% discount, USD, flat deck. Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.npv20 IS 'Novi pre-computed NPV at 20% discount, USD, flat deck. Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.npv25 IS 'Novi pre-computed NPV at 25% discount, USD, flat deck. Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.pv5 IS 'Novi pre-computed present value at 5% discount, USD (companion to npv5). Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.pv10 IS 'Novi pre-computed present value at 10% discount, USD. Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.pv15 IS 'Novi pre-computed present value at 15% discount, USD. Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.pv20 IS 'Novi pre-computed present value at 20% discount, USD. Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.pv25 IS 'Novi pre-computed present value at 25% discount, USD. Vendor screen, not authoritative.';
COMMENT ON COLUMN curated.intel_locations.npv5_be IS 'Novi breakeven flat oil price at which NPV-5 = 0, USD/bbl. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.npv10_be IS 'Novi breakeven flat oil price at which NPV-10 = 0, USD/bbl. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.npv15_be IS 'Novi breakeven flat oil price at which NPV-15 = 0, USD/bbl. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.npv20_be IS 'Novi breakeven flat oil price at which NPV-20 = 0, USD/bbl. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.npv25_be IS 'Novi breakeven flat oil price at which NPV-25 = 0, USD/bbl. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.be_1yr IS 'Novi 1-yr breakeven oil price (flat WTI needed for payout within 1 yr), USD/bbl. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.be_2yr IS 'Novi 2-yr breakeven oil price (flat WTI needed for payout within 2 yr), USD/bbl. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.be_3yr IS 'Novi 3-yr breakeven oil price (flat WTI needed for payout within 3 yr), USD/bbl. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.irr_pct IS 'Novi IRR normalized to PERCENT. The share''s IRR unit is inconsistent by (basin, category) slice, so a per-slice median calibration applies x10000 (slice median |irr| < 0.05) or x100. Vendor screen; see irr_pct_raw for the source value.';
COMMENT ON COLUMN curated.intel_locations.irr_pct_raw IS 'IRR exactly as delivered in the Snowflake share (fraction on some slices, fraction/100 on others -- raised with Novi). Audit trail behind the calibrated irr_pct.';
COMMENT ON COLUMN curated.intel_locations.pp_months IS 'Novi payback period, months. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.ttpt IS 'Novi time to double payback (2x payout), months (share double_payback_months). Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.dc_cost IS 'Novi total drill + complete cost, USD. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.dcet_cost IS 'Novi total drill, complete, equip + tie-in cost, USD. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.norm_dc IS 'Novi drill + complete cost normalized per lateral ft, USD/ft. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.norm_dcet IS 'Novi DCET cost normalized per lateral ft, USD/ft. Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.wti_price IS 'Flat WTI oil price behind the Novi economics, USD/bbl (from the report price deck).';
COMMENT ON COLUMN curated.intel_locations.hh_price IS 'Flat Henry Hub gas price behind the Novi economics, USD/MMBtu.';
COMMENT ON COLUMN curated.intel_locations.ngl_price IS 'Flat NGL price behind the Novi economics, USD/bbl.';
COMMENT ON COLUMN curated.intel_locations.wti_diff IS 'Oil price differential vs WTI in the Novi deck, USD/bbl.';
COMMENT ON COLUMN curated.intel_locations.hh_diff IS 'Gas price differential vs Henry Hub in the Novi deck, USD/MMBtu.';
COMMENT ON COLUMN curated.intel_locations.has_econ IS 'Yes/No: whether a Novi economics row exists for this location.';
COMMENT ON COLUMN curated.intel_locations.conf_int IS 'Always NULL: the Snowflake share has no confidence-interval source. Column retained so the sql/12 output contract is unchanged.';
COMMENT ON COLUMN curated.intel_locations.pad_npv25 IS 'Pad-level NPV-25 rollup, USD: SUM of member-stick npv25 per (report, pad_name). Delaware PUD pads only as of 2025Q3 (pad_name share gap). Vendor screen.';
COMMENT ON COLUMN curated.intel_locations.subbasin IS 'Novi subbasin name (e.g. Delaware, Midland).';
COMMENT ON COLUMN curated.intel_locations.heel_lat IS 'Heel point latitude, WGS84 decimal degrees (gunbarrel endpoint).';
COMMENT ON COLUMN curated.intel_locations.heel_lon IS 'Heel point longitude, WGS84 decimal degrees.';
COMMENT ON COLUMN curated.intel_locations.midpoint_lat IS 'Lateral midpoint latitude, WGS84 decimal degrees.';
COMMENT ON COLUMN curated.intel_locations.midpoint_lon IS 'Lateral midpoint longitude, WGS84 decimal degrees.';
COMMENT ON COLUMN curated.intel_locations.bh_lat IS 'Bottom-hole latitude, WGS84 decimal degrees.';
COMMENT ON COLUMN curated.intel_locations.bh_lon IS 'Bottom-hole longitude, WGS84 decimal degrees.';
COMMENT ON COLUMN curated.intel_locations.wellstick_geom IS 'Lateral stick geometry (LINESTRING, EPSG:4326) from the share WKT. GIST-indexed; the map/selection geometry.';

-- curated.intel_arps (view, sql/29)
COMMENT ON COLUMN curated.intel_arps.basin IS 'Basin slug: delaware or midland.';
COMMENT ON COLUMN curated.intel_arps.novi_wellname IS 'Novi planned-well name; joins intel_locations.unique_id for PUD/RES (share Arps covers planned wells only).';
COMMENT ON COLUMN curated.intel_arps.production_stream IS 'Forecast stream: oil, gas, or water (3 segments each).';
COMMENT ON COLUMN curated.intel_arps.segment IS 'Decline segment number (1..3) within the stream''s piecewise Arps forecast.';
COMMENT ON COLUMN curated.intel_arps.segment_curve_type IS 'Curve type of this segment (e.g. hyperbolic, exponential terminal).';
COMMENT ON COLUMN curated.intel_arps.b IS 'Arps b-factor of the segment (dimensionless).';
COMMENT ON COLUMN curated.intel_arps.d_nom IS 'Segment initial decline Di, NOMINAL per-year (not effective; values > 1/yr are normal). Effective equivalents are d_eff_secant / d_eff_tangent.';
COMMENT ON COLUMN curated.intel_arps.d_eff_secant IS 'Effective annual decline, secant convention (fraction/yr).';
COMMENT ON COLUMN curated.intel_arps.d_eff_tangent IS 'Effective annual decline, tangent convention (fraction/yr).';
COMMENT ON COLUMN curated.intel_arps.q_start IS 'Segment start rate qi (bbl/d for oil/water, Mcf/d for gas).';
COMMENT ON COLUMN curated.intel_arps.q_stop IS 'Segment end rate (bbl/d for oil/water, Mcf/d for gas).';
COMMENT ON COLUMN curated.intel_arps.terminal_day IS 'Producing day on which the terminal (exponential) decline takes over.';
COMMENT ON COLUMN curated.intel_arps.day_start IS 'First producing day covered by this segment (days since first production).';
COMMENT ON COLUMN curated.intel_arps.day_stop IS 'Last producing day covered by this segment.';
COMMENT ON COLUMN curated.intel_arps.planned_well_id IS 'Share well_ref of the planned well (text, format PW-{id}); lineage back to raw_intel.';
COMMENT ON COLUMN curated.intel_arps.well_inventory_name IS 'Always NULL: no source in the Snowflake share. Column retained for the legacy output contract.';

-- curated.intel_forecast (view, sql/29)
COMMENT ON COLUMN curated.intel_forecast.basin IS 'Basin slug: delaware or midland.';
COMMENT ON COLUMN curated.intel_forecast.novi_wellname IS 'Novi planned-well name; joins intel_locations.unique_id for PUD/RES (forecast covers planned wells only).';
COMMENT ON COLUMN curated.intel_forecast.ip_day IS 'Forecast day since first production, in 30-day steps (share forecast_day).';
COMMENT ON COLUMN curated.intel_forecast.mop IS 'Approximate month on production = ip_day / 30 (integer).';
COMMENT ON COLUMN curated.intel_forecast.oil IS 'Forecast oil rate for the month, bbl/d (Novi P50).';
COMMENT ON COLUMN curated.intel_forecast.gas IS 'Forecast gas rate for the month, Mcf/d (Novi P50).';
COMMENT ON COLUMN curated.intel_forecast.water IS 'Forecast water rate for the month, bbl/d (Novi P50).';

-- curated.intel_formation_blueox (matview, sql/19)
COMMENT ON COLUMN curated.intel_formation_blueox.stick_id IS 'Novi Intelligence stick id (curated.intel_locations.stick_id); unique key.';
COMMENT ON COLUMN curated.intel_formation_blueox.formation_blueox_raw IS 'Novi formation string as shipped (free text), before mapping to Blue Ox nomenclature.';
COMMENT ON COLUMN curated.intel_formation_blueox.basin_blueox IS 'Basin slug used for the crosswalk: delaware or midland.';
COMMENT ON COLUMN curated.intel_formation_blueox.formation_blueox IS 'Blue Ox canonical bench code (e.g. WCA_1, WCB_2, AVA_1) -- the grouping field of record for intel sticks. NULL = unmapped tail (empty today).';
COMMENT ON COLUMN curated.intel_formation_blueox.formation_blueox_source IS 'Assignment tier: pdp_join (api10 join to curated.formation_blueox), inferred (spatial + TVD k=1 sub-bench inference, ~84.5% LOO), crosswalk (ref.formation_crosswalk), or NULL.';
COMMENT ON COLUMN curated.intel_formation_blueox.formation_blueox_confidence IS 'NULL today; reserved for the planned k>1 weighted-vote confidence pass to route ambiguous inferred picks to review.';

-- curated.reconciled_inventory (matview, sql/21)
COMMENT ON COLUMN curated.reconciled_inventory.stick_id IS 'Novi PUD stick id (curated.intel_locations.stick_id, category PUD only); unique key.';
COMMENT ON COLUMN curated.reconciled_inventory.basin_blueox IS 'Basin slug: delaware or midland.';
COMMENT ON COLUMN curated.reconciled_inventory.formation_blueox IS 'Blue Ox bench code of the PUD (from curated.intel_formation_blueox); the same-bench test of the match.';
COMMENT ON COLUMN curated.reconciled_inventory.matched_api10 IS 'api10 of the best-overlap producing well realizing this PUD; NULL when no producing lateral covers > 5%.';
COMMENT ON COLUMN curated.reconciled_inventory.matched_survey_planned IS 'TRUE = the realizing well is still on a pre-drill (permit) directional survey, so the TVD confirmation is provisional (mostly NM); recheck when the actual survey files.';
COMMENT ON COLUMN curated.reconciled_inventory.match_overlap IS 'Fraction (0-1) of the PUD lateral lying inside the best producing well''s +/-150 ft corridor -- co-extent overlap, NOT min-distance. >= 0.5 realizes the PUD.';
COMMENT ON COLUMN curated.reconciled_inventory.n_overlapping IS 'Count of producing wells each covering >= 50% of the PUD; >= 2 forces status = conflict (re-frac / ambiguous).';
COMMENT ON COLUMN curated.reconciled_inventory.matched_first_prod IS 'First production date of the realizing well; splits realized into drift (after the Novi vintage) vs phantom (before it).';
COMMENT ON COLUMN curated.reconciled_inventory.status IS 'Reconciliation status: remaining_pud + conflict = the DRILLABLE remaining inventory; realized_drift (drilled since the Novi vintage) and realized_phantom (already drilled before it) are NOT drillable. Producers Novi missed are the reverse pass, curated.net_new_pdp.';

-- curated.net_new_pdp (matview, sql/25)
COMMENT ON COLUMN curated.net_new_pdp.api10 IS '10-digit API of the post-vintage producing horizontal that no Novi PUD anticipated; unique key.';
COMMENT ON COLUMN curated.net_new_pdp.basin_blueox IS 'Basin slug: delaware or midland.';
COMMENT ON COLUMN curated.net_new_pdp.formation_blueox IS 'Blue Ox bench code of the well (TVD-corrected producing code, sql/23 override applied).';
COMMENT ON COLUMN curated.net_new_pdp.tvd IS 'Landing true vertical depth, ft (from the producing reference).';
COMMENT ON COLUMN curated.net_new_pdp.first_production_date IS 'First production date; by definition after the loaded Novi vintage (curated.intel_vintage_date()).';
COMMENT ON COLUMN curated.net_new_pdp.operator IS 'Current operator of the well.';
COMMENT ON COLUMN curated.net_new_pdp.ll_ft IS 'Lateral length, ft.';
COMMENT ON COLUMN curated.net_new_pdp.survey_planned IS 'TRUE = directional survey is a pre-drill plan (provisional formation/TVD; mostly NM).';
COMMENT ON COLUMN curated.net_new_pdp.wellstick_geom IS 'Lateral stick geometry (LINESTRING, EPSG:4326) for mapping; GIST-indexed.';
COMMENT ON COLUMN curated.net_new_pdp.best_pud_overlap IS 'Max fraction (0-1) of any same-bench PUD lateral covered by this well''s +/-150 ft corridor; < 0.2 by definition (else the PUD counts as realized/conflict, not net-new).';

-- curated.erebor_locations (matview, sql/22) -- read directly by the land team via GIS
COMMENT ON COLUMN curated.erebor_locations.stick_id IS 'Row id. Positive = a Novi Intelligence stick (PUD/RES undrilled location); NEGATIVE = a producing well (PDP), where the id is minus its 10-digit API number.';
COMMENT ON COLUMN curated.erebor_locations.unique_id IS '10-digit API number for producing (PDP) rows; Novi well name for PUD/RES rows.';
COMMENT ON COLUMN curated.erebor_locations.category IS 'PDP = producing well (from the warehouse, what physically exists), PUD = Novi base-case undrilled location, RES = Novi emerging/resource location.';
COMMENT ON COLUMN curated.erebor_locations.basin IS 'Basin slug: delaware or midland.';
COMMENT ON COLUMN curated.erebor_locations.formation IS 'Raw vendor formation name (free text, inconsistent casing) -- display only. Group and filter on formation_blueox instead.';
COMMENT ON COLUMN curated.erebor_locations.formation_blueox IS 'Standardized Blue Ox bench code (e.g. WCA_1, WCB_2, BS2) -- the formation field of record for grouping/filtering. NULL = unmapped.';
COMMENT ON COLUMN curated.erebor_locations.basin_blueox IS 'Blue Ox basin slug (delaware/midland), aligned with formation_blueox.';
COMMENT ON COLUMN curated.erebor_locations.formation_blueox_source IS 'How the bench code was assigned: pdp_join / inferred / crosswalk (Novi sticks, sql/19) or the wells crosswalk chain (PDP rows).';
COMMENT ON COLUMN curated.erebor_locations.recon_status IS 'Reconciliation tag: remaining_pud + conflict = the DRILLABLE remaining inventory; realized_drift / realized_phantom = PUD slots already drilled (not inventory); net_new_pdp = a producing well Novi never inventoried; NULL = RES stick or ordinary PDP.';
COMMENT ON COLUMN curated.erebor_locations.deplet_t IS 'Novi depletion tier for PUD/RES: Tier-1..Tier-4, where Tier-4 = most depleted (drained by offset production). NULL on PDP rows (producing wells are not depletion-scored).';
COMMENT ON COLUMN curated.erebor_locations.operator IS 'Operator name: Novi-reported for PUD/RES, current operator from the warehouse for PDP.';
COMMENT ON COLUMN curated.erebor_locations.pad_name IS 'Novi DSU pad name (Delaware PUD only as of 2025Q3). NULL for PDP -- the gun-barrel assigns pads spatially instead.';
COMMENT ON COLUMN curated.erebor_locations.tvd IS 'True vertical depth, ft.';
COMMENT ON COLUMN curated.erebor_locations.ll_ft IS 'Lateral length, ft.';
COMMENT ON COLUMN curated.erebor_locations.npv5 IS 'Novi pre-computed NPV at 5% discount, USD, flat deck. Vendor SCREEN only, not authoritative economics. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.npv10 IS 'Novi pre-computed NPV at 10% discount, USD, flat deck. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.npv15 IS 'Novi pre-computed NPV at 15% discount, USD, flat deck. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.npv20 IS 'Novi pre-computed NPV at 20% discount, USD, flat deck. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.npv25 IS 'Novi pre-computed NPV at 25% discount, USD, flat deck. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.pv5 IS 'Novi pre-computed present value at 5% discount, USD. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.pv10 IS 'Novi pre-computed present value at 10% discount, USD. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.pv15 IS 'Novi pre-computed present value at 15% discount, USD. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.pv20 IS 'Novi pre-computed present value at 20% discount, USD. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.pv25 IS 'Novi pre-computed present value at 25% discount, USD. Vendor screen only. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.oil_eur IS 'Novi 30-yr oil EUR, bbl (vendor forecast horizon, not the suite''s 50-yr technical EUR). NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.gas_eur IS 'Novi 30-yr gas EUR, Mcf. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.wti_price IS 'Flat WTI oil price behind the Novi economics, USD/bbl. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.hh_price IS 'Flat Henry Hub gas price behind the Novi economics, USD/MMBtu. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.ngl_price IS 'Flat NGL price behind the Novi economics, USD/bbl. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.wti_diff IS 'Oil price differential vs WTI in the Novi deck, USD/bbl. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.hh_diff IS 'Gas price differential vs Henry Hub in the Novi deck, USD/MMBtu. NULL on PDP rows.';
COMMENT ON COLUMN curated.erebor_locations.wellstick_geom IS 'Lateral stick geometry (LINESTRING, EPSG:4326): the drawn/planned lateral for PUD/RES, the warehouse wellstick for PDP. GIST-indexed map geometry.';

-- ---------------------------------------------------------------------------
-- Part 2: table-level comments (relations without an existing comment only;
-- skipped: meta.intel_report_watermark, raw_intel.stick_id_map,
-- raw_novi.ForecastWellMonths, ref.formation_crosswalk)
-- ---------------------------------------------------------------------------

-- meta
COMMENT ON TABLE meta.etl_log IS 'One row per ETL step run (source x table_name), written by etl/db.py log_etl_run: status running/success/failed, row counts, timings. Doubles as the incremental cursor for Enverus pulls (updateddate > last success) and the curated refresh gate.';

-- raw_enverus (nightly run_daily; incremental API pull)
COMMENT ON TABLE raw_enverus.wells IS 'Enverus DirectAccess v3 wells dataset mirror; one row per completion event, upsert key (wellid, completionid). Nightly incremental pull (updateddate cursor from meta.etl_log; etl/enverus/pull.py). Intake lowercases Enverus PascalCase keys and converts literal "NULL" strings to SQL NULL.';

-- raw_novi (nightly run_daily; bulk TSV sync with no_diffs=True)
COMMENT ON TABLE raw_novi."Wells" IS 'Novi Insights well header mirror, one row per wellbore keyed API10 (some synthetic Novi APIs). Nightly full TRUNCATE + COPY from the bulk TSV (etl/novi/load.py; sync forces no_diffs=True). Column names are quoted PascalCase as shipped.';
COMMENT ON TABLE raw_novi."WellDetails" IS 'Novi Insights extended per-well attributes (completion intensity, cums, EURs, spacing, peak rates), one row per API10. Nightly full TRUNCATE + COPY from the bulk TSV. Primary source behind curated.wells.';
COMMENT ON TABLE raw_novi."WellMonths" IS 'Novi Insights monthly production actuals, grain (API10, Year, Month). Nightly INCREMENTAL upsert of rows newer than the live max(ModifiedAt) watermark (full snapshot rewrite is too heavy for the instance); deletions caught by on-demand reconcile.';
COMMENT ON TABLE raw_novi."WellSpacing" IS 'Novi Insights per-well spacing metrics (closest-well distance ft, wells in radius, avg of closest two), one row per API10. Nightly full TRUNCATE + COPY from the bulk TSV.';

-- raw_intel (quarterly manual reload from the Novi INTEL Snowflake share;
-- extracted by etl/intel_sf/extract.py via scripts/load_intel_sf.py;
-- report-scoped tables are slice-idempotent: DELETE WHERE report_name + COPY)
COMMENT ON TABLE raw_intel.source IS 'Snowflake share SOURCE dimension: one row per source file/collection. collection (basin_research__<Basin>__<yyyyQq>) feeds the nightly new-report detection (etl/intel_sf/detect.py -> meta.intel_report_watermark). Global dim: full-replace load.';
COMMENT ON TABLE raw_intel.basin IS 'Snowflake share BASIN dimension (Permian -> Delaware/Midland subbasins), keyed basin_id. Tiny global dim; full-replace on the quarterly intel load.';
COMMENT ON TABLE raw_intel.operator IS 'Snowflake share OPERATOR dimension (reported + normalized names, contact fields), keyed operator_id. Global dim; full-replace on the quarterly intel load.';
COMMENT ON TABLE raw_intel.pad IS 'Snowflake share PAD dimension, key (pad_id, report_name). latitude/longitude unpopulated as of 2025Q3. Loader adds basin_slug/report_version; quarterly slice reload.';
COMMENT ON TABLE raw_intel.econ_price_assumption IS 'Flat price decks behind the Novi economics (WTI/HH/NGL prices + differentials), key (price_deck_id [content hash, repeats across reports], report_name). Quarterly slice reload.';
COMMENT ON TABLE raw_intel.well IS 'Snowflake share WELL entity: existing (PDP) wells, key (well_id, report_name). uwi_api is a 10-digit API on every row -- the api10 crosswalk to curated.wells. Quarterly slice reload.';
COMMENT ON TABLE raw_intel.planned_well IS 'Snowflake share PLANNED_WELL entity: undrilled locations, inventory_class BASE_CASE (PUD) or EMERGING (RES), key (planned_well_id, report_name). name = the legacy sticks unique_id for BASE_CASE. planned_til_date entirely NULL as of 2025Q3. Quarterly slice reload.';
COMMENT ON TABLE raw_intel.wellbore IS 'Snowflake share WELLBORE entity: depths (tvd_td/md_td ft), lateral length ft, heel/mid/BH lat-lon, formation fields; exactly one of well_id / planned_well_id set. Key (wellbore_id, report_name). Quarterly slice reload.';
COMMENT ON TABLE raw_intel.wellbore_trajectory IS 'Snowflake share lateral trajectories: geometry_wkt (LINESTRING, EPSG:4326) landed as text, geom populated post-COPY per slice (share GEO columns are not mirrored). Key (trajectory_id, report_name). Quarterly slice reload.';
COMMENT ON TABLE raw_intel.surface_location IS 'Snowflake share SURFACE_LOCATION: surface-hole lat/lon + legal description (block/township, section, TX survey/abstract) per well or planned well. Key (surface_location_id, report_name). Quarterly slice reload.';
COMMENT ON TABLE raw_intel.well_completion IS 'Snowflake share WELL_COMPLETION: completion design -- proppant_loading lb/ft, fluid_loading gal/ft, masses/volumes. Planned wells only as of 2025Q3 (zero PDP rows; gap raised with Novi). Key (well_completion_id, report_name).';
COMMENT ON TABLE raw_intel.well_ml_score IS 'Snowflake share WELL_ML_SCORE: Novi ML spacing / prior-depletion / completion scores + tiers (Tier-1..Tier-4) per well x stream. Scores are sensitivity values, NOT footage. Replaces raw_novi_intel.pud_attrs; covers PDP too. Key (well_ml_score_id, report_name).';
COMMENT ON TABLE raw_intel.well_rock_quality IS 'Snowflake share WELL_ROCK_QUALITY: Novi ML rock-quality score + tier per well x stream. Key (well_rock_quality_id, report_name). Quarterly slice reload.';
COMMENT ON TABLE raw_intel.well_cost_summary IS 'Snowflake share WELL_COST_SUMMARY: Novi D&C and DCET cost totals (USD) and per-lateral-ft normalizations (USD/ft). Vendor screen inputs. Key (well_cost_summary_id, report_name).';
COMMENT ON TABLE raw_intel.well_economics_summary IS 'Snowflake share WELL_ECONOMICS_SUMMARY: Novi NPV/PV (5-25%), IRR, paybacks, breakevens, 30-yr EURs + IPs per well. irr unit is inconsistent by slice (fraction vs fraction/100; raised with Novi) -- normalized downstream in curated.intel_locations. Vendor screen, not authoritative economics. Key (well_economics_summary_id, report_name).';
COMMENT ON TABLE raw_intel.arps_forecast IS 'Snowflake share ARPS_FORECAST: segmented Arps decline parameters (b, NOMINAL per-year Di, secant/tangent effective declines, segment rates/days), planned wells only as of 2025Q3. Key (well_ref [PW-{id}], stream, segment_number, report_name).';
COMMENT ON TABLE raw_intel.well_master IS 'Snowflake share WELL_MASTER: the spine uniting PDP + BASE_CASE + EMERGING, grain (well_ref, report_name, inventory_class); well_ref = uwi_api (PDP) or PW-{id} (planned). geometry_wkt landed as text; geom populated post-COPY. Feeds curated.intel_locations. Quarterly slice reload.';
COMMENT ON TABLE raw_intel.production_forecast IS 'Snowflake share PRODUCTION_FORECAST: monthly P50 stream forecast for planned wells, 30-day forecast_day steps, ~73M rows (no ingested_at by design). Loaded via the separate --forecast gate after the legacy 7.7 GB table is dropped (disk headroom). Condensate columns all-NULL for Permian.';

-- raw_novi_intel (LEGACY quarterly Novi Intelligence file drop -- shapefiles +
-- CSVs; superseded by the raw_intel Snowflake mirror and being retired, EXCEPT
-- the frozen display geometries pads / land_grid / basin_outline)
COMMENT ON TABLE raw_novi_intel.pads IS 'Novi DSU pad polygons + pad-level NPV rollup from the quarterly file drop, tagged (basin, report_version). STILL IN USE for display: the Snowflake share has no pad geometry as of 2025Q3.';
COMMENT ON TABLE raw_novi_intel.land_grid IS 'Novi-supplied land grid polygons (raw DBF attributes in JSONB) from the file drop, tagged (basin, report_version). STILL IN USE as a map overlay: the Snowflake share has no equivalent geometry.';
COMMENT ON TABLE raw_novi_intel.basin_outline IS 'Novi-supplied basin outline polygons from the file drop, tagged (basin, report_version). STILL IN USE as a map overlay: the Snowflake share has no equivalent geometry.';

-- Table-level comments authored at assembly (missing from part C).
COMMENT ON VIEW curated.intel_arps IS 'Novi Intelligence Arps decline parameters per stick and stream (from raw_intel.arps_forecast). d_nom is NOMINAL per-year decline. Rebuilt quarterly by the intel reload chain.';
COMMENT ON VIEW curated.intel_forecast IS 'Novi Intelligence monthly production forecast per stick (P50, 30-day months, planned wells only; from raw_intel.production_forecast). Rebuilt quarterly by the intel reload chain.';
