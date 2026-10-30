"""D117 step 3: the BOX universe takes every Novi stick category BOX forecasts (PUD + RES, never PDP), and `box_pud_run augment`
carries a source build's rows verbatim while adding the RES rows (DB-free: the warehouse, pools and fits are stubbed)."""

from __future__ import annotations

import contextlib
import datetime as dt
import pickle
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from box import production as pr
from box import production16 as p16
from scripts import box_pud_run as bpr


def test_universe_sql_takes_pud_and_res_never_pdp():
    sql = pr._UNIVERSE_SQL
    assert "il.category IN ('PUD', 'RES')" in sql
    assert "'PDP'" not in sql and "il.category = 'PUD'" not in sql
    assert "SELECT il.stick_id, il.report_version, il.category," in sql  # the category rides along for the per-category splits
    # unchanged by D117: the reconciliation filter, the basin filter and the >= 50 % inside-extent rule
    assert "COALESCE(ri.status, 'not_reconciled') IN ('remaining_pud', 'conflict', 'not_reconciled')" in sql
    assert "il.basin = ANY (%(basins)s)" in sql
    assert pr.INSIDE_SHARE == 0.5


def test_classify_ignores_the_novi_category():
    base = {"in_scope": True, "formation_blueox": "WCC", "basin": "delaware", "bench": "WCC", "inside_extent": True}
    for cat in ("PUD", "RES"):
        assert pr.classify(SimpleNamespace(category=cat, **base), ("WCC",)) == "covered"
        assert pr.classify(SimpleNamespace(category=cat, **{**base, "inside_extent": False}), ("WCC",)) == "not_covered_outside_extent"


def test_last_month_pin_never_later_than_the_warehouse(monkeypatch):
    monkeypatch.setattr(bpr.rep, "_read", lambda conn, sql: None)
    monkeypatch.setattr(bpr.rep, "last_full_month", lambda rows: dt.date(2026, 8, 1))
    assert bpr.last_month(None) == dt.date(2026, 8, 1)
    assert bpr.last_month(None, dt.date(2026, 7, 1)) == dt.date(2026, 7, 1)
    with pytest.raises(SystemExit, match="later than"):
        bpr.last_month(None, dt.date(2026, 9, 1))


COLS = ["stick_id", "report_version", "basin", "bench", "in_scope", "formation_blueox", "recon_status", "pad_name", "ll_ft", "wkt", "mid_lon",
        "mid_lat", "stick_ft", "extent_id", "inside_share", "inside_extent", "prod_bench", "coverage"]


def _u(rows):
    d = pd.DataFrame([{**{c: None for c in COLS}, "report_version": "2026Q3", "in_scope": True, "recon_status": "remaining_pud", "ll_ft": 10000.0,
                       "wkt": "LINESTRING(0 0, 0 1)", "stick_ft": 10000.0, "extent_id": 27.0, "inside_share": 1.0, "inside_extent": True, **r}
                      for r in rows])
    return d


def _src_universe():
    return _u([{"stick_id": 1, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "prod_bench": "WCC", "coverage": "covered"},
               {"stick_id": 2, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "prod_bench": "WCC", "coverage": "covered"},
               {"stick_id": 3, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "prod_bench": "WCC", "coverage": "covered"},
               {"stick_id": 9, "basin": "midland", "bench": "BRNT", "formation_blueox": "BRNT", "coverage": "not_covered_emerging",
                "in_scope": False}])


def _live_universe():
    live = _u([{"stick_id": 1, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "prod_bench": "WCC", "coverage": "covered"},
               {"stick_id": 2, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "prod_bench": "WCC", "coverage": "covered",
                "recon_status": "conflict"},  # re-reconciled since the source build: counted, not applied
               {"stick_id": 4, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "prod_bench": "WCC", "coverage": "covered"},
               {"stick_id": 10, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "prod_bench": "WCC", "coverage": "covered"},
               {"stick_id": 11, "basin": "delaware", "bench": "WCC", "formation_blueox": "WCC", "coverage": "not_covered_outside_extent",
                "inside_extent": False, "inside_share": 0.2}])
    live["category"] = ["PUD", "PUD", "PUD", "RES", "RES"]
    return live


def test_augment_universe_adds_res_only_and_counts_drift():
    u, add, drift = bpr.augment_universe(_src_universe(), _live_universe(), "delaware")
    assert sorted(add["stick_id"]) == [10, 11]
    assert list(u["stick_id"]) == [1, 2, 3, 10, 11]  # source rows (its basin) verbatim, then the RES additions
    assert list(u["category"]) == ["PUD", "PUD", "PUD", "RES", "RES"]
    assert u.loc[u["stick_id"] == 2, "recon_status"].item() == "remaining_pud"  # the source row, not the live re-reconciliation
    assert drift == {"source_other_basin_dropped": 1, "source_rows_gone_live": 1, "live_pud_not_in_source": 1, "source_rows_reclassed_live": 1,
                     "res_already_in_source": 0}


def _fit(oil_eur, tag):
    m = np.full(600, oil_eur / 600.0)
    st = {"months_raw": m, "months": m, "eur": oil_eur, "eur_raw": oil_eur, "params": {"haircut": {"method": "none"}}}
    return {"key": tag, "streams": {"oil": dict(st), "gas": dict(st)}, "analogs": [{"api10": "4200000001"}], "flags": [], "n_analogs": 5}


def _loc(stick, gap):
    return {"api10": f"pud{stick}", "stick_id": stick, "prod_bench": "WCC", "lateral_ft": 10000.0, "spacing_ft": gap,
            "planned_spacing_ft": gap or 880.0, "spacing_source": "neighbour_gap" if gap else "default_880", "nearest": None, "near_pdp_ft": None}


@pytest.fixture
def source(tmp_path):
    run = {"built_at": "2026-10-24T00:59:00+00:00", "code_sha": "379e2ad83a5960517290bfd22c57a3d727528e15", "engine_sha": "e", "report_version": ["2026Q3"],
           "wells_dir": "docs/box/pool-2026-10-15", "data_through": dt.date(2026, 7, 1), "cutoff": dt.date(2026, 8, 1), "benches": ["WCC"],
           "haircut": {"method": "none"}, "selection": {"name": "r2", "evidence": "ev.json", "evidence_sha256": "abc"},
           "by_bench": {"WCC": {"spec": "box_v2s_r2", "n_pool": 858, "haircut": {"method": "none"}, "wells_dir": "docs/box/step15-WCC-2026-10-16",
                                "n_locations": 3, "n_forecast": 3}}}
    locs = [_loc(1, 1300.0), _loc(2, 1300.0), _loc(3, None)]
    res = [_fit(100.0, "src1"), _fit(200.0, "src2"), _fit(300.0, "src3")]
    meta = pd.DataFrame({"api10": ["4200000001"], "well_name": ["A"]})
    cum = {s: {"4200000001": np.ones(3)} for s in pr.STREAMS}
    d = tmp_path / "src"
    d.mkdir()
    with open(d / "run.pkl", "wb") as fh:
        pickle.dump({"run": run, "universe": _src_universe(), "locs": locs, "results": res, "analog_meta": meta, "analog_cum_kft": cum}, fh)
    return d


def _stub(monkeypatch, gaps_with_res, gaps_pud_only):
    calls = {}
    monkeypatch.setattr(bpr, "get_connection", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(bpr.pr, "universe", lambda conn, benches: _live_universe())
    monkeypatch.setattr(bpr, "load_evidence", lambda path: ({"groups": {"WCC": {}}}, "abc"))
    monkeypatch.setattr(bpr.di_config, "load", lambda: None)
    monkeypatch.setattr(bpr, "boxfit_sha", lambda: "e")
    monkeypatch.setattr(bpr, "_git_sha", lambda: "f" * 40)
    monkeypatch.setattr(p16, "haircut_from_pack", lambda ev: None)

    def nearest(conn, u, cand):
        g = gaps_with_res if (u["category"] == "RES").any() else gaps_pud_only
        return {int(s): (None if g[int(s)] is None else (g[int(s)], "pud:x")) for s in cand["stick_id"]}

    def build_bench(conn, a, u, b, cfg, t0):
        calls["only"] = set(a.only)
        calls["data_through"] = a.data_through
        locs = [_loc(s, gaps_with_res.get(s, 1500.0)) for s in sorted(a.only)]
        res = [_fit(1000.0 + s, f"new{s}") for s in sorted(a.only)]
        return {"P": {"last": a.data_through, "cutoff": dt.date(2026, 8, 1), "asof": dt.date(2026, 7, 1)},
                "record": {"n_pool": 860, "equivalence": {"n": len(locs), "max_rel_diff": 0.0}, "guard": {"verdict": "not applicable"}},
                "locs": locs, "results": res, "meta": pd.DataFrame({"api10": ["4200000002"], "well_name": ["B"]}),
                "cum": {s: {"4200000002": np.ones(3), "4200000001": np.zeros(3)} for s in pr.STREAMS}}

    monkeypatch.setattr(bpr, "nearest_by_stick", nearest)
    monkeypatch.setattr(bpr, "build_bench", build_bench)
    return calls


@pytest.mark.parametrize("refit", [False, True])
def test_augment_carries_the_source_rows_and_adds_res(monkeypatch, tmp_path, source, refit):
    # stick 2's gap narrows because of RES stick 10 (D64); stick 1 is unchanged; stick 3 has no neighbour either way
    calls = _stub(monkeypatch, gaps_with_res={1: 1300.0, 2: 650.0, 3: None, 10: 650.0}, gaps_pud_only={1: 1300.0, 2: 1300.0, 3: None})
    out = tmp_path / "aug"
    a = SimpleNamespace(src=source, out=out, workers=1, refit_gap_changed=refit)
    assert bpr.cmd_augment(a) == 0
    assert calls["data_through"] == dt.date(2026, 7, 1)  # pinned to the source build, not the live last month
    assert calls["only"] == {10, 2, 1, 3}  # the covered RES row + the gap-changed row + the reference sample (stable carried rows)
    A = bpr._load(out)
    by = {loc["stick_id"]: r for loc, r in zip(A["locs"], A["results"], strict=True)}
    assert sorted(by) == [1, 2, 3, 10]  # RES 11 is outside the extent: a universe row, never fitted
    assert by[1]["key"] == "src1" and by[3]["key"] == "src3"  # carried verbatim, never the reference refit
    assert by[2]["key"] == ("new2" if refit else "src2")
    assert by[10]["key"] == "new10"
    assert list(A["universe"]["stick_id"]) == [1, 2, 3, 10, 11]
    assert set(A["universe"]["basin"]) == {"delaware"}  # D135: the source's other-basin rows drop
    run = A["run"]
    assert run["basin"] == "delaware" and run["data_through"] == dt.date(2026, 7, 1)
    assert run["augmented_from"]["code_sha"].startswith("379e2ad") and run["augmented_from"]["res_added"] == 1
    w = run["by_bench"]["WCC"]
    assert (w["n_locations"], w["n_forecast"]) == (4, 4)
    assert w["d117_augment"]["res_added"] == 1 and w["d117_augment"]["gap_changed"] == 1
    assert w["d117_augment"]["reference_refit_max_rel_diff"] > 0  # the stubbed refit differs from the source: reported, not applied
    assert A["analog_cum_kft"]["oil"]["4200000001"][0] == 1.0  # the source's analog actuals win
    assert "4200000002" in set(A["analog_meta"]["api10"])
    gc = pd.read_csv(out / "gap_changed.csv")
    assert list(gc["stick_id"]) == [2] and gc["gap_with_res_ft"].item() == 650.0
    note = bpr.provenance_clause(run)
    assert "D117 universe (Novi PUD + RES): 1 RES rows added to build 379e2ad" in note
    assert ("except 1 refitted" in note) == refit


def test_months_rel_diff():
    a, b = _fit(100.0, "a"), _fit(100.0, "b")
    assert bpr.months_rel_diff(a, b) == 0.0
    assert bpr.months_rel_diff(_fit(110.0, "a"), b) == pytest.approx(0.1)
    del b["streams"]["gas"]
    assert bpr.months_rel_diff(a, b) == np.inf



def test_water_carry_reuses_only_identical_raw_oil(tmp_path):
    from scripts import box_water_run as bwr

    src_res = [_fit(100.0, "s1"), _fit(200.0, "s2")]
    src = {"run": {"code_sha": "379e2ad"}, "locs": [_loc(1, None), _loc(2, None)], "results": src_res}
    (tmp_path / "oil").mkdir()
    (tmp_path / "wat").mkdir()
    with open(tmp_path / "oil" / "run.pkl", "wb") as fh:
        pickle.dump(src, fh)
    with open(tmp_path / "wat" / "water.pkl", "wb") as fh:
        pickle.dump({"meta": {"run_built_from": "379e2ad", "data_through": "2026-07-01"}, "water": {1: {"w": 1}, 2: {"w": 2}}}, fh)
    A = {"locs": [_loc(1, None), _loc(2, None), _loc(10, None)], "results": [_fit(100.0, "c1"), _fit(250.0, "r2"), _fit(300.0, "n10")]}
    got = bwr.load_carry(tmp_path / "wat", tmp_path / "oil", A, dt.date(2026, 7, 1))
    assert got == {1: {"w": 1}}  # stick 2's raw oil moved (a refit): rebuilt; stick 10 is new
    with pytest.raises(SystemExit, match="through"):
        bwr.load_carry(tmp_path / "wat", tmp_path / "oil", A, dt.date(2026, 8, 1))


def test_compare_reproduced_differing_missing_and_additions():
    from scripts import box_d117_step3 as s3

    def frames(pf, st):
        out = {n: pd.DataFrame(columns=[*k, "image"]) for n, (_, k) in s3.TABLES.items()}
        out["pud_forecast"] = pd.DataFrame(pf, columns=["location_id", "image"])
        out["pud_forecast_stream"] = pd.DataFrame(st, columns=["location_id", "stream", "image"])
        return out

    live = frames([(1, '{"coverage": "covered", "planned_spacing_ft": 880.0}'), (2, '{"coverage": "covered", "planned_spacing_ft": 1300.0}'),
                   (3, '{"coverage": "covered"}')], [(1, "oil", '{"eur": 1.0}')])
    box = frames([(1, '{"coverage": "covered", "planned_spacing_ft": 880.0}'), (2, '{"coverage": "covered", "planned_spacing_ft": 650.0}'),
                   (9, '{"coverage": "covered"}')], [(1, "oil", '{"eur": 1.0}'), (9, "oil", '{"eur": 2.0}')])
    summ, diffs = s3.compare(live, box)
    pf = summ["pud_forecast"]
    assert (pf["reproduced"], pf["differ"], pf["missing_in_container"], pf["container_only"]) == (1, 1, 1, 1)
    assert pf["differ_columns"] == {"planned_spacing_ft": 1}
    assert summ["pud_forecast_stream"] == {"live_rows": 1, "reproduced": 1, "differ": 0, "differ_columns": {}, "missing_in_container": 0,
                                           "container_only": 1}
    assert list(diffs["location_id"]) == [2]
