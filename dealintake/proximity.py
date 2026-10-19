"""PDP-proximity cull — planned sticks inside an existing producer's depletion envelope.

Michael 2026-10-19 (Chevron Farmouts, "from my head" — every number PROVISIONAL,
config `pdp_proximity`, v14): no planned well within ~300 ft VERTICAL and ~800 ft
HORIZONTAL of an existing producer whose lateral runs alongside it by > 30 %.
He had dropped those rows/benches by hand (15-22 west rows 122 / 782 ft off WCB_1
PDP 4238935214; every bench but BS2_C on 6-7 and 49-50-5).

Per (planned stick, producer), in the unit's local frame, along = the plan azimuth:
  overlap  share of OUR stick's along-axis length that the producer spans (rule-9
           co-extent applied pairwise; denominator = our stick — the question is
           how much of our lateral drains depleted rock)
  dh_ft    MEDIAN perpendicular distance from our stick to the producer over that
           shared length (not the midpoint offset — a skewed producer reads right)
  dv_ft    |producer tvd_ft - our landing TVD|
Any bench counts, the producer's own included (same bench = the spacing case).

  cull     overlap >= overlap_min_frac AND dv <= vertical_ft AND dh <= horizontal_ft
  near     inside near_miss_ratio x either distance, not culled — FLAG only
  permit   a would-cull producer at a round-100 TVD (a permit depth, workspace rule
           10): FLAG, never culls unless permit_tvd_culls

Not the sql/50 660-ft vertical-parent gate: that one TAGS historical analogs
(midpoint offset, 1,000-ft band, other-bench parents, shielding) and never
removes anything; this one removes OUR rows. It reads none of sql/50's constants.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

from shapely import wkt as shp_wkt
from shapely.geometry.base import BaseGeometry

from dealintake.geo import FT_PER_M, LocalFrame, fold_azimuth

N_SAMPLES = 21          # points along our stick for the median gap


def settings(raw: dict[str, Any]) -> dict[str, Any] | None:
    """The config section, or None when absent / disabled."""
    sec = raw.get("pdp_proximity") or {}
    return sec if sec.get("enabled") else None


def rule_text(cfg: dict[str, Any]) -> str:
    return (f"<= {float(cfg['vertical_ft']):,.0f} ft vt / <= {float(cfg['horizontal_ft']):,.0f} ft hz / "
            f">= {float(cfg['overlap_min_frac']):.0%} alongside")


def hit_text(h: dict[str, Any]) -> str:
    return (f"{h['api10']} {h['bench']} {h['dh_ft']:,.0f} ft hz / {h['dv_ft']:,.0f} ft vt / {h['overlap']:.0%}"
            + (" (permit TVD)" if h.get("permit") else ""))


class ProximityRule:
    """One unit's producers, projected once; `check` tests one planned stick."""

    def __init__(self, unit: BaseGeometry, azimuth_deg: float, producers: list[dict[str, Any]],
                 cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.v_ft = float(cfg["vertical_ft"])
        self.h_ft = float(cfg["horizontal_ft"])
        self.min_frac = float(cfg["overlap_min_frac"])
        self.ratio = float(cfg.get("near_miss_ratio", 1.0))
        self.permit_culls = bool(cfg.get("permit_tvd_culls", False))
        self.rule = rule_text(cfg)
        self._loc = LocalFrame.around(unit).projector()
        a = math.radians(fold_azimuth(azimuth_deg))
        self._ax, self._ay = math.sin(a), math.cos(a)
        self.producers: list[tuple[dict[str, Any], BaseGeometry, tuple[float, float]]] = []
        for w in producers:
            if w.get("tvd_ft") is None or not w.get("wkt"):
                continue
            g = self._loc(shp_wkt.loads(w["wkt"]))
            if g.is_empty or g.length == 0:
                continue
            self.producers.append((w, g, self._span(g)))

    @classmethod
    def build(cls, unit: BaseGeometry, azimuth_deg: float, producers: list[dict[str, Any]],
              raw_cfg: dict[str, Any]) -> ProximityRule | None:
        cfg = settings(raw_cfg)
        return cls(unit, azimuth_deg, producers, cfg) if cfg else None

    def _along(self, x: float, y: float) -> float:
        return (x * self._ax + y * self._ay) * FT_PER_M

    def _span(self, g: BaseGeometry) -> tuple[float, float]:
        parts = getattr(g, "geoms", [g])
        vals = [self._along(x, y) for p in parts for x, y in p.coords]
        return min(vals), max(vals)

    def pair(self, stick_local: BaseGeometry, span: tuple[float, float],
             w_local: BaseGeometry, w_span: tuple[float, float]) -> tuple[float, float | None]:
        """(overlap fraction of OUR stick, median gap ft over the shared length)."""
        lo, hi = max(span[0], w_span[0]), min(span[1], w_span[1])
        length = span[1] - span[0]
        if hi <= lo or length <= 0:
            return 0.0, None
        pts = [stick_local.interpolate(i / (N_SAMPLES - 1), normalized=True) for i in range(N_SAMPLES)]
        ds = [p.distance(w_local) * FT_PER_M for p in pts if lo - 1e-6 <= self._along(p.x, p.y) <= hi + 1e-6]
        return (hi - lo) / length, (statistics.median(ds) if ds else None)

    def check(self, stick: BaseGeometry, tvd_ft: float) -> dict[str, Any]:
        """{rule, cull: [hit], near: [hit], permit: [hit]} — each list nearest first."""
        out: dict[str, Any] = {"rule": self.rule, "cull": [], "near": [], "permit": []}
        p = self._loc(stick)
        span = self._span(p)
        for w, g, w_span in self.producers:
            dv = abs(float(w["tvd_ft"]) - float(tvd_ft))
            if dv > self.v_ft * self.ratio:
                continue
            frac, dh = self.pair(p, span, g, w_span)
            if frac < self.min_frac or dh is None or dh > self.h_ft * self.ratio:
                continue
            permit = float(w["tvd_ft"]) % 100 == 0
            fp = w.get("first_production_date")
            h = {"api10": str(w["api10"]), "bench": w.get("bench") or "(unmapped)", "dv_ft": round(dv),
                 "dh_ft": round(dh), "overlap": round(frac, 2), "permit": permit,
                 "first_prod_year": int(str(fp)[:4]) if fp else None}
            h["text"] = hit_text(h)
            if dv <= self.v_ft and dh <= self.h_ft:
                out["permit" if permit and not self.permit_culls else "cull"].append(h)
            else:
                out["near"].append(h)
        for k in ("cull", "near", "permit"):
            out[k].sort(key=lambda h: (h["dh_ft"], h["dv_ft"]))
        return out


def summarize(rows: list[dict[str, Any]], kept: list[dict[str, Any]], *, enabled: bool) -> dict[str, Any] | None:
    """Per (unit x bench): what the rule did to these rows. `enabled` False =
    the rule was overridden (reviewer `pdp_proximity: false`) or is flag-only
    (Novi-sourced bench): the would-cull rows are listed, nothing was removed."""
    checked = [r for r in rows if r.get("proximity") is not None]
    if not checked:
        return None
    hit = [r for r in checked if r["proximity"]["cull"]]
    kept_ids = {id(r) for r in kept}

    def one(r: dict[str, Any], key: str) -> dict[str, Any]:
        return {"offset_ft": r["offset_ft"], **{k: v for k, v in r["proximity"][key][0].items() if k != "text"},
                "text": r["proximity"][key][0]["text"]}

    return {
        "rule": checked[0]["proximity"]["rule"], "enabled": enabled, "n_rows": len(checked),
        "n_culled": len(hit) if enabled else 0,
        "culled": [one(r, "cull") for r in hit] if enabled else [],
        "would_cull": [] if enabled else [one(r, "cull") for r in hit],
        "near": [one(r, "near") for r in checked if id(r) in kept_ids and r["proximity"]["near"] and not r["proximity"]["cull"]],
        "permit": [one(r, "permit") for r in checked if id(r) in kept_ids and r["proximity"]["permit"]],
    }


def flags(where: str, s: dict[str, Any] | None, *, source: str = "generate",
          manual_drops: list[str] | None = None) -> list[str]:
    """Reviewer flags for one unit x bench summary (culls themselves go to the
    decision log; these are the things to LOOK at)."""
    if not s:
        return []
    out = []
    if source == "novi" and s["would_cull"]:
        out.append(f"PDP proximity: {where} keeps Novi BASE_CASE locations, {len(s['would_cull'])} of them inside the "
                   f"envelope ({s['rule']}; nearest {s['would_cull'][0]['text']}) — flag only, Novi sticks are never culled")
    elif s["would_cull"]:
        out.append(f"PDP proximity OVERRIDDEN (pdp_proximity: false): {where} keeps {len(s['would_cull'])} row(s) the rule "
                   f"would cull ({s['rule']}; nearest {s['would_cull'][0]['text']})")
    if s["enabled"] and s["n_culled"] and s["n_culled"] == s["n_rows"]:
        out.append(f"PDP proximity: {where} — every one of {s['n_rows']} rows culled ({s['rule']}); no locations left "
                   "— drop the bench, or set pdp_proximity: false to keep it")
    if s["near"]:
        out.append(f"PDP proximity near-miss: {where} — {len(s['near'])} kept row(s) within the flag band "
                   f"(nearest {s['near'][0]['text']}); reviewer looks")
    if s["permit"]:
        out.append(f"PDP proximity: {where} — {len(s['permit'])} row(s) inside the envelope of a producer at a round-100 "
                   f"(permit) TVD, NOT culled ({s['permit'][0]['text']}); check that producer's real landing")
    if s["enabled"] and s["n_culled"] and manual_drops:
        out.append(f"PDP proximity: {where} — the rule culled {s['n_culled']} row(s) AND the reviewer's {', '.join(manual_drops)} "
                   "removed more; if those drops were for the same producers, remove them from benches.yaml (double drop)")
    return out
