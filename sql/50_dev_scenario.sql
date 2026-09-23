-- =============================================================================
-- 50 — curated.dev_scenario  (per-well VERTICAL development scenario at first
--      production: topfill / underfill / sandwich / codev_stack / standalone)
--
-- PURPOSE: one reproducible definition of "what was already producing above
-- and below this well when it came on", for scenario-matched analog pulls:
--   * Claude sessions  — scripts/find_analogs.py (API10 list + scenario detail)
--   * anduin           — header sync joins this view; FilterPanel
--                        "Development scenario" section
-- Both read THIS view, so the answers match.
--
-- DERIVED, NOT RE-MEASURED. A plain view over curated.codev_context (sql/47):
-- neighbor membership is the house co-extent rule baked there (1,320-ft
-- geography gate + >= 30% projected lateral coverage, LP->BHL; |dfp| <= 180 d
-- codev, < -180 d parent, > +180 d child). No second classifier, no spatial
-- work here — a well's scenario reads its own codev_context row only.
--
-- VERTICAL-PARENT RULE (convention of record, Michael 2026-09-23 after the
-- step-0 reconciliation against the ad-hoc Pad C 233 / 2025Q3-hindcast rule):
-- a neighbor bench counts as a VERTICAL PARENT bench when
--   bench <> subject bench AND bench <> '(unmapped)'
--   AND it has >= 1 parent (online > 180 d before the subject)
--   AND parent_min_offset_ft   <= 660   (closest parent's lateral MIDPOINT is
--                                         within 660 ft of the subject lateral)
--   AND |parent_nearest_dtvd_ft| <= 1000 (that closest parent's TVD delta)
-- sign of parent_nearest_dtvd_ft (neighbor - subject): > 0 parent BELOW
-- (subject is a topfill), < 0 parent ABOVE (subject is an underfill); 0 = no
-- direction, ignored.
-- WHY the offset gate: without it the 1,320-ft membership gate admits
-- next-bench parents ~1,000 ft away laterally and dilutes the Midland topfill
-- signal (2025Q3 hindcast mop-6 Novi/actual rel. to codev: 1.05x ungated vs
-- 1.12-1.22x gated at 450-900 ft; ad-hoc rule 1.23x). Bench-level stats
-- reproduce the exact per-parent rule on 99.7% of a 1,936-well sample.
--
-- CLASS (precedence top-down; NULL when codev_context.scorable = FALSE):
--   sandwich     vertical parent benches both below AND above
--   topfill      vertical parent below only
--   underfill    vertical parent above only
--   codev_stack  no vertical parent; >= 1 other-bench (mapped) neighbor came
--                on within +-180 d (no offset gate — co-developed pad-mates)
--   standalone   none of the above (parents may exist beyond 660 ft / 1,000 ft,
--                or only in the own bench — see has_same_bench_parent)
-- Same-bench parents (LATERAL infill) are a separate flag, not a class.
--
-- CENSORING: the class is PARENT-side and fully observed at first production
-- — not censored. The child side IS right-censored: a well online < 180 d
-- before the newest first_production_date in the load cannot have a child
-- yet (child_censored = TRUE); child_benches_other reads short on those.
--
-- THRESHOLDS are literals below (660 / 1000 / 180). Retuning is a view-only
-- change: edit here + sql/31 comment + scripts/find_analogs.py docstring.
-- The 180-d parent/codev window is sql/47's and is NOT retunable here
-- (deal-intake asserts it).
--
-- DEPENDS ON: curated.codev_context (sql/47, nightly matview, bench_context
--   parent-only keys added 2026-09-23). CASCADE VICTIM: every re-run of
--   sql/47 (DROP ... CASCADE) drops this view — scripts/apply_codev_context.py,
--   scripts/apply_dev_scenario.py and scripts/apply_reconciled_inventory.py
--   step 1d re-run this file right after sql/47.
-- REFRESH: none (plain view; current as of the last codev_context refresh).
-- CONSUMERS: scripts/find_analogs.py; anduin warehouse_client/wells.py header
--   sync.
-- RUN: python -m scripts.apply_dev_scenario  (sql/47 + this + sql/31 +
--   validate). Idempotent: DROP VIEW IF EXISTS (no CASCADE — anything built on
--   this view must fail loudly, not vanish) + CREATE VIEW.
-- =============================================================================

DROP VIEW IF EXISTS curated.dev_scenario;

CREATE VIEW curated.dev_scenario AS
SELECT
    c.api10,
    c.bench,
    c.first_production_date,
    c.tvd_ft,
    c.scorable,
    CASE
        WHEN NOT c.scorable                           THEN NULL
        WHEN v.n_below > 0 AND v.n_above > 0          THEN 'sandwich'
        WHEN v.n_below > 0                            THEN 'topfill'
        WHEN v.n_above > 0                            THEN 'underfill'
        WHEN cardinality(v.codev_benches_other) > 0   THEN 'codev_stack'
        ELSE 'standalone'
    END                                                             AS scenario_class,
    v.parent_benches_below,
    v.parent_benches_above,
    v.nearest_parent_below_dtvd_ft,
    v.nearest_parent_above_dtvd_ft,
    v.nearest_parent_offset_ft,
    v.youngest_parent_age_days,
    v.oldest_parent_age_days,
    CASE WHEN c.scorable
         THEN COALESCE((c.bench_context -> c.bench ->> 'n_parent')::int, 0) > 0
    END                                                             AS has_same_bench_parent,
    v.codev_benches_other,
    v.child_benches_other,
    c.first_production_date
        > (SELECT max(first_production_date) FROM curated.codev_context) - 180
                                                                    AS child_censored,
    c.bench_context
FROM curated.codev_context c
LEFT JOIN LATERAL (
    SELECT
        count(*) FILTER (WHERE e.vp AND e.dz > 0)                                   AS n_below,
        count(*) FILTER (WHERE e.vp AND e.dz < 0)                                   AS n_above,
        COALESCE(array_agg(e.nbr ORDER BY e.nbr) FILTER (WHERE e.vp AND e.dz > 0), '{}') AS parent_benches_below,
        COALESCE(array_agg(e.nbr ORDER BY e.nbr) FILTER (WHERE e.vp AND e.dz < 0), '{}') AS parent_benches_above,
        min(e.dz) FILTER (WHERE e.vp AND e.dz > 0)                                  AS nearest_parent_below_dtvd_ft,
        max(e.dz) FILTER (WHERE e.vp AND e.dz < 0)                                  AS nearest_parent_above_dtvd_ft,
        min(e.off) FILTER (WHERE e.vp AND e.dz <> 0)                                AS nearest_parent_offset_ft,
        min(e.age_min) FILTER (WHERE e.vp AND e.dz <> 0)                            AS youngest_parent_age_days,
        max(e.age_max) FILTER (WHERE e.vp AND e.dz <> 0)                            AS oldest_parent_age_days,
        COALESCE(array_agg(e.nbr ORDER BY e.nbr) FILTER (WHERE e.n_codev > 0), '{}') AS codev_benches_other,
        COALESCE(array_agg(e.nbr ORDER BY e.nbr) FILTER (WHERE e.n_child > 0), '{}') AS child_benches_other
    FROM (
        SELECT
            j.key                                              AS nbr,
            (j.value ->> 'n_codev')::int                       AS n_codev,
            (j.value ->> 'n_child')::int                       AS n_child,
            (j.value ->> 'parent_min_offset_ft')::numeric      AS off,
            (j.value ->> 'parent_nearest_dtvd_ft')::numeric    AS dz,
            (j.value ->> 'parent_min_age_days')::int           AS age_min,
            (j.value ->> 'parent_max_age_days')::int           AS age_max,
            COALESCE((j.value ->> 'n_parent')::int, 0) > 0
              AND (j.value ->> 'parent_min_offset_ft')::numeric <= 660             -- BAKED offset gate, ft
              AND abs((j.value ->> 'parent_nearest_dtvd_ft')::numeric) <= 1000     -- BAKED vertical band, ft
                                                               AS vp
        FROM jsonb_each(c.bench_context) j
        WHERE j.key <> c.bench
          AND j.key <> '(unmapped)'
    ) e
) v ON c.scorable;

COMMENT ON VIEW curated.dev_scenario IS
'Per producing horizontal (api10; row set = curated.codev_context): vertical development scenario at first production, derived from codev_context (house co-extent rule). Vertical parent bench = other mapped bench with a parent online > 180 d earlier whose lateral midpoint is within 660 ft of the subject lateral and whose TVD delta is within 1,000 ft; above/below by the sign of that parent''s TVD delta. scenario_class: sandwich (parents above and below) > topfill (below) > underfill (above) > codev_stack (other-bench neighbor within +-180 d) > standalone; NULL when not scorable. Same-bench (lateral infill) parents flagged separately. Class is parent-side and not censored; child_benches_other is right-censored (child_censored). Thresholds baked in the view body. sql/50.';
