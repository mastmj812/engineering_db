"""Build the tag rule's seed files from the reviewed card folders — docs/formation_tag_redesign/WAREHOUSE_STEP.md, W2.

    python -m scripts.tag_rule_seeds --write     # regenerate the four seeds
    python -m scripts.tag_rule_seeds --check     # exit 1 if any committed seed differs from what the folders give

Every human decision the rule review produced lands in a repo-reviewed seed (policy and human calls are never learned
or written by the nightly):

  seeds/formation_tag_overrides.csv         human calls: every carded verdict with a code, as its own block (notes
                                            start "tagrule "); the older rows are kept verbatim
  seeds/formation_tag_depth_exclusions.csv  SUSPECT TVD verdicts (Q5): the depth judged and its source
  seeds/formation_tag_policy.csv            Step 1 frozen winners (policy v1 = box/policy/step1_patterns_v1.csv)
  seeds/formation_tag_class.csv             every decided change class (Step 1 rounds, Step 3 class A)

Verdict reading (one rule for every card set): ACCEPT / agree -> the proposal; a bench code -> that code; REJECT -> the
card's input (Step 3) or today's tag (Step 1); SUSPECT TVD -> a depth exclusion; anything else -> a hold (no row).
A later card set wins for a well carded twice; clarifications.csv replaces a card's verdict.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

from box import tag_scoreboard as sb

DOCS = sb.ROOT / "docs" / "formation_tag_redesign"
SEEDS = sb.ROOT / "seeds"
OVERRIDES = SEEDS / "formation_tag_overrides.csv"
EXCLUSIONS = SEEDS / "formation_tag_depth_exclusions.csv"
POLICY = SEEDS / "formation_tag_policy.csv"
CLASSES = SEEDS / "formation_tag_class.csv"
POLICY_SRC = sb.ROOT / "box" / "policy" / "step1_patterns_v1.csv"
POLICY_VERSION = 1
BLOCK = "tagrule "
UNMAPPED = "(unmapped)"

# Card sets in the order they were reviewed (a later set wins for a well carded twice), with the step they judged.
CARD_SETS: list[tuple[str, int]] = [
    ("v5-cards-2026-11-06", 1), ("v5-cards-r2-2026-11-06", 1), ("v5_1-cards-2026-11-06", 2),
    ("v5_2-cards-2026-11-08", 3), ("policy-v1-cards-2026-11-09/step1", 1), ("policy-v1-cards-2026-11-09/step1_round2", 1),
    ("policy-v1-cards-2026-11-09/step3", 3), ("w1-queue-cards-2026-11-09", 3), ("shadow1-queue-cards-2026-11-11", 3),
    ("shadow1-direct-calls-2026-11-11", 3),
]
STEP1_DECISIONS = ["v5-cards-2026-11-06", "v5-cards-r2-2026-11-06", "policy-v1-cards-2026-11-09/step1",
                   "policy-v1-cards-2026-11-09/step1_round2"]
STEP3_SCORE = "v5_2-cards-2026-11-08"
_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_CLASS = re.compile(r"^(?P<basin>\w+) (?P<frm>\S+)->(?P<to>\S+) \((?P<basis>\w+)\)$")
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def read(text: object, proposed: str, keep: object) -> tuple[str, object]:
    """(kind, code) for one verdict: kind is call / exclusion / hold."""
    v = text.strip() if isinstance(text, str) else ""
    head = v.split(".", 1)[0].strip()
    low = head.lower()
    if low in ("agree", "accept", "accepted"):
        return "call", proposed
    if low.startswith(("suspect tvd", "suspect depth")):
        return "exclusion", None
    if low.startswith("reject"):
        return "call", keep
    if _CODE.match(head):
        return "call", head
    return "hold", None


def cards() -> pd.DataFrame:
    rows = []
    for order, (s, step) in enumerate(CARD_SETS):
        f = DOCS / s
        c = pd.read_csv(f / "cards_sample.csv", dtype={"api10": str})
        clar = {}
        if (f / "clarifications.csv").exists():
            k = pd.read_csv(f / "clarifications.csv", dtype={"api10": str})
            clar = dict(zip(k["api10"], k["verdict"], strict=True))
        for r in c.to_dict("records"):
            today = r.get("live")
            today = today if isinstance(today, str) else None
            keep = r.get("input") if step == 3 else today
            text = clar.get(r["api10"], r["verdict"])
            kind, code = read(text, r["proposed"], keep)
            rows.append({"api10": r["api10"], "set": s, "step": step, "order": order, "card": int(r["card"]),
                         "date": _DATE.search(s).group(1), "today": today, "proposed": r["proposed"],
                         "verdict": text if isinstance(text, str) else "", "kind": kind,
                         "code": code if isinstance(code, str) else None})
    d = pd.DataFrame(rows).sort_values(["api10", "order"], kind="stable")
    return d.drop_duplicates("api10", keep="last").reset_index(drop=True)


def overrides(c: pd.DataFrame) -> pd.DataFrame:
    old = pd.read_csv(OVERRIDES, dtype=str, keep_default_na=False)
    old = old[~old["note"].str.startswith(BLOCK)]
    clash = set(old["api10"]) & set(c["api10"])
    if clash:
        raise SystemExit(f"carded wells already carry an older override: {sorted(clash)}")
    calls = c[(c["kind"] == "call") & c["code"].notna()]
    new = pd.DataFrame({
        "api10": calls["api10"], "corrected_code": calls["code"], "was": calls["today"].fillna(""),
        "note": [f"{BLOCK}carded {r.date} {r.set} card {r.card} (Step {r.step}): "
                 f"{r.verdict.split('.', 1)[0].strip()} on proposed {r.proposed}" for r in calls.itertuples()]})
    return pd.concat([old, new.sort_values("api10")], ignore_index=True)


def exclusions(c: pd.DataFrame) -> pd.DataFrame:
    ex = pd.read_csv(DOCS / STEP3_SCORE / "depth_exclusions.csv", dtype={"api10": str})
    want = set(c.loc[c["kind"] == "exclusion", "api10"])
    if set(ex["api10"]) != want:
        raise SystemExit(f"depth_exclusions.csv != SUSPECT TVD verdicts: {sorted(set(ex['api10']) ^ want)}")
    return pd.DataFrame({"api10": ex["api10"], "depth_ft": ex["depth_ft"], "depth_source": ex["depth_source"],
                         "tag_kept": ex["tag_kept"], "card": [f"{STEP3_SCORE} card {k}" for k in ex["card"]],
                         "note": ex["decided"]}).sort_values("api10").reset_index(drop=True)


def policy() -> pd.DataFrame:
    p = pd.read_csv(POLICY_SRC)
    p.insert(0, "policy_version", POLICY_VERSION)
    return p


def classes() -> pd.DataFrame:
    rows: dict[tuple, dict] = {}
    for s in STEP1_DECISIONS:
        for r in pd.read_csv(DOCS / s / "class_decisions.csv").to_dict("records"):
            m = _CLASS.match(r["class"])
            if not m:
                raise SystemExit(f"unparsed class label in {s}: {r['class']}")
            rows[(1, m["basin"], m["frm"], m["to"], m["basis"])] = {
                "step": 1, "basin": m["basin"], "from_code": m["frm"], "to_code": m["to"], "basis": m["basis"],
                "decision": r["decision"], "agree": int(r["agree"]), "judged": int(r["judged"]),
                "class_wells": int(r["class_wells"]), "card_set": s}
    sc = json.loads((DOCS / STEP3_SCORE / "score.json").read_text(encoding="utf-8"))
    for label, v in sc["classes"].items():
        basin, rest = label.split(" ", 1)
        frm, to = (x.strip() for x in rest.split("->"))
        rows[(3, basin, frm, to, "gm_move")] = {
            "step": 3, "basin": basin, "from_code": frm, "to_code": to, "basis": "gm_move",
            "decision": "accept" if v["accepted"] else "reject", "agree": int(v["agree"]), "judged": int(v["cards"]),
            "class_wells": None, "card_set": STEP3_SCORE}
    out = pd.DataFrame(list(rows.values()))
    out = out[out["decision"].isin(["accept", "reject"])].copy()
    out["class_wells"] = out["class_wells"].astype("Int64")
    return out.sort_values(["step", "basin", "from_code", "to_code", "basis"]).reset_index(drop=True)


def build() -> dict[Path, pd.DataFrame]:
    c = cards()
    return {OVERRIDES: overrides(c), EXCLUSIONS: exclusions(c), POLICY: policy(), CLASSES: classes()}


def _text(df: pd.DataFrame) -> str:
    return df.to_csv(index=False, lineterminator="\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    bad = []
    for path, df in build().items():
        if a.write:
            path.write_text(_text(df), encoding="utf-8", newline="")
            print(f"wrote {path.relative_to(sb.ROOT)}: {len(df)} rows")
        elif not path.exists() or path.read_text(encoding="utf-8").replace("\r\n", "\n") != _text(df):
            bad.append(str(path.relative_to(sb.ROOT)))
    if bad:
        print("out of date: " + ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
