"""BOX sticks storage (phase 4, sql/73): generator output <-> table rows, the round trip that makes a stored set
reproducible, and static checks that the writer, the SQL and the Novi store path agree. DB-free."""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest
from narvi import generate as ng
from narvi import placement as npl
from shapely.geometry import LineString, box

from box.sticks import core, store
from box.sticks.reads import anchors_of, default_cfg, link_fn
from scripts import box_sticks_run as run

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "sql" / "73_box_location_set.sql").read_text(encoding="utf-8")
M = 1 / 3.280839895
X0, Y0 = 600_000.0, 3_500_000.0
CFG, LINK = default_cfg("delaware"), link_fn()


def _dsu(w_ft: float = 5280.0, h_ft: float = 10560.0) -> core.Dsu:
    def well(wid: str, code: str, depth: float | None, x_ft: float, member: bool = True) -> core.Well:
        x = X0 + x_ft * M
        return core.Well(wid, code, depth, LineString([(x, Y0 + 400 * M), (x, Y0 + (h_ft - 400) * M)]), member)

    benches = [
        core.Bench("BS3_S", 1, 10800.0, "direct", 880.0, 1.0, control=12.5, report_err=(41.0, 120.0), spacing_basis={"n_eff": 12.5, "band": "0-2 mi"}),
        core.Bench("WCA_1", 2, 11200.0, "thickness", 990.0, 1.0, control=3.25, tvd_err_median_ft=52.0, tvd_err_p90_ft=150.0, anchors=("BS3_S",),
                   second_tvd_ft=11380.0, flags=(core.SECOND_LEVEL,), spacing_basis={"n_eff": 3.25, "band": "2-5 mi"}),
        core.Bench("WCB_1", 3, 11700.0, "bracket", 1100.0, 1.0, control=1.0, tvd_err_median_ft=70.0, tvd_err_p90_ft=190.0, anchors=("WCA_1", "WCC"),
                   spacing_basis={"n_eff": 1.0, "band": "5-10 mi"}),
        core.Bench("WCC", 4, None, "none", 1320.0, 0.6, spacing_basis={}),
        core.Bench("AVA_1", 0, 9000.0, "direct", 880.0, 0.05, control=2.0, spacing_basis={}),
    ]
    wells = [well("4230100001", "BS3_S", 10810.0, 700.0), well("4230100002", "BS3_S", None, 1580.0), well("4230100003", "WCA_1", 11190.0, 5600.0, member=False)]
    return core.Dsu(pad_id=7, basin="delaware", polygon=box(X0, Y0, X0 + w_ft * M, Y0 + h_ft * M), az_grid_deg=0.0, az_true_deg=0.9, az_basis="test",
                    benches=benches, wells=wells, wca_class="one member", wca_dominant="WCA_1")


def test_the_four_narvi_engine_functions_have_public_names() -> None:
    # decision 2026-11-18 (Q7): public names since narvi #34; a missing one must fail here, not in a basin run
    assert callable(npl.longest_segment) and callable(ng.make_leg) and callable(ng.single_well) and callable(ng.place_uturns)


def test_anchors_and_expected_error_reach_the_stick() -> None:
    res = core.generate_dsu(_dsu(), CFG, LINK)
    by = {s["bench"]: s["tvd_basis"] for s in res.sticks}
    assert by["BS3_S"]["anchors"] == [] and (by["BS3_S"]["held_out_median_ft"], by["BS3_S"]["held_out_p90_ft"]) == (41.0, 120.0)
    assert by["WCA_1"]["anchors"] == ["BS3_S"] and by["WCA_1"]["held_out_median_ft"] == 52.0
    assert by["WCB_1"]["anchors"] == ["WCA_1", "WCC"]
    assert anchors_of("bracket", "LSSH/WCA_1") == ("LSSH", "WCA_1") and anchors_of("direct", "WCA") == () and anchors_of("offset", None) == ()


def test_the_reported_direct_error_moves_no_stick() -> None:
    d = _dsu()
    bare = replace(d, benches=[replace(b, report_err=None) for b in d.benches])
    a, b = core.generate_dsu(d, CFG, LINK), core.generate_dsu(bare, CFG, LINK)
    for s in a.sticks + b.sticks:
        s["tvd_basis"] = {k: v for k, v in s["tvd_basis"].items() if not k.startswith("held_out")}
    assert not store.diff_sticks(a.sticks, b.sticks) and len(a.sticks) == len(b.sticks) > 0


def test_stick_row_carries_every_stored_column() -> None:
    res = core.generate_dsu(_dsu(), CFG, LINK)
    s = next(s for s in res.sticks if s["bench"] == "WCA_1")
    r = store.stick_row(s, 7, "overlap", 0.93, 12.5)
    assert r["well_name"] == "7-WCA_1-07" and r["slot_no"] == 7 and (r["match_method"], r["match_share"], r["match_offset_ft"]) == ("overlap", 0.93, 12.5)
    assert r["tvd_rung"] == "thickness" and r["tvd_anchor"] == ["BS3_S"] and r["second_level_tvd_ft"] == 11380.0 and core.SECOND_LEVEL in r["flags"]
    assert r["legs_wkt"].startswith("MULTILINESTRING ((") and r["turn_wkt"] is None and r["azimuth_deg"] == 0.9 and len(r["gunbarrel_x_ft"]) == r["n_legs"]
    assert set(run._STICK_COLS) <= set(r)
    with pytest.raises(ValueError, match="unknown flag"):
        store.stick_row(s | {"flags": ["made_up"]}, 1, "seed")


def test_bench_rows_state_every_bench_with_its_reason() -> None:
    d = _dsu()
    rows = {r["formation_blueox"]: r for r in store.bench_rows(d, core.generate_dsu(d, CFG, LINK))}
    assert set(rows) == {b.code for b in d.benches}
    assert rows["WCC"]["no_row_reason"] == "no_depth" and rows["AVA_1"]["no_row_reason"] == "sliver" and rows["WCC"]["sticks"] == 0
    assert rows["BS3_S"]["tvd_err_median_ft"] == 41.0 and rows["BS3_S"]["spacing_basis"]["control"] == 12.5
    assert rows["BS3_S"]["sticks"] > 0 and sum(rows["BS3_S"]["rows_culled"].values()) >= 1          # the rows beside its two wells
    assert set(run._BENCH_COLS) <= set(rows["BS3_S"])


def test_a_stored_dsu_regenerates_the_same_sticks() -> None:
    d = _dsu()
    res = core.generate_dsu(d, CFG, LINK)
    wells = {w["api10"]: w for w in store.well_rows(d)}
    back = store.rebuild_dsu("delaware", d.polygon, store.dsu_row(d, res), store.bench_rows(d, res), wells)
    again = core.generate_dsu(back, CFG, LINK)
    assert not store.diff_sticks(res.sticks, again.sticks)
    assert [(b["code"], b["no_row_reason"], b.get("sticks")) for b in res.benches] == [(b["code"], b["no_row_reason"], b.get("sticks")) for b in again.benches]
    moved = [dict(s, target_tvd_ft=s["target_tvd_ft"] + 1.0) for s in again.sticks]
    assert store.diff_sticks(res.sticks, moved)                                                    # the comparison can fail


def _columns(table: str) -> set[str]:
    m = re.search(rf"CREATE TABLE IF NOT EXISTS box\.{table} \((.*?)\n\);", SQL, re.DOTALL)
    assert m is not None, table
    return {c.group(1) for c in re.finditer(r"^\s{4}([a-z_0-9]+)\s", m.group(1), re.MULTILINE) if c.group(1) not in ("primary", "constraint", "foreign", "check")}


def test_writer_columns_are_the_sql_columns() -> None:
    assert set(run._STICK_COLS) | {"set_id", "location_id", "legs_geom", "turn_geom", "detail"} == _columns("location_stick")
    assert set(run._DSU_COLS) | {"set_id"} == _columns("location_set_dsu")
    assert set(run._BENCH_COLS) | {"set_id", "spacing_basis", "rows_culled"} == _columns("location_set_bench")
    assert _columns("location_set_well") == {"set_id", "api10", "formation_blueox", "depth_ft", "status", "planned", "screen", "geom"}


def test_sql73_is_additive_and_guarded() -> None:
    code = re.sub(r"--.*", "", SQL)
    assert not re.search(r"\bDROP\s+(TABLE|INDEX|MATERIALIZED|VIEW|SCHEMA|COLUMN)\b", code, re.IGNORECASE) and "CASCADE" not in code.replace("ON DELETE CASCADE", "")
    assert "MATERIALIZED VIEW" not in code                                   # nothing to REFRESH, nothing for the nightly
    assert code.count("ADD COLUMN IF NOT EXISTS") == 6 and "RESTART WITH 10000001" in code and "last_value FROM box.location_location_id_seq" in code
    later = re.sub(r"--.*", "", (ROOT / "sql" / "77_box_sticks_grid_rung.sql").read_text(encoding="utf-8"))   # generator 0.13 widened the checks
    for flag in store.STICK_FLAGS:
        assert f"'{flag}'" in later and (f"'{flag}'" in code or flag in ("grid_bounded", "outside_grid"))
    for rung in store.RUNGS:
        assert later.count(f"'{rung}'") == 2                                # on the stick and on the bench
    assert "'none'" in later and "DROP TABLE" not in later and "DROP COLUMN" not in later and "DROP INDEX" not in later and "CASCADE" not in later
    from scripts import apply_box_sticks_grid_rung as ab

    for names in ab.CONSTRAINTS.values():
        for n in names:
            assert later.count(f"DROP CONSTRAINT IF EXISTS {n};") == 1 and later.count(f"ADD CONSTRAINT {n}") == 1
    assert "legs_geom::extensions.geography" in code and "bench_scope" not in code and "box.extent" not in code


def test_the_novi_store_path_never_reads_our_sticks() -> None:
    src = (ROOT / "scripts" / "box_pud_run.py").read_text(encoding="utf-8")
    assert "l.source = 'novi' AND l.basin = %s" in src and "AND basin = %s AND source = 'novi'" in src


def test_every_moving_constant_is_in_the_set_cfg() -> None:
    t = run.thresholds("midland")
    assert t["generator"]["tight_cap_ft"] == 440.0 and t["generator"]["min_lateral_ft"] == 7000.0 and t["chain"]["THICK_RULE"] == "rank"
    assert t["spacing"]["FLOOR_FT"] == 1320.0 and t["identity"] == {"corridor_ft": 220.0, "min_share": 0.5}
    assert t["generator"]["stacked"] != run.thresholds("delaware")["generator"]["stacked"]         # the envelope is per basin
    assert all(p.exists() for p in run.file_inputs().values())


def test_the_stored_set_is_read_back_with_exact_floats() -> None:
    # 2026-11-18: the live pooler session reads float8 with extra_float_digits = 0; the regeneration check then compared
    # 15-digit values against the stored ones and failed on every carried depth (rolled back, nothing stored)
    src = (ROOT / "scripts" / "box_sticks_run.py").read_text(encoding="utf-8")
    assert src.index('q("SET LOCAL extra_float_digits = 1")') < src.index("FROM box.location_set_bench WHERE set_id = %s AND pad_id = ANY(%s)")


def test_the_record_flip_supersedes_before_it_sets_and_defaults_to_a_dry_run() -> None:
    src = (ROOT / "scripts" / "box_sticks_run.py").read_text(encoding="utf-8")
    body = src[src.index("def flip_record"):src.index("def cmd_record")]
    # one record per basin is a unique index: the old record must be cleared first, in the same transaction
    assert body.index("SET is_record = false, superseded_by = %s WHERE basin = %s AND is_record") < body.index("SET is_record = true WHERE set_id = %s")
    assert "location_stick SET" not in body and "DELETE" not in body                    # the flip touches no stick row
    assert run.main.__doc__ is None and "if bad or not go:" in src[src.index("def cmd_record"):src.index("def main")]



def test_a_grid_note_survives_the_stored_round_trip() -> None:
    """Generator 0.13: the grid note is a stick flag, not a bench column; the rebuild reads it back from the stored sticks."""
    import dataclasses

    d = _dsu()
    d = dataclasses.replace(d, benches=[dataclasses.replace(b, flags=(*b.flags, "grid_bounded")) if b.code == "BS3_S" else b for b in d.benches])
    res = core.generate_dsu(d, CFG, LINK)
    assert any("grid_bounded" in s["flags"] for s in res.sticks if s["bench"] == "BS3_S")
    wells = {w["api10"]: w for w in store.well_rows(d)}
    args = ("delaware", d.polygon, store.dsu_row(d, res), store.bench_rows(d, res), wells)
    assert store.diff_sticks(res.sticks, core.generate_dsu(store.rebuild_dsu(*args), CFG, LINK).sticks)             # without the sticks: the note is lost
    assert not store.diff_sticks(res.sticks, core.generate_dsu(store.rebuild_dsu(*args, res.sticks), CFG, LINK).sticks)
