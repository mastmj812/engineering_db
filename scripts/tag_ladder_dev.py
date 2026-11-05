"""Rule v4 (ladder) development run, read-only — docs/formation_tag_redesign/RULE_V4.md §2 step 2.

    python -m scripts.tag_ladder_dev --cache <scoreboard cache> --out docs/formation_tag_redesign/v4-dev-<date>

Reports churn (all wells), guards, basis / flag / confidence counts and the rung tables. It deliberately computes NO
labelled-set score, NO grid agreement and NO test-fold number. Writes `producers_v4.pkl` to the cache for the cards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from box import tag_ladder as tl
from box import tag_rule as tr
from box import tag_scoreboard as sb
from scripts import tag_rule_dev as dev


def build(cache: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    w = pd.read_pickle(cache / "wells.pkl")
    st = pd.read_pickle(cache / "stations.pkl")
    v = pd.read_pickle(cache / "vendors.pkl")[["api10", "novi_code", "env_code", "novi_raw", "env_raw"]]
    order = sb.bench_order()
    d = dev.prepare(w).merge(v, on="api10", how="left")
    pairs = dev.rule_pairs(d)
    grid = dev.grid_for(d, st, order)
    res, rungs = tl.run_producers(d, pairs, order, grid)
    d = d.join(res)
    d["rule"] = d["code"]
    ovr = pd.read_csv(sb.OVERRIDE_SEED, dtype={"api10": str}).set_index("api10")["corrected_code"]
    d["override"] = d["api10"].map(ovr)
    d["final"] = d["override"].where(d["override"].notna(), d["rule"])
    return d, rungs


def run(cache: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d, rungs = build(cache)
    d.to_pickle(cache / "producers_v4.pkl")
    rungs.to_csv(out / "rungs.csv", index=False)
    vf = pd.Series([tr.family(b, c) for b, c in zip(d["basin"], d["vendor"], strict=True)], index=d.index)
    rf = pd.Series([tr.family(b, c) for b, c in zip(d["basin"], d["rule"], strict=True)], index=d.index)
    mv = d["rule"].fillna("~") != d["vendor"].fillna("~")
    s: dict = {"rule": tl.rule_record(), "wells": len(d)}
    churn = d.assign(code_moved=mv, fam_moved=vf != rf, vs_live=d["final"].fillna("~") != d["live"].fillna("~")) \
        .groupby("basin")[["code_moved", "fam_moved", "vs_live"]].sum()
    churn["wells"] = d.groupby("basin").size()
    churn.to_csv(out / "churn.csv")
    s["churn"] = churn.reset_index().to_dict("records")
    s["guards"] = {
        "protected": int((mv & (d["vendor"].isin(tr.PROTECTED) | d["rule"].isin(tr.PROTECTED))).sum()),
        "lithology": int(sum(mv & pd.Series([any({a, b} <= p for p in tr.LITH_PAIRS) for a, b in zip(d["vendor"], d["rule"], strict=True)], index=d.index))),
        "xy_lea_ward": int((mv & d["county"].isin(tr.RULE_B_COUNTIES)
                            & pd.Series([tr._crosses_xy(b, a, c) for b, a, c in zip(d["basin"], vf, rf, strict=True)], index=d.index)).sum()),
        "off_column_moved": int((mv & ~pd.Series([c in sb.bench_order().get(b, []) for b, c in zip(d["basin"], d["vendor"], strict=True)], index=d.index)).sum()),
    }
    d[mv].groupby(["basin", "vendor", "rule"]).size().rename("n").reset_index().sort_values("n", ascending=False).to_csv(out / "moves_from_to.csv", index=False)
    for c in ("basis", "flag", "anchor_used"):
        d.groupby(["basin", c], dropna=False).size().rename("n").reset_index().to_csv(out / f"by_{c}.csv", index=False)
    d[d["evidence"]].assign(fam=rf).groupby(["basin", "fam", "confidence"]).size().unstack(fill_value=0).to_csv(out / "confidence_by_family.csv")
    s["witness_share"] = d.groupby("basin")["witness"].mean().round(3).to_dict()
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: s[k] for k in ("churn", "guards", "witness_share")}, indent=1, default=str))
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.cache, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
