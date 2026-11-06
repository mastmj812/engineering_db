# formation_blueox rule v4, "the ladder" (revision 2, after v3 failed)

**Status:** rev 3 **K0 FAILED 2026-11-05: 18/29 (62 %)**; Delaware 10/15 passed per basin, Midland 8/14 failed (v4r3-blind-cards-2026-11-05/FINDINGS.md). v4 fails. Nothing is applied.

- Code: `box/tag_ladder.py`, constants in `LADDER`. Tests: `tests/test_tag_ladder.py`.
- Development run: `scripts/tag_ladder_dev.py`. Blind cards: `scripts/tag_ladder_cards.py`.

## 1. Why v4, and what changed from v3

v3 failed its one score (step2-score-2026-11-05/FINDINGS.md): K1 39 % / 30 %, K2 43 %, K3 holds. Two problems:
- it read sub-benches off neighbours' **vendor** codes, which share the vendor's local errors;
- its family step was too cautious for 170–250 ft family errors.

v4 measures every well against a **reliable reference**, which is what the Lea/Eddy rule V did (you upheld 15 of 15
of its family calls):

- **Witnesses.** Evidence wells (survey depth or clean `tvd_ft`, not planned) whose vendors agree on the family:
  every mapped vendor string (Novi and Enverus) maps to the same family.
- **Anchor (rev 2).** The median depth of witnesses of an anchor family within 1.5 mi, with 3 or more of them.
  - Delaware anchors: BS1_S, BS2_S, WCA. Midland anchors: JM, LSSH, WCA_1.
  - Each well uses the **nearest** anchor, and only within **1,000 ft**; beyond that it keeps its vendor code.
  - offset = depth − anchor.
- **Ladder.** One rung per bench.
  - A rung = the median offset of evidence wells carrying that vendor code, per county, falling back to state and
    then basin; each needs 15 or more wells. Anchors use witnesses only, but rungs use every evidence well: a
    county-wide median dilutes the local error clusters that sank v3.
  - Pre-freeze fix from the dev run: witnesses-only rungs left the Delaware with no BS2_C / BS3_C / WCC rung, because
    the vendors name those differently. A bench with no rung was then absorbed into its neighbour (673 WCC→WCB_2,
    206 BS3_C→BS2_S artifacts). A well whose vendor bench has no rung on its ladder is now not judged (`no_rung`).
  - Benches whose rungs sit less than 75 ft apart, or out of order, form one unresolvable cluster.
- **Placement.** A well lands in the cluster its offset falls in.
  - **Keep** the vendor code if it is in that cluster. Confidence is high only in a one-bench cluster, with a margin
    of at least max(30 ft, a quarter of the gap).
  - **Move** to the cluster's nearest bench only when the margin clears that bar, the target is a one-bench cluster
    (rev 2), **and** the target family has 3 or more evidence wells within 1.5 mi. That second condition comes from your reason for holding three #230 cards:
    "lacking deep neighbors".
- **Grid** (Delaware, controlled; same control test as v3 revision 1).
  - Where his interval excludes the vendor family by 50 ft or more, the well moves to the nearest rung of a family
    the interval allows.
  - A ladder move into a family the interval excludes is blocked (`grid_conflict`).
- **Guards.** As in v3: protected benches, sand↔carbonate, and the XY top in Lea / Ward. New in v4: off-column
  vendor codes (OTHER, unmapped) are never re-placed. The step-20a OTHER class was a TVD-defect bucket.
- **Sticks.** Same placement against producer witnesses and rungs. A cross-family result is a flag
  (`family_conflict`), never a move.
- **Overrides** win afterwards. The rule never reads them.

**Disclosed, because the labels have been seen:**
- The ladder idea comes from rule V. The target-support condition comes from your stated reason on the holds.
- No constant was fitted to individual labels. The 75 / 30 / 0.25 / 1.5-mi values are carried over from v3, and 15
  is a plain minimum sample for a median.
- K1–K3 below are therefore **not blind** on v4. **K0 is the blind test.**

## 2. Protocol

1. Dev run: churn (all wells), guards, and the rung tables, which are built from vendor codes only. No labels, no
   grid agreement, no test fold. It may run before the freeze, as v3's did.
2. Freeze this file and `box/tag_ladder.py` (this commit).
3. **Blind cards.** 30 cards, 15 per basin. Each is drawn at random (seed 20261105) from producers where v4 + overrides
   differs from the live tag, excluding every labelled, overridden or planned well. Each card shows the live tag,
   the proposed bench, the well's offset and the local rungs. It does not show label status, because none of these
   wells is labelled.
4. **Michael cards them.** A bench code that differs from the proposal counts against the rule; free text is a hold
   and isn't counted.
5. Only then: the full score (K0–K13) by `scripts/tag_rule_score.py`, adapted to v4 with the same criteria code.

## 3. Criteria (FROZEN at this commit)

| # | Test | Pass |
|---|---|---|
| **K0** | Blind cards: your agree share among judged cards | **≥ 70 %** (the class gate of record), and ≥ 60 % in each basin |
| K1 | Carded labels reproduced by `rule` (not blind) | ≥ 70 % each basin |
| K2 | Midland class-accepted (not blind) | ≥ 70 % |
| K3 | The 3 #230 holds | none moved with high confidence |
| K4–K13 | As RULE.md §3 (grid, self-consistency, guards, family-move cap, Pad 3240, Lea sticks) | as written there; since rev 3, **K4–K6 (grid) are reported only** |

**If K0 passes and K1–K2 fail**, the conflict is reported as it is: blind cards against labelled history. I recommend
nothing either way until you have seen both. **If K0 fails**, v4 fails.

## 4. Revisions

| # | Date | Change | Why |
|---|---|---|---|
| 1 | 2026-11-05 | (a) v4 starts from the vendor code **after the sql/23 gross correction**, i.e. the live tag for a non-overridden well. An overridden well starts from its raw vendor code, so overrides still never leak. (b) In Lea / Ward the XY guard blocks a move between **any** family above the XY top and any at or below it (v3 checked only BS3 ↔ WCA). | Found while checking the first card draw, before any verdict. Michael had seen nothing, and no score had been computed. Starting from the raw vendor code undid sql/23's > 600 ft fixes wherever v4 couldn't judge: 204 wells, e.g. PRE-ONGARD WELL #009 BS1_S → OTHER at 5,007 ft, and WARWINK UNIVERSITY 18-34 A 2H WCB_1 → BS3_S at 12,650 ft. The guard gap was found on the latter. The first draw is kept unjudged in `v4-blind-cards-2026-11-05-superseded/`; the cards were re-drawn with the same seed. |
| 2 | 2026-11-05 | (a) **Nearest anchor with a 1,000-ft lever cap.** Anchors are Delaware BS1_S / BS2_S / WCA and Midland JM / LSSH / WCA_1. Each well uses the anchor nearest its depth, and only if the offset is ≤ 1,000 ft; otherwise it keeps its code (`no_anchor`). (b) **No move into a multi-bench cluster** (`ambiguous_target`). (c) **Cards draw evidence wells only**: no planned survey, nothing under 4,000 ft. | Michael on card 1 of the revision-1 draw (COTTON DRAW UNIT #115H, AVA_2 at 8,920 ft, local AVA_2 median 8,960 / AVA_1 8,744). v4 measured it from the WCA band 2,969 ft below. The local Avalon–WCA interval runs about 170 ft thicker than Eddy's average, which is more than the 220-ft AVA_1/AVA_2 spacing, and v4 moved it into the AVA_0/AVA_1 cluster (rungs 26 ft apart). He also flagged sub-2,000-ft records on the card: excluded from v4 (4,000-ft evidence floor) but drawn on the plot, along with planned surveys, against his standing rule. Only card 1 was looked at, and no verdict was recorded. That draw is kept as `v4-blind-cards-2026-11-05-superseded-2/`, and the cards are re-drawn with the same seed. |
| 3 | 2026-11-05 | (a) **Delaware grid removed from the rule** (`use_grid = False`): it neither decides nor vetoes. Grid agreement stays in the scoreboard as a reported number; **K4–K6 become reported, not gating**. (b) **Move / high-confidence bar raised to 80 ft** (`conf_min_ft`; the quarter-gap bar stays). (c) **K0 is re-run on a fresh blind draw** of 30 (seed 51125), excluding every well on any earlier draw, plus labelled and overridden wells; same pass bar. | Michael, after the rev-2 K0 failed 14/30. All 4 grid-decided Delaware moves were rejected: his B1 / B2 tops are not where operators split WCA/WCB and WCB_2/WCC, and grid refinement is a longer-term geology task outside this work. Agreement tracked margin (median 87 ft agreed vs 51 ft rejected; 8/8 at ≥ 80 ft). **80 ft is fitted to those cards**, which is why the test is a fresh draw. |
| 3a | 2026-11-05 | **Card 23 (PARKS, ROY 316CH, 4232943352) is excluded from the K0 count**, which is scored on the other 29. Declared before any rev-3 verdict. | Not blind: Michael called it on 2026-10-30 (step-20a `owner_benches.csv` / `well_calls.csv`: back to the vendor WCC). Its live tag is still WCB_2 because it is one of the 4 stale override rows never reloaded, so v4's WCC matches his call. The labelled set misses his back-to-vendor calls; adding them is a scoreboard follow-up. |
