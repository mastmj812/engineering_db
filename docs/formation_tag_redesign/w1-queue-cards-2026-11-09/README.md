# W1 card queue (live, 2026-11-09)

These are the 11 single-well cards from the W1 live run (`../w1-live-2026-11-09/REPORT.md`, section 5). Each card
decides only its own well. Read-only; nothing is applied.

- **Drawn with:** `python -m scripts.tag_v5_2_cards --cache <live cache> --listed listed.csv`, as strike-section cards.
- **The card's input:**
  - the tag the rule starts from;
  - for cards 10 and 11, the **vendor tag**, per the class-identity check.
- **The card's "today" field:** today's warehouse tag, which may be a sql/23 flip.

## The cards and the pre-check

| Card | Well | County | Depth | Input → proposed | Pre-check |
|---|---|---|---|---|---|
| 1 | MEZCAL 10 FEDERAL COM #124H | Eddy | 8,173 | BS2_S → BS2_C (Step 2) | agrees: BS2_C 8,161 (n = 3, thin) vs BS2_S 8,530 (n = 13) |
| 2 | PERMIT 76-44 LOV UNIT 4H | Loving | 11,791 | WCA_1 → WCXY (Step 2) | agrees: WCXY 11,928 (n = 19) vs WCA_1 12,082 (n = 7) |
| 3 | SMALL EYED 54-1-36-25 UNIT 15H | Loving | 11,840 | WCA_1 → WCXY (Step 2) | agrees: WCXY 11,832 (n = 33) vs WCA_1 12,043 (n = 20) |
| 4 | KUDU 53-2-6 LOV E UNIT 6H | Loving | 11,667 | WCA_1 → WCXY (Step 2) | **marginal:** WCXY 11,757 (n = 21) vs WCA_1 11,776 (n = 14); the two sit 19 ft apart here |
| 5 | JAMES RANCH UNIT DI 7 SAWTOOTH FEDERAL C #804H | Eddy | 10,636 | BS2_S → BS3_C (Step 3) | agrees: 602 ft off the BS2 unit, 96 ft from BS3_C |
| 6 | VACA 24 FEDERAL COM #507H | Lea | 11,799 | BS2_S → BS3_C (Step 3) | agrees: 834 ft off BS2, 210 ft from BS3_C |
| 7 | JAMES 29 32 FEDERAL COM #024H | Lea | 11,349 | BS2_S → BS3_C (Step 3) | agrees: 741 ft off BS2, 130 ft from BS3_C |
| 8 | STARLIGHT 56-1-36-25 F 15H | Loving | 10,937 | OTHER → WCA_1 (Step 3) | agrees: WCA_1 66 ft |
| 9 | TETON 56-2-35-23 G 14H | Reeves | 10,499 | OTHER → WCXY (Step 3) | agrees: WCXY 126 ft |
| 10 | FRODERICK 33 FEDERAL COM #501H | Lea | 12,852 | BS1_S → WCB_1 (class identity) | agrees: BS1 unit 2,946 ft off, WCB_1 18 ft |
| 11 | GARDNER UNIT 15-10 3MH | Howard | 8,165 | MS → WCB_1 (class identity) | agrees: MS unit 1,286 ft off, WCB_1 30 ft |

**How the pre-check was read:**
- **Cards 1–4** were checked against plain medians of each sub-bench's witnesses within 2 mi. The card script's own
  check is unit-level, so it can't judge a sub-bench, and its "DISAGREES" on these four cards is meaningless.
- **Cards 5–11** use the card script's check: plain unit medians.

**Cards 5–7 are group-12 wells.** Group 12's pattern (Novi THIRD BONE SPRING LIME vs Enverus 2ND BONE SPRING SAND, so
Enverus wins) put them on BS2_S, and Step 3's depth check sends them back to Novi's BS3_C. It is the same concern as
the Lea rejects on the group-12 cards. ACCEPT means BS3_C; REJECT keeps BS2_S.

## Marking

Mark the verdict column in `cards_sample.csv`:
- **ACCEPT** takes the proposed code.
- **REJECT** keeps the input code.
- **A bench code** is your call on the well (cards 8 and 9 may want the other WCA sub-bench).
- **SUSPECT TVD** makes the well a depth exclusion.
- Anything else is a hold.
