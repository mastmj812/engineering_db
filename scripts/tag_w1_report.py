"""W1 report: the tag rule on live data, as the nightly would run it (read-only) — docs/formation_tag_redesign/WAREHOUSE_STEP.md.

    python -m scripts.tag_w1_report --live <live cache> --ref <reviewed-snapshot cache> --out <folder>

Both caches have been through Steps 1 -> 2 -> 3 (tag_precedence_dev, tag_subbench_dev, tag_grossmiss_dev) with the same
policy, card folders and class decisions. For each, the APPLIED tag is what the warehouse would carry after cutover:

  human call (override seed, or a carded Step 1 / 2 / 3 verdict)  >  Step 3 move in an accepted Step 3 class
  >  Step 1 class-accepted tag  >  the vendor tag (sql/16 without the rule)

Wells outside the rule's evidence frame (planned survey, no depth, < 4,000 ft) keep sql/16's code. The report covers:
reproduction (ref vs live, by whether the well's own inputs changed), the cutover diff against today's warehouse, new
wells, the card queue, the class-identity check (classes were written from today's tag; the nightly starts from the
vendor tag), human calls whose inputs moved since the card, policy drift and runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import tag_scoreboard as sb
from scripts.tag_v5_accepted import class_decisions

DOCS = sb.ROOT / "docs" / "formation_tag_redesign"
STEP1_CARDS = [DOCS / "v5-cards-2026-11-06", DOCS / "v5-cards-r2-2026-11-06", DOCS / "policy-v1-cards-2026-11-09" / "step1",
               DOCS / "policy-v1-cards-2026-11-09" / "step1_round2"]
STEP2_CARDS = DOCS / "v5_1-cards-2026-11-06"
STEP3_CARDS = [DOCS / "v5_2-cards-2026-11-08", DOCS / "policy-v1-cards-2026-11-09" / "step3"]
INPUTS = ["novi_raw", "env_raw", "tvd_ft", "lat_tvd_p50_ft", "planned"]
MIN_CLASS = 20


def step3_classes() -> set[str]:
    s = json.loads((STEP3_CARDS[0] / "score.json").read_text(encoding="utf-8"))
    return {k for k, v in s["classes"].items() if v["accepted"]}


def step3_calls() -> pd.Series:
    """Carded Step 3 verdicts, api10 -> code (a later card set wins). Rejects, holds and depth exclusions keep the input."""
    out = []
    for f in STEP3_CARDS:
        c = pd.read_csv(f / "cards_scored.csv", dtype={"api10": str})
        code = c["final_code"] if "final_code" in c.columns else c["final"]
        out.append(pd.DataFrame({"api10": c["api10"], "code": code}))
    return pd.concat(out, ignore_index=True).drop_duplicates("api10", keep="last").set_index("api10")["code"]


def carded_wells() -> pd.DataFrame:
    rows = []
    for f in [*STEP1_CARDS, STEP2_CARDS, *STEP3_CARDS]:
        c = pd.read_csv(f / "cards_sample.csv", dtype={"api10": str})
        rows.append(pd.DataFrame({"api10": c["api10"], "card_set": f.relative_to(DOCS).as_posix(), "card": c["card"]}))
    return pd.concat(rows, ignore_index=True)


def applied(cache: Path) -> pd.DataFrame:
    d = pd.read_pickle(cache / "producers_v5_2.pkl")
    d["api10"] = d["api10"].astype(str)
    acc3 = step3_classes()
    key = d["basin"] + " " + d["base52"].fillna("(unmapped)") + " -> " + d["gm_code"].fillna("~")
    move = d["gm_code"].fillna("~") != d["base52"].fillna("~")
    d["applied"] = d["base52"]
    d["applied_basis"] = np.select(
        [d["src"] == "override", d["src"] == "carded_call", d["accepted_basis"] == "class_accepted"],
        ["human_override", "carded_step1_2", "step1_class"], default="vendor")
    m3 = move & key.isin(acc3) & ~d["src"].isin(["override", "carded_call"])
    d.loc[m3, "applied"], d.loc[m3, "applied_basis"] = d.loc[m3, "gm_code"], "step3_class"
    calls = step3_calls()
    mc = d["api10"].isin(calls.index)
    d.loc[mc, "applied"], d.loc[mc, "applied_basis"] = d.loc[mc, "api10"].map(calls), "carded_step3"
    d["step3_queue"] = move & ~m3 & ~mc & (d["gm_basis"] == "gm_move")
    return d


def inputs_frame(cache: Path) -> pd.DataFrame:
    w = pd.read_pickle(cache / "wells.pkl").assign(api10=lambda x: x["api10"].astype(str))
    v = pd.read_pickle(cache / "vendors.pkl").assign(api10=lambda x: x["api10"].astype(str))[["api10", "novi_raw", "env_raw"]]
    return w[["api10", "tvd_ft", "lat_tvd_p50_ft", "planned", "pre_sql23", "live"]].merge(v, on="api10", how="left")


def _neq(a: pd.Series, b: pd.Series) -> pd.Series:
    an, bn = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    if an.notna().any() or bn.notna().any():
        return ~((an - bn).abs().le(0.5) | (an.isna() & bn.isna()))
    return a.astype(object).where(a.notna(), "~").astype(str) != b.astype(object).where(b.notna(), "~").astype(str)


def run(live: Path, ref: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    L, R = applied(live), applied(ref)
    iL, iR = inputs_frame(live), inputs_frame(ref)
    s: dict = {}

    # 1. reproduction: wells judged in both runs
    j = L[["api10", "basin", "county", "well_name", "live", "applied", "applied_basis", "in_box_extents"]].merge(
        R[["api10", "applied", "applied_basis"]], on="api10", suffixes=("", "_ref"))
    ii = iL.merge(iR, on="api10", suffixes=("", "_ref"))
    moved = pd.Series(False, index=ii.index)
    for c in INPUTS:
        ii[f"{c}_moved"] = _neq(ii[c], ii[f"{c}_ref"])
        moved |= ii[f"{c}_moved"]
    ii["inputs_moved"] = moved
    j = j.merge(ii[["api10", "inputs_moved", *[f"{c}_moved" for c in INPUTS]]], on="api10", how="left")
    j["differs"] = j["applied"].fillna("~") != j["applied_ref"].fillna("~")
    j["why"] = np.where(~j["differs"], "same", np.where(j["inputs_moved"], "own inputs moved", "evidence only (neighbours)"))
    s["reproduction"] = {"wells_in_both": len(j), "by_why": j["why"].value_counts().to_dict(),
                         "differs_by_basis_pair": j[j["differs"]].groupby(["applied_basis_ref", "applied_basis"]).size()
                         .rename("wells").reset_index().to_dict("records")}
    j[j["differs"]].sort_values(["why", "basin", "county"]).to_csv(out / "reproduction_differs.csv", index=False)

    # 2. cutover diff: applied tag vs today's warehouse tag (live run)
    L["vs_today"] = L["applied"].fillna("~") != L["live"].fillna("~")
    c = L[L["vs_today"]]
    s["cutover_vs_today"] = {"wells": len(c), "by_basin": c["basin"].value_counts().to_dict(),
                             "in_box_extents": int(c["in_box_extents"].sum()),
                             "by_basis": c["applied_basis"].value_counts().to_dict(),
                             "today_was_sql23_flip": int((c["live_source"] == "tvd_corrected").sum())}
    c[["api10", "basin", "county", "well_name", "operator", "live", "live_source", "pre_sql23", "applied", "applied_basis",
       "in_box_extents"]].sort_values(["basin", "applied_basis", "live"]).to_csv(out / "cutover_changes.csv", index=False)
    s["sql23_flips_today"] = {"wells_in_frame": int((L["live_source"] == "tvd_corrected").sum()),
                              "kept_by_rule": int(((L["live_source"] == "tvd_corrected") & ~L["vs_today"]).sum())}

    # 3. new wells (in the live frame only)
    new = L[~L["api10"].isin(R["api10"])]
    s["new_wells"] = {"wells": len(new), "by_basin": new["basin"].value_counts().to_dict(),
                      "by_applied_basis": new["applied_basis"].value_counts().to_dict()}
    s["left_frame"] = int((~R["api10"].isin(L["api10"])).sum())

    # 4. card queue (live run)
    decided = set(class_decisions(STEP1_CARDS)["class"])
    ch1 = L[L["final"].fillna("~") != L["live"].fillna("~")]
    cls1 = ch1.groupby("label").size().rename("wells").reset_index()
    q1 = cls1[(cls1["wells"] >= MIN_CLASS) & ~cls1["label"].isin(decided)].sort_values("wells", ascending=False)
    q1.to_csv(out / "queue_step1_classes.csv", index=False)
    carded2 = set(pd.read_csv(STEP2_CARDS / "cards_sample.csv", dtype={"api10": str})["api10"])
    q2 = L[(L["sb_code"].fillna("~") != L["accepted"].fillna("~")) & ~L["api10"].isin(carded2)]
    q2[["api10", "basin", "county", "well_name", "accepted", "sb_code", "sb_basis", "sb_lead_ft", "in_box_extents"]].to_csv(
        out / "queue_step2_subbench.csv", index=False)
    q3 = L[L["step3_queue"]]
    q3[["api10", "basin", "county", "well_name", "base52", "gm_code", "gm_own_gap_ft", "gm_target_gap_ft", "in_box_extents"]].to_csv(
        out / "queue_step3_moves.csv", index=False)
    s["card_queue"] = {"step1_classes_ge_20_undecided": q1.to_dict("records"),
                       "step2_uncarded_subbench_changes": len(q2),
                       "step2_by_class": q2.groupby(["basin", "accepted", "sb_code"]).size().sort_values(ascending=False)
                       .head(10).rename("wells").reset_index().to_dict("records"),
                       "step3_unapplied_moves": len(q3),
                       "step3_by_class": q3.groupby(["basin", "base52", "gm_code"], dropna=False).size().sort_values(ascending=False)
                       .head(10).rename("wells").reset_index().to_dict("records")}

    # 5. class identity: classes were written from today's tag; the nightly starts from the vendor tag (pre_sql23)
    lab_v = L["basin"] + " " + L["pre_sql23"].fillna("~") + "->" + L["final"].fillna("~") + " (" + L["basis"] + ")"
    differs_from = L["live"].fillna("~") != L["pre_sql23"].fillna("~")
    acc_live = L["accepted_basis"] == "class_accepted"
    rest = ~(L["applied_basis"].isin(["human_override", "carded_step1_2", "carded_step3"]))
    ci = L[differs_from & rest & ((L["final"].fillna("~") != L["pre_sql23"].fillna("~")) | acc_live)].copy()
    ci["label_vendor"] = lab_v[ci.index]
    ci["vendor_label_accepted"] = ci["label_vendor"].isin(set(class_decisions(STEP1_CARDS).query("decision == 'accept'")["class"]))
    ci["live_label_accepted"] = acc_live[ci.index]
    ci[["api10", "basin", "county", "well_name", "live", "live_source", "pre_sql23", "final", "basis", "label", "label_vendor",
        "live_label_accepted", "vendor_label_accepted", "applied"]].to_csv(out / "class_identity.csv", index=False)
    s["class_identity"] = {"wells_where_today_differs_from_vendor_and_rule_moves": len(ci),
                           "by_live_source": ci["live_source"].value_counts().to_dict(),
                           "accepted_under_today_label": int(ci["live_label_accepted"].sum()),
                           "accepted_under_vendor_label": int(ci["vendor_label_accepted"].sum()),
                           "accepted_under_both": int((ci["live_label_accepted"] & ci["vendor_label_accepted"]).sum())}

    # 6. human calls whose own inputs moved since the reviewed snapshot
    cw = carded_wells().drop_duplicates("api10", keep="last").merge(ii[["api10", "inputs_moved", *[f"{c}_moved" for c in INPUTS]]],
                                                                    on="api10", how="left")
    hm = cw[cw["inputs_moved"].fillna(False).astype(bool)]
    hm.to_csv(out / "human_calls_inputs_moved.csv", index=False)
    s["human_calls_inputs_moved"] = {"carded_wells": len(cw), "inputs_moved": len(hm),
                                     "by_input": {c: int(hm[f"{c}_moved"].sum()) for c in INPUTS}}

    # 7. policy drift (live Step 1) and runtime
    pd_path = out.parent / "live" / "step1" / "policy_drift.csv"
    s["policy_drift_rows"] = len(pd.read_csv(pd_path)) if pd_path.exists() else None
    rt = out.parent / "live" / "runtime.json"
    s["runtime"] = json.loads(rt.read_text()) if rt.exists() else None
    (out / "summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", type=Path, required=True)
    ap.add_argument("--ref", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    print(json.dumps(run(a.live, a.ref, a.out), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
