-- =============================================================================
-- 74_box_recon.sql - nightly BOX sticks reconciliation: the tables (docs/box_sticks_plan.md, phase 5)
-- =============================================================================
-- Every night, after the curated wells are refreshed, etl/box_recon.py judges every stick of the RECORD
-- box.location_set per basin against today's wells and lists the DSU x bench a new producer has made stale. This file
-- holds only the tables it writes. The rule itself is SQL inside etl/box_recon.py (JUDGE_SQL, STALE_SQL), versioned by
-- etl.box_recon.VERSION and recorded on every run row.
--
--   meta.box_recon_run                one row per nightly run: status, record sets judged, counts, changed, breaker
--   curated.box_location_status       today's status, one row per stick of the record sets; replaced whole every night
--   curated.box_location_status_log   history: one row per location per night it changed
--   curated.box_dsu_bench_stale       DSU x bench holding a producing well of that bench the record set never read:
--                                     the work list of the next regeneration, with an ESTIMATED stick count
--
-- Ownership: ETL-owned (curated / meta), written only by etl/box_recon.py. They READ schema box
-- (box.location_set / _stick / _set_dsu / _set_bench / _set_well) and never write it: "the ETL never touches box.*"
-- still holds. Plain TABLES, not matviews: nothing to REFRESH, not in etl/db.py:_CURATED_MATVIEWS, no dependency on
-- curated.wells (a sql/04 CASCADE cannot drop them), outside the CI matview lint.
--
-- Standing authorization requested with the apply (gate 5c): the nightly writes exactly these four tables, every
-- night, behind the circuit breaker (max(200, 1 %) of locations changed with the same record sets and rule version).
--
-- Decisions of record (plan decision table, 2026-11-18): only a PRODUCING well takes a stick out; conflict = a well
-- alongside 30 to 50 % of a stick leg; three generator rules mirrored; flat-ended corridors; a stale row per DSU x
-- bench. Until gate 5 proper NOTHING reads these tables: they drive no count and no app.
--
-- DEPENDS ON: schemas curated, meta; sql/73 (box.location_set and its record sets) for the writer, not for this DDL.
-- Additive only: nothing is dropped or re-pointed; sql/68 and the Novi objects are untouched. Spatial index: none new.
-- The writer's pair search is ST_DWithin(legs_geom::geography, well line::geography, limit), served by
-- box_location_stick_geog_gix (sql/73; the sql/26 rule); scripts.apply_box_recon asserts EXPLAIN names it.
-- Not exposed to the Supabase Data API. Idempotent.
--
-- RUN: python -m scripts.apply_box_recon      (!! go-apply required; rehearsal container first)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. meta.box_recon_run: one row per nightly run (the meta.formation_tag_run pattern, sql/72)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta.box_recon_run (
    run_id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    status            text    NOT NULL CHECK (status IN ('written', 'breaker', 'failed')),
    wrote             boolean NOT NULL DEFAULT false,
    predicate_version text    NOT NULL,                  -- etl.box_recon.VERSION
    set_ids           bigint[],                          -- the record box.location_set per basin that were judged
    wells_read        integer,
    counts            jsonb   NOT NULL DEFAULT '{}'::jsonb,   -- per basin: sticks, each status, crowded, inventory
    changed           integer,                           -- locations that differ from the previous night's table
    breaker_limit     integer,
    stale_dsu_bench   integer,
    seconds           double precision,
    error             text,
    CONSTRAINT box_recon_run_wrote_ck CHECK (wrote = (status = 'written'))
);

-- ---------------------------------------------------------------------------
-- 2. curated.box_location_status: today's status, one row per stick of the record sets
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS curated.box_location_status (
    location_id         bigint  PRIMARY KEY,             -- box.location.location_id = the app-facing stick_id (>= 10,000,001)
    set_id              bigint  NOT NULL,                -- the record set the stick was read from
    basin               text    NOT NULL CHECK (basin IN ('delaware', 'midland')),
    pad_id              bigint  NOT NULL,
    formation_blueox    text    NOT NULL,
    n_legs              smallint NOT NULL CHECK (n_legs IN (1, 2)),
    status              text    NOT NULL CHECK (status IN ('open', 'permitted', 'pending', 'producing', 'conflict')),
    counts_as_inventory boolean NOT NULL,
    legs_matched        smallint NOT NULL DEFAULT 0,
    matched_api10       text,
    match_overlap       numeric(4, 3) CHECK (match_overlap BETWEEN 0 AND 1),
    match_basis         text    CHECK (match_basis IN ('depth', 'planned')),
    conflict_reason     text    CHECK (conflict_reason IN ('partial_overlap', 'two_wells')),
    pending_api10       text,
    permit_api10        text,
    crowded             boolean NOT NULL DEFAULT false,
    crowd_api10         text,
    status_since        date    NOT NULL,
    run_id              bigint  NOT NULL REFERENCES meta.box_recon_run (run_id),
    CONSTRAINT box_location_status_inventory_ck CHECK (counts_as_inventory = (status IN ('open', 'permitted', 'pending') AND NOT crowded)),
    CONSTRAINT box_location_status_match_ck CHECK ((status IN ('producing', 'conflict')) = (matched_api10 IS NOT NULL)
        AND (status = 'producing') = (legs_matched > 0) AND (status = 'conflict') = (conflict_reason IS NOT NULL)),
    CONSTRAINT box_location_status_crowd_ck CHECK (crowded = (crowd_api10 IS NOT NULL) AND NOT (crowded AND status IN ('producing', 'conflict')))
);
CREATE INDEX IF NOT EXISTS box_location_status_status_ix ON curated.box_location_status (basin, status);
CREATE INDEX IF NOT EXISTS box_location_status_pad_ix    ON curated.box_location_status (pad_id, formation_blueox);
CREATE INDEX IF NOT EXISTS box_location_status_api10_ix  ON curated.box_location_status (matched_api10) WHERE matched_api10 IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. curated.box_location_status_log: one row per location per night it changed
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS curated.box_location_status_log (
    run_id        bigint  NOT NULL REFERENCES meta.box_recon_run (run_id),
    location_id   bigint  NOT NULL,
    set_id        bigint  NOT NULL,
    cause         text    NOT NULL CHECK (cause IN ('first_run', 'well', 'set_change', 'rule_change')),
    old_status    text,                                  -- NULL on a location's first row
    new_status    text    NOT NULL CHECK (new_status IN ('open', 'permitted', 'pending', 'producing', 'conflict', 'stopped')),
    old_crowded   boolean,
    new_crowded   boolean NOT NULL,
    old_api10     text,
    new_api10     text,
    match_overlap numeric(4, 3),
    match_basis   text,
    logged_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, location_id)
);
CREATE INDEX IF NOT EXISTS box_location_status_log_location_ix ON curated.box_location_status_log (location_id, run_id);

-- ---------------------------------------------------------------------------
-- 4. curated.box_dsu_bench_stale: the regeneration work list
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS curated.box_dsu_bench_stale (
    set_id           bigint  NOT NULL,
    basin            text    NOT NULL CHECK (basin IN ('delaware', 'midland')),
    pad_id           bigint  NOT NULL,
    formation_blueox text    NOT NULL,
    new_producers    integer NOT NULL CHECK (new_producers > 0),
    new_api10        text[]  NOT NULL,
    sticks           integer NOT NULL,                   -- sticks of the record set in this DSU x bench
    sticks_out       integer NOT NULL,                   -- of those, taken out tonight by the new producers (status or crowded)
    est_sticks       integer NOT NULL CHECK (est_sticks >= 0),
    stale_since      date    NOT NULL,
    run_id           bigint  NOT NULL REFERENCES meta.box_recon_run (run_id),
    PRIMARY KEY (set_id, pad_id, formation_blueox),
    CONSTRAINT box_dsu_bench_stale_wells_ck CHECK (cardinality(new_api10) = new_producers),
    CONSTRAINT box_dsu_bench_stale_est_ck CHECK (est_sticks = LEAST(sticks - sticks_out, GREATEST(sticks - new_producers, 0)))
);

GRANT SELECT ON meta.box_recon_run, curated.box_location_status, curated.box_location_status_log, curated.box_dsu_bench_stale TO analyst_ro;

-- ---------------------------------------------------------------------------
-- 5. Comments
-- ---------------------------------------------------------------------------
COMMENT ON TABLE meta.box_recon_run IS
    'Nightly BOX sticks reconciliation run log (etl/box_recon.py, sql/74): one row per run. status written = the status and stale tables were replaced; '
    'breaker = more than max(200, 1 %) of locations changed with the same record sets and rule version, so nothing was written; failed = the step '
    'errored and the previous tables stand. counts = per basin: sticks, each status, crowded, inventory.';
COMMENT ON TABLE curated.box_location_status IS
    'Nightly status of every BOX stick of the RECORD box.location_set per basin (sql/74, etl/box_recon.py). Recomputed from scratch every night, '
    'never latched: a wrong match heals. Keyed on location_id = the app-facing stick_id. Only a PRODUCING well (first production date) takes a '
    'stick out of inventory; drilled-not-producing wells and permits only flag (decision 2026-11-18). A technical screen: no economics, no forecast. '
    'A stick is never moved, added or removed here; regeneration is periodic and explicit-go. NOTHING reads this table until gate 5 of '
    'docs/box_sticks_plan.md.';
COMMENT ON COLUMN curated.box_location_status.status IS
    'open: no match. permitted: an approved permit lies along >= 50 % of a leg (flag; still inventory). pending: a well that is drilled but not yet '
    'producing lies along >= 50 % of a leg (flag; still inventory; re-judged the night it produces). producing: a producing well lies along >= 50 % of '
    'a leg, inside its 150 ft corridor, same bench (same code within 500 ft TVD, or within 150 ft whatever the tag). conflict: a producing well '
    'alongside 30 to 50 % of a leg, or two producing wells on one leg; not inventory, listed for review.';
COMMENT ON COLUMN curated.box_location_status.counts_as_inventory IS
    'TRUE for open / permitted / pending sticks that are not crowded. The undrilled count once gate 5 lets this table drive it.';
COMMENT ON COLUMN curated.box_location_status.legs_matched IS
    'Legs a producing well matched. A U-turn stick is out of inventory with ONE leg matched (the generator does not place an odd leg).';
COMMENT ON COLUMN curated.box_location_status.match_basis IS
    'depth = the realizing well has depth evidence. planned = it has none (planned survey or round-100 TVD): matched at the DSU''s landing of its '
    'tagged bench, or on formation family where that bench has no row; re-judged when the survey lands.';
COMMENT ON COLUMN curated.box_location_status.crowded IS
    'An open / permitted / pending stick now inside the record set''s own no-place envelope (box.location_set.cfg -> generator) of a producing well: '
    'the generator would not place it. Not inventory. crowd_api10 = the well.';
COMMENT ON COLUMN curated.box_location_status.status_since IS 'First night of the current status, carried while the status holds.';
COMMENT ON TABLE curated.box_location_status_log IS
    'History of curated.box_location_status (sql/74): one row per location per night it changed (status, crowded flag, realizing well, or the record '
    'set under it). cause: first_run, well (a well changed it), set_change (a new record set: carried ids are re-judged, ids that stopped get '
    'new_status = stopped), rule_change (etl.box_recon.VERSION changed). Append-only.';
COMMENT ON TABLE curated.box_dsu_bench_stale IS
    'DSU x bench of the record sets holding a producing well of that bench that the set never read, with >= 30 % of its lateral inside the DSU '
    '(sql/74). The work list of the next regeneration. est_sticks is an ESTIMATE of what a regeneration would leave: the lower of (sticks - '
    'sticks_out) and (sticks - new_producers, not below 0), sticks_out = the sticks these new producers took out by status or crowding. Measured '
    'against a regeneration (docs/box_sticks/phase5b-2026-11-19, 156 DSU x bench per basin): total -7.3 % Delaware / +7.8 % Midland, exactly right on '
    '58 % / 64 % of rows, mean absolute error 0.5 sticks. DSU x bench outside this list barely move in a regeneration (under 5 % change count).';
COMMENT ON COLUMN curated.box_dsu_bench_stale.est_sticks IS
    'Estimated sticks after a regeneration, NOT a count of record: LEAST(sticks - sticks_out, GREATEST(sticks - new_producers, 0)).';
