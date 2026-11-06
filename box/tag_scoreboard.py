"""formation_blueox scoreboard — step 0 of docs/formation_tag_redesign/PLAN.md.

Scores a CANDIDATE tag column on producing horizontals. Nothing here re-tags anything or writes to the warehouse.
The pull is read-only (SET TRANSACTION READ ONLY).

Three families of measure, in the order the plan ranks them (PLAN §2: independent evidence first):

  (a) grid  — agreement with the geologist's V5 structure grids (Delaware only), station by station along the
              lateral where the well has a survey, else at the midpoint. It reuses box.tops_qc: TAG_INTERVAL
              (rule A: one WCA interval; WCB_2 / WCC share B2 -> C) and apply_geology_rules (no_surface / held /
              no_control / surface_suspect). "controlled" = the tag's top AND base surfaces both have a geologist
              pick within extent_package.TRUST_MAX_FT.
  (b) labels — reproduction of the human calls: seeds/formation_tag_overrides.csv (tiers `carded` / `class_accepted`)
              plus the Lea/Eddy rule-V card calls (docs/lea_eddy_wc_tags, tier `carded`) and their holds (tier
              `hold`; a hold is a case a rule should ABSTAIN on, so it is counted, never scored right/wrong).
  (c) self  — consistency with neighbours: the band test (a well > MARGIN ft closer to an adjacent bench's local
              median than to its own), close-pair inversions (pairs within PAIR_MI on different benches whose depth
              order contradicts the bench order by > INV ft), and band separation per adjacent bench pair. A rule
              that copies its neighbours scores perfectly here, so (c) never passes a rule on its own.

Evidence (PLAN §2.4): planned surveys are never evidence. Depth = lateral median survey TVD (sql/64
lat_tvd_p50_ft) where the well has one, else tvd_ft, which must not be a round 100. Depths < 4,000 ft are data
errors (tops-QC MIN_EVIDENCE_TVD_FT). The `tvd_ft` basis is kept as a sensitivity that ties back to the
2026-11-05 audit.

Neighbours: the minimum distance between NPTS points along each lateral (wellstick, EPSG:3083 metres), same basin.
Bench order = the canonical strat column (.claude/skills/deal-intake/config/strat_column.yaml).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent.parent
STRAT_YAML = ROOT / ".claude" / "skills" / "deal-intake" / "config" / "strat_column.yaml"
OVERRIDE_SEED = ROOT / "seeds" / "formation_tag_overrides.csv"
LEA_EDDY_DIR = ROOT / "docs" / "lea_eddy_wc_tags"
BASINS = ("delaware", "midland")
M_PER_MI = 1609.344
MIN_EVIDENCE_TVD_FT = 4_000.0
NPTS = 10
CANDIDATES = {
    "live": "wells_enriched.formation_blueox: overrides + sql/23 correction (what downstream reads)",
    "pre_sql23": "wells_enriched.formation_blueox_base: overrides, no sql/23 correction",
    "vendor": "ref.formation_crosswalk on the sql/16 vendor string only (no override, no sql/23)",
}
VINTAGES = (0, 2014, 2017, 2020, 2023, 2100)
VINTAGE_LABELS = ("<=2014", "2015-17", "2018-20", "2021-23", "2024+")


@dataclass(frozen=True)
class Params:
    radius_mi: float = 1.0      # band-test neighbourhood
    pair_mi: float = 0.25       # close-pair inversion distance
    margin_ft: float = 25.0     # band test: closer to the adjacent band by more than this
    inv_ft: float = 50.0        # pair inversion: depth order contradicts bench order by more than this
    min_band_n: int = 3         # wells a local band needs
    min_sep_n: int = 50         # neighbourhoods a band-separation row needs


DEFAULT = Params()


# ----------------------------------------------------------------------------
# Bench order
# ----------------------------------------------------------------------------


def bench_order(path: Path = STRAT_YAML) -> dict[str, list[str]]:
    """Shallow -> deep formation_blueox codes per basin, from the canonical strat column."""
    col = yaml.safe_load(path.read_text(encoding="utf-8"))["column"]
    return {b: list(col[b]) for b in BASINS}


def adjacent_pairs(order: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    return [(b, cs[k], cs[k + 1]) for b, cs in order.items() for k in range(len(cs) - 1)]


# ----------------------------------------------------------------------------
# Evidence
# ----------------------------------------------------------------------------


def evidence_depth(df: pd.DataFrame, basis: str = "best") -> pd.DataFrame:
    """Adds depth_ft, depth_source and clean. basis 'best' = survey lateral median where present, else tvd_ft;
    'tvd_ft' = tvd_ft only (the audit's basis)."""
    d = df.copy()
    planned = d["planned"].fillna(False).astype(bool)
    tvd = pd.to_numeric(d["tvd_ft"], errors="coerce")
    sv = pd.to_numeric(d.get("lat_tvd_p50_ft"), errors="coerce") if "lat_tvd_p50_ft" in d else pd.Series(np.nan, index=d.index)
    use_sv = (basis == "best") & sv.notna()
    d["depth_ft"] = np.where(use_sv, sv, tvd)
    d["depth_source"] = np.where(use_sv, "survey", np.where(tvd.notna(), "tvd_ft", "none"))
    round100 = tvd.notna() & (tvd % 100 == 0)
    d["clean"] = (
        ~planned
        & pd.Series(d["depth_ft"], index=d.index).notna()
        & (d["depth_ft"] >= MIN_EVIDENCE_TVD_FT)
        & ((d["depth_source"] == "survey") | ~round100)
    )
    return d


# ----------------------------------------------------------------------------
# Neighbours (geometry only: computed once per radius, shared by every candidate)
# ----------------------------------------------------------------------------


def parse_points(wkt: str | None, fallback: tuple[float, float] | None = None) -> list[tuple[float, float]]:
    """MULTIPOINT / POINT WKT -> [(x, y)]; the fallback point when the WKT is missing."""
    if not isinstance(wkt, str) or not wkt.strip():
        return [fallback] if fallback is not None and np.all(np.isfinite(fallback)) else []
    body = wkt[wkt.index("(") + 1: wkt.rindex(")")].replace("(", "").replace(")", "")
    return [tuple(map(float, p.split())) for p in body.split(",") if p.strip()]


def neighbour_pairs(df: pd.DataFrame, radius_m: float) -> pd.DataFrame:
    """Directed pairs (i, j, d_m) of positional row indices whose laterals come within radius_m, same basin.
    df needs `pts` (list of (x, y) in metres) and `basin`."""
    xy, own = [], []
    for i, p in enumerate(df["pts"]):
        xy.extend(p)
        own.extend([i] * len(p))
    if not xy:
        return pd.DataFrame(columns=["i", "j", "d"])
    xy_a, own_a = np.asarray(xy, float), np.asarray(own, int)
    pr = cKDTree(xy_a).query_pairs(radius_m, output_type="ndarray")
    a, b = own_a[pr[:, 0]], own_a[pr[:, 1]]
    keep = a != b
    dist = np.linalg.norm(xy_a[pr[keep, 0]] - xy_a[pr[keep, 1]], axis=1)
    a, b = a[keep], b[keep]
    out = pd.DataFrame({"i": np.r_[a, b], "j": np.r_[b, a], "d": np.r_[dist, dist]}).groupby(["i", "j"], as_index=False)["d"].min()
    basin = df["basin"].to_numpy()
    return out[basin[out["i"]] == basin[out["j"]]].reset_index(drop=True)


# ----------------------------------------------------------------------------
# (c) self-consistency
# ----------------------------------------------------------------------------


def local_bands(df: pd.DataFrame, tag_col: str, pairs: pd.DataFrame, min_n: int) -> pd.DataFrame:
    """Per subject i and neighbour bench: median depth and count (bench needs >= min_n neighbours)."""
    p = pairs.assign(code=df[tag_col].to_numpy()[pairs["j"]], depth=df["depth_ft"].to_numpy()[pairs["j"]])
    g = p.groupby(["i", "code"])["depth"].agg(med="median", n="size").reset_index()
    return g[g["n"] >= min_n].reset_index(drop=True)


def band_test(df: pd.DataFrame, tag_col: str, bands: pd.DataFrame, order: dict[str, list[str]], margin_ft: float) -> pd.DataFrame:
    """Per well: own-band median, the adjacent bench it sits closer to (by > margin_ft) if any, and a status:
    'agree' / 'disagree' / 'untestable' (no own band) / 'off_column' (tag not in the basin's column)."""
    med = {(i, c): m for i, c, m in zip(bands["i"], bands["code"], bands["med"], strict=True)}
    status, closer, own_med, gap = [], [], [], []
    for i, (basin, tag, dep) in enumerate(zip(df["basin"], df[tag_col], df["depth_ft"], strict=True)):
        cs = order.get(basin, [])
        if tag not in cs:
            status.append("off_column"); closer.append(None); own_med.append(np.nan); gap.append(np.nan)
            continue
        om = med.get((i, tag))
        if om is None:
            status.append("untestable"); closer.append(None); own_med.append(np.nan); gap.append(np.nan)
            continue
        k, best = cs.index(tag), None
        for kk in (k - 1, k + 1):
            if 0 <= kk < len(cs):
                m = med.get((i, cs[kk]))
                if m is not None and abs(dep - m) + margin_ft < abs(dep - om) and (best is None or abs(dep - m) < abs(dep - best[1])):
                    best = (cs[kk], m)
        status.append("disagree" if best else "agree")
        closer.append(best[0] if best else None)
        own_med.append(om)
        gap.append(abs(dep - om) - abs(dep - best[1]) if best else np.nan)
    return pd.DataFrame({"band_status": status, "closer_bench": closer, "own_band_med": own_med, "closer_by_ft": gap}, index=df.index)


def pair_inversions(df: pd.DataFrame, tag_col: str, pairs: pd.DataFrame, order: dict[str, list[str]],
                    pair_m: float, inv_ft: float) -> pd.DataFrame:
    """Undirected close pairs on different in-column benches: i = the shallower-tagged well. inverted = i sits
    deeper than j by more than inv_ft. `rank_gap` = how many benches apart (1 = adjacent)."""
    rank = {(b, c): k for b, cs in order.items() for k, c in enumerate(cs)}
    p = pairs[pairs["d"] <= pair_m]
    tag, basin, dep = df[tag_col].to_numpy(), df["basin"].to_numpy(), df["depth_ft"].to_numpy(float)
    ri = np.array([rank.get((b, t), np.nan) for b, t in zip(basin[p["i"]], tag[p["i"]], strict=True)], float)
    rj = np.array([rank.get((b, t), np.nan) for b, t in zip(basin[p["j"]], tag[p["j"]], strict=True)], float)
    keep = np.isfinite(ri) & np.isfinite(rj) & (ri < rj)
    q = p[keep]
    out = pd.DataFrame({"i": q["i"].to_numpy(), "j": q["j"].to_numpy(), "basin": basin[q["i"]],
                        "tag_i": tag[q["i"]], "tag_j": tag[q["j"]], "rank_gap": (rj - ri)[keep].astype(int),
                        "dz_ft": dep[q["i"]] - dep[q["j"]]})
    out["inverted"] = out["dz_ft"] > inv_ft
    return out


def band_separation(df: pd.DataFrame, bands: pd.DataFrame, order: dict[str, list[str]], min_n: int) -> pd.DataFrame:
    """Per adjacent bench pair: across neighbourhoods holding both bands, median gap (deeper minus shallower band
    median), share inverted (< 0) and share < 50 ft."""
    wide = bands.pivot(index="i", columns="code", values="med")
    basin = pd.Series(df["basin"].to_numpy()[wide.index], index=wide.index)
    rows = []
    for b, up, dn in adjacent_pairs(order):
        if up not in wide or dn not in wide:
            continue
        g = (wide[dn] - wide[up])[basin == b].dropna()
        if len(g) < min_n:
            continue
        rows.append({"basin": b, "upper": up, "lower": dn, "n_hoods": len(g), "median_gap_ft": float(g.median()),
                     "inverted_pct": 100 * float((g < 0).mean()), "under_50ft_pct": 100 * float((g < 50).mean())})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# (b) labelled set
# ----------------------------------------------------------------------------


def labelled_set(root: Path = ROOT) -> pd.DataFrame:
    """api10, label (the human call), tier, source. One row per well; a later source never overrides an earlier."""
    s = pd.read_csv(root / "seeds" / "formation_tag_overrides.csv", dtype={"api10": str})
    s["tier"] = np.where(s["note"].fillna("").str.contains("class-accepted"), "class_accepted", "carded")
    s["source"] = "seeds/formation_tag_overrides.csv"
    parts = [s.rename(columns={"corrected_code": "label"})[["api10", "label", "tier", "source"]]]
    le = root / "docs" / "lea_eddy_wc_tags"
    if (le / "proposed_override_seed.csv").exists():
        v = pd.read_csv(le / "proposed_override_seed.csv", dtype={"api10": str})
        v = v[v["note"].fillna("").str.contains("ratified by MM")]
        parts.append(v.assign(tier="carded", source="docs/lea_eddy_wc_tags (rule V)")
                     .rename(columns={"corrected_code": "label"})[["api10", "label", "tier", "source"]])
        c = pd.read_csv(le / "cards_sample.csv", dtype={"api10": str})
        verdict = c["verdict"].fillna("").astype(str).str.strip()
        hold = (verdict != "") & ~verdict.str.fullmatch(r"[A-Z0-9_]+") & ~verdict.str.lower().isin(["agree", "reject"])
        parts.append(c[hold].assign(label=None, tier="hold", source="docs/lea_eddy_wc_tags (rule V hold)")[["api10", "label", "tier", "source"]])
    out = pd.concat(parts, ignore_index=True)
    return out.drop_duplicates("api10", keep="first").reset_index(drop=True)


def label_score(df: pd.DataFrame, tag_col: str, labels: pd.DataFrame) -> pd.DataFrame:
    """Per tier: labelled wells found in the frame, how many the candidate reproduces. Holds report n only."""
    m = labels.merge(df[["api10", "basin", tag_col]], on="api10", how="inner")
    rows = []
    for (tier, basin), g in m.groupby(["tier", "basin"]):
        rep = int((g[tag_col] == g["label"]).sum()) if tier != "hold" else None
        rows.append({"tier": tier, "basin": basin, "n": len(g), "reproduced": rep,
                     "reproduced_pct": (100 * rep / len(g)) if rep is not None and len(g) else None})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# (a) geologist grids (Delaware)
# ----------------------------------------------------------------------------


def grid_verdicts(stations: pd.DataFrame, depths: np.ndarray, tags: pd.Series, county: pd.Series) -> pd.DataFrame:
    """Per-well grid verdict for one candidate. ``stations`` columns api10 (+ anything); ``depths`` = the
    (N_stations, len(tops_qc.STACK)) grid depths sampled ONCE; ``tags`` / ``county`` indexed by api10.
    verdict = majority-in-interval (tops_qc.well_summary semantics), then tops_qc.apply_geology_rules."""
    from box import tops_qc as tq

    col = {s: k for k, s in enumerate(tq.STACK)}
    t = stations["api10"].map(tags)
    ti = t.map(tq.TAG_TOP).map(col).to_numpy(float)
    bi = t.map(lambda x: tq.TAG_INTERVAL[x][1] if x in tq.TAG_INTERVAL else None).map(col).to_numpy(float)
    known = np.isfinite(ti) & np.isfinite(bi)
    top = np.full(len(stations), np.nan)
    base = np.full(len(stations), np.nan)
    r = np.where(known)[0]
    top[r] = depths[r, ti[known].astype(int)]
    base[r] = depths[r, bi[known].astype(int)]
    miss = tq.signed_miss(stations["tvd"].to_numpy(float), top, base)
    f = pd.DataFrame({"api10": stations["api10"].to_numpy(), "miss": miss})
    f = f[np.isfinite(f["miss"])]
    g = f.groupby("api10")["miss"]
    w = pd.DataFrame({"pct_in": g.apply(lambda s: float((s == 0).mean())),
                      "pct_above": g.apply(lambda s: float((s < 0).mean())),
                      "pct_below": g.apply(lambda s: float((s > 0).mean())),
                      "miss_p50": g.median()})
    w["verdict_raw"] = np.select([w["pct_in"] >= 0.5, w["pct_above"] >= w["pct_below"]], ["agree", "shallow"], default="deep")
    out = pd.DataFrame(index=tags.index)
    out = out.join(w)
    out["verdict_raw"] = out["verdict_raw"].fillna("unmeasured")
    out["grid_verdict"] = [tq.apply_geology_rules(str(tg), c if isinstance(c, str) else None, v)
                           for tg, c, v in zip(tags.reindex(out.index), county.reindex(out.index), out["verdict_raw"], strict=True)]
    return out


def controlled(tags: pd.Series, xy: np.ndarray, dist: dict[str, np.ndarray], trust_ft: float) -> np.ndarray:
    """True where the tag's top AND base surfaces have a pick within trust_ft at the well midpoint.
    ``dist`` = {surface: distance array aligned with tags}."""
    from box import tops_qc as tq

    out = np.zeros(len(tags), bool)
    for k, t in enumerate(tags):
        if t not in tq.TAG_INTERVAL:
            continue
        top, base = tq.TAG_INTERVAL[t]
        dt_, db_ = dist.get(top, np.full(len(tags), np.nan))[k], dist.get(base, np.full(len(tags), np.nan))[k]
        out[k] = bool(np.isfinite(dt_) and np.isfinite(db_) and dt_ <= trust_ft and db_ <= trust_ft)
    return out


# ----------------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------------


def vintage(fp: pd.Series) -> pd.Series:
    yr = pd.to_datetime(fp, errors="coerce").dt.year
    return pd.cut(yr, list(VINTAGES), labels=list(VINTAGE_LABELS)).astype(object)


def band_table(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Band-test rates grouped by `by` (df carries band_status)."""
    g = df.groupby(by, dropna=False)
    t = pd.DataFrame({"wells": g.size(), "testable": g["band_status"].apply(lambda s: int(s.isin(["agree", "disagree"]).sum())),
                      "disagree": g["band_status"].apply(lambda s: int((s == "disagree").sum()))})
    t["disagree_pct"] = np.where(t["testable"] > 0, 100 * t["disagree"] / t["testable"].where(t["testable"] > 0), np.nan)
    return t.reset_index()


def inversion_table(inv: pd.DataFrame) -> pd.DataFrame:
    inv = inv.assign(span=np.where(inv["rank_gap"] == 1, "adjacent", "2+ apart"))
    g = inv.groupby(["basin", "span"])
    t = pd.DataFrame({"pairs": g.size(), "inverted": g["inverted"].sum()})
    t["inverted_pct"] = 100 * t["inverted"] / t["pairs"]
    return t.reset_index()


def grid_table(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Grid agreement among scored verdicts (agree / shallow / deep), overall and inside control."""
    s = df[df["grid_verdict"].isin(["agree", "shallow", "deep"])]
    rows = []
    for key, g in s.groupby(by, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        c = g[g["grid_controlled"]]
        rows.append({**dict(zip(by, key, strict=True)), "scored": len(g), "agree_pct": 100 * float((g["grid_verdict"] == "agree").mean()),
                     "controlled": len(c), "agree_controlled_pct": 100 * float((c["grid_verdict"] == "agree").mean()) if len(c) else np.nan,
                     "shallow_pct": 100 * float((g["grid_verdict"] == "shallow").mean()), "deep_pct": 100 * float((g["grid_verdict"] == "deep").mean())})
    return pd.DataFrame(rows)


def score_candidate(df: pd.DataFrame, tag_col: str, pairs_r: pd.DataFrame, pairs_pair: pd.DataFrame,
                    order: dict[str, list[str]], labels: pd.DataFrame, p: Params = DEFAULT) -> dict[str, Any]:
    """Everything (b) and (c) need for one candidate on a CLEAN frame (positional index 0..n-1)."""
    bands = local_bands(df, tag_col, pairs_r, p.min_band_n)
    bt = band_test(df, tag_col, bands, order, p.margin_ft)
    scored = df.join(bt)
    inv = pair_inversions(df, tag_col, pairs_pair, order, p.pair_mi * M_PER_MI, p.inv_ft)
    return {"frame": scored, "bands": bands, "inversions": inv, "separation": band_separation(df, bands, order, p.min_sep_n),
            "labels": label_score(df, tag_col, labels)}


# ----------------------------------------------------------------------------
# Pull (read-only)
# ----------------------------------------------------------------------------

_WELLS_SQL = """
SELECT w.api10, w.basin_blueox AS basin, w.state_code, w.county, w.current_operator AS operator, w.well_name,
       w.formation_blueox AS live, w.formation_blueox_base AS pre_sql23, fx.canonical_code AS vendor,
       w.formation_blueox_raw AS vendor_raw, w.formation_blueox_source AS live_source,
       w.formation_blueox_tvd_corrected AS sql23_corrected,
       w.directional_survey_is_planned AS planned, w.tvd_ft, s.lat_tvd_p50_ft,
       w.first_production_date, w.lateral_length_ft, w.midpoint_lon, w.midpoint_lat,
       CASE WHEN extensions.ST_GeometryType(w.wellstick_geom) = 'ST_LineString'
            THEN extensions.ST_AsText(extensions.ST_LineInterpolatePoints(
                     extensions.ST_Transform(w.wellstick_geom, 3083), %(frac)s, true)) END AS pts_wkt,
       CASE WHEN w.midpoint_lon IS NOT NULL THEN extensions.ST_AsText(extensions.ST_Transform(
                 extensions.ST_SetSRID(extensions.ST_MakePoint(w.midpoint_lon, w.midpoint_lat), 4326), 3083)) END AS mid_wkt
FROM curated.wells_enriched w
LEFT JOIN curated.well_lateral_survey s ON s.api10 = w.api10
LEFT JOIN ref.formation_crosswalk fx ON fx.basin = w.basin_blueox AND fx.raw_value = w.formation_blueox_raw
WHERE w.basin_blueox IN ('delaware', 'midland')
  AND w.is_horizontal
  AND w.first_production_date IS NOT NULL
"""


def _read(conn: Any, sql: str, params: dict[str, Any]) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=cols)


def pull_wells(conn: Any) -> pd.DataFrame:
    d = _read(conn, _WELLS_SQL, {"frac": 1.0 / NPTS})
    for c in ("tvd_ft", "lat_tvd_p50_ft", "lateral_length_ft", "midpoint_lon", "midpoint_lat"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["api10"] = d["api10"].astype(str)
    mids = [parse_points(m) for m in d["mid_wkt"]]
    d["pts"] = [parse_points(w, m[0] if m else None) for w, m in zip(d["pts_wkt"], mids, strict=True)]
    return d.drop(columns=["pts_wkt", "mid_wkt"])
