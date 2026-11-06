"""Score the rule v5 class cards (read-only) — docs/formation_tag_redesign/RULE_V5.md, "Verdict counting".

    python -m scripts.tag_v5_score --cards docs/formation_tag_redesign/v5-cards-2026-11-06
    python -m scripts.tag_v5_score --cards <round-1 folder> <round-2 folder>   # pooled; outputs land in the LAST folder

Counting, declared before any verdict: a bench code in the same UNIT as the proposed one agrees on the unit (the
sub-bench is recorded separately); a code in another unit, or 'reject...', counts against; 'agree' agrees; blank or
free text is a hold, never counted. The class decision is the gate of record, box.tag_screen.decide (5/5 accepts,
so few that 10 cards cannot reach 7/10 rejects, else round 2 tops up to 10).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import tag_precedence as tp
from box import tag_screen as ts


def unit_verdict(basin: str, proposed: str, text: object) -> tuple[str, str | None]:
    """(count, sub-bench) for one card: count is 'agree' / 'reject' / '' (hold); sub-bench is the reviewer's code when it
    agrees on the unit but names a different bench, else None."""
    v = "" if text is None or (isinstance(text, float) and np.isnan(text)) else str(text).strip()
    c = ts.clear_verdict(v, proposed)
    if c == "reject" and v and not v.lower().startswith("reject"):  # a bench code: judge it on the unit
        same = tp.unit(basin, v) is not None and tp.unit(basin, v) == tp.unit(basin, proposed)
        return ("agree", v) if same else ("reject", None)
    return c, None


def score(cards: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = cards.copy()
    res = [unit_verdict(b, p, t) for b, p, t in zip(c["basin"], c["proposed"], c["verdict"], strict=True)]
    c["count"], c["subbench"] = [r[0] for r in res], [r[1] for r in res]
    c["check_agrees"] = c["check"].str.startswith("agrees")
    c["check_read"] = ~c["check"].str.startswith("no plain-median")
    g = c.groupby(["class_no", "class", "class_wells"], sort=True)
    cls = g.agg(cards=("card", "size"), agree=("count", lambda s: int((s == "agree").sum())),
                against=("count", lambda s: int((s == "reject").sum())), holds=("count", lambda s: int((s == "").sum())),
                subbench_differs=("subbench", lambda s: int(s.notna().sum()))).reset_index()
    cls["judged"] = cls["agree"] + cls["against"]
    cls["decision"] = [ts.decide(a, j, n) for a, j, n in zip(cls["agree"], cls["judged"], cls["class_wells"], strict=True)]
    cls["cards_to_add"] = [max(ts.card_target(d, n) - j, 0) if d in ("round 2", "pending") else 0
                           for d, j, n in zip(cls["decision"], cls["judged"], cls["class_wells"], strict=True)]
    return c, cls


def run(folders: list[Path]) -> dict:
    folder = folders[-1]
    cards = pd.concat([pd.read_csv(f / "cards_sample.csv", dtype={"api10": str}) for f in folders], ignore_index=True)
    if cards["api10"].duplicated().any() or cards["card"].duplicated().any():
        raise SystemExit("a well or card number appears in more than one round")
    known = set(tp.UNIT["delaware"]) | {u for o in tp.UNIT_ORDER.values() for u in o} | set(cards["live"]) | set(cards["proposed"])
    bad = ts.unknown_bench_codes(cards["verdict"], known)
    if bad:
        raise SystemExit(f"verdicts that look like bench codes but are not: {bad}")
    c, cls = score(cards)
    c.to_csv(folder / "cards_scored.csv", index=False)
    cls.to_csv(folder / "class_decisions.csv", index=False)
    j = c[c["count"] != ""]
    pre = j.groupby(np.where(~j["check_read"], "no read", np.where(j["check_agrees"], "check agrees", "check disagrees")))["count"].agg(
        judged="size", agree=lambda s: int((s == "agree").sum()))
    s = {"cards": len(c), "judged": len(j), "agree": int((j["count"] == "agree").sum()),
         "classes": cls.to_dict("records"), "precheck_vs_verdict": pre.reset_index(names="precheck").to_dict("records"),
         "wells_in_accepted_classes": int(cls.loc[cls["decision"] == "accept", "class_wells"].sum()),
         "wells_in_rejected_classes": int(cls.loc[cls["decision"] == "reject", "class_wells"].sum())}
    (folder / "score.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cards", type=Path, nargs="+", required=True)
    a = ap.parse_args(argv)
    print(json.dumps(run(a.cards), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
