"""formation_blueox rule v4, "the ladder" — revision 2 of docs/formation_tag_redesign (RULE_V4.md). Pure core, no DB.

v3 failed because it read a well's sub-bench off its neighbours' VENDOR codes, and the vendor errors come in coherent
local clusters (step2-score-2026-11-05/FINDINGS.md). v4 measures every well against a RELIABLE reference instead,
as the Lea/Eddy rule V did (15/15 family calls upheld by Michael):

  A. Witnesses. Evidence wells (survey depth or clean tvd_ft, not planned) whose vendors agree on the FAMILY (every
     mapped vendor string, Novi and Enverus, maps to the same family). Families hold (0.5 % gross inversions), so
     these are the trustworthy depth references.
  B. Anchor (rev 2). Per well, the median depth of witnesses of each ANCHOR family within anchor_radius_mi (>=
     anchor_min_n): Delaware BS1_S / BS2_S / WCA, Midland JM / LSSH / WCA_1. The well uses the NEAREST one, and only
     when it is within max_lever_ft (a 3,000-ft lever arm turns normal isochore variation into a wrong sub-bench:
     COTTON DRAW UNIT #115H, 2026-11-05). offset = depth - anchor; otherwise `no_anchor` (vendor kept).
  C. Ladder. A rung per bench = the median offset of evidence wells (with an anchor) carrying that vendor code, per
     county, falling back to state, then basin (>= rung_min_n). Benches whose rungs sit closer than sep_ft (or out of
     order) form one unresolvable CLUSTER. A well whose vendor bench has no rung here is not judged (`no_rung`).
  D. Placement. The well lands in the cluster its offset falls in (boundaries = midpoints between cluster rungs).
     * vendor code in that cluster -> keep it. Confidence high only for a one-bench cluster with margin >=
       max(conf_min_ft, conf_frac x the gap); inside a multi-bench cluster it is low (Gate 0 Q1 (a)).
     * otherwise MOVE to the cluster's bench nearest the offset, but only when the margin clears the same bar,
       the target family has >= support_min_n evidence wells within support_radius_mi ("deep neighbours",
       Michael's reason for holding three #230 cards), the target is a ONE-bench cluster (rev 2:
       `ambiguous_target` otherwise), and no guard blocks it.
  E. Grid: OFF since rev 3 (use_grid=False; Michael 2026-11-05). On the rev-2 blind cards every grid-decided
     Delaware move was rejected (0/4); his B1 and B2 tops are not where operators split WCA/WCB or WCB_2/WCC. When on
     (Delaware, controlled), the grid decides where it excludes the vendor family by >= grid_min_miss_ft, and it
     vetoes a ladder move into a family the interval excludes (`grid_conflict`).
  Rev 3 also raises the move / high-confidence bar to conf_min_ft = 80 ft (rev-2 cards: 8/8 agree at >= 80 ft, so
  that value is fitted to those cards and is tested on a fresh draw).
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

# rev 2: several reliable anchor families per basin; a well uses the nearest one within max_lever_ft
ANCHORS: dict[str, tuple[str, ...]] = {"delaware": ("BS1_S", "BS2_S", "WCA"), "midland": ("JM", "LSSH", "WCA_1")}


@dataclass(frozen=True)
class Ladder:
    anchor_radius_mi: float = 1.5
    anchor_min_n: int = 3
    rung_min_n: int = 15
    sep_ft: float = 75.0
    conf_min_ft: float = 80.0  # rev 3: a move (and high confidence) needs >= 80 ft to the boundary
    conf_frac: float = 0.25
    support_radius_mi: float = 1.5
    support_min_n: int = 3
    grid_min_miss_ft: float = 50.0
    grid_min_share: float = 0.5
    max_lever_ft: float = 1_000.0  # rev 2: an anchor farther than this cannot place a thin split
    use_grid: bool = False  # rev 3: the geologist's grids neither decide nor veto (B1 / B2 are not operator boundaries)


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
    """Per subject i and anchor family: median depth of its witnesses within anchor_radius_mi (NaN below
    anchor_min_n). One column per anchor family across both basins."""
    fam = np.array([tr.family(b, c) for b, c in zip(ref["basin"], ref["vendor"], strict=True)], dtype=object)
    z = ref["depth_ft"].to_numpy(float)
    p = pairs[pairs["d"] <= lad.anchor_radius_mi * sb.M_PER_MI]
    p = p[witness[p["j"].to_numpy()]]
    j = p["j"].to_numpy()
    t = pd.DataFrame({"i": p["i"].to_numpy(), "fam": fam[j], "z": z[j], "basin": ref["basin"].to_numpy()[j]})
    cols = sorted({f for fs in ANCHORS.values() for f in fs})
    out = pd.DataFrame(np.nan, index=range(n_subj), columns=cols)
    keep = np.array([f in ANCHORS.get(b, ()) for b, f in zip(t["basin"], t["fam"], strict=True)], bool)
    g = t[keep].groupby(["i", "fam"])["z"].agg(["median", "size"])
    g = g[g["size"] >= lad.anchor_min_n].reset_index()
    for f, gg in g.groupby("fam"):
        out.loc[gg["i"].to_numpy(), f] = gg["median"].to_numpy()
    return out


def offsets(df: pd.DataFrame, anc: pd.DataFrame, lad: Ladder = LADDER) -> pd.DataFrame:
    """Rev 2: the NEAREST anchor family with local witnesses (smallest |depth - anchor|), used only when that
    offset is within max_lever_ft. Returns offset_ft, anchor_used (the family) and nearest_anchor_ft (reported
    even when it exceeds the cap)."""
    z = df["depth_ft"].to_numpy(float)
    off, used, near = np.full(len(df), np.nan), np.full(len(df), None, dtype=object), np.full(len(df), np.nan)
    A = {f: anc[f].to_numpy(float) for f in anc.columns}
    for k, b in enumerate(df["basin"]):
        best = None
        for f in ANCHORS.get(b, ()):
            a = A[f][k]
            if np.isfinite(a) and np.isfinite(z[k]) and (best is None or abs(z[k] - a) < abs(best[1])):
                best = (f, z[k] - a)
        if best is None:
            continue
        near[k] = abs(best[1])
        if abs(best[1]) <= lad.max_lever_ft:
            used[k], off[k] = best
    return pd.DataFrame({"offset_ft": off, "anchor_used": used, "nearest_anchor_ft": near}, index=df.index)


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
        g = grid.iloc[i] if lad.use_grid and grid is not None and i < len(grid) else None
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
        # rev 2: never move INTO a cluster depth cannot split (the bench picked inside it would be a coin flip)
        if why is None and len(next((ms for ms, _ in cl if target in ms), [target])) > 1:
            why = "ambiguous_target"
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
    off = offsets(df, anc, lad)
    d = df.join(off)
    # rungs from ALL evidence wells: a county-wide median dilutes the local error clusters that sank v3, and
    # witnesses-only left the Delaware with no BS2_C / BS3_C / WCC rung (the vendors name those differently)
    rungs = calibrate(d, df["evidence"].to_numpy(bool), lad)
    res = assign(d, pairs, df, rungs, order, grid, True, lad)
    return off.join(res).assign(witness=wit), rungs


def run_sticks(sticks: pd.DataFrame, pairs_sp: pd.DataFrame, prod: pd.DataFrame, prod_witness: np.ndarray, rungs: pd.DataFrame,
               order: dict[str, list[str]], grid: pd.DataFrame | None = None, lad: Ladder = LADDER) -> pd.DataFrame:
    anc = anchors(pairs_sp, prod, prod_witness, len(sticks), lad)
    off = offsets(sticks, anc, lad)
    res = assign(sticks.join(off), pairs_sp, prod, rungs, order, grid, False, lad)
    return off.join(res)


def rule_record() -> dict:
    return {"revision": 3, "ladder": asdict(LADDER), "anchors": ANCHORS, "families": tr.FAMILY, "protected": sorted(tr.PROTECTED)}
