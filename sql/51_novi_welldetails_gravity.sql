-- 51: Novi WellDetails schema drift (2026-09-22) — latest oil/gas gravity tests.
--
-- The 2026-09-22 Novi export added four columns to the WellDetails TSV
-- (shipped types: float8 NULL / date NULL):
--   LatestOilAPIGravity, LatestOilAPIGravityTestDate,
--   LatestGasSpecificGravity, LatestGasSpecificGravityTestDate.
-- Wells did not change. The nightly's reconcile_schema_drift() auto-added
-- them live (GitHub Actions run 35747928315, 2026-09-22 15:33:09 UTC —
-- "Novi schema drift: auto-added raw_novi.WellDetails.…" x4), so this file
-- is the repo MIRROR of DDL that already exists; it changes nothing on the
-- live DB. sql/02 was regenerated from the same export in this commit.
--
-- No sql/50: that number is claimed by the open dev_scenario PR.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS; safe to re-run. Purely additive —
-- no matview reads these yet, so no downstream rebuild is required.

ALTER TABLE raw_novi."WellDetails"
    ADD COLUMN IF NOT EXISTS "LatestOilAPIGravity" double precision;

ALTER TABLE raw_novi."WellDetails"
    ADD COLUMN IF NOT EXISTS "LatestOilAPIGravityTestDate" date;

ALTER TABLE raw_novi."WellDetails"
    ADD COLUMN IF NOT EXISTS "LatestGasSpecificGravity" double precision;

ALTER TABLE raw_novi."WellDetails"
    ADD COLUMN IF NOT EXISTS "LatestGasSpecificGravityTestDate" date;
