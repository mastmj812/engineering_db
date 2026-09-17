# Novi INTEL share profiling - 2026-09-16

## 1. Session context

- account: `WK94842`  role: `DATA_READER`  warehouse: `NOVI_WH`
- database: `NOVI_DATA_ACCESS`  schema: `NOVI_INTEL`

## 2. Visible collections

- 12 visible collection(s):
  - `basin_research__Anadarko_Basin__2026Q1`
  - `basin_research__DJ_Basin__2026Q3`
  - `basin_research__Delaware_Basin__2026Q3`
  - `basin_research__Eagle_Ford_Basin__2026Q2`
  - `basin_research__Haynesville_Basin__2025Q4`
  - `basin_research__Marcellus_Basin__2026Q1`
  - `basin_research__Midland_Basin__2026Q3`
  - `basin_research__Powder_River_Basin__2025Q4`
  - `basin_research__Uinta_Basin__2026Q2`
  - `basin_research__Utica_Basin__2026Q1`
  - `basin_research__Williston_Basin__2025Q4`
  - `basins`
- **3Q25-matching vintage visible: NO - phase-5 reconciliation will be drift analysis vs a newer vintage**

## 3. Row counts (all 22 views)

| view | rows |
|---|---|
| ARPS_FORECAST | 2333088 |
| BASIN | 26 |
| ECON_PRICE_ASSUMPTION | 2 |
| INVENTORY_FORECAST | 93064288 |
| ML_SCORE | 238940 |
| OPERATOR | 40736 |
| PAD | 5852 |
| PLANNED_WELL | 259232 |
| PRODUCTION_ARPS_SEGMENT_PARAMETER | 2333088 |
| PRODUCTION_FORECAST | 93064288 |
| SOURCE | 55 |
| SURFACE_LOCATION | 324360 |
| WELL | 65151 |
| WELLBORE | 324383 |
| WELLBORE_TRAJECTORY | 324360 |
| WELL_COMPLETION | 259232 |
| WELL_COST_SUMMARY | 324383 |
| WELL_ECONOMICS | 324383 |
| WELL_ECONOMICS_SUMMARY | 324383 |
| WELL_MASTER | 324383 |
| WELL_ML_SCORE | 234020 |
| WELL_ROCK_QUALITY | 238940 |

Retired static-drop reference (both basins, 3Q25; historical yardstick): sticks ~248,000, pud_attrs ~131,000, analytics ~23,000, arps ~200,000, forecast ~74,000,000

WELL_MASTER by report / inventory class:
| report_name | inventory_class | rows |
|---|---|---|
| basin_research__Delaware_Basin__2026Q3 | BASE_CASE | 122418 |
| basin_research__Delaware_Basin__2026Q3 | EMERGING | 49632 |
| basin_research__Delaware_Basin__2026Q3 | PDP | 34244 |
| basin_research__Midland_Basin__2026Q3 | BASE_CASE | 62082 |
| basin_research__Midland_Basin__2026Q3 | EMERGING | 25100 |
| basin_research__Midland_Basin__2026Q3 | PDP | 30907 |

## 4. PRODUCTION_FORECAST grain

PRODUCTION_FORECAST by granularity / scenario:
| granularity | scenario | rows | wells | rows/well |
|---|---|---|---|---|
| monthly | P50 | 93064288 | 259232 | 359.0 |

FORECAST_DAY step distribution (100-well sample):
| day step | occurrences |
|---|---|
| 30 | 35800 |
- **verdict: 30-day steps (matches old ip_day semantics)**

INVENTORY_FORECAST by granularity / scenario:
| granularity | scenario | rows | wells |
|---|---|---|---|
| monthly | P50 | 93064288 | 259232 |

## 5. UWI_API length

| length(UWI_API) | wells |
|---|---|
| 10 | 65151 |
- **all api10: no truncation needed in the crosswalk join**

## 6. ARPS_FORECAST coverage

| inventory_class | stream | segments | wells | seg/well |
|---|---|---|---|---|
| BASE_CASE | gas | 553500 | 184500 | 3.00 |
| BASE_CASE | oil | 553500 | 184500 | 3.00 |
| BASE_CASE | water | 553500 | 184500 | 3.00 |
| EMERGING | gas | 224196 | 74732 | 3.00 |
| EMERGING | oil | 224196 | 74732 | 3.00 |
| EMERGING | water | 224196 | 74732 | 3.00 |

## 7. Formation crosswalk coverage

- 85 distinct formation strings in the share; 77 covered by ref.formation_crosswalk
- **8 NOT in the crosswalk** (sql/19 tier-3 gaps; spatial inference or crosswalk additions needed):
  - `BONE SPRING LIME`
  - `CAPITAN`
  - `CAPITAN REEF`
  - `FIRST BONE SPRING LIME`
  - `HOLT`
  - `PURPLE SAGE WOLFCAMP`
  - `WICHITA`
  - `WOLFCAMP A XY`

## 8. Key semantics (EUR/PV columns, IRR units, decks, PAD)


- WELL_ECONOMICS_SUMMARY: 48 columns: WELL_ECONOMICS_SUMMARY_ID, WELL_ID, PLANNED_WELL_ID, NPV5, NPV10, NPV15, NPV20, NPV25, PV5, PV10, PV15, PV20, PV25, NPV, IRR, PVI, PAYBACK_MONTHS, DOUBLE_PAYBACK_MONTHS, BREAKEVEN_1YR, BREAKEVEN_2YR, BREAKEVEN_3YR, NPV5_BREAKEVEN, NPV10_BREAKEVEN, NPV15_BREAKEVEN, NPV20_BREAKEVEN, NPV25_BREAKEVEN, LIFETIME_MONTHS, EUR_OIL_30YR, EUR_GAS_30YR, EUR_NGL_30YR, EUR_DRY_GAS_30YR, EUR_WATER_30YR, IP_OIL, IP_NGL, IP_GAS, IP_DRY_GAS, IP_WATER, NGL_YIELD, NGL_SHRINK, STREAM, CURRENCY, PRICE_DECK_ID, SOURCE_ID, CREATED_AT, UPDATED_AT, BASIN, SUBBASIN, REPORT_NAME
- PV columns present: ['PV5', 'PV10', 'PV15', 'PV20', 'PV25', 'PVI']
- EUR oil columns present: ['EUR_OIL_30YR'] (sql/29 maps EUR_*_30YR — the only horizon shipped as of 2025Q3; a new/vanished horizon here means sql/29 needs a look)

- IRR: median|irr|=0.7203278243541718, range [-1.0, 1141559626039296.0], n=311930 - **FRACTION (multiply by 100 for irr_pct)** (global median; sql/29 calibrates per slice)

Price decks (old static drop assumed flat $75 WTI / $3 HH):
| deck_id | name | oil | gas | ngl | oil diff | gas diff |
|---|---|---|---|---|---|---|
| 738596916758416233 | PRICE_DECK_WTI75_HH3.5_NGLnull_DWTI4_DHH1 | 75.0 | 3.5 |  | 4.0 | 1.0 |
| 4742798813274665401 | PRICE_DECK_WTI75_HH3.5_NGLnull_DWTI5_DHH1.5 | 75.0 | 3.5 |  | 5.0 | 1.5 |
- PAD: 5852 rows, latitude populated on 0, longitude on 0 (expected 0 - frozen legacy polygons stay)

## 9. Trajectory geometry sanity

- sample of 20 PDP trajectories; CRS values: ['EPSG:4326']
- WKT geometry types: ['LINESTRING'] (expect LINESTRING, EPSG:4326 — anything else breaks the sql/27 WKT->geom hook)
