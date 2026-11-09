"""formation_blueox rule v5.2: the gross-miss step (docs/formation_tag_redesign/RULE_V5_2.md). Pure core.

v5 decides the unit where the vendors disagree; v5.1 decides a placeholder's sub-bench. Neither looks at a well whose
tag nobody disputes but whose DEPTH says it is in the wrong unit: both vendors agree on the wrong bench, one vendor only,
an OTHER / unmapped string, or a guarded conflict. sql/23 has done that job on top of sql/16 (> 600 ft off a band built
from the neighbours' own tags). v5.2 does it inside the rule, against the same witness depths as v5 and v5.1, so sql/23
can retire (Michael, 2026-11-08: one complete overhaul, no stacked fixes).

Per judged producer (evidence depth; human calls — overrides and carded calls — are never judged), with tag = the
accepted tag WITHOUT sql/23 (carded call > class-accepted v5 > sql/16's code):
  own reference   the witness depth of the tag's unit at the well (v5 unit witnesses: clean wells whose two vendors map
                  to the same unit; landing_surfaces.estimate within r_mi, >= n_min; the well itself left out).
  gross miss      |depth - own reference| > miss_ft.  OTHER / unmapped tags have no unit: they are always candidates,
                  held to the tighter other_match_ft (v5's bar for depth beating an OTHER call).
  placement       the unit whose witness depth is nearest, if within far_ft (other_match_ft for OTHER / unmapped) and
                  >= margin_ft nearer than every other referenced unit                       -> basis 'gm_move'
                  else the tag is kept, flagged                                              -> 'gm_unplaced'
  order guard     the referenced units from the tag's unit to the target must stand in stratigraphic order (for OTHER /
                  unmapped: the target and its nearest referenced unit above and below). Else  -> 'gm_inverted', kept.
  guards          never into or out of WDFD / BRNT / MISS; never BS3 <-> WCA in Lea / Ward (rule B pending)
                                                                                             -> 'gm_guard', kept.
  sub-bench       a single-code target unit is its code. A multi-code unit takes v5.1's depth decision among its codes
                  (sub-bench witnesses, margin_ft / far_ft, order) -> sub 'depth'; else the nearest referenced code ->
                  sub 'nearest' (low confidence); no referenced code -> 'gm_no_subbench', kept.
  not a miss      'gm_ok';  no own reference -> 'gm_no_control' (kept; reported).
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


def _ordered(zs: list[float]) -> bool:
    return bool(np.all(np.diff(zs) > 0)) if len(zs) > 1 else True


def _guarded(basin: str, county: object, own: str | None, tgt: str) -> bool:
    if {own, tgt} & tp.PROTECTED_UNITS:
        return True
    return basin == "delaware" and {own, tgt} == {"BS3", "WCA"} and county in tp.RULE_B_COUNTIES


def assign(d: pd.DataFrame, tag: str, r: tp.V5 = tp.RULE, g: V52 = RULE) -> pd.DataFrame:
    """d needs basin, county, x, y, depth_ft, evidence, novi_raw/env_raw, novi_code/env_code, the tag column and src
    (carded_call / override are never judged). Adds gm_code (the v5.2 tag), gm_basis, gm_own_gap_ft, gm_target,
    gm_target_gap_ft, gm_lead_ft, gm_sub."""
    d = d.copy()
    for c, v in (("gm_code", d[tag]), ("gm_basis", None), ("gm_own_gap_ft", np.nan), ("gm_target", None),
                 ("gm_target_gap_ft", np.nan), ("gm_lead_ft", np.nan), ("gm_sub", None)):
        d[c] = v
    uw = unit_witness(d)
    cw = pd.Series([ts1.witness_code(x) for x in d.itertuples()], index=d.index)
    judged = d["evidence"].astype(bool) & ~d["src"].isin(HUMAN) & d["depth_ft"].notna()
    for b in d["basin"].dropna().unique():
        order = tp.UNIT_ORDER.get(b, [])
        inb = d["basin"] == b
        own = pd.Series([tp.unit(b, c) for c in d[tag]], index=d.index)
        wit = {u: d.index[inb & (uw == u)] for u in order}
        wit = {u: ix for u, ix in wit.items() if len(ix) >= r.n_min}
        # pass 1: own-unit reference for every judged row with a unit in the column
        cand = []
        for u in own[inb & judged & own.isin(order)].unique():
            rows = d.index[inb & judged & (own == u)]
            if u not in wit:
                d.loc[rows, "gm_basis"] = "gm_no_control"
                continue
            w = wit[u]
            z = _refs(d.loc[w, ["x", "y"]].to_numpy(float), d.loc[w, "depth_ft"].to_numpy(float), w.to_numpy(),
                      d.loc[rows, ["x", "y"]].to_numpy(float), rows.to_numpy(), r)
            gap = np.abs(d.loc[rows, "depth_ft"].to_numpy(float) - z)
            d.loc[rows, "gm_own_gap_ft"] = gap
            d.loc[rows, "gm_basis"] = np.where(np.isnan(z), "gm_no_control", np.where(gap > g.miss_ft, None, "gm_ok"))
            cand.extend(rows[np.isfinite(gap) & (gap > g.miss_ft)])
        # OTHER / unmapped tags (no unit in the column) are always candidates, at the tighter tolerance
        loose = d.index[inb & judged & (own.isna() | ~own.isin(order))]
        cand = pd.Index(cand).append(loose)
        if not len(cand) or not wit:
            d.loc[loose, "gm_basis"] = "gm_other_kept"
            continue
        pts, pid = d.loc[cand, ["x", "y"]].to_numpy(float), cand.to_numpy()
        Z = {u: _refs(d.loc[w, ["x", "y"]].to_numpy(float), d.loc[w, "depth_ft"].to_numpy(float), w.to_numpy(), pts, pid, r)
             for u, w in wit.items()}
        for k, i in enumerate(cand):
            dep, o = float(d.at[i, "depth_ft"]), own[i]
            in_col = isinstance(o, str) and o in order
            ref = {u: Z[u][k] for u in order if u in Z and np.isfinite(Z[u][k])}
            if not ref:
                d.at[i, "gm_basis"] = "gm_unplaced" if in_col else "gm_other_kept"
                continue
            dist = sorted((abs(dep - z), u) for u, z in ref.items())
            best_gap, tgt = dist[0]
            lead = (dist[1][0] - best_gap) if len(dist) > 1 else np.inf
            tol = r.far_ft if in_col else r.other_match_ft
            d.at[i, "gm_target"], d.at[i, "gm_target_gap_ft"], d.at[i, "gm_lead_ft"] = tgt, best_gap, lead
            if best_gap > tol or lead < r.margin_ft or tgt == o:
                d.at[i, "gm_basis"] = "gm_unplaced" if in_col else "gm_other_kept"
                continue
            ti = order.index(tgt)
            if in_col:
                oi = order.index(o)
                span = [ref[u] for u in order[min(oi, ti): max(oi, ti) + 1] if u in ref]
            else:
                above = [u for u in order[:ti] if u in ref][-1:]
                below = [u for u in order[ti + 1:] if u in ref][:1]
                span = [ref[u] for u in above + [tgt] + below]
            if not _ordered(span):
                d.at[i, "gm_basis"] = "gm_inverted"
                continue
            if _guarded(b, d.at[i, "county"], o if in_col else None, tgt):
                d.at[i, "gm_basis"] = "gm_guard"
                continue
            code, sub = _subbench(d, b, tgt, i, cw, r)
            if code is None:
                d.at[i, "gm_basis"] = "gm_no_subbench"
                continue
            d.at[i, "gm_code"], d.at[i, "gm_sub"], d.at[i, "gm_basis"] = code, sub, "gm_move"
    return d


def _subbench(d: pd.DataFrame, basin: str, unit: str, i: object, cw: pd.Series, r: tp.V5) -> tuple[str | None, str | None]:
    codes = ts1.unit_codes(basin).get(unit)
    if not codes:
        return unit, "single"
    strat = sb.bench_order().get(basin, [])
    codes = sorted(codes, key=lambda c: strat.index(c) if c in strat else len(strat))
    pt, dep = d.loc[[i], ["x", "y"]].to_numpy(float), float(d.at[i, "depth_ft"])
    z = []
    for c in codes:
        w = d.index[(d["basin"] == basin) & (cw == c)]
        zz = _refs(d.loc[w, ["x", "y"]].to_numpy(float), d.loc[w, "depth_ft"].to_numpy(float), w.to_numpy(), pt, np.array([i]), r)
        z.append(zz[0])
    z = np.array(z)
    ok = np.isfinite(z)
    if not ok.any():
        return None, None
    dist = np.where(ok, np.abs(z - dep), np.inf)
    o = np.argsort(dist)
    if ok.sum() >= 2 and _ordered(list(z[ok])):
        lead = dist[o[1]] - dist[o[0]]
        if lead >= r.margin_ft and dist[o[0]] <= r.far_ft:
            return codes[o[0]], "depth"
    return codes[o[0]], "nearest"


def rule_record() -> dict:
    return {"v5_2": asdict(RULE), "v5": asdict(tp.RULE)}
