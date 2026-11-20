-- =============================================================================
-- 76_raw_novi_v4_nullable.sql - let raw_novi hold Novi v4 rows (cutover step 2)
-- =============================================================================
-- Novi v3 (bulk TSV) is deprecated; from the cutover the nightly fills raw_novi from the v4
-- Snowflake share (etl/novi_v4, NOVI_SOURCE=v4; docs/novi_v4_parity.md section 16).
--
-- v4 has no source for six columns that sql/02 declares NOT NULL on "Wells" and "WellDetails";
-- the v4 loader leaves them NULL. This drops the constraint on exactly those columns, the same
-- list sql/75 dropped on the side-by-side copy (tests/test_novi_v4.py pins all three: sql/02,
-- sql/75, this file).
--
-- The v3 loader keeps working after this (it still fills the columns), so applying this file
-- does not commit to the cutover and needs no rollback.
--
-- Metadata-only (no table rewrite), brief ACCESS EXCLUSIVE lock per table. No dependent object
-- is touched: no CASCADE, no matview, no index. Idempotent.
-- DEPENDS ON: sql/02. Apply needs an explicit go:
--   python -c "from scripts.load_intel_sf import run_sql_file; run_sql_file('76_raw_novi_v4_nullable.sql')"

ALTER TABLE raw_novi."Wells"
    ALTER COLUMN "IsHorizontalWell" DROP NOT NULL,
    ALTER COLUMN "WellType" DROP NOT NULL,
    ALTER COLUMN "HasPLSSData" DROP NOT NULL,
    ALTER COLUMN "WellboreLocations" DROP NOT NULL,
    ALTER COLUMN "HasAccurateFirstProductionDate" DROP NOT NULL,
    ALTER COLUMN "IsSyntheticApi" DROP NOT NULL;

ALTER TABLE raw_novi."WellDetails"
    ALTER COLUMN "IsHorizontalWell" DROP NOT NULL,
    ALTER COLUMN "WellType" DROP NOT NULL,
    ALTER COLUMN "HasPLSSData" DROP NOT NULL,
    ALTER COLUMN "WellboreLocations" DROP NOT NULL,
    ALTER COLUMN "HasAccurateFirstProductionDate" DROP NOT NULL,
    ALTER COLUMN "IsSyntheticApi" DROP NOT NULL;
