"""
Generate sql/02_raw_novi_ddl.sql from Novi's shipped schema.postgres.sql.

Novi ships an authoritative PostgreSQL schema with each bulk download. This
script reads it, filters to the MVP tables we care about, and rewrites every
table reference to live inside the `raw_novi` schema. Also adds an `ingested_at`
column to every table for ETL traceability.

Usage:
    # First ensure Novi bulk has been synced at least once, so schema.postgres.sql
    # exists somewhere on disk (typically under data/<scope>/.../Bulk/).
    python -m scripts.generate_novi_ddl --schema-file data/us-horizontals/All\\ basins/All\\ subbasins/Bulk/schema.postgres.sql

Output:
    sql/02_raw_novi_ddl.sql
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Tables we want to ingest for the MVP. Add to this list as analytical needs grow.
# Names must match Novi's table names exactly (case-sensitive, PascalCase).
MVP_TABLES: set[str] = {
    "Wells",
    "WellMonths",
    "WellDetails",
    "WellSpacing",
    "ForecastWellMonths",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema-file",
        type=Path,
        required=True,
        help="Path to Novi's schema.postgres.sql (found in the bulk download directory)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sql/02_raw_novi_ddl.sql"),
        help="Where to write the generated DDL (default: sql/02_raw_novi_ddl.sql)",
    )
    parser.add_argument(
        "--all-tables",
        action="store_true",
        help="Generate DDL for every table Novi ships, not just the MVP set",
    )
    return parser.parse_args()


# Regex matchers for Novi's shipped DDL. They use double-quoted PascalCase
# identifiers throughout, e.g. CREATE TABLE "WellDetails" (...).
CREATE_TABLE_RE = re.compile(r'CREATE TABLE\s+"(?P<name>[A-Za-z0-9_]+)"', re.IGNORECASE)
TABLE_REF_RE = re.compile(r'"(?P<name>[A-Za-z0-9_]+)"')  # generic quoted identifier


def split_statements(sql: str) -> list[str]:
    """Split a SQL file into statements on semicolons that end a line.

    Naive but works for Novi's schema file because it doesn't embed
    semicolons inside function bodies or string literals.
    """
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        buffer.append(line)
        if line.rstrip().endswith(";"):
            statements.append("\n".join(buffer).strip())
            buffer = []
    if buffer and "\n".join(buffer).strip():
        statements.append("\n".join(buffer).strip())
    return statements


def statement_table_name(stmt: str) -> str | None:
    """Return the table name a CREATE/ALTER/INDEX statement applies to, or None."""
    match = CREATE_TABLE_RE.search(stmt)
    if match:
        return match.group("name")

    # ALTER TABLE "Foo" / CREATE [UNIQUE] INDEX ... ON "Foo"
    alter_match = re.search(r'ALTER TABLE\s+"([A-Za-z0-9_]+)"', stmt, re.IGNORECASE)
    if alter_match:
        return alter_match.group(1)
    on_match = re.search(r'ON\s+"([A-Za-z0-9_]+)"', stmt, re.IGNORECASE)
    if on_match:
        return on_match.group(1)
    return None


def prefix_table_refs(stmt: str, tables_in_scope: set[str]) -> str:
    """Prefix every reference to an in-scope table with raw_novi.

    Conservative: only prefixes identifiers that appear in tables_in_scope,
    leaving column names and other quoted identifiers alone.
    """
    def replace(match: re.Match) -> str:
        name = match.group("name")
        if name in tables_in_scope:
            # Skip if already prefixed
            start = match.start()
            preceding = stmt[max(0, start - 10) : start]
            if preceding.endswith("raw_novi."):
                return match.group(0)
            return f'raw_novi."{name}"'
        return match.group(0)

    return TABLE_REF_RE.sub(replace, stmt)


def inject_ingested_at(stmt: str) -> str:
    """Add an `ingested_at` column to CREATE TABLE statements for ETL traceability.

    Inserts it just before the closing `)` of the column list.
    """
    if not stmt.lstrip().upper().startswith("CREATE TABLE"):
        return stmt

    # Find the last `)` that closes the column list (the one followed by `;` or
    # by trailing whitespace and `;`).
    paren_depth = 0
    last_open = -1
    matching_close = -1
    for i, ch in enumerate(stmt):
        if ch == "(":
            if paren_depth == 0:
                last_open = i
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
            if paren_depth == 0:
                matching_close = i
                break
    if last_open < 0 or matching_close < 0:
        logger.warning("Could not parse CREATE TABLE structure; skipping ingested_at injection")
        return stmt

    new_column = ',\n    "ingested_at" timestamptz NOT NULL DEFAULT now()'
    return stmt[:matching_close] + new_column + "\n" + stmt[matching_close:]


def generate(schema_file: Path, output_file: Path, mvp_only: bool) -> None:
    if not schema_file.exists():
        sys.exit(f"Schema file not found: {schema_file}")

    raw_sql = schema_file.read_text(encoding="utf-8")
    statements = split_statements(raw_sql)

    # First pass: discover all tables in the file
    all_tables: set[str] = set()
    for stmt in statements:
        match = CREATE_TABLE_RE.search(stmt)
        if match:
            all_tables.add(match.group("name"))

    if not all_tables:
        sys.exit("No CREATE TABLE statements found in schema file")

    if mvp_only:
        missing = MVP_TABLES - all_tables
        if missing:
            logger.warning("MVP tables not present in shipped schema: %s", sorted(missing))
        tables_in_scope = MVP_TABLES & all_tables
    else:
        tables_in_scope = all_tables

    logger.info("Tables in scope: %s", sorted(tables_in_scope))

    # Second pass: emit only statements that touch in-scope tables, prefixed
    output_lines: list[str] = [
        "-- =============================================================================",
        "-- raw_novi DDL - generated from Novi's shipped schema.postgres.sql",
        "-- Source file: " + str(schema_file),
        f"-- Tables included: {', '.join(sorted(tables_in_scope))}",
        "-- ",
        "-- DO NOT EDIT BY HAND. Regenerate with scripts/generate_novi_ddl.py.",
        "-- =============================================================================",
        "",
    ]

    for stmt in statements:
        table = statement_table_name(stmt)
        if table is None:
            # Statements without a table reference (e.g. SET, COMMENT) are skipped.
            continue
        if table not in tables_in_scope:
            continue

        rewritten = prefix_table_refs(stmt, tables_in_scope)
        if rewritten.lstrip().upper().startswith("CREATE TABLE"):
            rewritten = inject_ingested_at(rewritten)
        output_lines.append(rewritten)
        if not rewritten.rstrip().endswith(";"):
            output_lines[-1] = output_lines[-1] + ";"
        output_lines.append("")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(output_lines), encoding="utf-8")
    logger.info("Wrote %s (%d statements)", output_file, len(output_lines) - 7)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    generate(args.schema_file, args.output, mvp_only=not args.all_tables)


if __name__ == "__main__":
    main()
