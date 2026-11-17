# BOX sticks: the whole chain re-run on the post-cutover tags

2026-11-17. The formation-tag switch went ON 2026-11-16 19:58 UTC. Everything upstream of the generator and the
generator itself were re-run on a fresh pull (2026-11-17): phases 0, 1, 1b, 1c (landing depth), 2a (spacing), 2b
(envelopes), the phase 3 frame, the pilot, the back-test, both basins and the review cards. Generator
`box_sticks_0.9_pilot`, unchanged. **No decided threshold was reopened** (floor 1,320 ft, cap 440 ft, candidate D,
the bars); this is a re-measurement. Read-only; **nothing is stored**.

The pre-cutover folders (`phase0-2026-11-12` ... `phase3d-2026-11-16`) stay as the record of what was reviewed. The
only code change: `scripts/box_sticks_phase1c` reads its method rankings from `phase1/` and `phase1b/` here instead of
the 2026-11-12 files.

Layout: `phase0/`, `phase1/`, `phase1b/`, `phase1c/`, `phase2a/`, `phase2b/` mirror the dated folders of the same
name; `phase3/` holds the pilot files, `generated/`, `backtest/`, `cards/` and the basin-wide files
(`basin*.csv`, `basin_summary.json`, `dsu_bench.csv.gz`). `old_vs_new_by_bench.csv` is the per-bench table below.
`phase0/dsu_polygons.csv` is not repeated (byte-identical to `phase0-2026-11-12/`).

## What the pull holds

Grain: wells (api10), against the 2026-11-14 pull the earlier phases ran on.

- 1,313 of 60,865 common wells carry a different tag (Delaware 567, Midland 746). Largest moves: Midland WCA_1 -> WCB_1
  466, Midland LSSH -> JM 174, Delaware BS3_C -> BS2_S 147, Delaware BS3_S -> WCXY 73, Midland WCB_1 -> WCA_1 42,
  Delaware OTHER -> AVA_0 41.
- 58 wells added, 3 dropped. 475 of 257,397 Novi sticks re-tagged. Extents (21) and DSU polygons (16,585) unchanged.
- The pull is three days newer, so it also carries three nights of Novi revisions (the spacing column is rewritten
  nightly). The differences below are tags plus those revisions; they are not separated.

## Sticks, old against new

Grain: sticks (legs), DSU x bench. Old = `phase3d-2026-11-16` (0.9, tags pulled 2026-11-14). Same filters.

| | Old | New | Change |
|---|---|---|---|
| **Delaware sticks** (legs; lateral) | 46,499 (54,764; 446.4 MM ft) | **46,690** (54,964; 448.3 MM ft) | +191 (+0.4 %) |
| **Midland sticks** (legs; lateral) | 34,045 (37,688; 350.4 MM ft) | **33,791** (37,432; 347.8 MM ft) | -254 (-0.7 %) |
| Both basins | 80,544 | 80,481 | -63 |
| Novi remaining sticks, same DSUs and benches | 55,627 / 35,777 | 55,618 / 35,827 | -9 / +50 |
| DSU x bench with BOX sticks | 18,705 / 12,725 | 18,720 / 12,700 | +15 / -25 |
| Pilot sticks, 114 DSUs | 1,537 | 1,534 | -3 |
| Errors / invariant violations | 0 / 0 | 0 / 0 | |

The net is small; the churn under it is not. 2,997 of 49,554 DSU x bench changed their stick count (6.0 %):
Delaware +1,121 / -930, Midland +861 / -1,115.

Most of the change is **not** in the DSUs that hold a re-tagged well:

| DSUs | Delaware net (gained / lost) | Midland net (gained / lost) |
|---|---|---|
| Hold a re-tagged well (383 / 425 DSUs) | +42 (+320 / -278) | -36 (+223 / -259) |
| A well added or dropped, no re-tag (5 / 13) | +4 | -13 |
| Neither (4,684 / 3,947) | +145 (+795 / -650) | -205 (+638 / -843) |

The landing-depth and spacing surfaces are regional, so a re-tag moves the depth or the spacing of DSUs miles away, and
the nightly spacing revisions land everywhere. This run does not split those two causes.

Per bench (`old_vs_new_by_bench.csv`). Producers = producing wells on the bench in the DSUs.

| Basin | Bench | Producers old -> new | Sticks old -> new | Change |
|---|---|---|---|---|
| Delaware | AVA_0 | 351 -> 400 | 484 -> 489 | +5 |
| | AVA_1 | 500 -> 502 | 1,063 -> 1,088 | +25 |
| | AVA_2 | 401 -> 395 | 1,169 -> 1,171 | +2 |
| | BS1_S | 1,186 -> 1,184 | 5,183 -> 5,228 | +45 |
| | BS2_C | 580 -> 570 | 2,690 -> 2,701 | +11 |
| | BS2_S | 4,653 -> 4,850 | 4,085 -> 4,037 | -48 |
| | BS3_C | 1,755 -> 1,656 | 6,676 -> 6,702 | +26 |
| | BS3_S | 3,041 -> 2,974 | 4,706 -> 4,781 | +75 |
| | WCA_1 | 5,926 -> 5,941 | 3,601 -> 3,633 | +32 |
| | WCA_2 | 4,757 -> 4,735 | 3,325 -> 3,269 | -56 |
| | WCB_1 | 1,851 -> 1,878 | 4,681 -> 4,712 | +31 |
| | WCB_2 | 1,070 -> 1,074 | 5,220 -> 5,235 | +15 |
| | WCC | 954 -> 952 | 2,653 -> 2,685 | +32 |
| | WCXY | 1,691 -> 1,755 | 963 -> 959 | -4 |
| Midland | DEAN | 987 -> 986 | 2,436 -> 2,471 | +35 |
| | JM | 1,681 -> 1,847 | 3,454 -> 3,405 | -49 |
| | LSSH | 5,754 -> 5,590 | 5,641 -> 5,557 | -84 |
| | MS | 1,721 -> 1,720 | 4,154 -> 4,169 | +15 |
| | WCA_1 | 7,763 -> 7,379 | 5,349 -> 5,295 | -54 |
| | WCB_1 | 6,022 -> 6,441 | 4,703 -> 4,640 | -63 |
| | WCB_2 | 1,816 -> 1,819 | 2,056 -> 2,034 | -22 |
| | WCC | 258 -> 258 | 1,007 -> 993 | -14 |
| | WCD | 901 -> 903 | 5,245 -> 5,227 | -18 |

No bench moves more than 1.7 % except Delaware AVA_1 (+2.4 %). Midland LSSH and WCA_1 lost producers to JM and WCB_1
and still lost sticks; 103 of LSSH's -84 net and 74 of WCA_1's -54 sit in DSUs with no re-tagged well, so that is the
regional surfaces and the Novi revisions, not the re-tagged pads themselves.

TVD bust of BOX sticks against same-bench producers in the DSU: Delaware 28 -> 27 ft median, 118 -> 113 ft P90;
Midland 22 -> 22 ft, 95 -> 90 ft. Novi on the same pairs: 100 ft and 62 ft median, unchanged.

Drilled-across flag: Delaware 285 U-turn DSUs flagged (284), 1,466 sticks in 248 DSUs (1,450 in 246); Midland 118
(116), 492 sticks in 97 DSUs (486 in 96). 1,958 sticks, 2.4 % (1,936).

## Back-test (cutoff 2023-01-01, 708 hidden producers)

| Bar | Old (0.8, pre-cutover) | New | Verdict |
|---|---|---|---|
| T1 hidden wells with a leg (>= 60 %) | 59.2 % (Lea 52.9, Ward 46.9, Midland 69.8) | 59.7 % (Lea 53.9, Ward 49.5, Midland 69.0) | fails |
| T2 hidden wells on a bench with no row | 5.0 % | 4.7 % | passes |
| T3 units within one leg (>= 70 %); count ratio | 63.2 %; 0.96 | 63.2 %; 0.96 | fails; ratio passes |
| T4 unused slots (<= 25 %) | 33.0 % | 36.5 % (112 of 307 legs) | fails, worse |
| T5 direct rung: pairs, median, within 150 ft | 121, 59.0 ft, 80.2 % | 121, 55.1 ft, 82.6 % | passes |
| T5 thickness rung, observed / held-out median | 1.32x (63.0 / 47.6 ft, 217 pairs) | **1.56x** (67.7 / 43.5 ft, 221 pairs) | **now fails** (<= 1.5x) |
| T5 offset rung | 1.14x (38) | 1.16x (38) | passes |
| T5 bracket rung | 1.59x (24) | 1.71x (25) | fails |

One bar changed verdict: the thickness rung of T5 now fails its own bar. Both sides moved: the held-out expectation
fell 4.1 ft (the hold-out scores better on the new tags) and the observed error rose 4.7 ft. Nothing was tuned.
The carried-depth repair in the landing chain is already an open item; this adds the thickness rung to it.

## Upstream re-measurements

Landing depth (phases 0-1c):
- DSU x bench depth basis (phase 1, 52,712 rows): direct 48.2 % -> 48.2 %, thickness 16.3 -> 16.1, none 35.5 -> 35.7.
- Carried-depth expected error (phase 1b): Delaware 69.4 -> 67.5 ft median, 220.7 -> 211.2 ft P90; Midland 50.0 -> 47.4
  ft, 151.9 -> 145.8 ft.
- Two-part screen (phase 1c): wells whose depth says another bench 1,499 -> 1,125; of those the rule already moved,
  394 -> 0 (they are now moved). Midland WCA_1 on WCB_1 287 -> 106, LSSH on JM 218 -> 108. Bad depth 377 -> 372.
- The phase 1c rung and stack-order numbers in `phase1c/summary.json` are not comparable with `phase1c-2026-11-12`:
  that run had WCXY on the direct rung only.

Spacing (phase 2a): median same-landing gap Delaware 1,005 -> 998 ft, Midland 825 -> 831 ft; wells measured 13,899 ->
14,000 and 18,225 -> 18,744. Midland share of gaps under 440 ft 7.2 -> 6.4 %, under 660 ft 28.5 -> 27.1 %. The blended
surface of record keeps its pick (sigma 3 mi, k 1), train score 113.2 -> 111.9 ft. The chain-of-bands variant, which
was not adopted, now fails its fringe test in the Delaware.

Envelopes (phase 2b): candidate D, the envelope of record, still passes every bar in both basins: Delaware 1.15 %
excluded (260 of 22,675 children), worst bench AVA_2 2.3 %; Midland 1.56 % (378 of 24,291), worst bench WCA_1 3.2 %.
Candidates B and E, not adopted, now fail the per-bench bar in the Delaware on the OTHER bench (17 of 350 -> 19 of 322
children, 5.9 %).

## Not done

- The split between tag changes and three nights of Novi revisions.
- The review cards here are re-rendered on the new pull; they still do not draw the drilled-across flag.
