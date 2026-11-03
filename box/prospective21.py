"""BOX step 21d — the 2026 Midland prospective test of the method step 23 ships, all nine MID_ groups, pre-registered BEFORE
any 2026 Midland outcome is looked at (the 13d / D125 pattern; plan §5 step 21d, D151 (5)). Every Midland D52 holdout is spent
(21c, D151), so this is the only route on which a Midland group changes tier (D124), either way.

The definition below is the record. `DIGEST` pins it: tests/test_box_prospective21.py recomputes the SHA-256 of the canonical
definition and fails on any edit. Gate 21d chooses the graduation rule (`verdict.graduation`) and freezes this digest + the
commit SHA. Rationale, the evidence it was written from and the gate questions: docs/box/step21d-2026-11-03/PREREGISTRATION.md
and FINDINGS.md.

What is scored, in one paragraph: the next rolling-origin fold of the step-21 harness at cutoff 2025-12-01 (revision 8 at its
frozen SHA, the D149 record treatments as amended by the D151 tiers), with D150's continuous proximity factor in place of the
step-21 class table (Midland R3 per-side product, fitted level 1.0674, single-parent wells get F; oil only), on the Midland wells
first producing in 2026 inside each group's stored record extent. Group membership is read at SCORING time; the freeze-time tags
are a sensitivity. Each group's cells are judged once per horizon on a fixed date against intervals drawn from its own step-21b
TUNING packages under the same treatment. A uniform per-horizon haircut (WCA_1's D102 oil factor) scales the cohort bias and
both interval ends by the same map, so the consistency verdict does not depend on whether gate 23 recomputes that haircut.

Pure: no DB except `cohort()` (identities only; never a volume column). The read-only builder is scripts/box_prospective21.py.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

DOCS = Path("docs") / "box" / "step21d-2026-11-03"
TUNING_RUNS = Path("runs") / "step21b"   # gitignored; pinned by tuning_views.sha256 (the 21b tuning views, 5ceadc2)
LINKS_CACHE = Path("runs") / "step21a" / "links.pkl"   # gitignored; the drilled-child links D150's factor is measured on (pinned)
PROX_CHILDREN = Path("docs") / "box" / "step21b-2026-11-01" / "prox_children.csv.gz"   # committed; the 24a Midland frame

# group -> (bench, stored record extent id, tier after gate 21c (D151)). Order and extents = box/step21.GROUPS.
GROUPS: dict[str, tuple[str, int, str]] = {
    "MID_WCA_1": ("WCA_1", 36, "validated"),
    "MID_WCB_1": ("WCB_1", 37, "provisional"),
    "MID_WCB_2": ("WCB_2", 38, "provisional"),
    "MID_WCC": ("WCC", 39, "provisional"),
    "MID_WCD": ("WCD", 42, "validated"),
    "MID_MS": ("MS", 44, "provisional"),
    "MID_JM": ("JM", 45, "provisional"),
    "MID_LSSH": ("LSSH", 47, "validated"),
    "MID_DEAN": ("DEAN", 49, "provisional"),
}

# D150 / GATE_24A.json: the Midland curve of record (R3 per-side product; factor = level x F_R3; unexposed wells carry the level).
D150_MIDLAND = {"rule": "R3", "f_min": 0.7195304198267564, "d50_ft": 485.108159824318, "k": 1.9552065903775868,
                "a_below": 0.5, "a_above": 0.5, "level": 1.0673947845823253}
# D151 / GATE_21C.json: the step-23 haircut of record as computed at gate 21c (WCA_1 oil only). Gate 23 may recompute it on the
# D150 treatment; the test uses the factor AS DELIVERED by the Midland record run (the D85 pattern).
D102_WCA_1_OIL_AT_21C = {12: 0.979164, 24: 0.974905, 36: 0.954451, 48: 0.949671}

CUTOFF = dt.date(2025, 12, 1)
FP_FROM, FP_TO = dt.date(2026, 1, 1), dt.date(2026, 12, 31)
MIN_PACKAGES = 30
HORIZONS_JUDGED = (12, 24)
GRADUATION_OPTIONS = ("consistency", "consistency_or_accuracy")
GRADUATION = "consistency_or_accuracy"   # CHOSEN at gate 21d (Michael 2026-11-03, "Rule (b), accept recs"; D152)

DEFINITION: dict[str, Any] = {
    "name": "box_prospective_2026_midland",
    "written_on": "2026-11-03",
    "status": "FROZEN at gate 21d (D152)",
    "gate_21d": {"decided_on": "2026-11-03", "by": "Michael (\"Rule (b), accept recs\")", "decision": "D152",
                 "Q1": "graduation = consistency OR accuracy; accuracy spread bar = D58 benchmark + 0.05",
                 "Q2": "the consistency interval carries the tuning mean's own sampling error ([draw - complement] + all)",
                 "Q3": "water reported only, never a tier", "Q4": "drilled-side configuration; stick side reported",
                 "Q5": "every cohort well scored, precedent ignored; the no-forecast subset counted and reported",
                 "Q6": "tuning views + links cache copied to Engineering - General/box-step21d-tuning-views-2026-11-03"},
    "decisions": ["D52", "D53", "D58", "D63", "D85", "D99", "D102", "D105", "D106", "D107", "D109", "D124", "D125", "D128", "D130",
                  "D132", "D136", "D145", "D146", "D147", "D148", "D149", "D150", "D151", "D152"],
    "basin": "midland",
    "cutoff": CUTOFF.isoformat(),
    "cohort": {
        "first_production_from": FP_FROM.isoformat(), "first_production_to": FP_TO.isoformat(),
        "lateral_ft_gt": 0, "horizontal": True,
        "midpoint_inside": "the group's stored record extent (extent_id below; box.extent, basin midland)",
        "groups": {g: {"bench": b, "extent_id": e, "tier_at_freeze": t} for g, (b, e, t) in GROUPS.items()},
        "exclusions": "docs/box/exclusions.csv as it stands at scoring (the harness's load-time filter, box/exclusions.py)",
    },
    "membership": {
        "governing": "scoring_time",
        "record": ("the BOX membership of record at scoring: curated.formation_blueox then (its 13e tag-release id stamped on the "
                   "score), with the Midland BOX-only rules of record applied to every 2026 well — D136 (c) (a WCB_2-tagged well "
                   "north of the D136 line landing < 392 ft below the local WCA_1 band counts as WCB_1) and, once the Midland "
                   "joins step 13, the step-13b pool-refresh class rule (box/pool_refresh) as it then stands"),
        "applies_to": ["which group a 2026 well tests", "the analog pools the hindcast forecasts it from"],
        "sensitivity": "freeze-time tags (cohort_at_freeze.csv; pools as frozen at pool-midland-2026-10-31), reported, never the verdict",
        "merge_or_split": "re-defined by an amendment committed before any score is read; never after",
    },
    "method": {
        "what": "the method step 23 ships for the Midland",
        "base": {"definition": "box/step21.DEFINITION revision 8", "digest": "9780f326ef8a3aa037388270fd848e76f04ba6b0da47468d8fe4145b1dbefd77",
                 "frozen_sha": "5ceadc260b0e1ad78df2bfab39aaa79c812f8219",
                 "parts": "selection box_v2s_r2, Midland rules (translate_range 5,000 ft to inf), Cui & Cross Midland panel with the "
                          "Delaware panel for targets longer than their cohort (D148), measured spacing (D119), uptime-free (D63), "
                          "Df 0.06 (D132), the D57 short-history transfer, per-variant F(k)"},
        "fold": "the next rolling-origin fold of the step-21 harness: analogs, fits and F(k) from data before 2025-12-01",
        "proximity": {"decision": "D150 (replaces the step-21 class table at step 23)", "module": "box/prox_cont.py",
                      "digest": "2e8bb5a74ac5a42ba5a23567c8909901558d5a4aab75b0333154c5a360d55c83",
                      "frozen_sha": "77d50a7f69b807f0c710c148f071fd9e4c44ee4d", "curve": D150_MIDLAND,
                      "form": "oil x level x F_R3(parents); a well with no counting parent carries the level; gas and water untouched",
                      "configuration": ("drilled side, as D150 was fitted and validated and as 21b / 21c scored: a parent is a "
                                        "horizontal >= 365 d on production at the well's first production, >= 30 % alongside, "
                                        "dv <= 1,000 ft and dh <= 2,640 ft, permit TVDs dropped, no shielding exemption "
                                        "(box/prox_cont.parents, drilled=True); the stick-side configuration at the cutoff is "
                                        "reported (FINDINGS §6 Q4)"),
                      "precedent": ("every cohort well is scored, precedent ignored, as 21b / 21c and D150's validation; the wells "
                                    "the shipped gates would leave without a forecast (21a pattern precedent, the 400-ft same-bench "
                                    "floor, D114's package tier) are counted and their bias reported, never the verdict "
                                    "(FINDINGS §6 Q5)")},
        "haircut": {"MID_WCA_1": {"stream": "oil", "factor": "the D102 table AS DELIVERED by the Midland record run (D85 pattern)",
                                  "at_gate_21c": {str(k): v for k, v in D102_WCA_1_OIL_AT_21C.items()},
                                  "open_at_gate_23": "recomputed on the D150 treatment or kept (D151 open item)"},
                    "others": "none (D151: WCB_1 / WCB_2 / JM / MS / DEAN / WCC provisional raw; LSSH / WCD record mid_r2p)"},
        "streams_shipped": {"oil": "mid_r2 x D150 factor (x WCA_1 haircut)", "gas": "mid_r2 (D150 is oil only)",
                            "water": "D107 ratio on raw mid_r2 oil (D108)"},
        "record_run_check": ("before any read, the scorer checks the Midland record run's stored spec against this block (base "
                             "digest, D150 digest and curve, haircut table); a mismatch is an amendment committed before the "
                             "read, never after"),
        "constants_disclosed": ("the D150 curve and the D102 haircut were fitted on 2019-2024 tuning children with production "
                                "through 2026-08-01, after the cutoff; no 2026-first-producing well entered either"),
    },
    "grain": {"package_codev_days": 180, "package_overlap": 0.30, "min_packages": MIN_PACKAGES,
              "error": "sum actual / sum forecast - 1 (negative = forecast HIGH)", "bias": "mean over packages (D53)"},
    "verdict": {
        "cells": "oil AND gas x cum-12 and cum-24; a cell is judged when the full cohort holds >= 30 packages there",
        "consistency": {
            "rule": "D99: the cohort's package bias lies inside the cell's interval",
            "interval": ("P2.5-P97.5 of [bias(draw) - bias(complement)] + bias(all), over 2,000 random draws of 3-mi blocks "
                         "(D52 shape) of the group's 21b TUNING packages, block share = cohort packages / tuning packages, seed "
                         "20261103 — the D125 subset draw plus the tuning mean's own sampling error (FINDINGS §6 Q2)"),
            "reference": "21b tuning packages pooled over cutoffs 2019-2024 (tuning_views.sha256), under the treatment above",
            "draws": 2000, "seed": 20261103, "quantiles": [2.5, 97.5],
        },
        "accuracy": {"rule": "every judged cell: |package bias| <= 10 % (D53) AND scale-free spread <= the local-offsets "
                             "benchmark's + 0.05 (D58)", "min_packages": MIN_PACKAGES},
        "graduation_options": {"consistency": "provisional -> proposed for validated when every judged cell passes consistency "
                                              "(D125 as written)",
                               "consistency_or_accuracy": ("provisional -> proposed for validated when every judged cell passes "
                                                           "consistency, OR every judged cell passes accuracy; a group that "
                                                           "graduates on accuracy alone ships raw (no haircut) with the cohort "
                                                           "line as its disclosure until its own gate decides")},
        "graduation": GRADUATION,
        "keep_validated": "consistency only (D99): any judged cell outside -> validated becomes provisional (D105)",
        "group": {"PASS": "the graduation / keep rule holds on every judged cell, and at least one oil cell is judged",
                  "FAIL": "otherwise, with at least one oil cell judged",
                  "NOT_JUDGED": "no oil cell reaches 30 packages: tier unchanged"},
        "tier": {"provisional_PASS": "proposed for validated at its own gate (Michael)",
                 "validated_FAIL": "provisional (D105); diagnose, never re-tune",
                 "NOT_JUDGED": "tier unchanged"},
        "streams_judged": ["oil", "gas"],
        "water": "reported only (FINDINGS §6 Q3): the D109 measured-water read on the cohort, never a tier",
        "reported_not_gating": ["consistency and accuracy results for every judged cell under BOTH rules",
                                "the D125 subset-draw interval (no tuning-mean error) beside the one of record",
                                "the no-forecast subset (precedent / 400-ft floor / package tier), counted, bias shown",
                                "the stick-side configuration at the cutoff as a proximity sensitivity",
                                "freeze-time-tag sensitivity", "thin-control wells (< 3 local wells within 3 mi)",
                                "> 15,000-ft laterals and the D120 mismatch classes (D149 (6))",
                                "production-sharing vs non-sharing wells", "cum-6 early reads"],
    },
    "schedule": {"early_reads": ("cum-6 on wells with >= 7 reported months, and cum-12 on wells first producing Jan-Jun 2026 at "
                                 "production through 2027-08-01: REPORTED, never judged"),
                 "cum12_judged_once": "the first build whose production runs through >= 2028-01-01 (every 2026 well has 13 months)",
                 "cum24_judged_once": "the first build whose production runs through >= 2029-01-01",
                 "order": "each horizon's verdict takes effect at its own judgment; a cum-24 FAIL after a cum-12 PASS demotes"},
    "watch": ["DEAN holdout under-forecast (21c: oil +22 / +23 %, gas +29 %; gas BOX-specific)",
              "WCB_2 tuning-vs-holdout contrast (tuning -6 / -9 %, holdout +5 / +2 % oil)",
              "WCB_1 / JM / MS gas cum-12 below tuning at 21c",
              "MS ships ~6-9 % high on oil, raw (D151)", "the D150 Midland level drifting by fold (C8 1.000 -> 0.960)"],
}

DIGEST = "187811fd8f86b4cdb9b0e32909711013bb6f9dc99344d30df94a876419727ad7"  # FROZEN at gate 21d 2026-11-03 (D152: graduation consistency OR accuracy, A2 interval); draft 2dae765e


def canonical() -> str:
    return json.dumps(DEFINITION, sort_keys=True, separators=(",", ":"))


def digest() -> str:
    return hashlib.sha256(canonical().encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Text files hash with CRLF normalised to LF (checkout-independent); gzip / pickle / binary files hash raw."""
    b = path.read_bytes()
    return hashlib.sha256(b if path.suffix in (".gz", ".pkl", ".npz") else b.replace(b"\r\n", b"\n")).hexdigest()


# Identities only. NEVER add a volume column (curated.wells carries cum_12m_* / cum_24m_* / eur_* / peak_*): step 21d must not read
# a 2026 Midland outcome. tests/test_box_prospective21.py fails if any such column name appears in this query.
_COHORT_SQL = """
SELECT w.api10, COALESCE(fb.formation_blueox, '(unmapped)') AS formation_blueox, w.first_production_date, w.state_code,
       w.current_operator, w.lateral_length_ft, w.tvd_ft, w.has_production_sharing,
       extensions.ST_X(extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5)) AS mid_lon,
       extensions.ST_Y(extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5)) AS mid_lat
FROM curated.wells w
JOIN curated.formation_blueox fb ON fb.api10 = w.api10
JOIN box.extent e ON e.extent_id = %(extent)s AND e.basin = 'midland'
WHERE fb.basin_blueox = 'midland' AND fb.formation_blueox = ANY (%(forms)s)
  AND COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%%horizontal%%'
  AND w.first_production_date BETWEEN %(fp0)s AND %(fp1)s
  AND COALESCE(w.lateral_length_ft, 0) > %(lat)s AND w.wellstick_geom IS NOT NULL
  AND extensions.ST_Contains(e.geom, extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5))
ORDER BY w.first_production_date, w.api10
"""
# The only curated.wells columns the cohort query may name (tests pin it): identities, geometry, dates, TVD, lateral.
COHORT_COLUMNS_ALLOWED = ("api10", "first_production_date", "state_code", "current_operator", "lateral_length_ft", "tvd_ft",
                          "has_production_sharing", "wellstick_geom", "novi_slant_calculated", "enverus_trajectory")


def cohort_params(group: str, fp0: dt.date = FP_FROM, fp1: dt.date = FP_TO, forms: list[str] | None = None) -> dict[str, Any]:
    c = DEFINITION["cohort"]
    g = c["groups"][group]
    return {"extent": g["extent_id"], "forms": forms or [g["bench"]], "lat": c["lateral_ft_gt"], "fp0": fp0, "fp1": fp1}


def cohort(conn: Any, group: str, fp0: dt.date = FP_FROM, fp1: dt.date = FP_TO, forms: list[str] | None = None) -> list[tuple[Any, ...]]:
    """The group's wells first producing in [fp0, fp1] inside its record extent, tagged NOW. Identities only — no volumes."""
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_COHORT_SQL, cohort_params(group, fp0, fp1, forms))
        rows = cur.fetchall()
    conn.rollback()
    return rows
