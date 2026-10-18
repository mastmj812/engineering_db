"""BOX step 15 stage 2 page: 9a-style tuning view for the step-15 benches (read-only; tuning blocks only).

    python -m scripts.box_tune15 [--runs runs/box15t] [--out docs/box/step15-tuning-2026-10-17] [--draws 2000]

Reads the `scripts.box_acceptance --bench <B> --fold analog` outputs under --runs/<B>/ (BENCH_SPECS pre-registered at gate 14),
the step-14 judgeability table (holdout COUNTS only) and the extents of record (read-only). Writes index.html + CSV / JSON.
The D99 intervals written here are the frozen ones for the one-time holdout; never redraw them after a look at the holdout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import dev_factor_report as dfr
from box import rehearse9b as r9
from box import tc_area_report as tar
from box import tune9a_report as t9
from box import tune15_report as t15
from box.edge_gap_report import _CSS, _table
from etl.db import get_connection

STEP14 = Path("docs") / "box" / "step14-2026-10-17"


def _sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def _pct(cols: list[str]) -> dict[str, str]:
    return {c: "+.1%" for c in cols if "bias" in c or c.startswith("cum-") or c in ("tuning_bias", "interval_lo", "interval_hi")} | \
           {c: ".2f" for c in cols if "band" in c} | {c: ".0%" for c in cols if "share" in c or c == "pass_rate"} | \
           {c: ".3f" for c in cols if c == "factor"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("runs") / "box15t")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step15-tuning-2026-10-17")
    ap.add_argument("--draws", type=int, default=2000)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    j14 = pd.read_csv(STEP14 / "judgeability.csv")
    c14 = pd.read_csv(STEP14 / "package_counts.csv")
    benches = [b for b in t15.ORDER if (a.runs / b / f"cells_tuning_v2_{b}_analog.csv").exists()]
    with get_connection() as conn:
        ext = {b: tar.pull_extent(conn, b) for b in benches}
        conn.rollback()
    head, sections, d62_all, d92_all, ivl_all = [], [], [], [], []
    for b in benches:
        tag = f"tuning_v2_{b}_analog"
        d = a.runs / b
        var = t15.record_variant(b)
        cells = pd.read_csv(d / f"cells_{tag}.csv")
        summ = json.loads((d / f"summary_{tag}.json").read_text(encoding="utf-8"))
        v = r9.load_frames(d, tag)
        alt_var = "box_v2" if var == "box_v2_wf" else "box_v2_wf"
        by_var = {}
        for vname in (var, alt_var):
            tv = r9.package_table(v, vname)
            ehv = t15.expected_holdout(cells, vname, c14[c14.bench == b])
            ksv = tuple(int(k) for k in ehv.loc[ehv["d99_cell"], "horizon"])
            cand = [(s_, k) for s_ in ac.STREAMS for k in (12, 24, 36) if "box_a" in tv["sums"].get((s_, k), {}) and np.isfinite(tv["sums"][(s_, k)]["box_a"]).sum() > 0]
            ivlv, _ = r9.consistency(tv, cand, n_draws=a.draws) if cand else (pd.DataFrame(columns=["stream", "horizon", "tuning_bias", "interval_lo", "interval_hi"]), None)
            ivlv["d99_cell"] = ivlv["horizon"].isin(ksv)
            cr = r9.consistency(tv, [(s_, k) for s_ in ac.STREAMS for k in ksv], n_draws=a.draws)[1] if ksv else pd.DataFrame({"scale": [0.85, 0.9, 1.0, 1.1, 1.15], "pass_rate": np.nan})
            by_var[vname] = {"t": tv, "pool": t15.pooled(tv), "eh": ehv, "ks": ksv, "ivl": ivlv, "crate": cr}
            suffix = "" if vname == var else f"_alt_{vname}"
            for frame, name in ((by_var[vname]["pool"], "pooled"), (ehv, "expected_holdout"), (ivlv, "intervals"), (cr, "consistency_rate")):
                frame.to_csv(a.out / f"{name}_{b}{suffix}.csv", index=False)
        pool, eh, ks, ivl, crate = (by_var[var][k] for k in ("pool", "eh", "ks", "ivl", "crate"))
        per = t15.per_cutoff(cells, var)
        alt = by_var[alt_var]
        tab = t9.haircut_table(cells)
        wf = t15.wf_log(summ)
        for frame, name in ((cells, "cells"), (per, "per_cutoff"), (tab, "d62_tuning"), (wf, "walk_forward")):
            frame.to_csv(a.out / f"{name}_{b}.csv", index=False)
        d62_all.append({"bench": b, "record": var, **{f"{r.stream} cum-{r.horizon}": r.factor for r in tab.itertuples()}})
        ivl_all.append(ivl.assign(bench=b, record=var))
        d92 = []
        if var == "box_v2_wf":
            months = t9.load_months(d / f"months_{tag}.npz")
            for s in ac.STREAMS:
                m = np.concatenate([months[y][s] for y in months])
                rr = t9.realised_d92(m, tab, s)
                row = {"bench": b, "stream": s, "locations": rr.get("n", 0)}
                for k, q in (rr.get("realised") or {}).items():
                    row[f"cum-{k}"] = f"{q['p50']:.3f} [{q['p90']:.3f}–{q['p10']:.3f}] (target {rr['target'][k]:.3f})" if q else ""
                for k_ in ("g_month1", "g_month48"):
                    q = rr.get(k_)
                    row[k_] = f"{q['p50']:.3f} [{q['p90']:.3f}–{q['p10']:.3f}]" if q else ""
                d92.append(row)
        d92_all += d92
        vv = v.copy()
        x, y = dfr._xy(vv["mid_lon"], vv["mid_lat"])
        vv = pd.concat([vv.reset_index(drop=True), t15.side_classes(np.asarray(x), np.asarray(y), ext[b]["geom_ft"])], axis=1)
        vv["package"] = vv["cutoff"].astype(str) + ":" + vv["package"].astype(str)
        reg = t15.region_table(vv, var)
        reg.to_csv(a.out / f"edge_regions_{b}.csv", index=False)
        h = t15.bench_findings(per, pool, ivl[ivl["d99_cell"]])
        j = j14[j14.bench == b].set_index("horizon")
        head.append({"bench": b, "record": var, "pool wells": summ["n_pool_wells"], "extent": summ["extent_id"],
                     "per-cutoff judged / fail (bias fails)": f"{h['per_cutoff_judged']} / {h['per_cutoff_fail']} ({h['per_cutoff_bias_fail']})",
                     "pooled judged / fail (bias fails)": f"{h['pooled_judged']} / {h['pooled_fail']} ({h['pooled_bias_fail']})",
                     "pooled oil bias cum-12 / 24 / 36": " / ".join(f"{x_:+.1%}" for x_ in pool[pool.stream == "oil"]["pkg_bias"]),
                     "pooled gas bias cum-12 / 24 / 36": " / ".join(f"{x_:+.1%}" for x_ in pool[pool.stream == "gas"]["pkg_bias"]),
                     "D99 cells": h["d99_cells"],
                     "step-14 holdout pkgs cum-12 / 24": (f"{int(j.loc[12, 'pooled_holdout_wf'])} / {int(j.loc[24, 'pooled_holdout_wf'])}" if var == "box_v2_wf"
                                                          else f"{int(j.loc[12, 'pooled_holdout_raw'])} / {int(j.loc[24, 'pooled_holdout_raw'])}"),
                     "expected scored holdout cum-12 / 24 / 36": " / ".join(f"{x_:.0f}" for x_ in eh["expected_holdout_scored"]),
                     "D99 horizons": ", ".join(f"cum-{k}" for k in ks) or "none",
                     f"ALT {alt_var} pooled oil bias cum-12 / 24 / 36": " / ".join(f"{x_:+.1%}" for x_ in alt["pool"][alt["pool"].stream == "oil"]["pkg_bias"]),
                     f"ALT {alt_var} pooled gas bias cum-12 / 24 / 36": " / ".join(f"{x_:+.1%}" for x_ in alt["pool"][alt["pool"].stream == "gas"]["pkg_bias"]),
                     "ALT pooled judged / fail": f"{int(alt['pool']['verdict'].isin(['PASS', 'FAIL']).sum())} / {int((alt['pool']['verdict'] == 'FAIL').sum())}",
                     "ALT D99 horizons": ", ".join(f"cum-{k}" for k in alt["ks"]) or "none",
                     "consistency rule passes a good forecast": float(crate.loc[np.isclose(crate.scale, 1.0), "pass_rate"].iloc[0]),
                     "catches 15 % high": 1.0 - float(crate.loc[np.isclose(crate.scale, 1.15), "pass_rate"].iloc[0]),
                     "radius past 5 mi share": float(sum(n for r_, n in (summ.get("v2_radius_mi") or {}).items() if float(r_) > 5.0) /
                                                     max(sum((summ.get("v2_radius_mi") or {}).values()), 1)),
                     "strike share": float((summ.get("v2_mode_counts") or {}).get("strike", 0) / max(sum((summ.get("v2_mode_counts") or {}).values()), 1))})
        sections += [f"<h2 id={b}>{b} — {ac.BENCH_SPECS[b]['desc']}</h2>",
                     f"<div class=meta>record variant <b>{var}</b> · {summ['n_pool_wells']:,} pool wells · extent {summ['extent_id']} · "
                     f"{summ['actuals_through']} actuals · engine {summ['engine_sha'][:7]} · folds: "
                     + ", ".join(f"{f['cutoff'][:4]} {f['n_packages']} pkgs ({f['n_packages_held_out']} held out, not scored)" for f in summ["folds"]) + "</div>",
                     "<h3>Pooled tuning cells (record variant; every tuning package across cutoffs)</h3>", _table(pool, _pct(list(pool.columns))),
                     f"<h3>Alternative variant {alt_var}: pooled tuning cells</h3>", _table(alt["pool"], _pct(list(alt["pool"].columns))),
                     "<h3>Per-cutoff D53 cells (record variant)</h3>", _table(per, _pct(list(per.columns))),
                     "<h3>Walk-forward haircut log (box_v2, own tuning cells; D57 / D94)</h3>",
                     _table(wf, _pct(list(wf.columns))) if len(wf) else "<p>no walk-forward haircut at any cutoff</p>",
                     "<h3>D62-style tuning haircut table (package-weighted mean box_v2 bias over judged cells)</h3>", _table(tab, _pct(list(tab.columns))),
                     "<h3>D92 realised factors</h3>",
                     _table(pd.DataFrame(d92)) if d92 else "<p>raw box_v2 record — no haircut is applied (D97 pattern)</p>",
                     f"<h3>Edges (within {t9.EDGE_MI:.0f} mi of the extent boundary, by compass side) — oil, {var}</h3>", _table(reg, _pct(list(reg.columns))),
                     "<h3>Expected scored holdout packages (step-14 counts x the record variant's scored share; no holdout read)</h3>",
                     _table(eh, {"expected_holdout_scored": ".0f"}),
                     "<h3>FROZEN D99 consistency intervals for the one-time holdout (d99_cell = judged under the gate-14 rule)</h3>", _table(ivl, _pct(list(ivl.columns))),
                     "<div class=meta>pass rate of the consistency rule over the same draws, predictions × scale:</div>", _table(crate, _pct(list(crate.columns))),
                     f"<h3>Alternative variant {alt_var}: expected scored holdout + frozen intervals (used only if the gate switches variant)</h3>",
                     _table(alt["eh"], {"expected_holdout_scored": ".0f"}), _table(alt["ivl"], _pct(list(alt["ivl"].columns)))]
        print(b, "done", flush=True)
    hd = pd.DataFrame(head)
    hd.to_csv(a.out / "summary_table.csv", index=False)
    pd.DataFrame(d62_all).to_csv(a.out / "d62_by_bench.csv", index=False)
    pd.DataFrame(d92_all).to_csv(a.out / "d92_realised.csv", index=False)
    pd.concat(ivl_all, ignore_index=True).to_csv(a.out / "intervals_all.csv", index=False)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    meta = {"built_at": built, "code_sha": _sha(), "benches": benches, "draws": a.draws}
    (a.out / "summary.json").write_text(json.dumps({"meta": meta, "rows": head}, indent=1, default=str), encoding="utf-8")
    page = ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX step 15 tuning</title>",
            f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
            "<h1>BOX step 15, stage 2 — tuning view for the remaining Delaware benches (read-only)</h1>",
            (f"<div class=meta>built {built} · code {meta['code_sha']} · frozen spec box_v2_wf / raw box_v2 per the gate-14 pre-registration · "
             "tuning blocks only (D52 salt unchanged); no holdout package was scored · see FINDINGS.md for the decisions asked</div>"),
            "<div class=toc>" + " ".join(f"<a href='#{b}'>{b}</a>" for b in benches) + "</div>",
            "<h2>Summary</h2>", _table(hd, _pct(list(hd.columns))),
            "<h3>D62-style tuning haircut factors by bench (1 + bias; box_v2)</h3>", _table(pd.DataFrame(d62_all), {c: ".3f" for c in pd.DataFrame(d62_all).columns if "cum-" in c}),
            *sections, "</body></html>"]
    (a.out / "index.html").write_text("\n".join(page), encoding="utf-8")
    print(f"wrote {a.out / 'index.html'} ({len(benches)} benches)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
