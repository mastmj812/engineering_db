# formation_blueox rule v5.2 — the gross-miss step (2026-11-08)

**Status:** FROZEN at the commit that adds this file. Nothing is applied.

- Code: `box/tag_grossmiss.py` (tests: `tests/test_tag_grossmiss.py`).
- Development run: `scripts/tag_grossmiss_dev.py` → `v5_2-dev-2026-11-08/`. It computes moves, classes, what happens
  to today's sql/23 wells, and crossing area. It draws no cards and produces no labelled-set score. No constant changes
  after it runs.

## Why

Michael (2026-11-08) wants one complete overhaul of tag assignment, not a vendor mapping (sql/16) followed by a rule,
followed by a depth patch (sql/23) on top.

sql/23 can't simply be dropped:
- On the Nov 5 snapshot it moves 157 evidence producers.
- v5 makes its own depth call on only 48 of them. On the other 109 it defers (`sql23_kept`), because those wells sit
  where v5 never looks: both vendors agree on the wrong unit, only one vendor has a tag, the string maps to OTHER or to
  nothing, or a guard holds the conflict.

v5's own docstring says sql/23 "retires only once this rule carries its own gross-miss check". v5.2 is that check.

**Why not keep sql/23's method?**
- Its reference bands are built from its neighbours' own tags, mis-tags included.
- It runs after the rule, with no exemption for human calls. Card 12 (CHILES #004H, a BS3_C call) was lifted to BS2_S.
- v5.2 judges against v5's **witness** depths instead (wells whose two vendors agree on the unit), with the same
  stratigraphic-order guard as v5.1.

## The rule

**Input tag:** the accepted tag *without* sql/23. Precedence: human call (override, a v5 carded call, a v5.1 card's final
code) > class-accepted v5 code > sql/16's code.

**Judged:** every evidence producer except human calls. Evidence means a survey depth or a clean `tvd_ft`, no planned
survey, at least 4,000 ft.

| Step | Test | Outcome | Basis |
|---|---|---|---|
| own reference | witness depth of the tag's unit at the well (`landing_surfaces.estimate`, witnesses within 2 mi, ≥ 3; **the well itself left out**) | none → kept, reported | `gm_no_control` |
| gross miss | \|depth − own reference\| > **600 ft** | not a miss → kept | `gm_ok` |
| OTHER / unmapped tag | no unit in the column, so always a candidate | — | — |
| placement | nearest referenced unit within **300 ft** (OTHER / unmapped: **150 ft**) and ≥ **100 ft** nearer than every other referenced unit | otherwise kept, flagged | `gm_unplaced` / `gm_other_kept` |
| order guard | referenced units from the tag's unit to the target in stratigraphic order (OTHER / unmapped: the target and its nearest referenced unit above and below) | inverted → kept, flagged | `gm_inverted` |
| guards | never into or out of WDFD / BRNT / MISS; never BS3 ↔ WCA in Lea / Ward (rule B pending) | kept, flagged | `gm_guard` |
| sub-bench | a single-code unit is its code. A multi-code unit uses v5.1's depth decision over its codes (sub-bench witnesses, 100 / 300 ft, order); otherwise the nearest referenced code (low confidence); with no referenced code the tag is kept | `gm_sub` `depth` / `nearest` | `gm_no_subbench` |
| move | all of the above pass | the target code | `gm_move` |

**Constants:** all are v5's, untuned: 2 mi, ≥ 3 witnesses, 100-ft margin, 300-ft far limit, 150-ft OTHER bar. The one
new constant is the **600-ft** gross-miss trigger. It is sql/23's own threshold for a trusted survey depth, and also
2 × v5's far limit. sql/23's 1,000-ft permit-depth variant isn't needed, because permit-round depths are not evidence
here.

**Leave-one-out** matters for one case: a well both vendors agree on is itself a witness of its unit. Judged against a
reference that includes itself, it could hide a miss. A cluster of wells that both vendors mis-name together still
builds its own reference. That limit is shared with v5, and is the reason the guard and the cards exist.

## Rev 1: code-level references (2026-11-08)

Found in the first dev run, before any card or label was seen. No constant changed. The first run is kept as
`v5_2-dev-2026-11-08-superseded/`.

**What was found.**
1. **A bug.** A move into the Delaware BS1 unit wrote the unit name "BS1", not the code BS1_S (18 wells).
2. **A design flaw.** The 59 BS3_S → WCXY / WCA_1 moves (the two largest classes; Loving 30, Eddy 26) were artifacts
   of a mixed reference. The BS3 unit reference blends lime and sand: of its 3,004 witnesses, 1,356 are lime-vs-sand
   split wells. A sand well at the base of the 3rd sand therefore read "700 ft off BS3". Where a BS3_S sand reference
   exists, those wells sit a median 185 ft from it, which is not a gross miss.
   - Many of them are v5 D-case conflicts (Novi "WOLFCAMP A (XY)" vs Enverus "3RD BONE SPRING SAND") that v5
     deliberately left unresolved.
   - In the first run they also pushed Delaware adjacent crossing area **up**: 521 → 545 sq mi.

**The fix.** Every reference is a code reference:
- a multi-code unit's codes use v5.1's sub-bench witnesses;
- a single-code unit's code uses v5's unit witnesses.

A unit's distance from a well is its nearest referenced code. If the well lies beyond the unit's outermost referenced
code, on a side whose end code has no reference, the unit's extent there is unknown, so the well is `gm_no_control`
and kept. For example, a well below the BS3 lime with no BS3 sand reference can't be called a miss. The order guard
runs over codes. Unlike v5.1's rev 1, this one can also **add** moves: a well that sits between two sub-bench
references is nearer the unit blend than to either code. The rev-1 run compares the two move sets.

**Rev 1b (labelling only).** The unknown-extent test applies only when the well is more than 600 ft beyond the unit's
outermost referenced code. Within 600 ft of a referenced code, the well is not a miss on either side. The first rev-1
run labelled a well 50 ft above WCA_1 as "no control" whenever WCXY lacked a reference. The move set is identical
(125 = 125); only kept wells move from `gm_no_control` to `gm_ok`.

**Rev 1 result** (`v5_2r1-dev-2026-11-08/FINDINGS.md`):
- 125 moves (Delaware 96, Midland 29), every one a unit change, 112 inside the BOX extents.
- One class of 20 or more wells: Delaware OTHER → AVA_0, 38 wells. The other 87 moves each get a card.
- Of today's 234 sql/23 wells: 36 stay moved; 24 revert because v5.2 says sql/23 was wrong; 77 revert because they are
  outside the evidence frame; 97 revert with nothing confirming either way.
- Delaware non-adjacent crossing area: 166 → 146 sq mi.

## sql/23 retirement (part of this proposal)

- **Inside the evidence frame:** every well sql/23 corrects today is re-decided by v5 (its own depth call or an accepted
  class) or v5.2. A well that neither moves reverts to its sql/16 code. The dev run lists each one
  (`sql23_wells.csv`).
- **Outside the frame** (planned survey, permit-round depth, under 4,000 ft): no rule judges these wells. Under the
  standing rule, a planned survey is never depth evidence. So when sql/23 retires they take their vendor tag. The dev run
  counts them by reason (`sql23_outside_frame.csv`).

## Acceptance (FROZEN before the dev run)

- **Change classes** are (basin, input tag → v5.2 code).
- **A class of ≥ 20 wells** follows v5's class acceptance: 10 cards, accepted at 7/10, or 5/5 on a 5-card class.
- **A smaller class** gets a full review: one card per move, and each card decides only its own well.
- **Cards follow the strike-section format** (own tag, proposed tag, adjacent bands). Each card names the v5 code too
  when it differs, and asks for a **bench code** whenever the answer is neither the proposal nor the input tag (the
  card-24/25 lesson).
- **Guard checks**, reported and gating: zero moves into or out of WDFD / BRNT / MISS, and zero human calls changed.
- **Applying** belongs to the warehouse step (the sql/16 rewrite, with sql/23 retired in the same window), on Michael's
  explicit go.
