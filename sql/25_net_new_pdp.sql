-- =============================================================================
-- 25 — curated.net_new_pdp  (§6 reverse pass: producers Novi never inventoried)
--
-- The forward pass (curated.reconciled_inventory, sql/21) tags each Novi PUD as
-- realized / remaining / conflict. This is the REVERSE: producing curated wells
-- that drilled where Novi had NO PUD — incremental locations the static (biannual)
-- vintage didn't anticipate. Together they close the §6 arithmetic:
--   new wells since the vintage  ≈  realized PUDs  +  net_new_pdp.
--
-- DEFINITION. A POST-VINTAGE producing horizontal (first_production_date past the
-- 3Q25 Novi vintage) whose lateral does NOT co-extent-overlap any same-bench PUD
-- at the same depth — i.e. best PUD overlap < 0.2 (the realized/conflict floor).
--   * Post-vintage only: a pre-vintage producer trivially overlaps no current PUD
--     (Novi carried it as PDP, not inventory) — that is not "net new", just
--     existing production, so the date filter is essential.
--   * Computed WELL-SIDE (max overlap over PUDs per well), not via
--     reconciled_inventory.matched_api10 — matched_api10 records only the single
--     best well per PUD, so a well co-drilling a PUD with a higher-overlap sibling
--     would be missed and look net_new. The symmetric pass avoids that.
--   * Same bench = the hybrid match of the forward pass (sql/21): same TVD-corrected
--     code within 500 ft OR same depth <= 150 ft regardless of code. The <=150 ft
--     clause keeps ~96 Delaware same-depth label disagreements (mostly sand/carb,
--     where the producing and PUD pipelines tag the same bench differently) OUT of
--     net_new — they are realized, not incremental.
--   * Overlap vs PUD only (not RES): matches the forward pass and the new-well
--     anchor. Excluding wells that sit on a Novi RES stick is a future refinement.
--
-- DEPENDS ON: curated.producing_reference (sql/20), curated.formation_blueox_tvd
--   (sql/23), curated.intel_locations (sql/12), curated.intel_formation_blueox
--   (sql/19).
-- REFRESH: with the Novi load + as wells come online. REFRESH ... CONCURRENTLY.
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.net_new_pdp CASCADE;


CREATE MATERIALIZED VIEW curated.net_new_pdp AS
SELECT
    pr.api10,
    pr.basin                              AS basin_blueox,
    COALESCE(t.corrected_code, pr.code)   AS formation_blueox,
    pr.tvd,
    pr.first_production_date,
    pr.operator,
    pr.ll_ft,
    pr.survey_planned,
    pr.geom                               AS wellstick_geom,
    ROUND(COALESCE(m.best_pud_overlap, 0)::numeric, 3) AS best_pud_overlap
FROM curated.producing_reference pr
LEFT JOIN curated.formation_blueox_tvd t ON t.api10 = pr.api10
LEFT JOIN LATERAL (
    SELECT max(
               ST_Length(ST_Intersection(il.wellstick_geom, pr.corridor)::geography)
                 / NULLIF(ST_Length(il.wellstick_geom::geography), 0)
           ) AS best_pud_overlap
    FROM curated.intel_locations il
    JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
    WHERE il.category = 'PUD'
      AND il.wellstick_geom IS NOT NULL
      AND il.tvd IS NOT NULL
      AND il.basin = pr.basin
      AND ST_Intersects(il.wellstick_geom, pr.corridor)              -- GiST pre-filter
      -- same bench (mirrors the forward pass, sql/21): same (corrected) code within
      -- 500 ft, OR same depth <= 150 ft regardless of code — so a producer realized
      -- by a same-depth PUD whose label merely disagrees is NOT counted net_new.
      AND (
            (fb.formation_blueox = COALESCE(t.corrected_code, pr.code) AND abs(pr.tvd - il.tvd) <= 500)
         OR abs(pr.tvd - il.tvd) <= 150
          )
) m ON TRUE
WHERE pr.first_production_date > DATE '2025-09-30'   -- post the (3Q25) Novi vintage
  AND COALESCE(m.best_pud_overlap, 0) < 0.2          -- realized no PUD
;


CREATE UNIQUE INDEX idx_net_new_pdp_api10
    ON curated.net_new_pdp (api10);

CREATE INDEX idx_net_new_pdp_grp
    ON curated.net_new_pdp (basin_blueox, formation_blueox);

CREATE INDEX idx_net_new_pdp_geom
    ON curated.net_new_pdp USING gist (wellstick_geom);


COMMENT ON MATERIALIZED VIEW curated.net_new_pdp IS
'§6 reverse pass: post-vintage (first_production_date > 2025-09-30) producing horizontals whose lateral overlaps no same-(corrected)-bench PUD at the same depth (best_pud_overlap < 0.2) — incremental locations the static Novi vintage did not inventory. Closes the arithmetic new-wells ≈ realized_pud_to_pdp + net_new_pdp. Keyed on api10; carries wellstick_geom for mapping. Overlap vs PUD only (RES exclusion is a future refinement). Refresh with the Novi load / as wells come online.';
