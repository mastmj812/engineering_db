# Rule v5.2 rev 1 — dev run findings (2026-11-08)

This is a read-only run on the Nov 5 snapshot cache. The input is the accepted tag without sql/23. It produced no
cards and no labels. Files:
- `summary.json`
- `change_classes.csv`
- `changes.csv`: the 125 moves
- `sql23_wells.csv`: the 157 sql/23 wells in the evidence frame
- `sql23_outside_frame.csv`: the 77 outside it
- `flagged.csv`

The first run, before rev 1, is in `../v5_2-dev-2026-11-08-superseded/`.

## Moves: 125 (Delaware 96, Midland 29)

| | Delaware | Midland |
|---|---|---|
| Judged (evidence, not a human call) | 28,135 | 28,067 |
| Not a miss (`gm_ok`) | 23,214 | 25,757 |
| Own unit's extent unknown on the well's side, or no reference (`gm_no_control`) | 3,723 | 2,037 |
| OTHER / unmapped, no unit within 150 ft (`gm_other_kept`) | 1,020 | 234 |
| Miss, but no unit decisively within 300 ft (`gm_unplaced`, kept, flagged) | 62 | 10 |
| Miss, guarded: protected bench or BS3 ↔ WCA in Lea / Ward (`gm_guard`) | 17 | 0 |
| Miss, references inverted (`gm_inverted`) | 3 | 0 |
| **Moved (`gm_move`)** | **96** | **29** |

- **Every move changes the unit.** 112 of the 125 sit inside the BOX record extents.
- **Guard checks:** zero moves into or out of WDFD / BRNT / MISS, and zero human calls touched.
- **77 moves start from OTHER** (Delaware 65, Midland 12). The largest class is **Delaware OTHER → AVA_0, 38 wells:**
  - Novi "LEONARD" + Enverus "UPPER AVALON": 25;
  - Novi "LEONARD" + Enverus "MIDDLE AVALON": 6;
  - Novi "LEONARD" + Enverus 2ND / 1ST BONE SPRING: 7.

  v5 kept these on OTHER, because the blended AVA reference was more than 150 ft away. The AVA_0 code reference is
  within 150 ft (median 20 ft).
- **The remaining 87 moves** fall in classes of fewer than 20 wells, so each gets its own card under the frozen
  acceptance.
- **52 moves land on wells whose v5 change class was rejected or not accepted.** The cards will show v5's proposal
  beside v5.2's.
- **Sub-bench choice:** 51 by depth, 60 nearest-code (low confidence), 14 single-code units.

## What retiring sql/23 does to the 234 wells it corrects today

**Inside the evidence frame (157):**

| Outcome | Delaware | Midland | Total |
|---|---|---|---|
| v5.2 moves to sql/23's code | 14 | 13 | 27 |
| v5.2 moves to a different bench | 9 | 0 | 9 |
| Vendor tag is within 600 ft of its own reference: v5.2 says **sql/23 was wrong** | 17 | 7 | 24 |
| A miss, but no unit decisively close (`gm_unplaced`) | 21 | 6 | 27 |
| OTHER, no unit within 150 ft (`gm_other_kept`) | 30 | 4 | 34 |
| No control on the well's side (`gm_no_control`) | 29 | 6 | 35 |
| References inverted | 1 | 0 | 1 |

On the 24 "sql/23 was wrong" wells, many vendor tags sit almost on their own reference. For example, Pecos WCA_1 is
3.5 ft from the WCA_1 reference, and sql/23 moved it to WCA_2. Eddy WCA_1 is 0.9 ft off, and sql/23 moved it to WCXY.
This is the same failure as card 12.

**Outside the evidence frame (77), never judged by any rule:**
- Delaware: 43 planned surveys, 20 under 4,000 ft, 6 permit-round depths.
- Midland: 4 under 4,000 ft, 4 permit-round depths.

sql/23 moves these on depths the standing rule doesn't accept as evidence. When it retires, they take their vendor tag.

**Net effect if sql/23 retires with v5.2 and nothing else:**
- 36 of the 234 stay moved (27 to sql/23's code, 9 elsewhere);
- 24 + 77 revert, on evidence that sql/23 was wrong or never had a valid depth;
- **97 revert with nothing confirming either way** (unplaced 27, OTHER 34, no control 35, inverted 1).

The 97 are the open decision. The options are below.

## Crossing area (step-A method, same extents; adjacent / non-adjacent sq mi)

| | Delaware | Midland |
|---|---|---|
| Live today (sql/16 + overrides + sql/23) | 532 / 171 | 94 / 5 |
| Accepted tags, sql/23 removed (input) | 521 / 166 | 83 / 5 |
| **v5.2** | **520 / 146** | **81 / 5** |

v5.2's effect is almost all **non-adjacent** crossings: Delaware 166 → 146 sq mi. These are gross misses, as intended.
In the first run, before rev 1, Delaware adjacent area rose to 545 sq mi. Rev 1 removed that artifact.

## Rev 1 vs the first run

- The first run made 206 moves; rev 1 makes 125. 86 are in both, 120 were dropped by rev 1, and 39 are new.
- The drops are the mixed-reference artifacts, mainly BS3_S → WCXY / WCA_1 (59) and the "BS1" code bug (18).
- The rev-1b relabel (the unknown-extent test applies only past 600 ft) moved 7,982 Delaware / 1,416 Midland wells
  from `gm_no_control` to `gm_ok`. The move set is identical (125 = 125).

## Next: cards (not drawn yet)

- **Under the frozen acceptance:**
  - 10 cards for Delaware OTHER → AVA_0 (38 wells; accepted at 7/10);
  - one card for each of the other **87** moves.
  - Every card is pre-checked against plain local medians before it is sent.
  - Cards show the v5 code when it differs, and ask for a bench code when the answer is neither the proposal nor the
    input tag.
- **The 97 unconfirmed sql/23 wells: Michael's call.**
  - (a) Card them, with sql/23's code as the proposal, so each becomes a human call.
  - (b) Card only the 27 `gm_unplaced`, which are known misses of more than 600 ft. The other 70 keep the vendor tag,
    flagged (Gate 0 Q3).
  - (c) Card none; all 97 keep the vendor tag, flagged.
