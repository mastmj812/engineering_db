-- sql/62 — BOX water stream (plan step 12b; D107-D110, Michael 2026-10-19). Reserved for this step since the Phase-2 draft.
--
-- D72 kept water out of v1 because no water acceptance existed. Steps 11 / 12a built one (pre-registered 51d589c, holdout
-- scored once at 546c51a): water = WOR vs cumulative oil (boxfit ratio mode) fitted on MEASURED-water analogs, applied month by
-- month to the location's RAW box_v2 oil (D107 / D108). Its acceptance tier is per group and can be lower than the location's
-- oil tier, never higher (D109 / D110): validated on WCA and BS2_S, provisional everywhere else. So the tier has to live on the
-- stream row, not only in pud_forecast.coverage.
--
-- Changes (idempotent; sql/60's inline CHECK on stream carries a generated name, found by definition and re-added named):
--   box.pud_forecast_stream   stream IN (oil, gas, water)
--                             + tier text NULL CHECK IN (validated, provisional)
--                               water rows must state it; a covered_provisional location's water can never read validated
--   box.location_water_analog NEW: the named MEASURED-water analogs behind each location's water (a different, wider set than
--                             box.location_analog's oil / gas cohort: measured water only, D54 ladder + 30 / 40 / 50 mi extension;
--                             calculated-fallback cohorts are stated, never hidden)
-- Water's search provenance (method, alpha / beta, oil basis, source measured | calculated_fallback, radius, thin, NM share) lives in
-- the stream row's params jsonb; the group's disclosure lines in box.forecast_run.disclosure -> 'water'.
-- pud_forecast_month needs no change: its FK to (run_id, location_id, stream) admits water once the stream row does.
--
-- Requires sql/60, sql/63. Apply with: python -m scripts.apply_box_water (explicit "go apply" required).

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT k.conname
        FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE k.contype = 'c' AND n.nspname = 'box' AND c.relname = 'pud_forecast_stream'
          AND pg_get_constraintdef(k.oid) ~ '^CHECK \(\(?stream (=|= ANY)'
          AND k.conname <> 'box_pud_forecast_stream_stream_ck'
    LOOP
        EXECUTE format('ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;

ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT IF EXISTS box_pud_forecast_stream_stream_ck;
ALTER TABLE box.pud_forecast_stream ADD CONSTRAINT box_pud_forecast_stream_stream_ck CHECK (stream IN ('oil', 'gas', 'water'));

ALTER TABLE box.pud_forecast_stream ADD COLUMN IF NOT EXISTS tier text;
ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT IF EXISTS box_pud_forecast_stream_tier_ck;
ALTER TABLE box.pud_forecast_stream ADD CONSTRAINT box_pud_forecast_stream_tier_ck CHECK (tier IS NULL OR tier IN ('validated', 'provisional'));
ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT IF EXISTS box_pud_forecast_stream_water_tier_ck;
ALTER TABLE box.pud_forecast_stream ADD CONSTRAINT box_pud_forecast_stream_water_tier_ck CHECK (stream <> 'water' OR tier IS NOT NULL);
-- water never ranks above its oil (D109 rule 5): a provisional location's stream can only be provisional
ALTER TABLE box.pud_forecast_stream DROP CONSTRAINT IF EXISTS box_pud_forecast_stream_tier_le_coverage_ck;
ALTER TABLE box.pud_forecast_stream ADD CONSTRAINT box_pud_forecast_stream_tier_le_coverage_ck
    CHECK (tier IS NULL OR coverage = 'covered' OR tier = 'provisional');

CREATE TABLE IF NOT EXISTS box.location_water_analog (
    run_id              bigint   NOT NULL,
    location_id         bigint   NOT NULL,
    api10               text     NOT NULL CHECK (api10 ~ '^[0-9]{10}$'),
    rank                smallint NOT NULL CHECK (rank >= 1),
    dist_ft             double precision CHECK (dist_ft >= 0),
    state_code          text     CHECK (state_code IN ('30', '42')),
    water_label         text     NOT NULL CHECK (water_label IN ('measured', 'calculated', 'indeterminate', 'insufficient')),
    first_production    date,
    coverage            text     NOT NULL DEFAULT 'covered' CHECK (coverage IN ('covered', 'covered_provisional')),
    PRIMARY KEY (run_id, location_id, api10),
    FOREIGN KEY (run_id, location_id, coverage) REFERENCES box.pud_forecast (run_id, location_id, coverage) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS box_location_water_analog_rank_uq ON box.location_water_analog (run_id, location_id, rank);
CREATE INDEX IF NOT EXISTS box_location_water_analog_api10_ix ON box.location_water_analog (api10);

GRANT SELECT ON box.location_water_analog TO analyst_ro;

COMMENT ON COLUMN box.pud_forecast_stream.tier IS
    'Acceptance tier of THIS stream (sql/62). Water (D107-D110): validated where its group passed the D109 rule (WCA, BS2_S on run 10), else '
    'provisional; never above the location''s coverage tier. NULL on oil / gas rows: their tier is pud_forecast.coverage (covered = validated, '
    'covered_provisional = provisional, D105).';
COMMENT ON TABLE box.location_water_analog IS
    'Named analogs behind each location''s WATER (sql/62, D107): same-bench wells whose water is MEASURED (sql/41 measured; NM unless '
    'insufficient; seller VDR daily water), selected with box_v2''s first-ring rules on circles over 5 / 7.5 / 10 / 15 / 20 mi then 30 / 40 / 50 '
    'mi until 10 eligible. water_label = the label used; a calculated-fallback cohort (fewer than 3 measured at 50 mi) lists its non-measured '
    'wells and the stream row''s params say so. Different from box.location_analog (the oil / gas cohort).';
COMMENT ON TABLE box.pud_forecast_stream IS
    'Per (run, covered location, stream): the fitted P50 per-1,000-ft curve params (oil, gas) or the WOR ratio (water, D107: '
    'ln WOR = alpha + beta * cum oil per 1,000 ft, applied to the RAW box_v2 oil months, D108), lateral multiplier, haircut (water: none), '
    'EUR raw / delivered / per 1,000 ft, cum-12 / 24. tier = the stream''s own acceptance tier (water; sql/62). Water entered with sql/62 '
    '(D72 retired at gate 12b). See sql/60, sql/63.';
