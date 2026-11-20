# Novi v4 (Snowflake `NOVI_WELLS`) vs v3 bulk TSV: parity study

Date: 2026-11-19. Read-only study. No ETL code changed, nothing applied to the warehouse,
nothing written to Snowflake.

- **v3 side:** `raw_novi.*` as loaded by the nightly of 2026-11-19 11:02 UTC (scope us-horizontals,
  95,985 wells).
- **v4 side:** `NOVI_DATA_ACCESS.NOVI_WELLS` (41 secure views), read through
  `etl/intel_sf/client.get_sf_connection`, role DATA_READER, warehouse NOVI_WH. Share run
  `20261119_100441` (10:04 UTC the same day). Our entitlement is Permian only.

## 1. Recommendation

**Stay on v3 for the nightly, and dual-run v4 in shadow (read-only compare) until Novi answers
the questions in section 8. Do not migrate yet.**

The numbers behind it:

| Check | Result |
|---|---|
| Wells | All 95,985 v3 wells are in v4. v4 has 96,751 horizontal + U-turn wellbores; the 766 extra come from Novi's US_Onshore set. |
| Header columns (all 95,985 wells) | Names, formation, lateral length, TVD, MD, dates, EURs, completion: 100 % equal wherever both sides have a value. |
| Spacing (63,650 wells) | All 10 columns equal. `LATERAL_CLOSER_XY` = 2800.0 on the same 8,385 wells on both sides. |
| Surveys (68,972 wells) | 15,954,057 stations on both sides; station count equal on 100 % of wells. |
| Monthly production (2,551-well sample, 204,127 common well-months) | Oil, gas, water and producing days all equal on 99.51 % of well-months. The misses sit in 15 wells. |
| Forecast rates (2,227-well sample, 656,762 common rows) | Oil 99.90 %, gas 99.94 %, water 99.89 % within 0.1 %. The misses sit in 3 wells. |

So v4 is the same data. Two things stop a migration today:

1. **v4 has no per-day rate columns.** `PRODUCTION_MONTHLY` carries volumes and days only. The
   rates of record (`rate_calday_*`) would stop being "exactly as Novi computed them" and become
   something we compute. They reproduce exactly (section 4.3), but this changes a convention of
   record (domain rule 4), so it is Michael's decision.
2. **We have one snapshot of v4.** Novi released it on 2026-10-29 (user guide, section 11); the
   first draft of this study wrongly said it was released on 2026-11-19, the day we first read
   it. We have still not watched it night over night ourselves.

A third blocker in the first draft of this study, 2,211 wells with a v3 forecast and no v4
forecast, turned out to be stale rows on our side (section 10).

**Update, later on 2026-11-19:** Novi's user guide for the schema answers most of the questions
in section 8 and none of the answers contradicts the parity numbers. Section 11 lists what it
settles and what is still open.

**Side finding, independent of v4. Fixed the same day (section 10):** `raw_novi` held stale rows
that the nightly upsert never deletes. The log showed no full load or reconcile of `WellMonths` or
`ForecastWellMonths` since 2026-06-23. The numbers below and in section 4 are as measured before
the fix.

- `ForecastWellMonths`: on 44,087 of 57,771 wells (76 %) our series runs past the end of Novi's
  current forecast. That is 4,016,644 leftover rows from older forecast vintages (19 % of our
  forecast rows on those wells). They flow into `curated.production_forecast`. Header EURs are
  not affected.
- `WellMonths`: 207 wells (39,450 rows) no longer have a `Wells` row, and life-of-well volumes
  differ from v4 on 2,008 of 66,017 wells (3.0 %); total oil is 0.59 % higher on our side.

The fix is the documented one: `python -m etl.novi.load --reconcile`, then
`python -m etl.refresh --force`. Michael gave the go on 2026-11-19 and it was run that day;
section 10 has the result. The nightly still cannot delete rows from `WellMonths` or
`ForecastWellMonths`, so the stale rows will build up again until the loader handles deletions
or the reconcile is scheduled.

## 2. Method

- Columns in use: the live column-level dependencies of curated objects on the six `raw_novi`
  tables (`pg_depend`), cross-checked against `sql/04`, `sql/05`, `sql/10`, `sql/49`, `sql/64`.
- Header, spacing, survey counts, per-well production totals and per-well forecast ranges: full
  population, joined on api10 (`WELL_DETAIL.NATIVE_ID`; every Permian wellbore is type API10,
  sequence 0, so `wellbore_key` = `US:API10:<api10>:0`).
- Row-level production and forecast: a sample of 2,551 wells, every 26th api10 of the 66,311
  wells with `WellMonths` rows.
- Floats compared exactly, and again within 0.1 %. Nulls counted separately.

## 3. View and column map

"Used" means a curated object reads the column today. Unused v3 columns are left out.

### 3.1 `Wells` and `WellDetails` -> `WELL_DETAIL`

`WELL_DETAIL` is one flat row per wellbore (471,076 rows) that already joins `WELLBORE`, `WELL`,
`WELLBORE_COMPLETION_DESIGN`, `WELLBORE_PRODUCTION_SUMMARY` and `WELLBORE_SPACING_DETAIL`. It has
no modified timestamp; `WELL` and `WELLBORE` do. Land-grid columns come from `SURFACE_LOCATION`.

| v3 column | v4 column | Parity on common wells |
|---|---|---|
| API10 | NATIVE_ID | key |
| WellName, County, Basin, Subbasin | WELL_NAME, COUNTY, BASIN, SUBBASIN | 100 % |
| CountyCode | COUNTY_CODE | 100 % (94,729 with a value) |
| State ("Texas"), StateCode ("42") | STATE ("TX") | recode needed |
| Formation | FORMATION | 100 % |
| ReportedFormation | FORMATION_REPORTED_NORMALIZED | 100 % (the raw FORMATION_REPORTED matches 92 %) |
| GridFormation | FORMATION_CALCULATED | 100 % (73,765) |
| CurrentOperator | CURRENT_OPERATOR | 100 % |
| OriginalOperator | OPERATOR_ORIGINAL | 100 % |
| SlantCalculated | DIRECTION_CALCULATED | 100 % after recode. Note `DIRECTION` is not the same thing: 5,539 wells are "Vertical" in v3 and HORIZONTAL in v4 `DIRECTION`. |
| WellStatus | WELL_STATUS | recode needed: uppercase, underscores, "P&A" -> "PA" |
| WellType (Oil / Gas / O&G / Other) | PRIMARY_STREAM | **89.1 % only.** 7,472 wells are Oil in v3 and GAS in v4. See question 4. |
| LateralLength | LATERAL_LENGTH | 100 % (93,167) |
| TVD, MD | TVD_TD, MD_TD | 100 % |
| SHL / BHL / LP / MP latitude, longitude | SURFACE_*, BOTTOM_HOLE_*, LANDING_POINT_*, MIDPOINT_* | 100 % within 4e-6 degrees |
| SpudDate, DrillingEndDate, FirstCompletionDate, FirstProductionDate, PluggedDate | SPUD_DATE, TD_DATE, COMPLETION_DATE, FIRST_PRODUCTION_DATE, PA_DATE | 100 % |
| LastReportedMonth | LAST_REPORTED_MONTH | 100 % |
| FirstCompletionFluidVolume, FirstCompletionProppantMass | FLUID_VOLUME, PROPPANT_MASS | 100 % within 0.1 %; v3 is rounded to an integer (largest gap 6 lb) |
| FirstCompletionStages, FirstCompletionStages_AvgSpacing | STAGE_COUNT, STAGE_SPACING | 100 % |
| FirstCompletionProppantLbsPerGal, SoakTimeDays | PROPPANT_CONCENTRATION, SOAK_TIME_DAYS | 100 % |
| EUR20YR / 30YR / 50YR x Oil, Gas, Water, BOE | EUR_<stream>_<nn>YR | 100 % (65,965) |
| PeakMonthOil / Gas / Water / BOE | PEAK_MONTH_<stream>_INDEX | 100 % (oil checked) |
| PeakMonth<stream>Rate | PEAK_MONTH_<stream>_AMOUNT | 100 % (oil checked) |
| DirectionalSurveyIsPlanned | PLANNED_AS_DRILLED_SURVEY (PLANNED / AS_DRILLED) | 100 % after recode (68,972) |
| Section, TXSurvey, TXAbstract, TXBlock | SURFACE_LOCATION.SECTION, TX_SURVEY, ABSTRACT_LOT, BLOCK_TOWNSHIP | 100 % |
| Township, Range | SURFACE_LOCATION.BLOCK_TOWNSHIP ("23S 22E New Mexico Principal") | must be parsed |

Used in v3 with **no v4 column**: `IsSyntheticApi`, `HasAccurateFirstProductionDate`,
`HasProductionSharing`, `CountyUnique`, `CurrentOperatorEntity`, `DeletedAt`.
`WellboreLateralLength` exists only as a deprecated column on `WELLBORE` (frozen 2026-09-24,
matches 92.4 %).

### 3.2 `WellMonths` -> `PRODUCTION_MONTHLY` (flat) or `PRODUCTION` (base)

| v3 column | v4 column | Note |
|---|---|---|
| API10, Year, Month, Date | NATIVE_ID, YEAR, MONTH, PRODUCTION_DATE | |
| OilPerMonth, GasPerMonth, WaterPerMonth | OIL, GAS, WATER | integers on both sides |
| FlaredGasPerMonth | GAS_FLARED | |
| ProducingDays, CumulativeProducingDays | PRODUCING_DAYS, CUMULATIVE_PRODUCING_DAYS | |
| MonthsOnProduction | MONTHS_ON_PRODUCTION | |
| Operator | PRODUCTION.OPERATOR_REPORTED | base view only; uppercase in v4 |
| Is{Oil,Gas,Water}FromProductionSharing | IS_*_FROM_PRODUCTION_SHARING | |
| IsGasFlaredFromProductionSharing | PRODUCTION.IS_GAS_FLARED_FROM_PRODUCTION_SHARING | base view only |
| ModifiedAt | PRODUCTION.UPDATED_AT | base view only |
| Basin, Subbasin | BASIN, SUBBASIN | |

**No v4 column:** `OilPerDay`, `GasPerDay`, `WaterPerDay`, `FlaredGasPerDay` (the rates of
record), `CumulativeOil`, `CumulativeGas`, `CumulativeWater`, `CumulativeFlaredGas`,
`OperatorEntity`, `DeletedAt`. v4 adds `CALENDAR_DAYS`.

### 3.3 `WellSpacing` -> `WELL_SPACING` (base) or the spacing columns of `WELL_DETAIL`

All ten used columns exist under the obvious names (`IS_CHILD`, `PARENT_COUNT`,
`PARENT_DAYS_ONLINE`, `CLOSEST_WELL_XY`, `CLOSEST_TWO_AVG_XY`, `WELLS_IN_RADIUS`,
`LATERAL_CLOSER_XY`, `STAGGER_CLOSER_TANGENT`, `STACK_CLOSER_Z`, `BOUNDEDNESS_SCORE`).
`WELL_SPACING.UPDATED_AT` replaces `ModifiedAt`. No `DeletedAt`.

### 3.4 `ForecastWellMonths` -> `PRODUCTION_FORECAST_MONTHLY` (flat) or `PRODUCTION_FORECAST` (base)

| v3 column | v4 column | Note |
|---|---|---|
| API10, Date | NATIVE_ID, FORECAST_DATE | |
| OilPerDay, GasPerDay, WaterPerDay | OIL_PER_DAY, GAS_PER_DAY, WATER_PER_DAY | v3 rounded to 0.1; v4 mostly unrounded |
| CumulativeOil / Gas / Water | CUMULATIVE_OIL / GAS / WATER | **different origin**, section 4.6 |
| MonthsOnProduction | FORECAST_MONTH | equal on 17,751 of 17,751 sampled rows |
| IsForecasted | none | the v4 view holds forecast rows only; actuals are in `PRODUCTION_MONTHLY` |
| ModifiedAt | PRODUCTION_FORECAST.CREATED_AT | base view only; there is no UPDATED_AT |

**No v4 column:** `OilPerMonth`, `GasPerMonth`, `WaterPerMonth` (rate x days in month rebuilds
the oil volume within 1 bbl on 98.5 % of sampled rows), `DeletedAt`.

### 3.5 `DirectionalSurveys` -> `DIRECTIONAL_SURVEY_STATION`

| v3 column | v4 column |
|---|---|
| API10 | WELLBORE_KEY |
| Path | STATION_SEQUENCE (1-based, contiguous on all 69,095 wellbores) |
| MD, TVD | MD, TVD |
| SubSeaTVD | SUB_SEA_TVD_CALCULATED |
| LocationType | LOCATION_TYPE (same integer codes, -1 and 0 to 7) |
| Latitude, Longitude, Interpolated | LATITUDE, LONGITUDE, INTERPOLATED |
| ModifiedAt | UPDATED_AT |

No `DeletedAt`. `sql/64` would work unchanged on a table of the v3 shape built from this view.

## 4. Row-level parity

### 4.1 Well counts

| | Count |
|---|---|
| v3 `Wells` | 95,985 (89,973 Horizontal, 5,539 Vertical by `SlantCalculated`, 473 U-turn) |
| v4 `WELL_DETAIL`, DIRECTION horizontal or U-turn | 96,751 (96,278 + 473) |
| v3 wells found in v4 | 95,985 (100 %), all sourced from US_Horizontals |
| v3 wells missing from v4 | 0 |
| v4 horizontal wells missing from v3 | 766, all sourced from US_Onshore. 512 ACTIVE, 186 PA. 308 have a first production date. Novi's own calculated slant says VERTICAL on 557 of them. |

### 4.2 Monthly volumes and producing days (sample of 2,551 wells)

| | Well-months |
|---|---|
| v3 rows | 207,680 |
| v4 rows | 204,319 |
| In both | 204,127 |
| v3 only | 3,553. 3,477 have all three volumes null or zero, and 3,436 of those fall after the well's last v4 month (v3 pads the tail with empty rows). 76 carry volumes, in 5 wells. |
| v4 only | 192. 130 belong to one well; 66 are 2026 months. |

On the 204,127 common well-months:

| Field | Exactly equal | Misses |
|---|---|---|
| Oil, bbl/month | 99.706 % | 600 rows in 11 wells. Median gap 153 bbl, P90 604, max 6,500. |
| Gas, Mcf/month | 99.756 % | 496 rows in 8 wells. Median gap 664 Mcf, P90 3,729, max 35,507. |
| Water, bbl/month | 99.532 % | 955 rows in 14 wells. Median gap 504 bbl, P90 8,174, max 44,592. |
| Producing days | 100 % | none (null on 75 % of rows on both sides) |
| Cumulative producing days | 100 % | none |
| Months on production | 99.977 % | 47 rows, one well |
| Flared gas | 99.825 % | 186 rows; another 171 are null on one side and 0 on the other |
| All of oil, gas, water, days | **99.508 %** | 1,004 rows in 15 wells |

The misses are not noise. In all 15 wells the v4 row carries a later update stamp than our row
(for example v4 2026-11-16 against ours 2026-07-28), and whole runs of months differ by a
constant factor, which is what a re-allocation looks like. 5 of the 15 wells no longer have a
`Wells` row on our side. I read this as our rows being stale, not v4 being wrong. It is not
proven: there is no third production source in the warehouse to settle it (section 9).

Full population, per-well life totals: 66,311 v3 wells have production; 66,216 of them have v4
production. Of the 66,017 that also have a `Wells` row, oil, gas and water totals are all equal
on 64,009 wells (96.96 %). Across those wells v4 is lower by 0.59 % on oil, 0.13 % on gas and
0.33 % on water. Counting the wells without a `Wells` row as well, 2,132 of 2,156 mismatched
wells are in Texas. The well-level mismatch share
(3.0 %) is higher than the well-month share (0.5 %) because a single missing or extra month
breaks a well's total.

### 4.3 Calendar-day and producing-day rates

v4 carries **volumes and days only**. There is no per-day rate column in `PRODUCTION_MONTHLY` or
`PRODUCTION`.

The v3 rate is reproducible. On every sampled well-month where the volume matched, the v3
`OilPerDay`, `GasPerDay` and `WaterPerDay` equal `round(volume / days in month, 1)`: oil 202,206
of 202,206, gas 202,306 of 202,306, water 203,046 of 203,046. `FlaredGasPerDay` follows the same
rule (162,924 of 162,924). v4 `CALENDAR_DAYS` equals the days in the month on 100 % of rows. So
v3's rate is a calendar-day rate rounded to 0.1 bbl/d or Mcf/d, with no first-month exception.
Neither feed ships a producing-day rate; `rate_prodday_*` is already ours.

`CumulativeOil` equals the running sum of `OilPerMonth` on 98.8 % of sampled rows (2,435 of
2,551 wells). I did not chase the rest, and did not check gas, water or flared.

### 4.4 `LATERAL_CLOSER_XY` and the 2800.0 sentinel

- v3 has 63,650 live spacing rows (63,841 with 191 soft-deleted). v4 has a spacing row for every
  one of them, and for 264 more wells.
- All ten columns agree on all 63,650 wells. The float columns differ by at most 0.00012 ft.
- **2800.0 exactly: 8,385 wells in v3, the same 8,385 wells in v4.** Across all v4 horizontals
  the count is 8,574. `WELL_SPACING_CONFIGURATION` states it outright:
  `DEFAULT_LATERAL_DISTANCE` = 2800, `MAX_NEIGHBOR_DISTANCE` = 2640 ft, in every sub-basin.
- One sentinel changed: `ParentDaysOnline` is -1 in v3 on 22,971 wells and NULL in v4.
  `curated.wells_enriched` passes that column through.

### 4.5 Survey stations

| | v3 | v4 |
|---|---|---|
| Wells with stations | 68,972 | 69,095 (68,534 horizontal, 471 U-turn, 69 vertical, 21 directional) |
| Stations | 15,954,057 | 15,973,799 |
| Stations on the 68,972 common wells | 15,954,057 | 15,954,057 |

Station count is equal on 68,972 of 68,972 wells. On 300 wells compared station by station
(65,692 stations), MD, TVD, sub-sea TVD, location type, latitude, longitude and the interpolated
flag are equal on 100 %. Location-type code counts line up code for code.

### 4.6 Forecast rates and cumulative

| | v3 (`IsForecasted`) | v4 |
|---|---|---|
| Rows | 21,672,506 | 23,873,693 total; 17,231,371 on horizontals and U-turns |
| Wells | 59,982 | 115,222 total; 57,816 horizontal and U-turn |
| Scenario | one | P50 only, monthly only, one forecast id per wellbore |

Common wells: 57,771.

- **Start month** equal on 57,714 (99.9 %).
- **Row count** equal on only 13,662 (23.6 %). Our series is longer on 44,087 wells, v4's on 17.
  The extra 4,016,644 rows are ours, and they are stale. Example, well 3001538484: Novi's current
  forecast is 131 months and ends 2037-07 at 1.3 bbl/d. Our table continues with 129 more months
  stamped 2026-10-21, 10-15, 09-17 and 08-12, in which the oil rate jumps back to 5.4 bbl/d and
  cumulative water steps down from 575,554 to 545,519 bbl. Those are the tails of four older
  forecast vintages. On affected sample wells, our last cumulative oil is a median 13 % above the
  cumulative at the end of the current forecast.
- **Rates** on the 656,762 common sample rows: oil 99.895 %, gas 99.943 %, water 99.886 % within
  0.1 %. The misses are 3 wells whose rows on our side are stamped 2026-07-30 and 2026-10-30
  (stale again). Exact equality is only 39.8 % because v3 rounds to 0.1 and v4 mostly does not.
- **Cumulative.** v4 counts from the start of the forecast: the first forecast row's cumulative
  is that month's own volume (398 of 400 wells checked). v3 counts from first production. The
  difference v3 minus v4 is constant along each well on 2,224 of 2,227 wells (within 2 bbl), so
  v3 cumulative = v4 cumulative + cumulative actuals at the last reported month.
- **Forecast in `raw_novi` but not in v4:** 2,211 wells (427,772 rows), mostly Active, first
  production 2012 to 2017. These were stale too: today's v3 file has forecast rows on 57,711
  wells, against 59,982 in `raw_novi` before the fix and 57,816 in v4. v4 carries
  `EUR_OIL_50YR` for 2,172 of them and Arps segments for 2,170, so Novi holds a forecast for
  them but ships no monthly rows in either feed (question 2). 61 horizontal wells had a v4
  forecast and no forecast in `raw_novi`.

## 5. Incremental-load feasibility

v4 keeps v3's change stamps: the newest `PRODUCTION.UPDATED_AT` (2026-11-17 14:56:11.450 UTC) is
our newest `WellMonths.ModifiedAt` to the millisecond. So the watermark logic carries over, but
only on the base views.

| v4 view | Modified stamp | Rows | Changed in last 1 / 7 / 30 days |
|---|---|---|---|
| `WELL_DETAIL` (flat) | none | 471,076 | full pull each night |
| `WELL`, `WELLBORE` | UPDATED_AT | 471,076 | 6 / 174,773 / 419,804 |
| `WELL_SPACING` | UPDATED_AT | 64,151 | 63,841 / 63,870 / 63,904 (rewritten nightly, as in v3) |
| `PRODUCTION_MONTHLY` (flat) | none | 51,885,710 | use `PRODUCTION` |
| `PRODUCTION` | UPDATED_AT | 51,885,710 (5,308,022 horizontal) | 0 / 17.9M / 22.9M, all directions |
| `PRODUCTION_FORECAST_MONTHLY` (flat) | none | 23,873,693 | use `PRODUCTION_FORECAST` |
| `PRODUCTION_FORECAST` | CREATED_AT only | 23,873,693 | 166,882 / 482,131 / 6.5M |
| `DIRECTIONAL_SURVEY_STATION` | UPDATED_AT | 15,973,799 | 0 / 3.1M / 15.9M |
| `WELL_EVENT`, `WELL_COMPLETION` | UPDATED_AT | 4,868,062 / 292,151 | 97,373 / 1.6M / 2.4M (events) |

No view has a soft-delete column. v4 is a hard-delete snapshot, so a v4 loader needs a per-well
key census each night (count and newest stamp per wellbore, then delete what is gone). That
census is cheap, and it would have prevented the stale rows found above.

Measured pulls, NOVI_WH (Medium, auto-suspend 60 s), fetched to the laptop, horizontals only:

| Pull | Rows | Seconds |
|---|---|---|
| `WELL_DETAIL`, all columns | 96,751 | 13.5 |
| `PRODUCTION`, heaviest recent day (2026-11-16) | 1,641,920 | 24.5 |
| `PRODUCTION`, quiet day (2026-11-17) | 9,490 | 7.4 |
| `PRODUCTION_FORECAST`, rows created 2026-11-05 | 768,674 | 13.8 |
| `DIRECTIONAL_SURVEY_STATION`, stations updated 2026-11-16 | 1,839,977 | 17.8 |
| Per-well census of `PRODUCTION` | 66,329 groups | 7.1 |

Throughput was 56,000 to 103,000 rows/s. A heavy night is about 4.3M rows and under 2 minutes of
Snowflake time. A quiet night is the header, spacing and three censuses: under 1 minute. A full
reload of all three big tables (5.3M + 17.2M + 16.0M rows) extrapolates to about 10 minutes; I
did not run it. At the standard 4 credits per hour for a Medium warehouse, a nightly is roughly
0.1 to 0.2 credits. Whether Novi meters or caps the reader account is question 7.

For comparison, the v3 nightly downloads a 1.6 GB zip every night, and on forecast days upserts
7.9M to 9.3M `ForecastWellMonths` rows in about 4 minutes. v4 stamps far fewer forecast rows per
day (at most 768,674 in the last month), so the Supabase write would shrink. The Supabase write
cost was not measured.

## 6. What v4 adds

- **Verticals and directionals: 374,325 wellbores** (367,654 + 6,671) that we do not get from
  Novi today. 198,447 have a first production date, 287,246 a TVD, 195,117 an EUR. They carry
  46.6M monthly production rows back to 1973 and 6.6M forecast rows.
- **`WELL_EVENT`: 4,868,062 rows, 14 event types.** WELL_TEST 2,524,537; PERMIT_APPROVED 345,126;
  COMPLETED 289,673; SPUD 273,374; PERMIT_SUBMITTED 272,930; TIL 264,776; TD_REACHED 264,705;
  OPERATOR_CHANGE 211,431; PA 148,601; PERMIT_CANCELLED 93,443; FRAC_START and FRAC_END 86,381
  each; PERMIT_AMENDED 5,895; REFRAC 809. Every row has a date. Permit events carry the filed
  lateral length, TVD and bottom hole in a JSON payload. Operator-change history is new to us.
- **`WELLBORE_TRAJECTORY`:** a WKT line (EPSG:4326) for 94,535 of 96,278 horizontals (98.2 %)
  and all 473 U-turns.
- **Source lineage (`SOURCE`):** 32 rows. It names the Novi export set a row came from (for
  example `wells` from US_Horizontals or US_Onshore). It is dataset-level, not regulator-level;
  it does not say which state filing a volume came from.
- **`DOWNLOADS_FULL` / `DOWNLOADS_DIFF`:** signed links to zip files. Permian full = 7,313 MB;
  the last seven daily diffs ran 173 to 4,686 MB. That is 4.5 times our v3 zip, because it
  includes the verticals. I did not download one. With SQL access to the same data there is no
  reason to use the files.
- Also new: Arps segments per stream (`WELLBORE_DECLINE_PARAMETERS`, 260,779 wells), well tests
  (2.5M rows, 104,921 with oil gravity), permits with proposed TVD, FracFocus, rig activity.

**Could it replace Enverus?** Not as it stands. The warehouse uses one Enverus table,
`raw_enverus.wells` (640,167 rows), in two places: `curated.enverus_lateral_lines` (the
wellstick geometry from `lateralline`) and about 43 columns of `curated.wells`.

- Possible: v4 trajectories could stand in for the Enverus lateral line, and v4 vertical headers
  could cover the vertical wells we take from Enverus today. Neither was tested here.
- Not possible: v4 has no cluster data (`clustersperstage`, `clustersper1000ft`), no pad id
  (`PLANNED_WELL.PAD_ID` is documented as always NULL), and nothing like the Enverus interval
  and play names (`envinterval`, `envplay`, `envsubplay`).

Dropping Enverus is a separate study: geometry parity first, then a column-by-column call on the
43 columns.

## 7. Migration outline (for when the blockers clear)

1. Run the overdue `--reconcile` and `etl.refresh --force` on v3. It is independent of v4, and
   it makes later v3/v4 comparisons clean. Needs an explicit go.
2. Send section 8 to Novi. Decide the rate convention (question 1) with Michael.
3. Add a read-only shadow compare (a script like the ones behind this study) and run it for at
   least two weeks, across one heavy production day and one forecast day. Pass bar: the
   section 4 numbers hold or improve after step 1.
4. Build a v4 loader next to `etl/intel_sf` that lands v4 into new raw tables, with the per-well
   census for deletions. New DDL needs an explicit go. Leave `raw_novi` untouched.
5. Put a compatibility layer on top that presents the six v3 table shapes: v3 column names,
   recoded status, slant and state, -1 for `ParentDaysOnline`, cumulative rebased, per-day rates
   under the agreed rule. `sql/04`, `05`, `10`, `49`, `64` and the Python readers of `raw_novi`
   (BOX, `etl/box_recon.py`, the apply scripts) then need no change.
6. Cut over one table at a time, simplest first: `DirectionalSurveys`, `WellSpacing`, `Wells` and
   `WellDetails`, `WellMonths`, then `ForecastWellMonths`. Rebuild curated from the new source in
   a scratch schema and diff it against live before each switch.
7. Keep the `meta.etl_log` labels. The v4 forecast load must still log a `table_name` starting
   with `ForecastWellMonths`, or the `production_forecast` refresh gate never fires.
8. Keep the v3 nightly path runnable for one quarter as fallback.
9. Only then consider scope growth: verticals, `WELL_EVENT`, the Enverus question.

## 8. Open questions for Novi

Questions marked **[guide]** are answered by Novi's user guide (section 11) and need not be
sent. Still to send: 2, 7, 9, 10, 12 (notice period only), 13 and 14.

1. **[guide]** `PRODUCTION_MONTHLY` has no per-day rates. v3's `OilPerDay` equals volume / days in month
   rounded to 0.1. Is that the definition, and will v4 ever ship rates, or is the consumer meant
   to compute them?
2. About 2,200 Permian horizontal wells have an EUR and Arps segments but no monthly forecast
   rows, in v3 `ForecastWellMonths` and in v4 `PRODUCTION_FORECAST_MONTHLY` alike. They had
   monthly rows in v3 until recently. Is that intended? (Example list available.)
3. **[guide]** Answered by the 2026-11-19 v3 file (section 10): rows do leave the v3 TSV when a forecast
   shortens or a well leaves scope, with no deletion marker. Is there any signal for those
   removals short of comparing keys?
4. **[guide]** v3 `WellType` differs from v4 `PRIMARY_STREAM` on 10.9 % of wells (7,472 Oil in v3, GAS in
   v4). How was v3 `WellType` derived, and which v4 column carries it?
5. **[guide]** `PRODUCTION_FORECAST` has `CREATED_AT` and no `UPDATED_AT`, and rows within one forecast can
   carry different dates. What is the supported way to detect a changed forecast, and a deleted
   one?
6. **[guide]** No view has a deletion marker. Is a nightly key comparison the intended way to find deletes?
7. Is the reader account's warehouse use metered or capped? Is a nightly pull of 1M to 5M rows
   within fair use?
8. **[guide]** `WELL_DETAIL`, `PRODUCTION_MONTHLY` and `PRODUCTION_FORECAST_MONTHLY` have no modified stamp.
   Will they get one, or should incremental loads read the base views?
9. v3 columns with no v4 home: `HasAccurateFirstProductionDate`, `HasProductionSharing`,
   `IsSyntheticApi`, `CurrentOperatorEntity` / `OperatorEntity`, `CountyUnique`, the cumulative
   volume columns on production, forecast monthly volumes. Dropped on purpose?
10. `ParentDaysOnline` is -1 in v3 and NULL in v4 for the same 22,971 wells. Same meaning?
11. **[guide]** 766 Permian wells are HORIZONTAL in v4 but absent from v3 us-horizontals, and Novi's own
    calculated slant calls 557 of them vertical. Which direction column defines "horizontal" for
    scope?
12. What notice will Novi give before a v4 schema change, and is there a changelog?
13. Our entitlement is Permian only. Is that the intended scope of the share?
14. `WELLBORE_LATERAL_LENGTH` is deprecated in favour of `LATERAL_LENGTH_CALCULATED_LP_TO_BHL`,
    but that column is filled on only 18,727 of the 68,973 Permian horizontals where v3
    `WellboreLateralLength` has a value (section 11). Will its coverage be backfilled?

## 9. Checks I could not run

1. **Today's v3 TSV was not inspected during the study.** It was downloaded and scanned
   afterwards for the reconcile, and it confirmed the stale-row reading (section 10). The
   section 4 comparisons were not re-run against the cleaned tables.
2. **No third source for volumes.** The warehouse holds no Enverus production, so where v3 and
   v4 disagree I cannot say from data which is right.
3. **No curated-level diff.** Rebuilding `curated.wells`, `curated.production` or
   `curated.production_forecast` from v4 would need writes. Parity is shown at the raw level only.
4. **Row-level production and forecast parity is on the 2,551-well sample.** The full population
   was compared only on per-well totals, counts and date ranges.
5. **Cumulative gas, water and flared rebuilds** were not checked; oil only (98.8 %).
6. **Lateral geometry** (`WELLBORE_TRAJECTORY` against `curated.enverus_lateral_lines`) was not
   compared.
7. **Timing from a GitHub Actions runner** was not measured; all timings are to the laptop.
   Supabase write time for v4-shaped loads was not measured. Snowflake credit use was estimated
   from the standard rate, not read from account usage.
8. **One snapshot only.** Day-over-day behaviour of v4 (restamps, deletes, schema drift) is
   unobserved.
9. **Not compared on values:** `HasAccurateFirstProductionDate`, `HasProductionSharing`,
   `IsSyntheticApi`, `OperatorEntity`, per-month operator names beyond a spot check, and the
   peak-month columns for gas, water and BOE.

## 10. Reconcile run, 2026-11-19

Michael gave the go for the overdue v3 reconcile and a forced curated refresh after reading the
side finding. Both ran on 2026-11-19 from the laptop against the live warehouse. No ETL code
changed.

**Today's v3 file first.** Export `Novi_v3_US_Horizontals_T1_Permian_2026-11-19-10-37-57`, scanned
before anything was written: 95,990 wells; 5,241,013 `WellMonths` rows; 22,353,490
`ForecastWellMonths` rows, of which 17,217,480 are forecast rows on 57,711 wells; 15,954,057
survey stations. No row in any file has `DeletedAt` set, so Novi drops rows from the file rather
than marking them.

**Reconcile** (`python -m etl.novi.load --reconcile`, 15:58 to 16:32 UTC):

| Table | Rows before | Rows after | Deleted | Time |
|---|---:|---:|---:|---:|
| `WellMonths` | 5,388,571 | 5,241,013 | 149,178 | 283 s |
| `ForecastWellMonths` | 26,864,712 | 22,353,490 | 4,511,222 | 1,023 s |
| `DirectionalSurveys` | 15,954,057 | 15,954,057 | 0 | 713 s |

All three tables now equal the file row for row in count. 2.8 % of `WellMonths` and 16.8 % of
`ForecastWellMonths` had been stale. Wells with forecast rows fell from 59,982 to 57,711. No
`WellMonths` well is left without a `Wells` row. The example well 3001538484 went from a forecast
tail running past the vendor's to 131 forecast rows ending 2037-07, the same as v4.

**Forced refresh** (`python -m etl.refresh --force`, 16:37 to 17:43 UTC): all 16 nightly matviews
refreshed, each logged `success` in `meta.etl_log`. `curated.production_forecast` took 43 minutes.
Checked live afterwards:

- `curated.production_forecast`: 17,217,480 rows on 57,711 wells, equal to the forecast rows in
  the file.
- `curated.production`: 5,241,013 rows on 66,021 wells, equal to `raw_novi."WellMonths"`.

**Side effects of the refresh.** `etl.refresh` runs the same hooks as the nightly, so it also
wrote formation-tag run 10 (0 changes against run 9) and BOX recon run 3. Run 3 is the first
written BOX recon run (logged `first_run`, 79,200 record sticks), one night ahead of the 5d
shadow week, which planned the 2026-11-20 nightly as its first night. That nightly will now
compare against run 3 instead of being the first run.

**What this does not fix.** The nightly still cannot delete rows from `WellMonths` or
`ForecastWellMonths`. Stale rows will build up again, at roughly the rate seen here (4.5M
forecast rows in five months), until the loader handles deletions or the reconcile is put on a
schedule. Anything that copied the warehouse before today (anduin's synced production, stored
BOX inputs) still holds what it copied.

## 11. What Novi's user guide answers

Source: "WELLS Schema User Guide", release 26.4.3, generated 2026-11-13 (108 pages), received
from Michael on 2026-11-19 after the study. Read against the two blockers in section 1 and the
questions in section 8.

**Settled by the guide**

| Topic (question) | What the guide says | Effect |
|---|---|---|
| Age of v4 | Release 26.4.3, "the first release of Novi Wells in Snowflake", released 2026-10-29. Builds run on weekdays only. | Corrects section 1: v4 was three weeks old at the study, not one day. |
| Per-day rates (1) | `PRODUCTION` carries `CALENDAR_DAYS` and `PRODUCING_DAYS` "to support rate normalization". No actual-production view has a rate column. | The consumer computes rates. Matches section 4.3 (volume / days in month, rounded to 0.1). The rule 4 wording is still Michael's decision. |
| Deletions (3, 6) | No deletion marker in the views. The diff zips ship `<Table>--deleted.tsv` with the keys of removed rows, and a whole-table file when a table cannot be compared, "for example after a column change". | Hard deletes found by key comparison are the intended method. The census in section 5 is the SQL form of it. |
| Changed forecasts (5) | `PRODUCTION_FORECAST_ID` "groups the period rows of one forecast". `CREATED_AT` is the "source ingestion timestamp from the production forecast feed". | Compare forecast ids per well; a new id means re-pull that well's forecast whole. |
| Flat views (8) | They are "presentation views" that join the base views. | Incremental loads read the base views, as section 5 assumed. |
| Horizontal scope (11) | `DIRECTION` is resolved in order: U-turn from the calculated slant; a survey not marked planned that shows a horizontal path; the filed slant; the calculated slant. | The 557 wells Novi's calculation calls vertical are horizontal by filing. Scope can be stated as a rule on `DIRECTION` and `DIRECTION_CALCULATED`. |
| `WellType` (4) | `PRIMARY_STREAM` is the declared purpose from the filing: "Declared purpose, not observed production"; it "asserts nothing about volumes". | It is a different quantity from v3 `WellType`. The 10.9 % mismatch is expected, and one must not be mapped onto the other. v4 has no stated equivalent of v3 `WellType`. |
| Forecast cumulative | "Accumulated over the FORECAST horizon only." Actual and forecast months "OVERLAP and are not reconciled". | Confirms section 4.6. |
| Changelog (12, part) | A "What changed" chapter and a release-history appendix "generated from the release catalog". | A changelog exists. The notice period before a change is not stated. |

**Also learned**

- `MONTHS_ON_PRODUCTION` changed from 0-based to 1-based in September 2026. v3 and v4 agree in
  the sample, so nothing is off today, but Novi does change a convention in place.
- `WELLBORE_LATERAL_LENGTH` is "deprecated and no longer maintained": frozen at its value before
  2026-09-24 and NULL on wellbores added since. The guide names
  `LATERAL_LENGTH_CALCULATED_LP_TO_BHL` as the replacement. Checked live on 2026-11-19 against
  v3 `WellboreLateralLength` (read by `curated.wells` as `wellbore_lateral_length_ft`), on the
  68,973 wells where v3 has a value:

  | v4 column | Wells with a value | Equal to v3 within 1 ft |
  |---|---:|---:|
  | `WELLBORE_LATERAL_LENGTH` (deprecated) | 59,499 | 54,876 |
  | `LATERAL_LENGTH_CALCULATED_LP_TO_BHL` | 18,727 | 18,727 |

  The replacement is exact where it exists but covers 27 % of the wells. A v4 loader could not
  fill `wellbore_lateral_length_ft` for the other 73 % today (question 14). The completed lateral
  (`LateralLength` -> `LATERAL_LENGTH`) is not affected; it matched 100 % in section 3.1.

**Not answered by the guide**

- The roughly 2,200 wells with an EUR and Arps segments but no monthly forecast rows (2).
- Whether the reader account's warehouse use is metered or capped (7).
- v3 columns with no v4 home, and `ParentDaysOnline` -1 against NULL (9, 10). The guide is silent
  on all of them.
- How much notice precedes a schema change (12).
- Day-over-day behaviour is still unobserved by us (section 9, item 8).

## 12. Loader build, 2026-11-19

Michael reframed the question the same day: v3 is deprecated, v4 is the source, what stops the
move. Answer: nothing on Novi's side. The loader did not exist. It does now, in `etl/novi_v4`,
not yet wired into the nightly and not yet run against any table.

**Shape.** The loader presents v4 in the six v3 table shapes, so `sql/04`, `05`, `10`, `49`, `64`
and every reader of `raw_novi` stay as they are. The translation is Snowflake SQL
(`etl/novi_v4/queries.py`); Python only streams rows into Postgres.

- Header tables (`Wells`, `WellDetails`, `WellSpacing`): whole table each run, replaced inside
  one transaction.
- Child tables (`WellMonths`, `ForecastWellMonths`, `DirectionalSurveys`): a per-well census
  (row count and newest stamp) on both sides. A well that differs is re-pulled whole; a well
  that left the share is deleted. This is what the v3 nightly could not do.
- Guards: a run refuses to delete more than max(200, 1 %) of wells, or to replace a header
  table with under 90 % of its rows, without `--allow-breaker`. Writing `raw_novi` needs
  `--confirm-live`.
- `meta.etl_log` label on the live schema is `<table> (v4)`, so the `ForecastWellMonths%` gate
  keeps firing, and now fires on deletions too. On the side-by-side schema the label cannot
  match the gate.

**Two corrections to earlier sections.**

- *Scope.* The v3 population is exactly the wellbores whose `WELLBORE.SOURCE_ID` is Novi's
  `US_Horizontals` export set: 95,990 wells, the count in the 2026-11-19 v3 file. The loader
  uses that. A rule on `DIRECTION_CALCULATED` (floated in conversation) would have been wrong:
  5,539 wells already in v3 are calculated-vertical. Taking any of the 766 `US_Onshore`
  horizontals is a separate decision and is not built.
- *`HasProductionSharing` is not lost.* v4 has no well-level flag, but `PRODUCTION` carries the
  monthly ones. "Any month flagged" equals the v3 well flag on 95,985 of 95,985 wells.

**Read-only compare of the loader's output against `raw_novi`** (after the section 10
reconcile; `python -m etl.novi_v4.load --compare --sample-every 60`). Header tables are every
well; child tables are a 1,101-well sample.

| Table | Rows compared | Result |
|---|---:|---|
| `Wells`, `WellDetails` | 95,985 wells | Every filled column equal on 100 % of wells where both have a value, except the items below. v4 has 5 newer wells. |
| `WellSpacing` | 63,650 wells | All 12 filled columns equal on 100 %. v4 has 264 more wells; 191 v3 rows are not in v4. |
| `WellMonths` | 87,285 well-months | Volumes, days, months on production, operator, sharing flags and all four per-day rates equal on 100 %. `CumulativeWater` 99.92 %, `CumulativeFlaredGas` 99.80 % (v3's running totals are not a clean sum on a few wells; section 4.3). |
| `ForecastWellMonths` | 281,043 rows | Same rows on both sides. Rates and monthly volumes 100 %. `CumulativeOil` 99.65 % (misses are 1 bbl of rounding), gas and water 99.96 %. |
| `DirectionalSurveys` | 223,005 stations | Every column 100 %. |

Full-table row counts from the loader's SQL equal `raw_novi` exactly: 5,241,013 production
rows, 17,217,480 forecast rows, 15,954,057 stations. No NULL in any column the v3 tables
declare NOT NULL.

**What the compare changed in the translation.**

- *Rate rounding.* v3 rounds an exact tie to the even digit (97.25 -> 97.2). Snowflake's
  default rounds away from zero. Ties only happen in 28-day Februaries, about 0.2 % of
  well-months. The loader divides in fixed point and rounds half to even; rates then match 100 %.
- *Operator.* v3's monthly `Operator` is Novi's company name (`OPERATOR.NAME`), not the filer's
  legal name in `OPERATOR_REPORTED`.
- *Texas land grid.* v3 stores `''`, not NULL, on Texas wells without a block or abstract.

**Known differences that remain.**

- `DirectionalSurveyIsPlanned`: v4 is NULL on wells without a survey. v3 was FALSE on 23,107 of
  those and NULL on 3,906, with no rule that separates them; the loader writes FALSE. 584
  wells are planned in v3 with no v4 survey flag at all, so they lose the flag. They have no
  stations either. Worth a question to Novi.
- `WellboreLateralLength`: filled on 18,727 wells against 68,973 (section 11). Nothing reads it.
- No v4 source, left NULL: `WellType`, `IsHorizontalWell`, `HasPLSSData`, `WellboreLocations`,
  `HasAccurateFirstProductionDate`, `IsSyntheticApi`, `CountyUnique`, `CurrentOperatorEntity`,
  `OperatorEntity`. `curated.wells.well_type` then falls through to the Enverus value already
  in its COALESCE. No reader of any of these was found.
- `ForecastWellMonths` holds forecast rows only. v3 also carried 5,136,010 history rows
  (`IsForecasted` = FALSE); `sql/10` never read them and nothing else does. They go at cutover.
- `PermitID` differs on 0.13 % of wells (v4 carries a newer permit).

**Dry run of the census against the live tables** (`--schema raw_novi --dry-run`, no writes):

| Table | Wells remote / local | Wells to re-pull | Wells to delete |
|---|---|---:|---:|
| `WellMonths` | 66,021 / 66,021 | 0 | 0 |
| `ForecastWellMonths` | 57,711 / 65,959 | all (first run) | 8,248 (history-only wells) |
| `DirectionalSurveys` | 68,972 / 68,972 | 29,893 | 0 |

`WellMonths` agrees to the millisecond: v4 `UPDATED_AT` is v3 `ModifiedAt`. Survey stamps differ
on 43 % of wells with identical station counts, so the first run reloads surveys once. Section 5
showed Novi restamps every station within 30 days, so expect a full survey reload about monthly
(roughly 12 minutes of Supabase write, by the section 10 timing).

**Not done.** No table has been written. `sql/75` (the side-by-side schema `raw_novi_v4`) is
authored, not applied. The nightly does not call the loader. The Supabase write time of a full
v4 load is still unmeasured, and so is a run from a GitHub Actions runner.

**Order from here.** Apply `sql/75`; load `raw_novi_v4` in full; diff every row against
`raw_novi`; run a second night into it to see a real incremental; then drop NOT NULL on the same
unsourced columns in `raw_novi`, run the loader on it with `--confirm-live`, switch
`scripts/run_daily.py` to the v4 loader, force one curated refresh, and drop `raw_novi_v4`.
Each of those warehouse steps needs its own go.

## 13. Side-by-side load and full diff, 2026-11-19

With Michael's go, `sql/75` was applied and `raw_novi_v4` was loaded in full from v4, then every
row was diffed against `raw_novi` inside Postgres
(`python -m etl.novi_v4.load --schema raw_novi_v4 --diff`, read-only).

**Load.** 22 minutes from the laptop, 13:19 to 13:41 local, 38.7M rows. The first attempt failed
on its first table on a bug in the loader's COPY helper and rolled back with nothing written;
fixed and covered by a test.

| Table | Rows loaded | Time |
|---|---:|---:|
| `Wells`, `WellDetails`, `WellSpacing` | 95,990 / 95,990 / 63,914 | under 20 s each |
| `WellMonths` | 5,241,013 | 2 min 44 s |
| `ForecastWellMonths` | 17,217,480 | 10 min 26 s |
| `DirectionalSurveys` | 15,954,057 | 8 min 20 s |

`raw_novi_v4` is 7.6 GB on disk (`raw_novi` is 22.6 GB, bloated by the reconcile).

**Diff, every row.**

| Table | Common rows | v4 only / v3 only | Columns equal on every row | What differs |
|---|---:|---|---|---|
| `WellMonths` | 5,241,013 | 0 / 0 | 20 of 23 | `CumulativeWater` 0.062 % of rows, `CumulativeFlaredGas` 0.181 %, `Operator` 147 rows |
| `ForecastWellMonths` | 17,217,480 | 0 / 0 | 10 of 13 | The three cumulative columns, 0.1 to 0.4 % of rows. Almost all are 1 to 2 units of rounding; 135 wells are off by more on gas |
| `DirectionalSurveys` | 15,954,057 | 0 / 0 | 13 of 13 | nothing |
| `WellSpacing` | 63,650 | 264 / 191 | 12 of 12 | nothing |
| `Wells` | 95,985 | 5 / 0 | 40 of 52 | see below |
| `WellDetails` | 95,985 | 5 / 0 | 80 of 100 | see below |

All monthly volumes, producing days, months on production, sharing flags and the four per-day
rates are equal on all 5,241,013 well-months. All forecast rates and monthly volumes are equal
on all 17,217,480 rows. `LateralCloserXY` is equal on all 63,650 wells.

Header differences, all 95,985 wells:

- `DirectionalSurveyIsPlanned` 4,490 wells and `WellboreLateralLength` 50,246 wells: the two
  known gaps from section 12.
- `FirstCompletionProppantMass` 15,228 wells and `FirstCompletionFluidVolume` 8,656 wells: new at
  full population, and noise. Every difference is 1 to 6 lb or gal, at most 6e-8 relative
  (v4 ships a float, v3 an integer).
- `SpacingIsChild` / `SpacingClosestWellXY` on 907 wells (copies of spacing columns that nothing
  reads), `PermitID` 145, `SpudDate` 11, land grid and landing point on 1 or 2 wells.

**Read.** The side-by-side copy reproduces `raw_novi` on every column that feeds a rate, a
volume, a forecast, a survey or a spacing. What differs is listed above and in section 12, and
none of it is read by a forecast or a cohort.

**Not done.** A second night into `raw_novi_v4` (to see a real incremental with changed and
deleted wells), the cutover of `raw_novi`, and the nightly switch. Each needs its own go.

## 14. Incremental rehearsal and a stamp defect, 2026-11-19

Before the real second night, the incremental path was exercised on the scratch copy: in each
child table of `raw_novi_v4` one well's rows were removed, one row of a second well was removed,
and a third well's rows were copied under a fake API. The loader should re-pull two wells and
delete one.

**Defect found.** The first rehearsal reloaded every table in full. The share's stamps are
`TIMESTAMP_LTZ` and arrive in Pacific time with an offset; a Postgres `timestamp` column drops
the offset, so the scratch copy held `ModifiedAt` 8 hours off UTC and every well's census
differed. On a live cutover this would have meant a full 38M-row reload every night. The
section 13 diff did not see it because it skipped the stamp columns.

**Fix.** Stamps are converted to naive UTC in the translation SQL, rows and census alike
(pinned by a test). The full diff now compares `ModifiedAt`.

**Rehearsal after the fix.** 86 seconds for the three tables, from the laptop.

| Table | Wells re-pulled | Wells deleted | Rows in / out |
|---|---:|---:|---|
| `WellMonths` | 2 | 1 | 414 / 388 |
| `ForecastWellMonths` | 2 | 1 | 105 / 108 |
| `DirectionalSurveys` | 2 | 1 | 290 / 332 |

The full diff afterwards is identical to section 13 on every data column, so the scratch copy
was repaired exactly. `ModifiedAt`:

- `WellMonths`: equal on all 5,241,013 rows. The census will track v3 stamps exactly.
- `Wells` / `WellDetails`: differ on 381 wells (headers are replaced whole, so this is harmless).
- `ForecastWellMonths`: differ on 96.7 % of rows. v4's only stamp there is `CREATED_AT`, which is
  not v3's `ModifiedAt`. Expected; it costs one full forecast reload at cutover.
- `DirectionalSurveys`: differ on 45.7 % of rows, the restamping noted in section 12.

A quiet night (nothing changed) costs the three censuses: under 2 minutes.

**Still open.** The real second night, scheduled for 2026-11-20 after the v3 nightly, will show
what a production day's changes look like. One `meta.etl_log` row
(`v4 raw_novi_v4.ForecastWellMonths`, started 20:12 UTC) is left at `running` from the stopped
first rehearsal; the nightly's stale-run sweep will close it.

## 15. Second night, 2026-11-20: the forecast change check misses in-place revisions

Run after the v3 nightly finished (11:44 UTC, no `running` rows; the stale row from section 14
was swept). Share run `20261120_100520`. Scratch schema only; `raw_novi` untouched.

**Run.** Dry run 67 s, load 5 min 33 s, no breaker.

| Table | Wells re-pulled | Wells deleted | Rows in / out |
|---|---:|---:|---|
| `WellMonths` | 6,966 | 0 | 699,049 / 697,270 |
| `ForecastWellMonths` | 2,074 | 27 | 531,625 / 518,161 |
| `DirectionalSurveys` | 2,298 | 0 | 513,842 / 513,842 |

Headers replaced whole: `Wells` / `WellDetails` 96,009 (+19), `WellSpacing` 63,948 (+34).
Header keys now match v3 exactly (96,009 common, none on one side only).

**The diff does not match section 13 on the forecast table.** Section 13 had every rate and
monthly volume equal on 17,217,480 rows. Today, on 17,230,944 common rows:

| Column | Rows differing | Share |
|---|---:|---:|
| `OilPerMonth` / `OilPerDay` | 109,829 / 73,647 | 0.64 % / 0.43 % |
| `GasPerMonth` / `GasPerDay` | 174,532 / 154,798 | 1.01 % / 0.90 % |
| `WaterPerMonth` / `WaterPerDay` | 260,089 / 242,206 | 1.51 % / 1.41 % |
| `CumulativeOil` / `Gas` / `Water` | 356,232 / 554,296 / 442,171 | 2.07 % / 3.22 % / 2.57 % |

**Cause: a loader defect, not a v3/v4 data difference.** Novi revised forecasts in place between
share runs `20261119_100441` and `20261120_100520`: same row count per well, same `CREATED_AT`,
different volumes. The forecast census keys on (row count, newest `CREATED_AT`), so it saw
nothing. Checked directly: for well 4247538139 Snowflake today returns exactly v3's values
(2026-10 oil 3,560 bbl/month in both) while the scratch copy still holds yesterday's 3,575, with
identical stamps. Across the table, **2,289 of 57,747 wells** have a final forecast cumulative in
Snowflake that differs from the scratch copy (a floor: a revision that kept the final cumulative
would not show in this count). v3 caught them all, because the v3 file carries a `ModifiedAt`
that moves (4,520 wells rewritten last night; the v4 census flagged 2,074).

So section 11's reading that `CREATED_AT` is enough to detect forecast changes is wrong, and the
loader as built would let about 4 % of forecast wells go stale per revision night. **This blocks
cutover until fixed.** Two ways to fix it:

1. Add a content checksum to the forecast census (final cumulative per stream plus the sum of
   per-day rates, computed on both sides). Keeps the incremental; a revision that changes none
   of those would still slip through.
2. Pull the forecast table in full every night: about 10 minutes and 17 M rows rewritten nightly,
   blind to nothing.

`WellMonths` is not affected: its `ModifiedAt` equals v3 on all 5,242,792 common rows and every
volume and rate column is still equal.

**Other differences new today.**

- Production-sharing flags differ on 2,205 well-months (2,105 wells), 1,997 of them the newest
  month (2026-09): v3 says TRUE, v4 says FALSE for gas and water, volumes equal. These wells were
  re-pulled today and Snowflake returns the same FALSE, so this is a real v3/v4 difference on a
  freshly reported month, not staleness. `HasProductionSharing` follows on 14 wells. Watch
  whether it closes as the month settles; a question for Novi if it does not.
- `CumulativeFlaredGas` 18,805 rows (0.36 %, was 0.18 %); `CumulativeWater` 4,427 (was 3,246);
  `MonthsOnProduction` 14 rows.
- Rows only in v3: 384 well-months and 22,436 forecast rows. v3's upsert cannot delete, so these
  are one night's stale rows on the v3 side (the class the section 10 reconcile cleared).
- Header columns: as section 13 within a few rows (`DirectionalSurveyIsPlanned` 4,513 wells,
  was 4,490).
- `DirectionalSurveys`: all 13 data columns still equal on 15,954,057 rows. The 2,298 wells
  re-pulled came back with identical data, so Novi restamps surveys without changing them;
  that costs about 2.5 minutes a night and nothing else.

**Fix (Michael chose option 1, 2026-11-20).** The forecast census now carries a content checksum
per well: the sum over the well's rows of the v4 oil, gas and water cumulatives. The local side
rebuilds the same integer from the stored monthly volumes, whose running sum is the v4 cumulative.
A well is re-pulled when its row count, newest stamp or checksum differs. Only the forecast table
carries one; `WellMonths` and `DirectionalSurveys` have a stamp that moves.

Verified on the scratch copy the same morning:

- The census flagged **2,291 wells** (the 2,289 counted above plus 2 whose final cumulative was
  unchanged but whose shape moved). Re-pull: 762,782 rows, 2 min 44 s.
- A second dry run straight after: **0 changed, 0 gone**, so both sides compute the same number
  on all 57,747 wells.
- Forecast diff against `raw_novi` afterwards: every per-day rate, monthly volume and
  `MonthsOnProduction` equal again on all 17,230,944 common rows. Cumulatives differ on
  0.28–0.56 % of rows (the rebasing class of section 13, 0.1–0.4 % then).

Cost: the local side of the forecast census is a window over 17 M rows, so a quiet night's
forecast check takes about 2 min 20 s instead of under a minute.

Limit: a revision that changes per-day rates while leaving every monthly cumulative unchanged
would not be seen. The monthly volumes are the cumulative differences, so that would be a
rate-only restatement; none has been observed.

## 16. Cutover decisions, 2026-11-20

Michael's decisions. Nothing is applied yet; every step below is its own go.

- **Date: Friday 2026-11-27**, right after the 05:00 CT nightly finishes (about 06:30 CT). The BOX
  recon shadow week closes with the 11-26 nightly, so its inputs do not move mid-week.
- **Planned-survey flag: take v4 as shipped.** 584 wells go from planned to not planned (4,513
  differ in total); the tag rule and `etl/box_recon.py` read it. Ask Novi about the 584.
- **Rule 4 wording changes at cutover:** per-day rates are computed in the loader by Novi's
  formula (monthly volume / days in the calendar month, one decimal), not persisted as shipped.
  They equal v3 on every row.

Steps, in order:

1. Code, no database change: a v4 step in `scripts/run_daily.py` behind a setting that defaults
   to v3; `sql/76` dropping NOT NULL on the six columns v4 cannot fill in `raw_novi."Wells"` and
   `"WellDetails"`; triage skill and CLAUDE.md wording. Merge PR 264.
2. Apply `sql/76` live (metadata only; the v3 loader keeps working).
3. `python -m etl.novi_v4.load --schema raw_novi --confirm-live`, the forecast table with
   `--full --allow-breaker` (v3's 5,136,010 history rows go). About 20 minutes.
4. `python -m etl.refresh --force`, then verify by identity and in the three apps.
5. Flip the nightly setting to v4; watch the next 05:00 CT run.
6. A week later: drop `raw_novi_v4`, retire the v3 sync and load code in a separate PR.

Rollback until step 6: flip the setting back, run the v3 nightly with `--reconcile`, forced
refresh.

**Step 1 built, 2026-11-20 (code only, nothing applied).**

- `scripts/run_daily.py` reads `NOVI_SOURCE`. Unset, blank or `v3`: the bulk-TSV sync and load,
  unchanged. `v4`: no `novi.sync` step; `novi.load` is `etl.novi_v4.load.nightly_load`, which
  writes the six live `raw_novi` tables, logs the share run id, and keeps going past a table
  that fails (that table keeps its previous rows and the step fails with its error). Any other
  value fails the Novi step and loads neither feed.
- `.github/workflows/etl-nightly.yml` passes the repository variable `NOVI_SOURCE` with a `v3`
  default. The flip (step 5) is `gh variable set NOVI_SOURCE --body v4`: no code change, no
  merge, and the same command with `v3` flips back.
- `sql/76_raw_novi_v4_nullable.sql` authored, **not applied**: drops NOT NULL on the six
  unsourced columns of `raw_novi."Wells"` and `"WellDetails"`. A test pins it to the same list
  as sql/75 and sql/02.
- `etl-nightly-triage` skill: a section for nights on v4.
- Left for the flip itself (step 5), because they describe the live state: the rule 4 wording
  and the data-flow paragraph in the workspace CLAUDE.md.
