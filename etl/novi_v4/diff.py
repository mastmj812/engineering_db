"""Full-population diff of the side-by-side copy against `raw_novi`, run inside Postgres.

Read-only. One FULL JOIN per table on its primary key; for every column the loader fills, the
count of common rows where the two sides differ (NULL on one side counts as a difference).
Floats are compared within 1e-6 relative or 1e-4 absolute, everything else exactly.
"""

from __future__ import annotations

from typing import Any

from etl.db import get_connection
from etl.novi_v4 import queries as q
from etl.novi_v4.compare import KEYS, SKIP, V3_WHERE
from etl.novi_v4.sync import _check_schema

_FLOAT_TYPES = {"double precision", "real", "numeric"}


def column_diff(col: str, is_float: bool) -> str:
    a, b = f'a."{col}"', f'b."{col}"'
    if is_float:
        differs = (f"({a} IS NULL) <> ({b} IS NULL) OR "
                   f"abs({a} - {b}) > greatest(1e-4, 1e-6 * greatest(abs({a}), abs({b})))")
    else:
        differs = f"{a} IS DISTINCT FROM {b}"
    return f'count(*) FILTER (WHERE a."API10" IS NOT NULL AND b."API10" IS NOT NULL AND ({differs}))'


def diff_sql(schema: str, table: str, columns: list[str], float_cols: set[str]) -> str:
    schema = _check_schema(schema)
    key = KEYS[table]
    using = ", ".join(f'"{k}"' for k in key)
    v3 = f'raw_novi."{table}"' + (f" WHERE {V3_WHERE[table]}" if table in V3_WHERE else "")
    picks = ",\n       ".join(f'{column_diff(c, c in float_cols)} AS "{c}"' for c in columns)
    return f"""SELECT count(*) FILTER (WHERE a."API10" IS NOT NULL AND b."API10" IS NOT NULL) AS common,
       count(*) FILTER (WHERE b."API10" IS NULL) AS v4_only,
       count(*) FILTER (WHERE a."API10" IS NULL) AS v3_only,
       {picks}
FROM (SELECT * FROM {schema}."{table}") a
FULL JOIN (SELECT * FROM {v3}) b USING ({using})"""


def diff_table(schema: str, table: str) -> dict[str, Any]:
    _, filled = {**q.HEADER_TABLES, **q.CHILD_TABLES}[table]
    columns = [c for c in filled if c not in KEYS[table] and c not in SKIP]
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'raw_novi' AND table_name = %s", (table,))
        floats = {c for c, t in cur.fetchall() if t in _FLOAT_TYPES}
        cur.execute(diff_sql(schema, table, columns, floats))
        row = cur.fetchone()
        conn.rollback()
    return {"common": row[0], "v4_only": row[1], "v3_only": row[2],
            "differs": dict(zip(columns, row[3:], strict=True))}


def format_diff(table: str, r: dict[str, Any]) -> str:
    lines = [f"## {table}: common {r['common']:,}, v4 only {r['v4_only']:,}, v3 only {r['v3_only']:,}"]
    clean = [c for c, n in r["differs"].items() if n == 0]
    lines.append(f"  equal on every common row: {len(clean)} of {len(r['differs'])} columns")
    for c, n in r["differs"].items():
        if n:
            share = 100.0 * n / r["common"] if r["common"] else float("nan")
            lines.append(f"  {c:34s} differs on {n:>10,} rows ({share:.3f} %)")
    return "\n".join(lines)
