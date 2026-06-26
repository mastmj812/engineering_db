-- =============================================================================
-- 23 — curated.formation_blueox_tvd  (TVD-sanity audit + recolor for producers)
--
-- The formation_blueox precedence rule (sql/16) substitutes Enverus env_interval
-- for four coarse Novi formations (AVALON / WOLFCAMP A / WOLFCAMP B / LOWER
-- SPRABERRY SAND). When Enverus's call disagrees with Novi by a whole play group
-- the substitution lands a well in the wrong bench entirely — e.g. api10
-- 3002550278: Novi=WOLFCAMP A, Enverus="2ND BONE SPRING SAND" -> tagged BS2_S,
-- but it lands at 12,415 ft where the LOCAL BS2_S band is ~11,135 ft and the
-- local WCA_1 band is ~12,473 ft. Depth (and Novi) both say Wolfcamp A; only the
-- over-trusted Enverus call dissented.
--
-- This view catches that class of error WITHOUT a global depth band (benches dip,
-- so depth is only meaningful LOCALLY). For each producing horizontal it builds a
-- per-bench depth profile from its 40 nearest producing neighbours (same basin),
-- then:
--   * assigned_med = local median TVD of the well's OWN assigned bench
--   * nearest_code = the bench whose local median TVD is closest to the well's TVD
--                    (restricted to bands with >= 3 local wells, to ignore noise)
-- and recolors to nearest_code iff the well is a clear depth outlier for its
-- assigned bench AND the nearest band is decisively closer (>= 400 ft).
--
-- PERMIT-DEPTH HANDLING. A TVD that is an exact multiple of 100 ft (12,000 /
-- 11,500 / 10,600 …) is almost always a permit/plan depth carried forward, not an
-- actual landing — a real survey reads 12,415, not 12,000. These are ~3% of wells
-- and, in TX/Midland, are the ONLY permit tell (directional_survey_is_planned is
-- ~0 there). So:
--   (a) round-100 depths are EXCLUDED from the reference medians, so bands reflect
--       real landings; and
--   (b) a well whose own depth is permit_suspect (round-100 OR survey_planned) is
--       only flipped when MORE grossly off (> 1000 ft, vs > 600 ft for a trusted
--       survey depth) — 600 ft is within permit slop, 1000+ ft is a play-group miss
--       even allowing for it.
-- Median is robust to the residual mis-tags being corrected, so the (lightly
-- de-permited) reference is fine for v1; no second pass needed.
--
-- CONSERVATISM GUARDS (so only high-confidence flips fire):
--   (1) BAND SUPPORT: both the assigned and target bands must have >= 5 local
--       wells. Rare/deep benches (Woodford especially) have thin, noisy local
--       bands whose median is untrustworthy — e.g. local WDFD "median" jumping
--       11,300 -> 13,944 ft in one area — so a flip off 3 scattered wells is not
--       believable.
--   (2) PROTECTED BENCHES: never flip into OR out of WDFD / BRNT / MISS. Woodford
--       is core acquisition strategy (don't strip a two-source Woodford tag on a
--       noisy band); Barnett/Miss are sparse deep benches with the same problem.
--   (3) NO SAND<->CARB SWAPS within one interval (BS2_S<->BS2_C, BS3_S<->BS3_C):
--       sand vs carbonate is a lithology call, and the two interfinger at nearly
--       the same depth — depth cannot resolve it. (WCA_1<->WCA_2, AVA_0/1/2 are
--       genuine depth-ordered benches and are NOT suppressed.)
--
-- This is an AUDIT object: it changes nothing consumed. The override is applied
-- downstream in curated.wells_enriched (sql/06), where canonical formation_blueox
-- becomes COALESCE(corrected_code, base) with the base preserved.
--
-- DEPENDS ON: curated.producing_reference (sql/20) + a GiST index on its geom
-- (created here if missing; also added to sql/20 for future rebuilds).
-- REFRESH: after curated.producing_reference, before curated.wells_enriched.
-- =============================================================================


-- KNN driver: producing_reference ships a GiST on `corridor`, not on the lateral
-- `geom`. The <-> nearest-neighbour scan needs geom indexed. IF NOT EXISTS so it
-- is harmless when sql/20 already created it on a fresh rebuild.
CREATE INDEX IF NOT EXISTS idx_producing_reference_geom
    ON curated.producing_reference USING gist (geom);


DROP MATERIALIZED VIEW IF EXISTS curated.formation_blueox_tvd CASCADE;


CREATE MATERIALIZED VIEW curated.formation_blueox_tvd AS
WITH prof AS (
    -- One row per (well, neighbouring bench): the local median TVD of that bench
    -- among the well's 40 nearest producing neighbours in the same basin,
    -- EXCLUDING permit-round (x100) depths so the band reflects actual landings.
    SELECT
        pr.api10,
        pr.basin,
        pr.code                                                AS assigned_code,
        pr.tvd,
        pr.survey_planned,
        nb.code                                                AS nb_code,
        nb.med                                                 AS nb_med,
        nb.n                                                   AS nb_n
    FROM curated.producing_reference pr
    LEFT JOIN LATERAL (
        SELECT
            nbr.code,
            percentile_cont(0.5) WITHIN GROUP (ORDER BY nbr.tvd) AS med,
            count(*)                                             AS n
        FROM (
            SELECT pr2.code, pr2.tvd
            FROM curated.producing_reference pr2
            WHERE pr2.basin = pr.basin
              AND pr2.api10 <> pr.api10
              AND pr2.tvd IS NOT NULL
              AND pr2.tvd::numeric % 100 <> 0   -- drop permit-round depths
            ORDER BY pr2.geom <-> pr.geom
            LIMIT 40
        ) nbr
        WHERE nbr.code IS NOT NULL
        GROUP BY nbr.code
    ) nb ON TRUE
    WHERE pr.tvd IS NOT NULL
      AND pr.code IS NOT NULL
),
agg AS (
    SELECT
        api10,
        basin,
        assigned_code,
        tvd,
        survey_planned,
        -- exactly one prof row per (api10, nb_code), so max() picks that value
        max(nb_med) FILTER (WHERE nb_code = assigned_code)      AS assigned_med,
        max(nb_n)   FILTER (WHERE nb_code = assigned_code)      AS assigned_n,
        -- nearest band by |tvd - median|, among bands with >= 3 local wells
        -- (>= 3 to SELECT the nearest transparently; the >= 5 support bar is
        -- enforced in the flip gate below so a thin nearest is reported, not used)
        (array_agg(nb_code ORDER BY abs(tvd - nb_med))
            FILTER (WHERE nb_n >= 3))[1]                        AS nearest_code,
        (array_agg(nb_med  ORDER BY abs(tvd - nb_med))
            FILTER (WHERE nb_n >= 3))[1]                        AS nearest_med,
        (array_agg(nb_n    ORDER BY abs(tvd - nb_med))
            FILTER (WHERE nb_n >= 3))[1]                        AS nearest_n
    FROM prof
    GROUP BY api10, basin, assigned_code, tvd, survey_planned
),
scored AS (
    SELECT
        *,
        (tvd::numeric % 100 = 0)                                AS tvd_round,
        ((tvd::numeric % 100 = 0) OR COALESCE(survey_planned, FALSE)) AS permit_suspect
    FROM agg
),
decided AS (
    SELECT
        *,
        (
            -- assigned band established AND a different, well-supported band exists
            assigned_med IS NOT NULL
            AND nearest_code IS NOT NULL
            AND nearest_code IS DISTINCT FROM assigned_code
            -- guard (1): the HOME band must be well-established (>= 5) so "outlier"
            -- is meaningful; the TARGET needs only >= 3 corroborating wells (its
            -- tightness is already enforced by the >= 400 ft margin below). A tight
            -- 3-well target (e.g. a locally under-drilled but real Wolfcamp A band,
            -- gap 58 ft) is trustworthy; the noisy-band risk is Woodford et al.,
            -- handled by guard (2).
            AND assigned_n >= 5
            AND nearest_n  >= 3
            -- clear depth outlier for its own band (wider bar for permit depths)
            AND abs(tvd - assigned_med) > CASE WHEN permit_suspect THEN 1000 ELSE 600 END
            -- the target band is decisively closer
            AND abs(tvd - nearest_med) <= abs(tvd - assigned_med) - 400
            -- guard (2): never flip into/out of sparse/strategic benches; and
            -- never flip TO OTHER (its "band median" is a grab-bag of all depths,
            -- so it is meaningless as a target) — OTHER stays valid as a SOURCE
            -- (uncoded -> real bench is a genuine recovery).
            AND assigned_code NOT IN ('WDFD', 'BRNT', 'MISS')
            AND nearest_code  NOT IN ('WDFD', 'BRNT', 'MISS', 'OTHER')
            -- guard (3): no sand<->carb swap within one interval (same 3-char root,
            -- both end S/C, differing) — depth can't make a lithology call
            AND NOT (
                left(assigned_code, 3) = left(nearest_code, 3)
                AND right(assigned_code, 1) IN ('S', 'C')
                AND right(nearest_code, 1) IN ('S', 'C')
                AND right(assigned_code, 1) <> right(nearest_code, 1)
            )
        )                                                       AS corrected
    FROM scored
)
SELECT
    api10,
    basin,
    assigned_code,
    tvd,
    assigned_med,
    assigned_n,
    nearest_code,
    nearest_med,
    nearest_n,
    survey_planned,
    tvd_round,
    permit_suspect,
    round(abs(tvd - assigned_med))                             AS assigned_gap,
    round(abs(tvd - nearest_med))                              AS nearest_gap,
    corrected,
    CASE WHEN corrected THEN nearest_code ELSE assigned_code END AS corrected_code
FROM decided
;


CREATE UNIQUE INDEX idx_formation_blueox_tvd_api10
    ON curated.formation_blueox_tvd (api10);


COMMENT ON MATERIALIZED VIEW curated.formation_blueox_tvd IS
'TVD-sanity audit for producing horizontals: per-well local (40-NN) per-bench depth profile, gap to the assigned formation_blueox band, depth-nearest band, and a corrected_code that flips the tag only for gross depth outliers. Permit-round (x100) depths are excluded from the reference bands, and permit_suspect wells (round TVD or survey_planned) need a wider gap (1000 ft vs 600 ft) to flip. Catches Enverus-substitution mis-tags (sql/16) like 3002550278 BS2_S->WCA_1. Audit only; override is applied in curated.wells_enriched.';
