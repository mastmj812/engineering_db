-- =============================================================================
-- Reference layer: ref.formation_crosswalk
--
-- Human-maintained mapping from a raw upstream formation string (a Novi
-- formation name OR an Enverus ENVInterval string) to the Blue Ox canonical
-- nomenclature code, keyed by basin. Consumed by curated.wells (sql/04) to
-- populate `formation_blueox`.
--
-- Why a seed table (not an inline CASE): the mapping is interpretable,
-- traceable (one diffable CSV row per decision, with a rationale `notes`
-- column), and editable without touching SQL. Edit the loop:
--     1. edit seeds/formation_crosswalk.csv
--     2. re-run this file:  psql -d oilgas -f sql/14_formation_crosswalk.sql
--     3. refresh:           SELECT curated.refresh_all();   (or REFRESH
--                           MATERIALIZED VIEW CONCURRENTLY curated.wells)
--
-- Join contract (see sql/04): curated.wells joins on (basin, raw_value).
--   - `basin`       : 'delaware' | 'midland' (matches basin_blueox).
--   - `raw_value`   : EXACT upstream string (case-sensitive).
--   - `source`      : 'novi' | 'enverus' | 'both' — documentation only; NOT
--                     part of the join key. A raw_value that occurs in both
--                     sources within a basin is a single row tagged 'both'.
--   - `canonical_code` : value from nomenclature.xlsx (e.g. WCA_1, BS3_S, OTHER).
--   - `notes`       : free-text rationale / review flags.
--
-- Run order: standalone reference data; apply before sql/16 builds
-- curated.formation_blueox, which LEFT JOINs it (the sql/17 migration enforces
-- this ordering). \copy is client-side and path-relative — run psql from the
-- repo root.
-- =============================================================================


CREATE SCHEMA IF NOT EXISTS ref;


CREATE TABLE IF NOT EXISTS ref.formation_crosswalk (
    basin          text NOT NULL,            -- 'delaware' | 'midland'
    source         text,                     -- 'novi' | 'enverus' | 'both' (doc only)
    raw_value      text NOT NULL,            -- exact upstream string
    canonical_code text NOT NULL,            -- Blue Ox nomenclature code
    notes          text,
    PRIMARY KEY (basin, raw_value)
);


-- Idempotent reload: the CSV is the source of truth, so wipe and re-seed.
TRUNCATE ref.formation_crosswalk;

\copy ref.formation_crosswalk (basin, source, raw_value, canonical_code, notes) FROM 'seeds/formation_crosswalk.csv' WITH (FORMAT csv, HEADER true)


COMMENT ON TABLE ref.formation_crosswalk IS
'Maps raw upstream formation strings (Novi formation names or Enverus ENVInterval strings) to Blue Ox canonical nomenclature codes, per basin. Seeded from seeds/formation_crosswalk.csv. Joined by curated.wells on (basin, raw_value) to populate formation_blueox.';
