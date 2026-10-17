"""DB-free tests for the pre-9b rehearsal (box/rehearse9b.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from box import rehearse9b as r


def _frame(n_pkg: int, err: float) -> pd.DataFrame:
    rows = []
    for i in range(n_pkg):
        rows.append({"api10": f"a{i}", "cutoff": "2022-12-01", "package": f"p{i}", "bx": i % 40, "by": i // 40,
                     **{f"actual_{s}{k}": 100.0 * (1 + err) for s in ("oil", "gas") for k in r.HORIZONS},
                     **{f"pred_box_v2_{s}{k}": 100.0 for s in ("oil", "gas") for k in r.HORIZONS},
                     **{f"bench_{s}{k}": 100.0 for s in ("oil", "gas") for k in r.HORIZONS}})
    v = pd.DataFrame(rows)
    v["pkg"] = v["cutoff"] + ":" + v["package"]
    return v


def test_judge_needs_30_packages_and_scale_shifts_bias() -> None:
    t = r.package_table(_frame(40, 0.0), "box_v2")
    allp = np.ones(40, dtype=bool)
    assert r.judge(allp, t, "oil", 12)[0] == "PASS"
    assert r.judge(allp & (np.arange(40) < 20), t, "oil", 12)[0] == "not judged"  # 20 < 30 packages
    v, n, b = r.judge(allp, t, "oil", 12, scale=1.25, bias_only=True)
    assert v == "FAIL" and n == 40 and abs(b - (1 / 1.25 - 1)) < 1e-12


def test_nothing_judged_is_fail_for_the_rule_as_written() -> None:
    t = r.package_table(_frame(20, 0.0), "box_v2")
    out = r.verdicts(np.ones(20, dtype=bool), t, ["2022-12-01"])
    assert out["per_cutoff"] == "FAIL" and out["per_cutoff_judged"] == 0
