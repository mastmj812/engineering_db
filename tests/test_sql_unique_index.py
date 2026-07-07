"""SQL-file lint: every materialized view must have a UNIQUE index defined in
the SAME sql/NN file.

A UNIQUE index is the precondition for ``REFRESH MATERIALIZED VIEW
CONCURRENTLY`` — without it the concurrent refresh errors at runtime, and the
warehouse convention (see CLAUDE.md) is to co-locate the index with the
matview so a new sql/NN file can never introduce a matview that can't be
refreshed concurrently. This test is the tripwire: add a matview without its
unique index and CI goes red.

Pure static parsing — no database, no Supabase. Runs anywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

# Schema-qualified or bare identifier (optionally double-quoted).
_IDENT = r'[a-zA-Z0-9_."]+'
_MATVIEW_RE = re.compile(
    rf"CREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?({_IDENT})",
    re.IGNORECASE,
)
_UNIQUE_INDEX_ON_RE = re.compile(
    rf"CREATE\s+UNIQUE\s+INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?"
    rf"{_IDENT}\s+ON\s+({_IDENT})",
    re.IGNORECASE,
)


def _strip_line_comments(text: str) -> str:
    """Drop ``-- ...`` to end of line so a matview mentioned in a comment
    isn't mistaken for a real DDL statement. (Our sql/ files don't use
    ``--`` inside string literals, so this is safe here.)"""
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _norm(identifier: str) -> str:
    return identifier.replace('"', "").lower()


def _sql_files() -> list[Path]:
    return sorted(SQL_DIR.glob("*.sql"))


@pytest.mark.parametrize("sql_path", _sql_files(), ids=lambda p: p.name)
def test_matview_has_unique_index_in_same_file(sql_path: Path) -> None:
    body = _strip_line_comments(sql_path.read_text(encoding="utf-8"))
    matviews = {_norm(m) for m in _MATVIEW_RE.findall(body)}
    if not matviews:
        pytest.skip("no materialized view defined in this file")

    unique_index_targets = {_norm(t) for t in _UNIQUE_INDEX_ON_RE.findall(body)}
    missing = sorted(mv for mv in matviews if mv not in unique_index_targets)

    assert not missing, (
        f"{sql_path.name}: materialized view(s) {missing} have no matching "
        f"CREATE UNIQUE INDEX ... ON <view> in the same file. A UNIQUE index "
        f"is required before REFRESH ... CONCURRENTLY works (CLAUDE.md "
        f"warehouse rules). Add the index in this file before merging."
    )
