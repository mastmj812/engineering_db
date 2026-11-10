"""Rule v5.1 (sub-bench step) development run (read-only) — docs/formation_tag_redesign/RULE_V5_1.md.

    python -m scripts.tag_subbench_dev --cache <scoreboard cache> --cards <v5 r1> <v5 r2> --out docs/formation_tag_redesign/v5_1-dev-<date>

Base = the v5 ACCEPTED tags (scripts.tag_v5_accepted: carded call > accepted class > live). Reports placeholder counts,
how many the sub-bench step decides, the change classes (what would be carded), Michael's carded sub-bench calls as a
check, and the step-A crossing area accepted vs v5.1. It computes no labelled-set score and draws no cards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from box import tag_precedence as tp
from box import tag_subbench as ts1
from scripts.tag_surface_density import wells_frame
from scripts.tag_v5_accepted import accepted_tags, class_decisions, crossings

MIN_CLASS = 20


def build(cache: Path, folders: list[Path]) -> pd.DataFrame:
    d = pd.read_pickle(cache / "producers_v5.pkl")
    cards = pd.concat([pd.read_csv(f / "cards_sample.csv", dtype={"api10": str}) for f in folders], ignore_index=True)
    a = accepted_tags(d, cards, class_decisions(folders))
    a["src"] = None
    a.loc[(a["live_source"] == "tvd_corrected") & (a["accepted"] == a["live"]), "src"] = "sql23_kept"
    a.loc[a["override"].notna() & (a["accepted"] == a["live"]), "src"] = "override"
    a.loc[a["accepted_basis"] == "carded_call", "src"] = "carded_call"
    return ts1.assign(a, "accepted")


def run(cache: Path, folders: list[Path], out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = build(cache, folders)
    d.to_pickle(cache / "producers_v5_1.pkl")
    d["changes"] = d["sb_code"].fillna("~") != d["accepted"].fillna("~")
    ph = d[d["placeholder"]]
    by_unit = ph.groupby(["basin", "accepted", "sb_basis"]).size().unstack(fill_value=0)
    by_unit["changes"] = ph.groupby(["basin", "accepted"])["changes"].sum()
    by_unit.to_csv(out / "placeholders_by_code.csv")
    ch = d[d["changes"]]
    cls = ch.groupby(["basin", "accepted", "sb_code"]).agg(wells=("api10", "size"), in_extents=("in_box_extents", "sum"),
                                                          median_lead_ft=("sb_lead_ft", "median")).reset_index()
    cls = cls.sort_values("wells", ascending=False)
    cls.to_csv(out / "change_classes.csv", index=False)
    wit = d[d["wit_code"].notna()].groupby(["basin", "wit_code"]).size().rename("witnesses")
    wit.to_csv(out / "witnesses.csv")
    cols = ["api10", "basin", "county", "well_name", "operator", "live", "accepted", "sb_code", "sb_basis", "sb_lead_ft", "depth_ft",
            "novi_raw", "env_raw", "in_box_extents"] + sorted(c for c in d.columns if c.startswith("z_") and c not in ("z_novi", "z_env"))
    ch[cols].to_csv(out / "changes.csv", index=False)
    # Michael's carded sub-bench calls (not blind: he called these before the rule existed; reported, not tuned)
    cards = pd.concat([pd.read_csv(f / "cards_scored.csv", dtype={"api10": str}) for f in folders if (f / "cards_scored.csv").exists()],
                      ignore_index=True).drop_duplicates("api10", keep="last")
    sub = probe_carded(d, cards)
    sub.to_csv(out / "carded_subbench_check.csv", index=False)
    w = wells_frame(cache).assign(api10=lambda x: x["api10"].astype(str)).merge(d[["api10", "accepted", "sb_code"]], on="api10", how="left")
    for c in ("accepted", "sb_code"):
        w[c] = w[c].where(w[c].notna(), w["live"])
    ex = pd.read_pickle(cache / "extents.pkl")
    cx_acc, pt_acc = crossings(w, ex, "accepted")
    cx_51, pt_51 = crossings(w, ex, "sb_code")
    pt_acc.merge(pt_51, on=["basin", "upper", "lower", "benches_apart"], how="outer", suffixes=("_accepted", "_v5_1")).to_csv(
        out / "crossing_pairs_accepted_vs_v5_1.csv", index=False)
    s = {"wells": len(d), "placeholders": ph.groupby("basin").size().to_dict(),
         "placeholders_in_extents": ph[ph["in_box_extents"]].groupby("basin").size().to_dict(),
         "sb_basis": ph.groupby(["basin", "sb_basis"]).size().unstack(fill_value=0).to_dict("index"),
         "changes": ch.groupby("basin").size().to_dict(), "changes_in_extents": ch[ch["in_box_extents"]].groupby("basin").size().to_dict(),
         "unit_changes": int(sum(tp.unit(b, x) != tp.unit(b, y) for b, x, y in zip(ch["basin"], ch["accepted"], ch["sb_code"], strict=True))),
         "witnesses": {f"{b} {c}": int(n) for (b, c), n in wit.items()},
         "classes_ge_20": int((cls["wells"] >= MIN_CLASS).sum()), "wells_in_classes_ge_20": int(cls.loc[cls["wells"] >= MIN_CLASS, "wells"].sum()),
         "crossings_accepted": cx_acc, "crossings_v5_1": cx_51}
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    return s


def probe_carded(d: pd.DataFrame, cards: pd.DataFrame) -> pd.DataFrame:
    """What v5.1 would write on each carded well that agreed on the unit, had Michael's call not been there (tag = v5's
    proposed code, provenance cleared). Compared with the sub-bench he wrote. Not blind (he called these first)."""
    agree = cards[cards["count"] == "agree"][["api10", "card", "class", "proposed", "verdict"]]
    p = d.drop(columns=[c for c in d.columns if c.startswith("z_") and c not in ("z_novi", "z_env")] + ["placeholder", "wit_code", "sb_code",
                                                                                                       "sb_basis", "sb_lead_ft"])
    p["probe"] = p["final"].where(p["api10"].isin(agree["api10"]))
    p["src"] = None
    q = ts1.assign(p, "probe")
    q = q[q["api10"].isin(agree["api10"])][["api10", "placeholder", "sb_code", "sb_basis", "sb_lead_ft"]]
    return agree.merge(q, on="api10", how="left")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--cards", type=Path, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    print(json.dumps(run(a.cache, a.cards, a.out), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
