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
-- SAME-BENCH TEST (hybrid, code + depth):
--   * same TVD-CORRECTED producing code (sql/23) within |well.tvd-pud.tvd| <= 500 ft
--     — the permit-slop guard, kept because the code agreeing corroborates the match
--     (calibration: realized TVD gap median 120 / p90 349 ft; the >500 tail is
--     stacked mis-tags, benches ~500 ft apart); OR
--   * essentially the same depth (<= 150 ft) regardless of code — the producing and
--     PUD pipelines disagree on the LABEL for ~96 same-depth Delaware pairs (mostly
--     sand/carb), which are the same bench actually drilled; depth is the physical
--     arbiter the labels lack.
-- The recolor (sql/23) fixes the producing side's gross Enverus-substitution
-- mis-tags (Novi WOLFCAMP A -> Enverus "2nd Bone Spring"); the <=150 ft clause
-- mops up the residual producer-vs-PUD label disagreements. PUD codes come from
-- the inferred/crosswalk tiers (sql/19), unaffected by the producing recolor.
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
--   (sql/19), curated.producing_reference (sql/20), curated.formation_blueox_tvd
--   (sql/23, for the corrected producing-side bench).
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
    -- TRUE => the realizing well is still on a pre-drill PLAN survey, so the
    -- depth-confirmation behind this match rests on a provisional (permit) TVD
    -- and should be re-checked when the actual survey lands (mostly NM).
    m.matched_survey_planned,
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
        (array_agg(c.api10 ORDER BY c.overlap DESC))[1]          AS matched_api10,
        (array_agg(c.survey_planned ORDER BY c.overlap DESC))[1] AS matched_survey_planned,
        max(c.overlap)                                           AS best_overlap,
        count(*) FILTER (WHERE c.overlap >= 0.5)                 AS n_strong
    FROM (
        SELECT pr.api10, pr.survey_planned,
               ST_Length(ST_Intersection(pud.geom, pr.corridor)::geography)
                 / NULLIF(ST_Length(pud.geom::geography), 0) AS overlap
        FROM curated.producing_reference pr
        LEFT JOIN curated.formation_blueox_tvd t ON t.api10 = pr.api10
        WHERE pr.basin = pud.basin
          AND ST_Intersects(pud.geom, pr.corridor)   -- GiST pre-filter on corridor
          AND pr.tvd IS NOT NULL
          -- SAME BENCH = same code within the 500 ft permit-slop guard, OR — when the
          -- producing and PUD pipelines disagree on the LABEL — essentially the same
          -- depth (<=150 ft, well under bench spacing). The producing code is the
          -- TVD-corrected one (sql/23); depth arbitrates the label disagreements
          -- (the two pipelines disagreed on ~96 same-depth Delaware pairs, mostly
          -- sand/carb, which are the same bench drilled, not remaining inventory).
          AND (
                (COALESCE(t.corrected_code, pr.code) = pud.code AND abs(pr.tvd - pud.tvd) <= 500)
             OR abs(pr.tvd - pud.tvd) <= 150
              )
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
'Novi PUD inventory reconciled against producing curated wells by co-extent overlap + same formation_blueox + TVD consistency (|well.tvd-pud.tvd|<=500ft, which kills wrong-depth formation-mistag matches). status in (realized_pud_to_pdp, remaining_pud, conflict); matched_api10 + match_overlap record the realizing well; matched_survey_planned flags realizations whose depth-confirmation rests on a provisional permit survey (re-check when the actual survey lands, mostly NM). Keyed on stick_id (join curated.intel_locations / intel_formation_blueox for attributes). net_new_pdp (producing wells with no PUD) is a separate pass, not yet included. Refresh as wells come online.';
