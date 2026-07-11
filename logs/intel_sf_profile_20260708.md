# Novi INTEL share profiling - 2026-07-08

## 1. Session context

- account: `WK94842`  role: `DATA_READER`  warehouse: `NOVI_WH`
- database: `NOVI_DATA_ACCESS`  schema: `NOVI_INTEL`

## 2. Visible collections

- 12 visible collection(s):
  - `basin_research__Anadarko_Basin__2026Q1`
  - `basin_research__DJ_Basin__2025Q2`
  - `basin_research__Delaware_Basin__2025Q3`
  - `basin_research__Eagle_Ford_Basin__2026Q2`
  - `basin_research__Haynesville_Basin__2025Q4`
  - `basin_research__Marcellus_Basin__2026Q1`
  - `basin_research__Midland_Basin__2025Q3`
  - `basin_research__Powder_River_Basin__2025Q4`
  - `basin_research__Uinta_Basin__2026Q2`
  - `basin_research__Utica_Basin__2026Q1`
  - `basin_research__Williston_Basin__2025Q4`
  - `basins`
- **3Q25-matching vintage visible: YES - exact reconciliation possible**

## 3. Row counts (all 22 views)

| view | rows |
|---|---|
| ARPS_FORECAST | 1834974 |
| BASIN | 24 |
| ECON_PRICE_ASSUMPTION | 2 |
| INVENTORY_FORECAST | 73195074 |
| ML_SCORE | 178337 |
| OPERATOR | 40535 |
| PAD | 4585 |
| PLANNED_WELL | 203886 |
| PRODUCTION_ARPS_SEGMENT_PARAMETER | 1834974 |
| PRODUCTION_FORECAST | 73195074 |
| SOURCE | 54 |
| SURFACE_LOCATION | 251902 |
| WELL | 48016 |
| WELLBORE | 251902 |
| WELLBORE_TRAJECTORY | 251902 |
| WELL_COMPLETION | 203886 |
| WELL_COST_SUMMARY | 251902 |
| WELL_ECONOMICS | 251902 |
| WELL_ECONOMICS_SUMMARY | 251902 |
| WELL_MASTER | 251902 |
| WELL_ML_SCORE | 174265 |
| WELL_ROCK_QUALITY | 178337 |

Static-drop reference (both basins, 3Q25): sticks ~248,000, pud_attrs ~131,000, analytics ~23,000, arps ~200,000, forecast ~74,000,000

WELL_MASTER by report / inventory class:
| report_name | inventory_class | rows |
|---|---|---|
| basin_research__Delaware_Basin__2025Q3 | BASE_CASE | 83282 |
| basin_research__Delaware_Basin__2025Q3 | EMERGING | 44674 |
| basin_research__Delaware_Basin__2025Q3 | PDP | 24581 |
| basin_research__Midland_Basin__2025Q3 | BASE_CASE | 48183 |
| basin_research__Midland_Basin__2025Q3 | EMERGING | 27747 |
| basin_research__Midland_Basin__2025Q3 | PDP | 23435 |

## 4. PRODUCTION_FORECAST grain

PRODUCTION_FORECAST by granularity / scenario:
| granularity | scenario | rows | wells | rows/well |
|---|---|---|---|---|
| monthly | P50 | 73195074 | 203886 | 359.0 |

FORECAST_DAY step distribution (100-well sample):
| day step | occurrences |
|---|---|
| 30 | 35800 |
- **verdict: 30-day steps (matches old ip_day semantics)**

INVENTORY_FORECAST by granularity / scenario:
| granularity | scenario | rows | wells |
|---|---|---|---|
| monthly | P50 | 73195074 | 203886 |

## 5. UWI_API length

| length(UWI_API) | wells |
|---|---|
| 10 | 48016 |
- **all api10: no truncation needed in the crosswalk join**

## 6. ARPS_FORECAST coverage

| inventory_class | stream | segments | wells | seg/well |
|---|---|---|---|---|
| BASE_CASE | gas | 394395 | 131465 | 3.00 |
| BASE_CASE | oil | 394395 | 131465 | 3.00 |
| BASE_CASE | water | 394395 | 131465 | 3.00 |
| EMERGING | gas | 217263 | 72421 | 3.00 |
| EMERGING | oil | 217263 | 72421 | 3.00 |
| EMERGING | water | 217263 | 72421 | 3.00 |

Old raw_novi_intel.arps for comparison:
| stream | segments | wells |
|---|---|---|
| gas | 617253 | 205751 |
| oil | 617253 | 205751 |
| water | 617253 | 205751 |

## 7. Formation crosswalk coverage

- 41 distinct formation strings in the share; 37 covered by ref.formation_crosswalk
- **4 NOT in the crosswalk** (sql/19 tier-3 gaps; spatial inference or crosswalk additions needed):
  - `AVALON`
  - `BONE SPRING LIME`
  - `FIRST BONE SPRING LIME`
  - `WOLFCAMP A (XY)`

## 8. Key semantics (unique_id, EUR horizon, IRR, PV, decks, PAD)

- PLANNED_WELL.NAME sample: 50/50 match old sticks.unique_id (category=PUD)

- WELL_ECONOMICS_SUMMARY: 48 columns: WELL_ECONOMICS_SUMMARY_ID, WELL_ID, PLANNED_WELL_ID, NPV5, NPV10, NPV15, NPV20, NPV25, PV5, PV10, PV15, PV20, PV25, NPV, IRR, PVI, PAYBACK_MONTHS, DOUBLE_PAYBACK_MONTHS, BREAKEVEN_1YR, BREAKEVEN_2YR, BREAKEVEN_3YR, NPV5_BREAKEVEN, NPV10_BREAKEVEN, NPV15_BREAKEVEN, NPV20_BREAKEVEN, NPV25_BREAKEVEN, LIFETIME_MONTHS, EUR_OIL_30YR, EUR_GAS_30YR, EUR_NGL_30YR, EUR_DRY_GAS_30YR, EUR_WATER_30YR, IP_OIL, IP_NGL, IP_GAS, IP_DRY_GAS, IP_WATER, NGL_YIELD, NGL_SHRINK, STREAM, CURRENCY, PRICE_DECK_ID, SOURCE_ID, CREATED_AT, UPDATED_AT, BASIN, SUBBASIN, REPORT_NAME
- PV columns present: ['PV5', 'PV10', 'PV15', 'PV20', 'PV25', 'PVI']
- EUR oil columns present: ['EUR_OIL_30YR']

EUR horizon check (431 PDP wells joined on api10; median old_oil_eur / new_<col> - the column with ratio ~1.0 wins):
| column | n | median ratio old/new |
|---|---|---|
| EUR_OIL_30YR | 431 | 1.0 |

- IRR: median|irr|=0.11809371411800385, range [-0.269582599401474, 9.994486808776855], n=251890 - **FRACTION (multiply by 100 for irr_pct)**; the sql/12 slice_irr self-calibration dies either way

Price decks (old static drop assumed flat $75 WTI / $3 HH):
| deck_id | name | oil | gas | ngl | oil diff | gas diff |
|---|---|---|---|---|---|---|
| 4669854180624696488 | PRICE_DECK_WTI75_HH3_NGL20_DWTI5_DHH1.5 | 75.0 | 3.0 | 20.0 | 5.0 | 1.5 |
| 2691834811107553808 | PRICE_DECK_WTI75_HH3_NGL26_DWTI4_DHH1 | 75.0 | 3.0 | 26.0 | 4.0 | 1.0 |
- PAD: 4585 rows, latitude populated on 0, longitude on 0 (expected 0 - frozen legacy polygons stay)

## 9. Trajectory geometry sanity

- sample of 20 PDP trajectories; CRS values: ['EPSG:4326']
- WKT geometry types: ['LINESTRING']

Hausdorff distance vs old sticks geom (approx meters, ~111km/deg):
| api10 | hausdorff_m |
|---|---|
| 4238938766 | 0.0 |
| 4238940040 | 0.0 |
| 4247536156 | 0.0 |
| 4247536257 | 0.0 |
| 4247536539 | 0.0 |
| 4249534024 | 0.0 |
| 4249534550 | 0.0 |
| 4249534962 | 0.0 |
| 3001536321 | 0.0 |
| 3001541024 | 0.0 |
| 3001541061 | 0.0 |
| 4230134723 | 0.0 |
| 4230134762 | 0.0 |
| 4230135276 | 0.0 |
| 4230135510 | 0.0 |
| 4230135743 | 0.0 |
| 4230135744 | 0.0 |
| 4230135750 | 0.0 |
