"""BOX step 15 — the one-time D52 holdout of the six benches accepted at the step-15 tuning gate, judged under D99 (DB-free).

The rule is 9b's (box/holdout9b): each bench's holdout packages are POOLED across cutoffs per stream x horizon, and a bench PASSES
when every frozen cell's holdout package bias lies inside its frozen P2.5-P97.5 interval. +-10 % bias and the D58 scale-free
spread are reported, not gating. A FAIL means diagnose (7a pattern), never re-tune; the intervals are never redrawn.

What is new here is only the frozen manifest: docs/box/step15-tuning-2026-10-17/frozen_d99.csv carries, per bench, the chosen
record variant, the judged cells, their intervals and the SHA-256 (LF bytes) of the interval file they were copied from
(box/tune15_report.FROZEN mirrors the choice). `load_frozen` refuses to judge if a digest or the manifest's intervals no longer
match the source file, or if the manifest disagrees with FROZEN.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import holdout9b as h9
from box import tune15_report as t15

TUNING = Path("docs") / "box" / "step15-tuning-2026-10-17"


def sha256_lf(path: Path) -> str:
    """The manifest's digest: SHA-256 of the file's bytes with CRLF normalised to LF (checkout-independent)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_frozen(tuning_dir: Path = TUNING) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(manifest, integrity table). Raises if any source digest moved, any manifest interval differs from its source file, or the
    bench / variant / horizon set differs from tune15_report.FROZEN."""
    m = pd.read_csv(tuning_dir / "frozen_d99.csv")
    m["horizon"] = m["horizon"].astype(int)
    rows = []
    for (b, f), g in m.groupby(["bench", "source_file"], sort=False):
        src = tuning_dir / str(f)
        dig = sha256_lf(src)
        iv = pd.read_csv(src)
        iv["horizon"] = iv["horizon"].astype(int)
        j = g.merge(iv, on=["stream", "horizon"], suffixes=("", "_src"), how="left")
        same = bool(np.allclose(j[["tuning_bias", "interval_lo", "interval_hi"]].to_numpy(float),
                                j[["tuning_bias_src", "interval_lo_src", "interval_hi_src"]].to_numpy(float), rtol=0, atol=1e-12))
        rows.append({"bench": b, "source_file": f, "manifest_sha256": g["source_sha256_lf"].iloc[0], "sha256_now": dig,
                     "digest_match": dig == g["source_sha256_lf"].iloc[0], "intervals_match_source": same})
    chk = pd.DataFrame(rows)
    bad = chk[~(chk["digest_match"] & chk["intervals_match_source"])]
    if len(bad):
        raise ValueError(f"frozen D99 source changed since the tuning gate (D99 forbids redrawing): {bad['source_file'].tolist()}")
    for b, spec in t15.FROZEN.items():
        g = m[m.bench == b]
        if set(g["record_variant"]) != {spec["variant"]} or set(g["horizon"]) != set(spec["horizons"]) or len(g) != 2 * len(spec["horizons"]):
            raise ValueError(f"{b}: frozen_d99.csv disagrees with tune15_report.FROZEN")
    if set(m["bench"]) != set(t15.FROZEN):
        raise ValueError("frozen_d99.csv bench set differs from tune15_report.FROZEN")
    return m, chk


def intervals(manifest: pd.DataFrame, bench: str) -> pd.DataFrame:
    """The bench's frozen cells in 9b's interval-table shape (oil then gas, by horizon)."""
    g = manifest[manifest.bench == bench][["stream", "horizon", "tuning_bias", "interval_lo", "interval_hi"]]
    g = g.assign(_s=g["stream"].map({"oil": 0, "gas": 1})).sort_values(["_s", "horizon"]).drop(columns="_s")
    return g.reset_index(drop=True)


def judge(v: pd.DataFrame, variant: str, iv: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """9b's pooled cells + verdict, unchanged (the statistic the intervals were drawn with)."""
    cells = h9.pooled_cells(v, variant, iv)
    return cells, h9.verdict(cells)


def packages_by_cutoff(v: pd.DataFrame, variant: str, cells: Sequence[tuple[str, int]]) -> pd.DataFrame:
    """Scored holdout packages per cutoff per cell (a package is scored when any member has actual and a positive prediction).
    For a box_v2_wf record this shows only the cutoffs with a walk-forward haircut contribute (no haircut = no prediction)."""
    rows = []
    for c, g in v.groupby("cutoff"):
        r: dict[str, Any] = {"cutoff": str(c)[:4]}
        for s, k in cells:
            a, p = g[f"actual_{s}{k}"].astype(float), g[f"pred_{variant}_{s}{k}"].astype(float)
            ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
            r[f"{s} cum-{k}"] = int(g.loc[ok, "pkg"].nunique())
        rows.append(r)
    return pd.DataFrame(rows)


def wf_log_from_pivot(pv: pd.DataFrame) -> list[dict[str, Any]]:
    """The tuning page's walk_forward_<bench>.csv (stream, cutoff year, cum-k columns) back to a summary-style log."""
    out = []
    for _, r in pv.iterrows():
        for col in [c for c in pv.columns if str(c).startswith("cum-")]:
            v = r[col]
            out.append({"cutoff": f"{int(r['cutoff'])}-12-01", "variant": "box_v2", "stream": r["stream"], "horizon": int(col[4:]),
                        "haircut": None if pd.isna(v) else float(v)})
    return out


def wf_identity(holdout_log: Sequence[Mapping[str, Any]], tuning_pivot: pd.DataFrame) -> pd.DataFrame:
    """D58 / D94: holdout haircuts come from the tuning cells only, so they must equal the tuning page's walk-forward table."""
    h = [x for x in holdout_log if x.get("variant") == "box_v2" and str(x.get("cutoff", ""))[:4].isdigit()]
    h = [{**x, "cutoff": f"{str(x['cutoff'])[:4]}-12-01"} for x in h]
    return h9.walk_forward_identity(h, wf_log_from_pivot(tuning_pivot), "box_v2")


def discrimination(tuning_dir: Path, source_file: str) -> dict[str, float]:
    """From the tuning page's consistency_rate file for the frozen variant: how often the rule passes a forecast as good as tuning
    (scale 1.0) and catches a 15 %-high forecast (scale 1.15)."""
    cr = pd.read_csv(tuning_dir / source_file.replace("intervals_", "consistency_rate_"))
    rate = dict(zip(cr["scale"].round(2), cr["pass_rate"], strict=True))
    return {"passes_good": float(rate.get(1.0, np.nan)), "catches_15pct_high": 1.0 - float(rate.get(1.15, np.nan))}
