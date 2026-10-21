"""curated.box_scout_locations (sql/69) — static checks, no database.

Pins (v2, Michael 2026-10-21: "as simple as possible"): the view holds ONLY undrilled stick
locations with a BOX record-run forecast AND Steven's priced default-deck econ; it carries the
minimal land-facing column set (no reconciliation / coverage / Novi tag / NPV / screen_pass
columns); and every script that rebuilds curated.erebor_locations (sql/22, whose DROP ...
CASCADE drops this view) re-creates it right after.
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts import apply_box_scout_locations as app

ROOT = Path(__file__).resolve().parents[1]
SQL69 = (ROOT / "sql" / "69_box_scout_locations.sql").read_text(encoding="utf-8")
BODY = app.view_body(SQL69)

COLUMNS = [
    "stick_id", "location_name", "basin", "bench", "pad_name", "geom", "lateral_ft",
    "box_tier", "oil_eur_bbl", "oil_eur_bbl_per_ft", "gas_eur_mcf", "gas_eur_mcf_per_ft",
    "water_eur_bbl", "water_eur_bbl_per_ft",
    "pv10_mm", "pv20_mm", "irr_pct", "breakeven_wti_pv20", "capex_mm",
    "econ_deck", "box_run_id", "econ_pushed_at",
]


def _code(text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def _select_list(body: str) -> list[str]:
    """Output column names of the final SELECT (alias, else the bare column name)."""
    sel = _code(body).split("\nSELECT\n", 1)[1].split("\nFROM run", 1)[0]
    items, depth, cur = [], 0, ""
    for ch in sel:  # split on top-level commas only
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            items.append(cur)
            cur = ""
        else:
            cur += ch
    items.append(cur)
    names = []
    for it in (" ".join(i.split()) for i in items if i.strip()):
        m = re.search(r"\bAS (\w+)$", it)
        names.append(m.group(1) if m else it.split(".")[-1])
    return names


def test_body_extracts_the_whole_select():
    assert BODY.lstrip().startswith("WITH run AS (")
    assert BODY.rstrip().endswith("AND el.recon_status IS DISTINCT FROM 'realized_phantom'")
    assert ";" not in BODY


def test_minimal_column_set():
    assert _select_list(BODY) == COLUMNS
    for gone in ("recon_status AS", "box_coverage", "prox_", "water_tier", "stick_lateral_ft",
                 "econ_assumption_set_id", "unpriced_reason", "pushed_by"):
        assert gone not in _code(BODY), gone


def test_rows_are_priced_forecast_locations_only():
    code = _code(BODY)
    assert "FROM box.forecast_run WHERE is_record" in code
    assert "bp.coverage IN ('covered', 'covered_provisional')" in code
    # econ is an INNER join on the default deck's newest assumption set, priced rows only
    assert "JOIN box_econ.box_pud_econ be" in code and "LEFT JOIN box_econ" not in code
    assert "e.deck_id = 'wti70_hh3'" in code and "AND be.pv10_mm IS NOT NULL" in code
    assert "ORDER BY max(e.built_at) DESC NULLS LAST, e.assumption_set_id DESC" in code
    # undrilled only (our reconciliation), no PDP — the filter is applied, the column is not shown
    assert "el.recon_status IS DISTINCT FROM 'realized_drift'" in code
    assert "el.category <> 'PDP'" in code
    for alias in ("bso", "bsg", "bsw"):
        assert re.search(rf"{alias}\.run_id = bp\.run_id", code), alias


def test_no_novi_tags_npv_or_steven_screen():
    code = _code(BODY).lower()
    for banned in ("npv", "deplet", "rqt", "spacing_t", "screen_pass", "rejection_step", "intel_pdp_support",
                   "category = 'pud'"):
        assert banned not in code, banned


def test_per_foot_units_tier_grant_and_plain_view():
    code = _code(BODY)
    for s in ("bso", "bsg", "bsw"):
        assert f"{s}.eur_per_kft / 1000.0" in code
    assert "WHEN 'covered' THEN 'validated' ELSE 'provisional'" in code
    assert "GRANT SELECT ON curated.box_scout_locations TO analyst_ro;" in SQL69
    assert "DROP VIEW IF EXISTS curated.box_scout_locations;" in SQL69
    assert "MATERIALIZED" not in _code(SQL69).upper()
    for col in COLUMNS:  # every column is explained to the land team
        assert f"COMMENT ON COLUMN curated.box_scout_locations.{col} IS" in SQL69, col


def test_every_sql22_caller_recreates_the_view():
    callers = [p for p in (ROOT / "scripts").glob("*.py") if "22_erebor_locations.sql" in p.read_text(encoding="utf-8")]
    assert callers
    for p in callers:
        src = p.read_text(encoding="utf-8")
        i = src.index("22_erebor_locations.sql")
        assert "recreate_box_scout(" in src[i:] or "69_box_scout_locations.sql" in src[i:], p.name
    psql = (ROOT / "sql" / "32_wellstick_degenerate_fix.sql").read_text(encoding="utf-8")
    assert psql.index("\\ir 69_box_scout_locations.sql") > psql.index("\\ir 22_erebor_locations.sql")


def test_checks_cover_identity_and_tieout():
    labels = [label for label, _ in app.checks("v_src")]
    for need in ("rows", "expected rows (priced forecast locations, not realized)", "blank oil EUR or PV10 (must be 0)",
                 "deck labels", "oil EUR view vs box (MMbbl)"):
        assert need in labels
    # the independent expected-row query must not be correlated per row (it timed out once)
    assert "WHERE run_id = bp.run_id" not in app._population()
