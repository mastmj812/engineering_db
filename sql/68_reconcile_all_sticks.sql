-- =============================================================================
-- 68 — curated.reconciled_inventory over EVERY Novi stick (supersedes sql/21)
--
-- D117 (Michael, 2026-10-21; docs/box/universe-2026-10-21/AUDIT.md): a Novi stick
-- inside the BOX extent for its bench is in the BOX universe whatever Novi's
-- BASE_CASE / EMERGING (PUD / RES) tag. BOX's universe filters on reconciliation
-- (remaining_pud | conflict | not reconciled), so the reconciliation must cover RES
-- sticks too — otherwise a drilled RES slot would read "not reconciled" = remaining.
--
-- WHAT CHANGED vs sql/21: only the stick filter (category IN ('PUD','RES')) and a
-- new `category` column (+ index). The match rule — co-extent overlap of the
-- stick inside a same-bench producer's ±150 ft corridor, same TVD-corrected code
-- within 500 ft OR same depth <= 150 ft, the drift / phantom split at the vintage
-- date, the 0.5 / 0.2 thresholds — is sql/21's, byte for byte. PUD rows are
-- identical to sql/21's (verified by scripts/apply_reconcile_all_sticks).
-- See sql/21 for the rule's rationale and calibration; it stays as a pointer.
--
-- MEASURED read-only 2026-10-21 (2026Q3): RES Delaware 49,188 remaining /
-- 120 conflict / 294 realized_phantom / 0 drift; Midland 25,052 / 19 / 29 / 0.
-- The 312 realizing producers were already matched to a Novi PUD.
--
-- CHANGED 2026-11-25 (BOX sticks phase 8, sql/80): the drift / phantom split reads the
-- Novi vintage date of the stick's OWN basin (curated.intel_vintage_date_by_basin()),
-- not the one newest date. The basins reload on their own schedule (Delaware 2026Q3,
-- Midland 2026Q4). With production through 2026-09 no stick changes class.
--
-- CASCADE: dropping reconciled_inventory drops curated.intel_forecast_accuracy
-- (sql/38); rebuild it with scripts.apply_intel_forecast_accuracy. Since BOX sticks
-- phase 7 item 2 it no longer drops curated.erebor_locations (sql/22 reads no Novi
-- relation).
-- In the quarterly chain this file runs where sql/21 did
-- (scripts/apply_reconciled_inventory, after sql/50).
--
-- DEPENDS ON: curated.intel_locations (sql/29), curated.intel_formation_blueox
--   (sql/19), curated.producing_reference (sql/20), curated.formation_blueox_tvd
--   (sql/23). Quarterly-owned; REFRESH ... CONCURRENTLY as wells come online.
-- =============================================================================


DROP MATERIALIZED VIEW IF EXISTS curated.reconciled_inventory CASCADE;


CREATE MATERIALIZED VIEW curated.reconciled_inventory AS
WITH vint AS MATERIALIZED (
    -- one row per basin, computed ONCE (a per-row call would not be: the old bare
    -- call of the one-date function cost ~8 h here before it became an InitPlan)
    SELECT basin, vintage_date FROM curated.intel_vintage_date_by_basin()
),
pud AS (
    SELECT
        il.stick_id,
        il.wellstick_geom AS geom,
        il.tvd,
        il.basin,
        il.category,
        fb.formation_blueox AS code
    FROM curated.intel_locations il
    JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
    -- D117 (2026-10-21): every Novi stick, whatever Novi's BASE_CASE / EMERGING
    -- tag. category is carried for audit splits only; nothing keys on it.
    WHERE il.category IN ('PUD', 'RES')
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
    m.matched_first_prod,
    CASE
        WHEN COALESCE(m.n_strong, 0) >= 2  THEN 'conflict'
        -- one well covers >=50% => realized. Split by vintage: a well online AFTER
        -- the loaded Novi vintage OF THE STICK'S BASIN (vint, sql/80) is genuine
        -- DRIFT (real PUD->PDP value shift); one online BEFORE it means Novi listed
        -- an already-drilled slot => PHANTOM inventory (never real; e.g. Eddy 324).
        WHEN m.best_overlap >= 0.5 AND m.matched_first_prod > v.vintage_date
                                            THEN 'realized_drift'
        WHEN m.best_overlap >= 0.5          THEN 'realized_phantom'
        WHEN m.best_overlap >= 0.2          THEN 'conflict'
        ELSE                                     'remaining_pud'
    END                                     AS status,
    pud.category                            AS category
FROM pud
LEFT JOIN LATERAL (
    SELECT
        (array_agg(c.api10 ORDER BY c.overlap DESC))[1]          AS matched_api10,
        (array_agg(c.survey_planned ORDER BY c.overlap DESC))[1] AS matched_survey_planned,
        (array_agg(c.first_production_date ORDER BY c.overlap DESC))[1] AS matched_first_prod,
        max(c.overlap)                                           AS best_overlap,
        count(*) FILTER (WHERE c.overlap >= 0.5)                 AS n_strong
    FROM (
        SELECT pr.api10, pr.survey_planned, pr.first_production_date,
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
LEFT JOIN vint v ON v.basin = pud.basin
;


CREATE UNIQUE INDEX idx_reconciled_inventory_stick
    ON curated.reconciled_inventory (stick_id);

CREATE INDEX idx_reconciled_inventory_status
    ON curated.reconciled_inventory (status);

CREATE INDEX idx_reconciled_inventory_api10
    ON curated.reconciled_inventory (matched_api10) WHERE matched_api10 IS NOT NULL;


CREATE INDEX idx_reconciled_inventory_category
    ON curated.reconciled_inventory (category, status);


COMMENT ON MATERIALIZED VIEW curated.reconciled_inventory IS
'Every Novi stick (PUD = BASE_CASE and RES = EMERGING; D117, sql/68 supersedes sql/21) reconciled against producing curated wells by co-extent overlap + same (corrected) formation_blueox-or-depth + TVD consistency. status in (realized_drift, realized_phantom, remaining_pud, conflict): realized is split by the realizing well''s vintage — drift = online after the vintage (real stick->PDP), phantom = online before it (Novi listed an already-drilled slot). remaining_pud is the legacy label for "unrealized" and applies to RES sticks too. matched_api10 / match_overlap / matched_first_prod record the realizing well; matched_survey_planned flags realizations resting on a provisional permit survey (mostly NM). category = Novi''s tag, carried for audit splits only (D117: it decides nothing). Keyed on stick_id; one row per mapped Novi stick with geometry. The reverse pass (producing wells with no stick, formerly curated.net_new_pdp, sql/25) is retired. Refresh as wells come online.';
COMMENT ON COLUMN curated.reconciled_inventory.category IS
'Novi''s tag of the stick (PUD = BASE_CASE, RES = EMERGING), for audit splits only. D117: BOX and the apps do not key on it.';
