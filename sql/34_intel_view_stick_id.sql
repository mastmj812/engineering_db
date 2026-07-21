-- =============================================================================
-- 34 — stick_id on curated.intel_arps / curated.intel_forecast
--
-- Adds the suite's stable stick key (raw_intel.stick_id_map, append-only,
-- survives quarterly reloads) to both forecast views, so consumers filtering
-- curated.erebor_locations can join its unique key directly:
--
--     erebor_locations.stick_id = intel_forecast.stick_id
--
-- instead of the name key (erebor_locations.unique_id = novi_wellname).
-- novi_wellname is UNCHANGED — erebor's export/aggregate paths key on it and
-- keep working as-is.
--
-- LEFT JOIN, not JOIN: a small set of forecast inventory names has no
-- raw_intel.well_master row (Delaware carried ~1.9k such orphans in the legacy
-- layer) and therefore no stick_id_map entry -> stick_id NULL there. The row
-- set of both views is exactly unchanged.
--
-- sql/29 carries the SAME definitions (the quarterly reload re-runs that file
-- after DROP CASCADE); this file exists to apply the change to a live database
-- between reloads. Idempotent: CREATE OR REPLACE VIEW — legal because the new
-- column is appended LAST — and preserves any existing grants (analyst_ro).
-- =============================================================================

CREATE OR REPLACE VIEW curated.intel_arps AS
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
       NULL::text                        AS well_inventory_name,
       sid.stick_id
FROM raw_intel.arps_forecast af
JOIN raw_intel.planned_well pw
  ON af.well_ref = 'PW-' || pw.planned_well_id::text
 AND af.report_name = pw.report_name
LEFT JOIN raw_intel.stick_id_map sid
  ON sid.well_ref = af.well_ref;

CREATE OR REPLACE VIEW curated.intel_forecast AS
SELECT pf.basin_slug        AS basin,
       pw.name              AS novi_wellname,
       pf.forecast_day      AS ip_day,
       (pf.forecast_day / 30)::int AS mop,
       pf.oil_per_day       AS oil,
       pf.gas_per_day       AS gas,
       pf.water_per_day     AS water,
       sid.stick_id
FROM raw_intel.production_forecast pf
JOIN raw_intel.planned_well pw
  ON pw.planned_well_id = pf.planned_well_id
 AND pw.report_name = pf.report_name
LEFT JOIN raw_intel.stick_id_map sid
  ON sid.well_ref = 'PW-' || pw.planned_well_id::text;

COMMENT ON COLUMN curated.intel_arps.stick_id IS
  'Stable suite stick key (raw_intel.stick_id_map); joins curated.erebor_locations.stick_id / curated.intel_locations.stick_id. NULL for forecast names with no well_master stick.';
COMMENT ON COLUMN curated.intel_forecast.stick_id IS
  'Stable suite stick key (raw_intel.stick_id_map); joins curated.erebor_locations.stick_id / curated.intel_locations.stick_id. NULL for forecast names with no well_master stick.';
