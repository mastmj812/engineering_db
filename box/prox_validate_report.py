"""PDP-proximity study, step 2c — run + page for the pre-registered walk-forward validation (DB-FREE).

Rule of record: docs/box/prox-2026-10-19/PREREG_2c.md. The verdict is computed on oil cum-24 only; the other metrics
are reported. The final haircut table (fit on ALL folds) is written alongside as the candidate table of record —
it is what step 4 would apply if the gate accepts.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import prox_validate as pv
from box.edge_gap_report import _CSS, _table
from box.prox_config_report import frame

PREREG = Path("docs") / "box" / "prox-2026-10-19" / "PREREG_2c.md"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout.strip()


def final_table(d: pd.DataFrame, metric: str = "oil24") -> pd.DataFrame:
    """Haircut table fit on every fold (what step 4 would read), one row per (rung, key) with n."""
    keys = pv.ladder_keys(d)
    lr = pv.l_rel(d, metric)
    t = pv.fit(keys, lr)
    rows = [{"rung": k, "key": kk, "n_train": n, "factor": float(np.exp(m)), "usable": n >= pv.RUNG_MIN} for k in pv.RUNGS for kk, (m, n) in t[k].items()]
    return pd.DataFrame(rows).sort_values(["rung", "n_train"], ascending=[True, False])


def render(res: dict[str, Any], meta: dict[str, Any], final: pd.DataFrame) -> str:
    s = res["oil24"]
    fmt = {"f": ".3f", "resid": ".3f", "no_haircut_resid": ".3f", "mean_r": ".3f", "mean_r0": ".3f", "factor": ".3f"}
    rows = []
    for m, r in res.items():
        rows.append({"metric": m, "n_test": r["n_test"], "n_material": r["n_material"], "P1 resid": r["P1_resid"], "P1 90%": f"{r['P1_lo']:.3f}-{r['P1_hi']:.3f}",
                     "P1 no haircut": r["P1_no_haircut"], "P2 rms": r["P2_rms"], "P2 rms no haircut": r["P2_rms_no_haircut"], "cells": r["n_cells"],
                     "P3 share": r["P3_share"], "verdict" if m == "oil24" else "would-be verdict": r["verdict"]})
    summ = pd.DataFrame(rows)
    p = [(f"<!doctype html><html><head><meta charset=utf-8><title>PDP proximity validation</title><style>{_CSS} body{{overflow-x:hidden}} "
          "table{display:block;overflow-x:auto;max-width:100%}</style></head><body>"),
         "<h1>PDP-proximity study — step 2c: walk-forward validation of the configuration haircut</h1>",
         f"<div class=meta>{meta['built']} · pre-registration {meta['prereg_commit']} · code {meta['code_commit']} · DB-free</div>",
         f"<h2>Verdict (oil cum-24, pre-registered): {s['verdict']}</h2>",
         ("<p>P1: test children with a material haircut (f ≤ 0.90) — residual actual ÷ (BOX × haircut) on BOX's calibrated scale must "
          "lie in 0.95–1.05 or its 90 % interval contain 1. P2: across cells with ≥ 30 test children, the haircut must lower the "
          "RMS cell bias. P3: ≥ 80 % of those cells within ±10 %. Walk-forward: each test cutoff's haircuts are fit on earlier "
          "cutoffs only.</p>"),
         _table(summ, {"P1 resid": ".3f", "P1 no haircut": ".3f", "P2 rms": ".3f", "P2 rms no haircut": ".3f", "P3 share": ".2f"})]
    for m in res:
        p += [f"<h2>Cells — {m}</h2>", _table(res[m]["cells"].drop(columns=["mean_r", "mean_r0"]), fmt, max_rows=60)]
    p += ["<h2>Candidate haircut table of record (oil cum-24, fit on all folds)</h2>", _table(final, fmt, max_rows=200), "</body></html>"]
    return "\n".join(p)


def run(views_root: Path, runs: Path, out: Path, n_boot: int = pv.N_BOOT) -> dict[str, Any]:
    prereg_commit = _git("log", "-1", "--format=%h", "--", str(PREREG))
    if not prereg_commit or _git("status", "--porcelain", "--", str(PREREG), "box/prox_validate.py"):
        raise RuntimeError("PREREG_2c.md and box/prox_validate.py must be committed (clean) before scoring")
    d, _, meta = frame(views_root, runs)
    res = {}
    parts = {}
    for m, cuts in pv.TEST_CUTOFFS.items():
        p = pv.walk_forward(d, m, cuts)
        parts[m] = p
        res[m] = pv.score(p, n_boot=n_boot)
    final = final_table(d)
    meta |= {"built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"), "prereg_commit": prereg_commit, "code_commit": _git("rev-parse", "--short", "HEAD"),
             "n_boot": n_boot, "seed": pv.SEED, **{f"{m}_{k}": v for m, r in res.items() for k, v in r.items() if k != "cells"}}
    out.mkdir(parents=True, exist_ok=True)
    for m, r in res.items():
        r["cells"].to_csv(out / f"validate_cells_{m}.csv", index=False)
    pd.concat([p.assign(metric=m) for m, p in parts.items()], ignore_index=True).to_csv(out / "validate_children.csv.gz", index=False, compression="gzip")
    final.to_csv(out / "haircut_table_candidate.csv", index=False)
    (out / "validate_summary.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    (out / "validate.html").write_text(render(res, meta, final), encoding="utf-8")
    return {"meta": meta, "res": res, "final": final}
