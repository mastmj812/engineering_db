-- =============================================================================
-- 21 — curated.reconciled_inventory  (§6 PUD reconciliation, overlap-based)
--
-- Overlays the producing curated wells (curated.producing_reference) onto the
-- Novi PUD inventory and tags each PUD with a realization status. The Novi
-- vintage is static (biannual), so some PUDs have been drilled since; this finds
-- them so value shifts from risked PUD to proven PDP, and the rest is the true
-- remaining inventory.
--
-- MATCH = co-extent overlap + same formation_blueox + TVD consistency. For each
-- PUD: overlap = (length of the PUD lateral inside a same-bench producing well's
-- ±150 ft corridor) / (PUD lateral length). Min distance is NOT used — it
-- false-positives on end-to-end laterals across section lines.
--
-- TVD GUARD: a same-bench match must also be at the same depth — require
-- |well.tvd - pud.tvd| <= 500 ft. Without it, a well whose formation_blueox is
-- wrong (e.g. a Wolfcamp well that a vendor mis-tagged Bone Spring, adopted via
-- the WOLFCAMP A->Enverus trigger) passes the same-code filter and matches a
-- Bone Spring PUD it merely sits below (stacked). Calibration of existing
-- realized matches: TVD gap median 120 ft / p90 349 ft, with a 6.4% tail >500 ft
-- that is exactly these mis-tags (benches here are ~500 ft apart). Depth is the
-- independent check the formation tags lack.
--
-- STATUS taxonomy:
--   realized_pud_to_pdp — one producing well covers >=50% of the PUD (drilled
--                         in its slot). matched_api10 / match_overlap recorded.
--   remaining_pud       — no producing well covers >20% (genuinely undeveloped).
--   conflict            — partial cover (20-50%), OR >=2 producing wells each
--                         cover >=50% (re-frac / ambiguous) -> review.
-- net_new_pdp (a producing well with NO overlapping PUD — Novi missed it) is the
-- reverse pass and is NOT in this v1; added next. Cross-check: Delaware wells
-- online since the 3Q25 vintage (~1,761) ~= realized (~1,330) + net_new (~430),
-- which anchors the 0.5 overlap threshold (realized must stay under the new-well
-- count, the remainder being net_new).
--
-- Confidence is the overlap fraction itself for now (match_overlap); a richer
-- match_confidence (azimuth, length ratio) comes with the calibration pass.
--
-- DEPENDS ON: curated.intel_locations (sql/12), curated.intel_formation_blueox
--   (sql/19), curated.producing_reference (sql/20).
-- REFRESH: as new wells come online (the producing set grows) + with the Novi
--   load. Not nightly. REFRESH MATERIALIZED VIEW CONCURRENTLY.
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.reconciled_inventory CASCADE;


CREATE MATERIALIZED VIEW curated.reconciled_inventory AS
WITH pud AS (
    SELECT
        il.stick_id,
        il.wellstick_geom AS geom,
        il.tvd,
        il.basin,
        fb.formation_blueox AS code
    FROM curated.intel_locations il
    JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
    WHERE il.category = 'PUD'
      AND il.wellstick_geom IS NOT NULL
      AND fb.formation_blueox IS NOT NULL
)
SELECT
    pud.stick_id,
    pud.basin                               AS basin_blueox,
    pud.code                                AS formation_blueox,
    m.matched_api10,
    ROUND(m.best_overlap::numeric, 3)       AS match_overlap,
    COALESCE(m.n_strong, 0)                 AS n_overlapping,
    CASE
        WHEN COALESCE(m.n_strong, 0) >= 2  THEN 'conflict'
        WHEN m.best_overlap >= 0.5          THEN 'realized_pud_to_pdp'
        WHEN m.best_overlap >= 0.2          THEN 'conflict'
        ELSE                                     'remaining_pud'
    END                                     AS status
FROM pud
LEFT JOIN LATERAL (
    SELECT
        (array_agg(c.api10 ORDER BY c.overlap DESC))[1] AS matched_api10,
        max(c.overlap)                                  AS best_overlap,
        count(*) FILTER (WHERE c.overlap >= 0.5)        AS n_strong
    FROM (
        SELECT pr.api10,
               ST_Length(ST_Intersection(pud.geom, pr.corridor)::geography)
                 / NULLIF(ST_Length(pud.geom::geography), 0) AS overlap
        FROM curated.producing_reference pr
        WHERE pr.basin = pud.basin
          AND pr.code  = pud.code
          AND ST_Intersects(pud.geom, pr.corridor)   -- GiST pre-filter on corridor
          AND pr.tvd IS NOT NULL
          AND abs(pr.tvd - pud.tvd) <= 500            -- TVD guard: same bench => same depth
    ) c
    WHERE c.overlap > 0.05
) m ON TRUE
;


CREATE UNIQUE INDEX idx_reconciled_inventory_stick
    ON curated.reconciled_inventory (stick_id);

CREATE INDEX idx_reconciled_inventory_status
    ON curated.reconciled_inventory (status);

CREATE INDEX idx_reconciled_inventory_api10
    ON curated.reconciled_inventory (matched_api10) WHERE matched_api10 IS NOT NULL;


COMMENT ON MATERIALIZED VIEW curated.reconciled_inventory IS
'Novi PUD inventory reconciled against producing curated wells by co-extent overlap + same formation_blueox. status in (realized_pud_to_pdp, remaining_pud, conflict); matched_api10 + match_overlap record the realizing well. Keyed on stick_id (join curated.intel_locations / intel_formation_blueox for attributes). net_new_pdp (producing wells with no PUD) is a separate pass, not yet included. Refresh as wells come online.';
