"""BOX step 24 — continuous proximity factor: fit, contest, validate, sticks, report (DB-free; reads the §1 caches only).

    python -m scripts.box_prox_cont smoke [--out <dir>]            synthetic basin end-to-end (no real data; always allowed)
    python -m scripts.box_prox_cont run --basin delaware|midland   the score — REFUSED until gate 24a stamps the SHA in §11
        [--views runs/prox/views] [--runs runs/prox] [--midland-children docs/box/step21b-2026-11-01/prox_children.csv.gz]
        [--runs-midland runs/step21a] [--out docs/box/prox-continuous-2026-11-02] [--boot 1000] [--steps fit,contest,validate,sticks]

Pre-registration: docs/box/prox-continuous-2026-11-02/PREREGISTRATION.md. The model, rules, checks and verdict live in
box/prox_cont.py (DEFINITION digest-pinned by tests/test_box_prox_cont.py). `run` reads §11 of the pre-registration: while it
still says `<sha>` nothing is scored; once stamped, the working tree's HEAD must equal it (frozen files clean) or the run is
refused. Midland reads TUNING children only (the 21b frame); the D52 holdout blocks are never loaded here.

Delaware inputs: box.prox_dose_report.assemble (harness views + runs/prox caches, step-2 frame), the incumbent D113 ladder via
box.prox_validate per test fold. Midland inputs: the 21b prox_children frame (l_oil24, block, bench_group, cutoff) + the 21a
links / pud_links caches; the incumbent is the 21b factor_lookup column of that frame.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pickle
import re
import subprocess
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import prox_cont as pc
from box import prox_dose as pdz
from box import prox_validate as pv

PREREG = Path("docs") / "box" / "prox-continuous-2026-11-02" / "PREREGISTRATION.md"
FROZEN_FILES = ("box/prox_cont.py", "box/prox_dose.py", "box/prox_study.py", "box/prox_validate.py", "box/step21_prox.py", "scripts/box_prox_cont.py")
METRICS = ("oil24", "oil12", "oil36", "gas24")
GRID = np.arange(50.0, 2700.0, 50.0)


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        return ""


def frozen_sha() -> str | None:
    """The SHA stamped in §11, or None while the placeholder stands."""
    txt = PREREG.read_text(encoding="utf-8")
    m = re.search(r"## 11\. Frozen SHA.*?`([0-9a-f]{7,40}|<sha>)`", txt, re.DOTALL)
    if not m or m.group(1) == "<sha>":
        return None
    return m.group(1)


def gate_check() -> str:
    sha = frozen_sha()
    if sha is None:
        raise SystemExit("REFUSED: PREREGISTRATION.md section 11 still reads `<sha>` - gate 24a has not stamped the frozen SHA; nothing is scored before the freeze.")
    head = _git("rev-parse", "HEAD")
    if not head.startswith(sha) and not sha.startswith(head[: len(sha)]):
        raise SystemExit(f"REFUSED: HEAD {head[:12]} is not the frozen SHA {sha}")
    dirty = _git("status", "--porcelain", "--", *FROZEN_FILES)
    if dirty:
        raise SystemExit(f"REFUSED: frozen files modified in the working tree:\n{dirty}")
    return sha


# ---- loaders ---------------------------------------------------------------------------------------------------------
def load_delaware(views: Path, runs: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    from box import (
        prox_dose_report as pdr,  # imports matplotlib-side helpers; keep it off the smoke path
    )

    d, meta = pdr.assemble(views, runs)
    with open(runs / "links.pkl", "rb") as f:
        links = pickle.load(f)
    with open(runs / "pud_links.pkl", "rb") as f:
        pud = pickle.load(f)
    d["basin"] = "delaware"
    return d, links, pud, meta


def load_midland(children_csv: Path, runs: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    from box import step21_prox as sp

    d = pd.read_csv(children_csv, dtype={"api10": str, "cutoff": str})
    d = d.rename(columns={"factor_lookup": "f_incumbent"})
    d["basin"] = "midland"
    with open(runs / "links.pkl", "rb") as f:
        links = pickle.load(f)
    with open(runs / "pud_links.pkl", "rb") as f:
        pud = sp.existing_as_parents(pickle.load(f))   # revision 4: every existing producer is a stick parent
    if "holdout_block" in d.columns and bool(d["holdout_block"].any()):
        raise SystemExit("REFUSED: the Midland frame carries holdout-block children; this step reads tuning children only")
    meta = {"children": len(d), "by_group": d.groupby("bench_group").size().to_dict(), "source": str(children_csv)}
    return d, links, pud, meta


def incumbent_ln_f(d: pd.DataFrame, links: pd.DataFrame, metric: str, cutoffs: tuple[str, ...]) -> pd.Series:
    """Delaware: the D113 ladder (box.prox_validate) fitted per test fold on earlier cutoffs. Midland: the 21b column."""
    if "f_incumbent" in d.columns:
        return np.log(pd.to_numeric(d["f_incumbent"], errors="coerce").fillna(1.0).clip(lower=1e-3))
    cfg = pdz.configuration(list(d["api10"]), links).set_index("api10").reindex(d["api10"]).reset_index()
    cfg.index = d.index
    cfg["bench"] = d["bench"].to_numpy()
    keys = pv.ladder_keys(cfg)
    lr = pv.l_rel(d, metric)
    out = pd.Series(0.0, index=d.index)
    for c in cutoffs:
        tr, te = (d["cutoff"] < c), (d["cutoff"] == c)
        if not te.any():
            continue
        out[te] = pv.assign(keys[te], pv.fit(keys[tr], lr[tr]))["ln_f"]
    return out


# ---- steps -----------------------------------------------------------------------------------------------------------
def step_fit(d: pd.DataFrame, links: pd.DataFrame, metric: str, n_boot: int, out: Path, tag: str) -> dict[str, Any]:
    par = pc.parents(links, drilled=True)
    ctrl = pc.control_mask(d, links)
    lr = pc.l_rel(d, metric, ctrl)
    sp = pc.single_frame(d, par, lr)
    st = pc.fit_stages(sp)
    c2 = pc.check_c2(sp, n_boot=n_boot)
    res: dict[str, Any] = {"metric": metric, "n_children": len(d), "n_control": int(ctrl.sum()), "n_single": len(sp), "stage_n": st["n"],
                           "surface": st["surface"].as_dict() if st["surface"] else None, "three": st["three"].as_dict() if st["three"] else None,
                           "c2": {k: v for k, v in c2.items() if k != "fits"}}
    bands = {}
    for which in ("same", "below", "above"):
        n = st["n"][which]
        if n >= pc.MIN_FIT:
            b = pc.curve_band(sp, which, GRID, n_boot=n_boot)
            b["side"] = which
            bands[which] = b
    if bands:
        pd.concat(bands.values(), ignore_index=True).to_csv(out / f"fit_{tag}_{metric}_bands.csv", index=False)
    # C1 bins (the step-2 edges) per side
    c1 = {}
    for which, b in bands.items():
        col, edges = ("dh_ft", pdz.DH_EDGES) if which == "same" else ("dv_ft", pdz.DV_EDGES)
        m = (sp["side"] == which) if which == "same" else ((sp["side"] == which) & (sp["dh_ft"] <= pc.STACK_DH_MAX_FT))
        rows = []
        for lo, hi in pairwise(edges):
            mm = m & (sp[col] >= lo) & (sp[col] < hi)
            rows.append({"lo_ft": lo, "hi_ft": hi, "n": int(mm.sum()), "effect": float(np.exp(sp.loc[mm, "l_rel"].mean())) if mm.any() else np.nan})
        bins = pd.DataFrame(rows)
        bins["side"] = which
        bins.to_csv(out / f"fit_{tag}_{metric}_bins_{which}.csv", index=False)
        c1[which] = pc.check_c1(b, bins)
    res["c1"] = c1
    sp.to_csv(out / f"fit_{tag}_{metric}_single.csv.gz", index=False, compression="gzip")
    res["_model"] = st["three"] if c2["surface_fails"] else st["surface"]
    res["_sp"], res["_lr"], res["_par"] = sp, lr, par
    return res


def step_contest(d: pd.DataFrame, fit: dict[str, Any], n_boot: int, out: Path, tag: str) -> dict[str, Any]:
    two = pc.two_parent_frame(d, fit["_par"], fit["_lr"], fit["_model"])
    res = pc.contest(two, n_boot=n_boot)
    two.to_csv(out / f"contest_{tag}_children.csv.gz", index=False, compression="gzip")
    if len(res["table"]):
        res["table"].to_csv(out / f"contest_{tag}.csv", index=False)
    return {k: v for k, v in res.items() if k != "table"}


def step_validate(d: pd.DataFrame, links: pd.DataFrame, n_boot: int, out: Path, tag: str) -> dict[str, Any]:
    res = {}
    parts = []
    for m in METRICS:
        if f"l_{m}" not in d.columns:
            continue
        cuts = pc.TEST_CUTOFFS[m]
        inc = incumbent_ln_f(d, links, m, cuts)
        p, fits = pc.walk_forward(d, links, m, cuts, ln_f_inc=inc, n_boot=n_boot)
        if not len(p):
            continue
        s = pc.score(p, n_boot=n_boot)
        s["cells"].to_csv(out / f"validate_{tag}_{m}_cells.csv", index=False)
        res[m] = {k: v for k, v in s.items() if k != "cells"} | {"folds": fits}
        parts.append(p.assign(metric=m))
    if parts:
        pd.concat(parts, ignore_index=True).to_csv(out / f"validate_{tag}_children.csv.gz", index=False, compression="gzip")
    return res


def step_sticks(d: pd.DataFrame, pud: pd.DataFrame, fit: dict[str, Any], rule: str, out: Path, tag: str) -> dict[str, Any]:
    model = fit["_model"]
    rf = pc.rule_factor(d, fit["_par"], model, rule)
    mix = pc.f_mix(d[pc.MIX_KEY].to_numpy(), rf["F_rule"].to_numpy())
    groups = pud.drop_duplicates("child").set_index("child")["child_bench"].astype(str).to_dict()
    st = pc.sticks(pud, model, rule, mix, groups)
    drilled = pd.DataFrame({"pattern": rf["pattern"].to_numpy(), "n_parents": rf["n_parents"].to_numpy(), "nearest_d_eff": rf["nearest_d_eff"].to_numpy()})
    support = pc.g4_support(drilled)
    st["g4"] = pc.g4_outcome(st, support)
    st.to_csv(out / f"sticks_{tag}.csv.gz", index=False, compression="gzip")
    support.to_csv(out / f"sticks_{tag}_g4_support.csv", index=False)
    fb = pd.cut(st["factor"], [0, 0.8, 0.9, 0.95, 1.0001], labels=["<0.80", "0.80-0.90", "0.90-0.95", ">=0.95"], right=False)
    npb = pd.cut(st["n_parents"], [-1, 0, 1, 2, 10_000], labels=["0", "1", "2", "3+"])
    table = pd.crosstab(npb, fb)
    table.to_csv(out / f"sticks_{tag}_table.csv")
    return {"n_sticks": len(st), "rule": rule, "f_mix": mix, "by_parents_x_factor": {str(k): {str(c): int(v) for c, v in r.items()} for k, r in table.iterrows()},
            "g4": st["g4"].value_counts().to_dict(), "mean_factor": float(st["factor"].mean()), "mean_factor_uncapped": float(st["factor_uncapped"].mean())}


def run_basin(basin: str, d: pd.DataFrame, links: pd.DataFrame, pud: pd.DataFrame, n_boot: int, out: Path, steps: set[str]) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    tag = basin
    rep: dict[str, Any] = {"basin": basin, "digest": pc.digest(), "n_boot": n_boot, "built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")}
    fit = step_fit(d, links, pc.METRIC, n_boot, out, tag)
    rep["fit"] = {k: v for k, v in fit.items() if not k.startswith("_")}
    if "fit" in steps:
        for m in ("oil12", "oil36"):   # C4: F_min / d50 by horizon
            if f"l_{m}" in d.columns:
                f = step_fit(d, links, m, max(50, n_boot // 10), out, tag)
                rep["fit"][f"c4_{m}"] = f["surface"]
    rule = pc.RULE_DEFAULT
    if "contest" in steps:
        rep["contest"] = step_contest(d, fit, n_boot, out, tag)
        rule = rep["contest"]["winner"]
    if "validate" in steps:
        rep["validate"] = step_validate(d, links, n_boot, out, tag)
    if "sticks" in steps:
        rep["sticks"] = step_sticks(d, pud, fit, rule, out, tag)
    (out / f"summary_{tag}.json").write_text(json.dumps(rep, indent=2, default=_json), encoding="utf-8")
    return rep


def _json(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pc.Curve | pc.Model):
        return o.as_dict() if hasattr(o, "as_dict") else vars(o)
    return str(o)


# ---- smoke -----------------------------------------------------------------------------------------------------------
def synthetic_basin(seed: int = 11, n: int = 3000) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """A made-up basin: children over six cutoffs, 0-3 parents each from a known surface, R3 combination, controls at 1."""
    rng = np.random.default_rng(seed)
    truth = pc.Model(pc.Curve(0.78, 900.0, 3.0), 1.6, 2.4)
    cutoffs = [f"{y}-12-01" for y in range(2019, 2025)]
    kids = pd.DataFrame({"api10": [f"w{i:05d}" for i in range(n)], "bench": rng.choice(["WCA", "WCB_1", "BS3_S"], n), "basin": "x",
                         "cutoff": rng.choice(cutoffs, n), "block": rng.integers(0, 120, n)})
    kids["bench_group"] = kids["bench"]
    rows, lf = [], np.zeros(n)
    for i in range(n):
        k = rng.choice([0, 1, 2, 3], p=[0.45, 0.30, 0.18, 0.07])
        fs, sides = [], []
        for j in range(k):
            side = rng.choice(["same", "below", "above"], p=[0.6, 0.2, 0.2])
            dh = rng.uniform(150, 2600) if side == "same" else rng.uniform(0, 1500)
            dz = rng.uniform(-150, 150) if side == "same" else rng.uniform(160, 950) * (1 if side == "below" else -1)
            dxy = dh * rng.choice([-1.0, 1.0])
            rel = "parent" if rng.random() < 0.85 else "codev"
            age = int(rng.integers(400, 3000)) if rel == "parent" else int(rng.integers(-180, 180))
            rows.append({"child": kids.at[i, "api10"], "parent": f"p{i}_{j}", "child_bench": kids.at[i, "bench"], "parent_bench": kids.at[i, "bench"], "cls": "same",
                         "rel": rel, "age_days": age, "dz_ft": dz, "dv_ft": abs(dz), "dh_ft": dh, "overlap": rng.uniform(0.3, 1.0), "permit": False,
                         "shielded": False, "dxy_ft": dxy, "parent_cum_bbl_per_kft": rng.uniform(5, 80)})
            if rel == "parent" and abs(dz) <= 1000 and dh <= 2640:
                fs.append(float(truth.factor(np.array([dh]), np.array([dz]), np.array([side]))[0]))
                sides.append(pc.axis_side(np.array([side]), np.array([dxy]))[0])
        lf[i] = np.log(pc.combine(np.array(fs), np.array(sides, dtype=object), "R3")) if fs else 0.0
    bias = {b: v for b, v in zip(["WCA", "WCB_1", "BS3_S"], [0.05, -0.08, 0.0], strict=True)}
    for m, sd in (("oil24", 0.30), ("oil12", 0.32), ("oil36", 0.35), ("gas24", 0.45)):
        kids[f"l_{m}"] = lf + kids["bench"].map(bias).to_numpy() + rng.normal(0, sd, n)
    links = pd.DataFrame(rows)
    pud = links.sample(frac=0.4, random_state=1).copy()
    pud["child"] = "s" + pud["child"].str[1:]
    pud["rel"] = "parent"
    return kids, links, pud


def smoke(out: Path, n_boot: int = 60) -> dict[str, Any]:
    kids, links, pud = synthetic_basin()
    return run_basin("smoke", kids, links, pud, n_boot, out, {"fit", "contest", "validate", "sticks"})


# ---- CLI -------------------------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("smoke", "run"))
    ap.add_argument("--basin", choices=("delaware", "midland"))
    ap.add_argument("--views", type=Path, default=Path("runs") / "prox" / "views")
    ap.add_argument("--runs", type=Path, default=Path("runs") / "prox")
    ap.add_argument("--midland-children", type=Path, default=Path("docs") / "box" / "step21b-2026-11-01" / "prox_children.csv.gz")
    ap.add_argument("--runs-midland", type=Path, default=Path("runs") / "step21a")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--boot", type=int, default=pc.N_BOOT)
    ap.add_argument("--steps", default="fit,contest,validate,sticks")
    a = ap.parse_args(argv)
    if a.cmd == "smoke":
        out = a.out or Path("runs") / "prox_cont_smoke"
        rep = smoke(out, n_boot=min(a.boot, 100))
        print(json.dumps({"digest": rep["digest"], "surface": rep["fit"]["surface"], "c2": rep["fit"]["c2"], "contest": rep.get("contest", {}).get("winner"),
                          "beta": rep.get("contest", {}).get("beta", {}).get("all"), "verdict_oil24": rep.get("validate", {}).get("oil24", {}).get("verdict"),
                          "sticks": rep.get("sticks", {}).get("by_parents_x_factor")}, indent=1, default=_json))
        print(f"wrote {out}")
        return 0
    if not a.basin:
        ap.error("--basin is required for run")
    sha = gate_check()
    out = a.out or (Path("docs") / "box" / "prox-continuous-2026-11-02")
    steps = set(a.steps.split(","))
    if a.basin == "delaware":
        d, links, pud, meta = load_delaware(a.views, a.runs)
    else:
        d, links, pud, meta = load_midland(a.midland_children, a.runs_midland)
    rep = run_basin(a.basin, d, links, pud, a.boot, out, steps)
    rep["frozen_sha"], rep["inputs"] = sha, meta
    (out / f"summary_{a.basin}.json").write_text(json.dumps(rep, indent=2, default=_json), encoding="utf-8")
    print(json.dumps({k: rep[k] for k in ("basin", "digest", "frozen_sha")}, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
