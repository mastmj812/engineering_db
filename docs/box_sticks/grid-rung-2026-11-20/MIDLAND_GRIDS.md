# The Midland grids: a first evaluation, as done for the Delaware

2026-11-20, read-only: the grid files delivered today (`Grids/Midland/11-20-26`), live wells, the cache of today's pull, and
one read-only query of set 17. Nothing changed; generator 0.13 does not read these grids. Exploratory: no bars were written
for this, and the scripts that produced it are scratch, not committed. If it goes forward it becomes a bars-first change.

## What was delivered

18 structure surfaces, each with a grid (about 5,000 ft nodes), its control points (`_data.xyz`) and contours. Same file
format and coordinate system as the Delaware set. Control points per surface: 1,152 to 7,239.

Used here (11 surfaces): Upper Spraberry, Middle Spraberry, Jo Mill, Jo Mill Sand, Lower Spraberry Shale, Dean,
Wolfcamp A, B, C, D, Strawn. Not used: Clearfork Lime, Barnett, Meramec, Mississippian, Woodford, Devonian (few or no tagged
horizontals), and **Wolfcamp B Lower, which covers only 10 % of the wells**.

Datum: the surfaces are depths on the same datum as well TVD. Tagged producers sit where they should, for example Wolfcamp A
wells a median 129 ft below the Wolfcamp A top and 146 ft above the Wolfcamp B top.

## Intervals

| Bench | Top | Base | Median gridded thickness at wells |
|---|---|---|---|
| US | Upper Spraberry | Middle Spraberry | 234 ft |
| MS | Middle Spraberry | Jo Mill | 300 ft |
| JM | Jo Mill | Lower Spraberry Shale | 386 ft |
| LSSH | Lower Spraberry Shale | Dean | 397 ft |
| DEAN | Dean | Wolfcamp A | 180 ft |
| WCA_1 | Wolfcamp A | Wolfcamp B | 285 ft |
| WCB_1 | Wolfcamp B | Wolfcamp B + 236 ft | 236 ft (by construction) |
| WCB_2 | Wolfcamp B + 236 ft | Wolfcamp C | 104 ft |
| WCC | Wolfcamp C | Wolfcamp D | 577 ft |
| WCD | Wolfcamp D | Strawn | 323 ft |

**The WCB_1 / WCB_2 split is mine, not the geologist's.** His Wolfcamp B Lower surface is too small to use, so the split is
a constant 236 ft below the Wolfcamp B top: the midpoint between where WCB_1 wells land (a median 121 ft below the B top)
and where WCB_2 wells land (351 ft below). It is the same construction as the Delaware's B1 + 214 ft. With it, the Wolfcamp
C top falls above the split at 11.8 % of wells, so the WCB_2 interval is thin and partly inverted. Other intervals cross at
under 0.4 % of wells.

## 1. As a witness on tags

Producing wells with depth evidence, more than 25 ft from any surface: share in their own gridded interval.

| Bench | Wells | In own interval |
|---|---|---|
| LSSH | 4,600 | 95.8 % |
| WCD | 770 | 95.8 % |
| WCA_1 | 5,423 | 95.2 % |
| JM | 1,572 | 95.0 % |
| WCB_1 | 4,189 | 89.5 % |
| MS | 1,295 | 88.7 % |
| DEAN | 700 | 82.6 % |
| US | 38 | 73.7 % |
| WCB_2 | 1,599 | 72.1 % |
| WCC | 315 | 66.3 % |

Good witnesses for JM, LSSH, WCA_1 and WCD, usable for WCB_1 and MS. Weak for WCB_2 and WCC, which is the split and the
Wolfcamp C top; DEAN leaks mostly into WCA_1 (139 of 900 wells).

## 2. As a landing predictor, against the generator's offset and bracket rungs

Same test as the Delaware: each evidence well predicted with every well within 5 miles removed; grid = gridded top + the
regional fraction (same-bench wells 5 to 15 miles away) x gridded thickness. Median absolute error in ft (90th percentile).

| Bench | Wells scored | Grid | Offset rung | Grid wins | Bracket rung (grid on the same wells) |
|---|---|---|---|---|---|
| MS | 1,587 | 36 (99) | 39 (115) | yes | n/a |
| JM | 1,758 | 43 (135) | 45 (142) | yes | 46 (44) |
| LSSH | 4,925 | 48 (139) | 54 (148) | yes | 51 (48) |
| DEAN | 811 | 41 (138) | 45 (155) | yes | 39 (40) |
| WCA_1 | 6,832 | 47 (167) | 47 (128) | **no** (worse tail) | 41 (39) |
| WCB_1 | 5,753 | 52 (151) | 47 (132) | **no** | 46 (52) |
| WCB_2 | 1,747 | 58 (143) | 62 (149) | yes | 60 (52) |
| WCC | 348 | 183 (465) | 175 (503) | **no** (both poor) | n/a |
| WCD | 855 | 43 (143) | 87 (239) | **yes, by half** | n/a |

"Grid wins" uses the Delaware bar: median no worse, and 90th percentile no more than 10 ft worse.

The picture differs from the Delaware. The Midland's offset rung is already good (39 to 62 ft on eight of nine benches),
because the section is regular, so the grid gains only 2 to 6 ft where it wins. The one large gain is **WCD: 43 ft against
87 ft**. On WCA_1 and WCB_1, the two biggest benches, the grid is no better.

## 3. As a check on carried landings

Set 17's landings (11,696 DSU x bench with sticks and a gridded interval, 30,898 sticks) that fall outside their own
gridded interval:

| Rung | DSU x bench | Outside by more than 50 ft | Outside by more than 150 ft | Sticks outside by more than 150 ft |
|---|---|---|---|---|
| direct | 5,739 | 5.0 % | 1.7 % | 236 |
| thickness | 3,726 | 7.7 % | 2.1 % | 234 |
| bracket | 546 | 11.0 % | 1.8 % | 31 |
| offset | 1,685 | 17.6 % | 10.6 % | 565 |

365 DSU x bench (1,066 sticks) sit more than 150 ft outside. As in the Delaware, the offset rung is about five times
worse than the others: one landing in ten.

## Reading

- The Midland grids are sound enough to use the same way: datum right, nine in ten tags agree on the main benches.
- The case for a **grid rung** is narrower than in the Delaware: clear for WCD, marginal for MS, JM, LSSH, DEAN and WCB_2,
  and no case for WCA_1, WCB_1 or WCC.
- The case for the **bound** looks the same as in the Delaware: the offset rung leaves one landing in ten more than 150 ft
  outside its own bench. Whether pulling those to the grid helps was not tested here (that is bar G2).
- WCB_2 and WCC need either a usable Wolfcamp B Lower surface from the geologist or a decision on the 236 ft split before
  the grid can say anything firm about them.

## If this goes forward

A bars-first generator change like 0.13: per-bench G1 against the offset rung, G2 for the bound, the Delaware untouched,
and the same sequence of gos (schema already allows the rung; a pull, a store, a record flip). The grid module would need
a per-basin table of surfaces and intervals; today it is Delaware only.
