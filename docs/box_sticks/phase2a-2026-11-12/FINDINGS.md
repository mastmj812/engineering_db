# BOX sticks, phase 2a: realized well spacing (2026-11-12 / 13)

Read-only. Plan: `docs/box_sticks_plan.md`. Live tags, cache pulled 2026-11-12 (56,842 evidence wells, 257,397 Novi
sticks, as in phase 0). Nothing was written to the warehouse.

    python -m scripts.box_sticks_phase2a         --out docs/box_sticks/phase2a-2026-11-12 --cache <phase 0 cache>
    python -m scripts.box_sticks_phase2a_surface --out ... --cache ...     (needs the first)
    python -m scripts.box_sticks_phase2a_bands   --out ... --cache ...     (needs the first two)

## Decisions of record (Michael)

| # | Decision |
|---|---|
| 1 | Floor **1,320 ft** (4 WPS). Not 1,540 ft |
| 2 | Tight cap **440 ft** (12 WPS) |
| 3 | Density is **per bench**: the count of same-bench wells across a section, however the operator staggered them vertically |
| 4 | Spacing map = **blended surface**: per bench, a distance-weighted median of well gaps around the DSU (sigma 3 mi), relaxing toward the bench's extent-band median as control thins (k 1). Clamped to 440-1,320 ft |

How these were reached is in "Decision history" at the end; several intermediate choices were reversed during the
review, and that section says which.

## Headline

| | Delaware | Midland |
|---|---|---|
| Producers in the population (first production >= 2016, evidence rules, two-part screen) | 22,598 | 23,985 |
| Wells measured / unique pairs | 13,899 / 8,950 | 18,225 / 11,741 |
| Median gap to the nearest same-bench well | 1,005 ft (5.3 WPS) | 825 ft (6.4 WPS) |
| P10 (wide) / P90 (tight) | 1,617 / 539 ft (3.3 / 9.8 WPS) | 1,318 / 485 ft (4.0 / 10.9 WPS) |
| DSU x bench in the spacing map | 29,719 | 19,835 |
| Mean / median planned spacing on the map | 1,088 / 1,112 ft (4.9 WPS) | 949 / 893 ft (5.6 WPS) |
| Map tighter than 660 ft (over 8 WPS) | 2.1 % of DSU x bench | 7.1 % |
| Map within 50 ft of the 1,320 ft floor | 27.3 % | 9.6 % |

WPS = 5,280 / spacing. P10 is the wide end (SPE: P10 >= P50 >= P90 in feet); in WPS the order flips.

Operators space on three patterns: 660, 880 and 1,320 ft (8, 6 and 4 WPS). Both basins show sharp peaks at exactly
those values and none at 1,540 ft (`gap_histograms.png`).

Maps: `density_blend_wps_delaware.png`, `density_blend_wps_midland.png` (the rule of record, every bench);
`blend_map_delaware_BS2_S.png`, `blend_map_midland_DEAN.png` (against the superseded chain rule).

## Method, grain and filters

- **Gap** = the `dealintake/spacing.py` method with the deal-intake parameters of record (parallel within 15 deg,
  alongside >= 30 % of the well, median perpendicular distance over the shared length, a neighbour under 300 ft is
  the same slot). The script re-implements it on arrays so it can return WHICH neighbour; against the original
  `neighbour_gaps_ft` it agrees on 99.8 % of 1,220 Delaware BS1_S wells and 99.6 % of 1,004 Midland DEAN wells
  (bar 99 %; median difference -2 ft, from working in EPSG:3083 instead of a local frame).
- **Same bench = same live `formation_blueox` code**, whatever the landing depth. WCA_1, WCA_2 and WCXY are measured
  separately.
- **Neighbour search universe**: all 60,826 horizontal producers with a lateral line and a live tag, any vintage,
  any evidence status, so an older or unjudged well lying between two wells is seen.
- **A well is measured** when it is in the population and its NEAREST same-bench neighbour (300 to 2,800 ft) is also
  in the population and came on within 12 months of it: 32,124 of 46,583. Not measured: nearest neighbour from
  another campaign 6,757; no neighbour within 2,800 ft 4,118; nearest neighbour not evidence (planned survey,
  round-100 TVD, screened out) 2,361; nearest neighbour pre-2016 1,223.
- **The 12-month window matters little**: bench medians move by at most 27 ft at 6 months, by at most 40 ft at
  24 months except Midland WCC (+98 ft), and with no window by under 100 ft except Midland WCC (+133 ft) and
  Delaware WCB_1 (+102 ft).
- **Map unit** = one Novi 2026Q3 DSU polygon x one bench whose BOX record extent it intersects (WCXY: the
  hand-drawn extent file). 49,554 DSU x bench.

## Spacing by bench

Wells / pairs, well-level median with WPS, P10 wide / P90 tight, share of pairs landed more than 75 ft apart, the
median if only same-landing neighbours count (not the measure of record), share of gaps under 660 / under 440 ft,
and Novi's median stick gap for the bench.

| Basin | Bench | Wells / pairs | Median (WPS) | P10 / P90 ft | Two landings | Per-landing median ft | Gaps < 660 / < 440 | Novi stick gap ft |
|---|---|---|---|---|---|---|---|---|
| Delaware | AVA_0 | 190 / 119 | 877 ft (6.0) | 1,433 / 497 | 3 % | 877 | 33 % / 5 % | 880 |
| Delaware | AVA_1 | 202 / 136 | 835 ft (6.3) | 1,528 / 492 | 26 % | 932 | 33 % / 3 % | 2,615 |
| Delaware | AVA_2 | 158 / 100 | 907 ft (5.8) | 1,408 / 543 | 20 % | 996 | 28 % / 5 % | 880 |
| Delaware | **BS1_S** | 510 / 327 | 1,245 ft (4.2) | 1,766 / 731 | 16 % | 1,272 | 7 % / 2 % | 1,319 |
| Delaware | BS2_C | 320 / 202 | 1,269 ft (4.2) | 1,852 / 692 | 17 % | 1,301 | 8 % / 1 % | 1,319 |
| Delaware | BS2_S | 1,729 / 1,141 | 940 ft (5.6) | 1,378 / 459 | 44 % | 1,241 | 25 % / 9 % | 880 |
| Delaware | BS3_C | 923 / 588 | 1,122 ft (4.7) | 1,700 / 708 | 31 % | 1,282 | 9 % / 1 % | 1,319 |
| Delaware | BS3_S | 1,146 / 725 | 1,258 ft (4.2) | 1,703 / 648 | 21 % | 1,293 | 11 % / 3 % | 1,319 |
| Delaware | WCA_1 | 3,171 / 2,077 | 907 ft (5.8) | 1,551 / 528 | 18 % | 981 | 23 % / 5 % | 660 |
| Delaware | WCA_2 | 2,283 / 1,468 | 974 ft (5.4) | 1,628 / 565 | 17 % | 1,048 | 19 % / 4 % | 754 |
| Delaware | WCB_1 | 951 / 598 | 1,044 ft (5.1) | 1,668 / 621 | 16 % | 1,128 | 14 % / 2 % | 1,320 |
| Delaware | WCB_2 | 560 / 349 | 1,176 ft (4.5) | 1,772 / 660 | 21 % | 1,259 | 10 % / 1 % | 1,320 |
| Delaware | WCC | 433 / 277 | 881 ft (6.0) | 1,785 / 421 | 40 % | 1,208 | 30 % / 13 % | 1,320 |
| Delaware | WCXY | 1,030 / 660 | 999 ft (5.3) | 1,673 / 526 | 19 % | 1,088 | 23 % / 5 % | 879 |
| Midland | **DEAN** | 700 / 452 | 1,019 ft (5.2) | 1,503 / 659 | 7 % | 1,047 | 10 % / 1 % | 1,320 |
| Midland | JM | 1,231 / 770 | 910 ft (5.8) | 1,530 / 644 | 14 % | 995 | 12 % / 2 % | 1,320 |
| Midland | LSSH | 4,081 / 2,674 | 701 ft (7.5) | 1,060 / 398 | 29 % | 822 | 45 % / 15 % | 880 |
| Midland | MS | 1,190 / 765 | 966 ft (5.5) | 1,547 / 650 | 9 % | 990 | 11 % / 2 % | 1,320 |
| Midland | WCA_1 | 5,160 / 3,363 | 769 ft (6.9) | 1,163 / 461 | 18 % | 818 | 36 % / 8 % | 880 |
| Midland | WCB_1 | 3,433 / 2,193 | 843 ft (6.3) | 1,308 / 524 | 12 % | 865 | 24 % / 5 % | 880 |
| Midland | WCB_2 | 1,382 / 877 | 876 ft (6.0) | 1,408 / 636 | 5 % | 879 | 16 % / 2 % | 880 |
| Midland | WCC | 239 / 146 | 970 ft (5.4) | 1,781 / 647 | 10 % | 1,000 | 11 % / 4 % | 2,110 |
| Midland | WCD | 644 / 401 | 1,117 ft (4.7) | 1,644 / 656 | 14 % | 1,181 | 10 % / 2 % | 1,803 |

Full tables: `spacing_by_bench.csv` (also benches with no BOX extent), `spacing_by_extent.csv`.

## Why per bench: Ruthless 11 Federal COM (Lea County)

Eleven wells tagged BS2_S (vendor "Second Bone Spring") across one mile, on production January-April 2022, at two
landings about 350 ft apart: six at 10,486-10,562 ft and five at 10,811-10,930 ft (survey lateral median).

| Measure | Gap | Reads as |
|---|---|---|
| Per bench (of record) | 348-457 ft | 11-12 WPS: what was drilled |
| Per landing | 824-1,107 ft | 5-6 WPS in each of two landings |
| Blended map at this DSU | 499 ft | 10.6 WPS, 10 rows across the mile against 11 drilled |

Per landing with one row per bench would have placed about 6 sticks here. Per bench carries the count; the vertical
arrangement is a separate fact for the generator (open items).

## Cross-check against `lateral_closer_xy_ft`

Compared on population wells where Novi's value is bounded (not NULL, not 2800.0) and this method also finds a
neighbour that was on production when the well came on. Thresholds were fixed before the first run: median
difference within 50 ft and at least 70 % of wells within max(100 ft, 15 %).

| | Wells | Median (this - Novi) | Within max(100 ft, 15 %) | Verdict |
|---|---|---|---|---|
| Per bench (of record): Delaware | 16,546 | -8 ft | 65.0 % | **fails agreement** |
| Per bench (of record): Midland | 20,938 | -8 ft | 70.3 % | passes, barely |
| Per landing (diagnostic): Delaware | 15,325 | +1 ft | 75.3 % | passes |
| Per landing (diagnostic): Midland | 20,108 | +1 ft | 83.2 % | passes |

- **The measure of record fails this check in the Delaware.** The two disagree because they measure different
  things: Novi counts the nearest well in the same ZONE, which is finer than a bench, so it does not see the other
  landing of a staggered development. Where the well and its neighbour are landed within 75 ft, agreement is 82.6 %
  / 88.5 %; where they are not, 27 % / 17 %.
- The failure is therefore a definitional difference, and per bench is kept deliberately (decision 3). The
  cross-check does not validate the per-bench number where a bench holds two landings; it validates the gap
  geometry.
- Unbounded class: of 3,407 population wells Novi marks 2800.0, this method finds a neighbour for 815 (24 %); of
  42,197 Novi-bounded wells it finds none within 2,800 ft for 4,713 (11 %).

## Floor: 1,320 ft, not 1,540 ft

- Gap histogram: a sharp peak at 1,320 ft in both basins, nothing at 1,540 ft. Within 5 % of 1,320 ft: 15.5 % of
  Delaware gaps and 7.3 % of Midland; within 5 % of 1,540 ft: 4.5 % and 2.3 %, the background level (the band
  between them holds 2.9 % / 1.3 %).
- Sparse benches: BS1_S 28 % near 1,320 vs 5 % near 1,540; BS2_C 23 % vs 8 %; BS3_S 23 % vs 9 %; DEAN 17 % vs 5 %.
- One-mile-wide DSUs fully developed on a bench since 2016 within 12 months (`one_mile_dsu_wells_vs_gap.csv`):
  with 4 wells across (414 Delaware, 377 Midland DSU x bench) the median gap is 1,187 / 1,114 ft, upper quartile
  1,303 / 1,271 ft. Setback-packed 4-well spacing would be 1,540 ft; almost none reach it.
- Novi draws 1,320 ft on every 4 WPS bench.
- For 1,540 ft: arithmetic ((5,280 - 660) / 3) and a wide tail with no mode (10 % of Delaware gaps and 3.9 % of
  Midland exceed 1,617 ft).

## Tight cap: 440 ft

- 660 ft is a real pattern (a clear peak), but per bench it is not the tightest thing operators do: 19.5 % of
  Delaware and 28.5 % of Midland gaps are under 660 ft, and 5.0 % / 7.2 % are under 440 ft. About 40 % of the
  sub-660 gaps are between wells at two landings.
- One-mile DSUs with 10 same-bench wells across: median gap 503 ft (7 Delaware) and 443 ft (11 Midland); with 11:
  394 and 433 ft.
- A 660 ft cap would hold Ruthless 11 at 8 WPS. A 440 ft cap lets an 11 WPS development through.
- Neighbourhood medians (3 mi) under 660 ft: 7.6 % Delaware, 15.1 % Midland; under 440 ft: 0.6 % and 1.4 %.
- On the blended map nothing sits at the cap (the surface averages neighbours), and 2.1 % of Delaware and 7.1 % of
  Midland DSU x bench are tighter than 660 ft: mostly Midland LSSH (25 % of its DSUs) and WCA_1 (16 %), Delaware
  AVA_0 (22 %) and AVA_1 (13 %).

## The spacing map: blended surface

Michael's model for a mature bench: nested contours, about 8 WPS in the core, 6 around it, 4 at the fringe, because
operators drilled the best rock first and stepped outward; the extent is that envelope. A gap in development inside
the core must not drop to a default.

**Rule.** spacing = band - c (band - weighted median), c = n_eff / (n_eff + 1).
- weighted median: per-bench gaps of the bench's wells, weight exp(-0.5 (d / 3 mi)^2), d = DSU polygon to well,
  wells out to 7.5 mi; n_eff = sum of the weights.
- band: median gap of the bench's wells in the DSU's band, where bands are 0-2, 2-5, 5-10 and 10+ mi inside the
  bench's BOX extent edge; a band with fewer than 20 wells -> 1,320 ft.
- clamped to 440-1,320 ft.

**The band pattern it relaxes to** (`bands_spacing.csv`), median gap by miles inside the extent edge:

| Bench | 10+ mi | 5-10 mi | 2-5 mi | 0-2 mi | Shape |
|---|---|---|---|---|---|
| Delaware WCA_1 | 869 ft | 979 | 1,082 | 1,316 | steady widening outward |
| Delaware WCA_2 | 939 | 1,016 | 1,056 | 1,307 | widening outward |
| Delaware BS2_S | 836 | 973 | 1,125 | 1,317 | steady widening outward |
| Delaware BS1_S | 1,039 | 1,244 | 1,277 | 1,316 | tight core only |
| Delaware BS3_S | 1,254 | 1,250 | 1,253 | 1,305 | none |
| Midland WCA_1 | 763 | 736 | 795 | 1,001 | flat, then looser in the last 2 mi |
| Midland LSSH | 681 | 679 | 848 | 1,026 | flat, then looser from 5 mi out |
| Midland WCB_1 | 826 | 839 | 879 | 958 | gentle |
| Midland DEAN | 884 | 1,184 | 1,199 | 1,055 | tight core, no trend outside it |

**Hold-out.** Targets: DSU x bench with their own value (six or more gaps within 1 mi). Each method predicts the
target from wells farther than 1, 2 or 3 mi. Kernel width and k were picked on half the targets; every number is
from the other half (6,096). Median error, ft:

| Wells hidden within | Delaware: chain / chain + band / blend | Midland: chain / chain + band / blend |
|---|---|---|
| 1 mi | 129 / 128 / 119 | 82 / 83 / 77 |
| 2 mi | 161 / 152 / 137 | 104 / 102 / 87 |
| 3 mi | 396 / 185 / 148 | 506 / 120 / 91 |
| 2 mi, targets where the chain has no control | 323 / 194 / 161 | 352 / 170 / 146 |
| P90 error, 2 mi | 500 / 438 / 402 | 405 / 337 / 305 |
| Adjacent DSUs differing by more than 200 ft (all 49,554) | - / 16.2 % / 2.5 % | - / 14.8 % / 2.2 % |

("chain" = median of wells within 1 -> 2 -> 3 mi with six or more gaps, else 1,320 ft; "chain + band" = the same
with the band median as the default. Both were decided and then superseded; see the history.)

- **Adoption test, fixed before the first surface run: the blend passes in both basins.** Median error below the
  chain's at 1 and 2 mi; P90 within 10 %; outer 0-2 mi band no worse (Delaware 87 vs 94 ft, Midland 108 vs 130 ft).
- Against chain + band it changes gross rows by -1.0 % (Delaware) and -0.4 % (Midland); the outer 0-2 mi band gains
  1.6 % / 2.3 %.
- It smooths peaks as well as holes: an isolated tight pocket is pulled toward its surroundings, a broad dense core
  is not.
- The hold-out cannot see undrilled ground: every target sits in drilled acreage. What the map does in a fringe
  with no wells for 7.5 mi is the band value, by construction, not by test.
- Files: `blend_holdout.csv`, `blend_tuning.csv`, `blend_smoothness.csv`, `blend_vs_record.csv`,
  `spacing_dsu_bench_blend.csv.gz` (not committed).

## What changes against Novi's sticks

Novi spacing is quantized by bench (medians of exactly 660, 754, 880, 1,320 or about 2,640 ft) and essentially
uniform across a bench. Compared on 26,729 DSU x bench where Novi has sticks and the bench's BOX extent reaches the
DSU (25,676 with a measurable Novi gap), against the blended map (`novi_vs_blend_summary.csv`):

| | Delaware | Midland |
|---|---|---|
| Mean spacing, Novi -> BOX | 1,276 -> 1,124 ft | 1,224 -> 960 ft |
| BOX within 10 % of Novi | 44 % | 29 % |
| BOX tighter by more than 10 % | 38 % | 55 % |
| BOX wider by more than 10 % | 19 % | 15 % |

- **Little change**: BS1_S (73 % of DSUs within 10 %), BS3_S (63 %).
- **BOX wider (fewer wells)**: Delaware AVA_2 (Novi 660 ft -> 983 ft, 72 % of DSUs wider), BS2_S (Novi 880 ft ->
  1,084 ft, 64 % wider), WCA_1 / WCA_2 / WCXY (52-68 % wider).
- **BOX tighter (more wells)**: Midland WCC and WCD (Novi 1,760-1,950 ft -> about 1,030-1,160 ft, 93-96 % of DSUs
  tighter), DEAN, JM and MS (69-70 % tighter), Delaware WCC (68 %) and WCB_1 (62 %).
- **Gross rows** (Novi sticks + existing same-bench wells, against BOX rows across the DSU): Delaware +0.9 %,
  Midland +50 %. Indicative only: before existing-well pinning and the 2b no-place cull, and not a spacing effect
  alone, because Novi does not fill many Midland DSUs (DEAN reads +100 %).

Two things seen on the way, not investigated:

- 35,929 of 87,182 Midland Novi sticks (41 %) have their midpoint outside every 2026Q3 polygon (Delaware: 187 of
  170,215). They are outside this comparison.
- 142,794 of the 221,281 sticks inside a polygon sit on a bench whose BOX extent does not reach that DSU, including
  13,033 of 14,683 Novi WCXY sticks outside the hand-drawn extent. That is the bench-eligibility change, for gate 3b.

## Open items

- **Vertical arrangement inside a bench.** Per-bench density with one landing surface puts every stick in one plane.
  Where local wells show two landings (BS2_S 44 % of pairs, Delaware WCC 40 %, BS3_C 31 %, LSSH 29 %), the generator
  should alternate sticks between them. At Ruthless 11 a single BS2_S surface lands near 10,700 ft, between the two
  real landings; the evidence screen already flags one of those wells as a likely mis-tag. Whether 350 ft apart is a
  second row or a second bench is a tag question.
- **Bands by side of an extent.** Distance to the nearest edge treats the Central Basin Platform edge and the
  eastern shelf edge alike. Not tested.
- **Small extents.** The Avalon extents have no 10+ mi band and 21-108 wells per band.
- The 75 ft landing test uses the landing-surface depth evidence; some "two landing" pairs are depth noise or dip.
- Planned-survey wells are in the neighbour search by their tag but never measured; where one is the nearest
  neighbour the well is dropped (2,361 wells), which thins New Mexico.
- EPSG:3083 distances run about 0.2 % short of true (-2 ft on 1,000 ft). Rows are gross slots, not inventory.

## Decision history

1. **2026-11-12, first pass (per bench).** Floor 1,320 ft and cap 660 ft decided. The Delaware cross-check failed.
2. **2026-11-12, per landing.** On my recommendation the gap was restricted to same-landing neighbours (within
   75 ft), reading the cross-check failure as a method fault. Delaware median 1,133 ft, Midland 863 ft. **Reversed
   on 2026-11-13** (decision 3): the cross-check showed Novi measures per zone, not that per bench was wrong.
3. **2026-11-12, radius chain.** Local median within 1 -> 2 -> 3 mi with six or more gaps, else 1,320 ft. Merged in
   PR #244.
4. **2026-11-13, band default.** No local control -> the extent-band median instead of a flat 1,320 ft. Merged in
   PR #244. Bands alone lose to nearby wells as a predictor; as a default they cut the error where the chain had
   no control.
5. **2026-11-13, smooth surface relaxing to the floor.** Tested, not adopted: it carried a few wells' spacing far
   into undrilled fringe.
6. **2026-11-13, blended surface relaxing to the band.** Adopted (decision 4). Supersedes 3 and 4.
7. **2026-11-13, back to per bench, cap 440 ft** (decisions 2 and 3), after Ruthless 11. Everything above was
   re-run on per-bench gaps; the numbers in this document are from that run.

Not committed (regenerate with the scripts): `well_gaps.csv.gz`, `spacing_dsu_bench.csv.gz`,
`spacing_dsu_bench_surface.csv.gz`, `spacing_dsu_bench_blend.csv.gz`, `novi_vs_box_dsu_bench.csv.gz`.
