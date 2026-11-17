# Retired sql/23 flips: scored (2026-11-17)

- **Reader:** the seed builder's verdict rule (`scripts.tag_rule_seeds.read`). Each card decides only its own well.
- **Output:** `cards_scored.csv` (`final`, `human_call`, `changed`) and `depth_exclusions.csv` (the 22 SUSPECT TVD wells
  with the depth judged). `not_carded.csv` carries no marks, so those 123 wells stay on their vendor tag.

| Verdict | Cards | What it becomes |
|---|---|---|
| ACCEPT | 39 | the sql/23 bench comes back as a human call |
| A bench code | 11 | a human call on that bench |
| REJECT, vendor tag is a bench | 14 | a human call pinning the vendor tag |
| REJECT, vendor tag is OTHER | 22 | no row: the well stays OTHER and unpinned |
| SUSPECT TVD | 22 | a depth exclusion; the tag stays on the vendor tag |

**Result:** 64 new human calls and 22 depth exclusions. 50 wells change tag when the seed is loaded (39 + 11); the other
58 keep the tag they have now.

## The 11 bench-code calls

| Card | Well | County | Vendor tag → sql/23 bench | Your call |
|---|---|---|---|---|
| 14, 15 | PISTOLERO 15 FEDERAL #402H, #502H | Lea | BS2_S → WCA_1 | **WCB_2** |
| 17–19 | SILVERTIP 76-16 UNIT Q 21H, 23H, 24H | Loving | BS2_S → WCA_2 | **WCB_2** |
| 27 | SKY DWELLER 14 STATE COM #201H | Lea | BS3_S → BS2_C | **BS3_C** |
| 40 | STATE AP #001 | Lea | OTHER → BS2_S | **BS3_C** |
| 51 | GEMINI 36 35 FEDERAL COM #513H | Eddy | OTHER → BS3_S | **BS2_S** |
| 60 | LITTLE BETTY 20 #702H | Eddy | OTHER → WCA_2 | **WCA_2** |
| 69 | CREEDENCE 21 16 W0OB FEDERAL COM #002H | Eddy | WCA_1 → WCC | **WCB_2** |
| 96 | SOCO 1907 B 401H | Ector | OTHER → LSSH | **WCA_1** |

## Two reading choices to confirm

- **REJECT on an OTHER well writes no row.** The reader used to turn every REJECT into a human call on the card's
  input. For an input of OTHER that would pin the well to OTHER, and a bench the vendors name later could never come
  through. `scripts.tag_rule_seeds.read` now treats it as "leave alone". The 14 REJECTs on a named bench still pin that
  bench, as on every earlier card set.
- **SUGG STRIP 6H (card 104, Irion) stops being a depth exclusion.** It was SUSPECT TVD on v5.2 card 123. Here it is
  marked REJECT, and the latest verdict wins, so it becomes a human call on WCB_1 and its exclusion row drops out. Its
  card still shows the well 2,122 ft from the WCB unit. **Confirmed by Michael 2026-11-17: the WCB_1 call stands.**

## Depth exclusions: 12 → 25

- 22 SUSPECT TVD verdicts here. 8 of them were already exclusions from the v5.2 cards and are re-confirmed; 14 are
  new.
- 1 drops out (SUGG STRIP 6H, above). 12 − 1 + 14 = 25.
- `scripts.tag_rule_seeds` now reads `depth_exclusions.csv` from every card set that has SUSPECT TVD verdicts
  (`EXCLUSION_SETS`), not only the v5.2 folder.
- A depth-excluded well is left out of the rule's judged frame and is never depth evidence for its neighbours.

## What loading the seed changes

Nothing is loaded. `apply_formation_tag_rule --seeds --dry-run` against live (2026-11-17, after nightly run 7) reports
overrides add 64, change 0, remove 0, and depth exclusions seed 25 against live 12. Policy and class seeds match live.
