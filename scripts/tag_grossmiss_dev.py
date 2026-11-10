"""Rule v5.2 (the gross-miss step) development run (read-only) — docs/formation_tag_redesign/RULE_V5_2.md.

    python -m scripts.tag_grossmiss_dev --cache <scoreboard cache> --v5-1-cards docs/formation_tag_redesign/v5_1-cards-2026-11-06 \
        --out docs/formation_tag_redesign/v5_2-dev-<date>

Base tag = the accepted tag WITHOUT sql/23: a human call (override; v5 carded call; v5.1 card's final code) > a
class-accepted v5 code > sql/16's code (pre_sql23). v5.2 judges every non-human evidence producer against it. Reports:
the moves and their classes (what would be carded), what happens to each well sql/23 corrects today (in the evidence
frame, and the ones outside it that no rule judges), the kept/flagged counts by reason, and the step-A crossing area
for live / no-sql23-base / v5.2 (same method, same extents). Draws no cards and computes no labelled-set score.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import tag_grossmiss as gm
from box import tag_precedence as tp
from box import tag_scoreboard as sb
from scripts.tag_surface_density import wells_frame
from scripts.tag_v5_accepted import crossings

MIN_CLASS = 20


def base_frame(cache: Path, v51_cards: Path) -> pd.DataFrame:
    d = pd.read_pickle(cache / "producers_v5_1.pkl")
    d = d.drop(columns=[c for c in d.columns if c.startswith(("z_", "gm_")) and c not in ("z_novi", "z_env")])
    human = d["accepted_basis"] == "carded_call"
    d["base52"] = np.where(human | (d["accepted_basis"] == "class_accepted"), d["accepted"], d["pre_sql23"])
    d["src"] = np.where(human, "carded_call", np.where(d["live_source"] == "ratified_override", "override", None))
    c = pd.read_csv(v51_cards / "cards_scored.csv", dtype={"api10": str}).set_index("api10")["final_code"]
    m = d["api10"].isin(c.index)
    d.loc[m, "base52"], d.loc[m, "src"] = d.loc[m, "api10"].map(c), "carded_call"
    return d


def sql23_outcome(r) -> str:
    if r.src in gm.HUMAN:
        return "human call" + (" = sql/23" if r.gm_code == r.sql23_code else " != sql/23")
    if r.gm_basis == "gm_move":
        return "v5.2 = sql/23" if r.gm_code == r.sql23_code else "v5.2 other bench"
    if r.base52 == r.sql23_code:
        return "v5 class already = sql/23"
    return f"reverts to sql/16 ({r.gm_basis})"


def run(cache: Path, v51_cards: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = gm.assign(base_frame(cache, v51_cards), "base52")
    d.to_pickle(cache / "producers_v5_2.pkl")
    d["changes"] = d["gm_code"].fillna("~") != d["base52"].fillna("~")
    d["vs_live"] = d["gm_code"].fillna("~") != d["live"].fillna("~")
    d["unit_change"] = [tp.unit(b, x) != tp.unit(b, y) for b, x, y in zip(d["basin"], d["base52"], d["gm_code"], strict=True)]
    s23 = d["live_source"] == "tvd_corrected"
    d["sql23_outcome"] = None
    d.loc[s23, "sql23_outcome"] = [sql23_outcome(r) for r in d[s23].itertuples()]
    ch = d[d["changes"]]
    cls = ch.groupby(["basin", "base52", "gm_code"]).agg(
        wells=("api10", "size"), was_sql23=("live_source", lambda s: int((s == "tvd_corrected").sum())),
        in_extents=("in_box_extents", "sum"), median_own_gap_ft=("gm_own_gap_ft", "median"),
        median_target_gap_ft=("gm_target_gap_ft", "median")).reset_index().sort_values("wells", ascending=False)
    cls.to_csv(out / "change_classes.csv", index=False)
    cols = ["api10", "basin", "county", "well_name", "operator", "live", "live_source", "pre_sql23", "sql23_code", "base52", "gm_code",
            "gm_basis", "gm_sub", "gm_own_gap_ft", "gm_target", "gm_target_gap_ft", "gm_lead_ft", "depth_ft", "novi_raw", "env_raw",
            "accepted_basis", "in_box_extents"]
    ch[cols].sort_values(["basin", "base52", "gm_code"]).to_csv(out / "changes.csv", index=False)
    d[s23][cols + ["sql23_outcome"]].sort_values(["sql23_outcome", "basin"]).to_csv(out / "sql23_wells.csv", index=False)
    flagged = d[d["gm_basis"].isin(["gm_unplaced", "gm_inverted", "gm_guard", "gm_no_subbench"])]
    flagged[cols].sort_values(["gm_basis", "basin"]).to_csv(out / "flagged.csv", index=False)
    # sql/23 corrections on wells outside the evidence frame: no rule judges them (planned survey, permit-round depth, < 4,000 ft)
    w_all = sb.evidence_depth(pd.read_pickle(cache / "wells.pkl"), "best")
    w_all["api10"] = w_all["api10"].astype(str)
    outside = w_all[(w_all["live_source"] == "tvd_corrected") & ~w_all["api10"].isin(d["api10"])].copy()
    tvd = pd.to_numeric(outside["tvd_ft"], errors="coerce")
    outside["why"] = np.select([outside["planned"].fillna(False).astype(bool), outside["depth_ft"].isna(),
                                outside["depth_ft"] < sb.MIN_EVIDENCE_TVD_FT, tvd.notna() & (tvd % 100 == 0)],
                               ["planned survey", "no depth", "< 4,000 ft", "permit-round depth"], default="other")
    outside[["api10", "basin", "county", "well_name", "live", "pre_sql23", "tvd_ft", "lat_tvd_p50_ft", "planned", "why"]].to_csv(
        out / "sql23_outside_frame.csv", index=False)
    # step-A crossing area: live / base without sql/23 / v5.2
    w = wells_frame(cache).assign(api10=lambda x: x["api10"].astype(str)).merge(d[["api10", "base52", "gm_code"]], on="api10", how="left")
    for c in ("base52", "gm_code"):
        w[c] = w[c].where(w[c].notna(), w["pre_sql23"])
    ex = pd.read_pickle(cache / "extents.pkl")
    cx = {t: crossings(w, ex, t)[0] for t in ("live", "base52", "gm_code")}
    j = d["src"].isna() & d["evidence"].astype(bool)
    s = {"rule": gm.rule_record(), "wells": len(d), "judged": int(j.sum()),
         "gm_basis": d[j].groupby(["basin", "gm_basis"]).size().unstack(fill_value=0).to_dict("index"),
         "moves": ch.groupby("basin").size().to_dict(), "moves_in_extents": ch[ch["in_box_extents"]].groupby("basin").size().to_dict(),
         "moves_unit_change": int(ch["unit_change"].sum()), "moves_sub": ch["gm_sub"].value_counts().to_dict(),
         "moves_from_other_or_unmapped": int(ch["base52"].isna().sum() + (ch["base52"] == "OTHER").sum()),
         "classes_ge_20": int((cls["wells"] >= MIN_CLASS).sum()), "wells_in_classes_ge_20": int(cls.loc[cls["wells"] >= MIN_CLASS, "wells"].sum()),
         "sql23_in_frame": d.loc[s23, "sql23_outcome"].value_counts().to_dict(),
         "sql23_outside_frame": outside.groupby(["basin", "why"]).size().unstack(fill_value=0).to_dict("index"),
         "changes_vs_live": d[d["vs_live"]].groupby("basin").size().to_dict(),
         "crossings": cx}
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--v5-1-cards", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    print(json.dumps(run(a.cache, a.v5_1_cards, a.out), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
