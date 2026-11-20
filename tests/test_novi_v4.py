"""Novi v4 loader: the translation SQL, the census diff and the guards. DB-free."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from etl.novi_v4 import compare, sync
from etl.novi_v4 import queries as q

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
ALL = {**q.HEADER_TABLES, **q.CHILD_TABLES}


def _v3_ddl() -> dict[str, dict[str, bool]]:
    """sql/02 -> {table: {column: declared NOT NULL}}."""
    text = (SQL_DIR / "02_raw_novi_ddl.sql").read_text(encoding="utf-8")
    out: dict[str, dict[str, bool]] = {}
    for m in re.finditer(r'CREATE TABLE raw_novi\."(\w+)" \((.*?)\n\);', text, re.DOTALL):
        cols = {}
        for line in m.group(2).splitlines():
            cm = re.match(r'\s*"(\w+)"\s+(.+?),?\s*$', line)
            if cm:
                cols[cm.group(1)] = "NOT NULL" in cm.group(2)
        out[m.group(1)] = cols
    return out


DDL = _v3_ddl()


def test_six_tables_and_v3_load_order():
    from etl.novi.load import MVP_TABLES
    from etl.novi_v4.load import TABLES

    assert set(ALL) == set(MVP_TABLES) == set(DDL)
    assert TABLES == MVP_TABLES


@pytest.mark.parametrize("table", sorted(ALL))
def test_every_output_column_exists_in_the_v3_table(table):
    _, columns = ALL[table]
    unknown = [c for c in columns if c not in DDL[table]]
    assert not unknown, f"{table}: not v3 columns: {unknown}"


@pytest.mark.parametrize("table", sorted(ALL))
def test_sql_aliases_every_column_with_its_exact_v3_name(table):
    builder, columns = ALL[table]
    sql = builder()
    for c in columns:
        assert f' AS "{c}"' in sql, c
    assert sql.count(' AS "') == len(columns)


# v3 columns declared NOT NULL that v4 cannot fill. sql/75 drops the constraint on exactly these.
UNSOURCED_NOT_NULL = {
    "Wells": {"IsHorizontalWell", "WellType", "HasPLSSData", "WellboreLocations",
              "HasAccurateFirstProductionDate", "IsSyntheticApi"},
    "WellDetails": {"IsHorizontalWell", "WellType", "HasPLSSData", "WellboreLocations",
                    "HasAccurateFirstProductionDate", "IsSyntheticApi"},
}


@pytest.mark.parametrize("table", sorted(ALL))
def test_not_null_columns_are_sourced_or_listed(table):
    _, columns = ALL[table]
    missing = {c for c, nn in DDL[table].items() if nn and c not in columns and c != "ingested_at"}
    assert missing == UNSOURCED_NOT_NULL.get(table, set())


def test_scratch_ddl_drops_not_null_on_exactly_the_unsourced_columns():
    text = (SQL_DIR / "75_raw_novi_v4.sql").read_text(encoding="utf-8")
    for table in ALL:
        assert f'raw_novi_v4."{table}"' in text and f'LIKE raw_novi."{table}"' in text
    for table, cols in UNSOURCED_NOT_NULL.items():
        block = re.search(rf'ALTER TABLE raw_novi_v4\."{table}"(.*?);', text, re.DOTALL).group(1)
        assert set(re.findall(r'ALTER COLUMN "(\w+)" DROP NOT NULL', block)) == cols
    assert "MATERIALIZED VIEW" not in text


def test_live_ddl_drops_not_null_on_exactly_the_unsourced_columns():
    """sql/76 (cutover step 2) must free the same columns on raw_novi that sql/75 freed on the copy."""
    text = (SQL_DIR / "76_raw_novi_v4_nullable.sql").read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    blocks = dict(re.findall(r'ALTER TABLE raw_novi\."(\w+)"(.*?);', body, re.DOTALL))
    assert set(blocks) == set(UNSOURCED_NOT_NULL)
    for table, cols in UNSOURCED_NOT_NULL.items():
        assert set(re.findall(r'ALTER COLUMN "(\w+)" DROP NOT NULL', blocks[table])) == cols
    # nothing but those ALTERs: no drop, no cascade, no other schema
    assert not re.search(r"\b(DROP TABLE|DROP SCHEMA|CASCADE|TRUNCATE|DELETE|CREATE)\b", body)
    assert "raw_novi_v4" not in body


def test_scope_is_the_v3_export_set_and_every_query_uses_it():
    assert "s.SOURCE_FILE = 'US_Horizontals'" in q.SCOPE_CTE
    for table, (builder, _) in ALL.items():
        assert q.SCOPE_CTE in builder(), table
    for table in q.CHILD_TABLES:
        assert q.SCOPE_CTE in q.census_sql(table)


def test_monthly_rows_only():
    assert "p.PERIOD_GRANULARITY = 'monthly'" in q.well_months_sql()
    assert "f.PERIOD_GRANULARITY = 'monthly' AND f.SCENARIO = 'P50'" in q.forecast_sql()
    assert "PERIOD_GRANULARITY = 'monthly'" in q.census_sql("WellMonths")
    assert "SCENARIO = 'P50'" in q.census_sql("ForecastWellMonths")


def test_calendar_day_rate_rule():
    """Rule 4 as carried over: monthly volume / days in the calendar month, to 0.1, half to even."""
    expr = q.WELL_MONTHS_COLUMNS["OilPerDay"]
    assert "DAY(LAST_DAY(" in expr and "'HALF_TO_EVEN'" in expr and ", 1," in expr
    assert "NUMBER" in expr, "fixed-point division: a float tie would round half away from zero"
    assert "PRODUCING_DAYS" not in expr
    for stream, v4 in (("Oil", "OIL"), ("Gas", "GAS"), ("Water", "WATER"), ("FlaredGas", "GAS_FLARED")):
        assert q.WELL_MONTHS_COLUMNS[f"{stream}PerDay"] == expr.replace("p.OIL", f"p.{v4}")


def test_forecast_is_forecast_only_and_cumulative_is_rebased():
    assert q.FORECAST_COLUMNS["IsForecasted"] == "TRUE"
    assert "COALESCE(b.OIL, 0)" in q.FORECAST_COLUMNS["CumulativeOil"]
    sql = q.forecast_sql()
    assert "< s.FIRST_DATE" in sql, "base = actual cumulative BEFORE the first forecast month"
    assert "LAG(f.CUMULATIVE_OIL)" in q.FORECAST_COLUMNS["OilPerMonth"]


def test_code_maps():
    assert q.WELL_STATUS["PA"] == "P&A" and q.WELL_STATUS["PERMIT_CANCELLED"] == "Permit Cancelled"
    assert q.SLANT["U_TURN_HORIZONTAL"] == "U-Turn (Horizontal)"
    assert q.STATE_CODE == {"TX": 42, "NM": 30}
    assert "WHEN 'PA' THEN 'P&A'" in q.WELLS_COLUMNS["WellStatus"]
    assert q.WELLS_COLUMNS["WellStatus"].endswith("ELSE d.WELL_STATUS END"), "unknown codes pass through"
    assert q.WELLS_COLUMNS["StateCode"].endswith("ELSE NULL END")


def test_parent_days_online_keeps_the_v3_sentinel():
    assert q.SPACING_COLUMNS["ParentDaysOnline"] == "COALESCE(ws.PARENT_DAYS_ONLINE, -1)"


def test_lateral_closer_xy_is_passed_through_untouched():
    """Exactly 2800.0 is Novi's no-neighbor sentinel (rule 14); the loader must not round or recode it."""
    assert q.SPACING_COLUMNS["LateralCloserXY"] == "ws.LATERAL_CLOSER_XY"


def test_stamps_are_naive_utc_in_rows_and_in_the_census():
    """The share's stamps are TIMESTAMP_LTZ in Pacific time; Postgres `timestamp` drops the offset.
    Unconverted, every well's ModifiedAt lands 8 h off and every census differs (found on the
    first incremental rehearsal, 2026-11-19)."""
    for table, (_, columns) in ALL.items():
        for c in ("CreatedAt", "ModifiedAt"):
            assert columns[c].startswith("CONVERT_TIMEZONE('UTC', ") and columns[c].endswith(")::TIMESTAMP_NTZ"), (table, c)
    for table in q.CHILD_TABLES:
        assert "CONVERT_TIMEZONE('UTC', MAX(t." in q.census_sql(table)


def test_well_filter():
    assert q.well_filter(None) == ""
    assert q.well_filter(["4230112345", "3001512345"]) == " AND sc.API10 IN ('4230112345', '3001512345')"
    with pytest.raises(ValueError):
        q.well_filter([])
    with pytest.raises(ValueError):
        q.well_filter(["4230112345'); DROP"])
    assert "IN ('4230112345')" in q.well_months_sql(["4230112345"])
    assert "IN ('4230112345')" in q.forecast_sql(["4230112345"])
    assert "IN ('4230112345')" in q.surveys_sql(["4230112345"])


# --------------------------------------------------------------------------- sync

T0 = datetime(2026, 11, 17, 14, 56, 11, 450000)  # noqa: DTZ001  (raw_novi stamps are naive)


def test_etl_label_keeps_the_forecast_gate_on_live_and_off_on_scratch():
    from etl.db import _GATED_REFRESH

    pattern = _GATED_REFRESH["curated.production_forecast"]
    assert pattern.endswith("%") and "%" not in pattern[:-1] and "_" not in pattern
    prefix = pattern[:-1]  # SQL LIKE 'ForecastWellMonths%'
    assert sync.etl_label("raw_novi", "ForecastWellMonths").startswith(prefix)
    for table in ALL:
        assert not sync.etl_label("raw_novi_v4", table).startswith(prefix)


def test_diff_census():
    remote = {"A": (10, T0), "B": (5, T0), "C": (7, T0), "D": (3, T0), "N": (1, T0)}
    local = {"A": (10, T0), "B": (6, T0), "C": (7, T0 - timedelta(days=1)),
             "D": (3, T0 + timedelta(days=1)), "X": (4, T0)}
    changed, gone = sync.diff_census(remote, local)
    assert changed == ["B", "C", "D", "N"]  # count differs; older; NEWER locally (restamp back); new
    assert gone == ["X"]


def test_diff_census_ignores_timezone_and_sub_millisecond_noise():
    aware = T0.replace(tzinfo=timezone.utc)
    assert sync.diff_census({"A": (1, aware)}, {"A": (1, T0)}) == ([], [])
    assert sync.diff_census({"A": (1, T0.replace(microsecond=450123))}, {"A": (1, T0)}) == ([], [])
    assert sync.diff_census({"A": (1, None)}, {"A": (1, None)}) == ([], [])
    assert sync.diff_census({"A": (1, T0)}, {"A": (1, None)}) == (["A"], [])


def test_forecast_census_carries_a_content_checksum():
    """Novi revises forecasts in place: same row count, same CREATED_AT (2,289 wells on
    2026-11-20). Count + stamp alone miss it, so the forecast census adds a checksum."""
    remote_sql = q.census_sql("ForecastWellMonths")
    for stream in ("OIL", "GAS", "WATER"):
        assert f"COALESCE(t.CUMULATIVE_{stream}, 0)" in remote_sql
    local_sql = q.local_census_sql("raw_novi_v4", "ForecastWellMonths")
    assert 'OVER (PARTITION BY "API10" ORDER BY "Date")' in local_sql  # running sum = v4 cumulative
    for col in ("OilPerMonth", "GasPerMonth", "WaterPerMonth"):
        assert f'COALESCE("{col}", 0)' in local_sql
        assert "LAG(f.CUMULATIVE_" in q.FORECAST_COLUMNS[col]  # the identity the checksum rests on
    for table in ("WellMonths", "DirectionalSurveys"):
        assert "NULL AS CHECKSUM" in q.census_sql(table)
        assert "NULL::numeric" in q.local_census_sql("raw_novi_v4", table)


def test_diff_census_catches_an_in_place_revision():
    same = {"A": (546, T0, 1_000), "B": (546, T0, 2_000)}
    assert sync.diff_census(same, dict(same)) == ([], [])
    revised = {"A": (546, T0, 1_000), "B": (546, T0, 2_015)}
    assert sync.diff_census(revised, same) == (["B"], [])
    assert sync.diff_census({"A": (1, T0, None)}, {"A": (1, T0, None)}) == ([], [])


def test_sync_child_also_repulls_named_wells_that_are_still_on_the_share(monkeypatch):
    """A well with unchanged forecast rows but revised production: its stored forecast
    cumulatives (rebased by actuals) are stale, so the caller names it in `also`."""
    census = {w: (10, T0, i) for i, w in enumerate("ABCDEFGHIJ")}
    monkeypatch.setattr(sync, "remote_census", lambda sf, table: dict(census))
    monkeypatch.setattr(sync, "local_census", lambda schema, table: dict(census))
    r = sync.sync_child(None, "raw_novi_v4", "ForecastWellMonths", dry_run=True, also=["B", "GONE"])
    assert r["changed"] == ["B"] and r["wells_changed"] == 1 and r["mode"] == "batches"
    r = sync.sync_child(None, "raw_novi_v4", "ForecastWellMonths", dry_run=True)
    assert r["changed"] == [] and r["mode"] == "none"


def test_plan_pull():
    assert sync.plan_pull(0, 1000) == "none"
    assert sync.plan_pull(300, 1000) == "batches"
    assert sync.plan_pull(301, 1000) == "full"


def test_breaker():
    assert sync.breaker_limit(60_000) == 600 and sync.breaker_limit(5_000) == 200
    sync.check_breaker("WellMonths", 600, 60_000, allow=False)
    with pytest.raises(RuntimeError, match="refusing"):
        sync.check_breaker("WellMonths", 601, 60_000, allow=False)
    sync.check_breaker("WellMonths", 601, 60_000, allow=True)
    sync.check_breaker("WellMonths", 0, 0, allow=False)  # first load of an empty table


def test_dry_run_reports_a_tripped_breaker_and_writes_nothing(monkeypatch):
    """First v4 run on the live forecast table: v3's history-only wells look 'gone'."""
    remote = {f"{i:010d}": (10, T0) for i in range(1000)}
    local = {f"{i:010d}": (10, T0) for i in range(1500)}
    monkeypatch.setattr(sync, "remote_census", lambda sf, table: remote)
    monkeypatch.setattr(sync, "local_census", lambda schema, table: local)
    monkeypatch.setattr(sync, "log_etl_run", lambda *a: pytest.fail("a dry run must not log or write"))
    r = sync.sync_child(None, "raw_novi", "ForecastWellMonths", dry_run=True)
    assert r["breaker"] and r["wells_gone"] == 500 and r["mode"] == "none" and r["rows_inserted"] == 0
    with pytest.raises(RuntimeError, match="refusing"):
        sync.sync_child(None, "raw_novi", "ForecastWellMonths")


class _FakeSfCursor:
    description = (("API10",), ("Year",))

    def __init__(self, batches):
        self._batches = list(batches)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        self.sql = sql

    def fetchmany(self, n):
        return self._batches.pop(0) if self._batches else []


class _FakeSf:
    def __init__(self, batches):
        self._batches = batches

    def cursor(self):
        return _FakeSfCursor(self._batches)


class _FakeCopy:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        self.log.append("open")
        return self

    def __exit__(self, *exc):
        self.log.append("close")
        return False

    def write_row(self, row):
        self.log.append(row)


class _FakePgCursor:
    def __init__(self):
        self.log, self.statements = [], []

    def copy(self, statement):
        self.statements.append(statement)
        return _FakeCopy(self.log)


def test_copy_streams_every_batch_through_one_copy():
    cur = _FakePgCursor()
    n = sync._copy(_FakeSf([[("A", 1), ("A", 2)], [("B", 1)]]), "select 1", cur, "raw_novi_v4", "WellMonths")
    assert n == 3
    assert cur.statements == ['COPY raw_novi_v4."WellMonths" ("API10", "Year") FROM STDIN']
    assert cur.log == ["open", ("A", 1), ("A", 2), ("B", 1), "close"]


def test_copy_of_an_empty_result_opens_no_copy():
    cur = _FakePgCursor()
    assert sync._copy(_FakeSf([]), "select 1", cur, "raw_novi_v4", "Wells") == 0
    assert cur.statements == []


def test_diff_sql_shape():
    from etl.novi_v4 import diff

    sql = diff.diff_sql("raw_novi_v4", "ForecastWellMonths", ["OilPerDay", "OilPerMonth"], {"OilPerDay"})
    assert 'USING ("API10", "Date")' in sql and 'raw_novi."ForecastWellMonths" WHERE "IsForecasted"' in sql
    assert 'abs(a."OilPerDay" - b."OilPerDay")' in sql
    assert 'a."OilPerMonth" IS DISTINCT FROM b."OilPerMonth"' in sql
    with pytest.raises(ValueError):
        diff.diff_sql("bad;schema", "Wells", [], set())


def test_header_guard_refuses_an_empty_or_shrunken_pull():
    with pytest.raises(RuntimeError, match="no rows"):
        sync.check_header_rows("Wells", 0, 95_985, allow=True)
    with pytest.raises(RuntimeError, match="refusing"):
        sync.check_header_rows("Wells", 80_000, 95_985, allow=False)
    sync.check_header_rows("Wells", 80_000, 95_985, allow=True)
    sync.check_header_rows("Wells", 95_990, 95_985, allow=False)
    sync.check_header_rows("Wells", 95_990, 0, allow=False)


def test_schema_name_is_validated():
    with pytest.raises(ValueError):
        sync._check_schema('raw_novi"; DROP SCHEMA curated; --')
    assert sync._check_schema("raw_novi_v4") == "raw_novi_v4"


def test_cli_refuses_the_live_schema_without_confirmation(monkeypatch):
    from etl.novi_v4 import load

    monkeypatch.setattr(load, "get_sf_connection", lambda: pytest.fail("must not connect"))
    with pytest.raises(SystemExit):
        load.main(["--schema", "raw_novi"])


# --------------------------------------------------------------------------- compare

def test_values_equal():
    assert compare.values_equal(Decimal(42), 42)
    assert compare.values_equal(97.2, 97.2000000001)
    assert not compare.values_equal(97.3, 97.2)
    assert compare.values_equal("Oil ", "Oil") and not compare.values_equal("OIL", "Oil")
    assert not compare.values_equal(True, False)


def test_compare_rows():
    cols = ["API10", "Year", "Oil", "Gas"]
    v4 = [("A", 2026, 10, None), ("A", 2025, 5, 1.0), ("B", 2026, 7, 2.0)]
    v3 = [("A", 2026, 11, 3.0), ("A", 2025, 5, None), ("C", 2026, 1, 1.0)]
    r = compare.compare_rows(2, cols, v4, v3)
    assert (r["common"], r["v4_only"], r["v3_only"]) == (2, 1, 1)
    assert r["columns"]["Oil"]["both"] == 2 and r["columns"]["Oil"]["equal"] == 1
    assert r["columns"]["Oil"]["example"] == (("A", 2026), 10, 11)
    assert r["columns"]["Gas"]["v4_null"] == 1 and r["columns"]["Gas"]["v3_null"] == 1
    assert "<--" in compare.format_report("T", r)


# --------------------------------------------------------------------------- nightly switch

def _run_daily_with(monkeypatch, tmp_path, source):
    """Run scripts.run_daily.main() with every step stubbed; return (exit code, step names run)."""
    from scripts import run_daily

    ran: list[str] = []
    if source is None:
        monkeypatch.delenv(run_daily.NOVI_SOURCE_ENV, raising=False)
    else:
        monkeypatch.setenv(run_daily.NOVI_SOURCE_ENV, source)
    monkeypatch.setattr(run_daily, "_configure_logging", lambda: tmp_path / "run.log")
    monkeypatch.setattr(run_daily.notify_step, "ping_healthcheck", lambda *a, **k: None)
    monkeypatch.setattr(run_daily.notify_step, "notify_run", lambda *a, **k: None)
    monkeypatch.setattr(run_daily, "sweep_stale_runs", lambda: 0)
    monkeypatch.setattr(run_daily, "db_settle", lambda: None)
    monkeypatch.setattr(run_daily.enverus_wells, "main", lambda: 0)
    monkeypatch.setattr(run_daily.refresh_step, "main", lambda: 0)

    import etl.novi.load as v3_load
    import etl.novi.sync as v3_sync
    import etl.novi_v4.load as v4_load
    from etl.intel_sf import detect

    monkeypatch.setattr(detect, "check_new_reports", lambda: 0)
    monkeypatch.setattr(v3_sync, "sync_bulk", lambda: ran.append("v3.sync") or tmp_path)
    monkeypatch.setattr(v3_load, "load_all", lambda d: ran.append("v3.load") or {"Wells": 1})
    monkeypatch.setattr(v4_load, "nightly_load", lambda: ran.append("v4.load") or 7)
    return run_daily.main(), ran


@pytest.mark.parametrize("source", [None, "", "v3", " V3 "])
def test_nightly_defaults_to_v3(monkeypatch, tmp_path, source):
    """Merging the switch must change nothing: unset or blank NOVI_SOURCE is the v3 bulk load."""
    assert _run_daily_with(monkeypatch, tmp_path, source) == (0, ["v3.sync", "v3.load"])


def test_nightly_on_v4_skips_the_bulk_download(monkeypatch, tmp_path):
    assert _run_daily_with(monkeypatch, tmp_path, "v4") == (0, ["v4.load"])


def test_nightly_with_an_unknown_source_fails_the_novi_step_and_loads_neither(monkeypatch, tmp_path):
    assert _run_daily_with(monkeypatch, tmp_path, "v5") == (1, [])


def test_workflow_passes_the_source_variable_with_a_v3_default():
    text = (SQL_DIR.parent / ".github" / "workflows" / "etl-nightly.yml").read_text(encoding="utf-8")
    assert "NOVI_SOURCE: ${{ vars.NOVI_SOURCE || 'v3' }}" in text


def test_nightly_load_writes_live_and_one_failed_table_does_not_stop_the_rest(monkeypatch):
    from etl.novi_v4 import load

    class _SF:
        closed = False

        def close(self):
            self.closed = True

    sf = _SF()
    calls: list[tuple[str, str]] = []

    def header(sf_, schema, table, **kw):
        assert not kw  # the nightly never passes allow_breaker
        calls.append((schema, table))
        return 10

    also_seen: dict[str, list[str]] = {}

    def child(sf_, schema, table, **kw):
        assert set(kw) == {"also"}  # no --full, no --allow-breaker, not a dry run
        also_seen[table] = list(kw["also"])
        calls.append((schema, table))
        if table == "ForecastWellMonths":
            raise RuntimeError("601 wells would be deleted; refusing")
        return {"rows_inserted": 100, "changed": ["4200300001"] if table == "WellMonths" else []}

    monkeypatch.setattr(load, "get_sf_connection", lambda: sf)
    monkeypatch.setattr(load, "share_run_id", lambda sf_: "20261120_100520")
    monkeypatch.setattr(load.sync, "load_header", header)
    monkeypatch.setattr(load.sync, "sync_child", child)
    with pytest.raises(RuntimeError, match="ForecastWellMonths: 601 wells"):
        load.nightly_load()
    assert calls == [("raw_novi", t) for t in load.TABLES]  # every table tried, live schema only
    assert sf.closed
    # wells whose production was re-pulled go to the forecast sync (rebased cumulatives), and
    # to no other table
    assert also_seen == {"WellMonths": [], "ForecastWellMonths": ["4200300001"], "DirectionalSurveys": []}
    assert load.TABLES.index("WellMonths") < load.TABLES.index("ForecastWellMonths")

    monkeypatch.setattr(load.sync, "sync_child",
                        lambda sf_, schema, table, **kw: {"rows_inserted": 100, "changed": []})
    assert load.nightly_load() == 3 * 10 + 3 * 100
