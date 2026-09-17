"""Seed-shape guard for seeds/formation_tag_overrides.csv (sql/44).

Every row is a human-ratified re-tag: keys must be valid api10s, unique, and
map to codes the crosswalk vocabulary knows. No DB required.
"""

import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OVERRIDES = REPO / "seeds" / "formation_tag_overrides.csv"
CROSSWALK = REPO / "seeds" / "formation_crosswalk.csv"


def _rows():
    with OVERRIDES.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_header_contract():
    with OVERRIDES.open(encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    assert header == ["api10", "corrected_code", "was", "note"]


def test_api10_shape_and_uniqueness():
    rows = _rows()
    assert rows, "override seed is empty"
    apis = [r["api10"] for r in rows]
    assert len(apis) == len(set(apis)), "duplicate api10 in overrides"
    bad = [a for a in apis if not re.fullmatch(r"\d{10}", a)]
    assert not bad, f"non-api10 keys: {bad}"


def test_codes_in_known_vocabulary():
    with CROSSWALK.open(encoding="utf-8") as fh:
        known = {r["canonical_code"] for r in csv.DictReader(fh)}
    bad = [(r["api10"], r["corrected_code"]) for r in _rows()
           if r["corrected_code"] not in known]
    assert not bad, f"corrected_code not in crosswalk vocabulary: {bad}"


def test_every_row_is_a_real_change_with_provenance():
    for r in _rows():
        assert r["corrected_code"] != r["was"], f"{r['api10']}: override equals prior tag"
        assert r["note"].strip(), f"{r['api10']}: missing ratification note"
