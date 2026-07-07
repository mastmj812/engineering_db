-- =============================================================================
-- 13 — raw_novi_intel.pud_attrs: PUD machine-learning tier attributes
--
-- The PUD oil inventory ships THREE shapefiles with identical geometry and
-- Unique IDs (verified: 83,282 Delaware / 48,183 Midland, 100% key overlap with
-- the PUD sticks already in raw_novi_intel.sticks):
--   * PUD_Oil                  -> economics; loaded into raw_novi_intel.sticks (sql/11)
--   * Other_ML_PUD_Oil         -> spacing / depletion / completion ML score + tier
--   * Undrilled_Rock_Quality   -> rock-quality ML score + tier
-- This table holds the 8 ML attribute columns from the latter two, keyed by
-- (basin, report_version, unique_id) so the curated layer (sql/12) can LEFT JOIN
-- them onto the PUD sticks for the erebor "Highgrade" screening tab. Tiers are
-- text ('Tier-1'..'Tier-4'); scores are signed ML floats. Geometry is dropped
-- (it duplicates the PUD stick lateral already in raw_novi_intel.sticks).
--
-- Per-basin DBF field drift (handled in the loader; recorded here for reference):
--   Delaware: SpacingS/SpacingT DepletS/DepletT CompletS/CompletT   key 'Unique ID'
--   Midland:  ML-Spacing/ML-Spaci_1 ML-Prior D/ML-Prior_1 ML-Complet/ML-Compl_1
--             key 'Unique Ide' (DBF 10-char truncation)
--   RQS / RQT are identical field names in both basins.
--
-- RUN: scripts/load_novi_intel.py --ddl (creates table) then --pud-attrs (loads).
-- Idempotent: DROP ... IF EXISTS then CREATE, so re-running rebuilds cleanly.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw_novi_intel;

DROP TABLE IF EXISTS raw_novi_intel.pud_attrs CASCADE;
CREATE TABLE raw_novi_intel.pud_attrs (
    basin           TEXT NOT NULL,           -- 'delaware' | 'midland'
    report_version  TEXT NOT NULL,           -- e.g. '3Q25'
    unique_id       TEXT NOT NULL,           -- Novi well name; joins sticks.unique_id (PUD)
    -- spacing / depletion / completion ML scores (signed) + tiers ('Tier-1'..'Tier-4')
    spacing_s       DOUBLE PRECISION,
    spacing_t       TEXT,
    deplet_s        DOUBLE PRECISION,
    deplet_t        TEXT,
    complet_s       DOUBLE PRECISION,
    complet_t       TEXT,
    -- rock-quality ML score (signed) + tier
    rqs             DOUBLE PRECISION,
    rqt             TEXT,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (basin, report_version, unique_id)
);

CREATE INDEX IF NOT EXISTS idx_rni_pud_attrs_uid ON raw_novi_intel.pud_attrs (unique_id);
