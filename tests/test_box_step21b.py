"""Step 21b scorer (box/step21b.py): DB-free checks of the pieces that touch the frozen pre-registration."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from box import prox_pud as pp
from box import step21 as st
from box import step21b as sb
from scripts import box_step21b as drv


def test_frozen_sha_is_the_registered_one() -> None:
    assert len(drv.FROZEN_SHA) == 40 and int(drv.FROZEN_SHA, 16) >= 0
    assert drv.FROZEN_SHA in (st.DOCS / "PREREGISTRATION.md").read_text(encoding="utf-8")  # the SHA stamped in §11
    assert st.digest() == st.DIGEST  # the definition the scorer reads is the frozen one


def test_f_from_view_recovers_a_common_factor_and_refuses_a_mismatch() -> None:
    m = np.ones((3, 48))
    v = pd.DataFrame({"pred_mid_r2_oil12": [12 * 0.9, 12 * 0.9, np.nan]})
    f, spread = sb.f_from_view(v, m, "oil", 12)
    assert f == pytest.approx(0.9) and spread == pytest.approx(0.0)
    v.loc[1, "pred_mid_r2_oil12"] = 12 * 0.95
    with pytest.raises(ValueError):
        sb.f_from_view(v, m, "oil", 12)


def _children(n: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        multi = i % 2 == 0
        rows.append({"api10": f"{i:010d}", "cutoff": "2020-12-01" if i % 4 < 2 else "2021-12-01", "bench_group": "MID_WCA_1", "bench": "WCA_1",
                     "config_class": "same" if multi else None, "n_parents_total": 2 if multi else 0, "n_same": 2 if multi else 0,
                     "flanked_same": multi, "pb_same": "WCA_1" if multi else None, "n_topfill": 0, "n_underfill": 0,
                     "flanked_topfill": False, "flanked_underfill": False, "pb_topfill": None, "pb_underfill": None,
                     "config": "same|2|dh400-800" if multi else None,
                     "l_oil24": (np.log(0.8) if multi else 0.0) + rng.normal(0, 0.01)})
    return pd.DataFrame(rows)


def test_fit_table_reads_like_the_d113_table_and_applies_as_production_does() -> None:
    d = _children()
    tab = sb.fit_table(d)
    assert list(tab.columns) == ["rung", "key", "n_train", "factor", "usable"]
    k2 = tab[(tab.rung == "k2") & (tab.key == "same|2|F")].iloc[0]
    # l_rel = l minus the (group, cutoff) mean: multi children sit ln(0.8)/2 below the mean -> factor ~ sqrt(0.8)
    assert k2.n_train == 40 and k2.usable and k2.factor == pytest.approx(np.sqrt(0.8), rel=0.02)
    assert pp.haircut_lookup(tab)["k2:same|2|F"] == pytest.approx(k2.factor)
    f = sb.record_factor(d, tab)
    assert f[d.loc[0, "api10"]] == pytest.approx(k2.factor)  # multi-parent -> the k2 factor (production's ladder)
    assert f[d.loc[1, "api10"]] == 1.0  # unexposed -> 1.0 (D113 option (a))


def test_gap_rung_is_tried_first_only_in_the_sensitivity() -> None:
    d = _children()
    tab = sb.fit_table(d, gap_rung=True)
    assert ((tab.rung == sb.GAP_RUNG) & (tab.key == "same|2|dh400-800")).any()
    a = sb.assign(d, tab, rungs=sb.APPLIED_RUNGS, gap_rung=True)
    assert a.loc[0, "rung"] == sb.GAP_RUNG and a.loc[1, "rung"] == "not multi"
    assert sb.record_rung(d, sb.fit_table(d)).loc[0, "rung"] == "k2"


def test_frozen_interval_text_is_canonical() -> None:
    r = pd.DataFrame({"group": ["MID_WCC", "MID_DEAN"], "treatment": ["mid_r2p", "mid_r2p"], "role": ["record", "record"], "stream": ["oil", "oil"],
                      "horizon": [12, 12], "d99_cell": [True, True], "tuning_bias": [0.1, -0.05], "interval_lo": [-0.01, -0.2], "interval_hi": [0.2, 0.1]})
    a, b = sb.frozen_intervals_csv(r), sb.frozen_intervals_csv(r.iloc[::-1])
    assert a == b and "\r" not in a and sb.sha256_text(a) == sb.sha256_text(b)


def test_record_rule_reads_scored_counts() -> None:
    cells = pd.DataFrame([{"variant": sb.PROX_WF, "stream": "oil", "cutoff": c, "horizon": k, "n_packages": n}
                          for c, n in (("2021-12-01", 100), ("2022-12-01", 50)) for k in (12, 24)])
    counts = pd.DataFrame([{"cutoff": c, "horizon": k, "n_tuning": 100, "n_holdout": h} for c, h in (("2021-12-01", 20), ("2022-12-01", 30)) for k in (12, 24)])
    r = sb.record_treatment(cells, counts)
    assert r["expected_wf"][12] == pytest.approx(20 + 15) and r["record"] == sb.PROX_WF
    counts["n_holdout"] = 10
    assert sb.record_treatment(cells, counts)["record"] == sb.PROX
