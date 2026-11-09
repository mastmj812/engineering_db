"""formation_blueox rule v5 — "vendors propose, depth decides" (docs/formation_tag_redesign/RULE_V5.md). Pure core.

Replaces sql/16's DECISION logic ("Novi, unless Novi's value is coarse, then Enverus") and sql/23's depth patch. Keeps
the plumbing: both vendor strings still map through ref.formation_crosswalk, overrides still win, and the output is
still one formation_blueox code. Producers only; sticks keep their own path.

Per producing horizontal, with novi_code / env_code = each vendor string's crosswalk code and its UNIT (lime / sand
inside one interval grouped; tag_vendor_conflict.UNIT):
  A  one vendor mapped                      -> that code                              basis 'single_vendor'
  B  both map to the same code              -> that code (high)                       basis 'agree'
  C  same unit, different sub-bench         -> sql/16's choice, confidence low        basis 'subbench_vendor'
     (Gate 0 Q1 (a): the sub-bench split is not this rule's job)
  D  different units:
     D1 depth decides: both units' witness depths exist at the well and it sits >= margin_ft closer to one,
        within far_ft of it                 -> that vendor's code                     basis 'depth'
     D2 else the pattern's learned precedence: depth backed one vendor in >= pattern_share of >= pattern_min_n
        decided wells of the same (basin, Novi unit, Enverus unit)
                                            -> that vendor's code                     basis 'pattern'
        (a gross pattern, units >= 2 apart, needs only pattern_min_n_gross decided wells)
     D3 else                                -> sql/16's choice, flagged 'unresolved'  basis 'unresolved'
  O  one vendor names a bench, the other OTHER (a formation outside the column): the named bench only if the well is
     within other_match_ft of its witness depth (basis 'depth_vs_other'); else sql/16's choice, flagged
  A  (one vendor mapped) applies only where the other vendor string is genuinely missing.
  sql/23: a well sql/23 corrected (> 600 ft off its bench) keeps that code unless a per-well depth call places it
  (basis 'sql23_kept'); sql/23 retires only once this rule carries its own gross-miss check.
Guards (any D-case): either unit protected (WDFD / BRNT / MISS), or a BS3 vs WCA conflict in Lea / Ward (rule B
pending) -> sql/16's choice, flagged. Overrides win afterwards (the caller).
Witnesses = clean wells whose two vendor codes map to the SAME unit; a unit's depth at a point = landing_surfaces.estimate
of its witnesses within r_mi (>= n_min). A conflict well is never a witness, so a cluster of mis-named wells cannot
manufacture the reference it is judged against (the Magnolia 15 / Calm Breeze 2 lesson, 2026-11-06).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import landing_surfaces as ls

# Step 1 policy of record: the learned winners FROZEN at review (Michael, 2026-11-09). A run applies these winners; the
# table it learns from the day's data is only a drift report (see drift()). Reference depths are evidence and update
# with every run; winners, thresholds and guards are policy and change only on review.
POLICY_V1 = Path(__file__).resolve().parent / "policy" / "step1_patterns_v1.csv"

UNIT = {
    "delaware": {"AVA_0": "AVA", "AVA_1": "AVA", "AVA_2": "AVA", "BS1_S": "BS1", "BS2_C": "BS2", "BS2_S": "BS2", "BS3_C": "BS3",
                 "BS3_S": "BS3", "WCXY": "WCA", "WCA_1": "WCA", "WCA_2": "WCA", "WCB_1": "WCB", "WCB_2": "WCB"},
    "midland": {"WCB_1": "WCB", "WCB_2": "WCB"},
}
UNIT_ORDER = {"delaware": ["AVA", "BS1", "BS2", "BS3", "WCA", "WCB", "WCC", "WCD", "STRN", "BRNT", "MISS", "WDFD"],
              "midland": ["US", "MS", "JM", "LSSH", "DEAN", "WCA_1", "WCB", "WCC", "WCD", "STRN", "BRNT", "MRMC", "MISS", "WDFD"]}
PROTECTED_UNITS = frozenset({"WDFD", "BRNT", "MISS"})
RULE_B_COUNTIES = frozenset({"Lea", "Ward"})


@dataclass(frozen=True)
class V5:
    r_mi: float = 2.0
    n_min: int = 3
    margin_ft: float = 100.0
    far_ft: float = 300.0
    pattern_min_n: int = 20
    pattern_min_n_gross: int = 5      # units >= gross_span apart: fewer decided wells needed (Novi 80-90 % there)
    pattern_share: float = 0.75
    gross_span: int = 2
    other_match_ft: float = 150.0     # a named vendor beats an OTHER call only this close to its witness depth
    # What a learned pattern is keyed on: "string" = (basin, Novi string, Enverus string), adopted as Step 1 policy v1
    # (Michael, 2026-11-09); "unit" = (basin, Novi unit, Enverus unit), as v5 was first frozen. Unit keying pools vendor
    # strings that map to one unit but differ in reliability (Novi WOLFCAMP A vs WOLFCAMP A (XY) against Enverus 3rd
    # Bone Spring: one crosswalk row reversed 20 reviewed decisions).
    pattern_key: str = "string"


RULE = V5()


def unit(basin: str, code: object) -> str | None:
    if not isinstance(code, str) or code == "OTHER":
        return None
    return UNIT.get(basin, {}).get(code, code)


def span(basin: str, u1: str | None, u2: str | None) -> float:
    o = UNIT_ORDER.get(basin, [])
    return float(abs(o.index(u1) - o.index(u2))) if u1 in o and u2 in o else np.nan


def unit_depths(d: pd.DataFrame, r: V5 = RULE) -> pd.DataFrame:
    """Witness depth of the Novi unit and of the Enverus unit at every row (NaN without control). d needs basin, x, y,
    depth_ft, evidence, u_novi, u_env."""
    wit = d["evidence"] & d["u_novi"].notna() & (d["u_novi"] == d["u_env"])
    out = pd.DataFrame({"z_novi": np.nan, "z_env": np.nan}, index=d.index)
    rm = r.r_mi * ls.M_PER_MI
    for (b, u), g in d[wit].groupby(["basin", "u_novi"]):
        wxy, wz = g[["x", "y"]].to_numpy(float), g["depth_ft"].to_numpy(float)
        tree = cKDTree(wxy)
        for side, col in (("u_novi", "z_novi"), ("u_env", "z_env")):
            m = (d["basin"] == b) & (d[side] == u) & ~wit & d["evidence"]
            if not m.any():
                continue
            pts = d.loc[m, ["x", "y"]].to_numpy(float)
            vals = np.full(len(pts), np.nan)
            for k, js in enumerate(tree.query_ball_point(pts, rm)):
                if len(js) >= r.n_min:
                    vals[k] = ls.estimate(wxy[js], wz[js], pts[k])[0]
            out.loc[m, col] = vals
    return out


def depth_call(depth: pd.Series, z_novi: pd.Series, z_env: pd.Series, r: V5 = RULE) -> pd.Series:
    dn, de = (depth - z_novi).abs(), (depth - z_env).abs()
    return pd.Series(np.select(
        [z_novi.isna() | z_env.isna(), (dn > r.far_ft) & (de > r.far_ft), (dn + r.margin_ft <= de) & (dn <= r.far_ft),
         (de + r.margin_ft <= dn) & (de <= r.far_ft)],
        ["no control", "neither", "Novi", "Enverus"], default="cannot tell"), index=depth.index)


def pattern_keys(r: V5 = RULE) -> list[str]:
    if r.pattern_key == "unit":
        return ["basin", "u_novi", "u_env"]
    if r.pattern_key == "string":
        return ["basin", "novi_raw", "env_raw", "u_novi", "u_env"]
    raise ValueError(f"pattern_key must be 'unit' or 'string', not {r.pattern_key!r}")


def learn_patterns(d: pd.DataFrame, r: V5 = RULE) -> pd.DataFrame:
    """The precedence table: per pattern key (r.pattern_key), depth-decided counts and the learned winner."""
    c = d[d["case"] == "D"]
    g = c.groupby(pattern_keys(r))["call"].agg(
        conflicts="size", novi=lambda s: int((s == "Novi").sum()), enverus=lambda s: int((s == "Enverus").sum())).reset_index()
    g["decided"] = g["novi"] + g["enverus"]
    g["novi_share"] = np.where(g["decided"] > 0, g["novi"] / g["decided"].where(g["decided"] > 0), np.nan)
    gross = np.array([span(b, a, e) >= r.gross_span for b, a, e in zip(g["basin"], g["u_novi"], g["u_env"], strict=True)], bool)
    learn = g["decided"] >= np.where(gross, r.pattern_min_n_gross, r.pattern_min_n)
    g["winner"] = np.where(learn & (g["novi_share"] >= r.pattern_share), "Novi",
                           np.where(learn & (g["novi_share"] <= 1 - r.pattern_share), "Enverus", None))
    return g


def load_policy(path: Path = POLICY_V1) -> pd.DataFrame:
    """A frozen precedence table: one row per learned winner (the pattern-key columns + winner)."""
    p = pd.read_csv(path)
    if p["winner"].isna().any() or not p["winner"].isin(["Novi", "Enverus"]).all():
        raise ValueError(f"{path}: every policy row needs a winner of Novi / Enverus")
    return p


def drift(learned: pd.DataFrame, policy: pd.DataFrame, r: V5 = RULE) -> pd.DataFrame:
    """Pattern keys whose winner learned from today's data differs from the frozen policy (gained, lost or flipped).
    Reported for review; a run never applies it."""
    keys = pattern_keys(r)
    m = learned.merge(policy[keys + ["winner"]].rename(columns={"winner": "frozen"}), on=keys, how="outer")
    m["learned"] = m["winner"].where(m["winner"].isin(["Novi", "Enverus"]))
    out = m[m["learned"].fillna("-") != m["frozen"].fillna("-")].copy()
    out["change"] = np.select([out["frozen"].isna(), out["learned"].isna()], ["gained", "lost"], default="flipped")
    return out.drop(columns=["winner"])


def assign(d: pd.DataFrame, r: V5 = RULE, policy: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """d needs basin, county, x, y, depth_ft, evidence, novi_code, env_code, novi_raw, env_raw (string keying), sql16
    (today's pre-override, pre-sql/23 code). Pattern winners come from `policy` (a frozen table, load_policy) when given,
    else from the table learned here (development only). Returns (per-row frame with v5, basis, flag, confidence, call,
    case, units, depths) and the table LEARNED from d (the drift report's input)."""
    d = d.copy()
    d["u_novi"] = [unit(b, c) for b, c in zip(d["basin"], d["novi_code"], strict=True)]
    d["u_env"] = [unit(b, c) for b, c in zip(d["basin"], d["env_code"], strict=True)]
    nm, em = d["u_novi"].notna(), d["u_env"].notna()
    other = (d["novi_code"] == "OTHER") | (d["env_code"] == "OTHER")
    d["case"] = np.select([(nm ^ em) & other, nm ^ em, nm & em & (d["novi_code"] == d["env_code"]), nm & em & (d["u_novi"] == d["u_env"]), nm & em],
                          ["O", "A", "B", "C", "D"], default="none")
    d = d.join(unit_depths(d, r))
    d["call"] = np.where(d["case"] == "D", depth_call(d["depth_ft"], d["z_novi"], d["z_env"], r), None)
    table = learn_patterns(d, r)
    keys = pattern_keys(r)
    src = table if policy is None else policy
    win = {tuple(k): w for k, w in zip(src[keys].itertuples(index=False, name=None), src["winner"], strict=True)}
    v5, basis, flag, conf = [], [], [], []
    for row in d.itertuples():
        f, cf = None, "low"
        if row.case == "A":
            code, bs, cf = (row.novi_code if isinstance(row.u_novi, str) else row.env_code), "single_vendor", "low"
        elif row.case == "B":
            code, bs, cf = row.novi_code, "agree", "high"
        elif row.case == "C":
            code, bs = row.sql16, "subbench_vendor"
        elif row.case == "O":  # one vendor names a bench, the other a formation outside the column (OTHER)
            named = row.novi_code if isinstance(row.u_novi, str) else row.env_code
            z = row.z_novi if isinstance(row.u_novi, str) else row.z_env
            if {row.u_novi, row.u_env} & PROTECTED_UNITS:
                code, bs, f = row.sql16, "guard", "protected"
            elif np.isfinite(z) and abs(row.depth_ft - z) <= r.other_match_ft:
                code, bs = named, "depth_vs_other"
            else:
                code, bs, f = row.sql16, "other_vendor_kept", "vs_other"
        elif row.case == "D":
            guarded = ({row.u_novi, row.u_env} & PROTECTED_UNITS) or (
                row.basin == "delaware" and {row.u_novi, row.u_env} == {"BS3", "WCA"} and row.county in RULE_B_COUNTIES)
            if guarded:
                code, bs, f = row.sql16, "guard", "protected" if ({row.u_novi, row.u_env} & PROTECTED_UNITS) else "rule_b_pending"
            elif row.call in ("Novi", "Enverus"):
                code, bs, cf = (row.novi_code if row.call == "Novi" else row.env_code), "depth", "high"
            elif win.get(tuple(getattr(row, k) for k in keys)) in ("Novi", "Enverus"):
                w = win[tuple(getattr(row, k) for k in keys)]
                code, bs = (row.novi_code if w == "Novi" else row.env_code), "pattern"
            else:
                code, bs, f = row.sql16, "unresolved", "unresolved"
        else:
            code, bs = row.sql16, "unmapped"
        v5.append(code)
        basis.append(bs)
        flag.append(f)
        conf.append(cf)
    d["v5"], d["basis"], d["flag"], d["confidence"] = v5, basis, flag, conf
    if "sql23_code" in d:  # a sql/23-corrected well keeps that correction unless depth itself places it
        keep = d["sql23_code"].notna() & ~d["basis"].isin(["depth", "depth_vs_other"])
        d.loc[keep, "v5"], d.loc[keep, "basis"] = d.loc[keep, "sql23_code"], "sql23_kept"
    return d, table


def rule_record() -> dict:
    return {"rule": asdict(RULE), "policy": POLICY_V1.name, "unit": UNIT, "unit_order": UNIT_ORDER, "protected_units": sorted(PROTECTED_UNITS),
            "rule_b_counties": sorted(RULE_B_COUNTIES)}
