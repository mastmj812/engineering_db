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


# --- scripts.apply_formation_tag_overrides --refresh (pure pieces; no DB) ---

import pytest

from scripts import apply_formation_tag_overrides as afo

# Live rewrite edges below curated.formation_blueox (pg_depend, 2026-10-28):
# (child, child relkind, parent, parent relkind).
_M, _V = "m", "v"
LIVE_EDGES_2026_10_28 = [
    ("curated.bench_reference", _M, "curated.formation_blueox", _M),
    ("curated.box_scout_locations", _V, "curated.erebor_locations", _M),
    ("curated.codev_context", _M, "curated.formation_blueox", _M),
    ("curated.codev_context", _M, "curated.formation_blueox_tvd", _M),
    ("curated.dev_scenario", _V, "curated.codev_context", _M),
    ("curated.erebor_locations", _M, "curated.intel_formation_blueox", _M),
    ("curated.erebor_locations", _M, "curated.intel_pdp_support", _M),
    ("curated.erebor_locations", _M, "curated.net_new_pdp", _M),
    ("curated.erebor_locations", _M, "curated.reconciled_inventory", _M),
    ("curated.erebor_locations", _M, "curated.wells_enriched", _V),
    ("curated.formation_blueox_tvd", _M, "curated.producing_reference", _M),
    ("curated.intel_forecast_accuracy", _M, "curated.formation_blueox_tvd", _M),
    ("curated.intel_forecast_accuracy", _M, "curated.producing_reference", _M),
    ("curated.intel_forecast_accuracy", _M, "curated.reconciled_inventory", _M),
    ("curated.intel_forecast_accuracy_vintage", _M, "curated.bench_reference", _M),
    ("curated.intel_forecast_accuracy_vintage", _M, "curated.formation_blueox_tvd", _M),
    ("curated.intel_forecast_accuracy_vintage", _M, "curated.producing_reference", _M),
    ("curated.intel_formation_blueox", _M, "curated.bench_reference", _M),
    ("curated.intel_formation_blueox", _M, "curated.formation_blueox", _M),
    ("curated.intel_pdp_support", _M, "curated.formation_blueox", _M),
    ("curated.intel_pdp_support", _M, "curated.formation_blueox_tvd", _M),
    ("curated.intel_pdp_support", _M, "curated.intel_formation_blueox", _M),
    ("curated.net_new_pdp", _M, "curated.formation_blueox_tvd", _M),
    ("curated.net_new_pdp", _M, "curated.intel_formation_blueox", _M),
    ("curated.net_new_pdp", _M, "curated.producing_reference", _M),
    ("curated.producing_reference", _M, "curated.formation_blueox", _M),
    ("curated.reconciled_inventory", _M, "curated.formation_blueox_tvd", _M),
    ("curated.reconciled_inventory", _M, "curated.intel_formation_blueox", _M),
    ("curated.reconciled_inventory", _M, "curated.producing_reference", _M),
    ("curated.wells_enriched", _V, "curated.formation_blueox", _M),
    ("curated.wells_enriched", _V, "curated.formation_blueox_tvd", _M),
]


def test_chain_is_a_valid_refresh_of_the_live_graph():
    parents = afo.matview_parents(LIVE_EDGES_2026_10_28)
    assert set(parents) == set(afo.CHAIN)
    assert afo.chain_problems(afo.CHAIN, parents) == []
    assert afo.CHAIN[0] == afo.ROOT and afo.CHAIN[-1] == "curated.erebor_locations"


def test_matview_parents_sees_through_views():
    parents = afo.matview_parents(LIVE_EDGES_2026_10_28)
    # erebor_locations reads formation_blueox_tvd only through wells_enriched
    assert "curated.formation_blueox_tvd" in parents["curated.erebor_locations"]
    assert "curated.wells_enriched" not in parents["curated.erebor_locations"]
    assert "curated.dev_scenario" not in parents  # views never refreshed


def test_chain_problems_catches_order_missing_and_extra():
    parents = afo.matview_parents(LIVE_EDGES_2026_10_28)
    swapped = list(afo.CHAIN)
    i, j = swapped.index("curated.intel_pdp_support"), swapped.index("curated.erebor_locations")
    swapped[i], swapped[j] = swapped[j], swapped[i]
    assert any("before its parent" in p for p in afo.chain_problems(swapped, parents))
    short = [m for m in afo.CHAIN if m != "curated.net_new_pdp"]
    assert afo.chain_problems(short, parents) == [
        "live matview missing from CHAIN: curated.net_new_pdp"]
    extra = [*afo.CHAIN, "curated.production"]
    assert afo.chain_problems(extra, parents) == [
        f"CHAIN member not below {afo.ROOT} live: curated.production"]


def test_split_copy_on_sql44():
    before, after = afo.split_copy(afo.SQL44.read_text(encoding="utf-8"))
    assert "TRUNCATE ref.formation_tag_overrides" in before
    assert not [ln for ln in (before + "\n" + after).splitlines()
                if ln.lstrip().startswith(chr(92) + "copy")]
    assert "COMMENT ON TABLE ref.formation_tag_overrides" in after
    with pytest.raises(ValueError):
        afo.split_copy("SELECT 1;")


def test_seed_diff_and_tag_moves():
    seed = [{"api10": "1", "corrected_code": "WCB_1", "was": "WCB_2", "note": "n"},
            {"api10": "2", "corrected_code": "WCD", "was": "OTHER", "note": "n"},
            {"api10": "3", "corrected_code": "WCC", "was": "WCB_2", "note": "new note"}]
    live = [("3", "WCC", "WCB_2", "old note"), ("4", "WCA_1", "LSSH", "n"),
            ("1", "WCB_1", "WCB_2", "n")]
    assert afo.seed_diff(seed, live) == {"add": ["2"], "change": ["3"], "remove": ["4"]}
    moves = afo.tag_moves({"a": "WCB_1", "b": "WCC", "c": "WCD"},
                          {"a": "WCB_2", "b": "WCC", "d": "WCA_1"})
    assert moves == {("WCB_1", "WCB_2"): 1}


def test_mode_must_be_named():
    with pytest.raises(SystemExit):
        afo.main([])
    with pytest.raises(SystemExit):
        afo.main(["--rebuild", "--dry-run"])
    with pytest.raises(SystemExit):
        afo.main(["--refresh", "--rebuild"])
