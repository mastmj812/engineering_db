-- =============================================================================
-- 66 — raw_novi_intel.pads: 2026Q3 DSU pad polygon attributes (additive)
--
-- Novi's 2026Q3 shapefile drop ships DSU pad polygons for both basins with
-- fields the 3Q25 drop lacked: Operator, NPV0_Sum (Delaware only), LL_Sum and
-- WellCnt. This adds nullable columns for them so the raw table keeps the drop
-- as shipped (etl/novi_intel/load_shapefiles.pad_row). 3Q25 rows get NULLs.
--
-- The Pad Summary layer's sums EXCLUDE wells with Novi NPV25 < 0 (Novi
-- Field_Explainer.xlsx), so WellCnt/LL_Sum/NPV*_Sum describe Novi-economic
-- wells only: WellCnt = 0 (3,772 of 8,256 Delaware polygons) means no well
-- passing Novi's NPV25 >= 0 screen, NOT an empty DSU.
--
-- WHY THE RAW TABLE MATTERS NOW. Every 2026Q3 polygon is loaded, WellCnt = 0
-- included. raw_novi_intel.pads is the DSU geometry of record for the planned
-- BOX-derived locations (narvi-style infill of Novi DSUs); curated.intel_pad_geom
-- (sql/67) is only the stick-membership view erebor Highgrade aggregates on.
--
-- Additive + idempotent (ADD COLUMN IF NOT EXISTS; no rewrite, no drop).
-- sql/11 carries the same columns for a from-scratch rebuild.
-- RUN: python -m scripts.apply_intel_pad_geom --load-pads   (step 1 of 3)
-- =============================================================================

ALTER TABLE raw_novi_intel.pads
    ADD COLUMN IF NOT EXISTS operator   TEXT,
    ADD COLUMN IF NOT EXISTS npv0       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ll_sum_ft  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS well_cnt   INTEGER;

-- sql/67 joins pads by (basin, report_version, pad_name).
CREATE INDEX IF NOT EXISTS idx_rni_pads_name
    ON raw_novi_intel.pads (basin, report_version, pad_name);

COMMENT ON TABLE raw_novi_intel.pads IS
'Novi DSU pad polygons from the quarterly shapefile drop, tagged (basin, report_version), as shipped. 3Q25 rows = the legacy drop; 2026Q3 rows = the official 2026Q3 drop (Mid-Cycle pad summary; Strip has identical polygons), ALL polygons including WellCnt = 0 (no Novi-economic well; not an empty DSU). The DSU geometry of record (planned BOX-location infill); curated.intel_pad_geom (sql/67) takes the polygon for each pad whose report_version matches curated.intel_locations. The Snowflake share ships no pad geometry. NPV columns are Novi''s pad rollup — not read by apps.';
COMMENT ON COLUMN raw_novi_intel.pads.operator IS 'Most common operator among the pad''s wells, per Novi (2026Q3+; often blank).';
COMMENT ON COLUMN raw_novi_intel.pads.npv0 IS 'Novi NPV0 pad sum over wells with NPV25 >= 0 (2026Q3 Delaware only).';
COMMENT ON COLUMN raw_novi_intel.pads.ll_sum_ft IS 'Summed lateral feet of the pad''s wells with Novi NPV25 >= 0 (2026Q3+ Pad Summary filter).';
COMMENT ON COLUMN raw_novi_intel.pads.well_cnt IS 'Count of the pad''s wells with Novi NPV25 >= 0 (2026Q3+ Pad Summary filter). 0 = no Novi-economic well, NOT an empty DSU; the polygon is kept either way.';
