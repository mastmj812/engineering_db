"""Snowflake SQL that presents Novi v4 in the six v3 `raw_novi` table shapes.

Pure string builders, no connection. Every output column is aliased with the exact v3 column
name (quoted, so the case survives), so the loader can COPY a result set straight into a table
of the v3 shape and `sql/04`, `05`, `10`, `49`, `64` read it unchanged.

Conventions fixed here (docs/novi_v4_parity.md):

- **Scope** = wellbores whose `WELLBORE.SOURCE_ID` is Novi's `US_Horizontals` export set. That is
  exactly the v3 us-horizontals population (95,990 wells on 2026-11-19). `DIRECTION` alone is
  wider (766 more wells from `US_Onshore`).
- **Key**: `API10` = `WELLBORE.NATIVE_ID`. Every Permian wellbore is NATIVE_ID_TYPE 'API10'.
- **Per-day rates** are not shipped by v4. They are computed as Novi's v3 did:
  `round(monthly volume / days in the calendar month, 1)`, no first-month exception
  (parity study section 4.3: reproduced v3 on 100 % of rows checked).
- **Cumulative columns** on production are rebuilt as running sums per well, so a changed month
  means the whole well is re-pulled (see `sync`).
- **Forecast**: v4 holds forecast rows only (`IsForecasted` = TRUE on every row). v4 counts
  cumulative from the start of the forecast; v3 counted from first production, so the well's
  actual cumulative before its first forecast month is added back.
- Columns with no v4 source are simply absent from the SELECT; the target column stays NULL.
"""

from __future__ import annotations

import re

DB = "NOVI_DATA_ACCESS.NOVI_WELLS"

#: Novi's export set that defines the v3 us-horizontals population.
SCOPE_SOURCE_FILE = "US_Horizontals"

# v4 controlled vocabulary -> the v3 strings curated SQL and the apps compare against.
STATE_NAME = {"TX": "Texas", "NM": "New Mexico"}
STATE_CODE = {"TX": 42, "NM": 30}
WELL_STATUS = {
    "ACTIVE": "Active",
    "PERMIT_CANCELLED": "Permit Cancelled",
    "PERMIT_APPROVED": "Permit Approved",
    "INACTIVE": "Inactive",
    "PA": "P&A",
    "SPUD": "Spud",
    "COMPLETED": "Completed",
    "ABANDONED": "Abandoned",
    "DUC": "DUC",
    "PERMIT_SUBMITTED": "Permit Submitted",
    "UNKNOWN": "Unknown",
}
SLANT = {
    "HORIZONTAL": "Horizontal",
    "VERTICAL": "Vertical",
    "U_TURN_HORIZONTAL": "U-Turn (Horizontal)",
}

REPORTED_SLANT = {**SLANT, "DIRECTIONAL": "Directional"}

#: v3 sentinel for "no parent": v4 ships NULL on the same wells (parity study section 4.4).
PARENT_DAYS_ONLINE_NONE = -1

_API10_RE = re.compile(r"^\d{10}$")


def _lit(v: object) -> str:
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def case_map(expr: str, mapping: dict, *, passthrough: bool) -> str:
    """CASE over a v4 code. Unknown codes pass through as shipped (`passthrough`) so a new
    vendor value shows up in the data instead of vanishing, or become NULL when the target
    type cannot hold the raw code."""
    whens = " ".join(f"WHEN {_lit(k)} THEN {_lit(v)}" for k, v in mapping.items())
    return f"CASE {expr} {whens} ELSE {expr if passthrough else 'NULL'} END"


def _utc(expr: str) -> str:
    """A v4 stamp as naive UTC. The share's stamps are TIMESTAMP_LTZ and arrive in the session
    time zone (Pacific) with an offset; a Postgres `timestamp` column drops the offset on input,
    which would store Pacific wall time. v3 `ModifiedAt` is naive UTC."""
    return f"CONVERT_TIMEZONE('UTC', {expr})::TIMESTAMP_NTZ"


def _int(expr: str) -> str:
    return f"ROUND({expr})::INTEGER"


SCOPE_CTE = f"""scope AS (
    SELECT wb.WELLBORE_KEY, wb.WELL_KEY, wb.NATIVE_ID AS API10
    FROM {DB}.WELLBORE wb
    JOIN {DB}.SOURCE s ON s.SOURCE_ID = wb.SOURCE_ID
    WHERE s.SOURCE_FILE = {_lit(SCOPE_SOURCE_FILE)} AND wb.NATIVE_ID_TYPE = 'API10'
)"""


def well_filter(api10s: list[str] | None, alias: str = "sc") -> str:
    """` AND sc.API10 IN (...)` for a batch of wells, or '' for every well in scope.
    The ids are interpolated (the reader role cannot create temp tables), so each must be a
    10-digit API."""
    if api10s is None:
        return ""
    if not api10s:
        raise ValueError("empty well batch")
    bad = [a for a in api10s if not _API10_RE.match(a)]
    if bad:
        raise ValueError(f"not a 10-digit API10: {bad[:3]}")
    return f" AND {alias}.API10 IN ({', '.join(_lit(a) for a in api10s)})"


# ---------------------------------------------------------------------------------------------
# Header tables: Wells and WellDetails (both from WELL_DETAIL), WellSpacing.
# ---------------------------------------------------------------------------------------------

# v3 column -> v4 expression, shared by Wells and WellDetails. `d` = WELL_DETAIL,
# `wb` = WELLBORE, `sl` = SURFACE_LOCATION, `sh` = the production-sharing rollup.
_HEADER_COMMON: dict[str, str] = {
    "API10": "sc.API10",
    "WellName": "d.WELL_NAME",
    "OriginalOperator": "d.OPERATOR_ORIGINAL",
    "CurrentOperator": "d.CURRENT_OPERATOR",
    "Basin": "d.BASIN",
    "Subbasin": "d.SUBBASIN",
    "State": case_map("d.STATE", STATE_NAME, passthrough=True),
    "StateCode": case_map("d.STATE", STATE_CODE, passthrough=False),
    "County": "d.COUNTY",
    "CountyCode": "d.COUNTY_CODE",
    "Field": "d.FIELD_NAME",
    "Formation": "d.FORMATION",
    "ReportedFormation": "d.FORMATION_REPORTED_NORMALIZED",
    "ReportedFormationRaw": "d.FORMATION_REPORTED",
    "GridFormation": "d.FORMATION_CALCULATED",
    "SHLLatitude": "d.SURFACE_LATITUDE",
    "SHLLongitude": "d.SURFACE_LONGITUDE",
    "BHLLatitude": "d.BOTTOM_HOLE_LATITUDE",
    "BHLLongitude": "d.BOTTOM_HOLE_LONGITUDE",
    "Township": "IFF(d.STATE = 'NM', NULLIF(SPLIT_PART(sl.BLOCK_TOWNSHIP, ' ', 1), ''), NULL)",
    "Range": "IFF(d.STATE = 'NM', NULLIF(SPLIT_PART(sl.BLOCK_TOWNSHIP, ' ', 2), ''), NULL)",
    "Section": "TRY_TO_NUMBER(sl.SECTION)::INTEGER",
    # Texas only, and '' is kept as shipped: v3 stores '' (not NULL) on wells without a block.
    "TXBlock": "IFF(d.STATE = 'TX', sl.BLOCK_TOWNSHIP, NULL)",
    "TXSurvey": "IFF(d.STATE = 'TX', sl.TX_SURVEY, NULL)",
    "TXAbstract": "IFF(d.STATE = 'TX', sl.ABSTRACT_LOT, NULL)",
    "TVD": _int("d.TVD_TD"),
    "MD": _int("d.MD_TD"),
    "SpudDate": "d.SPUD_DATE",
    "DrillingEndDate": "d.TD_DATE",
    "FirstCompletionDate": "d.COMPLETION_DATE",
    "FirstProductionDate": "d.FIRST_PRODUCTION_DATE",
    "LastReportedMonth": "d.LAST_REPORTED_MONTH",
    "PluggedDate": "d.PA_DATE",
    "HasProductionSharing": "COALESCE(sh.ANY_SHARING, FALSE)",
    "LateralLength": _int("d.LATERAL_LENGTH"),
    "LateralLengthSource": "d.LATERAL_LENGTH_SOURCE",
    "FirstCompletionProppantMass": _int("d.PROPPANT_MASS"),
    "FirstCompletionFluidVolume": _int("d.FLUID_VOLUME"),
    "FirstCompletionStages": "d.STAGE_COUNT::INTEGER",
    "Refrac": "COALESCE(d.REFRAC_COUNT, 0)::INTEGER",
    "Altitude": "d.KB_ELEVATION::INTEGER",
    "WellStatus": case_map("d.WELL_STATUS", WELL_STATUS, passthrough=True),
    # v4 is NULL on wells without a survey. v3 was FALSE on 23,107 of those and NULL on 3,906,
    # with no rule that separates them, so no-survey is written FALSE (the majority v3 value;
    # every curated reader that guards the flag does COALESCE(..., FALSE)).
    "DirectionalSurveyIsPlanned": "COALESCE(d.PLANNED_AS_DRILLED_SURVEY = 'PLANNED', FALSE)",
    "ReportedSlant": "d.DIRECTION_REPORTED",
    "ReportedSlantNormalized": case_map("d.DIRECTION_REPORTED_NORMALIZED", REPORTED_SLANT, passthrough=True),
    "SlantCalculated": case_map("d.DIRECTION_CALCULATED", SLANT, passthrough=True),
    "PermitID": "d.PERMIT_ID",
    "UpperPerforation": "d.PERFORATION_UPPER",
    "LowerPerforation": "d.PERFORATION_LOWER",
    "PerforationInterval": "d.PERFORATION_INTERVAL",
    # Deprecated by Novi (frozen 2026-09-24); the named replacement covers 27 % of wells.
    # Nothing reads curated.wells.wellbore_lateral_length_ft, so take the replacement as is.
    "WellboreLateralLength": _int("wb.LATERAL_LENGTH_CALCULATED_LP_TO_BHL"),
    "LastRefracDate": "d.LAST_REFRAC_DATE",
    "ReportedWellType": "d.WELLBORE_TYPE_REPORTED",
    "CreatedAt": _utc("wb.CREATED_AT"),
    "ModifiedAt": _utc("wb.UPDATED_AT"),
}

_STREAMS = (("Oil", "OIL"), ("Gas", "GAS"), ("Water", "WATER"), ("BOE", "BOE"))

# WellDetails only.
_DETAIL_ONLY: dict[str, str] = {
    "LPLatitude": "d.LANDING_POINT_LATITUDE",
    "LPLongitude": "d.LANDING_POINT_LONGITUDE",
    "MPLatitude": "d.MIDPOINT_LATITUDE",
    "MPLongitude": "d.MIDPOINT_LONGITUDE",
    "LastReportedMonthsOnProduction": "d.LAST_REPORTED_MONTHS_ON_PRODUCTION::INTEGER",
    "FirstCompletionStages_AvgSpacing": _int("d.STAGE_SPACING"),
    "FirstCompletionProppantLbsPerGal": "d.PROPPANT_CONCENTRATION",
    "FirstCompletionProppantLbsPerFt": _int("d.PROPPANT_LOADING"),
    "SoakTimeDays": "d.SOAK_TIME_DAYS::INTEGER",
    "CumLifeGOR": "d.CUM_LIFE_GOR",
    "SpacingIsChild": "d.IS_CHILD",
    "SpacingClosestWellXY": "d.CLOSEST_WELL_XY",
    "LatestOilAPIGravity": "d.LATEST_OIL_GRAVITY",
    "LatestOilAPIGravityTestDate": "d.LATEST_OIL_GRAVITY_TEST_DATE",
    "LatestGasSpecificGravity": "d.LATEST_GAS_GRAVITY",
    "LatestGasSpecificGravityTestDate": "d.LATEST_GAS_GRAVITY_TEST_DATE",
}
for _v3, _v4 in _STREAMS:
    _DETAIL_ONLY[f"Cum12M{_v3}"] = _int(f"d.CUM_{_v4}_12_REPORTED")
    _DETAIL_ONLY[f"Cum24M{_v3}"] = _int(f"d.CUM_{_v4}_24_REPORTED")
    _DETAIL_ONLY[f"CumLife{_v3}"] = _int(f"d.CUM_{_v4}_LIFE_REPORTED")
    for _yr in (20, 30, 50):
        _DETAIL_ONLY[f"EUR{_yr}YR{_v3}"] = _int(f"d.EUR_{_v4}_{_yr}YR")
    _DETAIL_ONLY[f"PeakMonth{_v3}"] = f"d.PEAK_MONTH_{_v4}_INDEX::INTEGER"
    _DETAIL_ONLY[f"PeakMonth{_v3}Rate"] = _int(f"d.PEAK_MONTH_{_v4}_AMOUNT")

WELLS_COLUMNS: dict[str, str] = dict(_HEADER_COMMON)
WELL_DETAILS_COLUMNS: dict[str, str] = {**_HEADER_COMMON, **_DETAIL_ONLY}

SPACING_COLUMNS: dict[str, str] = {
    "API10": "sc.API10",
    "Basin": "ws.BASIN",
    "ClosestWellXY": "ws.CLOSEST_WELL_XY",
    "WellsInRadius": "ws.WELLS_IN_RADIUS::INTEGER",
    "ClosestTwoAvgXY": "ws.CLOSEST_TWO_AVG_XY",
    "WellsInRadiusAvgXY": "ws.WELLS_IN_RADIUS_AVG_XY",
    "IsChild": "ws.IS_CHILD",
    "ParentCount": "ws.PARENT_COUNT::INTEGER",
    "ParentDaysOnline": f"COALESCE(ws.PARENT_DAYS_ONLINE, {PARENT_DAYS_ONLINE_NONE})",
    "LateralCloserXY": "ws.LATERAL_CLOSER_XY",
    "StaggerCloserTangent": "ws.STAGGER_CLOSER_TANGENT",
    "StackCloserZ": "ws.STACK_CLOSER_Z",
    "BoundednessScore": "ws.BOUNDEDNESS_SCORE",
    "CreatedAt": _utc("ws.CREATED_AT"),
    "ModifiedAt": _utc("ws.UPDATED_AT"),
}


def _select(columns: dict[str, str]) -> str:
    return ",\n    ".join(f'{expr} AS "{name}"' for name, expr in columns.items())


def _header_sql(columns: dict[str, str]) -> str:
    return f"""WITH {SCOPE_CTE},
sharing AS (
    SELECT p.WELLBORE_KEY,
           BOOLOR_AGG(COALESCE(p.IS_OIL_FROM_PRODUCTION_SHARING, FALSE)
                   OR COALESCE(p.IS_GAS_FROM_PRODUCTION_SHARING, FALSE)
                   OR COALESCE(p.IS_WATER_FROM_PRODUCTION_SHARING, FALSE)) AS ANY_SHARING
    FROM {DB}.PRODUCTION p
    JOIN scope sc ON sc.WELLBORE_KEY = p.WELLBORE_KEY
    WHERE p.PERIOD_GRANULARITY = 'monthly'
    GROUP BY 1
)
SELECT
    {_select(columns)}
FROM scope sc
JOIN {DB}.WELL_DETAIL d ON d.WELLBORE_KEY = sc.WELLBORE_KEY
JOIN {DB}.WELLBORE wb ON wb.WELLBORE_KEY = sc.WELLBORE_KEY
LEFT JOIN {DB}.SURFACE_LOCATION sl ON sl.WELL_KEY = sc.WELL_KEY
LEFT JOIN sharing sh ON sh.WELLBORE_KEY = sc.WELLBORE_KEY"""


def wells_sql() -> str:
    return _header_sql(WELLS_COLUMNS)


def well_details_sql() -> str:
    return _header_sql(WELL_DETAILS_COLUMNS)


def well_spacing_sql() -> str:
    return f"""WITH {SCOPE_CTE}
SELECT
    {_select(SPACING_COLUMNS)}
FROM {DB}.WELL_SPACING ws
JOIN scope sc ON sc.WELLBORE_KEY = ws.WELLBORE_KEY"""


# ---------------------------------------------------------------------------------------------
# Child tables keyed by well: WellMonths, ForecastWellMonths, DirectionalSurveys.
# ---------------------------------------------------------------------------------------------

_PROD_DATE = "COALESCE(p.PRODUCTION_DATE, DATE_FROM_PARTS(p.YEAR, p.MONTH, 1))"
_DAYS_IN_MONTH = f"DAY(LAST_DAY({_PROD_DATE}))"


def _monthly(v4: str) -> str:
    return _int(f"p.{v4}")


def _per_day(v4: str) -> str:
    """Novi's v3 calendar-day rate: monthly volume / days in the calendar month, to 0.1.

    Fixed-point and half-to-even on purpose. Snowflake's default ROUND is half away from zero
    and float division hides the tie; v3 rounds an exact x.x5 to the even digit (97.25 -> 97.2).
    Ties only occur in 28-day Februaries (volume = 28k + 7), about 0.2 % of well-months."""
    return f"ROUND(ROUND(p.{v4})::NUMBER(18, 0) / {_DAYS_IN_MONTH}::NUMBER(2, 0), 1, 'HALF_TO_EVEN')::FLOAT"


def _running(v4: str) -> str:
    over = f"OVER (PARTITION BY p.WELLBORE_KEY ORDER BY {_PROD_DATE} ROWS UNBOUNDED PRECEDING)"
    return f"SUM(COALESCE(ROUND(p.{v4}), 0)) {over}::INTEGER"


WELL_MONTHS_COLUMNS: dict[str, str] = {
    "API10": "sc.API10",
    "Year": "p.YEAR::INTEGER",
    "Month": "p.MONTH::INTEGER",
    "Date": _PROD_DATE,
    # Novi's company name (mergers applied as of the month), as v3 shipped it. OPERATOR_REPORTED
    # is the filer's legal name in capitals and is not what v3 carried.
    "Operator": "o.NAME",
    "OilPerDay": _per_day("OIL"),
    "OilPerMonth": _monthly("OIL"),
    "CumulativeOil": _running("OIL"),
    "GasPerDay": _per_day("GAS"),
    "GasPerMonth": _monthly("GAS"),
    "CumulativeGas": _running("GAS"),
    "WaterPerDay": _per_day("WATER"),
    "WaterPerMonth": _monthly("WATER"),
    "CumulativeWater": _running("WATER"),
    "ProducingDays": "p.PRODUCING_DAYS::INTEGER",
    "CumulativeProducingDays": "COALESCE(p.CUMULATIVE_PRODUCING_DAYS, 0)::INTEGER",
    "MonthsOnProduction": "p.MONTHS_ON_PRODUCTION::INTEGER",
    "FlaredGasPerDay": _per_day("GAS_FLARED"),
    "FlaredGasPerMonth": _monthly("GAS_FLARED"),
    "CumulativeFlaredGas": _running("GAS_FLARED"),
    "Basin": "p.BASIN",
    "Subbasin": "p.SUBBASIN",
    "IsOilFromProductionSharing": "COALESCE(p.IS_OIL_FROM_PRODUCTION_SHARING, FALSE)",
    "IsGasFromProductionSharing": "COALESCE(p.IS_GAS_FROM_PRODUCTION_SHARING, FALSE)",
    "IsGasFlaredFromProductionSharing": "COALESCE(p.IS_GAS_FLARED_FROM_PRODUCTION_SHARING, FALSE)",
    "IsWaterFromProductionSharing": "COALESCE(p.IS_WATER_FROM_PRODUCTION_SHARING, FALSE)",
    "CreatedAt": _utc("p.CREATED_AT"),
    "ModifiedAt": _utc("p.UPDATED_AT"),
}


def well_months_sql(api10s: list[str] | None = None) -> str:
    return f"""WITH {SCOPE_CTE}
SELECT
    {_select(WELL_MONTHS_COLUMNS)}
FROM {DB}.PRODUCTION p
JOIN scope sc ON sc.WELLBORE_KEY = p.WELLBORE_KEY
LEFT JOIN {DB}.OPERATOR o ON o.OPERATOR_ID = p.OPERATOR_ID
WHERE p.PERIOD_GRANULARITY = 'monthly'{well_filter(api10s)}"""


def _fc_volume(stream: str) -> str:
    """Month volume from the v4 running total (the guide: 'difference consecutive rows')."""
    c = f"f.CUMULATIVE_{stream}"
    return f"({c} - COALESCE(LAG({c}) OVER (PARTITION BY f.WELLBORE_KEY ORDER BY f.FORECAST_DATE), 0))::INTEGER"


FORECAST_COLUMNS: dict[str, str] = {
    "API10": "sc.API10",
    "Date": "f.FORECAST_DATE",
    "MonthsOnProduction": "f.FORECAST_MONTH::SMALLINT",
    "IsForecasted": "TRUE",
    "Basin": "f.BASIN",
    "Subbasin": "f.SUBBASIN",
    "OilPerDay": "ROUND(f.OIL_PER_DAY, 1)",
    "OilPerMonth": _fc_volume("OIL"),
    "CumulativeOil": "(f.CUMULATIVE_OIL + COALESCE(b.OIL, 0))::INTEGER",
    "GasPerDay": "ROUND(f.GAS_PER_DAY, 1)",
    "GasPerMonth": _fc_volume("GAS"),
    "CumulativeGas": "(f.CUMULATIVE_GAS + COALESCE(b.GAS, 0))::INTEGER",
    "WaterPerDay": "ROUND(f.WATER_PER_DAY, 1)",
    "WaterPerMonth": _fc_volume("WATER"),
    "CumulativeWater": "(f.CUMULATIVE_WATER + COALESCE(b.WATER, 0))::INTEGER",
    "CreatedAt": _utc("f.CREATED_AT"),
    "ModifiedAt": _utc("f.CREATED_AT"),
}


def forecast_sql(api10s: list[str] | None = None) -> str:
    flt = well_filter(api10s)
    return f"""WITH {SCOPE_CTE},
f AS (
    SELECT f.*
    FROM {DB}.PRODUCTION_FORECAST f
    JOIN scope sc ON sc.WELLBORE_KEY = f.WELLBORE_KEY
    WHERE f.PERIOD_GRANULARITY = 'monthly' AND f.SCENARIO = 'P50'{flt}
),
fstart AS (SELECT WELLBORE_KEY, MIN(FORECAST_DATE) AS FIRST_DATE FROM f GROUP BY 1),
base AS (
    -- actual cumulative before the forecast starts: v3 counted the forecast cumulative from
    -- first production, v4 counts it from the first forecast month
    SELECT p.WELLBORE_KEY, SUM(ROUND(p.OIL)) AS OIL, SUM(ROUND(p.GAS)) AS GAS, SUM(ROUND(p.WATER)) AS WATER
    FROM {DB}.PRODUCTION p
    JOIN fstart s ON s.WELLBORE_KEY = p.WELLBORE_KEY
    WHERE p.PERIOD_GRANULARITY = 'monthly'
      AND COALESCE(p.PRODUCTION_DATE, DATE_FROM_PARTS(p.YEAR, p.MONTH, 1)) < s.FIRST_DATE
    GROUP BY 1
)
SELECT
    {_select(FORECAST_COLUMNS)}
FROM f
JOIN scope sc ON sc.WELLBORE_KEY = f.WELLBORE_KEY
LEFT JOIN base b ON b.WELLBORE_KEY = f.WELLBORE_KEY"""


SURVEY_COLUMNS: dict[str, str] = {
    "API10": "sc.API10",
    "Path": "ds.STATION_SEQUENCE::INTEGER",
    "Basin": "ds.BASIN",
    "Subbasin": "ds.SUBBASIN",
    "MD": _int("ds.MD"),
    "Inclination": "ds.INCLINATION",
    "Azimuth": "ds.AZIMUTH",
    "TVD": _int("ds.TVD"),
    "SubSeaTVD": _int("ds.SUB_SEA_TVD_CALCULATED"),
    "NS": _int("ds.NS_OFFSET"),
    "EW": _int("ds.EW_OFFSET"),
    "LocationType": "ds.LOCATION_TYPE::INTEGER",
    "Latitude": "ds.LATITUDE",
    "Longitude": "ds.LONGITUDE",
    "Interpolated": "ds.INTERPOLATED",
    "CreatedAt": _utc("ds.CREATED_AT"),
    "ModifiedAt": _utc("ds.UPDATED_AT"),
}


def surveys_sql(api10s: list[str] | None = None) -> str:
    return f"""WITH {SCOPE_CTE}
SELECT
    {_select(SURVEY_COLUMNS)}
FROM {DB}.DIRECTIONAL_SURVEY_STATION ds
JOIN scope sc ON sc.WELLBORE_KEY = ds.WELLBORE_KEY
WHERE TRUE{well_filter(api10s)}"""


# Per-well census of a child view: row count and newest stamp. Compared with the same census
# of the local table, it finds changed wells AND wells or rows that Novi removed (v4 has no
# deletion marker; Novi's own diff files are built by the same key comparison).
_CENSUS = {
    "WellMonths": ("PRODUCTION", "UPDATED_AT", "t.PERIOD_GRANULARITY = 'monthly'"),
    "ForecastWellMonths": ("PRODUCTION_FORECAST", "CREATED_AT",
                           "t.PERIOD_GRANULARITY = 'monthly' AND t.SCENARIO = 'P50'"),
    "DirectionalSurveys": ("DIRECTIONAL_SURVEY_STATION", "UPDATED_AT", "TRUE"),
}


#: Streams whose cumulatives make up the forecast content checksum.
_CHECKSUM_STREAMS = ("OIL", "GAS", "WATER")

# Content checksum per well, for tables whose stamp does not move when Novi revises rows in
# place. PRODUCTION_FORECAST is the one: on 2026-11-20 Novi rewrote 2,289 wells' forecasts with
# the row count and CREATED_AT unchanged. The checksum is the sum over a well's rows of the v4
# cumulatives of the three streams. The local side rebuilds the same number from the stored
# monthly volumes (their running sum IS the v4 cumulative), so both sides are exact integers.
_CENSUS_CHECKSUM = {
    "ForecastWellMonths": "SUM(" + " + ".join(
        f"COALESCE(t.CUMULATIVE_{s}, 0)" for s in _CHECKSUM_STREAMS) + ")",
}
LOCAL_CHECKSUM_COLUMNS = {
    "ForecastWellMonths": ("OilPerMonth", "GasPerMonth", "WaterPerMonth"),
}


def local_census_sql(schema: str, table: str) -> str:
    """The Postgres side of the census, same shape as `census_sql`: API10, N, STAMP, CHECKSUM."""
    cols = LOCAL_CHECKSUM_COLUMNS.get(table)
    if cols is None:
        return (f'SELECT "API10", count(*), max("ModifiedAt"), NULL::numeric '
                f'FROM {schema}."{table}" GROUP BY 1')
    monthly = " + ".join(f'COALESCE("{c}", 0)' for c in cols)
    return f"""SELECT "API10", count(*), max("ModifiedAt"), sum(running)
FROM (SELECT "API10", "ModifiedAt",
             sum(({monthly})::bigint) OVER (PARTITION BY "API10" ORDER BY "Date") AS running
      FROM {schema}."{table}") t
GROUP BY 1"""


def census_sql(table: str) -> str:
    view, stamp, where = _CENSUS[table]
    checksum = _CENSUS_CHECKSUM.get(table, "NULL")
    return f"""WITH {SCOPE_CTE}
SELECT sc.API10, COUNT(*) AS N, {_utc(f'MAX(t.{stamp})')} AS STAMP, {checksum} AS CHECKSUM
FROM {DB}.{view} t
JOIN scope sc ON sc.WELLBORE_KEY = t.WELLBORE_KEY
WHERE {where}
GROUP BY 1"""


#: table -> (full-table SQL builder, per-well SQL builder or None, v3 columns it fills)
HEADER_TABLES = {
    "Wells": (wells_sql, WELLS_COLUMNS),
    "WellDetails": (well_details_sql, WELL_DETAILS_COLUMNS),
    "WellSpacing": (well_spacing_sql, SPACING_COLUMNS),
}
CHILD_TABLES = {
    "WellMonths": (well_months_sql, WELL_MONTHS_COLUMNS),
    "ForecastWellMonths": (forecast_sql, FORECAST_COLUMNS),
    "DirectionalSurveys": (surveys_sql, SURVEY_COLUMNS),
}
