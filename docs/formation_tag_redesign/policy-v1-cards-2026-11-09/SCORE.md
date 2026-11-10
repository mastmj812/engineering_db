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

## Step 1 round 2 (cards 24–43): scored. Final: 12, 13 and 15 accepted; 14 rejected

Round 2 drew 5 per class from wells not carded before (seed `SEED_ROUND2`), on the same snapshot with the policy table.
The two rounds were scored pooled: `python -m scripts.tag_v5_score --cards .../step1 .../step1_round2`. Outputs are in
`step1_round2/` (`cards_scored.csv`, `class_decisions.csv`, `score.json`).

| Class | Wells | Agree / 10 | Decision | Agree / judged, by county |
|---|---|---|---|---|
| 12: BS3_C → BS2_S (pattern) | 100 | 7 | **accept** (exactly at the gate) | Eddy 5/5 · **Lea 2/5** |
| 13: BS3_S → WCXY (depth) | 75 | 8 | **accept**; 3 of the 8 are WCA_1 calls | Eddy 3/3 · Loving 3/3 · Reeves 1/1 · Winkler 1/2 · Culberson 0/1 |
| 14: BS2_C → BS1_S (pattern) | 34 | 6 | **reject** | Eddy 3/3 · Lea 2/2 · Reeves 1/1 · **Loving 0/4** |
| 15: BS3_S → WCA_1 (depth) | 23 | 8 | **accept** | Eddy 3/3 · Reeves 4/5 · Loving 1/2 |

**The class populations by county:**
- class 12: Eddy 50, Lea 32, Loving 8, Culberson 6, Reeves 3, Pecos 1;
- class 14: Loving 12, Lea 9, Eddy 7, Reeves 3, Ward 2, Winkler 1;
- class 13: Loving 42, Eddy 20, Culberson 5, Winkler 5, Reeves 3.

**Wells:**
- in the accepted classes: 198 (100 + 75 + 23);
- in the rejected class: 34. Those keep today's tag, BS2_C.

Every carded call is kept on its well. The round 2 calls:
- 27 IRONHOUSE 19 STATE COM #003H: BS3_C;
- 29 KANGAROO 12 FEDERAL COM #203H: WCA_1;
- 32 UNIVERSITY BLK 21 1803H: WCA_1;
- 33 BRIDAL VEIL STATE W 4132-27 I 9H: BS3_S;
- 36, 37, 38 (COPPERHEAD, ST. CLOUD, ST. BRIDES; Loving): BS2_C;
- 41 PERMIT 76-44 LOV UNIT 2H: BS3_S.

**Pre-check against verdict, both rounds:**
- where it agreed, 16 of 19 verdicts agreed;
- where it disagreed, 1 of 3;
- where there was no read, 12 of 18.

**What the gate does not see (for Michael's call; nothing is changed):**
1. **Class 12 rejects are all in Lea** (3 of 5 Lea cards; Eddy 5/5). As frozen, accepting puts BS2_S on all 32 Lea wells.
2. **Class 14 rejects are all in Loving** (0/4; elsewhere 6/6). As frozen, the class is rejected, so the non-Loving wells keep BS2_C too.
   - A county split of either class would be drawn after seeing the verdicts. It would need its own fresh cards to stand.
   - Separately, policy v1 still lists Enverus as the winner for this string pair, although the class was rejected. The gate, not the policy table, decides what is applied.
3. **Class 13 is accepted on the unit, but 3 of its 10 cards were called WCA_1, not WCXY:**
   - 10 BLAZER UNIT 14 3WA (Reeves);
   - 29 KANGAROO (Eddy);
   - 32 UNIVERSITY BLK (Winkler).

   No step adjudicates WCXY vs WCA_1 within the WCA unit; this is the same open item as the 953 same-unit conflicts. So the 72 uncarded wells would take WCXY.

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
