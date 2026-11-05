# formation_blueox rule v4, "the ladder" (revision 2, after v3 failed)

**Status:** DRAFT until the freeze commit that adds this file. Nothing is applied.

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
- **Anchor.** The median depth of witnesses of the basin's anchor family within 1.5 mi, with 3 or more of them.
  - Delaware: WCA (WCXY + WCA_1 + WCA_2), falling back to BS2_S.
  - Midland: WCA_1, falling back to LSSH.
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
  - **Move** to the cluster's nearest bench only when the margin clears that bar **and** the target family has 3 or
    more evidence wells within 1.5 mi. That second condition comes from your reason for holding three #230 cards:
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
| K4–K13 | As RULE.md §3 (grid, self-consistency, guards, family-move cap, Pad 3240, Lea sticks) | as written there |

**If K0 passes and K1–K2 fail**, the conflict is reported as it is: blind cards against labelled history. I recommend
nothing either way until you have seen both. **If K0 fails**, v4 fails.

## 4. Revisions

| # | Date | Change | Why |
|---|---|---|---|
| — | — | — | — |
