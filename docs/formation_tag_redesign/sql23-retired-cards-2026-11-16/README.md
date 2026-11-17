# Retired sql/23 flips: review cards (2026-11-16, after cutover)

The tag-rule cutover ran on 2026-11-16 (switch ON 19:58 UTC). sql/23, the old depth correction, is now a pass-through,
so every well it had moved went back to its vendor tag unless the rule or a human call places it. 231 wells changed
tag that way. This folder cards the ones a section can be drawn for. Read-only; nothing is applied.

| Group | Wells | Here |
|---|---|---|
| In the rule's judged frame, with depth evidence | 108 | `cards.html`, `cards_sample.csv` |
| Outside the frame, not a planned survey | 74 | `not_carded.csv` |
| Planned-survey wells | 49 | `not_carded.csv`, listed only (never judged in tag QC) |

## How the cards were made

- **Which wells:** a per-well snapshot of `curated.wells_enriched` taken just before the cutover, compared with the
  tags after it. A well is here if its tag moved and it is not one of the 1,003 rule rows.
- **Cache:** pulled after the cutover with `box.tag_rule_inputs`, Steps 1–3 run on it with the W1 chain. Every card's
  input matches the live tag (108 of 108). None of the 108 is a planned survey or a human call.
- **Drawn with:** `python -m scripts.tag_v5_2_cards --cache <cache> --listed listed.csv`, as strike-section cards.
- **Input** is the vendor tag the well carries now. **Proposed** is the bench sql/23 had it on until the cutover.

## Why the rule left them on the vendor tag

sql/23 moved a well when its depth was more than 600 ft from a band built from the neighbours' own tags. The rule
makes the same test against witness depths (wells where both vendors agree), and is stricter about placing a well.

| Rule's reading | Cards | What it means | Card's plain-median check on the sql/23 code |
|---|---|---|---|
| No depth control | 36 | no witnesses for the vendor tag's unit near the well, so no miss can be called | 18 agree, 3 disagree, 15 no read |
| OTHER, kept | 32 | vendor tag is OTHER or unmapped and no bench is within 150 ft with a 100 ft lead | 4 disagree, 28 no read |
| Gross miss, unplaced | 19 | more than 600 ft off its unit, but no bench within 300 ft with a 100 ft lead | 1 agrees, 16 disagree, 2 no read |
| Within 600 ft | 18 | the vendor tag's unit is within 600 ft on witness depths | 1 agrees, 10 disagree, 7 no read |
| Inverted | 2 | the local bench depths are out of order | 1 agrees, 1 disagrees |
| Now a move | 1 | card 102, BUTTER CRUNCH J 4WB: on today's data the rule proposes LSSH, as sql/23 did | agrees |

"No read" means there are no witnesses of the sql/23 bench within 2 mi, so the card can only show the well against
its neighbours' tags. Overall the plain check agrees on 22 cards, disagrees on 34 and has no read on 52. A
disagreement is the expected case here: these are the wells the rule would not move.

87 cards are Delaware and 21 Midland. The largest groups by move are OTHER → BS3_S (10), OTHER → BS2_S (6),
BS3_S → BS2_S (5), OTHER → BS3_C (4), BS3_S → BS2_C (4) and BS2_S → WCA_2 (4), reading vendor tag → sql/23 bench.

Card 1 (ZEUS STATE #173H, Lea) is worth a look for its depth, not its bench: the card puts it 4,779 ft from both the
vendor tag's unit and the sql/23 bench.

## The 74 wells that cannot be carded

They are outside the rule's frame, so the cache holds no evidence depth or section for them.

- 44 are horizontals and 30 are verticals. 42 first produced before 2010. 12 have a lateral under 1,000 ft or none.
- 41 Delaware, 33 Midland. 35 are active, 20 plugged, 17 inactive.
- Largest moves, sql/23 bench → tag now: BS1_S → BS2_S (12), MS → OTHER (10), WCC → BS3_S (4), WCB_1 → BS3_S (4).

`not_carded.csv` lists each with its header TVD, status and both tags, and has a `verdict` column. Why each one is
outside the frame was not traced well by well.

## Marking

Mark the verdict column in `cards_sample.csv` (and in `not_carded.csv` for any well you want to call from the table):
- **ACCEPT** takes the proposed code: the sql/23 bench comes back as a human call.
- **REJECT** leaves the well on its vendor tag.
- **A bench code** is your call on the well.
- **SUSPECT TVD** makes the well a depth exclusion.
- Anything else is a hold; the well stays where the cutover put it.

Verdicts become seed rows through a seed PR plus `apply_formation_tag_rule --seeds`, on an explicit go.

## Also in this PR

`box.tag_rule_inputs` run by hand asserted that the tag before sql/23 equals the vendor tag on every well. With the
switch on that differs on exactly the rule rows, so the command exited 1 after the cutover. The check now counts rule
rows apart (`rule_rows`: 1,003 live, 0 other differences). The nightly never ran this check.
