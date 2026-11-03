"""BOX step 23 — the production record runs (pure, no DB). Plan: docs/box/step23-2026-11-03/RECORD_PLAN.md.

One record per basin (D130, sql/70), both priced by Steven once (D144):

  Midland   a base run built with the step-21 method (revision 8 at 5ceadc2, the D149 treatments as amended by the D151 tiers;
            scripts/box_record23_midland), then the record DERIVED from it (D116 pattern) with D150's continuous proximity
            factor: oil x level x F_R3 on every forecast stick (single-parent and unexposed sticks included), WCA_1 oil x its D102
            haircut, the 21a pattern precedent + the 400-ft floor + D114 deciding which sticks get no forecast.
  Delaware  DERIVED from the D117 record (run 25, D153): its table haircut divided out of the oil rows (prox_factor), then
            level 1.046 x F_R2 on every forecast stick; D114 bench pair + package tier unchanged.

The Midland block `method_block()` is what the record run stores (forecast_run.disclosure -> "method_23"); `check_method` compares
it field by field with box/prospective21.DEFINITION["method"], the spec the 21d scorer checks the Midland record against before
its one read (~2028). tests/test_box_record23.py runs that comparison, so the record-run check passes by construction.

Outcome vocabulary under D150 (sql/71; D113's 'as_is' / 'haircut' words describe the retired table):
  level_unexposed       no counting parent: factor = the basin level
  factor_single_parent  one counting parent: factor = level x F
  factor_multi_parent   two or more: factor = level x F_rule (Delaware R2, Midland R3)
  no_forecast_*         precedent / package (D114), pattern / spacing (21a revisions 1 and 5, Midland): coverage
                        not_covered_no_precedent, no stream rows (as at D116)
The precedent gates read the INCUMBENT table factor for D114's package tier (<= 0.80), as step 24 measured "incumbent gates kept"
(GATE_24A G4); the continuous factor only scales oil.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import basin as bsn
from box import prospective21 as p21
from box import prox_cont as pc
from box import step21 as st21

ROOT = Path(__file__).resolve().parents[1]
DOCS = Path("docs") / "box" / "step23-2026-11-03"
GATE_21B = Path("docs") / "box" / "step21b-2026-11-01" / "GATE_21B.json"
GATE_21C = Path("docs") / "box" / "step21c-2026-11-02" / "GATE_21C.json"
GATE_24A = Path("docs") / "box" / "prox-continuous-2026-11-02" / "GATE_24A.json"
MIDLAND_TABLE = Path("docs") / "box" / "step21b-2026-11-01" / "prox_factor_table.csv"  # the incumbent (D149 (3)): package trigger only
DELAWARE_SOURCE_RUN = 25  # the D117 record (D153)

LEVEL_UNEXPOSED, SINGLE, MULTI = "level_unexposed", "factor_single_parent", "factor_multi_parent"
FORECAST_OUTCOMES = (LEVEL_UNEXPOSED, SINGLE, MULTI)
NO_FORECAST = ("no_forecast_precedent", "no_forecast_package", "no_forecast_pattern", "no_forecast_spacing")
OUTCOMES = (*FORECAST_OUTCOMES, *NO_FORECAST)
REL_TOL = 1e-9


def _json(path: Path) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def gate_21b() -> dict[str, Any]:
    return _json(GATE_21B)


def gate_21c() -> dict[str, Any]:
    return _json(GATE_21C)


def gate_24a() -> dict[str, Any]:
    return _json(GATE_24A)


# ----------------------------------------------------------------------------
# the Midland groups as they ship (D149 treatments, D151 tiers, D151 (2) haircut)
# ----------------------------------------------------------------------------


def midland_groups() -> dict[str, dict[str, Any]]:
    """group -> bench, record extent, tier, shipped oil / gas treatment, haircut streams. Built from the gate files, never typed."""
    t = gate_21c()["tier"]
    out: dict[str, dict[str, Any]] = {}
    for g, (bench, extent, _src) in st21.GROUPS.items():
        r = t[g]
        hc = ["oil"] if g == "MID_WCA_1" else []
        out[g] = {"bench": bench, "extent_id": extent, "tier": r["oil_gas"], "oil": r["ships"]["oil"], "gas": r["ships"]["gas"],
                  "haircut_streams": hc, "water_tier": "provisional"}
    return out


def d102_as_delivered() -> dict[int, float]:
    """WCA_1 oil, D151 (2): the D102 table computed at gate 21c on the 21 table treatment (cum-12 / 24 / 36 / 48)."""
    f = gate_21c()["haircut_step23"]["MID_WCA_1"]["d102_factor"]
    return {int(k): float(v) for k, v in f.items()}


# ----------------------------------------------------------------------------
# D150 curves
# ----------------------------------------------------------------------------


def d150(basin: str) -> tuple[pc.Model, str]:
    """(model, rule) of record for `basin` (GATE_24A.json curves): factor = level x F_rule."""
    c = gate_24a()["curves"][bsn.get(basin).name]
    m = pc.Model(curve=pc.Curve(c["f_min"], c["d50_ft"], c["k"]), a_below=c["a_below"], a_above=c["a_above"], level=c["level"])
    return m, str(c["rule"])


def stick_factors(pud_links: pd.DataFrame, basin: str, ids: list[str] | None = None) -> pd.DataFrame:
    """Per stick (child id): n D150 counting parents, F_rule, factor = level x F_rule. `pud_links` must already carry the basin's
    stick-side parent rule in `rel` (Delaware D115: >= 12 months at the run's data date; Midland 21a revision 4: every existing
    producer); box/prox_cont.parents(drilled=False) then keeps rel 'parent', >= 30 % alongside, dv <= 1,000 / dh <= 2,640 ft.
    `ids` adds sticks with no link at all (they carry the level)."""
    model, rule = d150(basin)
    st = pc.sticks(pud_links, model, rule).set_index("stick")
    if ids is not None:
        st = st.reindex(pd.Index([str(x) for x in ids], name="stick"))
        st["n_parents"] = st["n_parents"].fillna(0).astype(int)
        st["F_rule"] = st["F_rule"].fillna(1.0)
        st["level"] = model.level
        st["factor"] = model.level * st["F_rule"].to_numpy(float)
        st["pattern"] = st["pattern"].fillna("none")
        st["permit_parents"] = st["permit_parents"].fillna(0).astype(int)
    return st


def outcomes(incumbent: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    """The step-23 outcome per stick: the incumbent no-forecast outcomes stand (D114 / pattern / spacing, unchanged by D150);
    every other stick is forecast at the D150 factor, labelled by its D150 counting-parent count. `incumbent` indexed by stick id
    with an `outcome` column (box/prox_pud or box/step21_prox vocabulary); `factors` = stick_factors(...) on the same ids."""
    inc = incumbent["outcome"].astype(str)
    f = factors.reindex(inc.index)
    if f["factor"].isna().any():
        raise ValueError(f"{int(f['factor'].isna().sum())} sticks without a D150 factor row")
    n = f["n_parents"].astype(int).to_numpy()
    lab = np.where(n == 0, LEVEL_UNEXPOSED, np.where(n == 1, SINGLE, MULTI))
    no = inc.isin(NO_FORECAST).to_numpy()
    out = pd.DataFrame({"outcome": np.where(no, inc.to_numpy(), lab), "factor": f["factor"].to_numpy(float), "F_rule": f["F_rule"].to_numpy(float),
                        "n_parents_d150": n, "pattern_d150": f["pattern"].to_numpy(), "incumbent_outcome": inc.to_numpy()}, index=inc.index)
    out["keep"] = ~no
    bad = sorted(set(out["outcome"]) - set(OUTCOMES))
    if bad:
        raise ValueError(f"unknown outcomes {bad}")
    return out


def rescale(old_factor: np.ndarray, new_factor: np.ndarray) -> np.ndarray:
    """The multiplier a derived run applies to the source's oil rows: new / old (the source's prox_factor divided out)."""
    o, n = np.asarray(old_factor, float), np.asarray(new_factor, float)
    if (o <= 0).any() or (n <= 0).any():
        raise ValueError("factors must be > 0")
    return n / o


# ----------------------------------------------------------------------------
# the Midland method block the record run stores, checked against the 21d definition
# ----------------------------------------------------------------------------


def method_block(haircut: Mapping[int, float] | None = None, haircut_basis: str = "as_delivered_21c") -> dict[str, Any]:
    """forecast_run.disclosure["method_23"] of the Midland record run: what 21d's record_run_check reads. Every value comes from
    the frozen module or gate file that owns it (never copied from prospective21, so the comparison is a real one)."""
    h = d102_as_delivered() if haircut is None else {int(k): float(v) for k, v in haircut.items()}
    m, rule = d150(bsn.MIDLAND)
    c = gate_24a()
    g = midland_groups()
    return {
        "basin": bsn.MIDLAND,
        "base": {"definition": "box/step21.DEFINITION revision 8", "digest": st21.DIGEST, "frozen_sha": gate_21b()["frozen_sha"],
                 "selection": st21.SELECTION, "translate_range_ft": [st21.RULES.translate_range[0], "inf" if math.isinf(st21.RULES.translate_range[1])
                                                                     else st21.RULES.translate_range[1]],
                 "df_terminal": bsn.df_terminal(bsn.MIDLAND), "volumes": "uptime_free (D63)"},
        "proximity": {"decision": "D150", "module": "box/prox_cont.py", "digest": pc.DIGEST, "frozen_sha": c["frozen_sha"],
                      "curve": {"rule": rule, "f_min": m.curve.f_min, "d50_ft": m.curve.d50, "k": m.curve.k, "a_below": m.a_below,
                                "a_above": m.a_above, "level": m.level},
                      "streams": ["oil"], "configuration": "stick side at the build's data date: every existing producer (21a revision 4)",
                      "precedent": "D114 (tag-free key, 21b table factor for the package tier) + 21a pattern precedent + 400-ft floor"},
        "haircut": {"MID_WCA_1": {"stream": "oil", "factor": {str(k): h[k] for k in sorted(h)}, "basis": haircut_basis},
                    "others": "none"},
        "tiers": {k: v["tier"] for k, v in g.items()},
        "extents": {k: v["extent_id"] for k, v in g.items()},
        "treatments": {k: {"oil": v["oil"], "gas": v["gas"]} for k, v in g.items()},
        "streams_shipped": {"oil": "mid_r2 x D150 factor (x WCA_1 haircut)", "gas": "mid_r2 (D150 is oil only)",
                            "water": "D107 ratio on raw mid_r2 oil (D108)"},
        "conflict_sticks": "not drillable (D145): coverage not_covered_conflict, no forecast",
    }


def check_method(block: Mapping[str, Any], definition: Mapping[str, Any] | None = None) -> list[str]:
    """Mismatches between a stored Midland method block and box/prospective21.DEFINITION (empty = the record run is the method 21d
    tests). Checks exactly what DEFINITION['method']['record_run_check'] names (base digest, D150 digest + curve, haircut table) plus
    the frozen SHAs, the cohort's groups / extents / tiers at freeze, and the streams shipped."""
    d = p21.DEFINITION if definition is None else definition
    m = d["method"]
    bad: list[str] = []

    def eq(what: str, got: Any, want: Any) -> None:
        if got != want:
            bad.append(f"{what}: record {got!r} != 21d {want!r}")

    if block.get("basin") != d["basin"]:
        bad.append(f"basin: record {block.get('basin')!r} != 21d {d['basin']!r}")
    eq("base.digest", block["base"]["digest"], m["base"]["digest"])
    eq("base.frozen_sha", block["base"]["frozen_sha"], m["base"]["frozen_sha"])
    eq("proximity.digest", block["proximity"]["digest"], m["proximity"]["digest"])
    eq("proximity.frozen_sha", block["proximity"]["frozen_sha"], m["proximity"]["frozen_sha"])
    for k, v in m["proximity"]["curve"].items():
        eq(f"proximity.curve.{k}", block["proximity"]["curve"].get(k), v)
    eq("proximity.streams", list(block["proximity"]["streams"]), ["oil"])
    hk = m["haircut"]
    if set(block["haircut"]) != set(hk):
        bad.append(f"haircut groups: record {sorted(block['haircut'])} != 21d {sorted(hk)}")
    w = block["haircut"].get("MID_WCA_1", {})
    eq("haircut.MID_WCA_1.stream", w.get("stream"), hk["MID_WCA_1"]["stream"])
    f = {str(k): v for k, v in (w.get("factor") or {}).items()}
    if sorted(f) != sorted(hk["MID_WCA_1"]["at_gate_21c"]):
        bad.append(f"haircut.MID_WCA_1 horizons {sorted(f)} != 21d {sorted(hk['MID_WCA_1']['at_gate_21c'])}")
    elif not all(isinstance(x, float) and 0.5 < x < 1.5 for x in f.values()):
        bad.append(f"haircut.MID_WCA_1 factors out of range {f}")
    eq("haircut.others", block["haircut"].get("others"), "none" if hk["others"].startswith("none") else hk["others"])
    groups = d["cohort"]["groups"]
    eq("groups", sorted(block["tiers"]), sorted(groups))
    for g, x in groups.items():
        eq(f"tier.{g}", block["tiers"].get(g), x["tier_at_freeze"])
        eq(f"extent.{g}", block["extents"].get(g), x["extent_id"])
    eq("streams_shipped", dict(block["streams_shipped"]), dict(m["streams_shipped"]))
    return bad


def block_digest(block: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(block, sort_keys=True, separators=(",", ":"), default=float).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------
# expectations (identities by identity, never remembered constants)
# ----------------------------------------------------------------------------


def expected_oil(src: pd.DataFrame, oc: pd.DataFrame) -> pd.DataFrame:
    """Per bench: forecast count and oil EUR of the derived run = sum over KEPT source sticks of eur x new / old. `src` = the source
    run's forecast rows (location key, formation_blueox, oil eur, prox_factor); `oc` = outcomes(...) on the same key."""
    j = src.join(oc[["keep", "factor"]], how="left")
    if j["keep"].isna().any():
        raise ValueError(f"{int(j['keep'].isna().sum())} source sticks without an outcome")
    j = j[j["keep"].astype(bool)]
    j["oil_new"] = j["oil_eur"].to_numpy(float) * rescale(j["prox_factor"].to_numpy(float), j["factor"].to_numpy(float))
    return j.groupby("formation_blueox").agg(n=("oil_new", "size"), oil_src=("oil_eur", "sum"), oil_new=("oil_new", "sum"))
