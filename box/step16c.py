"""BOX step 16c — scoring the pre-registered step-16 variants (docs/box/step16b-2026-10-22/PREREGISTRATION.md, frozen 109f805).

Written AFTER the freeze, checked against the pre-registration as written (its §8 says so):
  hindcast_fold / hindcast_rows  §6 level-only hindcast: pool wells 3-5 calendar months after their oil peak at a tuning
                                 cutoff, own qi + the median Di / b of the >= 9-month long wells in their own box_v2s_r2
                                 cohort (box.analog.members_with_transfer, unchanged), next 12 months of oil vs actual
  off_local_rows                 §5 input 3: production PUDs of run 10, far-with-local set fixed by the BASE selection (as §5
                                 fixes the stratum), share whose cohort year-1 is > 25 % from its local wells', per variant
  pooled_cells / keep_validated  §4 / §5: the D99-form pooled tuning cells (box.tune15_report.pooled on
                                 box.rehearse9b.package_table, unchanged) and the validated keep-rule
  provisional_inputs             §5 / §6b: the stratum, the Cui-vs-linear checks and the cells adopt() reads
Read-only against the warehouse.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from boxfit.ramp_arps import model_cum_at_t
from scipy.spatial import cKDTree

from box import acceptance as ac
from box import analog as an
from box import backtest_report as br
from box import hindcast_production as hp
from box import hindcast_report as hr
from box import rehearse9b as r9
from box import step16 as s16
from box import tc_area_report as tar
from box import tc_curve_report as rep
from box import tune15_report as t15

PROVISIONAL: tuple[str, ...] = ("AVA_0", "AVA_1", "AVA_2", "BS2_C", "BS3_S", "BS3_C", "WCB_2", "BS1_S")
VALIDATED: tuple[str, ...] = ("WCA", "BS2_S", "WCXY_WCA1", "WCB_1", "WCC")
# §4: each validated group's new base and its record variant, and the cell form it was accepted on
VALIDATED_FORM: dict[str, tuple[str, str, str]] = {"WCA": ("box_v2s_wf", "box_v2_wf", "per_cutoff"),
                                                    "BS2_S": ("box_v2s_wf", "box_v2_wf", "pooled"),
                                                    "WCXY_WCA1": ("box_v2s", "box_v2", "pooled"),
                                                    "WCB_1": ("box_v2s", "box_v2", "pooled"),
                                                    "WCC": ("box_v2s", "box_v2", "pooled")}
HINDCAST_POST_PEAK = (3.0, 5.0)  # §6: 3-5 calendar months after the oil peak (inclusive)
HINDCAST_MONTHS = 12


# ----------------------------------------------------------------------------
# §6 level-only hindcast
# ----------------------------------------------------------------------------


def next_k_oil(p: Mapping[str, Any], months: float, k: int = HINDCAST_MONTHS) -> float:
    """Predicted oil (bbl) over the k calendar months after `months` (counted from the first reported month, as pool months
    are): the model's cum from its onset month, Cum((m + k - onset) / 12) - Cum((m - onset) / 12)."""
    onset = float(p.get("onset_index_months") or 0)
    t0, t1 = (float(months) - onset) / 12.0, (float(months) + k - onset) / 12.0

    qo, pim = p.get("qo"), p.get("peak_index_months")  # absent = a fit with no ramp (boxfit.tc.align.forecast_rates passes None)

    def cum(t: float) -> float:
        return float(model_cum_at_t(qo=None if qo is None else float(qo), peak_index_months=None if pim is None else int(pim),
                                    qi=float(p["qi"]), Di=float(p["Di"]), b=float(p["b"]), Df=float(p["Df"]), t_years=max(t, 0.0)))

    return cum(t1) - cum(t0)


def hindcast_subjects(pool: Mapping[str, Any]) -> list[int]:
    """Pool wells 3-5 calendar months after their oil peak (an oil fit is a pool requirement)."""
    lo, hi = HINDCAST_POST_PEAK
    out = []
    for i, a in enumerate(pool["api10"]):
        pp = an._post_peak(pool["params"][a]["oil"], float(pool["months"][i]))
        if lo <= pp <= hi:
            out.append(i)
    return out


def hindcast_rows(pool: Mapping[str, Any], tree: Any, cfg: Any, bench: str, subjects: Sequence[int],
                  actual_next: Mapping[str, float]) -> list[dict[str, Any]]:
    """One row per subject with >= 1 long-well donor in its own box_v2s_r2 cohort (as-of its first production, itself left
    out): the transferred prediction of the next 12 months and the actual (None when not yet known)."""
    rules = s16.VARIANTS["box_v2s_r2"][1]
    rows = []
    for i in subjects:
        a = pool["api10"][i]
        sp = pool["spacing"][i]
        loc = {"api10": a, "x": float(pool["x"][i]), "y": float(pool["y"][i]), "lateral_ft": float(pool["lateral"][i]),
               "lateral_eff": float(pool["lateral"][i]), "spacing_ft": None if not np.isfinite(sp) else float(sp), "fp_max": pool["fp"][i]}
        idx, r, _, _ = an.select_cohort_v2(pool, tree, cfg, loc, bench=bench, rules=rules)
        donors = [j for j in idx if an._post_peak(pool["params"][pool["api10"][j]]["oil"], float(pool["months"][j])) >= an.TRANSFER_MONTHS]
        row: dict[str, Any] = {"api10": a, "months": float(pool["months"][i]), "radius_mi": r, "n_cohort": len(idx), "n_donors": len(donors),
                               "post_peak": an._post_peak(pool["params"][a]["oil"], float(pool["months"][i]))}
        if donors:
            m = an.members_with_transfer(pool, [*idx, i])[-1]  # the subject's member: own qi, the cohort's long-well Di / b
            row.update({"pred_next12": next_k_oil(m.params["oil"], float(pool["months"][i])),
                        "own_next12": next_k_oil(pool["params"][a]["oil"], float(pool["months"][i])),
                        "actual_next12": actual_next.get(a)})
        rows.append(row)
    return rows


def hindcast_fold(conn: Any, group: str, wells_dir: Path, cutoff: dt.date, last: dt.date, workers: int) -> pd.DataFrame:
    """The fold's pool exactly as backtest_report.run_fold_analog builds it (cohort frame -> per-well fits at the cutoff ->
    analog.build_pool), with MEASURED spacing for every pool well (D119) and completed laterals (D56); then hindcast_rows."""
    from dealintake import config as di_config

    spec = ac.BENCH_SPECS[group]
    wells, _, _ = ac.bench_wells(wells_dir, group)
    ext = tar.pull_extent(conn, spec["extent"])
    asof = br._prev_month(cutoff)
    d4 = hr.cohort_frame(wells, ext["geom_ft"], asof)
    cb = hr.rebuild_curves(conn, wells, {"geoms": [ext["geom_ft"]], "frame": d4}, cutoff, asof, workers, area_curves=False)
    ids = sorted({str(a) for a in cb["frame"]["api10"]})
    pool = an.build_pool(cb["frame"], cb["fits"], br.spacing(conn, ids), {})
    ut = an.uturn_leg_spacing(conn, sorted({str(a) for a in pool["api10"]}))
    tvd = dict(zip(cb["frame"]["api10"], pd.to_numeric(cb["frame"]["tvd_ft"], errors="coerce"), strict=True))
    pool2 = an.with_completed_laterals(pool, ut, tvd)
    subj = hindcast_subjects(pool2)
    sid = [str(pool2["api10"][i]) for i in subj]
    actual: dict[str, float] = {}
    if sid:
        k = int(max(pool2["months"][i] for i in subj)) + HINDCAST_MONTHS
        h = hp.monthly_matrix(rep.pull_production(conn, sid, last), sid, drop_latest=True, k=k)
        for j, i in enumerate(subj):
            m = int(pool2["months"][i])
            v = h["oil"][j, m:m + HINDCAST_MONTHS]
            if len(v) == HINDCAST_MONTHS and np.isfinite(v).all():
                actual[sid[j]] = float(v.sum())
    tree = cKDTree(np.column_stack([pool2["x"], pool2["y"]]))
    rows = hindcast_rows(pool2, tree, di_config.load(), spec["label"], subj, actual)
    return pd.DataFrame(rows).assign(group=group, cutoff=str(cutoff))


def hindcast_bias(h: pd.DataFrame, pred: str = "pred_next12") -> tuple[float, int]:
    """Σ actual / Σ predicted − 1 over the subjects with both (the §6 pooled bias)."""
    if h.empty or pred not in h:
        return float("nan"), 0
    ok = h["actual_next12"].notna() & h[pred].notna() & (h[pred] > 0)
    return (float(h.loc[ok, "actual_next12"].sum() / h.loc[ok, pred].sum() - 1.0) if ok.any() else float("nan")), int(ok.sum())


# ----------------------------------------------------------------------------
# §5 off-local share on run 10's production PUDs
# ----------------------------------------------------------------------------


def off_local_rows(pool2: Mapping[str, Any], pool_m: Mapping[str, Any], locs: Sequence[Mapping[str, Any]], cfg: Any, bench: str,
                   variants: Sequence[str]) -> pd.DataFrame:
    """Per PUD: local evidence (step16.local_evidence on the production pool) and, per variant, the radius reached and the
    cohort's mean year-1 oil per 1,000 ft (pool oil12_kft, >= 3 known) on the measured-spacing pool."""
    tree = cKDTree(np.column_stack([pool2["x"], pool2["y"]]))
    rows = []
    for lo in locs:
        loc = {**lo, "lateral_ft": lo["lateral_eff"]}
        n_loc, y1_loc = s16.local_evidence(pool2, tree, float(lo["x"]), float(lo["y"]))
        r: dict[str, Any] = {"stick_id": int(lo["stick_id"]), "n_local": n_loc, "local_y1_kft": y1_loc}
        for v in variants:
            idx, rad, _, _ = an.select_cohort_v2(pool_m, tree, cfg, loc, bench=bench, rules=s16.VARIANTS[v][1])
            y = [float(pool_m["oil12_kft"][i]) for i in idx if np.isfinite(pool_m["oil12_kft"][i]) and pool_m["oil12_kft"][i] > 0]
            r[f"{v}_radius_mi"], r[f"{v}_cohort_y1_kft"] = rad, (float(np.mean(y)) if len(y) >= 3 else np.nan)
        rows.append(r)
    return pd.DataFrame(rows)


def off_local_share(d: pd.DataFrame, variants: Sequence[str]) -> pd.DataFrame:
    """Among the far-with-local PUDs fixed by the BASE selection, the share per variant whose cohort year-1 is > OFF_LOCAL from
    its local wells' (a PUD without a cohort year-1 under a variant counts as off: it has no evidence to be on)."""
    fw = s16.far_with_local(d[f"{s16.BASE}_radius_mi"], d["n_local"])
    x = d[fw]
    rows = []
    for v in variants:
        gap = x[f"{v}_cohort_y1_kft"] / x["local_y1_kft"] - 1.0
        off = ~(gap.abs() <= s16.OFF_LOCAL)
        rows.append({"variant": v, "n_far_with_local": len(x), "share_off": float(off.mean()) if len(x) else np.nan,
                     "median_gap": float(gap.median()) if len(x) else np.nan})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# §4 / §5 cells
# ----------------------------------------------------------------------------


def run_tag(group: str, fold: str = "analog") -> str:
    return f"tuning_v2_{group}_{fold}" if (group != "WCA" or fold != "full") else "tuning_v2"


def load_views(run_dir: Path, group: str, fold: str = "analog") -> pd.DataFrame:
    return r9.load_frames(run_dir, run_tag(group, fold)).assign(group=group)


def pooled_cells(v: pd.DataFrame, variants: Sequence[str]) -> pd.DataFrame:
    """D99-form pooled tuning cells (every package across the cutoffs) per variant — tune15_report.pooled, unchanged."""
    out = []
    for var in variants:
        if not any(c.startswith(f"pred_{var}_") for c in v.columns):
            continue
        out.append(t15.pooled(r9.package_table(v, var)).assign(variant=var))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def judged(cells: pd.DataFrame) -> pd.DataFrame:
    return cells[cells["verdict"].isin(["PASS", "FAIL"])]


def keep_validated(new: pd.DataFrame, record: pd.DataFrame) -> dict[str, Any]:
    """§4 on one group's cells (same form for both): stays validated when every judged cell of the new base has |pkg bias| <=
    10 % AND it fails no more judged cells than the re-scored record."""
    jn, jr = judged(new), judged(record)
    max_abs = float(jn["pkg_bias"].abs().max()) if len(jn) else float("nan")
    fails_new, fails_rec = int((jn["verdict"] == "FAIL").sum()), int((jr["verdict"] == "FAIL").sum())
    ok = bool(len(jn)) and max_abs <= ac.BIAS_TOL and fails_new <= fails_rec
    return {"judged_new": len(jn), "judged_record": len(jr), "max_abs_bias_new": max_abs, "fails_new": fails_new, "fails_record": fails_rec,
            "keeps_validated": ok}


def stratum_table(views: pd.DataFrame, variants: Sequence[str], k: int = 12) -> pd.DataFrame:
    """§5 input 2: the far-with-local stratum (fixed by the base selection) oil cum-k well-level bias per variant."""
    m = s16.stratum_mask(views)
    rows = []
    for v in variants:
        b, n = s16.stratum_bias(views, v, "oil", k, m)
        rows.append({"variant": v, "bias": b, "n_wells": n})
    return pd.DataFrame(rows)


def cui_table(views: pd.DataFrame, variant: str = "box_v2s_r2", horizons: Sequence[int] = (12, 24, 36)) -> pd.DataFrame:
    rows = [s16.cui_vs_linear(views, variant, s, k) for s in ac.STREAMS for k in horizons
            if f"pred_{variant}_lin_{s}{k}" in views and f"actual_{s}{k}" in views]
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
