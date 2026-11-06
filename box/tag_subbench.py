"""formation_blueox rule v5.1: the sub-bench step (docs/formation_tag_redesign/RULE_V5_1.md). Pure core.

v5 decides the UNIT (lime / sand and upper / lower inside one interval grouped). When the code it keeps comes only from
a vendor string that names the interval but not the sub-bench (a PLACEHOLDER: Novi "WOLFCAMP A" -> WCA_1), nothing has
decided the sub-bench. v5.1 decides it by depth against SUB-BENCH WITNESSES (Michael, 2026-11-06, card 62 HAY EVELYNN
17/20 002 0023WA: proposed WCA_1, sits in the WCA_2 band; reverses Gate 0 Q1 (a) for placeholder codes only).

  placeholder row  the tag's code lies in a multi-code unit, and every vendor string that maps to that code is a
                   PLACEHOLDER (at least one does). Human calls (overrides, carded calls) and sql/23 codes are never
                   placeholder rows. A vendor naming a sub-bench (case C) keeps v5's handling (sql/16's choice).
  sub-bench witness  a clean evidence well whose two vendors map to the same multi-code unit, and whose SPECIFIC
                   (non-placeholder) strings all name one code (at least one does). Its sub-bench = that code.
  reference        each candidate code's witness depth at the row (landing_surfaces.estimate of its witnesses within
                   r_mi, >= n_min) — the v5 constants, untuned.
  decision         the nearest candidate with a reference, when it is >= margin_ft closer than every other referenced
                   candidate and within far_ft  -> that code, basis 'subbench_depth' (may confirm the placeholder);
                   fewer than two referenced candidates, or no clear winner  -> the placeholder kept, basis
                   'subbench_default', flagged.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import landing_surfaces as ls
from box import tag_precedence as tp

# (basin, vendor, raw string): names the interval, not the sub-bench, where the column splits it. Pinned by a test.
PLACEHOLDER: frozenset[tuple[str, str, str]] = frozenset({
    ("delaware", "novi", "WOLFCAMP A"),
    ("delaware", "novi", "WOLFCAMP B"),
    ("midland", "novi", "WOLFCAMP B"),
    ("delaware", "env", "2ND BONE SPRING"),   # Enverus has no lime string in the Bone Spring; its SAND string is specific
    ("delaware", "env", "3RD BONE SPRING"),
})
HUMAN_OR_SQL23 = frozenset({"carded_call", "override", "sql23_kept"})


def unit_codes(basin: str) -> dict[str, list[str]]:
    """unit -> its codes, for units with more than one code."""
    out: dict[str, list[str]] = {}
    for code, u in tp.UNIT.get(basin, {}).items():
        out.setdefault(u, []).append(code)
    return {u: sorted(c) for u, c in out.items() if len(c) > 1}


def _multi(basin: str, code: object) -> bool:
    return isinstance(code, str) and tp.unit(basin, code) in unit_codes(basin)


def is_placeholder(basin: str, vendor: str, raw: object) -> bool:
    return isinstance(raw, str) and (basin, vendor, raw.strip().upper()) in PLACEHOLDER


def placeholder_row(r: pd.Series | tuple, tag: str) -> bool:
    b, code = r.basin, getattr(r, tag)
    if getattr(r, "src", None) in HUMAN_OR_SQL23 or not _multi(b, code):
        return False
    sup = [(v, getattr(r, f"{v}_raw")) for v in ("novi", "env") if getattr(r, f"{v}_code") == code]
    return bool(sup) and all(is_placeholder(b, v, raw) for v, raw in sup)


def witness_code(r: pd.Series | tuple) -> str | None:
    b = r.basin
    if not r.evidence or not _multi(b, r.novi_code) or tp.unit(b, r.novi_code) != tp.unit(b, r.env_code):
        return None
    spec = {getattr(r, f"{v}_code") for v in ("novi", "env") if not is_placeholder(b, v, getattr(r, f"{v}_raw"))}
    return spec.pop() if len(spec) == 1 else None


def assign(d: pd.DataFrame, tag: str, r: tp.V5 = tp.RULE) -> pd.DataFrame:
    """d needs basin, x, y, depth_ft, evidence, novi_raw/env_raw, novi_code/env_code, the tag column, and src (the
    tag's provenance: carded_call / override / sql23_kept exempt). Adds placeholder, wit_code, z_<code> refs,
    sb_code (the v5.1 tag), sb_basis, sb_lead_ft."""
    d = d.copy()
    d["placeholder"] = [placeholder_row(x, tag) for x in d.itertuples()]
    d["wit_code"] = [witness_code(x) for x in d.itertuples()]
    d["sb_code"], d["sb_basis"], d["sb_lead_ft"] = d[tag], None, np.nan
    rm = r.r_mi * ls.M_PER_MI
    for b in d["basin"].unique():
        for u, codes in unit_codes(b).items():
            rows = d.index[(d["basin"] == b) & d["placeholder"] & (d[tag].map(lambda c, b=b: tp.unit(b, c)) == u)]
            if not len(rows):
                continue
            pts = d.loc[rows, ["x", "y"]].to_numpy(float)
            refs = {}
            for c in codes:
                w = d[(d["basin"] == b) & (d["wit_code"] == c)]
                z = np.full(len(rows), np.nan)
                if len(w) >= r.n_min:
                    wxy, wz = w[["x", "y"]].to_numpy(float), w["depth_ft"].to_numpy(float)
                    for k, js in enumerate(cKDTree(wxy).query_ball_point(pts, rm)):
                        if len(js) >= r.n_min:
                            z[k] = ls.estimate(wxy[js], wz[js], pts[k])[0]
                refs[c] = z
                d.loc[rows, f"z_{c}"] = z
            dep = d.loc[rows, "depth_ft"].to_numpy(float)
            Z = np.column_stack([refs[c] for c in codes])
            dist = np.abs(Z - dep[:, None])
            for k, i in enumerate(rows):
                ok = np.isfinite(dist[k])
                if ok.sum() < 2:
                    d.at[i, "sb_basis"] = "subbench_default"
                    continue
                order = np.argsort(np.where(ok, dist[k], np.inf))
                best, second = order[0], order[1]
                lead = dist[k, second] - dist[k, best]
                d.at[i, "sb_lead_ft"] = lead
                if lead >= r.margin_ft and dist[k, best] <= r.far_ft:
                    d.at[i, "sb_code"], d.at[i, "sb_basis"] = codes[best], "subbench_depth"
                else:
                    d.at[i, "sb_basis"] = "subbench_default"
    return d
