import shutil

import numpy as np
import pandas as pd
import pytest

from box import holdout15 as h
from box import tune15_report as t15


def test_frozen_manifest_digests_and_values_match_sources():
    m, chk = h.load_frozen(h.TUNING)
    assert chk["digest_match"].all() and chk["intervals_match_source"].all()
    assert set(m["bench"]) == set(t15.FROZEN)
    iv = h.intervals(m, "WCB_1")
    assert list(zip(iv["stream"], iv["horizon"], strict=True)) == [("oil", 12), ("oil", 24), ("oil", 36), ("gas", 12), ("gas", 24), ("gas", 36)]


def test_load_frozen_refuses_a_moved_interval(tmp_path):
    for f in h.TUNING.glob("intervals_*.csv"):
        shutil.copy(f, tmp_path / f.name)
    shutil.copy(h.TUNING / "frozen_d99.csv", tmp_path / "frozen_d99.csv")
    p = tmp_path / "intervals_WCC.csv"
    iv = pd.read_csv(p)
    iv.loc[0, "interval_hi"] += 0.01
    iv.to_csv(p, index=False)
    with pytest.raises(ValueError, match="intervals_WCC.csv"):
        h.load_frozen(tmp_path)


def _view():
    # two cutoffs x two packages; the wf variant has no prediction at the first cutoff (no haircut yet)
    return pd.DataFrame({"cutoff": ["2019-12-01"] * 2 + ["2022-12-01"] * 2, "pkg": ["a", "b", "c", "d"],
                         "actual_oil12": [90.0, 110.0, 80.0, 100.0], "pred_box_v2_wf_oil12": [np.nan, np.nan, 100.0, 100.0]})


def test_packages_by_cutoff_counts_only_predicted():
    t = h.packages_by_cutoff(_view(), "box_v2_wf", [("oil", 12)])
    assert list(t["cutoff"]) == ["2019", "2022"] and list(t["oil cum-12"]) == [0, 2]


def test_wf_identity_roundtrip():
    pv = pd.DataFrame({"stream": ["oil"], "cutoff": [2022], "cum-12": [-0.06], "cum-24": [np.nan]})
    log = [{"cutoff": "2022-12-01", "variant": "box_v2", "stream": "oil", "horizon": 12, "haircut": -0.06},
           {"cutoff": "2022-12-01", "variant": "box_v2", "stream": "oil", "horizon": 24, "haircut": None}]
    w = h.wf_identity(log, pv)
    assert w["identical"].all() and len(w) == 2
    log[0]["haircut"] = -0.05
    assert not h.wf_identity(log, pv)["identical"].all()


def test_discrimination_reads_chosen_variant_file():
    d = h.discrimination(h.TUNING, "intervals_BS3_C_alt_box_v2.csv")
    assert 0.0 <= d["passes_good"] <= 1.0 and 0.0 <= d["catches_15pct_high"] <= 1.0
