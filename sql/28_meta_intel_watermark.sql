-- =============================================================================
-- 28 — meta.intel_report_watermark: new-report detection for the Novi INTEL share
--
-- etl/intel_sf/detect.py (nightly, notify-only) inserts every collection it
-- sees in NOVI_INTEL.SOURCE that isn't already here. Rows with
-- acknowledged_at IS NULL are "new reports awaiting a manual reload"; the
-- nightly summary surfaces them loudly. After the user runs the quarterly
-- reload (scripts/load_intel_sf.py + curated rebuild), the reload marks the
-- collection acknowledged.
--
-- Append-only by design; CREATE IF NOT EXISTS so re-runs never lose history.
-- RUN: scripts/load_intel_sf.py --ddl  (with sql/27; requires authorization).
-- =============================================================================

CREATE TABLE IF NOT EXISTS meta.intel_report_watermark (
    report_name     TEXT PRIMARY KEY,        -- e.g. basin_research__Midland_Basin__2025Q3
    report_family   TEXT,                    -- e.g. Midland_Basin (parsed)
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ              -- set by the manual reload
);

COMMENT ON TABLE meta.intel_report_watermark IS
  'Collections seen in the Novi INTEL share (NOVI_INTEL.SOURCE). NULL '
  'acknowledged_at = new report awaiting the manual quarterly reload. '
  'Written by etl/intel_sf/detect.py (nightly) and scripts/load_intel_sf.py.';
