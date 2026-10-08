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
        seed = [b for b, v in (u.get("bench_seed") or {}).items() if v["evaluate"]]
        out[label] = {
            "benches": benches, "planned_lateral_ft": float(ll), "seed_benches": seed,
            "bench_opts": opts, "min_leg_ft": None if min_leg is None else float(min_leg),
            "edited": (sorted(benches) != sorted(seed) or round(float(ll)) != round(u["planned_lateral"]["median_ft"])
                       or any(opts[b] for b in opts) or min_leg is not None),
        }
    return out


SIDES = ("west", "east", "north", "south")
ROLES = ("base", "upside")


def bench_options(v: dict[str, Any], where: str) -> dict[str, Any]:
    """Reviewer per-bench keys (all optional, VaULt walkthrough 2026-09-28):
      tvd_ft          landing TVD for a bench with thin/no local control (geology call)
      spacing_ft      row spacing for the generated pattern (the reviewer sets the
                      pattern; Novi's de-facto spacing is a suggestion, 880 the fallback)
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
                      Give each bench its own spacing_ft."""
    out: dict[str, Any] = {}
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
    if v.get("winerack") is not None:
        if not isinstance(v["winerack"], bool):
            raise ValueError(f"{FILENAME}: {where}.winerack must be true or false, got {v['winerack']!r}")
        out["winerack"] = v["winerack"]
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
                      "min_leg_ft": None if row.get("min_leg_ft") is None else float(row["min_leg_ft"])}
    return out
