"""BOX step 21c — the Midland one-time D52 holdout under the FROZEN pre-registration (revision 8: box/step21.DEFINITION digest
9780f326, frozen SHA 5ceadc2; docs/box/step21a-2026-10-31/PREREGISTRATION.md) and the gate-21b record (D149,
docs/box/step21b-2026-11-01/GATE_21B.json). Pure, DB-free. Written AFTER the freeze and checked against PREREGISTRATION §5-§7 as
written before it ran (the 16c pattern); each piece names the paragraph it implements and reuses the code of record unchanged.

  harness     The frozen box/acceptance.run refuses step16 + score_holdout (a Delaware step-16 guard, D118: those holdouts were
              spent). The Midland record variant mid_r2 exists only on the step-16 path, so no frozen command predicts the
              registered holdout. Michael 2026-11-02 (21c, option A): run the frozen run() with exactly that two-line guard
              removed and nothing else (`unguarded_run`, pinned by tests/test_box_step21c.py to the frozen source); the frozen
              harness then predicts the held-out view (`package_held_out == True`) exactly as it predicted the tuning view.
              The harness's own mid_r2_wf on a holdout run takes its haircuts from the HOLDOUT cells (history=None in the
              step-16 branch) and is never read; §5's "walk-forward factors from TUNING cells only (D58)" is applied here.
  §4 / §5     mid_r2p = mid_r2 x the Midland factor table as frozen at gate 21b (production's lookup: box/step21b.record_factor);
              mid_r2p_wf = mid_r2p x the walk-forward haircut from the group's TUNING mid_r2p cells (box/acceptance
              .apply_walk_forward with history = those cells, the D58 path box_v2_wf uses on a holdout); record per stream =
              GATE_21B.json (LSSH mid_r2p both streams; WCA_1 / WCB_1 wf oil, r2p gas).
  §6          cells = the horizons (12 / 24 / 36) whose pooled holdout cell under the record OIL treatment reaches 30 packages, oil
              AND gas at each (the 21b frozen file draws the horizon set from the oil record treatment the same way); judged by
              box/holdout9b.pooled_cells / verdict (step 9b / 15, unchanged) against the frozen_d99.csv rows of that treatment.
              PASS = every judged cell inside its interval with >= 1 oil cell. Tier: validated on PASS, provisional on FAIL or
              no cell; the gate-21b move (LSSH) is FLAGGED, not resolved (FINDINGS: §6 "moved at the tuning gate" vs §5).
  §5 prod     D102 haircut table for step 23: the group's tuning + holdout mid_r2p cells merged per cutoff (box/production
              .merge_cells_by_cutoff), then the >= 30 floor, factor = 1 + package-weighted bias (box/production.haircut_table's
              formula, horizon by horizon so a missing cum-48 is reported, not raised); 9c guard (D106) per stream.
  §7          water holdout once: D109 holdout cell = >= 10 measured packages, consistent inside its frozen_water.csv interval
              (box/water11_report.package_sums / _bias, the statistic the interval was drawn with).
"""

from __future__ import annotations
import __future__ as fut

import difflib
import hashlib
import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import holdout9b as h9
from box import step21 as st
from box import step21b as sb

RAW, PROX, PROX_WF = st.RAW, st.PROX, st.PROX_WF
ROOT = Path(__file__).resolve().parents[1]
DOCS_21B = ROOT / "docs" / "box" / "step21b-2026-11-01"
GATE_21B = DOCS_21B / "GATE_21B.json"

# The guard removed, verbatim from box/acceptance.run at 5ceadc2 (and nothing else).
GUARD = ('    if step16 and score_holdout:\n'
         '        raise ValueError("step 16 scores TUNING packages only: the D52 holdouts are spent (validated) or failed (provisional), D118")\n')
# sha256 of inspect.getsource(box.acceptance.run) at the frozen SHA 5ceadc2: any change to run() refuses the lift.
RUN_SOURCE_SHA256 = "4bcad48cc6e53bb2f2739166cd1bf111b81b2f65eac06242907f72f436fd6780"


# ----------------------------------------------------------------------------
# harness: the frozen run() minus the step-16 holdout guard
# ----------------------------------------------------------------------------


def run_source() -> str:
    return inspect.getsource(ac.run)


def unguarded_source(src: str | None = None) -> str:
    src = run_source() if src is None else src
    if src.count(GUARD) != 1:
        raise RuntimeError("box/acceptance.run: the step-16 holdout guard is not present exactly once — not the frozen run()")
    return src.replace(GUARD, "", 1)


def source_diff(src: str | None = None) -> list[str]:
    """The removed / added lines between the frozen run() and the lifted one (must be exactly the two guard lines, removed)."""
    src = run_source() if src is None else src
    d = difflib.ndiff(src.splitlines(keepends=True), unguarded_source(src).splitlines(keepends=True))
    return [x for x in d if x[:2] in ("- ", "+ ")]


def unguarded_run(check_sha: bool = True) -> Callable[..., dict[str, Any]]:
    """box/acceptance.run compiled from its own frozen source with the guard removed, in box/acceptance's module namespace (so
    every name it calls — including the 21b months observer's patches — resolves exactly as in the frozen run())."""
    src = run_source()
    if check_sha and hashlib.sha256(src.encode("utf-8")).hexdigest() != RUN_SOURCE_SHA256:
        raise RuntimeError("box/acceptance.run differs from the frozen 5ceadc2 source — not a score")
    ns: dict[str, Any] = {}
    code = compile(unguarded_source(src), ac.__file__, "exec", flags=fut.annotations.compiler_flag, dont_inherit=True)
    exec(code, ac.__dict__, ns)  # noqa: S102 - the frozen function's own source, minus two lines (tests pin both)
    return ns["run"]


# ----------------------------------------------------------------------------
# gate-21b record (D149)
# ----------------------------------------------------------------------------


def gate() -> dict[str, Any]:
    return json.loads(GATE_21B.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_frozen(g: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Both frozen interval files against the gate-21b sha256 (raw bytes; .gitattributes keeps them LF). Refuses on a mismatch."""
    g = gate() if g is None else g
    got = {"frozen_d99.csv": sha256_file(DOCS_21B / "frozen_d99.csv"), "frozen_water.csv": sha256_file(DOCS_21B / "frozen_water.csv")}
    want = {"frozen_d99.csv": g["frozen_d99_sha256"], "frozen_water.csv": g["frozen_water_sha256"]}
    bad = [k for k in got if got[k] != want[k]]
    if bad:
        raise RuntimeError(f"frozen interval file(s) {bad} differ from GATE_21B.json — never redraw; stop")
    return {"got": got, "want": want, "identical": True}


def record(g: Mapping[str, Any], group: str) -> dict[str, str]:
    r = g["record_treatment"][group]
    return {"oil": r["oil"], "gas": r["gas"]}


def frozen_rows(frozen: pd.DataFrame, group: str, oil_treatment: str) -> pd.DataFrame:
    """The frozen_d99.csv rows that carry `oil_treatment` for `group`: the 'record' role when its treatment is that oil treatment
    (WCA_1 / WCB_1 read 'mid_r2p_wf oil / mid_r2p gas (D106)'), else the 'alternative' role drawn for exactly that case (LSSH,
    moved to mid_r2p at gate 21b). Raises when neither matches — the file was frozen to make that impossible."""
    f = frozen[frozen["group"] == group]
    rec = f[f["role"] == "record"]
    if len(rec) and str(rec["treatment"].iloc[0]).split(" ")[0] == oil_treatment:
        return rec.assign(role_used="record")
    alt = f[(f["role"] != "record") & (f["treatment"] == oil_treatment)]
    if len(alt):
        return alt.assign(role_used="alternative")
    raise RuntimeError(f"{group}: no frozen interval rows for oil treatment {oil_treatment}")


# ----------------------------------------------------------------------------
# holdout treatments
# ----------------------------------------------------------------------------


def holdout_treatments(views: dict[str, pd.DataFrame], factor: Mapping[str, float], tuning_cells: pd.DataFrame,
                       rec: Mapping[str, str]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """In place on the holdout views: mid_r2p (§4 factor), mid_r2p_wf (TUNING haircuts, D58), pred_record_<s><k> per stream.
    Returns (per-cutoff D53 cells of mid_r2 / mid_r2p / mid_r2p_wf / record, the walk-forward log)."""
    sb.add_prox(views, factor, PROX)
    c = sb.score(views, [RAW, PROX])
    hist = tuning_cells[tuning_cells["variant"] == PROX]
    log: list[dict[str, Any]] = []
    c_wf = pd.concat(ac.apply_walk_forward(c, views, hist, log=log, bases=(PROX,)), ignore_index=True)
    for view in views.values():
        for s in ac.STREAMS:
            for k in ac.HORIZONS:
                src = f"pred_{rec[s]}_{s}{k}"
                if src in view and f"actual_{s}{k}" in view:
                    view[f"pred_record_{s}{k}"] = view[src]
                    view[f"record_err_{s}{k}"] = ac.hc.pct_error(view[f"actual_{s}{k}"].to_numpy(float), view[src].to_numpy(float))
    c_rec = sb.score(views, ["record"])
    return pd.concat([c, c_wf, c_rec], ignore_index=True), log


def oil_counts(v: pd.DataFrame, variant: str = "record", horizons: Sequence[int] = st.HORIZONS_JUDGEABLE) -> dict[int, int]:
    """Pooled holdout packages with a scored oil cum-k under `variant` (box/rehearse9b.package_table: finite actual, forecast > 0)."""
    from box import rehearse9b as r9

    t = r9.package_table(v, variant, horizons)
    return {k: int(np.isfinite(t["sums"][("oil", k)].get("box_a", np.array([]))).sum()) for k in horizons}


def judged_cells(counts: Mapping[int, int], floor: int = st.MIN_PACKAGES) -> list[tuple[str, int]]:
    """§6: oil AND gas at every horizon whose pooled record-oil holdout cell reaches `floor` packages."""
    hz = [k for k in st.HORIZONS_JUDGEABLE if int(counts.get(k, 0)) >= floor]
    return [(s, k) for s in ac.STREAMS for k in hz]


def judge(v: pd.DataFrame, frozen_g: pd.DataFrame, cells: Sequence[tuple[str, int]]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """box/holdout9b.pooled_cells + verdict on pred_record, against the frozen intervals of the cells judged. PASS also needs
    at least one oil cell (§6)."""
    if not cells:
        return pd.DataFrame(), {"overall": "NO CELL", "n_cells": 0, "n_outside": 0, "outside": [], "by_stream": {}}
    key = pd.DataFrame(list(cells), columns=["stream", "horizon"])
    iv = key.merge(frozen_g[["stream", "horizon", "tuning_bias", "interval_lo", "interval_hi", "d99_cell"]].astype({"horizon": int}),
                   on=["stream", "horizon"], how="left")
    if iv["interval_lo"].isna().any() or iv["interval_hi"].isna().any():
        raise RuntimeError(f"no frozen interval for {iv.loc[iv['interval_lo'].isna(), ['stream', 'horizon']].values.tolist()} — stop")
    pc = h9.pooled_cells(v, "record", iv)
    pc = pc.merge(iv[["stream", "horizon", "d99_cell"]].rename(columns={"d99_cell": "frozen_expected_d99_cell"}), on=["stream", "horizon"])
    vd = h9.verdict(pc)
    if not (pc["stream"] == "oil").any():
        vd["overall"] = "FAIL"
    return pc, vd


def tier(verdict: Mapping[str, Any]) -> str:
    return "validated" if verdict.get("overall") == "PASS" else "provisional"


# ----------------------------------------------------------------------------
# step-23 haircut table (D102) + 9c guard (D106)
# ----------------------------------------------------------------------------


def d102_table(tuning_cells: pd.DataFrame, holdout_cells: pd.DataFrame, variant: str = PROX, floor: int = st.MIN_PACKAGES) -> pd.DataFrame:
    """D102: tuning + holdout cells of `variant` merged per (cutoff, stream, horizon), then the >= floor rule, factor = 1 +
    package-weighted mean bias (box/production.haircut_table's formula; one row per stream x horizon, NaN where no merged
    cell clears the floor)."""
    from box import production as pr

    both = pd.concat([tuning_cells[tuning_cells["variant"] == variant].assign(side="tuning"),
                      holdout_cells[holdout_cells["variant"] == variant].assign(side="holdout")], ignore_index=True)
    m = pr.merge_cells_by_cutoff(both)
    rows = []
    for s in ac.STREAMS:
        for k in ac.HORIZONS:
            x = m[(m["stream"] == s) & (m["horizon"] == k) & (m["n_packages"] >= floor)]
            if x.empty:
                rows.append({"stream": s, "horizon": k, "factor": np.nan, "bias": np.nan, "n_packages": 0, "n_cells": 0, "cutoffs": ""})
                continue
            w = x["n_packages"].to_numpy(float)
            b = float(np.sum(w * x["pkg_bias"].to_numpy(float)) / w.sum())
            rows.append({"stream": s, "horizon": k, "factor": 1.0 + b, "bias": b, "n_packages": int(w.sum()), "n_cells": len(x),
                         "cutoffs": ", ".join(sorted(str(c)[:4] for c in x["cutoff"]))})
    return pd.DataFrame(rows)


def guard_d106(tab: pd.DataFrame, months: Mapping[str, np.ndarray]) -> dict[str, Any]:
    """box/step21b.guard (production_run9.guard_table + guard_tail) on a D102 table."""
    return sb.guard(tab, months)


# ----------------------------------------------------------------------------
# water (§7 / D109)
# ----------------------------------------------------------------------------


def water_judge(t: pd.DataFrame, frozen_w: pd.DataFrame, group: str) -> pd.DataFrame:
    """Per horizon: holdout measured-water packages, pooled ratio bias, judged at >= 10 packages, inside the frozen interval."""
    from box import water11_report as wr

    f = frozen_w[frozen_w["group"] == group].set_index("horizon")
    s = wr.package_sums(t, "ratio") if len(t) else None
    full = np.ones(len(s["pkg"]), dtype=bool) if s else None
    rows = []
    for k in (12, 24, 36):
        b, n = wr._bias(full, s, k) if s else (np.nan, 0)
        lo, hi = (float(f.at[k, "interval_lo"]), float(f.at[k, "interval_hi"])) if k in f.index else (np.nan, np.nan)
        judged = n >= wr.MIN_HOLDOUT_PACKAGES and np.isfinite(lo) and np.isfinite(hi)
        rows.append({"group": group, "horizon": k, "holdout_packages": n, "holdout_bias": b,
                     "tuning_bias": float(f.at[k, "tuning_bias"]) if k in f.index else np.nan, "interval_lo": lo, "interval_hi": hi,
                     "judged": bool(judged), "consistent": bool(judged and lo <= b <= hi) if judged else None})
    return pd.DataFrame(rows)
