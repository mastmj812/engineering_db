"""formation_blueox rule v3 — step 1 of docs/formation_tag_redesign/PLAN.md (draft; constants FROZEN in RULE).

Family from the vendor, position from depth. One rule for producers and Novi sticks. Pure core: no DB, and the
grids are passed in. Nothing here writes anywhere.

Per subject (a producing horizontal, or a stick):

  0. Evidence. Planned surveys, round-100 tvd_ft without a survey, and depths < 4,000 ft are NOT evidence (they
     are never neighbours) and are never re-positioned: such a subject keeps its vendor code (basis `no_depth`,
     confidence low).
  1. Family. FAMILY groups the codes depth may split: Delaware AVA {AVA_0, AVA_1, AVA_2}, WCA {WCXY, WCA_1,
     WCA_2}, WCB {WCB_1, WCB_2}; Midland WCB {WCB_1, WCB_2}. Every other code is its own family (sand vs carbonate
     is a lithology call, so BS2_C / BS2_S stay apart).
     a. Delaware, where the geologist's grid controls the well's dominant interval (both bounding surfaces with a
        pick within TRUST_MAX_FT, >= half the lateral in that interval): keep the vendor family if the interval
        allows it, or if the well sits within grid_min_miss_ft of the family's span. Otherwise move to the
        interval's family (basis `grid`). An interval that allows two families (his B2 -> C holds WCB_2 and WCC)
        is resolved by the local family bands, or not at all.
     b. Elsewhere (Midland, Delaware without control): local family bands. These are the median depth of each
        family among evidence neighbours within fam_radius_mi, from their VENDOR codes. Move to an adjacent
        family when the well is fam_margin_ft closer to that band, is fam_min_off_ft off its own band, both bands
        have fam_min_n wells, and the two bands are fam_min_sep_ft apart (basis `local_band`).
     Never: into or out of a protected bench (sql/23 guard); a BS2_C <-> BS2_S or BS3_C <-> BS3_S swap; across his
     XY top in Lea / Ward (rule B pending); a grid move on a no-control surface (Pecos Wolfcamp); a move into a
     held / suspect interval (WCD, WOLFCAMP_D). A blocked move keeps the vendor family and is flagged.
  2. Position, inside a multi-code family. Local code bands from evidence neighbours within pos_radius_mi
     (widened to pos_radius2_mi when thin), using the CURRENT pass's codes. A code band needs pos_min_n wells.
     Adjacent bands must be ordered and pos_min_sep_ft apart, or depth cannot resolve them there (Q1 (a): keep the
     vendor code, confidence low). Boundaries are the midpoints between adjacent band medians, and the well takes
     the band its depth falls in. Confidence is high when its margin to the nearest boundary is >= max(conf_min_ft,
     conf_frac x the gap). Re-run `passes` times on producers, so mis-tagged wells stop anchoring the bands.
  3. Ratified overrides win (applied by the caller, after the rule; the rule never reads them, not even as
     neighbour evidence, so the labelled-set score is not leaked).

Sticks (assign_sticks) take step 2 against the producers' FINAL codes. A stick is never moved across families: a
family conflict (grid or band) is a flag (`family_conflict`), per the plan (the Lea WCB case).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from box import tag_scoreboard as sb

FAMILY: dict[str, dict[str, str]] = {
    "delaware": {"AVA_0": "AVA", "AVA_1": "AVA", "AVA_2": "AVA", "WCXY": "WCA", "WCA_1": "WCA", "WCA_2": "WCA",
                 "WCB_1": "WCB", "WCB_2": "WCB"},
    "midland": {"WCB_1": "WCB", "WCB_2": "WCB"},
}
PROTECTED = frozenset({"WDFD", "BRNT", "MISS"})
LITH_PAIRS = (frozenset({"BS2_C", "BS2_S"}), frozenset({"BS3_C", "BS3_S"}))
RULE_B_COUNTIES = frozenset({"Lea", "Ward"})
# geologist interval (labelled by its top surface, tops_qc.INTERVALS) -> the codes it can hold
INTERVAL_CODES: dict[str, tuple[str, ...]] = {
    "AVALON1": ("AVA_0", "AVA_1"), "AVALON2": ("AVA_2",), "1BSPGS": ("BS1_S",), "2BSPGC": ("BS2_C",), "2BSPGS": ("BS2_S",),
    "3BSPGC": ("BS3_C",), "3BSPGS": ("BS3_S",), "WOLFCAMP_XY": ("WCXY", "WCA_1", "WCA_2"), "WOLFCAMP_A": ("WCXY", "WCA_1", "WCA_2"),
    "WOLFCAMP-B1": ("WCB_1",), "WOLFCAMP-B2": ("WCB_2", "WCC"),
}


@dataclass(frozen=True)
class Rule:
    fam_radius_mi: float = 1.5
    fam_min_n: int = 5
    fam_margin_ft: float = 100.0
    fam_min_off_ft: float = 150.0
    fam_min_sep_ft: float = 150.0
    grid_min_miss_ft: float = 50.0
    grid_min_share: float = 0.5
    pos_radius_mi: float = 1.0
    pos_radius2_mi: float = 1.5   # widened ring = the family radius (a 2-mi ring is ~billions of point pairs basin-wide)
    pos_min_n: int = 3
    pos_min_sep_ft: float = 75.0
    conf_frac: float = 0.25
    conf_min_ft: float = 30.0
    passes: int = 2


RULE = Rule()


def family(basin: str, code: str | None) -> str | None:
    if code is None or (isinstance(code, float) and np.isnan(code)):
        return None
    return FAMILY.get(basin, {}).get(code, code)


def family_order(order: dict[str, list[str]]) -> dict[str, list[str]]:
    """Families shallow -> deep per basin (codes collapsed, first appearance order)."""
    out = {}
    for b, cs in order.items():
        seen: list[str] = []
        for c in cs:
            f = family(b, c)
            if f not in seen:
                seen.append(f)
        out[b] = seen
    return out


def family_codes(order: dict[str, list[str]]) -> dict[tuple[str, str], list[str]]:
    out: dict[tuple[str, str], list[str]] = {}
    for b, cs in order.items():
        for c in cs:
            out.setdefault((b, family(b, c)), []).append(c)
    return out


def _blocked(basin: str, county: str | None, frm: str, to: str, crossing_xy: bool) -> str | None:
    if frm in PROTECTED or to in PROTECTED:
        return "protected"
    if any({frm, to} <= p for p in LITH_PAIRS):
        return "lithology"
    if crossing_xy and (county or "") in RULE_B_COUNTIES:
        return "rule_b_pending"
    return None


def _crosses_xy(basin: str, f1: str, f2: str) -> bool:
    return basin == "delaware" and {f1, f2} & {"BS3_S", "BS3_C"} != set() and {f1, f2} & {"WCA"} != set()


# ----------------------------------------------------------------------------
# Bands (vectorised over a pair table)
# ----------------------------------------------------------------------------


def _bands(pairs: pd.DataFrame, key: np.ndarray, depth: np.ndarray, ok: np.ndarray, d_max: float) -> pd.DataFrame:
    """Median depth and count per (subject i, key of neighbour j), over evidence neighbours j within d_max."""
    p = pairs[(pairs["d"] <= d_max) & ok[pairs["j"].to_numpy()]]
    t = pd.DataFrame({"i": p["i"].to_numpy(), "k": key[p["j"].to_numpy()], "z": depth[p["j"].to_numpy()]})
    t = t[pd.notna(t["k"])]
    return t.groupby(["i", "k"])["z"].agg(med="median", n="size").reset_index()


def _band_lookup(b: pd.DataFrame, min_n: int) -> dict[tuple[int, str], tuple[float, int]]:
    b = b[b["n"] >= min_n]
    return {(i, k): (m, n) for i, k, m, n in zip(b["i"], b["k"], b["med"], b["n"], strict=True)}


# ----------------------------------------------------------------------------
# Step 1: family
# ----------------------------------------------------------------------------


def family_stage(df: pd.DataFrame, pairs: pd.DataFrame, order: dict[str, list[str]], grid: pd.DataFrame | None,
                 r: Rule = RULE, move: bool = True) -> pd.DataFrame:
    """df (positional index) columns: basin, county, vendor, depth_ft, evidence (bool). grid (optional, indexed
    like df) columns: dom_interval, dom_share, controlled (bool), fam_miss_ft, no_control (bool). Returns family,
    family_basis, family_flag (blocked reason / family_conflict)."""
    fo = family_order(order)
    vf = np.array([family(b, c) for b, c in zip(df["basin"], df["vendor"], strict=True)], dtype=object)
    depth = df["depth_ft"].to_numpy(float)
    ev = df["evidence"].to_numpy(bool)
    lk = _band_lookup(_bands(pairs, vf, depth, ev, r.fam_radius_mi * sb.M_PER_MI), r.fam_min_n)
    fam, basis, flag = vf.copy(), np.full(len(df), "vendor", dtype=object), np.full(len(df), None, dtype=object)

    def nearest_band(i: int, cands: list[str]) -> str | None:
        best = None
        for f in cands:
            m = lk.get((i, f))
            if m is not None and (best is None or abs(depth[i] - m[0]) < abs(depth[i] - best[1])):
                best = (f, m[0])
        return best[0] if best else None

    for i in range(len(df)):
        b, f0, cty = df["basin"].iat[i], vf[i], df["county"].iat[i]
        if f0 is None or b not in fo or f0 not in fo[b]:
            continue
        if not ev[i]:
            basis[i] = "no_depth"
            continue
        target, how = None, None
        g = grid.iloc[i] if grid is not None and i < len(grid) else None
        use_grid = (g is not None and isinstance(g.get("dom_interval"), str) and bool(g.get("controlled"))
                    and not bool(g.get("no_control")) and float(g.get("dom_share") or 0) >= r.grid_min_share)
        if use_grid:
            codes = INTERVAL_CODES.get(g["dom_interval"])
            miss = float(g.get("fam_miss_ft")) if pd.notna(g.get("fam_miss_ft")) else np.nan
            if codes is None or not np.isfinite(miss):
                use_grid = False  # held / suspect / unmapped interval: fall back to bands
            else:
                basis[i] = "grid"
                allowed = list(dict.fromkeys(family(b, c) for c in codes))
                if f0 in allowed or abs(miss) < r.grid_min_miss_ft:
                    continue
                target = allowed[0] if len(allowed) == 1 else nearest_band(i, allowed)
                how = "grid"
                if target is None:
                    flag[i] = "family_conflict"
                    continue
        if not use_grid:
            own = lk.get((i, f0))
            if own is None:
                continue
            basis[i] = "local_band"
            k = fo[b].index(f0)
            best = None
            for kk in (k - 1, k + 1):
                if not 0 <= kk < len(fo[b]):
                    continue
                adj = lk.get((i, fo[b][kk]))
                if adj is None or abs(adj[0] - own[0]) < r.fam_min_sep_ft:
                    continue
                closer = abs(depth[i] - adj[0]) + r.fam_margin_ft <= abs(depth[i] - own[0])
                if (closer and abs(depth[i] - own[0]) >= r.fam_min_off_ft
                        and (best is None or abs(depth[i] - adj[0]) < abs(depth[i] - best[1]))):
                    best = (fo[b][kk], adj[0])
            if best is None:
                continue
            target, how = best[0], "local_band"
        why = _blocked(b, cty, f0, target, _crosses_xy(b, f0, target))
        if why:
            flag[i] = why
            continue
        if move:
            fam[i], basis[i] = target, how
        else:
            flag[i] = "family_conflict"
    return pd.DataFrame({"family": fam, "family_basis": basis, "family_flag": flag}, index=df.index)


# ----------------------------------------------------------------------------
# Step 2: position
# ----------------------------------------------------------------------------


def position(depth: float, bands: dict[str, tuple[float, int]], codes: list[str], r: Rule = RULE) -> tuple[str | None, float, bool]:
    """(code, margin_ft, resolvable) from the family's local code bands. Unresolvable when fewer than two codes
    have bands, or any adjacent pair present is out of order or closer than pos_min_sep_ft."""
    have = [c for c in codes if c in bands]
    if len(have) < 2:
        return None, np.nan, False
    meds = [bands[c][0] for c in have]
    gaps = np.diff(meds)
    if (gaps < r.pos_min_sep_ft).any():
        return None, np.nan, False
    bounds = (np.asarray(meds[:-1]) + np.asarray(meds[1:])) / 2.0
    k = int(np.searchsorted(bounds, depth))
    near = [abs(depth - bounds[j]) for j in (k - 1, k) if 0 <= j < len(bounds)]
    gap_near = [gaps[j] for j in (k - 1, k) if 0 <= j < len(gaps)]
    margin = float(min(near))
    need = max(r.conf_min_ft, r.conf_frac * float(min(gap_near)))
    return have[k], margin, margin >= need


def position_stage(df: pd.DataFrame, fam: pd.Series, codes_in: np.ndarray, pairs: pd.DataFrame, ref_codes: np.ndarray,
                   ref_depth: np.ndarray, ref_ok: np.ndarray, order: dict[str, list[str]], r: Rule = RULE) -> pd.DataFrame:
    """One position pass. Subjects i (df rows), neighbours j index the reference arrays."""
    fc = family_codes(order)
    near = _band_lookup(_bands(pairs, ref_codes, ref_depth, ref_ok, r.pos_radius_mi * sb.M_PER_MI), r.pos_min_n)
    wide = _band_lookup(_bands(pairs, ref_codes, ref_depth, ref_ok, r.pos_radius2_mi * sb.M_PER_MI), r.pos_min_n)
    out_code, basis, conf, margin = codes_in.copy(), np.full(len(df), "vendor", dtype=object), np.full(len(df), "low", dtype=object), np.full(len(df), np.nan)
    depth = df["depth_ft"].to_numpy(float)
    ev = df["evidence"].to_numpy(bool)
    for i in range(len(df)):
        b, f = df["basin"].iat[i], fam.iat[i]
        codes = fc.get((b, f), [])
        if len(codes) <= 1:
            if codes:
                out_code[i] = codes[0]
            basis[i] = "single"
            conf[i] = "high" if ev[i] else "low"
            continue
        if not ev[i]:
            basis[i] = "no_depth"
            continue
        for lk in (near, wide):
            bands = {c: lk[(i, c)] for c in codes if (i, c) in lk}
            code, m, ok_conf = position(depth[i], bands, codes, r)
            if code is not None:
                out_code[i], basis[i], conf[i], margin[i] = code, "local_band", "high" if ok_conf else "low", m
                break
        else:
            if out_code[i] not in codes:  # family moved but depth cannot place it: nearest band, else abstain
                cands = {c: v for c in codes for lk in (wide,) if (v := lk.get((i, c))) is not None}
                out_code[i] = min(cands, key=lambda c: abs(depth[i] - cands[c][0])) if cands else None
                basis[i] = "nearest_band" if cands else "abstain"
    return pd.DataFrame({"code": out_code, "position_basis": basis, "confidence": conf, "position_margin_ft": margin}, index=df.index)


# ----------------------------------------------------------------------------
# Producers and sticks
# ----------------------------------------------------------------------------


def assign_producers(df: pd.DataFrame, pairs: pd.DataFrame, order: dict[str, list[str]], grid: pd.DataFrame | None = None,
                     r: Rule = RULE) -> pd.DataFrame:
    """The rule on producers (pairs = neighbour_pairs over df itself, self excluded by construction)."""
    fam = family_stage(df, pairs, order, grid, r)
    codes = df["vendor"].to_numpy(object).copy()
    vf = np.array([family(b, c) for b, c in zip(df["basin"], df["vendor"], strict=True)], dtype=object)
    codes[fam["family"].to_numpy(object) != vf] = None  # a moved family drops its old code
    ev = df["evidence"].to_numpy(bool)
    depth = df["depth_ft"].to_numpy(float)
    pos = None
    for _ in range(r.passes):
        ref = codes if pos is None else pos["code"].to_numpy(object)
        pos = position_stage(df, fam["family"], codes, pairs, ref, depth, ev, order, r)
    out = df[["vendor"]].join(fam).join(pos)
    # abstain = keep the vendor code (Q1 (a)): a family move that depth cannot place reverts, flagged
    ab = out["code"].isna() & out["vendor"].notna()
    out.loc[ab, "family"] = [family(b, c) for b, c in zip(df.loc[ab, "basin"], df.loc[ab, "vendor"], strict=True)]
    out.loc[ab, "family_flag"] = "family_conflict"
    out.loc[ab, "code"] = out.loc[ab, "vendor"]
    out["rule"] = out["code"]
    return out


def assign_sticks(sticks: pd.DataFrame, prod: pd.DataFrame, prod_codes: np.ndarray, pairs_sp: pd.DataFrame,
                  order: dict[str, list[str]], grid: pd.DataFrame | None = None, r: Rule = RULE) -> pd.DataFrame:
    """The rule on sticks against the producers' final codes. pairs_sp: i = stick row, j = producer row.
    Family conflicts are flagged, never moved."""
    pv = np.array([family(b, c) for b, c in zip(prod["basin"], prod_codes, strict=True)], dtype=object)
    ev = prod["evidence"].to_numpy(bool)
    pz = prod["depth_ft"].to_numpy(float)
    fam = _stick_family(sticks, pairs_sp, pv, pz, ev, order, grid, r)
    pos = position_stage(sticks, fam["family"], sticks["vendor"].to_numpy(object).copy(), pairs_sp, np.asarray(prod_codes, object),
                         pz, ev, order, r)
    out = sticks[["vendor"]].join(fam).join(pos)
    out["rule"] = out["code"]
    return out


def _stick_family(sticks: pd.DataFrame, pairs_sp: pd.DataFrame, pv: np.ndarray, pz: np.ndarray, ev: np.ndarray,
                  order: dict[str, list[str]], grid: pd.DataFrame | None, r: Rule) -> pd.DataFrame:
    """family_stage with move=False, using producer bands across the stick->producer pairs."""
    fo = family_order(order)
    lk = _band_lookup(_bands(pairs_sp, pv, pz, ev, r.fam_radius_mi * sb.M_PER_MI), r.fam_min_n)
    vf = np.array([family(b, c) for b, c in zip(sticks["basin"], sticks["vendor"], strict=True)], dtype=object)
    depth = sticks["depth_ft"].to_numpy(float)
    flag = np.full(len(sticks), None, dtype=object)
    basis = np.full(len(sticks), "vendor", dtype=object)
    for i in range(len(sticks)):
        b, f0 = sticks["basin"].iat[i], vf[i]
        if f0 is None or b not in fo or f0 not in fo[b] or not np.isfinite(depth[i]):
            continue
        g = grid.iloc[i] if grid is not None and i < len(grid) else None
        if (g is not None and isinstance(g.get("dom_interval"), str) and bool(g.get("controlled")) and not bool(g.get("no_control"))
                and float(g.get("dom_share") or 0) >= r.grid_min_share and g["dom_interval"] in INTERVAL_CODES
                and pd.notna(g.get("fam_miss_ft"))):
            basis[i] = "grid"
            allowed = {family(b, c) for c in INTERVAL_CODES[g["dom_interval"]]}
            if f0 not in allowed and abs(float(g["fam_miss_ft"])) >= r.grid_min_miss_ft:
                flag[i] = "family_conflict"
            continue
        own = lk.get((i, f0))
        if own is None:
            continue
        basis[i] = "local_band"
        k = fo[b].index(f0)
        for kk in (k - 1, k + 1):
            adj = lk.get((i, fo[b][kk])) if 0 <= kk < len(fo[b]) else None
            if (adj is not None and abs(adj[0] - own[0]) >= r.fam_min_sep_ft
                    and abs(depth[i] - adj[0]) + r.fam_margin_ft <= abs(depth[i] - own[0]) and abs(depth[i] - own[0]) >= r.fam_min_off_ft):
                flag[i] = "family_conflict"
    return pd.DataFrame({"family": vf, "family_basis": basis, "family_flag": flag}, index=sticks.index)


# ----------------------------------------------------------------------------
# Grid evidence per well (Delaware)
# ----------------------------------------------------------------------------


def family_span(basin: str, fam: str, order: dict[str, list[str]]) -> tuple[str, str] | None:
    """(top surface, base surface) spanned by a family's codes in tops_qc.TAG_INTERVAL (None if any code lacks one)."""
    from box import tops_qc as tq

    codes = family_codes(order).get((basin, fam), [])
    if not codes or any(c not in tq.TAG_INTERVAL for c in codes):
        return None
    idx = {s: k for k, s in enumerate(tq.STACK)}
    tops = [tq.TAG_INTERVAL[c][0] for c in codes]
    bases = [tq.TAG_INTERVAL[c][1] for c in codes]
    return min(tops, key=idx.get), max(bases, key=idx.get)


def grid_evidence(stations: pd.DataFrame, depths: np.ndarray, wells: pd.DataFrame, order: dict[str, list[str]],
                  ctrl: dict[str, np.ndarray], trust_ft: float) -> pd.DataFrame:
    """Per well (wells indexed by api10, columns basin, vendor, county): dominant interval + share, its control,
    and the median signed miss of the stations against the VENDOR family's span.
    ctrl = {surface: distance-to-control array aligned with wells}."""
    from box import tops_qc as tq

    iv = np.array(tq.INTERVALS, dtype=object)[tq.interval_index(depths, stations["tvd"].to_numpy(float))]
    s = pd.DataFrame({"api10": stations["api10"].to_numpy(), "iv": iv})
    dom = s.groupby(["api10", "iv"]).size().rename("n").reset_index().sort_values(["api10", "n"], ascending=[True, False])
    tot = s.groupby("api10").size()
    dom = dom.drop_duplicates("api10").set_index("api10")
    out = pd.DataFrame(index=wells.index)
    out["dom_interval"] = dom["iv"]
    out["dom_share"] = dom["n"] / tot
    idx = {sname: k for k, sname in enumerate(tq.STACK)}
    # control of the dominant interval: its top surface and the next surface down
    ctl = np.zeros(len(out), bool)
    pos = {a: k for k, a in enumerate(wells.index)}
    for a, d in out["dom_interval"].items():
        if not isinstance(d, str) or d not in idx or idx[d] + 1 >= len(tq.STACK):
            continue
        top, base = d, tq.STACK[idx[d] + 1]
        k = pos[a]
        dt_, db_ = ctrl.get(top, np.full(len(out), np.nan))[k], ctrl.get(base, np.full(len(out), np.nan))[k]
        ctl[k] = bool(np.isfinite(dt_) and np.isfinite(db_) and dt_ <= trust_ft and db_ <= trust_ft)
    out["controlled"] = ctl
    nc = tq.NO_CONTROL_SURFACES_BY_COUNTY
    out["no_control"] = [isinstance(d, str) and (d in nc.get(c or "", frozenset()) or
                         (idx.get(d, -9) + 1 < len(tq.STACK) and tq.STACK[idx.get(d, -9) + 1] in nc.get(c or "", frozenset())))
                         for d, c in zip(out["dom_interval"], wells["county"], strict=True)]
    # signed miss vs the vendor family's span, per station, median per well
    span = {f: family_span("delaware", f, order) for f in family_order(order)["delaware"]}
    vf = wells.apply(lambda w: family(w["basin"], w["vendor"]), axis=1)
    sv = stations["api10"].map(vf)
    top = np.full(len(stations), np.nan)
    base = np.full(len(stations), np.nan)
    for f, sp in span.items():
        if sp is None:
            continue
        m = (sv == f).to_numpy()
        top[m], base[m] = depths[m, idx[sp[0]]], depths[m, idx[sp[1]]]
    miss = tq.signed_miss(stations["tvd"].to_numpy(float), top, base)
    out["fam_miss_ft"] = pd.Series(miss).groupby(stations["api10"].to_numpy()).median()
    return out


def rule_record() -> dict:
    return {"rule": asdict(RULE), "family": FAMILY, "protected": sorted(PROTECTED), "interval_codes": INTERVAL_CODES}
