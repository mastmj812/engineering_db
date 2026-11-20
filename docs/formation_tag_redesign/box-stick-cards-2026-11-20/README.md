# Human calls from the BOX stick and tag cards, 2026-11-20

18 producing Delaware wells whose formation tag Michael corrected while reviewing two card sets of the BOX sticks work:

- the off-depth pinned stick cards (`docs/box_sticks/pinned-depth-2026-11-20/cards`): wells he marked "tag wrong" on the
  sticks he kept, with the bench he then named;
- the Bone Spring tag cards (`docs/box_sticks/pinned-depth-2026-11-20/tag_cards`): producing wells he agreed or re-coded.

`cards_sample.csv` is in the format `scripts.tag_rule_seeds` reads (a direct-call set, Step 3). The `section` column names
the source card. Every verdict is a bench code, so every row becomes a human-call row in
`seeds/formation_tag_overrides.csv`.

| Change | Wells |
|---|---|
| BS3_C to BS2_S | 6 |
| BS3_S to BS3_C | 5 |
| BS3_S to WCA_1 / WCA_2 / WCXY | 3 |
| BS1_S to AVA_1; BS2_S to BS2_C; WCA_2 to WCB_2 | 1 each |
| BS2_S kept (pinned as a human call) | 1 (Eider 35 Federal Com #502H) |

Two notes:

- **Kudu 53-2-6 Lov E Unit 4H** (4230134220) was carded on 2026-11-06, when Michael kept BS3_S against a proposed WCA_1.
  His call here, WCXY, is later and replaces it.
- **Vintage F 313H** (4238941928) is NOT in this set. On its stick card Michael wrote that the tag should be WCB_1, but
  the well carries an older override to WCB_2 that he ratified on 2026-09-17 (WCB_1 to WCB_2 class review). Reversing a
  ratified call is his to confirm; until he does, the earlier call stands.

Nothing here is applied. The seeds reach the warehouse only through `python -m scripts.apply_formation_tag_rule --seeds`,
on an explicit go; the nightly then applies them.
