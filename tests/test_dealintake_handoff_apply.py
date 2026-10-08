"""handoff --apply: write order, verification, and the never-overwrite-edits
guards. DB-free: fake narvi / anduin / narvi read-back."""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import time
from typing import Any

import pytest

from dealintake import handoff


def _plan() -> dict[str, Any]:
    return {
        "status": "READY", "deal": "Rally Caps", "codename": "RALLY CAPS", "run_dir": "runs/x",
        "units": [{"body": {"deal_id": "u1", "scenario_id": "plan_u1", "zones": [{"formation": "WCB_2"}]},
                   "expected": {"WCB_2": 2}}],
        "curves": [{"name": "WCB_2_North", "preview_oil": {"eur_per_unit": 100.0},
                    "save_body": {"name": "WCB_2_North", "included_api10s": ["4200000001", "4200000002"]}}],
        "blueox_zones": [{"zone_name": "WCB_2_North", "reserve_category": "PUD", "benches": ["WCB_2"],
                          "scenario_scope": [{"deal_id": "u1", "scenario_id": "plan_u1"}]}],
        "narvi_selections": [{"deal_id": "u1", "scenario_id": "plan_u1"}],
    }


class Store:
    """narvi as the read-back sees it."""

    def __init__(self, planned: dict[str, int] | None = None) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.planned, self.n = planned, 0
        self.saves: list[dict[str, Any]] = []

    def save_composed(self, body: dict[str, Any]) -> dict[str, Any]:
        self.n += 1
        self.saves.append(body)
        self.rows[(body["deal_id"], body["scenario_id"])] = {
            "updated_at": f"2026-10-08T12:00:{self.n:02d}",
            "planned": self.planned if self.planned is not None else {"WCB_2": 2}}
        return {"saved_wells": 2}

    def saved(self, conn: Any, deal_id: str, scenario_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.rows.get((deal_id, scenario_id), {"updated_at": None, "planned": {}}))


class FakeAnduin:
    def __init__(self) -> None:
        self.user = {"display_name": "Michael Mast"}
        self.deals_: list[dict[str, Any]] = []
        self.curves: dict[str, dict[str, Any]] = {}
        self.config: dict[str, Any] | None = None
        self.calls: list[str] = []

    def login(self) -> None:
        self.calls.append("login")

    def deals(self) -> list[dict[str, Any]]:
        self.calls.append("deals")
        return self.deals_

    def create_deal(self, name: str, notes: str | None = None) -> dict[str, Any]:
        d = {"id": "deal-1", "name": name}
        self.deals_.append(d)
        return d

    def deal(self, deal_id: str) -> dict[str, Any]:
        return {"curves": [{"id": k, "name": v["name"]} for k, v in self.curves.items() if v["deal_id"] == deal_id]}

    def _row(self, tc_id: str, body: dict[str, Any], deal_id: str | None) -> dict[str, Any]:
        row = {"id": tc_id, "name": body["name"], "included_api10s": list(body["included_api10s"]),
               "deal_id": deal_id, "risk_multipliers": {}, "provenance": {},
               "series": {"streams": {"oil": {"fitted": {"qi": 90.0, "Di": 2.0, "b": 1.1, "eur_per_unit": 100.4}}}}}
        self.curves[tc_id] = row
        return copy.deepcopy(row)

    def save_type_curve(self, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("save")
        return self._row(f"tc-{len(self.curves) + 1}", body, None)

    def patch_type_curve(self, tc_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.curves[tc_id]["deal_id"] = body["deal_id"]
        return copy.deepcopy(self.curves[tc_id])

    def new_version(self, tc_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("version")
        deal = self.curves[tc_id]["deal_id"]
        self.curves[tc_id]["deal_id"] = None
        return self._row(f"tc-{len(self.curves) + 1}", body, deal)

    def type_curve(self, tc_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.curves[tc_id])

    def blueox_config(self, deal_id: str) -> dict[str, Any]:
        return {"config": copy.deepcopy(self.config)}

    def put_blueox_config(self, deal_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append("config")
        self.config = copy.deepcopy(body)
        return {"config": copy.deepcopy(body)}


def _apply(tmp_path, store, an, **kw):
    return handoff.apply(_plan(), tmp_path, store, an, contextlib.nullcontext, saved_fn=store.saved, **kw)


def test_fresh_apply_writes_narvi_then_anduin_and_pins_the_config(tmp_path):
    store, an = Store(), FakeAnduin()
    out = _apply(tmp_path, store, an)
    assert [n["action"] for n in out["narvi"]] == ["saved"] and out["narvi"][0]["verified"]
    assert out["curves"][0]["action"] == "saved" and out["curves"][0]["diff_pct"] == 0.4
    assert an.curves["tc-1"]["deal_id"] == "deal-1"
    cfg = an.config
    assert cfg["codename"] == "RALLY CAPS" and cfg["prepared_by"] == "Michael Mast"
    assert cfg["zones"][0]["type_curve_id"] == "tc-1" and cfg["narvi_selections"] == _plan()["narvi_selections"]
    assert (tmp_path / handoff.STATE_FILE).exists()


def test_rerun_with_nothing_changed_writes_nothing(tmp_path):
    store, an = Store(), FakeAnduin()
    _apply(tmp_path, store, an)
    an.calls.clear()
    out = _apply(tmp_path, store, an)
    assert len(store.saves) == 1
    assert [c["action"] for c in out["curves"]] == ["unchanged"] and "save" not in an.calls


def test_narvi_edited_since_handoff_is_refused_before_any_write(tmp_path):
    store, an = Store(), FakeAnduin()
    _apply(tmp_path, store, an)
    store.rows[("u1", "plan_u1")]["updated_at"] = "2026-10-09T09:00:00"     # Michael re-saved in narvi
    with pytest.raises(handoff.HandoffRefused, match="edited in narvi"):
        _apply(tmp_path, store, an)
    assert len(store.saves) == 1
    _apply(tmp_path, store, an, replace=True)
    assert len(store.saves) == 2


def test_scenario_saved_outside_the_handoff_is_refused(tmp_path):
    store, an = Store(), FakeAnduin()
    store.rows[("u1", "plan_u1")] = {"updated_at": "2026-10-01T00:00:00", "planned": {"WCB_2": 4}}
    with pytest.raises(handoff.HandoffRefused, match="outside this handoff"):
        _apply(tmp_path, store, an)
    assert store.saves == []


def test_curve_edited_in_anduin_is_refused_unless_new_version(tmp_path):
    store, an = Store(), FakeAnduin()
    _apply(tmp_path, store, an)
    an.curves["tc-1"]["included_api10s"] = ["4200000001"]                 # reviewer culled a well
    with pytest.raises(handoff.HandoffRefused, match="edited in anduin"):
        _apply(tmp_path, store, an)
    assert an.curves["tc-1"]["included_api10s"] == ["4200000001"]          # edit kept
    out = _apply(tmp_path, store, an, new_version=True)
    assert out["curves"][0]["action"] == "new version" and "version" in an.calls
    assert an.config["zones"][0]["type_curve_id"] == out["curves"][0]["id"]


def test_narvi_mismatch_stops_before_anduin(tmp_path):
    store, an = Store(planned={"WCB_2": 1}), FakeAnduin()
    with pytest.raises(handoff.HandoffRefused, match="saved sticks"):
        _apply(tmp_path, store, an)
    assert "deals" not in an.calls


def test_blocked_plan_is_refused(tmp_path):
    P = {**_plan(), "status": "BLOCKED"}
    with pytest.raises(handoff.HandoffRefused, match="BLOCKED"):
        handoff.apply(P, tmp_path, Store(), FakeAnduin(), contextlib.nullcontext)


def test_evaluate_flags_are_remembered_and_merged_by_bench(tmp_path):
    from dealintake.cli import _remember_evaluate

    def ns(**kw: Any) -> argparse.Namespace:
        base = {"forget": False, "spacing": [], "cohort": [], "radius": [], "tc_groups": [], "tc_single": [],
                "benches": None, "short_history_transfer": None, "no_short_history_transfer": False}
        return argparse.Namespace(**{**base, **kw})

    _remember_evaluate(tmp_path, ns(tc_groups=["WCB_2=a;b", "WCB_1=c;d"], cohort=["WCB_2=12"]))
    a = ns(tc_groups=["WCB_1=c,d"])                    # today's flag replaces that bench only
    _remember_evaluate(tmp_path, a)
    assert sorted(a.tc_groups) == ["WCB_1=c,d", "WCB_2=a;b"] and a.cohort == ["WCB_2=12"]
    a = ns(forget=True)
    _remember_evaluate(tmp_path, a)
    assert a.tc_groups == [] and json.loads((tmp_path / "evaluate_args.json").read_text())["cohort"] == []


def test_run_name_resolves_to_the_newest_matching_folder(tmp_path, monkeypatch):
    from dealintake import cli
    for name in ("rallycaps-2026-09-29", "rallycaps-2026-09-30", "vault-2026-09-25"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "proposal.json").write_text("{}")
    old = time.time() - 3600
    os.utime(tmp_path / "rallycaps-2026-09-29" / "proposal.json", (old, old))
    monkeypatch.setattr(cli, "RUNS", tmp_path)
    got = cli._resolve_run(argparse.Namespace(run="rallycaps", run_dir=None))
    assert got.name == "rallycaps-2026-09-30"
    with pytest.raises(SystemExit):
        cli._resolve_run(argparse.Namespace(run="nosuchdeal", run_dir=None))
