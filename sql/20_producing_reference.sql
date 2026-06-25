-- =============================================================================
-- 20 — curated.producing_reference  (spatial reference for PUD reconciliation)
--
-- Producing curated wells (the system of record for "what exists"), pre-joined
-- to formation_blueox and pre-buffered into a ±150 ft corridor, GiST-indexed.
-- curated.reconciled_inventory (sql/21) overlaps each Novi PUD against this to
-- decide realized vs remaining.
--
-- Why a pre-buffered corridor: the realized signal is CO-EXTENT OVERLAP, not
-- minimum distance. Min line-to-line distance goes to ~0 at the toe-to-heel
-- junction of end-to-end laterals across a section line, so it false-positives
-- on sequential (non-overlapping) wells. Overlap = (length of the PUD lateral
-- inside the producing well's corridor) / (PUD lateral length); end-to-end
-- laterals overlap ~0%, a well drilled in the PUD's slot overlaps ~100%.
-- 46 m ≈ 150 ft half-width: well below same-bench spacing (~900 ft), so it
-- can't catch the adjacent slot.
--
-- DEPENDS ON: curated.wells (sql/04), curated.formation_blueox (sql/16).
-- REFRESH: with curated.formation_blueox / as new wells come online (the set
-- grows as wells start producing). REFRESH MATERIALIZED VIEW CONCURRENTLY.
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.producing_reference CASCADE;


CREATE MATERIALIZED VIEW curated.producing_reference AS
SELECT
    w.api10,
    w.wellstick_geom                                  AS geom,
    -- ±150 ft corridor (buffer the lateral on the geography, store as geometry).
    ST_Buffer(w.wellstick_geom::geography, 46)::geometry AS corridor,
    fb.basin_blueox                                   AS basin,
    fb.formation_blueox                               AS code,
    w.tvd_ft                                          AS tvd,
    -- TRUE = the survey on file is the operator's pre-drill PLAN (permit), so
    -- tvd is provisional and will change when the actual survey is filed. ~44%
    -- of NM producers, ~0% of TX. Carried so the TVD-guard match can be flagged
    -- as resting on a provisional depth. See reference_directional_survey_trust.
    w.directional_survey_is_planned                   AS survey_planned,
    w.first_production_date,
    w.current_operator                                AS operator,
    w.lateral_length_ft                               AS ll_ft
FROM curated.wells w
JOIN curated.formation_blueox fb ON fb.api10 = w.api10
WHERE w.first_production_date IS NOT NULL
  AND w.wellstick_geom IS NOT NULL
  AND fb.formation_blueox IS NOT NULL
  AND fb.basin_blueox IN ('delaware', 'midland')
;


CREATE UNIQUE INDEX idx_producing_reference_api10
    ON curated.producing_reference (api10);

-- Corridor GiST drives the ST_Intersects candidate pre-filter in sql/21.
CREATE INDEX idx_producing_reference_corridor
    ON curated.producing_reference USING gist (corridor);

CREATE INDEX idx_producing_reference_grp
    ON curated.producing_reference (basin, code);


COMMENT ON MATERIALIZED VIEW curated.producing_reference IS
'Producing curated wells (first_production_date NOT NULL) pre-joined to formation_blueox and pre-buffered into a ±150 ft corridor, GiST-indexed. Spatial reference for curated.reconciled_inventory: a Novi PUD is realized when a same-bench producing well''s corridor covers most of the PUD lateral (co-extent overlap, not min distance). Refresh as wells come online.';
