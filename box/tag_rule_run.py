"""The tag rule as the nightly runs it — docs/formation_tag_redesign/WAREHOUSE_STEP.md (W2).

One pass of Steps 1 -> 2 -> 3 over the vendor-only input frame (box.tag_rule_inputs), under POLICY read from tables
(frozen Step 1 winners, decided change classes, human calls, depth exclusions) — never from card folders, and never
learning policy from the data. Pure: frames in, frames out; the nightly script does the I/O.

Resolution per well (what curated.formation_tag_rule records; sql/16 applies `applied_code` while the inputs match):

  human call (ref.formation_tag_overrides)   not a rule row: sql/16's override branch wins anyway
  Step 3 move in an ACCEPTED Step 3 class    applied, step 3
  Step 1 change in an ACCEPTED Step 1 class  applied, step 1
  anything else                              not applied: the well keeps its vendor tag (sql/16's crosswalk)

Change classes are keyed on the VENDOR tag (sql/16 without overrides): (basin, vendor -> rule code, basis). The review
wrote them against "today's tag"; the two agree except on sql/23-flipped wells (W1 report, section 6). sql/23 output is
never an input: the rule is vendor-only, so Step 1's sql23_kept branch stays dormant here.

Not applied, but reported (the card queue): Step 1 changes in a class never decided, Step 2 sub-bench changes (Step 2
lands only through cards), Step 3 moves outside an accepted class.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shapely

from box import tag_grossmiss as gm
from box import tag_precedence as tp
from box import tag_scoreboard as sb
from box import tag_subbench as ts1

UNMAPPED = "(unmapped)"
MIN_QUEUE_CLASS = 20


@dataclass(frozen=True)
class Policy:
    """Everything the rule reads besides evidence: ref.formation_tag_policy (one version), ref.formation_tag_class,
    ref.formation_tag_overrides, ref.formation_tag_depth_exclusions."""

    patterns: pd.DataFrame
    classes: pd.DataFrame
    overrides: pd.DataFrame
    exclusions: pd.DataFrame
    version: int

    def accepted(self, step: int) -> set[tuple[str, str, str, str]]:
        c = self.classes[(self.classes["step"] == step) & (self.classes["decision"] == "accept")]
        return set(zip(c["basin"], c["from_code"], c["to_code"], c["basis"], strict=True))

    def decided(self, step: int) -> set[tuple[str, str, str, str]]:
        c = self.classes[self.classes["step"] == step]
        return set(zip(c["basin"], c["from_code"], c["to_code"], c["basis"], strict=True))


def policy_from_seeds(version: int = 1) -> Policy:
    from scripts import tag_rule_seeds as seeds

    p = pd.read_csv(seeds.POLICY)
    return Policy(patterns=p[p["policy_version"] == version].drop(columns="policy_version"),
                  classes=pd.read_csv(seeds.CLASSES), overrides=pd.read_csv(seeds.OVERRIDES, dtype={"api10": str}),
                  exclusions=pd.read_csv(seeds.EXCLUSIONS, dtype={"api10": str}), version=version)


def _code(x: object) -> str:
    return x if isinstance(x, str) else UNMAPPED


def frame(wells: pd.DataFrame, vendors: pd.DataFrame, extents: pd.DataFrame, exclusions: pd.DataFrame) -> pd.DataFrame:
    """The judged frame: clean evidence wells (sb.evidence_depth 'best'), minus live depth exclusions, with midpoints,
    vendor codes and the BOX-extent flag. Every well of `wells` is returned; `in_frame` marks the judged ones."""
    w = sb.evidence_depth(wells, "best").assign(api10=lambda x: x["api10"].astype(str))
    ex = exclusions.assign(api10=lambda x: x["api10"].astype(str)).set_index("api10")
    m = w["api10"].isin(ex.index)
    same_depth = (w["depth_ft"] - w["api10"].map(ex["depth_ft"]).astype(float)).abs().le(0.5)
    same_src = w["depth_source"] == w["api10"].map(ex["depth_source"])
    w["depth_excluded"] = m & same_depth & same_src
    w["exclusion_lapsed"] = m & ~w["depth_excluded"]
    mid = np.array([p[len(p) // 2] if p else (np.nan, np.nan) for p in w["pts"]], float)
    w["x"], w["y"] = mid[:, 0], mid[:, 1]
    w["in_frame"] = w["clean"] & ~w["depth_excluded"] & np.isfinite(w["x"])
    w = w.rename(columns={"vendor": "sql16"})
    v = vendors.assign(api10=lambda x: x["api10"].astype(str))[["api10", "novi_raw", "env_raw", "novi_code", "env_code"]]
    w = w.merge(v, on="api10", how="left")
    w["in_box_extents"] = False
    for b, g in extents.groupby("basin"):
        geom = shapely.union_all([shapely.from_wkt(t) for t in g["wkt"]])
        mb = (w["basin"] == b).to_numpy() & np.isfinite(w["x"]).to_numpy()
        w.loc[mb, "in_box_extents"] = shapely.contains_xy(geom, w.loc[mb, "x"].to_numpy(), w.loc[mb, "y"].to_numpy())
    return w


def run(w: pd.DataFrame, policy: Policy, rule: tp.V5 = tp.RULE) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(per-well result for the judged frame, Step 1's learned table for the drift report)."""
    d = w[w["in_frame"]].reset_index(drop=True).copy()
    d["evidence"] = True
    d = d.drop(columns=[c for c in ("sql23_code",) if c in d.columns])
    d, learned = tp.assign(d, rule, policy.patterns)
    ovr = policy.overrides.assign(api10=lambda x: x["api10"].astype(str)).set_index("api10")["corrected_code"]
    d["override"] = d["api10"].map(ovr)
    human = d["override"].notna()
    d["src"] = np.where(human, "override", None)

    # Step 1, gated on the vendor tag
    d["step1_code"] = d["v5"]
    key1 = list(zip(d["basin"], d["sql16"].map(_code), d["v5"].map(_code), d["basis"], strict=True))
    acc1, dec1 = policy.accepted(1), policy.decided(1)
    ch1 = (d["v5"].fillna("~") != d["sql16"].fillna("~")) & ~human
    in1 = ch1 & pd.Series([k in acc1 for k in key1], index=d.index)
    d["step1_class"] = [f"{b} {f}->{t} ({s})" for b, f, t, s in key1]
    d["step1_decided"] = pd.Series([k in dec1 for k in key1], index=d.index)
    d["accepted"] = np.where(human, d["override"], np.where(in1, d["v5"], d["sql16"]))
    d["accepted_basis"] = np.select([human, in1, ch1], ["override", "class_accepted", "class_not_accepted"], default="unchanged")

    # Step 2: reported only (sub-bench changes land through cards)
    d = ts1.assign(d, "accepted", rule)
    d["step2_queue"] = (d["sb_code"].fillna("~") != d["accepted"].fillna("~")) & ~human

    # Step 3 on the gated Step 1 tag, applied in an accepted Step 3 class
    d["base52"] = d["accepted"]
    d = gm.assign(d, "base52", rule)
    mv = (d["gm_code"].fillna("~") != d["base52"].fillna("~")) & ~human
    key3 = list(zip(d["basin"], d["base52"].map(_code), d["gm_code"].map(_code), ["gm_move"] * len(d), strict=True))
    in3 = mv & pd.Series([k in policy.accepted(3) for k in key3], index=d.index)
    d["step3_class"] = [f"{b} {f}->{t}" for b, f, t, _ in key3]
    d["step3_queue"] = mv & ~in3

    d["applied_code"] = np.where(in3, d["gm_code"], np.where(in1, d["v5"], None))
    d["applied_step"] = np.where(in3, 3, np.where(in1, 1, 0))
    d["applied"] = in1 | in3
    d["applied_class"] = np.where(in3, d["step3_class"], np.where(in1, d["step1_class"], None))
    d["step1_queue"] = ch1 & ~d["step1_decided"]
    return d, learned


def queue_classes(d: pd.DataFrame, min_class: int = MIN_QUEUE_CLASS) -> pd.DataFrame:
    """Undecided Step 1 change classes of >= min_class wells (cards needed)."""
    q = d[d["step1_queue"]].groupby("step1_class").size().rename("wells").reset_index()
    return q[q["wells"] >= min_class].sort_values("wells", ascending=False).reset_index(drop=True)


RULE_COLUMNS = ["api10", "basin", "applied", "applied_code", "applied_step", "applied_class", "vendor_code", "step1_code",
                "step1_basis", "step2_code", "step2_basis", "step3_code", "step3_basis", "human_call", "step1_queue",
                "step2_queue", "step3_queue", "novi_raw", "env_raw", "tvd_ft", "planned", "depth_ft", "depth_source",
                "in_box_extents"]


def rule_rows(d: pd.DataFrame) -> pd.DataFrame:
    """The curated.formation_tag_rule rows (one per judged well). The recorded inputs are what sql/16's staleness guard
    compares with the well's current inputs."""
    out = pd.DataFrame({
        "api10": d["api10"], "basin": d["basin"], "applied": d["applied"].astype(bool),
        "applied_code": d["applied_code"], "applied_step": d["applied_step"].astype(int),
        "applied_class": d["applied_class"], "vendor_code": d["sql16"], "step1_code": d["v5"], "step1_basis": d["basis"],
        "step2_code": d["sb_code"], "step2_basis": d["sb_basis"], "step3_code": d["gm_code"], "step3_basis": d["gm_basis"],
        "human_call": d["override"], "step1_queue": d["step1_queue"].astype(bool), "step2_queue": d["step2_queue"].astype(bool),
        "step3_queue": d["step3_queue"].astype(bool), "novi_raw": d["novi_raw"], "env_raw": d["env_raw"],
        "tvd_ft": d["tvd_ft"], "planned": d["planned"].fillna(False).astype(bool), "depth_ft": d["depth_ft"],
        "depth_source": d["depth_source"], "in_box_extents": d["in_box_extents"].astype(bool)})
    out = out.astype(object).where(out.notna(), None)
    return out[RULE_COLUMNS]


def inputs_match(rule: pd.DataFrame, wells: pd.DataFrame, vendors: pd.DataFrame) -> pd.Series:
    """sql/16's staleness guard, in Python (the nightly's report and the tests): a rule row applies only while the
    well's Novi string, Enverus string, vendor TVD and planned flag equal what it was decided on."""
    cur = wells[["api10", "tvd_ft", "planned"]].merge(vendors[["api10", "novi_raw", "env_raw"]], on="api10")
    m = rule[["api10", "novi_raw", "env_raw", "tvd_ft", "planned"]].merge(cur, on="api10", how="left", suffixes=("", "_now"))

    def same(a: pd.Series, b: pd.Series) -> pd.Series:
        return (a.astype(object).where(a.notna(), "~").astype(str) == b.astype(object).where(b.notna(), "~").astype(str))

    tvd = pd.to_numeric(m["tvd_ft"], errors="coerce")
    tvd_now = pd.to_numeric(m["tvd_ft_now"], errors="coerce")
    ok = (same(m["novi_raw"], m["novi_raw_now"]) & same(m["env_raw"], m["env_raw_now"])
          & ((tvd - tvd_now).abs().le(0.5) | (tvd.isna() & tvd_now.isna()))
          & (m["planned"].fillna(False).astype(bool) == m["planned_now"].fillna(False).astype(bool)))
    return pd.Series(ok.to_numpy(), index=rule.index)


def breaker(prev: pd.DataFrame | None, new: pd.DataFrame, moved_inputs: set[str], floor: int = 200, share: float = 0.01) -> dict:
    """Circuit breaker (D3): applied codes that change against the previous run on wells present in both whose own
    inputs did not move. Trips above max(floor, share x judged wells)."""
    limit = max(floor, int(share * len(new)))
    if prev is None or prev.empty:
        return {"changed": 0, "limit": limit, "tripped": False, "first_run": True}
    a = prev.set_index("api10")["applied_code"]
    b = new.set_index("api10")["applied_code"]
    both = a.index.intersection(b.index).difference(pd.Index(sorted(moved_inputs)))
    norm = lambda s: s.loc[both].astype(object).where(s.loc[both].notna(), "~")
    changed = int((norm(a) != norm(b)).sum())
    return {"changed": changed, "limit": limit, "tripped": changed > limit, "first_run": False}


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False,
                              cwd=sb.ROOT).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def policy_digest(policy: Policy) -> str:
    h = hashlib.sha1()
    for df in (policy.patterns, policy.classes, policy.overrides, policy.exclusions):
        h.update(df.to_csv(index=False).encode())
    return h.hexdigest()[:12]


def summary(d: pd.DataFrame, w: pd.DataFrame, learned: pd.DataFrame, policy: Policy, rule: tp.V5 = tp.RULE) -> dict[str, Any]:
    drift = tp.drift(learned, policy.patterns, rule)
    q2 = d[d["step2_queue"]]
    q3 = d[d["step3_queue"]]
    return {
        "wells": len(w), "judged": len(d), "depth_excluded": int(w["depth_excluded"].sum()),
        "exclusions_lapsed": w.loc[w["exclusion_lapsed"], "api10"].tolist(),
        "applied": int(d["applied"].sum()), "applied_by_step": d.loc[d["applied"], "applied_step"].value_counts().to_dict(),
        "applied_by_class": d.loc[d["applied"], "applied_class"].value_counts().to_dict(),
        "human_calls_in_frame": int(d["override"].notna().sum()),
        "queue": {"step1_classes": queue_classes(d).to_dict("records"), "step1_wells_undecided": int(d["step1_queue"].sum()),
                  "step2": q2[["api10", "basin", "accepted", "sb_code", "sb_lead_ft"]].astype(object).to_dict("records"),
                  "step3": q3[["api10", "basin", "base52", "gm_code"]].astype(object).to_dict("records")},
        "policy_drift": drift.astype(object).where(drift.notna(), None).to_dict("records"),
        "policy_version": policy.version, "policy_digest": policy_digest(policy), "rule_sha": git_sha(),
    }
