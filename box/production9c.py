"""BOX step 9c — the per-bench pieces of a production run that covers WCA + BS2_S + WCXY (pure, DB-free).

  haircut_for(bench)          the haircut table each group carries: WCA = D62 (docs/box/acceptance tuning + holdout cells, per-cell
                              floor, as runs 4-7); BS2_S = D102 (its own 9a tuning + 9b holdout box_v2 cells merged per cutoff, then
                              the >= 30 floor; D94); WCXY_WCA1 = None — raw box_v2, no haircut (D97).
  bench_disclosure(bench, h)  D59 cond. 3 / D100 per bench x stream x horizon: the raw box_v2 bias the haircut corrects, the factor,
                              the DISCLOSED bias (D100 = the record variant's tuning bias, pooled across cutoffs) and the holdout bias
                              (9b, pooled), plus the D69 radius-class package range (tuning, pooled; spread_by_radius_<bench>.csv).
  radius_ranges_from_views    builds that range table from the 9a tuning views (record variant, oil, packages pooled across cutoffs).
  edge_flags(regions)         D101 workup text for BS2_S south-edge / other-edge locations; WCXY_FLAG = D100's WCXY call-out.

Error convention everywhere: actual / forecast - 1 (negative = the forecast is HIGH).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import production as pr

ACC = Path("docs") / "box" / "acceptance"
STEP9A = Path("docs") / "box" / "step9a-2026-10-16"
STEP9B = Path("docs") / "box" / "step9b-2026-10-17"
STEP9C = Path("docs") / "box" / "step9c-2026-10-17"
SPREAD_WCA = Path("docs") / "box" / "step7a-2026-10-14" / "spread_by_radius.csv"

# 9a / 9b file names per BENCH_SPECS key
_FILES = {"BS2_S": ("cells_tuning_BS2_S.csv", "cells_holdout_BS2_S.csv", "pooled_BS2_S.csv"),
          "WCXY_WCA1": ("cells_tuning_WCXY_WCA1.csv", "cells_holdout_WCXY_WCA1.csv", "pooled_WCXY_WCA1.csv")}

HAIRCUT_METHOD_NONE = "none (D97: WCXY record = raw box_v2; months = the uptime-free analog P50 x lateral)"


def record_variant(bench: str) -> str:
    return str(ac.BENCH_SPECS[bench].get("record", ac.RECORD_V2))


def haircut_for(bench: str, acc: Path = ACC, step9a: Path = STEP9A, step9b: Path = STEP9B) -> dict[str, Any] | None:
    if bench == "WCA":
        cells = pd.concat([pd.read_csv(acc / "cells_tuning_v2.csv"), pd.read_csv(acc / "cells_holdout_v2.csv")], ignore_index=True)
        return pr.haircut_table(cells)
    if record_variant(bench) == "box_v2":
        return None  # D97
    tun, hol, _ = _FILES[bench]
    cells = pd.concat([pd.read_csv(step9a / tun), pd.read_csv(step9b / hol)], ignore_index=True)
    return pr.haircut_table(pr.merge_cells_by_cutoff(cells[cells["variant"] == "box_v2"]))


def _weighted(cells: pd.DataFrame, variant: str, s: str, k: int) -> tuple[float | None, int]:
    x = cells[(cells["variant"] == variant) & (cells["stream"] == s) & (cells["horizon"] == k) & (cells["n_packages"] > 0)
              & np.isfinite(cells["pkg_bias"].astype(float))]
    w = x["n_packages"].to_numpy(float)
    return (float(np.sum(w * x["pkg_bias"].to_numpy(float)) / w.sum()) if w.sum() else None), int(w.sum())


def bench_disclosure(bench: str, hcut: Mapping[str, Any] | None, step9a: Path = STEP9A, step9b: Path = STEP9B,
                     step9c: Path = STEP9C) -> dict[str, Any]:
    """Disclosure for a 9c bench (WCA keeps the runs-4-7 disclosure built by scripts.box_pud_run.disclosure)."""
    tun, _, pooled = _FILES[bench]
    tc = pd.read_csv(step9a / tun)
    po = pd.read_csv(step9b / pooled).set_index(["stream", "horizon"])
    rec = record_variant(bench)
    bias: dict[str, Any] = {}
    for s in pr.STREAMS:
        bias[s] = {}
        for k in pr.HORIZONS:
            raw_b, raw_n = (hcut[s][k]["bias"], hcut[s][k]["n_packages"]) if hcut else _weighted(tc, "box_v2", s, k)
            judged = (s, k) in po.index
            dis_b, dis_n = _weighted(tc, rec, s, k)
            bias[s][str(k)] = {
                "record_variant": rec,
                "box_v2_pooled_bias": raw_b, "box_v2_pooled_packages": raw_n,
                "haircut_factor": hcut[s][k]["factor"] if hcut else 1.0,
                # D100: disclosed bias = the tuning bias per cell (D99 pooled cell where 9b judged it)
                "disclosed_bias": float(po.loc[(s, k), "tuning_bias"]) if judged else dis_b,
                "disclosed_packages": dis_n, "d99_judged": judged,
                "holdout_bias": float(po.loc[(s, k), "holdout_bias"]) if judged else None,
                "holdout_packages": int(po.loc[(s, k), "packages"]) if judged else None,
                "d99_interval": [float(po.loc[(s, k), "interval_lo"]), float(po.loc[(s, k), "interval_hi"])] if judged else None,
            }
    rr = pd.read_csv(step9c / f"spread_by_radius_{bench}.csv")
    ranges = {f"{r.radius_class}|cum-{int(r.horizon)}": {"p90_low": float(r.box_p90_low), "p10_high": float(r.box_p10_high), "packages": int(r.packages),
                                                          "bias": float(r.box_bias)} for r in rr.itertuples()}
    return {"hindcast_bias": bias, "radius_ranges": ranges, "error_convention": "actual / forecast - 1 (negative = forecast HIGH)",
            "radius_ranges_basis": f"{rec} oil package errors, 9a TUNING packages pooled across cutoffs (D100: disclosed = tuning)",
            "source": f"{step9a / tun}, {step9b / pooled}, {step9c / f'spread_by_radius_{bench}.csv'}"}


def radius_ranges_from_views(views: Mapping[str, pd.DataFrame], variant: str, horizons: Sequence[int] = (12, 24), stream: str = "oil") -> pd.DataFrame:
    """D69 range per analog-radius class: package errors of `variant` (sum actual / sum predicted - 1) pooled over every cutoff's
    tuning view; a package's class = its members' widest v2 radius (> 5 mi = past 5 mi), as step 7a. P90 low / P10 high = the
    10th / 90th percentile package error."""
    rows = []
    for k in horizons:
        pk = []
        for _, v in sorted(views.items()):
            a, p = f"actual_{stream}{k}", f"pred_{variant}_{stream}{k}"
            if a not in v or p not in v:
                continue
            e = ac.package_errors(v, "package", a, p)
            r = v.groupby("package")["v2_radius_mi"].max()
            pk.append(e.assign(radius_class=np.where(e["package"].map(r) > pr.RING_MI, "past 5 mi", "5 mi ring")))
        if not pk:
            continue
        x = pd.concat(pk, ignore_index=True)
        for rc, g in x.groupby("radius_class"):
            rows.append({"horizon": k, "radius_class": rc, "packages": len(g), "box_bias": float(g["err"].mean()),
                         "box_p90_low": float(np.percentile(g["err"], 10)), "box_p10_high": float(np.percentile(g["err"], 90))})
    return pd.DataFrame(rows)


# D101 (Michael 2026-10-17, gate 9b): workup text only, no spec change (D96 stands). Numbers = FINDINGS 9a / 9b.
D101_SOUTH = ("D101 BS2_S south edge (<= 5 mi of the extent-7 boundary, bearing 135-225 deg): box_v2_wf over-forecast measured here, "
              "oil cum-12 -26 % tuning (29 packages) / -31 % holdout (9); local-offsets benchmark -19 / -29 %")
D101_OTHER = ("D101 BS2_S other-edge WATCH ITEM (<= 5 mi of the extent-7 boundary): mirror-image under-forecast measured, "
              "oil cum-12 +13 % tuning (108 packages) / +20 % holdout (25), cum-24 +19 / +32 %")
WCXY_FLAG = ("D100 WCXY: raw box_v2 on WCXY + WCA_1 analogs (D93 / D97, no haircut); disclosed tuning bias oil cum-36 -9.2 % "
             "(forecast high; the one reported spread miss)")


def edge_flags(regions: Sequence[str]) -> list[list[str]]:
    return [[D101_SOUTH] if r == "south_edge" else [D101_OTHER] if r == "other_edge" else [] for r in regions]
