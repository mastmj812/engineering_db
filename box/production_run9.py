"""BOX run 9 — the per-group pieces of the first COMPLETE record run (pure, DB-free).

Run 9 = every in-scope Delaware bench in one record run (not appended to run 8):
  validated  (coverage `covered`):             WCA, BS2_S (box_v2_wf, own haircut), WCXY_WCA1, WCB_1, WCC (raw box_v2)
  provisional (coverage `covered_provisional`, D105 / sql/63): AVA_0, AVA_1, AVA_2, BS2_C (D105, never out-of-time tested);
                                               BS3_S, BS3_C, WCB_2, BS1_S (holdout FAIL 2026-10-18 -> provisional, raw box_v2)

  wells_dir(group, default)    the analog-pool well set each group was tuned / holdout-scored on (step-15 QC sets; WCA / BS2_S / WCXY
                               keep the D84 pool refresh passed as --wells).
  tier(group)                  'validated' or 'provisional' (BENCH_SPECS["provisional"]; the coverage class is box.production.covered_class).
  guard_table / guard_tail     the 9c haircut guard (Michael, step-15 tuning gate 2026-10-17): refuse a haircut whose D62 cum-k factors
                               are not monotone in k, or whose D92 g(48) leaves [0.6, 1.2]. Tolerances are module constants (stated
                               in the run record) — see GUARD.
  validated15_disclosure(b)    WCB_1 / WCC: D100 pattern — disclosed bias = the tuning bias per D99 cell (pooled), the one-time
                               holdout bias with its frozen interval, + the D69 radius-class range (tuning, record variant).
  provisional_disclosure(b)    D105: pooled in-sample bias + 95 % block-bootstrap range; holdout-fail benches also carry the holdout
                               and tuning + holdout lines (never the pooled number alone); the latest-vintage line; radius range.
  group_flags(group, region)   workup text that travels in pud_forecast.flags (tier, call-outs, the tuning-gate edge caveats).

Error convention everywhere: actual / forecast - 1 (negative = the forecast is HIGH).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import production as pr

DOCS = Path("docs") / "box"
STEP15_TUNING = DOCS / "step15-tuning-2026-10-17"
STEP15_HOLDOUT = DOCS / "step15-holdout-2026-10-18"
STEP15_PROV = DOCS / "step15-provisional-2026-10-17"
RUN9_INPUTS = DOCS / "run9-2026-10-18" / "inputs"  # spread_by_radius_<b>.csv + edge_regions_<b>.csv (scripts.box_run9_prep)

GROUPS: tuple[str, ...] = ("WCA", "BS2_S", "WCXY_WCA1", "WCB_1", "WCC",
                           "AVA_0", "AVA_1", "AVA_2", "BS2_C", "BS3_S", "BS3_C", "WCB_2", "BS1_S")
VALIDATED_15 = ("WCB_1", "WCC")
D105_BENCHES = ("AVA_0", "AVA_1", "AVA_2", "BS2_C")
HOLDOUT_FAIL = ("BS3_S", "BS3_C", "WCB_2", "BS1_S")

# the well set each step-15 group was tuned + holdout-scored on (summary_*.json wells_dir of runs/box15t, runs/box15h)
_WELLS: dict[str, Path] = {"WCB_1": DOCS / "step15-WCB-2026-10-16", "WCB_2": DOCS / "step15-WCB-2026-10-16",
                           "WCC": DOCS / "step15-WCC-2026-10-16", "BS1_S": DOCS / "step15-BS1-2026-10-16",
                           "BS2_C": DOCS / "step15-BS2C-2026-10-16", "BS3_S": DOCS / "step15a-2026-10-16",
                           "BS3_C": DOCS / "step15a-2026-10-16", "AVA_0": DOCS / "step15-AVA-2026-10-16",
                           "AVA_1": DOCS / "step15-AVA-2026-10-16", "AVA_2": DOCS / "step15-AVA-2026-10-16"}


def wells_dir(group: str, default: Path) -> Path:
    return _WELLS.get(group, default)


def is_provisional(group: str) -> bool:
    return bool(ac.BENCH_SPECS[group].get("provisional"))


def tier(group: str) -> str:
    return "provisional" if is_provisional(group) else "validated"


# ----------------------------------------------------------------------------
# 9c haircut guard
# ----------------------------------------------------------------------------

# Decided (Michael, 2026-10-17): refuse g(48) outside [0.6, 1.2] or non-monotone cum-k factors. As built here:
#  - monotone: the D62 factors at 12 / 24 / 36 / 48 must be non-increasing or non-decreasing, each reversal <= mono_tol (0.01, a
#    cum-factor noise floor; WCB_1 gas 1.189 -> 1.354 -> 1.252 reverses by 0.10). The defects that motivated the guard (BS3_C oil
#    g(48) 1.48, WCB_1 g(48) 0.40 / 1.60) are caught by the g(48) band; BS3_C oil 0.915 / 0.919 / 1.106 is monotone as numbers.
#  - g(48): the MEDIAN location's D92 tail factor must lie in [0.6, 1.2] (the statistic the tuning gate quoted, e.g. BS3_S 0.995);
#    min / max across locations are recorded beside it.
# Literal-strict reading (no tolerance, every location) would refuse WCA gas (1.0213 -> 1.0190 at cum-24 -> 36) and BS2_S gas
# (location min g(48) 0.587) - both already the stored record run 8; raised with Michael at the run-9 gate.
GUARD = {"g48_lo": 0.6, "g48_hi": 1.2, "mono_tol": 0.01, "g48_statistic": "median location"}


def guard_table(tab: Mapping[str, Mapping[int, Mapping[str, float]]], mono_tol: float = GUARD["mono_tol"]) -> list[str]:
    """Refusal reasons for a D62 table (empty = passes): per stream, factors must be monotone in k within mono_tol."""
    out = []
    for s, t in tab.items():
        f = np.array([float(t[k]["factor"]) for k in sorted(int(k) for k in t)])
        d = np.diff(f)
        worst = min(float(np.clip(d, 0, None).max(initial=0.0)), float(np.clip(-d, 0, None).max(initial=0.0)))  # the smaller direction's largest step
        if worst > mono_tol:
            out.append(f"{s} D62 factors not monotone in k ({' / '.join(f'{x:.3f}' for x in f)}; reversal {worst:.3f} > {mono_tol})")
    return out


def guard_tail(g_tail: Mapping[str, np.ndarray], lo: float = GUARD["g48_lo"], hi: float = GUARD["g48_hi"]) -> tuple[list[str], dict[str, Any]]:
    """Refusal reasons + the recorded statistic: per stream, the median location's D92 g(48) must lie in [lo, hi]."""
    out, stat = [], {}
    for s, g in g_tail.items():
        g = np.asarray(g, float)
        med = float(np.median(g))
        stat[s] = {"median": med, "min": float(g.min()), "max": float(g.max()),
                   "share_outside": float(((g < lo) | (g > hi)).mean()), "n": len(g)}
        if not lo <= med <= hi:
            out.append(f"{s} D92 g(48) median {med:.3f} outside [{lo}, {hi}]")
    return out, stat


# ----------------------------------------------------------------------------
# Disclosure
# ----------------------------------------------------------------------------


def _ranges(group: str, inputs: Path) -> tuple[dict[str, Any], str]:
    rr = pd.read_csv(inputs / f"spread_by_radius_{group}.csv")
    return ({f"{r.radius_class}|cum-{int(r.horizon)}": {"p90_low": float(r.box_p90_low), "p10_high": float(r.box_p10_high), "packages": int(r.packages),
                                                      "bias": float(r.box_bias)} for r in rr.itertuples()},
            f"box_v2 oil package errors, step-15 TUNING packages pooled across cutoffs ({inputs / f'spread_by_radius_{group}.csv'})")


def _weighted(cells: pd.DataFrame, variant: str, s: str, k: int) -> tuple[float | None, int]:
    x = cells[(cells["variant"] == variant) & (cells["stream"] == s) & (cells["horizon"] == k) & (cells["n_packages"] > 0)
              & np.isfinite(cells["pkg_bias"].astype(float))]
    w = x["n_packages"].to_numpy(float)
    return (float(np.sum(w * x["pkg_bias"].to_numpy(float)) / w.sum()) if w.sum() else None), int(w.sum())


def validated15_disclosure(group: str, tuning: Path = STEP15_TUNING, holdout: Path = STEP15_HOLDOUT, inputs: Path = RUN9_INPUTS) -> dict[str, Any]:
    """WCB_1 / WCC (raw box_v2, holdout PASS): the box.production9c.bench_disclosure shape, so existing readers parse it."""
    cells = pd.read_csv(tuning / f"cells_{group}.csv")
    po = pd.read_csv(holdout / f"pooled_{group}.csv").set_index(["stream", "horizon"])
    rec = str(ac.BENCH_SPECS[group].get("record", ac.RECORD_V2))
    bias: dict[str, Any] = {}
    for s in pr.STREAMS:
        bias[s] = {}
        for k in pr.HORIZONS:
            raw_b, raw_n = _weighted(cells, "box_v2", s, k)
            judged = (s, k) in po.index
            bias[s][str(k)] = {"record_variant": rec, "box_v2_pooled_bias": raw_b, "box_v2_pooled_packages": raw_n, "haircut_factor": 1.0,
                               "disclosed_bias": float(po.loc[(s, k), "tuning_bias"]) if judged else raw_b,
                               "disclosed_packages": int(po.loc[(s, k), "packages"]) if judged else raw_n, "d99_judged": judged,
                               "holdout_bias": float(po.loc[(s, k), "holdout_bias"]) if judged else None,
                               "holdout_packages": None,  # pooled_<b>.csv carries the tuning package count only
                               "d99_interval": [float(po.loc[(s, k), "interval_lo"]), float(po.loc[(s, k), "interval_hi"])] if judged else None}
    ranges, basis = _ranges(group, inputs)
    return {"tier": "validated", "hindcast_bias": bias, "radius_ranges": ranges, "radius_ranges_basis": basis,
            "error_convention": "actual / forecast - 1 (negative = forecast HIGH)",
            "source": f"{tuning / f'cells_{group}.csv'}, {holdout / f'pooled_{group}.csv'} (holdout scored once 2026-10-18, PASS)"}


def _prov_sources(group: str, tuning_prov: Path = STEP15_PROV, holdout: Path = STEP15_HOLDOUT) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """(disclosure rows, by-vintage rows, the disclosure 'bench' labels that apply to this group, lead first)."""
    if group in D105_BENCHES:
        d, v = pd.read_csv(tuning_prov / "disclosure.csv"), pd.read_csv(tuning_prov / "by_vintage.csv")
        d["scope"], v["scope"] = "tuning", "tuning"
        labels = ["AVA (0+1+2 pooled)", group] if group.startswith("AVA") else [group]
        return d, v, labels
    d, v = pd.read_csv(holdout / "provisional" / "disclosure.csv"), pd.read_csv(holdout / "provisional" / "by_vintage.csv")
    return d, v, [group]


# D105 gate (Michael 2026-10-17, ask 2 accepted): the latest-vintage line of record for the D105 benches, verbatim
D105_LATEST = {"AVA": "recent cohorts (2022-24) produced 14-18 % below forecast at 12 months",
               "BS2_C": "the miss changed sign; the 2023-24 cohorts came in ~12 % above forecast"}


def latest_vintage(v: pd.DataFrame, label: str, scope: str) -> dict[str, Any]:
    """Oil and gas cum-12 bias of the latest cutoff's cohort (the next-12-months wells after Dec 1 2024) for one label / scope."""
    x = v[(v["bench"] == label) & (v["scope"] == scope) & (v["horizon"] == 12)]
    cut = str(x["cutoff"].max())
    out: dict[str, Any] = {"cutoff": cut, "scope": scope, "label": label}
    for s in pr.STREAMS:
        r = x[(x["stream"] == s) & (x["cutoff"].astype(str) == cut)]
        out[s] = {"bias": float(r["bias"].iloc[0]), "packages": int(r["n_packages"].iloc[0])} if len(r) else None
    o = out["oil"]
    out["text"] = (f"latest vintage ({cut[:4]} cutoff cohort, {o['packages']} packages, {scope}): oil produced {abs(o['bias']):.1%} "
                   f"{'below' if o['bias'] < 0 else 'above'} forecast at 12 months") if o else "latest vintage: no cum-12 packages"
    return out


def _pick(L: pd.DataFrame, lab: str, sc: str, s: str, k: int) -> tuple[float | None, int | None]:
    m = L[(L["label"] == lab) & (L["scope"] == sc) & (L["stream"] == s) & (L["horizon"] == k)] if len(L) else L
    return (float(m["bias"].iloc[0]), int(m["packages"].iloc[0])) if len(m) else (None, None)


def provisional_disclosure(group: str, tuning_prov: Path = STEP15_PROV, holdout: Path = STEP15_HOLDOUT, inputs: Path = RUN9_INPUTS) -> dict[str, Any]:
    """D105 tier. `lines` = every (label, scope) measurement per stream x horizon; `hindcast_bias` keeps the 9c reader shape with the
    LEAD number as disclosed_bias (AVA: the pooled AVA 0+1+2; holdout fails: tuning + holdout, with the holdout beside it)."""
    d, v, labels = _prov_sources(group, tuning_prov, holdout)
    fail = group in HOLDOUT_FAIL
    lead_label, lead_scope = labels[0], ("tuning + holdout" if fail else "tuning")
    lines = []
    for lab in labels:
        for r in d[d["bench"] == lab].itertuples():
            lines.append({"label": lab, "scope": r.scope, "stream": r.stream, "horizon": int(r.horizon), "packages": int(r.n_packages),
                          "bias": float(r.bias), "range_95": [float(r.range_lo), float(r.range_hi)], "cutoffs": int(r.cutoffs)})
    L = pd.DataFrame(lines)
    ivl = pd.read_csv(holdout / f"pooled_{group}.csv").set_index(["stream", "horizon"]) if fail else None
    bias: dict[str, Any] = {}
    for s in pr.STREAMS:
        bias[s] = {}
        for k in pr.HORIZONS:
            lead_b, lead_n = _pick(L, lead_label, lead_scope, s, k)
            tun_b, tun_n = _pick(L, group, "tuning", s, k)
            hol_b, hol_n = _pick(L, group, "holdout", s, k) if fail else (None, None)
            judged = fail and (s, k) in ivl.index
            bias[s][str(k)] = {"record_variant": "box_v2", "box_v2_pooled_bias": tun_b, "box_v2_pooled_packages": tun_n, "haircut_factor": 1.0,
                               "disclosed_bias": lead_b, "disclosed_packages": lead_n, "disclosed_basis": f"{lead_label}, {lead_scope}",
                               "d99_judged": judged, "holdout_bias": hol_b, "holdout_packages": hol_n,
                               "d99_interval": [float(ivl.loc[(s, k), "interval_lo"]), float(ivl.loc[(s, k), "interval_hi"])] if judged else None}
    latest = [latest_vintage(v, lab, lead_scope) for lab in labels]
    accepted = D105_LATEST.get("AVA" if group.startswith("AVA") else group)
    ranges, basis = _ranges(group, inputs)
    return {"tier": "provisional", "holdout": "FAIL (scored once 2026-10-18, D99)" if fail else "none (D105: never out-of-time validated)",
            "hindcast_bias": bias, "lines": lines, "lead": {"label": lead_label, "scope": lead_scope}, "latest_vintage": latest,
            "latest_vintage_text": accepted or latest[0]["text"], "radius_ranges": ranges, "radius_ranges_basis": basis,
            "label": ("measured in-sample, never out-of-time validated" if not fail else
                      "holdout FAILED its one-time D99 test: show the pooled line WITH the holdout line, never the pooled figure alone"),
            "error_convention": "actual / forecast - 1 (negative = forecast HIGH)",
            "source": (f"{tuning_prov}/disclosure.csv + by_vintage.csv" if not fail else f"{holdout}/provisional/disclosure.csv + by_vintage.csv, {holdout}/pooled_{group}.csv")}


def disclosure_for(group: str) -> dict[str, Any]:
    if group in VALIDATED_15:
        return validated15_disclosure(group)
    if is_provisional(group):
        return provisional_disclosure(group)
    raise ValueError(f"{group}: WCA / BS2_S / WCXY_WCA1 keep the 9c disclosure")


# ----------------------------------------------------------------------------
# Workup flags (pud_forecast.flags)
# ----------------------------------------------------------------------------

# Tuning gate 2026-10-17 (FINDINGS §8): which step-15 benches carry which edge caveats; numbers come from the record-variant edge
# table (inputs/edge_regions_<b>.csv, raw box_v2 on tuning packages) so the text matches the forecast the row carries.
EDGE_CAVEAT_SIDES = {"BS3_S": ("S", "W"), "WCB_2": ("S",), "BS1_S": ("N", "E", "S"), "WCC": ("N", "E", "S", "W")}


def edge_text(group: str, side: str, inputs: Path = RUN9_INPUTS) -> str | None:
    if side not in EDGE_CAVEAT_SIDES.get(group, ()):
        return None
    t = pd.read_csv(inputs / f"edge_regions_{group}.csv").set_index("region")
    reg = f"{side} edge"
    if reg not in t.index:
        return None
    r = t.loc[reg]
    return (f"{group} {side}-edge caveat (<= 5 mi of the extent boundary; tuning gate 2026-10-17): box_v2 oil cum-12 {r['oil12 bias']:+.0%} "
            f"({int(r['oil12 packages'])} tuning packages; local-offsets benchmark {r['oil12 bench bias']:+.0%}); forecast NOT adjusted")


def tier_flag(group: str, disc: Mapping[str, Any]) -> str:
    if group in D105_BENCHES:
        o = disc["hindcast_bias"]["oil"]["12"]
        return (f"D105 PROVISIONAL {group}: raw box_v2, no haircut, never out-of-time validated; measured in-sample oil cum-12 "
                f"{o['disclosed_bias']:+.1%} ({o['disclosed_basis']}); {disc['latest_vintage_text']}")
    o = disc["hindcast_bias"]["oil"]["12"]
    g = disc["hindcast_bias"]["gas"]["12"]
    return (f"D105 PROVISIONAL {group} (holdout FAIL 2026-10-18): raw box_v2, no haircut; cum-12 bias tuning + holdout oil "
            f"{o['disclosed_bias']:+.1%} / gas {g['disclosed_bias']:+.1%}, HOLDOUT oil {o['holdout_bias']:+.1%} / gas {g['holdout_bias']:+.1%}; "
            f"{disc['latest_vintage_text']}")


CALLOUTS = {
    "WCB_1": "WCB_1 (validated, holdout PASS 6/6): raw box_v2; disclosed tuning bias oil cum-36 -13 % (forecast HIGH); gas runs LOW (+11 / +19 / +35 %)",
    "WCC": ("WCC (validated, weak evidence: holdout PASS 4/4 at rule power 54 %): raw box_v2; gas ~-11 % on the holdout (HIGH, just past "
            "+/-10 %); small extent, pooled bias is edge-weighted"),
}


def group_flags(group: str, disc: Mapping[str, Any], side: str | None) -> list[str]:
    out = []
    if is_provisional(group):
        out.append(tier_flag(group, disc))
    if group in CALLOUTS:
        out.append(CALLOUTS[group])
    if side:
        t = edge_text(group, side)
        if t:
            out.append(t)
    return out
