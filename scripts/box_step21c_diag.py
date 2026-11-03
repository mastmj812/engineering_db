"""BOX step 21c FAIL diagnosis (reported only, never gating, never re-tuning): reads the files `scripts.box_step21c judge` wrote.

    python -m scripts.box_step21c_diag [--docs docs/box/step21c-2026-11-02]

1. diag_shift.csv — per judged cell, the holdout-minus-tuning shift of BOX next to the same shift of the local-offsets benchmark
   (the 7a pattern: a shift both carry is the holdout packages differing, not BOX).
2. diag_null_group.csv — how many FAILs a holdout statistically like tuning would give. The frozen intervals ARE the spread of
   20 % block draws of the tuning packages (`rehearse9b.consistency`), so a cell lands outside by chance ~5 % of the time, and 21b
   reported per group the share of draws passing every judged cell ("consistency passes a good forecast", `summary_table.csv`).
   Expected FAILs with no real difference = sum of (1 - that share); the chance of at least the observed count is the
   Poisson-binomial tail over groups (groups treated as independent).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

DOCS = Path("docs/box/step21c-2026-11-02")


def tail_at_least(p: list[float], m: int) -> float:
    """P(at least m successes) for independent Bernoulli(p_i) (Poisson-binomial)."""
    dist = np.zeros(len(p) + 1)
    dist[0] = 1.0
    for q in p:
        dist[1:] = dist[1:] * (1 - q) + dist[:-1] * q
        dist[0] *= 1 - q
    return float(dist[m:].sum())


def main(docs: Path) -> int:
    pc = pd.read_csv(docs / "pooled_cells.csv")
    dis = pd.read_csv(docs / "disclosure.csv")
    tun = dis[dis.side == "tuning"].rename(columns={"bench": "group", "n_packages": "n_tuning"})[["group", "stream", "horizon", "n_tuning"]]
    tp = pd.read_csv(docs / "pooled_tuning_21b.csv")
    rows = []
    for r in pc.merge(tun, on=["group", "stream", "horizon"], how="left").itertuples():
        var = r.treatment.split(" oil / ")[0 if r.stream == "oil" else 1].replace(" gas", "")
        b = tp[(tp.group == r.group) & (tp.variant == var) & (tp.stream == r.stream) & (tp.horizon == r.horizon)]
        bench_t = float(b["bench_bias"].iloc[0]) if len(b) else np.nan
        rows.append({"group": r.group, "stream": r.stream, "horizon": r.horizon, "treatment": var, "inside_interval": r.inside_interval,
                     "box_tuning": r.tuning_bias, "box_holdout": r.holdout_bias, "box_shift": r.holdout_bias - r.tuning_bias,
                     "bench_tuning": bench_t, "bench_holdout": r.bench_bias, "bench_shift": r.bench_bias - bench_t,
                     "n_tuning": int(r.n_tuning), "n_holdout": int(r.packages)})
    d = pd.DataFrame(rows)
    d[["group", "stream", "horizon", "treatment", "inside_interval", "box_tuning", "box_holdout", "box_shift", "bench_tuning",
       "bench_holdout", "bench_shift"]].to_csv(docs / "diag_shift.csv", index=False)
    st21b = pd.read_csv(docs.parents[0] / "step21b-2026-11-01" / "summary_table.csv").set_index("group")
    g = d.groupby("group", sort=False).agg(cells=("stream", "size"), outside=("inside_interval", lambda s: int((~s.astype(bool)).sum()))).reset_index()
    g["pass_rate_good_forecast_21b"] = g["group"].map(st21b["consistency passes a good forecast"])
    g["fail"] = g["outside"] > 0
    g.to_csv(docs / "diag_null_group.csv", index=False)
    p = (1.0 - g["pass_rate_good_forecast_21b"]).tolist()
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(d.round(3).to_string())
        print(g.to_string())
        print(f"Midland: {int(g['fail'].sum())} FAIL groups of {len(g)} ({int(g['outside'].sum())} of {int(g['cells'].sum())} cells outside); "
              f"expected with no real difference {sum(p):.2f} groups (~{0.05 * g['cells'].sum():.1f} cells); "
              f"P(>= {int(g['fail'].sum())} FAILs | none) = {tail_at_least(p, int(g['fail'].sum())):.4f}")
    return 0


def d105_raw(docs: Path) -> int:
    """disclosure_provisional_r2p.csv — the D105 lines on raw `mid_r2p` (what §6 ships for a provisional group) for the groups whose
    record carried a walk-forward stream (judge wrote its disclosure on the record treatment). Same views, factor and bootstrap as
    the judge; reported only — the verdicts in verdicts.json are not recomputed."""
    import json
    import pickle

    from box import provisional as pv
    from box import step21 as st
    from box import step21b as sb
    from scripts import box_step21b_score as sc
    from scripts import box_step21c as c

    V = json.loads((docs / "verdicts.json").read_text(encoding="utf-8"))["groups"]
    todo = [g for g, x in V.items() if x["tier"] == "provisional" and st.PROX_WF in x["record"].values()]
    table = pd.read_csv(c.run_root() / "reproduce_docs" / "prox_factor_table.csv")
    with open(c.tuning_root() / "prox.pkl", "rb") as fh:
        kc = pickle.load(fh)["kc"]
    out = []
    for g in todo:
        sides = {}
        for side, views in (("tuning", sc.load_group(c.tuning_root(), g)["views"]), ("holdout", c.load_views(c.run_root() / g, g, c.htag(g))["views"])):
            sb.add_prox(views, sb.record_factor(sb.child_frame(sb.frames(views), kc, g), table).to_dict(), st.PROX)
            sides[side] = pv.package_frame(sb.frames(views), st.PROX)
        pk_b = pd.concat([sides["tuning"].assign(pkg="t:" + sides["tuning"]["pkg"]), sides["holdout"].assign(pkg="h:" + sides["holdout"]["pkg"])],
                         ignore_index=True)
        for side, pk in (*sides.items(), ("tuning + holdout", pk_b)):
            out.append(pv.disclosure(pk, g).assign(side=side, treatment=st.PROX))
    d = pd.concat(out, ignore_index=True)
    d = d[d.horizon <= 36]
    d.to_csv(docs / "disclosure_provisional_r2p.csv", index=False)
    with pd.option_context("display.width", 250):
        print(d.round(3).to_string())
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", type=Path, default=DOCS)
    ap.add_argument("--d105-raw", action="store_true", help="the D105 lines on raw mid_r2p for provisional groups whose record carried wf")
    a = ap.parse_args()
    raise SystemExit(d105_raw(a.docs) if a.d105_raw else main(a.docs))
