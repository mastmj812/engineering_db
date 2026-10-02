"""Pure-function tests for scripts/load_vdr.py (no Access driver, no DB)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.load_vdr import (
    COMMERCIAL_COLS,
    DAILY_COLS,
    ROLE_PROJECT,
    ROLE_UPDATE,
    AriesFile,
    api10_from_aries,
    build_package,
    classify_tables,
    merge_daily,
    month_start,
    order_files,
    production_lines,
    well_name,
)


@pytest.mark.parametrize(
    "api, expected",
    [
        ("42301354570000", "4230135457"),
        ("42-301-35457-00-00", "4230135457"),
        ("423013545700", "4230135457"),
        ("4230135457", "4230135457"),
        ("0HUHF1J2FZ", None),  # seller PUD placeholder
        ("1G7G2K92XU", None),
        ("", None),
        (None, None),
        (float("nan"), None),
        ("42301", None),
    ],
)
def test_api10_from_aries(api, expected):
    assert api10_from_aries(api) == expected


def test_classify_tables():
    assert classify_tables(["AC_PROPERTY", "AC_DAILY", "AC_ECONOMIC"]) == ROLE_PROJECT
    assert classify_tables(["ac_daily"]) == ROLE_UPDATE
    with pytest.raises(ValueError):
        classify_tables(["SomethingElse"])


def test_month_start_normalizes_aries_month_end():
    assert month_start(pd.Timestamp("2026-04-30")) == date(2026, 4, 1)
    assert month_start(date(2026, 2, 28)) == date(2026, 2, 1)


def test_well_name():
    assert well_name("Lowe 74 Unit", "61H") == "Lowe 74 Unit 61H"
    assert well_name("Atlanta 73", None) == "Atlanta 73"
    assert well_name(None, float("nan")) is None


def _daily(rows):
    df = pd.DataFrame(rows, columns=["propnum", "prod_date", "oil_bbl"])
    for c in DAILY_COLS.values():
        if c not in df:
            df[c] = None
    return df


def test_merge_daily_later_file_wins_and_keeps_both_sides():
    base = _daily(
        [
            ("A", date(2026, 5, 9), 0.1),
            ("A", date(2026, 5, 10), 0.0),
            ("B", date(2026, 5, 9), 7.0),
        ]
    )
    upd = _daily([("A", date(2026, 5, 9), 15.3), ("A", date(2026, 7, 3), 20.0)])
    out = merge_daily([("base.accdb", base), ("upd.accdb", upd)]).set_index(
        ["propnum", "prod_date"]
    )
    assert len(out) == 4
    assert out.loc[("A", date(2026, 5, 9)), "oil_bbl"] == 15.3  # revised by the update
    assert out.loc[("A", date(2026, 5, 9)), "file_name"] == "upd.accdb"
    assert (
        out.loc[("A", date(2026, 5, 10)), "file_name"] == "base.accdb"
    )  # untouched day survives
    assert out.loc[("A", date(2026, 7, 3)), "oil_bbl"] == 20.0  # appended day


def test_merge_daily_keeps_negative_volumes_as_reported():
    out = merge_daily([("f", _daily([("A", date(2026, 3, 22), -13.2)]))])
    assert out["oil_bbl"].iloc[0] == -13.2


def _file(name, role, through, **kw):
    return AriesFile(
        path=Path(name),
        role=role,
        sha256="x",
        daily=_daily([]),
        data_through=through,
        **kw,
    )


def test_order_files_project_first_then_updates_by_date():
    files = [
        _file("u2.accdb", ROLE_UPDATE, date(2026, 8, 1)),
        _file("proj.accdb", ROLE_PROJECT, date(2026, 6, 14)),
        _file("u1.accdb", ROLE_UPDATE, date(2026, 7, 3)),
    ]
    assert [f.name for f in order_files(files)] == [
        "proj.accdb",
        "u1.accdb",
        "u2.accdb",
    ]


def test_order_files_requires_exactly_one_project():
    with pytest.raises(ValueError):
        order_files([_file("u.accdb", ROLE_UPDATE, None)])
    with pytest.raises(ValueError):
        order_files(
            [_file("a.accdb", ROLE_PROJECT, None), _file("b.accdb", ROLE_PROJECT, None)]
        )


def test_production_lines_drops_economics_sections():
    econ = pd.DataFrame(
        {
            "SECTION": [2, 4, 5, 4, 9],
            "KEYWORD": ["BTU", "OIL", "PRI/OIL", "GAS", "S/1018"],
        }
    )
    assert production_lines(econ)["KEYWORD"].tolist() == ["OIL", "GAS"]


def _project(prop_rows, daily_rows):
    prop = pd.DataFrame(prop_rows)
    return AriesFile(
        path=Path("proj.accdb"),
        role=ROLE_PROJECT,
        sha256="x",
        daily=_daily(daily_rows),
        properties=prop,
        monthly=pd.DataFrame(
            {
                "PROPNUM": ["P1"],
                "P_DATE": [pd.Timestamp("2026-04-30")],
                "OIL": [1.0],
                "GAS": [2.0],
                "WATER": [3.0],
                "DAYSON": [30],
                "WELLNO": [1.0],
            }
        ),
        econ=pd.DataFrame(
            {
                "PROPNUM": ["P1"],
                "SECTION": [4],
                "SEQUENCE": [20],
                "QUALIFIER": ["ALCHEMIST"],
                "KEYWORD": ["OIL"],
                "EXPRESSION": ["79.37 X B/D 6 EXP B/0.9998 16.26"],
            }
        ),
        sidefile=pd.DataFrame(
            {
                "FILENAME": ["LOWE_WCB"],
                "SECTION": [4],
                "SEQUENCE": [20],
                "KEYWORD": ["OIL"],
                "EXPRESSION": ["150 725 B/D 1 MOS EXP X"],
            }
        ),
        data_through=date(2026, 6, 14),
    )


def test_build_package_shapes_rows_and_maps_api10():
    proj = _project(
        [
            {
                "PROPNUM": "P1",
                "API": "42301354570000",
                "LEASE": "Lowe 74 Unit",
                "WELLNUM": "61H",
                "RSV_CAT": "1PDP",
                "DATE_FIRST_PROD": pd.Timestamp("2022-01-07"),
            },
            {
                "PROPNUM": "P2",
                "API": "0HUHF1J2FZ",
                "LEASE": "Sheridan 27A Unit",
                "WELLNUM": "93HU",
                "RSV_CAT": "4PUD",
            },
        ],
        [("P1", date(2026, 6, 14), 30.0)],
    )
    pkg = build_package([proj])
    by_prop = {r[0]: r for r in pkg.property_rows}
    assert by_prop["P1"][1] == "4230135457"
    assert by_prop["P1"][2] == "Lowe 74 Unit 61H"
    assert by_prop["P2"][1] is None
    assert pkg.monthly_rows[0][1] == date(2026, 4, 1)
    kinds = sorted(r[0] for r in pkg.forecast_rows)
    assert kinds == ["property", "sidefile"]
    assert len(pkg.daily_rows) == 1


def test_build_package_rejects_daily_orphans():
    proj = _project(
        [{"PROPNUM": "P1", "API": "42301354570000"}],
        [("GHOST", date(2026, 6, 14), 1.0)],
    )
    with pytest.raises(ValueError, match="GHOST"):
        build_package([proj])


def test_commercial_columns_are_the_ownership_set():
    assert {"BPO_WI", "BPO_NRI", "APO_WI", "APO_NRI"} <= COMMERCIAL_COLS
