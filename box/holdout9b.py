"""BOX step 9b — the one-time D52 holdout of BS2_S and WCXY judged under D99 (read-only, DB-free).

D99 (Michael 2026-10-17, before 9b): each bench's holdout packages are scored POOLED across cutoffs per stream x horizon
(BS2_S oil + gas cum-12 / 24; WCXY oil + gas cum-12 / 24 / 36). A bench PASSES when every cell's holdout package bias lies
inside its FROZEN P2.5-P97.5 interval (docs/box/pre9b-2026-10-16/intervals_<bench>.csv). The +-10 % bias test and the D58
scale-free spread test are reported per cell, NOT gating. A FAIL means diagnose (7a pattern), never re-tune; the intervals
are never redrawn.

The pooled statistic is computed with box/rehearse9b.judge / _stats - the same function the intervals were drawn with - so
holdout and interval measure exactly the same thing (mean over packages of sum actual / sum predicted - 1; negative = the
forecast is HIGH). Inputs are the `scripts.box_acceptance --score-holdout --holdout-once --fold analog` frames
(view_<tag>_<yyyy>.csv.gz, cells_<tag>.csv, summary_<tag>.json). Nothing here re-scores a prediction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import rehearse9b as r

# D99: the judged cells and the record variant per bench (D94: BS2_S box_v2_wf on its own haircut; D97: WCXY raw box_v2)
BENCHES: dict[str, dict[str, Any]] = {
    "BS2_S": {"record": "box_v2_wf", "intervals": "intervals_BS2_S.csv",
              "cells": (("oil", 12), ("oil", 24), ("gas", 12), ("gas", 24))},
    "WCXY_WCA1": {"record": "box_v2", "intervals": "intervals_WCXY_WCA1.csv",
                  "cells": (("oil", 12), ("oil", 24), ("oil", 36), ("gas", 12), ("gas", 24), ("gas", 36))},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_intervals(path: Path, cells: Sequence[tuple[str, int]]) -> pd.DataFrame:
    """The frozen interval table, restricted to (and checked against) the D99 cell list - a missing cell is an error."""
    iv = pd.read_csv(path)
    iv["horizon"] = iv["horizon"].astype(int)
    have = set(zip(iv["stream"], iv["horizon"], strict=True))
    miss = [c for c in cells if c not in have]
    if miss:
        raise ValueError(f"{path}: no frozen interval for {miss}")
    key = pd.DataFrame(list(cells), columns=["stream", "horizon"])
    return key.merge(iv, on=["stream", "horizon"], how="left")


def pooled_cells(v: pd.DataFrame, variant: str, intervals: pd.DataFrame) -> pd.DataFrame:
    """Per D99 cell: holdout packages, BOX package bias (the interval's statistic), inside the frozen interval, plus the
    reported-only tests (|bias| <= 10 %, D58 scale-free spread vs the benchmark + 0.05) and the benchmark's own numbers."""
    t = r.package_table(v, variant)
    allp = np.ones(len(t["pkg"]), dtype=bool)
    rows = []
    for _, iv in intervals.iterrows():
        s, k = str(iv["stream"]), int(iv["horizon"])
        q = t["sums"][(s, k)]
        m = allp & np.isfinite(q["box_a"])
        e_box = q["box_a"][m] / q["box_p"][m] - 1.0
        mb = allp & np.isfinite(q["bench_a"])
        e_ben = q["bench_a"][mb] / q["bench_p"][mb] - 1.0
        b, w = r._stats(e_box)
        bb, bw = r._stats(e_ben)
        sf, bsf = ac.scale_free(w, b), ac.scale_free(bw, bb)
        inside = bool(np.isfinite(b) and iv["interval_lo"] <= b <= iv["interval_hi"])
        rows.append({"stream": s, "horizon": k, "packages": int(m.sum()), "wells": int(v[f"actual_{s}{k}"].notna().sum()),
                     "tuning_bias": float(iv["tuning_bias"]), "interval_lo": float(iv["interval_lo"]), "interval_hi": float(iv["interval_hi"]),
                     "holdout_bias": b, "inside_interval": inside,
                     "bias_ok_10pct": bool(np.isfinite(b) and abs(b) <= ac.BIAS_TOL),
                     "band": w, "band_scale_free": sf, "bench_bias": bb, "bench_band": bw, "bench_band_scale_free": bsf,
                     "spread_ok": bool(np.isfinite(sf) and np.isfinite(bsf) and sf <= bsf + ac.BAND_TOL),
                     "judged_d53_size": int(m.sum()) >= ac.MIN_PACKAGES})
    return pd.DataFrame(rows)


def verdict(cells: pd.DataFrame) -> dict[str, Any]:
    """D99: PASS iff every cell is inside its frozen interval (oil AND gas); by stream for the record."""
    out: dict[str, Any] = {"by_stream": {}}
    for s, g in cells.groupby("stream"):
        out["by_stream"][s] = "PASS" if bool(g["inside_interval"].all()) else "FAIL"
    out["overall"] = "PASS" if len(cells) and bool(cells["inside_interval"].all()) else "FAIL"
    out["n_cells"], out["n_outside"] = len(cells), int((~cells["inside_interval"]).sum())
    out["outside"] = [f"{s} cum-{k}" for s, k, ok in zip(cells["stream"], cells["horizon"], cells["inside_interval"], strict=True) if not ok]
    return out


def per_cutoff(cells: pd.DataFrame, variant: str, horizons: Sequence[int]) -> pd.DataFrame:
    """The harness's per-cutoff D53 cells for the record variant (the rule as written; reported only, D99)."""
    c = cells[(cells.variant == variant) & cells.horizon.isin(horizons)].copy()
    c["horizon"] = c["horizon"].astype(int)
    return c[["cutoff", "stream", "horizon", "n_packages", "n_wells", "pkg_bias", "pkg_band", "bench_bias", "bench_band", "verdict"]]


def walk_forward_identity(holdout_log: Sequence[Mapping[str, Any]], tuning_log: Sequence[Mapping[str, Any]], variant_base: str) -> pd.DataFrame:
    """D58 / D94: the holdout's haircuts come from the TUNING cells only, so they must equal the haircuts the tuning view
    applied at each (cutoff, stream, horizon). Returns the side-by-side table with |diff|."""
    def _df(log: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
        d = pd.DataFrame(list(log))
        if d.empty:
            return pd.DataFrame(columns=["cutoff", "stream", "horizon", "haircut"])
        d = d[d["variant"] == variant_base]
        return d[["cutoff", "stream", "horizon", "haircut"]]
    h, t = _df(holdout_log), _df(tuning_log)
    m = h.merge(t, on=["cutoff", "stream", "horizon"], how="outer", suffixes=("_holdout", "_tuning"))
    a, b = pd.to_numeric(m["haircut_holdout"], errors="coerce"), pd.to_numeric(m["haircut_tuning"], errors="coerce")
    m["abs_diff"] = (a - b).abs()
    m["identical"] = (a.isna() & b.isna()) | ((a - b).abs() <= 1e-12)
    return m.sort_values(["stream", "horizon", "cutoff"]).reset_index(drop=True)


def size_adjusted(pooled: pd.DataFrame) -> pd.DataFrame:
    """SENSITIVITY, not the rule: the frozen intervals were drawn at the rehearsal's package count (a 20 % draw of the tuning
    packages); a larger holdout resolves bias more tightly, roughly by sqrt(n_holdout / n_rehearsal). Shrinks each interval
    about its tuning bias by that factor and re-asks 'inside?'. The D99 verdict uses the frozen intervals unchanged."""
    f = np.sqrt(pooled["packages"] / pooled["rehearsal packages p50"])
    tb = pooled["tuning_bias"]
    lo, hi = tb + (pooled["interval_lo"] - tb) / f, tb + (pooled["interval_hi"] - tb) / f
    return pd.DataFrame({"stream": pooled["stream"], "horizon": pooled["horizon"], "packages": pooled["packages"],
                         "rehearsal packages p50": pooled["rehearsal packages p50"], "shrink": f, "adj_lo": lo, "adj_hi": hi,
                         "holdout_bias": pooled["holdout_bias"], "inside_adjusted": (pooled["holdout_bias"] >= lo) & (pooled["holdout_bias"] <= hi)})
