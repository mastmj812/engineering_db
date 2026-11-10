"""formation_blueox rule v5.2: the gross-miss step (docs/formation_tag_redesign/RULE_V5_2.md). Pure core.

v5 decides the unit where the vendors disagree; v5.1 decides a placeholder's sub-bench. Neither looks at a well whose
tag nobody disputes but whose DEPTH says it is in the wrong unit: both vendors agree on the wrong bench, one vendor only,
an OTHER / unmapped string, or a guarded conflict. sql/23 has done that job on top of sql/16 (> 600 ft off a band built
from the neighbours' own tags). v5.2 does it inside the rule, against witness depths, so sql/23 can retire (Michael,
2026-11-08: one complete overhaul, no stacked fixes).

Every depth reference is a CODE reference (rev 1): a multi-code unit's codes use v5.1's sub-bench witnesses, a
single-code unit's code uses v5's unit witnesses (both vendors map to that unit). landing_surfaces.estimate within r_mi,
>= n_min, the judged well itself left out. A unit's distance from a well = its nearest referenced code.

Per judged producer (evidence depth; human calls — overrides and carded calls — are never judged), with tag = the
accepted tag WITHOUT sql/23 (carded call > class-accepted v5 > sql/16's code):
  own gap         the distance to the tag's unit. If the well lies beyond the unit's outermost referenced code on a side
                  whose end code has no reference, the unit's extent there is unknown -> 'gm_no_control' (kept). Also
                  'gm_no_control' when no code of the unit is referenced.
  gross miss      own gap > miss_ft.  OTHER / unmapped tags have no unit: always candidates, at other_match_ft.
  placement       the nearest unit, if within far_ft (other_match_ft for OTHER / unmapped) and >= margin_ft nearer than
                  every other referenced unit                                               -> basis 'gm_move'
                  else kept, flagged                                                        -> 'gm_unplaced' /
                                                                                               'gm_other_kept'
  order guard     the referenced codes from the tag's code to the target code must stand in stratigraphic order (for
                  OTHER / unmapped: the target code and its nearest referenced code above and below) -> 'gm_inverted'.
  guards          never into or out of WDFD / BRNT / MISS; never BS3 <-> WCA in Lea / Ward (rule B pending) -> 'gm_guard'.
  sub-bench       a single-code unit is its code ('single'). A multi-code unit: v5.1's decision over its referenced
                  codes (>= 2, ordered, margin_ft / far_ft) -> 'depth'; else the nearest referenced code -> 'nearest'.
  not a miss      'gm_ok'.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import landing_surfaces as ls
from box import tag_precedence as tp
from box import tag_scoreboard as sb
from box import tag_subbench as ts1

HUMAN = frozenset({"carded_call", "override"})


@dataclass(frozen=True)
class V52:
    miss_ft: float = 600.0   # sql/23's threshold for a trusted survey depth = 2 x v5's far_ft


RULE = V52()


def _refs(wxy: np.ndarray, wz: np.ndarray, wid: np.ndarray, pts: np.ndarray, pid: np.ndarray, r: tp.V5) -> np.ndarray:
    """Witness depth at each point (NaN without >= n_min witnesses within r_mi), leaving out the point's own well."""
    out = np.full(len(pts), np.nan)
    if len(wz) == 0 or len(pts) == 0:
        return out
    for k, js in enumerate(cKDTree(wxy).query_ball_point(pts, r.r_mi * ls.M_PER_MI)):
        js = [j for j in js if wid[j] != pid[k]]
        if len(js) >= r.n_min:
            out[k] = ls.estimate(wxy[js], wz[js], pts[k])[0]
    return out


def unit_witness(d: pd.DataFrame) -> pd.Series:
    un = pd.Series([tp.unit(b, c) for b, c in zip(d["basin"], d["novi_code"], strict=True)], index=d.index)
    ue = pd.Series([tp.unit(b, c) for b, c in zip(d["basin"], d["env_code"], strict=True)], index=d.index)
    return un.where(d["evidence"].astype(bool) & un.notna() & (un == ue))


def code_witness(d: pd.DataFrame) -> pd.Series:
    """The code each well witnesses: a sub-bench witness (v5.1) in a multi-code unit, else its unit's single code."""
    uw = unit_witness(d)
    cw = pd.Series([ts1.witness_code(x) for x in d.itertuples()], index=d.index, dtype=object)
    single = pd.Series([u if isinstance(u, str) and u not in ts1.unit_codes(b) else None
                        for b, u in zip(d["basin"], uw, strict=True)], index=d.index, dtype=object)
    single = pd.Series([_code_of(b, u) if isinstance(u, str) else None for b, u in zip(d["basin"], single, strict=True)],
                       index=d.index, dtype=object)
    return cw.where(cw.notna(), single)


def _code_of(basin: str, unit: str) -> str:
    """The code of a single-code unit (Delaware BS1 -> BS1_S; a code outside tp.UNIT is its own unit)."""
    codes = [c for c, u in tp.UNIT.get(basin, {}).items() if u == unit]
    return codes[0] if codes else unit


def _ordered(zs: list[float]) -> bool:
    return bool(np.all(np.diff(zs) > 0)) if len(zs) > 1 else True


def _guarded(basin: str, county: object, own: str | None, tgt: str) -> bool:
    if {own, tgt} & tp.PROTECTED_UNITS:
        return True
    return basin == "delaware" and {own, tgt} == {"BS3", "WCA"} and county in tp.RULE_B_COUNTIES


def column(basin: str) -> list[str]:
    """Shallow -> deep codes whose unit is in the basin's unit order."""
    order = tp.UNIT_ORDER.get(basin, [])
    return [c for c in sb.bench_order().get(basin, []) if tp.unit(basin, c) in order]


def own_gap(dep: float, codes: list[str], ref: dict[str, float], miss_ft: float = RULE.miss_ft) -> float:
    """Distance from dep to the unit whose codes (shallow -> deep) are given. NaN when no code is referenced, or when
    the well is more than miss_ft beyond the outermost referenced code on a side whose end code has no reference (the
    unit's extent there is unknown, so a miss can't be called). Within miss_ft it is not a miss on any side."""
    zs = [ref[c] for c in codes if c in ref]
    if not zs:
        return np.nan
    gap = min(abs(dep - z) for z in zs)
    if gap > miss_ft and ((dep < min(zs) and codes[0] not in ref) or (dep > max(zs) and codes[-1] not in ref)):
        return np.nan
    return gap


def assign(d: pd.DataFrame, tag: str, r: tp.V5 = tp.RULE, g: V52 = RULE) -> pd.DataFrame:
    """d needs basin, county, x, y, depth_ft, evidence, novi_raw/env_raw, novi_code/env_code, the tag column and src
    (carded_call / override are never judged). Adds gm_code (the v5.2 tag), gm_basis, gm_own_gap_ft, gm_target,
    gm_target_gap_ft, gm_lead_ft, gm_sub."""
    d = d.copy()
    for c, v in (("gm_code", d[tag]), ("gm_basis", None), ("gm_own_gap_ft", np.nan), ("gm_target", None),
                 ("gm_target_gap_ft", np.nan), ("gm_lead_ft", np.nan), ("gm_sub", None)):
        d[c] = v
    cw = code_witness(d)
    judged = d["evidence"].astype(bool) & ~d["src"].isin(HUMAN) & d["depth_ft"].notna()
    for b in d["basin"].dropna().unique():
        col, order = column(b), tp.UNIT_ORDER.get(b, [])
        inb = d["basin"] == b
        wit = {c: d.index[inb & (cw == c)] for c in col}
        wit = {c: ix for c, ix in wit.items() if len(ix) >= r.n_min}
        own = pd.Series([tp.unit(b, c) for c in d[tag]], index=d.index)
        rows = d.index[inb & judged]
        if not len(rows) or not wit:
            continue
        pts, pid = d.loc[rows, ["x", "y"]].to_numpy(float), rows.to_numpy()
        Z = {c: _refs(d.loc[w, ["x", "y"]].to_numpy(float), d.loc[w, "depth_ft"].to_numpy(float), w.to_numpy(), pts, pid, r)
             for c, w in wit.items()}
        ucodes = {u: [c for c in col if tp.unit(b, c) == u] for u in order}
        for k, i in enumerate(rows):
            dep, o = float(d.at[i, "depth_ft"]), own[i]
            in_col = isinstance(o, str) and o in order
            ref = {c: Z[c][k] for c in col if c in Z and np.isfinite(Z[c][k])}
            if in_col:
                gap = own_gap(dep, ucodes[o], ref)
                d.at[i, "gm_own_gap_ft"] = gap
                if not np.isfinite(gap):
                    d.at[i, "gm_basis"] = "gm_no_control"
                    continue
                if gap <= g.miss_ft:
                    d.at[i, "gm_basis"] = "gm_ok"
                    continue
            miss = "gm_unplaced" if in_col else "gm_other_kept"
            udist = sorted((min(abs(dep - ref[c]) for c in cs if c in ref), u) for u, cs in ucodes.items() if any(c in ref for c in cs))
            if not udist:
                d.at[i, "gm_basis"] = miss
                continue
            best_gap, tgt = udist[0]
            lead = (udist[1][0] - best_gap) if len(udist) > 1 else np.inf
            tol = r.far_ft if in_col else r.other_match_ft
            d.at[i, "gm_target"], d.at[i, "gm_target_gap_ft"], d.at[i, "gm_lead_ft"] = tgt, best_gap, lead
            if best_gap > tol or lead < r.margin_ft or tgt == o:
                d.at[i, "gm_basis"] = miss
                continue
            code, sub = _subbench(dep, ucodes[tgt], ref)
            ti = col.index(code)
            if in_col:
                oc = d.at[i, tag] if d.at[i, tag] in col else ucodes[o][0]
                oi = col.index(oc)
                span = [ref[c] for c in col[min(oi, ti): max(oi, ti) + 1] if c in ref]
            else:
                above = [c for c in col[:ti] if c in ref][-1:]
                below = [c for c in col[ti + 1:] if c in ref][:1]
                span = [ref[c] for c in above + [code] + below]
            if not _ordered(span):
                d.at[i, "gm_basis"] = "gm_inverted"
                continue
            if _guarded(b, d.at[i, "county"], o if in_col else None, tgt):
                d.at[i, "gm_basis"] = "gm_guard"
                continue
            d.at[i, "gm_code"], d.at[i, "gm_sub"], d.at[i, "gm_basis"] = code, sub, "gm_move"
    return d


def _subbench(dep: float, codes: list[str], ref: dict[str, float], r: tp.V5 = tp.RULE) -> tuple[str, str]:
    """codes shallow -> deep, at least one referenced."""
    rc = [c for c in codes if c in ref]
    if len(codes) == 1:
        return codes[0], "single"
    dist = sorted((abs(dep - ref[c]), c) for c in rc)
    if (len(rc) >= 2 and _ordered([ref[c] for c in rc])
            and dist[1][0] - dist[0][0] >= r.margin_ft and dist[0][0] <= r.far_ft):
        return dist[0][1], "depth"
    return dist[0][1], "nearest"


def rule_record() -> dict:
    return {"v5_2": asdict(RULE), "v5": asdict(tp.RULE), "rev": 1}
