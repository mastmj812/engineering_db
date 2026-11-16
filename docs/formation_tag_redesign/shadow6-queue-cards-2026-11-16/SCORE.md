# Shadow run 6 card queue: scored (2026-11-16)

- **Reader:** the Step 3 verdict reader (`scripts.tag_v5_2_score.read_verdict`). Each card decides only its own well.
- **Output:** `cards_scored.csv`.

**Result:** all 22 cards are marked ACCEPT, so every well takes its proposed code. All 22 become human calls in the
overrides seed (`scripts.tag_rule_seeds`, card set `shadow6-queue-cards-2026-11-16`); the seed goes from 742 to 764
rows, with no changed or removed rows. They load only through `apply_formation_tag_rule --seeds`, on an explicit go.

| Card | Well | Input → proposed | Verdict | Final |
|---|---|---|---|---|
| 1 | WILD WEASEL 22 FEDERAL COM #753H (Lea) | AVA_0 → BS3_S | ACCEPT | **BS3_S** |
| 2 | RATTLESNAKE 28 FEDERAL COM #203H (Lea) | AVA_1 → WCB_1 | ACCEPT | **WCB_1** |
| 3 | RATTLESNAKE 28 FEDERAL COM #204H (Lea) | AVA_1 → WCB_1 | ACCEPT | **WCB_1** |
| 4 | RATTLESNAKE 28 FEDERAL COM #304H (Lea) | AVA_2 → WCB_1 | ACCEPT | **WCB_1** |
| 5 | STONEWALL 28 FEDERAL COM #508H (Lea) | BS2_S → AVA_0 | ACCEPT | **AVA_0** |
| 6 | DOUBLE STAMP FEDERAL COM #113H (Lea) | OTHER → BS1_S | ACCEPT | **BS1_S** |
| 7–12 | 6 wells (4 Eddy, 2 Lea) | OTHER → BS2_S | ACCEPT | **BS2_S** |
| 13 | MR POTATO HEAD 11 14 FEDERAL COM #235H (Eddy) | OTHER → BS3_C | ACCEPT | **BS3_C** |
| 14–16 | 3 wells (Eddy) | OTHER → WCA_1 | ACCEPT | **WCA_1** |
| 17–18 | 2 wells (Eddy) | OTHER → WCA_2 | ACCEPT | **WCA_2** |
| 19–21 | 3 wells (1 Eddy, 2 Lea) | OTHER → WCXY | ACCEPT | **WCXY** |
| 22 | BARBA-NEAL 2105H (Glasscock) | OTHER → WCD | ACCEPT | **WCD** |

**The three cards the README flagged were accepted as proposed:**
- **Card 1:** BS3_S, not the WCXY alternative. Michael checked the well in anduin first, which still showed
  Enverus's earlier 9,500 ft; Enverus revised it to 12,377 ft in the 2026-11-16 load and anduin had last synced
  before that. The card's 12,377 ft is the current warehouse value, with no survey behind it yet.
- **Card 2:** WCB_1, not WCB_2. The well sits 21 ft above the WCB_2 band (13,084 ft, n = 4) and 207 ft below WCB_1
  (12,856 ft, n = 7) on the section. Recorded as marked.
- **Card 6:** BS1_S, not Enverus's LOWER AVALON.

**What loading the seed changes:** a human call wins in sql/16 whatever the switch says, so these tags move on the
next refresh after the seed is loaded. 20 of the 22 wells change tag; cards 5 and 7 already carry their final code
today through sql/23.
