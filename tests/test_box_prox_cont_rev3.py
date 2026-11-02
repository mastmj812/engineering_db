"""BOX step 24 revision 3 — the joint fit on every exposed child and the per-rule contest (DB-free goldens)."""

import numpy as np
import pandas as pd
import pytest

from box import prox_cont as pc

TRUTH = pc.Model(pc.Curve(0.78, 900.0, 3.0), 1.6, 2.4)


def _basin(n=2500, seed=5, rule="R3", noise=0.20, p_zero=0.0):
    """Children with 1-4 parents (a share `p_zero` with none) from a known surface, combined by `rule`; returns the links
    frame, the child ids, l_rel and the block ids."""
    rng = np.random.default_rng(seed)
    rows, lrel, ids, blocks = [], [], [], []
    for i in range(n):
        k = 0 if rng.random() < p_zero else int(rng.choice([1, 2, 3, 4], p=[0.35, 0.3, 0.2, 0.15]))
        fs, sides = [], []
        for j in range(k):
            side = rng.choice(["same", "below", "above"], p=[0.6, 0.2, 0.2])
            dh = rng.uniform(100, 2600) if side == "same" else rng.uniform(0, 1200)
            dz = rng.uniform(-150, 150) if side == "same" else rng.uniform(160, 950) * (1 if side == "below" else -1)
            dxy = dh * rng.choice([-1.0, 1.0])
            rows.append({"child": f"c{i}", "parent": f"p{i}_{j}", "parent_bench": "X", "rel": "parent", "age_days": 900, "dz_ft": dz, "dv_ft": abs(dz),
                         "dh_ft": dh, "overlap": 0.9, "permit": False, "shielded": False, "dxy_ft": dxy, "parent_cum_bbl_per_kft": 30.0})
            fs.append(float(TRUTH.factor(np.array([dh]), np.array([dz]), np.array([side]))[0]))
            sides.append(pc.axis_side(np.array([side]), np.array([dxy]))[0])
        lrel.append((np.log(pc.combine(np.array(fs), np.array(sides, dtype=object), rule)) if fs else 0.0) + rng.normal(0, noise))
        ids.append(f"c{i}")
        blocks.append(int(rng.integers(0, 60)))
    return pd.DataFrame(rows), np.array(ids, dtype=object), np.array(lrel), np.array(blocks)


def _mix_calibrated(lrel):
    """What a BOX log-ratio looks like: level calibrated on the MIX of scored children (D58), so the mean over all is zero."""
    return lrel - lrel.mean()


def test_rule_vector_matches_combine_row_by_row():
    links, ids, _, _ = _basin(n=300, seed=2)
    par = pc.parents(links, drilled=True)
    P = pc.pad(par, ids)
    Fm = pc.f_matrix(P, TRUTH)
    for r in pc.RULES:
        v = pc.rule_vector(Fm, P, r)
        for i in range(0, 300, 37):
            g = par[par["child"] == ids[i]]
            f = TRUTH.factor(g["dh_ft"].to_numpy(), g["dz_ft"].to_numpy(), g["side"].to_numpy())
            assert v[i] == pytest.approx(pc.combine(f, g["axis_side"].to_numpy(), r), rel=1e-9)


def test_pad_keeps_every_parent_and_masks_the_rest():
    links, ids, _, _ = _basin(n=200, seed=9)
    par = pc.parents(links, drilled=True)
    P = pc.pad(par, ids)
    assert P.mask.shape[0] == 200 and (P.n_parents == par.groupby("child").size().reindex(ids).to_numpy()).all()
    assert np.all(P.side[~P.mask] == -1) and np.all(P.axis[~P.mask] == -1)


def test_joint_fit_recovers_the_surface_from_multi_parent_children():
    links, ids, lrel, _ = _basin()
    P = pc.pad(pc.parents(links, drilled=True), ids)
    m = pc.fit_joint(P, lrel, "R3")
    assert m.surface and abs(m.curve.f_min - 0.78) < 0.04 and abs(m.curve.d50 - 900.0) < 120.0
    assert abs(m.a_below - 1.6) < 0.4 and abs(m.a_above - 2.4) < 0.6
    pred = np.log(pc.rule_vector(pc.f_matrix(P, m), P, "R3"))
    truth = np.log(pc.rule_vector(pc.f_matrix(P, TRUTH), P, "R3"))
    assert np.abs(pred - truth).mean() < 0.02


def test_contest_joint_prefers_the_generating_rule_and_c2_keeps_a_true_surface():
    for gen in ("R2", "R3"):
        links, ids, lrel, blocks = _basin(seed=11, rule=gen, noise=0.08)
        P = pc.pad(pc.parents(links, drilled=True), ids)
        res = pc.contest_joint(P, lrel, blocks, n_boot=60)
        assert res["winner"] == gen, (gen, res["reason"], res["table"][["rule", "rms", "gain_lo", "gain_hi"]])
        assert set(res["models"]) == set(pc.RULES) and res["n_two"] >= pc.MIN_FIT and "b_near" in res["beta"]["all"]
    c2 = pc.check_c2_joint(P, lrel, blocks, n_boot=40)
    assert not c2["surface_fails"] and c2["n_cv"] == len(lrel)


def test_walk_forward_rows_carry_the_c3_c5_fields_and_score_runs():
    links, ids, lrel, blocks = _basin(n=2000, seed=3, p_zero=0.4)   # unexposed children too, so F_mix does not cancel the factor
    rng = np.random.default_rng(1)
    cut = rng.choice(["2019-12-01", "2020-12-01", "2021-12-01", "2022-12-01"], len(ids))
    d = pd.DataFrame({"api10": ids, "bench": "WCA", "bench_group": "WCA", "cutoff": cut, "block": blocks, "l_oil24": _mix_calibrated(lrel)})
    p, fits = pc.walk_forward(d, links, "oil24", ("2021-12-01", "2022-12-01"), n_boot=50)
    assert len(fits) == 2 and {"nearest_parent_bench", "nearest_age_days", "nearest_cum_kft", "cell", "f", "l_mix"} <= set(p.columns)
    assert all(f["rule"] in pc.RULES and "n_multi" in f for f in fits)
    s = pc.score(p, n_boot=50)
    assert s["verdict"] in ("PASS", "FAIL") and s["n_cells"] >= 1
    assert s["P1"], (s["P1_resid"], s["P1_lo"], s["P1_hi"])          # a mix-calibrated truth scores calibrated where material
    cells = s["cells"][s["cells"]["n"] >= 10]
    assert cells["mean_r"].abs().mean() < cells["mean_r0"].abs().mean()   # the factor removes most of the exposed miss
    assert s["C8"]["resid"] > 1.0                                        # unexposed children carry the 'none' uplift
