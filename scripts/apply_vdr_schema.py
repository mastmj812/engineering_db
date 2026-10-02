"""Apply sql/53 (vdr schema — seller data-room production) and validate it.

  1. sql/53 — schema vdr, tables source / load_file / property / daily /
     monthly / seller_forecast_line, view well_daily, analyst_ro read grants.
     Idempotent; no CASCADE, nothing else in the warehouse depends on it.
  2. validate by identity: every expected relation exists, keys are in place,
     analyst_ro can read, the Data API roles cannot.

Loading data is a separate step (scripts.load_vdr, per data room).

!! DDL on the shared warehouse — explicit authorization required. From repo
root in the venv:
    python -m scripts.apply_vdr_schema
"""

from __future__ import annotations

import sys
from pathlib import Path

from etl.db import get_connection

SQL = Path(__file__).resolve().parent.parent / "sql"
TABLES = ("source", "load_file", "property", "daily", "monthly", "seller_forecast_line")
VIEWS = ("well_daily",)
PKS = {
    "property": ["vdr_id", "propnum"],
    "daily": ["vdr_id", "propnum", "prod_date"],
    "monthly": ["vdr_id", "propnum", "prod_month"],
}

_failures: list[str] = []


def _check(ok: bool, msg: str) -> None:
    print(f"    {'ok  ' if ok else 'FAIL'} {msg}", flush=True)
    if not ok:
        _failures.append(msg)


def main() -> None:
    conn = get_connection()
    try:
        print("[1/2] sql/53 — vdr schema", flush=True)
        with conn.cursor() as cur:
            cur.execute((SQL / "53_vdr_schema.sql").read_text(encoding="utf-8"))
        conn.commit()

        print("[2/2] validate", flush=True)
        with conn.cursor() as cur:
            q = cur.execute
            for t in TABLES:
                _check(
                    q("SELECT to_regclass(%s) IS NOT NULL", (f"vdr.{t}",)).fetchone()[
                        0
                    ],
                    f"table vdr.{t}",
                )
            for v in VIEWS:
                _check(
                    q(
                        "SELECT relkind = 'v' FROM pg_class WHERE oid = to_regclass(%s)",
                        (f"vdr.{v}",),
                    ).fetchone()
                    == (True,),
                    f"view vdr.{v}",
                )
            for t, cols in PKS.items():
                got = [
                    r[0]
                    for r in q(
                        "SELECT a.attname FROM pg_index i "
                        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                        "WHERE i.indrelid = %s::regclass AND i.indisprimary "
                        "ORDER BY array_position(i.indkey::int2[], a.attnum)",
                        (f"vdr.{t}",),
                    ).fetchall()
                ]
                _check(got == cols, f"vdr.{t} PK {got}")
            for rel in (*TABLES, *VIEWS):
                _check(
                    q(
                        "SELECT has_table_privilege('analyst_ro', %s, 'SELECT')",
                        (f"vdr.{rel}",),
                    ).fetchone()[0],
                    f"analyst_ro can read vdr.{rel}",
                )
            for api_role in ("anon", "authenticated"):
                _check(
                    not q(
                        "SELECT has_schema_privilege(%s, 'vdr', 'USAGE')", (api_role,)
                    ).fetchone()[0],
                    f"{api_role} (Data API) has no USAGE on vdr",
                )
    finally:
        conn.close()
    if _failures:
        sys.exit(f"{len(_failures)} check(s) FAILED")
    print("all checks passed", flush=True)


if __name__ == "__main__":
    main()
