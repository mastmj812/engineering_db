# Shadow run 1 card queue (live, 2026-11-11)

These are the 25 wells the first nightly shadow run queued for cards. The run was `meta.formation_tag_run` run 1:
nightly 43008285330, rule sha `84e78ba`, policy v1 (digest `2bb641aa6f17`).

- **What is queued:**
  - 2 Step 2 sub-bench changes;
  - 23 Step 3 depth-check moves that fall outside an accepted Step 3 class.
- Each card decides only its own well. Read-only; nothing is applied.
- **Step 1:** its 157 undecided wells sit in classes of fewer than 20 wells, so none of them gets a class card.

## How the cards were made

- **Drawn with:** `python -m scripts.tag_v5_2_cards --cache <live cache> --listed listed.csv`, as strike-section
  cards.
- **The live cache:** pulled today with `box.tag_rule_inputs`. It matches `curated.wells` on all 60,845 wells. Steps
  1–3 then ran on it with the W1 chain (915 s).
- **Proposals:** `listed.csv` comes straight from run 1's own queue (`meta.formation_tag_run.summary`), not from
  the dev chain.
  - **Input** is the tag the step started from: the gated Step 1 tag. That is the vendor tag unless an accepted
    Step 1 class moved the well.
  - **Proposed** is the Step 2 sub-bench code or the Step 3 code.
- **Cross-check against the dev chain:**
  - The input matches on 25 of 25 wells, and the Step 3 code on 23 of 23.
  - The one difference is card 1's sub-bench: the nightly says BS3_C, while the dev chain puts the well in BS2_S.
    The witness depths below explain why.
- **The card's "today" field:** today's warehouse tag, which may be a sql/23 correction.
- **`also_show`** (a new optional `listed.csv` column) draws extra benches on the strike section. A card normally
  draws only the subject's tag, the proposal and the bands directly above and below; BS2_S (card 1) and WCA_1
  (card 3) were hidden.

## The cards and the pre-check

The card script's own check is unit-level. It can't judge a sub-bench (cards 1–2), and it marks every move from
OTHER as having no input unit. For the cards it disputes, the table also gives plain medians of evidence witnesses
within 2 mi (3 mi if fewer than 3), with the well left out. Witnesses are grouped by their accepted tag.

| Card | Well | County | Depth (ft) | Input → proposed | Pre-check |
|---|---|---|---|---|---|
| 1 | WOOL HEAD 20 STATE COM #554H | Lea | 11,108 | BS3_S → BS3_C (Step 2) | **looks like BS2_S, not either BS3:** BS2_S 10,952 (n = 28), BS3_C 11,322 (n = 4), BS3_S 11,778 (n = 23). BS3_C beats BS3_S by about 450 ft, but the section puts the well inside the BS2_S cloud (BS2_S drawn via `also_show`). sql/23 has it on BS2_S today. Vendor: Novi BONE SPRING (generic), Enverus 3RD BONE SPRING. |
| 2 | ST BRIDES 76 3031 111H | Loving | 11,842 | WCA_1 → WCXY (Step 2) | agrees: WCXY 11,848 (n = 37) vs WCA_1 12,076 (n = 14). It is the same Loving WCA_1 → WCXY pattern as W1 cards 2–4. |
| 3 | BONDI 24 FEDERAL COM #122H | Eddy | 9,097 (survey; tvd_ft 9,221) | BS2_S → WCA_2 (Step 3) | **out of BS2 for certain (1,468 ft off); where it lands is open:** the section has BS3_S about 290 ft above (8,809, n = 10) and WCA_2 about 190 ft below (9,291, n = 3). WCA_1 has only a few witnesses (8,972 by accepted tag, n = 9). Novi's WOLFCAMP A (XY) would sit in that gap, but there are no WCXY witnesses within 3 mi. Choices: WCXY / WCA_1 / WCA_2. sql/23 has it on WCA_2 today. |
| 4 | SILVERTIP 76-16 UNIT Q 25H | Loving | 12,447 (tvd_ft) | BS2_S → WCA_2 (Step 3) | agrees: BS2 unit 1,690 ft off; WCA_2 104 ft, lead 448 ft. First production 2026-06, so this is a new well. |
| 5 | SHERMAN 6-9 UNIT 1WA | Pecos | 9,313 | OTHER → WCA_1 (Step 3) | **thin but consistent:** WCA_1 is the only code with witnesses. On the section, its 3 wells sit at about 9,340–9,375 ft, right at the well (the rule's estimator gives 9,341). The 2-mi plain median, 8,944 (n = 3), comes from different wells. Novi says WOLFCAMP A; Enverus says VAL VERDE ALL, which places it on the Val Verde fringe. |
| 6 | PEELER D 16MA | Martin | 8,813 | MS → LSSH (Step 3) | agrees: MS unit 725 ft off; LSSH 56 ft. |
| 7 | CHARGER H150 MIPA UNIT H150LS | Midland | 8,242 | LSSH → MS (Step 3) | agrees: LSSH unit 799 ft off; MS 103 ft. The well name says LS: depth beats the landing suffix. |
| 8–25 | 18 Apache wells (HUITT, SCHWARTZ, HAMMERHEAD, BALLENGER, SQUIRE, LYNDA-NEAL, BARBA-NEAL) | Glasscock | 9,268–9,516 | OTHER → WCD (Step 3) | all agree: WCD unit 16–103 ft. |

**About cards 8–25:**
- They are one cluster: Apache, first production 2013–15.
- Novi names them CLINE, PENNSYLVANIAN or ATOKA, so they map to OTHER. Enverus has WOLFCAMP D on 13 of them,
  WOLFCAMP C AND ABOVE on 3 and nothing on 2.
- With 18 wells, they are two short of a class card. Each card still decides only its own well, but if one answer fits
  all 18, you can mark them all the same way.

## Marking

Mark the verdict column in `cards_sample.csv`:
- **ACCEPT** takes the proposed code.
- **REJECT** keeps the input code.
- **A bench code** is your call on the well. Card 1 may want BS2_S, and card 3 WCXY or WCA_1.
- **SUSPECT TVD** makes the well a depth exclusion.
- Anything else is a hold.

Verdicts become seed rows: human calls go in `seeds/formation_tag_overrides.csv`, and SUSPECT TVD rows in the
depth-exclusions seed. They land through a seed PR plus `apply_formation_tag_rule --seeds`, on an explicit go. Run 1
is not edited.
