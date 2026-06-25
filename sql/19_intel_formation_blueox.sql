-- =============================================================================
-- 19 — curated.intel_formation_blueox  (Blue Ox formation for Novi intel sticks)
--
-- Assigns a formation_blueox code to every Novi Intelligence stick
-- (curated.intel_locations), so the PUD/RES inventory can be matched to curated
-- wells "in the same formation_blueox" during reconciliation (the §6 spine-flip)
-- and carried into Narvi / valuation. Standalone matview keyed on stick_id;
-- nothing depends on it, so the inference rule can be re-derived cheaply.
--
-- FOUR-TIER PRECEDENCE (COALESCE order):
--   1. pdp_join  — PDP sticks carry a real api10; join curated.formation_blueox.
--   2. inferred  — a COARSE parent tag in a basin that SPLITS it gets a sub-bench
--                  by spatial+TVD inference (see below). Overrides the crosswalk.
--   3. crosswalk — everything else maps via ref.formation_crosswalk on
--                  (basin, UPPER(formation)): the clean specific tags, and coarse
--                  tags in basins that DON'T split (e.g. Midland WOLFCAMP A->WCA_1).
--   4. NULL      — unmapped tail. Empty today: the crosswalk now maps Midland
--                  'Lower Spraberry Sand' -> JM (Jo Mill; its TVD lands ~790 ft
--                  above LSSH, at Jo Mill depth). Reserved for future odd tags.
--
-- WHERE TIER 2 FIRES (curated laterals show >1 sub-bench for that parent∩basin):
--   Delaware: Avalon (AVA_0/1/2), Wolfcamp A (WCA_1/2), Wolfcamp B (WCB_1/2)
--   Midland : Wolfcamp B (WCB_1/2)
--   (Midland Wolfcamp A is single-bench -> tier 3 crosswalk -> WCA_1.)
--
-- INFERENCE (v1): TVD-aware k=1. Absolute TVD does NOT separate the sub-benches
-- basin-wide (structural dip swamps the ~bench-thickness offset), and the nearest
-- HORIZONTAL lateral is often the stacked sibling in the other bench (~63% LOO).
-- So: take the 12 horizontally-nearest same-parent laterals from
-- curated.bench_reference (local neighbourhood keeps the section ~flat), then
-- copy the bench of the one nearest in landing TVD. Leave-one-out accuracy on
-- curated laterals: ~84.5% (Wolfcamp A Delaware is the soft spot at ~79%).
-- Escalation path (later): k>1 weighted vote + a populated
-- formation_blueox_confidence to route thin/ambiguous picks to review.
--
-- DEPENDS ON: curated.intel_locations (sql/12), curated.bench_reference (sql/18),
--   curated.formation_blueox (sql/16), ref.formation_crosswalk (sql/14).
-- REFRESH: with the (biannual) Novi Intelligence load + on-demand. NOT in the
--   nightly refresh_all.
--   REFRESH MATERIALIZED VIEW CONCURRENTLY curated.intel_formation_blueox;
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.intel_formation_blueox CASCADE;


CREATE MATERIALIZED VIEW curated.intel_formation_blueox AS
WITH
-- Tier-2 candidates: coarse parent tags in a basin that splits them.
coarse AS (
    SELECT
        il.stick_id,
        il.basin,
        il.tvd,
        il.wellstick_geom AS geom,
        CASE UPPER(il.formation)
            WHEN 'WOLFCAMP A' THEN 'WCA'
            WHEN 'WOLFCAMP B' THEN 'WCB'
            WHEN 'AVALON'     THEN 'AVA'
        END AS parent
    FROM curated.intel_locations il
    WHERE il.category IN ('PUD','RES')
      AND il.wellstick_geom IS NOT NULL
      AND il.tvd IS NOT NULL
      AND (
            (il.basin = 'delaware' AND UPPER(il.formation) IN ('WOLFCAMP A','WOLFCAMP B','AVALON'))
         OR (il.basin = 'midland'  AND UPPER(il.formation) = 'WOLFCAMP B')
          )
),
-- TVD-aware k=1: 12-lateral horizontal neighbourhood (same parent∩basin, off the
-- GiST-indexed curated.bench_reference) -> the one nearest in landing TVD.
inferred AS (
    SELECT co.stick_id, nn.bench AS code
    FROM coarse co
    CROSS JOIN LATERAL (
        SELECT cand.bench
        FROM (
            SELECT br.bench, br.tvd
            FROM curated.bench_reference br
            WHERE br.basin = co.basin
              AND br.parent = co.parent
            ORDER BY br.geom <-> co.geom
            LIMIT 12
        ) cand
        ORDER BY abs(cand.tvd - co.tvd)
        LIMIT 1
    ) nn
)
SELECT
    il.stick_id,
    il.formation                                                AS formation_blueox_raw,
    il.basin                                                    AS basin_blueox,
    COALESCE(pdp.formation_blueox, inf.code, cx.canonical_code) AS formation_blueox,
    CASE
        WHEN pdp.formation_blueox IS NOT NULL THEN 'pdp_join'
        WHEN inf.code             IS NOT NULL THEN 'inferred'
        WHEN cx.canonical_code    IS NOT NULL THEN 'crosswalk'
    END                                                         AS formation_blueox_source,
    -- Populated by the later confidence pass (k>1 agreement, TVD margin, …).
    NULL::real                                                  AS formation_blueox_confidence
FROM curated.intel_locations il
LEFT JOIN curated.formation_blueox pdp ON pdp.api10 = il.api10          -- tier 1 (api10 NULL on PUD/RES -> no match)
LEFT JOIN inferred             inf     ON inf.stick_id = il.stick_id    -- tier 2
LEFT JOIN ref.formation_crosswalk cx   ON cx.basin = il.basin           -- tier 3
                                      AND cx.raw_value = UPPER(il.formation)
;


-- Unique on stick_id — required for REFRESH ... CONCURRENTLY.
CREATE UNIQUE INDEX idx_intel_formation_blueox_stick
    ON curated.intel_formation_blueox (stick_id);

CREATE INDEX idx_intel_formation_blueox_code
    ON curated.intel_formation_blueox (formation_blueox);

CREATE INDEX idx_intel_formation_blueox_source
    ON curated.intel_formation_blueox (formation_blueox_source);


COMMENT ON MATERIALIZED VIEW curated.intel_formation_blueox IS
'Blue Ox formation code per Novi Intelligence stick (curated.intel_locations), keyed on stick_id. Four-tier: PDP api10-join -> spatial+TVD inference (off curated.bench_reference) for coarse parents that split (Delaware Avalon/WolfcampA/WolfcampB, Midland WolfcampB) -> ref.formation_crosswalk -> NULL. Inference v1 = TVD-aware k=1 (12-lateral horizontal neighbourhood, then TVD-nearest; ~84.5% leave-one-out). formation_blueox_source in (pdp_join, inferred, crosswalk, NULL). Refresh with the biannual Novi Intelligence load, not nightly.';
