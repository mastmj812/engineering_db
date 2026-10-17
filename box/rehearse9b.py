"""BOX pre-9b rehearsal (read-only, DB-free): can the 9b holdout rule tell a good forecast from a bad one at holdout size?

Michael 2026-10-16, before 9b: instead of learning what the rule does by spending the one-time holdout, apply the EXACT 9b
rule to random 20 % subsets of 3-mile blocks of the TUNING packages (the holdout's shape: D52 = a salted 20 % of 3-mi blocks;
a package is in when any member's lateral midpoint is in a drawn block) and read the verdict distribution. No holdout well is
read. Also: how many cells each rule would judge, and how the verdict moves when the forecast is deliberately biased
(predictions x s), i.e. whether the rule discriminates.

Rules compared (D53 / D58 cell test everywhere: |package bias| <= 10 % AND scale-free band <= the benchmark's + 0.05;
a cell is judged with >= 30 packages):
  per_cutoff  — as written: every judged (cutoff x stream x horizon) cell passes, oil AND gas; nothing judged = FAIL
  pooled      — one cell per stream x horizon pooling every cutoff's packages (the D48 bench-pooled idea)
  *_bias      — the same with the bias half only (spread not tested)

Inputs: the step-9a tuning frames (runs/box9a/<bench>/view_<tag>_<yyyy>.csv.gz): per scored well its package, actuals,
the record variant's prediction and the benchmark's. Walk-forward caveat: the frames' box_v2_wf predictions carry haircuts
from the full tuning view (the holdout run takes them from the same tuning cells, so this matches 9b).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import dev_factor_report as dfr
from box import holdout as ho

HORIZONS = (12, 24, 36)  # cum-48 has no judged tuning cell on either bench
SHARE = ho.SHARE


def load_frames(run_dir: Path, tag: str) -> pd.DataFrame:
    v = pd.concat([pd.read_csv(f, dtype={"api10": str}) for f in sorted(run_dir.glob(f"view_{tag}_*.csv.gz"))], ignore_index=True)
    x, y = dfr._xy(v["mid_lon"], v["mid_lat"])
    v["bx"], v["by"] = ho.blocks(np.asarray(x), np.asarray(y))
    v["pkg"] = v["cutoff"].astype(str) + ":" + v["package"].astype(str)
    return v


def package_table(v: pd.DataFrame, variant: str, horizons: Sequence[int] = HORIZONS) -> dict[str, Any]:
    """Per package: cutoff, its blocks, and per (stream, k) the member sums used by package_errors for BOX and benchmark."""
    pk = v.groupby("pkg").agg(cutoff=("cutoff", "first")).reset_index()
    idx = {p: i for i, p in enumerate(pk["pkg"])}
    blk = v[["pkg", "bx", "by"]].drop_duplicates()
    blocks = sorted(set(zip(blk["bx"], blk["by"], strict=True)))
    bidx = {b: i for i, b in enumerate(blocks)}
    member = np.zeros((len(pk), len(blocks)), dtype=bool)
    member[[idx[p] for p in blk["pkg"]], [bidx[(a, b)] for a, b in zip(blk["bx"], blk["by"], strict=True)]] = True
    sums: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    for s in ac.STREAMS:
        for k in horizons:
            out = {}
            for who, col in (("box", f"pred_{variant}_{s}{k}"), ("bench", f"bench_{s}{k}")):
                if col not in v:
                    continue
                a, p = v[f"actual_{s}{k}"].astype(float), v[col].astype(float)
                ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
                g = v[ok].assign(_a=a[ok], _p=p[ok]).groupby("pkg")[["_a", "_p"]].sum()
                arr_a, arr_p = np.full(len(pk), np.nan), np.full(len(pk), np.nan)
                ii = [idx[x] for x in g.index]
                arr_a[ii], arr_p[ii] = g["_a"].to_numpy(), g["_p"].to_numpy()
                out[f"{who}_a"], out[f"{who}_p"] = arr_a, arr_p
            sums[(s, k)] = out
    return {"pkg": pk, "member": member, "n_blocks": len(blocks), "sums": sums}


def _stats(err: np.ndarray) -> tuple[float, float]:
    e = err[np.isfinite(err)]
    if not len(e):
        return float("nan"), float("nan")
    hi, lo = np.percentile(e, [90, 10])
    return float(e.mean()), float(hi - lo)


def judge(sel: np.ndarray, t: dict[str, Any], s: str, k: int, scale: float = 1.0, bias_only: bool = False) -> tuple[str, int, float]:
    """Verdict, package count, BOX bias for the packages in `sel` on (stream, k); predictions x `scale`."""
    q = t["sums"][(s, k)]
    if "box_a" not in q:
        return "not judged", 0, float("nan")
    m = sel & np.isfinite(q["box_a"])
    n = int(m.sum())
    e_box = q["box_a"][m] / (q["box_p"][m] * scale) - 1.0
    mb = sel & np.isfinite(q["bench_a"])
    e_ben = q["bench_a"][mb] / q["bench_p"][mb] - 1.0
    b, w = _stats(e_box)
    bb, bw = _stats(e_ben)
    if n < ac.MIN_PACKAGES or not np.isfinite(b):
        return "not judged", n, b
    if bias_only:
        return ("PASS" if abs(b) <= ac.BIAS_TOL else "FAIL"), n, b
    return ac.judge_cell({"bias": b, "band": w}, {"bias": bb, "band": bw}, n), n, b


def verdicts(sel: np.ndarray, t: dict[str, Any], cutoffs: Iterable[str], scale: float = 1.0, horizons: Sequence[int] = HORIZONS) -> dict[str, Any]:
    """Overall verdict of each rule for one subset of packages."""
    cut = t["pkg"]["cutoff"].astype(str).to_numpy()
    out: dict[str, Any] = {}
    for bias_only in (False, True):
        sfx = "_bias" if bias_only else ""
        per, pooled = [], []
        for s in ac.STREAMS:
            for k in horizons:
                for c in cutoffs:
                    per.append(judge(sel & (cut == c), t, s, k, scale, bias_only)[0])
                pooled.append(judge(sel, t, s, k, scale, bias_only)[0])
        for name, vs in (("per_cutoff", per), ("pooled", pooled)):
            j = [x for x in vs if x != "not judged"]
            out[name + sfx] = "PASS" if j and all(x == "PASS" for x in j) else "FAIL"
            out[name + sfx + "_judged"] = len(j)
    return out


def rehearse(t: dict[str, Any], cutoffs: Sequence[str], n_draws: int = 2000, seed: int = 20261016, scales: Sequence[float] = (1.0,),
             share: float = SHARE) -> pd.DataFrame:
    """n_draws random block subsets at `share` (iid per block, like the salted hash); per draw x scale, every rule's verdict."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(n_draws):
        drawn = rng.random(t["n_blocks"]) < share
        sel = (t["member"] & drawn[None, :]).any(axis=1)
        for sc in scales:
            rows.append({"draw": d, "scale": sc, "n_packages": int(sel.sum()), **verdicts(sel, t, cutoffs, sc)})
    return pd.DataFrame(rows)


def cell_counts(t: dict[str, Any], cutoffs: Sequence[str], share: float = SHARE, n_draws: int = 500, seed: int = 7) -> pd.DataFrame:
    """Expected package count per (cutoff | pooled) x stream x horizon at a 20 % block draw (median and P10-P90 over draws),
    and the share of draws in which the cell reaches the 30-package judging floor."""
    rng = np.random.default_rng(seed)
    cut = t["pkg"]["cutoff"].astype(str).to_numpy()
    acc: dict[tuple[str, str, int], list[int]] = {}
    for _ in range(n_draws):
        drawn = rng.random(t["n_blocks"]) < share
        sel = (t["member"] & drawn[None, :]).any(axis=1)
        for s in ac.STREAMS:
            for k in HORIZONS:
                q = t["sums"][(s, k)]
                if "box_a" not in q:
                    continue
                ok = np.isfinite(q["box_a"])
                for c in (*cutoffs, "pooled"):
                    m = sel & ok & ((cut == c) if c != "pooled" else True)
                    acc.setdefault((c, s, k), []).append(int(m.sum()))
    return pd.DataFrame([{"cell": c, "stream": s, "horizon": k, "packages_p50": float(np.median(v)), "packages_p10_p90": f"{np.percentile(v, 10):.0f}–{np.percentile(v, 90):.0f}",
                          "share_judged": float(np.mean(np.array(v) >= ac.MIN_PACKAGES))} for (c, s, k), v in acc.items()])


def cell_noise(t: dict[str, Any], n_draws: int = 1000, seed: int = 11, share: float = SHARE) -> pd.DataFrame:
    """Per pooled stream x horizon cell: the full-tuning BOX bias, and over 20 % block draws the P5-P95 of the drawn BOX bias, the
    share of draws with |bias| <= 10 %, and the share passing the scale-free spread test alone — i.e. what a holdout this size
    can resolve when the forecast is exactly as good as it is in tuning."""
    rng = np.random.default_rng(seed)
    allp = np.ones(len(t["pkg"]), dtype=bool)
    rows = []
    draws = [(t["member"] & (rng.random(t["n_blocks"]) < share)[None, :]).any(axis=1) for _ in range(n_draws)]
    for s in ac.STREAMS:
        for k in HORIZONS:
            if "box_a" not in t["sums"][(s, k)]:
                continue
            _, _, b0 = judge(allp, t, s, k, bias_only=True)
            bs, sp, ns = [], [], []
            for sel in draws:
                v, n, b = judge(sel, t, s, k)
                if v == "not judged":
                    continue
                bs.append(b)
                ns.append(n)
                sp.append(_spread_ok(sel, t, s, k))
            bs = np.array(bs)
            rows.append({"stream": s, "horizon": k, "tuning_bias": b0, "packages_p50": float(np.median(ns)) if ns else 0.0,
                         "draw_bias_p5": float(np.percentile(bs, 5)) if len(bs) else np.nan, "draw_bias_p95": float(np.percentile(bs, 95)) if len(bs) else np.nan,
                         "share_bias_ok": float(np.mean(np.abs(bs) <= ac.BIAS_TOL)) if len(bs) else np.nan,
                         "share_spread_ok": float(np.mean(sp)) if sp else np.nan, "share_judged": len(bs) / n_draws})
    return pd.DataFrame(rows)


def _spread_ok(sel: np.ndarray, t: dict[str, Any], s: str, k: int) -> bool:
    q = t["sums"][(s, k)]
    m, mb = sel & np.isfinite(q["box_a"]), sel & np.isfinite(q["bench_a"])
    b, w = _stats(q["box_a"][m] / q["box_p"][m] - 1.0)
    bb, bw = _stats(q["bench_a"][mb] / q["bench_p"][mb] - 1.0)
    return bool(ac.scale_free(w, b) <= ac.scale_free(bw, bb) + ac.BAND_TOL)


def consistency(t: dict[str, Any], cells: Sequence[tuple[str, int]], n_draws: int = 2000, seed: int = 5, share: float = SHARE,
                q: tuple[float, float] = (2.5, 97.5), scales: Sequence[float] = (0.85, 0.90, 1.0, 1.10, 1.15)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Proposed 9b rule: the holdout is CONSISTENT with tuning when every pooled cell's package bias lies inside the [q] interval
    of the same cell over 20 % tuning draws. Returns (the frozen interval table, the rule's pass rate by forecast scale)."""
    rng = np.random.default_rng(seed)
    draws = [(t["member"] & (rng.random(t["n_blocks"]) < share)[None, :]).any(axis=1) for _ in range(n_draws)]
    b = {sc: np.array([[judge(sel, t, s, k, sc, True)[2] for s, k in cells] for sel in draws]) for sc in scales}
    lo, hi = np.nanpercentile(b[1.0], q[0], axis=0), np.nanpercentile(b[1.0], q[1], axis=0)
    full = np.ones(len(t["pkg"]), dtype=bool)
    tab = pd.DataFrame([{"stream": s, "horizon": k, "tuning_bias": judge(full, t, s, k, bias_only=True)[2], "interval_lo": a, "interval_hi": z}
                        for (s, k), a, z in zip(cells, lo, hi, strict=True)])
    rate = pd.DataFrame([{"scale": sc, "pass_rate": float(np.mean(((b[sc] >= lo) & (b[sc] <= hi)).all(axis=1)))} for sc in scales])
    return tab, rate
