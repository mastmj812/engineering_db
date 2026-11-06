# Rule v5 class cards — round 2 and final class decisions (2026-11-06)

**Status:** acceptance cards complete. Nothing is applied.

- Verdicts: Michael, `cards_sample.csv` (cards 56–91).
- Pooled with round 1: `python -m scripts.tag_v5_score --cards ../v5-cards-2026-11-06 .` → `class_decisions.csv`,
  `cards_scored.csv`, `score.json`.
- Counting is unit level, as declared in `RULE_V5.md` before any verdict. Each round-2 class is judged at 7 / 10.

## Result

- Round 2 alone: 27 / 36 agree on the unit.
- Pooled over both rounds: **72 / 90 (80 %)**.

| # | Class | Wells | Agree / judged | Decision |
|---|---|---|---|---|
| 1 | Midland WCA_1 → WCB_1 (pattern) | 296 | 9 / 10 | **accept** |
| 2 | Midland WCA_1 → WCB_1 (depth) | 183 | 5 / 5 | **accept** (round 1) |
| 3 | Delaware WCB_1 → WCA_1 (depth) | 163 | 6 / 10 | **reject**: keep today's WCB_1 |
| 4 | Midland LSSH → JM (depth) | 115 | 5 / 5 | **accept** (round 1) |
| 5 | Midland LSSH → JM (pattern) | 82 | 7 / 10 | **accept** (at the gate) |
| 6 | Delaware BS3_C → BS2_S (depth) | 79 | 5 / 5 | **accept** (round 1) |
| 7 | Midland WCB_1 → WCA_1 (depth) | 55 | 7 / 10 | **accept** (at the gate) |
| 8 | Delaware BS3_S → WCA_1 (pattern) | 30 | 8 / 10, 1 hold | **accept** |
| 9 | Delaware OTHER → AVA_0 (depth vs other) | 29 | 5 / 5 | **accept** (round 1) |
| 10 | Delaware WCA_2 → WCB_1 (depth) | 29 | 8 / 10 | **accept** |
| 11 | Delaware BS2_C → BS1_S (depth) | 22 | 7 / 10 | **accept** (at the gate) |

- **Accepted:** 10 classes, 920 wells.
- **Rejected:** class 3, 163 wells, which keep today's tag.
- Classes under 20 wells (205 wells) keep today's tag, as frozen.

**Carded wells take Michael's own call, whatever their class decided.** His bench code is the well-level record. That
means:
- the 6 class-3 wells he called WCA_2 move to WCA_2;
- the rejected wells inside accepted classes keep the code he wrote.

## What round 2 added

**1. Delaware WCA ↔ WCB stays the hard boundary.**
- Class 3 (WCB_1 → WCA_1) failed at 6 / 10.
- All 6 of its agreeing cards said WCA_2, never the placeholder WCA_1. So even its correct calls would have written the
  wrong sub-bench.
- The rejects: Loving ×2 (LINDLEY 98 1 13H, PISTOL 24-9 1H), Lea (FEARLESS 26 FEDERAL COM #720H), Winkler (UL 20 S
  CHATTER C 2703H).
- The agrees: Eddy, Culberson ×2, Reeves ×2, Ward.
- Two of the rejects had a pre-check that agreed, by 319 ft and 101 ft. So the witness depths do not separate WCA from
  WCB there.
- This repeats v4's finding (Delaware WCA ↔ WCB 1 / 8) with an independent method. It is a geology or reference problem,
  not a rule constant.

**2. The Ward WCA ↔ WCB signal did not hold.**
- In round 2 both Ward cards agreed with the move (FLYING FORTRESS 98-83 401H → WCA_2, STOCKYARDS STATE B 347 3471H →
  WCB_1).
- Across both rounds Ward is 2 of 4 on these classes. No guard is warranted.

**3. Three classes passed exactly at the gate** (5, 7, 11, each 7 / 10). Their rejects:
- Midland LSSH → JM (pattern): TARZAN UNIT 1 2071JH and HILL UNIT 2 2577JH, both in Martin, both with no pre-check read.
  Plus MORGAN RANCH from round 1.
- Midland WCB_1 → WCA_1: BENNIE 4342 4H and SCOTT SUGG SE UNIT H 51U, both in Irion. Plus SCOTT SUGG SE UNIT H 41U from
  round 1. Three of its rejects are in Irion.
- Delaware BS2_C → BS1_S: SENILE FELINES 18 7 STATE COM #003H in Lea. Plus NEPTUNE 10 STATE COM #401H (Lea) and ST KITTS
  76 2833 TG 601H (Loving) from round 1. All three had agreeing pre-checks of 176–468 ft.

At 7 / 10, roughly 1 in 4 of the uncarded wells in these classes may be wrong. That is the gate of record and is
accepted as such. A later review could re-card Irion WCB ↔ WCA_1 and the Lea BS2_C → BS1_S wells.

**4. The pre-check, pooled over 90 cards:**

| Pre-check | Agree / judged |
|---|---|
| agrees | 40 / 47 (85 %) |
| disagrees | 15 / 21 (71 %) |
| no read | 17 / 22 (77 %) |

It is informative but weak, and it stays a card annotation, not a gate.

## Reported, not gating (`../v5-accepted-2026-11-06/`, `scripts/tag_v5_accepted.py`)

**The accepted tag** = Michael's carded call where he carded the well, else v5 in an accepted class, else today's tag.

**Changes against live:**
- Delaware: 188 of 28,303 producers (149 by class, 39 carded calls).
- Midland: 725 of 28,441 (691 by class, 34 carded calls).
- 887 of the 913 are inside the BOX record extents.
- Every change is a unit change. No sub-bench is moved by class acceptance.

**Labelled-set reproduction is unchanged** (not blind): Delaware carded 93 / 108, Midland carded 103 / 103, Midland
class-accepted 227 / 227. The accepted classes touch no labelled well's answer in either direction.

**sql/23 corrections:** 155 of 157 are kept.

**Step-A landing-surface crossing area** (adjacent pairs; same method and extents, live vs accepted tags):

| Basin | Live | Accepted |
|---|---|---|
| Delaware | 532 sq mi (3.29 %) | 534 sq mi (3.30 %), flat |
| Midland | 94 sq mi (0.71 %) | 82 sq mi (0.62 %), −13 % |

- **Where Delaware fell:** BS2_S | BS3_C 17 → 8 sq mi (the BS3_C → BS2_S class) and BS3_S | WCA_1 33 → 28.
- **Where Delaware rose:** the sub-bench pairs, WCA_1 | WCA_2 174 → 176, WCXY | WCA_1 79 → 84 and BS3_C | BS3_S 61 → 67.
- So the unit fixes work. The coarse-vendor default (WCA_1) adds wells to the WCA_1 | WCA_2 crossing, and that pair
  already has the largest crossing area in the basin. This is the measured side of the sub-bench question on card 62.

**The unresolved list:** 2,830 wells keep today's tag, flagged (2,759 in extents); 52 are "neither vendor" (both
references > 300 ft away). The top "neither vendor" patterns:
- THIRD BONE SPRING vs WOLFCAMP XY ×9;
- THIRD BONE SPRING LIME vs 2ND BONE SPRING SAND ×9;
- WOLFCAMP A vs WOLFCAMP B UPPER ×9.

Most of those sit **between** a blended unit reference and the next one. That is the same pooled-reference effect, not
a well outside the column.
