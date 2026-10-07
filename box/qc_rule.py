"""BOX step 1 — the QC rule of record for bench membership (BOX-only, no warehouse change).

Ratified from Michael's 142 card verdicts on 2026-10-07 (docs/box/step1-2026-10-06/VERDICTS.md):

  * Pooling (D19/D20): WCA_1 + WCA_2 + WCXY form the `WCA` evidence pool for steps 2-4; in-pool
    swaps are moot; nothing is ever promoted INTO WCXY.
  * Class gate: a consensus flag is applied only in an ACCEPTED swap class (card precision >= 0.70).
    REJECTED classes (thin boundaries, 0.33-0.40) and HOLD classes (0.60 on five cards; second
    sample pending) keep their tag.
  * Second vote: within an accepted class the flag is applied only when the live sql/23 band audit's
    nearest band concurs with the suggestion.
  * GOR veto (formalised from Michael's tiebreak): when the local cohort GOR separates the two
    benches and the subject produces like its own tag, the flag is not applied.
  * A-prime: a consensus flag on a planned-survey well means the TVD is suspect, not the tag. The tag
    stays as bench evidence; the well is dropped as a depth witness.
  * Bone Spring -> Wolfcamp flags are never applied (0.20): a Bone Spring well at a Wolfcamp depth is
    a TVD defect. The well keeps its tag and is dropped as a depth witness.

Output per well: ``box_bench`` (the evidence bench after the rule, pooled), ``box_action``,
``box_depth_witness`` (usable as depth evidence), ``box_reason``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from box.flag_cards import NEVER_INTO, pool

# Card precision ledger (agree / (agree + reject)), 2026-10-07. Classes are POOLED labels.
ACCEPTED_CLASSES: dict[str, float] = {
    "BS3_S->BS2_S": 1.00,
    "BS3_C->BS2_S": 0.90,
    "OTHER->WCA": 1.00,
    "WCD->WCA": 1.00,
    "WCC->WCA": 0.78,
    "WCB_1->WCA": 0.70,
    "WCB_2->WCA": 0.70,
    "WCA->WCB_2": 1.00,  # 3/3 on real-survey cards; planned-survey cards are A-prime cases
    "WCA->WCC": 1.00,  # 2/2 on real-survey cards
}
REJECTED_CLASSES: dict[str, float] = {
    "WCA->BS3_S": 0.40,
    "BS3_S->WCA": 0.40,
    "WCA->WCB_1": 0.40,
    "BS2_S->BS3_C": 0.33,
    "BS2_S->WCA": 0.20,
}
HOLD_CLASSES: dict[str, float] = {
    "BS2_S->BS1_S": 0.60,
    "BS2_S->BS3_S": 0.60,
}
CLASS_GATE = 0.70

_BONE_SPRING = ("BS", "AVA")
_WOLFCAMP = ("WC",)


def _is_bs_to_wc(from_pool: str, to_pool: str) -> bool:
    return from_pool.startswith(_BONE_SPRING) and to_pool.startswith(_WOLFCAMP)


def decide(row: pd.Series, verdicts: dict[str, str] | None = None) -> tuple[str, str, bool, str]:
    """(box_bench, box_action, box_depth_witness, box_reason) for one scored well.

    ``verdicts`` = Michael's per-card AGREE / REJECT by api10; a card verdict
    outranks the class rule for that well (he judged it individually)."""
    tag = str(row["formation_blueox"])
    tag_pool = pool(tag)
    witness = bool(row.get("cons_witness", False))
    if row.get("cons_status") != "flag" or not isinstance(row.get("cons_suggest"), str):
        return tag_pool, "keep", witness, ""
    sug = str(row["cons_suggest"])
    sug_pool = pool(sug)
    cls = f"{tag_pool}->{sug_pool}"
    if sug in NEVER_INTO:
        return tag_pool, "keep", witness, "flag into WCXY is never applied (D20)"
    if tag_pool == sug_pool:
        return tag_pool, "keep", witness, "in-pool swap, moot for extents (D19)"
    v = (verdicts or {}).get(str(row.get("api10", "")))
    if v == "AGREE":
        return sug_pool, "reassign", witness, f"card verdict AGREE ({cls})"
    if v == "REJECT":
        if _is_bs_to_wc(tag_pool, sug_pool):
            return tag_pool, "tvd_suspect", False, f"card verdict REJECT ({cls}): TVD wrong, tag right; TVD not evidence"
        return tag_pool, "keep", witness, f"card verdict REJECT ({cls})"
    if bool(row.get("planned", False)):
        return tag_pool, "tvd_suspect", False, f"A-prime: planned survey flagged -> {sug}; tag kept, TVD not evidence"
    if _is_bs_to_wc(tag_pool, sug_pool):
        return tag_pool, "tvd_suspect", False, f"Bone Spring -> Wolfcamp flag ({cls}) never applied; TVD not evidence"
    if cls in REJECTED_CLASSES:
        return tag_pool, "keep", witness, f"class {cls} rejected (precision {REJECTED_CLASSES[cls]:.2f})"
    if cls in HOLD_CLASSES:
        return tag_pool, "keep", witness, f"class {cls} on hold (precision {HOLD_CLASSES[cls]:.2f}; class exhausted, card verdicts decide)"
    if cls not in ACCEPTED_CLASSES:
        return tag_pool, "keep", witness, f"class {cls} not calibrated; tag kept"
    if row.get("sql23_nearest") != sug:
        return tag_pool, "keep", witness, f"class {cls} accepted but sql/23 nearest ({row.get('sql23_nearest')}) does not concur"
    if row.get("cons_gor_vote") == "own":
        return tag_pool, "keep", witness, f"class {cls} accepted, sql/23 concurs, but GOR says it produces like {tag}"
    return sug_pool, "reassign", witness, f"class {cls} (precision {ACCEPTED_CLASSES[cls]:.2f}) + sql/23 concurs + GOR {row.get('cons_gor_vote', 'none')}"


def load_verdicts(path: Any) -> dict[str, str]:
    """AGREE / REJECT by api10 from a cards_sample.csv; a comment starting with
    REJECT counts as REJECT, anything else (blank, inconclusive) is ignored."""
    d = pd.read_csv(path, dtype={"api10": str})
    v = d["verdict"].fillna("").astype(str).str.strip().str.upper()
    out: dict[str, str] = {}
    for api, s in zip(d["api10"], v):
        if s == "AGREE":
            out[api] = "AGREE"
        elif s.startswith("REJECT"):
            out[api] = "REJECT"
    return out


def apply_rule(df: pd.DataFrame, verdicts: dict[str, str] | None = None) -> pd.DataFrame:
    out = df.copy()
    res = [decide(r, verdicts) for _, r in out.iterrows()]
    out["box_bench"] = [r[0] for r in res]
    out["box_action"] = [r[1] for r in res]
    out["box_depth_witness"] = [r[2] for r in res]
    out["box_reason"] = [r[3] for r in res]
    return out


def rule_summary(df: pd.DataFrame, pools: tuple[str, ...]) -> dict[str, Any]:
    """Counts per pilot pool: membership before/after, actions, witness counts."""
    out: dict[str, Any] = {}
    tagged_pool = df["formation_blueox"].map(pool)
    for pb in pools:
        before = df[tagged_pool == pb]
        after = df[df["box_bench"] == pb]
        out[pb] = {
            "n_tagged": len(before),
            "n_after_rule": len(after),
            "reassigned_out": int(((tagged_pool == pb) & (df["box_bench"] != pb)).sum()),
            "reassigned_in": int(((tagged_pool != pb) & (df["box_bench"] == pb)).sum()),
            "tvd_suspect": int((before["box_action"] == "tvd_suspect").sum()),
            "depth_witnesses": int(after["box_depth_witness"].sum()),
            "cohort_after": int(after["cohort"].sum()),
            "actions": before["box_action"].value_counts().to_dict(),
            "flags_kept_by_reason": {
                k: int(v) for k, v in before.loc[(before["cons_status"] == "flag") & (before["box_action"] == "keep"), "box_reason"]
                .str.replace(r"\(.*?\)", "", regex=True).str.split(";").str[0].str.strip().value_counts().items()
            },
        }
    known = ACCEPTED_CLASSES | REJECTED_CLASSES | HOLD_CLASSES
    out["unknown_classes"] = sorted(
        {
            f"{pool(t)}->{pool(s)}"
            for t, s, st in zip(df["formation_blueox"], df["cons_suggest"], df["cons_status"])
            if st == "flag" and isinstance(s, str) and pool(t) != pool(s) and s not in NEVER_INTO
            and (pool(t) in pools or pool(s) in pools)
            and f"{pool(t)}->{pool(s)}" not in known
        }
    )
    return out


FINAL_COLS = [
    "api10", "well_name", "operator", "state_code", "county", "formation_blueox", "box_bench", "box_action", "box_depth_witness",
    "box_reason", "planned", "tvd_ft", "tvd_round", "lateral_length_ft", "first_production_date", "cum_12m_oil_bbl", "oil12_kft", "gor12",
    "cohort", "mid_lon", "mid_lat", "cons_status", "cons_suggest", "cons_nearest_delta", "cons_own_delta", "sql23_nearest", "cons_gor_vote",
]


def write_final_sets(df: pd.DataFrame, out_dir: Any, pools: tuple[str, ...]) -> None:
    for pb in pools:
        g = df[df["box_bench"] == pb].sort_values("api10")
        g[[c for c in FINAL_COLS if c in g.columns]].to_csv(out_dir / f"wells_final_{pb}.csv", index=False)
