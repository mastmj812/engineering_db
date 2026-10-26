"""PDP-proximity study, step 1 — data pull, pair table, precedent atlas, page (READ ONLY).

Children = Delaware producing horizontals, first production >= 2016, landing TVD known, lateral >= 1,000 ft,
BOX exclusions dropped (docs/box/exclusions.csv — the El Campeon state-line double-booked laterals would read as
0-ft same-bench pairs). Candidates = every producing horizontal (any basin, any vintage) in the Delaware bbox.
Bench = curated.wells_enriched.formation_blueox (TVD-corrected, sql/06). Geometry = sql/47's lateral line
(LP -> BHL, else the whole stick) in UTM 13N feet (box.edge_gap.to_ft).

Outputs: <out>/ (committed: CSVs, summary.json, atlas.html) and <runs>/ (git-ignored: links.pkl, children.pkl).
Nothing is written to the warehouse.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import pickle
import time
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapely

from box import edge_gap as eg
from box import exclusions
from box import prox_study as ps
from box.edge_gap_report import _CSS, _png, _table
from box.spacing3d_report import cum_before, pull_cum
from box.tc_curve_report import _read

FP_MIN = dt.date(2016, 1, 1)
MIN_LATERAL_FT = 1000.0
OPP_RADIUS_FT = 10560.0        # "child bench developed within 2 mi of the parent"
OPP_PARENT_FP_MAX = dt.date(2022, 6, 30)  # parents with >= 4 yr of exposure to infill by the 2026-07 data
UPTAKE_RULES = ((300.0, 800.0), (300.0, 1400.0), (500.0, 1400.0), (1000.0, 2640.0))
MAIN_BENCHES = ("BS1_S", "BS2_C", "BS2_S", "BS3_C", "BS3_S", "WCXY", "WCA_1", "WCA_2", "WCB_1", "WCB_2", "WCC", "WCD", "AVA_2", "WDFD")
CLASSES = ("same", "topfill", "underfill")

_UNIVERSE_SQL = """
WITH bb AS (
    SELECT extensions.ST_Expand(extensions.ST_SetSRID(extensions.ST_Extent(w.wellstick_geom)::extensions.geometry, 4326), 0.05) AS g
    FROM curated.wells w JOIN curated.wells_enriched we ON we.api10 = w.api10
    WHERE we.basin_blueox = %(basin)s AND w.wellstick_geom IS NOT NULL
)
SELECT w.api10, COALESCE(we.formation_blueox, '(unmapped)') AS bench, we.basin_blueox, w.first_production_date, w.tvd_ft,
       extensions.ST_AsText(CASE
           WHEN w.landing_point_lat IS NOT NULL AND w.landing_point_lon IS NOT NULL
            AND NOT extensions.ST_Equals(extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                                         extensions.ST_EndPoint(w.wellstick_geom))
           THEN extensions.ST_MakeLine(extensions.ST_SetSRID(extensions.ST_Point(w.landing_point_lon, w.landing_point_lat), 4326),
                                       extensions.ST_EndPoint(w.wellstick_geom))
           ELSE w.wellstick_geom END)
FROM curated.wells w
LEFT JOIN curated.wells_enriched we ON we.api10 = w.api10
WHERE COALESCE(w.novi_slant_calculated, w.enverus_trajectory) ILIKE '%%horizontal%%'
  AND w.first_production_date IS NOT NULL AND w.wellstick_geom IS NOT NULL
  AND w.wellstick_geom && (SELECT g FROM bb)
"""

_DEV_SCENARIO_SQL = """
SELECT api10, bench, scenario_class, parent_benches_below, parent_benches_above
FROM curated.dev_scenario WHERE api10 = ANY(%(a)s)
"""


# ----------------------------------------------------------------------------
# Pull + pairs
# ----------------------------------------------------------------------------


def pull_universe(conn: Any, basin: str = "delaware") -> pd.DataFrame:
    """Every producing horizontal inside the basin's bounding box (+0.05 deg): the parents a PUD / child can have, any bench."""
    cols = ["api10", "bench", "basin", "fp", "tvd_ft", "wkt"]
    u = pd.DataFrame(_read(conn, _UNIVERSE_SQL, {"basin": basin}), columns=cols).drop_duplicates("api10").reset_index(drop=True)
    u["tvd_ft"] = pd.to_numeric(u["tvd_ft"], errors="coerce")
    u["geom"] = eg.to_ft([shapely.from_wkt(w) for w in u["wkt"]])
    u["lat_ft"] = [float(g.length) for g in u["geom"]]
    u, _ = exclusions.drop(u)
    return u.drop(columns="wkt")


def children_of(u: pd.DataFrame, basin: str = "delaware") -> pd.DataFrame:
    c = u[(u["basin"] == basin) & (u["fp"] >= FP_MIN) & u["tvd_ft"].notna() & (u["lat_ft"] >= MIN_LATERAL_FT)].copy()
    c["state"] = np.where(c["api10"].str.startswith("30"), "NM", np.where(c["api10"].str.startswith("42"), "TX", "?"))
    c["fp_year"] = [d.year for d in c["fp"]]
    return c.reset_index(drop=True)


def build_links(u: pd.DataFrame, kids: pd.DataFrame, log_every: int = 2000) -> pd.DataFrame:
    cand = u[u["tvd_ft"].notna() & (u["lat_ft"] > 0)].reset_index(drop=True)
    recs = cand[["api10", "bench", "fp", "tvd_ft", "geom"]].to_dict("records")
    tree = shapely.STRtree(list(cand["geom"]))
    pos = {a: i for i, a in enumerate(cand["api10"])}
    out: list[ps.Link] = []
    t0 = time.time()
    for n, a in enumerate(kids["api10"]):
        i = pos[a]
        me = recs[i]
        idx = tree.query(me["geom"], predicate="dwithin", distance=ps.PAIR_GATE_FT)
        out.extend(ps.links_for_child(me, (recs[j] for j in idx if j != i)))
        if log_every and n and n % log_every == 0:
            print(f"  pairs: {n:,}/{len(kids):,} children, {len(out):,} links, {time.time() - t0:.0f} s", flush=True)
    return pd.DataFrame([vars(k) for k in out])


def attach_parent_cum(conn: Any, links: pd.DataFrame, u: pd.DataFrame, kids: pd.DataFrame) -> pd.DataFrame:
    """Parent cum oil at the child's first production (bbl) and per 1,000 ft of parent lateral — the depletion dose
    step 2 needs. Read for depleting/young parents within 1,000 ft vertical only."""
    want = links[(links["rel"].isin(["parent", "young"])) & (links["dv_ft"] <= 1000)]
    series = pull_cum(conn, sorted(set(want["parent"])))
    fp = dict(zip(kids["api10"], kids["fp"]))
    lat = dict(zip(u["api10"], u["lat_ft"]))
    cum = np.full(len(links), np.nan)
    for k in want.index:
        cum[k] = cum_before(series.get(links.at[k, "parent"]), fp[links.at[k, "child"]])
    links = links.copy()
    links["parent_cum_bbl"] = cum
    links["parent_lat_ft"] = links["parent"].map(lat)
    links["parent_cum_bbl_per_kft"] = links["parent_cum_bbl"] / (links["parent_lat_ft"] / 1000.0)
    return links


def opportunity(u: pd.DataFrame, benches: tuple[str, ...] = MAIN_BENCHES, basin: str = "delaware") -> dict[tuple[str, str], set[str]]:
    """Parents (the basin's, first production <= OPP_PARENT_FP_MAX, any vintage start) whose lateral lies within 2 mi of
    a >= 2016 producer of the child bench — that bench is a live target around this parent."""
    del_u = u[(u["basin"] == basin) & (u["lat_ft"] > 0)]
    targets = {b: del_u[(del_u["bench"] == b) & (del_u["fp"] >= FP_MIN)] for b in benches}
    trees = {b: shapely.STRtree(list(t["geom"])) for b, t in targets.items() if len(t)}
    out: dict[tuple[str, str], set[str]] = {}
    for pb in benches:
        par = del_u[(del_u["bench"] == pb) & (del_u["fp"] <= OPP_PARENT_FP_MAX)]
        for cb, tr in trees.items():
            hit = tr.query(list(par["geom"]), predicate="dwithin", distance=OPP_RADIUS_FT)
            par_ids = par["api10"].to_numpy()[hit[0]]
            tgt_ids = targets[cb]["api10"].to_numpy()[hit[1]]
            ids = set(par_ids[par_ids != tgt_ids])  # same bench: a target OTHER than the parent itself
            out[(pb, cb)] = ids
    return out


# ----------------------------------------------------------------------------
# Reconciliation vs sql/50
# ----------------------------------------------------------------------------


def reconcile_sql50(conn: Any, links: pd.DataFrame, kids: pd.DataFrame) -> pd.DataFrame:
    """sql/50 'has a vertical parent' (other bench, midpoint offset <= 660, |dz| <= 1,000, parent > 180 d, shielded
    counted) vs ours under the closest equivalent (other POOL, median gap <= 660, dv <= 1,000, age > 180 d,
    shielded counted, permit TVDs kept). The gates differ by construction (midpoint offset vs median gap; bench vs
    pool) — this measures how much, per child bench."""
    rows: list[tuple[Any, ...]] = []
    ids = list(kids["api10"])
    for i in range(0, len(ids), 5000):
        rows += _read(conn, _DEV_SCENARIO_SQL, {"a": ids[i : i + 5000]})
    ds = pd.DataFrame(rows, columns=["api10", "ds_bench", "scenario_class", "below", "above"])
    ds["sql50_vertical_parent"] = [bool(b) or bool(a) for b, a in zip(ds["below"], ds["above"])]
    q = links[links["rel"].isin(["parent", "young"]) & (links["cls"] != "same") & (links["dv_ft"] <= 1000) & (links["dh_ft"] <= 660)]
    ours = set(q["child"])
    m = kids[["api10", "bench"]].merge(ds[["api10", "sql50_vertical_parent"]], on="api10", how="left")
    m["sql50_vertical_parent"] = m["sql50_vertical_parent"].astype("boolean").fillna(False).astype(bool)
    m["ours"] = m["api10"].isin(ours)
    g = m.groupby("bench").agg(n=("api10", "size"), sql50=("sql50_vertical_parent", "sum"), ours=("ours", "sum"),
                               both=("ours", lambda s: int((s & m.loc[s.index, "sql50_vertical_parent"]).sum())))
    g["agree_pct"] = 100.0 * (g["n"] - (g["sql50"] - g["both"]) - (g["ours"] - g["both"])) / g["n"]
    tot = g[["n", "sql50", "ours", "both"]].sum()
    g.loc["ALL"] = [*tot.tolist(), 100.0 * (tot["n"] - (tot["sql50"] - tot["both"]) - (tot["ours"] - tot["both"])) / tot["n"]]
    return g.reset_index().sort_values("n", ascending=False)


# ----------------------------------------------------------------------------
# Atlas tables + figures
# ----------------------------------------------------------------------------


def atlas(links: pd.DataFrame, kids: pd.DataFrame, opp: dict[tuple[str, str], set[str]]) -> dict[str, Any]:
    main = kids[kids["bench"].isin(MAIN_BENCHES)]
    res: dict[str, Any] = {"grids": {c: ps.grid(links, cls=c) for c in CLASSES}}
    res["grids"]["any"] = ps.grid(links)
    res["by_bench"] = ps.share_table(main, links)
    res["by_bench_1400"] = ps.share_table(main, links, rule=(300.0, 1400.0))
    # same-pool horizontal sweep, by state
    rows = []
    for st, g in main.groupby("state"):
        ids = set(g["api10"])
        near = ps.nearest_by_child(links[links["child"].isin(ids)], 1500.0, cls="same")
        rows.append({"state": st, "n_children": len(ids), **{f"le_{x}": int((near <= x).sum()) for x in ps.X_GRID}})
    res["same_by_state"] = pd.DataFrame(rows)
    # per-bench topfill/underfill parent-bench matrix at the v14 rule
    q = ps.qualifying(links, cls=["topfill", "underfill"])
    q = q[(q["dv_ft"] <= 300) & (q["dh_ft"] <= 800) & q["child_bench"].isin(MAIN_BENCHES)]
    res["pairs_v14"] = (q.groupby(["child_bench", "parent_bench", "cls"])["child"].nunique().rename("n_children").reset_index()
                        .sort_values("n_children", ascending=False))
    up = []
    for z, x in UPTAKE_RULES:
        t = ps.uptake(pd.DataFrame(), links, opp, rule=(z, x))
        t.insert(0, "rule", f"{z:,.0f} vt / {x:,.0f} hz")
        up.append(t)
    res["uptake"] = pd.concat(up, ignore_index=True)
    # age of the parent at the child's first production, for the v14 violators (how depleted were they?)
    v = ps.qualifying(links)
    v = v[(v["dv_ft"] <= 300) & (v["dh_ft"] <= 800)]
    age = v.groupby("cls")["age_days"].describe(percentiles=[0.1, 0.5, 0.9])
    age[["mean", "std", "min", "10%", "50%", "90%", "max"]] = (age[["mean", "std", "min", "10%", "50%", "90%", "max"]] / 365.25).round(2)
    age["n_links"] = age.pop("count").astype(int)
    age["parent_cum_kbbl_per_kft_p50"] = (v.groupby("cls")["parent_cum_bbl_per_kft"].median() / 1000.0).round(1)
    res["violator_parent_age_yr"] = age
    res["fp_year"] = (main.assign(viol=main["api10"].isin(ps.exposed(links, 300, 800)))
                      .groupby("fp_year").agg(n=("api10", "size"), v14_violators=("viol", "sum")).reset_index())
    res["fp_year"]["pct"] = 100.0 * res["fp_year"]["v14_violators"] / res["fp_year"]["n"]
    return res


def nearest_points(links: pd.DataFrame, cls: str) -> pd.DataFrame:
    """Per child, its nearest depleting parent of the class by the v14 rule's aspect (dh + 8/3 x dv) — the scatter."""
    q = ps.qualifying(links, cls=cls)
    q = q[(q["dv_ft"] <= 1500) & (q["dh_ft"] <= ps.PAIR_GATE_FT)]
    if q.empty:
        return q
    k = np.hypot(q["dh_ft"], q["dv_ft"] * ps.RULE_V14[1] / ps.RULE_V14[0])
    return q.loc[k.groupby(q["child"]).idxmin()]


def scatter_png(links: pd.DataFrame) -> str:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), sharey=False)
    for ax, cls in zip(axes, CLASSES):
        p = nearest_points(links, cls)
        y = p["dz_ft"] if cls != "same" else p["dv_ft"]
        ax.hexbin(p["dh_ft"], y, gridsize=40, extent=(0, 2640, -1500 if cls == "underfill" else 0, 0 if cls == "underfill" else 1500) if cls != "same" else (0, 2640, 0, 400),
                  mincnt=1, cmap="Blues", bins="log")
        z, x = ps.RULE_V14
        if cls == "topfill":
            ax.add_patch(plt.Rectangle((0, 0), x, z, fill=False, ec="#dc2626", lw=1.5))
        elif cls == "underfill":
            ax.add_patch(plt.Rectangle((0, -z), x, z, fill=False, ec="#dc2626", lw=1.5))
        else:
            ax.axvline(x, color="#dc2626", lw=1.2)
            ax.axvline(1400, color="#d97706", lw=1.2, ls="--")
        ax.set_title(f"{cls}: nearest ≥12-mo parent per child (n={len(p):,})", fontsize=10)
        ax.set_xlabel("median horizontal gap, ft")
        ax.set_ylabel({"same": "|dz| ft (same pool)", "topfill": "parent below child, ft", "underfill": "parent above child, ft (−)"}[cls])
    fig.tight_layout()
    return _png(fig)


def grid_png(g: pd.DataFrame, title: str) -> str:
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.imshow(g.to_numpy(), cmap="Blues", aspect="auto")
    ax.set_xticks(range(len(g.columns)), [f"{c:,}" for c in g.columns], fontsize=8)
    ax.set_yticks(range(len(g.index)), [f"{r:,}" for r in g.index], fontsize=8)
    for i in range(g.shape[0]):
        for j in range(g.shape[1]):
            v = int(g.iat[i, j])
            ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=7, color="white" if v > g.to_numpy().max() * 0.55 else "#111827")
    ax.set_xlabel("horizontal ≤ ft")
    ax.set_ylabel("vertical ≤ ft")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    return _png(fig)


def render(ctx: dict[str, Any]) -> str:
    a, s = ctx["atlas"], ctx["summary"]
    esc = html.escape
    up = a["uptake"]
    up_main = up[up["child_bench"].isin(MAIN_BENCHES) & up["parent_bench"].isin(MAIN_BENCHES)]
    parts = [
        f"<!doctype html><html><head><meta charset=utf-8><title>PDP proximity atlas</title><style>{_CSS}</style></head><body>",
        "<h1>PDP-proximity study — step 1: precedent atlas (Delaware)</h1>",
        (f"<div class=meta>{esc(s['built'])} · data through curated.production as read · children {s['n_children']:,} "
         f"(Delaware producing horizontals, FP ≥ 2016) · links {s['n_links']:,} · read-only</div>"),
        ("<p>A <b>depleting parent</b> is an older producer whose first production came ≥ 12 months before the child's. "
        "Overlap is ≥ 30 % of the child's lateral. Gap = median perpendicular distance over the shared span, i.e. the "
        "deal-intake v14 metric. Permit-round TVDs and shielded parents are excluded unless stated. "
        "The red box is the provisional v14 rule (300 ft vt / 800 ft hz); the dashed line is 1,400 ft.</p>"),
        "<h2>Where drilled wells sit relative to their nearest depleting parent</h2>", f"<img src='{scatter_png(ctx['links'])}'>",
        "<h2>How many drilled children would a rectangle rule have forbidden?</h2>",
        "<p>Cumulative count of children with ≥ 1 depleting parent inside (vertical ≤ row, horizontal ≤ column).</p>",
    ]
    for c in (*CLASSES, "any"):
        parts.append(f"<img src='{grid_png(a['grids'][c], f'{c} — children inside the rectangle')}'>")
    parts += [
        "<h2>By child bench — share of drilled wells that violate the v14 rule</h2>",
        _table(a["by_bench"], {"pct_any": ".1f"}),
        "<h2>Same rule with 1,400 ft horizontal</h2>", _table(a["by_bench_1400"], {"pct_any": ".1f"}),
        "<h2>Bench pairs among v14 violators (vertical classes)</h2>", _table(a["pairs_v14"], max_rows=40),
        "<h2>Same-pool horizontal spacing to the nearest depleting parent, by state</h2>",
        "<p>Children whose nearest same-pool parent (≥ 12 mo older, ≥ 30 % alongside) is within each gap.</p>",
        _table(a["same_by_state"]),
        "<h2>Uptake — revealed preference</h2>",
        (f"<p>Parents with first production ≤ {OPP_PARENT_FP_MAX} (≥ 4 yr exposure), where the child bench has a ≥ 2016 "
        "producer within 2 mi. Each row is the share of those parents that later received a child of that bench inside "
        "the rule. Pairs with fewer than 30 opportunities are omitted.</p>"),
        _table(up_main, {"pct_infilled": ".1f"}, max_rows=120),
        "<h2>Parent age at the child's first production (v14 violators, years)</h2>",
        _table(a["violator_parent_age_yr"].reset_index(), {c: ".2f" for c in a["violator_parent_age_yr"].columns if c != "n_links"}),
        "<h2>v14 violators by child first-production year</h2>", _table(a["fp_year"], {"pct": ".1f"}),
        "<h2>Reconciliation vs sql/50 (curated.dev_scenario)</h2>",
        ("<p>sql/50's 'has vertical parent' flag compared with ours under the nearest equivalent gate: other pool, median "
        "gap ≤ 660, dv ≤ 1,000, age > 180 d, shielded counted. The gates differ by construction (midpoint offset vs "
        "median gap; bench vs pool).</p>"),
        _table(ctx["reconcile"], {"agree_pct": ".1f"}),
        "</body></html>",
    ]
    return "\n".join(parts)


def run(conn: Any, out: Path, runs: Path) -> dict[str, Any]:
    t0 = time.time()
    u = pull_universe(conn)
    kids = children_of(u)
    print(f"universe {len(u):,}, children {len(kids):,} ({time.time() - t0:.0f} s)", flush=True)
    links = build_links(u, kids)
    print(f"links {len(links):,} ({time.time() - t0:.0f} s)", flush=True)
    links = attach_parent_cum(conn, links, u, kids)
    opp = opportunity(u)
    rec = reconcile_sql50(conn, links, kids)
    a = atlas(links, kids, opp)
    out.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    with open(runs / "links.pkl", "wb") as f:
        pickle.dump(links, f)
    with open(runs / "children.pkl", "wb") as f:
        pickle.dump(kids.drop(columns="geom"), f)
    for c, g in a["grids"].items():
        g.to_csv(out / f"grid_{c}.csv")
    for k in ("by_bench", "by_bench_1400", "pairs_v14", "same_by_state", "uptake", "fp_year"):
        a[k].to_csv(out / f"{k}.csv", index=False)
    a["violator_parent_age_yr"].to_csv(out / "violator_parent_age.csv")
    rec.to_csv(out / "reconcile_sql50.csv", index=False)
    summary = {"built": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"), "n_universe": len(u), "n_children": len(kids),
               "n_links": len(links), "n_depleting_links": int((links["rel"] == "parent").sum()),
               "v14_violators_any": len(ps.exposed(links, *ps.RULE_V14)),
               "params": {"min_overlap": ps.MIN_OVERLAP, "parent_min_days": ps.PARENT_MIN_DAYS, "codev_days": ps.CODEV_DAYS,
                          "pair_gate_ft": ps.PAIR_GATE_FT, "store_dv_ft": ps.STORE_DV_FT, "fp_min": str(FP_MIN),
                          "opp_radius_ft": OPP_RADIUS_FT, "opp_parent_fp_max": str(OPP_PARENT_FP_MAX)},
               "seconds": round(time.time() - t0)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "atlas.html").write_text(render({"atlas": a, "summary": summary, "links": links, "reconcile": rec}), encoding="utf-8")
    return {"summary": summary, "atlas": a, "reconcile": rec}
