"""PDP-proximity -> BOX record run 11: the rows to store (pure, no DB). Plan: docs/box/prox-2026-10-19/RECORD_PLAN.md.

Inputs of record (digest-stamped, never recomputed silently):
  * docs/box/prox-2026-10-19/pud_outcomes.csv.gz   the gate-4 measurement Michael reviewed (outcome, factor, keys, precedent)
  * runs/prox/pud_links.pkl                        the PUD pair table it came from (named parents; configuration re-derived
                                                   here and asserted equal to the outcomes file, field by field)
  * docs/box/prox-2026-10-19/haircut_table_candidate.csv   the factor table (its sha256 goes into table_ref)
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import prox_dose as pdz
from box import prox_study as ps

PREREG_COMMIT = "b20603d"
NO_FORECAST = ("no_forecast_precedent", "no_forecast_package")
LABEL = "validated_with_exception"
PROX_COLS = ["location_id", "coverage", "config_class", "n_same", "n_topfill", "n_underfill", "n_parents_total", "flanked_same", "flanked_topfill",
             "flanked_underfill", "outcome", "factor", "haircut_key", "pair_key", "prec_multi", "prec_package", "label", "n_permit_parents",
             "n_recent_producers", "table_ref"]
PARENT_COLS = ["location_id", "api10", "cls", "parent_bench", "dv_ft", "dh_ft", "dxy_ft", "overlap", "age_days", "permit"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def counted_parents(L: pd.DataFrame) -> pd.DataFrame:
    """The links that count as parents for the configuration: >= 12 months, >= 30 % alongside, inside the class envelope
    (permit-round TVDs included — D115)."""
    q = L[(L["rel"] == "parent") & (L["overlap"] >= ps.MIN_OVERLAP)]
    hit = np.zeros(len(q), bool)
    for c, (vmax, hmax) in pdz.ENVELOPE.items():
        hit |= ((q["cls"] == c) & (q["dv_ft"] <= vmax) & (q["dh_ft"] <= hmax)).to_numpy()
    return q[hit]


def prepare(outcomes: pd.DataFrame, links: pd.DataFrame, table_ref: str) -> dict[str, Any]:
    """(proximity rows, parent rows, expected counts). Asserts the re-derived configuration equals the reviewed outcomes."""
    o = outcomes.copy()
    o["api10"] = o["location_id"].astype(str)
    cfg = pdz.configuration(list(o["api10"]), links.assign(permit=False)).set_index("api10")
    oo = o.set_index("api10")
    mism = {}
    for c in ("n_same", "n_topfill", "n_underfill", "n_parents_total"):
        bad = int((cfg[c].reindex(oo.index).astype(int) != oo[c].astype(int)).sum())
        if bad:
            mism[c] = bad
    a, b = cfg["config_class"].reindex(oo.index), oo["config_class"]
    bad = int((~((a.isna() & b.isna()) | (a == b))).sum())
    if bad:
        mism["config_class"] = bad
    bad = int((cfg["flanked_topfill"].reindex(oo.index).fillna(False).astype(bool) != oo["flanked_topfill"].fillna(False).astype(bool)).sum())
    if bad:
        mism["flanked_topfill"] = bad
    if mism:
        raise RuntimeError(f"configuration re-derived from pud_links differs from the reviewed outcomes: {mism}")
    p = o.copy()
    for c in ("flanked_same", "flanked_underfill"):
        p[c] = p["api10"].map(cfg[c]).fillna(False).astype(bool)
    p["flanked_topfill"] = p["flanked_topfill"].fillna(False).astype(bool)
    p["coverage"] = np.where(p["outcome"].isin(NO_FORECAST), "not_covered_no_precedent", p["coverage"])
    p["label"] = np.where(p["outcome"] == "haircut", LABEL, None)
    p["table_ref"] = table_ref
    for c in ("haircut_key", "pair_key"):
        p[c] = p[c].where(p[c].notna(), None)
    for c in ("prec_multi", "prec_package"):
        p[c] = p[c].astype("Int64")
    p["config_class"] = p["config_class"].where(p["config_class"].notna(), None)
    par = counted_parents(links)
    par = par[par["child"].isin(set(o["api10"]))]
    parents = pd.DataFrame({"location_id": par["child"].astype("int64").to_numpy(), "api10": par["parent"].to_numpy(), "cls": par["cls"].to_numpy(),
                            "parent_bench": par["parent_bench"].to_numpy(), "dv_ft": par["dv_ft"].to_numpy(), "dh_ft": par["dh_ft"].to_numpy(),
                            "dxy_ft": par["dxy_ft"].to_numpy(), "overlap": par["overlap"].to_numpy(), "age_days": par["age_days"].astype(int).to_numpy(),
                            "permit": par["permit"].astype(bool).to_numpy()})
    # every counted parent belongs to a PUD whose configuration counted it
    n_by = parents.groupby("location_id").size()
    tot = p.set_index("location_id")["n_parents_total"]
    if not (n_by.reindex(tot.index).fillna(0).astype(int) == tot.astype(int)).all():
        raise RuntimeError("named parents per PUD != n_parents_total")
    exp = {"n_puds": len(p), "outcomes": p["outcome"].value_counts().to_dict(), "n_parents": len(parents),
           "moved_to_no_precedent": o[o["outcome"].isin(NO_FORECAST)].groupby("coverage").size().to_dict()}
    return {"prox": p[PROX_COLS], "parents": parents[PARENT_COLS], "expected": exp}


def disclosure(exp: dict[str, Any], table_ref: str, oil_before_mmbbl: float, oil_after_mmbbl: float) -> dict[str, Any]:
    return {
        "decisions": "D112-D116 (docs/box_type_curves_plan.md); study docs/box/prox-2026-10-19 (FINDINGS, PREREG_2c, RECORD_PLAN)",
        "method": ("parents = producing horizontals >= 12 mo at data_through, >= 30 % alongside the PUD stick, in the class envelope (same 1,400 hz; "
                   "topfill 800 vt / 1,400 hz; underfill 500 vt / 1,400 hz), no shielding exemption, permit TVDs counted + flagged. Multi-parent "
                   "configurations: oil x the cum-24 configuration factor (BOX's calibrated level); single-parent / unexposed: as-is; gas / water "
                   "untouched. Precedent: >= 30 drilled multi-parent wells of the bench pair; >= 30 drilled packages when factor <= 0.80; else "
                   "not_covered_no_precedent (search provenance kept)."),
        "validation": {"prereg_commit": PREREG_COMMIT, "verdict_as_written": "FAIL (P1 1.060 [1.023-1.097] on material haircuts; P2 / P3 pass)",
                       "accepted_as": "option (a), validated_with_exception: multi-parent material cells 1.043 [1.003-1.088] at cum-24, "
                                      "1.005 [0.95-1.05] at cum-36 (post-look split)",
                       "confirmation": "2026 prospective cohort, first cum-12 read ~2027-Q2"},
        "survivorship": "factors are measured on operator-selected infills: an upper bound for undrilled PUDs in the same configuration",
        "table_ref": table_ref,
        "counts": exp["outcomes"],
        "oil_eur_mmbbl": {"before": round(oil_before_mmbbl, 3), "after": round(oil_after_mmbbl, 3)},
    }
