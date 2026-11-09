# Warehouse step: landing rule v5 + v5.1 (plan, 2026-11-08)

**Status: PLAN.** Nothing is written to Supabase. Each W-step below ends at a gate. The write in W3 needs Michael's
explicit, specific go.

## What lands

From the Nov 5 snapshot, before the live rebuild in W1:

| | Delaware | Midland | Total |
|---|---|---|---|
| v5 unit changes, carded calls | 39 | 34 | 73 |
| v5 unit changes, class-accepted | 149 | 691 | 840 |
| v5.1 sub-bench changes (all carded) | 25 | 0 | 25 |
| overlap: cards 22–25 are class-8 wells already counted above | −4 | | −4 |
| card 25 (MAKO) returns to its live tag, so no row is needed | −1 | | −1 |
| **override rows to add** | **208** | **725** | **≈ 933** |

- 887 of the 913 v5 changes (DE 187, MID 700) sit inside the BOX record extents; 26 sit outside.
- None of these wells is already an override.
- The 4 stale live override rows go in the same load (Gate 0 Q4). These are 4232943352, 4232945905, 4232946987 and
  4246139770, all WCB_2, removed from the seed by the §8.16 doublecheck calls.

## Revision 2026-11-08: Q1 reversed, toward a sql/16 rewrite

Michael has the off-hours window, and he corrected a premise. The cadence below was tied to the "quarterly Novi
reload", but that reload is **Novi Intelligence** (`raw_intel`). The formation strings come from **Novi Insights**,
which updates **daily**: 51 producers changed tag in three days, 50 of them inside the BOX extents.

With daily revisions, the override-row mechanism below has a correctness cost, not only a cost in convenience. It
pins about 840 **rule outputs** as if they were **human calls**.
- A human call should stand whatever the vendors do.
- A rule output is a function of today's vendor strings plus neighbouring depths. It should not outlive those inputs.

**Recommended design (Q1 = rewrite):**
- **`ref.formation_tag_overrides` keeps only human calls:** today's 437 rows, plus the 73 v5 carded calls and the 25
  v5.1 cards. Card 25 now needs a row, because otherwise the class-8 rule row would move MAKO to WCA_1. The seed stays
  repo-reviewed.
- **New `ref.formation_tag_rule`:** one row per class-accepted well. It holds the code, the rule version, the class,
  and the inputs it was decided on: Novi `formation`, Enverus `env_interval` and basin. It is written whole by a script
  (data, not a seed PR). Each write is an explicit go.
- **sql/16 precedence:** override, then a rule row **only while its recorded inputs still equal the well's current
  inputs**, then the crosswalk.
  - A well whose vendor string has been revised since the run falls back to today's mapping until the next run. It is
    never left on a stale pin.
  - Source is `rule_v5`, distinct from `ratified_override`. This is the existing column, so the Q3 provenance columns
    stay a later step.
- **sql/23 exemption in the same window:** `corrected` is FALSE for override and rule rows. `formation_blueox_tvd` is
  in sql/16's CASCADE anyway, so the change costs no extra window. Card 12 (CHILES #004H, a BS3_C call that sql/23
  lifted to BS2_S) is the case it fixes. Every consumer reads `corrected_code` from sql/23, so this is one edit.
- **Cost:** a chain-rebuild window. `apply_formation_tag_overrides --rebuild`, then the quarterly tail, then sql/26.
  erebor and narvi are dark for a couple of hours (longest step `intel_pdp_support`). anduin is not affected; it reads
  its own synced copy.
  - Schema changes: one new ref table, so sql/31 comments are needed and the data dictionary is regenerated.
  - erebor's "colour by source" legend knows neither `ratified_override` nor `rule_v5` today, and both fall to grey.
    That is a small erebor follow-up.

Under the rewrite, W1, W4 and W5 stand as written. W2 becomes:
- the sql/NN table;
- the sql/16 and sql/23 edits;
- the writer script (`--dry-run` diff, `--write`);
- the 98 carded seed rows;
- tests.

W3 becomes the chain window. The original override-row plan follows for the record.

## The mechanism as first planned: override rows, not a sql/16 rewrite

Earlier I described this step as "a new matview replacing sql/16's decision logic". **I recommended against that**
(superseded above).

- **The rule can't live in SQL.** v5 and v5.1 run in Python: witness depths, `landing_surfaces.estimate`, class
  precedence, card verdicts. A matview cannot recompute them. It could only join a table of the results.
- **A sql/16 rewrite is expensive.** Rewriting sql/16 is a `DROP … CASCADE`. Live `pg_depend` (2026-11-08) shows it
  drops 12 matviews and 3 views: the whole intel chain, `wells_enriched`, `reconciled_inventory`, `erebor_locations`
  and `box_scout_locations`. erebor and narvi go dark until the quarterly tail rebuilds them.
- **A mechanism already exists for exactly this.** `ref.formation_tag_overrides` (sql/44) was amended 2026-10-28,
  convention (a), to take both kinds of ratification: well-by-well **carded** calls and **class-accepted** wells
  ("class-accepted <class> k/n cards <date>"). That is how the BOX step-20a Midland screen landed (231 class-accepted,
  93 carded). sql/16 joins that table, so a seed change is a CONTENT change. It is loaded with
  `scripts/apply_formation_tag_overrides --refresh`: TRUNCATE + COPY in one transaction, then
  `REFRESH … CONCURRENTLY` down the chain in pg_depend order, with `erebor_locations` last. That run:
  - drops nothing;
  - keeps every object readable throughout;
  - takes about 55–60 min, mostly `intel_pdp_support`.

**Consequence: the tags are pinned until the rule is re-run.**
- The rule doesn't recompute nightly. New wells get today's vendor mapping plus sql/23 until the next rule run.
- An override always wins (Gate 0 Q4), so a pinned well doesn't move when vendors revise it.
- Every row's `note` carries its provenance (carded vs class-accepted, and which round).

## Steps

### W1 — Rebuild from live (read-only)

The snapshot is three days old, and 51 producers have changed tag since.
1. Re-pull the scoreboard frame.
2. Re-run v5, the accepted tags and v5.1 on live data.
3. Diff against what was reviewed.

The diff reports:
- **still applies:** the live tag still equals the reviewed `was`;
- **dropped by drift:** the live tag moved since the review (for example, a Novi revision now agrees with the call).
  These rows are not seeded;
- **new class-accepted wells:** new producers, or drifted ones, that fall in an accepted class (Q2 below);
- **new v5.1 changes outside the 25 reviewed:** each gets a card, or keeps its vendor default.

**Gate W1:** Michael reviews the diff and cards any new v5.1 changes.

### W2 — Seed rows (repo only)

- `scripts/tag_v5_seed.py`, in the `scripts/box_tag_seed.py` pattern, writes its own block into
  `seeds/formation_tag_overrides.csv`. Every note ends "rule v5". `--write` replaces only that block.
- Notes follow convention (a):
  - "carded <date> v5 r1 / r2 / v5.1 card N …";
  - "class-accepted <class> k/n cards <date> rule v5".
- Michael's direct well calls win over a class. Cards 24 and 25 are recorded as he clarified them.
- `--check-live` asserts, read-only, that each row's `was` is the live tag and that no row is already an override.
- Tests pin:
  - every row is unique by api10;
  - no row would set the tag the well already has (so card 25 is not seeded);
  - every carded call is present;
  - every class-accepted row's class was accepted.
- The sql/44 header gets a **Batch 4** paragraph.
- Commit, then a PR off `main` **after PR #233 merges** (the seed imports `box/tag_*`; no stacking).

**Gate W2:** Michael reviews the PR and merges it. Merged still means nothing applied.

### W3 — Apply, off-hours, on explicit go

1. Check that no nightly is running (`gh run list --workflow etl-nightly.yml`). The window is outside 05:00–06:30 CT.
2. `python -m scripts.apply_formation_tag_overrides --refresh --dry-run`. This checks `CHAIN` against live pg_depend
   and prints the seed diff (≈ +933 / −4). It writes nothing.
3. On the go: `python -m scripts.apply_formation_tag_overrides --refresh` (about 1 h, apps stay up).

### W4 — Verify live (read-only)

- **The applier's own checks:** every row landed, every PDP tag change is an override row, and stick-tag and recon
  status moves are reported.
- **sql/23 vs overrides.** sql/23 has no exemption for overrides. It has flipped none of the 437 today, but about 933
  new rows shift its bands. Assert 0 overrides flipped, and compare the `tvd_corrected` count before and after.
- **Re-score live.** Crossing area should fall to about 529 sq mi Delaware and about 82 Midland. Label reproduction
  should match the v5-accepted numbers.
- **Sticks.** PUD/RES stick benches move through sql/19, which copies neighbour producer tags. Count:
  - stick moves by basin and bench;
  - `reconciled_inventory` status moves;
  - erebor `box_locations` class counts before and after. A stick whose bench moves away from its BOX record bench
    changes coverage class.

**Gate W4:** live state confirmed.

### W5 — Propagate

- **BOX:** records run 32 (Delaware) and run 30 (Midland) stay on their old benches until the next BOX run (Gate 0
  Q5). State that in the step-23 memory and in #eng-updates only if Michael wants a post.
- **anduin:** header re-sync. Saved type curves keep their members; only new cohort builds see new tags.
- **narvi:** list the saved scenarios whose benches moved, and re-save them.
- **Blue Ox:** no vocabulary or column change, so the ledger only gets a note that drops already shipped keep their
  old benches.
- **Data dictionary:** no schema change, so no regeneration is needed.

## Later, separate go: not in this landing

- **Provenance columns** (`unit_basis`, `subbench_basis`: vendor / depth / vendor default / inverted / human /
  sql23), including the flag on the 447 placeholder rows kept at their default.
  - Additive DDL: a new `ref.formation_tag_basis` table, plus `CREATE OR REPLACE VIEW curated.wells_enriched` with the
    columns appended (the sql/40 / sql/49 precedent). No drops.
- **sql/23 override exemption.** (If Q1 = rewrite, this moves INTO the landing window; see the revision.) This is a
  sql/23 logic change, which is a DROP CASCADE of `formation_blueox_tvd`, so it
  needs a chain-rebuild window. Bundle it with the next quarterly reload. PLAN.md step 3 already retires sql/23's
  role.
- **Re-run cadence.** Each re-run produces new class-accepted rows for new wells, and new v5.1 changes that need cards.

## Decisions

- **Q2: DECIDED (Michael, 2026-11-08).** New wells in accepted classes are seeded as class-accepted.
- **Q3: DECIDED (Michael, 2026-11-08).** Provenance columns come in a later, separate step.
- **Q1 Mechanism: open.** Recommended: the sql/16 rewrite (revision above). The rule rows' staleness guard and the
  sql/23 exemption are worth the window. The alternative is override rows: no drops, but ~840 rule outputs pinned as if
  they were human calls.
- **Q4 Re-run cadence: open.** The earlier "quarterly" option was wrong: Insights updates daily. Recommended:
  - a **monthly** run, plus a **mandatory run before every BOX run**;
  - each write on Michael's go for the first ~3 runs;
  - then the writer moves into the nightly, once its diffs show only new wells in accepted classes.

  With the staleness guard, the gap between runs is never a wrong pin. New or revised wells simply sit on the vendor
  tag, which is today's state. New v5.1 sub-bench changes always queue for cards, whatever the cadence.
