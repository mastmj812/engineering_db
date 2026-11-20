# Delaware Bone Spring mistags, producing wells only

2026-11-20, read-only. Corrects `TAG_TWO_WITNESS.md`, whose counts included permits and other non-producing wells. Nothing
changed: no tag, no seed, no rule row.

## Why the redo

The depth-evidence test (not a planned survey; survey lateral median, else header TVD unless a round 100) lets through a
permit whose planned TVD happens not to be round. 5,605 of the 34,052 judged wells were not producing. Here both the
judged wells and the WCA_1 control are restricted to wells with a first production date.

## The witnesses on producers

Grain: producing Delaware horizontals with depth evidence, tagged BS2_S, BS3_C or BS3_S, inside the grids: 8,086 wells.
Height bands recomputed on producers: BS3_S median 201 ft above local WCA_1, BS3_C 835 ft, BS2_S 1,421 ft; edges at 518
and 1,128 ft.

Share in their own gridded interval (more than 25 ft from a surface): BS2_S 95 %, BS3_C 95 %, BS3_S 77 %.

| Tag | Both witnesses, same answer | Both off, different | Grid only | Grid only, no control | Height only | Tag fits | All |
|---|---|---|---|---|---|---|---|
| BS3_S | 116 | 15 | 250 | 56 | 136 | 1,989 | 2,562 |
| BS2_S | 28 | 9 | 37 | 46 | 259 | 3,683 | 4,062 |
| BS3_C | 29 | 2 | 14 | 24 | 226 | 1,167 | 1,462 |
| All | **173** | 26 | 301 | 126 | 621 | 6,839 | 8,086 |

The 173:

| Tag | Both say | Wells |
|---|---|---|
| BS3_S | BS3_C | 51 (Eddy 22, Lea 20, Winkler 4, Pecos 4) |
| BS3_S | WCXY / WCA / below B1 | 20 / 13 / 17 |
| BS3_S | BS2_S, BS1 or above | 11, 4 |
| BS3_C | BS2_S | 22 |
| BS3_C | BS3_S | 7 |
| BS2_S | BS3_C | 15 |
| BS2_S | other | 13 |

How the stick generator already treats the 173 (set 16's own evidence screen): 105 `keep` (they feed depth bands), 52
already screened out as `mistag`, 16 carry no depth in the set. 170 of the 173 have a row in the tag rule table.

## The cards against this

| Group | Producing cards | Verdicts | Non-producing cards | Verdicts |
|---|---|---|---|---|
| S (BS3_S, both say BS3_C) | 5 | 4 AGREE, 1 KEEP | 19 | 19 AGREE |
| H (BS2_S, height only) | 4 | 4 KEEP | 2 | 1 KEEP, 1 BS1_S |
| G (BS3_S, grid only) | 5 | 2 AGREE, 2 KEEP, 1 WCA_1 | 1 | 1 AGREE |

Reading:

- **Height alone is not a test for BS2_S.** 5 of 5 "BS3_C level" calls were KEEP. The one height call that held was 2,052 ft
  above WCA_1 (BS1_S).
- **The grid alone is right when it says Wolfcamp A or BS3_C, wrong when it says WCXY** (4 of 6 agreed; both WCXY calls
  were KEEP). The XY top is the weak surface, as the October QC found.
- **Both witnesses together**: 4 of 5 producers agreed; the KEEP was the card closest to the height boundary (559 ft).

## What this says about the depth bands

Gross mistags among producers are few: 173 of 8,086 (2 %) by both witnesses, 105 of them still feeding the stick
generator's depth bands. That is too few to explain the 26 "same well" removals on the stick cards or the 580 Delaware
DSU x bench the generator dropped in a depth conflict. Card 03 is the pattern those more likely follow: a row of wells
within 30 ft of a bench boundary carrying three different tags, which neither witness calls wrong. The next question is
therefore the landing computation itself on those 26 sticks, not a larger tag class.

Lists: `tag_two_witness_delaware_producers.csv` (1,247 producers failing at least one witness).
