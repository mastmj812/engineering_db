-- =============================================================================
-- DRAFT. BOX sticks phase 5a: nightly reconciliation storage. NOT on the apply path, NOT applied anywhere.
-- Gate 5b turns this into a numbered sql/NN (74 is free on main with no open PR as of 2026-11-18; re-check then).
--
-- Ownership: these are ETL-owned objects in `curated` / `meta` / `ref`, written by a nightly hook (the etl/tag_rule.py
-- pattern, sql/72). They READ box.location_set / box.location_stick / box.location_set_dsu / box.location_set_bench and
-- never write schema box, so "the ETL never touches box.*" still holds. Plain tables, not matviews: nothing to add to
-- etl/db.py:_CURATED_MATVIEWS, nothing for the CI matview lint, and no pg dependency on curated.wells (a sql/04
-- CASCADE cannot drop them).
--
-- Additive only. Nothing is dropped or re-pointed; sql/68 and the Novi objects are untouched.
-- =============================================================================

-- 1. One row per nightly run (the meta.formation_tag_run pattern)
CREATE TABLE IF NOT EXISTS meta.box_recon_run (
    run_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    status            text NOT NULL CHECK (status IN ('written', 'breaker', 'failed', 'no_record_set')),
    wrote             boolean NOT NULL DEFAULT false,
    predicate_version text,                      -- etl.box_recon.VERSION: a change of rule is visible in the log
    set_ids           bigint[],                  -- the record box.location_set per basin the run judged
    wells_read        integer,
    counts            jsonb NOT NULL DEFAULT '{}'::jsonb,   -- per basin: status counts, crowded, inventory count
    changed           integer,                   -- locations whose status or crowded flag changed against the previous run
    seconds           double precision,
    error             text
);

-- 2. Today's status: one row per location of the record sets. Rewritten every night from scratch (recomputed, not latched).
CREATE TABLE IF NOT EXISTS curated.box_location_status (
    location_id        bigint  PRIMARY KEY,      -- box.location.location_id = the app-facing stick_id (>= 10,000,001)
    set_id             bigint  NOT NULL,         -- the record set the stick was read from
    basin              text    NOT NULL,
    pad_id             bigint  NOT NULL,
    formation_blueox   text    NOT NULL,
    status             text    NOT NULL CHECK (status IN ('open', 'permitted', 'drilled', 'producing', 'conflict')),
    counts_as_inventory boolean NOT NULL,        -- open and permitted, and not crowded (see the open question on crowded)
    n_legs             smallint NOT NULL,
    legs_matched       smallint NOT NULL DEFAULT 0,   -- a U-turn stick is out of inventory with one leg matched
    matched_api10      text,                     -- the realizing well (best overlap), or the conflicting one
    matched_class      text CHECK (matched_class IN ('producing', 'drilled')),
    match_overlap      numeric(4, 3),            -- best leg overlap, 0 to 1
    match_basis        text CHECK (match_basis IN ('depth', 'planned')),   -- planned = no depth evidence; re-judged when the survey lands
    conflict_reason    text CHECK (conflict_reason IN ('partial_overlap', 'two_wells')),
    permit_api10       text,                     -- an approved permit over >= 0.5 of a leg; a flag only
    crowded            boolean NOT NULL DEFAULT false,   -- open / permitted, and now inside the set's no-place envelope
    crowd_api10        text,
    status_since       date    NOT NULL,         -- first night of the current status (carried from the previous run)
    run_id             bigint  NOT NULL REFERENCES meta.box_recon_run (run_id),
    CONSTRAINT box_location_status_match_ck CHECK ((status IN ('drilled', 'producing')) = (legs_matched > 0 AND conflict_reason IS NULL))
);
CREATE INDEX IF NOT EXISTS box_location_status_status_ix ON curated.box_location_status (basin, status);
CREATE INDEX IF NOT EXISTS box_location_status_api10_ix  ON curated.box_location_status (matched_api10) WHERE matched_api10 IS NOT NULL;
CREATE INDEX IF NOT EXISTS box_location_status_pad_ix    ON curated.box_location_status (pad_id);

-- 3. History: one row per location per night it CHANGED (status, crowded flag, realizing well, or the set under it).
CREATE TABLE IF NOT EXISTS curated.box_location_status_log (
    run_id             bigint  NOT NULL REFERENCES meta.box_recon_run (run_id),
    location_id        bigint  NOT NULL,
    set_id             bigint  NOT NULL,
    cause              text    NOT NULL CHECK (cause IN ('first_run', 'well', 'set_change', 'rule_change', 'override')),
    old_status         text,                     -- NULL on a location's first row
    new_status         text    NOT NULL CHECK (new_status IN ('open', 'permitted', 'drilled', 'producing', 'conflict', 'stopped')),
    old_crowded        boolean,
    new_crowded        boolean NOT NULL,
    old_api10          text,
    new_api10          text,
    match_overlap      numeric(4, 3),
    match_basis        text,
    logged_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, location_id)
);
CREATE INDEX IF NOT EXISTS box_location_status_log_location_ix ON curated.box_location_status_log (location_id, run_id);

-- 4. Card verdicts on conflict rows (the ref.formation_tag_overrides pattern: a repo seed, reloaded by the apply script;
--    never hand-edited). Read by the hook after the predicate; a verdict wins while its well still overlaps the stick.
CREATE TABLE IF NOT EXISTS ref.box_recon_override (
    location_id        bigint  NOT NULL,
    api10              text    NOT NULL,
    verdict            text    NOT NULL CHECK (verdict IN ('drilled', 'not_this_stick')),
    note               text,
    decided_on         date    NOT NULL,
    PRIMARY KEY (location_id, api10)
);

GRANT SELECT ON meta.box_recon_run, curated.box_location_status, curated.box_location_status_log, ref.box_recon_override TO analyst_ro;

-- Spatial indexes: none new. The pair search is ST_DWithin(legs_geom::geography, well line::geography, limit), served by
-- box_location_stick_geog_gix (sql/73), which already exists; EXPLAIN on live 2026-11-18 names it. The wells drive the
-- nested loop, so no index on the well side is needed.
