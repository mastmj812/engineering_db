# Rule v5 class cards — round 1 findings (2026-11-06)

**Status:** round 1 scored. Nothing is applied.

- Verdicts: Michael, in `cards_sample.csv`. Card 37 (TX AMERICAN SYNDICATE ST B 212 1H, Pecos) was skipped as too
  far from any control, so it is a hold and isn't counted.
- Scorer: `scripts/tag_v5_score.py`. Counting is the unit-level rule declared in `RULE_V5.md` before any verdict; the
  gate is `box.tag_screen.decide`.
- Outputs: `cards_scored.csv`, `class_decisions.csv`, `score.json`.

## Overall

- **54 cards judged; 45 agree on the unit (83 %).**
- 8 of the 9 cards that disagree say "keep today's tag". Only one names a third bench: card 22, MORGAN RANCH 35-47 B
  UNIT L 5H, which v5 proposed as JM; Michael says WCA_1.

## By class

| # | Class | Wells | Agree / judged | Decision |
|---|---|---|---|---|
| 1 | Midland WCA_1 → WCB_1 (pattern) | 296 | 4 / 5 | round 2 (+5) |
| 2 | Midland WCA_1 → WCB_1 (depth) | 183 | 5 / 5 | **accept** |
| 3 | Delaware WCB_1 → WCA_1 (depth) | 163 | 4 / 5 | round 2 (+5) |
| 4 | Midland LSSH → JM (depth) | 115 | 5 / 5 | **accept** |
| 5 | Midland LSSH → JM (pattern) | 82 | 4 / 5 | round 2 (+5) |
| 6 | Delaware BS3_C → BS2_S (depth) | 79 | 5 / 5 | **accept** |
| 7 | Midland WCB_1 → WCA_1 (depth) | 55 | 4 / 5 | round 2 (+5) |
| 8 | Delaware BS3_S → WCA_1 (pattern) | 30 | 3 / 4, 1 hold | round 1 incomplete; any 5th card leaves it in round 2 (+6) |
| 9 | Delaware OTHER → AVA_0 (depth vs other) | 29 | 5 / 5 | **accept** |
| 10 | Delaware WCA_2 → WCB_1 (depth) | 29 | 3 / 5 | round 2 (+5) |
| 11 | Delaware BS2_C → BS1_S (depth) | 22 | 3 / 5 | round 2 (+5) |

- **Accepted:** 4 classes, 406 wells.
- **Rejected:** none.
- **Round 2:** 7 classes, 677 wells. They need 36 more cards (5 per class, 6 for class 8) and are judged at 7 / 10.
- Classes under 20 wells (205 wells) keep today's tag, as frozen.

## What the cards say

**1. Sub-bench placeholder (class 3).** All 4 agreeing cards chose **WCA_2**, not the proposed WCA_1:
- DEEP ELEM 4 FEDERAL COM #733H, HAY YENGLIK 001 0014WA, BIG PINEY 57-2-41 1H, MAROON BELLS 13-14 UNIT F 6H.
- This confirms the limitation stated before the cards: when coarse-Novi "Wolfcamp A" wins, the crosswalk writes
  WCA_1 as a placeholder.
- The unit is right, but an accepted class 3 would write the wrong sub-bench on most of its 163 wells.
- So whatever class 3 decides, its sub-bench needs its own step: today's sql/16 sub-bench, or a depth split inside WCA.

**2. The pre-check helped, but it is not the gate.**

| Pre-check | Cards judged | Agree |
|---|---|---|
| agrees | 30 | 27 (90 %) |
| disagrees | 13 | 9 (69 %) |
| no read | 11 | 9 (82 %) |

- A disagreeing pre-check lowered the odds, but most of those calls still held.
- The 3 cards that failed despite an agreeing check:
  - CONDIMENT KING 6920A-34 7H: 206 ft closer to WCB, Michael kept WCA_2.
  - NEPTUNE 10 STATE COM #401H: 468 ft closer to BS1, Michael kept BS2_C.
  - ST KITTS 76 2833 TG 601H: 176 ft closer to BS1, Michael kept BS2_C.
- On these three the witness reference itself is suspect, not the rule's arithmetic.

**3. Ward WCA ↔ WCB (observation only, nothing tuned).**
- In class 10, both Ward cards were rejected (UL LOVELAND 1920-17 6H, CONDIMENT KING 6920A-34 7H). All 3 Reeves cards
  agreed.
- Step-A card 1, UL 16 TILDEN WB1 1H (Ward, proposed WCB_1), was also marked WCA_2.
- Rule B already guards BS3 ↔ WCA in Lea / Ward. A Ward WCA ↔ WCB guard would be a rule change, so it is not made
  here. The round-2 cards will show whether the pattern holds.

**4. OTHER → AVA_0 is accepted on cards with no pre-check read.** On those cards the strike section had to carry the
call alone.

## Next (Michael's call)

1. Draw round 2 for classes 1, 3, 5, 7, 8, 10, 11. Same seed rule; wells not on any earlier card.
2. Decide how a class-3 acceptance treats the sub-bench.
3. Only after both rounds: the warehouse step (a new matview replacing sql/16's decision logic, off-hours), with an
   explicit go.
