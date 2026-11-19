"""Read-only diff of the v4-shaped result sets against what `raw_novi` holds today.

Writes nothing on either side. Header tables are compared on every well; child tables on a
sample of wells (every k-th API10 with production). The output is one line per v3 column that
the loader fills: rows where both sides have a value, how many are equal, and how many are
null on one side only.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from etl.db import get_connection
from etl.novi_v4 import queries as q

KEYS = {
    "Wells": ("API10",), "WellDetails": ("API10",), "WellSpacing": ("API10",),
    "WellMonths": ("API10", "Year", "Month"),
    "ForecastWellMonths": ("API10", "Date"),
    "DirectionalSurveys": ("API10", "Path"),
}
#: Stamp columns are compared separately (v4 carries its own load times).
SKIP = {"CreatedAt", "ModifiedAt"}
#: Extra predicate on the v3 side so both sides hold the same kind of row.
V3_WHERE = {"ForecastWellMonths": '"IsForecasted"', "WellSpacing": '"DeletedAt" IS NULL'}


def _norm(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, str):
        return v.strip()
    return v


def values_equal(a: Any, b: Any) -> bool:
    """Exact for text, dates, booleans and integers; floats within 1e-6 relative or 1e-4."""
    a, b = _norm(a), _norm(b)
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-4)
    if isinstance(a, date) and isinstance(b, date):
        return a == b
    return a == b


def compare_rows(key_len: int, cols: list[str], v4: list[tuple], v3: list[tuple]) -> dict[str, Any]:
    """Join two row lists on their first `key_len` columns and score every other column."""
    def keyed(rows: list[tuple]) -> dict[tuple, tuple]:
        return {tuple(_norm(x) for x in r[:key_len]): r for r in rows}
    a, b = keyed(v4), keyed(v3)
    common = a.keys() & b.keys()
    out: dict[str, Any] = {
        "v4_rows": len(a), "v3_rows": len(b), "common": len(common),
        "v4_only": len(a) - len(common), "v3_only": len(b) - len(common), "columns": {},
    }
    for i in range(key_len, len(cols)):
        both = eq = v4_null = v3_null = 0
        example = None
        for k in common:
            x, y = a[k][i], b[k][i]
            if x is None and y is None:
                continue
            if x is None:
                v4_null += 1
            elif y is None:
                v3_null += 1
            else:
                both += 1
                if values_equal(x, y):
                    eq += 1
                elif example is None:
                    example = (k, _norm(x), _norm(y))
        out["columns"][cols[i]] = {"both": both, "equal": eq, "v4_null": v4_null, "v3_null": v3_null,
                                   "example": example}
    return out


def _v3_rows(table: str, cols: list[str], api10s: list[str] | None) -> list[tuple]:
    quoted = ", ".join(f'"{c}"' for c in cols)
    where = [V3_WHERE[table]] if table in V3_WHERE else []
    params: tuple = ()
    if api10s is not None:
        where.append('"API10" = ANY(%s)')
        params = (api10s,)
    sql = f'SELECT {quoted} FROM raw_novi."{table}"' + (" WHERE " + " AND ".join(where) if where else "")
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, params)
        rows = cur.fetchall()
        conn.rollback()
    return rows


def sample_wells(every: int) -> list[str]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute('SELECT DISTINCT "API10" FROM raw_novi."WellMonths" ORDER BY 1')
        wells = [str(r[0]).strip() for r in cur.fetchall()]
        conn.rollback()
    return wells[::every]


def compare_table(sf: Any, table: str, api10s: list[str] | None) -> dict[str, Any]:
    key = KEYS[table]
    if table in q.HEADER_TABLES:
        builder, columns = q.HEADER_TABLES[table]
        sql, wells = builder(), None
    else:
        builder, columns = q.CHILD_TABLES[table]
        sql, wells = builder(api10s), api10s
    cols = list(key) + [c for c in columns if c not in key and c not in SKIP]
    with sf.cursor() as cur:
        cur.execute(sql)
        names = [d[0] for d in cur.description]
        idx = [names.index(c) for c in cols]
        v4 = [tuple(r[i] for i in idx) for r in cur.fetchall()]
    return compare_rows(len(key), cols, v4, _v3_rows(table, cols, wells))


def format_report(table: str, r: dict[str, Any]) -> str:
    head = (f"## {table}: v4 {r['v4_rows']:,} rows, v3 {r['v3_rows']:,}, common {r['common']:,}, "
            f"v4 only {r['v4_only']:,}, v3 only {r['v3_only']:,}")
    lines = [head]
    for col, c in r["columns"].items():
        pct = 100.0 * c["equal"] / c["both"] if c["both"] else float("nan")
        flag = "" if c["both"] == c["equal"] and not c["v4_null"] and not c["v3_null"] else "  <--"
        ex = f"  e.g. {c['example']}" if c["example"] else ""
        lines.append(f"  {col:34s} both {c['both']:>10,}  equal {pct:7.3f} %  "
                     f"null in v4 only {c['v4_null']:>7,}  in v3 only {c['v3_null']:>7,}{flag}{ex}")
    return "\n".join(lines)
