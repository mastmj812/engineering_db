# BOX sticks phase 6, step 1: design, with numbers from live

Written 2026-11-23 before any code. Read-only: `step1_probe.py` in this folder (every query in a READ ONLY transaction).
Record stick sets: 24 (Delaware, 46,153 sticks) and 25 (Midland, 33,122). Record forecast runs today: 32 (Delaware) and 30
(Midland), both on Novi sticks.

The end state (plan, phase 6): the runs on BOX sticks are the records, erebor and the land team's view are populated from BOX
sticks, econ is blank until Steven prices.

## What the swap does to the picture

| Measure (grain) | Delaware | Midland |
|---|---|---|
| Undrilled locations in `curated.erebor_locations` today (Novi PUD + RES sticks) | 170,215 | 87,182 |
| of which carry a forecast in the record run (sticks) | 48,148 (run 32) | 28,801 (run 30) |
| of which are "outside extent" or "emerging bench" (sticks) | 108,590 | 52,630 |
| Record BOX sticks (sticks) | 46,153 | 33,122 |
| on a bench with no BOX pool, or a pool with no record extent (sticks) | 0 | 0 |
| Rows in the land team's view today | 48,077 | 28,754 |

Every BOX stick sits on a BOX bench with a record extent, because the generator only places sticks there. The two large
"no forecast" classes of today (outside extent, emerging bench) have no BOX stick to apply to.

## Decision 1: what the nightly status means for a forecast

| Nightly status (sticks) | Delaware | Midland | Recommended treatment |
|---|---|---|---|
| open, not crowded | 45,013 | 32,967 | forecast |
| permitted | 701 | 72 | forecast; the status is stored on the row |
| pending (spud, DUC or completed, not yet producing) | 63 | 19 | forecast; the status is stored on the row |
| producing | 121 | 16 | left out of the run, as a realized stick is today |
| conflict | 29 | 2 | no forecast, class `not_covered_conflict`, both basins |
| crowded (a producer inside the stick's envelope at another landing) | 227 | 47 | no forecast, class `not_covered_conflict`, reason kept as crowded |

Counts are of status rows; a crowded stick is counted in the crowded row only. This makes "counts as inventory" in the nightly
and "can carry a forecast" in the run the same set. It extends D145 (a conflict stick is not a drillable location) from the
Midland to both basins: 31 sticks.

## Decision 2: the in-extent rule

Today a stick is in-extent when at least 50 % of its length is inside the bench's extent. The generator placed BOX sticks by
DSU (a DSU x bench is kept when at least 10 % of the DSU is inside the extent).

| Share of the stick's legs inside its extent (sticks) | Delaware | Midland |
|---|---|---|
| 50 % or more | 43,846 (95.0 %) | 31,413 (94.8 %) |
| more than 0, under 50 % | 1,750 | 1,400 |
| none | 557 | 309 |

**Recommended: every stored stick is in-extent** (the plan's "DSU intersects the extent"), with the stick's own inside share
stored on the row so the 3,150 edge sticks and the 866 sticks wholly outside can be filtered or looked at. The alternative,
keeping the 50 % rule, takes 4,016 sticks (5.1 %) out of the forecast as "outside extent".

## Decision 3: a two-leg (U-turn) stick

| Measure (U-turn sticks) | Delaware | Midland |
|---|---|---|
| Sticks | 8,128 (17.6 %) | 3,573 (10.8 %) |
| Legs + turn arc join into one continuous line | 8,128 of 8,128 | 3,573 of 3,573 |
| Gap between the two legs, median / max (ft) | 1,200 / 2,537 | 1,199 / 1,789 |
| Completed lateral, median (ft) | 8,029 | 8,010 |

Recommended rules:

- **Analog distance:** measured from the point midway between the two legs' midpoints. It is about 600 ft from either leg;
  the analog rings are miles wide.
- **Proximity to producers:** each leg is measured on its own, with its own heading, and the stick takes the more exposed
  leg's outcome. Never the straight line from heel to toe, which for a U-turn is a short line across the turn.
- **Lateral length:** the completed lateral (both legs, no arc), which is what the generator stored.

The effect of the proximity rule is measured on a pilot area in step 2 before any full build.

## Decision 4: spacing and lateral length come from the generator

| Measure | Delaware | Midland |
|---|---|---|
| Planned spacing on BOX sticks, P10 / P50 / P90 (ft) | 826 / 1,170 / 1,310 | 715 / 958 / 1,278 |
| Planned spacing in the record run (D64 guess), P10 / P50 / P90 (ft) | 743 / 1,058 / 1,322 | 756 / 882 / 1,547 |
| Record-run rows on the 880 ft default | 390 | 51 |
| Completed lateral, median: BOX single sticks / record run (ft) | 9,898 / 7,720 | 9,869 / 10,560 |

**Recommended: the generator's spacing and completed lateral replace the D64 nearest-stick guess**, with the source stored as
`generator`. Consequence to expect in step 3: Delaware locations are about 2,200 ft longer at the median than run 32's, so EUR
per location rises with length. Comparisons between runs are made per foot and by count, not per location.

## Decision 5: how a BOX stick is stored for erebor and the land team's view

- `curated.erebor_locations` keeps its producing-well arm and swaps its Novi arm for the record BOX sticks. Its only dependent
  object is `curated.box_scout_locations` (sql/69), a view. It stays one relation with one unique id, so erebor's tiles,
  selection and Highgrade keep their shape.
- `stick_id` = the BOX `location_id` (10,000,001 and up: positive, as the sign convention requires; no overlap with Novi ids
  or the negative PDP ids).
- `wellstick_geom` = the drilled path as ONE line (legs + arc for a U-turn; all 11,701 join cleanly). Everything that takes a
  start point, a midpoint or an intersection from a single line keeps working.
- `tvd` = the stick's landing TVD; `ll_ft` = completed lateral; `formation_blueox` = the stick's bench; `pad_name` from the DSU.
- The Novi-only columns (Novi NPV / PV / EUR, depletion and support scores) are NULL on a BOX stick. erebor stopped showing
  them in the October overhaul; step 2 checks every reader, including deal-intake.
- The gunbarrel draws one point per leg (the preview's code path becomes the main one).
- The dashed preview layer and its switch are removed: BOX sticks are the locations.
- Novi sticks stay available to narvi, deal-intake and anduin through `curated.intel_locations` until phase 7.

## Bars for step 3 (the two stored runs, before the cutover)

| Bar | Measure (grain) | Passes when |
|---|---|---|
| P1 | Identity (sticks, per basin) | forecast rows + not-covered rows + producing sticks left out = record sticks; one row per stick |
| P2 | Volumes (forecast rows) | every row's monthly volumes sum to its stored EUR within 0.1 % (rule 6); the batch's own harness equivalence check passes |
| P3 | Forecast share (sticks that count as inventory, per basin) | at least 80 % carry a forecast. Reference: 85 % (run 32) and 89 % (run 30) of screened in-extent sticks today; the rest are "no drilled precedent" |
| P4 | Oil EUR per foot (median, per pool with 200 or more forecast rows in both runs) | within 10 % of the record run's median for the pool. A pool outside 10 % is explained by spacing, lateral, proximity or location mix, and nothing is tuned to pull it in |
| P5 | Record sets only | every stick of the run is a stick of sets 24 / 25 as they stood at the pull; the run names the set |
| P6 | Stored, not yet record | runs 30 and 32 and everything that reads them are unchanged by the stores (row counts and the land team's view identical before and after) |

Reported with no bar: proximity outcome mix against the record run; forecast rows by tier (validated / provisional); the
count and total length of forecast locations per pool; EUR per location.

## Bars for step 4 (the cutover)

| Bar | Measure | Passes when |
|---|---|---|
| C1 | `curated.erebor_locations` (rows) | undrilled rows = record sticks not producing (by identity, per basin); producing-well rows unchanged in count; unique on `stick_id`; the geography indexes (sql/26) rebuilt and used (EXPLAIN) |
| C2 | Records | one record run per basin, the BOX-stick runs; runs 30 and 32 kept, not record |
| C3 | Land team's view (rows) | = forecast rows of the record runs on undrilled sticks, per basin; econ columns NULL |
| C4 | erebor | every undrilled stick on the map carries a forecast or a stated class; a selection's counts equal an independent count; econ shows "not yet priced" |
| C5 | Nightly | the next nightly is green and refreshes the relation |
