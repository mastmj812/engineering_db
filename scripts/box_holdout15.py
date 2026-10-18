"""BOX step 15 holdout page: the one-time D52 holdout of the six benches accepted at the step-15 tuning gate, judged under D99.

    python -m scripts.box_holdout15 [--runs runs/box15h] [--tuning-runs <dir with the step-15 tuning runs>] [--out docs/box/step15-holdout-2026-10-18]

Reads the `scripts.box_acceptance --bench <B> --fold analog --score-holdout --holdout-once` outputs under --runs/<B>/, the FROZEN
manifest docs/box/step15-tuning-2026-10-17/frozen_d99.csv (digests re-checked; box/holdout15.load_frozen), the tuning page's
walk-forward / edge / discrimination tables, and read-only warehouse objects (extents of record for the edge view; meta.etl_log
for the run window). --tuning-runs (optional) recomputes the TUNING edge table for the frozen variant from the tuning frames, so
BS3_C / WCB_1 (switched to raw at the gate) compare like with like. Writes index.html + CSV / JSON. Nothing is stored and nothing
is re-scored: every holdout number is read from the frames or computed from them by box/holdout9b / box/holdout15.
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

from box import dev_factor_report as dfr
from box import holdout9b as h9
from box import holdout15 as h
from box import rehearse9b as r9
from box import tc_area_report as tar
from box import tune15_report as t15
from box.edge_gap_report import _CSS, _table
from etl.db import get_connection

ORDER = ("BS3_S", "BS3_C", "WCB_1", "WCB_2", "BS1_S", "WCC")
_ETL_SQL = """SELECT source, table_name, status, run_started_at, run_finished_at FROM meta.etl_log
WHERE run_started_at < %(b)s AND COALESCE(run_finished_at, now()) > %(a)s ORDER BY run_started_at"""


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def _pct(cols: list[str]) -> dict[str, str]:
    return {c: "+.1%" for c in cols if "bias" in c or c in ("tuning_bias", "interval_lo", "interval_hi", "haircut_holdout", "haircut_tuning")} | \
           {c: ".2f" for c in cols if "band" in c} | {c: ".0%" for c in cols if "share" in c} | {"abs_diff": ".1e"}


def _edges(v: pd.DataFrame, ext_ft: object, variant: str, horizons: tuple[int, ...]) -> pd.DataFrame:
    vv = v.copy()
    x, y = dfr._xy(vv["mid_lon"], vv["mid_lat"])
    vv = pd.concat([vv.reset_index(drop=True), t15.side_classes(np.asarray(x), np.asarray(y), ext_ft)], axis=1)
    vv["package"] = vv["cutoff"].astype(str) + ":" + vv["package"].astype(str)
    return t15.region_table(vv, variant, horizons)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("runs") / "box15h")
    ap.add_argument("--tuning-runs", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step15-holdout-2026-10-18")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")

    manifest, integrity = h.load_frozen(h.TUNING)  # raises if a frozen interval moved (D99: never redrawn)
    res: dict[str, dict[str, object]] = {}
    windows = []
    for b in ORDER:
        spec = t15.FROZEN[b]
        var, tag, rd = spec["variant"], f"holdout_v2_{b}_analog", a.runs / b
        summ = json.loads((rd / f"summary_{tag}.json").read_text(encoding="utf-8"))
        if summ["record_variant"] != var or summ["view"] != "HOLDOUT (final scoring)":
            raise SystemExit(f"{b}: summary says record {summ['record_variant']} / view {summ['view']}")
        v = r9.load_frames(rd, tag)
        iv = h.intervals(manifest, b)
        pooled, vd = h.judge(v, var, iv)
        hz = tuple(int(k) for k in spec["horizons"])
        cells_l = [(s, k) for s in ("oil", "gas") for k in hz]
        by_cut = h.packages_by_cutoff(v, var, cells_l)
        cells = pd.read_csv(rd / f"cells_{tag}.csv")
        pc = h9.per_cutoff(cells, var, hz)
        src = str(manifest.loc[manifest.bench == b, "source_file"].iloc[0])
        disc = h.discrimination(h.TUNING, src)
        wf = h.wf_identity(summ.get("walk_forward", []), pd.read_csv(h.TUNING / f"walk_forward_{b}.csv")) if var.endswith("_wf") else None
        res[b] = {"summary": summ, "pooled": pooled, "verdict": vd, "by_cutoff": by_cut, "per_cutoff": pc, "wf": wf, "view": v,
                  "disc": disc, "variant": var, "hz": hz}
        pooled.to_csv(a.out / f"pooled_{b}.csv", index=False)
        by_cut.to_csv(a.out / f"packages_by_cutoff_{b}.csv", index=False)
        pc.to_csv(a.out / f"per_cutoff_{b}.csv", index=False)
        if wf is not None:
            wf.to_csv(a.out / f"walk_forward_identity_{b}.csv", index=False)
        for nm in ("started", "finished"):
            p = a.runs / f"{nm}_{b}.txt"
            windows.append({"bench": b, "event": nm, "utc": p.read_text().strip() if p.exists() else None})

    win = pd.DataFrame(windows)
    t_a, t_b = min(win["utc"].dropna()), max(win["utc"].dropna())
    with get_connection() as conn:
        ext = {b: tar.pull_extent(conn, b) for b in ORDER}
        with conn.cursor() as cur:
            cur.execute(_ETL_SQL, {"a": t_a, "b": t_b})
            etl = pd.DataFrame(cur.fetchall(), columns=["source", "table_name", "status", "run_started_at", "run_finished_at"])
        conn.rollback()
    for b in ORDER:
        r_ = res[b]
        r_["edges"] = _edges(r_["view"], ext[b]["geom_ft"], r_["variant"], r_["hz"])
        r_["edges"].to_csv(a.out / f"edge_regions_{b}.csv", index=False)
        tdir = a.tuning_runs / b if a.tuning_runs else None
        if tdir is not None and (tdir / f"cells_tuning_v2_{b}_analog.csv").exists():
            r_["edges_tuning"] = _edges(r9.load_frames(tdir, f"tuning_v2_{b}_analog"), ext[b]["geom_ft"], r_["variant"], r_["hz"])
            r_["edges_tuning_src"] = f"recomputed from the tuning frames for {r_['variant']}"
        else:
            r_["edges_tuning"] = pd.read_csv(h.TUNING / f"edge_regions_{b}.csv")
            r_["edges_tuning_src"] = f"tuning page edge_regions_{b}.csv (the variant pre-registered at gate 14)"
        r_["edges_tuning"].to_csv(a.out / f"edge_regions_tuning_{b}.csv", index=False)
    etl.to_csv(a.out / "etl_during_runs.csv", index=False)
    integrity.to_csv(a.out / "frozen_d99_check.csv", index=False)
    win.to_csv(a.out / "run_window_utc.csv", index=False)

    out_json = {"built_at": built, "code_sha": _git("rev-parse", "HEAD"),
                "rule": "D99 (pooled across cutoffs; every frozen cell inside its P2.5-P97.5 interval; frozen_d99.csv)",
                "frozen_manifest": (h.TUNING / "frozen_d99.csv").as_posix(), "frozen_check": integrity.to_dict(orient="records"),
                "run_window_utc": windows, "etl_rows_during_runs": len(etl),
                "benches": {b: {"record": r_["variant"], "d99_horizons": list(r_["hz"]), "verdict": r_["verdict"],
                                "cells": r_["pooled"][["stream", "horizon", "packages", "holdout_bias", "interval_lo", "interval_hi", "inside_interval",
                                                       "bias_ok_10pct", "band_scale_free", "bench_band_scale_free", "spread_ok", "bench_bias"]].to_dict(orient="records"),
                                "rule_power_from_tuning": r_["disc"], "engine_sha": r_["summary"]["engine_sha"],
                                "actuals_through": r_["summary"]["actuals_through"], "live_last_full_month": r_["summary"]["live_last_full_month"],
                                "folds": r_["summary"]["folds"], "v2_radius_mi": r_["summary"].get("v2_radius_mi"),
                                "v2_mode_counts": r_["summary"].get("v2_mode_counts"),
                                "walk_forward_identical": (bool(r_["wf"]["identical"].all()) if r_["wf"] is not None else None),
                                "verdict_as_written_d53": r_["summary"]["verdict"]} for b, r_ in res.items()}}
    (a.out / "verdict.json").write_text(json.dumps(out_json, indent=2, default=str), encoding="utf-8")

    s0 = res[ORDER[0]]["summary"]
    head = pd.DataFrame([{"bench": b, "record": r_["variant"], "D99 cells": len(r_["pooled"]),
                          "verdict": r_["verdict"]["overall"], "outside": ", ".join(r_["verdict"]["outside"]) or "—",
                          "oil holdout bias": " / ".join(f"{x:+.1%}" for x in r_["pooled"].loc[r_["pooled"].stream == "oil", "holdout_bias"]),
                          "gas holdout bias": " / ".join(f"{x:+.1%}" for x in r_["pooled"].loc[r_["pooled"].stream == "gas", "holdout_bias"]),
                          "packages oil": " / ".join(str(x) for x in r_["pooled"].loc[r_["pooled"].stream == "oil", "packages"]),
                          "|bias| > 10 % cells": int((~r_["pooled"]["bias_ok_10pct"]).sum()),
                          "spread fails": int((~r_["pooled"]["spread_ok"]).sum()),
                          "rule catches a 15 %-high forecast": f"{r_['disc']['catches_15pct_high']:.0%}"} for b, r_ in res.items()])
    head.to_csv(a.out / "summary_table.csv", index=False)
    p = ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX step 15 holdout</title>",
         f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
         "<h1>BOX step 15 — six-bench holdout, scored once (D52) under the frozen D99 rule</h1>",
         (f"<div class=meta>built {built} · code {out_json['code_sha'][:7]} · blueox-boxfit @ {s0['engine_sha'][:7]} · "
          f"actuals curated.production through {s0['actuals_through']} (live last full month {s0['live_last_full_month']}) · "
          "held-out packages = any member in a D52 holdout block (salt unchanged) · error = Σ actual / Σ predicted − 1 per package, mean over packages "
          "(negative = forecast HIGH) · read-only, nothing stored</div>"),
         ("<div class=meta>A bench PASSES when every frozen cell's pooled holdout package bias lies inside its frozen P2.5–P97.5 interval "
          "(docs/box/step15-tuning-2026-10-17/frozen_d99.csv; digests re-checked below). |bias| ≤ 10 % and the D58 scale-free spread are reported, not gating. "
          "A FAIL means diagnose (7a pattern), never re-tune.</div>"),
         "<h2>Verdicts</h2>", _table(head, {})]
    for b, r_ in res.items():
        vd, summ = r_["verdict"], r_["summary"]
        p += [f"<h2 id={b}>{b} — {r_['variant']}</h2>",
              (f"<div class='flag {'ok' if vd['overall'] == 'PASS' else 'bad'}'><b>{vd['overall']}</b> — oil {vd['by_stream'].get('oil')}, gas {vd['by_stream'].get('gas')}; "
               f"{vd['n_outside']} of {vd['n_cells']} cells outside" + (f": {', '.join(vd['outside'])}" if vd["outside"] else "") +
               f". Rule power (tuning draws): passes a tuning-quality forecast {r_['disc']['passes_good']:.0%}, catches a 15 %-high forecast "
               f"{r_['disc']['catches_15pct_high']:.0%}.</div>"),
              "<h3>D99 cells (pooled across cutoffs)</h3>", _table(r_["pooled"], _pct(list(r_["pooled"].columns))),
              "<h3>Scored holdout packages by cutoff</h3>", _table(r_["by_cutoff"], {}),
              "<h3>Per-cutoff D53 cells (the rule as written; reported only)</h3>", _table(r_["per_cutoff"], _pct(list(r_["per_cutoff"].columns)))]
        if r_["wf"] is not None:
            ok = bool(r_["wf"]["identical"].all())
            p += [f"<h3>Walk-forward haircuts: holdout = tuning ({'identical' if ok else 'DIFFERENT'})</h3>", _table(r_["wf"], _pct(list(r_["wf"].columns)))]
        p += [f"<h3>Edges (within 5 mi of extent {summ['extent_id']}, by compass side) — oil, {r_['variant']}, holdout packages</h3>",
              _table(r_["edges"], _pct(list(r_["edges"].columns))),
              f"<h3>Same regions, tuning packages ({r_['edges_tuning_src']})</h3>", _table(r_["edges_tuning"], _pct(list(r_["edges_tuning"].columns)))]
        folds = pd.DataFrame(summ["folds"])[["cutoff", "n_train", "n_scored_wells", "n_packages", "n_packages_held_out", "n_wells_held_out"]]
        p += ["<h3>Folds</h3>", _table(folds, {}),
              f"<div class=meta>analog search: {summ.get('v2_mode_counts')} · radius reached (mi → n): {summ.get('v2_radius_mi')}</div>"]
    p += ["<h2>Integrity</h2>", "<h3>Frozen D99 manifest vs its source files (digest + values)</h3>", _table(integrity, {}),
          "<h3>Run window + warehouse ETL activity inside it</h3>", _table(win, {}),
          _table(etl, {}) if len(etl) else "<div class=meta>No meta.etl_log row overlaps the run window.</div>", "</body></html>"]
    (a.out / "index.html").write_text("\n".join(p), encoding="utf-8")
    print(head.to_string())
    print(f"wrote {a.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
