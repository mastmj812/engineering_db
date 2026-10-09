# BOX step 4 — TC areas on WCA (gate 4 summary)

Built 2026-10-09 on branch `claude/box-step4-tc-areas`. Rebuilt the same day after Michael excluded
the El Campeon / Los Vaqueros wells (§6b).

Read-only against the warehouse; **nothing stored**. `sql/57` (box.tc_area) is authored and
container-validated, **not applied**. It needs Michael's "go apply", and the `--store --record` write
needs its own go-ahead.

**Review surface:** `areas_WCA.html`. Serve with `python -m http.server 8766 --directory docs/box`
(or the `box-static` launch config), then open `/step4-2026-10-09/areas_WCA.html`.

## 1. What exists

| File | What |
|---|---|
| `areas_WCA.html` | Interactive area map with a response toggle (12-mo / 24-mo / Novi 30-yr EUR per ft) and a nested-level toggle (k = 6, 10, 14, 20, **35 = pick**, 38 = CV minimum). Click an area for its card. Also on the page: the 3-panel gut-check figure, the CV curve, the sensitivity table, and the per-area table. |
| `areas_WCA.csv` | One row per area at the pick: n12 / n24 / n_eur, P50 and P10 (high) / P90 (low) in bbl/ft, member tags, median first-prod year, top operator, D1 PUD counts, review flags. |
| `areas_levels_WCA.csv` | The same table for every level shown on the map. |
| `areas_WCA_v1.geojson` | Area polygons at the pick (EPSG:4326) with the per-area stats. |
| `cv_WCA.csv`, `sensitivity_WCA.csv` | The CV curve (k = 1..60) and the knob sensitivity. |
| `wells_area_WCA.csv` | Every cohort well → area_no, with its responses and cohort flags. |
| `summary.json` | Run stamp, identities, the excluded api10s, pick, R² values. |
| `../exclusions.csv` | **BOX well exclusions of record** (api10, pool, reason, decided_by, decided_on), applied at load by `box/exclusions.py`. |

Code: `box/tc_area.py` (pure method), `box/tc_area_report.py` (inputs, stats, page),
`box/tc_area_store.py` (the `--store` write), `box/exclusions.py`, `scripts/box_tc_areas.py` (CLI,
~80 s), `sql/57_box_tc_area.sql` + `scripts/apply_box_tc_area.py`, and `tests/test_box_tc_area.py`
(12 DB-free tests).

## 2. Inputs and cohorts (D9)

- **Extent of record:** `box.extent` id 6 (WCA v1 generated, 6,168.7 sq mi).
- **Well set:** gate-1 `wells_final_WCA.csv` (WCA_1 + WCA_2 pooled, WCXY as one-way evidence,
  D19/D20), **minus `exclusions.csv`**: 27 WCA wells, 26 of them in the cohort.
- **Data:** through 2026-08-01.

| Response | Cohort | n |
|---|---|---|
| **12-mo oil / ft** (the areas are built on this) | the gate-1 `cohort` flag (fp ≥ 2016-01-01, lateral 6,000–13,000 ft, 12 full months, cum-12 > 0), midpoint inside the extent | **7,527** (9 of 7,536 fall outside the extent) |
| 24-mo oil / ft | same filter, 24 full months, cum-24 > 0 | 6,816 |
| bo / ft | same vintage and lateral filter; Novi 30-yr oil EUR ÷ lateral (life cum where Novi has none, 0 such wells) | 8,156 |

Grain is wells. Responses are Novi WellDetails cum pass-throughs, calendar months from first
production. Vintage is normalized **by filter only**, and operator / completion confounding is **not
removed** (D9, stated on the page). The Novi 30-yr EUR is a vendor forecast horizon, not the 50-yr
technical EUR, and is used here as a screen for the gut check only. Percentiles follow SPE: P10 = HIGH.
Pool P50 of 12-mo oil is 21.8 bbl/ft (21,800 bbl/1,000 ft).

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

## 4. How many areas, and why: **35**

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
| k = 6 | 0.18 |
| k = 14 | 0.20 |
| **k = 35 (pick)** | **0.21** |
| k = 38 (CV minimum) | 0.21 |
| a local 15-well median, no areas at all (the ceiling) | 0.22 |

In-sample, the 35 areas explain 41 % of the well-to-well variance. Across areas, the rank agreement of
the area P50s is 0.98 between 12-mo and 24-mo, and 0.89 between 12-mo and Novi 30-yr EUR/ft. A
regionalization run on the 24-mo response alone picks k = 18 at R² 0.21.

**The exact k is weakly identified.** Across cell size {1, 1.5 mi} × field kNN {10, 15, 25}, the pick
ranges from 10 to 35, while held-out R² at the pick stays between 0.19 and 0.21. The curve is flat past
about 14 areas. The areas capture nearly all the spatial signal a well-by-well local estimate gets
(0.21 vs 0.22). The remaining ~78 % of variance is well-to-well (completion, spacing, operator), which
no map resolves.

How much these R² numbers move between runs: changing which wells enter the CV reshuffles the 3-mi
blocks across folds, so the same partition can score about ±0.03 differently. Compare R² within one
table, not across runs.

## 5. Gut check: what the map shows

- **The sweet spot is north-central, along and just north of the state line.** Southern Eddy and Lea
  around 32.0–32.25° N, −103.6 to −103.9:
  - area 12, EOG: 39.0 bbl/ft, n 152
  - area 5, Devon: 37.7, n 205
  - area 7, Mewbourne: 31.2, n 113
  - area 9, EOG: 29.6, n 636
  - area 10, Occidental: 25.8, n 1,810
- **Performance falls off toward every edge:**
  - W (Reeves / Culberson flank): areas 4, 11, 17, 18 at 7–14 bbl/ft
  - N (32.5° N+): areas 1, 2, 3 at 13–15
  - far S and E (Ward / Pecos / Reeves S): areas 28, 29, 32–34 at 9–13
  - The middle-Texas belt of areas 22, 24, 31 sits at 18–22.
- This is the expected sweet-spot-in-the-middle pattern. The three responses agree, as the
  three-panel figure shows.
- At k = 6 the picture is the same:
  - core: 32.7 bbl/ft, n 993
  - two big middle areas: 25.0 and 19.9 (n 2,270 / 747)
  - southern TX: 19.1, n 2,666
  - W and S flanks: 12.9–13.7

## 6. Flags for gate 4

**Gate 4 CLOSED 2026-10-09:** keep 35 areas; El Campeon / Los Vaqueros excluded; gas via GOR; gas in
the acceptance test. `sql/57` applied live (15/15) on Michael's go-apply; the 35 areas are stored as
`box.tc_area` v1 on extent_id 6, `is_record` (a read-only rebuild immediately before the store matched
this deliverable exactly; live check: 35 rows, n_wells 7,527, areas/extent geodesic ratio 0.99999997,
no overlap, per-area n and P50 equal to `areas_WCA_v1.geojson`). Data dictionary regenerated.

**a. k = 35 vs a coarser nested level.** *DECIDED 2026-10-09 (Michael): keep 35 (plan D29).*
- The rule picks 35 areas: median 79 cohort wells, quartiles 35 / 197, min 15.
- Five of them are pad-scale (< 25 sq mi) and four are dominated by one operator (≥ 70 % of wells),
  mostly 2019–23 vintage. These look like operator / program clusters, the confounding D9 accepts but
  which makes poor TC areas.
- k = 14 gives up 0.02 of held-out R² and leaves one pad-scale area (Crescent, 16 sq mi, 18 wells).
- The options are: accept 35; pick a nested level such as 14; or re-run with a minimum-area floor (a new
  knob, so your call).
- Step 5 impact: a quarter of the 35 areas have ≤ 35 wells and will lean on the relaxation ladder (D10).

**b. El Campeon / Los Vaqueros: EXCLUDED (Michael 2026-10-09).** *Decided.*
- One Permian Resources state-line program at −103.38 to −103.41, 32.00–32.01.
- Each lateral is booked twice, once per state, under two api10s. For example, EL CAMPEON FEDERAL COM
  #432H (3002547394, NM) and EL CAMPEON UNIT 2 432H (4230136057, TX) are the same lateral.
- Production is split between the two records:
  - in the first build, the TX twins ran about 3× low on oil (median ~5.8 vs ~16–18 bbl/ft in NM)
  - **with the same GOR on both sides** (TX 1,538 vs NM 1,409 scf/bbl)
  - so it is a volume split, not a misreported stream.
- Michael has raised the allocation defect with Novi.
- All 46 of the program's wells in the BOX well sets (27 WCA, 19 BS2_S, most BS2_S still pre-cohort)
  are in `docs/box/exclusions.csv`, applied at load for every later step.
- The gate-1 well sets stay frozen as the gate-1 record.
- Extents are **not** regenerated: these wells are deep inside the developed interior, which D27
  fills, so they never set an edge.
- Effect: the 18-well pad-scale area (old area 12) is gone. Its ground is now inside area 24
  (Diamondback-led, 18.2 bbl/ft, n 735).
- The pick moved 34 → 35: the merge order shifted and two areas split out elsewhere (area 8, Matador,
  NE Lea; area 13, ConocoPhillips). Area numbers from 8 onward differ from the first build.

**c. WCXY inside the pool (D20).** *No change needed.*
- 1,066 of the 7,527 12-mo cohort wells are WCXY-tagged (1,963 in the whole well set). They count as
  WCA evidence and are concentrated in the core and middle (area 10: 409; area 9: 119; area 22: 117;
  area 6: 95).
- Dropping them moves an area P50 by at most 1.75 bbl/ft (area 18, 6 WCXY wells; 7.1 → 5.3), in every
  area with ≥ 10 non-WCXY wells (column `oil12_p50_exWCXY`), so WCXY does not shape the areas.
- WCXY PUD membership stays a step-7 call. The page counts 3,211 WCXY D1 PUDs inside, against 1,934
  WCA_1 + WCA_2.

**d. Vintage and operator confounding is visible.** *Accepted for v1 (D9).*
- The median first-prod year runs from 2018 to 2023 across areas, and the newest areas (2022–23) are
  among the low ones (areas 1, 2, 4).
- The step-6 hindcast is where it will show if it matters.

**e. The areas do not follow GOR; GOR needs its own handling for the gas stream.** *DECIDED 2026-10-09
(Michael): recommendation adopted — gas via GOR ratio mode at a local GOR level (plan D30), gas added
to §8 acceptance (plan D31).*

Asked at the gate (Michael 2026-10-09): do the TC areas align with GOR trends, should they, and
should GOR inform them?

- **GOR is a regional east-to-west fluid-maturity trend.** 12-mo GOR = Novi cum-12 gas ÷ cum-12 oil,
  7,524 cohort wells. Pool P90 (low) / P50 / P10 (high) = 1,266 / 2,669 / 5,996 scf/bbl.

  | Counties | Median GOR (scf/bbl) |
  |---|---|
  | Pecos / Winkler / Ward | 1,200–1,600 |
  | Lea / Loving | 2,000–2,200 |
  | Eddy / Reeves | ~3,400 |
  | Culberson and W Reeves | 5,800–10,000 |

- The gassy west is the *shallow* side (Culberson median TVD 8,994 ft vs Lea 12,390 ft). Across areas,
  GOR falls as TVD rises (Spearman −0.54), so this is maturity, not burial depth.
- **The oil sweet spot runs across that trend.** Correlation between log oil/ft and log GOR is −0.16
  per well. Rank correlation between area P50s for oil and GOR is −0.14 at k = 35.
- **GOR is far more predictable from location than oil is.** A 15-nearest-well median predicts 77 % of
  held-out log-GOR variance, against 22 % for log oil/ft. GOR is a map property; oil/ft is mostly a
  well property.
- **Built on oil vs built on GOR**, scored on held-out wells (R² of the log):

  | Areas built on | k | Oil R² | GOR R² |
  |---|---|---|---|
  | oil | 14 | 0.22 | 0.35 |
  | oil (the pick) | 35 | 0.24 | 0.46 |
  | GOR | 6 | 0.12 | 0.67 |
  | GOR | 35 | 0.20 | 0.74 |

  The oil areas capture about half of the GOR signal. GOR-built areas cost oil skill. This table uses
  a different fold draw from §4 (±0.03); compare within it.
- **Inside the oil areas, GOR is mixed.** At k = 35, the median area's GOR P10/P90 ratio is 2.5×,
  against 4.7× for the pool. In 16 of the 35 areas, fewer than 60 % of wells fall in the area's most
  common GOR band (< 1.5k / 1.5–2.5k / 2.5–4k / > 4k scf/bbl).
- **Vintage effect on GOR is modest.** Median 12-mo GOR drifts from 2,184 (2018) to 3,122 (2024),
  about +40 %, against 4.7× across the map.

**Why it matters.**
- Step 5 as written fits a gas curve per area. In a mixed area that curve is an average of a 1,500 and
  a 6,000 scf/bbl population, so a PUD's gas forecast could be off by up to ~2× either way while its
  oil is right. That flows into Steven's gas and NGL revenue.
- §8 acceptance scores oil only (cum-6 / cum-12), so a gas miss would pass silently.

**Recommendation (Michael's call; it changes step 5 and §8, not step 4):**
1. Keep the oil-built areas. GOR should not move the oil boundaries: the trends cross each other, and
   forcing GOR in costs oil skill.
2. Forecast gas as **GOR versus cumulative oil**, using the PUD's local GOR level. This ratio method is
   already a decision of record for anduin (2026-08-17), at both well and type-curve level. Each area
   supplies the *shape* of the GOR-vs-cum-oil trend. The level comes from the PUD's neighbourhood: a
   local median, or a separate GOR area set, since 6 GOR areas already reach R² 0.67.
3. At step 5, test whether the oil decline shape (b, nominal Di) shifts with GOR within an area. If it
   does, that is the case for splitting on GOR.
4. Add gas cum-6 / cum-12 to the §8 hindcast, at least as a reported metric.

## 7. Verification (§7)

**Rendered surface:**
- `areas_WCA.html` opens via the local server.
- All 6 levels × 3 responses draw with no JS errors (re-checked in the browser pane after the exclusion rebuild).
- n per area and the filters are stated on the page and in every table.

**Identities:**
- The 12-mo cohort n, 7,527, equals the gate-1 cohort (7,562), minus the 26 excluded cohort wells,
  minus the 9 wells with their midpoint outside the extent.
- Area n12 sums to 7,527.
- Areas tile the extent: 6,168.7 sq mi planar, the same as box.extent id 6.
- In the container store test of the first build: zero overlap, and geodesic area sum = extent within 0.1 %.

**Warehouse, `sql/57`:**
- Applied **twice** (idempotent) to a throwaway `postgis/postgis:16-3.4` container carrying sql/54 + sql/56.
- `apply_box_tc_area` checks: 15 / 15, including the D9 CHECK (n_wells ≥ 10), the is_record partial
  unique index, and EXPLAIN showing `box_tc_area_geom_gix` and `box_tc_area_geog_gix`.
- `store_areas` dry run into the container: rows = areas, identity check passed, and the record
  handover from v1 to v2 is correct.
- **Applied to Supabase 2026-10-09** (15/15 live) and the areas stored as the version of record (gate-4 block above).

**Tests:** `pytest -q` passes 326, skips 35, including 12 new box tests. Ruff is clean on every touched
file (mypy is not installed in this venv).

**Deferred to the apply (needs go-apply):**
- `python -m scripts.apply_box_tc_area`
- then `python -m scripts.box_tc_areas --store --record` (the write; its own go-ahead)
- then regenerate the data dictionary (`python -m scripts.gen_data_dictionary --html docs/data_dictionary.html`)

The k level you choose at gate 4 is what gets stored.
