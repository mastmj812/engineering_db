"""DB-free tests for the PDP-proximity dose-response (box/prox_dose.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from box import prox_dose as pd_

COLS = ["child", "parent", "child_bench", "parent_bench", "cls", "rel", "age_days", "dz_ft", "dv_ft", "dh_ft", "overlap", "permit", "shielded",
        "parent_cum_bbl_per_kft"]


def _links(rows):
    return pd.DataFrame([dict(zip(COLS, r, strict=True)) for r in rows])


def test_exposure_groups_and_worst_parent() -> None:
    L = _links([
        ("a", "p1", "BS3_S", "WCA_1", "topfill", "parent", 900, 250, 250, 700, 0.9, False, False, 40e3),
        ("a", "p2", "BS3_S", "BS3_S", "same", "parent", 900, 0, 0, 1300, 0.9, False, False, 35e3),     # 1,300 hz < hypot(700, 667)? no: 1,300 > 967
        ("b", "p3", "BS3_S", "WCA_1", "topfill", "young", 250, 250, 250, 300, 0.9, False, False, 5e3),
        ("c", "p4", "BS3_S", "WCA_1", "topfill", "parent", 900, 250, 250, 300, 0.9, True, False, 30e3),  # permit only
        ("d", "p5", "BS3_S", "WCA_1", "topfill", "codev", 20, 250, 250, 300, 0.9, False, False, np.nan),
        ("e", "p6", "BS3_S", "WCA_1", "topfill", "parent", 900, 1200, 1200, 300, 0.9, False, False, 30e3),  # outside 1,000 vt
    ])
    e = pd_.exposure(["a", "b", "c", "d", "e", "f"], L).set_index("api10")
    assert e["group"].to_dict() == {"a": "exposed", "b": "young", "c": "ambiguous", "d": "control", "e": "control", "f": "control"}
    assert (e.at["a", "parent"], e.at["a", "dv_bin"], e.at["a", "dh_bin"], bool(e.at["a", "v14"])) == ("p1", "200-300", "400-800", True)


def _frame(n_ctrl=400, n_exp=120, haircut=0.8, seed=1):
    rng = np.random.default_rng(seed)
    n = n_ctrl + n_exp
    d = pd.DataFrame({"api10": [f"w{i}" for i in range(n)], "bench_group": rng.choice(["WCA", "BS3_S"], n), "cutoff": rng.choice(["2021", "2022"], n)})
    d["group"] = ["control"] * n_ctrl + ["exposed"] * n_exp
    bias = np.where(d["bench_group"] == "WCA", 0.9, 1.1)          # BOX bias differs by bench: must cancel
    noise = rng.normal(0, 0.15, n)
    d["l_oil12"] = np.log(bias) + noise + np.where(d["group"] == "exposed", np.log(haircut), 0.0)
    for m in pd_.METRICS:
        if m != "oil12":
            d[f"l_{m}"] = d["l_oil12"]
    d["block"] = np.arange(n) % 60
    return d


def test_effect_recovers_haircut_and_control_is_one() -> None:
    d = _frame()
    W = pd_.boot_weights(d["block"].to_numpy(), n_boot=200)
    eff = pd_.Effects(d, "oil12", W)
    ex = eff.cell((d["group"] == "exposed").to_numpy())
    ct = eff.cell((d["group"] == "control").to_numpy())
    assert ex["effect"] == pytest.approx(0.8, abs=0.03) and ex["lo"] < 0.8 < ex["hi"]
    assert ct["effect"] == pytest.approx(1.0, abs=1e-12)
    t = pd_.table(d, {m: pd_.Effects(d, m, W) for m in pd_.METRICS}, {"exp": (d["group"] == "exposed").to_numpy(), "tiny": np.arange(len(d)) < 5})
    assert t.loc[0, "oil12"] == pytest.approx(ex["effect"]) and not t.loc[0, "below_floor"] and t.loc[1, "below_floor"]


def test_thin_groups_fall_back_to_wider_baselines() -> None:
    d = _frame(n_ctrl=30)
    d.loc[(d["group"] == "control") & (d["bench_group"] == "BS3_S"), "cutoff"] = "2021"  # BS3_S|2022 has no controls
    keys = pd_.baseline_keys(d, "oil12")
    assert set(keys[(d["bench_group"] == "BS3_S").to_numpy() & (d["cutoff"] == "2022").to_numpy()]) <= {"BS3_S|*", "ALL"}


def test_log_ratios_clip_and_missing() -> None:
    v = pd.DataFrame({f"{p}{s}{k}": [100.0, 0.0, 5000.0] for p in ("actual_", "pred_box_v2_") for s in ("oil", "gas") for k in (12, 24, 36)})
    v.loc[2, "pred_box_v2_oil12"] = 1.0                                       # 5,000x -> clipped to ln 10
    lr = pd_.log_ratios(v)
    assert lr.at[0, "l_oil12"] == 0.0 and np.isnan(lr.at[1, "l_oil12"]) and lr.at[2, "l_oil12"] == pytest.approx(np.log(10))
