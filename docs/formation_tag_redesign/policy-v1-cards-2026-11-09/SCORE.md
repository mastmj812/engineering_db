# Policy v1 cards: scored (2026-11-09)

Michael's verdicts are in `step1/cards_sample.csv` and `step3/cards_sample.csv`. Read-only. Nothing is applied.

## Step 1 round 1 (cards 1–20): all four classes go to round 2

Counting is Step 1's frozen rule (`scripts/tag_v5_score.py`):
- ACCEPT counts as agree.
- A bench code in the proposed code's UNIT agrees on the unit; its sub-bench is recorded on the well.
- A code in another unit counts against.

The gate: 5/5 accepts, 0–1 of 5 rejects, otherwise 5 more cards and 7/10.

| Class | Wells | Agree | Against | Decision |
|---|---|---|---|---|
| 12: BS3_C → BS2_S (pattern) | 100 | 3 | 2 | round 2: needs 4 of the next 5 |
| 13: BS3_S → WCXY (depth) | 75 | 4 | 1 | round 2: needs 3 of the next 5 |
| 14: BS2_C → BS1_S (pattern) | 34 | 4 | 1 | round 2: needs 3 of the next 5 |
| 15: BS3_S → WCA_1 (depth) | 23 | 4 | 1 | round 2: needs 3 of the next 5 |

**The cards that did not agree.** Each of these is kept as Michael's call on that well, whatever its class decides.

| Card | Well | Proposed | Call | Pre-check |
|---|---|---|---|---|
| 4 | THUNDERBALL FEDERAL COM #223H (Lea) | BS2_S | BS3_C | no read |
| 5 | PAKSE 4 SOUTH FEDERAL COM #303H (Lea) | BS2_S | BS3_C | no read |
| 6 | DR STATE WISE UNIT 1 015 0154TB (Culberson) | WCXY | BS3_S | disagreed: flagged before sending |
| 10 | BLAZER UNIT 14 3WA (Reeves) | WCXY | **WCA_1**: same unit, counts as agree; sub-bench WCA_1 on the well | agrees |
| 14 | SAN ANTONIO 76 2734 TG 601H (Loving) | BS1_S | BS2_C | disagreed by 24 ft |
| 20 | DARLINGTON UNIT 11B5 5H (Reeves) | WCA_1 | BS3_S | agreed by 377 ft: the one miss of a clean pre-check |

**Pre-check against verdict:**
- where the pre-check agreed, 8 of 9 verdicts agreed;
- where it disagreed, 1 of 3;
- where there was no read, 6 of 8.

**Reading the result.**
- **Class 12** is the weak one. Its pattern is Novi THIRD BONE SPRING LIME vs Enverus 2ND BONE SPRING SAND, with Enverus backed in 77 % of 112 depth-decided wells. Both rejects are Lea wells with no local depth read.
- The two pattern classes (12, 14) are the ones with no depth read at the well, so the cards are judging the learned winner itself.

## Step 1 round 2 (cards 24–43): drawn, awaiting verdicts

- **Folder:** `step1_round2/` (`cards.html`, `cards_sample.csv`).
- **Draw:** 5 per class from wells not carded before (seed `SEED_ROUND2`), on the same snapshot (`sbcache_xys`) with the policy table.
- **Numbering:** cards start at 24, clear of Step 3's cards 21–23.

**Pre-check:**
- classes 12 and 14: no plain-median read on any card (pattern classes, as expected);
- class 13: all 5 agree;
- class 15: all 5 agree.

**To score after marking:**

```
python -m scripts.tag_v5_score --cards docs/formation_tag_redesign/policy-v1-cards-2026-11-09/step1 docs/formation_tag_redesign/policy-v1-cards-2026-11-09/step1_round2
```

## Step 3 follow-ups (cards 21–23): all accepted

| Card | Well | Input | Final | Note |
|---|---|---|---|---|
| 21 | HARACZ AMO FEDERAL #009H (Eddy) | AVA_0 | WCXY | new move after the XY row |
| 22 | SALADO DRAW 9 16 W0BO FEDERAL COM #002H (Lea) | OTHER | **WCXY** | **supersedes v5.2 card 50** (call WCA_1 then; the evidence moved with the XY witnesses) |
| 23 | SQUINTS 4 5 FEE #715H (Eddy) | WCXY | WCA_1 | confirms card 11's call |

**Effect on the Step 3 set.** `v5_2-cards-2026-11-08/final_v5_2.csv` still holds 140 wells. Of those, SALADO DRAW moves WCA_1 → WCXY, and SQUINTS is unchanged at WCA_1. HARACZ AMO adds one more, for **141 Step 3 wells** once the warehouse step assembles the rule table.

## Tooling fixes made while scoring

- `box/tag_screen.py`: `clear_verdict` and `unknown_bench_codes` read **ACCEPT** as agree. These cards asked for ACCEPT; the frozen counting used only "agree". A test was added.
- `scripts/tag_v5_cards.py`, already-carded exclusion: it now searches card sets' step subfolders too. The old one-level glob missed `policy-v1-cards-2026-11-09/step1/`, and a first round-2 draw repeated 5 judged wells. That draw was discarded before anyone saw it.
- `scripts/tag_v5_cards.py`, numbering: `--first-card` now applies to round 2 as well, to keep card numbers unique across sets.
