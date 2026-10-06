"""BOX step 1 — bench QC for the pilot benches (read-only).

docs/box_type_curves_plan.md §5 step 1: for Delaware WCA_1 / WCA_2 / BS2_S,

  * count producing horizontals; share with DirectionalSurveyIsPlanned = TRUE;
    share whose bench tag disagrees with a local depth consensus; share sitting
    on a permit-round TVD (exact multiple of 100 ft);
  * the state-line check: density, planned-survey share, median TVD and median
    12-mo oil per 1,000 ft in 10-mi bins each side of the TX/NM line (32 N);
  * the decision input for NM planned-survey wells (reassign by depth vs exclude).

Two tag-disagreement measures are reported side by side:

  1. ``sql23``  — the LIVE warehouse audit (curated.formation_blueox_tvd): 40-NN
     per-bench local medians, nearest band vs assigned band, and its decisive
     ``corrected`` flip.
  2. ``cons``   — a re-implementation of the gunbarrel-consensus detector v2 from
     its recorded rules (memory note wcb2-deep-tvd-screening, 2026-09-15): clean
     witnesses <= 1.5 mi (real survey, non-round TVD, >= 6 mo seasoned), band =
     >= 3 witnesses with IQR <= 150 ft, bands < 100 ft apart merge into a
     complex, flag when the well sits <= 120 ft inside another band while its
     own band is absent / incoherent / >= 2x farther and the runner-up is
     >= 1.5x farther. The original v2 script lived in a session scratchpad and
     is not in the repo — this is NOT that script; treat its flags as a QC
     measure, not ratified output (ratified rows live in ref.formation_tag_overrides).
     sql/23 guard (3) is kept: a sand<->carbonate swap within one interval
     (BS2_S<->BS2_C) is reported as ``ambiguous_lith``, never as a flag.

Rates / cohort conventions: 12-mo oil is Novi's cum_12m_oil_bbl pass-through
(bbl, calendar basis as Novi computed it); per-ft uses lateral_length_ft; the
cohort filter is D9 (first prod >= 2016-01-01, lateral 6,000-13,000 ft) plus a
full 12 months of history. Everything is reported with n.
"""

from __future__ import annotations

import base64
import datetime as _dt
import html
import io
import json
import math
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASIN = "delaware"
PILOT_BENCHES: tuple[str, ...] = ("WCA_1", "WCA_2", "BS2_S")

STATE_LINE_LAT = 32.0  # TX/NM boundary across the Delaware Basin
MI_PER_DEG_LAT = 69.0  # ~68.9 mi/deg at 32 N; bins are 10 mi, so this is fine
FT_PER_MI = 5280.0
BIN_MI = 10
BIN_LO_MI, BIN_HI_MI = -60, 60

COHORT_FP_MIN = date(2016, 1, 1)  # D9
COHORT_LL_MIN_FT = 6_000  # D9
COHORT_LL_MAX_FT = 13_000  # D9
SEASONING_DAYS = 182  # consensus v2.1: >= 6 mo online before a TVD is evidence
MIN_BIN_N = 20  # below this a bin's median / density is shown but not judged

NM_FIPS, TX_FIPS = 30, 42


# ----------------------------------------------------------------------------
# Consensus rule (pure; DB-free; unit-tested)
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsensusParams:
    radius_ft: float = 1.5 * FT_PER_MI
    min_witness: int = 3
    iqr_max_ft: float = 150.0
    sits_in_ft: float = 120.0
    own_ratio: float = 2.0
    runner_ratio: float = 1.5
    merge_ft: float = 100.0


DEFAULT_PARAMS = ConsensusParams()


def local_bands(
    tvd_by_bench: dict[str, np.ndarray], p: ConsensusParams
) -> dict[str, tuple[float, int, float]]:
    """Coherent local depth bands: bench -> (median_tvd, n, iqr) for benches
    with >= min_witness clean witnesses and IQR <= iqr_max_ft."""
    out: dict[str, tuple[float, int, float]] = {}
    for bench, arr in tvd_by_bench.items():
        arr = np.asarray(arr, dtype=float)
        if len(arr) < p.min_witness:
            continue
        q1, q3 = np.percentile(arr, [25, 75])
        if q3 - q1 <= p.iqr_max_ft:
            out[bench] = (float(np.median(arr)), len(arr), float(q3 - q1))
    return out


def band_complexes(bands: dict[str, tuple[float, int, float]], merge_ft: float) -> dict[str, int]:
    """Merge bands whose medians are < merge_ft apart into complexes (chain merge)."""
    order = sorted(bands, key=lambda b: bands[b][0])
    cid: dict[str, int] = {}
    c, prev = 0, None
    for b in order:
        if prev is not None and bands[b][0] - bands[prev][0] >= merge_ft:
            c += 1
        cid[b] = c
        prev = b
    return cid


def _is_lith_swap(a: str, b: str) -> bool:
    return (
        a[:3] == b[:3]
        and a[-1] in ("S", "C")
        and b[-1] in ("S", "C")
        and a[-1] != b[-1]
    )


def score_subject(
    tvd: float, tag: str, bands: dict[str, tuple[float, int, float]], p: ConsensusParams
) -> dict[str, Any]:
    """Apply the consensus v2 rule to one well against its local bands.

    Returns cons_status in {no_evidence, agree, flag, ambiguous, ambiguous_lith,
    off_band, own_only} plus the supporting numbers.
    """
    res: dict[str, Any] = {
        "cons_status": "no_evidence",
        "cons_n_bands": len(bands),
        "cons_own_med": np.nan,
        "cons_own_n": 0,
        "cons_own_delta": np.nan,
        "cons_nearest": None,
        "cons_nearest_delta": np.nan,
        "cons_suggest": None,
    }
    if not bands:
        return res
    d = {b: abs(tvd - bands[b][0]) for b in bands}
    if tag in bands:
        res["cons_own_med"] = bands[tag][0]
        res["cons_own_n"] = bands[tag][1]
        res["cons_own_delta"] = d[tag]
    order = sorted(d, key=lambda b: d[b])
    b1 = order[0]
    d1 = d[b1]
    res["cons_nearest"], res["cons_nearest_delta"] = b1, d1

    if b1 == tag:
        res["cons_status"] = "agree"
        return res
    if d1 > p.sits_in_ft:
        res["cons_status"] = "off_band"  # sits inside no coherent local band
        return res
    cid = band_complexes(bands, p.merge_ft)
    if tag in bands and cid[tag] == cid[b1]:
        res["cons_status"] = "ambiguous"
        return res
    own_ok = (tag not in bands) or (d[tag] >= p.own_ratio * d1)
    runner = [b for b in order[1:] if b != tag and cid[b] != cid[b1]]
    runner_ok = (not runner) or (d[runner[0]] >= p.runner_ratio * d1)
    if not (own_ok and runner_ok):
        res["cons_status"] = "ambiguous"
        return res
    members = [b for b in bands if cid[b] == cid[b1] and d[b] <= p.sits_in_ft]
    suggest = max(members, key=lambda b: bands[b][1])
    res["cons_suggest"] = suggest
    res["cons_status"] = "ambiguous_lith" if _is_lith_swap(tag, suggest) else "flag"
    return res


# ----------------------------------------------------------------------------
# State-line bins (pure)
# ----------------------------------------------------------------------------


def state_line_bins(df: pd.DataFrame) -> pd.DataFrame:
    """Per 10-mi bin of signed distance from 32 N (negative = TX side):
    producing-horizontal count, approximate density, planned-survey share,
    permit-round share, median TVD, and cohort median 12-mo oil per 1,000 ft."""
    edges = np.arange(BIN_LO_MI, BIN_HI_MI + BIN_MI, BIN_MI)
    d = df.copy()
    d["dist_mi"] = (d["mid_lat"] - STATE_LINE_LAT) * MI_PER_DEG_LAT
    d["bin_lo"] = pd.cut(d["dist_mi"], edges, right=False, labels=edges[:-1]).astype(float)
    rows = []
    for lo in edges[:-1]:
        g = d[d["bin_lo"] == lo]
        n = len(g)
        coh = g[g["cohort"]]
        if n >= MIN_BIN_N:
            lon_lo, lon_hi = np.percentile(g["mid_lon"], [2.5, 97.5])
            lat_mid = float(g["mid_lat"].median())
            ew_mi = (lon_hi - lon_lo) * MI_PER_DEG_LAT * math.cos(math.radians(lat_mid))
            density = n / (ew_mi * BIN_MI) if ew_mi > 0 else np.nan
        else:
            density = np.nan
        rows.append(
            {
                "bin_lo_mi": float(lo),
                "bin_hi_mi": float(lo + BIN_MI),
                "side": "NM" if lo >= 0 else "TX",
                "n_prod_hz": n,
                "n_nm_tagged": int((g["state_code"] == NM_FIPS).sum()),
                "density_per_sqmi": density,
                "planned_share": float(g["planned"].mean()) if n else np.nan,
                "round_tvd_share": float(g["tvd_round"].mean()) if n else np.nan,
                "med_tvd_ft": float(g["tvd_ft"].median()) if n else np.nan,
                "n_cohort": len(coh),
                "med_oil12_kft": float(coh["oil12_kft"].median()) if len(coh) else np.nan,
                "p25_oil12_kft": float(coh["oil12_kft"].quantile(0.25)) if len(coh) else np.nan,
                "p75_oil12_kft": float(coh["oil12_kft"].quantile(0.75)) if len(coh) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def border_step_verdict(bins: pd.DataFrame) -> dict[str, Any]:
    """Compare the median-oil/ft step across the border bins (-10..0 vs 0..10)
    with the steps between every other adjacent pair of judged bins."""
    ok = bins[bins["n_cohort"] >= MIN_BIN_N].reset_index(drop=True)
    steps = []
    border = None
    for i in range(len(ok) - 1):
        a, b = ok.iloc[i], ok.iloc[i + 1]
        if b["bin_lo_mi"] - a["bin_lo_mi"] != BIN_MI:
            continue  # non-adjacent after dropping thin bins
        rel = abs(b["med_oil12_kft"] - a["med_oil12_kft"]) / ((a["med_oil12_kft"] + b["med_oil12_kft"]) / 2)
        item = {"from": a["bin_lo_mi"], "to": b["bin_lo_mi"], "rel_step": float(rel)}
        if a["bin_lo_mi"] == -BIN_MI and b["bin_lo_mi"] == 0:
            border = item
        else:
            steps.append(item)
    if border is None:
        return {"verdict": "not_judged", "reason": f"a border bin has < {MIN_BIN_N} cohort wells"}
    typical = float(np.median([s["rel_step"] for s in steps])) if steps else np.nan
    worst = float(max(s["rel_step"] for s in steps)) if steps else np.nan
    flagged = bool(steps) and border["rel_step"] > max(0.15, 1.5 * typical)
    return {
        "verdict": "flag" if flagged else "no_step",
        "border_rel_step": border["rel_step"],
        "typical_rel_step": typical,
        "max_other_rel_step": worst,
        "n_other_steps": len(steps),
    }


# ----------------------------------------------------------------------------
# Warehouse pull (read-only)
# ----------------------------------------------------------------------------

_SQL = """
SELECT
    w.api10, w.well_name, w.current_operator AS operator, w.state_code, w.county,
    w.formation_blueox, w.formation_blueox_base, w.formation_blueox_source,
    w.formation_blueox_tvd_corrected,
    w.directional_survey_is_planned AS planned,
    w.tvd_ft, w.lateral_length_ft, w.first_production_date, w.last_reported_month,
    w.cum_12m_oil_bbl, w.cum_24m_oil_bbl, w.has_production_sharing,
    COALESCE(w.midpoint_lon,
             CASE WHEN ST_GeometryType(w.wellstick_geom) = 'ST_LineString'
                  THEN ST_X(ST_LineInterpolatePoint(w.wellstick_geom, 0.5)) END,
             (w.surface_lon + w.bhl_lon) / 2.0, w.surface_lon)               AS mid_lon,
    COALESCE(w.midpoint_lat,
             CASE WHEN ST_GeometryType(w.wellstick_geom) = 'ST_LineString'
                  THEN ST_Y(ST_LineInterpolatePoint(w.wellstick_geom, 0.5)) END,
             (w.surface_lat + w.bhl_lat) / 2.0, w.surface_lat)               AS mid_lat,
    t.assigned_code AS sql23_assigned, t.nearest_code AS sql23_nearest,
    t.assigned_med AS sql23_assigned_med, t.nearest_med AS sql23_nearest_med,
    t.assigned_n AS sql23_assigned_n, t.nearest_n AS sql23_nearest_n,
    t.assigned_gap AS sql23_assigned_gap, t.nearest_gap AS sql23_nearest_gap,
    t.corrected AS sql23_corrected
FROM curated.wells_enriched w
LEFT JOIN curated.formation_blueox_tvd t ON t.api10 = w.api10
WHERE w.basin_blueox = %(basin)s
  AND w.is_horizontal
  AND w.first_production_date IS NOT NULL
"""


def pull_delaware_producers(conn: Any) -> pd.DataFrame:
    """Every producing horizontal in the Delaware (all benches — the consensus
    witnesses are cross-bench) joined to the sql/23 audit. READ ONLY."""
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_SQL, {"basin": BASIN})
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
    conn.rollback()
    df = pd.DataFrame(rows, columns=cols)
    return prepare(df)


def prepare(df: pd.DataFrame, asof: date | None = None) -> pd.DataFrame:
    """Derive the QC columns on the pulled frame (pure; used by tests)."""
    d = df.copy()
    for c in ("tvd_ft", "lateral_length_ft", "cum_12m_oil_bbl", "cum_24m_oil_bbl", "mid_lon", "mid_lat"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["first_production_date"] = pd.to_datetime(d["first_production_date"]).dt.date
    d["planned"] = d["planned"].fillna(False).astype(bool)
    d["formation_blueox"] = d["formation_blueox"].fillna("(unmapped)")
    d["tvd_round"] = d["tvd_ft"].notna() & ((d["tvd_ft"] % 100) == 0)
    d["oil12_kft"] = d["cum_12m_oil_bbl"] / d["lateral_length_ft"] * 1000.0
    if asof is None:
        lrm = pd.to_datetime(d["last_reported_month"], errors="coerce")
        asof = lrm.max().date() if lrm.notna().any() else _dt.datetime.now(tz=_dt.UTC).date()
    d.attrs["asof"] = asof
    twelve_full = pd.Series([fp <= asof - timedelta(days=395) for fp in d["first_production_date"]], index=d.index)
    d["cohort"] = (
        pd.Series([fp >= COHORT_FP_MIN for fp in d["first_production_date"]], index=d.index)
        & d["lateral_length_ft"].between(COHORT_LL_MIN_FT, COHORT_LL_MAX_FT)
        & d["cum_12m_oil_bbl"].notna()
        & (d["cum_12m_oil_bbl"] > 0)
        & twelve_full
    )
    d["sql23_disagree"] = (
        d["sql23_nearest"].notna()
        & (d["sql23_nearest"] != d["sql23_assigned"])
        & (d["sql23_nearest_gap"] < d["sql23_assigned_gap"])
    )
    return d


# ----------------------------------------------------------------------------
# Consensus scoring over the frame
# ----------------------------------------------------------------------------


def _project_xy_ft(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", "EPSG:32613", always_xy=True)
    x, y = tr.transform(lon, lat)
    return np.column_stack([x, y]) * 3.280839895


def score_consensus(df: pd.DataFrame, p: ConsensusParams = DEFAULT_PARAMS) -> pd.DataFrame:
    """Score every well with a TVD and a position against clean witnesses
    (any bench) within p.radius_ft. Adds cons_* columns."""
    from scipy.spatial import cKDTree

    asof: date = df.attrs.get("asof", _dt.datetime.now(tz=_dt.UTC).date())
    pos_ok = df["mid_lon"].notna() & df["mid_lat"].notna() & df["tvd_ft"].notna()
    seasoned = pd.Series([fp <= asof - timedelta(days=SEASONING_DAYS) for fp in df["first_production_date"]], index=df.index)
    clean = (
        pos_ok
        & ~df["planned"]
        & ~df["tvd_round"]
        & seasoned
        & ~df["formation_blueox"].isin(["(unmapped)", "OTHER"])
    )
    df = df.copy()
    df["cons_witness"] = clean
    xy_all = np.full((len(df), 2), np.nan)
    xy_all[pos_ok.values] = _project_xy_ft(df.loc[pos_ok, "mid_lon"].values, df.loc[pos_ok, "mid_lat"].values)
    wit_idx = np.where(clean.values)[0]
    tree = cKDTree(xy_all[wit_idx])
    wit_bench = df["formation_blueox"].values[wit_idx]
    wit_tvd = df["tvd_ft"].values[wit_idx].astype(float)
    tvd = df["tvd_ft"].values
    tag = df["formation_blueox"].values
    out: list[dict[str, Any]] = []
    subj = np.where(pos_ok.values)[0]
    neigh = tree.query_ball_point(xy_all[subj], r=p.radius_ft)
    for k, i in enumerate(subj):
        js = [wit_idx[j] for j in neigh[k] if wit_idx[j] != i]
        by: dict[str, list[float]] = {}
        for j in neigh[k]:
            if wit_idx[j] == i:
                continue
            by.setdefault(str(wit_bench[j]), []).append(float(wit_tvd[j]))
        bands = local_bands({b: np.array(v) for b, v in by.items()}, p)
        r = score_subject(float(tvd[i]), str(tag[i]), bands, p)
        r["idx"] = i
        r["cons_n_witness"] = len(js)
        r["cons_bands"] = {b: v[0] for b, v in bands.items()}  # bench -> local median TVD
        out.append(r)
    res = pd.DataFrame(out).set_index("idx")
    for c in res.columns:
        df[c] = res[c]
    df["cons_status"] = df["cons_status"].fillna("no_position")
    df["cons_n_witness"] = df["cons_n_witness"].fillna(0).astype(int)
    return df


def pair_separation(df: pd.DataFrame, bench: str, min_hoods: int = 30) -> list[dict[str, Any]]:
    """For this bench's wells whose own band is coherent, the local depth
    separation (other band median - own band median, ft) to every other
    coherent band in the same 1.5-mi neighbourhood. Tells whether adjacent
    benches are depth-separable where they co-occur (sql/23 guard-3 logic,
    measured). Positive = other bench is deeper."""
    b = df[(df["formation_blueox"] == bench) & df["cons_bands"].notna()]
    rows: dict[str, list[tuple[float, int]]] = {}
    for bands, state in zip(b["cons_bands"], b["state_code"]):
        if not isinstance(bands, dict) or bench not in bands:
            continue
        own = bands[bench]
        for other, med in bands.items():
            if other != bench:
                rows.setdefault(other, []).append((med - own, int(state)))
    out = []
    for other, vals in rows.items():
        if len(vals) < min_hoods:
            continue
        sep = np.array([v[0] for v in vals])
        st = np.array([v[1] for v in vals])
        rec = {
            "other": other,
            "n_hoods": len(sep),
            "med_sep_ft": float(np.median(sep)),
            "p25_sep_ft": float(np.percentile(sep, 25)),
            "p75_sep_ft": float(np.percentile(sep, 75)),
            "share_within_100ft": float((np.abs(sep) < 100).mean()),
            "share_inverted": float(((sep < 0) if np.median(sep) > 0 else (sep > 0)).mean()),
        }
        for code, name in ((TX_FIPS, "tx"), (NM_FIPS, "nm")):
            m = st == code
            rec[f"n_{name}"] = int(m.sum())
            rec[f"med_sep_ft_{name}"] = float(np.median(sep[m])) if m.any() else float("nan")
            rec[f"share_within_100ft_{name}"] = float((np.abs(sep[m]) < 100).mean()) if m.any() else float("nan")
        out.append(rec)
    out.sort(key=lambda r: -r["n_hoods"])
    return out


# ----------------------------------------------------------------------------
# Per-bench summary
# ----------------------------------------------------------------------------


def _share(mask: pd.Series) -> float:
    return float(mask.mean()) if len(mask) else float("nan")


def bench_summary(df: pd.DataFrame, bench: str) -> dict[str, Any]:
    b = df[df["formation_blueox"] == bench]
    nm = b[b["state_code"] == NM_FIPS]
    tx = b[b["state_code"] == TX_FIPS]
    coh = b[b["cohort"]]
    inbound = df[(df["formation_blueox"] != bench) & (df["cons_suggest"] == bench) & (df["cons_status"] == "flag")]
    s: dict[str, Any] = {
        "bench": bench,
        "asof": str(df.attrs.get("asof")),
        "n_prod_hz": len(b),
        "n_tx": len(tx),
        "n_nm": len(nm),
        "n_fp_ge_2016": int(sum(fp >= COHORT_FP_MIN for fp in b["first_production_date"])),
        "n_cohort": len(coh),
        "n_cohort_tx": int(coh["state_code"].eq(TX_FIPS).sum()),
        "n_cohort_nm": int(coh["state_code"].eq(NM_FIPS).sum()),
        "planned_share": _share(b["planned"]),
        "planned_share_nm": _share(nm["planned"]),
        "planned_share_tx": _share(tx["planned"]),
        "round_tvd_share": _share(b["tvd_round"]),
        "round_tvd_share_nm": _share(nm["tvd_round"]),
        "round_tvd_share_tx": _share(tx["tvd_round"]),
        "tvd_null": int(b["tvd_ft"].isna().sum()),
        "source_counts": b["formation_blueox_source"].fillna("(null)").value_counts().to_dict(),
        "n_tvd_corrected_in": int(b["formation_blueox_tvd_corrected"].fillna(False).sum()),
        "sql23_disagree_share": _share(b["sql23_disagree"]),
        "sql23_disagree_n": int(b["sql23_disagree"].sum()),
        "sql23_nearest_counts": b.loc[b["sql23_disagree"], "sql23_nearest"].value_counts().to_dict(),
        "cons_status_counts": b["cons_status"].value_counts().to_dict(),
        "cons_flag_n": int((b["cons_status"] == "flag").sum()),
        "cons_flag_share": _share(b["cons_status"] == "flag"),
        "cons_flag_share_scored": _share(b.loc[b["cons_status"].isin(["agree", "flag", "ambiguous", "ambiguous_lith", "off_band"]), "cons_status"] == "flag"),
        "cons_suggest_counts": b.loc[b["cons_status"] == "flag", "cons_suggest"].value_counts().to_dict(),
        "cons_inbound_n": len(inbound),
        "cons_inbound_from": inbound["formation_blueox"].value_counts().to_dict(),
        "cons_lith_n": int((b["cons_status"] == "ambiguous_lith").sum()),
        "cohort_med_oil12_kft": float(coh["oil12_kft"].median()) if len(coh) else float("nan"),
        "cohort_med_oil12_kft_tx": float(coh.loc[coh["state_code"] == TX_FIPS, "oil12_kft"].median()) if len(coh) else float("nan"),
        "cohort_med_oil12_kft_nm": float(coh.loc[coh["state_code"] == NM_FIPS, "oil12_kft"].median()) if len(coh) else float("nan"),
        "cohort_med_oil12_kft_nm_planned": float(coh.loc[(coh["state_code"] == NM_FIPS) & coh["planned"], "oil12_kft"].median()) if len(coh) else float("nan"),
        "cohort_med_oil12_kft_nm_actual": float(coh.loc[(coh["state_code"] == NM_FIPS) & ~coh["planned"], "oil12_kft"].median()) if len(coh) else float("nan"),
        "n_cohort_nm_planned": int(((coh["state_code"] == NM_FIPS) & coh["planned"]).sum()),
        "n_cohort_nm_actual": int(((coh["state_code"] == NM_FIPS) & ~coh["planned"]).sum()),
        "state_mismatch_n": int(((b["state_code"] == NM_FIPS) & (b["mid_lat"] < STATE_LINE_LAT)).sum() + ((b["state_code"] == TX_FIPS) & (b["mid_lat"] >= STATE_LINE_LAT)).sum()),
    }
    # NM planned-survey decision input
    nmp = nm[nm["planned"]]
    s["nm_planned_n"] = len(nmp)
    s["nm_planned_cons_status"] = nmp["cons_status"].value_counts().to_dict()
    s["nm_planned_cons_suggest"] = nmp.loc[nmp["cons_status"] == "flag", "cons_suggest"].value_counts().to_dict()
    s["nm_planned_sql23_disagree_share"] = _share(nmp["sql23_disagree"])
    s["nm_actual_sql23_disagree_share"] = _share(nm.loc[~nm["planned"], "sql23_disagree"])
    s["nm_actual_cons_flag_share"] = _share(nm.loc[~nm["planned"], "cons_status"] == "flag")
    s["nm_planned_cons_flag_share"] = _share(nmp["cons_status"] == "flag")
    s["tx_cons_flag_share"] = _share(tx["cons_status"] == "flag")
    # option effects on the cohort
    flagged = b["cons_status"] == "flag"
    s["option_current_cohort"] = {"tx": s["n_cohort_tx"], "nm": s["n_cohort_nm"]}
    keep_a = b["cohort"] & ~(b["planned"] & flagged)
    s["option_a_cohort"] = {
        "tx": int((keep_a & (b["state_code"] == TX_FIPS)).sum()),
        "nm": int((keep_a & (b["state_code"] == NM_FIPS)).sum()),
        "reassigned_out": int((b["planned"] & flagged).sum()),
        "reassigned_in": int((inbound["planned"]).sum()),
    }
    keep_b = b["cohort"] & ~b["planned"]
    s["option_b_cohort"] = {
        "tx": int((keep_b & (b["state_code"] == TX_FIPS)).sum()),
        "nm": int((keep_b & (b["state_code"] == NM_FIPS)).sum()),
        "excluded": int((b["planned"]).sum()),
    }
    bins = state_line_bins(b)
    s["state_line"] = bins.to_dict(orient="records")
    s["border_step"] = border_step_verdict(bins)
    s["pair_separation"] = pair_separation(df, bench)
    return s


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

_CSS = """
body{font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:#111827;margin:0 24px 48px;max-width:1500px}
h1{font-size:20px;margin:18px 0 4px} h2{font-size:16px;margin:36px 0 6px;border-top:2px solid #e5e7eb;padding-top:14px}
h3{font-size:14px;margin:18px 0 4px} .meta{color:#6b7280;font-size:12px}
.flag{background:#fffbeb;border-left:4px solid #d97706;padding:4px 10px;margin:4px 0} .bad{background:#fef2f2;border-left-color:#dc2626}
.ok{background:#f0fdf4;border-left-color:#16a34a}
.row{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap} .row img{max-width:700px;height:auto} svg{max-width:100%;height:auto}
table{border-collapse:collapse;font-size:12px;margin:8px 0} th,td{border:1px solid #e5e7eb;padding:3px 7px;text-align:left;vertical-align:top}
th{background:#f9fafb} td.num,th.num{text-align:right}
details{margin:6px 0} summary{cursor:pointer;color:#374151;font-size:12px} .toc a{margin-right:10px;font-size:12px}
"""


def _esc(v: Any) -> str:
    return html.escape("" if v is None else str(v))


def _fmt(v: Any, nd: int = 1, pct: bool = False) -> str:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "—"
    if pct:
        return f"{100 * float(v):.{nd}f} %"
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}"
    return f"{float(v):,.{nd}f}"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    h = "".join(f"<th>{_esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>"


def _png(fig: Any, dpi: int = 120) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _svg(fig: Any) -> str:
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    body = buf.getvalue()
    return body[body.index("<svg") :]


def _basemap(ax: Any, ctx: pd.DataFrame, b: pd.DataFrame) -> None:
    ax.scatter(ctx["mid_lon"], ctx["mid_lat"], s=1, c="#d1d5db", alpha=0.35, linewidths=0, rasterized=True)
    lon0, lon1 = np.nanpercentile(b["mid_lon"], [0.5, 99.5])
    lat0, lat1 = np.nanpercentile(b["mid_lat"], [0.5, 99.5])
    pad = 0.15
    ax.set_xlim(lon0 - pad, lon1 + pad)
    ax.set_ylim(lat0 - pad, lat1 + pad)
    ax.axhline(STATE_LINE_LAT, color="#111827", ls="--", lw=0.8)
    ax.axvline(-103.0, color="#111827", ls="--", lw=0.8)
    ax.text(lon0 - pad + 0.02, STATE_LINE_LAT + 0.01, "NM", fontsize=8)
    ax.text(lon0 - pad + 0.02, STATE_LINE_LAT - 0.04, "TX", fontsize=8)
    ax.set_aspect(1 / math.cos(math.radians(32.0)))
    ax.set_xlabel("lon")
    ax.set_ylabel("lat")


def tag_qc_map(ctx: pd.DataFrame, b: pd.DataFrame, bench: str) -> str:
    fig, ax = plt.subplots(figsize=(8.5, 8))
    _basemap(ax, ctx, b)
    clean = b[~b["planned"] & ~b["tvd_round"] & (b["cons_status"] != "flag")]
    ax.scatter(clean["mid_lon"], clean["mid_lat"], s=3, c="#2563eb", alpha=0.5, linewidths=0, label=f"clean (n={len(clean):,})", rasterized=True)
    rnd = b[b["tvd_round"] & ~b["planned"]]
    ax.scatter(rnd["mid_lon"], rnd["mid_lat"], s=6, c="#7c3aed", alpha=0.8, linewidths=0, label=f"permit-round TVD (n={len(rnd):,})", rasterized=True)
    pl = b[b["planned"]]
    ax.scatter(pl["mid_lon"], pl["mid_lat"], s=6, c="#f59e0b", alpha=0.8, linewidths=0, label=f"planned survey (n={len(pl):,})", rasterized=True)
    fl = b[b["cons_status"] == "flag"]
    ax.scatter(fl["mid_lon"], fl["mid_lat"], s=14, facecolors="none", edgecolors="#dc2626", linewidths=0.8, label=f"consensus flag (n={len(fl):,})")
    ax.legend(loc="lower left", fontsize=8, markerscale=2)
    ax.set_title(f"{bench} — producing horizontals, tag QC (n={len(b):,}); grey = other Delaware benches", fontsize=10)
    return _png(fig)


def perf_map(ctx: pd.DataFrame, b: pd.DataFrame, bench: str) -> str:
    coh = b[b["cohort"]].copy()
    fig, ax = plt.subplots(figsize=(8.5, 8))
    _basemap(ax, ctx, b)
    if len(coh):
        lo, hi = np.nanpercentile(coh["oil12_kft"], [5, 95])
        sc = ax.scatter(coh["mid_lon"], coh["mid_lat"], s=5, c=coh["oil12_kft"].clip(lo, hi), cmap="RdYlBu_r", linewidths=0, rasterized=True)
        cb = fig.colorbar(sc, ax=ax, shrink=0.6)
        cb.set_label("12-mo cum oil, bbl per 1,000 ft (clipped p5–p95)")
    ax.set_title(f"{bench} — D9 cohort 12-mo oil/ft (n={len(coh):,}; fp ≥ 2016, lateral 6–13 kft, 12 full months)", fontsize=10)
    return _png(fig)


def state_line_fig(bins: pd.DataFrame, bench: str) -> str:
    x = bins["bin_lo_mi"] + BIN_MI / 2
    fig, axes = plt.subplots(4, 1, figsize=(9, 10), sharex=True)
    axes[0].bar(x, bins["n_prod_hz"], width=BIN_MI * 0.9, color="#93c5fd", label="producing hz")
    axes[0].bar(x, bins["n_cohort"], width=BIN_MI * 0.6, color="#1d4ed8", label="D9 cohort")
    axes[0].set_ylabel("wells")
    axes[0].legend(fontsize=8)
    ax0b = axes[0].twinx()
    ax0b.plot(x, bins["density_per_sqmi"], "k.-", lw=0.8)
    ax0b.set_ylabel("≈ wells / sq mi")
    axes[1].plot(x, 100 * bins["planned_share"], "o-", color="#f59e0b", label="planned-survey share")
    axes[1].plot(x, 100 * bins["round_tvd_share"], "s-", color="#7c3aed", label="permit-round TVD share")
    axes[1].set_ylabel("%")
    axes[1].legend(fontsize=8)
    axes[2].plot(x, bins["med_tvd_ft"], "o-", color="#374151")
    axes[2].set_ylabel("median TVD, ft")
    axes[2].invert_yaxis()
    ok = bins["n_cohort"] >= MIN_BIN_N
    axes[3].errorbar(
        x[ok], bins.loc[ok, "med_oil12_kft"],
        yerr=[bins.loc[ok, "med_oil12_kft"] - bins.loc[ok, "p25_oil12_kft"], bins.loc[ok, "p75_oil12_kft"] - bins.loc[ok, "med_oil12_kft"]],
        fmt="o-", color="#16a34a", capsize=3, label=f"median ± IQR (bins with ≥ {MIN_BIN_N} cohort wells)",
    )
    axes[3].plot(x[~ok], bins.loc[~ok, "med_oil12_kft"], "o", color="#9ca3af", label="thin bin (shown, not judged)")
    for xi, n, m in zip(x, bins["n_cohort"], bins["med_oil12_kft"]):
        if n and not math.isnan(m):
            axes[3].annotate(f"n={n}", (xi, m), textcoords="offset points", xytext=(0, 8), fontsize=7, ha="center")
    axes[3].set_ylabel("12-mo oil, bbl / 1,000 ft")
    axes[3].legend(fontsize=8)
    axes[3].set_xlabel("miles from the TX/NM line (32° N); negative = Texas, positive = New Mexico")
    for ax in axes:
        ax.axvline(0, color="#111827", ls="--", lw=0.8)
        ax.grid(alpha=0.25)
    fig.suptitle(f"{bench} — state-line check, {BIN_MI}-mi bins", fontsize=11)
    fig.tight_layout()
    return _svg(fig)


def _counts_table(d: dict[str, Any]) -> str:
    rows = [[k, _fmt(v)] for k, v in sorted(d.items(), key=lambda kv: -kv[1])]
    return _table(["value", "n"], rows)


def render_bench_page(df: pd.DataFrame, s: dict[str, Any], out: Path) -> Path:
    bench = s["bench"]
    b = df[df["formation_blueox"] == bench]
    ctx = df[(df["formation_blueox"] != bench) & df["mid_lon"].notna()]
    bins = pd.DataFrame(s["state_line"])
    bs = s["border_step"]
    p: list[str] = [
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>BOX step 1 — bench QC {bench}</title><style>{_CSS}</style></head><body>",
        f"<h1>BOX step 1 — bench QC: Delaware {bench}</h1>",
        f"<div class=meta>Grain: producing horizontals (one row per api10) from curated.wells_enriched, basin_blueox = delaware, is_horizontal, first_production_date NOT NULL, grouped on the TVD-corrected formation_blueox. Warehouse as-of (max last_reported_month): {_esc(s['asof'])}. Read-only; nothing written. Plan: docs/box_type_curves_plan.md §5 step 1.</div>",
        "<div class=toc><a href=index.html>← index</a><a href=#counts>counts</a><a href=#tags>tag QC</a><a href=#stateline>state line</a><a href=#nm>NM planned-survey decision</a><a href=#wells>well set</a></div>",
    ]
    # --- counts
    p.append("<h2 id=counts>1. Counts</h2>")
    p.append(_table(
        ["measure", "all", "TX", "NM"],
        [
            ["producing horizontals", _fmt(s["n_prod_hz"]), _fmt(s["n_tx"]), _fmt(s["n_nm"])],
            ["first prod ≥ 2016-01-01", _fmt(s["n_fp_ge_2016"]), "", ""],
            ["D9 cohort (fp ≥ 2016, lateral 6–13 kft, 12 full months, cum12 > 0)", _fmt(s["n_cohort"]), _fmt(s["n_cohort_tx"]), _fmt(s["n_cohort_nm"])],
            ["planned-survey share (DirectionalSurveyIsPlanned)", _fmt(s["planned_share"], pct=True), _fmt(s["planned_share_tx"], pct=True), _fmt(s["planned_share_nm"], pct=True)],
            ["permit-round TVD share (TVD % 100 = 0)", _fmt(s["round_tvd_share"], pct=True), _fmt(s["round_tvd_share_tx"], pct=True), _fmt(s["round_tvd_share_nm"], pct=True)],
            ["TVD missing", _fmt(s["tvd_null"]), "", ""],
            ["cohort median 12-mo oil, bbl / 1,000 ft", _fmt(s["cohort_med_oil12_kft"], 0), _fmt(s["cohort_med_oil12_kft_tx"], 0), _fmt(s["cohort_med_oil12_kft_nm"], 0)],
            ["state_code vs 32° N mismatches", _fmt(s["state_mismatch_n"]), "", ""],
        ],
    ))
    p.append("<h3>Bench-tag source (formation_blueox_source)</h3>" + _counts_table(s["source_counts"]))
    # --- tags
    p.append("<h2 id=tags>2. Tag disagreement</h2>")
    p.append(
        "<p>Two measures. <b>sql/23 (live)</b>: curated.formation_blueox_tvd, 40-nearest-neighbour per-bench medians; "
        "'disagree' = the depth-nearest band is a different bench and closer than the assigned band (any margin); "
        "'corrected' = its decisive flip (600/1,000-ft gap, 400-ft margin), already applied in formation_blueox — so corrected rows here were flipped INTO this bench. "
        "<b>consensus v2 (re-implemented)</b>: clean witnesses ≤ 1.5 mi (real survey, non-round TVD, ≥ 6 mo online), band = ≥ 3 witnesses with IQR ≤ 150 ft, complexes merge bands < 100 ft apart; "
        "flag = sits ≤ 120 ft inside another band while own band is absent / incoherent / ≥ 2× farther and the runner-up is ≥ 1.5× farther; sand↔carbonate swaps within one interval are 'ambiguous_lith', never flags.</p>"
    )
    p.append(_table(
        ["measure", "value"],
        [
            ["sql/23: flipped into this bench (formation_blueox_tvd_corrected)", _fmt(s["n_tvd_corrected_in"])],
            ["sql/23: nearest band ≠ assigned (any margin)", f"{_fmt(s['sql23_disagree_n'])} ({_fmt(s['sql23_disagree_share'], pct=True)})"],
            ["consensus: flag", f"{_fmt(s['cons_flag_n'])} ({_fmt(s['cons_flag_share'], pct=True)} of bench; {_fmt(s['cons_flag_share_scored'], pct=True)} of scored)"],
            ["consensus: flag share TX / NM-actual / NM-planned", f"{_fmt(s['tx_cons_flag_share'], pct=True)} / {_fmt(s['nm_actual_cons_flag_share'], pct=True)} / {_fmt(s['nm_planned_cons_flag_share'], pct=True)}"],
            ["consensus: ambiguous_lith (sand↔carb, depth cannot resolve)", _fmt(s["cons_lith_n"])],
            ["consensus: flagged INTO this bench from other benches", f"{_fmt(s['cons_inbound_n'])}  {_esc(s['cons_inbound_from'])}"],
        ],
    ))
    p.append("<div class=row><div><h3>consensus status</h3>" + _counts_table(s["cons_status_counts"]) + "</div>"
             "<div><h3>consensus flags → suggested bench</h3>" + _counts_table(s["cons_suggest_counts"]) + "</div>"
             "<div><h3>sql/23 disagreements → nearest band</h3>" + _counts_table(s["sql23_nearest_counts"]) + "</div></div>")
    p.append(f"<div class=row><img src=\"{tag_qc_map(ctx, b, bench)}\"><img src=\"{perf_map(ctx, b, bench)}\"></div>")
    p.append("<h3>Adjacent-bench depth separation where both bands are coherent in the same 1.5-mi neighbourhood</h3>"
             "<p>other band median − own band median, ft (positive = the other bench sits deeper). 'within 100 ft' = the two bands merge into one complex there — depth cannot tell the tags apart, so swaps in that neighbourhood are ambiguous, not flags. "
             "'inverted' = the sign is opposite to the overall median (the stack order flips locally — a tagging tell).</p>")
    p.append(_table(
        ["other bench", "neighbourhoods", "median sep ft", "p25", "p75", "within 100 ft", "inverted", "TX n / med / within100", "NM n / med / within100"],
        [[r["other"], _fmt(r["n_hoods"]), _fmt(r["med_sep_ft"], 0), _fmt(r["p25_sep_ft"], 0), _fmt(r["p75_sep_ft"], 0), _fmt(r["share_within_100ft"], pct=True), _fmt(r["share_inverted"], pct=True),
          f"{_fmt(r['n_tx'])} / {_fmt(r['med_sep_ft_tx'], 0)} / {_fmt(r['share_within_100ft_tx'], pct=True)}", f"{_fmt(r['n_nm'])} / {_fmt(r['med_sep_ft_nm'], 0)} / {_fmt(r['share_within_100ft_nm'], pct=True)}"]
         for r in s["pair_separation"]],
    ))
    # --- state line
    p.append("<h2 id=stateline>3. State-line check</h2>")
    p.append("<p>10-mi bins of signed distance from 32° N (lateral midpoint; 69 mi/deg). Density ≈ wells ÷ (10 mi × the bin's 2.5–97.5 % east–west span) — a coarse strip density, judged only for bins with ≥ 20 wells. Median 12-mo oil/ft is on the D9 cohort with n per bin. A step in oil/ft or in planned share that lines up with the border and does not line up with TVD is a tagging artifact.</p>")
    cls = {"flag": "flag bad", "no_step": "flag ok", "not_judged": "flag"}[bs["verdict"]]
    if bs["verdict"] == "not_judged":
        txt = f"Border step not judged: {_esc(bs['reason'])}."
    else:
        txt = (f"Border bins (−10..0 vs 0..10): median 12-mo oil/ft relative step {_fmt(bs['border_rel_step'], pct=True)}; "
               f"typical adjacent-bin step elsewhere {_fmt(bs['typical_rel_step'], pct=True)} (max {_fmt(bs['max_other_rel_step'], pct=True)}, {bs['n_other_steps']} pairs). "
               + ("<b>FLAG — step lines up with the border.</b>" if bs["verdict"] == "flag" else "No border-aligned step beyond the typical bin-to-bin variation."))
    p.append(f"<div class='{cls}'>{txt}</div>")
    p.append(f"<div class=row>{state_line_fig(bins, bench)}</div>")
    p.append(_table(
        ["bin (mi)", "side", "producing hz", "NM-tagged", "≈ wells/sq mi", "planned %", "round-TVD %", "median TVD ft", "cohort n", "median oil12 /kft", "p25", "p75"],
        [[f"{int(r.bin_lo_mi):+d}..{int(r.bin_hi_mi):+d}", r.side, _fmt(r.n_prod_hz), _fmt(r.n_nm_tagged), _fmt(r.density_per_sqmi, 2), _fmt(r.planned_share, pct=True), _fmt(r.round_tvd_share, pct=True), _fmt(r.med_tvd_ft, 0), _fmt(r.n_cohort), _fmt(r.med_oil12_kft, 0), _fmt(r.p25_oil12_kft, 0), _fmt(r.p75_oil12_kft, 0)] for r in bins.itertuples() if r.n_prod_hz > 0],
    ))
    # --- NM decision
    p.append("<h2 id=nm>4. NM planned-survey wells — decision input (gate 1, §9)</h2>")
    p.append(f"<p>{_fmt(s['nm_planned_n'])} NM wells in this bench carry a pre-drill planned survey (their TVD and therefore their bench tag are provisional). "
             f"Cohort median 12-mo oil/ft: NM planned {_fmt(s['cohort_med_oil12_kft_nm_planned'], 0)} (n={_fmt(s['n_cohort_nm_planned'])}) vs NM actual-survey {_fmt(s['cohort_med_oil12_kft_nm_actual'], 0)} (n={_fmt(s['n_cohort_nm_actual'])}) vs TX {_fmt(s['cohort_med_oil12_kft_tx'], 0)} (n={_fmt(s['n_cohort_tx'])}). "
             f"sql/23 disagreement share: NM planned {_fmt(s['nm_planned_sql23_disagree_share'], pct=True)} vs NM actual {_fmt(s['nm_actual_sql23_disagree_share'], pct=True)}.</p>")
    p.append("<div class=row><div><h3>consensus status of NM planned-survey wells</h3>" + _counts_table(s["nm_planned_cons_status"]) + "</div>"
             "<div><h3>their flags → suggested bench</h3>" + _counts_table(s["nm_planned_cons_suggest"]) + "</div></div>")
    oa, ob, oc = s["option_a_cohort"], s["option_b_cohort"], s["option_current_cohort"]
    p.append("<h3>Effect on the D9 cohort under each option</h3>" + _table(
        ["option", "cohort TX", "cohort NM", "note"],
        [
            ["current (tags as-is)", _fmt(oc["tx"]), _fmt(oc["nm"]), ""],
            ["A — reassign planned-survey wells by local depth consensus (BOX-only, no warehouse change)", _fmt(oa["tx"]), _fmt(oa["nm"]), f"{_fmt(oa['reassigned_out'])} planned wells leave this bench on a consensus flag; {_fmt(oa['reassigned_in'])} planned wells from other benches would join it"],
            ["B — exclude all planned-survey wells from edge + cohort evidence", _fmt(ob["tx"]), _fmt(ob["nm"]), f"{_fmt(ob['excluded'])} wells (all planned, any state) drop from evidence"],
        ],
    ))
    # --- well set
    p.append("<h2 id=wells>5. The well set for gate 1</h2>")
    role = b["qc_role"].value_counts().to_dict()
    p.append("<p>Per-well CSV beside this page (<code>wells_" + bench + ".csv</code>): every producing horizontal with its flags and a proposed role — <b>evidence</b> (no flag), <b>review</b> (planned survey, permit-round TVD, or a consensus flag). The role is a proposal; gate 1 is Michael's confirmation.</p>")
    p.append(_counts_table(role))
    fl = b[b["cons_status"] == "flag"].sort_values("cons_nearest_delta")
    p.append(f"<details><summary>consensus flags ({len(fl)}) — nearest first</summary>" + _table(
        ["api10", "well", "operator", "state", "fp", "TVD", "planned", "own band med (n)", "own Δ", "suggest", "band Δ", "witnesses", "sql/23 nearest"],
        [[r.api10, r.well_name, r.operator, "NM" if r.state_code == NM_FIPS else "TX", r.first_production_date, _fmt(r.tvd_ft, 0), "Y" if r.planned else "", f"{_fmt(r.cons_own_med, 0)} ({_fmt(r.cons_own_n)})", _fmt(r.cons_own_delta, 0), r.cons_suggest, _fmt(r.cons_nearest_delta, 0), _fmt(r.cons_n_witness), r.sql23_nearest] for r in fl.itertuples()],
    ) + "</details>")
    p.append("</body></html>")
    out.write_text("".join(p), encoding="utf-8")
    return out


def render_index(summaries: list[dict[str, Any]], out: Path, run_meta: dict[str, Any]) -> Path:
    p = [f"<!doctype html><html><head><meta charset=\"utf-8\"><title>BOX step 1 — bench QC</title><style>{_CSS}</style></head><body>",
         "<h1>BOX step 1 — bench QC, Delaware pilot benches</h1>",
         f"<div class=meta>Built {_esc(run_meta['built_at'])} from the live warehouse (read-only). Plan: docs/box_type_curves_plan.md §5 step 1. Grain: producing horizontals.</div>"]
    rows = []
    for s in summaries:
        bs = s["border_step"]
        rows.append([
            f"<a href=qc_{s['bench']}.html>{s['bench']}</a>", _fmt(s["n_prod_hz"]), _fmt(s["n_tx"]), _fmt(s["n_nm"]), _fmt(s["n_cohort"]),
            _fmt(s["planned_share"], pct=True), _fmt(s["planned_share_nm"], pct=True), _fmt(s["round_tvd_share"], pct=True),
            _fmt(s["sql23_disagree_share"], pct=True), f"{_fmt(s['cons_flag_n'])} ({_fmt(s['cons_flag_share'], pct=True)})", _fmt(s["cons_lith_n"]),
            _fmt(s["cohort_med_oil12_kft"], 0), bs["verdict"] + ("" if bs["verdict"] == "not_judged" else f" ({_fmt(bs['border_rel_step'], pct=True)} vs typical {_fmt(bs['typical_rel_step'], pct=True)})"),
        ])
    h = ["bench", "producing hz", "TX", "NM", "D9 cohort", "planned %", "planned % (NM)", "round-TVD %", "sql/23 disagree %", "consensus flags", "lith-ambiguous", "cohort med oil12 / kft", "border step"]
    hh = "".join(f"<th>{_esc(x)}</th>" for x in h)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    p.append(f"<table><thead><tr>{hh}</tr></thead><tbody>{body}</tbody></table>")
    p.append("<p>Per-bench pages carry the maps, the state-line plot, the NM planned-survey decision input and the per-well CSV. The consensus detector here is a re-implementation from recorded rules, not the ratified 2026-09 script — see each page §2.</p>")
    p.append("</body></html>")
    out.write_text("".join(p), encoding="utf-8")
    return out


def assign_roles(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    reasons = []
    for r in df.itertuples():
        why = []
        if r.planned:
            why.append("planned_survey")
        if r.tvd_round:
            why.append("permit_round_tvd")
        if r.cons_status == "flag":
            why.append(f"consensus_flag->{r.cons_suggest}")
        if r.cons_status == "ambiguous_lith":
            why.append(f"lith_ambiguous->{r.cons_suggest}")
        reasons.append(";".join(why))
    df["qc_reason"] = reasons
    df["qc_role"] = np.where(df["qc_reason"] == "", "evidence", "review")
    return df


WELL_COLS = [
    "api10", "well_name", "operator", "state_code", "county", "formation_blueox", "formation_blueox_base",
    "formation_blueox_source", "formation_blueox_tvd_corrected", "planned", "tvd_ft", "tvd_round",
    "lateral_length_ft", "first_production_date", "cum_12m_oil_bbl", "oil12_kft", "cohort",
    "mid_lon", "mid_lat", "sql23_nearest", "sql23_assigned_gap", "sql23_nearest_gap", "sql23_disagree",
    "sql23_corrected", "cons_status", "cons_n_witness", "cons_own_med", "cons_own_n", "cons_own_delta",
    "cons_nearest", "cons_nearest_delta", "cons_suggest", "qc_role", "qc_reason",
]


def run(conn: Any, out_dir: Path, benches: tuple[str, ...] = PILOT_BENCHES) -> dict[str, Any]:
    """Pull, score, summarise, render. Returns the summary dict (also written as summary.json)."""

    out_dir.mkdir(parents=True, exist_ok=True)
    df = pull_delaware_producers(conn)
    df = score_consensus(df)
    df = assign_roles(df)
    summaries = []
    for bench in benches:
        s = bench_summary(df, bench)
        render_bench_page(df, s, out_dir / f"qc_{bench}.html")
        df.loc[df["formation_blueox"] == bench, WELL_COLS].sort_values("api10").to_csv(out_dir / f"wells_{bench}.csv", index=False)
        summaries.append(s)
    meta = {"built_at": _dt.datetime.now(tz=_dt.UTC).astimezone().isoformat(timespec="seconds"), "asof": str(df.attrs.get("asof")),
            "n_delaware_prod_hz": len(df), "n_witness": int(df["cons_witness"].sum()),
            "consensus_params": asdict(ConsensusParams()), "benches": list(benches)}
    render_index(summaries, out_dir / "index.html", meta)
    (out_dir / "summary.json").write_text(json.dumps({"meta": meta, "benches": summaries}, indent=1, default=str), encoding="utf-8")
    return {"meta": meta, "benches": summaries}
