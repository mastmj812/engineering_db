# BOX step 4 — TC areas on WCA (gate 4 summary)

Built 2026-10-09 on branch `claude/box-step4-tc-areas`. Read-only against the warehouse; **nothing
stored**. `sql/57` (box.tc_area) is authored and container-validated, **not applied**. It needs Michael's
"go apply", and the `--store --record` write needs its own go-ahead.

**Review surface:** `areas_WCA.html`. Serve with `python -m http.server 8766 --directory docs/box`
(or the `box-static` launch config), then open `/step4-2026-10-09/areas_WCA.html`.

## 1. What exists

| File | What |
|---|---|
| `areas_WCA.html` | Interactive area map with a response toggle (12-mo / 24-mo / Novi 30-yr EUR per ft) and a nested-level toggle (k = 6, 10, 14, 20, **34 = pick**, 39 = CV minimum). Click an area for its card. Also on the page: the 3-panel gut-check figure, the CV curve, the sensitivity table, and the per-area table. |
| `areas_WCA.csv` | One row per area at the pick: n12 / n24 / n_eur, P50 and P10 (high) / P90 (low) in bbl/ft, member tags, median first-prod year, top operator, D1 PUD counts, review flags. |
| `areas_levels_WCA.csv` | The same table for every level shown on the map. |
| `areas_WCA_v1.geojson` | Area polygons at the pick (EPSG:4326) with the per-area stats. |
| `cv_WCA.csv`, `sensitivity_WCA.csv` | The CV curve (k = 1..60) and the knob sensitivity. |
| `wells_area_WCA.csv` | Every cohort well → area_no, with its responses and cohort flags. |
| `summary.json` | Run stamp, identities, pick, R² values. |

Code: `box/tc_area.py` (pure method), `box/tc_area_report.py` (inputs, stats, page),
`box/tc_area_store.py` (the `--store` write), `scripts/box_tc_areas.py` (CLI, ~80 s),
`sql/57_box_tc_area.sql` + `scripts/apply_box_tc_area.py`, and `tests/test_box_tc_area.py` (11 DB-free tests).

## 2. Inputs and cohorts (D9)

- **Extent of record:** `box.extent` id 6 (WCA v1 generated, 6,168.7 sq mi).
- **Well set:** gate-1 `wells_final_WCA.csv` (WCA_1 + WCA_2 pooled, WCXY as one-way evidence, D19/D20).
- **Data:** through 2026-08-01.

| Response | Cohort | n |
|---|---|---|
| **12-mo oil / ft** (the areas are built on this) | the gate-1 `cohort` flag (fp ≥ 2016-01-01, lateral 6,000–13,000 ft, 12 full months, cum-12 > 0), midpoint inside the extent | **7,553** (9 of 7,562 fall outside the extent) |
| 24-mo oil / ft | same filter, 24 full months, cum-24 > 0 | 6,842 |
| bo / ft | same vintage and lateral filter; Novi 30-yr oil EUR ÷ lateral (life cum where Novi has none, 0 such wells) | 8,182 |

Grain is wells. Responses are Novi WellDetails cum pass-throughs, calendar months from first
production. Vintage is normalized **by filter only**, and operator / completion confounding is **not
removed** (D9, stated on the page). The Novi 30-yr EUR is a vendor forecast horizon, not the 50-yr
technical EUR, and is used here as a screen for the gut check only. Percentiles follow SPE: P10 = HIGH.
Pool P50 of 12-mo oil is 21.7 bbl/ft (21,700 bbl/1,000 ft).

## 3. Method

1. Tile the extent with 1-mi hexagons: 7,386 cells. Each well goes to the cell holding its lateral midpoint.
2. **Contiguity-constrained Ward agglomeration** on log(12-mo oil/ft). Adjacent regions merge, cheapest
   rise in within-area sum of squares first. Empty cells carry a light pseudo-observation from a
   15-nearest-well median, so they join the neighbour they resemble. Until every area holds ≥ 10 cohort
   wells (the D9 floor), only merges involving a sub-floor area are allowed.
3. The merges are nested, so one run yields every k, and the areas always tile the extent.
4. This is the constrained-hierarchical (REDCAP) member of the max-p / SKATER family the plan names.
   I tried plain MST-cut SKATER first. On a synthetic two-block world it carved the step into chunks
   along the smoothed gradient. The tests pin both behaviours: it finds a step, and it stays at ≤ 2
   areas when there is no signal.

## 4. How many areas, and why: **34**

The number of areas comes from a 5-fold cross-validation on 3-mi blocks:

- Each fold rebuilds the areas without its held-out blocks, then predicts every held-out well by its
  area's training median. That is the PUD situation: ground the areas never saw.
- The pick is the smallest k whose CV error is within one **paired** standard error of the minimum. The
  same held-out wells are scored at both k, differences are summed per 3-mi block, and the SE is taken
  over blocks.
- My first pass used the fold-to-fold SE instead. It collapsed to k = 2, because the folds differ in how
  hard their ground is, which is the same for every k and swamps the k-to-k difference.

| | held-out R² of log(12-mo oil/ft) |
|---|---|
| one pool median (k = 1) | −0.01 |
| k = 6 | 0.17 |
| k = 14 | 0.19 |
| **k = 34 (pick)** | **0.21** |
| k = 39 (CV minimum) | 0.21 |
| a local 15-well median, no areas at all (the ceiling) | 0.22 |

In-sample, the 34 areas explain 41 % of the well-to-well variance. Across areas, the rank agreement of
the area P50s is 0.98 between 12-mo and 24-mo, and 0.90 between 12-mo and Novi 30-yr EUR/ft. A
regionalization run on the 24-mo response alone picks k = 18 at R² 0.21.

**The exact k is weakly identified.** Across cell size {1, 1.5 mi} × field kNN {10, 15, 25}, the pick
ranges from 10 to 49, while held-out R² at the pick stays between 0.19 and 0.21. The curve is flat past
about 14 areas. The areas capture nearly all the spatial signal a well-by-well local estimate gets
(0.21 vs 0.22). The remaining ~78 % of variance is well-to-well (completion, spacing, operator), which
no map resolves.

## 5. Gut check: what the map shows

- **The sweet spot is north-central, along and just north of the state line.** Southern Eddy and Lea
  around 32.0–32.25° N, −103.6 to −103.9:
  - area 11, EOG: 39.0 bbl/ft, n 152
  - area 5, Devon: 37.7, n 205
  - area 8, EOG: 29.6, n 636
  - area 9, Occidental: 25.8, n 1,810
- **Performance falls off toward every edge:**
  - W (Reeves / Culberson flank, −104.2 to −104.4): areas 4, 10, 16, 17 at 7–14 bbl/ft
  - N (32.5° N+): areas 1, 2, 3 at 13–15
  - far S and E (Ward / Pecos / Reeves S, 31.0–31.4° N): areas 27, 28, 31–33 at 9–13
  - The middle-Texas belt of areas 21, 22, 30 sits at 18–22.
- This is the expected sweet-spot-in-the-middle pattern. The three responses agree, as the three-panel
  figure shows.
- At k = 6 the picture is the same:
  - core: 32.7 bbl/ft, n 993
  - big middle: 23.4, n 3,629
  - southern TX: 18.8, n 1,844
  - W, S and N flanks: 12.9–16.0

## 6. Flags for gate 4 (not resolved)

**a. k = 34 vs a coarser nested level.**
- The rule picks 34 areas: median 69 cohort wells, quartiles 33 / 201, min 15.
- Six of them are pad-scale (< 25 sq mi) and five are dominated by one operator (≥ 70 % of wells),
  mostly 2022–24 vintage. These look like operator / program clusters, the confounding D9 accepts but
  which makes poor TC areas.
- k = 14 gives up 0.02 of held-out R² and leaves one pad-scale area (area 11, Crescent, 16 sq mi, 18 wells).
- The options are: accept 34; pick a nested level such as 14; or re-run with a minimum-area floor (a new
  knob, so your call).
- Step 5 impact: a quarter of the 34 areas have ≤ 33 wells and will lean on the relaxation ladder (D10).

**b. Area 12 is a data artifact candidate, not geology.**
- It is 2.6 sq mi, 18 wells, one Permian Resources program (El Campeon / Los Vaqueros) at −103.40, 32.01,
  and it persists at every level down to k = 10.
- It straddles the state line at one TVD (12,640–12,810 ft):
  - the 8 Lea Co. NM wells run 10.5–25.5 bbl/ft, median ~16
  - the 10 Loving Co. TX twins run 3.4–9.6, median ~5.8
- Same operator, same program, same bench, a ~3× step at the border. This smells like TX lease
  allocation or reporting, not rock.
- Step 1 found no basin-wide border step; this one is local. Candidate for the next Novi vintage query,
  alongside Diez and McGary (§9).

**c. WCXY inside the pool (D20).**
- 1,066 of the 7,553 12-mo cohort wells are WCXY-tagged (1,963 in the whole well set). They count as
  WCA evidence and are concentrated in the core and middle (area 9: 409; area 8: 119; area 21: 117;
  area 6: 95).
- Dropping them moves an area P50 by at most 1.75 bbl/ft (area 17, 6 WCXY wells; 7.1 → 5.3), in every
  area with ≥ 10 non-WCXY wells (column `oil12_p50_exWCXY`), so WCXY does not shape the areas.
- WCXY PUD membership stays a step-7 call. The page counts 3,211 WCXY D1 PUDs inside, against 1,934
  WCA_1 + WCA_2.

**d. Vintage and operator confounding is visible.**
- The median first-prod year runs from 2018 to 2024 across areas, and the newest areas (2023–24) are
  among the low ones (areas 1, 2, 12).
- D9 accepts this for v1. The step-6 hindcast is where it will show if it matters.

## 7. Verification (§7)

**Rendered surface:**
- `areas_WCA.html` opens via the local server.
- All 6 levels × 3 responses draw with no JS errors (checked in the browser pane).
- n per area and the filters are stated on the page and in every table.

**Identities:**
- The 12-mo cohort n, 7,553, equals the gate-1 cohort (7,562) minus the 9 wells with their midpoint
  outside the extent.
- Area n12 sums to 7,553.
- Areas tile the extent: 6,168.7 sq mi planar, the same as box.extent id 6.
- In the container store test: zero overlap, and geodesic area sum = extent within 0.1 %.

**Warehouse, `sql/57`:**
- Applied **twice** (idempotent) to a throwaway `postgis/postgis:16-3.4` container carrying sql/54 + sql/56.
- `apply_box_tc_area` checks: 15 / 15, including the D9 CHECK (n_wells ≥ 10), the is_record partial
  unique index, and EXPLAIN showing `box_tc_area_geom_gix` and `box_tc_area_geog_gix`.
- `store_areas` dry run into the container: 34 rows, identity check passed, and the record handover
  from v1 to v2 is correct.
- **Not applied to Supabase.**

**Tests:** `pytest -q` passes 325, skips 35. Ruff is clean on every touched file (mypy is not installed
in this venv).

**Deferred to the apply (needs go-apply):**
- `python -m scripts.apply_box_tc_area`
- then `python -m scripts.box_tc_areas --store --record` (the write; its own go-ahead)
- then regenerate the data dictionary (`python -m scripts.gen_data_dictionary --html docs/data_dictionary.html`)

The k level you choose at gate 4 is what gets stored.
