-- =============================================================================
-- Migration 09: add raw_novi."ForecastWellMonths"
--
-- Additive migration for Phase 1 of the Novi forecast integration. Creates
-- the new raw_novi."ForecastWellMonths" table without touching the existing
-- four MVP tables (Wells / WellMonths / WellDetails / WellSpacing).
--
-- After applying: run
--     python -c "from pathlib import Path; from etl.novi.load import load_table; \
--                bulk = Path('data/us-horizontals/All basins/All subbasins/Bulk'); \
--                print(load_table(bulk, 'ForecastWellMonths'))"
-- to TRUNCATE+COPY the ~3 GB / ~50–100M-row TSV into the new table.
--
-- About IsForecasted: ForecastWellMonths is a unified history + forecast
-- time series. Rows where IsForecasted=false duplicate actuals already
-- present in raw_novi."WellMonths"; rows where IsForecasted=true are
-- Novi's algorithmic decline projection for the months after
-- LastProductionMonth. Curated views downstream should filter on
-- IsForecasted=TRUE to isolate the new information.
-- =============================================================================

CREATE TABLE raw_novi."ForecastWellMonths" (
    "API10" varchar(32) NOT NULL,
    "Date" date NOT NULL,
    "MonthsOnProduction" int2 NOT NULL,
    "IsForecasted" bool NOT NULL,
    "Basin" varchar(36) NOT NULL,
    "Subbasin" varchar(36) NOT NULL,
    "OilPerDay" float8 NULL,
    "OilPerMonth" int4 NULL,
    "CumulativeOil" int4 NULL,
    "GasPerDay" float8 NULL,
    "GasPerMonth" int4 NULL,
    "CumulativeGas" int4 NULL,
    "WaterPerDay" float8 NULL,
    "WaterPerMonth" int4 NULL,
    "CumulativeWater" int4 NULL,
    "CreatedAt" timestamp NULL,
    "ModifiedAt" timestamp NULL,
    "DeletedAt" timestamp NULL,
    CONSTRAINT "ForecastWellMonths_pkey" PRIMARY KEY ("API10", "Date"),
    "ingested_at" timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE raw_novi."ForecastWellMonths" IS
    'Novi unified history+forecast time series. IsForecasted=false rows '
    'duplicate raw_novi."WellMonths" actuals; IsForecasted=true rows are '
    'Novi''s algorithmic decline forecast. Curated layer should filter '
    'on IsForecasted=TRUE to isolate new information.';
