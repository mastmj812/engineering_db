# BOX sticks, phase 2b: definitions and pass/fail bars, fixed before the first run (2026-11-13)

Committed before `scripts/box_sticks_phase2b.py` was run on real data. Read-only study; live tags; cache pulled
2026-11-13. If a method misses its bar, the findings say so; nothing here is tuned after the run.

## Populations

- **Universe**: every horizontal producer with a lateral line and a live tag (phase 2a `universe`).
- **Child**: an evidence well (phase 0 rules) that passes the two-part screen, first production >= 2016.
- **Parent**: a universe well with depth evidence (never a planned survey or a round-100 TVD without a survey; a
  `bad_depth` well is out) whose first production is >= 365 days before the child's (D112). 180-365 days = young,
  within 180 days = co-developed; neither is a parent, and neither is judged by the envelope.
- **Unjudged older neighbour**: an older universe well with no depth evidence. Counted per child, never used.

## Pair metric

Child-relative, as `box/prox_study.py`: overlap = share of the child's lateral the parent runs alongside; horizontal
gap = median perpendicular distance over the shared length (21 samples); dz = parent depth - child depth (positive =
parent deeper = the child is a topfill). Depth = the evidence depth (survey lateral median TVD, else TVD). Computed
with the phase 2a array method (`pair_table`, parallel within 15 deg), stored out to 2,640 ft sideways, 1,500 ft
vertically, overlap >= 5 % (so overlap is a measured dimension; a qualifying link needs >= 30 %).

Classes by DEPTH, not tag (D150): same landing |dz| <= 150 ft; topfill dz > 150 ft; underfill dz < -150 ft. The bench
pair (child tag, parent tag) is the reporting key.

## What "rare" means

Relative drilling rate r = qualifying parent-child links per foot of horizontal gap in a cell, divided by the same
count per foot at 1,000-2,000 ft in the same vertical band and group. Every link counts, not only the nearest, so r is
flat when operators ignore the parent. Cells: 100 ft sideways; vertical bands same landing, then 100-ft bands.

## Bars

| # | Bar | Fixed value |
|---|---|---|
| B1 | The array pair metric reproduces `prox_study.pair_signed` | On 2,000 random stored links per basin, >= 99 % within max(5 ft, 0.5 %) on the gap and 0.02 on overlap. Recall: of the `prox_study` links (overlap >= 30 %, gap <= 1,400 ft, vertical <= 1,000 ft) of 300 random children per basin, >= 97 % are in the array table |
| B2 | A cell is **rare** | r < 0.25, judged only where the 1,000-2,000 ft level predicts >= 30 links in the cell. A bench pair that cannot reach 30 is read at basin x class level and listed as not resolved on its own |
| B3 | A proposed envelope is acceptable | It is rare by B2 taken as one region, AND it excludes <= 2.0 % of all children per basin, AND <= 5.0 % of the children of any bench with >= 200 children. Each starting point (21a floor 150 / 400 / 30 %; D112 topfill 800 ft and underfill 500 ft vertical at 1,400 ft sideways; deal-intake v14 300 / 800 / 30 %) is scored against the same three tests |
| B4 | The envelope does not double-count the D150 factor | The D150 fit of record (step 24 revision 5 inputs, rule of record per basin, fitted level) is refitted without the children that have a parent inside the proposed envelope. Outside the envelope the per-parent factor moves by <= 0.02 anywhere on the grid, and the level by <= 0.01. Reported beside it, not a bar: the residual after the factor of the children inside the envelope |
| B5 | The envelope does not cull the stagger operators drill | Same-tag parent links at another landing (|dz| > 75 ft) are read as their own group. Where that group is not rare by B2, the envelope may not cover it. Co-developed wells are never parents, so a co-developed two-landing pad is untouched by construction; that is stated, not tested |

## Novi stick count

Every remaining Novi stick (reconciliation status NULL, `remaining_pud` or `conflict`) against every existing producer
with depth evidence, whatever its age. Stick depth = Novi's TVD, which phase 0 showed is often wrong; a second count
by tag (same bench pool, sideways test only) is reported beside it. Indicative only: the generator will not place
Novi's sticks.
