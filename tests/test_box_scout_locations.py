"""curated.box_scout_locations (sql/69) — static checks, no database.

Pins: the view reads the BOX RECORD run and Steven's default deck only, carries no Novi tag /
NPV and no Steven screen_pass, classes every location the way erebor does (never a zero), and
every script that rebuilds curated.erebor_locations (sql/22, whose DROP ... CASCADE drops this
view) re-creates it right after.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts import apply_box_scout_locations as app

ROOT = Path(__file__).resolve().parents[1]
SQL69 = (ROOT / "sql" / "69_box_scout_locations.sql").read_text(encoding="utf-8")
BODY = app.view_body(SQL69)


def _code(text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def test_body_extracts_the_whole_select():
    assert BODY.lstrip().startswith("WITH run AS (")
    assert BODY.rstrip().endswith("WHERE el.category <> 'PDP'")
    assert ";" not in BODY


def test_record_run_and_default_deck_only():
    code = _code(BODY)
    assert "FROM box.forecast_run WHERE is_record" in code
    assert "e.deck_id = 'wti70_hh3'" in code
    assert "ORDER BY max(e.built_at) DESC NULLS LAST, e.assumption_set_id DESC" in code and "LIMIT 1" in code
    # every BOX join is keyed on the record run, so no other run's numbers can leak in
    for alias in ("bso", "bsg", "bsw", "bpp"):
        assert re.search(rf"{alias}\.run_id = bp\.run_id", code), alias
    assert "be.run_id = bp.run_id" in code


def test_no_novi_tags_npv_or_steven_screen():
    code = _code(BODY).lower()
    for banned in ("npv", "deplet", "rqt", "spacing_t", "screen_pass", "rejection_step", "intel_pdp_support",
                   "category = 'pud'", "category in"):
        assert banned not in code, banned
    assert "el.category <> 'pdp'" in code  # PDP is context, never forecast (rule 8)


def test_coverage_classes_mirror_erebor():
    code = _code(BODY)
    order = ["WHEN bp.coverage IS NOT NULL THEN bp.coverage",
             "THEN 'realized'", "THEN 'not_screened'", "ELSE 'bench_not_in_box'"]
    pos = [code.index(s) for s in order]
    assert pos == sorted(pos)
    assert "WHEN 'covered' THEN 'validated'" in code and "WHEN 'covered_provisional' THEN 'provisional'" in code


def test_per_foot_units_and_grant():
    code = _code(BODY)
    for s in ("bso", "bsg", "bsw"):
        assert f"{s}.eur_per_kft / 1000.0" in code
    assert "GRANT SELECT ON curated.box_scout_locations TO analyst_ro;" in SQL69
    assert "DROP VIEW IF EXISTS curated.box_scout_locations;" in SQL69
    assert "MATERIALIZED" not in _code(SQL69).upper()  # a plain view: no storage, no refresh


def test_every_sql22_caller_recreates_the_view():
    callers = [p for p in (ROOT / "scripts").glob("*.py") if "22_erebor_locations.sql" in p.read_text(encoding="utf-8")]
    assert callers  # apply_erebor_locations at least
    for p in callers:
        src = p.read_text(encoding="utf-8")
        i = src.index("22_erebor_locations.sql")
        assert "recreate_box_scout(" in src[i:] or "69_box_scout_locations.sql" in src[i:], p.name
    psql = (ROOT / "sql" / "32_wellstick_degenerate_fix.sql").read_text(encoding="utf-8")
    assert psql.index("\\ir 69_box_scout_locations.sql") > psql.index("\\ir 22_erebor_locations.sql")


def test_checks_cover_identity_tieout_and_index():
    labels = [label for label, _ in app.checks("v_src")]
    for need in ("rows", "map stick locations", "forecast rows", "record-run forecast PUDs on the map",
                 "oil EUR view vs box (MMbbl)", "EUR on a location without a forecast (must be 0)"):
        assert need in labels
    assert "idx_erebor_locations_geom" in Path(app.__file__).read_text(encoding="utf-8")
