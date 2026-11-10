# Warehouse step: the tag rule runs in the nightly (plan, revised 2026-11-09)

**Status: PLAN.** Nothing is written to Supabase.
- Each W-step ends at a gate.
- W3 and W5 write to the warehouse, and each needs Michael's explicit, specific go.
- The 2026-11-08 version of this plan (rule outputs pinned as override rows, then a monthly re-run) is superseded. It
  is kept in git history (`git log -p -- docs/formation_tag_redesign/WAREHOUSE_STEP.md`), and its decisions are carried
  below.

**Names.** The rule is one chain of three steps: **Step 1** vendor choice (files and code say "v5"), **Step 2**
sub-bench (v5.1), **Step 3** depth check (v5.2). Renaming the code is a separate, cosmetic follow-up.

## Why the rule has to run nightly

- **Both inputs change every night.**
  - The vendor strings change: Novi Insights is a daily feed, and 51 producers changed tag in three days (50 of them
    inside the BOX extents).
  - So do the depths: vendor TVD, surveys, and new witnesses.
- **A tag is a function of those inputs.** Computed once and pinned, it goes stale silently.
- **This is the job sql/23 does today, nightly.** "Retiring sql/23" means replacing its *method* (40 nearest producers'
  own tags) while keeping a nightly depth check. Step 3 is that check.

**Three kinds of thing feed a tag. Only the first is recomputed nightly.**

| Kind | Examples | Changes when | Lives in |
|---|---|---|---|
| **Evidence** | vendor strings, TVD, surveys, witness reference depths | every night | the vendor tables, `curated.wells`, `curated.well_lateral_survey` |
| **Policy** | Step 1's frozen winners (policy v1), thresholds, guards, the list of accepted change classes | only on review: a PR plus a card round | repo-seeded `ref.*` tables |
| **Human calls** | carded well calls, depth exclusions (SUSPECT TVD) | only on a card verdict | repo-seeded `ref.*` tables |

The nightly applies policy to evidence. It never learns policy: it re-learns Step 1's winners only to **report drift**.
It never makes a human call; anything new **queues for cards** and sits on its vendor tag meanwhile.

## What the tag becomes

`curated.formation_blueox` (sql/16, rewritten) resolves each well in this order:

1. **Human call** (`ref.formation_tag_overrides`). Always wins, whatever the vendors do. Since 2026-11-09 this table
   holds only human calls:
   - today's 437 rows;
   - every carded call from the Step 1/2/3 rounds, policy v1 included.

   No class-accepted rows go here (Q1, revision of 2026-11-08).
2. **Rule output** (`curated.formation_tag_rule`, written by the nightly). Used **only while the well's recorded inputs
   still equal its current inputs**: Novi string, Enverus string, TVD and depth source. Otherwise the well falls through
   to its vendor tag until the next run.
   - Only rows in an **accepted change class** (or a Step 2 sub-bench change that was carded) carry a code.
   - Everything else the rule decides is recorded with `applied = false`, for the report.
3. **Vendor tag:** the crosswalk mapping, as today (Novi string unless coarse, then Enverus).
4. **Unmapped:** NULL in Delaware and Midland, OTHER in CBP, as today.

**`curated.formation_blueox_tvd` (sql/23) becomes a pass-through.** It keeps its columns, so no consumer changes:
- `corrected_code` = the sql/16 code;
- `corrected` = FALSE. (Revised in W2: TRUE on Step 3 moves would make `wells_enriched` relabel them `tvd_corrected`
  and lose the `rule_step3` source. Step 3 provenance shows as `formation_blueox_source = 'rule_step3'` instead.)

Until cutover (switch off) sql/23 keeps its legacy flip, except that it never flips a human call. After cutover its
own 40-neighbour flip is gone. Every consumer already reads `corrected_code` through `wells_enriched`, so the
pass-through is invisible to anduin, erebor and narvi.

**`source` values.** sql/16 writes:
- `ratified_override` (a human call);
- `rule_step1`, `rule_step2` or `rule_step3` (a rule output);
- the existing vendor sources.

erebor's "colour by source" legend needs those added (a small erebor follow-up; today both of the new kinds fall to grey).
The full provenance columns are still a later step (Q3).

## The tables

| Table | Written by | Holds |
|---|---|---|
| `ref.formation_tag_overrides` (exists, sql/44) | seed PR + `apply_formation_tag_overrides` | human calls only |
| `ref.formation_tag_depth_exclusions` (new) | seed PR | Q5 SUSPECT TVD wells: api10, the depth and depth source judged, card, date |
| `ref.formation_tag_policy` (new) | seed PR | Step 1 frozen winners by (basin, Novi string, Enverus string), `policy_version` = 1 |
| `ref.formation_tag_class` (new) | seed PR | every reviewed change class: step, basin, from → to, basis, decision (accept / reject), cards k/n, card folder |
| `curated.formation_tag_rule` (new **table**, not a matview) | the nightly rule step, whole-table replace in one transaction | per well: code, step, basis, class, `applied`, recorded inputs, `policy_version`, rule git sha, `run_id` |
| `meta.formation_tag_run` (new) | the nightly rule step | one row per run: counts by step/basis/class, drift report, queue sizes, circuit-breaker result, runtime |

- **The split is by who writes:** `ref.*` is reviewed in the repo; `curated.formation_tag_rule` is computed by the ETL.
- **This refines Q5's storage.** Q5 put depth exclusions in "the rule table" as rows the writer never touches. Here they
  get their own seeded table, so the nightly can replace its table whole without special cases. Q5's substance is
  unchanged:
  - sql/16 ignores exclusions (the well keeps its vendor tag);
  - the rule turns the well's depth off as evidence;
  - an exclusion lapses when the well's live depth or depth source differs from the recorded one.

  Flagged for Michael below.

## The nightly

`etl-nightly.yml` → `scripts.run_daily`, after the vendor loads:

1. Refresh `curated.wells` (as today).
2. **Rule step (new):** `python -m scripts.tag_rule_nightly`. The order matters:
   1. Read the inputs: `curated.wells`, `curated.well_lateral_survey`, the crosswalk, and the four `ref.formation_tag_*`
      tables.
   2. Run Step 1 → 2 → 3 under the frozen policy and the accepted-class list.
   3. Write `curated.formation_tag_rule` and `meta.formation_tag_run`.
   - **It must not read** `formation_blueox` / `wells_enriched` for its inputs. Today's pull reads `wells_enriched`,
     which is the rule's own output one night later, a feedback loop. The input query is rewritten to vendor-only
     columns (W2). Reading yesterday's `formation_blueox` for the **report** (what would change) is fine.
   - **Survey lag:** `well_lateral_survey` refreshes last in the nightly (and is gated), so the rule sees the previous
     night's surveys. Accept the one-day lag, or move that refresh ahead of the rule step (it has no curated
     dependencies). Recommended: move it.
3. Refresh `formation_blueox` → `producing_reference` → `formation_blueox_tvd` → … (the existing order).

**Runtime:** about 15 min on the laptop (Step 1 seconds, Step 2 ~6 min, Step 3 ~9 min). The 05:00 CT dispatch currently
finishes by ~06:30, so this adds roughly 15–25 min on a runner. W2 measures it on Actions before anything goes live.

**Safety rails. A bad night must not move tags:**
- **One transaction:** TRUNCATE + COPY + the run row commit together, or nothing changes. That's the lesson of the
  11-09 crosswalk loader, which emptied a table for a minute.
- **Failure is soft.** If the rule step errors, the nightly logs it, keeps yesterday's table, and continues. The
  staleness guard drops any rows whose inputs changed overnight to their vendor tag. The run summary email says so.
- **Circuit breaker:** if more than **N** wells (proposed: 200, or 1 % of judged producers) would change their applied
  code versus the previous run, the step writes nothing and alerts. Excluded from the count:
  - new wells;
  - wells whose own inputs changed.

  A crosswalk change, a policy PR or a vendor bulk re-tag should trip it on purpose, so Michael sees the effect first.
- **The switch:** `ref.formation_tag_switch` (one row: `use_rule boolean`). sql/16 reads rule rows only when it is on.
  This makes cutover and rollback a content change plus a `REFRESH … CONCURRENTLY`, not a drop.

**What the run reports** (in `meta.formation_tag_run` and the summary email):
- **Applied changes** versus yesterday, by class: new wells, and wells whose inputs moved.
- **Card queue:**
  - change classes of 20 or more wells that are not in `ref.formation_tag_class`;
  - Step 2 sub-bench changes that were never carded.

  These stay on the vendor tag until carded.
- **Policy drift:** the learned Step 1 table versus the frozen policy (gained, lost or flipped winners). It is report
  only; a flip means a policy review, never an automatic change.
- **Human calls to re-check:** carded calls whose vendor strings or depth changed since the card. The call still
  stands; it is flagged for a look.
- **Lapsed depth exclusions:** the depth changed, so the well is judged again.

## What lands at cutover

Counts come from W1's live run. From the reviewed snapshots:

- **Step 1 accepted classes (13):**
  - Midland: WCA_1 → WCB_1 (pattern 296, depth 183), LSSH → JM (depth 115, pattern 82), WCB_1 → WCA_1 (depth 55);
  - Delaware: BS3_C → BS2_S (depth 79, pattern 100), BS3_S → WCA_1 (pattern 30, depth 23), OTHER → AVA_0 (29),
    WCA_2 → WCB_1 (depth 29), BS2_C → BS1_S (depth 22), BS3_S → WCXY (depth 75).

  These counts are the class sizes when each class was reviewed. Policy v1 moved several of them; for example,
  BS3_S → WCA_1 (pattern) is now 25 and LSSH → JM (pattern) 77.
- **Step 1 rejected classes:** Delaware WCB_1 → WCA_1 (depth) and Delaware BS2_C → BS1_S (pattern). They stay on the
  vendor tag.
- **Step 2:** the 25 carded sub-bench changes.
- **Step 3:** class A accepted. The final set is 141 wells: SALADO DRAW → WCXY superseding card 50, SQUINTS on WCA_1,
  and HARACZ AMO added.
- **Human calls:** every carded call, including the policy-v1 calls (cards 4, 5, 6, 10, 14, 20, 27, 29, 32, 33,
  36–38, 41).
- **Depth exclusions:** the 12 from v5.2 cards.
- **Stale override rows:** the 4 stale rows leave in the same load (Gate 0 Q4): 4232943352, 4232945905, 4232946987 and
  4246139770.

**Class identity across the baseline change.** The reviewed classes are written "live → final", and "live" was
today's warehouse tag: the vendor tag plus overrides plus sql/23 flips. Under the new resolution the rule's starting
point is the **vendor tag**. W1 must show that each reviewed class maps onto (step, basin, vendor tag → final, basis)
with the same wells. Any well that moves class because sql/23 had flipped it gets listed, not silently re-labelled.

## Steps

### W1: Rebuild from live, as it would run nightly (read-only)

1. Rewrite the input pull to vendor-only columns (no `wells_enriched`).
2. Run Steps 1–3 on live data under policy v1, the class list and the exclusions.
3. Report:
   - **reproduction:** the reviewed decisions, re-derived on live;
   - **drift since review:** wells whose vendor tag moved, e.g. a Novi revision now agreeing with the call;
   - **new wells in accepted classes;**
   - **the card queue** (unreviewed classes of 20 or more, uncarded Step 2 changes);
   - **the class-identity check** above;
   - **runtime.**

**Gate W1:** Michael reviews the report and cards whatever the queue holds before cutover.

**W1 run 2026-11-09:** `w1-live-2026-11-09/REPORT.md`.
- The vendor-only pull reproduces sql/16 on all 60,832 wells.
- The rule on live reproduces the reviewed decisions on 99.94 % of 56,713 wells; every difference is the well's own
  inputs or its neighbours moving.
- The cutover would change 1,353 frame wells; 78 more outside the frame lose a sql/23 flip.
- The queue is 11 single cards: 4 Step 2, 5 Step 3, and the 2 class-identity wells.
- 10 human calls are flagged because their inputs moved.
- The chain takes 15 min.

### W2: Repo (one PR off `main`, after PR #233 merges; no stacking)

- **`sql/NN_formation_tag_rule.sql`:**
  - the four new `ref` tables, `curated.formation_tag_rule`, `meta.formation_tag_run` and the switch;
  - the sql/16 rewrite (precedence above, switch **off**);
  - sql/23 rewritten as a pass-through.
- **Seeds:**
  - `formation_tag_overrides.csv`: carded calls added; the 4 stale rows removed;
  - `formation_tag_depth_exclusions.csv`;
  - `formation_tag_policy.csv` (= `box/policy/step1_patterns_v1.csv`);
  - `formation_tag_class.csv`, from the `class_decisions.csv` files.
- **`scripts/tag_rule_nightly.py`:**
  - `--dry-run` prints the report and writes nothing;
  - `--write` does the single-transaction replace;
  - also the circuit breaker, and the run row.
- **The nightly:** the `run_daily` hook (soft-fail), the `etl-nightly.yml` timing check, and `well_lateral_survey`
  moved ahead of the rule step.
- **The appliers:** `apply_formation_tag_rule.py` (the structural window: CASCADE rebuild order, sql/26, sql/31) and
  `--cutover` / `--rollback` (switch + concurrent refresh down the chain).
- **Tests:**
  - the reproduction test pins the reviewed decisions on a fixture;
  - the staleness guard;
  - the class gating;
  - the circuit breaker;
  - the switch;
  - the SQL lint (UNIQUE index on every matview).
- **Docs and the dictionary:** sql/31 comments, the data dictionary regenerated, the `warehouse-change` /
  `novi-quarterly-reload` skills updated if the CASCADE graph changed, and CLAUDE.md's nightly description.

**Gate W2:** Michael reviews the PR and merges it. Merged still means nothing applied.

**W2 as built (2026-11-09, branch `claude/tag-rule-nightly`; its PR opens once PR #233 is merged):**
- **`sql/72_formation_tag_rule.sql`:** the six tables (switch inserted OFF), all additive. Table comments are in sql/31.
- **`sql/16`:** human call > rule row > crosswalk. A rule row applies only behind the switch and while the well's Novi
  formation, Enverus interval, tvd_ft and planned flag equal the recorded ones. Sources are `rule_step1` /
  `rule_step3`.
- **`sql/23`:** never flips a human call; a pass-through with the switch on.
- **`scripts/tag_rule_seeds.py`:** builds the four seeds from the card folders. `--check` is a CI test.
  - Overrides: +279 human calls, notes "tagrule carded …". 66 of them confirm the tag on the card, which pins the
    well against the nightly rule; 30 of those keep a sql/23 flip that you confirmed.
  - Depth exclusions: 12. Policy v1: 19 rows. Decided classes: 16 (Step 1: 13 accepted, 2 rejected; Step 3: class A).
  - The first load also removes the 4 stale rows and catches 5 note-only rows up with the repo (the 263bc6b §8.16
    doublecheck was merged but never reloaded live).
- **`box/tag_rule_run.py`:** Steps 1 → 2 → 3 from tables, with class gating on the vendor tag. Step 1's `sql23_kept`
  branch is dormant, because sql/23 output is never an input.
  - **Verified on the W1 live cache:** 56,896 judged wells. Against the W1 dev chain, every difference is an intended
    one: the 10 W1-queue calls, the 4 stale overrides, the 3 vendor-gated Bone Spring wells, and the 12 depth
    exclusions now out of the frame.
- **`etl/tag_rule.py`:**
  - pull → rule → breaker → TRUNCATE + COPY + run row in one transaction;
  - soft as the nightly hook;
  - a no-op until sql/72 exists;
  - `--dry-run [--from-seeds]` / `--write [--allow-breaker]`.
  - **Live dry run 2026-11-09:** 75 s; 1,032 applied (Step 1 1,004, Step 3 28); breaker limit 568; the queue holds
    1 Step 2 well (3002546483, BS3_S → BS3_C, lead 441 ft); drift is the 2 small pairs.
- **The nightly (`etl/db.py`, `etl/refresh.py`):**
  - `well_lateral_survey` moves right after `curated.wells` (D4);
  - `refresh_curated(hooks=…)` runs the rule step just before `formation_blueox`;
  - `--no-tag-rule` is for manual refreshes;
  - `requirements.txt` gains scipy / shapely / pyyaml (the nightly installs only that file).
- **`scripts/apply_formation_tag_rule.py`:**
  - `--structure` (W3), with the chain tail and the switch-off verification;
  - `--seeds`;
  - `--cutover` / `--rollback` (W5);
  - `--dry-run` with any mode. The structure dry run passed live.
- **SQL behaviour check (`scripts/tag_rule_sqlcheck.py`, a throwaway PostGIS container, never Supabase):**
  - sql/72 applies twice, so it is idempotent;
  - switch off = vendor tags plus overrides;
  - switch on = a matching rule row applies, while a stale TVD, a changed planned flag, a human call and a well without
    a row keep their tags;
  - sql/23 flips a depth outlier with the switch off but not a human call, and nothing with the switch on;
  - REFRESH CONCURRENTLY works on both.

  It caught an unescaped apostrophe in sql/16's new COMMENT, which would have failed W3.
- **Safety:**
  - `require_sql72` makes the three sql/16 rebuild scripts refuse before dropping anything while sql/72 is absent;
  - both crosswalk loaders are now one transaction (the 11-09 trap).
- **Not in W2:**
  - the data dictionary is regenerated at W3, because the generator reads the live catalog;
  - CLAUDE.md's nightly paragraph is updated after merge (that file is outside this repo).

### W3: Structural window (off-hours, explicit go)

The sql/16 rewrite is a `DROP … CASCADE`. Live `pg_depend` (2026-11-08) shows it drops 12 matviews and 3 views,
including the intel chain, `wells_enriched`, `reconciled_inventory`, `erebor_locations` and `box_scout_locations`.

1. Check that no nightly is running (`gh run list --workflow etl-nightly.yml`). The window is outside 05:00–06:30 CT.
2. `apply_formation_tag_rule --dry-run`: the live pg_depend check plus the seed diff.
3. On the go: rebuild the chain in the quarterly order, then sql/26, then sql/31. erebor and narvi are dark for a
   couple of hours (the longest step is `intel_pdp_support`). anduin is unaffected.
4. **Verify that the switch is off and the tags are unchanged:** `formation_blueox` and `wells_enriched` are
   row-for-row identical to the pre-window snapshot. The only expected exception is the overrides seed (carded calls
   in, 4 stale rows out), and that diff is listed. The EXPLAIN assertions on the geography indexes run too.

**Gate W3:** structure live, tags unchanged.

### W4: Shadow period (nightly writes, nobody reads)

- The nightly runs the rule step with the switch off. `curated.formation_tag_rule` fills; tags don't move.
- **Length:** at least 10 nightly runs. Exit criteria:
  - no circuit-breaker trips that weren't explained;
  - a runtime that fits the window;
  - day-over-day changes that are only new wells, input-moved wells and queued classes.
- Michael cards the queue as it grows.

**Gate W4:** Michael reviews the shadow reports.

### W5: Cutover (explicit go)

1. `apply_formation_tag_rule --cutover`: switch on, then `REFRESH … CONCURRENTLY` down the chain (~1 h, apps stay up,
   `erebor_locations` last).
2. **Verify live:**
   - applied-row count = the rule table's `applied` rows whose inputs match;
   - 0 human calls overridden;
   - the sql/23 pass-through is clean;
   - crossing area falls toward ~529 sq mi Delaware / ~82 Midland;
   - stick bench moves through sql/19, `reconciled_inventory` status moves and erebor `box_locations` class counts,
     each before and after.
3. **Rollback** is `--rollback`: switch off plus the same refresh.

**Gate W5:** live state confirmed.

### W6: Propagate

- **BOX:** records run 32 (Delaware) and run 30 (Midland) stay on their old benches until the next BOX run (Gate 0 Q5).
  This goes in the step-23 memory, and in #eng-updates only if Michael wants a post.
- **anduin:** header re-sync. Saved type curves keep their members; only new cohort builds see the new tags.
- **narvi:** list the saved scenarios whose benches moved, and re-save them.
- **erebor:** the source legend gets `ratified_override` and `rule_step1/2/3`.
- **Blue Ox:** no vocabulary or column change, so the ledger only gets a note that drops already shipped keep their old
  benches.

## Decisions

**Decided:**
- **Q2 (2026-11-08):** new wells in accepted classes take the class's answer. In the nightly this is automatic.
- **Q3 (2026-11-08):** provenance columns come later, as a separate additive step (the `wells_enriched`
  `CREATE OR REPLACE VIEW` precedent).
- **Q4 cadence: superseded.** The rule runs nightly (Michael, 2026-11-09).
- **Q5 (2026-11-09):** SUSPECT TVD wells are depth exclusions. Storage is refined above.
- **Q6 (2026-11-09):** Step 1 policy v1: string-keyed, frozen winners; the nightly reports drift and never re-learns.
- **Policy-v1 classes (2026-11-09):** decisions taken as they stand:
  - 12, 13 and 15 accepted;
  - 14 rejected.

  Noted, not acted on: class 12's rejects are all in Lea, class 14's all in Loving, and 3 of class 13's 10 cards were
  WCA_1 calls.
- **Crosswalk fix (2026-11-09, applied live):** Novi Insights `WOLFCAMP A (XY)` → WCXY (PR #234).

**Decided 2026-11-09 (Michael: "Confirm as recommended"):**
- **Q1, mechanism:** the sql/16 rewrite with the switch. Rule outputs are never pinned as override rows.
- **D1, standing write:** the nightly may write `curated.formation_tag_rule` and `meta.formation_tag_run` every night
  without a per-run go. The scope is exactly those two tables, behind the circuit breaker. Every policy or seed change
  stays a PR plus an explicit apply. W3 and W5 still need their own explicit go.
- **D2, Q5 storage:** depth exclusions go in their own seeded table, `ref.formation_tag_depth_exclusions`.
- **D3, circuit breaker and shadow:** 200 wells or 1 % of judged producers, whichever is larger; at least 10 shadow
  runs.
- **D4, survey refresh:** `well_lateral_survey` moves ahead of the rule step in the nightly.

**Still open in the rule itself (not blocking the warehouse step):**
- **Step 1's unit-blend reference:** it uses unit-level, not code-level, references, as Step 3 rev 1 does. This is
  where the 9 WCB_1 gains came from.
- **Same-unit sub-bench conflicts:** about 953 Novi WCXY vs Enverus WCA_1 / WCA_2 wells, now joined by class 13's three
  WCA_1 calls. No step adjudicates them; they keep Enverus's code.

**Smaller follow-ups:**
- making `_load_crosswalk` transactional;
- renaming v5/v5.1/v5.2 to Step 1/2/3 in the code.
