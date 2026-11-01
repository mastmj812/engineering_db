"""BOX step 21b — Pad C 233, the named check (box/step21.DEFINITION named_checks.pad_c233; reported, NEVER judged).

Called by `python -m scripts.box_step21b pad`. For the audit's 15 sticks: the production machinery of record, read-only, at the
pre-registered data date (2026-08-01): scripts/box_pud_run.build_pool_analog (the harness pool at a production cutoff; D119
measured spacing) for each sticks' group, scripts/box_pud_run.nearest_by_stick (D64 planned spacing) and box/production
.fit_many under box/step21.RULES on basin 'midland' — uptime-free months, 600 of them. Per stick: BOX oil cum12 / cum24 /
EUR30 / EUR (50-yr) per 1,000 ft (raw mid_r2), the same x the Midland proximity factor where the stick's outcome is a haircut,
EUR30 / cum24, and BOX's own cohort level vs local rock (cohort mean year-1 oil per 1,000 ft / the mean of pool wells within 3
mi, box/step16.local_evidence) for the audit's rock read. Nothing is stored.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import dev_factor_report as dfr
from box import production as pr
from box import step16 as s16
from box import step21 as st
from scripts import box_pud_run as bpr

LAST = dt.date.fromisoformat(st.DEFINITION["folds"]["actuals_through"])
GROUP_OF_BENCH = {b: g for g, (b, _, _) in st.GROUPS.items()}


def run(conn: Any, sticks_midland: pd.DataFrame, workers: int) -> pd.DataFrame:
    from dealintake import config as di_config

    lab = {int(v): k for k, v in st.PAD_C233.items()}
    u = pr.universe(conn, basins=["midland"])
    u["stick_id"] = u["stick_id"].astype(int)
    cand = u[u["stick_id"].isin(lab)].copy()
    if len(cand) != len(lab):
        raise RuntimeError(f"Pad C 233: {len(cand)} of {len(lab)} sticks in the Midland universe")
    near = bpr.nearest_by_stick(conn, u, cand)
    sm = sticks_midland.assign(stick_id=sticks_midland["location_id"].astype(int)).set_index("stick_id")
    x, y = dfr._xy(cand["mid_lon"], cand["mid_lat"])
    cand["x"], cand["y"] = x, y
    cfg = di_config.load()
    rows = []
    for bench, t in cand.groupby("formation_blueox"):
        g = GROUP_OF_BENCH[bench]
        P = bpr.build_pool_analog(conn, workers, st.POOL_DIR, g, measured=True, last=LAST)
        locs = []
        for r in t.itertuples():
            lat = float(r.ll_ft) if np.isfinite(r.ll_ft) and r.ll_ft > 0 else float(r.stick_ft)
            gap = near[int(r.stick_id)]
            locs.append({"api10": f"pud{r.stick_id}", "stick_id": int(r.stick_id), "x": float(r.x), "y": float(r.y), "lateral_ft": lat,
                         "lateral_eff": lat, "spacing_ft": float(gap[0]) if gap is not None else None, "fp_max": None})
        res = pr.fit_many(locs, P["pool"], P["pool2"], cfg, max(1, min(workers, len(locs))), bench=P["label"], rules=st.RULES, basin="midland")
        pool2 = P["pool2"]
        tree = cKDTree(np.column_stack([pool2["x"], pool2["y"]]))
        pidx = {str(a): i for i, a in enumerate(pool2["api10"])}
        for loc, f in zip(locs, res, strict=True):
            sid = loc["stick_id"]
            n_loc, y1_loc = s16.local_evidence(pool2, tree, loc["x"], loc["y"])
            ids = [a["api10"] for a in f.get("analogs", [])]
            y1 = [float(pool2["oil12_kft"][pidx[a]]) for a in ids if a in pidx and np.isfinite(pool2["oil12_kft"][pidx[a]]) and pool2["oil12_kft"][pidx[a]] > 0]
            row: dict[str, Any] = {"label": lab[sid], "stick_id": sid, "group": g, "lateral_ft": loc["lateral_eff"], "planned_spacing_ft": loc["spacing_ft"],
                                   "radius_mi": f.get("radius_mi"), "n_analogs": f.get("n_analogs"), "search_mode": f.get("search_mode"),
                                   "flags": "; ".join(f.get("flags", [])), "n_local_3mi": n_loc, "local_y1_oil_kft": y1_loc,
                                   "cohort_y1_oil_kft": float(np.mean(y1)) if len(y1) >= 3 else np.nan, "pool_asof": str(P["asof"])}
            row["cohort_vs_local"] = row["cohort_y1_oil_kft"] / y1_loc if y1_loc and np.isfinite(y1_loc) else np.nan
            s = sm.loc[sid] if sid in sm.index else None
            row.update({"outcome_interim": s["outcome_interim"] if s is not None else None, "factor_interim": s["factor_interim"] if s is not None else None,
                        "outcome": s["outcome"] if s is not None else None, "factor_midland": s["factor"] if s is not None else None,
                        "key_midland": s["key"] if s is not None else None, "factor_gap_sensitivity": s["factor_gap"] if s is not None else None})
            oil = (f.get("streams") or {}).get("oil")
            if oil is not None:
                m = np.asarray(oil["months_raw"], float)
                c = np.cumsum(m)
                kft = loc["lateral_eff"] / 1000.0
                row.update({"oil_cum12_kft": c[11] / kft, "oil_cum24_kft": c[23] / kft, "oil_eur30_kft": c[359] / kft, "oil_eur50_kft": c[-1] / kft,
                            "eur30_over_cum24": c[359] / c[23], "Di_nominal": oil["params"].get("Di"), "b": oil["params"].get("b"),
                            "Di_effective_1yr": pr.de_eff_1yr(float(oil["params"]["Di"]), float(oil["params"]["b"])) if oil["params"].get("Di") else np.nan})
                fm = float(row["factor_midland"]) if row["outcome"] == "haircut" else (1.0 if str(row["outcome"]).startswith("as_is") else np.nan)
                row.update({"oil_cum12_kft_prox": row["oil_cum12_kft"] * fm, "oil_cum24_kft_prox": row["oil_cum24_kft"] * fm})
            rows.append(row)
        print(f"[pad] {bench}: {len(locs)} sticks forecast on the {g} pool ({len(pool2['api10']):,} wells)", flush=True)
    order = list(st.PAD_C233)
    return pd.DataFrame(rows).assign(_o=lambda d: d["label"].map(order.index)).sort_values("_o").drop(columns="_o").reset_index(drop=True)
