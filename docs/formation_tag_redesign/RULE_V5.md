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
