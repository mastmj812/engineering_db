"""BOX step 13d — the 2026 prospective test of the run-19 method (r2, D121) on all 13 groups, pre-registered BEFORE any 2026
outcome was looked at. The only path that moves a group between tiers (D105 validated / provisional), either way (D124).

The definition below is the record. `DIGEST` pins it: tests/test_box_prospective16.py recomputes the SHA-256 of the canonical
definition and fails on any edit. D85 (box/prospective.py: WCA only, run-4 method) stays frozen and is scored alongside, for
information only. Rationale, schedule and the gate questions: docs/box/step13d-2026-10-25/PREREGISTRATION.md.

What is scored, in one paragraph: the next rolling-origin fold of the 16c harness at cutoff 2025-12-01 (analogs, fits, F(k),
proximity configuration all from data before it), run with the PRODUCTION method of run 19 — r2 selection, measured spacing,
Cui translation, the D113 proximity oil factor, the walk-forward haircut on WCA oil and BS2_S oil + gas from the frozen evidence
pack — on the Delaware wells first producing in 2026 inside each group's record extent. Bench membership is read at SCORING
time (13d tag rule); the freeze-time tags are a sensitivity. Each group's cells are judged by D99 consistency against intervals
drawn from its own tuning packages at the cohort's size; one judgment per horizon, on a fixed date.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

DOCS = Path("docs") / "box" / "step13d-2026-10-25"
TUNING_RUNS = Path("runs") / "step16c"  # gitignored; pinned by tuning_views.sha256 (13d manifest)

# group -> (formation_blueox tags it tests, record extent id of run 19, tier at the freeze)
GROUPS: dict[str, tuple[tuple[str, ...], int, str]] = {
    "WCA": (("WCA_1", "WCA_2"), 6, "validated"),
    "WCXY_WCA1": (("WCXY",), 6, "validated"),
    "BS2_S": (("BS2_S",), 7, "validated"),
    "WCB_1": (("WCB_1",), 22, "validated"),
    "WCC": (("WCC",), 27, "validated"),
    "AVA_0": (("AVA_0",), 28, "provisional"),
    "AVA_1": (("AVA_1",), 29, "provisional"),
    "AVA_2": (("AVA_2",), 30, "provisional"),
    "BS1_S": (("BS1_S",), 26, "provisional"),
    "BS2_C": (("BS2_C",), 20, "provisional"),
    "BS3_C": (("BS3_C",), 18, "provisional"),
    "BS3_S": (("BS3_S",), 16, "provisional"),
    "WCB_2": (("WCB_2",), 24, "provisional"),
}

DEFINITION: dict[str, Any] = {
    "name": "box_prospective_2026_r2",
    "frozen_on": "2026-10-25",
    "decisions": ["D52", "D53", "D58", "D63", "D99", "D105", "D113", "D114", "D119", "D120", "D121", "D122", "D124"],
    "d85": "kept frozen (box/prospective.py, digest a72c797d); scored alongside, informational, never a tier verdict",
    "cutoff": "2025-12-01",
    "cohort": {"basin": "delaware", "first_production_from": "2026-01-01", "first_production_to": "2026-12-31",
               "lateral_ft_gt": 0, "midpoint_inside": "the group's record extent (extent_id below)",
               "groups": {g: {"formations": list(f), "extent_id": e, "tier_at_freeze": t} for g, (f, e, t) in GROUPS.items()}},
    "tags": {"governing": "scoring_time",
             "record": "curated.formation_blueox at scoring, its 13e tag-release id stamped on the score",
             "applies_to": ["which group a 2026 well tests", "the analog pools the hindcast forecasts it from"],
             "sensitivity": "freeze-time tags (cohort_at_freeze.csv; pools as frozen in run 19), reported, never the verdict",
             "merge_or_split": "re-defined by an amendment committed before any score is read; never after"},
    "method": {"source_run_id": 19, "code_sha": "06fe42c", "selection": "box_v2s_r2",
               "rules": "Rules(relax=('count', 'spacing'), count_floor=5, wide_tol=0.4, lateral='translate', "
                        "translate_range=(5000.0, 15000.0), level_only=False, level_only_post_peak=3.0)",
               "spacing": "measured (D119)", "volumes": "uptime_free (D63)",
               "proximity": {"factor": "box.prox_pud.decide, oil only (D113)", "configuration": "parents producing before the cutoff",
                             "no_precedent": "excluded from the verdict and counted (D114)",
                             "tables": {"haircut_table_candidate.csv": "0a62beb86812eaebeab7c40e7cfc23675cc8154f6503398700363b74828e3c80",
                                        "config_children.csv.gz": "a0149ac91f2e67a2f3ef3fa65f4df3102dce0bcb7471641575a076709afa3b6f"}},
               "haircut": {"streams": {"WCA": ["oil"], "BS2_S": ["oil", "gas"]}, "others": "none",
                           "source": "docs/box/step16d-2026-10-23/r2_evidence.json",
                           "source_sha256_lf": "90da3c56cb9dc31cf53850603dfd142f5c27593e15ee93b1729dcc3e20d22626"}},
    "grain": {"package_codev_days": 180, "package_overlap": 0.30, "error": "sum actual / sum forecast - 1 (negative = forecast HIGH)"},
    "verdict": {"rule": "D99 consistency",
                "cell_pass": "the cohort's package bias lies inside P2.5-P97.5 of the group's TUNING package bias drawn at the "
                             "cohort's size: 2,000 draws of 3-mi blocks (D52 shape) from the 16c tuning packages pooled over "
                             "cutoffs 2019-2024, under the production treatment (r2 + proximity, + haircut where run 19 has one)",
                "draws": 2000, "seed": 20261025, "quantiles": [2.5, 97.5],
                "share": "cell packages in the cohort / cell packages in tuning (the block share that matches the cohort's size)",
                "streams": ["oil", "gas"], "horizons_judged": [12, 24], "min_packages": 30,
                "group": {"PASS": "every judged cell passes and at least one oil cell is judged",
                          "FAIL": "any judged cell fails",
                          "NOT_JUDGED": "no oil cell reaches min_packages"},
                "tier": {"provisional_PASS": "proposed for validated at its gate (Michael)",
                         "validated_FAIL": "provisional (D105); diagnose, never re-tune",
                         "NOT_JUDGED": "tier unchanged"},
                "reported_not_gating": ["|package bias| <= 10 % per cell (D53)", "scale-free spread vs the benchmark (D58)",
                                        "thin-control wells (< 3 local wells within 3 mi), oil cum-12 / cum-24",
                                        "NM vs TX", "freeze-time-tag sensitivity", "no-precedent count", "cum-6 early reads"]},
    "schedule": {"early_reads": "cum-6 on wells with >= 7 reported months, and cum-12 on wells first producing Jan-Jun 2026 at "
                                "production through 2027-08-01: REPORTED, never judged",
                 "cum12_judged_once": "the first build whose production runs through >= 2028-01-01 (every 2026 well has 13 months)",
                 "cum24_judged_once": "the first build whose production runs through >= 2029-01-01"},
    "watch": ["the 2022-23 vintage episode (provisional cutoff bias -10 / -11 %): does 2026 read like 2023-24 (within ~2 %)?",
              "WCA gas newest cohort trending high (D122 watch)", "WCC and BS2_S cum-24 (-17 % / -10 % disclosed)"],
}

DIGEST = "6bc679947ce564aab8ef8564f5f7ad2d090176d21a9342408db37749c35445af"


def canonical() -> str:
    return json.dumps(DEFINITION, sort_keys=True, separators=(",", ":"))


def digest() -> str:
    return hashlib.sha256(canonical().encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    """Text files hash with CRLF normalised to LF (checkout-independent); gzip / binary files hash raw."""
    b = path.read_bytes()
    return hashlib.sha256(b if path.suffix == ".gz" else b.replace(b"\r\n", b"\n")).hexdigest()


_COHORT_SQL = """
SELECT w.api10, fb.formation_blueox, w.first_production_date, w.state_code
FROM curated.wells w
JOIN curated.formation_blueox fb ON fb.api10 = w.api10
JOIN box.extent e ON e.extent_id = %(extent)s
WHERE fb.basin_blueox = %(basin)s AND fb.formation_blueox = ANY (%(forms)s)
  AND w.first_production_date BETWEEN %(fp0)s AND %(fp1)s
  AND COALESCE(w.lateral_length_ft, 0) > %(lat)s AND w.wellstick_geom IS NOT NULL
  AND extensions.ST_Contains(e.geom, extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5))
ORDER BY w.first_production_date, w.api10
"""


def cohort_params(group: str) -> dict[str, Any]:
    c = DEFINITION["cohort"]
    g = c["groups"][group]
    return {"extent": g["extent_id"], "basin": c["basin"], "forms": g["formations"], "lat": c["lateral_ft_gt"],
            "fp0": dt.date.fromisoformat(c["first_production_from"]), "fp1": dt.date.fromisoformat(c["first_production_to"])}


def cohort(conn: Any, group: str) -> list[tuple[Any, ...]]:
    """The group's 2026 wells as tagged NOW (api10, formation_blueox, first production, state). Identities only — no volumes."""
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_COHORT_SQL, cohort_params(group))
        rows = cur.fetchall()
    conn.rollback()
    return rows
