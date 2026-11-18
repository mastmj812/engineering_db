# BOX sticks phase 3b: basin-wide run against Novi (gate 3b)

2026-11-15. Generator `box_sticks_0.7_pilot`, the rules of gate 3a unchanged. Live tags, pulled 2026-11-14 (before the
2026-11-16 formation-tag cutover decision). Read-only; **nothing is stored**: the sticks exist as files only.
Numbers: `basin_summary.json`, `basin.csv`, `basin_bench.csv`, `basin_county.csv`, `dsu_bench.csv.gz` (one row per
DSU x bench). Run: `scripts/box_sticks_phase3_basin.py`; comparison: `scripts/box_sticks_phase3_basin_report.py`.

## Result

| | Delaware | Midland |
|---|---|---|
| 2026Q3 DSU polygons | 8,256 | 8,329 |
| ... touched by at least one BOX extent (run) | 5,072 | 4,385 |
| DSUs straight / U-turn / no drillable row | 3,073 / 1,491 / 508 | 3,140 / 594 / 651 |
| DSU x bench | 29,719 | 19,835 |
| ... with BOX sticks | 18,472 | 12,725 |
| ... with no row, by bench reason | 5,967 | 1,847 |
| **BOX sticks** (straight / U-turn) | **46,002** (37,836 / 8,166) | **34,045** (30,402 / 3,643) |
| BOX legs | 54,168 | 37,688 |
| BOX completed lateral | 441.5 MM ft | 350.4 MM ft |
| Novi remaining sticks, same DSUs and benches | 55,627 | 35,777 |
| Novi lateral | 492.6 MM ft | 365.4 MM ft |
| Existing producers on those benches | 28,716 | 26,903 |
| Errors / invariant violations (I1-I8) | 0 / 0 | 0 / 0 |

BOX places 83 % of the Novi stick count and 90 % of its footage in the Delaware, 95 % and 96 % in the Midland, on the
DSUs and benches where both exist. Run time 564 s and 488 s.

Grain: a Novi stick is counted in its main DSU (largest share of its line, >= 30 %), when it is remaining (status NULL /
remaining_pud / conflict) and its bench has a BOX extent touching that DSU.

### Per DSU

| BOX sticks minus Novi sticks, per DSU | Delaware (5,072) | Midland (4,385) |
|---|---|---|
| BOX more | 1,714 | 1,762 |
| Equal | 629 | 838 |
| Novi more | 2,729 | 1,785 |
| BOX none, Novi some | 421 | 380 |
| Novi none, BOX some | 173 | 368 |
| P10 / P25 / median / P75 / P90 | -9 / -5 / -1 / +2 / +5 | -8 / -3 / 0 / +2 / +6 |

### TVD bust (stick TVD minus the median depth of the same-bench producers in the DSU)

One value per DSU x bench with depth-evidenced producers; two-landing units left out (251 Delaware, 261 Midland).

| | Delaware | Midland |
|---|---|---|
| BOX: units / median abs / P90 abs | 5,235 / 28 ft / 118 ft | 4,052 / 22 ft / 95 ft |
| Novi: units / median abs / P90 abs | 4,952 / 100 ft / 458 ft | 3,828 / 62 ft / 211 ft |
| Same units both: BOX / Novi median abs | 3,107: 29 / 103 ft | 2,746: 22 / 60 ft |

**This favours BOX by construction** where the rung is direct (the depth came from those producers). The unbiased
figure is the phase 3a back-test: 59 ft direct, 61-118 ft carried. DSU x bench with sticks by rung: Delaware direct
7,992, thickness 7,045, offset 2,526, bracket 909; Midland 6,291 / 4,054 / 1,826 / 554.

### Per bench (BOX sticks against Novi sticks; full table in `basin_bench.csv`)

| Delaware | DSU x bench | BOX | Novi | BOX MM ft | Novi MM ft | BOX bust | Novi bust |
|---|---|---|---|---|---|---|---|
| AVA_0 | 244 | 484 | 793 | 4.3 | 6.3 | 21 | 37 |
| AVA_1 | 408 | 1,063 | 1,631 | 10.4 | 14.5 | 29 | 73 |
| AVA_2 | 482 | 1,169 | 3,310 | 11.4 | 30.1 | 23 | 88 |
| BS1_S | 2,359 | 5,183 | 5,650 | 50.0 | 50.7 | 32 | 103 |
| BS2_C | 1,169 | 2,690 | 3,462 | 25.5 | 30.1 | 33 | 78 |
| BS2_S | 2,401 | 4,085 | 8,088 | 39.4 | 71.5 | 34 | 87 |
| BS3_C | 2,840 | 6,677 | 8,478 | 64.7 | 74.4 | 26 | 102 |
| BS3_S | 3,608 | 4,710 | 10,313 | 45.3 | 91.6 | 30 | 75 |
| WCXY | 1,299 | 454 | 1,586 | 4.3 | 13.5 | 22 | 212 |
| WCA_1 | 4,457 | 3,603 | 1,150 | 34.1 | 10.8 | 24 | 60 |
| WCA_2 | 4,457 | 3,333 | 996 | 32.0 | 9.5 | 28 | 65 |
| WCB_1 | 2,664 | 4,678 | 4,495 | 44.3 | 38.7 | 29 | 104 |
| WCB_2 | 2,280 | 5,219 | 2,816 | 49.3 | 24.9 | 21 | 78 |
| WCC | 1,051 | 2,654 | 2,859 | 26.5 | 26.2 | 31 | 762 |

| Midland | DSU x bench | BOX | Novi | BOX MM ft | Novi MM ft | BOX bust | Novi bust |
|---|---|---|---|---|---|---|---|
| MS | 1,902 | 4,154 | 4,595 | 42.7 | 48.1 | 16 | 42 |
| JM | 1,826 | 3,454 | 4,536 | 35.0 | 46.6 | 15 | 67 |
| LSSH | 2,821 | 5,641 | 7,807 | 59.2 | 80.8 | 24 | 54 |
| DEAN | 2,271 | 2,436 | 1,448 | 25.3 | 14.7 | 17 | 66 |
| WCA_1 | 3,593 | 5,349 | 5,728 | 54.9 | 56.1 | 25 | 68 |
| WCB_1 | 3,397 | 4,703 | 6,087 | 47.6 | 61.6 | 24 | 72 |
| WCB_2 | 1,357 | 2,056 | 894 | 20.8 | 8.7 | 27 | 73 |
| WCC | 494 | 1,007 | 881 | 10.3 | 9.3 | 20 | 143 |
| WCD | 2,174 | 5,245 | 3,801 | 54.7 | 39.6 | 15 | 45 |

Bust = median absolute, ft.

- **Where Novi has far more:** Delaware BS3_S (10,313 against 4,710), BS2_S (8,088 against 4,085), AVA_2 (3,310 against
  1,169), WCXY (1,586 against 454). BS2_S and BS3_S are the developed benches: 3,073 and 2,695 rows closed as same
  landing, and BS3_S another 2,186 as stacked.
- **Where BOX has far more:** Delaware WCA_1 and WCA_2 (6,936 against 2,146 together), WCB_2 (5,219 against 2,816);
  Midland DEAN (2,436 against 1,448), WCB_2 (2,056 against 894), WCD (5,245 against 3,801).
- **Delaware WCC: the Novi sticks sit 762 ft (median) from the WCC producers in their own DSU.** 357 units. BOX 31 ft.
- **WCXY: no row in 592 of 1,299 DSU x bench** (no landing depth; WCXY takes direct control only).
- **Midland DEAN: 2,906 rows closed as stacked** and 1,770 as same landing against 2,801 legs placed.

### Benches with no row, and rows not placed

| Bench gets no row | Delaware | Midland |
|---|---|---|
| WCA rule: one member carries the row set | 2,621 | 0 |
| No landing depth | 1,830 | 1,137 |
| Sliver (extent under 10 % of the DSU) | 713 | 494 |
| Dropped in stack reconciliation | 558 | 216 |
| WCA one landing (members under 75 ft apart) | 245 | 0 |

| Row not placed | Delaware | Midland |
|---|---|---|
| Same landing, within 400 ft of an existing well | 22,671 | 22,943 |
| Stacked, within 300 ft | 7,851 | 12,208 |
| U-turn leg with no partner | 2,014 | 466 |
| Outside the clear width | 1,815 | 1,312 |
| Row count reduced to fit | 366 | 153 |
| Straight row under 7,000 ft | 252 | 77 |
| No-depth well, bench has no landing in the DSU | 222 | 7 |

Azimuth basis, DSUs: wells in the DSU 3,682 Delaware / 3,073 Midland; long axis 907 / 828; 6-mi cell 428 / 384; county
50 / 100; near-square unresolved 5 / 0.

## What the comparison does not cover

| Remaining Novi sticks | Delaware | Midland |
|---|---|---|
| All | 166,636 | 85,811 |
| Compared above (bench has a BOX extent touching the DSU of the stick) | 55,627 | 35,777 |
| In a DSU where that bench has no BOX extent | 110,978 | 50,029 |
| In no DSU (under 30 % of the line in any polygon) | 31 | 5 |

Two thirds of the remaining Delaware Novi sticks and 58 % of the Midland ones are on a bench whose BOX extent does not
reach their DSU. Largest groups: Delaware WDFD 15,845, WCC 14,311, WCXY 12,829, BS2_C 10,212, BS2_S 9,615; Midland BRNT
11,041, WCC 7,661, WCA_1 6,538, WCD 4,648. These get no BOX stick by the bench-eligibility decision (extent intersects
the DSU), and most carry no forecast in the record runs today (phase 2b).

Polygons with no BOX extent at all: 3,184 Delaware, 3,944 Midland.

## Open item closed: "35,929 Midland Novi sticks have their midpoint outside every 2026Q3 polygon"

Not real. The `x`, `y` on the stick rows is not the midpoint of the stick: it sits a median 5,276 ft (Midland) and
5,176 ft (Delaware) from the midpoint of the stick geometry, half a 2-mile lateral, so it is an END of the stick. A
stick end lies on the DSU line and often falls outside it. Measured on the stick geometry, **166 of 85,811** Midland
sticks and 90 of 166,636 Delaware sticks have their midpoint outside every polygon, and 5 / 31 have under 30 % of their
line in any DSU. The phase 2a count (35,929; 35,271 on the remaining set of today) tested the end point.

## Limits

- The back-test of phase 3a failed T1, T3 and T4; this run is the same generator. Counts are right in total and off by
  20-30 % in a typical DSU x bench; row positions in benches with no existing well are arbitrary.
- Stick counts in developed DSUs overstate practical inventory (rows between parents stay; gate 3a).
- Tags are the 2026-11-14 live tags. If the cutover on 2026-11-16 changes tags, the run is repeated before anything
  is stored.
- Open from gate 3a and untouched here: the 30 % alongside threshold; a second landing by campaign inside one bench.

Not started: phase 4 (storage; DDL needs an explicit go).
