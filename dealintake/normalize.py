"""PROTOTYPE (config v17, REPORT-ONLY): BOX's analog normalization read on a deal-intake bench.

Michael 2026-11-04 (Eggs Tyrone): "what if we applied our proximity work to the narvi scenarios" + "BOX moved from lateral
bands to Cui". Nothing here changes the curve, the cohort or the handoff — it writes `B["normalize"]` for the dossier.

Three pieces, all BOX's own definitions (no constant copied):
  * STICK F — each generated row is a child whose first production is the data date; every existing producer >= 12 months
    on at that date counts (BOX D115 stick side: no shielding exemption, permit TVDs counted + flagged), links by
    box/prox_pud.pud_links (BOX pair metric, UTM-13N feet), factor = level x F_rule of record (D150, box/record23.d150).
  * ANALOG F — each cohort well against the producers >= 12 months on at ITS first production (drilled side,
    box/prox_cont.parents(drilled=True): permit TVDs out), same model and rule.
  * CUI — Cui & Cross lateral efficiency (D50, box/lateral.relative): E(unit lateral) / mean E(cohort member laterals).

Readings per unit (the level cancels in the ratio; a TC is ~ the mean of its members):
  A  the curve of record:      TC_A x (stick factor / mean analog factor of cohort A) x Cui_A
  B  normalized nearest pool:  TC_B x (stick factor / mean analog factor of cohort B) x Cui_B
     cohort B = the bench's pool rule WITHOUT its scenario_classes selection, analogs 5,000-15,000 ft (BOX's window,
     Cui-translated instead of a band), nearest `cohort_size` — scenario is normalized, not filtered.
  B per-well check: median over cohort B of EUR_i/kft x (stick factor / factor_i) x E(L_unit) / E(L_i).
"""

from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

import numpy as np
import pandas as pd
import shapely

from box import edge_gap as eg
from box import exclusions
from box import lateral as lat
from box import prox_cont as pc
from box import prox_pud as pp
from box import prox_study as ps
from box import record23 as rc
from dealintake import warehouse as wh

_UNIVERSE_SQL = f"""
SELECT w.api10, COALESCE(we.formation_blueox, '(unmapped)') AS bench, w.first_production_date AS fp, w.tvd_ft,
       extensions.ST_AsText(w.wellstick_geom) AS wkt
FROM curated.wells w
LEFT JOIN curated.wells_enriched we ON we.api10 = w.api10
WHERE {wh._HZ}
  AND w.first_production_date IS NOT NULL AND w.wellstick_geom IS NOT NULL AND w.tvd_ft IS NOT NULL
  AND extensions.ST_DWithin(w.wellstick_geom::extensions.geography,
                            extensions.ST_GeomFromText(%(u)s, 4326)::extensions.geography, %(r)s)
"""


def universe(conn: Any, area: Any, radius_mi: float) -> pd.DataFrame:
    """Every producing horizontal with a stick and a TVD within `radius_mi` of `area`, in UTM-13N feet, minus BOX's
    exclusion list — the parents a stick or an analog can have, any bench."""
    rows = wh._rows(conn, _UNIVERSE_SQL, {"u": area.wkt, "r": radius_mi * wh.M_PER_MI})
    u = pd.DataFrame(rows, columns=["api10", "bench", "fp", "tvd_ft", "wkt"]).drop_duplicates("api10").reset_index(drop=True)
    if u.empty:
        return u.assign(geom=[])
    u["tvd_ft"] = pd.to_numeric(u["tvd_ft"], errors="coerce")
    u["geom"] = eg.to_ft([shapely.from_wkt(w) for w in u["wkt"]])
    u = u[[g.length > 0 for g in u["geom"]]].drop(columns="wkt")
    u, _ = exclusions.drop(u, rc.ROOT / exclusions.PATH)
    return u


class _Index:
    def __init__(self, u: pd.DataFrame) -> None:
        self.recs = u[["api10", "bench", "fp", "tvd_ft", "geom"]].to_dict("records")
        self.tree = shapely.STRtree([r["geom"] for r in self.recs])
        self.pos = {r["api10"]: i for i, r in enumerate(self.recs)}

    def near(self, geom: Any) -> list[dict[str, Any]]:
        return [self.recs[j] for j in self.tree.query(geom, predicate="dwithin", distance=ps.PAIR_GATE_FT)]


def stick_factors(idx: _Index, sticks: list[dict[str, Any]], bench: str, as_of: dt.date, basin: str) -> pd.DataFrame:
    """sticks = [{id, wkt (lon/lat), tvd_ft}] -> per stick: n_parents, F_rule, factor (level x F_rule), pattern,
    permit_parents. Producers >= 12 months on at `as_of` count (BOX D115)."""
    links: list[ps.Link] = []
    ids = []
    for s in sticks:
        g = eg.to_ft([shapely.from_wkt(s["wkt"])])[0]
        child = {"api10": str(s["id"]), "bench": bench, "fp": as_of, "tvd_ft": float(s["tvd_ft"]), "geom": g}
        ids.append(str(s["id"]))
        links += pp.pud_links(child, idx.near(g))
    lf = pp.links_frame(links)
    if lf.empty:
        model, _ = rc.d150(basin)
        return pd.DataFrame({"n_parents": 0, "F_rule": 1.0, "level": model.level, "factor": model.level,
                             "pattern": "none", "permit_parents": 0}, index=pd.Index(ids, name="stick"))
    return rc.stick_factors(lf, basin, ids)


def analog_factors(idx: _Index, api10s: list[str], basin: str) -> pd.DataFrame:
    """Per analog: n_parents, F_rule, factor = level x F_rule on the DRILLED side (parents >= 12 months on at the analog's
    own first production, permit TVDs out). An analog missing from the universe (no stick / TVD) gets NaN."""
    model, rule = rc.d150(basin)
    links: list[ps.Link] = []
    for a in api10s:
        i = idx.pos.get(a)
        if i is None:
            continue
        me = idx.recs[i]
        links += ps.links_for_child(me, (r for r in idx.near(me["geom"]) if r["api10"] != a))
    out = pd.DataFrame(index=pd.Index(api10s, name="api10"))
    lf = pp.links_frame(links)
    par = pc.parents(lf, drilled=True) if not lf.empty else lf
    if par.empty:
        cf = pd.DataFrame(columns=["n_parents", f"F_{rule}", "pattern"])
    else:
        cf = pc.child_factors(par, model, rules=(rule,)).set_index("child")
    cf = cf.reindex(out.index)
    known = out.index.isin(list(idx.pos))
    out["n_parents"] = np.where(known, cf["n_parents"].fillna(0), np.nan)
    out["F_rule"] = np.where(known, cf[f"F_{rule}"].astype(float).fillna(1.0), np.nan)
    out["factor"] = model.level * out["F_rule"]
    out["pattern"] = np.where(known, cf["pattern"].fillna("none"), None)
    return out


def _mean(xs: list[float]) -> float | None:
    xs = [float(x) for x in xs if x is not None and np.isfinite(x)]
    return float(np.mean(xs)) if xs else None


def _median(xs: list[float]) -> float | None:
    xs = [float(x) for x in xs if x is not None and np.isfinite(x)]
    return float(statistics.median(xs)) if xs else None


def reading(tc_eur_kft: float | None, stick_factor: float | None, analog_factors_: list[float], unit_ll: float,
            member_ll: list[float], basin: str) -> dict[str, Any]:
    """One unit x cohort: ratio = stick factor / mean analog factor, Cui relative, implied EUR per 1,000 ft."""
    mf = _mean(analog_factors_)
    ms = [float(x) for x in member_ll if x and np.isfinite(x)]
    cui = lat.relative(unit_ll, ms, basin=basin) if ms else None
    ratio = stick_factor / mf if stick_factor is not None and mf else None
    eur = tc_eur_kft * ratio * cui if tc_eur_kft is not None and ratio is not None and cui is not None else None
    return {"mean_analog_factor": mf, "ratio": ratio, "cui": cui, "eur_per_1000ft": eur,
            "vs_tc": (eur / tc_eur_kft - 1.0) if eur is not None and tc_eur_kft else None}


def per_well(wells: list[dict[str, Any]], fac: pd.DataFrame, stick_factor: float, unit_ll: float, basin: str) -> float | None:
    """Median over a cohort of EUR_i/kft x (stick factor / factor_i) x E(L_unit) / E(L_i) — the translation done well by well."""
    vals = []
    for w in wells:
        e, f, ll = w.get("anduin_oil_eur_per_1000ft"), fac["factor"].get(w["api10"]), w.get("lateral_length_ft")
        if e is None or f is None or not np.isfinite(f) or not ll:
            continue
        vals.append(e * stick_factor / f * lat.relative(unit_ll, [ll], basin=basin))
    return _median(vals)
