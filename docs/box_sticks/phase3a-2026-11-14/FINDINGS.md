# BOX sticks phase 3a: pilot findings (gate 3a)

2026-11-15. Generator `box_sticks_0.7_pilot`. Live tags, pulled 2026-11-14 (before the 2026-11-16 formation-tag cutover
decision). Read-only; nothing is stored. 114 pilot DSUs in three areas (Ward TX 40, Lea NM 34, Glasscock / Midland 40).
Bars: `BARS.md`. Numbers: `backtest/backtest_summary.json` and the CSVs beside it. Cards: `cards/index.html`.

## Result in one paragraph

The generator meets all eight invariants (0 violations on today's wells and on the back-test inputs). **It fails the
back-test on three bars.** Of 657 hidden producers in straight DSUs, 58.9 % land on a generated slot against a bar of
60 %, and Ward is at 46.9 % against a per-area bar of 50 % (T1). The per-unit count bar (T3) and the unused-slot bar
(T4) also fail, and one carried depth rung (bracket) is over its limit. T2 and the direct-rung depth bar pass; T6
matches phase 2b. Nothing was tuned after the back-test ran. The misses are row position, not row count: total legs
against wells drilled is 0.96, and on the sideways test the grid scores what a random phase would (76 % against 80 %).

Corrected 2026-11-15 after the first report: T5 direct was first reported as a fail (81.5 ft, 74.7 %). The scoring had
not left out the two-landing units as BARS.md requires. With them left out it passes (59.0 ft, 80.2 %).

## Back-test against the bars

Cutoff 2023-01-01. Hidden: 21,297 producers basin-wide with first production on or after the cutoff and all 3,564
wells not yet producing. The generator read 39,537 producers and 18,483 spacing gaps; the spacing surface, the landing
chain and the regional azimuth / WCA / two-landing tables were rebuilt without the hidden wells. Not hidden (as the
bars state): live tags, the 2026Q3 DSU polygons, BOX extents, thickness tables, the depth screen, the constants.

Population W: 733 hidden producers sit >= 30 % inside a pilot DSU; 26 are tagged with a bench that has no BOX extent in
that DSU (BRNT 5, WCD 4, MISS 4, OTHER 3, WCC 3, WCB_2 3, WCXY 2, BS2_C 1, MS 1). **W = 707 wells** (Lea 288, Ward 138,
Midland 281): 657 in straight DSUs, 50 in U-turn DSUs.

| # | Bar | Result | Verdict |
|---|---|---|---|
| T1 | >= 60 % of W on a slot, >= 50 % per area (straight DSUs) | **58.9 %** (387 / 657). Lea 52.1 % (146 / 280), Ward **46.9 %** (45 / 96), Midland 69.8 % (196 / 281) | **Fail** (overall by 1.1 pt; Ward by 3.1 pt) |
| T2 | <= 10 % of W on a bench that got no row | 5.1 % (36 / 707). Lea 1.7 %, Ward 18.1 %, Midland 2.1 % | Pass (Ward alone would not) |
| T3 | Drilled-across DSU x bench: legs within 1 of wells in >= 70 %; legs / wells 0.85-1.20 | 68 DSU x bench. Within 1 in **63.2 %** (43 / 68). Legs / wells 0.96 (309 / 321) | **Fail** on the per-unit count; the total passes |
| T4 | Unmatched legs <= 25 % of legs, same units | **33.3 %** (103 / 309) | **Fail** |
| T5 direct | median abs TVD difference <= 75 ft, >= 80 % within 150 ft | 121 pairs: median 59.0 ft, 80.2 % within 150 ft | Pass (by 0.2 pt on the second test) |
| T5 carried | observed median <= 1.5 x the rung's held-out median | thickness 61 ft vs 48 (1.28x, 215 pairs) pass; offset 100 vs 87 (1.15x, 37) pass; bracket **118 vs 74 (1.59x**, 24) fail | 2 of 3 pass |
| T6 | reported | 1.1 % of W with depth (7 / 661) inside the envelope of a pre-cutoff well. Lea 1.63 %, Ward 2.21 %, Midland 0 % | In line with phase 2b (1.15 % / 1.57 %) |

Reported beside the bars, not judged: U-turn DSUs 4 of 50 wells on a slot (8 %), as expected from rule 5. Wells with
no depth evidence 24 of 40 on a slot; wells in a two-landing DSU x bench 50 of 76 (depth test skipped for both).

### Why the wells miss (T1, straight DSUs, 270 misses)

| First test that fails | Wells | Lea | Ward | Midland |
|---|---|---|---|---|
| Sideways gap to the nearest row of the bench | 149 | 75 | 36 | 38 |
| Depth more than 150 ft off | 78 | 35 | 11 | 32 |
| Slot already taken by another well | 25 | 19 | 0 | 6 |
| Bench has no row in the DSU | 15 | 5 | 4 | 6 |
| No leg alongside half the well | 3 | 0 | 0 | 3 |

- **Sideways (149).** The nearest row is 453 ft away at the median (quartiles 383 / 574 ft): a grid out of phase with
  what was drilled. On the 603 wells whose bench got a row, 76.3 % pass the sideways test; a grid of the same spacing
  with a random phase would pass 79.7 %. The generator carries no information about phase, and for a bench with no well
  in the DSU there is none to carry. T4 is the same miss counted from the leg side.
- **Benches pinned by existing wells do worse than chance.** 81 wells: 59.3 % pass sideways against 80.5 % by chance
  (not pinned: 522 wells, 78.9 % against 79.6 %). A pinned grid puts rows on the existing wells (closed by the
  envelope) and one spacing away from them; the later wells were drilled between or beside the earlier ones.
- **Trial, not adopted: the wells' own spacing inside the DSU.** A bench with >= 2 (or >= 3) own wells in the DSU takes
  their median gap instead of the map spacing. T1 57.2 % either way (from 58.9 %); pinned wells 57.0 % / 61.5 % sideways
  (from 59.3 %). No gain on the hidden wells, and today's pilot sticks fall from 1,526 to 1,433 / 1,460. The pinned miss
  is not a spacing error. The switch (`Cfg.local_spacing_wells`) stays off.
- **The left-right alternation costs about 2 points.** Diagnostic only, nothing changed: the same back-test with every
  unpinned grid centred gives T1 61.0 % (Lea 53.9, Ward 49.0, Midland 72.2) and T4 29.8 %. With phase at chance, that
  difference is noise; Ward fails either way.
- **Depth (78).** See T5 below.
- **Worst benches** (W >= 10): Lea BS1_S 2 of 17, Ward BS3_S 0 of 7 and BS1_S 0 of 5, Lea WCB_1 4 of 14, BS3_C 8 of 24,
  Midland DEAN 7 of 17. Best: Midland WCD 61 of 73, WCB_1 32 of 39, WCA_1 46 of 62; Lea AVA_2 13 of 15, WCA_1 15 of 19.

### Count (T3 / T4)

Legs minus wells per drilled-across unit: 16 exact, 27 within one (19 one over, 8 one under), 11 over by 2-3, 14 under
by 2 or more (the worst -8). Lea is under-generated (95 legs for 126 wells, 13 of 23 within one); Midland is slightly
over (181 for 164, 25 of 37); Ward 33 for 31 (5 of 8). Generated spacing over the actual gap between the hidden wells:
median 0.93, quartiles 0.71 / 1.21. So the spacing map is right on average and off by 20-30 % in a typical unit, which
is the phase 2a held-out error showing up as it should. This is the spacing surface, not the placement logic.

### Depth (T5)

| Direct rung | Pairs | Median abs | Within 150 ft | Median signed (well - stick) |
|---|---|---|---|---|
| Lea | 30 | 73 ft | 80.0 % | -52 ft |
| Ward | 10 | 152 ft | 50.0 % | -85 ft |
| Midland | 81 | 39 ft | 84.0 % | +28 ft |

Two-landing units left out (48 pairs). The bar passes overall. Ward is 10 pairs, 4 of them WCB_1 wells in DSUs 12615 and
12617 landed 186 ft above the stick.

Checked, read-only: **the landing did not move with time.** In the 40 pilot DSU x bench that have depth-evidenced wells
on both sides of the cutoff, post-2022 median depth minus pre-2023 is -24 ft in Lea (24 units, quartiles -62 / +150),
+56 ft in Ward (14 units) and +119 ft in Midland (2 units): no consistent direction. But the two sides differ by more
than 150 ft in 17 of the 40 units (42 %). So within one DSU and one bench tag, a later campaign often lands a different
level from the earlier one. That is the two-landing question (rule 3: one landing per bench, flag) showing up across
time, and it is the source of most depth misses. The flag catches it only when today's wells show both levels.

### What the back-test does and does not show

- It tests placement inside today's frame (tags, polygons, extents). The DSU polygons were drawn with the hidden wells
  in view, so it flatters the DSU frame and the azimuth.
- T1 is mostly a test of grid phase. Phase matters for a location only when a neighbour exists; with no neighbour, a
  row 450 ft off is the same inventory. The count result (0.96 overall) is the one that carries to phase 6.
- T3 / T4 use units with no same-bench well before the cutoff. They say nothing about infill.

## Pilot report, today's wells (BOX against Novi)

Grain: DSU x bench = a pilot DSU and a bench whose BOX extent touches it. Novi sticks = remaining Novi sticks (status
NULL / remaining_pud / conflict) whose main DSU is a pilot DSU, on a bench with a BOX extent there. A further 79 (Lea),
584 (Ward) and 312 (Midland) remaining Novi sticks sit on benches with no BOX extent in their DSU and are not compared.

| | Lea NM | Ward TX | Glasscock / Midland |
|---|---|---|---|
| DSUs (straight / U-turn) | 34 (27 / 7) | 40 (22 / 18) | 40 (36 / 4) |
| DSU x bench | 460 | 274 | 256 |
| ... with BOX sticks | 304 | 176 | 109 |
| ... with no row, by bench reason | 66 | 42 | 4 |
| BOX sticks (straight / U-turn) | 875 (774 / 101) | 380 (272 / 108) | 271 (255 / 16) |
| BOX legs | 976 | 488 | 287 |
| Rows not placed | 786 | 320 | 862 |
| Novi sticks, same DSUs and benches | 1,212 | 416 | 365 |
| BOX lateral footage | 8.62 MM ft | 3.69 MM ft | 3.08 MM ft |
| Novi lateral footage | 10.80 MM ft | 3.17 MM ft | 3.86 MM ft |
| Existing producers on those benches | 670 | 277 | 572 |

Total: **1,526 BOX sticks (1,751 legs)** against 1,993 Novi sticks. Benches with no row: WCA rule (one member 40, one
landing 16), reconciled out 25, no landing depth 19, sliver 12.

Rows not placed, all areas: same landing 1,205 and stacked 593 (existing wells), unpaired U-turn leg 74, outside the
clear width 83, row count reduced to fit 10, no-depth well with no bench landing 10.

### Landing depth against same-bench producers (the phase 0 bust)

Stick TVD minus the median depth of the DSU's own producers of that bench (depth evidence only, two-landing units left
out). One value per DSU x bench.

| | Lea | Ward | Midland |
|---|---|---|---|
| BOX: units / median abs / P90 abs | 74 / 35 ft / 189 ft | 61 / 27 ft / 147 ft | 43 / 18 ft / 102 ft |
| Novi: units / median abs / P90 abs | 92 / 73 ft / 311 ft | 56 / 102 ft / 334 ft | 53 / 42 ft / 158 ft |
| Same units both: BOX / Novi median abs | 50: 21 / 52 ft | 39: 27 / 103 ft | 33: 18 / 38 ft |

BOX is closer than Novi in every area. **This comparison favours BOX by construction**: where the rung is direct the
stick depth was derived from those same producers. The back-test T5 above is the unbiased number (61-118 ft).

### By bench

`backtest/report_area_bench.csv` holds every area x bench row: DSU x bench, sticks straight / U-turn, rows not placed by
reason, Novi sticks, footage both ways, and the bust both ways. The lines that matter:

- **Midland DEAN: 22 sticks in 13 of 40 DSUs; 118 of 149 rows closed by existing wells (85 stacked, 33 same landing).**
  Candidate D closes DEAN wherever LSSH and WCA_1 are developed. Novi has no DEAN sticks here.
- **Midland WCA_1 22 sticks against 58 Novi, WCB_1 27 against 69, LSSH 60 against 93.** BOX closes far more rows next to
  existing wells than Novi does (WCA_1: 166 of 201 rows).
- **Lea AVA_2 82 against 258 Novi, WCC 76 against 166, BS3_S 38 against 104.** Novi is denser on these three.
- **Lea WCB_1 75 against 25, Ward WCB_2 70 against 24, Ward WCA_2 42 against 5.** BOX places where Novi has little.
- **WCXY: 3 sticks in 27 DSU x bench.** 20 of 25 Lea units have no landing depth.
- **Ward WCA_1: no row in 32 of 40 DSUs** (rule 4, one member; WCA_2 carries the row set there).

## Defects and gaps found

1. **Stack reconciliation bug, fixed.** The back-test inputs produced one I3 violation (DSU 11333: WCA_1 and WCB_2 15 ft
   apart). A bench bounced between two neighbours was dropped without re-testing the pair it left. Fixed (a bench moved
   more than twice is dropped and the loop continues), test added. Today's output changed in one DSU (11201, +2 sticks).
2. **My scoring bug, fixed before any number was read as a result.** The first scoring pass turned a missing depth into
   NaN, which failed the depth test for every well with no depth evidence or in a two-landing unit (T1 read 47.8 %).
   Corrected to skip the depth test as BARS.md says; T1 is 58.9 %.
   A second one was found after the first report: T5 did not leave out two-landing units (corrected above).
3. **The 30 % alongside threshold lets a full-length row through.** DSU 10600: a BS2_S row is placed 161 ft and 184 ft
   from two Chevron spuds that run beside 27 % of it. Not measured across the pilot; nothing changed.
4. **A carried depth can sit far from in-DSU evidence of a neighbour bench.** Lea 10809: carried WCA_1 at 10,981 ft is
   1,300 ft above the in-DSU WCA_2 wells and knocks BS3_C and BS3_S out in reconciliation.
5. **A 1-mile polygon drilled with 2-mile laterals is classed U-turn.** Midland 18899: 22 wells not yet producing, 0
   sticks. The DSU frame, not the generator.
6. **Three private narvi functions are imported** (`_make_leg`, `_single_well`, `_place_uturns`), pinned by commit.

## Decided today, after the cards (all in BARS.md with their measured effect)

No cross-bench 300 ft cull; each bench keeps its own spacing; a no-depth well is taken at its bench's landing in the
DSU where the bench kept one; unpinned benches alternate left and right down the whole stack and none loses a row to
it; rows between existing same-bench producers stay, unstamped.

## For gate 3a

1. The back-test fails T1, T3 and T4 (and the bracket rung of T5). What they measure: T1 / T4 grid phase at chance
   level; T3 the phase 2a spacing error per unit (quartiles 0.71 / 1.21) around a correct total (0.96). Does the pilot
   generator go on to the basin-wide run (gate 3b) with those stated, or go back?
2. Grid phase for an unpinned bench: keep the left-right alternation or centre it (noise either way).
3. A second landing inside one bench tag in 42 % of units drilled in two campaigns: stay with one landing per bench and
   the flag, or revisit rule 3.
4. The 30 % alongside threshold (defect 3).

Not started: gate 3b (basin-wide run), phase 4.
