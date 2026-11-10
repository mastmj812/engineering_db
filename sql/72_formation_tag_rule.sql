-- =============================================================================
-- sql/72 — the formation-tag rule's tables (docs/formation_tag_redesign/WAREHOUSE_STEP.md, W2)
--
-- The tag rule (Step 1 vendor choice -> Step 2 sub-bench -> Step 3 depth check; RULE_V5*.md) runs INSIDE the
-- nightly, between curated.wells and curated.formation_blueox (etl/tag_rule.py). It applies POLICY to EVIDENCE:
--   evidence  vendor strings, depths, surveys       -> recomputed every night
--   policy    frozen Step 1 winners, decided classes -> repo seeds, changed only by a PR + card round
--   human     card calls, depth exclusions          -> repo seeds, changed only by a card verdict
-- The nightly never learns policy and never makes a human call: it re-learns Step 1's winners only to REPORT drift,
-- and anything new queues for cards while the well keeps its vendor tag.
--
-- Tables (all additive; nothing here drops or rewrites an existing object):
--   ref.formation_tag_policy             Step 1 frozen winners by (basin, Novi string, Enverus string), versioned
--   ref.formation_tag_class              every decided change class: step, basin, from -> to (vendor tag based), basis
--   ref.formation_tag_depth_exclusions   SUSPECT TVD wells (Q5): never judged / never a witness while the recorded
--                                        depth + depth source stand; lapse when either changes
--   ref.formation_tag_switch             one row; sql/16 reads rule rows only while use_rule is TRUE (cutover W5 /
--                                        rollback = flip + REFRESH CONCURRENTLY down the chain, no drop)
--   curated.formation_tag_rule           the nightly's per-well output (a TABLE, replaced whole in one transaction);
--                                        sql/16 applies applied_code only while the recorded inputs equal the well's
--   meta.formation_tag_run               one row per nightly run: counts, breaker, queue, drift, policy digest
-- Human calls stay in ref.formation_tag_overrides (sql/44), now human-only for new rows.
--
-- Seeds are loaded by `python -m scripts.apply_formation_tag_rule --seeds` (TRUNCATE + COPY per table, one
-- transaction each), never by this file. Standing authorization (Michael 2026-11-09, D1): the nightly writes
-- curated.formation_tag_rule and meta.formation_tag_run every night, behind the circuit breaker (D3: max(200, 1 %)
-- applied-code changes on wells whose own inputs did not move). Nothing else here is written without an explicit go.
--
-- DEPENDS ON: schemas ref, curated, meta. READ BY: curated.formation_blueox (sql/16: rule + switch),
-- curated.formation_blueox_tvd (sql/23: switch). Idempotent (IF NOT EXISTS; the switch row is inserted once, OFF).
-- RUN: python -m scripts.apply_formation_tag_rule --structure (W3, off-hours, explicit go) — it runs this file first.
-- =============================================================================

CREATE TABLE IF NOT EXISTS ref.formation_tag_policy (
    policy_version int     NOT NULL,
    basin          text    NOT NULL,
    novi_raw       text    NOT NULL,
    env_raw        text    NOT NULL,
    u_novi         text    NOT NULL,
    u_env          text    NOT NULL,
    decided        int     NOT NULL,
    novi_share     numeric NOT NULL,
    winner         text    NOT NULL CHECK (winner IN ('Novi', 'Enverus')),
    PRIMARY KEY (policy_version, basin, novi_raw, env_raw)
);

CREATE TABLE IF NOT EXISTS ref.formation_tag_class (
    step        int  NOT NULL CHECK (step IN (1, 3)),
    basin       text NOT NULL,
    from_code   text NOT NULL,          -- the VENDOR tag ('(unmapped)' for NULL)
    to_code     text NOT NULL,
    basis       text NOT NULL,          -- Step 1 basis (depth / pattern / depth_vs_other ...) or 'gm_move' (Step 3)
    decision    text NOT NULL CHECK (decision IN ('accept', 'reject')),
    agree       int  NOT NULL,
    judged      int  NOT NULL,
    class_wells int,
    card_set    text NOT NULL,
    PRIMARY KEY (step, basin, from_code, to_code, basis)
);

CREATE TABLE IF NOT EXISTS ref.formation_tag_depth_exclusions (
    api10        text    PRIMARY KEY,
    depth_ft     numeric NOT NULL,      -- the depth Michael judged untrustworthy
    depth_source text    NOT NULL,      -- survey / tvd_ft
    tag_kept     text,
    card         text    NOT NULL,
    note         text
);

CREATE TABLE IF NOT EXISTS ref.formation_tag_switch (
    id         boolean     PRIMARY KEY DEFAULT TRUE CHECK (id),
    use_rule   boolean     NOT NULL DEFAULT FALSE,
    changed_at timestamptz NOT NULL DEFAULT now(),
    note       text
);
INSERT INTO ref.formation_tag_switch (id, use_rule, note)
VALUES (TRUE, FALSE, 'created OFF by sql/72 (shadow); cutover = apply_formation_tag_rule --cutover')
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS curated.formation_tag_rule (
    api10          text        PRIMARY KEY,
    basin          text        NOT NULL,
    applied        boolean     NOT NULL,     -- in an accepted class (Step 1 or Step 3)
    applied_code   text,                     -- the code sql/16 uses while the inputs match (NULL when not applied)
    applied_step   int         NOT NULL,     -- 3 / 1 / 0
    applied_class  text,
    vendor_code    text,                     -- sql/16 without overrides (the class "from")
    step1_code     text,
    step1_basis    text,
    step2_code     text,
    step2_basis    text,
    step3_code     text,
    step3_basis    text,
    human_call     text,                     -- the override code when the well has one (never applied from here)
    step1_queue    boolean     NOT NULL,     -- Step 1 change in a class never decided
    step2_queue    boolean     NOT NULL,     -- uncarded Step 2 sub-bench change
    step3_queue    boolean     NOT NULL,     -- Step 3 move outside an accepted class
    novi_raw       text,                     -- recorded inputs: the staleness guard compares these four
    env_raw        text,
    tvd_ft         numeric,
    planned        boolean     NOT NULL,
    depth_ft       numeric,
    depth_source   text,
    in_box_extents boolean     NOT NULL,
    run_id         bigint      NOT NULL,
    CHECK (NOT applied OR applied_code IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_formation_tag_rule_applied ON curated.formation_tag_rule (api10) WHERE applied;

CREATE TABLE IF NOT EXISTS meta.formation_tag_run (
    run_id          bigserial   PRIMARY KEY,
    started_at      timestamptz NOT NULL,
    finished_at     timestamptz NOT NULL DEFAULT now(),
    status          text        NOT NULL CHECK (status IN ('written', 'tripped', 'dry_run', 'failed')),
    wrote           boolean     NOT NULL,
    judged          int,
    applied         int,
    changed_vs_prev int,
    breaker_limit   int,
    policy_version  int,
    policy_digest   text,
    rule_sha        text,
    summary         jsonb
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst_ro') THEN
        GRANT SELECT ON ref.formation_tag_policy, ref.formation_tag_class, ref.formation_tag_depth_exclusions,
                        ref.formation_tag_switch, curated.formation_tag_rule, meta.formation_tag_run TO analyst_ro;
    END IF;
END $$;

-- Table comments live in sql/31_comments.sql (re-applied after every chain rebuild).
