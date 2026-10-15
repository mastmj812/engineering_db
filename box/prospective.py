"""BOX prospective confirmation (D59 condition 1, D70): the 2026 cohort, frozen BEFORE any of its outcomes were looked at.

The definition below is the record. `DIGEST` pins it: tests/test_box_prospective.py recomputes the SHA-256 of the canonical
definition and fails if anything changed, so an edit cannot slip in after the data arrive (that would be tuning after the fact).
Frozen 2026-10-15, step 7d.

What is scored: the next rolling-origin fold of the D53 harness, nothing re-tuned.
  - prediction cutoff 2025-12-01: analogs, fits and F(k) built only from data before it (box/backtest_report.run_fold rules)
  - cohort = Delaware WCA-pool wells (formation_blueox WCA_1 / WCA_2 / WCXY, the gate-1 WCA pool incl. the D20 one-way WCXY
    evidence) first producing 2026-01-01 .. 2026-12-31, real lateral, lateral midpoint inside the record WCA extent
    (box.extent 6). Bench = curated formation_blueox as-is: the gate-1 consensus class rule is NOT re-run on 2026 wells (the
    harness scored the gate-1 set), a stated difference. No 2026 well was ever in a tuning or holdout view
  - method = box_v2 (spec box_v2_wf, D58, code d5c3ebd) x the D62 haircut AS DELIVERED (box.forecast_run 4 factors), i.e.
    the method Steven receives
  - grain, error and verdict = D53 / D58 / D70 unchanged: development packages (co-extent, first production within 180 d,
    overlap >= 30 %), error = sum actual / sum predicted - 1, judged per (stream x horizon) cell with >= 30 packages:
    |package bias| <= 10 % AND scale-free spread <= benchmark + 0.05; oil AND gas
  - horizons judged 12 / 24 / 36; cum-6 is REPORTED as the early read (D59), never judged
  - watch item (D68): NM vs TX cum-12 spread reported separately
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

DEFINITION: dict[str, Any] = {
    "name": "box_prospective_2026",
    "frozen_on": "2026-10-15",
    "decisions": ["D52", "D53", "D58", "D59", "D62", "D68", "D70"],
    "cutoff": "2025-12-01",
    "cohort": {"basin": "delaware", "formations": ["WCA_1", "WCA_2", "WCXY"], "first_production_from": "2026-01-01",
               "first_production_to": "2026-12-31", "lateral_ft_gt": 0, "midpoint_inside_extent_id": 6},
    "method": {"spec": "box_v2_wf", "spec_code_sha": "d5c3ebd", "variant": "box_v2", "haircut": "D62 as delivered",
               "haircut_source_run_id": 4},
    "grain": {"package_codev_days": 180, "package_overlap": 0.30},
    "verdict": {"bias_tol": 0.10, "band_tol": 0.05, "scale_free": True, "min_packages": 30, "streams": ["oil", "gas"],
                "horizons_judged": [12, 24, 36], "horizons_reported": [6]},
    "watch": ["NM vs TX cum-12 scale-free spread (D68)"],
}

DIGEST = "a72c797d845bcdbde4a17c150d448740d1e98744335e9d12a8b4cd876dbfd55d"


def canonical() -> str:
    return json.dumps(DEFINITION, sort_keys=True, separators=(",", ":"))


def digest() -> str:
    return hashlib.sha256(canonical().encode("utf-8")).hexdigest()


_COHORT_SQL = """
SELECT w.api10, fb.formation_blueox, w.first_production_date, w.lateral_length_ft,
       (SELECT count(*) FROM curated.production p WHERE p.api10 = w.api10) AS months_reported
FROM curated.wells w
JOIN curated.formation_blueox fb ON fb.api10 = w.api10
JOIN box.extent e ON e.extent_id = %(extent)s
WHERE fb.basin_blueox = %(basin)s AND fb.formation_blueox = ANY (%(forms)s)
  AND w.first_production_date BETWEEN %(fp0)s AND %(fp1)s
  AND COALESCE(w.lateral_length_ft, 0) > %(lat)s AND w.wellstick_geom IS NOT NULL
  AND extensions.ST_Contains(e.geom, extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5))
ORDER BY w.first_production_date, w.api10
"""


def cohort_params() -> dict[str, Any]:
    c = DEFINITION["cohort"]
    return {"extent": c["midpoint_inside_extent_id"], "basin": c["basin"], "forms": c["formations"],
            "fp0": dt.date.fromisoformat(c["first_production_from"]), "fp1": dt.date.fromisoformat(c["first_production_to"]),
            "lat": c["lateral_ft_gt"]}


def cohort(conn: Any) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_COHORT_SQL, cohort_params())
        rows = cur.fetchall()
    conn.rollback()
    return rows
