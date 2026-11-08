"""Score the rule v5.1 sub-bench cards (read-only) — docs/formation_tag_redesign/RULE_V5_1.md, Acceptance (full review).

    python -m scripts.tag_v5_1_score --cards docs/formation_tag_redesign/v5_1-cards-<date>

Each card decides only its own well: agree / accept (a trailing comment is kept, not read) applies the proposed
sub-bench; reject keeps the v5 code; a bench code is Michael's call on the well; any other text is a hold (v5 code kept,
listed). An optional clarifications.csv (card, api10, verdict, verdict_source) replaces a card's verdict with what the
reviewer said he meant, for when the marked file cannot be edited (verdict_marked keeps the original). Writes cards_scored.csv (final_code per
well) and score.json into the cards folder.
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
_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def read_verdict(text: object, proposed: str, v5: str) -> tuple[str, str]:
    """(outcome, final_code): outcome is agree / reject / call / hold."""
    v = "" if text is None or (isinstance(text, float) and np.isnan(text)) else str(text).strip()
    if _ACCEPT.match(v):
        return "agree", proposed
    if v.lower().startswith("reject"):
        return "reject", v5
    if _CODE.match(v) and v not in ("ACCEPT", "AGREE", "REJECT"):
        return ("agree" if v == proposed else "call"), v
    return "hold", v5


def score(cards: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    c = cards.copy()
    out = [read_verdict(t, p, v) for t, p, v in zip(c["verdict"], c["proposed"], c["v5"], strict=True)]
    c["outcome"], c["final_code"] = [o for o, _ in out], [f for _, f in out]
    c["comment"] = [str(t).split(".", 1)[1].strip() if isinstance(t, str) and "." in t else "" for t in c["verdict"]]
    c["move"] = c["v5"] + " -> " + c["proposed"]
    c["check_agrees"] = c["check"].str.startswith("agrees")
    by_move = c.groupby("move")["outcome"].value_counts().unstack(fill_value=0)
    by_check = c.groupby("check_agrees")["outcome"].value_counts().unstack(fill_value=0)
    s = {"cards": len(c), "outcomes": c["outcome"].value_counts().to_dict(),
         "by_move": by_move.to_dict("index"), "by_precheck_agrees": {str(k): v for k, v in by_check.to_dict("index").items()},
         "applied": int((c["final_code"] != c["v5"]).sum()),
         "comments": c.loc[c["comment"] != "", ["card", "api10", "comment"]].to_dict("records")}
    return c, s


def run(folder: Path) -> dict:
    cards = pd.read_csv(folder / "cards_sample.csv", dtype={"api10": str, "verdict_source": str})
    cards["verdict_marked"] = cards["verdict"]
    cl = folder / "clarifications.csv"
    if cl.exists():
        k = pd.read_csv(cl, dtype={"api10": str}).set_index("card")
        hit = cards["card"].isin(k.index)
        if (cards.loc[hit, "api10"].to_numpy() != k.loc[cards.loc[hit, "card"], "api10"].to_numpy()).any():
            raise SystemExit("clarifications.csv: card / api10 mismatch")
        cards.loc[hit, "verdict"] = cards.loc[hit, "card"].map(k["verdict"])
        cards.loc[hit, "verdict_source"] = cards.loc[hit, "card"].map(k["verdict_source"])
    c, s = score(cards)
    c.to_csv(folder / "cards_scored.csv", index=False)
    (folder / "score.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cards", type=Path, required=True)
    a = ap.parse_args(argv)
    print(json.dumps(run(a.cards), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
