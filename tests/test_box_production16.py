"""Step 16d wiring — r2 in production (box/production16, box/production.fit_location, scripts/box_pud_run resume + evidence), DB-free."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from box import analog as an
from box import production as pr
from box import production16 as p16
from box import production_run9 as p9r
from box import step16 as s16
from dealintake import config as di_config
from scripts import box_pud_run as bpr

MI = an.MI
P = {"Di": 2.0, "b": 1.0, "qi": 50.0, "qo": 0.0, "peak_index_months": 1, "onset_index_months": 0, "Df": 0.08}


def _pool() -> dict:
    # Pad 1925 in miniature: five 10,000-ft wells at 1.7-2.5 mi (outside the 7,720-ft +/-25 % band) + ten in-band wells at 18 mi
    rows = [(1.7 + 0.2 * i, 10_000.0) for i in range(5)] + [(18.0 + 0.1 * i, 7_800.0) for i in range(10)]
    a = np.array(rows)
    n = len(rows)
    ids = np.array([f"w{i}" for i in range(n)])
    return {"api10": ids, "x": a[:, 0] * MI, "y": np.zeros(n), "fp": [dt.date(2020, 1, 1)] * n, "lateral": a[:, 1],
            "months": np.full(n, 30.0), "spacing": np.full(n, 1_100.0), "tvd": np.full(n, 10_000.0), "oil12_kft": np.full(n, 20_000.0),
            "f_oil": np.ones(n), "params": {w: {"oil": dict(P), "gas": dict(P), "water": None} for w in ids}}


LOC = {"api10": "pud1", "stick_id": 1, "x": 0.0, "y": 0.0, "lateral_ft": 7_720.0, "lateral_eff": 7_720.0, "spacing_ft": 1_000.0}


def _fit(rules: an.Rules | None) -> dict:
    pool = _pool()
    pr.init_state({"pool": pool, "pool2": pool, "cfg": di_config.load(), "k": pr.N_MONTHS, "cutoff": None, "bench": "BS1_S", "rules": rules})
    return pr.fit_location(dict(LOC))


def test_fit_location_record_rules_unchanged_and_r2_goes_local():
    rec = _fit(None)
    assert rec["radius_mi"] == 20.0 and {x["api10"] for x in rec["analogs"]} == {f"w{i}" for i in range(5, 15)}
    assert rec["lateral_mult"] == pytest.approx(7.72)  # record: linear per ft at >= 7,500 ft
    r2 = _fit(p16.RULES)
    assert r2["radius_mi"] == 5.0 and {x["api10"] for x in r2["analogs"]} == {f"w{i}" for i in range(5)}
    assert an.LATERAL_TRANSLATED in r2["flags"] and "relaxed: count (5 < 10)" in r2["flags"]
    assert r2["lateral_mult"] == pytest.approx(an.lateral_multiplier(7_720.0, [10_000.0] * 5, [an.LATERAL_TRANSLATED]))
    assert r2["lateral_mult"] > 7.72  # Cui: the shorter stick earns more per ft than its 10,000-ft analogs


def test_production_r2_equals_the_harness_r2_exactly():
    r2 = _fit(p16.RULES)
    pool = _pool()
    an._init({"pool": pool, "pool2": pool, "cfg": di_config.load(), "k": pr.N_MONTHS, "cutoff": None, "bench": "BS1_S",
              s16.MEASURED: pool, "variants16": {p16.SELECTION: (s16.MEASURED, p16.RULES)}})
    h = an.predict_location_v2(dict(LOC))
    for s in pr.STREAMS:
        assert np.array_equal(np.asarray(r2["streams"][s]["months_raw"]), np.asarray(h[p16.SELECTION][s]))


def test_haircut_from_pack_and_method_none():
    ev = {"haircut": {"oil": {"12": {"factor": 0.95}, "24": {"factor": 0.93}}, "gas": {"12": {"factor": 0.97}, "24": {"factor": 0.96}}}}
    h = p16.haircut_from_pack(ev)
    assert h["oil"][12]["factor"] == 0.95 and set(h["gas"]) == {12, 24}
    assert p16.haircut_from_pack({"haircut": None}) is None
    assert p16.haircut_method_none("BS1_S").startswith("none (D121")  # erebor reads the 'none' prefix
    assert p16.spec_label("WCA") == "box_v2s_r2_wf" and p16.spec_label("BS1_S") == "box_v2s_r2"


def test_committed_evidence_pack_matches_its_digest_and_passes_the_guard():
    pack, sha = bpr.load_evidence(p16.EVIDENCE)
    assert sha == hashlib.sha256(p16.EVIDENCE.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert set(pack["groups"]) == set(p9r.GROUPS) and pack["decision"] == "D121"
    for g, ev in pack["groups"].items():
        h = p16.haircut_from_pack(ev)
        assert (h is not None) == (g in p16.HAIRCUT_GROUPS)
        if h:  # the 9c table guard the build applies before any fit, on the streams that carry a haircut (D122: WCA gas none)
            assert p9r.guard_table({s: t for s, t in h.items() if t is not None}) == []
        d = ev["disclosure"]
        assert set(d["hindcast_bias"]) == {"oil", "gas"} and {"12", "24", "36", "48"} <= set(d["hindcast_bias"]["oil"])
        assert d["radius_ranges"] and d["tier"] == p16.tier(g) and "thin_control" in d
        fl = p16.flags(g, d)
        assert fl[0].startswith(f"D121 r2 selection ({p16.tier(g)}) {g}") and fl[1].startswith("thin-control caveat")


def test_evidence_digest_mismatch_is_refused(tmp_path):
    f = tmp_path / "r2_evidence.json"
    f.write_text(json.dumps({"groups": {}}), encoding="utf-8")
    (tmp_path / "r2_evidence.sha256").write_text("0" * 64 + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        bpr.load_evidence(f)


def test_bench_cache_resumes_only_on_identical_inputs(tmp_path):
    u = pd.DataFrame({"stick_id": [2, 1], "coverage": ["covered", "covered_provisional"], "prod_bench": ["WCA", "BS1_S"]})
    a = argparse.Namespace(selection="r2", pack_sha256="abc", wells="docs/box/pool-2026-10-15", limit=0)
    meta = bpr.resume_meta("sha1", a, u)
    assert bpr.load_bench_cache(tmp_path, "WCA", meta) is None  # nothing cached: build it
    bpr.save_bench_cache(tmp_path, "WCA", meta, {"record": {"n_forecast": 7}})
    assert bpr.load_bench_cache(tmp_path, "WCA", meta) == {"record": {"n_forecast": 7}}
    assert not list(tmp_path.glob("*.tmp"))
    assert bpr.resume_meta("sha1", a, u.iloc[::-1]) == meta  # row order does not matter
    for changed in (bpr.resume_meta("sha2", a, u),
                    bpr.resume_meta("sha1", a, u.assign(coverage=["covered", "covered"])),
                    bpr.resume_meta("sha1", argparse.Namespace(**{**vars(a), "pack_sha256": "xyz"}), u)):
        with pytest.raises(SystemExit):
            bpr.load_bench_cache(tmp_path, "WCA", changed)


def test_d122_wca_gas_carries_no_haircut():
    pack, _ = bpr.load_evidence(p16.EVIDENCE)
    wca = pack["groups"]["WCA"]
    h = p16.haircut_from_pack(wca)
    assert h["gas"] is None and h["oil"] is not None and wca["haircut_dropped"]["gas"]["decision"] == "D122"
    assert p16.haircut_from_pack(pack["groups"]["BS2_S"])["gas"] is not None
    hb = wca["disclosure"]["hindcast_bias"]["gas"]["12"]
    assert hb["haircut_factor"] == 1.0 and "D122" in hb["disclosed_basis"]
    raw = np.linspace(100.0, 1.0, pr.N_MONTHS)
    res = [{"streams": {"oil": {"months_raw": raw.copy(), "params": {}}, "gas": {"months_raw": raw.copy(), "params": {}}}}]
    bpr.apply_haircut_all(res, h)
    assert np.array_equal(res[0]["streams"]["gas"]["months"], raw)  # exactly raw, not a C1 fit to 1.0
    assert res[0]["streams"]["oil"]["eur"] < res[0]["streams"]["oil"]["eur_raw"]  # oil keeps its haircut
    rec = bpr.haircut_record(h, res)
    assert all(rec["gas"][k]["factor"] == 1.0 for k in pr.HORIZONS) and rec["gas"]["method"] == p16.STREAM_NONE
    assert rec["oil"][12]["factor"] == h["oil"][12]["factor"]


def test_code_key_tracks_build_code_only():
    k = bpr.code_key()
    assert len(k.split("-")[0]) == 16 and "scripts/box_pud_run.py" in bpr.BUILD_CODE and "docs" not in bpr.BUILD_CODE
