"""Load a seller VDR production package into the ``vdr`` schema (sql/53).

One data room = one ``vdr_id``. Every ``.accdb`` under ``--path`` is read and
classified by its tables:

  aries_project  has AC_PROPERTY — the seller's ARIES project: properties,
                 AC_DAILY, AC_PRODUCT (monthly), section-4 AC_ECONOMIC +
                 AR_SIDEFILE (production forecast lines).
  daily_update   AC_DAILY only — a production update. It REVISES days the
                 project already carries (seller re-allocations), not just
                 appends, so files apply in order and the later file wins.

Order: the project first, then updates by the last date each carries.
Volumes land as reported (negatives kept). Commercial columns (WI/NRI,
payout, LOS group) and every non-production ARIES section are never read
into the warehouse — production only (scope rule).

A load REPLACES every row for the vdr_id in one transaction. Reading .accdb
needs the 64-bit "Microsoft Access Driver (*.mdb, *.accdb)" (Windows) and
``pip install -r requirements-vdr.txt``. ``--dry-run`` reads and validates
without touching the database.

    python -m scripts.load_vdr --vdr-id alchemist_merlin --deal alchemist \
        --path "<...>\\Alchemist\\VDR\\Merlin\\02. Reserves" [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ACCESS_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"

ROLE_PROJECT = "aries_project"
ROLE_UPDATE = "daily_update"

# ARIES AC_PROPERTY columns that are commercial terms, not engineering data.
# Never landed, not even inside property.raw.
COMMERCIAL_COLS = frozenset(
    {"BPO_WI", "BPO_NRI", "APO_WI", "APO_NRI", "PAYOUT", "LOS_GROUP"}
)

# ARIES section 4 = production forecast. Every other section (BTU, prices,
# expenses, ownership, ...) is economics and stays out.
PRODUCTION_SECTION = 4

# AC_DAILY source column -> vdr.daily column.
DAILY_COLS = {
    "OIL": "oil_bbl",
    "GAS": "gas_mcf",
    "WATER": "water_bbl",
    "HRS": "hours_on",
    "TBG_PSI": "tbg_psi",
    "CSG_PSI": "csg_psi",
    "CHOKE": "choke",
    "BHP_PSI": "bhp_psi",
}

# AC_PROPERTY source column -> vdr.property typed column.
PROPERTY_COLS = {
    "API": "api14",
    "LEASE": "lease",
    "WELLNUM": "well_num",
    "RSV_CAT": "reserve_category",
    "STATUS": "status",
    "LAND_ZONE": "land_zone",
    "COUNTY": "county",
    "STATE": "state",
    "OPERATOR": "operator",
    "HOLE_DIRECTION": "hole_direction",
    "LATERAL_LENGTH": "lateral_length_ft",
    "MEASURED_DEPTH": "measured_depth_ft",
    "TVD": "tvd_ft",
    "UPR_PERF": "upper_perf_ft",
    "LWR_PERF": "lower_perf_ft",
    "SURFACE_LAT": "surface_lat",
    "SURFACE_LONG": "surface_lon",
    "BH_LAT": "bh_lat",
    "BH_LONG": "bh_lon",
    "DATE_SPUD": "spud_date",
    "DATE_FRAC": "frac_date",
    "DATE_FIRST_PROD": "first_prod_date",
    "TYPE_CURVE": "seller_type_curve",
}
_DATE_PROPERTY_COLS = {"spud_date", "frac_date", "first_prod_date"}


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested; no Access / Postgres)
# ---------------------------------------------------------------------------


def api10_from_aries(api: object) -> str | None:
    """Suite api10 from an ARIES API field, or None for a placeholder.

    Real APIs are all digits (10/12/14, dashes tolerated). Seller PUD rows
    carry alphanumeric placeholders (``0HUHF1J2FZ``) — not wells yet.
    """
    if api is None or (isinstance(api, float) and math.isnan(api)):
        return None
    s = str(api).strip()
    if not s or re.search(r"[A-Za-z]", s):
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) not in (10, 12, 14):
        return None
    return digits[:10]


def classify_tables(table_names: Iterable[str]) -> str:
    names = {t.upper() for t in table_names}
    if "AC_PROPERTY" in names:
        return ROLE_PROJECT
    if "AC_DAILY" in names:
        return ROLE_UPDATE
    raise ValueError(f"not an ARIES project or daily update (tables: {sorted(names)})")


def well_name(lease: object, well_num: object) -> str | None:
    parts = [
        str(x).strip() for x in (lease, well_num) if _present(x) and str(x).strip()
    ]
    return " ".join(parts) or None


def month_start(d: object) -> date:
    ts = pd.Timestamp(d)
    return date(ts.year, ts.month, 1)


def merge_daily(frames: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    """Stack per-file daily frames in load order; the LATER file wins.

    Each frame carries ``propnum`` + ``prod_date`` + the DAILY_COLS targets;
    the surviving row's ``file_name`` records which file supplied it.
    """
    if not frames:
        return pd.DataFrame(
            columns=["propnum", "prod_date", *DAILY_COLS.values(), "file_name"]
        )
    stacked = pd.concat(
        [df.assign(file_name=name, _order=i) for i, (name, df) in enumerate(frames)],
        ignore_index=True,
    )
    stacked = stacked.sort_values(["propnum", "prod_date", "_order"], kind="stable")
    out = stacked.drop_duplicates(["propnum", "prod_date"], keep="last")
    return out.drop(columns="_order").reset_index(drop=True)


def order_files(files: list[AriesFile]) -> list[AriesFile]:
    """Project first, then updates by the last date they carry (name breaks ties)."""
    projects = [f for f in files if f.role == ROLE_PROJECT]
    if len(projects) != 1:
        raise ValueError(
            f"expected exactly one ARIES project .accdb, found {len(projects)}"
        )
    updates = sorted(
        (f for f in files if f.role == ROLE_UPDATE),
        key=lambda f: (f.data_through or date.min, f.name),
    )
    return projects + updates


def production_lines(econ: pd.DataFrame) -> pd.DataFrame:
    """Keep ARIES section-4 (production forecast) lines only."""
    return econ[econ["SECTION"] == PRODUCTION_SECTION].reset_index(drop=True)


def _present(v: object) -> bool:
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    return not (v is pd.NaT)


def _clean(v: object) -> Any:
    """NaN/NaT -> None; pandas/numpy scalars -> python; timestamps -> date."""
    if not _present(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.date()
    if hasattr(v, "item"):
        return v.item()
    return v


def _json_safe(v: object) -> Any:
    v = _clean(v)
    return v.isoformat() if isinstance(v, date) else v


# ---------------------------------------------------------------------------
# Reading (.accdb via pyodbc)
# ---------------------------------------------------------------------------


@dataclass
class AriesFile:
    path: Path
    role: str
    sha256: str
    daily: pd.DataFrame
    properties: pd.DataFrame | None = None
    monthly: pd.DataFrame | None = None
    econ: pd.DataFrame | None = None
    sidefile: pd.DataFrame | None = None
    data_through: date | None = None
    row_counts: dict[str, int] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.path.name


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_table(cur, sql: str) -> pd.DataFrame:
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return pd.DataFrame.from_records([tuple(r) for r in cur.fetchall()], columns=cols)


def read_accdb(path: Path) -> AriesFile:
    try:
        import pyodbc
    except ImportError:
        sys.exit("pyodbc missing - pip install -r requirements-vdr.txt")
    if ACCESS_DRIVER not in pyodbc.drivers():
        sys.exit(
            f"ODBC driver {ACCESS_DRIVER!r} not installed (64-bit Access Database Engine)"
        )

    conn = pyodbc.connect(f"DRIVER={{{ACCESS_DRIVER}}};DBQ={path};ReadOnly=1")
    try:
        cur = conn.cursor()
        tables = [t.table_name for t in cur.tables(tableType="TABLE")]
        role = classify_tables(tables)
        daily_src = ", ".join(["PROPNUM", "D_DATE", *DAILY_COLS])
        daily = _read_table(cur, f"SELECT {daily_src} FROM AC_DAILY")
        daily = daily.rename(
            columns={"PROPNUM": "propnum", "D_DATE": "prod_date", **DAILY_COLS}
        )
        daily["prod_date"] = pd.to_datetime(daily["prod_date"]).dt.date
        f = AriesFile(path=path, role=role, sha256=_sha256(path), daily=daily)
        f.data_through = max(daily["prod_date"]) if len(daily) else None
        f.row_counts["daily"] = len(daily)
        if role == ROLE_PROJECT:
            prop_cols = [c.column_name for c in cur.columns(table="AC_PROPERTY")]
            keep = [c for c in prop_cols if c.upper() not in COMMERCIAL_COLS]
            f.properties = _read_table(
                cur, "SELECT " + ", ".join(f"[{c}]" for c in keep) + " FROM AC_PROPERTY"
            )
            f.monthly = _read_table(
                cur,
                "SELECT PROPNUM, P_DATE, OIL, GAS, WATER, DAYSON, WELLNO FROM AC_PRODUCT",
            )
            f.econ = production_lines(
                _read_table(
                    cur,
                    "SELECT PROPNUM, SECTION, SEQUENCE, QUALIFIER, KEYWORD, EXPRESSION "
                    f"FROM AC_ECONOMIC WHERE SECTION = {PRODUCTION_SECTION}",
                )
            )
            f.sidefile = production_lines(
                _read_table(
                    cur,
                    "SELECT FILENAME, SECTION, SEQUENCE, KEYWORD, EXPRESSION "
                    f"FROM AR_SIDEFILE WHERE SECTION = {PRODUCTION_SECTION}",
                )
            )
            f.row_counts.update(
                property=len(f.properties),
                monthly=len(f.monthly),
                forecast_lines=len(f.econ) + len(f.sidefile),
            )
        return f
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Shaping into vdr.* rows
# ---------------------------------------------------------------------------


@dataclass
class VdrPackage:
    files: list[AriesFile]
    property_rows: list[tuple]
    daily_rows: list[tuple]
    monthly_rows: list[tuple]
    forecast_rows: list[tuple]


PROPERTY_INSERT_COLS = ["propnum", "api10", "well_name", *PROPERTY_COLS.values(), "raw"]
DAILY_INSERT_COLS = ["propnum", "prod_date", *DAILY_COLS.values(), "file_name"]
MONTHLY_INSERT_COLS = [
    "propnum",
    "prod_month",
    "oil_bbl",
    "gas_mcf",
    "water_bbl",
    "days_on",
    "well_count",
    "file_name",
]
FORECAST_INSERT_COLS = [
    "owner_kind",
    "owner_key",
    "qualifier",
    "sequence",
    "keyword",
    "expression",
    "file_name",
]


def build_package(files: list[AriesFile]) -> VdrPackage:
    import json

    files = order_files(files)
    project = files[0]
    assert project.properties is not None and project.monthly is not None
    assert project.econ is not None and project.sidefile is not None

    prop = project.properties
    dupes = prop["PROPNUM"][prop["PROPNUM"].duplicated()].tolist()
    if dupes:
        raise ValueError(f"duplicate PROPNUM in AC_PROPERTY: {dupes}")
    property_rows = []
    for rec in prop.to_dict("records"):
        typed = {dst: _clean(rec.get(src)) for src, dst in PROPERTY_COLS.items()}
        for k in _DATE_PROPERTY_COLS:
            if isinstance(typed[k], datetime):
                typed[k] = typed[k].date()
        raw = {k: _json_safe(v) for k, v in rec.items()}
        property_rows.append(
            (
                rec["PROPNUM"],
                api10_from_aries(rec.get("API")),
                well_name(rec.get("LEASE"), rec.get("WELLNUM")),
                *typed.values(),
                json.dumps(raw),
            )
        )
    known = set(prop["PROPNUM"])

    daily = merge_daily([(f.name, f.daily) for f in files])
    orphans = sorted(set(daily["propnum"]) - known)
    if orphans:
        raise ValueError(
            f"AC_DAILY rows for propnums missing from AC_PROPERTY: {orphans}"
        )
    daily_rows = [
        tuple(_clean(v) for v in r)
        for r in daily[DAILY_INSERT_COLS].itertuples(index=False, name=None)
    ]

    m = project.monthly.copy()
    m["prod_month"] = m["P_DATE"].map(month_start)
    if m.duplicated(["PROPNUM", "prod_month"]).any():
        raise ValueError("AC_PRODUCT has more than one row per property-month")
    monthly_rows = [
        (
            r.PROPNUM,
            r.prod_month,
            _clean(r.OIL),
            _clean(r.GAS),
            _clean(r.WATER),
            _clean(r.DAYSON),
            _clean(r.WELLNO),
            project.name,
        )
        for r in m.itertuples(index=False)
    ]

    forecast_rows = [
        (
            "property",
            r.PROPNUM,
            _clean(r.QUALIFIER) or "",
            int(r.SEQUENCE),
            r.KEYWORD,
            _clean(r.EXPRESSION),
            project.name,
        )
        for r in project.econ.itertuples(index=False)
    ] + [
        (
            "sidefile",
            r.FILENAME,
            "",
            int(r.SEQUENCE),
            r.KEYWORD,
            _clean(r.EXPRESSION),
            project.name,
        )
        for r in project.sidefile.itertuples(index=False)
    ]

    return VdrPackage(files, property_rows, daily_rows, monthly_rows, forecast_rows)


# ---------------------------------------------------------------------------
# Writing + verification
# ---------------------------------------------------------------------------


def _copy(cur, vdr_id: str, table: str, cols: list[str], rows: list[tuple]) -> None:
    with cur.copy(f"COPY vdr.{table} (vdr_id, {', '.join(cols)}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row((vdr_id, *r))


def write_package(conn, vdr_id: str, deal: str, root: Path, pkg: VdrPackage) -> None:
    import json

    with conn.cursor() as cur:
        cur.execute("DELETE FROM vdr.source WHERE vdr_id = %s", (vdr_id,))  # cascades
        cur.execute(
            "INSERT INTO vdr.source (vdr_id, deal, vendor_format, root_path) VALUES (%s, %s, 'aries_accdb', %s)",
            (vdr_id, deal, str(root)),
        )
        for i, f in enumerate(pkg.files):
            cur.execute(
                "INSERT INTO vdr.load_file (vdr_id, file_name, file_role, load_order, file_sha256, "
                "row_counts, data_through) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    vdr_id,
                    f.name,
                    f.role,
                    i,
                    f.sha256,
                    json.dumps(f.row_counts),
                    f.data_through,
                ),
            )
        _copy(cur, vdr_id, "property", PROPERTY_INSERT_COLS, pkg.property_rows)
        _copy(cur, vdr_id, "daily", DAILY_INSERT_COLS, pkg.daily_rows)
        _copy(cur, vdr_id, "monthly", MONTHLY_INSERT_COLS, pkg.monthly_rows)
        _copy(
            cur, vdr_id, "seller_forecast_line", FORECAST_INSERT_COLS, pkg.forecast_rows
        )
    conn.commit()


def verify(conn, vdr_id: str, pkg: VdrPackage) -> list[str]:
    fails: list[str] = []
    expect = {
        "property": len(pkg.property_rows),
        "daily": len(pkg.daily_rows),
        "monthly": len(pkg.monthly_rows),
        "seller_forecast_line": len(pkg.forecast_rows),
        "load_file": len(pkg.files),
    }
    with conn.cursor() as cur:
        for table, n in expect.items():
            got = cur.execute(
                f"SELECT count(*) FROM vdr.{table} WHERE vdr_id = %s", (vdr_id,)
            ).fetchone()[0]
            ok = got == n
            print(
                f"    {'ok  ' if ok else 'FAIL'} vdr.{table}: {got} rows (expected {n})"
            )
            if not ok:
                fails.append(table)
        rows = cur.execute(
            """
            SELECT p.reserve_category, count(*) AS props, count(p.api10) AS with_api10,
                   count(w.api10) AS in_curated_wells,
                   min(d.d0), max(d.d1)
            FROM vdr.property p
            LEFT JOIN curated.wells w ON w.api10 = p.api10
            LEFT JOIN (SELECT propnum, min(prod_date) d0, max(prod_date) d1
                       FROM vdr.daily WHERE vdr_id = %s GROUP BY propnum) d USING (propnum)
            WHERE p.vdr_id = %s
            GROUP BY 1 ORDER BY 1
            """,
            (vdr_id, vdr_id),
        ).fetchall()
        print("    reserve_category | props | api10 | in curated.wells | daily range")
        for cat, props, api, cw, d0, d1 in rows:
            print(f"    {cat!s:<16} | {props:>5} | {api:>5} | {cw:>16} | {d0} .. {d1}")
            if api != cw:
                fails.append(f"{cat}: {api - cw} api10(s) not in curated.wells")
    return fails


def _summarize(pkg: VdrPackage) -> None:
    for i, f in enumerate(pkg.files):
        print(
            f"  [{i}] {f.role:<13} {f.name}  through {f.data_through}  {f.row_counts}"
        )
    print(
        f"  -> property {len(pkg.property_rows)}, daily {len(pkg.daily_rows)} (after last-file-wins), "
        f"monthly {len(pkg.monthly_rows)}, forecast lines {len(pkg.forecast_rows)}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--vdr-id",
        required=True,
        help="lowercase id for this data room, e.g. alchemist_merlin",
    )
    ap.add_argument("--deal", required=True, help="Blue Ox deal codename")
    ap.add_argument(
        "--path",
        required=True,
        type=Path,
        help="folder searched recursively for .accdb files",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="read + validate only; no database writes",
    )
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9_]+", args.vdr_id):
        sys.exit("--vdr-id must match [a-z0-9_]+")

    paths = sorted(args.path.rglob("*.accdb"))
    if not paths:
        sys.exit(f"no .accdb files under {args.path}")
    print(f"reading {len(paths)} file(s)", flush=True)
    pkg = build_package([read_accdb(p) for p in paths])
    _summarize(pkg)
    if args.dry_run:
        print("dry run - nothing written")
        return

    from etl.db import get_connection

    conn = get_connection()
    try:
        write_package(conn, args.vdr_id, args.deal, args.path, pkg)
        print("verify", flush=True)
        fails = verify(conn, args.vdr_id, pkg)
    finally:
        conn.close()
    if fails:
        sys.exit(f"{len(fails)} check(s) FAILED: {fails}")
    print("all checks passed")


if __name__ == "__main__":
    main()
