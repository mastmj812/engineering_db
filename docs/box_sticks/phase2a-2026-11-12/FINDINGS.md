# BOX sticks, phase 2a: realized well spacing (2026-11-12)

Read-only. `python -m scripts.box_sticks_phase2a --out docs/box_sticks/phase2a-2026-11-12 --cache <phase 0 cache>`.
Plan: `docs/box_sticks_plan.md`. Live tags, cache pulled 2026-11-12 (56,842 evidence wells, 257,397 Novi sticks, as
in phase 0). Nothing was written to the warehouse.

## Headline

| | Delaware | Midland |
|---|---|---|
| Producers in the population (first production >= 2016, evidence rules, two-part screen) | 22,598 | 23,985 |
| Wells measured / unique pairs | 13,899 / 8,950 | 18,225 / 11,741 |
| Median gap | 1,005 ft (5.3 WPS) | 825 ft (6.4 WPS) |
| P10 (wide) / P90 (tight) | 1,617 / 539 ft (3.3 / 9.8 WPS) | 1,318 / 485 ft (4.0 / 10.9 WPS) |
| DSU x bench neighbourhoods | 29,719 | 19,835 |
| ... with local control (>= 6 gaps within 3 mi) | 61.9 % | 72.8 % |
| ... no control -> 1,320 ft | 38.1 % | 27.2 % |

WPS = 5,280 / spacing. P10 is the wide end (SPE: P10 >= P50 >= P90 in feet); in WPS the order flips.

- **Operators space on three patterns: 660, 880 and 1,320 ft (8, 6 and 4 WPS).** Both basins show sharp peaks at
  exactly those values and none at 1,540 ft (`gap_histograms.png`).
- **Recommendation: floor 1,320 ft, tight cap 660 ft.** Evidence for both below.
- **The Novi cross-check fails its own agreement threshold in the Delaware** (65.0 % against a 70 % bar; Midland
  70.3 %). The cause is identified, not tuned away: see "Cross-check".

## Method, grain and filters

- **Gap** = the `dealintake/spacing.py` method with the deal-intake parameters of record (parallel within 15 deg,
  alongside >= 30 % of the well, median perpendicular distance over the shared length, a neighbour under 300 ft is
  the same slot). The script re-implements it on arrays so it can return WHICH neighbour; against the original
  `neighbour_gaps_ft` it agrees on 99.8 % of 1,220 Delaware BS1_S wells and 99.6 % of 1,004 Midland DEAN wells
  (bar 99 %; median difference -2 ft, from working in EPSG:3083 instead of a local frame).
- **Neighbour search universe**: all 60,826 horizontal producers with a lateral line and a live tag, any vintage,
  any evidence status, so an older or unjudged well lying between two wells is seen.
- **A well is measured** when it is in the population and its NEAREST same-tag neighbour (300 to 2,800 ft) is also
  in the population and came on within 12 months of it. Not measured, of 46,583: nearest neighbour from another
  campaign 6,757; no neighbour within 2,800 ft 4,118; nearest neighbour not evidence (planned survey, round-100
  TVD, screened out) 2,361; nearest neighbour pre-2016 1,223.
- **The 12-month window barely matters**: bench medians move under 30 ft at 6 or 24 months, and under 50 ft for most
  benches with no window at all (`spacing_by_bench.csv`: `median_183d_ft`, `median_730d_ft`, `median_any_neighbour_ft`).
- **Neighbourhood** = one Novi 2026Q3 DSU polygon x one bench whose BOX record extent it intersects (WCXY: the
  hand-drawn extent file). Local spacing = median gap of same-bench measured wells within 1, then 2, then 3 mi of the
  polygon, first radius with >= 6 gaps (the deal-intake chain). 49,554 neighbourhoods.
- Same bench = same live `formation_blueox` code. WCA_1, WCA_2 and WCXY are measured separately.

## Spacing by bench

Wells / pairs, well-level median with WPS, P10 wide / P90 tight, the median for pairs landed within 75 ft of each
other, share of pairs landed MORE than 75 ft apart, DSUs intersecting the extent, share with local control, median
of the local values, Novi's median stick gap for the bench, and cross-check agreement.

| Basin | Bench | Wells / pairs | Median (WPS) | P10 / P90 ft | Same-landing median ft | Two landings | DSUs | Local control | Local median (WPS) | Novi stick gap ft | Cross-check |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Delaware | AVA_0 | 190 / 119 | 877 ft (6.0) | 1,433 / 497 | 876 | 3 % | 244 | 81 % | 891 ft (5.9) | 880 | 79 % |
| Delaware | AVA_1 | 202 / 136 | 835 ft (6.3) | 1,528 / 492 | 855 | 26 % | 408 | 64 % | 841 ft (6.3) | 2,615 | 51 % |
| Delaware | AVA_2 | 158 / 100 | 907 ft (5.8) | 1,408 / 543 | 951 | 20 % | 482 | 62 % | 908 ft (5.8) | 880 | 72 % |
| Delaware | **BS1_S** | 510 / 327 | 1,245 ft (4.2) | 1,766 / 731 | 1,247 | 16 % | 2,359 | 38 % | 1,248 ft (4.2) | 1,319 | 79 % |
| Delaware | BS2_C | 320 / 202 | 1,269 ft (4.2) | 1,852 / 692 | 1,286 | 17 % | 1,169 | 51 % | 1,180 ft (4.5) | 1,319 | 77 % |
| Delaware | BS2_S | 1,729 / 1,141 | 940 ft (5.6) | 1,378 / 459 | 1,187 | 44 % | 2,401 | 83 % | 1,119 ft (4.7) | 880 | 52 % |
| Delaware | BS3_C | 923 / 588 | 1,122 ft (4.7) | 1,700 / 708 | 1,199 | 31 % | 2,840 | 52 % | 1,107 ft (4.8) | 1,319 | 67 % |
| Delaware | BS3_S | 1,146 / 725 | 1,258 ft (4.2) | 1,703 / 648 | 1,287 | 21 % | 3,608 | 52 % | 1,236 ft (4.3) | 1,319 | 71 % |
| Delaware | WCA_1 | 3,171 / 2,077 | 907 ft (5.8) | 1,551 / 528 | 934 | 18 % | 4,457 | 74 % | 966 ft (5.5) | 660 | 66 % |
| Delaware | WCA_2 | 2,283 / 1,468 | 974 ft (5.4) | 1,628 / 565 | 1,023 | 17 % | 4,457 | 71 % | 970 ft (5.4) | 754 | 67 % |
| Delaware | WCB_1 | 951 / 598 | 1,044 ft (5.1) | 1,668 / 621 | 1,091 | 16 % | 2,664 | 66 % | 1,035 ft (5.1) | 1,320 | 76 % |
| Delaware | WCB_2 | 560 / 349 | 1,176 ft (4.5) | 1,772 / 660 | 1,211 | 21 % | 2,280 | 46 % | 1,146 ft (4.6) | 1,320 | 75 % |
| Delaware | WCC | 433 / 277 | 881 ft (6.0) | 1,785 / 421 | 1,157 | 40 % | 1,051 | 51 % | 901 ft (5.9) | 1,320 | 52 % |
| Delaware | WCXY | 1,030 / 660 | 999 ft (5.3) | 1,673 / 526 | 1,040 | 19 % | 1,299 | 78 % | 1,079 ft (4.9) | 879 | 60 % |
| Midland | **DEAN** | 700 / 452 | 1,019 ft (5.2) | 1,503 / 659 | 1,035 | 7 % | 2,271 | 40 % | 1,076 ft (4.9) | 1,320 | 83 % |
| Midland | JM | 1,231 / 770 | 910 ft (5.8) | 1,530 / 644 | 958 | 14 % | 1,826 | 84 % | 976 ft (5.4) | 1,320 | 77 % |
| Midland | LSSH | 4,081 / 2,674 | 701 ft (7.5) | 1,060 / 398 | 792 | 29 % | 2,821 | 82 % | 781 ft (6.8) | 880 | 58 % |
| Midland | MS | 1,190 / 765 | 966 ft (5.5) | 1,547 / 650 | 973 | 9 % | 1,902 | 71 % | 1,015 ft (5.2) | 1,320 | 82 % |
| Midland | WCA_1 | 5,160 / 3,363 | 769 ft (6.9) | 1,163 / 461 | 799 | 18 % | 3,593 | 87 % | 813 ft (6.5) | 880 | 68 % |
| Midland | WCB_1 | 3,433 / 2,193 | 843 ft (6.3) | 1,308 / 524 | 855 | 12 % | 3,397 | 87 % | 867 ft (6.1) | 880 | 73 % |
| Midland | WCB_2 | 1,382 / 877 | 876 ft (6.0) | 1,408 / 636 | 876 | 5 % | 1,357 | 79 % | 894 ft (5.9) | 880 | 80 % |
| Midland | WCC | 239 / 146 | 970 ft (5.4) | 1,781 / 647 | 986 | 10 % | 494 | 62 % | 900 ft (5.9) | 2,110 | 81 % |
| Midland | WCD | 644 / 401 | 1,117 ft (4.7) | 1,644 / 656 | 1,158 | 14 % | 2,174 | 41 % | 1,195 ft (4.4) | 1,803 | 82 % |

Full tables: `spacing_by_bench.csv` (also benches with no BOX extent), `spacing_by_extent.csv` (control by radius:
only 8-52 % of DSUs resolve at 1 mi; the rest need 2 or 3 mi).

**Focus benches** (`spacing_map_delaware_BS1_S.png`, `spacing_map_midland_DEAN.png`):

- **Delaware BS1_S**: 510 wells, 327 pairs, 1,245 ft (4.2 WPS). 885 of 2,359 DSUs (38 %) have local control, in
  the developed core; the west and south of the extent have none and take 1,320 ft. Where there is control the
  local median is 1,248 ft with only 1.6 % of DSUs under 660 ft. 28 % of gaps sit within 5 % of 1,320 ft.
- **Midland DEAN**: 700 wells, 452 pairs, 1,019 ft (5.2 WPS). 916 of 2,271 DSUs (40 %) have local control; local
  median 1,076 ft, none under 587 ft. DEAN is developed tighter than Novi's blanket 1,320 ft where it is developed
  at all.

## Cross-check against `lateral_closer_xy_ft`

Compared on 37,484 population wells where Novi's value is bounded (not NULL, not 2800.0) and this method also finds a
same-tag neighbour that was on production when the well came on. Thresholds were fixed before the first run.

| | Wells | Median (this - Novi) | Bar | Within max(100 ft, 15 %) | Bar | Verdict |
|---|---|---|---|---|---|---|
| Delaware | 16,546 | -8 ft | 50 ft | 65.0 % | 70 % | **fails agreement** |
| Midland | 20,938 | -8 ft | 50 ft | 70.3 % | 70 % | passes, barely |

- The central tendency agrees (median difference -8 ft, 56 % of wells within 50 ft). The disagreement is one-sided:
  this method is tighter on 24 % of wells and wider on 8 %.
- **Cause (diagnosed after the fact, the verdict stands):** where the well and its neighbour are landed within 75 ft
  of each other, agreement is 82.6 % Delaware / 88.5 % Midland. Where they are landed more than 75 ft apart it is
  27 % / 17 %. Novi's "same zone" is finer than a `formation_blueox` tag: it does not count a neighbour in the other
  landing of a staggered pattern, the tag does. The benches that fail worst are the ones with two landings inside
  one tag: Delaware BS2_S (52 %), WCC (52 %), AVA_1 (51 %), Midland LSSH (58 %).
- Unbounded class: of 3,407 population wells Novi marks 2800.0, this method finds a neighbour for 815 (24 %); of
  42,197 Novi-bounded wells it finds none within 2,800 ft for 4,713 (11 %).
- Consequence: **a tag-level gap is a flattened gap.** For BS2_S it reads 940 ft where wells in the same landing sit
  1,187 ft apart; LSSH 701 vs 792 ft; Delaware WCC 881 vs 1,157 ft. See decision 3.

## 1,320 or 1,540 ft for the 4 WPS floor

Evidence for 1,320 ft:

- Gap histogram: a sharp peak at 1,320 ft in both basins, nothing at 1,540 ft. Within 5 % of 1,320 ft: 15.5 % of
  Delaware gaps and 7.3 % of Midland; within 5 % of 1,540 ft: 4.5 % and 2.3 %, which is the background level
  (the 1,386-1,463 ft band between them holds 2.9 % / 1.3 %).
- Sparse benches, the ones a floor actually governs: BS1_S 28 % near 1,320 vs 5 % near 1,540; BS3_S 23 % vs 9 %;
  BS2_C 23 % vs 8 %; DEAN 17 % vs 5 %.
- One-mile-wide DSUs fully developed on a bench since 2016 within 12 months (`one_mile_dsu_wells_vs_gap.csv`):
  with 4 wells across (414 Delaware, 377 Midland DSU x bench) the median gap is 1,187 / 1,114 ft, upper quartile
  1,303 / 1,271 ft. Setback-packed 4-well spacing would be 1,540 ft; almost none reach it.
- Neighbourhood medians above 1,320 ft: 16.0 % of Delaware local values and 8.8 % of Midland; in the 1,540 band
  3.8 % and 2.8 %.
- Novi itself draws 1,320 ft on every 4 WPS bench (stick gap medians 1,319-1,320 ft).

Evidence for 1,540 ft: none as a pattern. Its only support is arithmetic ((5,280 - 660) / 3) and the wide tail:
10 % of Delaware gaps and 3.9 % of Midland exceed 1,617 ft, with no mode.

Cost of the choice (`cap_floor_choices.csv`, gross rows across each DSU, all 49,554 neighbourhoods, before existing
wells and no-place culls): a 1,540 ft floor removes 5.5 % of Delaware rows and 3.5 % of Midland relative to 1,320 ft.

**Recommendation: 1,320 ft.**

## Tight cap

| Local median below | Delaware (share of local values) | Midland |
|---|---|---|
| 660 ft (8 WPS) | 7.6 % | 15.1 % |
| 587 ft (9 WPS) | 2.9 % | 5.9 % |
| 528 ft (10 WPS) | 1.7 % | 4.2 % |
| 440 ft (12 WPS) | 0.6 % | 1.4 % |

- 660 ft is itself a real pattern (a clear peak in both basins). Below it there is a thin tail and no mode.
- The sub-660 values are concentrated: Midland LSSH (32 % of its local values under 660 ft), Midland WCA_1 (25 %),
  WCB_1 (14 %); Delaware AVA_0 / AVA_1 (25 %), WCC (22 %), AVA_2 (17 %), BS2_S (12 %). Every other bench is under 10 %.
- 43 % of Delaware and 39 % of Midland gaps under 660 ft are between wells landed more than 75 ft apart (all gaps:
  23 % and 17 %). A good part of the sub-660 population is two landings read as one row.
- Cost: lowering the cap from 660 to 528 ft adds 1.3 % gross rows in the Delaware and 2.5 % in the Midland; to
  440 ft, 1.6 % and 3.3 %.

**Recommendation: 660 ft (8 WPS).** It is the tightest spacing operators repeat, and a single-landing stick row
should not copy a two-landing wine rack. The alternative, if tag-level well count matters more than per-landing
spacing, is 528 ft (10 WPS), which leaves only LSSH (11 %), Delaware WCC (12 %) and AVA_0 (8 %) clamped materially.

## What changes against Novi's sticks

Novi spacing is quantized by bench (medians of exactly 660, 754, 880, 1,320 or about 2,640 ft) and essentially
uniform across a bench. BOX spacing follows local drilling. Compared on 26,729 DSU x bench where Novi has sticks and
the bench's BOX extent reaches the DSU (25,676 with a measurable Novi gap), tight cap 660 ft, floor 1,320 ft
(`novi_vs_box_summary.csv`):

| | Delaware | Midland |
|---|---|---|
| Mean spacing, Novi -> BOX | 1,276 -> 1,181 ft | 1,224 -> 1,052 ft |
| BOX within 10 % of Novi | 50 % | 30 % |
| BOX tighter by more than 10 % | 28 % | 46 % |
| BOX wider by more than 10 % | 21 % | 24 % |

- **No control, both say 1,320 ft**: 72 % of Delaware default DSU x bench are within 10 % of Novi. BS1_S, BS2_C,
  BS3_C, BS3_S change little (65-82 % within 10 %).
- **BOX wider (fewer wells)**: Delaware AVA_2 (Novi 660 -> BOX about 1,250 ft), BS2_S (880 -> about 1,260 ft, 67 %
  of DSUs wider), WCA_1 / WCA_2 / WCXY (Novi 660-880 ft against local 970-1,080 ft, 57-70 % wider).
- **BOX tighter (more wells)**: Midland WCC and WCD (Novi 1,760-1,950 ft -> BOX at most 1,320 ft, about 90 % of DSUs
  tighter), JM and MS (Novi 1,320 -> local about 1,000 ft, about half tighter), Delaware WCC (61 % tighter).
- **Gross rows** (Novi sticks + existing same-tag wells, against BOX rows across the DSU): Delaware -2.5 %,
  Midland +40 %. Indicative only: this is before existing-well pinning and the 2b no-place cull, and it is not a
  spacing effect alone. Midland DEAN shows +74 % rows at identical 1,320 ft spacing because Novi does not fill
  those DSUs. Where both sides are at 1,320 ft the row arithmetic reproduces Novi within 3 % (5,652 DSU x bench).

Two things seen on the way, not investigated:

- 35,929 of 87,182 Midland Novi sticks (41 %) have their midpoint outside every 2026Q3 polygon (Delaware: 187 of
  170,215). They are outside this comparison.
- 142,794 of the 221,281 sticks inside a polygon sit on a bench whose BOX extent does not reach that DSU, including
  13,033 of 14,683 Novi WCXY sticks outside the hand-drawn extent. That is the bench-eligibility change, for gate 3b.

## Caveats

- **Wide local spread.** The deal-intake "mixed" flag (IQR / median > 0.15) fires on 77 % of Delaware and 73 % of
  Midland local values. On real wells it does not discriminate; the local median summarises a mix of patterns.
- **Control is mostly not close.** Local control at 1 mi covers 8-31 % of DSUs for most Delaware benches (Midland
  WCA_1 and LSSH about 50 %); the headline 62 % / 73 % needs the 2 and 3 mi steps.
- **Planned-survey wells** are in the neighbour search by their tag but are never measured; where such a well is the
  nearest neighbour the well is dropped (2,361 wells), which thins New Mexico.
- EPSG:3083 distances run about 0.2 % short of true (-2 ft on 1,000 ft).
- Rows are gross slots, not inventory.

## Decisions needed (gate 2, spacing half)

1. **Floor: 1,320 ft** (recommended) or 1,540 ft.
2. **Tight cap: 660 ft** (recommended) or 528 ft.
3. **Flattened or per-landing spacing** for tags that hold two landings (BS2_S, Delaware WCC, LSSH, BS3_C). This
   study measured the flattened, tag-level gap. A 660 ft cap limits the damage; a per-landing gap would need the
   75 ft rule applied before the neighbour is chosen, a re-run.
4. **Control radius**: keep the deal-intake 1 -> 2 -> 3 mi chain with >= 6 gaps, or tighten it and accept more
   1,320 ft defaults.

Not committed (regenerate with the script): `well_gaps.csv.gz`, `spacing_dsu_bench.csv.gz`,
`novi_vs_box_dsu_bench.csv.gz`.
