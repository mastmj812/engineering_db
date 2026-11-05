"""Development-fold sanity run of the v3 rule (read-only) — step 1 of docs/formation_tag_redesign/PLAN.md.

    python -m scripts.tag_rule_dev --cache <scoreboard cache dir> --out docs/formation_tag_redesign/step1-dev-<date>

Runs box.tag_rule on every producing horizontal and reports ONLY:
  * churn (how many wells move, by basin / basis / flag / from -> to), over all wells, and
  * the band test on DEVELOPMENT-fold subjects (6-mi checkerboard, even cells).
It deliberately does NOT compute the labelled-set score or grid agreement. Those, and every number on the test fold,
are scored once, in step 2, after the rule and criteria are frozen.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import extent_package as pkg
from box import tag_rule as tr
from box import tag_scoreboard as sb
from scripts import tag_scoreboard as sbs

CELL_M = 6 * sb.M_PER_MI


def fold(df: pd.DataFrame) -> np.ndarray:
    """'dev' / 'test' by a 6-mi checkerboard on the lateral's first point (EPSG:3083)."""
    xy = np.array([p[0] if p else (np.nan, np.nan) for p in df["pts"]], float)
    cx, cy = np.floor(xy[:, 0] / CELL_M), np.floor(xy[:, 1] / CELL_M)
    return np.where(np.isfinite(cx) & ((cx + cy) % 2 == 0), "dev", "test")


def prepare(w: pd.DataFrame) -> pd.DataFrame:
    d = sb.evidence_depth(w, "best").reset_index(drop=True)
    d["evidence"] = d["clean"]
    d["vendor"] = d["vendor"].where(d["vendor"].notna(), None)
    d["fold"] = fold(d)
    return d


def rule_pairs(d: pd.DataFrame, r: tr.Rule = tr.RULE) -> pd.DataFrame:
    """Neighbour pairs at the rule's widest radius on 5 points per lateral."""
    thin = d[["basin"]].assign(pts=[p[::2] if len(p) > 2 else p for p in d["pts"]])
    return sb.neighbour_pairs(thin, max(r.fam_radius_mi, r.pos_radius2_mi) * sb.M_PER_MI)


def grid_for(d: pd.DataFrame, st: pd.DataFrame, order: dict[str, list[str]]) -> pd.DataFrame:
    clean = d[d["evidence"]].reset_index(drop=True)
    stations, depths, mid = sbs.grid_frame(clean, st)
    ctrl = sbs.control_distances(mid)
    wells = clean.set_index("api10").loc[mid["api10"], ["basin", "vendor", "county"]]
    g = tr.grid_evidence(stations, depths, wells, order, ctrl, pkg.TRUST_MAX_FT)
    return g.reindex(d["api10"]).reset_index(drop=True)


def run(cache: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    w = pd.read_pickle(cache / "wells.pkl")
    st = pd.read_pickle(cache / "stations.pkl")
    order = sb.bench_order()
    d = prepare(w)
    pairs = rule_pairs(d)
    grid = grid_for(d, st, order)
    res = tr.assign_producers(d, pairs, order, grid)
    d = d.join(res[["family", "family_basis", "family_flag", "rule", "position_basis", "confidence", "position_margin_ft"]])
    d["moved"] = d["rule"].fillna("~") != d["vendor"].fillna("~")
    d["fam_moved"] = [tr.family(b, a) != tr.family(b, c) for b, a, c in zip(d["basin"], d["rule"], d["vendor"], strict=True)]

    summ: dict = {"rule": tr.rule_record(), "wells": len(d), "evidence": int(d["evidence"].sum())}
    churn = d.groupby("basin").agg(wells=("api10", "size"), moved=("moved", "sum"), family_moved=("fam_moved", "sum"))
    churn["moved_pct"] = 100 * churn["moved"] / churn["wells"]
    churn["family_moved_pct"] = 100 * churn["family_moved"] / churn["wells"]
    churn.to_csv(out / "churn_by_basin.csv")
    summ["churn"] = churn.round(2).reset_index().to_dict("records")
    d[d["moved"]].groupby(["basin", "vendor", "rule"]).size().rename("n").reset_index().sort_values("n", ascending=False).to_csv(out / "moves_from_to.csv", index=False)
    d[d["moved"]][["api10", "basin", "county", "vendor", "rule", "family_basis", "position_basis", "confidence",
                   "depth_ft", "fold"]].to_csv(out / "moved_wells.csv", index=False)
    # guards (K10), checked on the dev run too: they are rule properties, not scores
    v_fam = pd.Series([tr.family(b, c) for b, c in zip(d["basin"], d["vendor"], strict=True)], index=d.index)
    r_fam = pd.Series([tr.family(b, c) for b, c in zip(d["basin"], d["rule"], strict=True)], index=d.index)
    mv = d["moved"]
    summ["guards"] = {
        "protected_moves": int((mv & (d["vendor"].isin(tr.PROTECTED) | d["rule"].isin(tr.PROTECTED))).sum()),
        "lithology_swaps": int(sum(mv & pd.Series([any({a, b} <= p for p in tr.LITH_PAIRS) for a, b in zip(d["vendor"], d["rule"], strict=True)], index=d.index))),
        "xy_crossings_lea_ward": int((mv & d["county"].isin(tr.RULE_B_COUNTIES)
                                      & pd.Series([tr._crosses_xy(b, f1, f2) for b, f1, f2 in zip(d["basin"], v_fam, r_fam, strict=True)], index=d.index)).sum()),
    }
    for c in ("family_basis", "family_flag", "position_basis", "confidence"):
        d.groupby(["basin", c], dropna=False).size().rename("n").reset_index().to_csv(out / f"by_{c}.csv", index=False)
    conf = d[d["evidence"]].groupby(["basin", "family", "confidence"]).size().unstack(fill_value=0)
    conf.to_csv(out / "confidence_by_family.csv")

    # band test on the dev fold only (clean subjects; neighbours from the whole clean set)
    clean = d[d["evidence"]].reset_index(drop=True)
    p1 = sb.neighbour_pairs(clean, 1.0 * sb.M_PER_MI)
    devm = clean["fold"].to_numpy() == "dev"
    bt = {}
    for cand in ("vendor", "rule"):
        c = clean.assign(**{cand: clean[cand].fillna("(unmapped)")})
        bands = sb.local_bands(c, cand, p1, sb.DEFAULT.min_band_n)
        f = c.join(sb.band_test(c, cand, bands, order, sb.DEFAULT.margin_ft))
        t = sb.band_table(f[devm], ["basin"])
        bt[cand] = t.set_index("basin")["disagree_pct"].round(2).to_dict()
        sb.band_table(f[devm], ["basin", cand]).query("wells >= 100").to_csv(out / f"dev_band_by_bench_{cand}.csv", index=False)
    summ["dev_fold_band_disagree_pct"] = bt
    summ["dev_fold_wells"] = int(devm.sum())
    (out / "summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summ[k] for k in ("churn", "dev_fold_band_disagree_pct", "dev_fold_wells")}, indent=1, default=str))
    return summ


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.cache, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
