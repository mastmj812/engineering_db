# BOX sticks, phase 0: baseline evidence (2026-11-12)

Read-only. `python -m scripts.box_sticks_phase0 --out docs/box_sticks/phase0-2026-11-12`. Plan: `docs/box_sticks_plan.md`.

Grain and filters: 257,397 Novi PUD + RES sticks (2026Q3 vintage, with geometry and a `formation_blueox`);
56,842 evidence wells (horizontal producers, Delaware + Midland; planned surveys, round-100 TVDs without a survey
and depths under 4,000 ft excluded; depth = survey lateral median TVD, else `tvd_ft`); 16,585 Novi 2026Q3 DSU
polygons (`raw_novi_intel.pads`); the 21 BOX record extents.

## 0a. TVD bust: Novi stick TVD minus same-bench producer landing depth

Bust is measured only where a stick has local control: >= 3 same-code evidence wells within 2 mi and the nearest
within 1 mi. **That is 42,810 sticks, 17 % of the universe** (Delaware 15 %, Midland 20 %). The other 83 % have no
same-bench producer close enough to judge.

| Basin | Sticks with control | Median bust | Median abs. bust | Beyond 150 ft | Beyond 300 ft |
|---|---|---|---|---|---|
| Delaware | 25,575 | +21 ft | 94 ft | 35 % | 16 % |
| Midland | 17,235 | +40 ft | 56 ft | 16 % | 3 % |

Positive = Novi deeper than the producers. Worst benches (full table `bust_by_bench.csv`, maps `bust_map_*.png`):

| Basin | Bench | Sticks with control | Median bust | Beyond 150 ft |
|---|---|---|---|---|
| Delaware | WCC | 1,550 | +846 ft | 94 % |
| Delaware | WCXY | 1,115 | +169 ft | 60 % |
| Delaware | WDFD | 306 | +1 ft (P10 -1,053, P90 +672) | 78 % |
| Delaware | WCB_1 | 2,487 | +78 ft | 35 % |
| Delaware | AVA_2 / BS1_S | 2,151 / 1,562 | +30 / +4 ft | 35 % |
| Midland | WCC | 679 | +140 ft | 51 % |
| Midland | WCA_1 / WCB_1 | 3,913 / 3,797 | +37 / +61 ft | 20 % |

- Delaware WCC is the gross offender and it is systematic, not noise: Reeves +2,138 ft (n 346), Loving +1,386 ft,
  Culberson +902 ft, Eddy +585 ft (`bust_by_bench_county.csv`). A bust that size is a different bench, so this
  mixes Novi's depth with the bench we infer onto the stick (sql/19); either way the stick is unusable as placed.
- Even the well-behaved Delaware benches (BS2_S, BS3_S, WCB_2) have 25-28 % of sticks more than 150 ft off.
- Midland is tighter everywhere except WCC, with a consistent +30 to +60 ft deep bias.
- RES sticks are far worse where they can be measured (Delaware median +282 ft, 70 % beyond 150 ft) but only
  1.4 % of them have control at all.
- The shadow tag rule barely moves this (`bust_live_vs_shadow_tags.csv`): it changes about 1,000 well tags.
  The bust is a Novi stick problem, not a producer-tag problem.

## 0b. DSU polygons

| | Delaware | Midland |
|---|---|---|
| Polygons | 8,256 | 8,329 |
| With no Novi well | 3,772 | 3,809 |
| Median area | 960 ac | 1,265 ac |
| Overlapping another polygon by >= 10 % of its area | 0.24 % | 0.30 % |
| Near-square (long side / short side < 1.15) | 25.8 % | 17.3 % |
| Non-rectangular (fills < 90 % of its bounding rectangle) | 0 % | 0 % |

- The 2026Q3 polygons tile the basin: they are rectangles and essentially do not overlap.
- They cover 97-100 % of every BOX record extent, and under 1.5 % of >= 2016 producers of any bench sit outside
  every polygon (`dsu_extent_coverage.csv`).
- Extent edges: per extent, 20-80 polygons have under 10 % of their area inside it (slivers) and 50-215 have
  under half. This is the population the "intersect counts" rule decides.

## 0c. Lateral length

| | Delaware | Midland |
|---|---|---|
| Novi sticks under 6,000 ft | 57,518 (33.8 %) | 17,873 (20.5 %) |
| Polygons whose straight lateral would be under 7,000 ft (U-turn class) | 2,739 (33.2 %) | 1,687 (20.3 %) |
| Novi median lateral in those polygons | 5,080 ft | 5,280 ft |
| BOX U-turn completed lateral in those polygons (two legs, 330 ft setbacks) | 9,262 ft | 9,268 ft |

- The short sticks are almost exactly the 1-mile polygons: 96 % (Delaware) and 99.5 % (Midland) of Novi sticks in
  the U-turn class are under 6,000 ft.
- Those 1-mile polygons are mostly square sections (median 639 ac), so the U-turn class and the near-square class
  are largely the same DSUs: orientation there has to come from surrounding producers, not the polygon.
- Outside that class the two agree: Novi median 10,360 / 10,560 ft vs 9,922 / 9,909 ft straight.

## What this means for the plan

1. **Local control is thin.** Only 17 % of today's stick positions have a same-bench producer within 1 mile. The
   Phase 1 landing surface cannot be "direct nodes only" for non-pooled benches without leaving most of each extent
   with no depth. The existing thickness method reaches 5 mi; how much of each extent it covers, and at what
   hold-out error, is the first thing Phase 1 must show.
2. **The polygons are a usable frame**: no overlap handling needed, near-complete extent coverage.
3. **About a quarter of Delaware and a sixth of Midland DSUs are near-square**, so the PDP-orientation fallback is
   a main path, not an edge case.
4. The tag cutover does not change the bust picture; Phase 0 does not need re-running after 11-16.

Not committed: `bust_sticks.csv.gz` (per-stick rows, regenerate with the script).
