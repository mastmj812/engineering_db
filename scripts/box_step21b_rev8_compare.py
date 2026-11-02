"""BOX step 21b — revision 8 realized vs revision 7 and vs the §8 projection (read-only, DB-free, TUNING views only).

The §8 diagnostic projected revision 8 as an exact splice of the revision-7 twins: the Delaware-panel twin where the target is
longer than its cohort's mean lateral, the Midland-panel record otherwise. The harness then re-fits each variant's calendar
factor F(k) on its seeded training sample (box/acceptance, frozen behaviour), so the realized record differs from the splice
by one constant per cutoff x stream x horizon. This script scores the three side by side on the same packages, with the same
class / PUD-mix weighting as the diagnostic (`scripts/box_step21b_lateral_diag`), and refuses any D52 holdout row.

    python -m scripts.box_step21b_rev8_compare --r7 runs/step21b_r7 --r8 runs/step21b

Outputs: docs/box/step21b-2026-11-01/rev8_vs_rev7/ (by_class.csv, weighted.csv, pooled.csv, by_group.csv).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import step21 as st
from scripts import box_step21b_lateral_diag as ld

R7 = "revision 7 record (Midland panel)"
PROJ = "revision 8 projected (diagnostic splice)"
R8 = "revision 8 realized (record)"
DE = "Delaware panel twin"
NAMES = (R7, PROJ, R8, DE)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--r7", type=Path, default=Path("runs") / "step21b_r7")
    ap.add_argument("--r8", type=Path, default=Path("runs") / "step21b")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step21b-2026-11-01" / "rev8_vs_rev7")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    d7, d8 = ld.load(a.r7), ld.load(a.r8)
    key = ["group", "cutoff", "api10"]
    if not (d7[key].astype(str).to_numpy() == d8[key].astype(str).to_numpy()).all():
        raise RuntimeError("revision 7 and revision 8 views are not the same wells in the same order")
    if not np.allclose(d7["lat_ratio"], d8["lat_ratio"], equal_nan=True):
        raise RuntimeError("lat_ratio moved between revisions")

    def preds(k: int) -> dict[str, pd.Series]:
        return {R7: d7[f"pred_mid_r2_oil{k}"], PROJ: ld.hybrid(d7, k), R8: d8[f"pred_mid_r2_oil{k}"], DE: d8[f"pred_mid_r2_cuide_oil{k}"]}

    d = d8  # actuals, packages, classes are identical in both
    cls = pd.concat([ld.class_bias(d, preds(k), k) for k in ld.H], ignore_index=True)

    sb = pd.read_csv(st.DOCS / "sticks_by_length.csv")
    w = {c: float(sb[list(col)].to_numpy().sum()) if isinstance(col, tuple) else float(sb[col].sum()) for c, col in ld.STICK_COLS.items()}
    tot = sum(w.values())
    mix = pd.DataFrame({"class": list(w), "share": [v / tot for v in w.values()]})
    wt = []
    for k in ld.H:
        x = cls[cls["horizon"] == k].merge(mix, on="class")
        ref = x.set_index("class").loc["10,000-12,500"]
        long_ = x["class"].isin(ld.LABELS[4:])
        for n in NAMES:
            wt.append({"horizon": k, "option": n, "stick-weighted bias": float((x[n] * x["share"]).sum()),
                       "stick-weighted |bias - 10-12.5k class|": float(((x[n] - ref[n]).abs() * x["share"]).sum()),
                       ">= 15,000 ft bias (stick-weighted)": float((x[n] * x["share"])[long_].sum() / x["share"][long_].sum())})

    pooled, by_group = [], []
    for k in ld.H:
        for n, p in preds(k).items():
            pe = ac.package_errors(d.assign(_p=p), "pkg", f"actual_oil{k}", "_p")
            pooled.append({"horizon": k, "option": n, "packages": len(pe), "pooled oil package bias": float(pe["err"].mean())})
            for g, x in d.assign(_p=p).groupby("group"):
                pg = ac.package_errors(x, "pkg", f"actual_oil{k}", "_p")
                by_group.append({"group": g, "horizon": k, "option": n, "packages": len(pg), "oil package bias": float(pg["err"].mean())})
    out = {"by_class": cls, "weighted": pd.DataFrame(wt), "pooled": pd.DataFrame(pooled), "by_group": pd.DataFrame(by_group)}
    for name, df in out.items():
        df.to_csv(a.out / f"{name}.csv", index=False)
    pd.set_option("display.width", 250)
    for name, df in out.items():
        print(f"== {name}\n{df.round(4).to_string(index=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
