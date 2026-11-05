"""formation_blueox rule v4, "the ladder" — revision 2 of docs/formation_tag_redesign (RULE_V4.md). Pure core, no DB.

v3 failed because it read a well's sub-bench off its neighbours' VENDOR codes, and the vendor errors come in coherent
local clusters (step2-score-2026-11-05/FINDINGS.md). v4 measures every well against a RELIABLE reference instead,
as the Lea/Eddy rule V did (15/15 family calls upheld by Michael):

  A. Witnesses. Evidence wells (survey depth or clean tvd_ft, not planned) whose vendors agree on the FAMILY (every
     mapped vendor string, Novi and Enverus, maps to the same family). Families hold (0.5 % gross inversions), so
     these are the trustworthy depth references.
  B. Anchor. Per well, the median depth of witnesses of the basin's ANCHOR family within anchor_radius_mi (>=
     anchor_min_n). Delaware anchor WCA (fallback BS2_S); Midland WCA_1 (fallback LSSH). offset = depth - anchor.
  C. Ladder. A rung per bench = the median offset of evidence wells (with an anchor) carrying that vendor code, per
     county, falling back to state, then basin (>= rung_min_n). Benches whose rungs sit closer than sep_ft (or out of
     order) form one unresolvable CLUSTER. A well whose vendor bench has no rung here is not judged (`no_rung`).
  D. Placement. The well lands in the cluster its offset falls in (boundaries = midpoints between cluster rungs).
     * vendor code in that cluster -> keep it. Confidence high only for a one-bench cluster with margin >=
       max(conf_min_ft, conf_frac x the gap); inside a multi-bench cluster it is low (Gate 0 Q1 (a)).
     * otherwise MOVE to the cluster's bench nearest the offset, but only when the margin clears the same bar,
       the target family has >= support_min_n evidence wells within support_radius_mi ("deep neighbours",
       Michael's reason for holding three #230 cards), and no guard blocks it.
  E. Grid (Delaware, controlled). Where the geologist's interval decisively (>= grid_min_miss_ft) excludes the
     vendor family, the well may move to the nearest rung of a family the interval allows. A ladder move into a
     family the interval excludes is blocked (`grid_conflict`).
  Guards (as v3): never into or out of WDFD / BRNT / MISS; never a BS2 / BS3 sand<->carbonate swap; never across
  the XY top in Lea / Ward (rule B pending). Off-column vendor codes (OTHER, unmapped) are never re-placed
  (`unmapped`: the step-20a OTHER class was a TVD-defect bucket).
  Overrides win afterwards (the caller); the rule never reads them.
Sticks: the same placement against producer witnesses and rungs, but a move across families is a flag
(`family_conflict`), never a move.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from box import tag_rule as tr
from box import tag_scoreboard as sb

ANCHORS: dict[str, tuple[str, str]] = {"delaware": ("WCA", "BS2_S"), "midland": ("WCA_1", "LSSH")}


@dataclass(frozen=True)
class Ladder:
    anchor_radius_mi: float = 1.5
    anchor_min_n: int = 3
    rung_min_n: int = 15
    sep_ft: float = 75.0
    conf_min_ft: float = 30.0
    conf_frac: float = 0.25
    support_radius_mi: float = 1.5
    support_min_n: int = 3
    grid_min_miss_ft: float = 50.0
    grid_min_share: float = 0.5


LADDER = Ladder()


def crosses_xy(basin: str, f1: str | None, f2: str | None, order: dict[str, list[str]]) -> bool:
    """v4 rev 1: a move between a Delaware family above the XY top (shallower than WCA) and one at or below it."""
    if basin != "delaware" or f1 is None or f2 is None:
        return False
    fo = tr.family_order(order)["delaware"]
    k = fo.index("WCA")
    i1, i2 = (fo.index(f) if f in fo else None for f in (f1, f2))
    return i1 is not None and i2 is not None and (i1 < k) != (i2 < k)


def input_code(df: pd.DataFrame) -> pd.Series:
    """v4 rev 1: the code v4 starts from = the vendor code after the sql/23 gross correction (= live for a
    non-overridden well); a ratified-override well starts from its raw vendor code, so overrides never leak."""
    return df["live"].where(df["live_source"] != "ratified_override", df["vendor"])


def family_agree(df: pd.DataFrame) -> np.ndarray:
    """Every mapped vendor code (novi_code, env_code) maps to the vendor code's family."""
    out = np.zeros(len(df), bool)
    for k, (b, v, n, e) in enumerate(zip(df["basin"], df["vendor"], df["novi_code"], df["env_code"], strict=True)):
        fv = tr.family(b, v)
        if fv is None:
            continue
        fams = [tr.family(b, c) for c in (n, e) if isinstance(c, str)]
        out[k] = bool(fams) and all(f == fv for f in fams)
    return out


def anchors(pairs: pd.DataFrame, ref: pd.DataFrame, witness: np.ndarray, n_subj: int, lad: Ladder = LADDER) -> pd.DataFrame:
    """Per subject i: anchor_primary / anchor_secondary median depth (NaN when < anchor_min_n witnesses)."""
    fam = np.array([tr.family(b, c) for b, c in zip(ref["basin"], ref["vendor"], strict=True)], dtype=object)
    z = ref["depth_ft"].to_numpy(float)
    p = pairs[pairs["d"] <= lad.anchor_radius_mi * sb.M_PER_MI]
    p = p[witness[p["j"].to_numpy()]]
    t = pd.DataFrame({"i": p["i"].to_numpy(), "fam": fam[p["j"].to_numpy()], "z": z[p["j"].to_numpy()],
                      "basin": ref["basin"].to_numpy()[p["j"].to_numpy()]})
    out = pd.DataFrame(index=range(n_subj), columns=["anchor_primary", "anchor_secondary"], dtype=float)
    for slot, k in (("anchor_primary", 0), ("anchor_secondary", 1)):
        want = np.array([ANCHORS.get(b, (None, None))[k] for b in t["basin"]], dtype=object)
        g = t[t["fam"] == want].groupby("i")["z"].agg(["median", "size"])
        g = g[g["size"] >= lad.anchor_min_n]
        out.loc[g.index, slot] = g["median"].to_numpy()
    return out


def offsets(df: pd.DataFrame, anc: pd.DataFrame) -> pd.DataFrame:
    """offset and anchor_used ('primary' / 'secondary' / None) per row."""
    z = df["depth_ft"].to_numpy(float)
    a1, a2 = anc["anchor_primary"].to_numpy(float), anc["anchor_secondary"].to_numpy(float)
    used = np.where(np.isfinite(a1), "primary", np.where(np.isfinite(a2), "secondary", None))
    off = np.where(np.isfinite(a1), z - a1, np.where(np.isfinite(a2), z - a2, np.nan))
    return pd.DataFrame({"offset_ft": off, "anchor_used": used}, index=df.index)


def calibrate(df: pd.DataFrame, calib: np.ndarray, lad: Ladder = LADDER) -> pd.DataFrame:
    """Rungs: median offset per (level key, anchor_used, code) over calibration rows, >= rung_min_n.
    Levels: county, state, basin. Returns long table (level, key, anchor_used, code, rung_ft, n)."""
    c = df[calib & np.isfinite(df["offset_ft"].to_numpy(float))]
    rows = []
    for level, key in (("county", ["basin", "county"]), ("state", ["basin", "state_code"]), ("basin", ["basin"])):
        g = c.groupby([*key, "anchor_used", "vendor"])["offset_ft"].agg(rung_ft="median", n="size").reset_index()
        g = g[g["n"] >= lad.rung_min_n].copy()
        if g.empty:
            continue
        g["level"] = level
        g["key"] = ["|".join(map(str, t)) for t in g[key].itertuples(index=False)]
        rows.append(g.rename(columns={"vendor": "code"})[["level", "key", "anchor_used", "code", "rung_ft", "n"]])
    cols = ["level", "key", "anchor_used", "code", "rung_ft", "n"]
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=cols)


def rung_lookup(rungs: pd.DataFrame) -> dict[tuple[str, str, str, str], float]:
    return {(lv, k, a, c): r for lv, k, a, c, r in zip(rungs["level"], rungs["key"], rungs["anchor_used"], rungs["code"], rungs["rung_ft"], strict=True)}


def ladder_for(basin: str, county: str | None, state: object, anchor_used: str, order: dict[str, list[str]],
               lk: dict[tuple[str, str, str, str], float]) -> list[tuple[str, float]]:
    """(code, rung) in strat order for this place: county rung, else state, else basin."""
    keys = (("county", f"{basin}|{county}"), ("state", f"{basin}|{state}"), ("basin", basin))
    out = []
    for c in order.get(basin, []):
        for lv, k in keys:
            r = lk.get((lv, k, anchor_used, c))
            if r is not None:
                out.append((c, float(r)))
                break
    return out


def clusters(ladder: list[tuple[str, float]], sep_ft: float) -> list[tuple[list[str], float]]:
    """Merge adjacent benches (strat order) whose rungs are < sep_ft apart or out of order. Returns (codes, rep rung)."""
    cl: list[tuple[list[str], list[float]]] = []
    for c, r in ladder:
        if cl and r - max(cl[-1][1]) < sep_ft:
            cl[-1][0].append(c)
            cl[-1][1].append(r)
        else:
            cl.append(([c], [r]))
    out = [(codes, float(np.median(rs))) for codes, rs in cl]
    merged: list[tuple[list[str], float]] = []
    for codes, rep in out:  # a later cluster whose rep is not below the previous one merges into it
        if merged and rep - merged[-1][1] < sep_ft:
            merged[-1] = (merged[-1][0] + codes, float(np.median([merged[-1][1], rep])))
        else:
            merged.append((codes, rep))
    return merged


def place(offset: float, cl: list[tuple[list[str], float]], lad: Ladder = LADDER) -> tuple[int, float, bool]:
    """(cluster index, margin to the nearest boundary, margin clears the confidence bar)."""
    reps = np.array([r for _, r in cl])
    if len(reps) == 1:
        return 0, np.inf, True
    bounds = (reps[:-1] + reps[1:]) / 2.0
    k = int(np.searchsorted(bounds, offset))
    near = [(abs(offset - bounds[j]), reps[j + 1] - reps[j]) for j in (k - 1, k) if 0 <= j < len(bounds)]
    m, gap = min(near)
    return k, float(m), m >= max(lad.conf_min_ft, lad.conf_frac * gap)


def support(pairs: pd.DataFrame, ref: pd.DataFrame, evidence: np.ndarray, lad: Ladder = LADDER) -> dict[tuple[int, str], int]:
    """Evidence wells per (subject i, vendor family) within support_radius_mi."""
    fam = np.array([tr.family(b, c) for b, c in zip(ref["basin"], ref["vendor"], strict=True)], dtype=object)
    p = pairs[(pairs["d"] <= lad.support_radius_mi * sb.M_PER_MI) & evidence[pairs["j"].to_numpy()]]
    t = pd.DataFrame({"i": p["i"].to_numpy(), "f": fam[p["j"].to_numpy()]})
    g = t.groupby(["i", "f"]).size()
    return {(i, f): int(n) for (i, f), n in g.items()}


def assign(subj: pd.DataFrame, pairs: pd.DataFrame, ref: pd.DataFrame, rungs: pd.DataFrame, order: dict[str, list[str]],
           grid: pd.DataFrame | None = None, move_family: bool = True, lad: Ladder = LADDER) -> pd.DataFrame:
    """Place every subject row. subj needs basin, county, state_code, vendor, depth_ft, evidence, offset_ft,
    anchor_used. pairs: i = subject row, j = ref row. ref needs basin, vendor, evidence. grid aligned with subj."""
    lk = rung_lookup(rungs)
    sup = support(pairs, ref, ref["evidence"].to_numpy(bool), lad)
    n = len(subj)
    code = subj["vendor"].to_numpy(object).copy()
    basis = np.full(n, "vendor", dtype=object)
    conf = np.full(n, "low", dtype=object)
    margin = np.full(n, np.nan)
    flag = np.full(n, None, dtype=object)
    cache: dict[tuple, list] = {}
    for i in range(n):
        b, cty, stc, v = subj["basin"].iat[i], subj["county"].iat[i], subj["state_code"].iat[i], code[i]
        if b not in order or v not in order[b]:
            basis[i], flag[i] = "unmapped", "unmapped" if isinstance(v, str) else None
            continue
        if not bool(subj["evidence"].iat[i]):
            basis[i] = "no_depth"
            continue
        a, off = subj["anchor_used"].iat[i], subj["offset_ft"].iat[i]
        if not isinstance(a, str) or not np.isfinite(off):
            basis[i] = "no_anchor"
            continue
        key = (b, cty, stc, a)
        if key not in cache:
            cache[key] = clusters(ladder_for(b, cty, stc, a, order, lk), lad.sep_ft)
        cl = cache[key]
        if not cl:
            basis[i] = "no_ladder"
            continue
        if not any(v in members for members, _ in cl):  # the vendor bench has no rung here: cannot be judged
            basis[i] = "no_rung"
            continue
        k, m, ok = place(off, cl, lad)
        margin[i] = m
        basis[i] = "ladder"
        members = cl[k][0]
        rep = dict(ladder_for(b, cty, stc, a, order, lk))
        vf = tr.family(b, v)
        target = None
        if v in members:
            conf[i] = "high" if (len(members) == 1 and ok) else "low"
        elif ok:
            target = min(members, key=lambda c: abs(off - rep[c]))
        # grid (Delaware, controlled): may exclude the vendor family, or veto a move
        g = grid.iloc[i] if grid is not None and i < len(grid) else None
        if (g is not None and isinstance(g.get("dom_interval"), str) and bool(g.get("controlled")) and not bool(g.get("no_control"))
                and float(g.get("dom_share") or 0) >= lad.grid_min_share and g["dom_interval"] in tr.INTERVAL_CODES and pd.notna(g.get("fam_miss_ft"))):
            allowed = {tr.family(b, c) for c in tr.INTERVAL_CODES[g["dom_interval"]]}
            decisive = abs(float(g["fam_miss_ft"])) >= lad.grid_min_miss_ft
            if decisive and vf not in allowed:
                cands = [c for c in rep if tr.family(b, c) in allowed]
                if target is None or tr.family(b, target) not in allowed:
                    target = min(cands, key=lambda c: abs(off - rep[c])) if cands else None
                    if target is None:
                        flag[i] = "family_conflict"
                basis[i] = "grid"
            elif target is not None and tr.family(b, target) != vf and tr.family(b, target) not in allowed:
                flag[i], target = "grid_conflict", None
        if target is None or target == v:
            continue
        tf = tr.family(b, target)
        why = tr._blocked(b, cty, v, target, crosses_xy(b, vf, tf, order))
        if why is None and tf != vf and sup.get((i, tf), 0) < lad.support_min_n:
            why = "no_target_support"
        if why is None and tf != vf and not move_family:
            why = "family_conflict"
        if why:
            flag[i] = why
            continue
        code[i] = target
        conf[i] = "high" if ok and len(members) == 1 else "low"
    return pd.DataFrame({"code": code, "basis": basis, "confidence": conf, "margin_ft": margin, "flag": flag}, index=subj.index)


def run_producers(df: pd.DataFrame, pairs: pd.DataFrame, order: dict[str, list[str]], grid: pd.DataFrame | None = None,
                  lad: Ladder = LADDER) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(result frame aligned with df, rung table). df needs basin, county, state_code, vendor, novi_code, env_code,
    depth_ft, evidence."""
    wit = df["evidence"].to_numpy(bool) & family_agree(df)
    anc = anchors(pairs, df, wit, len(df), lad)
    off = offsets(df, anc)
    d = df.join(off)
    # rungs from ALL evidence wells: a county-wide median dilutes the local error clusters that sank v3, and
    # witnesses-only left the Delaware with no BS2_C / BS3_C / WCC rung (the vendors name those differently)
    rungs = calibrate(d, df["evidence"].to_numpy(bool), lad)
    res = assign(d, pairs, df, rungs, order, grid, True, lad)
    return off.join(res).assign(witness=wit), rungs


def run_sticks(sticks: pd.DataFrame, pairs_sp: pd.DataFrame, prod: pd.DataFrame, prod_witness: np.ndarray, rungs: pd.DataFrame,
               order: dict[str, list[str]], grid: pd.DataFrame | None = None, lad: Ladder = LADDER) -> pd.DataFrame:
    anc = anchors(pairs_sp, prod, prod_witness, len(sticks), lad)
    off = offsets(sticks, anc)
    res = assign(sticks.join(off), pairs_sp, prod, rungs, order, grid, False, lad)
    return off.join(res)


def rule_record() -> dict:
    return {"ladder": asdict(LADDER), "anchors": ANCHORS, "families": tr.FAMILY, "protected": sorted(tr.PROTECTED)}
