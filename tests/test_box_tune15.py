import numpy as np
import pandas as pd
import shapely

from box import acceptance as ac
from box import tune15_report as t15


def test_preregistered_record_variants_and_cells():
    assert [t15.record_variant(b) for b in t15.ORDER] == ["box_v2_wf"] + ["box_v2"] * 6
    assert t15.d99_cells("WCB_2") == [("oil", 12), ("oil", 24), ("oil", 36), ("gas", 12), ("gas", 24), ("gas", 36)]
    assert set(t15.D99_CELLS) == set(t15.ORDER)
    for b in t15.ORDER:
        assert ac.BENCH_SPECS[b]["extent"] == b and ac.BENCH_SPECS[b]["wells"] == b


def test_side_classes_compass_sides():
    sq = shapely.box(0, 0, 100 * 5280, 100 * 5280)  # 100-mi square
    x = np.array([50, 50, 99, 50, 1]) * 5280.0
    y = np.array([50, 99, 50, 1, 50]) * 5280.0
    e = t15.side_classes(x, y, sq)
    assert list(e["region"]) == ["interior", "N edge", "E edge", "S edge", "W edge"]


def _t(a_box, p_box, a_ben, p_ben):
    n = len(a_box)
    sums = {(s, k): {"box_a": np.array(a_box, float), "box_p": np.array(p_box, float), "bench_a": np.array(a_ben, float),
                     "bench_p": np.array(p_ben, float)} for s in ac.STREAMS for k in (12,)}
    return {"pkg": pd.DataFrame({"pkg": [f"p{i}" for i in range(n)]}), "member": np.ones((n, 1), bool), "n_blocks": 1, "sums": sums}


def test_pooled_bias_and_judging_floor():
    t = _t([90.0] * 40, [100.0] * 40, [100.0] * 40, [100.0] * 40)
    p = t15.pooled(t, (12,))
    assert len(p) == 2 and np.allclose(p["pkg_bias"], -0.10) and (p["n_packages"] == 40).all()
    t = _t([90.0] * 10, [100.0] * 10, [100.0] * 10, [100.0] * 10)
    assert (t15.pooled(t, (12,))["verdict"] == "not judged").all()


def test_per_cutoff_drops_empty_cells():
    cells = pd.DataFrame({"cutoff": ["2021-12-01", "2022-12-01"], "stream": "oil", "horizon": 12, "variant": "box_v2", "n_packages": [35, 0],
                          "pkg_bias": [0.05, np.nan], "pkg_band": [0.8, np.nan], "bench_bias": [0.0, np.nan], "bench_band": [0.9, np.nan],
                          "verdict": ["PASS", "not judged"]})
    p = t15.per_cutoff(cells, "box_v2")
    assert len(p) == 1 and np.isclose(p["sf band"].iloc[0], 0.8 / 1.05)


def test_frozen_choices_match_specs_and_manifest():
    from pathlib import Path

    m = pd.read_csv(Path(__file__).resolve().parents[1] / "docs" / "box" / "step15-tuning-2026-10-17" / "frozen_d99.csv")
    for b, f in t15.FROZEN.items():
        assert t15.record_variant(b) == f["variant"]
        g = m[m.bench == b]
        assert set(g["horizon"]) == set(f["horizons"]) and set(g["record_variant"]) == {f["variant"]}
        assert len(g) == 2 * len(f["horizons"])
    assert ac.BENCH_SPECS["BS2_C"].get("provisional") and "BS2_C" not in t15.FROZEN
