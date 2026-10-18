"""BOX step 15 stage 2 — 9a-style tuning view for the step-15 benches (read-only; tuning blocks only).

Inputs: one `scripts.box_acceptance --fold analog` run per bench (BENCH_SPECS pre-registered at gate 14, 2026-10-17). Per bench:
the D53 cells of the record variant per cutoff, the same cells POOLED across cutoffs (thin benches judge few per-cutoff cells),
the walk-forward haircut log (D57 / D94), the D62-style tuning haircut table, the D92 realised factors (box_v2_wf records only —
a raw record carries no haircut, D97), edge behaviour (box/tune9a_report's edge geometry, regions by compass side), and the
FROZEN D99 consistency intervals for the later one-time holdout (box/rehearse9b.consistency: 2,000 random 20 % draws of 3-mi
blocks of the TUNING packages, P2.5-P97.5). No holdout package is read; holdout counts come from step 14 (counts only).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import rehearse9b as r9
from box import strike as stk
from box import tune9a_report as t9

# Gate-14 reading of the D99 cells from the step-14 RAW counts (FINDINGS §4). The cells frozen at the tuning gate apply the same
# rule (pooled holdout reaching 30) to expected_holdout() - the counts the record variant can actually score. Original note: pooled holdout cells that reach 30
# packages in the step-14 counts; for a box_v2_wf record only the cutoffs with a walk-forward haircut count).
D99_CELLS: dict[str, tuple[int, ...]] = {"BS3_S": (12, 24), "BS3_C": (12, 24), "WCB_1": (12, 24), "WCB_2": (12, 24, 36),
                                         "BS1_S": (12, 24), "WCC": (12, 24), "BS2_C": (12, 24)}
ORDER = ("BS3_S", "BS3_C", "WCB_1", "WCB_2", "BS1_S", "WCC", "BS2_C")


def record_variant(bench: str) -> str:
    return ac.BENCH_SPECS[bench].get("record", ac.RECORD_V2)


def d99_cells(bench: str) -> list[tuple[str, int]]:
    return [(s, k) for s in ac.STREAMS for k in D99_CELLS[bench]]


def per_cutoff(cells: pd.DataFrame, variant: str) -> pd.DataFrame:
    """D53 cells of `variant` per cutoff with the scale-free bands (D58) next to the benchmark's."""
    c = cells[cells.variant == variant].copy()
    c["sf band"] = [ac.scale_free(b, x) for b, x in zip(c["pkg_band"], c["pkg_bias"], strict=True)]
    c["sf band bench"] = [ac.scale_free(b, x) for b, x in zip(c["bench_band"], c["bench_bias"], strict=True)]
    c = c[c["n_packages"] > 0]
    return c[["stream", "horizon", "cutoff", "n_packages", "pkg_bias", "sf band", "bench_bias", "sf band bench", "verdict"]].sort_values(
        ["stream", "horizon", "cutoff"]).reset_index(drop=True)


def pooled(t: dict[str, Any], horizons: Iterable[int] = (12, 24, 36)) -> pd.DataFrame:
    """Every tuning package pooled across cutoffs per stream x horizon: D53 / D58 verdict at >= 30 packages, bias, scale-free band
    vs the benchmark's (the form the D99 holdout cells take)."""
    full = np.ones(len(t["pkg"]), dtype=bool)
    rows = []
    for s in ac.STREAMS:
        for k in horizons:
            q = t["sums"].get((s, k), {})
            if "box_a" not in q:
                continue
            v, n, b = r9.judge(full, t, s, k)
            m = np.isfinite(q["box_a"])
            bb, bw = r9._stats(q["bench_a"][np.isfinite(q["bench_a"])] / q["bench_p"][np.isfinite(q["bench_a"])] - 1.0)
            _, w = r9._stats(q["box_a"][m] / q["box_p"][m] - 1.0)
            rows.append({"stream": s, "horizon": k, "n_packages": n, "pkg_bias": b, "sf band": ac.scale_free(w, b), "bench_bias": bb,
                         "sf band bench": ac.scale_free(bw, bb), "verdict": v})
    return pd.DataFrame(rows)


def wf_log(summary: dict[str, Any]) -> pd.DataFrame:
    w = pd.DataFrame([x for x in summary["walk_forward"] if x["variant"] == "box_v2"])
    if w.empty:
        return w
    w["cutoff"] = w["cutoff"].str[:4]
    return w.pivot_table(index=["stream", "cutoff"], columns="horizon", values="haircut").rename(columns=lambda k: f"cum-{k}").reset_index()


def side_classes(x: np.ndarray, y: np.ndarray, extent_ft: Any, edge_mi: float = t9.EDGE_MI) -> pd.DataFrame:
    """t9.edge_classes with the region named by compass side of the nearest boundary point (N / E / S / W edge, or interior)."""
    e = t9.edge_classes(x, y, extent_ft, edge_mi)
    side = np.array(["N", "E", "S", "W"])[(((e["edge_bearing_deg"].to_numpy() + 45.0) % 360.0) // 90.0).astype(int)]
    e["region"] = np.where(e["edge_dist_mi"] > edge_mi, "interior", np.char.add(side.astype(str), " edge"))
    return e


def region_table(v: pd.DataFrame, variant: str, horizons: Sequence[int] = (12, 24, 36)) -> pd.DataFrame:
    """t9.region_table for any variant: per region, strike share, radius, strike-vs-edge angle, oil package bias (packages = the
    region's members) for the record variant and the benchmark."""
    rows = []
    for reg, g in v.groupby("region"):
        st = g[g["v2_mode"] == "strike"]
        ang = [stk.angle_diff(float(a), float(e)) for a, e in zip(st["v2_strike_az_deg"], st["edge_az_deg"], strict=True) if np.isfinite(a)]
        r = {"region": reg, "locations": len(g), "strike share": float((g["v2_mode"] == "strike").mean()),
             "past 5 mi share": float((g["v2_radius_mi"] > 5.0).mean()), "radius p50 mi": float(g["v2_radius_mi"].median()),
             "strike vs edge angle p50 deg": float(np.median(ang)) if ang else np.nan}
        for k in horizons:
            col = f"pred_{variant}_oil{k}"
            if col not in g:
                continue
            pp = ac.package_errors(g, "package", f"actual_oil{k}", col)
            bp = ac.package_errors(g, "package", f"actual_oil{k}", f"bench_oil{k}")
            r[f"oil{k} packages"] = len(pp)
            r[f"oil{k} bias"] = float(pp["err"].mean()) if len(pp) else np.nan
            r[f"oil{k} bench bias"] = float(bp["err"].mean()) if len(bp) else np.nan
        rows.append(r)
    order = {"interior": 0, "N edge": 1, "E edge": 2, "S edge": 3, "W edge": 4}
    return pd.DataFrame(rows).sort_values("region", key=lambda s: s.map(order)).reset_index(drop=True)


def bench_findings(per: pd.DataFrame, pool: pd.DataFrame, ivl: pd.DataFrame) -> dict[str, Any]:
    """Headline numbers per bench (for the summary table)."""
    judged = per[per["verdict"].isin(["PASS", "FAIL"])]
    pj = pool[pool["verdict"].isin(["PASS", "FAIL"])]
    return {"per_cutoff_judged": len(judged), "per_cutoff_fail": int((judged["verdict"] == "FAIL").sum()),
            "per_cutoff_bias_fail": int((judged["pkg_bias"].abs() > ac.BIAS_TOL).sum()),
            "pooled_judged": len(pj), "pooled_fail": int((pj["verdict"] == "FAIL").sum()),
            "pooled_bias_fail": int((pj["pkg_bias"].abs() > ac.BIAS_TOL).sum()),
            "max_abs_pooled_oil_bias": float(pool.loc[pool.stream == "oil", "pkg_bias"].abs().max()),
            "d99_cells": len(ivl)}


def expected_holdout(cells: pd.DataFrame, variant: str, counts14: pd.DataFrame, horizons: Sequence[int] = (12, 24, 36)) -> pd.DataFrame:
    """Expected pooled holdout packages per horizon for `variant`, WITHOUT reading a holdout package: step-14 holdout COUNTS per
    cutoff x the share of that cutoff's tuning packages the variant actually scored (a thin as-of analog pool or an undefined F(k)
    / walk-forward haircut leaves locations unpredicted). The gate-14 rule (D99 cell = pooled holdout reaching 30) is applied to
    this, not to the raw counts, which assumed every package is scored."""
    oil = cells[(cells.variant == variant) & (cells.stream == "oil")].set_index(["cutoff", "horizon"])["n_packages"]
    rows = []
    for k in horizons:
        c14 = counts14[counts14.horizon == k].set_index("cutoff")
        exp, raw, used = 0.0, 0, []
        for c, r in c14.iterrows():
            n_t = int(r["n_tuning"])
            n_s = int(oil.get((c, k), 0))
            raw += int(r["n_holdout"])
            if n_s > 0 and n_t > 0:
                exp += r["n_holdout"] * min(1.0, n_s / n_t)
                used.append(c[:4])
        rows.append({"horizon": k, "holdout_counts_all_cutoffs": raw, "expected_holdout_scored": exp, "scored_cutoffs": ", ".join(used),
                     "d99_cell": exp >= MIN_D99})
    return pd.DataFrame(rows)


MIN_D99 = 30
