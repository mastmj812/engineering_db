"""BOX step 12a — water: the tuning identity guard and the ONE-TIME holdout verdict under the rule frozen at gate 11 (D109;
docs/box/step11-2026-10-19/PREREGISTRATION.md §5, intervals_water.csv). Pure, DB-free.

Rule (D109, unchanged): pooled group x horizon cells on measured-water packages, method `ratio` on raw box_v2 oil (D107 / D108).
  (i)   the group's oil is validated (`covered`)
  (ii)  every judged pooled TUNING cell passes the water cell test (|bias| <= 20 % AND scale-free band <= benchmark + 0.10, >= 30 pkgs)
  (iii) every judged HOLDOUT cell (>= 10 packages) lies inside its frozen P2.5-P97.5 tuning interval, at least one judged
  -> validated water; otherwise provisional (D105-style disclosure). The +-20 % and spread tests are reported per holdout cell, never gating.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import water11_report as wr

METHOD = "ratio"  # D107
INTERVALS_SHA256 = "969981e5d1f5355bbf4af76eab5c61eabbb50f70f5b683c553ba30a5146fe5ea"  # frozen at gate 11 (D109); checked before scoring
IDENTITY_TOL = 1e-9


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(old: pd.DataFrame, new: pd.DataFrame, method: str = METHOD, tol: float = IDENTITY_TOL) -> pd.DataFrame:
    """Per group x horizon: step-11 vs re-scored pooled ratio cells (packages, bias, band) and whether they agree within tol."""
    cols = ["pkg_n_packages", "pkg_bias", "pkg_band", "bench_bias", "bench_band"]
    o = old[old["method"] == method].set_index(["group", "horizon"])[cols]
    n = new[new["method"] == method].set_index(["group", "horizon"])[cols]
    j = o.join(n, lsuffix="_s11", rsuffix="_12a", how="outer")
    diffs = [np.abs(j[f"{c}_s11"].astype(float) - j[f"{c}_12a"].astype(float)) for c in cols]
    j["max_abs_diff"] = np.nanmax(np.column_stack(diffs), axis=1)
    j["identical"] = j["max_abs_diff"] <= tol
    return j.reset_index()


def holdout_cells(h: pd.DataFrame, intervals: pd.DataFrame, method: str = METHOD) -> pd.DataFrame:
    """Pooled holdout cells of `method` per group x horizon with the frozen interval and the consistency verdict (>= 10 packages);
    the D109-reported (non-gating) +-20 % and spread tests alongside."""
    c = wr.cells(h, ("group",), (method,))
    iv = intervals.set_index(["group", "horizon"])
    rows = []
    for r in c.itertuples():
        lo, hi = (iv.loc[(r.group, r.horizon), ["interval_lo", "interval_hi"]] if (r.group, r.horizon) in iv.index else (np.nan, np.nan))
        n = int(r.pkg_n_packages)
        judged = n >= wr.MIN_HOLDOUT_PACKAGES and np.isfinite(r.pkg_bias) and np.isfinite(lo)
        inside = bool(lo <= r.pkg_bias <= hi) if judged else None
        sf, bsf = ac.scale_free(r.pkg_band, r.pkg_bias), ac.scale_free(r.bench_band, r.bench_bias)
        rows.append({"group": r.group, "horizon": r.horizon, "packages": n, "holdout_bias": r.pkg_bias, "interval_lo": lo, "interval_hi": hi,
                     "consistency": "not judged" if not judged else ("INSIDE" if inside else "OUTSIDE"),
                     "bias_within_20pct": bool(abs(r.pkg_bias) <= wr.BIAS_TOL_W) if np.isfinite(r.pkg_bias) else None,
                     "band_sf": sf, "bench_bias": r.bench_bias, "bench_band_sf": bsf,
                     "spread_ok": bool(sf <= bsf + wr.BAND_TOL_W) if np.isfinite(sf) and np.isfinite(bsf) else None})
    return pd.DataFrame(rows)


def tier(group: str, oil_validated: bool, tuning: pd.DataFrame, hold: pd.DataFrame | None, method: str = METHOD) -> dict[str, Any]:
    """D109 water tier for one group from its pooled tuning cells (wr.cells) and holdout cells (holdout_cells; None = no holdout)."""
    t = tuning[(tuning["group"] == group) & (tuning["method"] == method) & (tuning["verdict"] != "not judged")]
    c2 = bool(len(t)) and bool((t["verdict"] == "PASS").all())
    hj = hold[(hold["group"] == group) & (hold["consistency"] != "not judged")] if hold is not None else pd.DataFrame(columns=["consistency"])
    c3 = bool(len(hj)) and bool((hj["consistency"] == "INSIDE").all())
    reasons = []
    if not oil_validated:
        reasons.append("oil provisional (D105): water never ranks above its oil")
    if not c2:
        reasons.append(f"tuning: {int((t['verdict'] == 'FAIL').sum())} of {len(t)} judged cells fail the water test")
    if hold is None or not len(hj):
        reasons.append("no judged holdout cell")
    elif not c3:
        reasons.append(f"holdout: {int((hj['consistency'] == 'OUTSIDE').sum())} of {len(hj)} judged cells outside the frozen interval")
    return {"group": group, "oil_validated": oil_validated, "tuning_all_pass": c2, "holdout_judged": len(hj), "holdout_all_inside": c3,
            "water_tier": "validated" if (oil_validated and c2 and c3) else "provisional", "reasons": "; ".join(reasons) or "all three conditions met"}
