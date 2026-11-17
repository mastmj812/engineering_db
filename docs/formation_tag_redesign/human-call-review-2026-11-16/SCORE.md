# Human-call review: scored (2026-11-16)

- **Reader:** the seed builder's verdict rule (`scripts.tag_rule_seeds.read`). Each card decides only its own well.
- **Output:** `cards_scored.csv` (`final` = the well's call after this review, `changed` = it differs from the call
  before).

**Result:** 21 of the 32 human calls change, 11 are confirmed. No holds, no SUSPECT TVD. `depth_doubt.csv` carries no
marks, so those 19 wells stay as they are.

| Verdict | Cards | Effect |
|---|---|---|
| ACCEPT, the nearest bench today | 21 | the call moves |
| ACCEPT on cards 2 and 3 (proposed = the call) | 2 | confirmed |
| The existing call written in | 9 (cards 6, 7, 8, 17, 18, 20, 21, 22, 28) | confirmed |

## The 21 calls that change

| Card | Well | County | Was → now |
|---|---|---|---|
| 1 | COTTON DRAW UNIT #601H | Eddy | WCXY → **BS2_C** |
| 4 | ALKALINE EARTH I 8LL | Midland | WCB_1 → **LSSH** |
| 5 | JAVELINA UNIT #509H | Eddy | WCXY → **WCA_1** |
| 9 | PERMIT 76-44 LOV UNIT 1H | Loving | WCA_1 → **WCXY** |
| 10, 11 | SMALL EYED 54-1-36-25 UNIT 15H, 17H | Loving | BS3_S → **WCXY** |
| 12–14 | ST KITTS / ST. BRIDES / ST. CLOUD 76 TG | Loving | BS2_C → **BS1_S** |
| 15 | HALL 28 1H | Pecos | WCA_1 → **WCB_2** |
| 16 | SIBLEY 3-2 3WA | Pecos | WCB_2 → **WCA_1** |
| 19 | UTL 2635-17D 4H | Ward | WCB_2 → **WCB_1** |
| 23 | BENDER C 252 2LS | Martin | WCA_1 → **LSSH** |
| 24 | MATTINGLEY 14-26 UNIT 2 271 | Martin | WCB_1 → **WCB_2** |
| 25 | EVERGLADES 5C 303H | Midland | WCB_1 → **WCB_2** |
| 26 | TXL 11 UNIT 3 1412AH | Midland | WCA_1 → **LSSH** |
| 27 | HICKMAN O 2074SH | Reagan | WCA_1 → **WCB_1** |
| 29 | JRS FARMS 22-27-M 13H | Upton | WCB_2 → **WCB_1** |
| 30 | NEAL F UNIT 8 7H | Upton | WCB_1 → **WCB_2** |
| 31, 32 | PONDEROSA EAST A 7H, C 10H | Upton | WCB_2 → **WCB_1** |

**Two things to know about these:**
- **Card 1** now rests on Enverus's revised header TVD of 9,671 ft, with no Novi TVD and no survey behind it. If the
  header is revised again or a survey lands, this call is the first to re-check.
- **Cards 10–14 and 9** reverse bench codes that were written in on earlier cards (2026-11-06 to 2026-11-11) with the
  same depths shown. They are recorded as marked.

## What changed in the seed

- `seeds/formation_tag_overrides.csv` stays at 764 rows. All 32 reviewed wells now carry this review's row; 21 of them
  with a new code.
- 17 of the 32 held a row from before the tag rule (September consensus ratifications, October step 20a cards and
  class-accepted rows, one doublecheck). `scripts.tag_rule_seeds` now lets a review set (`REVIEW_SETS`) replace such a
  row; before, it stopped on any carded well that already had one. A hold in a review set leaves the earlier call alone.
- `tests/test_box_step20a.py`: the step 20a block is still pinned to the October screen, less the 11 wells this review
  re-judged.

## What loading the seed changes

Nothing is loaded. `apply_formation_tag_rule --seeds --dry-run` against live reports overrides add 22, change 32,
remove 0 (the 22 are the shadow-6 calls still waiting). On the refresh after a load, 41 live tags move: these 21 plus
20 of the 22 shadow-6 wells.
