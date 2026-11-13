# BOX sticks, phase 2b: the no-place envelope (2026-11-13)

Read-only. Plan: `docs/box_sticks_plan.md`. Live tags, cache pulled 2026-11-13 (60,834 horizontal producers, 257,397
Novi sticks). Nothing was written to the warehouse. Definitions and pass/fail bars: `BARS.md`, committed before the
first run (`ca1718e`). **Awaiting Michael's decision; nothing here is decided.**

    python -m scripts.box_sticks_phase2b --out docs/box_sticks/phase2b-2026-11-13 --cache <phase 0 cache> --prox-runs <main checkout>/runs

## Headline

| | Delaware | Midland |
|---|---|---|
| Children (evidence wells, two-part screen, first production >= 2016) | 22,610 | 23,988 |
| Parent-child links (parent >= 12 months on production, >= 30 % alongside, within 2,640 ft sideways and 1,500 ft vertically) | 57,478 | 82,948 |
| Children with a parent within 1,400 ft sideways and 1,000 ft vertically | 8,507 | 8,996 |
| Same landing (within 150 ft vertically): drilling rate inside 400 ft of the parent, relative to 1,000-2,000 ft | 0.05 | 0.04 |
| Same landing: first 100-ft bin that is not rare | 600-700 ft | 600-700 ft |
| Stacked 150-350 ft over or under the parent, within 300 ft sideways: rate with a parent | 0.22 | 0.14 |
| The same stacked position when the neighbour is co-developed | 0.87 | 1.15 |
| **Recommended envelope (candidate D): historical children it would have excluded** | **260 (1.15 %)** | **377 (1.57 %)** |
| Remaining Novi sticks it would cull (Novi TVD) | 11,703 of 166,636 (7.0 %) | 7,243 of 85,811 (8.4 %) |

Rate r = parent-child links per foot of sideways gap, divided by the same at 1,000-2,000 ft in the same vertical band.
r = 1 means operators ignore the parent; "rare" was fixed at r < 0.25.

**The one finding that organises everything else.** Operators stack a well directly over or under a neighbour freely
when the two are drilled together, and almost never when the neighbour is a parent a year or more old
(`parent_vs_codev.csv`):

| Position of the neighbour | Neighbour | Delaware r within 300 ft | Midland r within 300 ft |
|---|---|---|---|
| Same landing | co-developed | 0.11 | 0.09 |
| Same landing | parent | 0.04 | 0.02 |
| Stacked 150-350 ft | co-developed | 0.87 | 1.15 |
| Stacked 150-350 ft | parent | 0.22 | 0.14 |
| Stacked 350-550 ft | co-developed | 1.59 | 1.64 |
| Stacked 350-550 ft | parent | 0.67 | 0.27 |

So the envelope has two parts: a same-landing part, which is mostly a spacing fact (true with or without a parent),
and a stacked part, which only exists next to a depleted parent.

Figures: `rate_profiles.png`, `rate_heatmap.png`, `gunbarrel_parents_delaware_BS1_S.png`,
`gunbarrel_parents_midland_DEAN.png`, `map_delaware_BS1_S.png`, `map_midland_DEAN.png`, five `pad_*.png`.

## Method, grain and filters

- **Child**: evidence well (phase 0 rules) passing the two-part screen, first production >= 2016. **Parent**: any
  horizontal producer with depth evidence whose first production is >= 365 days before the child's. Wells 180-365 days
  older and co-developed wells (within 180 days) are never parents. Planned surveys and round-100 TVDs are never
  depth evidence; 907 Delaware children (4.0 %) and 161 Midland (0.7 %) have such an unjudged older well within
  400 ft sideways, which this study cannot place vertically.
- **Pair metric** (child-relative, as `box/prox_study.py`): overlap = share of the child's lateral the parent runs
  alongside; gap = median perpendicular distance over the shared length; dz = parent depth minus child depth
  (positive = parent deeper = the child is a topfill). Depth = survey lateral median TVD, else TVD.
- **Classes by depth, not tag** (as D150): same landing = within 150 ft; stacked = more than 150 ft apart. The bench
  pair is the reporting key (`bench_pairs.csv`, 653 pair x class rows; 65 Delaware and 55 Midland pairs have >= 150 children).
- **Overlap matters and 30 % is the right line.** Same landing, within 200 ft sideways: neighbours alongside for
  5-30 % of the child are drilled at r = 0.79 (Delaware) and 0.84 (Midland), i.e. heel-to-toe neighbours are normal;
  at 30 % or more r is 0.00-0.03 (`overlap_dimension.csv`).

## The bars, and how the study did against them

| Bar | Result |
|---|---|
| **B1** array pair metric reproduces `prox_study.pair_signed`: >= 99 % of links within max(5 ft, 0.5 %) and 0.02 overlap; recall >= 97 % | **Agreement FAILS: 53.8 % Delaware, 65.5 % Midland.** Recall passes: 97.6 % / 99.9 % |
| **B2** rare = r < 0.25 where >= 30 links are expected | applied as written |
| **B3** an envelope is rare as one region, excludes <= 2.0 % of children per basin and <= 5.0 % of any bench with >= 200 children | candidates A, B and D pass; C and E fail (below) |
| **B4** refitting D150 without the children inside the envelope moves the factor outside it by <= 0.02 and the level by <= 0.01 | **Delaware passes for every candidate. Midland FAILS for every candidate, including the 21a floor that is already of record** |
| **B5** same-bench neighbours at another landing are not culled where operators drill them | holds (below) |

**B1, said plainly.** The bar I set was too tight for what it compares. The two methods measure overlap differently:
`prox_study` projects the parent's vertices onto the child's line (nearest point); the array method projects onto the
child's straight axis. Far from the child they drift (95th percentile difference 0.07-0.10 in overlap, 34-54 ft in
gap). At the scale the envelope works on they agree: same side of the 30 % line on 98.7 % / 99.4 % of links; among
qualifying links, same side of 300 ft on 99.8 % / 100 %. Re-measuring every close-in link with `prox_study` changes
the recommended envelope's excluded children from 260 to 258 (256 in common) in the Delaware and from 377 to 379
(376 in common) in the Midland. The bar stays failed as written; I did not loosen it.
One fault of mine in the check itself: the first run compared recall against parent links only and read 12-17 %; the
candidates carry no age filter, so the comparison is against every stored link. Fixed before any result was used.

## Where drilling next to a parent becomes rare

Same landing, 50-ft bins (`rate_same_landing_50ft.csv`):

| Sideways gap | Delaware links / r | Midland links / r |
|---|---|---|
| 0-200 ft | 31 / 0.03 | 33 / 0.02 |
| 200-400 ft | 101 / 0.08 | 100 / 0.05 |
| 400-500 ft | 66 / 0.11 | 102 / 0.11 |
| 500-600 ft | 116 / 0.19 | 196 / 0.21 |
| 600-650 ft | 93 / 0.31 | 150 / 0.32 |
| 650-700 ft | 168 / 0.56 | 268 / 0.58 |

The step at 650 ft is the 660 ft pattern: the nearest thing operators actually drill beside a same-landing parent.
Every same-bench pair with enough wells shows it (WCA_1 by WCA_1 r = 0.04 inside 400 ft in both basins, LSSH 0.04,
BS2_S 0.10, DEAN 0.02).

Stacked, r inside 400 ft by vertical band (`rate_edges_by_band.csv`):

| Vertical gap | Delaware, parent deeper | Delaware, parent shallower | Midland, parent deeper | Midland, parent shallower |
|---|---|---|---|---|
| 150-250 ft | 0.16 | 0.22 | 0.20 | 0.11 |
| 250-350 ft | 0.33 | 0.44 | 0.30 | 0.15 |
| 350-450 ft | 0.46 | 0.74 | 0.33 | 0.22 |
| 450-550 ft | 0.67 | 0.79 | 0.44 | 0.25 |
| 650-750 ft | 0.91 | 0.86 | 0.53 | 0.25 |

- **Delaware**: the avoidance is gone by about 450 ft of vertical gap. A BS3_C child 877 ft over a WCA_1 parent is
  drilled at r = 0.95 inside 300 ft (725 children); BS1_S over BS2_S (794 ft) at 1.04.
- **Midland**: the rate never returns to 1 inside 800 ft sideways at any vertical gap, and it is lowest under a
  shallower parent even 700-1,100 ft below (WCB_1 under LSSH 0.21, LSSH under MS 0.08, WCA_1 under MS 0.13). The
  Midland curves in `rate_profiles.png` rise in a straight line to 2,500 ft with no plateau. I read that as
  development order (operators step to the next pad rather than return under an existing one), not as a
  parent-distance effect, because it does not fade with vertical distance. It means a Midland r is a weaker measure
  than a Delaware r, and it is why I did not carry the envelope past 350 ft vertically there. That is my
  interpretation, not a tested result.
- The vertical gap, not the bench name, explains the pairs: WCA_1 over WCA_2 (206 ft) 0.11; WCXY over WCA_2 (264 ft)
  0.12; BS3_S over WCA_1 (254 ft) 0.30; WCB_1 under WCA_1 (354 ft) 0.51; Midland WCB_1 under WCA_1 (270 ft) 0.08;
  WCA_1 over WCB_1 (289 ft) 0.31; DEAN under LSSH (256 ft) 0.10; DEAN over WCA_1 (249 ft) 0.15 (r inside 300 ft).
  So the proposal is written in feet and every bench pair inherits it from its own vertical gap.

## The starting points and the candidates

Candidates A-E were written after the profiles above were read; the bars were not.

| Envelope | Delaware excluded | Midland excluded | Worst bench | r as one region (D / M) | B3 |
|---|---|---|---|---|---|
| 21a floor: same landing, 400 ft (= candidate A) | 127 (0.56 %) | 127 (0.53 %) | AVA_1 1.5 %, DEAN 1.0 % | 0.05 / 0.04 | pass |
| D112 vertical: topfill 800 / underfill 500 ft, 1,400 ft sideways | 4,743 (21.0 %) | 6,708 (28.0 %) | BS3_C 42.6 %, LSSH 39.5 % | 2.59 / 2.08 | **fail**, not rare |
| D112 vertical at 400 ft sideways (extra) | 1,267 (5.6 %) | 1,732 (7.2 %) | BS3_C 17.7 %, LSSH 13.4 % | 0.50 / 0.33 | fail |
| deal-intake v14: 300 ft vertical, 800 ft sideways | 1,687 (7.5 %) | 1,937 (8.1 %) | DEAN 13.3 % | 0.28 / 0.21 | **fail** |
| B same landing 600 ft | 294 (1.30 %) | 404 (1.68 %) | AVA_0 3.6 %, LSSH 2.4 % | 0.09 / 0.08 | pass |
| C same landing 600 ft + stacked 150-350 ft within 300 ft | 521 (2.30 %) | 633 (2.64 %) | WCA_1 4.4 % | 0.12 / 0.09 | fail (over 2 %) |
| **D same landing 400 ft + stacked within 300 ft** | **260 (1.15 %)** | **377 (1.57 %)** | AVA_2 2.3 %, WCA_1 3.1 % | 0.08 / 0.07 | **pass** |
| E same landing 600 ft + every rare stacked cell | 422 (1.87 %) | 723 (3.01 %) | WCA_1 5.1 % | 0.10 / 0.10 | fail (Midland) |

Candidate D in full, parent depth relative to the stick, >= 30 % alongside in every part:

| Part | Delaware | Midland |
|---|---|---|
| Same landing (within 150 ft vertically) | no stick within 400 ft sideways | no stick within 400 ft sideways |
| Parent deeper by 150-350 ft | no stick within 300 ft sideways | no stick within 300 ft sideways |
| Parent shallower | by 150-250 ft: no stick within 300 ft | by 150-350 ft: no stick within 300 ft |

(Delaware's parent-shallower 250-350 ft cell reads r = 0.37 inside 300 ft, not rare, so it is left out.)

- **D112's vertical numbers and v14 are not no-place rules.** They were measured as where a parent affects a child's
  production, and operators drill there routinely. As placement rules they would have removed 7-28 % of what was
  actually drilled.
- **The 21a floor holds in both basins**, and the Delaware supports the same 400 ft the Midland adopted.

### Recommendation: D. Why not B or C

- The stacked part is the only part that is specific to a depleted parent (the co-developed contrast above), and it is
  what the spacing grid cannot do: the generator pins rows to existing same-bench wells, so it will rarely put a stick
  400-600 ft from one anyway, but nothing else stops a stick directly over or under a parent on the next bench.
- 400 ft sits under the 440 ft tight cap from phase 2a, so the envelope never overrules the spacing map. 600 ft would
  cull the first row beside an existing well wherever the map says 440-600 ft.
- C (both the wider landing limit and the stacked part) is what the rarity bar alone supports, and it fails my own
  2 % cap (2.3 % / 2.6 %). If you would rather have C, that is a decision to accept a higher exclusion share, not
  something the study shows is safe.

Real wells where the choice changes the answer:

| Well | What was drilled | A (21a floor) | B (600 ft) | D | D112 vertical |
|---|---|---|---|---|---|
| **Vaca 24 Federal Com 756H** (EOG, Lea, BS2_S; `pad_delaware_stacked_tier.png`) | 243 ft above the Vaca 24 Federal Com 404H (BS2_S, 14 months older), 108 ft sideways | placed | placed | **not placed** | not placed |
| **UL Mason East Unit 12LS** (Midland LSSH; `pad_midland_same_landing_400_600.png`) | 524 ft from a same-landing LSSH parent | placed | **not placed** | placed | placed |
| **Blaster the Burro 13-19 A 1DN** (Birch, Howard, DEAN; `pad_midland_DEAN_sandwich.png`) | 225 ft under an LSSH parent 64 ft sideways, WCA_1 parents 448 ft away below | placed | placed | **not placed** | not placed |
| **Dauntless 7 Federal 752H** (Lea, BS3_C; `pad_delaware_BS3C_over_WCA1.png`) | 869 ft above a WCA_1 parent, 56 ft sideways | placed | placed | placed | **not placed** |

The first three are wells an envelope would have got wrong, by construction: every envelope excludes some real wells.
The Vaca well is also the stagger case below.

### What the excluded children looked like (candidate D, `excluded_children_proposed.csv`)

| | Delaware (260) | Midland (377) |
|---|---|---|
| Median sideways gap / vertical gap to the excluding parent | 222 ft / 166 ft | 218 ft / 237 ft |
| Median parent age at the child's first production | 3.6 years | 2.3 years |
| Parent lateral under 5,000 ft | 59 % | 9 % |
| Same operator as the parent | 89 % | 93 % |
| Child drilled with >= 2 co-developed siblings | 74 % | 89 % |
| Counties | Reeves 69, Loving 55, Lea 49, Eddy 39 | Midland 110, Howard 101, Martin 67, Reagan 31 |
| Largest pairs (child by parent) | BS2_S by BS2_S 25, WCA_1 by WCA_2 24, WCA_1 by WCA_1 17 | WCA_1 over WCB_1 120, WCA_1 by WCA_1 54, LSSH by LSSH 33 |
| Production against BOX's level (step 24 frame, oil cum-24) | 0.86, n 130 | 0.77, n 131 |

- They are mostly an operator filling its own pad as part of a larger package, not lone wells.
- In the Delaware, 59 % sit beside a short old lateral: a long new well runs past a 4,000-5,000 ft parent. The
  envelope treats that parent like any other. Not changed; noted.
- Focus benches: BS1_S 2 of 813 children (0.25 %); DEAN 27 of 961 (2.8 %).

## The same-bench stagger (Ruthless 11)

How the envelope treats a same-bench neighbour at the other landing:

1. **A co-developed neighbour is never a parent.** Ruthless 11 Federal COM's eleven BS2_S wells came on within four
   months of each other, so no well there is a parent of another and no envelope says anything about the pad
   (`pad_ruthless_11.png`). The envelope tests a stick against existing producers only, never against other sticks,
   so the generator stays free to alternate landings inside a bench.
2. **An existing producer at the other landing is judged by depth, like any other well.** Within 150 ft it is the same
   landing. Further apart it is a stacked neighbour, and under D a stick is refused only when it is within 300 ft
   sideways of it. A staggered slot (half the spacing sideways, 440 ft or more on every map value) is placed.
3. **That is what operators do with a parent.** Same-tag parent links at another landing
   (`same_bench_other_landing.csv`):

| Vertical gap, same tag | Delaware parent links, r inside 300 ft / inside 660 ft | Midland |
|---|---|---|
| 75-150 ft | 2,123 links, 0.04 / 0.13 | 4,060 links, 0.03 / 0.13 |
| 150-300 ft | 1,142 links, 0.10 / 0.28 | 1,890 links, 0.07 / 0.21 |
| 300-500 ft | 241 links, 0.16 / 0.31 | 135 links, 0.27 / 0.25 (18 expected, not resolved) |

   A year-old well at the other landing is avoided directly over or under (15 Delaware children against 143 expected
   at 150-300 ft), and less so by 660 ft. So B5 holds: the stacked part covers only ground that is rare. The Vaca 24
   well above is one of the 15.

Open detail for the generator, not settled here: at 75-150 ft apart (the Delaware WCA_1 / WCA_2 case, about 115 ft)
two landings count as the same landing, so a stick needs 400 ft sideways from a parent on the other one.

## Midland DEAN: topfill, underfill, sandwich

961 DEAN children. DEAN lands a median 256 ft under LSSH parents and 213-249 ft over WCA_1 parents, so both
neighbours fall inside the 150-350 ft stacked band.

| Configuration (parents within 1,400 ft sideways, 1,000 ft vertically) | DEAN children |
|---|---|
| No parent | 573 (59.6 %) |
| Parent below only (topfill) | 141 (14.7 %) |
| Parents above and below (sandwich) | 139 (14.5 %) |
| Parent above only (underfill) | 64 (6.7 %) |
| Same-landing parent only | 44 (4.6 %) |

- Sandwiches get drilled (139), but not tight ones: only **17** DEAN children have a parent above AND a parent below
  both within 660 ft sideways, and **4** have both within 300 ft.
- By DSU (`dean_sandwich_uptake_by_dsu.csv`): of 920 polygons in the DEAN extent with LSSH above and WCA_1 below both
  on production 12 months ago, 129 got DEAN with that development, **61 (6.6 %) got DEAN 12 months or more later**,
  706 have no DEAN well. With LSSH only: 23 of 262 (8.8 %); WCA_1 only: 18 of 330 (5.5 %).
- What D does: a DEAN stick directly under an LSSH parent or over a WCA_1 parent (within 300 ft sideways) is not
  placed; a stick offset 300 ft or more from both is placed and D150 discounts it (Midland per-side product: about
  0.80 for one such neighbour, about 0.65 for a sandwich, before the 1.067 level). Where LSSH and WCA_1 rows are
  themselves staggered at about 400 ft, almost no DEAN slot clears both, so a fully developed cube gets few or no
  DEAN sticks. That matches your D143 expectation and the 6.6 % uptake.
- On today's Novi sticks: 367 of 1,880 remaining DEAN sticks (19.5 %) fall inside D; 134 inside the 21a floor alone.

Delaware BS1_S, for contrast: 813 children, 465 with no parent; its usual neighbour is BS2_S 794 ft below, drilled at
r = 1.04. The envelope barely touches it (2 children; 465 of 9,017 Novi sticks, 5.2 %).

## Does the envelope double-count the D150 factor? (B4)

Three separate things:

1. **No stick gets both.** A stick inside the envelope is not placed, so it has no forecast to discount. Outside it,
   the factor is the stick's own level x F from its own parents; removing other sticks does not change it.
2. **Does the factor applied outside rest on the wells inside?** Tested by refitting the D150 fit of record (step 24
   revision 5 inputs; my refit reproduces the record parameters to the last digit: Delaware F_min 0.912, d50
   1,259 ft, level 1.046; Midland F_min 0.720, d50 485 ft, level 1.067) without the children inside the envelope.

| Candidate | Delaware: children removed / largest factor change outside / level change | Midland |
|---|---|---|
| A (21a floor) | 71 / 0.003 / -0.000 | 46 / **0.070** / -0.001 |
| B | 156 / 0.005 / -0.002 | 153 / **0.075** / -0.004 |
| D | 130 / 0.008 / -0.001 | 131 / **0.122** / -0.003 |
| Bar | 0.02 / 0.01 | 0.02 / 0.01 |

   **Delaware passes. Midland fails, for every candidate including the floor already of record.** The direction is
   the opposite of double-counting: without the close-in children the Midland curve is deeper (same landing at 450 ft:
   0.831 against 0.849 of record; stacked at 400 ft under D: 0.66-0.69 against 0.76; the two meet by about 800 ft).
   The few close-in children did better than the curve says (46 inside the floor: produced 0.83 of BOX's level against
   a factor of 0.70) and they hold the record curve up. So next to the envelope edge the Midland factor of record is,
   if anything, 0.02-0.10 too lenient, not doubled. It also says the near end of the Midland curve hangs on about 50
   to 130 wells (a_below and a_above are at their bound in the record fit). The level passes in both basins.
3. **Is the factor right for the wells that would be culled?** Residual after the factor for children inside D: 1.04
   in both basins (Delaware actual 0.86 against factor 0.83; Midland 0.77 against 0.74). The factor already prices
   them. The envelope is therefore a statement about what gets drilled, not an extra production penalty.

What I am not claiming: that the Midland curve is wrong, or that B4's failure is harmless. It is a failed bar. The
honest consequence is that phase 6 should re-measure the Midland factor on the placed geometry (the D116-style
re-measure the plan already calls for) rather than carry revision 5's near end across unchanged.

## What changes against Novi's sticks

252,447 remaining sticks (status NULL, `remaining_pud` or `conflict`) against every existing producer with depth
evidence, whatever its age. Stick depth is Novi's TVD (`novi_cull_by_basin.csv`, `novi_cull_by_bench.csv`).

| Envelope | Delaware (166,636) | Midland (85,811) |
|---|---|---|
| A, the 21a floor | 5,706 (3.4 %) | 2,055 (2.4 %) |
| B, same landing 600 ft | 8,722 (5.2 %) | 3,307 (3.9 %) |
| **D, recommended** | **11,703 (7.0 %)** | **7,243 (8.4 %)** |
| C | 15,563 (9.3 %) | 8,125 (9.5 %) |
| deal-intake v14 | 21,153 (12.7 %) | 11,345 (13.2 %) |
| D112 vertical | 42,800 (25.7 %) | 27,336 (31.9 %) |
| Same-landing part only, by tag instead of Novi TVD | 2,930 (1.8 %) | 936 (1.1 %) |

- Heaviest under D: Delaware BS3_S 3,635 of 15,301 (23.8 %), BS3_C 10.0 %, WCB_1 8.7 %; Midland DEAN 19.5 %, JM
  16.0 %, WCB_1 15.7 %, WCA_1 13.2 %. Lightest: Delaware WCC 2.0 %, Midland WCD 0.7 %.
- **Novi's TVD inflates these.** By tag, half as many sticks sit on a same-bench producer (2,930 against 5,706
  Delaware): Novi puts many sticks at the depth of a neighbouring bench's wells (the phase 0 bust). BS3_S at 23.8 %
  is the WCA_1 seam. Read the table as "what changes on today's sticks", not as a forecast of BOX stick counts.
- **Most of it is not new.** Of the sticks D culls, the record runs already give no forecast to 8,431 of 11,703 in
  the Delaware (3,832 outside extent, 3,144 no precedent, 1,223 conflict, 161 not in the run, 71 emerging) and 4,253
  of 7,243 in the Midland (`novi_cull_vs_record.csv`). The rest: 1,678 / 1,674 provisional, and 1,594 / 1,316
  forecast with a proximity factor that averages 0.79 / 0.75 on the multi-parent ones.

## Open items

- **Midland D150 near end** (B4): re-measure on placed geometry in phase 6.
- **Midland reference level**: r has no plateau there. A second normalisation (against co-developed neighbours at the
  same position) would test my development-order reading. Not run; it was not in the bars.
- **Which existing wells count for a stick**: here, every producer with depth evidence, any age. D115 counts
  producers >= 12 months on. A producer under 12 months old will be over 12 by the time a stick is drilled; I would
  count them all, plus DUCs on the drop trigger. Your call at the generator.
- **Wells with no depth evidence** (planned surveys, permit depths; mostly New Mexico) cannot be placed vertically.
  The generator needs a rule for a stick beside one: proposal, test sideways only against the same vendor formation
  family and flag it, as the plan already does for reconciliation.
- **Short old parents** drive 59 % of the Delaware exclusions. No exemption proposed.
- **75-150 ft landings** (WCA_1 / WCA_2) count as one landing for the 400 ft test.
- Novi stick counts use Novi TVD; they will be re-run on BOX sticks at gate 3b.

## Decisions asked of Michael

1. The envelope: **D** (recommended), A (the 21a floor in both basins), B, or C with its 2.3-2.6 % exclusion accepted.
2. Whether the Delaware adopts the Midland's 400 ft same-landing floor as its own (part of A and D).
3. Whether the stacked part stops at 350 ft in the Midland (recommended) or follows the rare cells to 550 ft under a
   shallower parent (candidate E, fails the bench cap at WCA_1 5.1 %).
4. B1 and the Midland B4 are failed bars. Accept the study with them stated, or have me rework either first.

Not committed (regenerate with the script): the link tables in the cache.
