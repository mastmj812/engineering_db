"""Rule v5 as ACCEPTED by the class cards, and the reported (not gating) checks (read-only) — RULE_V5.md, Acceptance.

    python -m scripts.tag_v5_accepted --cache <scoreboard cache> --cards <r1 folder> <r2 folder> --out <folder>

The accepted tag per producer:
  - a well Michael carded takes his call (a bench code verbatim; 'agree' = the proposed code; a hold = its class's outcome);
  - else a well in an ACCEPTED change class takes v5's code;
  - else today's live tag (rejected classes, classes under 20 wells, and every well v5 leaves unchanged).
Reports: churn, label reproduction (live vs accepted; not blind), the step-A landing-surface crossing area with live vs
accepted tags (same method, same extents), sql/23 corrections kept, and the unresolved list ("neither vendor" first).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import tag_precedence as tp
from box import tag_scoreboard as sb
from box import tag_screen as ts
from scripts import tag_landing_crossings as lc
from scripts.tag_surface_density import wells_frame
from scripts.tag_v5_cards import class_label


def class_decisions(folders: list[Path]) -> pd.DataFrame:
    """Every round's class decisions, one row per class; a later folder (a later round) wins."""
    fs = [f / "class_decisions.csv" for f in folders if (f / "class_decisions.csv").exists()]
    if not fs:
        raise SystemExit("no class_decisions.csv in the card folders")
    return pd.concat([pd.read_csv(f) for f in fs], ignore_index=True).drop_duplicates("class", keep="last")


def accepted_tags(d: pd.DataFrame, cards: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    d["label"] = [class_label(*k) for k in zip(d["basin"], d["live"], d["final"], d["basis"], strict=True)]
    acc = set(decisions.loc[decisions["decision"] == "accept", "class"])
    changes = d["final"].fillna("~") != d["live"].fillna("~")
    in_acc = changes & d["label"].isin(acc)
    d["accepted"] = np.where(in_acc, d["final"], d["live"])
    d["accepted_basis"] = np.where(in_acc, "class_accepted", np.where(changes, "class_not_accepted", "unchanged"))
    v = cards.dropna(subset=["verdict"]).copy()
    v["verdict"] = v["verdict"].astype(str).str.strip()
    v["call"] = np.where(v["verdict"].str.lower().isin(ts.AGREE_WORDS), v["proposed"], v["verdict"])  # ACCEPT = agree
    is_code = v["call"].str.fullmatch(r"[A-Z0-9_]+") & ~v["call"].str.startswith("REJECT")
    calls = v[is_code].set_index("api10")["call"]
    m = d["api10"].isin(calls.index)
    d.loc[m, "accepted"] = d.loc[m, "api10"].map(calls)
    d.loc[m, "accepted_basis"] = "carded_call"
    return d


def crossings(w: pd.DataFrame, ex: pd.DataFrame, tag: str) -> dict:
    ww = w.copy()
    ww["live"] = ww[tag]
    surf, _ = lc.build_surfaces(ww, ex)
    pt, _ = lc.pair_table(surf, sb.bench_order())
    adj = pt[pt["benches_apart"] == 1]
    return {b: {"adjacent_shared_sqmi": round(float(g["shared_sqmi"].sum())), "adjacent_crossing_sqmi": round(float(g["crossing_sqmi"].sum())),
                "adjacent_crossing_pct": round(100 * float(g["crossing_sqmi"].sum() / g["shared_sqmi"].sum()), 2),
                "adjacent_merged_sqmi": round(float(g["merged_sqmi"].sum())),
                "nonadjacent_crossing_sqmi": round(float(pt[(pt["basin"] == b) & (pt["benches_apart"] > 1)]["crossing_sqmi"].sum()))}
            for b, g in adj.groupby("basin")}, pt


def run(cache: Path, folders: list[Path], out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = pd.read_pickle(cache / "producers_v5.pkl")
    cards = pd.concat([pd.read_csv(f / "cards_sample.csv", dtype={"api10": str}) for f in folders], ignore_index=True)
    decisions = class_decisions(folders)
    a = accepted_tags(d, cards, decisions)
    a["changes"] = a["accepted"].fillna("~") != a["live"].fillna("~")
    a["unit_changes"] = [tp.unit(b, x) != tp.unit(b, y) for b, x, y in zip(a["basin"], a["live"], a["accepted"], strict=True)]
    cols = ["api10", "basin", "county", "live", "v5", "final", "accepted", "accepted_basis", "basis", "flag", "depth_ft", "z_novi", "z_env",
            "novi_raw", "env_raw", "in_box_extents"]
    a[a["changes"]][[c for c in cols if c in a]].to_csv(out / "accepted_changes.csv", index=False)
    churn = a.groupby("basin").agg(wells=("api10", "size"), changes=("changes", "sum"), unit_changes=("unit_changes", "sum"),
                                   in_extents=("in_box_extents", lambda s: int(s[a.loc[s.index, "changes"]].sum())))
    by_basis = a[a["changes"]].groupby(["basin", "accepted_basis"]).size().unstack(fill_value=0)
    labels = sb.labelled_set()
    ls_live, ls_acc = sb.label_score(a, "live", labels), sb.label_score(a, "accepted", labels)
    lab = ls_live.merge(ls_acc, on=["tier", "basin", "n"], suffixes=("_live", "_accepted"))
    lab.to_csv(out / "label_reproduction.csv", index=False)
    unres = a[a["basis"] == "unresolved"].copy()
    unres["neither"] = (unres["depth_ft"] - unres["z_novi"]).abs().gt(300) & (unres["depth_ft"] - unres["z_env"]).abs().gt(300)
    unres = unres.sort_values(["neither", "in_box_extents", "basin"], ascending=[False, False, True])
    unres[[c for c in cols + ["neither"] if c in unres]].to_csv(out / "unresolved.csv", index=False)
    s23 = a[a["live_source"] == "tvd_corrected"]
    # step-A crossing area, live vs accepted, same method
    w = wells_frame(cache).assign(api10=lambda x: x["api10"].astype(str))
    w = w.merge(a[["api10", "accepted"]], on="api10", how="left")
    w["accepted"] = w["accepted"].where(w["accepted"].notna(), w["live"])
    ex = pd.read_pickle(cache / "extents.pkl")
    lc.WELLS_XY = w[["api10", "x", "y"]]
    cx_live, pt_live = crossings(w, ex, "live")
    cx_acc, pt_acc = crossings(w, ex, "accepted")
    pt_live.merge(pt_acc, on=["basin", "upper", "lower", "benches_apart"], how="outer", suffixes=("_live", "_accepted")).to_csv(
        out / "crossing_pairs_live_vs_accepted.csv", index=False)
    s = {"churn": churn.reset_index().to_dict("records"), "changes_by_basis": by_basis.to_dict("index"),
         "label_reproduction": lab.to_dict("records"),
         "unresolved": {"wells": len(unres), "neither_vendor": int(unres["neither"].sum()), "in_extents": int(unres["in_box_extents"].sum())},
         "sql23_corrected": {"wells": len(s23), "kept": int((s23["accepted"] == s23["live"]).sum())},
         "crossings_live": cx_live, "crossings_accepted": cx_acc}
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    return s


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
