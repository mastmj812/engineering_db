"""deal-intake gate 8 — hand the reviewed dossier to narvi + anduin.

`plan()` turns a finished `evaluate` run into the exact requests the apps will
receive, and checks them before anything is written:

* narvi — one composed scenario per unit (the UI's own save route, so narvi
  regenerates the sticks server-side): `deal_id` = the UI's slug of the parcel
  label, `scenario_id` = `plan_<slug>`, name = the label (the VaULt
  convention). narvi has no row rules (n_wells / keep_side / drop_<side>_rows /
  min_leg_ft), so the plan previews the IDENTICAL save recipe, matches every
  leg to the dossier's kept locations (midpoint <= MATCH_TOL_FT, same bench)
  and sends the rest as `culled_wells`. A unit whose dossier benches came from
  more than one generate call (e.g. 1-12: WCB_1 + WCB_2, each placed alone)
  would be staggered together by the save, so every bench is PINNED at its own
  preview position (`ZoneModel.offset_ft`). Any dossier location the recipe
  cannot reproduce BLOCKS the unit — never a silent difference.
* anduin — one saved type curve per dossier curve (name = the dossier's
  compass name, members = the dossier cohort, peak_ramp, per lateral ft, Arps
  on every stream), the deal, and the Blue Ox zones: one zone per curve,
  scenario scope = that curve's units, tab order shallow -> deep then the
  dossier's curve order.

Read-only: narvi /api/generate previews and a warehouse read of narvi.scenario.
Cohort culls are the reviewer's job in anduin after the save (Michael
2026-10-08); a curve edited in anduin since the handoff is never overwritten.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from dealintake.geo import LocalFrame, true_to_grid
from dealintake.select_wells import bench_code

MATCH_TOL_FT = 50.0
FT_PER_M = 3.28084
NARVI_CATEGORIES = ["pdp", "pud"]          # Novi benches: PUD only, as the dossier counted them


def slug(label: str) -> str:
    """narvi's `dealIdFor` (frontend/src/store.ts): lowercase, non-[a-z0-9] runs -> '_'."""
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def scenario_key(label: str) -> dict[str, str]:
    s = slug(label)
    return {"deal_id": s, "scenario_id": f"plan_{s}"}


def load_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    sig = json.loads((run_dir / "signals.json").read_text(encoding="utf-8"))
    prop = json.loads((run_dir / "proposal.json").read_text(encoding="utf-8"))
    return sig, prop


def unit_benches(sig: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """{unit label: {bench: UB}} over every evaluated bench (lateral classes merged)."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for B in sig["benches"].values():
        for label, UB in B["units"].items():
            if UB.get("locations"):
                out.setdefault(label, {})[B["bench"]] = UB
    return out


# ---------------------------------------------------------------------------
# narvi
# ---------------------------------------------------------------------------

def _mid(wkt_or_geom: Any) -> Any:
    from shapely import wkt as shp_wkt
    g = shp_wkt.loads(wkt_or_geom) if isinstance(wkt_or_geom, str) else wkt_or_geom
    return g.interpolate(0.5, normalized=True)


def match_legs(
    targets: list[dict[str, Any]], legs: list[dict[str, Any]], frame: LocalFrame, tol_ft: float = MATCH_TOL_FT,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], list[int]]:
    """Greedy nearest-midpoint match of dossier locations to preview legs (one
    bench). Returns ({target index: leg}, unmatched legs, unmatched target indices)."""
    tm = [frame.to_local(_mid(t["wkt"])) for t in targets]
    lm = [frame.to_local(_mid(lg["geom"])) for lg in legs]
    pairs = sorted((tm[i].distance(lm[j]) * FT_PER_M, i, j) for i in range(len(tm)) for j in range(len(lm)))
    got: dict[int, dict[str, Any]] = {}
    used: set[int] = set()
    for d, i, j in pairs:
        if d > tol_ft or i in got or j in used:
            continue
        got[i] = {**legs[j], "match_ft": round(d, 1)}
        used.add(j)
    return got, [lg for j, lg in enumerate(legs) if j not in used], [i for i in range(len(targets)) if i not in got]


def _by_bench(legs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for lg in legs:
        out.setdefault(bench_code(str(lg.get("formation") or "")), []).append(lg)
    return out


def plan_unit(
    narvi: Any, unit: dict[str, Any], ubs: dict[str, dict[str, Any]], setback_ft: float,
    upload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The composed-save body for one unit + its row match against the dossier.
    `upload` = narvi's own parcel record for this label (attributes + tracts in
    the shape its parcel card reads); None -> proposal attributes, no tracts."""
    from dealintake.clients.narvi import legs as narvi_legs

    label, geom = unit["label"], shape(unit["geometry"])
    frame = LocalFrame.around(geom)
    az_true = float(unit["planned_lateral"]["azimuth_deg"])
    az_grid = true_to_grid(az_true, geom.centroid.x, geom.centroid.y)
    gen = {b: UB for b, UB in ubs.items() if UB["gate2"]["source"] != "novi"}
    novi = {b: UB for b, UB in ubs.items() if UB["gate2"]["source"] == "novi"}
    order = sorted(gen, key=lambda b: gen[b]["tvd_ft"])
    zones = [{"formation": b, "target_tvd_ft": gen[b]["tvd_ft"], "spacing_ft": gen[b]["spacing_ft"]} for b in order]
    base_sp = zones[0]["spacing_ft"] if zones else 0.0
    issues: list[str] = []

    # evaluate's own calls: winerack benches together, every other bench alone
    wr = [b for b in order if gen[b].get("winerack")]
    calls = ([wr] if wr else []) + [[b] for b in order if b not in wr]
    pins: dict[str, float] = {}
    if len(calls) > 1:
        for call in calls:
            zs = [z for z in zones if z["formation"] in call]
            got = _by_bench(narvi_legs(narvi.generate(geom, zs, setback_ft=setback_ft,
                                                      spacing_ft=zs[0]["spacing_ft"], azimuth_deg=az_grid)))
            for b in call:
                hit, _, miss = match_legs(gen[b]["locations"], got.get(b, []), frame)
                if miss or not hit:
                    issues.append(f"{b}: {len(miss)} dossier location(s) not reproduced by narvi's preview "
                                  "— re-run evaluate (narvi or inputs changed since)")
                    continue
                pins[b] = float(hit[min(hit)]["gunbarrel_x_ft"])
        for z in zones:
            if z["formation"] in pins:
                z["offset_ft"] = pins[z["formation"]]

    params = {"spacing_ft": base_sp, "setback_ft": setback_ft, "azimuth_deg": az_grid, "well_type": "single"}
    rows: list[dict[str, Any]] = []
    culled: list[str] = []
    if zones and not issues:
        save_legs = _by_bench(narvi_legs(narvi.generate(geom, zones, setback_ft=setback_ft, spacing_ft=base_sp,
                                                        azimuth_deg=az_grid)))
        for b in order:
            targets = gen[b]["locations"]
            hit, extra, miss = match_legs(targets, save_legs.get(b, []), frame)
            for i, t in enumerate(targets):
                lg = hit.get(i)
                rows.append({"bench": b, "well_name": lg and lg["well_name"], "status": "kept" if lg else "MISSING",
                             "lateral_ft": lg and lg.get("completed_lateral_ft"), "match_ft": lg and lg["match_ft"],
                             "offset_ft": lg and lg.get("gunbarrel_x_ft"), "tvd_ft": gen[b]["tvd_ft"],
                             "wkt": t["wkt"]})
            for lg in extra:
                culled.append(lg["well_name"])
                rows.append({"bench": b, "well_name": lg["well_name"], "status": "culled",
                             "lateral_ft": lg.get("completed_lateral_ft"), "match_ft": None, "wkt": lg["geom"].wkt,
                             "offset_ft": lg.get("gunbarrel_x_ft"), "tvd_ft": gen[b]["tvd_ft"],
                             "why": "; ".join(gen[b].get("row_rules") or []) or "not a dossier location"})
            if miss:
                issues.append(f"{b}: {len(miss)} of {len(targets)} dossier location(s) not in the save recipe's sticks")
            for lg in save_legs.get(b, []):
                if not lg.get("well_name"):
                    issues.append(f"{b}: preview leg without a well_name — cannot cull by name")
        stray = sorted(set(save_legs) - set(order))
        if stray:
            issues.append(f"save recipe generated unexpected bench(es) {stray}")

    win = unit.get("window_used") or [None, None]
    declared = str(unit.get("window_source") or "").startswith("declared")
    body = {
        **scenario_key(label), "name": label, "parcel": unit["geometry"],   # what evaluate generated on
        "bench_sources": {**{b: "generate" for b in gen}, **{b: "novi" for b in novi}},
        "categories": NARVI_CATEGORIES, "culled_wells": sorted(culled), "category_overrides": {},
        "params": params, "zones": zones, "source_azimuth": False,
        "deal_terms": {
            "min_depth_ft": win[0], "max_depth_ft": win[1],
            # narvi reads a basis starting "land file declared" as not-yet-correlated
            "basis": (f"land file declared — {unit.get('rights') or ''}" if declared
                      else str(unit.get("window_source") or "")),
            "attributes": (upload or {}).get("attributes") or unit.get("attributes") or {},
            "tracts": (upload or {}).get("tracts") or [],
        },
    }
    return {
        "label": label, "dsu": unit.get("dsu_name") or label, "body": body, "rows": rows,
        "pins": pins, "azimuth_true_deg": az_true, "azimuth_grid_deg": round(az_grid, 2),
        "expected": {b: len(UB["locations"]) for b, UB in ubs.items()},
        "novi_benches": {b: [loc["id"] for loc in UB["locations"]] for b, UB in novi.items()},
        "issues": issues,
    }


# ---------------------------------------------------------------------------
# anduin
# ---------------------------------------------------------------------------

def plan_curves(sig: dict[str, Any], prop: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    """One saved type curve + one Blue Ox zone per dossier curve, in tab order."""
    from dealintake.render.dossier_html import _labels

    out: list[dict[str, Any]] = []
    benches = sorted(sig["benches"].items(), key=lambda kv: kv[1].get("tvd_ft") or 0.0)
    for key, B in benches:
        groups = B.get("tc_groups") or []
        for G, name in zip(groups, _labels(key, B, prop), strict=True):
            api10s = [w["api10"] for w in G["tc_wells"]]
            roles = {(B["units"].get(u) or {}).get("role", "base") for u in G["units"]}
            issues = []
            if len(roles) > 1:
                issues.append(f"units mix roles {sorted(roles)} — one zone needs one reserve category")
            if not api10s:
                issues.append("empty cohort")
            oil = (G.get("tc_preview") or {}).get("oil") or {}
            out.append({
                "name": name, "bench": B["bench"], "key": key, "units": G["units"],
                "dsus": [next((u.get("dsu_name") for u in prop["units"] if u["label"] == lb), lb) for lb in G["units"]],
                "n_wells": len(api10s),
                "reserve_category": "UPSIDE" if roles == {"upside"} else "PUD",
                "preview_oil": {k: oil.get(k) for k in ("qi", "Di", "b", "Df", "eur_per_unit")},
                "issues": issues,
                "save_body": {
                    "name": name,
                    "notes": f"deal-intake handoff: {run_dir.as_posix()} (config v{sig.get('config_version')}), "
                             f"bench {B['bench']}, units {', '.join(G['units'])}",
                    "filter_spec": {"source": "deal-intake", "run_dir": run_dir.as_posix(),
                                    "config_version": sig.get("config_version"), "bench": B["bench"],
                                    "units": G["units"], "cohort_rule": G.get("order_reason")},
                    "included_api10s": api10s,
                    "normalization_basis": "per_lateral_ft",
                    "alignment_method": "peak_ramp",
                    "provenance": {
                        "selection_events": [{"kind": "click_add", "at": datetime.now(UTC).isoformat(),
                                              "api10s": api10s,
                                              "filters": {"source": "deal-intake cohort", "group": G["name"]}}],
                        "formations": [B["bench"]],
                    },
                },
                "zone": {"zone_name": name, "reserve_category": "UPSIDE" if roles == {"upside"} else "PUD",
                         "benches": [B["bench"]], "scenario_scope": [scenario_key(u) for u in G["units"]]},
            })
    return out


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

def existing_scenarios(conn: Any, keys: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Read-only: what narvi already holds under the planned ids."""
    if not keys:
        return {}
    rows = conn.execute(
        "SELECT deal_id, scenario_id, name, updated_at, "
        "(SELECT count(*) FROM jsonb_object_keys(COALESCE(summary->'category_overrides', '{}'::jsonb))) "
        "AS n_overrides "
        "FROM narvi.scenario WHERE deal_id = ANY(%s)", ([k["deal_id"] for k in keys],)).fetchall()
    return {(r[0], r[1]): {"name": r[2], "updated_at": r[3].isoformat() if r[3] else None, "n_overrides": r[4]}
            for r in rows}


def plan(run_dir: Path, narvi: Any, cfg: Any, *, deal: str, codename: str, conn: Any = None) -> dict[str, Any]:
    sig, prop = load_run(run_dir)
    setback = float(cfg["planned_lateral"]["setback_ft"])
    ub = unit_benches(sig)
    issues: list[str] = []
    uploads: dict[str, dict[str, Any]] = {}
    deal_file = Path(prop.get("deal_file") or "")
    if deal_file.is_file():
        uploads = {pc["label"]: pc for pc in narvi.upload_parcels(deal_file)}   # stateless parse
    else:
        issues.append(f"deal file {deal_file} not found — narvi parcel cards would lose the land tracts")
    units = [plan_unit(narvi, u, ub[u["label"]], setback, uploads.get(u["label"]))
             for u in prop["units"] if u["label"] in ub]
    for u in units:
        if uploads and u["label"] not in uploads:
            issues.append(f"{u['label']}: not in the deal file's parcels (relabelled since propose?)")
    curves = plan_curves(sig, prop, run_dir)
    keys = [scenario_key(u["label"]) for u in units]
    have = existing_scenarios(conn, keys) if conn is not None else None
    for u in units:
        k = (u["body"]["deal_id"], u["body"]["scenario_id"])
        u["existing"] = None if have is None else have.get(k)
    covered = {(lb, c["bench"]) for c in curves for lb in c["units"]}
    issues += [f"{u['label']} {b}: located in the dossier but no curve applies to it"
              for u in units for b in u["expected"] if (u["label"], b) not in covered]
    names = [c["name"] for c in curves]
    issues += [f"duplicate curve name {n}" for n in sorted({n for n in names if names.count(n) > 1})]
    issues += [f"curve name {n!r} is over 26 characters (Blue Ox zone limit)" for n in names if len(n) > 26]
    blocked = issues + [f"{u['label']}: {i}" for u in units for i in u["issues"]] \
        + [f"{c['name']}: {i}" for c in curves for i in c["issues"]]
    return {
        "deal": deal, "codename": codename, "run_dir": run_dir.as_posix(),
        "config_version": sig.get("config_version"), "planned_at": datetime.now(UTC).isoformat(),
        "status": "BLOCKED" if blocked else "READY", "blocked": blocked,
        "units": units, "curves": curves,
        "blueox_zones": [c["zone"] for c in curves],
        "narvi_selections": keys,
        "narvi_checked": have is not None,
    }
