"""BOX step 21a — the Midland tuning + holdout PRE-REGISTRATION (Phase 3, D134: the run-19 method transferred, not re-derived),
written and committed before any Midland BOX forecast is scored. Gate 21a stamps the frozen SHA.

The definition below is the record. `DIGEST` pins it: tests/test_box_step21.py recomputes the SHA-256 of the canonical
definition and fails on any edit. A change after the freeze needs Michael and a later commit that says why (the 16b revision
table pattern). Rationale, the evidence it was written from, and the gate-21a questions:
docs/box/step21a-2026-10-31/PREREGISTRATION.md.

What 21b / 21c score, in one paragraph: nine Midland groups (`MID_<bench>`, D128 / D135: one extent and one pool per bench), the
D53 rolling-origin folds (cutoffs Dec 2019 ... Dec 2024) on the D53 package grain, with the run-19 production method of record
(r2 selection, measured spacing, Cui translation, uptime-free volumes, D132 Df 0.06) and the D129 / D134 C lateral band (no upper
bound: > 15,000-ft producers are analogs, every cohort Cui-translated, extrapolation flagged), the proximity oil factor measured
on Midland producers (D112-D116 pattern), and each group's own walk-forward haircut where its holdout can judge it (D94 / D97);
the D52 holdout scored ONCE per group under D99 consistency; D107 water scored the D109 way from the same folds (D133 / D134 D).

Pure: no DB. The read-only evidence builder is scripts/box_step21a.py.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from box import step16 as s16

DOCS = Path("docs") / "box" / "step21a-2026-10-31"
POOL_DIR = Path("docs") / "box" / "pool-midland-2026-10-31"  # the frozen Midland analog pool (copies of the sets of record)

# group -> (bench, record extent id, the step-20 set of record the pool file is copied from). D135: MID_<bench>, basin midland.
GROUPS: dict[str, tuple[str, int, str]] = {
    "MID_WCA_1": ("WCA_1", 36, "docs/box/step20a-2026-10-26/r3/wells_final_WCA_1.csv"),
    "MID_WCB_1": ("WCB_1", 37, "docs/box/step20a-2026-10-26/r3/wells_final_WCB_1.csv"),
    "MID_WCB_2": ("WCB_2", 38, "docs/box/step20a-2026-10-26/r3/wells_final_WCB_2.csv"),
    "MID_WCC": ("WCC", 39, "docs/box/step20a-2026-10-26/r3/wells_final_WCC.csv"),
    "MID_WCD": ("WCD", 42, "docs/box/step20a-2026-10-26/r3/wells_final_WCD.csv"),
    "MID_MS": ("MS", 44, "docs/box/step20b-2026-10-30/wells_final_MS.csv"),
    "MID_JM": ("JM", 45, "docs/box/step20b-2026-10-30/wells_final_JM.csv"),
    "MID_LSSH": ("LSSH", 47, "docs/box/step20b-2026-10-30/wells_final_LSSH.csv"),
    "MID_DEAN": ("DEAN", 49, "docs/box/step20b-2026-10-30/wells_final_DEAN.csv"),
}
# D143: DEAN sticks are reported by outcome inside the generated body vs the loop's addition. The generated body = 20b's v1 extent.
DEAN_BODY_GEOJSON = "docs/box/step20b-2026-10-30/extents/extent_DEAN_v1.geojson"

# The one Midland selection variant (D129 / D134 C): run 19's r2 rules with the lateral band's upper bound removed.
SELECTION = "box_v2s_r2"  # the selection of record (D121) = box.production16.SELECTION; Midland differs only in translate_range
RULES = dataclasses.replace(s16.VARIANTS[SELECTION][1], translate_range=(5_000.0, math.inf))
# Treatments scored in 21b (names used in every 21b / 21c table). RAW is also the harness variant name: the --step16 path of
# box/acceptance predicts it (and its linear-per-ft twin RAW_lin, the length-class report) for a Midland group.
RAW, PROX, PROX_WF = "mid_r2", "mid_r2p", "mid_r2p_wf"
HARNESS_VARIANTS: dict[str, tuple[str, Any]] = {RAW: (s16.MEASURED, RULES)}
HARNESS_TWINS: tuple[str, ...] = (RAW,)
HARNESS_SCORED: tuple[str, ...] = (RAW, f"{RAW}_lin")

# Length classes REPORTED in 21b, never judged (D134 C): the D120 condition-6 mismatch classes (well lateral / cohort mean lateral)
# and absolute completed-lateral classes (the D129 question: does the extrapolated Cui curve hold past 12,500 / 15,000 ft?).
MISMATCH_CUTS = (0.80, 1.25)
LATERAL_CLASS_FT = (5_000.0, 7_500.0, 10_000.0, 12_500.0, 15_000.0, 17_500.0, 20_000.0)
CUI_PAPER_MAX_FT = 12_500.0  # past this E(L) is the extended last segment (flagged)

MIN_PACKAGES = 30  # D53 / D99 / D102 floor
MIN_PRIOR = 2  # D57 walk-forward: >= 2 earlier judged cutoffs
HORIZONS_JUDGEABLE = (12, 24, 36)  # D99 cells are drawn from these (cum-48 reported where reached, never judged)


def mismatch_class(well_lateral_ft: float, cohort_mean_lateral_ft: float) -> str:
    """D120 condition-6 class of a scored well: shorter / near / longer than its cohort's mean completed lateral."""
    r = float(well_lateral_ft) / float(cohort_mean_lateral_ft)
    return "shorter" if r < MISMATCH_CUTS[0] else ("longer" if r >= MISMATCH_CUTS[1] else "near")


def lateral_class(lateral_ft: float, cuts: Sequence[float] = LATERAL_CLASS_FT) -> str:
    """Absolute completed-lateral class label, e.g. '12500-15000', '<5000', '>=20000'."""
    x = float(lateral_ft)
    if not math.isfinite(x):
        return "(unknown)"
    if x < cuts[0]:
        return f"<{cuts[0]:.0f}"
    for lo, hi in itertools.pairwise(cuts):
        if x < hi:
            return f"{lo:.0f}-{hi:.0f}"
    return f">={cuts[-1]:.0f}"


def d99_horizons(pooled_holdout: Mapping[int, int], floor: int = MIN_PACKAGES) -> tuple[int, ...]:
    """The horizons whose POOLED holdout cell (all scoreable cutoffs) reaches the floor: the group's D99 cells (oil AND gas
    are judged at each)."""
    return tuple(k for k in HORIZONS_JUDGEABLE if int(pooled_holdout.get(k, 0)) >= floor)


def record_treatment(pooled_holdout_wf: Mapping[int, int], floor: int = MIN_PACKAGES) -> str:
    """The pre-registered record treatment of a group (the step-14 / D97 pattern): the walk-forward form PROX_WF only where
    its own holdout can judge it at cum-12 AND cum-24 (pooled holdout packages over the cutoffs that carry a walk-forward
    haircut reach the floor at both); otherwise PROX (no haircut)."""
    return PROX_WF if all(int(pooled_holdout_wf.get(k, 0)) >= floor for k in (12, 24)) else PROX


def tier_route(pooled_holdout: Mapping[int, int], floor: int = MIN_PACKAGES) -> str:
    """'holdout' = the group's one-time D99 holdout can judge at least one oil cell (cum-12 at minimum) -> validated on PASS,
    provisional on FAIL; 'provisional' = no cell can be judged -> D105 provisional by construction (no holdout is scored)."""
    return "holdout" if d99_horizons(pooled_holdout, floor) else "provisional"


DEFINITION: dict[str, Any] = {
    "name": "box_midland_tuning_holdout_r2",
    "written_on": "2026-10-31",
    "decisions": ["D52", "D53", "D57", "D58", "D63", "D92", "D94", "D97", "D99", "D102", "D105", "D106", "D107", "D108", "D109",
                  "D112", "D113", "D114", "D115", "D116", "D119", "D120", "D121", "D122", "D127", "D128", "D129", "D130", "D131",
                  "D132", "D133", "D134", "D135", "D136", "D141", "D142", "D143"],
    "basin": "midland",
    "groups": {g: {"bench": b, "extent_id": e, "pool_file": f"{POOL_DIR.as_posix()}/wells_final_{b}.csv", "pool_source": s}
               for g, (b, e, s) in GROUPS.items()},
    "out_of_scope": {"US": "D127 emerging (bench_scope in_scope false); not covered, never zero",
                     "BRNT/MISS/MRMC/WDFD": "D2 emerging"},
    "pools": {"rule": "the step-20 sets of record (20a r3 + ask-3 verdicts; 20b post-verdict), members only, exclusions.csv "
                      "applied by the harness; frozen as copies in pool_dir with a sha256 manifest",
              "pool_dir": POOL_DIR.as_posix(), "manifest": f"{POOL_DIR.as_posix()}/MANIFEST.json",
              "membership": "box_bench (BOX-only reassignments: D136 WCB line, card verdicts, owner benches); no pooling (D128)"},
    "folds": {"cutoffs": ["2019-12-01", "2020-12-01", "2021-12-01", "2022-12-01", "2023-12-01", "2024-12-01"],
              "scored": "next 12 months' pool wells first producing after each cutoff, midpoint inside the group's record extent, "
                        "lateral > 0 (box.acceptance.run, fold 'analog')",
              "horizons": [12, 24, 36, 48], "judged_horizons_max": 36,
              "actuals_through": "2026-08-01", "actuals_note": "curated.production through the live last full month at 21a; "
                                                               "each well's newest month dropped (acceptance as built)"},
    "grain": {"package_codev_days": 180, "package_overlap": 0.30, "min_packages": MIN_PACKAGES,
              "error": "sum actual / sum forecast - 1 (negative = forecast HIGH)"},
    "holdout": {"rule": "D52 as frozen: 3-mi blocks (UTM 13N ft), salt 'box-holdout-2026-10-13', share 0.20; a package is held "
                        "out when any member midpoint sits in a holdout block; held-out packages are dropped before any "
                        "statistic and only counted until 21c",
                "salt": "box-holdout-2026-10-13", "block_ft": 15840.0, "share": 0.20},
    "method": {
        "selection": SELECTION,
        "rules": "Rules(relax=('count', 'spacing'), count_floor=5, wide_tol=0.4, lateral='translate', "
                 "translate_range=(5000.0, inf), level_only=False, level_only_post_peak=3.0)",
        "lateral": "translate: analogs completed lateral >= 5,000 ft, NO upper bound (D129 / D134 C); every cohort Cui & Cross "
                   "2,000 lb / 60 bbl per ft (box/lateral.py), the last segment extended past 12,500 ft (flagged); ONE variant",
        "spacing": "measured, every pool well (D119)", "volumes": "uptime_free (D63)", "df_terminal": 0.06,
        "short_history": "the D57 transfer as in r2 (level_only off)", "calendar_factor": "per-variant F(k), seeded sample (as built)",
    },
    "treatments": {
        RAW: "box_v2s_r2 under the Midland rules, raw",
        PROX: "mid_r2 x the Midland proximity oil factor (option (a): multi-parent configurations only; precedent ignored so "
              "every multi-parent scored well carries its factor, the step-16 level pattern)",
        PROX_WF: "mid_r2p x the group's OWN walk-forward haircut (D57 / D94: mean package bias at the same horizon over >= 2 "
                 "earlier judged tuning cutoffs, per stream)",
    },
    "proximity": {
        "pair_metric": "D112 child-relative (box/prox_study): overlap share of the child, median gap over the shared span, "
                       "dz = parent TVD - child TVD",
        "depleting_parent_months": 12,
        "envelopes_ft": {"same": [1000.0, 1400.0], "topfill": [800.0, 1400.0], "underfill": [500.0, 1400.0]},
        "pools": "one per Midland bench (D128); no WCA-style pooling",
        "bench_label": "BOX membership (box_bench) for a producer in a Midland set of record, else its formation_blueox tag "
                       "(gate-21a question 2; the warehouse-tag reading is reported as a sensitivity)",
        "factor_table": {"form": "D113 option (a): oil only, cum-24, uniform scale (Di / b unchanged); ladder bench pair x count "
                                 "-> class x count x flank -> class x count -> class at the first rung with >= 30 children "
                                 "(box/prox_validate.fit); factor = exp(mean l_rel), l_rel = ln(actual / as-of mid_r2) minus the "
                                 "(group, cutoff) mean",
                         "source": "Midland TUNING children only (held-out packages never enter), all six tuning cutoffs "
                                   "(gate-21a question 1; the Delaware D113 table is reported as a sensitivity)",
                         "gas_water": "untouched (D113)"},
        "precedent": {"multi_parent_floor": 30, "severe_factor": 0.80, "package_floor": 30,
                      "counted_on": "Midland drilled children (first production >= 2016), the PUD's own bench pair (D114)"},
        "puds": "every producer >= 12 months at the data date counts; no shielding exemption (D115); permit-round TVDs counted, "
                "flagged",
        "production": "derived from the Midland base run by scripts.box_prox_record (D116), configuration re-measured per run",
    },
    "haircut": {
        "record_treatment_rule": "PROX_WF where the group's pooled holdout over its walk-forward cutoffs reaches 30 packages at "
                                 "cum-12 AND cum-24 (step-14 / D97 pattern); otherwise PROX (no haircut). Fixed from the 21b "
                                 "tuning run's SCORED counts (step-15 section 2 correction), before any holdout is read",
        "guard": "D106 per stream: refuse when the cum-k factors reverse by > 0.01 or the median location's D92 g(48) leaves "
                 "[0.6, 1.2]; a refused stream carries none (D122 representation), months exactly raw",
        "tuning_gate": "21b may move a group PROX_WF -> PROX on tuning evidence (step-15 BS3_C / WCB_1 precedent), or a group to "
                       "provisional (step-15 BS2_C precedent), on Michael's call; never PROX -> PROX_WF, never toward "
                       "validated, never after a holdout look",
        "holdout_time": "walk-forward factors from TUNING cells only (D58)",
        "production": "D102: tuning + holdout cells merged per cutoff, then the >= 30 floor; D92 rate shape; 9c guard",
    },
    "d99": {
        "cells": "per group, the horizons (12 / 24 / 36) whose POOLED holdout cell, as the record treatment scores it, reaches "
                 "30 packages; oil AND gas at each",
        "intervals": "P2.5-P97.5 of the pooled tuning package bias over 2,000 random 20 % draws of 3-mi blocks of the TUNING "
                     "packages (box/rehearse9b.consistency, seed 5); drawn at 21b, frozen at gate 21b with a sha256, never "
                     "redrawn",
        "pass": "every judged cell's holdout package bias inside its interval; >= 1 oil cell judged",
        "reported_not_gating": ["|package bias| <= 10 % per cell (D53)", ("scale-free spread vs the local-offsets benchmark + 0.05 "
                                "(D58)"), "per-cutoff cells"],
        "fail": "diagnose (7a pattern), never re-tune",
    },
    "tiers": {
        "validated": "D99 holdout PASS (oil and gas cells) on the record treatment (D131: validated where data allow)",
        "provisional": "D99 FAIL, or no cell judgeable (no holdout scored), or moved at the tuning gate: raw mid_r2p, no "
                       "haircut, D105 disclosure (tuning + holdout lines where a holdout failed, never the pooled figure alone)",
        "write": "box.bench_scope.validation per Midland bench at step 23 on go (today every Midland row reads the column "
                 "default 'validated')",
    },
    "water": {
        "method": "D107 ratio (ln WOR = a + b Np) on the measured-water cohort, on raw mid_r2 oil (D108)",
        "measured": "curated.water_data_quality 'measured' (Texas: the sql/41 label stands) + seller VDR daily water >= 6 months "
                    "(box/water11 as built)",
        "selection": "the oil first-ring rules on circles over the D54 ladder, then 30 / 40 / 50 mi to >= 10 measured analogs "
                     "(reach recorded); 3-9 at 50 mi = thin; < 3 = vendor-calculated fallback, flagged",
        "d109": "pooled group x horizon cells on measured-water packages: tuning |bias| <= 20 % AND scale-free band <= measured "
                "local-offsets benchmark + 0.10 (>= 30 packages); holdout once, a cell with >= 10 packages consistent inside "
                "its frozen P2.5-P97.5 tuning interval; validated water = validated oil + every judged tuning cell passes + "
                "every judged holdout cell consistent; else provisional",
        "reported": ["reach distribution per group", "top-operator share of the 10 nearest measured analogs (D133)",
                     "fallback and thin counts"],
    },
    "long_laterals": {
        "rule": "D129 / D134 C: ONE variant (the rules above); no exclusion by length",
        "reported_never_judged": [("D120 condition-6 mismatch classes (< 0.80 / 0.80-1.25 / >= 1.25 of the cohort mean), oil + "
                                   "gas, cum-12 / 24 / 36, Cui vs a linear-per-ft twin from the same cohort"),
                                  "absolute completed-lateral classes 5,000 ... >= 20,000 ft", ("share of locations whose "
                                  "translation extrapolates past 12,500 ft (and past 15,000 ft)")],
    },
    "reported_never_judged": [
        "thin-control wells (< 3 modern local wells within 3 mi at the cutoff), oil cum-12 / cum-24",
        "edges within 5 mi of the extent by compass side (step-15 section 5)",
        "analog radius reached; share of each cohort drawn from OUTSIDE the group's extent (20a: every MID_WCC location)",
        "production-sharing vs non-sharing scored wells per group (20b section 3: Spraberry sharing wells 1.13x oil / 1,000 ft)",
        "DEAN undrilled sticks by proximity outcome, inside the generated body vs the loop's addition (D143)",
        "the Delaware D113 factor table and the warehouse-tag bench label as proximity sensitivities",
        "Novi 2025Q3 Midland per-ft bias as the exhibit (step 18)",
    ],
    "read_before_this": [
        "step 18: Novi Midland bias and per-bench medians over all modern producers (no BOX forecast)",
        "step 20a / 20b: production summaries over all wells for the extents and cards (no BOX forecast)",
        ("step 21a: package counts (no forecast, no error), analog and water reach, PUD-side proximity configuration; the "
         "per-ft-vs-length measurement on producers in TUNING blocks only"),
    ],
}

DIGEST = "3299259e86d157aeeb157d8b2d66393585a40e889f42e1a4fb7b46fad0af59de"  # as registered 2026-10-31; a gate revision re-stamps it with its revision row


def canonical() -> str:
    return json.dumps(DEFINITION, sort_keys=True, separators=(",", ":"))


def digest() -> str:
    return hashlib.sha256(canonical().encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Text files hash with CRLF normalised to LF (checkout-independent)."""
    b = path.read_bytes()
    return hashlib.sha256(b if path.suffix == ".gz" else b.replace(b"\r\n", b"\n")).hexdigest()
