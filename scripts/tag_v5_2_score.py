"""Score the rule v5.2 cards (read-only) — docs/formation_tag_redesign/RULE_V5_2.md, Acceptance.

    python -m scripts.tag_v5_2_score --cards docs/formation_tag_redesign/v5_2-cards-<date> \
        --dev docs/formation_tag_redesign/v5_2r1-dev-<date>

Verdicts (a trailing ". comment" is kept, not read):
  ACCEPT / agree     the proposed code (section C: sql/23's code)
  REJECT             keep the INPUT code (the accepted tag without sql/23)
  a bench code       Michael's call on the well (equal to the proposal = agree)
  SUSPECT TVD        the depth is not trusted: no depth rule may judge the well, so it keeps the INPUT code and is
                     listed as a depth exclusion (evidence off for v5 / v5.2 and as a witness)
  anything else      a hold: the INPUT code is kept, listed

Section A is the class sample: the class (basin, input -> proposed) is accepted at >= 7 of 10 agree; then every well of
the class in the dev run's changes.csv takes the proposal, except a carded well, which takes its own verdict. Sections
B and C decide only their own well. Writes cards_scored.csv, final_v5_2.csv (one row per well that leaves its input
code or is excluded) and score.json into the cards folder.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ACCEPT = re.compile(r"^\s*(agree|accept(ed)?)\b", re.IGNORECASE)
_SUSPECT = re.compile(r"^\s*suspect\s+(tvd|depth)\b", re.IGNORECASE)
_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
PROTECTED = frozenset({"WDFD", "BRNT", "MISS"})
CLASS_N, CLASS_PASS = 10, 7


def _blank(x: object) -> bool:
    return x is None or (isinstance(x, float) and np.isnan(x))


def read_verdict(text: object, proposed: str, inp: object) -> tuple[str, object]:
    """(outcome, final_code): outcome is agree / reject / call / suspect_depth / hold."""
    v = "" if _blank(text) else str(text).strip()
    head = v.split(".", 1)[0].strip()
    if _ACCEPT.match(head):
        return "agree", proposed
    if head.lower().startswith("reject"):
        return "reject", inp
    if _SUSPECT.match(head):
        return "suspect_depth", inp
    if _CODE.match(head) and head not in ("ACCEPT", "AGREE", "REJECT"):
        return ("agree" if head == proposed else "call"), head
    return "hold", inp


def score(cards: pd.DataFrame, changes: pd.DataFrame, extents: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    c = cards.copy()
    out = [read_verdict(t, p, i) for t, p, i in zip(c["verdict"], c["proposed"], c["input"], strict=True)]
    c["outcome"], c["final_code"] = [o for o, _ in out], [f for _, f in out]
    c["comment"] = [str(t).split(".", 1)[1].strip() if isinstance(t, str) and "." in t else "" for t in c["verdict"]]
    c["check_agrees"] = c["check"].str.startswith("agrees")
    inp = c["input"].fillna("(unmapped)")

    a = c[c["section"] == "A"]
    classes = {}
    for (b, i, p), g in a.groupby([a["basin"], inp[a.index], a["proposed"]]):
        n_ok = int((g["outcome"] == "agree").sum())
        need = CLASS_PASS if len(g) >= CLASS_N else len(g)
        classes[f"{b} {i} -> {p}"] = {"cards": len(g), "agree": n_ok, "accepted": n_ok >= need}

    ch = changes.copy()
    ch["input"] = ch["base52"]
    ch_key = ch["basin"] + " " + ch["base52"].fillna("(unmapped)") + " -> " + ch["gm_code"]
    acc = ch[ch_key.map(lambda k: classes.get(k, {}).get("accepted", False))]
    rows = [{"api10": r.api10, "basin": r.basin, "county": r.county, "well_name": r.well_name, "input": r.input,
             "final_code": r.gm_code, "basis": "v5_2_class_accepted", "card": None, "in_box_extents": r.in_box_extents}
            for r in acc.itertuples()]
    fin = pd.DataFrame(rows, columns=["api10", "basin", "county", "well_name", "input", "final_code", "basis", "card",
                                      "in_box_extents"])
    ext = {**(extents or {}), **changes.set_index("api10")["in_box_extents"].to_dict()}
    basis = {"agree": "v5_2_carded_accept", "call": "carded_call", "suspect_depth": "depth_excluded",
             "reject": "carded_reject", "hold": "hold"}
    carded = pd.DataFrame({"api10": c["api10"], "basin": c["basin"], "county": c["county"], "well_name": c["well_name"],
                           "input": c["input"], "final_code": c["final_code"],
                           "basis": [("sql23_" if s == "C" and o == "agree" else "") + basis[o]
                                     for s, o in zip(c["section"], c["outcome"], strict=True)],
                           "card": c["card"], "in_box_extents": c["api10"].map(ext)})
    fin = pd.concat([fin[~fin["api10"].isin(carded["api10"])], carded], ignore_index=True)
    fin["changed"] = fin["final_code"].fillna("~") != fin["input"].fillna("~")

    rule_moves = fin[fin["basis"].isin({"v5_2_class_accepted", "v5_2_carded_accept", "sql23_v5_2_carded_accept"})]
    guard = int((rule_moves["final_code"].isin(PROTECTED) | rule_moves["input"].isin(PROTECTED)).sum())
    by_sec = c.groupby("section")["outcome"].value_counts().unstack(fill_value=0)
    by_chk = c[c["section"] != "C"].groupby("check_agrees")["outcome"].value_counts().unstack(fill_value=0)
    s = {"cards": len(c), "outcomes": c["outcome"].value_counts().to_dict(),
         "by_section": by_sec.to_dict("index"),
         "by_precheck_agrees_AB": {str(k): v for k, v in by_chk.to_dict("index").items()},
         "classes": classes,
         "final": {"wells_changed": int(fin["changed"].sum()),
                   "by_basis": fin.groupby("basis")["changed"].agg(["size", "sum"]).astype(int).to_dict("index"),
                   "by_basin_changed": fin[fin["changed"]]["basin"].value_counts().to_dict(),
                   "in_box_extents_changed": int(fin.loc[fin["changed"], "in_box_extents"].fillna(False).astype(bool).sum()),
                   "depth_excluded": c.loc[c["outcome"] == "suspect_depth", "api10"].tolist(),
                   "holds": c.loc[c["outcome"] == "hold", ["card", "api10", "verdict"]].to_dict("records")},
         "guard": {"rule_moves_into_or_out_of_protected": guard},
         "comments": c.loc[c["comment"] != "", ["card", "api10", "comment"]].to_dict("records")}
    return c, fin, s


def run(folder: Path, dev: Path) -> dict:
    cards = pd.read_csv(folder / "cards_sample.csv", dtype={"api10": str, "verdict_source": str})
    changes = pd.read_csv(dev / "changes.csv", dtype={"api10": str})
    s23 = pd.read_csv(dev / "sql23_wells.csv", dtype={"api10": str})
    c, fin, s = score(cards, changes, s23.set_index("api10")["in_box_extents"].to_dict())
    c.to_csv(folder / "cards_scored.csv", index=False)
    fin.to_csv(folder / "final_v5_2.csv", index=False)
    (folder / "score.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cards", type=Path, required=True)
    ap.add_argument("--dev", type=Path, required=True)
    a = ap.parse_args(argv)
    print(json.dumps(run(a.cards, a.dev), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
