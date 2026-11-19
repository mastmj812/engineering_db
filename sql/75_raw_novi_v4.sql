-- =============================================================================
-- 75_raw_novi_v4.sql - side-by-side copy of the six raw_novi tables, loaded from Novi v4
-- =============================================================================
-- Novi v3 (bulk TSV) is deprecated; v4 is the Snowflake share NOVI_DATA_ACCESS.NOVI_WELLS.
-- etl/novi_v4 pulls v4 and presents it in the six v3 table shapes. Before the nightly is cut
-- over, that loader writes HERE, not raw_novi, so the two can be diffed row for row
-- (docs/novi_v4_parity.md; python -m etl.novi_v4.load --schema raw_novi_v4).
--
-- Each table is a structural copy of its raw_novi twin (columns, defaults, primary key).
-- NOT NULL is dropped on the columns v4 has no source for; the loader leaves them NULL:
--   Wells / WellDetails: IsHorizontalWell, WellType, HasPLSSData, WellboreLocations,
--                        HasAccurateFirstProductionDate; Wells also IsSyntheticApi
-- (tests/test_novi_v4.py pins this list against sql/02 and the loader's column maps).
--
-- Ownership: ETL-owned scratch. Nothing reads it: no curated object, no app, not in
-- etl/db.py:_CURATED_MATVIEWS, no matview (outside the CI unique-index lint). The nightly does
-- not write it. Safe to drop whole once the cutover is done:
--   DROP SCHEMA raw_novi_v4 CASCADE;
--
-- Size: about the same as raw_novi (5.2M production, 17.2M forecast, 16.0M survey rows).
-- Idempotent. DEPENDS ON: sql/02 (raw_novi tables). Apply needs an explicit go.

CREATE SCHEMA IF NOT EXISTS raw_novi_v4;

CREATE TABLE IF NOT EXISTS raw_novi_v4."Wells"              (LIKE raw_novi."Wells"              INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS raw_novi_v4."WellDetails"        (LIKE raw_novi."WellDetails"        INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS raw_novi_v4."WellSpacing"        (LIKE raw_novi."WellSpacing"        INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS raw_novi_v4."WellMonths"         (LIKE raw_novi."WellMonths"         INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS raw_novi_v4."ForecastWellMonths" (LIKE raw_novi."ForecastWellMonths" INCLUDING DEFAULTS INCLUDING INDEXES);
CREATE TABLE IF NOT EXISTS raw_novi_v4."DirectionalSurveys" (LIKE raw_novi."DirectionalSurveys" INCLUDING DEFAULTS INCLUDING INDEXES);

ALTER TABLE raw_novi_v4."Wells"
    ALTER COLUMN "IsHorizontalWell" DROP NOT NULL,
    ALTER COLUMN "WellType" DROP NOT NULL,
    ALTER COLUMN "HasPLSSData" DROP NOT NULL,
    ALTER COLUMN "WellboreLocations" DROP NOT NULL,
    ALTER COLUMN "HasAccurateFirstProductionDate" DROP NOT NULL,
    ALTER COLUMN "IsSyntheticApi" DROP NOT NULL;

ALTER TABLE raw_novi_v4."WellDetails"
    ALTER COLUMN "IsHorizontalWell" DROP NOT NULL,
    ALTER COLUMN "WellType" DROP NOT NULL,
    ALTER COLUMN "HasPLSSData" DROP NOT NULL,
    ALTER COLUMN "WellboreLocations" DROP NOT NULL,
    ALTER COLUMN "HasAccurateFirstProductionDate" DROP NOT NULL,
    ALTER COLUMN "IsSyntheticApi" DROP NOT NULL;

COMMENT ON SCHEMA raw_novi_v4 IS
'Side-by-side copy of the six raw_novi tables loaded from Novi v4 (Snowflake) by etl/novi_v4, for the v3 -> v4 cutover diff. Scratch: nothing reads it. Drop after cutover.';
