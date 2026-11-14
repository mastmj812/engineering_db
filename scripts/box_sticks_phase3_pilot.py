"""BOX sticks, phase 3a step 1: pilot areas and the evidence for the open generator rules (read-only).

    python -m scripts.box_sticks_phase3_pilot --out docs/box_sticks/phase3a-<date> --cache <phase 0 cache> [--step frame|windows|areas]

Not the generator. It builds one frame per DSU polygon x bench from the earlier phases' loaders and methods, never
re-derived here:
  benches        scripts.box_sticks_phase2a.extent_list (record BOX extents; WCXY = the hand-drawn file);
  landing depth  scripts.box_sticks_phase1c.build_chain on the two-part-screened evidence wells (rung per DSU x bench);
  spacing        scripts.box_sticks_phase2a_bands.build (the blended surface of record, sigma 3 mi, k 1);
  DSU shape      scripts.box_sticks_phase0.pad_frame (long axis, aspect, straight lateral, U-turn class).
Wells and Novi sticks are attached to a DSU by the >= 30 % overlap rule (share of the line inside the polygon).
Wells not yet on production (Spud / DUC / Completed) are pulled here; the earlier caches hold producers only.

Steps: `frame` builds and caches the frame; `windows` scores candidate blocks; `areas` writes the chosen pilot areas
(AREAS below), their counts and maps. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely
from matplotlib.collections import LineCollection, PolyCollection
from pyproj import Transformer

from box import landing_surfaces as ls
from box import tag_scoreboard as sb
from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_phase1c as p1c
from scripts import box_sticks_phase2a as p2a
from scripts import box_sticks_phase2a_bands as bands
from scripts import box_sticks_phase2a_surface as sf
from scripts import box_sticks_phase2b as p2b

MI = ls.M_PER_MI
FT_PER_M = p0.FT_PER_M
MEMBER_FRAC = 0.30            # a well / stick belongs to a DSU when >= 30 % of its line is inside (rule 9)
SQUARE_ASPECT = 1.15          # plan value, open (rule b8)
BLEND_COL = "blend_s3_k1"     # the spacing rule of record (phase 2a decision 4)
LOW_CONF_P90_FT = 200.0       # phase 1c: a carried depth whose rung's held-out P90 is above this is low confidence
REMAINING = (None, "remaining_pud", "conflict")
TO_LL = Transformer.from_crs("EPSG:3083", "EPSG:4326", always_xy=True)
FROM_LL = Transformer.from_crs("EPSG:4326", "EPSG:3083", always_xy=True)
NM_TX_LAT, NM_TX_LON = 32.0, -103.064

_PREPROD_SQL = """
SELECT w.api10, w.basin_blueox AS basin, w.state_code, w.county, w.current_operator AS operator, w.well_name,
       w.well_status, w.spud_date, w.formation_blueox AS live, fx.canonical_code AS vendor,
       w.directional_survey_is_planned AS planned, w.tvd_ft, s.lat_tvd_p50_ft,
       extensions.ST_AsText(extensions.ST_Transform(w.wellstick_geom, 3083)) AS wkt
FROM curated.wells_enriched w
LEFT JOIN curated.well_lateral_survey s ON s.api10 = w.api10
LEFT JOIN ref.formation_crosswalk fx ON fx.basin = w.basin_blueox AND fx.raw_value = w.formation_blueox_raw
WHERE w.basin_blueox IN ('delaware', 'midland') AND w.is_horizontal AND w.first_production_date IS NULL
  AND w.well_status IN ('Spud', 'DUC', 'Completed')
  AND extensions.ST_GeometryType(w.wellstick_geom) = 'ST_LineString'
"""

# The pilot areas (step `areas`): DSUs whose centroid falls in a square of `size_mi` (EPSG:3083) centred on lon / lat.
# Picked from the `windows` scoring (docs/box_sticks/phase3a-*/PROPOSAL.md says why); proposal until Michael confirms.
AREAS: dict[str, dict] = {
    "delaware_tx_ward": {"basin": "delaware", "focus": "BS1_S", "lon": -103.310, "lat": 31.581, "size_mi": 7.0,
                         "label": "Delaware TX: Ward County (BS1_S extent)"},
    "delaware_nm_lea": {"basin": "delaware", "focus": "BS1_S", "lon": -103.664, "lat": 32.159, "size_mi": 7.0,
                        "label": "Delaware NM: Lea County, holds Ruthless 11 Federal COM (BS1_S extent)"},
    "midland_glasscock": {"basin": "midland", "focus": "DEAN", "lon": -101.754, "lat": 31.871, "size_mi": 8.0,
                          "label": "Midland: Glasscock / Midland County (DEAN extent)"},
}
RUTHLESS_PAD_ID = 10785       # the DSU polygon holding 37 of the 38 Ruthless 11 Federal COM producers
BACKTEST_CUTOFF = pd.Timestamp("2023-01-01")
YOUNG_DAYS = 365
BENCH_COLORS = {"AVA": "#a3a3a3", "BS1": "#0ea5e9", "BS2": "#2563eb", "BS3": "#7c3aed", "WCX": "#f59e0b", "WCA": "#dc2626", "WCB": "#ea580c",
                "WCC": "#65a30d", "WCD": "#15803d", "MS": "#0ea5e9", "JM": "#2563eb", "LSS": "#7c3aed", "DEA": "#db2777"}


def pull_preprod(cache: Path) -> pd.DataFrame:
    f = cache / "p3_preprod.pkl"
    if f.exists():
        return pd.read_pickle(f)
    from etl.db import get_connection

    with get_connection() as conn:
        d = sb._read(conn, _PREPROD_SQL, {})
    d["api10"] = d["api10"].astype(str)
    d = sb.evidence_depth(d, "best")
    d["geom"] = shapely.from_wkt(d["wkt"].to_numpy())
    d = d[shapely.length(d["geom"].to_numpy()) > 1.0].reset_index(drop=True)
    d.to_pickle(f)
    return d


def membership(lines: np.ndarray, basin: np.ndarray, pads: pd.DataFrame, min_frac: float = MEMBER_FRAC) -> pd.DataFrame:
    """(line index, pad_id, share of the line inside the polygon) for every pair at or above min_frac."""
    parts = []
    for b, pb in pads.groupby("basin"):
        ix = np.flatnonzero(basin == b)
        if not len(ix):
            continue
        pg = pb["geom"].to_numpy()
        a, k = shapely.STRtree(pg).query(lines[ix], predicate="intersects")
        share = shapely.length(shapely.intersection(lines[ix][a], pg[k])) / shapely.length(lines[ix][a])
        keep = share >= min_frac
        parts.append(pd.DataFrame({"i": ix[a[keep]], "pad_id": pb["pad_id"].to_numpy()[k[keep]], "share": share[keep]}))
    return pd.concat(parts, ignore_index=True)


def build_frame(cache: Path) -> dict:
    f = cache / "p3_frame.pkl"
    if f.exists():
        return pd.read_pickle(f)
    d = p0.pull(cache)
    wg, sg = p2a.pull_geoms(cache)
    u = p2a.universe(d, wg, cache)
    pads = p0.pad_frame(d["pads"])
    pads = pads[pads["geom"].map(lambda g: g.geom_type == "Polygon")].reset_index(drop=True)
    cen = shapely.centroid(pads["geom"].to_numpy())
    pads["cx"], pads["cy"] = shapely.get_x(cen), shapely.get_y(cen)
    pads["lon"], pads["lat"] = TO_LL.transform(pads["cx"].to_numpy(), pads["cy"].to_numpy())
    pads["state"] = np.where((pads["lat"] > NM_TX_LAT) & (pads["lon"] < NM_TX_LON), "NM", "TX")
    ext = p2a.extent_list(d["extents"])

    # DSU x bench: eligibility by intersect, with the share of the DSU inside the extent
    rows = []
    for basin, bench, code, eg in ext:
        pb = pads[pads["basin"] == basin]
        pg = pb["geom"].to_numpy()
        hit = np.sort(shapely.STRtree(pg).query(eg, predicate="intersects"))
        rows.append(pd.DataFrame({"basin": basin, "bench": bench, "code": code, "pad_id": pb["pad_id"].to_numpy()[hit],
                                  "inside_frac": shapely.area(shapely.intersection(pg[hit], eg)) / shapely.area(pg[hit])}))
    db = pd.concat(rows, ignore_index=True)
    db = db[db["inside_frac"] > 0].reset_index(drop=True)

    # landing chain (phase 1c), screened evidence
    ev = p0.evidence(d["wells"], d["rule"]).merge(pd.read_pickle(cache / "p2a_screen.pkl"), on="api10", how="left")
    ev = ev[ev["screen"] == "keep"].reset_index(drop=True)
    thick, far = p1c.rankings()
    ch = p1c.build_chain(ev, d["extents"], pads, sb.bench_order(), thick, far)
    db = db.merge(ch[["basin", "code", "pad_id", "z", "rung", "how", "expected_median_ft", "expected_p90_ft", "near_mi"]],
                  on=["basin", "code", "pad_id"], how="left")
    db["rung"] = db["rung"].fillna("none")

    # spacing (phase 2a blended surface)
    m = sf.measured(cache)
    _, app, _ = bands.build(m, pads, ext)
    db = db.merge(app[["basin", "code", "pad_id", "edge_mi", "edge_band", BLEND_COL]].rename(columns={BLEND_COL: "spacing_ft"}),
                  on=["basin", "code", "pad_id"], how="left")

    # existing wells (producers + not yet producing) and Novi sticks per DSU
    pre = pull_preprod(cache)
    wm = membership(u["geom"].to_numpy(), u["basin"].to_numpy(), pads)
    pm = membership(pre["geom"].to_numpy(), pre["basin"].to_numpy(), pads)
    s = d["sticks"].dropna(subset=["x", "y", "code"]).merge(sg, on="stick_id", how="inner").reset_index(drop=True)
    s["geom"] = shapely.from_wkt(s["wkt"].to_numpy())
    status, _ = p2b.pull_stick_status(cache)
    s = s.merge(status, on="stick_id", how="left")
    s["remaining"] = s["status"].isna() | s["status"].isin(["remaining_pud", "conflict"])
    sm = membership(s["geom"].to_numpy(), s["basin"].to_numpy(), pads)
    sm = sm.sort_values("share", ascending=False).drop_duplicates("i")          # a stick counts once, in its main DSU
    out = {"u": u, "pre": pre, "pads": pads, "ext": ext, "db": db, "wm": wm, "pm": pm, "sticks": s, "sm": sm,
           "tags": "live", "pulled": str(pd.Timestamp.now().date())}
    pd.to_pickle(out, f)
    return out


def dsu_table(F: dict) -> pd.DataFrame:
    """One row per DSU: shape class, benches, existing wells by evidence class, remaining Novi sticks."""
    u, pads, db, wm, pm, s, sm = F["u"], F["pads"], F["db"], F["wm"], F["pm"], F["sticks"], F["sm"]
    t = pads[["pad_id", "basin", "state", "lon", "lat", "cx", "cy", "acres", "long_ft", "short_ft", "aspect", "straight_ft", "well_type", "long_az_deg"]].copy()
    t["square"] = t["aspect"] < SQUARE_ASPECT
    g = db.groupby("pad_id")
    t = t.merge(pd.DataFrame({"benches": g.size(), "carried": g["rung"].apply(lambda r: int(r.isin(["thickness", "bracket", "offset"]).sum())),
                              "no_depth": g["rung"].apply(lambda r: int((r == "none").sum())),
                              "low_conf": g["expected_p90_ft"].apply(lambda v: int((v > LOW_CONF_P90_FT).sum()))}).reset_index(), on="pad_id", how="left")
    w = wm.assign(code=u["live"].to_numpy()[wm["i"]], planned=u["planned"].fillna(False).to_numpy(bool)[wm["i"]],
                  clean=u["clean"].to_numpy(bool)[wm["i"]], fp=u["fp"].to_numpy()[wm["i"]])
    w["no_depth_evidence"] = ~w["clean"]
    gw = w.groupby("pad_id")
    t = t.merge(pd.DataFrame({"producers": gw.size(), "producers_planned": gw["planned"].sum(), "producers_no_depth": gw["no_depth_evidence"].sum(),
                              "producer_benches": gw["code"].nunique(), "last_fp": gw["fp"].max()}).reset_index(), on="pad_id", how="left")
    t = t.merge(pm.groupby("pad_id").size().rename("preprod").reset_index(), on="pad_id", how="left")
    st = sm.assign(remaining=s["remaining"].to_numpy()[sm["i"]])
    t = t.merge(st.groupby("pad_id").agg(novi_sticks=("i", "size"), novi_remaining=("remaining", "sum")).reset_index(), on="pad_id", how="left")
    for c in ("benches", "carried", "no_depth", "low_conf", "producers", "producers_planned", "producers_no_depth", "producer_benches", "preprod", "novi_sticks", "novi_remaining"):
        t[c] = t[c].fillna(0).astype(int)
    return t


def bench_wells(F: dict) -> pd.DataFrame:
    """Producers per DSU x live code (>= 30 % overlap)."""
    u, wm = F["u"], F["wm"]
    w = wm.assign(code=u["live"].to_numpy()[wm["i"]], basin=u["basin"].to_numpy()[wm["i"]])
    return w.groupby(["basin", "pad_id", "code"]).size().rename("wells").reset_index()


# ----------------------------------------------------------------------------
# Candidate blocks
# ----------------------------------------------------------------------------


def windows(F: dict, basin: str, focus: str, size_mi: float = 7.0, step_mi: float = 2.0) -> pd.DataFrame:
    t = dsu_table(F)
    t = t[t["basin"] == basin]
    bw = bench_wells(F)
    bw = bw[bw["basin"] == basin].pivot(index="pad_id", columns="code", values="wells").fillna(0)
    db = F["db"][F["db"]["basin"] == basin]
    foc = db[db["code"] == focus].set_index("pad_id")
    t = t.merge(foc[["inside_frac", "rung"]].rename(columns={"inside_frac": "focus_inside", "rung": "focus_rung"}), on="pad_id", how="left")
    t["focus_wells"] = t["pad_id"].map(bw[focus]) if focus in bw else 0
    for c in ("LSSH", "WCA_1"):
        t[f"w_{c}"] = t["pad_id"].map(bw[c]).fillna(0) if c in bw else 0
    half = size_mi * MI / 2
    rows = []
    for x0 in np.arange(t["cx"].min(), t["cx"].max(), step_mi * MI):
        for y0 in np.arange(t["cy"].min(), t["cy"].max(), step_mi * MI):
            g = t[(np.abs(t["cx"] - x0) <= half) & (np.abs(t["cy"] - y0) <= half)]
            if not 20 <= len(g) <= 40 or (g["focus_inside"].fillna(0) > 0.5).mean() < 0.9:
                continue
            lon, lat = TO_LL.transform(x0, y0)
            rows.append({"lon": round(lon, 3), "lat": round(lat, 3), "state_nm_pct": 100 * float((g["state"] == "NM").mean()), "dsu": len(g),
                         "dsu_bench": int(g["benches"].sum()), "undeveloped": int((g["producers"] == 0).sum()),
                         "producers": int(g["producers"].sum()), "focus_dsu_with_wells": int((g["focus_wells"].fillna(0) > 0).sum()),
                         "uturn": int((g["well_type"] == "uturn").sum()), "square": int(g["square"].sum()),
                         "carried_pct": 100 * g["carried"].sum() / max(g["benches"].sum(), 1), "no_depth_pct": 100 * g["no_depth"].sum() / max(g["benches"].sum(), 1),
                         "planned_wells": int(g["producers_planned"].sum()), "no_depth_wells": int(g["producers_no_depth"].sum()), "preprod": int(g["preprod"].sum()),
                         "novi_remaining": int(g["novi_remaining"].sum()),
                         "lssh_wca1_cubes": int(((g["w_LSSH"] >= 2) & (g["w_WCA_1"] >= 2)).sum())})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Two landings inside one bench (evidence for the open rule; the generator's detector is decided at the gate)
# ----------------------------------------------------------------------------

TWO_MIN_WELLS, TWO_MIN_SEP_FT, TWO_MIN_SIDE, TWO_TIGHT = 4, 150.0, 2, 0.6


def two_landing_split(depths: np.ndarray) -> tuple[float, int, int, float]:
    """Best split of a DSU x bench's producer depths into an upper and a lower group: (separation of the group
    medians, n upper, n lower, the wider group's range). The empty band between the groups must be at least half
    the separation."""
    v = np.sort(np.asarray(depths, float))
    best = (0.0, 0, 0, 0.0)
    for k in range(TWO_MIN_SIDE, len(v) - TWO_MIN_SIDE + 1):
        a, b = v[:k], v[k:]
        sep = float(np.median(b) - np.median(a))
        if sep > best[0] and (v[k] - v[k - 1]) >= 0.5 * sep:
            best = (sep, len(a), len(b), float(max(np.ptp(a), np.ptp(b))))
    return best


def two_landings(F: dict) -> pd.DataFrame:
    """Per DSU x bench with >= TWO_MIN_WELLS same-tag producers that have depth evidence (a `bad_depth` well is out; a
    well the screen calls a likely mis-tag stays, because at Ruthless 11 the screen calls one real landing a mis-tag)."""
    u, wm = F["u"], F["wm"]
    ok = u["clean"].to_numpy(bool) & (u["screen"].to_numpy() != "bad_depth")
    w = wm.assign(code=u["live"].to_numpy()[wm["i"]], basin=u["basin"].to_numpy()[wm["i"]], depth=u["depth_ft"].to_numpy(float)[wm["i"]])[ok[wm["i"]]]
    rows = []
    for (basin, pid, code), g in w.groupby(["basin", "pad_id", "code"]):
        if len(g) < TWO_MIN_WELLS:
            continue
        sep, na, nb, rng = two_landing_split(g["depth"].to_numpy())
        v = np.sort(g["depth"].to_numpy())
        rows.append({"basin": basin, "pad_id": pid, "code": code, "wells": len(g), "sep_ft": sep, "n_upper": na, "n_lower": nb, "range_ft": rng,
                     "upper_ft": float(np.median(v[:na])) if na else np.nan, "lower_ft": float(np.median(v[na:])) if nb else np.nan,
                     "two": bool(sep >= TWO_MIN_SEP_FT and min(na, nb) >= TWO_MIN_SIDE and rng <= TWO_TIGHT * sep)})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Pilot areas
# ----------------------------------------------------------------------------


def area_pads(F: dict, a: dict) -> np.ndarray:
    pads = F["pads"]
    x0, y0 = FROM_LL.transform(a["lon"], a["lat"])
    half = a["size_mi"] * MI / 2
    return pads.loc[(pads["basin"] == a["basin"]) & (np.abs(pads["cx"] - x0) <= half) & (np.abs(pads["cy"] - y0) <= half), "pad_id"].to_numpy()


def _fam(code: str | None) -> str:
    return (code or "")[:3] if (code or "")[:2] not in ("MS", "JM") else (code or "")[:2]


def area_counts(F: dict, name: str, a: dict, t: pd.DataFrame, tl: pd.DataFrame) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    u, pre, db, wm, pm = F["u"], F["pre"], F["db"], F["wm"], F["pm"]
    ids = area_pads(F, a)
    g, d = t[t["pad_id"].isin(ids)], db[db["pad_id"].isin(ids)]
    wi = wm.loc[wm["pad_id"].isin(ids), "i"].unique()
    w = u.loc[wi]
    asof = u["fp"].max()
    pw = pre.loc[pm.loc[pm["pad_id"].isin(ids), "i"].unique()]
    carried = d["rung"].isin(["thickness", "bracket", "offset"])
    by = d.assign(carried=carried, none=d["rung"] == "none", low=d["expected_p90_ft"] > LOW_CONF_P90_FT).groupby("code").agg(
        dsu=("pad_id", "size"), sliver_under_10pct=("inside_frac", lambda v: int((v < 0.10).sum())), direct=("rung", lambda r: int((r == "direct").sum())),
        carried=("carried", "sum"), carried_low_conf=("low", "sum"), no_depth=("none", "sum"), median_spacing_ft=("spacing_ft", "median")).reset_index()
    by["producers"] = by["code"].map(w["live"].value_counts()).fillna(0).astype(int)
    st = F["sticks"].loc[F["sm"].loc[F["sm"]["pad_id"].isin(ids), "i"]]
    by["novi_remaining"] = by["code"].map(st[st["remaining"]]["code"].value_counts()).fillna(0).astype(int)
    by["two_landing_dsu"] = by["code"].map(tl[tl["two"] & tl["pad_id"].isin(ids)]["code"].value_counts()).fillna(0).astype(int)
    by.insert(0, "area", name)
    other = w[~w["live"].isin(by["code"])]["live"].value_counts()
    c = {"area": name, "label": a["label"], "centre_lon_lat": [a["lon"], a["lat"]], "size_mi": a["size_mi"],
         "counties": w["county"].value_counts().head(3).to_dict(), "operators": w["operator"].value_counts().head(4).to_dict(),
         "dsu": len(g), "dsu_bench": len(d), "dsu_undeveloped": int((g["producers"] == 0).sum()), "dsu_1_to_4_producers": int(g["producers"].between(1, 4).sum()),
         "dsu_uturn": int((g["well_type"] == "uturn").sum()), "dsu_uturn_pct": 100 * float((g["well_type"] == "uturn").mean()),
         "dsu_near_square": int(g["square"].sum()), "producers": len(w), "producers_on_benches_without_extent_here": other.to_dict(),
         "producers_no_depth_evidence": int((~w["clean"]).sum()), "producers_planned_survey": int(w["planned"].fillna(False).sum()),
         "producers_under_12_months": int((w["fp"] > asof - pd.Timedelta(days=YOUNG_DAYS)).sum()),
         "producers_since_backtest_cutoff": int((w["fp"] >= BACKTEST_CUTOFF).sum()),
         "not_yet_producing": pw["well_status"].value_counts().to_dict(), "not_yet_producing_with_depth_evidence": int(pw["clean"].sum()),
         "bench_carried_pct": 100 * float(carried.mean()), "bench_no_depth_pct": 100 * float((d["rung"] == "none").mean()),
         "bench_carried_low_conf_pct": 100 * float((d["expected_p90_ft"] > LOW_CONF_P90_FT).mean()),
         "novi_sticks": int(g["novi_sticks"].sum()), "novi_remaining": int(g["novi_remaining"].sum()),
         "novi_remaining_on_benches_without_extent_here": int((st["remaining"] & ~st["code"].isin(by["code"])).sum()),
         "two_landing_dsu_bench": int((tl["two"] & tl["pad_id"].isin(ids)).sum()), "dsu_bench_under_10pct_inside": int((d["inside_frac"] < 0.10).sum())}
    return c, by, g


def area_map(F: dict, name: str, a: dict, g: pd.DataFrame, out: Path) -> str:
    u, pre, pads, wm, pm, s, sm = F["u"], F["pre"], F["pads"], F["wm"], F["pm"], F["sticks"], F["sm"]
    ids = g["pad_id"].to_numpy()
    pg = pads.set_index("pad_id").loc[ids]
    x0, y0 = pg["cx"].mean(), pg["cy"].mean()

    def xy(geom: shapely.Geometry) -> np.ndarray:
        return (shapely.get_coordinates(geom) - (x0, y0)) / MI

    fig, ax = plt.subplots(figsize=(15, 15))
    n = g.set_index("pad_id")["producers"].reindex(ids).to_numpy()
    pc = PolyCollection([xy(v) for v in pg["geom"]], array=np.minimum(n, 30), cmap="Greys", linewidths=0.8, edgecolors="#374151", alpha=0.45)
    pc.set_clim(0, 60)
    ax.add_collection(pc)
    ut = pg[pg["well_type"] == "uturn"]
    ax.add_collection(PolyCollection([xy(v) for v in ut["geom"]], facecolors="none", edgecolors="#f59e0b", linewidths=2.2))
    if RUTHLESS_PAD_ID in pg.index:
        ax.add_collection(PolyCollection([xy(pg.at[RUTHLESS_PAD_ID, "geom"])], facecolors="none", edgecolors="#111827", linewidths=3.5))
    st = s.loc[sm.loc[sm["pad_id"].isin(ids), "i"]]
    ax.add_collection(LineCollection([xy(v) for v in st.loc[st["remaining"], "geom"]], colors="#9ca3af", linewidths=0.35))
    w = u.loc[wm.loc[wm["pad_id"].isin(ids), "i"].unique()]
    nd = ~w["clean"].to_numpy(bool)
    for fam, col in BENCH_COLORS.items():
        k = np.array([_fam(c) == fam for c in w["live"]])
        if k.any():
            ax.add_collection(LineCollection([xy(v) for v in w.loc[k & ~nd, "geom"]], colors=col, linewidths=1.1, label=f"{fam}* producers ({int(k.sum())})"))
            ax.add_collection(LineCollection([xy(v) for v in w.loc[k & nd, "geom"]], colors=col, linewidths=1.1, linestyles="dashed"))
    pw = pre.loc[pm.loc[pm["pad_id"].isin(ids), "i"].unique()]
    ax.add_collection(LineCollection([xy(v) for v in pw["geom"]], colors="#111827", linewidths=1.0, linestyles="dotted", label=f"spud / DUC / completed, not producing ({len(pw)})"))
    for pid, r in pg.iterrows():
        tag = ("U" if r["well_type"] == "uturn" else "") + ("S" if r["aspect"] < SQUARE_ASPECT else "")
        ax.text((r["cx"] - x0) / MI, (r["cy"] - y0) / MI, f"{pid}\n{tag}", fontsize=6.5, ha="center", va="center", color="#111827")
    for basin, _, code, eg in F["ext"]:
        if basin == a["basin"]:
            for part in shapely.get_parts(shapely.boundary(eg)):
                c = xy(part)
                if (np.abs(c) < a["size_mi"]).all(axis=1).any():
                    ax.plot(c[:, 0], c[:, 1], color="#059669", lw=1.0, ls="-.")
                    k = np.flatnonzero((np.abs(c) < a["size_mi"] / 2).all(axis=1))
                    if len(k):
                        ax.text(c[k[len(k) // 2], 0], c[k[len(k) // 2], 1], f"{code} extent edge", fontsize=7, color="#059669")
    lim = a["size_mi"] / 2 + 1.2
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.set_xlabel("miles east of the block centre (EPSG:3083)")
    ax.set_ylabel("miles north")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.set_title(f"{a['label']}\n{len(ids)} DSU polygons (number = pad_id; shade = producers in the DSU), {len(w):,} producers, {int(st['remaining'].sum()):,} remaining Novi sticks (grey)\n"
                 "orange outline / U = straight lateral under 7,000 ft (U-turn class); S = near-square (aspect under 1.15); dashed = producer with no depth evidence; "
                 "green dash-dot = a BOX extent edge", fontsize=10)
    f = out / f"pilot_map_{name}.png"
    p2a.save_fig(fig, f, dpi=120)
    plt.close(fig)
    return f.name


def run(out: Path, cache: Path, step: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    F = build_frame(cache)
    print(f"frame: {len(F['pads']):,} DSUs, {len(F['db']):,} DSU x bench, {len(F['u']):,} producers, {len(F['pre']):,} not yet producing, tags {F['tags']} pulled {F['pulled']}", flush=True)
    if step == "windows":
        for basin, focus in p2a.FOCUS:
            w = windows(F, basin, focus)
            w.to_csv(out / f"windows_{basin}_{focus}.csv", index=False)
            print(basin, focus, len(w), "candidate blocks", flush=True)
    if step == "areas":
        t, tl = dsu_table(F), two_landings(F)
        counts, benches, dsus, maps = [], [], [], []
        for name, a in AREAS.items():
            c, by, g = area_counts(F, name, a, t, tl)
            counts.append(c)
            benches.append(by)
            dsus.append(g.assign(area=name))
            maps.append(area_map(F, name, a, g, out))
            print(json.dumps(c, indent=1, default=str), flush=True)
            print(by.to_string(index=False), flush=True)
        pd.concat(benches).to_csv(out / "pilot_benches.csv", index=False)
        cols = ["area", "pad_id", "basin", "state", "lon", "lat", "acres", "long_ft", "short_ft", "aspect", "long_az_deg", "straight_ft", "well_type", "square", "benches",
                "carried", "no_depth", "low_conf", "producers", "producers_planned", "producers_no_depth", "preprod", "novi_sticks", "novi_remaining"]
        pd.concat(dsus)[cols].to_csv(out / "pilot_dsus.csv", index=False)
        d = F["db"].merge(pd.concat(dsus)[["pad_id", "area"]], on="pad_id")
        d.drop(columns=["in_bin"], errors="ignore").to_csv(out / "pilot_dsu_bench.csv", index=False)
        tl[tl["pad_id"].isin(d["pad_id"])].to_csv(out / "pilot_two_landings.csv", index=False)
        (out / "pilot_summary.json").write_text(json.dumps({"code_sha": p0._git_sha(), "tags": F["tags"], "cache_pulled": F["pulled"], "pad_vintage": p0.PAD_VINTAGE,
                                                            "member_frac": MEMBER_FRAC, "backtest_cutoff": str(BACKTEST_CUTOFF.date()), "areas": counts, "maps": maps},
                                                           indent=2, default=str), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--step", default="frame", choices=("frame", "windows", "areas"))
    a = ap.parse_args(argv)
    run(a.out, a.cache, a.step)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
