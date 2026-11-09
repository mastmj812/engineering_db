"""Rule v5 development run (read-only) — docs/formation_tag_redesign/RULE_V5.md.

    python -m scripts.tag_precedence_dev --cache <scoreboard cache> --out docs/formation_tag_redesign/v5-dev-<date>

Reports the learned precedence table, the churn against today's tag, the change classes (what would be carded), the
guards, and what happens to the sql/23-corrected wells. It computes no labelled-set score and draws no cards.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd
import shapely

from box import tag_precedence as tp
from box import tag_scoreboard as sb
from scripts.tag_surface_density import wells_frame


def build(cache: Path, rule: tp.V5 = tp.RULE) -> tuple[pd.DataFrame, pd.DataFrame]:
    w = wells_frame(cache).assign(api10=lambda x: x["api10"].astype(str))
    w = w.rename(columns={"vendor": "sql16"})
    w["evidence"] = True  # wells_frame keeps clean evidence wells only
    w["sql23_code"] = w["live"].where(w["live_source"] == "tvd_corrected")
    v = pd.read_pickle(cache / "vendors.pkl").assign(api10=lambda x: x["api10"].astype(str))[["api10", "novi_raw", "env_raw", "novi_code", "env_code"]]
    d, table = tp.assign(w.merge(v, on="api10", how="left"), rule)
    ovr = pd.read_csv(sb.OVERRIDE_SEED, dtype={"api10": str}).set_index("api10")["corrected_code"]
    d["override"] = d["api10"].map(ovr)
    d["final"] = d["override"].where(d["override"].notna(), d["v5"])
    ex = pd.read_pickle(cache / "extents.pkl")
    d["in_box_extents"] = False
    for b, g in ex.groupby("basin"):
        geom = shapely.union_all([shapely.from_wkt(t) for t in g["wkt"]])
        m = (d["basin"] == b).to_numpy()
        d.loc[m, "in_box_extents"] = shapely.contains_xy(geom, d.loc[m, "x"].to_numpy(), d.loc[m, "y"].to_numpy())
    return d, table


def run(cache: Path, out: Path, rule: tp.V5 = tp.RULE) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d, table = build(cache, rule)
    d.to_pickle(cache / "producers_v5.pkl")
    table.sort_values(["basin", "decided"], ascending=[True, False]).round(3).to_csv(out / "precedence_table.csv", index=False)
    d["changes"] = d["final"].fillna("~") != d["live"].fillna("~")
    d["unit_changes"] = [tp.unit(b, a) != tp.unit(b, c) for b, a, c in zip(d["basin"], d["live"], d["final"], strict=True)]
    churn = d.groupby("basin").agg(wells=("api10", "size"), changes=("changes", "sum"), unit_changes=("unit_changes", "sum"))
    churn["changes_pct"] = 100 * churn["changes"] / churn["wells"]
    churn.to_csv(out / "churn.csv")
    d.groupby(["basin", "case", "basis"], dropna=False).size().rename("n").reset_index().to_csv(out / "by_case_basis.csv", index=False)
    ch = d[d["changes"]]
    cls = ch.groupby(["basin", "live", "final", "basis"]).agg(wells=("api10", "size"), in_extents=("in_box_extents", "sum")).reset_index()
    cls.sort_values("wells", ascending=False).to_csv(out / "change_classes.csv", index=False)
    s23 = d[d["live_source"] == "tvd_corrected"]
    s23_t = s23.groupby(["basin", "basis"]).agg(wells=("api10", "size"), keeps_sql23_tag=("changes", lambda c: int((~c).sum()))).reset_index()
    s23_t.to_csv(out / "sql23_corrected_wells.csv", index=False)
    s = {"rule": {**tp.rule_record(), "rule": asdict(rule)}, "wells": len(d), "churn": churn.reset_index().to_dict("records"),
         "basis": d.groupby(["basin", "basis"]).size().unstack(fill_value=0).to_dict("index"),
         "flags": d.groupby(["basin", "flag"]).size().unstack(fill_value=0).to_dict("index"),
         "learned_patterns": int(table["winner"].notna().sum()),
         "change_classes_ge_20": int((cls["wells"] >= 20).sum()), "wells_in_classes_ge_20": int(cls.loc[cls["wells"] >= 20, "wells"].sum()),
         "sql23_corrected": {"wells": len(s23), "kept": int((~s23["changes"]).sum())}}
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: s[k] for k in ("churn", "basis", "flags", "learned_patterns", "change_classes_ge_20", "wells_in_classes_ge_20",
                                         "sql23_corrected")}, indent=1, default=str))
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pattern-key", choices=("unit", "string"), default=tp.RULE.pattern_key)
    a = ap.parse_args(argv)
    run(a.cache, a.out, replace(tp.RULE, pattern_key=a.pattern_key))
    return 0


if __name__ == "__main__":
    sys.exit(main())
