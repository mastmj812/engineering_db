# Human-call review (2026-11-16)

Michael's question: were the human calls made on data that has since changed (TVD or otherwise)? This folder screens
all 764 calls in `seeds/formation_tag_overrides.csv` against today's warehouse and cards the 32 that need a second look.
Read-only; nothing is applied and no seed is changed.

- **Why it matters:** a human call wins in sql/16 whatever the data does afterwards, and the nightly never re-judges it.
- **Made with:** `python -m scripts.tag_human_call_review --cache <live cache> --out <this folder>`, then
  `python -m scripts.tag_v5_2_cards --cache <live cache> --listed listed.csv`. The cache is today's pull
  (`box.tag_rule_inputs`, the same one behind `../shadow6-queue-cards-2026-11-16`).
- **Files:** `screen.csv` (every call), `cards.html` + `cards_sample.csv` (the 32 cards), `depth_doubt.csv` (19 wells,
  below).

## What the screen found

**1. Depth then against depth now.** Only the card sets from 2026-11-06 on printed the depth they judged, so this
covers 325 of the 764 calls. The 428 older calls in the frame recorded no depth and cannot be compared this way.

| Of the 325 | Wells |
|---|---|
| Depth unchanged | 267 |
| Moved less than 100 ft | 54 |
| Moved 100 ft or more | 4 (cards 1–4) |
| A survey has arrived since (card used the header TVD) | 12, largest shift 195 ft |

Two of the four big moves break the call:
- **COTTON DRAW UNIT #601H (Eddy):** carded WCXY at 12,290 ft. Enverus revised the header TVD to 9,671 ft
  (row updated 2026-11-11); Novi has no TVD and there is no survey. At 9,671 ft the well is 2,209 ft above WCXY and
  28 ft from BS2_C. Which header value is right is not established.
- **ALKALINE EARTH I 8LL (Midland):** carded WCB_1 at a survey depth of 8,956 ft. The survey depth is now 8,356 ft,
  which is 605 ft above WCB_1 and 156 ft from LSSH. Both vendors name the Lower Spraberry.

**2. Today's benches at each well.** The rule's witness depth for every bench within 2 mi, the well left out.

| Today | Calls |
|---|---|
| Holds (called bench is nearest, or under 100 ft behind the nearest) | 600 |
| Another bench is 100 ft or more nearer | 30 (cards 1, 4–32) |
| Called bench has no witnesses nearby, so no test | 94 |
| No witnesses of any bench nearby | 29 |
| Not in the judged frame | 11 |

Of the 30, 13 are calls carded since 2026-11-06 and 17 are older (consensus ratifications, step 20a class-accepted
rows and October cards). A call that sits off the witness depths is not wrong by itself: several were made knowing
that. The cards are there so each can be confirmed or changed on today's picture.

**3. How well the depth is supported.** 630 calls rest on a survey depth and 123 on a header TVD only.
- On 36 of the 123, Enverus is the only source of the TVD (the Wild Weasel and Cotton Draw #601H situation). 32 of
  those hold today, 3 have no witnesses for the called bench, 1 is Cotton Draw #601H.
- On 19 of the 123, Novi and Enverus header TVDs differ by 300 ft or more (`depth_doubt.csv`). The warehouse uses
  Novi's. Three of them sit far from their own bench: MARQUARDT FEDERAL #016H (818 ft), ROCKER B ZACHRY R 18H
  (714 ft) and COACHWHIP 17-20 261 (408 ft). No card is drawn for these because there is no nearer bench to propose;
  mark the `verdict` column there if any should become a depth exclusion.

**Not checked:** vendor strings then against now. The nightly already reports human calls whose inputs moved
overnight (8 so far in the shadow period).

## The cards

Each card is a strike section drawn on today's data. **Input** is the human call; **proposed** is today's nearest
bench (on cards 2 and 3 the call is still the nearest bench, so the two are the same).

| Card | Well | County | Call → nearest today | Depth (ft) | Call off / nearest off (ft) | Call made |
|---|---|---|---|---|---|---|
| 1 | COTTON DRAW UNIT #601H | Eddy | WCXY → BS2_C | 9,671 header (was 12,290) | 2,209 / 28 | v5.2 card 107 |
| 2 | IRONHOUSE 19 STATE COM #003H | Lea | BS3_C holds | 9,579 survey (was 9,384 header) | 134 / 134 | policy-v1 round 2 card 27 |
| 3 | VAST STATE #005H | Lea | AVA_0 holds | 9,260 survey (was 9,155 header) | 47 / 47 | v5 card 43 |
| 4 | ALKALINE EARTH I 8LL | Midland | WCB_1 → LSSH | 8,356 survey (was 8,956) | 605 / 156 | v5.2 card 74 |
| 5 | JAVELINA UNIT #509H | Eddy | WCXY → WCA_1 | 11,820 | 248 / 56 | policy-v1 round 2 card 30 |
| 6–8 | DAUNTLESS 7 FEDERAL #721H, #723H, #728H | Lea | WCB_1 → WCA_2 | 12,628–12,646 | 227–277 / 114–152 | consensus, 2026-09-16 |
| 9 | PERMIT 76-44 LOV UNIT 1H | Loving | WCA_1 → WCXY | 11,819 | 251 / 60 | policy-v1 step 1 card 17 |
| 10 | SMALL EYED 54-1-36-25 UNIT 15H | Loving | BS3_S → WCXY | 11,840 header | 258 / 7 | W1 queue card 3 |
| 11 | SMALL EYED 54-1-36-25 UNIT 17H | Loving | BS3_S → WCXY | 11,787 | 206 / 77 | direct call, 2026-11-11 |
| 12–14 | ST KITTS / ST. BRIDES / ST. CLOUD 76 TG | Loving | BS2_C → BS1_S | 9,993–10,182 | 193–233 / 12–83 | v5 card 55, policy-v1 round 2 cards 38, 37 |
| 15 | HALL 28 1H | Pecos | WCA_1 → WCB_2 | 10,648 | 191 / 30 | consensus, 2026-09-16 |
| 16 | SIBLEY 3-2 3WA | Pecos | WCB_2 → WCA_1 | 10,456 | 310 / 58 (n = 3) | consensus, 2026-09-16 |
| 17 | BLAZER UNIT 14 3WA | Reeves | WCA_1 → BS3_S | 10,932 | 155 / 43 (n = 3) | policy-v1 step 1 card 10 |
| 18 | CONDIMENT KING 6920A-34 7H | Ward | WCA_2 → WCB_2 | 11,256 | 156 / 8 (n = 3) | v5 card 50 |
| 19 | UTL 2635-17D 4H | Ward | WCB_2 → WCB_1 | 11,714 | 149 / 46 | consensus, 2026-09-17 |
| 20 | UL 20 S CHATTER C 2703H | Winkler | WCB_1 → WCA_2 | 11,962 | 238 / 87 | v5 round 2 card 65 |
| 21 | FREDERICK LINDSEY E 5H | Howard | WCB_2 → WCB_1 | 8,439 | 225 / 36 (n = 3) | Michael's doublecheck, 2026-10-30 |
| 22 | BENNIE 4342 4H | Irion | WCB_1 → WCA_1 | 6,582 | 169 / 51 (n = 3) | v5 round 2 card 71 |
| 23 | BENDER C 252 2LS | Martin | WCA_1 → LSSH | 9,130 | 237 / 106 | class-accepted, 2026-10-28 |
| 24 | MATTINGLEY 14-26 UNIT 2 271 | Martin | WCB_1 → WCB_2 | 9,706 | 136 / 26 | class-accepted, 2026-10-28 |
| 25 | EVERGLADES 5C 303H | Midland | WCB_1 → WCB_2 | 9,913 | 137 / 1 (n = 3) | class-accepted, 2026-10-28 |
| 26 | TXL 11 UNIT 3 1412AH | Midland | WCA_1 → LSSH | 8,794 | 567 / 78 | what-if card, 2026-10-27 |
| 27 | HICKMAN O 2074SH | Reagan | WCA_1 → WCB_1 | 7,178 | 120 / 18 | what-if card, 2026-10-27 |
| 28 | UNIVERSITY 9-31 1H | Reagan | WCB_1 → WCB_2 | 8,298 header | 141 / 4 | class-accepted, 2026-10-28 |
| 29 | JRS FARMS 22-27-M 13H | Upton | WCB_2 → WCB_1 | 9,584 | 123 / 20 | round 1 card, 2026-10-27 |
| 30 | NEAL F UNIT 8 7H | Upton | WCB_1 → WCB_2 | 9,163 | 349 / 1 | class-accepted, 2026-10-28 |
| 31 | PONDEROSA EAST A 7H | Upton | WCB_2 → WCB_1 | 8,594 | 335 / 34 | round 2 card, 2026-10-28 |
| 32 | PONDEROSA EAST C 10H | Upton | WCB_2 → WCB_1 | 8,632 | 298 / 100 | round 2 card, 2026-10-28 |

On cards 10, 12, 17, 18, 20 and 22 the earlier verdict was a bench code written in against that card's proposal, and
the depth has not moved since. Those were deliberate calls, shown again only because today's witness depths still sit
nearer another bench.

## Marking

Mark the verdict column in `cards_sample.csv`:
- **REJECT** keeps the human call as it stands.
- **ACCEPT** takes the proposed code (today's nearest bench). On cards 2 and 3 that is the call itself.
- **A bench code** is a new call on the well.
- **SUSPECT TVD** makes the well a depth exclusion.
- Anything else is a hold; the call stays.

Changed verdicts become seed rows through a seed PR plus `apply_formation_tag_rule --seeds`, on an explicit go.
