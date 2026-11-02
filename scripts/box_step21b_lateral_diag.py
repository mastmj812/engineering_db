"""BOX step 21b — long-lateral diagnostic (read-only, DB-free, TUNING views only; asked by Michael 2026-11-02 at gate 21b).

Question: why `mid_r2` (Cui MIDLAND panel, revision 7) over-forecasts oil on >= 15,000-ft laterals by ~11-13 % (FINDINGS §1 Q6) when
21a read per-ft oil as flat with length, and what each translation option would do on the PUD length mix.

1. Masking test. Per-ft cum-12 oil vs lateral two ways: across the basin (bench x cutoff fixed effects only: 21a's read) and
   within the well's own analog neighbourhood (the error of the LINEAR twin vs ln(lat_ratio), group x cutoff fixed effects:
   the cohort is local, so location drops out). Plus the local rock (mean year-1 oil per 1,000 ft within 3 mi) by length class.
2. Options by completed-lateral class, pooled package bias (D53 grain; packages = the class's members): Midland panel (record),
   Delaware panel and linear (the harness twins, exact), and a fitted power law E(L) = (L / 5,000)^e. Alternatives to the
   twins are emulated as pred_lin x E(L) / E(L / lat_ratio); the emulator is validated against both exact twins first.
   e is cross-fitted on 3-mi holdout-grid blocks (fit on odd blocks, score even, and back) so the fitted option is not scored
   in-sample.
3. The 21a PUD length mix (`sticks_by_length.csv`): stick-weighted class bias per option.

Nothing here touches the D52 holdout: rows with package_held_out are refused. Outputs: docs/box/step21b-2026-11-01/lateral_diag/.
"""

from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import basin as bsn
from box import dev_factor_report as dfr
from box import holdout as hd
from box import lateral as lat
from box import step21 as st

CLASSES = [0, 7500, 10000, 12500, 15000, 17500, 1e9]
LABELS = ["5,000-7,500", "7,500-10,000", "10,000-12,500", "12,500-15,000", "15,000-17,500", ">= 17,500"]
STICK_COLS = {"5,000-7,500": "sticks_5-7.5k", "7,500-10,000": "sticks_7.5-10k", "10,000-12,500": "sticks_10-12.5k",
              "12,500-15,000": "sticks_12.5-15k", "15,000-17,500": "sticks_15-17.5k", ">= 17,500": ("sticks_17.5-20k", "sticks_>=20k")}
H = (12, 24, 36)


def load(run: Path) -> pd.DataFrame:
    frames = []
    for f in sorted(glob.glob(str(run / "MID_*" / "view_tuning_v2_*_analog_*.csv.gz"))):
        if "_plain" in Path(f).parent.name:
            continue
        v = pd.read_csv(f, dtype={"api10": str}, low_memory=False)
        held = v["package_held_out"].astype(str).str.lower().isin(("true", "1"))
        if held.any():
            raise RuntimeError(f"{f}: {int(held.sum())} D52 holdout rows in a tuning view")
        v["group"] = Path(f).parent.name
        frames.append(v)
    d = pd.concat(frames, ignore_index=True)
    d["pkg"] = d["group"] + ":" + d["cutoff"].astype(str) + ":" + d["package"].astype(str)
    d["lat_ratio"] = pd.to_numeric(d["mid_r2_lat_ratio"], errors="coerce")
    d["L"] = pd.to_numeric(d["lateral_ft"], errors="coerce")
    d["cls"] = pd.cut(d["L"], CLASSES, labels=LABELS, right=False)
    bx, by = hd.blocks(*dfr._xy(d["mid_lon"], d["mid_lat"]))  # the D52 3-mi grid (ids only; membership unused)
    d["blk"] = [f"{i}_{j}" for i, j in zip(bx, by, strict=True)]
    d["blk_parity"] = (np.asarray(bx) + np.asarray(by)) % 2 == 1
    return d


def e_cui(x: np.ndarray, basin: str) -> np.ndarray:
    return np.array([lat.lateral_efficiency(float(v), basin=basin) for v in x])


def emulate(d: pd.DataFrame, law, k: int) -> pd.Series:
    """pred_lin x E(L) / E(L / lat_ratio): the cohort's mean lateral recovered from the ratio, mean E ~ E(mean)."""
    lm = d["L"] / d["lat_ratio"]
    return d[f"pred_mid_r2_lin_oil{k}"] * law(d["L"].to_numpy()) / law(lm.to_numpy())


HYBRID = "hybrid (Midland shorter / Delaware longer)"


def hybrid(d: pd.DataFrame, k: int) -> pd.Series:
    """Designed AFTER reading this table (tuning only; untested on the holdout): the Delaware-panel twin where the target is
    longer than its cohort's mean lateral (lat_ratio > 1), the Midland-panel record otherwise. Both pieces are exact twins."""
    return pd.Series(np.where(d["lat_ratio"] > 1, d[f"pred_mid_r2_cuide_oil{k}"], d[f"pred_mid_r2_oil{k}"]), index=d.index)


def by_ratio(d: pd.DataFrame, k: int) -> pd.DataFrame:
    """Within each completed-lateral class, package bias by target / cohort-mean lateral (the mismatch the translation bridges)."""
    rb = pd.cut(d["lat_ratio"], [0, 0.8, 1.0, 1.25, 1.5, 99], labels=["< 0.8", "0.8-1.0", "1.0-1.25", "1.25-1.5", ">= 1.5"])
    rows = []
    for c in LABELS:
        for b in rb.cat.categories:
            m = (d["cls"] == c) & (rb == b)
            if m.sum() < 40:
                continue
            r = {"class": c, "lat_ratio": b, "horizon": k, "wells": int(m.sum()), "cohort mean lateral p50": float((d["L"] / d["lat_ratio"])[m].median())}
            for name, col in (("Midland panel (record)", f"pred_mid_r2_oil{k}"), ("Delaware panel", f"pred_mid_r2_cuide_oil{k}")):
                pe = ac.package_errors(d[m], "pkg", f"actual_oil{k}", col)
                r[f"{name} pkgs"], r[name] = len(pe), float(pe["err"].mean())
            rows.append(r)
    return pd.DataFrame(rows)


def class_bias(d: pd.DataFrame, pred: dict[str, pd.Series], k: int) -> pd.DataFrame:
    rows = []
    for c in LABELS:
        m = d["cls"] == c
        r = {"class": c, "horizon": k, "wells": int((m & d[f"actual_oil{k}"].notna()).sum())}
        for name, p in pred.items():
            x = d[m].assign(_p=p[m])
            pe = ac.package_errors(x, "pkg", f"actual_oil{k}", "_p")
            r[f"{name} pkgs"], r[name] = len(pe), (float(pe["err"].mean()) if len(pe) else np.nan)
        rows.append(r)
    return pd.DataFrame(rows)


def fit_e(d: pd.DataFrame, k: int) -> float:
    """Elasticity of per-ft oil to lateral WITHIN the neighbourhood: ln(actual / pred_lin) on ln(lat_ratio), group x cutoff FE."""
    x = d[[f"actual_oil{k}", f"pred_mid_r2_lin_oil{k}", "lat_ratio", "group", "cutoff"]].dropna()
    x = x[(x[f"actual_oil{k}"] > 0) & (x[f"pred_mid_r2_lin_oil{k}"] > 0) & (x["lat_ratio"] > 0)]
    y = np.log(x[f"actual_oil{k}"] / x[f"pred_mid_r2_lin_oil{k}"])
    z = np.log(x["lat_ratio"])
    fe = x["group"] + x["cutoff"].astype(str)
    y, z = y - y.groupby(fe).transform("mean"), z - z.groupby(fe).transform("mean")
    return float((y * z).sum() / (z * z).sum())


def basin_slope(d: pd.DataFrame, k: int, fe_cols: list[str]) -> tuple[float, int]:
    x = d[[f"actual_oil{k}", "L", *fe_cols]].dropna()
    x = x[(x[f"actual_oil{k}"] > 0) & (x["L"] > 0)]
    y = np.log(x[f"actual_oil{k}"] / x["L"])
    z = np.log(x["L"])
    fe = x[fe_cols].astype(str).agg("|".join, axis=1)
    y, z = y - y.groupby(fe).transform("mean"), z - z.groupby(fe).transform("mean")
    return float((y * z).sum() / (z * z).sum()), len(x)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=Path("runs/step21b"))
    ap.add_argument("--out", type=Path, default=Path("docs/box/step21b-2026-11-01/lateral_diag"))
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    d = load(a.run)
    print(f"[diag] {len(d):,} tuning wells, {d['pkg'].nunique():,} packages; holdout rows: 0 (refused if present)")

    # 1. masking: the basin-wide read vs within-neighbourhood
    lines = []
    for k in (12, 24):
        s_raw, n_raw = basin_slope(d, k, ["group", "cutoff"])
        s_blk, n_blk = basin_slope(d, k, ["group", "cutoff", "blk"])
        e_in = fit_e(d, k)
        lines.append({"horizon": k, "basin_wide_slope (bench x cutoff FE)": s_raw, "wells": n_raw,
                      "within_3mi_block_slope (+ block FE)": s_blk, "wells_block": n_blk, "within_cohort_elasticity (lat_ratio)": e_in})
    mask = pd.DataFrame(lines)
    rock = (d.assign(local=pd.to_numeric(d["local_y1_kft"], errors="coerce"), oil12_ft=d["actual_oil12"] / d["L"] * 1000)
             .groupby("cls", observed=True).agg(wells=("api10", "size"), local_rock_y1_kft=("local", "median"),
                                                actual_oil12_kft=("oil12_ft", "median"), cutoff_2022plus=("cutoff", lambda s: (s.astype(str) >= "2022-12-01").mean()))
             .reset_index())
    rock["actual_over_local_rock"] = rock["actual_oil12_kft"] / rock["local_rock_y1_kft"]

    # 2. emulator check against the exact twins
    chk = []
    for k in H:
        for name, basin, col in (("Delaware panel", bsn.DELAWARE, f"pred_mid_r2_cuide_oil{k}"), ("Midland panel", bsn.MIDLAND, f"pred_mid_r2_oil{k}")):
            em = emulate(d, lambda x, b=basin: e_cui(x, b), k)
            r = (em / d[col]).replace([np.inf, -np.inf], np.nan).dropna()
            chk.append({"horizon": k, "law": name, "wells": len(r), "median |emulated / exact - 1|": float((r - 1).abs().median()),
                        "p95 |emulated / exact - 1|": float((r - 1).abs().quantile(0.95))})
    chk_df = pd.DataFrame(chk)

    # cross-fitted power law on 3-mi blocks
    half = d["blk_parity"]
    tabs, efit = [], {}
    for k in H:
        e_a, e_b = fit_e(d[half], k), fit_e(d[~half], k)
        efit[k] = {"fit on odd blocks": e_a, "fit on even blocks": e_b, "all": fit_e(d, k)}
        pf = pd.Series(np.nan, index=d.index)
        for m, e in ((~half, e_a), (half, e_b)):  # score each half with the other half's elasticity
            pf[m] = emulate(d[m], lambda x, e=e: (np.maximum(x, 5000.0) / 5000.0) ** e, k)
        pred = {"Midland panel (record)": d[f"pred_mid_r2_oil{k}"], "Delaware panel": d[f"pred_mid_r2_cuide_oil{k}"],
                "linear": d[f"pred_mid_r2_lin_oil{k}"], "fitted power law (cross-fit)": pf, HYBRID: hybrid(d, k)}
        tabs.append(class_bias(d, pred, k))
    opt = pd.concat(tabs, ignore_index=True)

    # 3. the PUD length mix (21a sticks_by_length.csv)
    sb = pd.read_csv(st.DOCS / "sticks_by_length.csv")
    w = {}
    for c, col in STICK_COLS.items():
        w[c] = float(sb[list(col)].to_numpy().sum()) if isinstance(col, tuple) else float(sb[col].sum())
    tot = sum(w.values())
    mix = pd.DataFrame({"class": list(w), "sticks": list(w.values()), "share": [v / tot for v in w.values()]})
    names = ["Midland panel (record)", "Delaware panel", "linear", "fitted power law (cross-fit)", HYBRID]
    wt = []
    for k in H:
        x = opt[opt["horizon"] == k].merge(mix, on="class")
        ref = x.set_index("class").loc["10,000-12,500"]
        for n in names:
            rel = x[n] - ref[n]
            wt.append({"horizon": k, "option": n, "stick-weighted bias": float((x[n] * x["share"]).sum()),
                       "stick-weighted |bias - 10-12.5k class|": float((rel.abs() * x["share"]).sum()),
                       ">= 15,000 ft bias (stick-weighted)": float((x[n] * x["share"])[x["class"].isin(LABELS[4:])].sum() / x["share"][x["class"].isin(LABELS[4:])].sum())})
    wtd = pd.DataFrame(wt)

    pooled = []
    for k in H:
        for n, p in (("Midland panel (record)", d[f"pred_mid_r2_oil{k}"]), ("Delaware panel", d[f"pred_mid_r2_cuide_oil{k}"]), (HYBRID, hybrid(d, k))):
            pe = ac.package_errors(d.assign(_p=p), "pkg", f"actual_oil{k}", "_p")
            pooled.append({"horizon": k, "option": n, "packages": len(pe), "pooled oil package bias": float(pe["err"].mean())})
    ratio = pd.concat([by_ratio(d, k) for k in H], ignore_index=True)
    for name, df in {"pooled_all_lengths": pd.DataFrame(pooled), "by_lat_ratio": ratio, "masking": mask, "rock_by_length": rock, "emulator_check": chk_df, "options_by_class": opt, "pud_length_mix": mix,
                     "options_weighted": wtd, "elasticity_fit": pd.DataFrame(efit).T.rename_axis("horizon").reset_index()}.items():
        df.to_csv(a.out / f"{name}.csv", index=False)
    pd.set_option("display.width", 250)
    for name, df in (("masking", mask), ("rock", rock), ("emulator", chk_df), ("elasticity", pd.DataFrame(efit).T), ("options", opt), ("mix", mix), ("weighted", wtd)):
        print(f"== {name}\n{df.round(4).to_string(index=name == 'elasticity')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
