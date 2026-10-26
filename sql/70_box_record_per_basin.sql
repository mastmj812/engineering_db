-- sql/70 — one BOX record run PER BASIN (D130, Michael 2026-10-26, gate 18; built in step 19)
--
-- "BOX exists to replace Novi's forecasts; tying a Midland publish to a Delaware rebuild or the next vintage is the wrong
-- coupling." Each basin's record publishes on its own schedule. sql/60 allowed exactly ONE is_record run in all of box;
-- this makes it one per basin:
--
--   box.forecast_run.basin   text NOT NULL, CHECK IN (delaware, midland). Every run stored so far is the Delaware's (run 19,
--                            the live record, = delaware). DEFAULT 'delaware' is kept so a writer from before step 19 (the
--                            sql/60-63 / sql/65 apply smokes) still inserts; every step-19 writer names the basin itself.
--   box_forecast_run_record_basin_uq   UNIQUE (basin) WHERE is_record — replaces sql/60's box_forecast_run_record_uq
--                            (UNIQUE (is_record) WHERE is_record). A record flip supersedes only its own basin's record.
--
-- A run's pud_forecast rows are its basin's universe (box_pud_run builds per basin since step 19). Run 19 predates that and
-- also carries the 4,154 Midland emerging-bench (not_covered_emerging) universe rows; they leave the Delaware record with
-- its next build and return under the first Midland record (step 23). No FK enforces pud_forecast.basin = the run's basin
-- (run 19 would violate it; a box_prox_record derivation from run 19 copies its rows as they are).
--
-- D123 now reads "keep only the record run PER BASIN" (scripts.box_prune_runs). Readers of "the" record (BOX scripts,
-- sql/69, erebor box_locations) name the basin or take every record, one per basin.
--
-- Idempotent. Requires sql/60. Apply with: python -m scripts.apply_box_run_basin (explicit "go apply" required).

ALTER TABLE box.forecast_run ADD COLUMN IF NOT EXISTS basin text NOT NULL DEFAULT 'delaware';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'box_forecast_run_basin_ck') THEN
        ALTER TABLE box.forecast_run ADD CONSTRAINT box_forecast_run_basin_ck CHECK (basin IN ('delaware', 'midland'));
    END IF;
END $$;

DROP INDEX IF EXISTS box.box_forecast_run_record_uq;
CREATE UNIQUE INDEX IF NOT EXISTS box_forecast_run_record_basin_uq ON box.forecast_run (basin) WHERE is_record;

COMMENT ON COLUMN box.forecast_run.basin IS
    'The basin this run forecasts (D130): one record run per basin (box_forecast_run_record_basin_uq). A run''s pud_forecast rows are '
    'its basin''s universe (run 19, built before step 19, also carries 4,154 Midland not_covered_emerging rows). See sql/70.';
COMMENT ON COLUMN box.forecast_run.is_record IS
    'The record run of its basin (at most one per basin, sql/70 / D130); readers name the basin or take one record per basin.';
COMMENT ON INDEX box.box_forecast_run_record_basin_uq IS 'D130: at most one record run per basin (replaced sql/60 box_forecast_run_record_uq).';
