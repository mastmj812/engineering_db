# BOX sticks, phase 2a: realized well spacing (2026-11-12)

Read-only. `python -m scripts.box_sticks_phase2a --out docs/box_sticks/phase2a-2026-11-12 --cache <phase 0 cache>`.
Plan: `docs/box_sticks_plan.md`. Live tags, cache pulled 2026-11-12 (56,842 evidence wells, 257,397 Novi sticks, as
in phase 0). Nothing was written to the warehouse.

**Two passes.** The first pass measured the gap at tag level ("flattened"). Its cross-check against Novi failed in
the Delaware and showed why: a tag can hold two landings. Michael then decided the spacing is PER LANDING. The
numbers below are per-landing unless marked "first pass"; the first-pass values are kept in the `flat_*` columns.

## Decisions (Michael, 2026-11-12)

| # | Decision |
|---|---|
| 1 | Floor **1,320 ft** (4 WPS). Not 1,540 ft |
| 2 | Tight cap **660 ft** (8 WPS) |
| 3 | Spacing is **per landing**: a neighbour landed more than 75 ft from the well is the other landing of a staggered pattern, not this row's neighbour. "Second landing inside a tag" is an open item for the pilot cards (BS2_S, Delaware WCC, LSSH, BS3_C) |
| 4 | Control radius stays **1 -> 2 -> 3 mi with >= 6 gaps**; every stick records the radius its spacing came from |
| 5 | (2026-11-13) **No local control -> the bench's extent-band median**, not a flat 1,320 ft: bands 0-2, 2-5, 5-10, 10+ mi inside the extent edge, clamped to 660-1,320 ft; a band with fewer than 20 wells -> 1,320 ft. See addendum 2. The smooth surface (addendum 1) is not adopted |
| 6 | (2026-11-13) **Spacing map = the blended surface** (addendum 3): Gaussian-weighted median of well gaps, sigma 3 mi, relaxed toward the band median as control thins (k 2). Supersedes the radius chain of decision 4 and the hard band default of decision 5; the band survives as what the surface relaxes to |

Decisions 4 and 5 are superseded by decision 6. Decision 4 was taken on the first-pass hold-out. The per-landing hold-out is weaker for the Delaware Bone Spring
benches: see "Control radius".

## Headline

| | Delaware | Midland |
|---|---|---|
| Producers in the population (first production >= 2016, evidence rules, two-part screen) | 22,598 | 23,985 |
| Wells measured / unique pairs | 12,836 / 8,124 | 18,034 / 11,472 |
| Median gap | 1,133 ft (4.7 WPS) | 863 ft (6.1 WPS) |
| P10 (wide) / P90 (tight) | 1,772 / 641 ft (3.0 / 8.2 WPS) | 1,395 / 599 ft (3.8 / 8.8 WPS) |
| First pass, tag-level median | 1,005 ft (5.3 WPS) | 825 ft (6.4 WPS) |
| DSU x bench neighbourhoods | 29,719 | 19,835 |
| ... with local control (>= 6 gaps within 3 mi) | 59.0 % | 72.0 % |
| ... resolved at 1 / 2 / 3 mi | 16.7 / 23.7 / 18.5 % | 33.9 / 23.7 / 14.4 % |
| ... no control -> 1,320 ft | 41.0 % | 28.0 % |

WPS = 5,280 / spacing. P10 is the wide end (SPE: P10 >= P50 >= P90 in feet); in WPS the order flips.

Operators space on three patterns: 660, 880 and 1,320 ft (8, 6 and 4 WPS). Both basins show sharp peaks at exactly
those values and none at 1,540 ft (`gap_histograms.png`).

## Method, grain and filters

- **Gap** = the `dealintake/spacing.py` method with the deal-intake parameters of record (parallel within 15 deg,
  alongside >= 30 % of the well, median perpendicular distance over the shared length, a neighbour under 300 ft is
  the same slot). The script re-implements it on arrays so it can return WHICH neighbour; against the original
  `neighbour_gaps_ft` it agrees on 99.8 % of 1,220 Delaware BS1_S wells and 99.6 % of 1,004 Midland DEAN wells
  (bar 99 %; median difference -2 ft, from working in EPSG:3083 instead of a local frame).
- **Per landing**: a same-tag neighbour whose landing depth differs by more than 75 ft is not a candidate. A
  neighbour whose depth is not evidence cannot be ruled out and stays a candidate.
- **Neighbour search universe**: all 60,826 horizontal producers with a lateral line and a live tag, any vintage,
  any evidence status, so an older or unjudged well lying between two wells is seen.
- **A well is measured** when it is in the population and its NEAREST same-landing neighbour (300 to 2,800 ft) is
  also in the population and came on within 12 months of it: 30,870 of 46,583. Not measured: nearest neighbour
  from another campaign 6,424; no neighbour within 2,800 ft 6,364; nearest neighbour not evidence (planned survey,
  round-100 TVD, screened out) 1,881; nearest neighbour pre-2016 1,044.
- **The 12-month window matters little**: for benches with >= 100 wells the median moves by a median of 3 ft at
  6 months and 17 ft at 24 months (largest 58 and 80 ft, both WCC); with no window at all 20 ft (largest 154 ft).
- **Neighbourhood** = one Novi 2026Q3 DSU polygon x one bench whose BOX record extent it intersects (WCXY: the
  hand-drawn extent file). Local spacing = median gap of same-bench measured wells within 1, then 2, then 3 mi of the
  polygon, first radius with >= 6 gaps (the deal-intake chain). 49,554 neighbourhoods.
- Same bench = same live `formation_blueox` code. WCA_1, WCA_2 and WCXY are measured separately.

## Spacing by bench (per landing)

Wells / pairs, well-level median with WPS, P10 wide / P90 tight, the first-pass tag-level median, share of gaps
under 660 ft, DSUs intersecting the extent, share with local control, median of the local values, share of local
values under 660 ft (clamped up by the cap), and Novi's median stick gap for the bench.

| Basin | Bench | Wells / pairs | Median (WPS) | P10 / P90 ft | First pass ft | Gaps < 660 | DSUs | Local control | Local median (WPS) | Local < 660 | Novi stick gap ft |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Delaware | AVA_0 | 189 / 117 | 877 ft (6.0) | 1,408 / 498 | 877 | 32 % | 244 | 82 % | 891 ft (5.9) | 27 % | 880 |
| Delaware | AVA_1 | 223 / 147 | 932 ft (5.7) | 1,729 / 526 | 835 | 22 % | 408 | 66 % | 946 ft (5.6) | 18 % | 2,615 |
| Delaware | AVA_2 | 147 / 92 | 996 ft (5.3) | 1,620 / 566 | 907 | 24 % | 482 | 58 % | 981 ft (5.4) | 14 % | 880 |
| Delaware | **BS1_S** | 487 / 307 | 1,272 ft (4.2) | 1,838 / 766 | 1,245 | 6 % | 2,359 | 36 % | 1,271 ft (4.2) | 1 % | 1,319 |
| Delaware | BS2_C | 303 / 185 | 1,301 ft (4.1) | 2,016 / 851 | 1,269 | 4 % | 1,169 | 49 % | 1,276 ft (4.1) | 1 % | 1,319 |
| Delaware | BS2_S | 1,529 / 997 | 1,241 ft (4.3) | 1,762 / 773 | 940 | 6 % | 2,401 | 80 % | 1,292 ft (4.1) | 1 % | 880 |
| Delaware | BS3_C | 824 / 509 | 1,282 ft (4.1) | 1,992 / 826 | 1,122 | 4 % | 2,840 | 48 % | 1,255 ft (4.2) | 0 % | 1,319 |
| Delaware | BS3_S | 1,028 / 643 | 1,293 ft (4.1) | 1,796 / 789 | 1,258 | 6 % | 3,608 | 47 % | 1,268 ft (4.2) | 2 % | 1,319 |
| Delaware | WCA_1 | 2,963 / 1,921 | 981 ft (5.4) | 1,680 / 593 | 907 | 18 % | 4,457 | 72 % | 1,023 ft (5.2) | 6 % | 660 |
| Delaware | WCA_2 | 2,140 / 1,343 | 1,048 ft (5.0) | 1,711 / 631 | 974 | 14 % | 4,457 | 69 % | 1,044 ft (5.1) | 5 % | 754 |
| Delaware | WCB_1 | 893 / 549 | 1,128 ft (4.7) | 1,738 / 662 | 1,044 | 10 % | 2,664 | 61 % | 1,107 ft (4.8) | 2 % | 1,320 |
| Delaware | WCB_2 | 516 / 319 | 1,259 ft (4.2) | 1,920 / 783 | 1,176 | 5 % | 2,280 | 43 % | 1,258 ft (4.2) | 2 % | 1,320 |
| Delaware | WCC | 367 / 222 | 1,208 ft (4.4) | 1,863 / 602 | 881 | 12 % | 1,051 | 48 % | 1,133 ft (4.7) | 5 % | 1,320 |
| Delaware | WCXY | 982 / 617 | 1,088 ft (4.9) | 1,817 / 595 | 999 | 16 % | 1,299 | 76 % | 1,172 ft (4.5) | 4 % | 879 |
| Midland | **DEAN** | 690 / 438 | 1,047 ft (5.0) | 1,542 / 664 | 1,019 | 10 % | 2,271 | 40 % | 1,077 ft (4.9) | 3 % | 1,320 |
| Midland | JM | 1,198 / 740 | 995 ft (5.3) | 1,681 / 734 | 910 | 6 % | 1,826 | 83 % | 1,033 ft (5.1) | 1 % | 1,320 |
| Midland | LSSH | 4,062 / 2,623 | 822 ft (6.4) | 1,296 / 534 | 701 | 26 % | 2,821 | 81 % | 842 ft (6.3) | 13 % | 880 |
| Midland | MS | 1,170 / 751 | 990 ft (5.3) | 1,653 / 682 | 966 | 9 % | 1,902 | 71 % | 1,053 ft (5.0) | 1 % | 1,320 |
| Midland | WCA_1 | 5,153 / 3,297 | 818 ft (6.5) | 1,300 / 576 | 769 | 26 % | 3,593 | 86 % | 851 ft (6.2) | 14 % | 880 |
| Midland | WCB_1 | 3,378 / 2,138 | 865 ft (6.1) | 1,333 / 594 | 843 | 18 % | 3,397 | 86 % | 887 ft (6.0) | 7 % | 880 |
| Midland | WCB_2 | 1,375 / 866 | 879 ft (6.0) | 1,489 / 638 | 876 | 14 % | 1,357 | 78 % | 919 ft (5.7) | 6 % | 880 |
| Midland | WCC | 225 / 136 | 1,000 ft (5.3) | 1,760 / 744 | 970 | 7 % | 494 | 58 % | 940 ft (5.6) | 4 % | 2,110 |
| Midland | WCD | 624 / 385 | 1,181 ft (4.5) | 1,789 / 737 | 1,117 | 8 % | 2,174 | 40 % | 1,255 ft (4.2) | 4 % | 1,803 |

Full tables: `spacing_by_bench.csv` (also benches with no BOX extent), `spacing_by_extent.csv` (control by radius).

- **Per landing, the whole Delaware Bone Spring is a 4 WPS play**: BS1_S, BS2_C, BS2_S, BS3_C, BS3_S all sit at
  1,240-1,300 ft. BS2_S moved most (940 -> 1,241 ft); Delaware WCC 881 -> 1,208 ft; LSSH 701 -> 822 ft.
- **Delaware BS1_S** (`spacing_map_delaware_BS1_S.png`): 487 wells, 307 pairs, 1,272 ft (4.2 WPS). 36 % of 2,359
  DSUs have local control, in the developed core; the west and south take 1,320 ft. 28 % of gaps are within 5 % of
  1,320 ft.
- **Midland DEAN** (`spacing_map_midland_DEAN.png`): 690 wells, 438 pairs, 1,047 ft (5.0 WPS). 40 % of 2,271 DSUs
  have local control; local median 1,077 ft. DEAN is developed tighter than Novi's blanket 1,320 ft where it is
  developed at all.

## Cross-check against `lateral_closer_xy_ft`

Compared on population wells where Novi's value is bounded (not NULL, not 2800.0) and this method also finds a
neighbour that was on production when the well came on. Thresholds were fixed before the first run: median
difference within 50 ft and at least 70 % of wells within max(100 ft, 15 %).

| | Wells | Median (this - Novi) | Within max(100 ft, 15 %) | Verdict |
|---|---|---|---|---|
| First pass, tag-level: Delaware | 16,546 | -8 ft | 65.0 % | **fails agreement** |
| First pass, tag-level: Midland | 20,938 | -8 ft | 70.3 % | passes, barely |
| Per landing: Delaware | 15,325 | +1 ft | 75.3 % | passes |
| Per landing: Midland | 20,108 | +1 ft | 83.2 % | passes |

- **The method as first specified failed its check in the Delaware.** That is the verdict of record for the
  tag-level gap. The per-landing rows are the same comparison on a method changed after seeing the failure, so
  they are confirmation of the diagnosis, not an independent pass.
- The diagnosis: in the first pass, agreement was 82.6 % Delaware / 88.5 % Midland where the well and its neighbour
  were landed within 75 ft, and 27 % / 17 % where they were not. Novi's "same zone" is finer than a
  `formation_blueox` tag. Worst first-pass benches: Delaware BS2_S (52 %), WCC (52 %), AVA_1 (51 %), Midland LSSH (58 %).
- First-pass unbounded class: of 3,407 population wells Novi marks 2800.0, the tag-level method finds a neighbour
  for 815 (24 %); of 42,197 Novi-bounded wells it finds none within 2,800 ft for 4,713 (11 %).
- `crosscheck_closer_xy.csv` (first pass), `crosscheck_closer_xy_per_landing.csv`.

## 1,320 or 1,540 ft for the 4 WPS floor (decided: 1,320 ft)

- Gap histogram: a sharp peak at 1,320 ft in both basins, nothing at 1,540 ft. Within 5 % of 1,320 ft: 17.4 % of
  Delaware gaps and 8.9 % of Midland; within 5 % of 1,540 ft: 5.8 % and 2.9 %, which is the background level (the
  1,386-1,463 ft band between them holds 3.3 % / 1.5 %).
- Sparse benches, the ones a floor governs: BS1_S 28 % near 1,320 vs 6 % near 1,540; BS2_S 25 % vs 6 %; BS3_S
  24 % vs 10 %; DEAN 18 % vs 6 %.
- One-mile-wide DSUs fully developed on a bench since 2016 within 12 months (`one_mile_dsu_wells_vs_gap.csv`):
  with 4 wells across (414 Delaware, 377 Midland DSU x bench) the median gap is 1,253 / 1,143 ft, upper quartile
  1,332 / 1,287 ft. Setback-packed 4-well spacing would be 1,540 ft; almost none reach it.
- Novi itself draws 1,320 ft on every 4 WPS bench (stick gap medians 1,319-1,320 ft).
- For 1,540 ft: no pattern. Its support is arithmetic ((5,280 - 660) / 3) and the wide tail: 14 % of Delaware
  gaps and 5.8 % of Midland exceed 1,617 ft, with no mode. Local values above 1,320 ft are 24 % of Delaware and
  12 % of Midland local values; they are clamped down to the floor.
- Cost (`cap_floor_choices.csv`, gross rows across each DSU, all 49,554 neighbourhoods, before existing wells and
  no-place culls): a 1,540 ft floor would remove 6.5 % of Delaware rows and 3.8 % of Midland.

## Tight cap (decided: 660 ft)

| Local value below | Delaware (share of local values) | Midland |
|---|---|---|
| 660 ft (8 WPS) | 3.7 % | 7.7 % |
| 600 ft | 1.2 % | 1.6 % |
| 500 ft | 0.3 % | 0.7 % |
| 440 ft (12 WPS) | 0.1 % | 0.2 % |

- 660 ft is itself a real pattern (a clear peak in both basins). Below it there is a thin tail and no mode.
- Per landing, the cap binds on few neighbourhoods: Delaware AVA_0 (27 %), AVA_1 (18 %), AVA_2 (14 %); Midland
  WCA_1 (14 %), LSSH (13 %). Every other bench is at 7 % or less. First pass it was 7.6 % / 15.1 % overall.
- Cost: a 528 ft cap would add 0.6 % gross rows in the Delaware and 1.1 % in the Midland.

## Control radius (decided: keep 1 -> 2 -> 3 mi)

Hold-out (`radius_holdout.csv`): for every DSU x bench that has its own value inside 1 mi, the value it would get
from the 2-3 mi ring alone, against assuming 1,320 ft. All clamped to 660-1,320 ft.

| | Delaware (3,924) | Midland (6,074) |
|---|---|---|
| Median error, 2-3 mi ring | 139 ft | 87 ft |
| Median error, 1,320 ft default | 296 ft | 476 ft |
| Ring closer than default / tie | 61 % / 15 % | 86 % / 2 % |

- **Midland: far control clearly beats the default on every bench.**
- **Delaware Wolfcamp and Avalon: it beats the default** (WCA_1 125 vs 385 ft, WCB_1 164 vs 363 ft).
- **Delaware Bone Spring: it does not.** The default is as good or better on BS2_C (54 vs 50 ft), BS3_C (65 vs
  48 ft), BS3_S (78 vs 40 ft); BS2_S is a wash (139 vs 150 ft). These benches sit near 1,320 ft anyway, so either
  answer is within about 80 ft. BS1_S still favours the ring (119 vs 203 ft).
- The first-pass hold-out, on which the decision was taken, showed the ring ahead on every bench (Delaware 128 vs
  409 ft). The per-landing result weakens that for the Bone Spring only; the cost of keeping the chain there is small.
- The test is biased toward developed areas: a DSU with its own 1 mi control sits in a drilled fairway. At extent
  edges the default would do better than this table suggests.

## Addendum: does spacing follow position in the bench, and would a smooth surface beat the chain?

Michael, 2026-11-12: wells per section should follow reservoir quality, densest in the core of a bench and thinning
outward, so the map should be a gradient and not the step the radius chain makes. `scripts/box_sticks_phase2a_surface.py`.
**Outcome: not adopted (decision 5 takes the band default instead).**

**Spacing does widen outward.** Measured wells by distance of the lateral midpoint inside its bench's BOX extent edge:

| Inside the edge by | Delaware median gap | Midland median gap |
|---|---|---|
| 10+ mi | 1,034 ft (5.1 WPS), 5,619 wells | 830 ft (6.4 WPS), 9,158 wells |
| 5-10 mi | 1,151 ft (4.6 WPS), 3,501 | 871 ft (6.1 WPS), 5,310 |
| 2-5 mi | 1,258 ft (4.2 WPS), 2,259 | 966 ft (5.5 WPS), 2,345 |
| 0-2 mi | 1,283 ft (4.1 WPS), 1,212 | 1,069 ft (4.9 WPS), 1,062 |

Most benches show it individually (Delaware WCA_1 930 -> 1,321 ft, Midland WCA_1 800 -> 1,214 ft, DEAN 886 ->
1,189 ft); BS3_S, WCB_2 and AVA_1 do not. Well-level rank correlation is only -0.1 to -0.3. The extent is an
envelope of drilling, so this is a proxy for "outward from the sweet spot", not a reservoir-quality measure.

**The surface tested.** Gaussian-weighted median of a bench's per-well gaps (distance DSU polygon to well, cut at
2.5 sigma), optionally relaxed toward 1,320 ft as control thins (c = n_eff / (n_eff + k)). Targets: 11,695 DSU x
bench with their own value inside 1 mi; each method predicts them from wells farther than 1, 2 or 3 mi. sigma and
k were picked on half the targets (sigma 3 mi, k 0, i.e. no relaxation); every number below is from the other half
(5,873). The adoption test was fixed before the first run.

| Median error, ft (chain -> surface) | Delaware | Midland |
|---|---|---|
| Wells within 1 mi hidden | 118 -> 111 | 75 -> 71 |
| Within 2 mi hidden | 146 -> 128 | 91 -> 79 |
| Within 3 mi hidden (chain can only say 1,320 ft) | 279 -> 142 | 467 -> 85 |
| P90 error, 2 mi hidden | 473 -> 391 | 396 -> 320 |
| Adjacent DSUs differing by more than 200 ft (all 49,554) | 12.6 % -> 2.9 % | 13.9 % -> 2.9 % |

| Adoption test | Delaware | Midland |
|---|---|---|
| Median error below the chain's at 1 and 2 mi | yes | yes |
| P90 error within 10 % of the chain's | yes | yes |
| Fringe (0-2 mi inside the edge, 1 mi hidden) no worse than the chain + 10 ft | **no** (37 vs 23 ft, 99 DSU x bench) | yes (71 vs 91 ft, 95) |
| Verdict | **fails** | passes |

- **Where the surface is clearly better: holes inside developed ground.** With everything inside 3 mi hidden the
  chain answers 1,320 ft and is 280-470 ft off; the surface is 85-140 ft off. Under the chain, 26 % of Delaware and
  11 % of Midland DSU x bench more than 10 mi inside the edge take 1,320 ft.
- **At 1-2 mi the gain is modest**, and in the Delaware Bone Spring the chain is still better (2 mi hidden: BS1_S
  79 vs 111 ft, BS2_C 30 vs 62 ft, BS3_C 95 vs 113 ft, WCB_2 68 vs 116 ft). Those benches sit near 1,320 ft.
- **It failed its fringe test in the Delaware.** Narrowly and on 99 targets, but it failed.
- **The picked surface does the opposite of the reservoir-quality expectation at the fringe.** With no relaxation
  it carries a few wells' spacing up to 7.5 mi: gross rows in the outer 0-2 mi band rise 6.6 % (Delaware) and
  12.4 % (Midland) against the chain, DEAN +13.7 % overall. On `surface_map_midland_DEAN.png` a handful of wells in
  the south of the extent paint a large area at 660-800 ft.
- **The relaxed variant (sigma 3 mi, k 2)** scores within 2 ft of the picked one on the training half, halves the
  fringe increase (+2.4 % / +5.9 %), and fails the same Delaware fringe test by more (51 vs 23 ft). Files `*_relaxed.csv`.
- **What this hold-out cannot see:** every target has six or more of its own wells within a mile, so it sits in
  drilled ground. Whether undrilled fringe should be looser than its nearest fairway is exactly the part it cannot
  judge, and that is why tuning chose no relaxation.

Conclusion: a smooth surface is the better tool inside developed ground and removes the steps, but as tested it is
not ready to replace the chain: it fails in the Delaware fringe and over-extends thin control. A fair test of the
outward-thinning idea needs a hold-out that hides the OUTER wells of a bench and predicts them from the inner ones.

## Addendum 2: spacing by extent band

Michael, 2026-11-13: the envelope of a bench is governed by structure or reservoir, not by a circle around a well.
Contour each extent into bands by distance inside its edge, and let a well inform spacing ALONG its band. Expected
to hold best on the mature primary benches (the WCA, developed outward from the best rock) and least on add-on
zones such as DEAN. `scripts/box_sticks_phase2a_bands.py`. **Outcome: Michael adopted the band as the no-control default (decision 5), then replaced chain + band with the blended surface (decision 6, addendum 3).**

**The band pattern is real, and it has the shapes described.** Median gap by band (miles inside the extent edge):

| Bench | 10+ mi | 5-10 mi | 2-5 mi | 0-2 mi | Shape |
|---|---|---|---|---|---|
| Delaware WCA_1 | 930 ft | 1,013 | 1,196 | 1,321 | steady widening outward |
| Delaware WCA_2 | 1,020 | 1,105 | 1,096 | 1,306 | widening outward |
| Delaware BS1_S | 1,108 | 1,274 | 1,291 | 1,323 | tight core only |
| Midland WCA_1 | 800 | 838 | 874 | 1,214 | flat, then a cliff in the last 2 mi |
| Midland LSSH | 813 | 815 | 861 | 1,228 | flat, then a cliff in the last 2 mi |
| Midland WCB_1 | 848 | 880 | 905 | 1,029 | gentle |
| Midland DEAN | 886 | 1,239 | 1,220 | 1,189 | tight core, no trend outside it |
| Delaware BS3_S | 1,293 | 1,286 | 1,304 | 1,305 | none |

Full table with well counts and quartiles: `bands_spacing.csv`. The outer band is thin on some benches (LSSH 41
wells, Delaware WCA_1 47, DEAN 26).

**As a predictor it loses to nearby wells.** Same hold-out as the surface, all 11,695 targets (nothing tuned).
Median error, ft:

| Wells hidden within | Basin | Chain | Band (whole extent) | Band within 10 mi | Chain, band where no control |
|---|---|---|---|---|---|
| 1 mi | Delaware | 120 | 168 | 132 | 122 |
| 1 mi | Midland | 76 | 108 | 92 | 78 |
| 2 mi | Delaware | 143 | 173 | 138 | 144 |
| 2 mi | Midland | 92 | 108 | 98 | 93 |
| 3 mi (chain can only say 1,320 ft) | Delaware | 275 | 176 | 145 | 176 |
| 3 mi | Midland | 467 | 109 | 102 | 109 |

- Bands on their own fail the adoption test in both basins, and worst on the WCA, the benches the idea fits best
  geologically (2 mi hidden: Delaware WCA_1 179 vs 134 ft, Midland WCA_1 86 vs 70 ft). Those benches have dense
  control, and wells 1-3 mi away say more about a DSU than its band does.
- Bands beat the chain on benches with sparse control: BS1_S 69 vs 82 ft, BS3_S 59 vs 87 ft, DEAN 102 vs 131 ft.
- In the outer band the band median reads about 150-180 ft too wide for the targets there. Those targets are the
  drilled pockets of the fringe (six wells within a mile), not typical fringe ground.

**Where bands help: as the default.** On targets where the chain finds no control and falls back to 1,320 ft:

| Wells hidden within | Delaware: 1,320 ft -> band | Midland: 1,320 ft -> band |
|---|---|---|
| 1 mi | 128 -> 153 ft (324 targets, worse) | 270 -> 171 ft (210) |
| 2 mi | 195 -> 161 ft (1,050) | 311 -> 170 ft (647) |
| 3 mi | 275 -> 176 ft (4,974) | 467 -> 109 ft (6,721) |

- "Chain, band where no control" ties the chain on the overall median (it changes few targets) and improves the P90
  error (Delaware 468 -> 425 ft, Midland 397 -> 337 ft at 2 mi). By the letter of the pre-set test it does not pass:
  its overall median is not below the chain's.
- Applied to all 49,554 DSU x bench: the 41 % of Delaware and 28 % of Midland that take 1,320 ft today would take a
  band value averaging 1,232 ft and 1,132 ft; the outer 0-2 mi band stays loose (1,274 / 1,190 ft). Gross rows
  +1.7 % Delaware, +3.2 % Midland (`bands_vs_chain.csv`). Unlike the smooth surface, this does not densify the fringe.
- Not tested: bands by side of the extent. Distance to the nearest edge treats the Central Basin Platform edge and
  the eastern shelf edge alike.

## Addendum 3: blending (smooth surface relaxing to the band)

Michael, 2026-11-13, after the density maps (`density_wps_*.png`): on a mature bench the picture should be nested
contours, about 8 WPS in the core, 6 around it, 4 at the fringe; the rule of record nearly shows that but drops to
the band value at a hard step wherever development has a gap, even in the middle of the proven core.
**Outcome: adopted by Michael 2026-11-13 (decision 6). "Record" in the table below means the superseded decision 5 rule.**

The blend: the Gaussian-weighted median of addendum 1, relaxed toward the BAND value (not the floor) as control
thins: spacing = band - c (band - weighted median), c = n_eff / (n_eff + k). sigma and k picked on half the
hold-out targets (sigma 3 mi, k 2); numbers below are from the other half (5,873).

| Median error, ft | Delaware: chain / record / blend | Midland: chain / record / blend |
|---|---|---|
| Wells within 1 mi hidden | 118 / 120 / 110 | 75 / 77 / 72 |
| Within 2 mi hidden | 146 / 145 / 129 | 91 / 93 / 80 |
| Within 3 mi hidden | 279 / 175 / 141 | 467 / 108 / 84 |
| Where the chain has no control, 2 mi hidden | 230 / 163 / 136 | 304 / 178 / 139 |
| P90 error, 2 mi hidden | 473 / 431 / 384 | 396 / 333 / 312 |
| Adjacent DSUs differing by more than 200 ft (all 49,554) | - / 13.2 % / 1.5 % | - / 13.5 % / 1.8 % |

("record" = decision 5: wells within 3 mi, else band.)

- The blend beats the rule of record on every aggregate line and removes the steps.
- **Adoption test (the one fixed for addendum 1, against the chain): Midland passes; Delaware fails the fringe
  line again**, 35 vs 23 ft in the outer 0-2 mi band with 1 mi hidden (bar 33 ft, 99 targets). With 2 mi hidden
  the same band reads 58 vs 117 ft in the blend's favour.
- Cost: the blend smooths peaks as well as holes. Small 8 WPS pockets under the rule of record come out at 6-7 WPS
  (`blend_map_delaware_BS2_S.png`); broad dense cores keep 8 WPS (Midland WCA_1, LSSH on `density_blend_wps_midland.png`).
- Gross rows against the rule of record: Delaware -0.5 %, Midland +1.0 %; outer 0-2 mi band +2.3 % / +4.9 %.
- Files: `blend_holdout.csv`, `blend_tuning.csv`, `blend_smoothness.csv`, `blend_vs_record.csv`,
  `density_blend_wps_*.png`, `blend_map_*.png`.

## What changes against Novi's sticks

Novi spacing is quantized by bench (medians of exactly 660, 754, 880, 1,320 or about 2,640 ft) and essentially
uniform across a bench. BOX spacing follows local drilling. Compared on 26,729 DSU x bench where Novi has sticks and
the bench's BOX extent reaches the DSU (25,676 with a measurable Novi gap), cap 660 ft, floor 1,320 ft
(`novi_vs_box_summary.csv`):

| | Delaware | Midland |
|---|---|---|
| Mean spacing, Novi -> BOX | 1,276 -> 1,226 ft | 1,224 -> 1,089 ft |
| BOX within 10 % of Novi | 53 % | 31 % |
| BOX tighter by more than 10 % | 22 % | 39 % |
| BOX wider by more than 10 % | 25 % | 29 % |

- **Little change**: BS1_S, BS2_C, BS3_C, BS3_S (70-84 % of DSUs within 10 % of Novi), and wherever there is no
  control and both say 1,320 ft (71 % of Delaware default DSU x bench within 10 %).
- **BOX wider (fewer wells)**: Delaware BS2_S (Novi 880 ft -> BOX mean 1,233 ft, 83 % of DSUs wider), AVA_2 (Novi
  660 ft -> 1,137 ft, 76 % wider), WCA_1 / WCA_2 / WCXY (61-74 % wider). Midland LSSH, WCA_1, WCB_1 and WCB_2 are
  wider than Novi's 880 ft in about half their DSUs.
- **BOX tighter (more wells)**: Midland WCC and WCD (Novi 1,760-1,950 ft -> BOX at most 1,320 ft, 88-90 % of DSUs
  tighter), JM and MS (43-47 % tighter), Delaware WCC (58 % tighter).
- **Gross rows** (Novi sticks + existing same-tag wells, against BOX rows across the DSU): Delaware -6.8 %,
  Midland +35 %. Indicative only: this is before existing-well pinning and the 2b no-place cull, and it is not a
  spacing effect alone. Midland DEAN shows +73 % rows at essentially the same spacing because Novi does not fill
  those DSUs.

Two things seen on the way, not investigated:

- 35,929 of 87,182 Midland Novi sticks (41 %) have their midpoint outside every 2026Q3 polygon (Delaware: 187 of
  170,215). They are outside this comparison.
- 142,794 of the 221,281 sticks inside a polygon sit on a bench whose BOX extent does not reach that DSU, including
  13,033 of 14,683 Novi WCXY sticks outside the hand-drawn extent. That is the bench-eligibility change, for gate 3b.

## Caveats and open items

- **Second landing inside a tag.** Per-landing spacing with one row per bench under-counts inventory where operators
  develop two landings in one tag (first pass: 44 % of BS2_S pairs, 40 % of Delaware WCC, 31 % of BS3_C, 29 % of
  LSSH were landed more than 75 ft apart). For the pilot cards.
- The 75 ft test uses the landing-surface depth evidence; some "two landing" pairs are depth noise or dip.
- **Wide local spread.** The deal-intake "mixed" flag (IQR / median > 0.15) fires on 76 % of Delaware and 72 % of
  Midland local values. On real wells it does not discriminate.
- **Planned-survey wells** are in the neighbour search by their tag but are never measured; where such a well is the
  nearest neighbour the well is dropped (1,881 wells), which thins New Mexico.
- EPSG:3083 distances run about 0.2 % short of true (-2 ft on 1,000 ft).
- Rows are gross slots, not inventory.

Not committed (regenerate with the script): `well_gaps.csv.gz`, `spacing_dsu_bench.csv.gz`,
`novi_vs_box_dsu_bench.csv.gz`.
