"""DB-free tests for the D52 holdout and the D53 acceptance pieces (box/holdout.py, box/acceptance.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import holdout as ho
from box import spacing3d as s3


def test_holdout_is_deterministic_and_about_a_fifth() -> None:
    rng = np.random.default_rng(3)
    x, y = rng.uniform(0, 4e6, 30000), rng.uniform(0, 4e6, 30000)
    h = ho.is_holdout(x, y)
    assert abs(h.mean() - ho.SHARE) < 0.02
    assert (ho.is_holdout(x, y) == h).all()
    # every point of a block shares the block's fate
    bx, by = ho.blocks(x, y)
    df = pd.DataFrame({"b": list(zip(bx, by, strict=True)), "h": h})
    assert (df.groupby("b")["h"].nunique() == 1).all()


def test_packages_codev_overlap_components() -> None:
    P = {
        "a": [s3.Pair("b", 0.8, 800, 0, 30), s3.Pair("x", 0.9, 700, 0, 10)],  # x is not a scored well
        "b": [s3.Pair("c", 0.2, 600, 0, 20)],  # overlap 0.2 from b's side ...
        "c": [s3.Pair("b", 0.35, -600, 0, -20), s3.Pair("d", 0.9, 700, 0, 400)],  # ... 0.35 from c's: linked; d is a parent, not codev
        "d": [],
    }
    m = ac.packages(["a", "b", "c", "d"], P)
    assert m["a"] == m["b"] == m["c"] == "a" and m["d"] == "d"


def test_package_errors_and_judge() -> None:
    df = pd.DataFrame({"package": ["p", "p", "q"], "a": [90.0, 110.0, np.nan], "f": [100.0, 100.0, 50.0]})
    e = ac.package_errors(df, "package", "a", "f")
    assert list(e["package"]) == ["p"] and e["err"].iloc[0] == 0.0
    assert ac.judge_cell({"bias": -0.05, "band": 0.5}, {"band": 0.6, "bias": 0.0}, 40, scale_free_band=False) == "PASS"
    assert ac.judge_cell({"bias": -0.12, "band": 0.5}, {"band": 0.6, "bias": 0.0}, 40, scale_free_band=False) == "FAIL"
    assert ac.judge_cell({"bias": -0.05, "band": 0.7}, {"band": 0.6, "bias": 0.0}, 40, scale_free_band=False) == "FAIL"  # 0.10 wider: over the 0.05 tolerance
    assert ac.judge_cell({"bias": -0.05, "band": 0.64}, {"band": 0.6, "bias": 0.0}, 40, scale_free_band=False) == "PASS"  # within tolerance
    assert ac.judge_cell({"bias": -0.05, "band": 0.64}, {"band": 0.6, "bias": 0.0}, 40, band_tol=0.0, scale_free_band=False) == "FAIL"  # strict
    assert ac.judge_cell({"bias": -0.05, "band": 0.5}, {"band": 0.6, "bias": 0.0}, 10) == "not judged"


def test_verdict_needs_oil_and_gas() -> None:
    cells = pd.DataFrame({"variant": ["lat"] * 4, "stream": ["oil", "oil", "gas", "gas"], "verdict": ["PASS", "not judged", "PASS", "FAIL"]})
    v = ac.verdict(cells)
    assert v["by_stream"] == {"oil": "PASS", "gas": "FAIL"} and v["overall"] == "FAIL" and v["n_judged"] == 3


def test_scale_free_band_does_not_penalise_a_corrected_forecast() -> None:
    # same wells: a forecast 15 % high has errors (1+e)/1.15 - 1; correcting it (x 0.85) widens the raw a/f-1 spread by 1/0.85
    raw_box = {"bias": 0.0, "band": 0.70}       # corrected forecast
    bench = {"bias": -0.15, "band": 0.70 * 0.85}  # the same spread, compressed by being 15 % high
    assert ac.judge_cell(raw_box, bench, 40, scale_free_band=False) == "FAIL"  # 0.70 > 0.595 + 0.05
    assert ac.judge_cell(raw_box, bench, 40, scale_free_band=True) == "PASS"   # 0.70 vs 0.70: equal once scale-free
