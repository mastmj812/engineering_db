# Policy v1 cards (2026-11-09)

These are the cards the adoption of Step 1 policy v1 needs (string-keyed, frozen learned winners; `../RULE_V5.md`,
Policy v1), on the snapshot with the WOLFCAMP A (XY) crosswalk row. Read-only. Nothing is applied.

## `step1/` — Step 1 (vendor choice) class cards, 20 cards

These are the change classes of ≥ 20 wells that are new or newly over 20. The gate is Step 1's own, frozen: 5 cards per
class; 5/5 accepts it, 0–1 of 5 rejects it, otherwise 5 more cards and 7/10. Classes are numbered after the 11 reviewed
Step 1 classes.

| Class | Wells | Cards | Basis |
|---|---|---|---|
| 12: Delaware BS3_C → BS2_S | 100 | 1–5 | pattern: Novi THIRD BONE SPRING LIME vs Enverus 2ND BONE SPRING SAND; depth backed Enverus 77 % of 112 |
| 13: Delaware BS3_S → WCXY | 75 | 6–10 | depth (per well) |
| 14: Delaware BS2_C → BS1_S | 34 | 11–15 | pattern: Novi SECOND BONE SPRING LIME vs Enverus 1ST BONE SPRING; depth backed Enverus 96 % of 23 |
| 15: Delaware BS3_S → WCA_1 | 23 | 16–20 | depth (per well) |

**Pre-check.** This is the plain median of each unit's witnesses within 2 mi, compared with the call. Cards that
disagree are marked, not dropped.
- **Classes 12 and 14 (pattern):** 7 of 10 have no plain-median read. That is expected: a pattern call exists because
  depth could not decide at the well. Cards 1 and 14 disagree by 50 ft and 24 ft.
- **Class 15:** all 5 agree.
- **Class 13:** 4 of 5 agree. **Card 6 disagrees, and it looks right to:** DR STATE WISE UNIT 1 015 0154TB (Culberson,
  7,872 ft) sits in its section's BS3_S band (7,887 ft, 6 wells). The rule's BS3 estimate there is 6,714 ft against a
  plain median of 7,833 ft (n = 3), an extrapolation on thin control.

## `step3/` — Step 3 (depth check) follow-up cards, 3 cards (21–23)

| Card | Well | Why it is here |
|---|---|---|
| 21 | HARACZ AMO FEDERAL #009H (Eddy) | a new move after the XY row: AVA_0 → WCXY |
| 22 | SALADO DRAW 9 16 W0BO FEDERAL COM #002H (Lea) | re-card of v5.2 card 50: you accepted WCA_1; it now proposes WCXY (Enverus says WOLFCAMP XY) |
| 23 | SQUINTS 4 5 FEE #715H (Eddy) | confirm your card-11 call WCA_1, now that the vendor tag is WCXY. ACCEPT keeps WCA_1; REJECT takes WCXY |

## Marking

Mark the verdict column in each `cards_sample.csv`:
- **ACCEPT** takes the proposed code.
- **REJECT** keeps today's tag (Step 1) or the input tag (Step 3).
- **A bench code** is your call on the well.
- Anything else is a hold.
