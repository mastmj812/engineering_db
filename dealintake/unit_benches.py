"""Per-unit bench list: seeded by `propose`, edited by the reviewer, read by `evaluate`.

Why per unit (VaULt, 2026-09-21): current-SOP land packages carry DEPTH-
SEVERED stacked DSUs — identical polygons with different rights and different
WI/NRI ("2-11 (Bone Spring)" Surface-11,985 ft over "2-11 (WCB)" 12,224 ft-
COE). One deal-wide --benches list would evaluate every bench in both halves.

The seed is a PROPOSAL with a reason on every row; `benches.yaml` in the run
directory is the reviewer's decision of record. Rules, in order:
  1. bench outside the rights BY STRATIGRAPHIC ORDER (formation-phrase
     bounds, dealintake.strat)                                   -> off
  2. no local offset depth, or thin control (< 3 real-depth wells) -> off
  3. numeric window (judged on LOCAL offset medians; declared depths are NOT
     local depths): in_window -> on; out -> off; edge (within
     depth.edge_margin_ft) -> the DSU NAME breaks the tie when it names a
     formation ("(WCB)"), else inside-edge on / outside-edge off
  4. no restriction on that side                                  -> on
`planned_lateral_ft` rides in the same file: the estimate is a median chord
and can be wrong for an odd-shaped unit — the reviewer overrides it here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from dealintake import strat
from dealintake.select_wells import bench_code

FILENAME = "benches.yaml"
_SKIP = {"OTHER"}


def seed_unit(
    dsu_name: str | None,
    lo: strat.Bound,
    hi: strat.Bound,
    bench_proposal: list[dict[str, Any]],
    col: strat.Column,
    basin: str | None,
) -> dict[str, dict[str, Any]]:
    allowed = strat.allowed_benches(lo, hi, col, basin) if basin else None
    hint = strat.name_hint(dsu_name, col, basin)
    rights = f"{lo.describe()} -> {hi.describe()}"
    out: dict[str, dict[str, Any]] = {}

    def put(b: str, on: bool, why: str) -> None:
        out[b] = {"evaluate": on, "why": why}

    for r in bench_proposal:
        b = bench_code(r["bench"])
        if b in _SKIP or b in out:
            continue
        thin = "thin control" in (r.get("note") or "")
        if allowed is not None and b not in allowed:
            put(b, False, f"outside {rights} by stratigraphic order")
        elif r.get("median_tvd_ft") is None:
            put(b, False, "no local offset control (no horizontal wells within 1 mi)")
        elif thin:
            put(b, False, f"thin control: {r.get('wells')} well(s), local median {r['median_tvd_ft']:,.0f} ft")
        elif r["status"] == "out":
            put(b, False, f"local median {r['median_tvd_ft']:,.0f} ft is {abs(r['margin_ft']):,.0f} ft outside {rights}")
        elif r["status"] == "edge":
            m = r["margin_ft"]
            side = f"{abs(m):,.0f} ft {'inside' if m > 0 else 'OUTSIDE'} the declared window edge"
            if hint:
                on = b in hint[1]
                put(b, on, f"edge: {side}; DSU name -> {hint[0]} ({'in' if on else 'not in'} it). "
                           "Declared depths are not local — confirm")
            else:
                put(b, m > 0, f"edge: {side}; no formation in the DSU name — confirm")
        else:  # in_window | no_window
            put(b, True, f"local median {r['median_tvd_ft']:,.0f} ft, {r.get('wells')} wells; within {rights}"
                if r["status"] == "in_window" else
                f"local median {r['median_tvd_ft']:,.0f} ft, {r.get('wells')} wells; allowed by {rights}")
    for b in allowed or []:        # allowed by order but never seen locally — visible, off
        if b not in out:
            put(b, False, f"allowed by {rights}, but no local offset control")
    return out


def render(prop: dict[str, Any]) -> str:
    """benches.yaml text from a proposal (hand-written YAML: one bench per line)."""
    s = [
        "# Per-unit bench list — REVIEWER DECISION OF RECORD for `evaluate`.",
        "# Seeded by `propose`; every row says why. Flip `evaluate`, fix `planned_lateral_ft`,",
        "# then run:  python -m dealintake.cli evaluate --run-dir <this folder>",
        "# Declared land depths are NOT local depths; formation phrases were resolved by",
        "# stratigraphic order (config/strat_column.yaml). A re-run of `propose` never overwrites this file.",
        f"config_version: {prop['config_version']}",
        f"strat_version: {prop.get('strat_version')}",
        "units:",
    ]
    for u in prop["units"]:
        s.append(f"  {u['label']}:")
        s.append(f"    dsu: {json.dumps(u.get('dsu_name'))}")
        s.append(f"    rights: {json.dumps(u['rights'])}")
        s.append(f"    planned_lateral_ft: {round(u['planned_lateral']['median_ft'])}"
                 f"    # median chord, range {u['planned_lateral']['min_ft']:,.0f}-{u['planned_lateral']['max_ft']:,.0f}"
                 f" at azimuth {u['planned_lateral']['azimuth_deg']} ({u['planned_lateral']['azimuth_source']})")
        s.append("    benches:")
        for b, row in u["bench_seed"].items():
            s.append(f"      {b + ':':7s} {{evaluate: {str(row['evaluate']).lower():5s}, why: {json.dumps(row['why'])}}}")
    return "\n".join(s) + "\n"


def read(run_dir: Path, prop: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{unit: {benches: [enabled, shallow->deep as listed], planned_lateral_ft, edited}}."""
    path = run_dir / FILENAME
    if not path.exists():
        raise FileNotFoundError(f"{path} not found — run `propose` first, or pass --benches for a deal-wide list")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    by_label = {u["label"]: u for u in prop["units"]}
    units = raw.get("units") or {}
    unknown = sorted(set(units) - set(by_label))
    if unknown:
        raise ValueError(f"{FILENAME}: unknown unit(s) {unknown}; proposal units are {sorted(by_label)}")
    out: dict[str, dict[str, Any]] = {}
    for label, u in by_label.items():
        row = units.get(label) or {}
        benches, opts = [], {}
        for b, v in (row.get("benches") or {}).items():
            if not isinstance(v, dict) or not isinstance(v.get("evaluate"), bool):
                raise ValueError(f"{FILENAME}: {label}.{b} needs `evaluate: true|false`")  # noqa: TRY004 — a file-content error
            if v["evaluate"]:
                benches.append(bench_code(b))
                opts[bench_code(b)] = bench_options(v, f"{label}.{b}")
        ll = row.get("planned_lateral_ft", u["planned_lateral"]["median_ft"])
        if not isinstance(ll, (int, float)) or ll <= 0:
            raise ValueError(f"{FILENAME}: {label}.planned_lateral_ft must be a positive number, got {ll!r}")
        min_leg = row.get("min_leg_ft")
        if min_leg is not None and (not isinstance(min_leg, (int, float)) or min_leg <= 0):
            raise ValueError(f"{FILENAME}: {label}.min_leg_ft must be a positive number, got {min_leg!r}")
        anchor = unit_anchor(row, label)
        leads = [b for b, o in opts.items() if o.get("stagger_lead")]
        if len(leads) > 1:
            raise ValueError(f"{FILENAME}: {label} names {len(leads)} stagger_lead benches {leads} — at most one")
        seed = [b for b, v in (u.get("bench_seed") or {}).items() if v["evaluate"]]
        out[label] = {
            "benches": benches, "planned_lateral_ft": float(ll), "seed_benches": seed,
            "bench_opts": opts, "min_leg_ft": None if min_leg is None else float(min_leg), "anchor": anchor,
            "edited": (sorted(benches) != sorted(seed) or round(float(ll)) != round(u["planned_lateral"]["median_ft"])
                       or any(opts[b] for b in opts) or min_leg is not None or anchor is not None),
        }
    return out


SIDES = ("west", "east", "north", "south")
ROLES = ("base", "upside")
WELL_TYPES = ("single", "uturn")
ANCHORS = ("west", "east", "center")


def unit_anchor(row: dict[str, Any], label: str) -> str | None:
    """Unit-level `anchor` (Michael 2026-10-22, RIP Harambe): where narvi hangs
    the unit's rows — `east` / `west` = flush to that LEASE LINE (narvi then
    runs the laterals parallel to it, not to the long axis), `center` = centred
    in the unit. Absent = narvi's auto (most footage)."""
    a = row.get("anchor")
    if a is not None and a not in ANCHORS:
        raise ValueError(f"{FILENAME}: {label}.anchor must be one of {ANCHORS}, got {a!r}")
    return a


def bench_options(v: dict[str, Any], where: str) -> dict[str, Any]:
    """Reviewer per-bench keys (all optional, VaULt walkthrough 2026-09-28):
      tvd_ft          landing TVD for a bench with thin/no local control (geology call)
      spacing_ft      row spacing for the generated pattern (overrides the nearby-Novi
                      spacing, config v15; REQUIRED where none is found nearby)
      n_wells         cap on rows per unit (4-per-section = 4 at 1,320 ft)
      keep_side       keep only the rows on that compass side of the unit centre
      drop_east_rows / drop_west_rows / drop_north_rows / drop_south_rows
                      drop the n rows nearest that side (PDP there, basin edge)
      min_leg_ft      (unit level) drop generated legs shorter than this
      role            base (default) | upside — carried to the dossier/handoff
      winerack        DEFAULT true (Michael 2026-10-08): a unit's generated benches
                      are placed TOGETHER in one narvi call, adjacent benches
                      staggered by half a spacing. false = place this bench on its
                      own (rows may stack directly over the neighbouring bench).
                      Give each bench its own spacing_ft.
      pdp_proximity   DEFAULT true (config v14): generated rows inside an existing
                      producer's depletion envelope (pdp_proximity: in thresholds.yaml)
                      are culled. false = keep them — a reviewer call, decision-logged.
      pdp_proximity_ignore  [api10, ...] — producers the reviewer exempts from the
                      cull (the rest still cull); their would-be culls are listed
      well_type       single (default) | uturn — narvi U-turns: two legs per well,
                      spacing_ft is LEG-TO-LEG; one location per well with its total
                      completed lateral. A U-turn bench is placed on its own (no stagger).
      anchor          (unit level) east | west | center — where the rows hang
      pin_offset_ft   put a row at this gunbarrel offset (ft; origin = unit centroid,
                      + = sign rule v2: E for N-S plans, N for E-W, SE on a 44° plan);
                      the bench's lattice runs through it at spacing_ft. A pinned bench
                      is placed on its own (no stagger). For hand-drawn layouts
                      (RIP Harambe blob: WCA_2 at -1,320 / 0 / +1,320 = pin 0 @ 1,320)
      stagger_lead    true on ONE staggered bench: it keeps its own layout and the
                      others shift half a spacing off it (default: the bench keeping
                      the most rows after its row rules leads)"""
    out: dict[str, Any] = {}
    if v.get("pin_offset_ft") is not None:
        if isinstance(v["pin_offset_ft"], bool) or not isinstance(v["pin_offset_ft"], (int, float)):
            raise ValueError(f"{FILENAME}: {where}.pin_offset_ft must be a number (ft), got {v['pin_offset_ft']!r}")
        out["pin_offset_ft"] = float(v["pin_offset_ft"])
    for k in ("tvd_ft", "spacing_ft"):
        if v.get(k) is not None:
            if not isinstance(v[k], (int, float)) or v[k] <= 0:
                raise ValueError(f"{FILENAME}: {where}.{k} must be a positive number, got {v[k]!r}")
            out[k] = float(v[k])
    if v.get("n_wells") is not None:
        if not isinstance(v["n_wells"], int) or v["n_wells"] < 1:
            raise ValueError(f"{FILENAME}: {where}.n_wells must be a positive integer, got {v['n_wells']!r}")
        out["n_wells"] = int(v["n_wells"])
    if v.get("keep_side") is not None:
        if v["keep_side"] not in SIDES:
            raise ValueError(f"{FILENAME}: {where}.keep_side must be one of {SIDES}, got {v['keep_side']!r}")
        out["keep_side"] = v["keep_side"]
    for side in SIDES:
        k = f"drop_{side}_rows"
        if v.get(k) is not None:
            if not isinstance(v[k], int) or v[k] < 0:
                raise ValueError(f"{FILENAME}: {where}.{k} must be a non-negative integer, got {v[k]!r}")
            out[k] = int(v[k])
    if v.get("role") is not None:
        if v["role"] not in ROLES:
            raise ValueError(f"{FILENAME}: {where}.role must be one of {ROLES}, got {v['role']!r}")
        out["role"] = v["role"]
    for k in ("winerack", "pdp_proximity", "stagger_lead"):
        if v.get(k) is not None:
            if not isinstance(v[k], bool):
                raise ValueError(f"{FILENAME}: {where}.{k} must be true or false, got {v[k]!r}")
            out[k] = v[k]
    if v.get("well_type") is not None:
        if v["well_type"] not in WELL_TYPES:
            raise ValueError(f"{FILENAME}: {where}.well_type must be one of {WELL_TYPES}, got {v['well_type']!r}")
        out["well_type"] = v["well_type"]
    if v.get("pdp_proximity_ignore") is not None:
        ig = v["pdp_proximity_ignore"]
        if not isinstance(ig, list) or not all(isinstance(a, (int, str)) and str(a).isdigit() and len(str(a)) == 10
                                               for a in ig):
            raise ValueError(f"{FILENAME}: {where}.pdp_proximity_ignore must be a list of api10s, got {ig!r}")
        out["pdp_proximity_ignore"] = [str(a) for a in ig]
    return out


def reviewed_benches(run_dir: Path) -> dict[str, dict[str, Any]]:
    """{unit: {benches: [enabled], bench_opts: {bench: options}, min_leg_ft}}
    from an existing benches.yaml, {} when there is none — lets a re-propose
    draw its previews at the REVIEWER's benches, TVDs, spacing and row rules."""
    path = run_dir / FILENAME
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, dict[str, Any]] = {}
    for label, row in (raw.get("units") or {}).items():
        row = row or {}
        on = {bench_code(b): bench_options(v, f"{label}.{b}") for b, v in (row.get("benches") or {}).items()
              if isinstance(v, dict) and v.get("evaluate") is True}
        out[label] = {"benches": list(on), "bench_opts": on,
                      "min_leg_ft": None if row.get("min_leg_ft") is None else float(row["min_leg_ft"]),
                      "anchor": unit_anchor(row, label)}
    return out
