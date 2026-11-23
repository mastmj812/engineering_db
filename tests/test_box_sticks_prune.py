"""BOX sticks prune command: the pure parts (no database)."""
from datetime import date
from pathlib import Path

import pytest

from scripts import box_sticks_prune as bp

SRC = Path(bp.__file__).read_text(encoding="utf-8")


def test_child_rows_go_bench_before_dsu_and_the_header_and_id_tables_are_never_deleted():
    assert set(bp.CHILD_TABLES) == {"box.location_stick", "box.location_set_dsu", "box.location_set_bench", "box.location_set_well"}
    assert bp.CHILD_TABLES.index("box.location_set_bench") < bp.CHILD_TABLES.index("box.location_set_dsu")   # bench references dsu
    assert "DELETE FROM box.location_set " not in SRC and "DELETE FROM box.location " not in SRC
    assert SRC.count("DELETE FROM") == 1                                                                     # the one loop over CHILD_TABLES


def test_the_header_note_carries_the_date():
    assert bp.note(date(2026, 11, 23)) == "pruned 2026-11-23: stick, dsu, bench and well rows deleted; header kept"


class _Cur:
    """Answers the header read only: a record set must be refused before anything else is asked."""

    def __init__(self, rows):
        self.rows, self.calls = rows, 0

    def execute(self, sql, params=None):
        self.calls += 1
        return self

    def fetchall(self):
        return self.rows


def test_a_record_set_and_an_unknown_set_are_refused_before_any_delete():
    cur = _Cur([(24, "delaware", True, None, "box_sticks_0.13", None)])
    with pytest.raises(SystemExit, match="record set"):
        bp.prune(cur, [24], date(2026, 11, 23))
    assert cur.calls == 1
    with pytest.raises(SystemExit, match="no set"):
        bp.prune(_Cur([]), [99], date(2026, 11, 23))
