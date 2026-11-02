"""BOX step 24 — continuous proximity factor: definition digest + goldens on a synthetic gunbarrel (DB-free)."""

from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from box import prox_cont as pc


def test_definition_matches_the_pinned_digest():
    assert pc.digest() == pc.DIGEST, "box/prox_cont.py DEFINITION changed after the pre-registration — that needs Michael and a dated revision row"


def test_definition_states_the_registered_defaults():
    d = pc.DEFINITION
    assert d["side_by_depth_ft"] == 150.0 and d["universe_ft"] == {"dv": 1000.0, "dh": 2640.0}
    assert d["gate_defaults"]["G2"] == "R3" and d["level"]["cap"] is None and d["bootstrap"] == {"blocks_ft": "3-mi (box.dev_factor.blocks)", "n": 1000, "seed": 20261102, "ci": (5.0, 95.0)}
    assert d["validation"]["test_cutoffs"]["oil24"] == ("2021-12-01", "2022-12-01", "2023-12-01")


# ---- geometry --------------------------------------------------------------------------------------------------------
def test_side_by_depth_and_axis_side():
    assert list(pc.side_of(np.array([0.0, 150.0, -150.0, 151.0, -151.0, 800.0]))) == ["same", "same", "same", "below", "above", "below"]
    s = pc.side_of(np.array([10.0, 400.0, -400.0, -5.0]))
    assert list(pc.axis_side(s, np.array([300.0, 300.0, -300.0, -700.0]))) == ["left", "below", "above", "right"]


def test_d_eff_is_the_registered_ellipse():
    side = np.array(["same", "below", "above"])
    d = pc.d_eff(np.array([600.0, 300.0, 0.0]), np.array([100.0, 400.0, -250.0]), side, a_below=1.5, a_above=2.0)
    assert d[0] == 600.0                                   # same side ignores depth
    assert d[1] == pytest.approx(np.hypot(300.0, 600.0))   # below: a_below * dz
    assert d[2] == pytest.approx(500.0)                    # above: a_above * |dz|


def test_curve_shape_is_monotone_with_floor_and_asymptote():
    c = pc.Curve(0.78, 1000.0, 3.0)
    assert c(np.array([0.0]))[0] == pytest.approx(0.78)
    assert c(np.array([1000.0]))[0] == pytest.approx(0.78 + 0.22 / 2)
    g = c(np.linspace(0, 5000, 200))
    assert np.all(np.diff(g) >= 0) and g[-1] > 0.998


# ---- the §3 rule table ------------------------------------------------------------------------------------------------
def test_rules_reproduce_the_prereg_table():
    f = np.array([0.8, 0.8])
    flanked = np.array(["left", "right"], dtype=object)
    same_side = np.array(["left", "left"], dtype=object)
    assert pc.combine(f, flanked, "R1") == pytest.approx(0.80)
    assert pc.combine(f, flanked, "R2") == pytest.approx(0.64)
    assert pc.combine(f, flanked, "R3") == pytest.approx(0.64)
    assert pc.combine(f, flanked, "R4") == pytest.approx(0.60)
    assert pc.combine(f, same_side, "R3") == pytest.approx(0.80)   # shielding native
    assert pc.combine(f, same_side, "R4") == pytest.approx(0.80)
    assert pc.combine(f, same_side, "R2") == pytest.approx(0.64)   # counts both
    # a single parent is F under every rule; no parent is 1
    for r in pc.RULES:
        assert pc.combine(np.array([0.7]), np.array(["below"], dtype=object), r) == pytest.approx(0.7)
        assert pc.combine(np.array([]), np.array([], dtype=object), r) == 1.0
    # stack pair: one above + one below at 0.8 -> vertical axis share 0.6 under R4, 0.64 under R3
    stack = np.array(["above", "below"], dtype=object)
    assert pc.combine(f, stack, "R4") == pytest.approx(0.60)
    assert pc.combine(f, stack, "R3") == pytest.approx(0.64)


# ---- fitting on a synthetic basin ------------------------------------------------------------------------------------
def _synthetic(n=1200, seed=3):
    """Single-parent children drawn from a known surface (F_min 0.78, d50 900, k 3, a_below 1.6, a_above 2.4) + noise."""
    rng = np.random.default_rng(seed)
    truth = pc.Model(pc.Curve(0.78, 900.0, 3.0), 1.6, 2.4)
    side = rng.choice(["same", "below", "above"], size=n, p=[0.5, 0.25, 0.25])
    dh = np.where(side == "same", rng.uniform(100, 2600, n), rng.uniform(0, 390, n))
    dz = np.where(side == "same", rng.uniform(-150, 150, n), rng.uniform(160, 900, n) * np.where(side == "below", 1, -1))
    lrel = np.log(truth.factor(dh, dz, side)) + rng.normal(0, 0.25, n)
    sp = pd.DataFrame({"api10": [f"c{i}" for i in range(n)], "bench_group": "G", "block": rng.integers(0, 40, n), "l_rel": lrel,
                       "dh_ft": dh, "dz_ft": dz, "dv_ft": np.abs(dz), "side": side,
                       "axis_side": pc.axis_side(side, np.where(rng.random(n) < 0.5, 1.0, -1.0)), "parent_bench": "X", "age_days": 800,
                       "parent_cum_bbl_per_kft": np.nan})
    return sp, truth


def test_stages_recover_a_known_surface():
    sp, truth = _synthetic()
    st = pc.fit_stages(sp)
    a = st["curve_same"]
    assert abs(a.f_min - 0.78) < 0.05 and abs(a.d50 - 900.0) < 150.0
    assert abs(st["surface"].a_below - 1.6) < 0.5 and abs(st["surface"].a_above - 2.4) < 0.7
    pred = st["surface"].factor(sp["dh_ft"].to_numpy(), sp["dz_ft"].to_numpy(), sp["side"].to_numpy())
    assert np.abs(np.log(pred) - np.log(truth.factor(sp["dh_ft"].to_numpy(), sp["dz_ft"].to_numpy(), sp["side"].to_numpy()))).mean() < 0.03


def test_c2_does_not_reject_a_true_surface_and_c1_bins_sit_in_the_band():
    sp, _ = _synthetic()
    c2 = pc.check_c2(sp, n_boot=40)
    assert not c2["surface_fails"]
    band = pc.curve_band(sp, "same", np.arange(100.0, 2700.0, 100.0), n_boot=40)
    same = sp[sp["side"] == "same"]
    edges = [0, 400, 800, 1400, 2000, 2640]
    rows = []
    for lo, hi in pairwise(edges):
        m = (same["dh_ft"] >= lo) & (same["dh_ft"] < hi)
        rows.append({"lo_ft": lo, "hi_ft": hi, "n": int(m.sum()), "effect": float(np.exp(same.loc[m, "l_rel"].mean()))})
    c1 = pc.check_c1(band, pd.DataFrame(rows))
    assert c1["n_bins"] >= 4 and c1["share_inside"] >= 0.6


def test_contest_prefers_the_generating_rule_and_defaults_on_a_tie():
    rng = np.random.default_rng(7)
    n = 800
    f1, f2 = rng.uniform(0.6, 0.95, n), rng.uniform(0.6, 0.95, n)
    flank = rng.random(n) < 0.7
    sides = [("left", "right") if fl else ("left", "left") for fl in flank]
    fr = {r: np.array([pc.combine(np.array([a, b]), np.array(s, dtype=object), r) for a, b, s in zip(f1, f2, sides, strict=True)]) for r in pc.RULES}
    two = pd.DataFrame({"child": range(n), "block": rng.integers(0, 30, n), "flanked": flank, "F_near": np.minimum(f1, f2), "F_far": np.maximum(f1, f2),
                        **{f"F_{r}": fr[r] for r in pc.RULES}})
    two["l_rel"] = np.log(fr["R2"]) + rng.normal(0, 0.05, n)   # generated multiplicatively
    res = pc.contest(two, n_boot=60)
    assert res["winner"] == "R2" and res["beta"]["all"]["b_near"] == pytest.approx(1.0, abs=0.15) and res["beta"]["all"]["b_far"] == pytest.approx(1.0, abs=0.15)
    two["l_rel"] = np.log(fr["R1"]) + rng.normal(0, 0.05, n)   # generated worst-only -> R1 wins (revision 2)
    res = pc.contest(two, n_boot=60)
    assert res["winner"] == "R1" and "entirely below zero" in res["reason"]
    two["l_rel"] = rng.normal(0, 0.5, n)                      # residuals centred at zero: the smallest correction (R1) wins, not a tie
    res = pc.contest(two, n_boot=60)
    assert res["winner"] == "R1"
    two["l_rel"] = 0.5 * (np.log(fr["R1"]) + np.log(fr["R2"])) + rng.normal(0, 0.5, n)   # halfway between R1 and R2, noisy -> unresolved -> R3 default
    res = pc.contest(two, n_boot=60)
    assert res["winner"] == "R3" and "default" in res["reason"], res["reason"]


def test_level_mapping_caps_at_one_and_f_mix_is_the_group_mean():
    mix = pc.f_mix(np.array(["A", "A", "A", "B"]), np.array([1.0, 0.8, 0.64, 0.9]))
    assert mix["A"] == pytest.approx(np.exp(np.mean(np.log([1.0, 0.8, 0.64])))) and mix["B"] == pytest.approx(0.9)
    out = pc.applied(np.array([1.0, 0.64, 0.9]), np.array(["A", "A", "B"]), mix, cap=1.0)
    assert out[0] == 1.0 and out[1] == pytest.approx(0.64 / mix["A"]) and out[2] == 1.0
    assert pc.applied(np.array([1.0]), np.array(["A"]), mix, cap=None)[0] > 1.0
    assert pc.CAP is None and pc.applied(np.array([1.0]), np.array(["A"]), mix)[0] == pytest.approx(1.0 / mix["A"])   # revision 4: the uplift is carried


def _links(rows):
    cols = ["child", "parent", "parent_bench", "rel", "age_days", "dz_ft", "dh_ft", "overlap", "permit", "shielded", "dxy_ft"]
    L = pd.DataFrame(rows, columns=cols)
    L["dv_ft"] = L["dz_ft"].abs()
    return L


def test_parents_filter_is_the_registered_one():
    L = _links([("c", "p1", "X", "parent", 800, 10.0, 500.0, 0.9, False, True, 500.0),    # shielded still counts
                ("c", "p2", "X", "parent", 800, 10.0, 600.0, 0.2, False, False, 600.0),   # under 30 % alongside: out
                ("c", "p3", "X", "parent", 200, 10.0, 700.0, 0.9, False, False, 700.0),   # 200 d: not depleting on the drilled side
                ("c", "p4", "X", "parent", 800, 10.0, 800.0, 0.9, True, False, 800.0),    # permit TVD: out on the drilled side, in on the stick side
                ("c", "p5", "X", "codev", -30, 10.0, 300.0, 0.9, False, False, 300.0),    # codev never a dose
                ("c", "p6", "X", "parent", 800, 1200.0, 300.0, 0.9, False, False, 300.0)])  # outside the universe
    assert sorted(pc.parents(L, drilled=True)["parent"]) == ["p1"]
    assert sorted(pc.parents(L, drilled=False)["parent"]) == ["p1", "p3", "p4"]


def test_child_factors_and_sticks_end_to_end():
    model = pc.Model(pc.Curve(0.78, 900.0, 3.0), 1.6, 2.4)
    L = _links([("s1", "a", "X", "parent", 800, 0.0, 600.0, 0.9, False, False, 600.0), ("s1", "b", "X", "parent", 800, 0.0, 600.0, 0.9, False, False, -600.0),
                ("s2", "a", "X", "parent", 800, 0.0, 600.0, 0.9, False, False, 600.0), ("s3", "a", "X", "parent", 800, 0.0, 2500.0, 0.9, True, False, 2500.0)])
    cf = pc.child_factors(pc.parents(L, drilled=False), model).set_index("child")
    f = float(model.curve(np.array([600.0]))[0])
    assert cf.at["s1", "pattern"] == "left+right" and bool(cf.at["s1", "flanked"]) and cf.at["s1", "F_R3"] == pytest.approx(f * f)
    assert cf.at["s2", "F_R1"] == cf.at["s2", "F_R4"] == pytest.approx(f)
    st = pc.sticks(L, model, "R3", {"G": 0.95}, {"s1": "G", "s2": "G", "s3": "G"})
    st = st.set_index("stick")
    assert st.at["s1", "factor_capped"] == pytest.approx(min(1.0, f * f / 0.95)) and st.at["s3", "permit_parents"] == 1 and st.at["s2", "factor_uncapped"] == pytest.approx(f / 0.95)
    assert st.at["s2", "factor"] == st.at["s2", "factor_uncapped"]   # revision 4: factor = the uncapped one
    sup = pc.g4_support(pd.DataFrame({"pattern": ["left+right"] * 40 + ["left"] * 5, "n_parents": 2, "nearest_d_eff": list(np.linspace(300, 1500, 40)) + [100.0] * 5}))
    assert sup.set_index("pattern").at["left+right", "precedent"] and not sup.set_index("pattern").at["left", "precedent"]
    out = pc.g4_outcome(st.reset_index(), sup)
    assert list(out) == ["forecast", "no_forecast_geometry", "no_forecast_geometry"]   # s1 flanked at 600 inside support; s2 / s3 'left' has 5 < 30 precedents
