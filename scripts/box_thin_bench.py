"""BOX step 14 — thin-bench D2 evidence table (READ ONLY; decision only, nothing stored).

    python -m scripts.box_thin_bench [--out docs/box/step14-2026-10-17] [--actuals-through 2026-07-01]

Per Delaware bench: modern producers vs in-extent drillable PUDs (record run's box.pud_forecast rows), nearest-analog distance
spread, and the D52 tuning / holdout PACKAGE COUNTS per cutoff x horizon with what they allow under D53 / D57 / D99 / D102
(box/thin_bench). BS2_S is the calibration row: its tuning counts must reproduce step 9a's cells_tuning_BS2_S.csv.
Only counts are computed for holdout packages — no forecast, no error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely

from box import acceptance as acc
from box import dev_factor_report as dfr
from box import edge_gap_report as egr
from box import exclusions
from box import hindcast_production as hp
from box import holdout as ho
from box import spacing3d as s3
from box import spacing3d_report as s3r
from box import tc_area_report as tar
from box import tc_curve_report as rep
from box import thin_bench as tb
from etl.db import get_connection

# bench -> (wells dir, extent bench of record or None). BS2_S = calibration vs step 9a.
BENCHES: dict[str, tuple[str, str | None]] = {
    "BS2_S": ("docs/box/pool-2026-10-15", "BS2_S"),
    "BS3_S": ("docs/box/step15a-2026-10-16", "BS3_S"),
    "BS3_C": ("docs/box/step15a-2026-10-16", "BS3_C"),
    "WCB_1": ("docs/box/step15-WCB-2026-10-16", "WCB_1"),
    "WCB_2": ("docs/box/step15-WCB-2026-10-16", "WCB_2"),
    "BS1_S": ("docs/box/step15-BS1-2026-10-16", "BS1_S"),
    "WCC": ("docs/box/step15-WCC-2026-10-16", "WCC"),
    "BS2_C": ("docs/box/step15-BS2C-2026-10-16", "BS2_C"),
    "AVA_0": ("docs/box/step15-AVA-2026-10-16", "AVA_0"),
    "AVA_1": ("docs/box/step15-AVA-2026-10-16", "AVA_1"),
    "AVA_2": ("docs/box/step15-AVA-2026-10-16", "AVA_2"),
    "WCD": ("docs/box/step15-WCD-2026-10-16", None),  # D2 emerging since the step-15 QC gate: no extent
}
STEP14 = ("BS2_C", "AVA_0", "AVA_1", "AVA_2", "WCD")
AVA_POOLED = "AVA (0+1+2 pooled, sensitivity)"

_PUD_SQL = """
SELECT f.bench, f.location_id, f.inside_extent,
       extensions.ST_X(extensions.ST_Centroid(l.geom)), extensions.ST_Y(extensions.ST_Centroid(l.geom))
FROM box.pud_forecast f
JOIN box.forecast_run r USING (run_id)
JOIN box.location l USING (location_id)
WHERE r.is_record AND r.basin = 'delaware' AND f.basin = 'delaware' AND f.bench = ANY(%(b)s)
"""


def _sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def _pairs_within(u: pd.DataFrame, ids: list[str]) -> dict[str, list[s3.Pair]]:
    """s3r.build_pairs restricted to `ids` as both subject and neighbour — the only pairs acceptance.packages() reads
    (it keeps p.nbr in the scored set, which is always same-bench)."""
    v = u[u["api10"].isin(set(ids))].reset_index(drop=True)
    lines = list(v["geom"])
    tree = shapely.STRtree(lines)
    out: dict[str, list[s3.Pair]] = {}
    for i in range(len(v)):
        a, g, tvd, fp = v.at[i, "api10"], lines[i], float(v.at[i, "tvd_ft"]), v.at[i, "fp"]
        ps = []
        for j in tree.query(g, predicate="dwithin", distance=s3.GATE):
            if j == i:
                continue
            p = s3.pair_geometry(g, lines[j], tvd, float(v.at[j, "tvd_ft"]), (v.at[j, "fp"] - fp).days, v.at[j, "api10"], s3.MIN_OVERLAP)
            if p is not None:
                ps.append(p)
        out[a] = ps
    return out


def _add_months(d: dt.date, n: int) -> dt.date:
    m = d.month - 1 + n
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def bench_counts(conn: Any, wells: pd.DataFrame, geom_ft: Any | None, u: pd.DataFrame, last: dt.date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per cutoff x horizon tuning / holdout package counts (acceptance.run's fold, counts only) + the per-well frame."""
    subj = wells[np.array([f >= dt.date(2016, 1, 1) for f in wells["first_production_date"]])
                 & (pd.to_numeric(wells["lateral_length_ft"], errors="coerce") > 0).to_numpy()].reset_index(drop=True)
    pairs = _pairs_within(u, list(subj["api10"]))
    rows, frames = [], []
    for c in acc.CUTOFFS:
        end = _add_months(c, 12)
        hw = wells[[c <= f < end for f in wells["first_production_date"]]].copy()
        hx, hy = dfr._xy(hw["mid_lon"], hw["mid_lat"])
        inside = rep.assign_area(np.column_stack([hx, hy]), [geom_ft]) > 0 if geom_ft is not None else np.ones(len(hw), bool)
        hw["lateral_ft"] = pd.to_numeric(hw["lateral_length_ft"], errors="coerce")
        hs = hw[inside & (hw["lateral_ft"] > 0).to_numpy()].reset_index(drop=True)
        if hs.empty:
            for k in acc.HORIZONS:
                rows.append({"cutoff": str(c), "horizon": k, "n_tuning": 0, "n_holdout": 0, "n_wells_tuning": 0, "n_wells_holdout": 0, "n_scored_wells": 0})
            continue
        hs["holdout_block"] = ho.is_holdout(*dfr._xy(hs["mid_lon"], hs["mid_lat"]))
        hs["package"] = hs["api10"].map(acc.packages(list(hs["api10"]), pairs))
        held = set(hs.loc[hs["holdout_block"], "package"])
        hs["held_out"] = hs["package"].isin(held)
        prod = rep.pull_production(conn, list(hs["api10"]), last)
        act = hp.monthly_matrix(prod, list(hs["api10"]), drop_latest=True, k=acc.K_MONTHS)
        for k in acc.HORIZONS:
            hs[f"reached_{k}"] = np.isfinite(np.cumsum(act["oil"], axis=1)[:, k - 1])
        pc = tb.package_counts(hs, acc.HORIZONS)
        pc["cutoff"], pc["n_scored_wells"] = str(c), len(hs)
        for col in ("n_tuning", "n_holdout", "n_wells_tuning", "n_wells_holdout"):
            pc.loc[[(str(c), int(h)) in tb.UNSCORED_EARLY for h in pc["horizon"]], col] = 0
        rows.extend(pc.to_dict("records"))
        frames.append(hs[["api10", "package", "holdout_block", "held_out", *[f"reached_{k}" for k in acc.HORIZONS]]].assign(cutoff=str(c)))
    counts = pd.DataFrame(rows)[["cutoff", "horizon", "n_tuning", "n_holdout", "n_wells_tuning", "n_wells_holdout", "n_scored_wells"]]
    return counts, (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())


def _fmt_mi(d: dict[str, float] | None) -> str:
    return "–" if not d else f"{d['p10']:.1f} / {d['p50']:.1f} / {d['p90']:.1f}"


def render(out: Path) -> str:
    """DB-free review page from the written package_counts.csv / judgeability.csv / summary.json."""
    from box.edge_gap_report import _CSS, _table

    counts = pd.read_csv(out / "package_counts.csv")
    judge = pd.read_csv(out / "judgeability.csv")
    s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    meta, benches = s["meta"], s["benches"]
    ev = []
    for b, v in benches.items():
        j = judge[judge.bench == b].set_index("horizon")
        r = v["ring10"] or {}
        ev.append({"bench": b, "step 14": "yes" if b in meta["step14_benches"] or b.startswith("AVA (") else "",
                   "extent sq mi": v["extent_sqmi"] if v["extent_sqmi"] is not None else float("nan"),
                   "modern producers in extent": v["modern_in_extent"], "drillable PUDs in extent": v["puds_in_extent"],
                   "PUDs per producer": v["puds_per_modern_in_extent"],
                   "fp 2016-19 / 20-22 / 23+": f"{v['vintage']['2016-19']} / {v['vintage']['2020-22']} / {v['vintage']['2023+']}",
                   "nearest producer mi P10/P50/P90": _fmt_mi(v["d1_mi"]), "10th nearest mi P10/P50/P90": _fmt_mi(v["d10_mi"]),
                   "10th within 5 mi": r.get("<=5", float("nan")), "past 10 mi": sum(r.get(k, 0.0) for k in ("<=15", "<=20", ">20 (cap)")),
                   "tuning pkgs cum-12 (pooled)": int(j.loc[12, "pooled_tuning"]), "holdout pkgs cum-12 / 24 (raw pooled)":
                   f"{int(j.loc[12, 'pooled_holdout_raw'])} / {int(j.loc[24, 'pooled_holdout_raw'])}",
                   "holdout pkgs cum-12 / 24 (wf cutoffs)": f"{int(j.loc[12, 'pooled_holdout_wf'])} / {int(j.loc[24, 'pooled_holdout_wf'])}",
                   "can be judged": v["verdict"]})
    ev = pd.DataFrame(ev)
    parts = [(f"<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>BOX step 14</title><style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>"),
             "<h1>BOX step 14 — thin-bench D2 evidence (decision only)</h1>",
             (f"<div class=meta>built {meta['built_at']} · code {meta['code_sha']} · actuals through {meta['actuals_through']} · "
             f"D52 salt {meta['holdout_salt']} ({meta['holdout_share']:.0%} of 3-mi blocks) · read-only, nothing stored · "
             "PUDs = record run's box.pud_forecast rows inside the extent of record · see FINDINGS.md for the asks</div>"),
             "<h2>1. Evidence table</h2>",
             ("<p>Producers = the step-15 QC set (gate-1 rule + class verdicts), first production ≥ 2016, real lateral. Analog reach = "
             "distance from each in-extent PUD's midpoint to the 1st and 10th nearest same-bench producer with ≥ 6 months (deal-intake "
             "min_wells 10; circle only, so a lower bound on the real D55 search). Packages = acceptance.run's development packages of "
             "the next-12-months wells per cutoff (2019–2024), counts only. 'raw pooled' = every cutoff (a raw box_v2 record, D97 "
             "pattern); 'wf cutoffs' = only cutoffs with ≥ 2 earlier judged tuning cells (a box_v2_wf record). D99 judges a pooled "
             "cell when it reaches ~30 packages (the pre-9b rehearsal's floor). BS2_S is the calibration row (accepted at gate 9b).</p>"),
             _table(ev, {"extent sq mi": ",.0f", "PUDs per producer": ".1f", "10th within 5 mi": ".0%", "past 10 mi": ".0%"}),
             "<h2>2. Judgeability per horizon</h2>",
             ("<p>d53_cells = per-cutoff tuning cells ≥ 30 packages; wf_cutoffs = cutoffs with a walk-forward haircut (D57); "
             "d102_cutoffs = cutoffs whose tuning + holdout merge reaches 30 (production haircut inputs, D102).</p>"),
             _table(judge[["bench", *[c for c in judge.columns if c != "bench"]]]),
             "<h2>3. Package counts per cutoff (tuning / holdout)</h2>",
             ("<p>2019 cum-36/48 and 2020 cum-48 are zeroed: the analog fold cannot score them on a thin 2016 base "
             "(observed on BS2_S in step 9a).</p>")]
    for b in counts.bench.unique():
        x = counts[counts.bench == b]
        t = (x.pivot(index="cutoff", columns="horizon", values="n_tuning").astype(int).astype(str) + " / "
             + x.pivot(index="cutoff", columns="horizon", values="n_holdout").astype(int).astype(str))
        t.columns = [f"cum-{c}" for c in t.columns]
        parts.append(f"<h3>{b}</h3>" + _table(t.reset_index()))
    parts.append("</body></html>")
    page = "\n".join(parts)
    (out / "index.html").write_text(page, encoding="utf-8")
    return page


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("docs/box/step14-2026-10-17"))
    ap.add_argument("--actuals-through", type=dt.date.fromisoformat, default=None,
                    help="cap the last full month (2026-07-01 reproduces step 9a's BS2_S counts)")
    ap.add_argument("--render", action="store_true", help="only re-render index.html from the written files (DB-free)")
    a = ap.parse_args(argv)
    if a.render:
        render(a.out)
        return 0
    a.out.mkdir(parents=True, exist_ok=True)
    sha = _sha()
    with get_connection() as conn:
        live_last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
        last = min(live_last, a.actuals_through) if a.actuals_through else live_last
        wells_by: dict[str, pd.DataFrame] = {}
        for b, (d, _) in BENCHES.items():
            w, _ = exclusions.drop(egr.load_final_sets(Path(d), (b,)))
            wells_by[b] = w
        allw = pd.concat(wells_by.values(), ignore_index=True)
        modern = allw[np.array([f >= dt.date(2016, 1, 1) for f in allw["first_production_date"]])]
        u = s3r.pull_universe(conn, modern)
        ext = {b: tar.pull_extent(conn, e) for b, (_, e) in BENCHES.items() if e}
        pud = pd.DataFrame(rep._read(conn, _PUD_SQL, {"b": list(BENCHES)}), columns=["bench", "location_id", "inside_extent", "lon", "lat"])
        conn.rollback()
        pud["x"], pud["y"] = dfr._xy(pud["lon"], pud["lat"])

        groups: dict[str, list[str]] = {b: [b] for b in BENCHES}
        groups[AVA_POOLED] = ["AVA_0", "AVA_1", "AVA_2"]
        counts_all, judge_all, summary = [], [], {}
        six_mo = _add_months(last, -5)
        for g, members in groups.items():
            w = pd.concat([wells_by[b] for b in members], ignore_index=True)
            geom = shapely.union_all([ext[b]["geom_ft"] for b in members]) if all(b in ext for b in members) else None
            counts, _ = bench_counts(conn, w, geom, u, last)
            j = tb.judgeability(counts)
            counts_all.append(counts.assign(bench=g))
            judge_all.append(j.assign(bench=g))
            # producers / PUDs / analog reach
            fp = np.array([f >= dt.date(2016, 1, 1) for f in w["first_production_date"]])
            m = w[fp & (pd.to_numeric(w["lateral_length_ft"], errors="coerce") > 0).to_numpy()]
            mx, my = dfr._xy(m["mid_lon"], m["mid_lat"])
            m_in = int((rep.assign_area(np.column_stack([mx, my]), [geom]) > 0).sum()) if geom is not None else len(m)
            pool = m[np.array([f <= six_mo for f in m["first_production_date"]])]
            px, py = dfr._xy(pool["mid_lon"], pool["mid_lat"])
            p = pud[pud["bench"].isin(members)]
            p_in = p[p["inside_extent"].fillna(True).astype(bool)] if geom is not None else p
            d1, d10 = tb.knn_distances_mi(p_in[["x", "y"]].to_numpy(float), np.column_stack([px, py]))
            yrs = pd.Series([f.year for f in m["first_production_date"]])
            summary[g] = {
                "members": members, "extent_ids": [ext[b]["extent_id"] for b in members if b in ext],
                "extent_sqmi": float(sum(ext[b]["area_sqmi"] for b in members if b in ext)) if geom is not None else None,
                "set_wells": len(w), "modern_producers": len(m), "modern_in_extent": m_in, "analog_pool_6mo": len(pool),
                "vintage": {"2016-19": int(((yrs >= 2016) & (yrs <= 2019)).sum()), "2020-22": int(((yrs >= 2020) & (yrs <= 2022)).sum()),
                            "2023+": int((yrs >= 2023).sum())},
                "puds_total": len(p), "puds_in_extent": len(p_in),
                "puds_per_modern_in_extent": len(p_in) / m_in if m_in else None,
                "d1_mi": dict(zip(("p10", "p50", "p90"), np.nanpercentile(d1, [10, 50, 90]).tolist(), strict=True)) if len(d1) else None,
                "d10_mi": dict(zip(("p10", "p50", "p90"), np.nanpercentile(d10, [10, 50, 90]).tolist(), strict=True)) if len(d10) else None,
                "ring10": tb.ring_shares(d10) if len(d10) else None,
                "verdict": tb.verdict_class(j),
            }
            print(g, summary[g]["modern_in_extent"], summary[g]["puds_in_extent"], summary[g]["verdict"], flush=True)

    counts = pd.concat(counts_all, ignore_index=True)
    judge = pd.concat(judge_all, ignore_index=True)
    counts.to_csv(a.out / "package_counts.csv", index=False)
    judge.to_csv(a.out / "judgeability.csv", index=False)
    meta = {"built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "code_sha": sha,
            "actuals_through": str(last), "live_last_full_month": str(live_last), "holdout_salt": ho.SALT, "holdout_share": ho.SHARE,
            "min_packages": tb.MIN_PACKAGES, "rings_mi": list(tb.RINGS_MI), "min_wells": tb.MIN_WELLS, "step14_benches": list(STEP14)}
    (a.out / "summary.json").write_text(json.dumps({"meta": meta, "benches": summary}, indent=1, default=str), encoding="utf-8")
    render(a.out)
    print(json.dumps(meta, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
