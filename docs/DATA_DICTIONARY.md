# oilgas data dictionary

*Generated 2026-07-10 by `scripts/gen_data_dictionary.py` from the live catalog — do not hand-edit. Descriptions are Postgres COMMENTs (`sql/31_comments.sql`); re-run this script after schema changes.*

## Data flow

**Novi Insights (nightly) + Enverus (nightly) + Novi Intelligence (quarterly Snowflake share) -> raw schemas -> `curated` matviews -> apps (anduin / erebor / narvi) and direct read-only users.** Nightly: `scripts.run_daily` loads raw then refreshes the curated matviews in dependency order. Quarterly: the intel reload chain rebuilds the intel-derived matviews (`load_intel_sf` -> `apply_intel_formation_blueox` -> `apply_reconciled_inventory` -> `apply_erebor_locations`). The `narvi` schema is app-owned and not documented here.

## Conventions that affect interpretation

- `api10` is the universal well key; Novi <-> Enverus join is `LEFT(api14, 10) = api10`.
- Formation grouping always uses `formation_blueox`, never raw free-text `formation`.
- Rates for fitting/aggregation are calendar-day (`rate_calday_*`); `rate_prodday_*` is a per-well diagnostic.
- Novi NPV/IRR columns are a vendor screen, not authoritative economics; economics happens downstream of exports.
- SPE percentiles: P10 = HIGH case, P90 = LOW case.

## Schema `raw_novi`

### `raw_novi.ForecastWellMonths` (table)

Novi unified history+forecast time series. IsForecasted=false rows duplicate raw_novi."WellMonths" actuals; IsForecasted=true rows are Novi's algorithmic decline forecast. Curated layer should filter on IsForecasted=TRUE to isolate new information.

~23,202,590 rows | nightly (scripts.run_daily raw load)

| column | type | description |
|---|---|---|
| `API10` | character varying(32) |  |
| `Date` | date |  |
| `MonthsOnProduction` | smallint |  |
| `IsForecasted` | boolean |  |
| `Basin` | character varying(36) |  |
| `Subbasin` | character varying(36) |  |
| `OilPerDay` | double precision |  |
| `OilPerMonth` | integer |  |
| `CumulativeOil` | integer |  |
| `GasPerDay` | double precision |  |
| `GasPerMonth` | integer |  |
| `CumulativeGas` | integer |  |
| `WaterPerDay` | double precision |  |
| `WaterPerMonth` | integer |  |
| `CumulativeWater` | integer |  |
| `CreatedAt` | timestamp without time zone |  |
| `ModifiedAt` | timestamp without time zone |  |
| `DeletedAt` | timestamp without time zone |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi.WellDetails` (table)

Novi Insights extended per-well attributes (completion intensity, cums, EURs, spacing, peak rates), one row per API10. Nightly full TRUNCATE + COPY from the bulk TSV. Primary source behind curated.wells.

~92,818 rows | nightly (scripts.run_daily raw load)

| column | type | description |
|---|---|---|
| `API10` | character varying(32) |  |
| `IsHorizontalWell` | boolean |  |
| `Direction` | character varying(32) |  |
| `WellName` | character varying(64) |  |
| `WellType` | character varying(16) |  |
| `OriginalOperator` | character varying(64) |  |
| `CurrentOperator` | character varying(64) |  |
| `CurrentOperatorEntity` | character varying(64) |  |
| `LeaseID` | character varying |  |
| `Basin` | character varying(36) |  |
| `Subbasin` | character varying(36) |  |
| `State` | character varying(16) |  |
| `StateCode` | integer |  |
| `County` | character varying(32) |  |
| `CountyUnique` | character varying(32) |  |
| `CountyCode` | character varying(5) |  |
| `Field` | character varying(64) |  |
| `Formation` | character varying(64) |  |
| `ReportedFormation` | character varying(64) |  |
| `ReportedFormationRaw` | character varying(1024) |  |
| `GridFormation` | character varying(64) |  |
| `SHLLatitude` | double precision |  |
| `SHLLongitude` | double precision |  |
| `BHLLatitude` | double precision |  |
| `BHLLongitude` | double precision |  |
| `LPLatitude` | double precision |  |
| `LPLongitude` | double precision |  |
| `MPLatitude` | double precision |  |
| `MPLongitude` | double precision |  |
| `HasPLSSData` | boolean |  |
| `Meridian` | character varying(36) |  |
| `Township` | character varying(5) |  |
| `Range` | character varying(5) |  |
| `Section` | integer |  |
| `Quarter` | character varying(10) |  |
| `TXBlock` | character varying(36) |  |
| `TXSurvey` | character varying(36) |  |
| `TXAbstract` | character varying(36) |  |
| `TVD` | integer |  |
| `MD` | integer |  |
| `WellboreLocations` | integer |  |
| `PermitID` | character varying(32) |  |
| `PermitSubmitDate` | date |  |
| `PermitApprovedDate` | date |  |
| `PermitExpirationDate` | date |  |
| `SpudDate` | date |  |
| `DrillingEndDate` | date |  |
| `DrillingCompletionDate` | date |  |
| `FirstCompletionDate` | date |  |
| `FirstProductionDate` | date |  |
| `HasAccurateFirstProductionDate` | boolean |  |
| `FirstProductionDateFromState` | date |  |
| `FirstProductionYear` | integer |  |
| `LastReportedMonth` | date |  |
| `LastReportedMonthsOnProduction` | integer |  |
| `LastWellStatus` | character varying |  |
| `WellStatus` | text |  |
| `WellStatusReportedNormalized` | character varying(64) |  |
| `ReportedWellStatus` | character varying(64) |  |
| `PluggedDate` | date |  |
| `HasProductionSharing` | boolean |  |
| `LateralLength` | integer |  |
| `LateralLengthSource` | character varying |  |
| `FirstCompletionProppantMass` | integer |  |
| `FirstCompletionFluidVolume` | integer |  |
| `FirstCompletionStages` | integer |  |
| `Refrac` | integer |  |
| `FirstCompletionStages_AvgSpacing` | integer |  |
| `FirstCompletionProppantLbsPerGal` | real |  |
| `FirstCompletionProppantLbsPerFt` | integer |  |
| `SoakTimeDays` | integer |  |
| `Altitude` | integer |  |
| `Cum12MOil` | integer |  |
| `Cum12MGas` | integer |  |
| `Cum12MWater` | integer |  |
| `Cum12MBOE` | integer |  |
| `Cum24MOil` | integer |  |
| `Cum24MGas` | integer |  |
| `Cum24MWater` | integer |  |
| `Cum24MBOE` | integer |  |
| `CumLifeOil` | integer |  |
| `CumLifeGas` | integer |  |
| `CumLifeWater` | integer |  |
| `CumLifeBOE` | integer |  |
| `CumLifeGOR` | double precision |  |
| `EUR20YROil` | integer |  |
| `EUR20YRGas` | integer |  |
| `EUR20YRWater` | integer |  |
| `EUR20YRBOE` | integer |  |
| `EUR30YROil` | integer |  |
| `EUR30YRGas` | integer |  |
| `EUR30YRWater` | integer |  |
| `EUR30YRBOE` | integer |  |
| `EUR50YROil` | integer |  |
| `EUR50YRGas` | integer |  |
| `EUR50YRWater` | integer |  |
| `EUR50YRBOE` | integer |  |
| `PeakMonthOil` | integer |  |
| `PeakMonthGas` | integer |  |
| `PeakMonthWater` | integer |  |
| `PeakMonthBOE` | integer |  |
| `PeakMonthOilRate` | integer |  |
| `PeakMonthGasRate` | integer |  |
| `PeakMonthWaterRate` | integer |  |
| `PeakMonthBOERate` | integer |  |
| `SpacingIsChild` | boolean |  |
| `SpacingClosestWellXY` | double precision |  |
| `DirectionalSurveyIsPlanned` | boolean |  |
| `ReportedSlant` | character varying |  |
| `ReportedSlantNormalized` | character varying(36) |  |
| `SlantCalculated` | character varying(32) |  |
| `UpperPerforation` | bigint |  |
| `LowerPerforation` | bigint |  |
| `PerforationInterval` | bigint |  |
| `WellboreLateralLength` | integer |  |
| `CreatedAt` | timestamp without time zone |  |
| `ModifiedAt` | timestamp without time zone |  |
| `DeletedAt` | timestamp without time zone |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi.WellMonths` (table)

Novi Insights monthly production actuals, grain (API10, Year, Month). Nightly INCREMENTAL upsert of rows newer than the live max(ModifiedAt) watermark (full snapshot rewrite is too heavy for the instance); deletions caught by on-demand reconcile.

~4,915,883 rows | nightly (scripts.run_daily raw load)

| column | type | description |
|---|---|---|
| `API10` | character varying(32) |  |
| `Year` | integer |  |
| `Month` | integer |  |
| `Date` | date |  |
| `Operator` | character varying(64) |  |
| `OperatorEntity` | character varying(64) |  |
| `OilPerDay` | double precision |  |
| `OilPerMonth` | integer |  |
| `CumulativeOil` | integer |  |
| `GasPerDay` | double precision |  |
| `GasPerMonth` | integer |  |
| `CumulativeGas` | integer |  |
| `WaterPerDay` | double precision |  |
| `WaterPerMonth` | integer |  |
| `CumulativeWater` | integer |  |
| `ProducingDays` | integer |  |
| `CumulativeProducingDays` | integer |  |
| `MonthsOnProduction` | integer |  |
| `FlaredGasPerDay` | double precision |  |
| `FlaredGasPerMonth` | integer |  |
| `CumulativeFlaredGas` | integer |  |
| `Basin` | character varying(36) |  |
| `Subbasin` | character varying(36) |  |
| `IsOilFromProductionSharing` | boolean |  |
| `IsGasFromProductionSharing` | boolean |  |
| `IsGasFlaredFromProductionSharing` | boolean |  |
| `IsWaterFromProductionSharing` | boolean |  |
| `CreatedAt` | timestamp without time zone |  |
| `ModifiedAt` | timestamp without time zone |  |
| `DeletedAt` | timestamp without time zone |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi.WellSpacing` (table)

Novi Insights per-well spacing metrics (closest-well distance ft, wells in radius, avg of closest two), one row per API10. Nightly full TRUNCATE + COPY from the bulk TSV.

~59,784 rows | nightly (scripts.run_daily raw load)

| column | type | description |
|---|---|---|
| `API10` | character varying(32) |  |
| `Basin` | character varying(36) |  |
| `ClosestWellXY` | double precision |  |
| `WellsInRadius` | integer |  |
| `ClosestTwoAvgXY` | double precision |  |
| `WellsInRadiusAvgXY` | double precision |  |
| `IsChild` | boolean |  |
| `ParentCount` | integer |  |
| `ParentDaysOnline` | double precision |  |
| `LateralCloserXY` | double precision |  |
| `StaggerCloserTangent` | double precision |  |
| `StackCloserZ` | bigint |  |
| `BoundednessScore` | bigint |  |
| `CreatedAt` | timestamp without time zone |  |
| `ModifiedAt` | timestamp without time zone |  |
| `DeletedAt` | timestamp without time zone |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi.Wells` (table)

Novi Insights well header mirror, one row per wellbore keyed API10 (some synthetic Novi APIs). Nightly full TRUNCATE + COPY from the bulk TSV (etl/novi/load.py; sync forces no_diffs=True). Column names are quoted PascalCase as shipped.

~92,818 rows | nightly (scripts.run_daily raw load)

| column | type | description |
|---|---|---|
| `API10` | character varying(32) |  |
| `IsHorizontalWell` | boolean |  |
| `WellName` | character varying(64) |  |
| `WellType` | character varying(16) |  |
| `OriginalOperator` | character varying(64) |  |
| `CurrentOperator` | character varying(64) |  |
| `CurrentOperatorEntity` | character varying(64) |  |
| `LeaseID` | character varying |  |
| `Basin` | character varying(36) |  |
| `Subbasin` | character varying(36) |  |
| `State` | character varying(16) |  |
| `StateCode` | integer |  |
| `County` | character varying(32) |  |
| `CountyUnique` | character varying(32) |  |
| `CountyCode` | character varying(5) |  |
| `Field` | character varying(64) |  |
| `Formation` | character varying(64) |  |
| `ReportedFormation` | character varying(64) |  |
| `ReportedFormationRaw` | character varying(1024) |  |
| `GridFormation` | character varying(64) |  |
| `SHLLatitude` | double precision |  |
| `SHLLongitude` | double precision |  |
| `BHLLatitude` | double precision |  |
| `BHLLongitude` | double precision |  |
| `HasPLSSData` | boolean |  |
| `Meridian` | character varying(36) |  |
| `Township` | character varying(5) |  |
| `Range` | character varying(5) |  |
| `Section` | integer |  |
| `Quarter` | character varying(10) |  |
| `TXBlock` | character varying(36) |  |
| `TXSurvey` | character varying(36) |  |
| `TXAbstract` | character varying(36) |  |
| `TVD` | integer |  |
| `MD` | integer |  |
| `WellboreLocations` | integer |  |
| `SpudDate` | date |  |
| `DrillingEndDate` | date |  |
| `DrillingCompletionDate` | date |  |
| `FirstCompletionDate` | date |  |
| `FirstProductionDate` | date |  |
| `HasAccurateFirstProductionDate` | boolean |  |
| `LastReportedMonth` | date |  |
| `PluggedDate` | date |  |
| `HasProductionSharing` | boolean |  |
| `LateralLength` | integer |  |
| `LateralLengthSource` | character varying |  |
| `FirstCompletionProppantMass` | integer |  |
| `FirstCompletionFluidVolume` | integer |  |
| `FirstCompletionStages` | integer |  |
| `Refrac` | integer |  |
| `Altitude` | integer |  |
| `LastWellStatus` | character varying |  |
| `WellStatus` | text |  |
| `WellStatusReportedNormalized` | character varying(64) |  |
| `ReportedWellStatus` | character varying(64) |  |
| `DirectionalSurveyIsPlanned` | boolean |  |
| `ReportedSlant` | character varying |  |
| `ReportedSlantNormalized` | character varying(36) |  |
| `SlantCalculated` | character varying(32) |  |
| `PermitID` | character varying(32) |  |
| `PermitSubmitDate` | date |  |
| `PermitApprovedDate` | date |  |
| `PermitExpirationDate` | date |  |
| `UpperPerforation` | bigint |  |
| `LowerPerforation` | bigint |  |
| `PerforationInterval` | bigint |  |
| `WellboreLateralLength` | integer |  |
| `IsSyntheticApi` | boolean |  |
| `CreatedAt` | timestamp without time zone |  |
| `ModifiedAt` | timestamp without time zone |  |
| `DeletedAt` | timestamp without time zone |  |
| `ingested_at` | timestamp with time zone |  |

## Schema `raw_enverus`

### `raw_enverus.wells` (table)

Enverus DirectAccess v3 wells dataset mirror; one row per completion event, upsert key (wellid, completionid). Nightly incremental pull (updateddate cursor from meta.etl_log; etl/enverus/pull.py). Intake lowercases Enverus PascalCase keys and converts literal "NULL" strings to SQL NULL.

~634,899 rows | nightly (scripts.run_daily raw load)

| column | type | description |
|---|---|---|
| `api_uwi` | text |  |
| `api_uwi_12` | text |  |
| `api_uwi_12_unformatted` | text |  |
| `api_uwi_14` | text |  |
| `api_uwi_14_unformatted` | text |  |
| `api_uwi_unformatted` | text |  |
| `abstract` | text |  |
| `acidvolume_bbl` | real |  |
| `alternativewellname` | text |  |
| `averagestagespacing_ft` | real |  |
| `avgbreakdownpressure_psi` | integer |  |
| `avgclusterspacingperstage_ft` | integer |  |
| `avgclusterspacing_ft` | integer |  |
| `avgfluidpercluster_bbl` | integer |  |
| `avgfluidpershot_bbl` | integer |  |
| `avgfluidperstage_bbl` | integer |  |
| `avgfracgradient_psiperft` | double precision |  |
| `avgisip_psi` | integer |  |
| `avgmilltime_min` | integer |  |
| `avgportsleeveopeningpressure_psi` | integer |  |
| `avgproppantpercluster_lbs` | integer |  |
| `avgproppantpershot_lbs` | integer |  |
| `avgproppantperstage_lbs` | integer |  |
| `avgshotspercluster` | integer |  |
| `avgshotsperft` | integer |  |
| `avgtreatmentpressure_psi` | integer |  |
| `avgtreatmentrate_bblpermin` | double precision |  |
| `biocide_lbs` | real |  |
| `block` | text |  |
| `bottomholeage` | text |  |
| `bottomholeformationname` | text |  |
| `bottomholelithology` | text |  |
| `bottom_hole_temp_degf` | double precision |  |
| `breaker_lbs` | real |  |
| `buffer_lbs` | real |  |
| `casingpressure_psi` | real |  |
| `chokesize_64in` | integer |  |
| `claycontrol_lbs` | real |  |
| `clustersper1000ft` | integer |  |
| `clustersperstage` | integer |  |
| `completiondate` | timestamp without time zone |  |
| `completiondesign` | text |  |
| `completionid` | bigint |  |
| `completionnumber` | integer |  |
| `completiontime_days` | integer |  |
| `contract` | text |  |
| `coordinatequality` | text |  |
| `coordinatesource` | text |  |
| `country` | text |  |
| `county` | text |  |
| `crosslinker_lbs` | real |  |
| `cumgas_mcf` | real |  |
| `cumgas_mcfper1000ft` | real |  |
| `cumoil_bbl` | real |  |
| `cumoil_bblper1000ft` | real |  |
| `cumprod_boe` | real |  |
| `cumprod_boeper1000ft` | real |  |
| `cumprod_mcfe` | real |  |
| `cumprod_mcfeper1000ft` | real |  |
| `cumwater_bbl` | real |  |
| `cumulativesor` | real |  |
| `deleteddate` | timestamp without time zone |  |
| `developmentflag` | integer |  |
| `discovermagnitudecomments` | text |  |
| `discoverytype` | text |  |
| `district` | text |  |
| `diverter_lbs` | real |  |
| `drillingenddate` | timestamp without time zone |  |
| `drillingtddate` | timestamp without time zone |  |
| `drillingtddatequalifier` | text |  |
| `envbasin` | text |  |
| `envcompinserteddate` | timestamp without time zone |  |
| `envelevationglsource` | text |  |
| `envelevationgl_ft` | double precision |  |
| `envelevationkbsource` | text |  |
| `envelevationkb_ft` | double precision |  |
| `envfluidtype` | text |  |
| `envfracjobtype` | text |  |
| `envinterval` | text |  |
| `envintervalsource` | text |  |
| `envoperator` | text |  |
| `envpeergroup` | text |  |
| `envplay` | text |  |
| `envprodwelltype` | text |  |
| `envproducingmethod` | text |  |
| `envproppantbrand` | text |  |
| `envproppanttype` | text |  |
| `envregion` | text |  |
| `envstockexchange` | text |  |
| `envsubplay` | text |  |
| `envticker` | text |  |
| `envwellgrouping` | text |  |
| `envwellserviceprovider` | text |  |
| `envwellstatus` | text |  |
| `envwelltype` | text |  |
| `envwellboretype` | text |  |
| `elevationgl_ft` | double precision |  |
| `elevationkb_ft` | double precision |  |
| `enddatequalifier` | text |  |
| `energizer_lbs` | real |  |
| `environment` | text |  |
| `explorationflag` | integer |  |
| `field` | text |  |
| `first12monthflaredgas_mcf` | real |  |
| `first12monthgas_mcf` | real |  |
| `first12monthgas_mcfper1000ft` | real |  |
| `first12monthoil_bbl` | real |  |
| `first12monthoil_bblper1000ft` | real |  |
| `first12monthprod_boe` | real |  |
| `first12monthprod_boeper1000ft` | real |  |
| `first12monthprod_mcfe` | real |  |
| `first12monthprod_mcfeper1000ft` | real |  |
| `first12monthwater_bbl` | real |  |
| `first36monthgas_mcf` | double precision |  |
| `first36monthgas_mcfper1000ft` | double precision |  |
| `first36monthoil_bbl` | double precision |  |
| `first36monthoil_bblper1000ft` | double precision |  |
| `first36monthprod_boe` | double precision |  |
| `first36monthprod_boeper1000ft` | double precision |  |
| `first36monthprod_mcfe` | double precision |  |
| `first36monthprod_mcfeper1000ft` | double precision |  |
| `first36monthwaterproductionbblper1000ft` | double precision |  |
| `first36monthwater_bbl` | double precision |  |
| `first3monthflaredgas_mcf` | real |  |
| `first3monthgas_mcf` | real |  |
| `first3monthgas_mcfper1000ft` | real |  |
| `first3monthoil_bbl` | real |  |
| `first3monthoil_bblper1000ft` | real |  |
| `first3monthprod_boe` | real |  |
| `first3monthprod_boeper1000ft` | real |  |
| `first3monthprod_mcfe` | real |  |
| `first3monthprod_mcfeper1000ft` | real |  |
| `first3monthwater_bbl` | real |  |
| `first6monthflaredgas_mcf` | real |  |
| `first6monthgas_mcf` | real |  |
| `first6monthgas_mcfper1000ft` | real |  |
| `first6monthoil_bbl` | real |  |
| `first6monthoil_bblper1000ft` | real |  |
| `first6monthprod_boe` | real |  |
| `first6monthprod_boeper1000ft` | real |  |
| `first6monthprod_mcfe` | real |  |
| `first6monthprod_mcfeper1000ft` | real |  |
| `first6monthwater_bbl` | real |  |
| `first9monthflaredgas_mcf` | real |  |
| `first9monthgas_mcf` | real |  |
| `first9monthgas_mcfper1000ft` | real |  |
| `first9monthoil_bbl` | real |  |
| `first9monthoil_bblper1000ft` | real |  |
| `first9monthprod_boe` | real |  |
| `first9monthprod_boeper1000ft` | real |  |
| `first9monthprod_mcfe` | real |  |
| `first9monthprod_mcfeper1000ft` | real |  |
| `first9monthwater_bbl` | real |  |
| `firstday` | timestamp without time zone |  |
| `firstproddate` | timestamp without time zone |  |
| `firstprodmonth` | text |  |
| `firstprodquarter` | text |  |
| `firstprodyear` | text |  |
| `flaredgasratio` | real |  |
| `flowingtubingpressure_psi` | real |  |
| `fluidintensity_bblperft` | real |  |
| `formation` | text |  |
| `fracrigonsitedate` | timestamp without time zone |  |
| `fracrigreleasedate` | timestamp without time zone |  |
| `fracstages` | integer |  |
| `frictionreducer_lbs` | real |  |
| `gor_scfperbbl` | real |  |
| `gasgravity_sg` | double precision |  |
| `gastestrate_mcfperday` | real |  |
| `gastestrate_mcfperdayper1000ft` | real |  |
| `gellingagent_lbs` | real |  |
| `generalcomments` | text |  |
| `geombhl_point` | text |  |
| `geomshl_point` | text |  |
| `governmentwellid` | text |  |
| `initialoperator` | text |  |
| `ironcontrol_lbs` | real |  |
| `last12monthgasproduction_mcf` | real |  |
| `last12monthoilproduction_bbl` | real |  |
| `last12monthproduction_boe` | real |  |
| `last12monthwaterproduction_bbl` | real |  |
| `last3monthisor` | real |  |
| `lastmonthflaredgas_mcf` | real |  |
| `lastmonthgasproduction_mcf` | double precision |  |
| `lastmonthliquidsproduction_bbl` | double precision |  |
| `lastmonthwaterproduction_bbl` | double precision |  |
| `lastproducingmonth` | timestamp without time zone |  |
| `laterallength_ft` | real |  |
| `lateralline` | text |  |
| `latitude` | double precision |  |
| `latitude_bh` | double precision |  |
| `lease` | text |  |
| `leasename` | text |  |
| `longitude` | double precision |  |
| `longitude_bh` | double precision |  |
| `lowerperf_ft` | integer |  |
| `md_ft` | double precision |  |
| `monthstopeakproduction` | bigint |  |
| `numberofstrings` | integer |  |
| `objectiveage` | text |  |
| `objectivelithology` | text |  |
| `offconfidentialdate` | timestamp without time zone |  |
| `oilgravity_api` | double precision |  |
| `oilprodpriortest_bbl` | double precision |  |
| `oiltestmethodname` | text |  |
| `oiltestrate_bblperday` | real |  |
| `oiltestrate_bblperdayper1000ft` | real |  |
| `onconfidential` | text |  |
| `onoffshore` | text |  |
| `peakflaredgas_mcf` | real |  |
| `peakgas_mcf` | real |  |
| `peakgas_mcfper1000ft` | real |  |
| `peakoil_bbl` | real |  |
| `peakoil_bblper1000ft` | real |  |
| `peakprod_boe` | real |  |
| `peakprod_boeper1000ft` | real |  |
| `peakprod_mcfe` | real |  |
| `peakprod_mcfeper1000ft` | real |  |
| `peakproductiondate` | timestamp without time zone |  |
| `peakwater_bbl` | real |  |
| `perfinterval_ft` | integer |  |
| `permitapproveddate` | timestamp without time zone |  |
| `permitsubmitteddate` | timestamp without time zone |  |
| `permittospud_days` | bigint |  |
| `platform` | text |  |
| `plugdate` | timestamp without time zone |  |
| `plugbackmeasureddepth_ft` | integer |  |
| `plugbacktrueverticaldepth_ft` | integer |  |
| `proppantintensity_lbsperft` | real |  |
| `proppantloading_lbspergal` | real |  |
| `proppant_lbs` | double precision |  |
| `range` | text |  |
| `rawoperator` | text |  |
| `rawvintage` | integer |  |
| `resourcemagnitude` | text |  |
| `resourcemagnitudereviewdate` | timestamp without time zone |  |
| `resourcesourcequalifier` | text |  |
| `resourcevolumegasbcf` | text |  |
| `resourcevolumeliquidsmmb` | text |  |
| `rigreleasedate` | timestamp without time zone |  |
| `scaleinhibitor_lbs` | real |  |
| `section` | text |  |
| `section_township_range` | text |  |
| `shotsper1000ft` | integer |  |
| `shotsperstage` | integer |  |
| `shutinpressure_psi` | real |  |
| `soaktime_days` | bigint |  |
| `spuddate` | timestamp without time zone |  |
| `spuddatequalifier` | text |  |
| `spuddatesource` | text |  |
| `spudtocompletion_days` | bigint |  |
| `spudtorigrelease_days` | bigint |  |
| `spudtosales_days` | bigint |  |
| `statefilenumber` | text |  |
| `stateprovince` | text |  |
| `statewelltype` | text |  |
| `stimulatedstages` | integer |  |
| `surfacelatlongsource` | text |  |
| `surfactant_lbs` | real |  |
| `tvd_ft` | double precision |  |
| `testcomments` | text |  |
| `testdate` | timestamp without time zone |  |
| `testrate_boeperday` | real |  |
| `testrate_boeperdayper1000ft` | real |  |
| `testrate_mcfeperday` | real |  |
| `testrate_mcfeperdayper1000ft` | real |  |
| `testwhliquids_pct` | real |  |
| `totalclusters` | integer |  |
| `totalfluidpumped_bbl` | double precision |  |
| `totalproducingmonths` | bigint |  |
| `totalshots` | integer |  |
| `totalwaterpumped_gal` | real |  |
| `township` | text |  |
| `trajectory` | text |  |
| `unconventionalflag` | integer |  |
| `unconventionaltype` | text |  |
| `unit_name` | text |  |
| `updateddate` | timestamp without time zone |  |
| `upperperf_ft` | integer |  |
| `vintage` | text |  |
| `whliquids_pct` | real |  |
| `waterdepth` | double precision |  |
| `waterintensity_galperft` | real |  |
| `watersaturation_pct` | double precision |  |
| `watertestrate_bblperday` | real |  |
| `watertestrate_bblperdayper1000ft` | real |  |
| `wellid` | bigint |  |
| `wellname` | text |  |
| `wellnumber` | text |  |
| `wellpaddirection` | text |  |
| `wellpadid` | text |  |
| `wellsymbols` | text |  |
| `wellboreid` | bigint |  |
| `ingested_at` | timestamp with time zone |  |

## Schema `raw_intel`

### `raw_intel.arps_forecast` (table)

Snowflake share ARPS_FORECAST: segmented Arps decline parameters (b, NOMINAL per-year Di, secant/tangent effective declines, segment rates/days), planned wells only as of 2025Q3. Key (well_ref [PW-{id}], stream, segment_number, report_name).

~1,835,317 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_ref` | text |  |
| `inventory_class` | text |  |
| `stream` | text |  |
| `segment_number` | integer |  |
| `kind` | text |  |
| `segment_curve_type` | text |  |
| `b_factor` | double precision |  |
| `nominal_decline_rate` | double precision |  |
| `effective_decline_rate_secant` | double precision |  |
| `effective_decline_rate_tangent` | double precision |  |
| `segment_start_rate` | double precision |  |
| `segment_end_rate` | double precision |  |
| `terminal_transition_day` | integer |  |
| `day_start` | integer |  |
| `day_stop` | integer |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `created_at` | timestamp without time zone |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.basin` (table)

Snowflake share BASIN dimension (Permian -> Delaware/Midland subbasins), keyed basin_id. Tiny global dim; full-replace on the quarterly intel load.

~24 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `basin_id` | bigint |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.econ_price_assumption` (table)

Flat price decks behind the Novi economics (WTI/HH/NGL prices + differentials), key (price_deck_id [content hash, repeats across reports], report_name). Quarterly slice reload.

~2 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `price_deck_id` | text |  |
| `name` | text |  |
| `detail` | text |  |
| `effective_date` | date |  |
| `currency` | text |  |
| `oil_price` | double precision |  |
| `gas_price` | double precision |  |
| `ngl_price` | double precision |  |
| `oil_price_differential` | double precision |  |
| `gas_price_differential` | double precision |  |
| `oil_price_node` | text |  |
| `gas_price_node` | text |  |
| `oil_price_units` | text |  |
| `gas_price_units` | text |  |
| `ngl_price_units` | text |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.operator` (table)

Snowflake share OPERATOR dimension (reported + normalized names, contact fields), keyed operator_id. Global dim; full-replace on the quarterly intel load.

~40,535 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `operator_id` | bigint |  |
| `reporting_state` | text |  |
| `external_operator_id` | text |  |
| `name_reported` | text |  |
| `name_normalized` | text |  |
| `address` | text |  |
| `address2` | text |  |
| `zip` | text |  |
| `city` | text |  |
| `state` | text |  |
| `country` | text |  |
| `phone` | text |  |
| `emergency_phone` | text |  |
| `email` | text |  |
| `website` | text |  |
| `comments` | text |  |
| `source_id` | bigint |  |
| `verified` | boolean |  |
| `created_at` | timestamp with time zone |  |
| `updated_at` | timestamp with time zone |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.pad` (table)

Snowflake share PAD dimension, key (pad_id, report_name). latitude/longitude unpopulated as of 2025Q3. Loader adds basin_slug/report_version; quarterly slice reload.

~4,585 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `pad_id` | bigint |  |
| `name` | text |  |
| `latitude` | double precision |  |
| `longitude` | double precision |  |
| `crs` | text |  |
| `operator_name` | text |  |
| `surface_location_id` | bigint |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.planned_well` (table)

Snowflake share PLANNED_WELL entity: undrilled locations, inventory_class BASE_CASE (PUD) or EMERGING (RES), key (planned_well_id, report_name). name = the legacy sticks unique_id for BASE_CASE. planned_til_date entirely NULL as of 2025Q3. Quarterly slice reload.

~203,886 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `planned_well_id` | bigint |  |
| `name` | text |  |
| `operator_id` | bigint |  |
| `basin_id` | bigint |  |
| `county` | text |  |
| `pad_id` | bigint |  |
| `drilling_template_id` | text |  |
| `completion_template_id` | text |  |
| `target_formation` | text |  |
| `lateral_length` | double precision |  |
| `azimuth_deg` | double precision |  |
| `status` | text |  |
| `inventory_class` | text |  |
| `planned_spud_date` | date |  |
| `planned_til_date` | date |  |
| `materialized_well_id` | bigint |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.production_forecast` (table)

Snowflake share PRODUCTION_FORECAST: monthly P50 stream forecast for planned wells, 30-day forecast_day steps, ~73M rows (no ingested_at by design). Loaded via the separate --forecast gate after the legacy 7.7 GB table is dropped (disk headroom). Condensate columns all-NULL for Permian.

~73,197,064 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `production_forecast_id` | bigint |  |
| `well_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `period_granularity` | text |  |
| `forecast_day` | integer |  |
| `year` | integer |  |
| `month` | integer |  |
| `scenario` | text |  |
| `oil_per_day` | double precision |  |
| `cumulative_oil` | double precision |  |
| `gas_per_day` | double precision |  |
| `cumulative_gas` | double precision |  |
| `ngl_per_day` | double precision |  |
| `cumulative_ngl` | double precision |  |
| `water_per_day` | double precision |  |
| `cumulative_water` | double precision |  |
| `condensate_per_day` | double precision |  |
| `cumulative_condensate` | double precision |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |

### `raw_intel.source` (table)

Snowflake share SOURCE dimension: one row per source file/collection. collection (basin_research__<Basin>__<yyyyQq>) feeds the nightly new-report detection (etl/intel_sf/detect.py -> meta.intel_report_watermark). Global dim: full-replace load.

~54 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `source_id` | bigint |  |
| `system` | text |  |
| `collection` | text |  |
| `source_file` | text |  |
| `source_path` | text |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.stick_id_map` (table)

Append-only well_ref -> stable positive stick_id registry; survives DDL re-runs and quarterly reloads. Do NOT drop or truncate: downstream matviews and erebor selections key on stick_id.

~251,902 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_ref` | text |  |
| `stick_id` | bigint |  |
| `first_seen` | timestamp with time zone |  |

### `raw_intel.surface_location` (table)

Snowflake share SURFACE_LOCATION: surface-hole lat/lon + legal description (block/township, section, TX survey/abstract) per well or planned well. Key (surface_location_id, report_name). Quarterly slice reload.

~251,902 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `surface_location_id` | bigint |  |
| `well_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `latitude` | double precision |  |
| `longitude` | double precision |  |
| `crs` | text |  |
| `legal_description` | text |  |
| `block_township` | text |  |
| `section` | text |  |
| `tx_survey` | text |  |
| `abstract_lot` | text |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.well` (table)

Snowflake share WELL entity: existing (PDP) wells, key (well_id, report_name). uwi_api is a 10-digit API on every row -- the api10 crosswalk to curated.wells. Quarterly slice reload.

~48,016 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_id` | bigint |  |
| `well_name` | text |  |
| `uwi_api` | text |  |
| `operator_id` | bigint |  |
| `lease_name` | text |  |
| `basin_id` | bigint |  |
| `county` | text |  |
| `well_type` | text |  |
| `state` | text |  |
| `field_name` | text |  |
| `offshore_region` | text |  |
| `country` | text |  |
| `status_reported` | text |  |
| `status_reported_normalized` | text |  |
| `status` | text |  |
| `first_production_date` | date |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.well_completion` (table)

Snowflake share WELL_COMPLETION: completion design -- proppant_loading lb/ft, fluid_loading gal/ft, masses/volumes. Planned wells only as of 2025Q3 (zero PDP rows; gap raised with Novi). Key (well_completion_id, report_name).

~203,886 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_completion_id` | bigint |  |
| `well_id` | bigint |  |
| `wellbore_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `completion_sequence` | integer |  |
| `completion_state` | text |  |
| `completion_start_date` | date |  |
| `completion_end_date` | date |  |
| `proppant_mass` | double precision |  |
| `fluid_volume` | double precision |  |
| `proppant_loading` | double precision |  |
| `fluid_loading` | double precision |  |
| `lateral_length_ft` | double precision |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.well_cost_summary` (table)

Snowflake share WELL_COST_SUMMARY: Novi D&C and DCET cost totals (USD) and per-lateral-ft normalizations (USD/ft). Vendor screen inputs. Key (well_cost_summary_id, report_name).

~251,902 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_cost_summary_id` | bigint |  |
| `well_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `currency` | text |  |
| `total_dc_cost` | numeric(28,7) |  |
| `total_dcet_cost` | numeric(28,7) |  |
| `normalized_dc_cost_per_ft` | numeric(28,7) |  |
| `normalized_dcet_cost_per_ft` | numeric(28,7) |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.well_economics_summary` (table)

Snowflake share WELL_ECONOMICS_SUMMARY: Novi NPV/PV (5-25%), IRR, paybacks, breakevens, 30-yr EURs + IPs per well. irr unit is inconsistent by slice (fraction vs fraction/100; raised with Novi) -- normalized downstream in curated.intel_locations. Vendor screen, not authoritative economics. Key (well_economics_summary_id, report_name).

~251,902 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_economics_summary_id` | bigint |  |
| `well_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `npv5` | numeric(28,7) |  |
| `npv10` | numeric(28,7) |  |
| `npv15` | numeric(28,7) |  |
| `npv20` | numeric(28,7) |  |
| `npv25` | numeric(28,7) |  |
| `pv5` | numeric(28,7) |  |
| `pv10` | numeric(28,7) |  |
| `pv15` | numeric(28,7) |  |
| `pv20` | numeric(28,7) |  |
| `pv25` | numeric(28,7) |  |
| `npv` | numeric(28,7) |  |
| `irr` | double precision |  |
| `pvi` | double precision |  |
| `payback_months` | integer |  |
| `double_payback_months` | integer |  |
| `breakeven_1yr` | double precision |  |
| `breakeven_2yr` | double precision |  |
| `breakeven_3yr` | double precision |  |
| `npv5_breakeven` | double precision |  |
| `npv10_breakeven` | double precision |  |
| `npv15_breakeven` | double precision |  |
| `npv20_breakeven` | double precision |  |
| `npv25_breakeven` | double precision |  |
| `lifetime_months` | integer |  |
| `eur_oil_30yr` | double precision |  |
| `eur_gas_30yr` | double precision |  |
| `eur_ngl_30yr` | double precision |  |
| `eur_dry_gas_30yr` | double precision |  |
| `eur_water_30yr` | double precision |  |
| `ip_oil` | double precision |  |
| `ip_ngl` | double precision |  |
| `ip_gas` | double precision |  |
| `ip_dry_gas` | double precision |  |
| `ip_water` | double precision |  |
| `ngl_yield` | double precision |  |
| `ngl_shrink` | double precision |  |
| `stream` | text |  |
| `currency` | text |  |
| `price_deck_id` | text |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.well_master` (table)

Snowflake share WELL_MASTER: the spine uniting PDP + BASE_CASE + EMERGING, grain (well_ref, report_name, inventory_class); well_ref = uwi_api (PDP) or PW-{id} (planned). geometry_wkt landed as text; geom populated post-COPY. Feeds curated.intel_locations. Quarterly slice reload.

~251,902 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_ref` | text |  |
| `inventory_class` | text |  |
| `uwi_api` | text |  |
| `name` | text |  |
| `wellbore_type` | text |  |
| `status` | text |  |
| `spud_date` | date |  |
| `td_date` | date |  |
| `pa_date` | date |  |
| `first_production_date` | date |  |
| `planned_til_date` | date |  |
| `lateral_length` | double precision |  |
| `azimuth_deg` | double precision |  |
| `tvd_td` | double precision |  |
| `md_td` | double precision |  |
| `formation` | text |  |
| `latitude` | double precision |  |
| `longitude` | double precision |  |
| `midpoint_latitude` | double precision |  |
| `midpoint_longitude` | double precision |  |
| `bottom_hole_latitude` | double precision |  |
| `bottom_hole_longitude` | double precision |  |
| `geometry_wkt` | text |  |
| `operator_name` | text |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `county` | text |  |
| `pad_name` | text |  |
| `report_name` | text |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |
| `geom` | geometry(Geometry,4326) |  |

### `raw_intel.well_ml_score` (table)

Snowflake share WELL_ML_SCORE: Novi ML spacing / prior-depletion / completion scores + tiers (Tier-1..Tier-4) per well x stream. Scores are sensitivity values, NOT footage. Replaces raw_novi_intel.pud_attrs; covers PDP too. Key (well_ml_score_id, report_name).

~174,265 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_ml_score_id` | bigint |  |
| `well_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `external_id` | text |  |
| `external_id_system` | text |  |
| `well_class` | text |  |
| `stream` | text |  |
| `operator_id` | bigint |  |
| `operator_name` | text |  |
| `formation` | text |  |
| `spacing_score` | double precision |  |
| `spacing_tier` | text |  |
| `prior_depletion_score` | double precision |  |
| `prior_depletion_tier` | text |  |
| `completion_score` | double precision |  |
| `completion_tier` | text |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.well_rock_quality` (table)

Snowflake share WELL_ROCK_QUALITY: Novi ML rock-quality score + tier per well x stream. Key (well_rock_quality_id, report_name). Quarterly slice reload.

~178,337 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `well_rock_quality_id` | bigint |  |
| `well_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `trajectory_id` | bigint |  |
| `external_id` | text |  |
| `external_id_system` | text |  |
| `well_class` | text |  |
| `stream` | text |  |
| `operator_id` | bigint |  |
| `operator_name` | text |  |
| `formation` | text |  |
| `rock_quality_score` | double precision |  |
| `rock_quality_tier` | text |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.wellbore` (table)

Snowflake share WELLBORE entity: depths (tvd_td/md_td ft), lateral length ft, heel/mid/BH lat-lon, formation fields; exactly one of well_id / planned_well_id set. Key (wellbore_id, report_name). Quarterly slice reload.

~251,902 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `wellbore_id` | bigint |  |
| `well_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `wellbore_name` | text |  |
| `wellbore_type` | text |  |
| `tvd_td` | double precision |  |
| `md_td` | double precision |  |
| `lateral_length` | double precision |  |
| `azimuth_deg` | double precision |  |
| `midpoint_latitude` | double precision |  |
| `midpoint_longitude` | double precision |  |
| `bottom_hole_latitude` | double precision |  |
| `bottom_hole_longitude` | double precision |  |
| `heelpoint_latitude` | double precision |  |
| `heelpoint_longitude` | double precision |  |
| `formation_reported` | text |  |
| `formation_reported_normalized` | text |  |
| `formation` | text |  |
| `formation_calculated` | text |  |
| `sequence_number` | integer |  |
| `status` | text |  |
| `spud_date` | date |  |
| `td_date` | date |  |
| `pa_date` | date |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_intel.wellbore_trajectory` (table)

Snowflake share lateral trajectories: geometry_wkt (LINESTRING, EPSG:4326) landed as text, geom populated post-COPY per slice (share GEO columns are not mirrored). Key (trajectory_id, report_name). Quarterly slice reload.

~251,902 rows | quarterly (scripts.load_intel_sf, Novi Snowflake share)

| column | type | description |
|---|---|---|
| `trajectory_id` | bigint |  |
| `wellbore_id` | bigint |  |
| `planned_well_id` | bigint |  |
| `geometry_wkt` | text |  |
| `crs` | text |  |
| `source_id` | bigint |  |
| `created_at` | timestamp without time zone |  |
| `updated_at` | timestamp without time zone |  |
| `basin` | text |  |
| `subbasin` | text |  |
| `report_name` | text |  |
| `basin_slug` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |
| `geom` | geometry(Geometry,4326) |  |

## Schema `raw_novi_intel`

### `raw_novi_intel.analytics` (table)

LEGACY: Novi Analytics File CSV (well geometry endpoints, TVD, completion loading) keyed by well_name, tagged (basin, report_version). Superseded by raw_intel.wellbore / well_completion; slated for retirement.

~205,751 rows | static (legacy file drop; being retired)

| column | type | description |
|---|---|---|
| `well_name` | text |  |
| `tvd` | double precision |  |
| `midpoint_lat` | double precision |  |
| `midpoint_lon` | double precision |  |
| `bh_lat` | double precision |  |
| `bh_lon` | double precision |  |
| `heel_lat` | double precision |  |
| `heel_lon` | double precision |  |
| `target_formation` | text |  |
| `lateral_length` | double precision |  |
| `proppant_loading` | double precision |  |
| `fluid_loading` | double precision |  |
| `county` | text |  |
| `subbasin` | text |  |
| `proppant_mass` | double precision |  |
| `fluid_volume` | double precision |  |
| `md` | double precision |  |
| `pad_name` | text |  |
| `basin` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi_intel.arps` (table)

LEGACY: segmented Arps decline-parameter CSV from the file drop, key (novi_wellname, production_stream, segment); d_nom is NOMINAL per-year. Superseded by raw_intel.arps_forecast; slated for retirement.

~1,851,759 rows | static (legacy file drop; being retired)

| column | type | description |
|---|---|---|
| `job_name` | text |  |
| `well_inventory_name` | text |  |
| `planned_well_id` | text |  |
| `production_stream` | text |  |
| `segment` | integer |  |
| `segment_curve_type` | text |  |
| `b` | double precision |  |
| `d_nom` | double precision |  |
| `d_eff_secant` | double precision |  |
| `d_eff_tangent` | double precision |  |
| `q_start` | double precision |  |
| `q_stop` | double precision |  |
| `terminal_day` | double precision |  |
| `day_start` | double precision |  |
| `day_stop` | double precision |  |
| `novi_wellname` | text |  |
| `basin` | text |  |
| `report_version` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi_intel.basin_outline` (table)

Novi-supplied basin outline polygons from the file drop, tagged (basin, report_version). STILL IN USE as a map overlay: the Snowflake share has no equivalent geometry.

~2 rows | static (legacy file drop; being retired)

| column | type | description |
|---|---|---|
| `outline_id` | bigint |  |
| `basin` | text |  |
| `report_version` | text |  |
| `attrs` | jsonb |  |
| `geom` | geometry(Geometry,4326) |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi_intel.land_grid` (table)

Novi-supplied land grid polygons (raw DBF attributes in JSONB) from the file drop, tagged (basin, report_version). STILL IN USE as a map overlay: the Snowflake share has no equivalent geometry.

~42,668 rows | static (legacy file drop; being retired)

| column | type | description |
|---|---|---|
| `grid_id` | bigint |  |
| `basin` | text |  |
| `report_version` | text |  |
| `attrs` | jsonb |  |
| `geom` | geometry(Geometry,4326) |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi_intel.pads` (table)

Novi DSU pad polygons + pad-level NPV rollup from the quarterly file drop, tagged (basin, report_version). STILL IN USE for display: the Snowflake share has no pad geometry as of 2025Q3.

~9,040 rows | static (legacy file drop; being retired)

| column | type | description |
|---|---|---|
| `pad_id` | bigint |  |
| `basin` | text |  |
| `report_version` | text |  |
| `pad_name` | text |  |
| `npv5` | double precision |  |
| `npv10` | double precision |  |
| `npv15` | double precision |  |
| `npv20` | double precision |  |
| `npv25` | double precision |  |
| `geom` | geometry(Geometry,4326) |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi_intel.pud_attrs` (table)

LEGACY: PUD ML tier attributes (spacing/depletion/completion/rock-quality scores + Tier-1..4 labels) from the Other_ML / Rock_Quality shapefiles, key (basin, report_version, unique_id). Scores are sensitivities, NOT footage. Superseded by raw_intel.well_ml_score / well_rock_quality.

~131,465 rows | static (legacy file drop; being retired)

| column | type | description |
|---|---|---|
| `basin` | text |  |
| `report_version` | text |  |
| `unique_id` | text |  |
| `spacing_s` | double precision |  |
| `spacing_t` | text |  |
| `deplet_s` | double precision |  |
| `deplet_t` | text |  |
| `complet_s` | double precision |  |
| `complet_t` | text |  |
| `rqs` | double precision |  |
| `rqt` | text |  |
| `ingested_at` | timestamp with time zone |  |

### `raw_novi_intel.sticks` (table)

LEGACY: union of the PDP/PUD/Resource economic stick shapefiles from the quarterly file drop, one row per lateral tagged (basin, report_version); BIGSERIAL stick_id renumbers per reload (why raw_intel.stick_id_map replaced it). Superseded by raw_intel.well_master + well_economics_summary; retained for reconciliation QC until retirement.

~248,618 rows | static (legacy file drop; being retired)

| column | type | description |
|---|---|---|
| `stick_id` | bigint |  |
| `basin` | text |  |
| `report_version` | text |  |
| `src_layer` | text |  |
| `unique_id` | text |  |
| `api10` | text |  |
| `category` | text |  |
| `phase` | text |  |
| `operator` | text |  |
| `formation` | text |  |
| `county` | text |  |
| `pad_name` | text |  |
| `fp_year` | integer |  |
| `tvd` | double precision |  |
| `md` | double precision |  |
| `ll_ft` | double precision |  |
| `prop_load` | double precision |  |
| `oil_eur` | double precision |  |
| `gas_eur` | double precision |  |
| `dgas_eur` | double precision |  |
| `ngl_eur` | double precision |  |
| `water_eur` | double precision |  |
| `oil_ip` | double precision |  |
| `gas_ip` | double precision |  |
| `dgas_ip` | double precision |  |
| `ngl_ip` | double precision |  |
| `water_ip` | double precision |  |
| `ngl_yield` | double precision |  |
| `ngl_shrink` | double precision |  |
| `npv5` | double precision |  |
| `npv10` | double precision |  |
| `npv15` | double precision |  |
| `npv20` | double precision |  |
| `npv25` | double precision |  |
| `pv5` | double precision |  |
| `pv10` | double precision |  |
| `pv15` | double precision |  |
| `pv20` | double precision |  |
| `pv25` | double precision |  |
| `npv5_be` | double precision |  |
| `npv10_be` | double precision |  |
| `npv15_be` | double precision |  |
| `npv20_be` | double precision |  |
| `npv25_be` | double precision |  |
| `be_1yr` | double precision |  |
| `be_2yr` | double precision |  |
| `be_3yr` | double precision |  |
| `irr_pct` | double precision |  |
| `pp_months` | double precision |  |
| `ttpt` | double precision |  |
| `dc_cost` | double precision |  |
| `dcet_cost` | double precision |  |
| `norm_dc` | double precision |  |
| `norm_dcet` | double precision |  |
| `wti_price` | double precision |  |
| `hh_price` | double precision |  |
| `ngl_price` | double precision |  |
| `wti_diff` | double precision |  |
| `hh_diff` | double precision |  |
| `has_econ` | text |  |
| `conf_int` | double precision |  |
| `geom` | geometry(Geometry,4326) |  |
| `ingested_at` | timestamp with time zone |  |

## Schema `ref`

### `ref.formation_crosswalk` (table)

Maps raw upstream formation strings (Novi formation names or Enverus ENVInterval strings) to Blue Ox canonical nomenclature codes, per basin. Seeded from seeds/formation_crosswalk.csv. Joined by curated.wells on (basin, raw_value) to populate formation_blueox.

~170 rows | static reference

| column | type | description |
|---|---|---|
| `basin` | text |  |
| `source` | text |  |
| `raw_value` | text |  |
| `canonical_code` | text |  |
| `notes` | text |  |

## Schema `curated`

### `curated.bench_reference` (materialized view)

Candidate pool for TVD-aware sub-bench inference: curated laterals in the splitting benches (Delaware AVA/WCA/WCB, Midland WCB; ~30k rows), one row per api10, pre-joined to formation_blueox and GiST-indexed on geom. Feeds curated.intel_formation_blueox (sql/19). Not in the nightly etl.refresh list - refresh manually alongside curated.formation_blueox / on the quarterly intel rebuild.

~37,032 rows | on demand | reads: `curated.formation_blueox`, `curated.wells`

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | Universal well key (Novi 10-digit API); unique index supports REFRESH CONCURRENTLY. |
| `geom` | geometry | Wellstick LINESTRING (4326) from curated.wells; GiST-indexed as the <-> KNN driver for sub-bench inference. |
| `tvd` | integer | True vertical depth, ft (curated.wells.tvd_ft); NOT NULL by filter - the depth discriminator between stacked benches. |
| `basin` | text | Blue Ox basin token (delaware or midland) from curated.formation_blueox. |
| `bench` | text | Blue Ox sub-bench code: one of WCA_1, WCA_2, WCB_1, WCB_2, AVA_0, AVA_1, AVA_2 (only the parents that split). |
| `parent` | text | 3-char parent group = left(bench, 3): WCA, WCB or AVA; the KNN recheck filter alongside basin. |

### `curated.erebor_locations` (materialized view)

erebor display spine (§6 PDP-from-curated), MATERIALIZED for per-tile read latency on hosted Postgres: PUD/RES from curated.intel_locations + intel_formation_blueox + reconciled_inventory; PDP from curated.wells_enriched (producing) + net_new_pdp. Drop-in for curated.intel_locations in erebor's map/gun-barrel/selection. PDP stick_id = -(api10); PDP econ columns NULL (producing context, not risked value). UNIQUE(stick_id) enables CONCURRENTLY refresh. Refresh: nightly via curated.refresh_all() (PDP arm) + recreate after the quarterly Novi reload (scripts/apply_erebor_locations.py).

~262,625 rows | nightly (etl.refresh, 9/10) (also DROP+recreated by the quarterly intel reload) | reads: `curated.intel_formation_blueox`, `curated.intel_locations`, `curated.net_new_pdp`, `curated.reconciled_inventory`, `curated.wells_enriched` | consumers: erebor tiles/selection, land team direct GIS

| column | type | description |
|---|---|---|
| `stick_id` | bigint | Row id. Positive = a Novi Intelligence stick (PUD/RES undrilled location); NEGATIVE = a producing well (PDP), where the id is minus its 10-digit API number. |
| `unique_id` | text | 10-digit API number for producing (PDP) rows; Novi well name for PUD/RES rows. |
| `category` | text | PDP = producing well (from the warehouse, what physically exists), PUD = Novi base-case undrilled location, RES = Novi emerging/resource location. |
| `basin` | text | Basin slug: delaware or midland. |
| `formation` | text | Raw vendor formation name (free text, inconsistent casing) -- display only. Group and filter on formation_blueox instead. |
| `formation_blueox` | text | Standardized Blue Ox bench code (e.g. WCA_1, WCB_2, BS2) -- the formation field of record for grouping/filtering. NULL = unmapped. |
| `basin_blueox` | text | Blue Ox basin slug (delaware/midland), aligned with formation_blueox. |
| `formation_blueox_source` | text | How the bench code was assigned: pdp_join / inferred / crosswalk (Novi sticks, sql/19) or the wells crosswalk chain (PDP rows). |
| `recon_status` | text | Reconciliation tag: remaining_pud + conflict = the DRILLABLE remaining inventory; realized_drift / realized_phantom = PUD slots already drilled (not inventory); net_new_pdp = a producing well Novi never inventoried; NULL = RES stick or ordinary PDP. |
| `deplet_t` | text | Novi depletion tier for PUD/RES: Tier-1..Tier-4, where Tier-4 = most depleted (drained by offset production). NULL on PDP rows (producing wells are not depletion-scored). |
| `operator` | text | Operator name: Novi-reported for PUD/RES, current operator from the warehouse for PDP. |
| `pad_name` | text | Novi DSU pad name (Delaware PUD only as of 2025Q3). NULL for PDP -- the gun-barrel assigns pads spatially instead. |
| `tvd` | double precision | True vertical depth, ft. |
| `ll_ft` | double precision | Lateral length, ft. |
| `npv5` | double precision | Novi pre-computed NPV at 5% discount, USD, flat deck. Vendor SCREEN only, not authoritative economics. NULL on PDP rows. |
| `npv10` | double precision | Novi pre-computed NPV at 10% discount, USD, flat deck. Vendor screen only. NULL on PDP rows. |
| `npv15` | double precision | Novi pre-computed NPV at 15% discount, USD, flat deck. Vendor screen only. NULL on PDP rows. |
| `npv20` | double precision | Novi pre-computed NPV at 20% discount, USD, flat deck. Vendor screen only. NULL on PDP rows. |
| `npv25` | double precision | Novi pre-computed NPV at 25% discount, USD, flat deck. Vendor screen only. NULL on PDP rows. |
| `pv5` | double precision | Novi pre-computed present value at 5% discount, USD. Vendor screen only. NULL on PDP rows. |
| `pv10` | double precision | Novi pre-computed present value at 10% discount, USD. Vendor screen only. NULL on PDP rows. |
| `pv15` | double precision | Novi pre-computed present value at 15% discount, USD. Vendor screen only. NULL on PDP rows. |
| `pv20` | double precision | Novi pre-computed present value at 20% discount, USD. Vendor screen only. NULL on PDP rows. |
| `pv25` | double precision | Novi pre-computed present value at 25% discount, USD. Vendor screen only. NULL on PDP rows. |
| `oil_eur` | double precision | Novi 30-yr oil EUR, bbl (vendor forecast horizon, not the suite's 50-yr technical EUR). NULL on PDP rows. |
| `gas_eur` | double precision | Novi 30-yr gas EUR, Mcf. NULL on PDP rows. |
| `wti_price` | double precision | Flat WTI oil price behind the Novi economics, USD/bbl. NULL on PDP rows. |
| `hh_price` | double precision | Flat Henry Hub gas price behind the Novi economics, USD/MMBtu. NULL on PDP rows. |
| `ngl_price` | double precision | Flat NGL price behind the Novi economics, USD/bbl. NULL on PDP rows. |
| `wti_diff` | double precision | Oil price differential vs WTI in the Novi deck, USD/bbl. NULL on PDP rows. |
| `hh_diff` | double precision | Gas price differential vs Henry Hub in the Novi deck, USD/MMBtu. NULL on PDP rows. |
| `wellstick_geom` | geometry | Lateral stick geometry (LINESTRING, EPSG:4326): the drawn/planned lateral for PUD/RES, the warehouse wellstick for PDP. GIST-indexed map geometry. |

### `curated.formation_blueox` (materialized view)

Blue Ox standardized formation mapping, one row per curated.wells api10 (~90k rows). Sources: Novi formation preferred, Enverus ENVInterval substituted for coarse Novi values; mapped via ref.formation_crosswalk. Factored out of curated.wells so crosswalk edits are a cheap REFRESH, not a production-chain DROP CASCADE. Refreshed nightly by etl.refresh / curated.refresh_all().

~91,312 rows | nightly (etl.refresh, 2/10) | reads: `curated.wells`, `ref.formation_crosswalk`

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | Universal well key (Novi 10-digit API); unique index supports REFRESH CONCURRENTLY. |
| `formation_blueox_raw` | character varying | Raw formation string selected by the precedence rule - Novi formation normally, Enverus ENVInterval when the Novi value is coarse/unreliable - before crosswalk mapping. |
| `formation_blueox_source` | text | Source of the selected raw string: novi or enverus. Enverus wins on trigger values (WOLFCAMP A/B variants, LOWER SPRABERRY SAND, generic WOLFCAMP/BONE SPRING(S)/SPRABERRY/UNKNOWN, SUB-WOODFORD); NULL when both sources are empty. |
| `basin_blueox` | text | Blue Ox basin token: delaware, midland or cbp - from Novi Subbasin, falling back to Enverus ENVBasin; NULL outside the three nomenclature basins. |
| `formation_blueox` | text | Blue Ox canonical bench code mapped via ref.formation_crosswalk on (basin_blueox, raw_value). NULL = crosswalk gap (delaware/midland, review); OTHER = unmapped CBP conventional shelf by design. Group/filter on this, never raw formation. |
| `formation_blueox_is_mapped` | boolean | TRUE = the crosswalk matched the raw string. FALSE rows are genuine gaps in delaware/midland but intentional in cbp (bucketed to OTHER). |

### `curated.formation_blueox_tvd` (materialized view)

TVD-sanity audit, one row per producing horizontal (api10): local 40-NN per-bench depth bands vs the assigned formation_blueox, flipping only gross depth outliers (e.g. Enverus-substitution mis-tags). Audit object - the override is applied downstream in curated.wells_enriched. Refreshed nightly by etl.refresh / curated.refresh_all() after producing_reference.

~59,012 rows | nightly (etl.refresh, 4/10) | reads: `curated.producing_reference`

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | Universal well key (Novi 10-digit API); one row per producing horizontal in curated.producing_reference with TVD and a bench code. |
| `basin` | text | Blue Ox basin token (delaware/midland) carried from curated.producing_reference. |
| `assigned_code` | text | Blue Ox bench assigned by curated.formation_blueox (sql/16) BEFORE this depth audit. |
| `tvd` | integer | Well true vertical depth, ft (curated.wells.tvd_ft). |
| `assigned_med` | double precision | Local median TVD, ft, of the well's assigned bench among its 40 nearest producing neighbours (same basin; permit-round x100 depths excluded from the band). |
| `assigned_n` | bigint | Neighbour count behind assigned_med; a flip requires >= 5 so the home band is well established. |
| `nearest_code` | text | Bench whose local median TVD is closest to the well's TVD, among neighbour bands with >= 3 wells. |
| `nearest_med` | double precision | Local median TVD, ft, of the depth-nearest bench (nearest_code). |
| `nearest_n` | bigint | Neighbour count behind nearest_med; a flip requires >= 3. |
| `survey_planned` | boolean | TRUE = the directional survey on file is the operator's pre-drill plan (DirectionalSurveyIsPlanned), so the TVD is provisional; ~44% of NM producers, ~0% TX. |
| `tvd_round` | boolean | TRUE = TVD is an exact multiple of 100 ft - the permit/plan-depth tell (a real survey reads 12415 ft, not 12000); ~3% of wells, the only tell in TX. |
| `permit_suspect` | boolean | tvd_round OR survey_planned: the depth is likely a permit number, so the outlier gap required to flip widens to 1000 ft (vs 600 ft for a trusted survey depth). |
| `assigned_gap` | double precision | abs(tvd - assigned_med), ft: how far the well sits from its own bench's local depth band. |
| `nearest_gap` | double precision | abs(tvd - nearest_med), ft: distance to the depth-nearest bench's local band. |
| `corrected` | boolean | TRUE = all flip guards passed: gap > 600/1000 ft, target band >= 400 ft closer, band support (5/3), no flips into/out of WDFD/BRNT/MISS or to OTHER, no sand<->carb swaps. |
| `corrected_code` | text | Bench of record after the audit: nearest_code when corrected, else assigned_code. Consumed by curated.wells_enriched as the canonical formation_blueox. |

### `curated.intel_arps` (view)

Novi Intelligence Arps decline parameters per stick and stream (from raw_intel.arps_forecast). d_nom is NOMINAL per-year decline. Rebuilt quarterly by the intel reload chain.

~0 rows | quarterly (Novi intel reload chain) | reads: `raw_intel.arps_forecast`, `raw_intel.planned_well`

| column | type | description |
|---|---|---|
| `basin` | text | Basin slug: delaware or midland. |
| `novi_wellname` | text | Novi planned-well name; joins intel_locations.unique_id for PUD/RES (share Arps covers planned wells only). |
| `production_stream` | text | Forecast stream: oil, gas, or water (3 segments each). |
| `segment` | integer | Decline segment number (1..3) within the stream's piecewise Arps forecast. |
| `segment_curve_type` | text | Curve type of this segment (e.g. hyperbolic, exponential terminal). |
| `b` | double precision | Arps b-factor of the segment (dimensionless). |
| `d_nom` | double precision | Segment initial decline Di, NOMINAL per-year (not effective; values > 1/yr are normal). Effective equivalents are d_eff_secant / d_eff_tangent. |
| `d_eff_secant` | double precision | Effective annual decline, secant convention (fraction/yr). |
| `d_eff_tangent` | double precision | Effective annual decline, tangent convention (fraction/yr). |
| `q_start` | double precision | Segment start rate qi (bbl/d for oil/water, Mcf/d for gas). |
| `q_stop` | double precision | Segment end rate (bbl/d for oil/water, Mcf/d for gas). |
| `terminal_day` | integer | Producing day on which the terminal (exponential) decline takes over. |
| `day_start` | integer | First producing day covered by this segment (days since first production). |
| `day_stop` | integer | Last producing day covered by this segment. |
| `planned_well_id` | text | Share well_ref of the planned well (text, format PW-{id}); lineage back to raw_intel. |
| `well_inventory_name` | text | Always NULL: no source in the Snowflake share. Column retained for the legacy output contract. |

### `curated.intel_forecast` (view)

Novi Intelligence monthly production forecast per stick (P50, 30-day months, planned wells only; from raw_intel.production_forecast). Rebuilt quarterly by the intel reload chain.

~0 rows | quarterly (Novi intel reload chain) | reads: `raw_intel.planned_well`, `raw_intel.production_forecast`

| column | type | description |
|---|---|---|
| `basin` | text | Basin slug: delaware or midland. |
| `novi_wellname` | text | Novi planned-well name; joins intel_locations.unique_id for PUD/RES (forecast covers planned wells only). |
| `ip_day` | integer | Forecast day since first production, in 30-day steps (share forecast_day). |
| `mop` | integer | Approximate month on production = ip_day / 30 (integer). |
| `oil` | double precision | Forecast oil rate for the month, bbl/d (Novi P50). |
| `gas` | double precision | Forecast gas rate for the month, Mcf/d (Novi P50). |
| `water` | double precision | Forecast water rate for the month, bbl/d (Novi P50). |

### `curated.intel_formation_blueox` (materialized view)

Blue Ox formation code per Novi Intelligence stick (curated.intel_locations), keyed on stick_id. Four-tier: PDP api10-join -> spatial+TVD inference (off curated.bench_reference) for coarse parents that split (Delaware Avalon/WolfcampA/WolfcampB, Midland WolfcampB) -> ref.formation_crosswalk -> NULL. Inference v1 = TVD-aware k=1 (12-lateral horizontal neighbourhood, then TVD-nearest; ~84.5% leave-one-out). formation_blueox_source in (pdp_join, inferred, crosswalk, NULL). Refresh with the biannual Novi Intelligence load, not nightly.

~251,902 rows | quarterly (Novi intel reload chain) | reads: `curated.bench_reference`, `curated.formation_blueox`, `curated.intel_locations`, `ref.formation_crosswalk`

| column | type | description |
|---|---|---|
| `stick_id` | bigint | Novi Intelligence stick id (curated.intel_locations.stick_id); unique key. |
| `formation_blueox_raw` | text | Novi formation string as shipped (free text), before mapping to Blue Ox nomenclature. |
| `basin_blueox` | text | Basin slug used for the crosswalk: delaware or midland. |
| `formation_blueox` | text | Blue Ox canonical bench code (e.g. WCA_1, WCB_2, AVA_1) -- the grouping field of record for intel sticks. NULL = unmapped tail (empty today). |
| `formation_blueox_source` | text | Assignment tier: pdp_join (api10 join to curated.formation_blueox), inferred (spatial + TVD k=1 sub-bench inference, ~84.5% LOO), crosswalk (ref.formation_crosswalk), or NULL. |
| `formation_blueox_confidence` | real | NULL today; reserved for the planned k>1 weighted-vote confidence pass to route ambiguous inferred picks to review. |

### `curated.intel_locations` (materialized view)

Novi Intelligence sticks (PDP/PUD/RES) for erebor deal valuation, sourced from the INTEL Snowflake share mirror (raw_intel, sql/27). Same output contract as the retired sql/12 version: irr_pct in percent, pad NPV rollup (SUM of member sticks), api10 crosswalk to curated.wells (PDP), gunbarrel points (all classes), GIST-indexed wellstick_geom, stable stick_id via raw_intel.stick_id_map. Economics are Novi pre-computed on a flat deck — a screen, not the authoritative deal value.

~251,902 rows | nightly (etl.refresh, 8/10) (also DROP+recreated by the quarterly intel reload) | reads: `curated.wells`, `raw_intel.econ_price_assumption`, `raw_intel.stick_id_map`, `raw_intel.well`, `raw_intel.well_completion`, `raw_intel.well_cost_summary`, `raw_intel.well_economics_summary`, `raw_intel.well_master`, `raw_intel.well_ml_score`, `raw_intel.well_rock_quality`, `raw_intel.wellbore` | consumers: erebor Highgrade/facets/export

| column | type | description |
|---|---|---|
| `stick_id` | bigint | Stable unique id for this location. Always positive here (assigned from raw_intel.stick_id_map, so it survives quarterly Novi reloads). In erebor_locations, producing (PDP) rows instead use the negative of their API10. |
| `basin` | text | Basin slug: delaware or midland. |
| `report_version` | text | Novi Intelligence report vintage in share format, e.g. 2025Q3 (the old file-drop wrote 3Q25). |
| `category` | text | Location class: PDP = producing well, PUD = Novi base-case undrilled location, RES = emerging/resource (more speculative) location. |
| `src_layer` | text | Source report name in the Novi Snowflake share (e.g. basin_research__Delaware Basin__2025Q3); lineage only. |
| `unique_id` | text | Row identifier for joins/exports: 10-digit API number for PDP rows, Novi well name for PUD/RES rows. |
| `api10` | text | 10-digit API well number; populated for PDP rows only (undrilled PUD/RES have no API). Universal well key across the suite. |
| `pdp_in_warehouse` | boolean | TRUE when this PDP api10 also exists in curated.wells (the warehouse well header); FALSE/NULL means Novi lists a well the warehouse does not carry. |
| `phase` | text | Target phase label; constant Oil for this inventory (carried from the legacy layer). |
| `operator` | text | Operator name as reported by Novi (vendor spelling, not entity-normalized). |
| `formation` | text | Novi target formation name (vendor free text, UPPERCASE-ish). For grouping/filtering use curated.intel_formation_blueox, not this. |
| `county` | text | County name from the Novi share. |
| `pad_name` | text | Novi DSU pad name. Share gap: populated only for Delaware PUD (BASE_CASE) as of 2025Q3; NULL elsewhere. |
| `fp_year` | integer | First-production year for PDP wells; 2050 placeholder for undrilled PUD/RES (the share has no planned TIL dates). |
| `tvd` | double precision | True vertical depth at total depth, ft. |
| `md` | double precision | Measured depth at total depth, ft. |
| `ll_ft` | double precision | Lateral length, ft. |
| `prop_load` | double precision | Planned proppant loading, lb per lateral ft. NULL for PDP (the share carries completion data for planned wells only). |
| `spacing_s` | double precision | Novi ML spacing sensitivity SCORE (signed, unitless) -- NOT a spacing footage. Per-bench spacing footage is user-set in the apps. |
| `spacing_t` | text | Novi ML spacing tier LABEL (Tier-1..Tier-4) -- NOT footage. Tier-1 = least spacing-degraded. |
| `deplet_s` | double precision | Novi ML prior-depletion score (signed, unitless); how much offset production has drained this location. |
| `deplet_t` | text | Novi depletion tier: Tier-1..Tier-4 where Tier-4 = most depleted (drained by offsets); also No Depletion. Drives the erebor depletion filter. |
| `complet_s` | double precision | Novi ML completion-design score (signed, unitless). |
| `complet_t` | text | Novi ML completion tier label (Tier-1..Tier-4). |
| `rqs` | double precision | Novi ML rock-quality score (signed, unitless), oil stream. |
| `rqt` | text | Novi ML rock-quality tier label (Tier-1..Tier-4). |
| `oil_eur` | double precision | Novi 30-yr oil EUR, bbl (30-yr is the only horizon in the share). Vendor forecast, not the suite's 50-yr technical EUR. |
| `gas_eur` | double precision | Novi 30-yr wet-gas EUR, Mcf. |
| `dgas_eur` | double precision | Novi 30-yr dry (residue) gas EUR, Mcf. |
| `ngl_eur` | double precision | Novi 30-yr NGL EUR, bbl. |
| `water_eur` | double precision | Novi 30-yr produced-water volume, bbl. |
| `oil_ip` | double precision | Novi initial oil rate, bbl/d. |
| `gas_ip` | double precision | Novi initial wet-gas rate, Mcf/d. |
| `dgas_ip` | double precision | Novi initial dry-gas rate, Mcf/d. |
| `ngl_ip` | double precision | Novi initial NGL rate, bbl/d. |
| `water_ip` | double precision | Novi initial water rate, bbl/d. |
| `ngl_yield` | double precision | Novi NGL yield assumption, bbl NGL per MMcf gas (basin-typical 100-150; an input, not derived from the EUR columns). |
| `ngl_shrink` | double precision | Novi gas shrink assumption (fraction of wet gas lost to processing). |
| `npv5` | double precision | Novi pre-computed NPV at 5% discount, USD, flat price deck. Vendor SCREEN only -- never authoritative economics (economics live downstream of the export). |
| `npv10` | double precision | Novi pre-computed NPV at 10% discount, USD, flat deck. Vendor screen, not authoritative. |
| `npv15` | double precision | Novi pre-computed NPV at 15% discount, USD, flat deck. Vendor screen, not authoritative. |
| `npv20` | double precision | Novi pre-computed NPV at 20% discount, USD, flat deck. Vendor screen, not authoritative. |
| `npv25` | double precision | Novi pre-computed NPV at 25% discount, USD, flat deck. Vendor screen, not authoritative. |
| `pv5` | double precision | Novi pre-computed present value at 5% discount, USD (companion to npv5). Vendor screen, not authoritative. |
| `pv10` | double precision | Novi pre-computed present value at 10% discount, USD. Vendor screen, not authoritative. |
| `pv15` | double precision | Novi pre-computed present value at 15% discount, USD. Vendor screen, not authoritative. |
| `pv20` | double precision | Novi pre-computed present value at 20% discount, USD. Vendor screen, not authoritative. |
| `pv25` | double precision | Novi pre-computed present value at 25% discount, USD. Vendor screen, not authoritative. |
| `npv5_be` | double precision | Novi breakeven flat oil price at which NPV-5 = 0, USD/bbl. Vendor screen. |
| `npv10_be` | double precision | Novi breakeven flat oil price at which NPV-10 = 0, USD/bbl. Vendor screen. |
| `npv15_be` | double precision | Novi breakeven flat oil price at which NPV-15 = 0, USD/bbl. Vendor screen. |
| `npv20_be` | double precision | Novi breakeven flat oil price at which NPV-20 = 0, USD/bbl. Vendor screen. |
| `npv25_be` | double precision | Novi breakeven flat oil price at which NPV-25 = 0, USD/bbl. Vendor screen. |
| `be_1yr` | double precision | Novi 1-yr breakeven oil price (flat WTI needed for payout within 1 yr), USD/bbl. Vendor screen. |
| `be_2yr` | double precision | Novi 2-yr breakeven oil price (flat WTI needed for payout within 2 yr), USD/bbl. Vendor screen. |
| `be_3yr` | double precision | Novi 3-yr breakeven oil price (flat WTI needed for payout within 3 yr), USD/bbl. Vendor screen. |
| `irr_pct` | double precision | Novi IRR normalized to PERCENT. The share's IRR unit is inconsistent by (basin, category) slice, so a per-slice median calibration applies x10000 (slice median \|irr\| < 0.05) or x100. Vendor screen; see irr_pct_raw for the source value. |
| `irr_pct_raw` | double precision | IRR exactly as delivered in the Snowflake share (fraction on some slices, fraction/100 on others -- raised with Novi). Audit trail behind the calibrated irr_pct. |
| `pp_months` | double precision | Novi payback period, months. Vendor screen. |
| `ttpt` | double precision | Novi time to double payback (2x payout), months (share double_payback_months). Vendor screen. |
| `dc_cost` | double precision | Novi total drill + complete cost, USD. Vendor screen. |
| `dcet_cost` | double precision | Novi total drill, complete, equip + tie-in cost, USD. Vendor screen. |
| `norm_dc` | double precision | Novi drill + complete cost normalized per lateral ft, USD/ft. Vendor screen. |
| `norm_dcet` | double precision | Novi DCET cost normalized per lateral ft, USD/ft. Vendor screen. |
| `wti_price` | double precision | Flat WTI oil price behind the Novi economics, USD/bbl (from the report price deck). |
| `hh_price` | double precision | Flat Henry Hub gas price behind the Novi economics, USD/MMBtu. |
| `ngl_price` | double precision | Flat NGL price behind the Novi economics, USD/bbl. |
| `wti_diff` | double precision | Oil price differential vs WTI in the Novi deck, USD/bbl. |
| `hh_diff` | double precision | Gas price differential vs Henry Hub in the Novi deck, USD/MMBtu. |
| `has_econ` | text | Yes/No: whether a Novi economics row exists for this location. |
| `conf_int` | double precision | Always NULL: the Snowflake share has no confidence-interval source. Column retained so the sql/12 output contract is unchanged. |
| `pad_npv25` | numeric | Pad-level NPV-25 rollup, USD: SUM of member-stick npv25 per (report, pad_name). Delaware PUD pads only as of 2025Q3 (pad_name share gap). Vendor screen. |
| `subbasin` | text | Novi subbasin name (e.g. Delaware, Midland). |
| `heel_lat` | double precision | Heel point latitude, WGS84 decimal degrees (gunbarrel endpoint). |
| `heel_lon` | double precision | Heel point longitude, WGS84 decimal degrees. |
| `midpoint_lat` | double precision | Lateral midpoint latitude, WGS84 decimal degrees. |
| `midpoint_lon` | double precision | Lateral midpoint longitude, WGS84 decimal degrees. |
| `bh_lat` | double precision | Bottom-hole latitude, WGS84 decimal degrees. |
| `bh_lon` | double precision | Bottom-hole longitude, WGS84 decimal degrees. |
| `wellstick_geom` | geometry(Geometry,4326) | Lateral stick geometry (LINESTRING, EPSG:4326) from the share WKT. GIST-indexed; the map/selection geometry. |

### `curated.net_new_pdp` (materialized view)

§6 reverse pass: post-vintage (first_production_date > 2025-09-30) producing horizontals whose lateral overlaps no same-(corrected)-bench PUD at the same depth (best_pud_overlap < 0.2) — incremental locations the static Novi vintage did not inventory. Closes the arithmetic new-wells ≈ realized_pud_to_pdp + net_new_pdp. Keyed on api10; carries wellstick_geom for mapping. Overlap vs PUD only (RES exclusion is a future refinement). Refresh with the Novi load / as wells come online.

~2,160 rows | quarterly (Novi intel reload chain) | reads: `curated.formation_blueox_tvd`, `curated.intel_formation_blueox`, `curated.intel_locations`, `curated.producing_reference`

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | 10-digit API of the post-vintage producing horizontal that no Novi PUD anticipated; unique key. |
| `basin_blueox` | text | Basin slug: delaware or midland. |
| `formation_blueox` | text | Blue Ox bench code of the well (TVD-corrected producing code, sql/23 override applied). |
| `tvd` | integer | Landing true vertical depth, ft (from the producing reference). |
| `first_production_date` | date | First production date; by definition after the loaded Novi vintage (curated.intel_vintage_date()). |
| `operator` | character varying(64) | Current operator of the well. |
| `ll_ft` | integer | Lateral length, ft. |
| `survey_planned` | boolean | TRUE = directional survey is a pre-drill plan (provisional formation/TVD; mostly NM). |
| `wellstick_geom` | geometry | Lateral stick geometry (LINESTRING, EPSG:4326) for mapping; GIST-indexed. |
| `best_pud_overlap` | numeric | Max fraction (0-1) of any same-bench PUD lateral covered by this well's +/-150 ft corridor; < 0.2 by definition (else the PUD counts as realized/conflict, not net-new). |

### `curated.producing_reference` (materialized view)

Producing curated wells (first_production_date NOT NULL, delaware/midland, mapped bench), one row per api10, pre-buffered into a +/-150 ft corridor and GiST-indexed. The spatial system of record for PUD reconciliation (curated.reconciled_inventory) and the sql/23 TVD audit: realized = co-extent overlap in-corridor, same bench, TVD-guarded. Refreshed nightly by etl.refresh / curated.refresh_all().

~59,052 rows | nightly (etl.refresh, 3/10) | reads: `curated.formation_blueox`, `curated.wells`

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | Universal well key (Novi 10-digit API); unique index supports REFRESH CONCURRENTLY. |
| `geom` | geometry | Wellstick LINESTRING (4326) from curated.wells; GiST-indexed to drive the <-> KNN depth profile in sql/23. |
| `corridor` | geometry | Lateral buffered +/-150 ft (46 m on the geography, stored as geometry), GiST-indexed. Realization is co-extent OVERLAP of a PUD inside this corridor - never min distance, which false-positives on toe-to-heel laterals. |
| `basin` | text | Blue Ox basin token (delaware or midland) from curated.formation_blueox. |
| `code` | text | Blue Ox bench code from curated.formation_blueox (pre-TVD-correction); NOT NULL by filter - same-bench is required for a reconciliation match. |
| `tvd` | integer | True vertical depth, ft (curated.wells.tvd_ft); input to the sql/21 TVD guard and the sql/23 depth bands. |
| `survey_planned` | boolean | TRUE = directional survey on file is the pre-drill plan, so tvd is provisional and will move when the actual survey lands; ~44% of NM producers, ~0% TX. Flags matches resting on permit depths. |
| `first_production_date` | date | First production date (Novi preferred, Enverus fallback); NOT NULL by definition - this matview is the producing population. |
| `operator` | character varying(64) | Current operator (curated.wells.current_operator). |
| `ll_ft` | integer | Completed lateral length, ft (curated.wells.lateral_length_ft); denominator context for overlap fractions. |

### `curated.production` (materialized view)

Well-month production actuals from raw_novi.WellMonths (soft-deleted rows excluded), ~5M rows. Grain: one row per well-month; key (api10, prod_year, prod_month). Refreshed nightly by etl.refresh via curated.refresh_all(), per-view with settle().

~4,965,105 rows | nightly (etl.refresh, 5/10) | reads: `raw_novi.WellMonths`

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | 10-digit API wellbore id (Novi convention) - the universal well key across the suite. Joins curated.wells.api10; Novi-Enverus join is LEFT(api14,10) = api10. |
| `prod_year` | integer | Calendar year of the production month; part of the composite key (api10, prod_year, prod_month). |
| `prod_month` | integer | Calendar month (1-12) of the production month; part of the composite key. |
| `prod_date` | date | First day of the production month (date form of prod_year/prod_month). |
| `operator` | character varying(64) | Operator of record for THIS month. Novi tracks operator per-month, so a well's operator changes mid-history when it is sold. |
| `operator_entity` | character varying(64) | Novi parent-entity roll-up of the monthly operator (aggregates subsidiaries to the corporate parent). |
| `months_on_production` | integer | Months since first production, 1-indexed (MoP 1 = first-production month). The type-curve alignment axis - wells align on MoP, not calendar date. |
| `producing_days` | integer | Days the well actually produced in the month. Month-1 exception: the partial first-prod month uses producing_days as the rate denominator; later months use calendar days. |
| `cumulative_producing_days` | integer | Running total of producing_days since first production, days. |
| `oil_per_day_bbl` | double precision | Oil rate, bbl/d, CALENDAR-day denominator (Novi OilPerDay) - the fitting/aggregation convention; month-1 exception uses producing_days for the partial first month. |
| `oil_per_month_bbl` | integer | Oil volume produced in the month, bbl. |
| `cumulative_oil_bbl` | integer | Cumulative oil from first production through this month, bbl. |
| `gas_per_day_mcf` | double precision | Gas rate, Mcf/d, calendar-day denominator (month-1 exception: producing_days). Gas commonly peaks ~4 months after oil - anchor gas fits on the gas peak, not the oil peak. |
| `gas_per_month_mcf` | integer | Gas volume produced in the month, Mcf. |
| `cumulative_gas_mcf` | integer | Cumulative gas from first production through this month, Mcf. |
| `water_per_day_bbl` | double precision | Water rate, bbl/d, calendar-day denominator (month-1 exception: producing_days). Water typically peaks in flowback - anchor water fits on its own peak. |
| `water_per_month_bbl` | integer | Water volume produced in the month, bbl. |
| `cumulative_water_bbl` | integer | Cumulative water from first production through this month, bbl. |
| `flared_gas_per_day_mcf` | double precision | Flared gas rate, Mcf/d, calendar-day denominator (Novi FlaredGasPerDay). |
| `flared_gas_per_month_mcf` | integer | Flared gas volume in the month, Mcf. |
| `cumulative_flared_gas_mcf` | integer | Cumulative flared gas from first production through this month, Mcf. |
| `basin` | character varying(36) | Novi basin label carried from WellMonths for filter-without-join (duplicated on curated.wells). |
| `subbasin` | character varying(36) | Novi sub-basin label (e.g. DELAWARE, MIDLAND, CENTRAL BASIN PLATFORM) carried from WellMonths. |
| `is_oil_proprietary` | boolean | TRUE when the month's oil volume came from Novi's proprietary production-sharing source rather than state filings. |
| `is_gas_proprietary` | boolean | TRUE when the month's gas volume came from Novi's proprietary production-sharing source rather than state filings. |
| `is_gas_flared_proprietary` | boolean | TRUE when the month's flared-gas volume came from Novi's proprietary production-sharing source rather than state filings. |
| `is_water_proprietary` | boolean | TRUE when the month's water volume came from Novi's proprietary production-sharing source rather than state filings. |

### `curated.production_combined` (view)

Regular VIEW (no storage, always fresh): production_normalized actuals UNION ALL production_forecast (Novi ML P50 tail) with an is_forecast flag - one continuous per-well well-month timeline. Key (api10, prod_year, prod_month); actual and forecast months are disjoint per well.

~0 rows | n/a (plain view, always current) | reads: `curated.production_forecast`, `curated.production_normalized`

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | 10-digit API wellbore id - universal well key; joins curated.wells.api10. |
| `prod_year` | integer | Calendar year of the production/forecast month; part of the composite key. |
| `prod_month` | integer | Calendar month (1-12); part of the composite key. |
| `prod_date` | date | First day of the month; per well, actuals then forecast form one contiguous date series. |
| `months_on_production` | integer | Months since first production, 1-indexed; contiguous across the actual-to-forecast seam (forecast rows continue the actuals MoP count). |
| `producing_days` | integer | Days actually produced in the month; populated on actual rows only, NULL on forecast rows. |
| `oil_per_day_bbl` | double precision | Oil rate, bbl/d, calendar-day basis; actual when is_forecast=FALSE (month-1 exception uses producing_days), Novi ML P50 projection when TRUE. |
| `gas_per_day_mcf` | double precision | Gas rate, Mcf/d, calendar-day basis; actual when is_forecast=FALSE, Novi ML P50 projection when TRUE. |
| `water_per_day_bbl` | double precision | Water rate, bbl/d, calendar-day basis; actual when is_forecast=FALSE, Novi ML P50 projection when TRUE. |
| `oil_per_month_bbl` | integer | Oil volume in the month, bbl (actual or Novi ML P50 forecast per is_forecast). |
| `gas_per_month_mcf` | integer | Gas volume in the month, Mcf (actual or Novi ML P50 forecast per is_forecast). |
| `water_per_month_bbl` | integer | Water volume in the month, bbl (actual or Novi ML P50 forecast per is_forecast). |
| `cumulative_oil_bbl` | integer | Cumulative oil through this month, bbl; forecast rows continue the actuals cumulative. |
| `cumulative_gas_mcf` | integer | Cumulative gas through this month, Mcf; forecast rows continue the actuals cumulative. |
| `cumulative_water_bbl` | integer | Cumulative water through this month, bbl; forecast rows continue the actuals cumulative. |
| `boe_per_day_bbl` | double precision | Synthetic BOE rate, bbl/d: oil + gas/6 (6:1 basis; water excluded); actual or forecast per is_forecast. |
| `boe_per_month_bbl` | numeric | Synthetic BOE volume in the month, bbl (oil + gas/6). |
| `cumulative_boe_bbl` | numeric | Cumulative synthetic BOE through this month, bbl (cum oil + cum gas/6). |
| `oil_per_day_per_1000ft` | double precision | Oil rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `gas_per_day_per_1000ft` | double precision | Gas rate normalized per lateral length, Mcf/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `water_per_day_per_1000ft` | double precision | Water rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `boe_per_day_per_1000ft` | double precision | BOE rate (oil + gas/6) per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_oil_per_1000ft` | numeric | Cumulative oil per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_gas_per_1000ft` | numeric | Cumulative gas per lateral length, Mcf per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_water_per_1000ft` | numeric | Cumulative water per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_boe_per_1000ft` | numeric | Cumulative BOE (oil + gas/6) per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `state_code` | integer | State FIPS code, carried from curated.wells. |
| `county_code` | character varying(5) | County FIPS code (5-char state+county), carried from curated.wells. |
| `county` | character varying(32) | County name, carried from curated.wells. |
| `basin` | character varying(36) | Novi basin label, carried from curated.wells. |
| `subbasin` | character varying(36) | Novi sub-basin label (DELAWARE / MIDLAND / CENTRAL BASIN PLATFORM), carried from curated.wells. |
| `formation` | character varying(64) | RAW Novi formation string (free-text UPPERCASE). For grouping/filtering use formation_blueox (via curated.wells_enriched), never this column. |
| `lateral_length_ft` | integer | Completed lateral length, ft, from curated.wells; denominator of every per-1,000-ft column. |
| `first_production_date` | date | Well-level first production date, from curated.wells. |
| `first_completion_date` | date | Well-level first completion date, from curated.wells; basis for the vintage columns. |
| `first_completion_year` | integer | Calendar year of first_completion_date. |
| `completion_vintage_bucket` | text | Completion vintage cohort bucket: pre-2017 / 2017-2019 / 2020-2022 / 2023+; NULL when first_completion_date is NULL. |
| `lateral_length_class` | text | Lateral length bucket, ft: <5000 / 5000-7499 / 7500-9999 / 10000-14999 / 15000+; NULL when lateral_length_ft is missing or <= 0. |
| `is_forecast` | boolean | FALSE = actual (production_normalized, from Novi WellMonths); TRUE = Novi ML P50 projection (production_forecast). Forecast rows begin the month after the well's last actual. |

### `curated.production_forecast` (materialized view)

Novi ML P50 forecast tail (raw_novi.ForecastWellMonths, IsForecasted=TRUE, ~17M rows) JOINed to curated.wells and normalized per 1,000 ft; column-identical to production_normalized for clean UNION. Key (api10, prod_year, prod_month); MoP 1-600. Nightly refresh is gated on ForecastWellMonths source change and runs LAST.

~18,420,580 rows | nightly (etl.refresh, 10/10) — refresh gated on source change | reads: `curated.wells`, `raw_novi.ForecastWellMonths` | consumers: anduin (Novi ML forecast overlay)

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | 10-digit API wellbore id - universal well key; joins curated.wells.api10. |
| `prod_year` | integer | Calendar year of the forecast month, derived from ForecastWellMonths Date; part of the composite key. |
| `prod_month` | integer | Calendar month (1-12) of the forecast month, derived from Date; part of the composite key. |
| `prod_date` | date | First day of the forecast month. |
| `months_on_production` | integer | Months since first production, 1-indexed, continuing the actuals count; forecast rows start the month AFTER the well's last actual, so low-MoP forecast population is sparse. |
| `producing_days` | integer | Always NULL - ForecastWellMonths has no producing-days analog; column kept for parity with production_normalized so the UNION in production_combined stays clean. |
| `oil_per_day_bbl` | double precision | Forecast oil rate, bbl/d, calendar-day basis - Novi ML P50 projection, not an actual. |
| `gas_per_day_mcf` | double precision | Forecast gas rate, Mcf/d, calendar-day basis - Novi ML P50 projection. |
| `water_per_day_bbl` | double precision | Forecast water rate, bbl/d, calendar-day basis - Novi ML P50 projection. |
| `oil_per_month_bbl` | integer | Forecast oil volume in the month, bbl (integer-truncated in the Novi source). |
| `gas_per_month_mcf` | integer | Forecast gas volume in the month, Mcf (integer-truncated in the Novi source). |
| `water_per_month_bbl` | integer | Forecast water volume in the month, bbl (integer-truncated in the Novi source). |
| `cumulative_oil_bbl` | integer | Forecast cumulative oil through this month, bbl, continuing from the actuals history. |
| `cumulative_gas_mcf` | integer | Forecast cumulative gas through this month, Mcf, continuing from the actuals history. |
| `cumulative_water_bbl` | integer | Forecast cumulative water through this month, bbl, continuing from the actuals history. |
| `boe_per_day_bbl` | double precision | Forecast synthetic BOE rate, bbl/d: oil + gas/6 (6:1 basis; water excluded). |
| `boe_per_month_bbl` | numeric | Forecast synthetic BOE volume in the month, bbl (oil + gas/6). |
| `cumulative_boe_bbl` | numeric | Forecast cumulative synthetic BOE, bbl (cum oil + cum gas/6). |
| `oil_per_day_per_1000ft` | double precision | Forecast oil rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `gas_per_day_per_1000ft` | double precision | Forecast gas rate normalized per lateral length, Mcf/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `water_per_day_per_1000ft` | double precision | Forecast water rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `boe_per_day_per_1000ft` | double precision | Forecast BOE rate (oil + gas/6) per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_oil_per_1000ft` | numeric | Forecast cumulative oil per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_gas_per_1000ft` | numeric | Forecast cumulative gas per lateral length, Mcf per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_water_per_1000ft` | numeric | Forecast cumulative water per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_boe_per_1000ft` | numeric | Forecast cumulative BOE (oil + gas/6) per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `state_code` | integer | State FIPS code, carried from curated.wells (identical derivation to production_normalized for cohort alignment). |
| `county_code` | character varying(5) | County FIPS code (5-char state+county), carried from curated.wells. |
| `county` | character varying(32) | County name, carried from curated.wells. |
| `basin` | character varying(36) | Novi basin label, carried from curated.wells. |
| `subbasin` | character varying(36) | Novi sub-basin label (DELAWARE / MIDLAND / CENTRAL BASIN PLATFORM), carried from curated.wells. |
| `formation` | character varying(64) | RAW Novi formation string (free-text UPPERCASE). For grouping/filtering use formation_blueox (via curated.wells_enriched), never this column. |
| `lateral_length_ft` | integer | Completed lateral length, ft, from curated.wells; denominator of every per-1,000-ft column. |
| `first_production_date` | date | Well-level first production date, from curated.wells. |
| `first_completion_date` | date | Well-level first completion date, from curated.wells; basis for the vintage columns. |
| `first_completion_year` | integer | Calendar year of first_completion_date. |
| `completion_vintage_bucket` | text | Completion vintage cohort bucket: pre-2017 / 2017-2019 / 2020-2022 / 2023+; NULL when first_completion_date is NULL. |
| `lateral_length_class` | text | Lateral length bucket, ft: <5000 / 5000-7499 / 7500-9999 / 10000-14999 / 15000+; NULL when lateral_length_ft is missing or <= 0. |

### `curated.production_normalized` (materialized view)

Actuals well-months: curated.production INNER JOIN curated.wells, adding BOE (oil + gas/6) and per-1,000-ft normalized rates plus cohort keys. Grain well-month; key (api10, prod_year, prod_month); MoP filtered 1-600. Refreshed nightly by etl.refresh after wells and production.

~4,914,519 rows | nightly (etl.refresh, 6/10) | reads: `curated.production`, `curated.wells` | consumers: anduin type-curve fitting

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | 10-digit API wellbore id - universal well key; joins curated.wells.api10. |
| `prod_year` | integer | Calendar year of the production month; part of the composite key. |
| `prod_month` | integer | Calendar month (1-12) of the production month; part of the composite key. |
| `prod_date` | date | First day of the production month. |
| `months_on_production` | integer | Months since first production, 1-indexed (MoP 1 = first-prod month); the type-curve alignment axis. Rows restricted to MoP 1-600. |
| `producing_days` | integer | Days actually produced in the month. Month-1 exception: partial first-prod month uses producing_days as the rate denominator. |
| `oil_per_day_bbl` | double precision | Oil rate, bbl/d, calendar-day denominator (pass-through from curated.production; month-1 exception uses producing_days). |
| `gas_per_day_mcf` | double precision | Gas rate, Mcf/d, calendar-day denominator (pass-through; month-1 exception uses producing_days). |
| `water_per_day_bbl` | double precision | Water rate, bbl/d, calendar-day denominator (pass-through; month-1 exception uses producing_days). |
| `oil_per_month_bbl` | integer | Oil volume in the month, bbl. |
| `gas_per_month_mcf` | integer | Gas volume in the month, Mcf. |
| `water_per_month_bbl` | integer | Water volume in the month, bbl. |
| `cumulative_oil_bbl` | integer | Cumulative oil through this month, bbl. |
| `cumulative_gas_mcf` | integer | Cumulative gas through this month, Mcf. |
| `cumulative_water_bbl` | integer | Cumulative water through this month, bbl. |
| `boe_per_day_bbl` | double precision | Synthetic BOE rate, bbl/d: oil_per_day_bbl + gas_per_day_mcf/6 (6:1 Mcf:bbl basis; water excluded). |
| `boe_per_month_bbl` | numeric | Synthetic BOE volume in the month, bbl (oil + gas/6). |
| `cumulative_boe_bbl` | numeric | Cumulative synthetic BOE through this month, bbl (cum oil + cum gas/6). |
| `oil_per_day_per_1000ft` | double precision | Oil rate normalized per lateral length, bbl/d per 1,000 ft (rate x 1000 / lateral_length_ft); NULL when lateral_length_ft is missing or <= 0. |
| `gas_per_day_per_1000ft` | double precision | Gas rate normalized per lateral length, Mcf/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `water_per_day_per_1000ft` | double precision | Water rate normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `boe_per_day_per_1000ft` | double precision | BOE rate (oil + gas/6) normalized per lateral length, bbl/d per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_oil_per_1000ft` | numeric | Cumulative oil normalized per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_gas_per_1000ft` | numeric | Cumulative gas normalized per lateral length, Mcf per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_water_per_1000ft` | numeric | Cumulative water normalized per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `cumulative_boe_per_1000ft` | numeric | Cumulative BOE (oil + gas/6) normalized per lateral length, bbl per 1,000 ft; NULL when lateral_length_ft is missing or <= 0. |
| `state_code` | integer | State FIPS code - cohort key carried from curated.wells so aggregations avoid a re-JOIN. |
| `county_code` | character varying(5) | County FIPS code (5-char state+county), carried from curated.wells. |
| `county` | character varying(32) | County name, carried from curated.wells. |
| `basin` | character varying(36) | Novi basin label, carried from curated.wells. |
| `subbasin` | character varying(36) | Novi sub-basin label (DELAWARE / MIDLAND / CENTRAL BASIN PLATFORM), carried from curated.wells. |
| `formation` | character varying(64) | RAW Novi formation string (free-text UPPERCASE, e.g. SPRABERRY - no Y). For grouping/filtering use formation_blueox (via curated.wells_enriched), never this column. |
| `lateral_length_ft` | integer | Completed lateral length, ft, from curated.wells; the denominator of every per-1,000-ft column. |
| `first_production_date` | date | Well-level first production date, from curated.wells. |
| `first_completion_date` | date | Well-level first completion date, from curated.wells; basis for the vintage columns. |
| `first_completion_year` | integer | Calendar year of first_completion_date. |
| `completion_vintage_bucket` | text | Completion vintage cohort bucket: pre-2017 / 2017-2019 / 2020-2022 / 2023+; NULL when first_completion_date is NULL. |
| `lateral_length_class` | text | Lateral length bucket, ft: <5000 / 5000-7499 / 7500-9999 / 10000-14999 / 15000+; NULL when lateral_length_ft is missing or <= 0. |

### `curated.reconciled_inventory` (materialized view)

Novi PUD inventory reconciled against producing curated wells by co-extent overlap + same (corrected) formation_blueox-or-depth + TVD consistency. status in (realized_drift, realized_phantom, remaining_pud, conflict): realized is split by the realizing well's vintage — drift = online after the 3Q25 vintage (real PUD->PDP), phantom = online before it (Novi listed an already-drilled slot). matched_api10 / match_overlap / matched_first_prod record the realizing well; matched_survey_planned flags realizations resting on a provisional permit survey (mostly NM). Keyed on stick_id. net_new_pdp (producing wells with no PUD) is curated.net_new_pdp (sql/25). Refresh as wells come online.

~131,465 rows | quarterly (Novi intel reload chain) | reads: `curated.formation_blueox_tvd`, `curated.intel_formation_blueox`, `curated.intel_locations`, `curated.producing_reference` | consumers: narvi remaining inventory, erebor recon status

| column | type | description |
|---|---|---|
| `stick_id` | bigint | Novi PUD stick id (curated.intel_locations.stick_id, category PUD only); unique key. |
| `basin_blueox` | text | Basin slug: delaware or midland. |
| `formation_blueox` | text | Blue Ox bench code of the PUD (from curated.intel_formation_blueox); the same-bench test of the match. |
| `matched_api10` | character varying | api10 of the best-overlap producing well realizing this PUD; NULL when no producing lateral covers > 5%. |
| `matched_survey_planned` | boolean | TRUE = the realizing well is still on a pre-drill (permit) directional survey, so the TVD confirmation is provisional (mostly NM); recheck when the actual survey files. |
| `match_overlap` | numeric | Fraction (0-1) of the PUD lateral lying inside the best producing well's +/-150 ft corridor -- co-extent overlap, NOT min-distance. >= 0.5 realizes the PUD. |
| `n_overlapping` | bigint | Count of producing wells each covering >= 50% of the PUD; >= 2 forces status = conflict (re-frac / ambiguous). |
| `matched_first_prod` | date | First production date of the realizing well; splits realized into drift (after the Novi vintage) vs phantom (before it). |
| `status` | text | Reconciliation status: remaining_pud + conflict = the DRILLABLE remaining inventory; realized_drift (drilled since the Novi vintage) and realized_phantom (already drilled before it) are NOT drillable. Producers Novi missed are the reverse pass, curated.net_new_pdp. |

### `curated.type_curve_cohorts` (materialized view)

Pre-aggregated type-curve cohorts over production_normalized: one row per (state_code, county_code, formation, completion_vintage_bucket, months_on_production), MoP 1-240. Percentiles are STATISTICAL orientation (p10 = low tail), opposite of SPE P10=high. Nightly etl.refresh.

~175,644 rows | nightly (etl.refresh, 7/10) | reads: `curated.production_normalized` | consumers: legacy delaware_basin_eval

| column | type | description |
|---|---|---|
| `state_code` | integer | Cohort key: state FIPS code. |
| `county_code` | character varying(5) | Cohort key: county FIPS code (5-char state+county). |
| `formation` | character varying(64) | Cohort key: RAW Novi formation string (free-text) - NOT formation_blueox; blueox-grain cohorts must be computed upstream via wells_enriched. |
| `completion_vintage_bucket` | text | Cohort key: completion vintage bucket (pre-2017 / 2017-2019 / 2020-2022 / 2023+). |
| `months_on_production` | integer | Cohort key: months since first production, 1-indexed; capped at 1-240 (20 yr) - beyond that samples are too sparse for fitting. |
| `well_months` | bigint | Sample size: count of well-month rows aggregated in this cohort x MoP cell. |
| `well_count` | bigint | Sample size: distinct wells contributing at this MoP. Filter on this for a statistical floor (e.g. >= 10) before treating the cell as a type curve. |
| `p10_oil_per_day_per_1000ft` | double precision | Statistical 10th percentile of oil rate, bbl/d per 1,000 ft - the LOW tail here; SPE convention (P10 = high case) is the OPPOSITE orientation. |
| `p25_oil_per_day_per_1000ft` | double precision | Statistical 25th percentile of oil rate, bbl/d per 1,000 ft (low quartile). |
| `p50_oil_per_day_per_1000ft` | double precision | Median oil rate, bbl/d per 1,000 ft - the primary type-curve series. |
| `p75_oil_per_day_per_1000ft` | double precision | Statistical 75th percentile of oil rate, bbl/d per 1,000 ft (high quartile). |
| `p90_oil_per_day_per_1000ft` | double precision | Statistical 90th percentile of oil rate, bbl/d per 1,000 ft - the HIGH tail here; SPE convention (P90 = low case) is the OPPOSITE orientation. |
| `mean_oil_per_day_per_1000ft` | double precision | Arithmetic mean oil rate, bbl/d per 1,000 ft; skews above p50 in right-tailed cohorts. |
| `p10_boe_per_day_per_1000ft` | double precision | Statistical 10th percentile of BOE rate (oil + gas/6), bbl/d per 1,000 ft - LOW tail; opposite of SPE P10=high. |
| `p25_boe_per_day_per_1000ft` | double precision | Statistical 25th percentile of BOE rate, bbl/d per 1,000 ft. |
| `p50_boe_per_day_per_1000ft` | double precision | Median BOE rate (oil + gas/6), bbl/d per 1,000 ft - secondary series for gas-weighted cohorts. |
| `p75_boe_per_day_per_1000ft` | double precision | Statistical 75th percentile of BOE rate, bbl/d per 1,000 ft. |
| `p90_boe_per_day_per_1000ft` | double precision | Statistical 90th percentile of BOE rate, bbl/d per 1,000 ft - HIGH tail; opposite of SPE P90=low. |
| `mean_boe_per_day_per_1000ft` | double precision | Arithmetic mean BOE rate (oil + gas/6), bbl/d per 1,000 ft. |
| `p50_gas_per_day_per_1000ft` | double precision | Median gas rate, Mcf/d per 1,000 ft. Median only by design; other gas percentiles compute on the fly from production_normalized. |
| `p50_water_per_day_per_1000ft` | double precision | Median water rate, bbl/d per 1,000 ft. Median only by design. |
| `p50_cum_oil_per_1000ft` | double precision | Median cumulative oil at this MoP, bbl per 1,000 ft - cohort EUR sanity check (raw technical integral; no economic limit anywhere). |
| `p50_cum_boe_per_1000ft` | double precision | Median cumulative BOE (oil + gas/6) at this MoP, bbl per 1,000 ft. |

### `curated.wells` (materialized view)

One row per wellbore, keyed api10 (unique). Novi Wells + WellDetails + WellSpacing LEFT JOINed to the latest Enverus completion event via LEFT(api14, 10) = api10; per-column source precedence is Novi preferred, Enverus fallback unless noted. Permian-wide (~90k rows). Refreshed nightly by etl.refresh / curated.refresh_all() after the vendor loads.

~92,818 rows | nightly (etl.refresh, 1/10) | reads: `raw_enverus.wells`, `raw_novi.WellDetails`, `raw_novi.WellSpacing`, `raw_novi.Wells`

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | 10-digit API wellbore id (Novi); the universal well key across the suite. PK / unique index. Novi-Enverus join convention: LEFT(api14, 10) = api10. |
| `api14` | text | Formatted 14-digit API/UWI from the latest Enverus completion row; legacy cross-reference only (api10 is the key). NULL when no Enverus match. |
| `api14_unformatted` | text | Digits-only Enverus 14-digit API; LEFT(api14_unformatted, 10) is the join key back to api10. |
| `enverus_wellid` | bigint | Enverus WellID of the matched wellbore; NULL when the well has no Enverus row. |
| `enverus_latest_completionid` | bigint | Enverus CompletionID of the latest completion event per wellbore (DISTINCT ON api10 ordered by completiondate DESC). |
| `well_name` | character varying | Well name; Novi WellDetails preferred, then Novi Wells, then Enverus. |
| `well_pad_id` | text | Enverus WellPadID grouping wells drilled from a shared pad; NULL without an Enverus match. |
| `current_operator` | character varying(64) | Current operator (Novi authoritative; tracks operator changes across A&D). |
| `original_operator` | character varying(64) | Operator at drill time (Novi). |
| `operator_entity` | character varying(64) | Parent operator entity (Novi CurrentOperatorEntity) for corporate-level rollups across subsidiary names. |
| `state` | character varying(16) | State (Novi WellDetails preferred, Novi Wells fallback). |
| `state_code` | integer | State FIPS code (Novi); 42 = TX, 30 = NM. |
| `county` | character varying(32) | County name, title-cased per Novi convention (e.g. Reeves) - note Enverus filter values are UPPERCASE (LOVING), so do not reuse these strings in Enverus API filters. |
| `county_unique` | character varying(32) | County name disambiguated across states (Novi CountyUnique). |
| `county_code` | character varying(5) | 5-digit county FIPS code (Novi); a primary cohort key downstream. |
| `basin` | character varying(36) | Novi basin classification (Novi WellDetails preferred). Vendor taxonomy; the standardized token is basin_blueox in wells_enriched. |
| `subbasin` | character varying(36) | Novi sub-basin (Delaware / Midland / Central Basin Platform ...); the primary input for resolving basin_blueox. |
| `env_region` | text | Enverus ENVRegion (warehouse scope filter is envregion = PERMIAN). |
| `env_basin` | text | Enverus ENVBasin - sub-basin grain (DELAWARE / MIDLAND / PERMIAN OTHER; no umbrella PERMIAN value). Fallback for basin_blueox resolution. |
| `env_play` | text | Enverus ENVPlay classification (vendor taxonomy, UPPERCASE). |
| `env_sub_play` | text | Enverus ENVSubPlay classification (vendor taxonomy, UPPERCASE). |
| `env_interval` | text | Enverus ENVInterval landing-interval call from their structure model (UPPERCASE); the substitute source for formation_blueox when the Novi formation is coarse/unreliable. |
| `section` | integer | Land-survey section number (Novi WellDetails); populated for both NM PLSS and TX survey systems. |
| `township` | character varying(5) | PLSS Township (Novi WellDetails); NM-style land subdivision, empty in TX. |
| `range_` | character varying(5) | PLSS Range (NM-style land subdivision). Trailing underscore avoids the contextually-reserved SQL keyword. Populated only for PLSS states; ~0% in TX, ~20% Permian-wide. |
| `tx_block` | character varying(36) | TX Spanish-grant land system: Block (Novi WellDetails); NULL for NM/PLSS wells. |
| `tx_survey` | character varying(36) | TX Spanish-grant land system: Survey name (Novi WellDetails); NULL for NM/PLSS wells. |
| `tx_abstract` | character varying(36) | TX Spanish-grant land system: Abstract number (Novi WellDetails); NULL for NM/PLSS wells. |
| `surface_lat` | double precision | Surface hole latitude, WGS84 deg (Novi preferred, Enverus fallback). |
| `surface_lon` | double precision | Surface hole longitude, WGS84 deg (Novi preferred, Enverus fallback). |
| `bhl_lat` | double precision | Bottom hole latitude, WGS84 deg (Novi preferred, Enverus fallback). |
| `bhl_lon` | double precision | Bottom hole longitude, WGS84 deg (Novi preferred, Enverus fallback). |
| `landing_point_lat` | double precision | Landing point latitude, WGS84 deg (Novi WellDetails only; Enverus has no LP). |
| `landing_point_lon` | double precision | Landing point longitude, WGS84 deg (Novi WellDetails only). |
| `midpoint_lat` | double precision | Lateral midpoint latitude, WGS84 deg (Novi WellDetails only). |
| `midpoint_lon` | double precision | Lateral midpoint longitude, WGS84 deg (Novi WellDetails only). |
| `wellstick_geom` | geometry | LINESTRING (4326) built from the four Novi locations Surface Hole -> Landing Point -> Midpoint -> Bottom Hole, in natural traverse order. NULL points are skipped; NULL if fewer than two valid points. Cast to geography only via the sql/26 expression GiST indexes. |
| `formation` | character varying(64) | Novi formation call (WellDetails preferred, Wells fallback). RAW FREE-TEXT, inconsistent granularity - never group or filter on this; use formation_blueox (wells_enriched). |
| `reported_formation` | character varying(64) | Operator-reported formation from the regulatory filing (Novi); free-text, often coarser than the model call. |
| `grid_formation` | character varying(64) | Formation implied by Novi structure grids at the landing depth (Novi); free-text, model-derived. |
| `directional_survey_is_planned` | boolean | TRUE = the directional survey is the operator's pre-drill PLAN, not the actual post-drill survey. Both Novi and Enverus land the well off that plan, so formation / env_interval are likely misassigned; ~46% of NM wells. Self-corrects when the actual survey is filed. |
| `tvd_ft` | integer | True vertical depth, ft (Novi WellDetails > Novi Wells > Enverus). Exact multiples of 100 ft are usually permit/plan depths, not real landings - see curated.formation_blueox_tvd. |
| `md_ft` | integer | Measured depth, ft (Novi preferred, Enverus fallback). |
| `lateral_length_ft` | integer | Completed lateral length, ft (Novi preferred, Enverus fallback); the denominator for every per-1000-ft normalization downstream. |
| `wellbore_lateral_length_ft` | integer | Novi WellboreLateralLength, ft - geometric wellbore lateral, as distinct from the completed lateral_length_ft. |
| `enverus_trajectory` | text | Enverus Trajectory string (e.g. HORIZONTAL); fallback source for wells_enriched.is_horizontal. |
| `novi_slant_calculated` | character varying(32) | Novi SlantCalculated slant string (H... = horizontal); preferred source for wells_enriched.is_horizontal. |
| `spud_date` | date | Spud date (Novi preferred, Enverus fallback). |
| `drilling_end_date` | date | Drilling end (rig release) date (Novi preferred, Enverus fallback). |
| `first_completion_date` | date | First completion date (Novi preferred, Enverus fallback); drives completion_vintage_bucket. |
| `first_production_date` | date | First production date (Novi-calculated preferred, Enverus fallback). NULL = not yet producing; the producing_reference / reconciliation population keys on NOT NULL here. |
| `has_accurate_first_prod_date` | boolean | Novi confidence flag that first_production_date is accurate rather than inferred. |
| `last_reported_month` | date | Most recent month with reported production (Novi preferred, Enverus fallback). |
| `plugged_date` | date | Plug date (Novi preferred, Enverus fallback); NULL = not plugged. |
| `proppant_lbs` | bigint | Total proppant placed, lbs (Enverus preferred; Novi FirstCompletionProppantMass fallback). |
| `fluid_bbl` | bigint | Total frac fluid pumped, bbl (Enverus preferred; Novi FirstCompletionFluidVolume reported in gallons is divided by 42 in the fallback). |
| `frac_stages` | integer | Frac stage count (Enverus preferred, Novi FirstCompletionStages fallback). |
| `proppant_lbs_per_ft` | real | Proppant intensity, lbs per lateral ft (Enverus only; no Novi fallback). |
| `fluid_bbl_per_ft` | real | Fluid intensity, bbl per lateral ft (Enverus only; no Novi fallback). |
| `proppant_lbs_per_gal` | real | Proppant loading, lbs per gallon of fluid (Enverus preferred, Novi fallback). |
| `avg_stage_spacing_ft` | integer | Average frac stage spacing, ft (Enverus preferred, Novi fallback). |
| `clusters_per_stage` | integer | Perforation clusters per frac stage (Enverus). |
| `clusters_per_1000ft` | integer | Perforation clusters per 1000 ft of lateral (Enverus). |
| `soak_time_days` | integer | Soak time, days, between stimulation and turn-in-line (Novi WellDetails SoakTimeDays). |
| `cum_12m_oil_bbl` | integer | Cumulative oil through production month 12, bbl (Novi WellDetails pass-through). |
| `cum_12m_gas_mcf` | integer | Cumulative gas through production month 12, Mcf (Novi WellDetails pass-through). |
| `cum_12m_water_bbl` | integer | Cumulative water through production month 12, bbl (Novi WellDetails pass-through). |
| `cum_12m_boe` | integer | Cumulative BOE through production month 12, bbl at 6:1 gas conversion (Novi WellDetails pass-through). |
| `cum_24m_oil_bbl` | integer | Cumulative oil through production month 24, bbl (Novi WellDetails pass-through). |
| `cum_24m_gas_mcf` | integer | Cumulative gas through production month 24, Mcf (Novi WellDetails pass-through). |
| `cum_24m_water_bbl` | integer | Cumulative water through production month 24, bbl (Novi WellDetails pass-through). |
| `cum_24m_boe` | integer | Cumulative BOE through production month 24, bbl at 6:1 (Novi WellDetails pass-through). |
| `cum_life_oil_bbl` | integer | Life-to-date cumulative oil, bbl (Novi WellDetails pass-through). |
| `cum_life_gas_mcf` | integer | Life-to-date cumulative gas, Mcf (Novi WellDetails pass-through). |
| `cum_life_water_bbl` | integer | Life-to-date cumulative water, bbl (Novi WellDetails pass-through). |
| `cum_life_boe` | integer | Life-to-date cumulative BOE, bbl at 6:1 (Novi WellDetails pass-through). |
| `cum_life_gor` | double precision | Life-to-date gas-oil ratio, Mcf/bbl (= cum_life_gas_mcf / cum_life_oil_bbl; multiply by 1000 for scf/bbl). Novi WellDetails CumLifeGOR pass-through. |
| `eur_20yr_oil_bbl` | integer | Novi-forecast oil EUR at a 20-yr horizon, bbl (WellDetails pass-through). Vendor screen; the suite's EUR of record is the raw 50-yr integral fit in anduin. |
| `eur_20yr_gas_mcf` | integer | Novi-forecast gas EUR at a 20-yr horizon, Mcf (WellDetails pass-through); vendor screen. |
| `eur_20yr_water_bbl` | integer | Novi-forecast water EUR at a 20-yr horizon, bbl (WellDetails pass-through); vendor screen. |
| `eur_20yr_boe` | integer | Novi-forecast BOE EUR at a 20-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor screen. |
| `eur_30yr_oil_bbl` | integer | Novi-forecast oil EUR at a 30-yr horizon, bbl (WellDetails pass-through); vendor screen. |
| `eur_30yr_gas_mcf` | integer | Novi-forecast gas EUR at a 30-yr horizon, Mcf (WellDetails pass-through); vendor screen. |
| `eur_30yr_water_bbl` | integer | Novi-forecast water EUR at a 30-yr horizon, bbl (WellDetails pass-through); vendor screen. |
| `eur_30yr_boe` | integer | Novi-forecast BOE EUR at a 30-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor screen. |
| `eur_50yr_oil_bbl` | integer | Novi-forecast oil EUR at a 50-yr horizon, bbl (WellDetails pass-through). Same horizon as the suite convention, but this is Novi's number, not the anduin fit. |
| `eur_50yr_gas_mcf` | integer | Novi-forecast gas EUR at a 50-yr horizon, Mcf (WellDetails pass-through); vendor number, not the anduin fit. |
| `eur_50yr_water_bbl` | integer | Novi-forecast water EUR at a 50-yr horizon, bbl (WellDetails pass-through); vendor number, not the anduin fit. |
| `eur_50yr_boe` | integer | Novi-forecast BOE EUR at a 50-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor number, not the anduin fit. |
| `peak_month_oil` | integer | Month-on-production index of the peak OIL month (Novi). Streams peak independently - gas typically ~4 months after oil, water in flowback - so each stream anchors on its own peak. |
| `peak_month_gas` | integer | Month-on-production index of the peak GAS month (Novi); commonly ~4 months after the oil peak - never force gas to the oil peak. |
| `peak_month_water` | integer | Month-on-production index of the peak WATER month (Novi); typically month 1 (flowback). |
| `peak_month_boe` | integer | Month-on-production index of the peak BOE month (Novi). |
| `peak_oil_rate_bblpd` | integer | Oil rate in the peak oil month, bbl/d (Novi PeakMonthOilRate pass-through). |
| `peak_gas_rate_mcfpd` | integer | Gas rate in the peak gas month, Mcf/d (Novi PeakMonthGasRate pass-through). |
| `peak_water_rate_bblpd` | integer | Water rate in the peak water month, bbl/d (Novi PeakMonthWaterRate pass-through). |
| `peak_boe_rate_boepd` | integer | BOE rate in the peak BOE month, BOE/d at 6:1 (Novi PeakMonthBOERate pass-through). |
| `months_to_peak_production` | bigint | Months from first production to peak production (Enverus MonthsToPeakProduction). |
| `closest_well_xy_ft` | double precision | Horizontal (XY) distance to the closest neighbouring well, ft (Novi WellSpacing). |
| `wells_in_radius` | integer | Count of wells inside Novi WellSpacing's neighbourhood search radius. |
| `closest_two_avg_xy_ft` | double precision | Mean XY distance to the two closest neighbouring wells, ft (Novi WellSpacing). |
| `is_child` | boolean | Novi WellSpacing flag: TRUE = child well, offset to at least one pre-existing (parent) producer at drill time. |
| `parent_count` | integer | Number of parent wells already producing in the neighbourhood when this well came online (Novi WellSpacing). |
| `boundedness_score` | bigint | Novi WellSpacing boundedness score - vendor score of how bounded the well is by neighbours; a rank, not footage. |
| `well_status` | text | Well status (Novi preferred, Enverus ENVWellStatus fallback); vendor strings, not standardized. |
| `well_type` | character varying | Well type, e.g. OIL / GAS (Novi preferred, Enverus ENVWellType fallback). |
| `has_production_sharing` | boolean | Novi flag: TRUE = production is shared/allocated across wells (allocation reporting), so per-well monthly volumes are allocated estimates, not measured. |
| `novi_synthetic_api` | boolean | TRUE = Novi minted a synthetic api10 (no state-assigned API on file yet); the key can change when the real API is assigned. |

### `curated.wells_enriched` (view)

Analytics view over curated.wells (one row per api10): joins the Blue Ox formation mapping (curated.formation_blueox) with the sql/23 TVD correction applied on top, and adds vintage, lateral-length-class, horizontal-flag and per-stage intensity derivations. Regular view - no refresh; current as of the nightly matview refreshes it reads.

~0 rows | n/a (plain view, always current) | reads: `curated.formation_blueox`, `curated.formation_blueox_tvd`, `curated.wells` | consumers: anduin sync, erebor, narvi, ad-hoc analysis

| column | type | description |
|---|---|---|
| `api10` | character varying(32) | 10-digit API wellbore id (Novi); the universal well key across the suite. PK / unique index. Novi-Enverus join convention: LEFT(api14, 10) = api10. |
| `api14` | text | Formatted 14-digit API/UWI from the latest Enverus completion row; legacy cross-reference only (api10 is the key). NULL when no Enverus match. |
| `api14_unformatted` | text | Digits-only Enverus 14-digit API; LEFT(api14_unformatted, 10) is the join key back to api10. |
| `enverus_wellid` | bigint | Enverus WellID of the matched wellbore; NULL when the well has no Enverus row. |
| `enverus_latest_completionid` | bigint | Enverus CompletionID of the latest completion event per wellbore (DISTINCT ON api10 ordered by completiondate DESC). |
| `well_name` | character varying | Well name; Novi WellDetails preferred, then Novi Wells, then Enverus. |
| `well_pad_id` | text | Enverus WellPadID grouping wells drilled from a shared pad; NULL without an Enverus match. |
| `current_operator` | character varying(64) | Current operator (Novi authoritative; tracks operator changes across A&D). |
| `original_operator` | character varying(64) | Operator at drill time (Novi). |
| `operator_entity` | character varying(64) | Parent operator entity (Novi CurrentOperatorEntity) for corporate-level rollups across subsidiary names. |
| `state` | character varying(16) | State (Novi WellDetails preferred, Novi Wells fallback). |
| `state_code` | integer | State FIPS code (Novi); 42 = TX, 30 = NM. |
| `county` | character varying(32) | County name, title-cased per Novi convention (e.g. Reeves) - note Enverus filter values are UPPERCASE (LOVING), so do not reuse these strings in Enverus API filters. |
| `county_unique` | character varying(32) | County name disambiguated across states (Novi CountyUnique). |
| `county_code` | character varying(5) | 5-digit county FIPS code (Novi); a primary cohort key downstream. |
| `basin` | character varying(36) | Novi basin classification (Novi WellDetails preferred). Vendor taxonomy; the standardized token is basin_blueox in wells_enriched. |
| `subbasin` | character varying(36) | Novi sub-basin (Delaware / Midland / Central Basin Platform ...); the primary input for resolving basin_blueox. |
| `env_region` | text | Enverus ENVRegion (warehouse scope filter is envregion = PERMIAN). |
| `env_basin` | text | Enverus ENVBasin - sub-basin grain (DELAWARE / MIDLAND / PERMIAN OTHER; no umbrella PERMIAN value). Fallback for basin_blueox resolution. |
| `env_play` | text | Enverus ENVPlay classification (vendor taxonomy, UPPERCASE). |
| `env_sub_play` | text | Enverus ENVSubPlay classification (vendor taxonomy, UPPERCASE). |
| `env_interval` | text | Enverus ENVInterval landing-interval call from their structure model (UPPERCASE); the substitute source for formation_blueox when the Novi formation is coarse/unreliable. |
| `section` | integer | Land-survey section number (Novi WellDetails); populated for both NM PLSS and TX survey systems. |
| `township` | character varying(5) | PLSS Township (Novi WellDetails); NM-style land subdivision, empty in TX. |
| `range_` | character varying(5) | PLSS Range (NM-style land subdivision). Trailing underscore avoids the contextually-reserved SQL keyword. Populated only for PLSS states; ~0% in TX, ~20% Permian-wide. |
| `tx_block` | character varying(36) | TX Spanish-grant land system: Block (Novi WellDetails); NULL for NM/PLSS wells. |
| `tx_survey` | character varying(36) | TX Spanish-grant land system: Survey name (Novi WellDetails); NULL for NM/PLSS wells. |
| `tx_abstract` | character varying(36) | TX Spanish-grant land system: Abstract number (Novi WellDetails); NULL for NM/PLSS wells. |
| `surface_lat` | double precision | Surface hole latitude, WGS84 deg (Novi preferred, Enverus fallback). |
| `surface_lon` | double precision | Surface hole longitude, WGS84 deg (Novi preferred, Enverus fallback). |
| `bhl_lat` | double precision | Bottom hole latitude, WGS84 deg (Novi preferred, Enverus fallback). |
| `bhl_lon` | double precision | Bottom hole longitude, WGS84 deg (Novi preferred, Enverus fallback). |
| `landing_point_lat` | double precision | Landing point latitude, WGS84 deg (Novi WellDetails only; Enverus has no LP). |
| `landing_point_lon` | double precision | Landing point longitude, WGS84 deg (Novi WellDetails only). |
| `midpoint_lat` | double precision | Lateral midpoint latitude, WGS84 deg (Novi WellDetails only). |
| `midpoint_lon` | double precision | Lateral midpoint longitude, WGS84 deg (Novi WellDetails only). |
| `wellstick_geom` | geometry | LINESTRING (4326) built from the four Novi locations Surface Hole -> Landing Point -> Midpoint -> Bottom Hole, in natural traverse order. NULL points are skipped; NULL if fewer than two valid points. Cast to geography only via the sql/26 expression GiST indexes. |
| `formation` | character varying(64) | Novi formation call (WellDetails preferred, Wells fallback). RAW FREE-TEXT, inconsistent granularity - never group or filter on this; use formation_blueox (wells_enriched). |
| `reported_formation` | character varying(64) | Operator-reported formation from the regulatory filing (Novi); free-text, often coarser than the model call. |
| `grid_formation` | character varying(64) | Formation implied by Novi structure grids at the landing depth (Novi); free-text, model-derived. |
| `directional_survey_is_planned` | boolean | TRUE = the directional survey is the operator's pre-drill PLAN, not the actual post-drill survey. Both Novi and Enverus land the well off that plan, so formation / env_interval are likely misassigned; ~46% of NM wells. Self-corrects when the actual survey is filed. |
| `tvd_ft` | integer | True vertical depth, ft (Novi WellDetails > Novi Wells > Enverus). Exact multiples of 100 ft are usually permit/plan depths, not real landings - see curated.formation_blueox_tvd. |
| `md_ft` | integer | Measured depth, ft (Novi preferred, Enverus fallback). |
| `lateral_length_ft` | integer | Completed lateral length, ft (Novi preferred, Enverus fallback); the denominator for every per-1000-ft normalization downstream. |
| `wellbore_lateral_length_ft` | integer | Novi WellboreLateralLength, ft - geometric wellbore lateral, as distinct from the completed lateral_length_ft. |
| `enverus_trajectory` | text | Enverus Trajectory string (e.g. HORIZONTAL); fallback source for wells_enriched.is_horizontal. |
| `novi_slant_calculated` | character varying(32) | Novi SlantCalculated slant string (H... = horizontal); preferred source for wells_enriched.is_horizontal. |
| `spud_date` | date | Spud date (Novi preferred, Enverus fallback). |
| `drilling_end_date` | date | Drilling end (rig release) date (Novi preferred, Enverus fallback). |
| `first_completion_date` | date | First completion date (Novi preferred, Enverus fallback); drives completion_vintage_bucket. |
| `first_production_date` | date | First production date (Novi-calculated preferred, Enverus fallback). NULL = not yet producing; the producing_reference / reconciliation population keys on NOT NULL here. |
| `has_accurate_first_prod_date` | boolean | Novi confidence flag that first_production_date is accurate rather than inferred. |
| `last_reported_month` | date | Most recent month with reported production (Novi preferred, Enverus fallback). |
| `plugged_date` | date | Plug date (Novi preferred, Enverus fallback); NULL = not plugged. |
| `proppant_lbs` | bigint | Total proppant placed, lbs (Enverus preferred; Novi FirstCompletionProppantMass fallback). |
| `fluid_bbl` | bigint | Total frac fluid pumped, bbl (Enverus preferred; Novi FirstCompletionFluidVolume reported in gallons is divided by 42 in the fallback). |
| `frac_stages` | integer | Frac stage count (Enverus preferred, Novi FirstCompletionStages fallback). |
| `proppant_lbs_per_ft` | real | Proppant intensity, lbs per lateral ft (Enverus only; no Novi fallback). |
| `fluid_bbl_per_ft` | real | Fluid intensity, bbl per lateral ft (Enverus only; no Novi fallback). |
| `proppant_lbs_per_gal` | real | Proppant loading, lbs per gallon of fluid (Enverus preferred, Novi fallback). |
| `avg_stage_spacing_ft` | integer | Average frac stage spacing, ft (Enverus preferred, Novi fallback). |
| `clusters_per_stage` | integer | Perforation clusters per frac stage (Enverus). |
| `clusters_per_1000ft` | integer | Perforation clusters per 1000 ft of lateral (Enverus). |
| `soak_time_days` | integer | Soak time, days, between stimulation and turn-in-line (Novi WellDetails SoakTimeDays). |
| `cum_12m_oil_bbl` | integer | Cumulative oil through production month 12, bbl (Novi WellDetails pass-through). |
| `cum_12m_gas_mcf` | integer | Cumulative gas through production month 12, Mcf (Novi WellDetails pass-through). |
| `cum_12m_water_bbl` | integer | Cumulative water through production month 12, bbl (Novi WellDetails pass-through). |
| `cum_12m_boe` | integer | Cumulative BOE through production month 12, bbl at 6:1 gas conversion (Novi WellDetails pass-through). |
| `cum_24m_oil_bbl` | integer | Cumulative oil through production month 24, bbl (Novi WellDetails pass-through). |
| `cum_24m_gas_mcf` | integer | Cumulative gas through production month 24, Mcf (Novi WellDetails pass-through). |
| `cum_24m_water_bbl` | integer | Cumulative water through production month 24, bbl (Novi WellDetails pass-through). |
| `cum_24m_boe` | integer | Cumulative BOE through production month 24, bbl at 6:1 (Novi WellDetails pass-through). |
| `cum_life_oil_bbl` | integer | Life-to-date cumulative oil, bbl (Novi WellDetails pass-through). |
| `cum_life_gas_mcf` | integer | Life-to-date cumulative gas, Mcf (Novi WellDetails pass-through). |
| `cum_life_water_bbl` | integer | Life-to-date cumulative water, bbl (Novi WellDetails pass-through). |
| `cum_life_boe` | integer | Life-to-date cumulative BOE, bbl at 6:1 (Novi WellDetails pass-through). |
| `cum_life_gor` | double precision | Life-to-date gas-oil ratio, Mcf/bbl (= cum_life_gas_mcf / cum_life_oil_bbl; multiply by 1000 for scf/bbl). Novi WellDetails CumLifeGOR pass-through. |
| `eur_20yr_oil_bbl` | integer | Novi-forecast oil EUR at a 20-yr horizon, bbl (WellDetails pass-through). Vendor screen; the suite's EUR of record is the raw 50-yr integral fit in anduin. |
| `eur_20yr_gas_mcf` | integer | Novi-forecast gas EUR at a 20-yr horizon, Mcf (WellDetails pass-through); vendor screen. |
| `eur_20yr_water_bbl` | integer | Novi-forecast water EUR at a 20-yr horizon, bbl (WellDetails pass-through); vendor screen. |
| `eur_20yr_boe` | integer | Novi-forecast BOE EUR at a 20-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor screen. |
| `eur_30yr_oil_bbl` | integer | Novi-forecast oil EUR at a 30-yr horizon, bbl (WellDetails pass-through); vendor screen. |
| `eur_30yr_gas_mcf` | integer | Novi-forecast gas EUR at a 30-yr horizon, Mcf (WellDetails pass-through); vendor screen. |
| `eur_30yr_water_bbl` | integer | Novi-forecast water EUR at a 30-yr horizon, bbl (WellDetails pass-through); vendor screen. |
| `eur_30yr_boe` | integer | Novi-forecast BOE EUR at a 30-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor screen. |
| `eur_50yr_oil_bbl` | integer | Novi-forecast oil EUR at a 50-yr horizon, bbl (WellDetails pass-through). Same horizon as the suite convention, but this is Novi's number, not the anduin fit. |
| `eur_50yr_gas_mcf` | integer | Novi-forecast gas EUR at a 50-yr horizon, Mcf (WellDetails pass-through); vendor number, not the anduin fit. |
| `eur_50yr_water_bbl` | integer | Novi-forecast water EUR at a 50-yr horizon, bbl (WellDetails pass-through); vendor number, not the anduin fit. |
| `eur_50yr_boe` | integer | Novi-forecast BOE EUR at a 50-yr horizon, bbl at 6:1 (WellDetails pass-through); vendor number, not the anduin fit. |
| `peak_month_oil` | integer | Month-on-production index of the peak OIL month (Novi). Streams peak independently - gas typically ~4 months after oil, water in flowback - so each stream anchors on its own peak. |
| `peak_month_gas` | integer | Month-on-production index of the peak GAS month (Novi); commonly ~4 months after the oil peak - never force gas to the oil peak. |
| `peak_month_water` | integer | Month-on-production index of the peak WATER month (Novi); typically month 1 (flowback). |
| `peak_month_boe` | integer | Month-on-production index of the peak BOE month (Novi). |
| `peak_oil_rate_bblpd` | integer | Oil rate in the peak oil month, bbl/d (Novi PeakMonthOilRate pass-through). |
| `peak_gas_rate_mcfpd` | integer | Gas rate in the peak gas month, Mcf/d (Novi PeakMonthGasRate pass-through). |
| `peak_water_rate_bblpd` | integer | Water rate in the peak water month, bbl/d (Novi PeakMonthWaterRate pass-through). |
| `peak_boe_rate_boepd` | integer | BOE rate in the peak BOE month, BOE/d at 6:1 (Novi PeakMonthBOERate pass-through). |
| `months_to_peak_production` | bigint | Months from first production to peak production (Enverus MonthsToPeakProduction). |
| `closest_well_xy_ft` | double precision | Horizontal (XY) distance to the closest neighbouring well, ft (Novi WellSpacing). |
| `wells_in_radius` | integer | Count of wells inside Novi WellSpacing's neighbourhood search radius. |
| `closest_two_avg_xy_ft` | double precision | Mean XY distance to the two closest neighbouring wells, ft (Novi WellSpacing). |
| `is_child` | boolean | Novi WellSpacing flag: TRUE = child well, offset to at least one pre-existing (parent) producer at drill time. |
| `parent_count` | integer | Number of parent wells already producing in the neighbourhood when this well came online (Novi WellSpacing). |
| `boundedness_score` | bigint | Novi WellSpacing boundedness score - vendor score of how bounded the well is by neighbours; a rank, not footage. |
| `well_status` | text | Well status (Novi preferred, Enverus ENVWellStatus fallback); vendor strings, not standardized. |
| `well_type` | character varying | Well type, e.g. OIL / GAS (Novi preferred, Enverus ENVWellType fallback). |
| `has_production_sharing` | boolean | Novi flag: TRUE = production is shared/allocated across wells (allocation reporting), so per-well monthly volumes are allocated estimates, not measured. |
| `novi_synthetic_api` | boolean | TRUE = Novi minted a synthetic api10 (no state-assigned API on file yet); the key can change when the real API is assigned. |
| `formation_blueox` | text | Blue Ox canonical bench code WITH the TVD-outlier correction applied (sql/23 flips gross depth outliers). THE grouping/filter key - never raw formation. NULL = unmapped (report as (unmapped)); OTHER = CBP conventional shelf by design. |
| `formation_blueox_base` | text | Pre-correction Blue Ox code straight from curated.formation_blueox; kept for audit of TVD-corrected flips. Differs from formation_blueox only when formation_blueox_tvd_corrected. |
| `formation_blueox_raw` | character varying | Raw formation string that fed the crosswalk (Novi formation or Enverus ENVInterval, per the sql/16 precedence rule). |
| `formation_blueox_source` | text | Winning source for the bench code: novi, enverus, or tvd_corrected when the sql/23 depth audit overrode both. |
| `basin_blueox` | text | Blue Ox basin token: delaware, midland or cbp (from Novi Subbasin, Enverus ENVBasin fallback); NULL when the well is outside all three. |
| `formation_blueox_is_mapped` | boolean | TRUE = the raw string matched ref.formation_crosswalk. FALSE = genuine crosswalk gap in delaware/midland, but intentional OTHER bucketing in cbp (not a gap). |
| `formation_blueox_tvd_corrected` | boolean | TRUE = curated.formation_blueox_tvd flipped the bench because the well is a gross local depth outlier (~0.4% of producers); base value preserved in formation_blueox_base. |
| `first_completion_year` | integer | Calendar year of first_completion_date. |
| `first_completion_quarter` | integer | Calendar quarter (1-4) of first_completion_date. |
| `first_production_year` | integer | Calendar year of first_production_date. |
| `completion_vintage_bucket` | text | Completion vintage cohort: pre-2017 / 2017-2019 / 2020-2022 / 2023+ (from first_completion_date); a standard type-curve cohort key. |
| `lateral_length_class` | text | Lateral length bin, ft: <5000 / 5000-7499 / 7500-9999 / 10000-14999 / 15000+; NULL when lateral_length_ft is missing or non-positive. |
| `is_horizontal` | boolean | TRUE when the slant string starts with H (Novi SlantCalculated preferred, Enverus trajectory fallback); NULL when both sources are missing. |
| `stages_per_1000ft` | numeric | Frac stages per 1000 ft of lateral (frac_stages * 1000 / lateral_length_ft); NULL when either input is missing/non-positive. |
| `proppant_lbs_per_stage` | numeric | Proppant per frac stage, lbs (proppant_lbs / frac_stages). |
| `fluid_bbl_per_stage` | numeric | Frac fluid per stage, bbl (fluid_bbl / frac_stages). |
| `has_completion_intensity` | boolean | TRUE when proppant_lbs, fluid_bbl, frac_stages and a positive lateral_length_ft are all populated - the cohort filter for completion-intensity studies. |

## Schema `meta`

### `meta.etl_log` (table)

One row per ETL step run (source x table_name), written by etl/db.py log_etl_run: status running/success/failed, row counts, timings. Doubles as the incremental cursor for Enverus pulls (updateddate > last success) and the curated refresh gate.

~323 rows | continuous (ETL bookkeeping)

| column | type | description |
|---|---|---|
| `etl_log_id` | bigint |  |
| `source` | text |  |
| `table_name` | text |  |
| `run_started_at` | timestamp with time zone |  |
| `run_finished_at` | timestamp with time zone |  |
| `status` | text |  |
| `rows_inserted` | bigint |  |
| `rows_updated` | bigint |  |
| `rows_deleted` | bigint |  |
| `bytes_downloaded` | bigint |  |
| `export_date` | text |  |
| `error_message` | text |  |

### `meta.intel_report_watermark` (table)

Collections seen in the Novi INTEL share (NOVI_INTEL.SOURCE). NULL acknowledged_at = new report awaiting the manual quarterly reload. Written by etl/intel_sf/detect.py (nightly) and scripts/load_intel_sf.py.

~0 rows | continuous (ETL bookkeeping)

| column | type | description |
|---|---|---|
| `report_name` | text |  |
| `report_family` | text |  |
| `first_seen_at` | timestamp with time zone |  |
| `acknowledged_at` | timestamp with time zone |  |

