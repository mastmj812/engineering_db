"""BOX sticks, phase 0: baseline evidence (read-only) -- docs/box_sticks_plan.md.

    python -m scripts.box_sticks_phase0 --out docs/box_sticks/phase0-<date> [--cache <dir>]

Three audits, nothing written to the warehouse:
  0a  TVD bust     Novi PUD/RES stick TVD minus the landing depth of same-code producers at the stick
                   (box.landing_surfaces.estimate: clean wells within 2 mi, >= 3, nearest within 1 mi). Run on the
                   live tags and on the shadow rule tags (curated.formation_tag_rule.applied_code where applied).
  0b  DSU polygons raw_novi_intel.pads, newest vintage: size, shape, overlap, BOX extent coverage, producers outside.
  0c  Laterals     Novi stick lateral length vs the lateral a straight or U-turn well gets in its own polygon.

Evidence wells follow the tag rule (box.tag_scoreboard.evidence_depth): survey lateral median TVD else tvd_ft; planned
surveys, round-100 TVDs without a survey and depths under 4,000 ft are never evidence. Coordinates are EPSG:3083 m.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from box import landing_surfaces as ls
from box import tag_scoreboard as sb

FT_PER_M = 3.280839895
P = ls.PARAMS
SETBACK_FT = 330.0          # per side, the narvi / deal-intake default
UTURN_BELOW_FT = 7_000.0    # plan decision 2026-11-12: a shorter straight lateral becomes a U-turn
BUST_FT = (150.0, 300.0)
PAD_VINTAGE = "2026Q3"
PRODUCER_SINCE = 2016

_STICKS_SQL = """
SELECT il.stick_id, il.basin, il.category, il.pad_name, il.county, il.tvd, il.ll_ft,
       fb.formation_blueox AS code, fb.formation_blueox_source AS code_source,
       extensions.ST_Length(il.wellstick_geom::extensions.geography) * 3.280839895 AS geom_len_ft,
       extensions.ST_X(extensions.ST_Transform(extensions.ST_PointOnSurface(il.wellstick_geom), 3083)) AS x,
       extensions.ST_Y(extensions.ST_Transform(extensions.ST_PointOnSurface(il.wellstick_geom), 3083)) AS y
FROM curated.intel_locations il
JOIN curated.intel_formation_blueox fb USING (stick_id)
WHERE il.category IN ('PUD', 'RES') AND il.wellstick_geom IS NOT NULL
"""
_EXTENTS_SQL = """
SELECT basin, bench, extent_id, extensions.ST_AsText(extensions.ST_Transform(geom, 3083)) AS wkt
FROM box.extent WHERE is_record
"""
_PADS_SQL = """
SELECT pad_id, basin, pad_name, operator, well_cnt, ll_sum_ft,
       extensions.ST_AsText(extensions.ST_Transform(geom, 3083)) AS wkt
FROM raw_novi_intel.pads WHERE report_version = %(v)s
"""
_RULE_SQL = "SELECT api10, applied_code FROM curated.formation_tag_rule WHERE applied"


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def pull(cache: Path | None) -> dict[str, pd.DataFrame]:
    names = ("wells", "sticks", "extents", "pads", "rule")
    if cache and all((cache / f"{n}.pkl").exists() for n in names):
        return {n: pd.read_pickle(cache / f"{n}.pkl") for n in names}
    from etl.db import get_connection

    with get_connection() as conn:
        d = {"wells": sb.pull_wells(conn), "sticks": sb._read(conn, _STICKS_SQL, {}), "extents": sb._read(conn, _EXTENTS_SQL, {}),
             "pads": sb._read(conn, _PADS_SQL, {"v": PAD_VINTAGE}), "rule": sb._read(conn, _RULE_SQL, {})}
    for c in ("tvd", "ll_ft", "geom_len_ft", "x", "y"):
        d["sticks"][c] = pd.to_numeric(d["sticks"][c], errors="coerce")
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        for n, f in d.items():
            f.to_pickle(cache / f"{n}.pkl")
    return d


# ----------------------------------------------------------------------------
# 0a  TVD bust
# ----------------------------------------------------------------------------


def evidence(wells: pd.DataFrame, rule: pd.DataFrame) -> pd.DataFrame:
    w = sb.evidence_depth(wells, "best")
    w = w[w["clean"]].copy()
    mid = np.array([p[len(p) // 2] if p else (np.nan, np.nan) for p in w["pts"]], float)
    w["x"], w["y"] = mid[:, 0], mid[:, 1]
    w = w[np.isfinite(w["x"]) & w["live"].notna()].reset_index(drop=True)
    w["shadow"] = w["api10"].map(rule.assign(api10=rule["api10"].astype(str)).set_index("api10")["applied_code"]).fillna(w["live"])
    return w


def landing_at(sticks: pd.DataFrame, w: pd.DataFrame, tag_col: str) -> pd.DataFrame:
    """Landing depth of same-code producers at each stick: (z, n wells, nearest mi). NaN z = no local control."""
    z, n, near = np.full(len(sticks), np.nan), np.zeros(len(sticks), int), np.full(len(sticks), np.inf)
    r, dmax = P.r_mi * ls.M_PER_MI, P.direct_max_mi * ls.M_PER_MI
    pos = {k: np.asarray(v) for k, v in sticks.reset_index(drop=True).groupby(["basin", "code"]).indices.items()}
    for (basin, code), idx in pos.items():
        c = w[(w["basin"] == basin) & (w[tag_col] == code)]
        if len(c) < P.n_min:
            continue
        cxy, cz = c[["x", "y"]].to_numpy(float), c["depth_ft"].to_numpy(float)
        tree = cKDTree(cxy)
        sxy = sticks.iloc[idx][["x", "y"]].to_numpy(float)
        d1, _ = tree.query(sxy, k=1)
        near[idx] = d1 / ls.M_PER_MI
        for i, js in zip(idx, tree.query_ball_point(sxy, r), strict=True):
            n[i] = len(js)
            if len(js) >= P.n_min and near[i] * ls.M_PER_MI <= dmax:
                z[i] = ls.estimate(cxy[js], cz[js], sticks.iloc[i][["x", "y"]].to_numpy(float), P)[0]
    return pd.DataFrame({"landing_ft": z, "n_wells": n, "near_mi": near}, index=sticks.index)


def bust_table(s: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = []
    for key, g in s.groupby(by, dropna=False):
        b = g["bust_ft"].dropna()
        o = dict(zip(by, key if isinstance(key, tuple) else (key,), strict=True))
        o |= {"sticks": len(g), "with_control": len(b), "control_pct": 100 * len(b) / len(g),
              "median_ft": np.nan, "p10_ft": np.nan, "p90_ft": np.nan, "median_abs_ft": np.nan}
        if len(b):
            o |= {"median_ft": b.median(), "p10_ft": b.quantile(0.10), "p90_ft": b.quantile(0.90),
                  "median_abs_ft": b.abs().median()}
            for t in BUST_FT:
                o[f"beyond_{int(t)}_pct"] = 100 * float((b.abs() > t).mean())
            o["deep_150_pct"] = 100 * float((b > 150).mean())
            o["shallow_150_pct"] = 100 * float((b < -150).mean())
        rows.append(o)
    return pd.DataFrame(rows)


def bust_maps(s: pd.DataFrame, extents: pd.DataFrame, out: Path) -> list[str]:
    files = []
    for basin, g in s[s["bust_ft"].notna()].groupby("basin"):
        codes = g.groupby("code").size().sort_values(ascending=False).index.tolist()
        ncol = 4
        nrow = int(np.ceil(len(codes) / ncol))
        fig, axes = plt.subplots(nrow, ncol, figsize=(4.6 * ncol, 4.6 * nrow), squeeze=False)
        sc = None
        for ax, code in zip(axes.ravel(), codes, strict=False):
            c = g[g["code"] == code]
            for e in extents[extents["basin"] == basin].itertuples():
                if code in ls.extent_codes(basin, e.bench):
                    for poly in shapely.get_parts(shapely.from_wkt(e.wkt)):
                        ex, ey = poly.exterior.xy
                        ax.plot(np.asarray(ex) / ls.M_PER_MI, np.asarray(ey) / ls.M_PER_MI, color="#6b7280", lw=0.6)
            sc = ax.scatter(c["x"] / ls.M_PER_MI, c["y"] / ls.M_PER_MI, c=c["bust_ft"].clip(-500, 500), cmap="RdBu_r",
                            vmin=-500, vmax=500, s=1.5, linewidths=0, rasterized=True)
            b = c["bust_ft"]
            ax.set_title(f"{code}: n {len(c):,}\nmedian {b.median():+.0f} ft, {100 * (b.abs() > 150).mean():.0f}% beyond 150 ft", fontsize=9)
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
        for ax in axes.ravel()[len(codes):]:
            ax.axis("off")
        if sc is not None:
            cb = fig.colorbar(sc, ax=axes, shrink=0.5, pad=0.01)
            cb.set_label("Novi stick TVD minus same-bench producer landing depth, ft (red = Novi deeper)")
        fig.suptitle(f"{basin}: Novi stick TVD bust by bench (sticks with local producer control; grey = BOX extent)", fontsize=12)
        f = out / f"bust_map_{basin}.png"
        fig.savefig(f, dpi=110, bbox_inches="tight")
        plt.close(fig)
        files.append(f.name)
    return files


# ----------------------------------------------------------------------------
# 0b / 0c  DSU polygons and laterals
# ----------------------------------------------------------------------------


def pad_frame(pads: pd.DataFrame) -> pd.DataFrame:
    p = pads.copy()
    geoms = shapely.make_valid(shapely.from_wkt(p["wkt"].to_numpy()))
    p["geom"] = geoms
    p["acres"] = shapely.area(geoms) / 4046.8564224
    long_ft, short_ft, az = [], [], []
    for g in geoms:
        r = shapely.oriented_envelope(g)
        xy = np.asarray(r.exterior.coords)[:4] if r.geom_type == "Polygon" else np.zeros((4, 2))
        e1, e2 = xy[1] - xy[0], xy[2] - xy[1]
        l1, l2 = float(np.hypot(*e1)), float(np.hypot(*e2))
        lv = e1 if l1 >= l2 else e2
        long_ft.append(max(l1, l2) * FT_PER_M)
        short_ft.append(min(l1, l2) * FT_PER_M)
        az.append(float(np.degrees(np.arctan2(lv[0], lv[1])) % 180.0))   # grid bearing of the long side, axial
    p["long_ft"], p["short_ft"], p["long_az_deg"] = long_ft, short_ft, az
    p["aspect"] = p["long_ft"] / p["short_ft"].replace(0, np.nan)
    p["fill"] = shapely.area(geoms) / (p["long_ft"] * p["short_ft"] / FT_PER_M ** 2).replace(0, np.nan)
    p["straight_ft"] = (p["long_ft"] - 2 * SETBACK_FT).clip(lower=0)
    p["well_type"] = np.where(p["straight_ft"] >= UTURN_BELOW_FT, "straight", "uturn")
    p["planned_lateral_ft"] = np.where(p["well_type"] == "straight", p["straight_ft"], 2 * p["straight_ft"])
    p["long_mi_class"] = pd.cut(p["long_ft"], [0, 3960, 6600, 9240, 11880, 14520, 1e9],
                                labels=["< 0.75 mi", "1 mi", "1.5 mi", "2 mi", "2.5 mi", "3 mi +"])
    return p


def pad_overlaps(p: pd.DataFrame) -> pd.DataFrame:
    """Per polygon: how many other polygons share >= 10 % / >= 90 % of ITS area (Novi stacks pads over shared acreage)."""
    geoms = p["geom"].to_numpy()
    tree = shapely.STRtree(geoms)
    a, b = tree.query(geoms, predicate="intersects")
    keep = a != b
    a, b = a[keep], b[keep]
    share = shapely.area(shapely.intersection(geoms[a], geoms[b])) / shapely.area(geoms[a])
    o = pd.DataFrame({"i": a, "share": share})
    out = pd.DataFrame({"n_overlap_10": o[o["share"] >= 0.10].groupby("i").size(),
                        "n_overlap_90": o[o["share"] >= 0.90].groupby("i").size(),
                        "max_share": o.groupby("i")["share"].max()}).reindex(range(len(p))).fillna(0)
    out.index = p.index
    return out


def extent_coverage(p: pd.DataFrame, extents: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for basin, pb in p.groupby("basin"):
        union = shapely.union_all(pb["geom"].to_numpy())
        shapely.prepare(union)
        geoms = pb["geom"].to_numpy()
        tree = shapely.STRtree(geoms)
        for e in extents[extents["basin"] == basin].itertuples():
            eg = shapely.make_valid(shapely.from_wkt(e.wkt))
            hit = tree.query(eg, predicate="intersects")
            inter = shapely.area(shapely.intersection(geoms[hit], eg)) / shapely.area(geoms[hit])
            c = w[(w["basin"] == basin) & w["live"].isin(ls.extent_codes(basin, e.bench))
                  & (pd.to_datetime(w["first_production_date"]).dt.year >= PRODUCER_SINCE)]
            inside = shapely.contains_xy(union, c["x"].to_numpy(), c["y"].to_numpy()) if len(c) else np.array([])
            rows.append({"basin": basin, "bench": e.bench, "extent_sqmi": shapely.area(eg) / ls.M_PER_MI ** 2,
                         "covered_pct": 100 * shapely.area(shapely.intersection(union, eg)) / shapely.area(eg),
                         "polygons_intersecting": len(hit), "polygons_under_10pct_inside": int((inter < 0.10).sum()),
                         "polygons_under_50pct_inside": int((inter < 0.50).sum()),
                         f"producers_{PRODUCER_SINCE}plus": len(c),
                         "producers_outside_any_polygon_pct": 100 * float((~inside).mean()) if len(c) else np.nan})
    return pd.DataFrame(rows)


def lateral_tables(s: pd.DataFrame, p: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s = s.assign(lat_ft=s["ll_ft"].fillna(s["geom_len_ft"]))
    bins = [0, 6000, 7000, 8500, 11000, 13500, 1e9]
    labels = ["< 6,000", "6,000-7,000", "7,000-8,500", "8,500-11,000", "11,000-13,500", "13,500 +"]
    s["len_class"] = pd.cut(s["lat_ft"], bins, labels=labels)
    novi = (s.groupby(["basin", "len_class"], observed=False).agg(sticks=("stick_id", "size"), lateral_ft=("lat_ft", "sum")).reset_index())
    novi["sticks_pct"] = 100 * novi["sticks"] / novi.groupby("basin")["sticks"].transform("sum")
    shape = (p.groupby(["basin", "long_mi_class", "well_type"], observed=True)
             .agg(polygons=("pad_id", "size"), median_acres=("acres", "median"), median_planned_lateral_ft=("planned_lateral_ft", "median")).reset_index())
    shape["polygons_pct"] = 100 * shape["polygons"] / shape.groupby("basin")["polygons"].transform("sum")
    # each named stick against the polygon carrying its pad_name
    key = p.drop_duplicates(["basin", "pad_name"]).set_index(["basin", "pad_name"])[["straight_ft", "well_type", "planned_lateral_ft"]]
    m = s.join(key, on=["basin", "pad_name"], how="inner")
    m["novi_vs_planned"] = m["lat_ft"] / m["planned_lateral_ft"].replace(0, np.nan)
    cmp_ = m.groupby(["basin", "well_type"]).agg(sticks=("stick_id", "size"), novi_median_ft=("lat_ft", "median"),
                                                  box_median_ft=("planned_lateral_ft", "median"),
                                                  novi_under_6000_pct=("lat_ft", lambda v: 100 * float((v < 6000).mean()))).reset_index()
    return novi, shape, cmp_


# ----------------------------------------------------------------------------


def run(out: Path, cache: Path | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = pull(cache)
    w = evidence(d["wells"], d["rule"])
    s = d["sticks"].dropna(subset=["x", "y", "code"]).reset_index(drop=True)
    print(f"evidence wells {len(w):,}; sticks {len(s):,}", flush=True)

    live = landing_at(s, w, "live")
    shadow = landing_at(s, w, "shadow")
    s = s.join(live)
    s["bust_ft"] = s["tvd"] - s["landing_ft"]
    s["bust_shadow_ft"] = s["tvd"] - shadow["landing_ft"]
    by_code = bust_table(s, ["basin", "code"]).sort_values(["basin", "sticks"], ascending=[True, False])
    by_cat = bust_table(s, ["basin", "category"])
    by_src = bust_table(s, ["basin", "code_source"])
    by_county = bust_table(s, ["basin", "code", "county"])
    by_county = by_county[by_county["with_control"] >= 50].sort_values("median_abs_ft", ascending=False)
    sh = bust_table(s.assign(bust_ft=s["bust_shadow_ft"]), ["basin", "code"])
    tag_effect = by_code[["basin", "code", "with_control", "median_ft", "beyond_150_pct"]].merge(
        sh[["basin", "code", "with_control", "median_ft", "beyond_150_pct"]], on=["basin", "code"], suffixes=("_live", "_shadow"))
    by_code.to_csv(out / "bust_by_bench.csv", index=False)
    by_cat.to_csv(out / "bust_by_category.csv", index=False)
    by_src.to_csv(out / "bust_by_tag_source.csv", index=False)
    by_county.to_csv(out / "bust_by_bench_county.csv", index=False)
    tag_effect.to_csv(out / "bust_live_vs_shadow_tags.csv", index=False)
    s.drop(columns=["x", "y"]).to_csv(out / "bust_sticks.csv.gz", index=False, compression="gzip")
    maps = bust_maps(s, d["extents"], out)

    p = pad_frame(d["pads"])
    p = p.join(pad_overlaps(p))
    shape_cols = ["pad_id", "basin", "pad_name", "operator", "well_cnt", "acres", "long_ft", "short_ft", "aspect", "fill", "long_az_deg",
                  "straight_ft", "well_type", "planned_lateral_ft", "long_mi_class", "n_overlap_10", "n_overlap_90", "max_share"]
    p[shape_cols].to_csv(out / "dsu_polygons.csv", index=False)
    cov = extent_coverage(p, d["extents"], w)
    cov.to_csv(out / "dsu_extent_coverage.csv", index=False)
    novi_len, shape, cmp_ = lateral_tables(s, p)
    novi_len.to_csv(out / "novi_lateral_length.csv", index=False)
    shape.to_csv(out / "dsu_shape_classes.csv", index=False)
    cmp_.to_csv(out / "novi_vs_box_lateral.csv", index=False)

    def pad_summary(g: pd.DataFrame) -> dict:
        return {"polygons": len(g), "no_novi_wells": int((g["well_cnt"] == 0).sum()), "median_acres": float(g["acres"].median()),
                "near_square_pct_aspect_lt_1_15": 100 * float((g["aspect"] < 1.15).mean()),
                "irregular_pct_fill_lt_0_90": 100 * float((g["fill"] < 0.90).mean()),
                "uturn_pct": 100 * float((g["well_type"] == "uturn").mean()),
                "overlapped_10_pct": 100 * float((g["n_overlap_10"] > 0).mean()),
                "duplicated_90_pct": 100 * float((g["n_overlap_90"] > 0).mean()),
                "median_overlapping_polygons": float(g["n_overlap_10"].median())}

    summary = {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "code_sha": _git_sha(), "pad_vintage": PAD_VINTAGE,
        "evidence_wells": len(w), "sticks": len(s), "sticks_with_control": int(s["bust_ft"].notna().sum()),
        "bust_all": {b: {"median_ft": float(g["bust_ft"].median()), "median_abs_ft": float(g["bust_ft"].abs().median()),
                         "beyond_150_pct": 100 * float((g["bust_ft"].dropna().abs() > 150).mean()),
                         "beyond_300_pct": 100 * float((g["bust_ft"].dropna().abs() > 300).mean())} for b, g in s.groupby("basin")},
        "pads": {b: pad_summary(g) for b, g in p.groupby("basin")}, "maps": maps,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
