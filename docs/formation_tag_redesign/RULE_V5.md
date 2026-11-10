# formation_blueox rule v5 — "vendors propose, depth decides" (2026-11-06)

**Status:** FROZEN at the commit that adds this file. Nothing is applied.

- Code: `box/tag_precedence.py` (tests: `tests/test_tag_precedence.py`).
- Development run: `scripts/tag_precedence_dev.py` → `v5-dev-2026-11-06/`. It computed churn, classes and the
  learned table only; no labels, no cards.

## Why

The vendor-vs-depth test (`vendor-conflict-2026-11-06/`) found:
- where Novi and Enverus disagree on the unit and depth can decide, today's tag is right only 54 % (Delaware) / 44 %
  (Midland) of the time;
- sql/16's "coarse Novi defers to Enverus" is right only 38 % / 37 % of the time;
- neither vendor is right overall, but individual patterns are lopsided in both directions.

Michael (2026-11-06): we are downstream of past sins (sql/16). The decision: replace sql/16's **decision logic** and
keep its plumbing (crosswalk, basin resolution, override join, the `formation_blueox` contract).

## The rule, per producing horizontal

Both vendor strings map through the crosswalk. A unit groups lime / sand inside one interval.

| Case | When | Tag | Basis |
|---|---|---|---|
| A | one vendor string maps, the other is missing | that code | `single_vendor` |
| O | one maps, the other is OTHER (outside the column) | the named code only if the well is within **150 ft** of that unit's witness depth; else today's sql/16 choice, flagged | `depth_vs_other` / `other_vendor_kept` |
| B | both map to the same code | that code (high confidence) | `agree` |
| C | same unit, different sub-bench | today's sql/16 choice, low confidence (Gate 0 Q1 (a)) | `subbench_vendor` |
| D1 | different units, and depth decides at the well | the backed vendor's code | `depth` |
| D2 | different units, depth can't decide, the pattern is learned | the pattern winner's code | `pattern` |
| D3 | otherwise | today's sql/16 choice, flagged | `unresolved` |
| guard | either unit is WDFD / BRNT / MISS, or BS3 vs WCA in Lea / Ward (rule B pending) | today's sql/16 choice, flagged | `guard` |

**Terms:**
- **Witnesses:** clean wells (survey depth else clean `tvd_ft`, no planned survey, ≥ 4,000 ft) whose two vendors
  agree on the unit. A unit's depth at a well = `landing_surfaces.estimate` (rev 1) of its witnesses within 2 mi
  (≥ 3). A conflict well is never a witness, so a mis-named cluster can't build the reference it is judged against
  (Magnolia 15 / Calm Breeze 2).
- **Depth decides** when both units have witness depths at the well, and it is ≥ 100 ft closer to one and within
  300 ft of it.
- **Learned pattern:** depth backed one vendor in ≥ 75 % of ≥ 20 decided wells of that (basin, Novi unit, Enverus
  unit). For units two or more apart, ≥ 5 decided wells.
- **sql/23:** a well sql/23 corrected keeps that code unless a per-well depth call places it (`sql23_kept`). sql/23
  retires only once v5 has its own gross-miss check.
- **Overrides** win afterwards. Producers only; sticks keep their own path for now.

**Constants:** 2 mi, ≥ 3 witnesses, 100-ft margin, 300-ft far limit and 75 % share are the scoreboard's and the test's
values; 20 and 5 are minimum samples; 150 ft is the v4 move bar rounded up. None was tuned on a card or a label.

**Pre-freeze changes from the dev run** (no score, card or label seen):
1. OTHER is a disagreement, not "unmapped". The first draft moved 413 Delaware OTHER wells to AVA_0 with no depth
   check; now 29.
2. sql/23 corrections are kept unless depth decides. The first draft undid 121 of 157; now 19 are moved, all by depth.
3. The blanket "gross conflict → Novi" default is replaced by gross patterns learned at ≥ 5 decided wells. The first
   draft moved 98 Delaware WCD wells to WCB_1 with no evidence.
4. The protected-bench guard also covers the OTHER case. The guard check found 2 OTHER → BRNT moves.

## What it does (`v5-dev-2026-11-06/`)

**Churn:**
- Delaware: 488 of 28,303 producers change (1.7 %).
- Midland: 800 of 28,441 change (2.8 %).
- 23 patterns learned (`precedence_table.csv`). It is the evidence-based replacement for sql/16's coarse list.

**Largest change classes:**

| Class | Basis | Wells |
|---|---|---|
| Midland WCA_1 → WCB_1 | pattern | 296 |
| Midland WCA_1 → WCB_1 | depth | 183 |
| Delaware WCB_1 → WCA_1 | depth | 163 |
| Midland LSSH → JM | depth | 115 |
| Midland LSSH → JM | pattern | 82 |
| Delaware BS3_C → BS2_S | depth | 79 |
| Midland WCB_1 → WCA_1 | depth | 55 |
| Delaware BS3_S → WCA_1 | pattern | 30 |
| Delaware OTHER → AVA_0 | depth vs other | 29 |
| Delaware WCA_2 → WCB_1 | depth | 29 |
| Delaware BS2_C → BS1_S | depth | 22 |

These 11 classes have ≥ 20 wells each, 1,083 wells in all.

**Magnolia 15 / Calm Breeze 2:**
- #204H → WCB_1, #404H → WCB_1, #205H → WCA_1;
- Calm Breeze #201H / #202H / #401H → WCB_1, #303H → WCA_1.

All are depth calls. Calm Breeze #301H / #302H (≈ 13,350 ft, about 320 ft below the WCB witnesses) match neither
vendor's unit: they stay `unresolved`, flagged for review.

## Acceptance (FROZEN)

**Review by class with the gate of record (convention (a)).**

For each change class with ≥ 20 wells (the 11 above):
- 5 cards, drawn at random from wells that are not labelled, overridden or on any earlier card.
- 5 / 5 agree accepts the class; 0–1 / 5 rejects it; otherwise 5 more cards and 7 / 10.
- An accepted class's changes stand. A rejected class's wells keep today's tag.
- Classes under 20 wells (205 wells) keep today's tag until a later round.

Each card shows:
- both vendor names and the well's depth;
- both units' **witness** depths at the well, with a pre-check that they agree with the plain median of the same
  witnesses within 2 mi (≥ 3);
- the strike section of evidence wells.

**Guards, which must hold:** zero changes into or out of WDFD / BRNT / MISS, and zero BS3 ↔ WCA changes in Lea /
Ward.

**Reported, not gating:**
- step-A crossing area re-run with v5 tags (it should fall);
- reproduction of Michael's labelled calls (not blind);
- sql/23 corrections kept;
- the `unresolved` list, with the "neither vendor" wells (e.g. Calm Breeze #301H / #302H) at the top.

Applying any of it is a separate warehouse step (a new matview that replaces sql/16's logic), with Michael's explicit
go.

## Verdict counting (declared 2026-11-06, after the cards were built and before any verdict)

v5 decides the **unit**. Where the backed vendor is coarse Novi, its code is a crosswalk placeholder sub-bench, as on
card 11: DEEP ELEM 4 FEDERAL COM #733H, proposed WCA_1 while sitting nearer the WCA_2 / WCB_1 bands.

So for these cards:
- a **bench code in the same unit as the proposed one** counts as **agree on the unit**. The sub-bench is recorded
  separately and does not count against the class;
- a code in another unit, or "reject", counts against the class;
- free text is a hold.

Pre-check, observed when the cards were built:

| Class | Plain-median check disagrees |
|---|---|
| Midland WCA_1 → WCB_1 (pattern) | 4 of 5 (depth can't separate there; the learned prior carries it) |
| Midland WCB_1 → WCA_1 (depth) | 3 of 5 |
| Delaware WCA_2 → WCB_1 (depth) | 2 of 5 |
| Delaware OTHER → AVA_0 | no read on any card (the OTHER side has no witnesses) |

## Policy v1: string-keyed, frozen learned winners (Michael, 2026-11-09)

**What changed in D2 (the learned precedence).** Two changes were adopted together after the XY crosswalk re-run
(`xy-rerun-2026-11-09/`) and the string-keyed dev run (`string-key-dev-2026-11-09/`).

1. **Keyed on vendor STRING pairs:** (basin, Novi string, Enverus string), not (basin, Novi unit, Enverus unit).
   - Unit keying pooled strings that map to one unit but differ in reliability. Against Enverus 3RD BONE SPRING SAND,
     depth backs Novi `WOLFCAMP A` ~9 in 10 but Novi `WOLFCAMP A (XY)` ~2 in 3. Adding the XY row erased the pooled
     winner and reversed 20 reviewed decisions.
   - Thresholds are unchanged: ≥ 75 % share, ≥ 20 decided wells (≥ 5 when the units are two or more apart).
2. **Winners are FROZEN at review:**
   - A run applies `box/policy/step1_patterns_v1.csv` (19 winners). The table it learns from the day's data is only a
     drift report (`tag_precedence.drift`: gained / lost / flipped), for review and never applied.
   - **Reference depths are evidence** and update every run. **Winners, thresholds and guards are policy** and change
     only on review, as a new policy version.

**Code.** `V5.pattern_key = "string"` (the default). `assign(d, r, policy)` takes the frozen table, and
`load_policy()` reads it. `scripts.tag_precedence_dev` applies policy v1 by default; `--policy learn` re-learns it
(development only) and writes `policy_drift.csv` otherwise.

**Verified.** Step 1 with the frozen v1 table on the XY snapshot reproduces the string-keyed dev run exactly (0 wells
differ in code, basis or final). The drift report is empty.

**Effect against the reviewed set** (`string-key-dev-2026-11-09/FINDINGS.md`):
- no reviewed winner flips;
- 16 accepted tags differ (unit keying with the XY row: 29);
- four change classes of ≥ 20 wells need cards: BS3_C → BS2_S pattern (100), BS3_S → WCXY depth (75), BS2_C → BS1_S
  pattern (34), BS3_S → WCA_1 depth (23).

**Naming.** "v5 / v5.1 / v5.2" are the three steps of one rule, run in order, not releases. Going forward: **Step 1
vendor choice** (this file), **Step 2 sub-bench** (RULE_V5_1.md), **Step 3 depth check** (RULE_V5_2.md), under one rule
version.
