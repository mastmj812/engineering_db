"""BOX step 9b page: the one-time D52 holdout of BS2_S (box_v2_wf, D94) and WCXY (raw box_v2 on the D93 pool, D97) judged under D99.

    python -m scripts.box_holdout9b [--runs runs/box9b] [--out docs/box/step9b-2026-10-17]

Reads the `scripts.box_acceptance --score-holdout --holdout-once --fold analog` outputs under --runs (bs2s/, wcxy_wca1/), the
FROZEN intervals (docs/box/pre9b-2026-10-16), the step-9a walk-forward table, and read-only warehouse objects (the BS2_S extent
of record for the D96 south-edge watch item; meta.etl_log for the run window). Writes index.html + small CSV / JSON. Nothing is
stored and nothing is re-scored: every holdout number is read from the frames or computed from them by box/holdout9b.py.
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
from box import holdout as ho
from box import holdout9b as h
from box import tc_area_report as tar
from box import tune9a_report as t9
from box.edge_gap_report import _CSS, _table
from etl.db import get_connection

FROZEN = Path("docs") / "box" / "pre9b-2026-10-16"
TUNE = Path("docs") / "box" / "step9a-2026-10-16"
INTERVALS_COMMIT = "22650ce"  # the pre-9b commit that wrote the interval CSVs (eng_db #147)
RUNS = (("BS2_S", "bs2s", "holdout_BS2_S", "BS2_S — box_v2_wf on its own walk-forward haircut (D94), extent 7"),
        ("WCXY_WCA1", "wcxy_wca1", "holdout_WCXY_WCA1", "WCXY — raw box_v2 (D97), analogs WCXY + WCA_1 (D93), WCA extent 6 (D95)"))
_ETL_SQL = """SELECT source, table_name, status, run_started_at, run_finished_at FROM meta.etl_log
WHERE run_started_at < %(b)s AND COALESCE(run_finished_at, now()) > %(a)s ORDER BY run_started_at"""


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def _views(d: Path, tag: str) -> pd.DataFrame:
    return pd.concat([pd.read_csv(f, dtype={"api10": str}) for f in sorted(d.glob(f"view_{tag}_*.csv.gz"))], ignore_index=True)


def _wf_tuning(bench: str) -> list[dict[str, object]]:
    """The step-9a own-bench walk-forward table as a log (cutoff year -> Dec 1)."""
    w = pd.read_csv(TUNE / "walk_forward.csv")
    w = w[(w["bench"] == bench) & (w["haircut from"] == "own")]
    out = []
    for _, r in w.iterrows():
        for k in (12, 24, 36, 48):
            v = r.get(f"cum-{k}")
            out.append({"cutoff": f"{int(r['cutoff'])}-12-01", "variant": "box_v2", "stream": r["stream"], "horizon": k,
                        "haircut": None if pd.isna(v) else float(v)})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("runs") / "box9b")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step9b-2026-10-17")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")

    # ---- frozen intervals: byte-identical to the commit that froze them (D99: never redrawn)
    frozen = []
    for spec in h.BENCHES.values():
        f = FROZEN / spec["intervals"]
        committed = _git("show", f"{INTERVALS_COMMIT}:{f.as_posix()}")
        same = committed.replace("\r\n", "\n").strip() == f.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        frozen.append({"file": f.as_posix(), "sha256": h.sha256(f), "identical_to": INTERVALS_COMMIT, "identical": same,
                       "last_commit": _git("log", "-1", "--format=%h %cs", "--", f.as_posix())})
    frozen_df = pd.DataFrame(frozen)
    if not frozen_df["identical"].all():
        raise SystemExit("frozen interval file differs from its freezing commit - D99 forbids redrawing; stop")

    res: dict[str, dict[str, object]] = {}
    windows = []
    for bench, d, tag, title in RUNS:
        spec = h.BENCHES[bench]
        rd = a.runs / d
        summ = json.loads((rd / f"summary_{tag}.json").read_text(encoding="utf-8"))
        cells = pd.read_csv(rd / f"cells_{tag}.csv")
        v = _views(rd, tag)
        x, y = dfr._xy(v["mid_lon"], v["mid_lat"])
        v["pkg"] = v["cutoff"].astype(str) + ":" + v["package"].astype(str)
        v["bx"], v["by"] = ho.blocks(np.asarray(x), np.asarray(y))
        iv = h.load_intervals(FROZEN / spec["intervals"], spec["cells"])
        pooled = h.pooled_cells(v, spec["record"], iv)
        vd = h.verdict(pooled)
        hz = sorted({k for _, k in spec["cells"]})
        pc = h.per_cutoff(cells, spec["record"], hz)
        cc = pd.read_csv(FROZEN / f"cell_counts_{bench}.csv")
        cc = cc[cc.cell == "pooled"][["stream", "horizon", "packages_p50", "packages_p10_p90"]]
        pooled = pooled.merge(cc.rename(columns={"packages_p50": "rehearsal packages p50", "packages_p10_p90": "rehearsal P10–P90"}),
                              on=["stream", "horizon"], how="left")
        wf = h.walk_forward_identity(summ.get("walk_forward", []), _wf_tuning(bench), "box_v2") if spec["record"].endswith("_wf") else None
        if summ["record_variant"] != spec["record"] or summ["view"] != "HOLDOUT (final scoring)":
            raise SystemExit(f"{bench}: summary says record {summ['record_variant']} / view {summ['view']}")
        res[bench] = {"title": title, "summary": summ, "pooled": pooled, "verdict": vd, "per_cutoff": pc, "wf": wf, "view": v}
        pooled.to_csv(a.out / f"pooled_{bench}.csv", index=False)
        pc.to_csv(a.out / f"per_cutoff_{bench}.csv", index=False)
        if wf is not None:
            wf.to_csv(a.out / f"walk_forward_identity_{bench}.csv", index=False)
        for nm in ("started", "finished"):
            p = a.runs / f"{nm}_{'bs2s' if bench == 'BS2_S' else 'wcxy'}_utc.txt"
            windows.append({"bench": bench, "event": nm, "utc": p.read_text().strip() if p.exists() else None})

    # ---- read-only warehouse: BS2_S extent (D96 south edge) + ETL activity during the run window
    win = pd.DataFrame(windows)
    t_a, t_b = min(win["utc"].dropna()), max(win["utc"].dropna())
    with get_connection() as conn:
        ext = tar.pull_extent(conn, "BS2_S")
        with conn.cursor() as cur:
            cur.execute(_ETL_SQL, {"a": t_a, "b": t_b})
            etl = pd.DataFrame(cur.fetchall(), columns=["source", "table_name", "status", "run_started_at", "run_finished_at"])
    vb = res["BS2_S"]["view"]
    xb, yb = dfr._xy(vb["mid_lon"], vb["mid_lat"])
    vb = pd.concat([vb.reset_index(drop=True), t9.edge_classes(np.asarray(xb), np.asarray(yb), ext["geom_ft"])], axis=1)
    south = t9.region_table(vb, horizons=(12, 24))
    south.to_csv(a.out / "bs2s_regions_holdout.csv", index=False)
    tune_regions = pd.read_csv(TUNE / "bs2s_edge_regions.csv") if (TUNE / "bs2s_edge_regions.csv").exists() else None
    etl.to_csv(a.out / "etl_during_runs.csv", index=False)
    frozen_df.to_csv(a.out / "frozen_intervals_check.csv", index=False)

    overall = "PASS" if all(r_["verdict"]["overall"] == "PASS" for r_ in res.values()) else "FAIL"
    out_json = {"built_at": built, "code_sha": _git("rev-parse", "HEAD"), "rule": "D99 (pooled across cutoffs; every cell inside its frozen P2.5–P97.5 interval)",
                "frozen_intervals": frozen, "run_window_utc": windows, "etl_rows_during_runs": len(etl),
                "benches": {b: {"record": h.BENCHES[b]["record"], "verdict": r_["verdict"], "engine_sha": r_["summary"]["engine_sha"],
                                "actuals_through": r_["summary"]["actuals_through"], "live_last_full_month": r_["summary"]["live_last_full_month"],
                                "folds": r_["summary"]["folds"], "v2_radius_mi": r_["summary"].get("v2_radius_mi"),
                                "v2_mode_counts": r_["summary"].get("v2_mode_counts"),
                                "verdict_as_written_d53": r_["summary"]["verdict"]} for b, r_ in res.items()}}
    (a.out / "verdict.json").write_text(json.dumps(out_json, indent=2, default=str), encoding="utf-8")

    pct = {c: "+.1%" for c in ("tuning_bias", "interval_lo", "interval_hi", "holdout_bias", "bench_bias", "pkg_bias")}
    pct |= {c: ".2f" for c in ("band", "band_scale_free", "bench_band", "bench_band_scale_free", "pkg_band")}
    p = ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX step 9b holdout</title>",
         f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
         "<h1>BOX step 9b — BS2_S + WCXY holdout, scored once (D52) under D99</h1>",
         (f"<div class=meta>built {built} · code {out_json['code_sha'][:7]} · blueox-boxfit @ {res['BS2_S']['summary']['engine_sha'][:7]} · "
          f"actuals curated.production through {res['BS2_S']['summary']['actuals_through']} (live last full month {res['BS2_S']['summary']['live_last_full_month']}) · "
          "held-out packages = any member in a D52 holdout block (salt unchanged) · error = Σ actual / Σ predicted − 1 per package, mean over packages "
          "(negative = forecast HIGH) · read-only, nothing stored</div>"),
         (f"<div class='flag {'ok' if overall == 'PASS' else 'bad'}'><b>D99 verdict: BS2_S {res['BS2_S']['verdict']['overall']} · WCXY {res['WCXY_WCA1']['verdict']['overall']}</b>"
          " — a bench passes when every pooled cell's holdout package bias lies inside its frozen P2.5–P97.5 interval (oil AND gas). "
          "|bias| ≤ 10 % and the D58 scale-free spread are reported, not gating (D99).</div>")]
    for r_ in res.values():
        vd = r_["verdict"]
        p += [f"<h2>{r_['title']}</h2>",
              (f"<div class='flag {'ok' if vd['overall'] == 'PASS' else 'bad'}'><b>{vd['overall']}</b> — oil {vd['by_stream'].get('oil')}, gas {vd['by_stream'].get('gas')}; "
               f"{vd['n_outside']} of {vd['n_cells']} cells outside" + (f": {', '.join(vd['outside'])}" if vd["outside"] else "") + "</div>"),
              "<h3>D99 cells (pooled across cutoffs)</h3>",
              _table(r_["pooled"], pct),
              "<h3>Sensitivity (not the rule): intervals shrunk to the holdout's package count</h3>",
              ("<div class=meta>The frozen intervals were drawn at a 20 % draw of the TUNING packages; this holdout holds more packages than that "
               "(the salted block hash is geographic, not per bench), so it resolves bias more tightly. Shrink = sqrt(n holdout / n rehearsal).</div>"),
              _table(h.size_adjusted(r_["pooled"]), pct | {"adj_lo": "+.1%", "adj_hi": "+.1%", "shrink": ".2f"}),
              "<h3>Per-cutoff D53 cells (the rule as written; reported only — D99 replaced it because these cells hold too few packages)</h3>",
              _table(r_["per_cutoff"], pct)]
        if r_["wf"] is not None:
            ok = bool(r_["wf"]["identical"].all())
            p += [f"<h3>Walk-forward haircuts: holdout = tuning ({'identical' if ok else 'DIFFERENT'})</h3>",
                  ("<div class=meta>D58 / D94: the holdout's haircut at each cutoff comes from BS2_S's own TUNING cells at earlier cutoffs only; "
                   "it must equal the step-9a tuning table.</div>"), _table(r_["wf"], {"haircut_holdout": "+.3f", "haircut_tuning": "+.3f", "abs_diff": ".1e"})]
        folds = pd.DataFrame(r_["summary"]["folds"])[["cutoff", "n_train", "n_scored_wells", "n_packages", "n_packages_held_out", "n_wells_held_out"]]
        p += ["<h3>Folds</h3>", _table(folds, {}),
              f"<div class=meta>analog search (location-cutoffs): {r_['summary'].get('v2_mode_counts')} · radius reached (mi → n): {r_['summary'].get('v2_radius_mi')}</div>"]
    p += ["<h2>D96 watch item — BS2_S south edge, holdout packages</h2>",
          ("<div class=meta>Regions as in step 9a (within 5 mi of the extent boundary; south = bearing 135–225° from the centroid). "
           "Package bias restricted to the region's members, box_v2_wf oil.</div>"),
          _table(south, {c: "+.1%" for c in south.columns if "bias" in c} | {c: ".0%" for c in south.columns if "share" in c})]
    if tune_regions is not None:
        p += ["<h3>Step-9a tuning, same regions</h3>", _table(tune_regions, {c: "+.1%" for c in tune_regions.columns if "bias" in c} | {c: ".0%" for c in tune_regions.columns if "share" in c})]
    p += ["<h2>Integrity</h2>", "<h3>Frozen intervals (D99: never redrawn)</h3>", _table(frozen_df, {}),
          "<h3>Run window + warehouse ETL activity inside it</h3>", _table(win, {}),
          _table(etl, {}) if len(etl) else "<div class=meta>No meta.etl_log row overlaps the run window.</div>", "</body></html>"]
    (a.out / "index.html").write_text("\n".join(p), encoding="utf-8")
    print(json.dumps({b: r_["verdict"] for b, r_ in res.items()}, indent=1))
    print(f"wrote {a.out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
