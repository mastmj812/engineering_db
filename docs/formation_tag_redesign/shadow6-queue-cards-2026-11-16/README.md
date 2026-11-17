# Shadow run 6 card queue (live, 2026-11-16)

These are the 22 wells in the card queue of the sixth nightly shadow run. The run was `meta.formation_tag_run` run 6:
nightly 43853826074, rule sha `245a286`, policy v1 (digest `9687263e313c`).

- **What is queued:** 22 Step 3 depth-check moves that fall outside an accepted Step 3 class. No Step 2 changes.
- **When they arrived:** 21 at run 3 (2026-11-13, the night 261 wells' inputs moved) and one at run 6
  (WILD WEASEL 22 FEDERAL COM #753H, card 1).
- Each card decides only its own well. Read-only; nothing is applied.
- **Step 1:** its 166 undecided wells sit in classes of fewer than 20 wells, so none of them gets a class card.

## How the cards were made

- **Drawn with:** `python -m scripts.tag_v5_2_cards --cache <live cache> --listed listed.csv`, as strike-section
  cards. Same method as `../shadow1-queue-cards-2026-11-11`.
- **The live cache:** pulled today with `box.tag_rule_inputs`. It matches `curated.wells` on all 60,889 wells. Steps
  1–3 then ran on it with the W1 chain.
- **Proposals:** `listed.csv` comes straight from run 6's own queue (`meta.formation_tag_run.summary`), not from
  the dev chain.
  - **Input** is the tag the step started from: the gated Step 1 tag, here the vendor tag on all 22.
  - **Proposed** is the Step 3 code.
- **Cross-check against the dev chain:** the input matches on 22 of 22 wells and the Step 3 code on 22 of 22.
- **No planned surveys:** none of the 22 is a planned-survey well.
- **`also_show`:** card 1 draws WCXY, card 2 draws WCB_2, card 6 asks for AVA_2 (no AVA_2 wells are near enough to
  draw).

## Novi now calls 17 of these wells PENNSYLVANIAN

- On 17 of the 22 cards the Novi string is PENNSYLVANIAN, which the crosswalk maps to OTHER. Enverus names an
  Avalon, Bone Spring or Wolfcamp interval on all 17. That is why the input is OTHER.
- Across the judged frame, 80 Delaware wells carry Novi PENNSYLVANIAN today (32 Lea, 32 Eddy, 9 Reeves, 4 Ward, 3
  elsewhere), and every one has the vendor tag OTHER. 36 of the Lea and Eddy wells first produced in 2020 or later.
- **Not established:** when Novi began sending this string. The queue timing points at the 2026-11-13 load, but the
  rule table keeps no history, so that is an inference.
- The 22 queued wells are only the ones where depth evidence places the well. The other PENNSYLVANIAN wells stay OTHER
  with no proposal.

## The cards and the pre-check

The card script's own check repeats the move's test on plain medians of evidence witnesses within 2 mi, with the
well left out. It marks every move from OTHER as having no input unit.

| Card | Well | County | Depth (ft) | Input → proposed | Pre-check |
|---|---|---|---|---|---|
| 1 | WILD WEASEL 22 FEDERAL COM #753H | Lea | 12,377 (tvd_ft) | AVA_0 → BS3_S | **agrees, but thin:** the Avalon unit is 2,096 ft off. BS3_S 12,452 has only 3 witnesses; WCXY 12,642 has 12 on the section, 265 ft below the well. Novi says WOLFCAMP (generic). New well, first production 2026-09, no survey depth yet. Choices: BS3_S / WCXY. |
| 2 | RATTLESNAKE 28 FEDERAL COM #203H | Lea | 13,063 | AVA_1 → WCB_1 | **out of the Avalon for certain (3,154 ft off); looks like WCB_2, not WCB_1:** on the section WCB_1 is at 12,856 (n = 7) and WCB_2 at 13,084 (n = 4). The well is 207 ft below WCB_1 and 21 ft above WCB_2. Novi says WOLFCAMP B. |
| 3 | RATTLESNAKE 28 FEDERAL COM #204H | Lea | 12,912 | AVA_1 → WCB_1 | agrees: Avalon unit 3,004 ft off; WCB_1 188 ft, lead 322 ft. Same pad as card 2. |
| 4 | RATTLESNAKE 28 FEDERAL COM #304H | Lea | 12,883 | AVA_2 → WCB_1 | agrees: Avalon unit 2,974 ft off; WCB_1 159 ft, lead 322 ft. Same pad as card 2. |
| 5 | STONEWALL 28 FEDERAL COM #508H | Lea | 9,409 | BS2_S → AVA_0 | agrees: BS2 unit 1,111 ft off; AVA_0 27 ft, lead 657 ft. sql/23 has it on AVA_0 today. |
| 6 | DOUBLE STAMP FEDERAL COM #113H | Lea | 8,814 (survey; tvd_ft 8,885) | OTHER → BS1_S | **thin, and the check disagrees:** BS1_S is the only code with witnesses (8,920 by the rule's estimator, plain median 8,993, n = 5), 179 ft off on the plain median. Enverus says LOWER AVALON; there are no AVA_2 witnesses within range to test it. Choices: BS1_S / AVA_2. |
| 7 | POKER LAKE UNIT 15 TWIN WELLS RANCH #305H | Eddy | 10,490 | OTHER → BS2_S | agrees: BS2_S 96 ft, lead 344 ft. sql/23 has it on BS2_S today. |
| 8 | LITTLE GIANTS 20 19 B3AD FEDERAL COM #001H | Eddy | 7,903 | OTHER → BS2_S | agrees: BS2_S 17 ft, lead 1,496 ft. Enverus says 3RD BONE SPRING SAND, and the well name says B3: depth beats both. |
| 9 | BONDI 24 FEDERAL COM #134H | Eddy | 7,682 | OTHER → BS2_S | agrees: BS2_S 46 ft, lead 1,082 ft. Enverus says 3RD BONE SPRING SAND. |
| 10 | BENT TREE 9 11 STATE COM #224H | Eddy | 7,466 (survey; tvd_ft 7,618) | OTHER → BS2_S | agrees: BS2_S 90 ft, lead 842 ft. |
| 11 | STACK CATS 25 36 FEDERAL COM #022H | Lea | 10,891 | OTHER → BS2_S | agrees: BS2_S 113 ft, lead 308 ft. |
| 12 | DL 15 22 FEDERAL COM #419H | Lea | 10,818 | OTHER → BS2_S | agrees: BS2_S 59 ft, lead 1,331 ft. |
| 13 | MR POTATO HEAD 11 14 FEDERAL COM #235H | Eddy | 9,672 | OTHER → BS3_C | agrees: BS3_C 90 ft, lead 591 ft. Enverus says 3RD BONE SPRING (no sand or carbonate). |
| 14 | BONANZA 22 15 W0FC FEDERAL COM #001H | Eddy | 9,525 | OTHER → WCA_1 | agrees: WCA_1 102 ft, lead 749 ft. |
| 15 | DELAWARE RANCH 11 14 W1BO FEDERAL COM #002H | Eddy | 9,615 | OTHER → WCA_1 | agrees: WCA_1 5 ft, lead 1,420 ft. |
| 16 | JAMESON 13 24 FEDERAL COM #437H | Eddy | 9,190 | OTHER → WCA_1 | agrees: WCA_1 80 ft, lead 854 ft. |
| 17 | FULLER 13 12 W1GB FEDERAL COM #001H | Eddy | 10,647 | OTHER → WCA_2 | agrees: WCA_2 14 ft, lead 1,043 ft. |
| 18 | DELAWARE RANCH 11 14 W1BO FEDERAL COM #001H | Eddy | 9,766 | OTHER → WCA_2 | agrees: WCA_2 114 ft, lead 1,488 ft. Same pad as card 15, 151 ft deeper. |
| 19 | POKER LAKE UNIT 19 DTD #309H | Eddy | 10,572 | OTHER → WCXY | agrees: WCXY 56 ft, lead 642 ft. |
| 20 | COLGROVE 35 FEDERAL COM #705H | Lea | 12,501 | OTHER → WCXY | agrees: WCXY 31 ft, lead 454 ft. |
| 21 | COLGROVE 35 FEDERAL COM #707H | Lea | 12,511 (tvd_ft) | OTHER → WCXY | agrees: WCXY 80 ft, lead 406 ft. |
| 22 | BARBA-NEAL 2105H | Glasscock | 9,300 | OTHER → WCD | agrees: WCD 10 ft; no other unit has witnesses. Same Apache cluster as shadow-1 cards 8–25. |

**About cards 7–21:** on every one the proposed code is the bench Enverus already names, except cards 8, 9 and 13.
Cards 8 and 9 land one unit above Enverus's 3RD BONE SPRING SAND, and card 13 resolves Enverus's unsplit 3RD BONE
SPRING to the carbonate.

## Marking

Mark the verdict column in `cards_sample.csv`:
- **ACCEPT** takes the proposed code.
- **REJECT** keeps the input code.
- **A bench code** is your call on the well. Card 1 may want WCXY, card 2 WCB_2, and card 6 AVA_2.
- **SUSPECT TVD** makes the well a depth exclusion.
- Anything else is a hold.

Verdicts become seed rows: human calls go in `seeds/formation_tag_overrides.csv`, and SUSPECT TVD rows in the
depth-exclusions seed. They land through a seed PR plus `apply_formation_tag_rule --seeds`, on an explicit go. Run 6
is not edited.
