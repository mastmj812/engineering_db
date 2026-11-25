"""BOX step 13b — the steady-state refresh's decisions of record as code (D126), DB-free apart from the read-only pulls.

  due(...)            is a refresh due? The record's production-through lagging the warehouse by more than LAG_MONTHS
                      (D126, unchanged). A Novi Intelligence vintage is no longer a trigger (BOX sticks phase 8, Michael
                      2026-11-25: locations are ours, Novi is comparison only); on demand is Michael's call and needs no
                      rule. The warehouse date is max(prod_date), which a few early reporters carry about two months
                      past a record's own data-through built the same day (run 36: 2026-09 against 2026-11), so
                      "more than 4" is roughly a quarter of new production.
  extent_trigger(...) the D17 re-review trigger: >= EXTENT_N producers of a group's tags, first producing after its extent was
                      stored, with lateral midpoints OUTSIDE the extent and within EXTENT_X_MI of it.
  chain(...)          the ordered commands of one refresh: read-only steps run by scripts.box_refresh, every store a separate go.

Step 19 (D130): a refresh is one basin's - its record run, its groups (GROUPS_BY_BASIN), its extents; the other basin's record is
never read or touched. The Midland groups join GROUPS_BY_BASIN at step 23.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

LAG_MONTHS = 4  # D126; since phase 8 (2026-11-25) the ONLY trigger - the Novi-vintage one is gone
EXTENT_N = 10  # D126 = D17's N
EXTENT_X_MI = 2.0  # D126 = D17's X
MI_M = 1609.344
# the record run's groups, in the 16d build order, with the formation_blueox tags each tests and its extent's bench
GROUPS: dict[str, tuple[tuple[str, ...], str]] = {
    "WCA": (("WCA_1", "WCA_2"), "WCA"), "BS2_S": (("BS2_S",), "BS2_S"), "WCXY_WCA1": (("WCXY",), "WCA"),
    "WCB_1": (("WCB_1",), "WCB_1"), "WCC": (("WCC",), "WCC"), "AVA_0": (("AVA_0",), "AVA_0"), "AVA_1": (("AVA_1",), "AVA_1"),
    "AVA_2": (("AVA_2",), "AVA_2"), "BS2_C": (("BS2_C",), "BS2_C"), "BS3_S": (("BS3_S",), "BS3_S"), "BS3_C": (("BS3_C",), "BS3_C"),
    "WCB_2": (("WCB_2",), "WCB_2"), "BS1_S": (("BS1_S",), "BS1_S"),
}
GROUPS_BY_BASIN: dict[str, dict[str, tuple[tuple[str, ...], str]]] = {"delaware": GROUPS}


def groups_for(basin: str) -> dict[str, tuple[tuple[str, ...], str]]:
    if basin not in GROUPS_BY_BASIN:
        raise ValueError(f"no record-run groups for basin {basin!r} yet (Midland joins at step 23); known {sorted(GROUPS_BY_BASIN)}")
    return GROUPS_BY_BASIN[basin]


def months_between(a: dt.date, b: dt.date) -> int:
    """Whole calendar months from a to b (b later = positive)."""
    return (b.year - a.year) * 12 + (b.month - a.month)


def due(record_through: dt.date, live_through: dt.date, lag_months: int = LAG_MONTHS) -> tuple[bool, list[str]]:
    lag = months_between(record_through, live_through)
    reasons = [f"production-through lags the warehouse by {lag} months (> {lag_months}, D126)"] if lag > lag_months else []
    return bool(reasons), reasons


def extent_trigger(counts: dict[str, int], n: int = EXTENT_N) -> list[str]:
    """Groups whose extent re-review is due (D126 / D17), from the outside-within-X counts."""
    return [g for g, c in counts.items() if c >= n]


EXTENT_SQL = """
WITH e AS (SELECT geom, created_at FROM box.extent WHERE basin = %(basin)s AND bench = %(bench)s AND is_record)
SELECT count(*)
FROM curated.wells w
JOIN curated.formation_blueox fb ON fb.api10 = w.api10, e
WHERE fb.basin_blueox = %(basin)s AND fb.formation_blueox = ANY (%(forms)s)
  AND w.first_production_date > e.created_at::date
  AND COALESCE(w.lateral_length_ft, 0) > 0 AND w.wellstick_geom IS NOT NULL
  AND NOT extensions.ST_Contains(e.geom, extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5))
  AND extensions.ST_DWithin(extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5)::extensions.geography,
                            e.geom::extensions.geography, %(x_m)s)
"""

STATE_SQL = """
SELECT r.run_id, r.data_through,
       (SELECT max(prod_date) FROM curated.production) AS live_through
FROM box.forecast_run r WHERE r.is_record AND r.basin = %(basin)s
"""


def chain(pool_dir: str, out: str, workers: int, basin: str = "delaware") -> list[dict[str, Any]]:
    """The refresh of ONE basin (D130), in order. `go` = a WRITE to the database that needs Michael's explicit go (each its own)."""
    benches = ",".join(groups_for(basin))
    return [
        {"step": "pool refresh (read-only; Michael confirms the added wells, then commit the directory)", "go": False,
         "cmd": f"python -m scripts.box_pool_refresh --out {pool_dir}"},
        {"step": "build (read-only, ~7 h, resumes per group)", "go": False,
         "cmd": f"python -m scripts.box_pud_run build --source box_sticks --selection r2 --wells {pool_dir} --benches {benches} "
                f"--workers {workers} --out {out}"},
        {"step": "water build (read-only, ~40 min)", "go": False,
         "cmd": f"python -m scripts.box_water_run build --run-pkl {out}/run.pkl --out {out}_water --workers {workers}"},
        # the chain run on live at the BOX sticks cutover (2026-11-24, docs/box_sticks/phase6-2026-11-23/STEP4A.md, STEP4B.md):
        # the base run is never the record; the derived (proximity) run is flipped on its own go
        {"step": "store the base run (not record)", "go": True, "cmd": f"python -m scripts.box_pud_run store --out {out}"},
        {"step": "store water on it", "go": True, "cmd": f"python -m scripts.box_water_run store --out {out}_water --run-id <base>"},
        {"step": "proximity re-measure (read-only; leg by leg on U-turn sticks)", "go": False,
         "cmd": f"python -m scripts.box_record23 measure --basin {basin} --src-run <base> --out {out}_prox"},
        {"step": "store the derived run (not record): rollback rehearsal, then --commit", "go": True,
         "cmd": f"python -m scripts.box_record23 store --basin {basin} --src-run <base> --outcomes {out}_prox/outcomes.csv.gz "
                f"--links {out}_prox/pud_links.pkl [--commit]"},
        {"step": "flip the record to the derived run (unpriced: econ blank until Steven prices it)", "go": True,
         "cmd": f"python -m scripts.box_record23 flip --basin {basin} --run <derived> --allow-unpriced [--commit]"},
        {"step": f"prune every non-record {basin} run (D123 / D130)", "go": True,
         "cmd": f"python -m scripts.box_prune_runs --apply --include-priced --basin {basin}"},
        {"step": "Steven re-prices the new record (#eng-updates post = its own go)", "go": True, "cmd": "-"},
    ]
