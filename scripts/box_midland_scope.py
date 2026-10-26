"""BOX step 18 — Midland scope + value-case evidence pack (READ ONLY; decision only, nothing stored).

    python -m scripts.box_midland_scope [--out docs/box/step18-2026-10-26] [--n-boot 200]

Per Midland bench (box/midland_scope): the plan's Phase-3 headline table re-derived live (identity check against the
numbers written into the plan), a card per bench (TVD, spacing, operator mix, vintage + D53 fold wells, laterals,
allocation wells, water source, undrilled sticks, analog reach), the adjacent-bench pooling evidence (step-1 local
TVD separation, co-location, 5-mi-block + first-production-year contrasts with a block bootstrap — the D19 / D33
pattern), Novi 2025Q3 accuracy per bench (sql/43, the sql/38 convention), the terminal-Df EUR sensitivity on the
record run's own fits, and the record-run facts behind decision (e). Every query runs in a READ ONLY transaction.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from box import bench_qc as bq
from box import edge_gap as eg
from box import exclusions
from box import family_qc as fq
from box import midland_scope as ms
from etl.db import get_connection

OUT = Path("docs/box/step18-2026-10-26")

# The Phase-3 evidence table as written into the plan (2026-10-26, eng_db #198): bench -> (modern producers, oil bbl/kft,
# GOR12, undrilled sticks, PUD-only). The build re-derives it live and reports the differences (identity, not memory).
PLAN_TABLE: dict[str, tuple[int, int, int, int, int]] = {
    "WCA_1": (6202, 15365, 1377, 12281, 10738), "LSSH": (4915, 14714, 1312, 11707, 8103),
    "WCB_1": (4114, 14383, 2101, 9522, 7748), "WCB_2": (1711, 13932, 2008, 2096, 2010),
    "JM": (1392, 15989, 1474, 8029, 5801), "MS": (1371, 13023, 1266, 8562, 5709),
    "DEAN": (780, 16710, 1393, 1882, 1789), "WCD": (669, 13156, 2299, 8452, 6769),
    "WCC": (460, 10423, 2090, 8542, 6998), "US": (70, 11247, 1730, 3751, 986),
}

_PROD_SQL = """
SELECT w.api10, w.well_name, w.current_operator AS operator, w.county, w.formation_blueox, w.tvd_ft,
       w.lateral_length_ft, w.first_production_date, w.last_reported_month, w.cum_12m_oil_bbl, w.cum_12m_gas_mcf,
       w.cum_24m_oil_bbl, w.lateral_closer_xy_ft, w.has_production_sharing, w.novi_slant_calculated,
       COALESCE(w.midpoint_lon,
                CASE WHEN extensions.ST_GeometryType(w.wellstick_geom) = 'ST_LineString'
                     THEN extensions.ST_X(extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5)) END,
                (w.surface_lon + w.bhl_lon) / 2.0, w.surface_lon) AS mid_lon,
       COALESCE(w.midpoint_lat,
                CASE WHEN extensions.ST_GeometryType(w.wellstick_geom) = 'ST_LineString'
                     THEN extensions.ST_Y(extensions.ST_LineInterpolatePoint(w.wellstick_geom, 0.5)) END,
                (w.surface_lat + w.bhl_lat) / 2.0, w.surface_lat) AS mid_lat,
       q.water_source
FROM curated.wells_enriched w
LEFT JOIN curated.water_data_quality q ON q.api10 = w.api10
WHERE w.basin_blueox = %(basin)s AND w.is_horizontal AND w.first_production_date IS NOT NULL
"""

_STICK_SQL = """
SELECT il.stick_id, il.category, fb.formation_blueox, COALESCE(ri.status, 'not_reconciled') AS recon_status, il.ll_ft,
       extensions.ST_Length(il.wellstick_geom::extensions.geography) * 3.28084 AS stick_ft,
       extensions.ST_X(extensions.ST_LineInterpolatePoint(il.wellstick_geom, 0.5)) AS mid_lon,
       extensions.ST_Y(extensions.ST_LineInterpolatePoint(il.wellstick_geom, 0.5)) AS mid_lat
FROM curated.intel_locations il
JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
LEFT JOIN curated.reconciled_inventory ri ON ri.stick_id = il.stick_id
WHERE il.basin = %(basin)s AND il.category IN ('PUD', 'RES') AND il.wellstick_geom IS NOT NULL
"""

# sql/38 convention: direct tier, bias = mean per-ft pct error, is_latest_reported excluded
_NOVI_SQL = """
SELECT basin, formation_blueox, GROUPING(formation_blueox) AS basin_row, mop, count(*) AS n,
       avg(pct_err_oil_perft) AS oil_perft, avg(pct_err_oil) AS oil_raw, avg(pct_err_gas_perft) AS gas_perft,
       avg(ll_ratio) AS ll_ratio
FROM curated.intel_forecast_accuracy_vintage
WHERE report_version = %(v)s AND tier = 'direct' AND mop IN (6, 12) AND NOT is_latest_reported
  AND pct_err_oil_perft IS NOT NULL
GROUP BY GROUPING SETS ((basin, mop), (basin, formation_blueox, mop))
"""

_RUN_SQL = "SELECT run_id, report_version, data_through, counts FROM box.forecast_run WHERE is_record"
_PARAMS_SQL = """
SELECT s.params FROM box.pud_forecast_stream s JOIN box.forecast_run r USING (run_id)
WHERE r.is_record AND s.stream = 'oil' AND s.params ? 'qi'
ORDER BY md5(s.location_id::text) LIMIT %(n)s
"""
_SIZE_SQL = """
SELECT c.relname, c.reltuples::bigint, pg_total_relation_size(c.oid)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'box' AND c.relname IN ('pud_forecast_month', 'pud_forecast', 'pud_forecast_stream', 'location_analog')
"""


def _sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def _read(conn: Any, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, params or {})
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=cols)


def _xy(lon: Any, lat: Any) -> np.ndarray:
    """Planar EPSG:32613 ft (the BOX frame; ~0.1-0.2 % scale error on the Midland, mostly in zone 14 — accepted, plan Phase 3)."""
    x, y = eg._transformer().transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.column_stack([np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT])


def pull(conn: Any, n_params: int) -> dict[str, Any]:
    prod = _read(conn, _PROD_SQL, {"basin": ms.BASIN})
    prod, excluded = exclusions.drop(prod)
    for c in ("tvd_ft", "lateral_length_ft", "cum_12m_oil_bbl", "cum_12m_gas_mcf", "cum_24m_oil_bbl", "lateral_closer_xy_ft", "mid_lon", "mid_lat"):
        prod[c] = pd.to_numeric(prod[c], errors="coerce")
    sticks = _read(conn, _STICK_SQL, {"basin": ms.BASIN})
    for c in ("ll_ft", "stick_ft", "mid_lon", "mid_lat"):
        sticks[c] = pd.to_numeric(sticks[c], errors="coerce")
    novi = _read(conn, _NOVI_SQL, {"v": "2025Q3"})
    run = _read(conn, _RUN_SQL)
    params = _read(conn, _PARAMS_SQL, {"n": n_params})
    sizes = _read(conn, _SIZE_SQL)
    asof = _read(conn, "SELECT max(last_reported_month) AS m FROM curated.wells_enriched WHERE basin_blueox = %(basin)s", {"basin": ms.BASIN})
    return {"prod": prod, "excluded": excluded, "sticks": sticks, "novi": novi, "run": run, "params": params, "sizes": sizes,
            "asof": str(asof.iloc[0, 0])}


# ----------------------------------------------------------------------------
# Evidence
# ----------------------------------------------------------------------------

def frames(d: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dt.date]:
    p = d["prod"].copy()
    asof = dt.date.fromisoformat(d["asof"][:10])
    p["modern"] = ms.modern_mask(p["first_production_date"], p["lateral_length_ft"])
    p["oil12_kft"] = ms.per_kft(p["cum_12m_oil_bbl"], p["lateral_length_ft"])
    p["gor12"] = ms.gor(p["cum_12m_gas_mcf"], p["cum_12m_oil_bbl"])
    p["in_oil_window"] = [ms.OIL_WINDOW[0] <= f <= ms.OIL_WINDOW[1] for f in p["first_production_date"]]
    p["months_on"] = [ms.months_between(f, asof) for f in p["first_production_date"]]
    p["xy_ok"] = p["mid_lon"].notna() & p["mid_lat"].notna()
    s = d["sticks"].copy()
    s["undrilled"] = s["recon_status"].isin(["remaining_pud", "conflict", "not_reconciled"])
    s["xy_ok"] = s["mid_lon"].notna() & s["mid_lat"].notna()
    return p, s, asof


def bench_card(p: pd.DataFrame, s: pd.DataFrame, b: str) -> dict[str, Any]:
    g = p[p["formation_blueox"] == b]
    m = g[g["modern"]]
    coh = m[m["in_oil_window"]]
    recent = g[[f >= ms.RECENT_FROM for f in g["first_production_date"]]]
    water = g[[f >= ms.WATER_FROM for f in g["first_production_date"]]]
    st = s[(s["formation_blueox"] == b) & s["undrilled"]]
    cand = m[(m["months_on"] >= ms.ANALOG_MIN_MONTHS) & m["xy_ok"]]
    stx = st[st["xy_ok"]]
    reach = ms.analog_reach(_xy(stx["mid_lon"], stx["mid_lat"]), _xy(cand["mid_lon"], cand["mid_lat"])) if len(stx) else {"n_sticks": 0}
    years = list(range(2016, 2027))
    p10, p50, p90 = ms.quantiles(m["tvd_ft"])
    return {
        "bench": b, "family": "Spraberry" if b in ms.SPRABERRY else "Wolfcamp",
        "producers_all": len(g), "modern": len(m), "cohort_oil_window": int(coh["oil12_kft"].notna().sum()),
        "oil12_kft_med": float(np.nanmedian(coh["oil12_kft"])) if coh["oil12_kft"].notna().any() else math.nan,
        "gor12_med": float(np.nanmedian(coh["gor12"])) if coh["gor12"].notna().any() else math.nan,
        "tvd": {"p10": p10, "p50": p50, "p90": p90},
        "spacing": ms.spacing_stats(m["lateral_closer_xy_ft"]),
        "operators_modern": ms.operator_mix(m["operator"]),
        "operators_recent": ms.operator_mix(recent["operator"]),
        "vintage": ms.vintage_counts(m["first_production_date"], years),
        "share_modern_2023plus": float(np.mean([f >= ms.RECENT_FROM for f in m["first_production_date"]])) if len(m) else math.nan,
        "fold_wells": ms.fold_counts(list(m["first_production_date"])),
        "lateral_recent": ms.length_shares(recent["lateral_length_ft"]),
        "lateral_recent_median_ft": float(recent["lateral_length_ft"].median()) if len(recent) else math.nan,
        "recent_n": len(recent),
        "recent_gt_band_excluded": int((recent["lateral_length_ft"] > ms.LAT_BAND[1]).sum()),
        "sharing_recent": float(recent["has_production_sharing"].fillna(False).astype(bool).mean()) if len(recent) else math.nan,
        "uturn_modern": int((m["novi_slant_calculated"] == "U-Turn (Horizontal)").sum()),
        "water_2019": ms.water_split(water["water_source"]),
        "undrilled": len(st), "undrilled_pud": int((st["category"] == "PUD").sum()),
        "undrilled_reconciled_null": int((st["recon_status"] == "not_reconciled").sum()),
        "stick_length": ms.length_shares(st["ll_ft"].where(st["ll_ft"] > 0, st["stick_ft"])),
        "reach": reach,
        "measured_water_candidates": int(((water["water_source"] == "measured") & (water["months_on"] >= ms.ANALOG_MIN_MONTHS)).sum()),
    }


def water_reach(p: pd.DataFrame, s: pd.DataFrame, b: str) -> dict[str, Any]:
    """D107 sizing preview: distance from each undrilled stick to its 10th nearest MEASURED-water same-bench producer
    (first production >= 2019, >= 6 months) and the operator concentration of those producers."""
    g = p[(p["formation_blueox"] == b) & (p["water_source"] == "measured") & (p["months_on"] >= ms.ANALOG_MIN_MONTHS)
          & p["xy_ok"] & np.array([f >= ms.WATER_FROM for f in p["first_production_date"]])]
    st = s[(s["formation_blueox"] == b) & s["undrilled"] & s["xy_ok"]]
    out: dict[str, Any] = {"n_measured": len(g), "operators": ms.operator_mix(g["operator"])}
    if len(g) >= 10 and len(st):
        from scipy.spatial import cKDTree

        dd, _ = cKDTree(_xy(g["mid_lon"], g["mid_lat"])).query(_xy(st["mid_lon"], st["mid_lat"]), k=10)
        d10 = dd[:, 9] / ms.FT_PER_MI
        out |= {"k10_p50_mi": float(np.median(d10)), "k10_p90_mi": float(np.quantile(d10, 0.9)),
                "share_within": {str(r): float((d10 <= r).mean()) for r in (5, 10, 20, 30, 50)}}
    return out


def pair_evidence(p: pd.DataFrame, a: str, b: str, n_boot: int) -> dict[str, Any]:
    m = p[p["modern"] & p["xy_ok"]]
    ga, gb = m[m["formation_blueox"] == a], m[m["formation_blueox"] == b]
    xa, xb = _xy(ga["mid_lon"], ga["mid_lat"]), _xy(gb["mid_lon"], gb["mid_lat"])
    out: dict[str, Any] = {"a": a, "b": b, "n_a": len(ga), "n_b": len(gb),
                           "separation": ms.local_separation(xa, ga["tvd_ft"].to_numpy(float), xb, gb["tvd_ft"].to_numpy(float)),
                           "colocation_1mi": ms.colocation(xa, xb)}
    coh = pd.concat([ga, gb])
    coh = coh[coh["in_oil_window"].to_numpy(bool)]
    xy = _xy(coh["mid_lon"], coh["mid_lat"])
    is_b = (coh["formation_blueox"].to_numpy() == b).astype(int)
    block = fq._blocks(xy)
    year = np.array([f.year for f in coh["first_production_date"]])
    oil = coh["oil12_kft"].to_numpy(float)
    gor = coh["gor12"].to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        lo = np.where(oil > 0, np.log(oil), np.nan)
        lg = np.where(gor > 0, np.log(gor), np.nan)
    out["oil12_kft_ratio"] = fq.fe_with_ci(lo, is_b, block, year, n_boot=n_boot)
    out["gor12_ratio"] = fq.fe_with_ci(lg, is_b, block, year, n_boot=n_boot)
    return out


def novi_table(novi: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for r in novi.itertuples():
        bench = "(basin)" if int(r.basin_row) else (r.formation_blueox if isinstance(r.formation_blueox, str) else "(unmapped)")
        rows.append({"basin": r.basin, "bench": bench, "mop": int(r.mop), "n": int(r.n),
                     "oil_perft": float(r.oil_perft), "oil_raw": float(r.oil_raw),
                     "gas_perft": float(r.gas_perft) if r.gas_perft is not None else math.nan,
                     "ll_ratio": float(r.ll_ratio) if r.ll_ratio is not None else math.nan})
    return sorted(rows, key=lambda x: (x["basin"], x["bench"] != "(basin)", x["bench"], x["mop"]))


def plan_identity(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in cards:
        if c["bench"] not in PLAN_TABLE:
            continue
        pm, po, pg, pu, pp = PLAN_TABLE[c["bench"]]
        live = (c["modern"], round(c["oil12_kft_med"]), round(c["gor12_med"]), c["undrilled"], c["undrilled_pud"])
        out.append({"bench": c["bench"], "plan": [pm, po, pg, pu, pp], "live": list(live),
                    "diff": [int(lv) - int(pv) for lv, pv in zip(live, (pm, po, pg, pu, pp), strict=True)]})
    return out


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

def _png(fig: Any) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def maps_png(p: pd.DataFrame, s: pd.DataFrame) -> str:
    bg = p[p["modern"] & p["xy_ok"]]
    fig, axes = plt.subplots(2, 5, figsize=(20, 9.6), sharex=True, sharey=True)
    for ax, b in zip(axes.ravel(), ms.BENCHES, strict=True):
        g = bg[bg["formation_blueox"] == b]
        st = s[(s["formation_blueox"] == b) & s["undrilled"] & s["xy_ok"]]
        ax.scatter(bg["mid_lon"], bg["mid_lat"], s=0.3, c="#e5e7eb", rasterized=True)
        ax.scatter(st["mid_lon"], st["mid_lat"], s=0.6, c="#f59e0b", alpha=0.5, rasterized=True, label=f"undrilled sticks ({len(st):,})")
        ax.scatter(g["mid_lon"], g["mid_lat"], s=1.2, c="#1d4ed8", rasterized=True, label=f"modern producers ({len(g):,})")
        ax.set_title(b, fontsize=11)
        ax.set_aspect(1 / math.cos(math.radians(32.0)))
        ax.legend(loc="lower left", fontsize=7, markerscale=6, frameon=False)
        ax.tick_params(labelsize=7)
    fig.suptitle("Midland: modern producers (blue) vs undrilled reconciled Novi sticks (orange) per bench; grey = every modern Midland horizontal", fontsize=11)
    return _png(fig)


def oil_by_year_png(p: pd.DataFrame) -> str:
    m = p[p["modern"] & p["in_oil_window"]]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for b in ms.BENCHES:
        g = m[m["formation_blueox"] == b]
        yr = g.groupby([f.year for f in g["first_production_date"]])["oil12_kft"].agg(["median", "count"])
        yr = yr[yr["count"] >= 15]
        if len(yr):
            ax.plot(yr.index, yr["median"] / 1000.0, marker="o", ms=3, lw=1.2, ls="-" if b in ms.WOLFCAMP else "--", label=b)
    ax.set_ylabel("median 12-mo oil, bbl per ft")
    ax.set_xlabel("first-production year (years with >= 15 wells)")
    ax.legend(ncol=5, fontsize=7, frameon=False)
    ax.grid(alpha=0.3)
    return _png(fig)


def render(out: Path, sm: dict[str, Any], imgs: dict[str, str]) -> Path:
    f, e = bq._fmt, bq._esc

    def pct(v: Any, nd: int = 0) -> str:
        return f(v, nd, pct=True)

    cards = sm["cards"]
    P: list[str] = [
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>BOX step 18 — Midland scope</title><style>{bq._CSS}</style></head><body>",
        "<h1>BOX step 18 — Midland scope + value case (evidence pack, decision only)</h1>",
        (f"<div class=meta>Grain: Midland producing horizontals (one row per api10, curated.wells_enriched, formation_blueox) and reconciled Novi "
         f"sticks (one row per stick_id, curated.intel_locations × intel_formation_blueox × reconciled_inventory, Novi {e(sm['novi_vintage'])}). "
         f"<b>Modern</b> = first production ≥ 2016-01-01, lateral 5,000–15,000 ft (the r2 analog band, D121). <b>Oil / GOR</b> = medians of 12-mo "
         f"calendar-day cum per 1,000 ft / scf per bbl, modern wells first-producing 2016-01 … 2025-07. <b>Undrilled</b> = PUD + RES sticks with "
         f"reconciliation status NULL / remaining_pud / conflict (D117). Warehouse as-of {e(sm['asof'])}; built {e(sm['built_at'])} at {e(sm['git_sha'])}. "
         f"BOX exclusions applied ({sm['n_excluded']} Midland rows hit). READ ONLY — nothing written. Plan: docs/box_type_curves_plan.md PHASE 3, step 18.</div>"),
        ("<div class=toc><a href=#t1>1 headline</a><a href=#t2>2 cards</a><a href=#t3>3 laterals</a><a href=#t4>4 analog reach</a>"
         "<a href=#t5>5 pooling</a><a href=#t6>6 Novi accuracy</a><a href=#t7>7 water</a><a href=#t8>8 Df</a><a href=#t9>9 record run</a><a href=#t10>10 maps</a></div>"),
    ]
    # 1 headline + identity
    P.append("<h2 id=t1>1. Headline table (the plan's Phase-3 table, re-derived live)</h2>")
    rows = []
    for c, idn in zip(cards, sm["plan_identity"], strict=True):
        rows.append([c["bench"], c["family"], f(c["modern"]), f(c["oil12_kft_med"], 0), f(c["gor12_med"], 0), f"{f(c['undrilled'])} ({f(c['undrilled_pud'])})",
                     " / ".join(f"{d:+,}" for d in idn["diff"])])
    P.append(bq._table(["Bench", "Family", "Modern producers", "Oil bbl / 1,000 ft", "GOR12 scf/bbl", "Undrilled sticks (PUD)", "Δ vs plan table (modern / oil / GOR / sticks / PUD)"], rows))
    P.append(f"<p class=meta>Out of scope already (D2, box.bench_scope): {', '.join(ms.EMERGING_D2)}. Other Midland tags with producers, not in the plan: "
             f"{e(sm['other_tags'])}.</p>")
    # 2 cards
    P.append("<h2 id=t2>2. Bench cards — depth, spacing, operators, vintage</h2>")
    rows = []
    for c in cards:
        sp, op, opr = c["spacing"], c["operators_modern"], c["operators_recent"]
        top = "; ".join(f"{e(t['operator'])} {pct(t['share'])}" for t in op["top"])
        rows.append([c["bench"], f"{f(c['tvd']['p10'], 0)} / {f(c['tvd']['p50'], 0)} / {f(c['tvd']['p90'], 0)}",
                     f"{f(sp['median_ft'], 0)} ({f(sp['p10_ft'], 0)}–{f(sp['p90_ft'], 0)})", pct(sp["share_unbounded"]),
                     f(op["n_operators"]), top, f(op["hhi"], 0), f(opr["hhi"], 0), pct(c["share_modern_2023plus"]),
                     " ".join(f"{y % 100:02d}:{n}" for y, n in c["vintage"].items()),
                     " ".join(str(n) for n in c["fold_wells"].values())])
    P.append(bq._table(["Bench", "TVD ft P10 / P50 / P90 (modern)", "Gap to nearest same-zone lateral, ft: median (P10–P90)", "Unbounded (NULL / 2,800 sentinel)",
                        "Operators", "Top 3 (share of modern wells)", "HHI modern", "HHI 2023+", "Modern 2023+", "Modern wells by first-prod year (16 … 26)",
                        "D53 fold wells (cutoffs 2019 … 2024)"], rows))
    P.append("<p class=meta>Spacing = wells_enriched.lateral_closer_xy_ft, as of first production (rule 14); the unbounded class (NULL + exactly 2,800) is excluded from the gap "
             "quantiles. HHI on percent shares (10,000 = one operator; < 1,500 unconcentrated, > 2,500 concentrated). Fold wells = modern wells first-producing in the "
             "12 months after each D53 cutoff — WELLS, not packages: a D53 / D99 cell needs ≥ 30 packages, so these overstate judgeability (step 14 lesson); "
             "package counts are step 21a's job.</p>")
    # 3 laterals + allocation
    P.append("<h2 id=t3>3. Laterals and allocation wells (decision f; step 20 screen)</h2>")
    rows = []
    for c in cards:
        lr, sl = c["lateral_recent"], c["stick_length"]
        rows.append([c["bench"], f(c["recent_n"]), f(c["lateral_recent_median_ft"], 0), pct(lr["ge_12500"]), pct(lr["ge_15000"]), f(c["recent_gt_band_excluded"]),
                     pct(c["sharing_recent"]), f(c["uturn_modern"]), f(sl["n"]), pct(sl["ge_12500"]), pct(sl["ge_15000"]), pct(sl["ge_20000"])])
    P.append(bq._table(["Bench", "Producers 2023+ (all hz)", "Median lateral 2023+, ft", "≥ 12,500 ft", "> 15,000 ft (≥)", "2023+ wells OUTSIDE the r2 analog band (> 15,000 ft)",
                        "Production-sharing 2023+", "U-turns (modern)", "Undrilled sticks", "Sticks ≥ 12,500 ft", "≥ 15,000", "≥ 20,000"], rows))
    P.append("<p class=meta>Stick length = Novi's ll_ft (geodesic stick length where ll_ft is missing). Under the r2 selection of record (D121) a location's length never "
             "selects analogs: analogs are 5,000–15,000-ft completed laterals and the cohort is ALWAYS Cui-translated to the location (box/analog.Rules, lateral='translate'). "
             "So a long Midland PUD is not denied analogs — it is translated on the Delaware WCA Cui &amp; Cross curve, extrapolated past 12,500 ft (E(20,000 ft) ≈ "
             f"{f(sm['cui_20k'], 3)} vs 5,000 ft) — and Midland producers longer than 15,000 ft are excluded from every analog pool.</p>")
    # 4 analog reach
    P.append("<h2 id=t4>4. Analog reach from undrilled sticks (geometry proxy for the r2 search)</h2>")
    rows = []
    for c in cards:
        r = c["reach"]
        k5, k10 = r.get("k5", {}), r.get("k10", {})
        w5, w10 = k5.get("share_within", {}), k10.get("share_within", {})
        rows.append([c["bench"], f(r.get("n_sticks", 0)), f(r.get("n_candidates", 0)),
                     f"{f(k5.get('p50_mi'), 1)} / {f(k5.get('p90_mi'), 1)}", f"{f(k10.get('p50_mi'), 1)} / {f(k10.get('p90_mi'), 1)}",
                     pct(w10.get("5.0")), pct(w5.get("5.0")), pct(1 - w5["20.0"]) if "20.0" in w5 else "—", pct(1 - w10["20.0"]) if "20.0" in w10 else "—"])
    P.append(bq._table(["Bench", "Undrilled sticks", "Analog candidates (modern, ≥ 6 mo)", "5th analog, mi P50 / P90", "10th analog, mi P50 / P90",
                        "10 analogs inside 5 mi", "5 analogs inside 5 mi", "5th analog beyond 20 mi (→ no_analogs even at the r2 count floor)", "10th beyond 20 mi"], rows))
    P.append("<p class=meta>Distance = stick midpoint to producer midpoint, same formation_blueox, planar 32613 ft. Proxy only: ignores the spacing rule and the D55 strike ellipse "
             "(the real search admits fewer wells per ring), so it reads optimistic; extents (step 20) will remove most far sticks before any search runs (D1 / rule 11).</p>")
    # 5 pooling
    P.append("<h2 id=t5>5. Adjacent-bench pooling evidence (decision b; D19 / D33 pattern)</h2>")
    rows = []
    for pe in sm["pairs"]:
        sep, co, oil, gr = pe["separation"], pe["colocation_1mi"], pe["oil12_kft_ratio"], pe["gor12_ratio"]
        rows.append([f"{pe['a']} → {pe['b']}", f"{f(pe['n_a'])} / {f(pe['n_b'])}", f(sep.get("n_hoods", 0)),
                     f"{f(sep.get('median_ft'), 0)} ({f(sep.get('p10_ft'), 0)} … {f(sep.get('p90_ft'), 0)})", pct(sep.get("share_merged")), pct(sep.get("share_inverted")),
                     f"{pct(co['a_with_b'])} / {pct(co['b_with_a'])}",
                     f"{f(oil['ratio'], 3)} [{f(oil['ci90'][0], 3)}–{f(oil['ci90'][1], 3)}] ({oil['n_blocks_both']} blocks)",
                     f"{f(gr['ratio'], 3)} [{f(gr['ci90'][0], 3)}–{f(gr['ci90'][1], 3)}]"])
    P.append(bq._table(["Pair (shallow → deep)", "Modern wells a / b", "1.5-mi hoods with ≥ 3 of each", "Local TVD separation b − a, ft: median (P10 … P90)",
                        "Merged (< 100 ft)", "Inverted (b above a)", "Co-located within 1 mi: a with b / b with a",
                        "Oil12 / kft, b ÷ a, same 5-mi block + fp year [90 % CI]", "GOR12, b ÷ a [90 % CI]"], rows))
    P.append("<p class=meta>Step-1 reading (Delaware WCA_1 / WCA_2, pooled by D19): ~128 ft apart locally, merged in 36 % of neighbourhoods. Block contrasts = OLS on log values with "
             f"5-mi block + first-production-year fixed effects, blocks holding both benches only; {sm['n_boot']} block-bootstrap draws.</p>")
    # 6 Novi
    P.append("<h2 id=t6>6. Novi 2025Q3 accuracy per bench (decision a — value case)</h2>")
    rows = []
    for r in sm["novi"]:
        if r["basin"] == "midland" or r["bench"] == "(basin)":
            rows.append([r["basin"], r["bench"], r["mop"], f(r["n"]), pct(r["oil_perft"], 1), pct(r["oil_raw"], 1), pct(r["gas_perft"], 1), f(r["ll_ratio"], 2)])
    P.append(bq._table(["Basin", "Bench", "Months on", "Wells", "Oil bias per ft (convention)", "Oil bias raw volume", "Gas bias per ft", "Mean drilled ÷ Novi stick lateral"], rows))
    P.append("<p class=meta>curated.intel_forecast_accuracy_vintage (sql/43), report 2025Q3, direct tier, is_latest_reported excluded; bias = mean of (actual ÷ forecast − 1) "
             "(sql/38 convention; negative = Novi over-forecast). Per-ft is the bias of record; the raw column shows the lateral-length mismatch on top.</p>")
    # 7 water
    P.append("<h2 id=t7>7. Water source and measured-cohort reach (decision g)</h2>")
    rows = []
    for c in cards:
        w, wr = c["water_2019"], sm["water_reach"][c["bench"]]
        sw = wr.get("share_within", {})
        top = wr["operators"]["top"][:1]
        rows.append([c["bench"], f(w["n"]), pct(w["share_calculated"]), pct(w["share_measured"]), f(wr["n_measured"]),
                     f"{e(top[0]['operator'])} {pct(top[0]['share'])}" if top else "—", f(wr["operators"]["hhi"], 0),
                     f"{f(wr.get('k10_p50_mi'), 1)} / {f(wr.get('k10_p90_mi'), 1)}", pct(sw.get("10")), pct(sw.get("30")), pct(sw.get("50"))])
    P.append(bq._table(["Bench", "Hz first-prod ≥ 2019", "Calculated", "Measured", "Measured, ≥ 6 mo (D107 candidates)", "Top measured operator", "HHI measured",
                        "10th measured analog, mi P50 / P90", "10 inside 10 mi", "10 inside 30 mi", "10 inside 50 mi"], rows))
    P.append("<p class=meta>water_source = curated.water_data_quality (sql/41); the Midland is all Texas, so the D107 NM amendment never applies. D107 needs ≥ 10 measured "
             "analogs by 50 mi (else thin / calculated fallback).</p>")
    # 8 Df
    d = sm["df"]
    P.append("<h2 id=t8>8. Terminal decline Df (decision d)</h2>")
    P.append(f"<p>On {f(d['n'])} oil fits of the live record run {e(sm['record_run'])} (Delaware, sampled by md5 of location_id), swapping the terminal Df from 0.08 to 0.06 /yr "
             f"with the same qi / Di / b changes the 50-yr EUR by a median <b>{pct(d['median'] - 1, 1)}</b> (P10 {pct(d['p10'] - 1, 1)}, P90 {pct(d['p90'] - 1, 1)}). "
             "Df is the in-house Midland value (CLAUDE.md sub-basin terminal decline: Midland 0.06, otherwise 0.08); box/analog.DF_DELAWARE = 0.08 is hard-coded on every fit path.</p>")
    # 9 record run
    P.append("<h2 id=t9>9. Record-run facts (decision e)</h2>")
    P.append(bq._table(["Item", "Value"], [[k, v] for k, v in sm["record_facts"].items()]))
    # 10 maps
    P.append("<h2 id=t10>10. Maps and the oil trend</h2>")
    P.append(f"<div class=row><img src=\"data:image/png;base64,{imgs['maps']}\" style=\"max-width:1500px\"></div>")
    P.append(f"<div class=row><img src=\"data:image/png;base64,{imgs['oil_year']}\"></div>")
    P.append("<p class=meta>Gate 18 = the decision list in FINDINGS.md (same folder).</p></body></html>")
    page = out / "index.html"
    page.write_text("\n".join(P), encoding="utf-8")
    return page


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--n-boot", type=int, default=200)
    ap.add_argument("--n-params", type=int, default=3000)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        d = pull(conn, a.n_params)
    p, s, _ = frames(d)
    cards = [bench_card(p, s, b) for b in ms.BENCHES]
    pairs = [pair_evidence(p, x, y, a.n_boot) for x, y in ms.ADJACENT]
    water = {b: water_reach(p, s, b) for b in ms.BENCHES}
    from box import lateral as lat_eff

    params = [x for x in d["params"]["params"] if all(k in x for k in ("qi", "Di_nominal", "b"))]
    run = d["run"].iloc[0]
    sizes = {r.relname: (int(r.reltuples), int(r[3])) for r in d["sizes"].itertuples()}
    other = p[~p["formation_blueox"].isin([*ms.BENCHES, *ms.EMERGING_D2])].groupby(p["formation_blueox"].fillna("(null)")).size().sort_values(ascending=False)
    und = s[s["undrilled"]]
    other_st = und[~und["formation_blueox"].isin([*ms.BENCHES, *ms.EMERGING_D2])].groupby(und["formation_blueox"].fillna("(null)")).size().to_dict()
    sm: dict[str, Any] = {
        "asof": d["asof"], "built_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "git_sha": _sha(), "novi_vintage": "2026Q3 (live)",
        "n_excluded": len(d["excluded"]), "n_boot": a.n_boot, "cards": cards, "pairs": pairs, "water_reach": water,
        "plan_identity": plan_identity(cards), "novi": novi_table(d["novi"]),
        "other_tags": ", ".join(f"{k} {v:,} producers / {other_st.get(k, 0):,} undrilled sticks" for k, v in other.items()),
        "cui_20k": lat_eff.lateral_efficiency(20_000.0), "df": ms.df_eur_ratio(params, 0.06, 0.08),
        "record_run": int(run["run_id"]),
        "record_facts": {
            "Record run": f"run_id {int(run['run_id'])} (Novi {run['report_version']}, production through {run['data_through']}); the only BOX run (D123)",
            "Record coverage counts": json.dumps(run["counts"]),
            "box.pud_forecast_month (est. rows / total size)": f"{sizes.get('pud_forecast_month', (0, 0))[0]:,} / {sizes.get('pud_forecast_month', (0, 0))[1] / 1e9:.1f} GB",
            "box.location_analog (est. rows / size)": f"{sizes.get('location_analog', (0, 0))[0]:,} / {sizes.get('location_analog', (0, 0))[1] / 1e9:.1f} GB",
            "One-record index (sql/60)": "box_forecast_run_record_uq: UNIQUE (is_record) WHERE is_record — exactly one record run, no basin column on box.forecast_run",
            "Readers keyed on THE record run": "erebor app/box_locations.py + api/highgrade.py; sql/69 curated.box_scout_locations; box_econ.box_pud_econ (Steven, keyed on run_id); scripts.box_prune_runs / box_refresh",
        },
    }
    (a.out / "summary.json").write_text(json.dumps(sm, indent=1, default=str), encoding="utf-8")
    flat = []
    for c in cards:
        r10 = c["reach"].get("k10", {})
        flat.append({"bench": c["bench"], "family": c["family"], "modern": c["modern"], "oil12_kft_med": c["oil12_kft_med"], "gor12_med": c["gor12_med"],
                     "tvd_p50": c["tvd"]["p50"], "spacing_med_ft": c["spacing"]["median_ft"], "spacing_unbounded": c["spacing"]["share_unbounded"],
                     "n_operators": c["operators_modern"]["n_operators"], "hhi": c["operators_modern"]["hhi"], "share_2023plus": c["share_modern_2023plus"],
                     "recent_ge_12500": c["lateral_recent"]["ge_12500"], "recent_gt_15000": c["recent_gt_band_excluded"], "sharing_recent": c["sharing_recent"],
                     "water_calc_2019": c["water_2019"]["share_calculated"], "undrilled": c["undrilled"], "undrilled_pud": c["undrilled_pud"],
                     "sticks_ge_15000": c["stick_length"]["ge_15000"], "k10_p50_mi": r10.get("p50_mi"), "k10_within_5mi": r10.get("share_within", {}).get("5.0"),
                     **{f"fold_{k[:4]}": v for k, v in c["fold_wells"].items()}})
    pd.DataFrame(flat).to_csv(a.out / "cards.csv", index=False)
    pd.DataFrame([{"a": x["a"], "b": x["b"], **{f"sep_{k}": v for k, v in x["separation"].items()}, **{f"coloc_{k}": v for k, v in x["colocation_1mi"].items()},
                   "oil_ratio": x["oil12_kft_ratio"]["ratio"], "oil_ci_lo": x["oil12_kft_ratio"]["ci90"][0], "oil_ci_hi": x["oil12_kft_ratio"]["ci90"][1],
                   "gor_ratio": x["gor12_ratio"]["ratio"], "gor_ci_lo": x["gor12_ratio"]["ci90"][0], "gor_ci_hi": x["gor12_ratio"]["ci90"][1]} for x in pairs]
                 ).to_csv(a.out / "pairs.csv", index=False)
    pd.DataFrame(sm["novi"]).to_csv(a.out / "novi_bias.csv", index=False)
    page = render(a.out, sm, {"maps": maps_png(p, s), "oil_year": oil_by_year_png(p)})
    print(f"wrote {page}")
    for idn in sm["plan_identity"]:
        print(idn["bench"], "diff vs plan:", idn["diff"])


if __name__ == "__main__":
    main()
