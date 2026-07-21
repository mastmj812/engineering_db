-- 33: Enverus wells schema drift (2026-07-17) — nine new API columns.
--
-- Enverus added columns to the `wells` dataset; the nightly pull builds its
-- INSERT column list from the API response keys, so raw_enverus.wells must
-- carry every key or the upsert fails (observed: `column "envcompanytype"
-- of relation "wells" does not exist`, failing enverus.pull_wells nightly
-- since 2026-07-17).
--
-- Types follow the sql/03 DDL conventions for analogous columns:
--   dates -> TIMESTAMP WITHOUT TIME ZONE (FirstProdDate), lengths -> REAL
--   (LateralLength_FT), counts -> INTEGER (NumberOfStrings), else TEXT.
-- Idempotent: ADD COLUMN IF NOT EXISTS; safe to re-run. Purely additive —
-- no matview reads these yet, so no downstream rebuild is required.

ALTER TABLE raw_enverus.wells
    ADD COLUMN IF NOT EXISTS envcompanytype                  TEXT,
    ADD COLUMN IF NOT EXISTS enveffectivelaterallength       REAL,
    ADD COLUMN IF NOT EXISTS enveffectivelaterallengthsource TEXT,
    ADD COLUMN IF NOT EXISTS envwellborestatus               TEXT,
    ADD COLUMN IF NOT EXISTS firstinjdate                    TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS injectorwellclass               TEXT,
    ADD COLUMN IF NOT EXISTS lastinjdate                     TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS numberofwellbores               INTEGER,
    ADD COLUMN IF NOT EXISTS survey                          TEXT;
