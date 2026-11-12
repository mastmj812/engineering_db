# BOX sticks: WCXY by landing tiers (2026-11-12) - NEGATIVE RESULT

Read-only, live tags. `python -m scripts.box_sticks_wcxy_tiers --out docs/box_sticks/wcxy-tiers-2026-11-12
--verdicts docs/box_sticks/wcxy-cards-2026-11-12`.

## What was tried

Michael marked 31 review cards (`../wcxy-cards-2026-11-12/verdicts.csv`: 19 XY, 12 one landing) and confirmed the
reading: a pad is XY when the Wolfcamp A shows three landings and the pad is in the top one; the upper of only two
is just upper WCA. On CORRAL BLUFF #033H (card 2, one landing) he saw it only on a wider W-E section in anduin.

Implemented tag-blind: every WCXY / WCA_1 / WCA_2-tagged well within 1 mi along the pad's laterals and 1.5-4.5 mi
across; parallel planes (one dip, one offset per tier; tiers split at an empty band of 40-90 ft; tiers of fewer
than 2-4 wells ignored); XY when at least two tiers lie below the pad's tier.

## Result: it does not reproduce the calls

| Rule | Agrees with Michael (31 cards) |
|---|---|
| Call everything XY | 19 (61 %) |
| Separation above the WCA_1 surface, best cutoff 110 ft | 21 (68 %) |
| Empty-band test (`../wcxy-2026-11-12/`) | 19 (61 %) |
| **Tier count, best of 45 parameter sets** | **18 (58 %)** |

- Across the 45 parameter sets agreement ran from 10 to 18 cards (`grid_vs_verdicts.csv`).
- The dominant miss: 10 cards Michael called XY have only ONE Wolfcamp A tier below the pad in the data, including
  ST BRIDES (card 9), his own first example. There the WCA_2 is barely drilled (one well), so "three landings" is
  not literally present; he reads XY from the pad sitting between BS3_S above and a WCA_1 row below.
- So the rule as stated is not the whole of what he sees. Stratigraphic context (what is above, how thick the
  interval is, what development exists farther along strike) enters the call, and 31 labels are too few to fit a
  rule with that many inputs without fitting noise.
- The all-pad classification this produced (355 pads XY, 816 one landing) is NOT kept: a rule that agrees with
  the reviewer less often than a coin weighted to his base rate must not draw an extent.

## Recommendation

Stop trying to classify WCXY pads automatically. Draw the WCXY extent by hand on evidence, which is the path the
BOX extents already support (`scripts/box_extents_import.py`, `source = 'geology_edited'`; `box/family_extent.py`
reads pen strokes from a slide):

1. Build the candidate with the construction of record from ALL WCXY-tagged wells (they are all north of about
   31.5 N already).
2. Give Michael the map with the candidate outline, every WCXY-tagged well coloured by its separation above the
   WCA_1 surface, and his 31 card calls marked.
3. He pen-edits the outline; the edited extent is stored on an explicit go.
4. WCXY-tagged wells outside the edited extent are treated as upper WCA by the BOX surface builder.
