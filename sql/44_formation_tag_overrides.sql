-- =============================================================================
-- Reference layer: ref.formation_tag_overrides
--
-- Human-RATIFIED per-well formation_blueox corrections, keyed by api10. This is
-- the "geologist's manual relands" mechanism sql/16 was factored out for: each
-- row is one well whose vendor-derived tag was adjudicated wrong by gunbarrel
-- review and re-tagged by Michael. Rows are decisions of record, never
-- algorithm output — the gunbarrel-consensus detector (2026-09 WCB tag audit)
-- only PROPOSES flags; a row lands here only after MM ratifies it well-by-well
-- (supervised rounds, no auto-flips, no cascade).
--
-- Batch 1 (2026-09-16/17): 47 rows from the Delaware WCB audit — 46 ratified
-- consensus-v2 flags (calibration: 19/20 v1 flags confirmed; detector rules:
-- 1.5-mi neighborhood bands, >=3 clean witnesses, IQR<=150 coherence gate,
-- nearest-member complex distance, 2x own-band margin) + 1 gold label (Kesey
-- Unit 10-7E 8H — MM drilled it, WCB_2 target). Rejected and held flags are
-- deliberately NOT here (Merciless 3002547676 held: destination disputed).
--
-- Consumed by curated.formation_blueox (sql/16): an override wins over the
-- crosswalk result, and formation_blueox_source becomes 'ratified_override'.
-- Because the override arrives via a JOINed table, editing THIS CSV is a
-- CONTENT change: reload here, then
--     REFRESH MATERIALIZED VIEW CONCURRENTLY curated.formation_blueox;
-- and refresh/rebuild the downstream tag consumers (producing_reference,
-- formation_blueox_tvd, reconciled_inventory, bench_reference, intel chain) —
-- in practice: bundle with a quarterly-chain rebuild window.
--
-- Edit loop:
--     1. edit seeds/formation_tag_overrides.csv (one row per ratified decision;
--        `was` records the pre-override tag; `note` carries provenance)
--     2. re-run this file (scripts/apply_formation_tag_overrides.py replicates
--        the \copy for psycopg runs)
--     3. refresh formation_blueox + downstream chain (see above)
--
-- Run order: standalone reference data; before sql/16.
-- =============================================================================


CREATE SCHEMA IF NOT EXISTS ref;


CREATE TABLE IF NOT EXISTS ref.formation_tag_overrides (
    api10          text PRIMARY KEY,   -- universal well key
    corrected_code text NOT NULL,      -- Blue Ox nomenclature code (the ratified tag)
    was            text,               -- pre-override formation_blueox (provenance)
    note           text                -- who/when/evidence — every row cites its ratification
);


-- Idempotent reload: the CSV is the source of truth, so wipe and re-seed.
TRUNCATE ref.formation_tag_overrides;

\copy ref.formation_tag_overrides (api10, corrected_code, was, note) FROM 'seeds/formation_tag_overrides.csv' WITH (FORMAT csv, HEADER true)


COMMENT ON TABLE ref.formation_tag_overrides IS
'Human-ratified per-well formation_blueox corrections (api10-keyed), seeded from seeds/formation_tag_overrides.csv. Overrides win over the crosswalk in curated.formation_blueox (source becomes ratified_override). Rows are decisions of record from gunbarrel review (2026-09 WCB consensus audit, batch 1 = 47 wells) — the consensus detector proposes, a human ratifies, nothing lands here automatically. Edit loop in sql/44 header.';
