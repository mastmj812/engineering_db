"""Step 21a: the Midland pre-registration is pinned, its groups are the harness's, its method is run 19's with the D129 band,
and the rules it names behave as written (DB-free)."""

import math
from pathlib import Path

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import basin as bsn
from box import holdout as ho
from box import production16 as p16prod
from box import prox_dose as pdz
from box import prox_pud as pp
from box import step16 as s16
from box import step21 as st
from box import step21_evidence as ev
from box import thin_bench as tb


def test_definition_matches_the_pinned_digest():
    assert st.digest() == st.DIGEST, "box/step21.py DEFINITION changed after the pre-registration — that needs Michael and a stated revision"


def test_groups_are_harness_specs_in_the_midland():
    assert set(st.GROUPS) == {f"MID_{b}" for b in ("WCA_1", "WCB_1", "WCB_2", "WCC", "WCD", "MS", "JM", "LSSH", "DEAN")}
    for g, (b, e, src) in st.GROUPS.items():
        spec = ac.BENCH_SPECS[g]
        assert spec["basin"] == bsn.MIDLAND and spec["wells"] == spec["extent"] == spec["label"] == b and spec["step21"]
        assert spec["pool_tags"] is None and spec["target_tags"] is None  # membership = box_bench (D136 / card reassignments)
        assert not spec.get("provisional")  # tiers come from 21c (D131)
        d = st.DEFINITION["groups"][g]
        assert d == {"bench": b, "extent_id": e, "pool_file": f"{st.POOL_DIR.as_posix()}/wells_final_{b}.csv", "pool_source": src}
    assert "US" not in {b for b, _, _ in st.GROUPS.values()}  # D127 emerging


def test_delaware_specs_untouched():
    assert all(s["basin"] == bsn.DELAWARE for g, s in ac.BENCH_SPECS.items() if not g.startswith("MID_"))
    assert not any(s.get("step21") for g, s in ac.BENCH_SPECS.items() if not g.startswith("MID_"))


def test_method_is_run_19s_r2_with_the_d129_band():
    assert st.SELECTION == p16prod.SELECTION
    assert st.RULES.translate_range == (5_000.0, math.inf)
    assert st.RULES == p16prod.RULES.__class__(**{**p16prod.RULES.__dict__, "translate_range": (5_000.0, math.inf)})
    assert repr(st.RULES) == st.DEFINITION["method"]["rules"]
    assert st.HARNESS_VARIANTS == {st.RAW: (s16.MEASURED, st.RULES)} and st.HARNESS_SCORED == (st.RAW, f"{st.RAW}_lin")
    assert bsn.df_terminal(bsn.MIDLAND) == st.DEFINITION["method"]["df_terminal"] == 0.06  # D132


def test_long_producer_is_an_analog_under_the_midland_band_only():
    """select_wells' lateral test is `lo <= completed lateral <= hi` on the band the rules pass (analog.select_cohort_v2)."""
    lo, hi = st.RULES.translate_range
    lo16, hi16 = s16.VARIANTS[st.SELECTION][1].translate_range
    assert lo <= 18_000.0 <= hi and not lo16 <= 18_000.0 <= hi16
    assert lo == lo16 == 5_000.0  # the floor is unchanged: < 5,000-ft producers stay out


def test_folds_holdout_grain_match_the_harness():
    f = st.DEFINITION["folds"]
    assert f["cutoffs"] == [str(c) for c in ac.CUTOFFS] and f["horizons"] == list(ac.HORIZONS)
    h = st.DEFINITION["holdout"]
    assert (h["salt"], h["block_ft"], h["share"]) == (ho.SALT, ho.BLOCK_FT, ho.SHARE)
    g = st.DEFINITION["grain"]
    assert (g["package_codev_days"], g["package_overlap"], g["min_packages"]) == (ac.PACKAGE_CODEV_DAYS, ac.PACKAGE_OVERLAP, ac.MIN_PACKAGES)
    assert st.MIN_PACKAGES == tb.MIN_PACKAGES and st.MIN_PRIOR == tb.MIN_PRIOR


def test_proximity_constants_are_the_delaware_ones():
    p = st.DEFINITION["proximity"]
    assert {k: tuple(v) for k, v in p["envelopes_ft"].items()} == pdz.ENVELOPE
    assert (p["precedent"]["multi_parent_floor"], p["precedent"]["severe_factor"]) == (pp.PRECEDENT_FLOOR, pp.SEVERE)


def test_record_treatment_rule():
    assert st.record_treatment({12: 30, 24: 30}) == st.PROX_WF
    assert st.record_treatment({12: 120, 24: 29}) == st.PROX
    assert st.record_treatment({}) == st.PROX


def test_d99_cells_and_tier_route():
    assert st.d99_horizons({12: 40, 24: 31, 36: 12, 48: 90}) == (12, 24)  # cum-48 never judged
    assert st.tier_route({12: 30}) == "holdout"
    assert st.tier_route({12: 29, 24: 29}) == "provisional"


def test_length_classes():
    assert st.mismatch_class(7_000, 10_000) == "shorter" and st.mismatch_class(8_000, 10_000) == "near"
    assert st.mismatch_class(12_500, 10_000) == "longer"
    assert st.lateral_class(4_000) == "<5000" and st.lateral_class(12_500) == "12500-15000" and st.lateral_class(21_000) == ">=20000"
    assert ev.length_class(16_000) == "15-17.5k" and ev.length_class(25_000) == ">=20k" and ev.length_class(4_000) is None


def test_pool_manifest_matches_files():
    import json

    man = json.loads((st.POOL_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    assert {e["group"] for e in man["files"]} == set(st.GROUPS)
    for e in man["files"]:
        assert st.sha256_file(Path(e["file"])) == e["sha256_lf"], e["file"]
        assert st.sha256_file(Path(e["source"])) == e["sha256_lf"], f"{e['source']} moved after the pool was frozen"


def test_reach_and_water_class():
    pool = np.array([[i * 5280.0, 0.0] for i in range(1, 13)])
    r = ev.reach(np.array([[0.0, 0.0]]), pool, ev.OIL_RINGS_MI)
    assert r.at[0, "d10_mi"] == 10.0 and r.at[0, "ring"] == "<=10" and r.at[0, "d3_mi"] == 3.0
    assert ev.water_class(3.0, 45.0) == "ring" and ev.water_class(20.0, 60.0) == "thin" and ev.water_class(55.0, np.inf) == "fallback"
    short = ev.reach(np.array([[0.0, 0.0]]), pool[:4], ev.OIL_RINGS_MI)
    assert not np.isfinite(short.at[0, "d10_mi"]) and short.at[0, "ring"] == "none"


def test_top_operator_share():
    pool = np.array([[i * 100.0, 0.0] for i in range(10)])
    ops = ["A"] * 7 + ["B"] * 3
    assert ev.top_operator_share(np.array([[0.0, 0.0]]), pool, ops)[0] == 0.7
    assert np.isnan(ev.top_operator_share(np.array([[0.0, 0.0]]), pool[:5], ops[:5])[0])


def test_per_ft_by_length_recovers_a_planted_ratio():
    rng = np.random.default_rng(0)
    rows = []
    for b in range(60):
        lvl = rng.normal(0, 0.3)
        for lat_ft, f in ((8_750, 1.0), (13_750, 0.90), (16_250, 0.85)):
            for _ in range(3):
                rows.append({"block": b, "fp_year": 2022, "lateral_ft": lat_ft, "oil12_kft": 15_000 * f * np.exp(lvl + rng.normal(0, 0.02))})
    t = ev.per_ft_by_length(pd.DataFrame(rows), n_boot=50).set_index("class")
    assert abs(t.at["7.5-10k", "observed"] - 1.0) < 1e-9
    assert abs(t.at["12.5-15k", "observed"] - 0.90) < 0.01 and abs(t.at["15-17.5k", "observed"] - 0.85) < 0.01
    assert t.at["15-17.5k", "extrapolated"] and not t.at["7.5-10k", "extrapolated"]
    assert t.at["15-17.5k", "cui"] < t.at["12.5-15k", "cui"] < 1.0


def test_dean_body_or_addition():
    assert ev.body_or_addition(0.5) == "body" and ev.body_or_addition(0.49) == "addition" and ev.body_or_addition(float("nan")) == "addition"


def test_ladder_fill():
    k = pd.DataFrame({"k1": ["a"] * 31 + ["b"] * 5, "k2": ["x"] * 36, "k3": [None] * 36, "k4": ["same"] * 36})
    f = ev.ladder_fill(k).set_index(["rung", "key"])
    assert f.at[("k1", "a"), "fills"] and not f.at[("k1", "b"), "fills"] and f.at[("k2", "x"), "n_children"] == 36
