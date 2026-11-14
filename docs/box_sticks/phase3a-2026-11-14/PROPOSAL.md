# BOX sticks, phase 3a step 1: pilot areas and open rules (2026-11-14, awaiting Michael's go)

Read-only. Plan: `docs/box_sticks_plan.md`. Live tags, cache pulled 2026-11-14 (60,834 horizontal producers, 3,564
horizontals spudded / DUC / completed and not yet producing, 257,397 Novi sticks, 16,585 Novi 2026Q3 DSU polygons,
49,554 DSU x bench). No generator code exists yet. Bars: `BARS.md`, committed on its own before this file.

    python -m scripts.box_sticks_phase3_pilot --out docs/box_sticks/phase3a-2026-11-14 --cache <phase 0 cache> --step areas

Grain and filters used throughout: a well or a Novi stick belongs to a DSU when at least 30 % of its line lies inside
the polygon. DSU x bench = a polygon and a bench whose BOX record extent it intersects (WCXY: the hand-drawn file).
Landing rung = phase 1c chain on the two-part-screened evidence wells. Spacing = phase 2a blended surface.
"No depth evidence" = planned survey, or a round-100 TVD with no survey, or under 4,000 ft.

## 1. Pilot areas

Each is every DSU polygon whose centroid falls in a square block. Picked by scoring every 7-8 mi block inside the focus
extent for the card cases you listed (`pilot_summary.json`, `pilot_dsus.csv`, `pilot_dsu_bench.csv`, `pilot_benches.csv`).

| | Delaware TX: Ward County | Delaware NM: Lea County | Midland: Glasscock / Midland County |
|---|---|---|---|
| Block centre, size | -103.310, 31.581; 7 mi | -103.664, 32.159; 7 mi | -101.754, 31.871; 8 mi |
| Focus extent | BS1_S | BS1_S | DEAN |
| Map | `pilot_map_delaware_tx_ward.png` | `pilot_map_delaware_nm_lea.png` | `pilot_map_midland_glasscock.png` |
| DSUs | 40 | 34 | 40 |
| DSU x bench | 274 | 460 | 256 |
| Undeveloped DSUs / DSUs with 1-4 producers | 4 / 8 | 1 / 8 | 6 / 2 |
| Producers | 282 | 698 | 592 |
| Spud / DUC / completed, not producing | 7 | 56 | 82 |
| Remaining Novi sticks (of them on a bench with no BOX extent there) | 1,000 (488) | 1,291 (66) | 677 (308) |
| DSU x bench on a carried landing depth | 37.2 % | 43.0 % | 28.9 % |
| DSU x bench with no depth | 0 % | 4.3 % (WCXY, direct only) | 0 % |
| Carried and low confidence (rung P90 over 200 ft) | 20.1 % | 13.0 % | 0 % |
| DSUs under 7,000 ft straight lateral (U-turn class) | 18 (45 %) | 7 (21 %) | 4 (10 %) |
| Near-square DSUs (aspect under 1.15) | 13 | 6 | 3 |
| Producers with no depth evidence | 23 (permit depths) | 89 (85 planned surveys) | 1 |
| Producers under 12 months on | 13 | 79 | 125 |
| Producers since 2023-01-01 (back-test) | 135 in 19 DSUs | 293 in 22 DSUs | 294 in 22 DSUs |
| DSU x bench showing two landings | 1 | 15 (12 are BS2_S) | 9 |

Producers by bench (live tag), remaining Novi sticks in the same DSUs, and landing rungs: `pilot_benches.csv`.

| Area | DSU x bench per bench | Producers by bench |
|---|---|---|
| Ward | BS1_S 39, BS3_C 40, BS3_S 40, WCA_1 40, WCA_2 40, WCB_1 40, WCB_2 33, WCXY 2 | BS3_S 84, WCB_1 50, WCA_2 42, BS3_C 37, WCA_1 26, WCB_2 19, WCXY 7, BS1_S 5 (12 more on benches with no extent there, 8 of them WCC) |
| Lea | AVA_0 28, AVA_1 34, AVA_2 34, BS1_S 34, BS2_C 34, BS2_S 34, BS3_C 34, BS3_S 34, WCA_1 34, WCA_2 34, WCB_1 34, WCB_2 34, WCC 33, WCXY 25 | BS2_S 190, WCA_2 107, AVA_1 82, WCB_1 59, WCA_1 48, WCB_2 32, AVA_0 30, AVA_2 29, BS3_C 27, BS1_S 24, BS3_S 14, BS2_C 13, WCC 12, WCXY 7 (24 more: OTHER 20, WCD 3, BRNT 1) |
| Glasscock / Midland | DEAN 40, JM 38, LSSH 40, WCA_1 40, WCB_1 40, WCB_2 18, WCD 40 | WCA_1 163, LSSH 111, WCD 111, WCB_1 97, JM 44, WCB_2 36, DEAN 18 (12 more: MISS 4, BRNT 4, OTHER 2, MS 1, WCC 1) |

Why these three:

- **Ward** tests thin BS1_S control: 5 BS1_S producers in 3 DSUs, BS1_S depth carried in 36 of 39 DSUs (34 low
  confidence). It has the most U-turn and near-square DSUs, three survey grids meeting (laterals near 164 deg and near
  43 deg), and 16 DSUs within 3 deg of the 45 deg gunbarrel seam (`near_seam`). The BS1_S, WCB_2 and WCXY extent
  edges cross it.
- **Lea** holds **Ruthless 11 Federal COM (pad_id 10785)**, so no fourth DSU is needed. It is inside the BS1_S extent
  (10+ mi band). 85 producers are still on planned surveys, 44 of the 56 not-yet-producing wells have no depth
  evidence, and BS2_S shows two landings in 12 DSUs.
- **Glasscock / Midland**: 26 DSUs carry at least 2 LSSH and 2 WCA_1 producers; 19 of those have no DEAN well. DEAN
  has 18 producers in 7 DSUs and a carried depth in 33 of 40. Novi has no remaining DEAN stick in the block.

## 2. Open rules: recommendation, alternative, and a pad where the choice changes the sticks

Without a generator, "what changes" below is arithmetic on the cross-section (row counts from spacing and width,
shares of the drillable width closed by a rule). The cards will show the placed result.

### Rule 1. Which existing wells count (pinning and envelope)

- **Recommend: every producer whatever its age, plus spud / DUC / completed wells.** A stick is drilled later, so a
  3-month-old well is a parent by then; and a spud removes a location under the drop trigger already decided.
- Alternative: D115 (only wells 12 months or more on) for the stacked part of the envelope. The same-landing part has
  to count every well under any option, or a stick lands on a producing well.
- **Midland DSU 22309**: 30 producers, 24 of them 3 months on (6 JM, 6 tagged LSSH, 9 WCA_1, 3 WCB_1). DEAN is
  eligible at a carried 8,470 ft. Seven of those wells sit 150-350 ft above or below that depth and 74 % of the
  drillable width is within 300 ft sideways of one of them; four more are within 150 ft vertically. Every producer:
  DEAN keeps at most about one of its 5 rows. D115: none of the 24 count and DEAN gets all 5 rows through a
  3-month-old cube.
- **Ward DSU 12620**: five Crescent "UL Air Force" wells spudded 2026-04-30 to 05-24 (BS1_S, BS3_C, two WCA_2, WCB_1),
  all with surveys. If spuds do not count, sticks are placed on five wells being drilled now.
- Size: producers under 12 months on are 2,796 Delaware and 2,324 Midland (8-9 %). Not yet producing: 1,995 Delaware
  (1,007 with depth evidence) and 1,569 Midland (1,172).

### Rule 2. A stick beside a well with no depth evidence

- **Recommend the proposal on the table, with two details.** Such a well (a) pins its bench's row grid like any other
  well, and (b) closes 400 ft sideways (at least 30 % alongside) to sticks of its **formation family**, reason
  `no_depth_neighbour`, re-judged when a survey lands. Families: Avalon; BS1; BS2 (C and S); BS3 (C and S); WCA (XY,
  A1, A2); WCB; WCC; WCD. Midland: MS, JM, LSSH and DEAN each alone (MS to LSSH is about 700 ft, not one family);
  WCA_1; WCB; WCC; WCD.
- Alternatives: (A) ignore these wells altogether; (B) close 400 ft sideways to every bench.
- **Lea DSU 11331**: Devon's Chincoteague 8-32 pad, 11 wells 2-3 months on production, every one still on a planned
  survey (2 WCA_1, 3 WCA_2, 2 WCB_1, 2 WCB_2, 1 BS3_C, plus one old Cotton Draw well). (A) reads the west half of the
  DSU as open in WCA and WCB and puts sticks on an 11-well pad. Recommended: the wells hold their slots in their own
  families. (B) also takes Avalon, BS1 and BS2 rows out across the west half.
- **Ward DSU 12620**: four BS3_S producers with permit depths (11,700 / 11,800 ft). (A) leaves four BS3_S slots open
  on top of 18-29-year-old producers. (B) closes about half the DSU width to all seven benches.
- Size: no depth evidence on 3,347 of 16,980 New Mexico producers (19.7 %), 222 Delaware Texas, 417 Midland; and on
  988 of the 1,995 Delaware wells not yet producing.

### Rule 3. Two landings inside one bench

- **Recommend: detect it from the bench's own producers in the DSU.** At least 4 with depth evidence; split them into
  an upper and a lower group; two landings when the group medians are at least 150 ft apart (the envelope's
  same-landing limit), the empty band between the groups is at least half the separation, each group has at least 2
  wells and 25 % of the wells, and the groups alternate across the section (at least two switches in cross-section
  order). The bench keeps its per-bench spacing; rows alternate upper / lower; an open row takes the landing opposite
  its nearest existing same-bench neighbour; the two depths are the group medians, `tvd_basis = direct_two_landing`.
  Wells the screen calls a likely mis-tag stay in this test (bad depths do not).
- **Ruthless 11 (10785)**: 10 BS2_S wells with depth evidence split 6 at 10,538 ft and 4 at 10,862 ft, 324 ft apart,
  alternating at 8 of 8 possible switches. The 11th (#506H, planned survey) sits in the lower row by position. So two
  rows near 10,540 and 10,860 ft at the bench spacing of 498 ft. Your 10,890 ft is the median of the lower five
  including #506H's planned 10,930 ft; without it the four surveyed wells give 10,862 ft.
- Alternative (A): one row at the single surface, 10,667 ft, flagged. (B) in addition to the recommendation, carry the
  pattern into a DSU with fewer than 4 same-bench wells from wells within 1 mi. I would show (B) on the cards as an
  option, not adopt it untested: in the Lea block 12 of the 14 DSUs with 4 or more BS2_S wells show two landings
  (191-324 ft apart), so an undeveloped neighbour on one row near 10,700 ft would be wrong the same way.
- Size: 534 of 5,474 DSU x bench with 4 or more wells show two groups 150 ft or more apart; 455 are balanced and
  alternating (Midland LSSH 111, BS2_S 104, Midland WCA_1 71, BS3_C 24, Midland WCB_1 22). 21 in the pilot areas
  (`pilot_two_landings.csv` lists every tested DSU x bench; 25 pass the 150 ft test before balance and alternation).
- A lower group that is really the next bench under the wrong tag is a tag-review item. The generator never re-tags.

### Rule 4. WCA_1 / WCA_2 landings 75-150 ft apart

- **Recommend: confirm it. They are one landing for the 400 ft test**, which is what "within 150 ft vertically,
  whatever the tag" already says.
- What it does to the count. Sticks are never tested against sticks, so in open ground both benches get their rows,
  half a spacing apart (WCA density is the two per-bench densities added: 907 and 974 ft is 5.8 + 5.4 = 11.2 WPS).
  Beside an existing producer of the other member, the staggered slot clears 400 ft only where spacing is 800 ft or
  more. Basin: 3,880 DSUs carry both depths; 1,220 get one WCA landing (under 75 ft or out of order), 1,425 are
  75-150 ft apart, 1,235 over 150 ft. Of the 1,425, 195 have spacing under 800 ft.
- **Lea DSU 11331**: six WCA_2 producers at 12,092 ft, WCA_1 carried 108 ft above, spacing 684 ft. WCA_1 slots sit
  342 ft from the WCA_2 wells and are all culled beside them. **Ward DSU 12638** (122 ft apart, spacing 1,010-1,065 ft,
  stagger 505-532 ft): every staggered slot is placed.
- Alternative: treat them as two landings with no test between 75 and 150 ft. At 11331 that places WCA_1 sticks 342 ft
  sideways and 108 ft above producers. Phase 2b: same-tag parents 75-150 ft apart are drilled beside at 0.04 of the
  far rate inside 300 ft and 0.13 inside 660 ft.

### Rule 5. U-turn leg separation where bench spacing is under 990 ft

- Size first. U-turn-class DSU x bench with a depth: 8,409 Delaware (34 % under 990 ft spacing), 2,649 Midland (59 %).
  Legs across them: 45,956 at bench spacing; 41,734 at max(spacing, 990 ft) (-9 %); 36,918 once legs are paired into
  U-turns and an odd leg is dropped (-20 %; Midland -27 %). Pilot: Lea 490 -> 393 -> 334, Ward 514 -> 501 -> 424,
  Glasscock 132 -> 102 -> 84.
- **Recommend for the pilot: the plan's rule.** Legs at max(spacing, 990 ft); an odd leg, and a single open slot
  between existing wells, are not placed, each with a recorded reason; the cards and the findings show legs placed
  against legs at bench spacing. I am not confident it is the right final rule, because of the pad below.
- **Lea DSU 10809** (one-mile square, 36 producers, all about 4,600 ft straights): BS2_S has 8 wells about 500 ft
  apart and the map says 498 ft, 10 legs. The rule gives 5 rows at 990 ft, so 2 U-turns (4 legs). AVA_0 has 3 wells
  at -2,330 / -554 / +880 ft and a spacing of 1,025 ft: one open slot in each gap, no U-turn fits, zero AVA_0 sticks
  where an operator would add two one-mile wells. **Midland DSU 18898** (undeveloped square): WCA_1 at 664 ft is 7
  legs at bench spacing and 2 U-turns (4 legs) under the rule.
- Alternatives: (B) nested U-turns. Rows stay at bench spacing and a U-turn joins row i to row i+2 (leg separation
  twice the spacing, 880-1,980 ft; narvi's own note puts Novi's 214 real U-turns near 1,400-1,600 ft), neighbours
  turning at opposite ends. Keeps the density. It needs a narvi engine change (it pairs adjacent rows only) and your
  call that it is drillable. (C) keep an odd leg or a single open slot as a short straight, flagged, which brings back
  the 4,600 ft laterals the plan set out to remove.
- Our producer data cannot calibrate this: 9 of 60,834 well sticks look like U-turns.

### Rule 6. Lithology pairs (BS2_C / BS2_S, BS3_C / BS3_S)

- **Finding: they are not at one landing.** On the landing chain BS2_C sits a median 462 ft above BS2_S (743 DSUs) and
  BS3_C 534 ft above BS3_S (2,380 DSUs); 1.1 % and 3.2 % of those are under 75 ft or out of order (phase 1c
  `order_pairs_screened.csv`). In the pilot DSUs the BS2 pair is never closer than 296 ft; the BS3 pair is under
  75 ft in 6 of 74.
- **Recommend: no pair rule.** They are ordinary adjacent benches; the few DSUs under 75 ft go through the stack
  reconciliation already decided.
- Alternative (the plan's proposal): one shared landing, only the locally developed member gets a row.
- **Ward DSU 12613**: 4 BS3_C producers at 11,000 ft and 3 BS3_S at 11,477 ft. The pair rule gives one row where
  seven wells sit at two depths 476 ft apart. Lea 10684: 3 BS2_C at 10,460 ft and 10 BS2_S at 10,865 ft. In the pilot,
  16 DSUs have producers in both BS3 members and 7 in both BS2 members.
- If you had a specific area in mind where the carbonate and the sand share a depth, name it and I will look there.

### Rule 7. Sliver floor

- Size. DSU x bench by the share of the DSU inside the extent (Delaware / Midland): under 5 %: 469 / 334; 5-10 %:
  244 / 160; 10-25 %: 549 / 336; 25-50 %: 643 / 468; 50 % to under 100 %: 1,754 / 1,242; all of it: 26,060 / 17,295.
  The share holding a same-bench producer climbs steadily (5-7 % under 10 %, 9-11 % at 25-50 %, 16-18 % at 50-100 %,
  42-47 % fully inside). The data show no step to hang a floor on.
- **Recommend 10 % of the DSU's area** (the phase 0 sliver definition). It drops 1,207 of 49,554 DSU x bench (2.4 %).
  No exception for a DSU holding a same-bench producer (70 of them): the extent is where the bench is a target.
- Alternatives: 25 % (drops 2,092, 4.2 %); or no floor.
- **Ward DSU 12639**: 2.1 % of the DSU is inside the hand-drawn WCXY extent, with a direct WCXY depth (one of its 16
  producers is tagged WCXY). No floor: a full WCXY row set across a DSU the extent only clips. **Midland DSU 22314**:
  0.2 % inside the WCB_2 extent, direct depth, 675 ft spacing.

### Rule 8. Near-square DSUs

- **The threshold does not matter.** DSU shapes are bimodal: among DSUs with 3 or more wells every near-square one has
  an aspect under 1.02 (659 Delaware, 102 Midland), 7 Midland DSUs fall between 1.02 and 1.25 and no Delaware one, and
  the next class starts at 1.25. Any threshold from 1.05 to 1.25 classes them the same; keep 1.15.
- In a square the long axis is noise: wells follow it in 69 % of Delaware and 42 % of Midland squares. Where a square
  holds 3 or more wells they are coherent in 86 % / 89 % and run along one of the polygon's sides within 5 deg in
  88 % / 87 %. Most squares hold no well: Delaware 1,081 with none, 391 with 1-2, 659 with 3 or more; Midland 1,175 /
  160 / 107.
- **Recommend this order for a near-square DSU**: (1) wells inside the DSU, any bench, if coherent (R >= 0.85);
  (2) wells within 1 mi, then 2 mi (at least 3, R >= 0.85); (3) where those are not coherent, the polygon side that
  at least two-thirds of the wells within 1 mi run along (within 15 deg); (4) else the long axis, flagged
  `square_unresolved` and listed. Sticks are placed in every case: in a square the count and the lateral are the same
  either way. The wells choose WHICH side; the azimuth used is that side's bearing, so rows stay parallel to the lease
  line.
- Alternative (the plan as written): surrounding PDP not coherent -> flagged, no sticks.
- **Ward DSU 12627** (aspect 1.003, sides at 163.7 and 73.7 deg): two wells inside at 169.6 deg; neighbours not
  coherent at 1, 2 or 3 mi (R 0.20 / 0.49 / 0.39 on 30 / 84 / 176 wells) because three grids meet. Plan rule: no
  sticks. Recommended: the inside wells decide, 163.7 deg. **Ward DSU 11523**: five wells inside at 42.2 deg (R 1.00)
  while the 1-mi mean is 12.9 deg at R 0.47, a bearing nobody drilled. Easy case: Lea 14157, undeveloped, 68 wells
  within 1 mi at 1.2 deg, R 0.98.

### Rule 9. How narvi's engine is imported

- **Recommend pinning narvi by commit in `requirements-dealintake.txt`**, the pattern already used for
  `blueox-boxfit`: `narvi @ git+https://github.com/mastmj812/narvi.git@<sha>`. The narvi repo is public and requires
  Python 3.12 or later, which is what CI runs. The canonical copy stays in narvi; a test checks the installed narvi's
  gunbarrel rule against our golden table. Cost: `import narvi` runs its whole `__init__`, so CI also installs pyshp
  and psycopg-pool. A bump needs a commit merged on narvi `master`.
- Alternatives: a vendored copy of `generate.py`, `placement.py` and `records.py` (one more copy of the gunbarrel rule;
  not done without your say); or a git submodule.
- What the engine already does: `Zone.offset_ft` pins a bench's row grid at a stored gunbarrel offset, per-bench
  spacing and well type, U-turn pairing of adjacent rows, the 3-D inter-zone check. The generator would compute every
  bench's offset itself and pass it pinned, so no narvi change is needed for the pilot. Not in the engine: nested
  U-turns (rule 5 B).
- narvi works in UTM 13N everywhere. The Midland block is in zone 14: convergence 1.72 deg (handled by
  `true_to_grid`) and a scale of 1.00076, so lengths read 0.08 % long (8 ft on 10,000 ft). Ward 0.89 deg, Lea 0.71 deg.

### Rule 10 (not on your list). Adjacent benches with different spacings

- **Finding.** Per-bench spacing means adjacent benches seldom share a grid. Of adjacent bench pairs 75-300 ft apart
  vertically (10,618 Delaware, 7,221 Midland DSU pairs) spacing differs by more than 15 % in 46 % / 57 %. A
  half-spacing stagger then cannot hold across a DSU: at the median ratio (1.14 / 1.20) rows drift from staggered to
  stacked inside a mile of width. Pilot: Glasscock DEAN at 955 ft between LSSH at 742 ft (214 ft above) and WCA_1 at
  666 ft (206 ft below); Lea BS3_S at 1,249 ft over WCA_1 at 681 ft (217 ft); Ward is mild (median ratio 1.07).
- (A) narvi as it is: each bench on its own grid, alternate benches shifted half a spacing at the anchor, rows closer
  than 300 ft in 3-D only reported. Bar I2(b) then cannot be a zero-violation bar.
- **(B) recommended.** Benches are placed in order of trust (pinned by existing wells, then direct depth, then
  carried). An adjacent bench within 300 ft vertically whose spacing is within 15 % of the lead's takes the lead's
  spacing and sits in its gaps, recorded in `spacing_basis`. Otherwise it keeps its own spacing, its grid takes the
  best phase, and a row still under 300 ft in 3-D from a lead row is not placed (reason `stagger`).
- Stated plainly: (B) is a stick-against-stick test. It is the stagger rule, not the envelope, but it means the middle
  bench of a tight stack (DEAN between LSSH and WCA_1) loses rows in undeveloped DSUs too. **Midland DSU 18898**
  (undeveloped): LSSH 775 ft, DEAN 827 ft, WCA_1 664 ft. (A) places every row, and with those three spacings some
  DEAN rows can end up about 210 ft directly under or over a neighbour's row. (B) puts DEAN on the LSSH grid (ratio 1.07) in its gaps, then drops the
  DEAN rows within about 220 ft sideways of a WCA_1 row.
- I also need your reading of "never under 300 ft": 3-D as narvi measures it (what `BARS.md` assumes), or 300 ft
  sideways.

## 3. Bars and back-test

`BARS.md`. Nine generator invariants at zero violations (envelope, stagger, order and 75 ft, well type at 7,000 ft,
inside the DSU, provenance on every stick, a ledger with a reason per culled row, the gunbarrel golden table,
repeatability), and a back-test with the cutoff at 2023-01-01: 722 producers since then in 63 pilot DSUs. A well lands
on a slot at the same bench, within min(330 ft, half the spacing) sideways and 150 ft vertically, matched one-to-one.
Bars: 60 % of wells on a slot (50 % in each area); at most 10 % of wells on a bench that got no row; leg count within
1 of the wells drilled in 70 % of DSU x bench drilled across since the cutoff; at most 25 % of slots unused there.
Limits are stated in the file: tags, polygons and extents are today's.

## 4. Seen on the way (tag review, nothing touched)

- Midland 22309: six wells tagged LSSH land at 8,335 ft, 284 ft below the LSSH surface (8,051 ft) and 135 ft above the
  carried DEAN depth.
- Ward 12620: a well tagged WCXY at 12,650 ft where the WCA lands near 11,750 ft.
- Lea 11331: the WCB_1 direct surface (12,038 ft) is above the WCA_2 direct surface (12,092 ft): a stack
  reconciliation case for the cards.
- Midland two-landing WCA_1 (22308: 6 wells at 8,647 ft and 6 at 8,850 ft, alternating): a second WCA_1 row or WCB_1
  under the wrong tag.

The formation-tag cutover decision is 2026-11-16. This cache holds live tags pulled 2026-11-14. If step 2 runs past the
cutover the cache is re-pulled before any number goes in the findings.

## Decisions asked

1. The three pilot areas.
2. Rules 1-10: the recommendation or the alternative for each. Rule 5 and rule 10 are the two I am least sure of.
3. The bars in `BARS.md`, including the reading of "never under 300 ft" and the 2023-01-01 cutoff.
