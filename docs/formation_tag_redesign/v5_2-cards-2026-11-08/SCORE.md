# Rule v5.2 cards — score (2026-11-09)

Michael's verdicts: `cards_sample.csv`. Scored with `python -m scripts.tag_v5_2_score --cards <this folder> --dev
../v5_2r1-dev-2026-11-08`, which writes `cards_scored.csv`, `final_v5_2.csv` and `score.json`. Read-only. Nothing is
applied.

## Verdicts (124 cards)

| Section | Cards | Agree | Bench-code call | SUSPECT TVD | Hold |
|---|---|---|---|---|---|
| A: class sample, Delaware OTHER → AVA_0 | 10 | **10** | 0 | 0 | 0 |
| B: full review (other v5.2 moves) | 87 | 81 | 5 | 1 | 0 |
| C: sql/23 unplaced (proposal = sql/23's code) | 27 | 8 | 8 | 11 | 0 |

- **Class A is accepted (10/10, the bar is 7/10).** The 28 uncarded wells of the class take AVA_0.
- **B: 81 of 87 accepted** (card 11 by clarification, below). All four cards the plain-median pre-check marked (35, 37, 40, 45) were accepted.
- **Sub-bench basis in B:**

  | Basis | Agree | Overruled |
  |---|---|---|
  | `depth` | 20 | 0 |
  | `single` (a single-code unit) | 12 | 1 |
  | `nearest` (low confidence) | 49 | 4 |

- **The five B calls:**
  - card 46, TEA OLIVE #128H (Lea): BS3_S → **WCA_1**. This changes the unit.
  - card 66, LOE FEDERAL #803H (Lea): WCC → **WCB_2**. This changes the unit.
  - cards 75, 76, 79 (Martin / Midland): WCB_2 → **WCB_1**, which is v5's sub-bench. All three were `nearest`.
- **C:**
  - 7 ACCEPT plus card 106 (written WCC = the proposal): 8 wells keep sql/23's code.
  - 8 bench-code calls: the FULLER pad is WCC ×3 and WCB_2 ×2; WARWINK UNIVERSITY 2H and 3H are WCC; POKER LAKE #179H is
    WCB_2.
  - 11 SUSPECT TVD.

## The final v5.2 set (`final_v5_2.csv`)

**140 wells leave their input tag** (Delaware 111, Midland 29). 127 of them are inside the BOX record extents.

| Basis | Wells |
|---|---|
| `v5_2_class_accepted` (uncarded AVA_0 class wells) | 28 |
| `v5_2_carded_accept` (A + B) | 91 |
| `sql23_v5_2_carded_accept` (C, sql/23's code confirmed) | 8 |
| `carded_call` (B 5 + C 8) | 13 |
| `depth_excluded` (keeps its input tag) | 12 |

- **Guard checks (gating):**
  - zero rule moves into or out of WDFD / BRNT / MISS;
  - zero human calls changed (the rule never judges them).
- **Fixed-point check.** I re-ran v5.2 with every card verdict applied as a human call and the 12 suspect depths turned
  off as evidence. It made no new move. The only moves left are the 28 class-accepted wells and card 11 (then still held), so the
  verdicts don't shift anyone else's reference. Only one of the 12 suspect wells was a witness (card 92, a WCB_1
  witness), and removing it changed nothing.

## Open items for the warehouse step

1. **SUSPECT TVD (12 wells): a new verdict class.** The rule can't judge a well whose depth Michael doesn't trust.
   These wells keep the input tag (the vendor tag via sql/16).
   - **They need a durable depth exclusion** (evidence off for v5 / v5.2 and as a witness). Without one, the next run on
     new data re-proposes them.
   - Four are survey depths, not `tvd_ft`-only: BUTTER CRUNCH J 4WB, PRESTON-FREEMAN 15F 106H, PUTNAM THE PIO 32 7LS
     and NEAL 34GG 12HM. So "survey" alone doesn't prove a depth is clean.
   - **DECIDED (Michael, 2026-11-09):** they go in the rule table as depth exclusions. The rows are in
     `depth_exclusions.csv`; the design is in `../WAREHOUSE_STEP.md`, Q5.
2. **Card 11, SQUINTS 4 5 FEE #715H (Eddy, Mewbourne): RESOLVED, WCA_1.** "Can't find" meant the well was hard to
   find in anduin, not a card problem. The well has no bench tag, so it draws as a grey dot, and it sat under the grey
   "Carlsbad" map label. Michael called it WCA_1 in chat (2026-11-09), which is v5.2's proposal. The marked verdict stays
   in `cards_sample.csv`; the call is in `clarifications.csv`.
   - Novi's "WOLFCAMP A (XY)" is a coarse value that defers to Enverus, and Enverus has no interval for this well, so
     the warehouse tag is NULL. anduin's Formation filter has no `(unmapped)` entry for such wells (2,421 of 70,228 in
     anduin), so they show every bench at 0. That is an anduin follow-up, not part of this step.
