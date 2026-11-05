"""Score rule v3 ONCE against the frozen criteria (read-only) — step 2 of docs/formation_tag_redesign/PLAN.md.

    python -m scripts.tag_rule_score --cache <scoreboard cache> --out docs/formation_tag_redesign/step2-score-<date>

Rule and criteria: docs/formation_tag_redesign/RULE.md (frozen 1be65da). Candidates:
  vendor  crosswalk only;  live  wells_enriched.formation_blueox today;
  rule    box.tag_rule, no overrides;  final  seeds/formation_tag_overrides.csv where present, else rule.
Producers come from the scoreboard's cached pull (2026-11-05). Sticks (curated.intel_locations, non-PDP), the BOX
record pools, scout labels and reconciliation are read here under SET TRANSACTION READ ONLY. Nothing is written to
the warehouse.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import extent_package as pkg
from box import tag_rule as tr
from box import tag_scoreboard as sb
from scripts import tag_rule_dev as dev
from scripts import tag_scoreboard as sbs

OPEN_BOUNDARY = {("WCB_2", None), ("BS3_S", "Lea"), ("BS3_S", "Ward"), ("WCXY", "Lea"), ("WCXY", "Ward")}
LEA_ANOM = sb.ROOT / "docs" / "lea_eddy_wc_tags" / "sticks_anomalous.csv"

_STICK_SQL = """
SELECT il.stick_id, il.basin, il.county, il.category, il.formation AS novi_formation, il.pad_name, il.tvd::float8 AS tvd,
       il.midpoint_lon, il.midpoint_lat, ifb.formation_blueox AS live, ifb.formation_blueox_source AS live_source,
       CASE WHEN il.midpoint_lon IS NOT NULL THEN extensions.ST_AsText(extensions.ST_Transform(
            extensions.ST_SetSRID(extensions.ST_MakePoint(il.midpoint_lon, il.midpoint_lat), 4326), 3083)) END AS mid_wkt
FROM curated.intel_locations il
JOIN curated.intel_formation_blueox ifb USING (stick_id)
WHERE il.basin IN ('delaware', 'midland') AND ifb.formation_blueox_source IS DISTINCT FROM 'pdp_join'
"""
_POOL_SQL = """
SELECT m.api10, a.basin, a.bench AS pool, m.included
FROM box.tc_member m JOIN box.type_curve tc USING (tc_id) JOIN box.tc_area ta USING (area_id) JOIN box.extent a USING (extent_id)
WHERE tc.is_record AND tc.stream = 'oil' AND m.included
"""
_RECORD_STICKS_SQL = """
SELECT pf.stick_id, pf.basin, pf.bench, pf.coverage, fr.run_id
FROM box.pud_forecast pf JOIN box.forecast_run fr USING (run_id) WHERE fr.is_record
"""
_SCOUT_SQL = "SELECT stick_id, basin, bench FROM curated.box_scout_locations"
_RECON_SQL = "SELECT stick_id, basin_blueox AS basin, formation_blueox, matched_api10, status FROM curated.reconciled_inventory"


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def pull_context(cache: Path) -> dict[str, pd.DataFrame]:
    f = cache / "step2_context.pkl"
    if f.exists():
        return pd.read_pickle(f)
    from etl.db import get_connection

    with get_connection() as conn:
        ctx = {k: sb._read(conn, q, {}) for k, q in
               {"sticks": _STICK_SQL, "pools": _POOL_SQL, "record_sticks": _RECORD_STICKS_SQL, "scout": _SCOUT_SQL, "recon": _RECON_SQL}.items()}
    for k in ("pools", "recon"):
        for c in ("api10", "matched_api10"):
            if c in ctx[k]:
                ctx[k][c] = ctx[k][c].astype("string")
    pd.to_pickle(ctx, f)
    return ctx


def stick_pairs(sticks: pd.DataFrame, prod: pd.DataFrame, radius_m: float, chunk: int = 20_000) -> pd.DataFrame:
    """(i stick row, j producer row, d m): stick midpoint to the nearest of the producer's lateral points, same basin."""
    xy, own = [], []
    for j, p in enumerate(prod["pts"]):
        q = p[::2] if len(p) > 2 else p
        xy.extend(q)
        own.extend([j] * len(q))
    pxy, pown = np.asarray(xy, float), np.asarray(own, int)
    tree = cKDTree(pxy)
    sxy = np.array([p[0] if p else (np.nan, np.nan) for p in sticks["pts"]], float)
    sb_, pb = sticks["basin"].to_numpy(), prod["basin"].to_numpy()
    parts = []
    for s0 in range(0, len(sticks), chunk):
        idx = np.arange(s0, min(s0 + chunk, len(sticks)))
        ok = idx[np.isfinite(sxy[idx, 0])]
        hits = tree.query_ball_point(sxy[ok], radius_m)
        ii = np.repeat(ok, [len(h) for h in hits])
        jj = np.concatenate([np.asarray(h, int) for h in hits]) if len(ii) else np.zeros(0, int)
        if not len(ii):
            continue
        d = np.hypot(sxy[ii, 0] - pxy[jj, 0], sxy[ii, 1] - pxy[jj, 1])
        t = pd.DataFrame({"i": ii, "j": pown[jj], "d": d}).groupby(["i", "j"], as_index=False)["d"].min()
        parts.append(t[sb_[t["i"]] == pb[t["j"]]])
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["i", "j", "d"])


def grid_table_open(g: pd.DataFrame, cand: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a grid frame into open-boundary and other wells for the candidate's own tag."""
    is_open = [(t, None) in OPEN_BOUNDARY or (t, c) in OPEN_BOUNDARY for t, c in zip(g[cand], g["county"], strict=True)]
    m = pd.Series(is_open, index=g.index)
    return g[m], g[~m]


def run(cache: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    w = pd.read_pickle(cache / "wells.pkl")
    st = pd.read_pickle(cache / "stations.pkl")
    order = sb.bench_order()
    labels = sb.labelled_set()

    # ---- producers: the rule
    d = dev.prepare(w)
    pairs = dev.rule_pairs(d)
    grid = dev.grid_for(d, st, order)
    res = tr.assign_producers(d, pairs, order, grid)
    d = d.join(res[["family", "family_basis", "family_flag", "rule", "position_basis", "confidence", "position_margin_ft"]])
    ovr = pd.read_csv(sb.OVERRIDE_SEED, dtype={"api10": str}).set_index("api10")["corrected_code"]
    d["override"] = d["api10"].map(ovr)
    d["final"] = d["override"].where(d["override"].notna(), d["rule"])
    for c in ("vendor", "live", "rule", "final"):
        d[c] = d[c].where(d[c].notna(), "(unmapped)")
    d[["api10", "basin", "county", "operator", "well_name", "vendor", "live", "rule", "final", "override", "family", "family_basis",
       "family_flag", "position_basis", "confidence", "position_margin_ft", "depth_ft", "depth_source", "evidence", "fold",
       "live_source", "first_production_date", "midpoint_lon", "midpoint_lat"]].to_csv(out / "producers_rule.csv.gz", index=False)

    S: dict[str, Any] = {"git_sha": _git_sha(), "rule": tr.rule_record(), "criteria": {}, "reported": {}}
    K = S["criteria"]

    # ---- K1-K3 labels (rule, all wells, clean frame)
    clean = d[d["evidence"]].reset_index(drop=True)
    ls = sb.label_score(clean, "rule", labels)
    ls.to_csv(out / "labels_rule.csv", index=False)
    car = ls[ls["tier"] == "carded"].set_index("basin")
    K["K1"] = {"carded_pct": car["reproduced_pct"].round(1).to_dict(), "pass": bool((car["reproduced_pct"] >= 70).all() and len(car) == 2)}
    ca = ls[(ls["tier"] == "class_accepted") & (ls["basin"] == "midland")]
    K["K2"] = {"class_accepted_pct": float(ca["reproduced_pct"].iloc[0]) if len(ca) else None,
               "pass": bool(len(ca) and ca["reproduced_pct"].iloc[0] >= 70)}
    holds = labels[labels["tier"] == "hold"].merge(d[["api10", "vendor", "rule", "confidence", "position_basis"]], on="api10", how="left")
    holds["ok"] = (holds["rule"] == holds["vendor"]) | (holds["confidence"] != "high")
    K["K3"] = {"holds": holds[["api10", "vendor", "rule", "confidence", "position_basis"]].to_dict("records"), "pass": bool(holds["ok"].all() and len(holds) == 3)}
    lab_detail = labels.merge(d[["api10", "basin", "vendor", "live", "rule", "final", "family_basis", "position_basis", "confidence", "evidence"]],
                              on="api10", how="left")
    lab_detail.to_csv(out / "labels_detail.csv", index=False)

    # ---- K4-K6 grid (Delaware test fold, final vs live)
    stations, depths, mid = sbs.grid_frame(clean, st)
    dist = sbs.control_distances(mid)
    de = clean[(clean["basin"] == "delaware")].set_index("api10")
    test_ids = set(de.index[de["fold"] == "test"])
    gtabs = {}
    for cand in ("live", "final", "rule", "vendor"):
        tags = de[cand]
        gv = sb.grid_verdicts(stations, depths, tags, de["county"])
        gv["grid_controlled"] = pd.Series(sb.controlled(tags.reindex(mid["api10"]), mid[["x", "y"]].to_numpy(float), dist, pkg.TRUST_MAX_FT),
                                          index=mid["api10"].to_numpy()).reindex(gv.index).fillna(False)
        g = de[[cand, "county", "fold"]].join(gv)
        g = g[g.index.isin(test_ids)]
        gtabs[cand] = g
        sb.grid_table(g, [cand]).to_csv(out / f"grid_test_by_bench_{cand}.csv", index=False)
    ov = {c: sb.grid_table(g.assign(all="all"), ["all"]).iloc[0] for c, g in gtabs.items()}
    K["K4"] = {"agree_pct": {c: round(float(v["agree_pct"]), 2) for c, v in ov.items()},
               "pass": bool(ov["final"]["agree_pct"] >= ov["live"]["agree_pct"])}
    bl, bf = (sb.grid_table(gtabs[c], [c]).rename(columns={c: "bench"}).set_index("bench") for c in ("live", "final"))
    j = bl[["scored", "agree_pct"]].join(bf[["scored", "agree_pct"]], lsuffix="_live", rsuffix="_final", how="inner")
    j = j[(j["scored_live"] >= 200) & (j["scored_final"] >= 200)]
    j["delta"] = j["agree_pct_final"] - j["agree_pct_live"]
    j.round(2).to_csv(out / "K5_grid_per_bench.csv")
    K["K5"] = {"worst_delta_pt": round(float(j["delta"].min()), 2), "per_bench": j["delta"].round(2).to_dict(), "pass": bool((j["delta"] >= -1.0).all())}
    ctl = {}
    for c in ("live", "final"):
        _, rest = grid_table_open(gtabs[c], c)
        rest = rest[rest["grid_verdict"].isin(["agree", "shallow", "deep"]) & rest["grid_controlled"]]
        ctl[c] = (100 * float((rest["grid_verdict"] == "agree").mean()), len(rest))
    K["K6"] = {"controlled_agree_pct_excl_open": {c: round(v[0], 2) for c, v in ctl.items()}, "n": {c: v[1] for c, v in ctl.items()},
               "pass": bool(ctl["final"][0] >= ctl["live"][0] + 0.5)}
    S["reported"]["grid_family_basis_wells"] = int((d["family_basis"] == "grid").sum())
    S["reported"]["grid_family_moves"] = int(((d["family_basis"] == "grid") & (d["family"] != [tr.family(b, c) for b, c in zip(d["basin"], d["vendor"], strict=True)])).sum())

    # ---- K7-K9 self-consistency (test fold, 1 mi, scoreboard params)
    p1 = sb.neighbour_pairs(clean, 1.0 * sb.M_PER_MI)
    p25 = p1[p1["d"] <= sb.DEFAULT.pair_mi * sb.M_PER_MI]
    tmask = clean["fold"].to_numpy() == "test"
    selfc: dict[str, Any] = {}
    for cand in ("vendor", "live", "rule", "final"):
        bands = sb.local_bands(clean, cand, p1, sb.DEFAULT.min_band_n)
        f = clean.join(sb.band_test(clean, cand, bands, order, sb.DEFAULT.margin_ft))
        bt = sb.band_table(f[tmask], ["basin"]).set_index("basin")["disagree_pct"]
        sb.band_table(f[tmask], ["basin", cand]).query("wells >= 100").to_csv(out / f"band_test_by_bench_{cand}.csv", index=False)
        inv = sb.pair_inversions(clean, cand, p25, order, sb.DEFAULT.pair_mi * sb.M_PER_MI, sb.DEFAULT.inv_ft)
        inv = inv[tmask[inv["i"].to_numpy()]]
        it = sb.inversion_table(inv).set_index(["basin", "span"])["inverted_pct"]
        sep = sb.band_separation(clean[tmask].reset_index(drop=True), sb.local_bands(clean[tmask].reset_index(drop=True), cand,
                                 sb.neighbour_pairs(clean[tmask].reset_index(drop=True), sb.M_PER_MI), 3), order, 50)
        sep.to_csv(out / f"band_separation_test_{cand}.csv", index=False)
        selfc[cand] = {"band": bt.round(2).to_dict(), "inv": {f"{b}|{s}": round(float(v), 3) for (b, s), v in it.items()}}
    S["reported"]["self_consistency_test_fold"] = selfc
    lv, fn = selfc["live"], selfc["final"]
    K["K7"] = {"band_pct": {c: selfc[c]["band"] for c in ("live", "final")}, "pass": all(fn["band"][b] < lv["band"][b] for b in ("delaware", "midland"))}
    K["K8"] = {"inv_2plus_pct": {c: {b: selfc[c]["inv"][f"{b}|2+ apart"] for b in ("delaware", "midland")} for c in ("live", "final")},
               "pass": all(fn["inv"][f"{b}|2+ apart"] <= lv["inv"][f"{b}|2+ apart"] for b in ("delaware", "midland"))}
    K["K9"] = {"inv_adjacent_pct": {c: {b: selfc[c]["inv"][f"{b}|adjacent"] for b in ("delaware", "midland")} for c in ("live", "final")},
               "pass": all(fn["inv"][f"{b}|adjacent"] <= lv["inv"][f"{b}|adjacent"] for b in ("delaware", "midland"))}

    # ---- K10-K11 guards (all wells, rule vs vendor)
    vf = pd.Series([tr.family(b, c) for b, c in zip(d["basin"], d["vendor"], strict=True)], index=d.index)
    rf = pd.Series([tr.family(b, c) for b, c in zip(d["basin"], d["rule"], strict=True)], index=d.index)
    mv = d["rule"] != d["vendor"]
    g10 = {"protected": int((mv & (d["vendor"].isin(tr.PROTECTED) | d["rule"].isin(tr.PROTECTED))).sum()),
           "lithology": int(sum(mv & pd.Series([any({a, b} <= p for p in tr.LITH_PAIRS) for a, b in zip(d["vendor"], d["rule"], strict=True)], index=d.index))),
           "xy_lea_ward": int((mv & d["county"].isin(tr.RULE_B_COUNTIES) & pd.Series([tr._crosses_xy(b, a, c) for b, a, c in zip(d["basin"], vf, rf, strict=True)],
                                                                                     index=d.index)).sum())}
    K["K10"] = {**g10, "pass": sum(g10.values()) == 0}
    fm = d.assign(fm=vf != rf).groupby("basin")["fm"].mean() * 100
    K["K11"] = {"family_moved_pct": fm.round(2).to_dict(), "pass": bool((fm <= 5.0).all())}
    churn = d.assign(code_moved=mv, fam_moved=vf != rf, vs_live=d["final"] != d["live"]).groupby("basin")[["code_moved", "fam_moved", "vs_live"]].sum()
    churn.to_csv(out / "producer_churn.csv")
    d[d["final"] != d["live"]].groupby(["basin", "live", "final"]).size().rename("n").reset_index().sort_values("n", ascending=False) \
        .to_csv(out / "producer_moves_live_to_final.csv", index=False)
    d[d["evidence"]].groupby(["basin", "family", "confidence"]).size().unstack(fill_value=0).to_csv(out / "confidence_by_family.csv")

    # ---- sticks
    ctx = pull_context(cache)
    sk = ctx["sticks"].copy()
    sk["tvd"] = pd.to_numeric(sk["tvd"], errors="coerce")
    sk["pts"] = [sb.parse_points(m) for m in sk["mid_wkt"]]
    sk["depth_ft"] = sk["tvd"]
    sk["evidence"] = sk["tvd"].notna() & (sk["tvd"] >= sb.MIN_EVIDENCE_TVD_FT) & sk["pts"].map(bool)
    sk["vendor"] = sk["live"].where(sk["live"].notna(), None)
    sk = sk.reset_index(drop=True)
    prod_codes = d["final"].where(d["final"] != "(unmapped)", None).to_numpy(object)
    sp = stick_pairs(sk, d, max(tr.RULE.fam_radius_mi, tr.RULE.pos_radius2_mi) * sb.M_PER_MI)
    sgrid = stick_grid(sk, order)
    sres = tr.assign_sticks(sk, d, prod_codes, sp, order, sgrid)
    sk = sk.join(sres[["family", "family_basis", "family_flag", "rule", "position_basis", "confidence", "position_margin_ft"]])
    sk["rule"] = sk["rule"].where(sk["rule"].notna(), sk["vendor"])
    sk["moved"] = sk["rule"].fillna("~") != sk["vendor"].fillna("~")
    sk[["stick_id", "basin", "county", "category", "novi_formation", "pad_name", "tvd", "live", "live_source", "rule", "family_basis",
        "family_flag", "position_basis", "confidence", "position_margin_ft"]].to_csv(out / "sticks_rule.csv.gz", index=False)
    p3240 = sk[(sk["pad_name"] == "Delaware Pad 3240") & (sk["family"] == "WCB")]
    K["K12"] = {"pad_3240": p3240[["stick_id", "live", "rule", "confidence"]].to_dict("records"),
                "pass": bool(len(p3240) > 0 and (p3240["rule"] == "WCB_1").all())}
    an = pd.read_csv(LEA_ANOM, dtype={"stick_id": str})
    an = an[an["county"] == "Lea"]
    sk["stick_id"] = sk["stick_id"].astype(str)
    hit = sk[sk["stick_id"].isin(an["stick_id"])]
    share = float((hit["family_flag"] == "family_conflict").mean()) if len(hit) else float("nan")
    K["K13"] = {"lea_anomalous": len(an), "found": len(hit), "flagged_pct": round(100 * share, 1), "pass": bool(len(hit) and share >= 0.5)}
    stick_rep = sk.groupby(["basin", "live_source"]).agg(sticks=("stick_id", "size"), moved=("moved", "sum"),
                                                         flagged=("family_flag", lambda s: int((s == "family_conflict").sum())))
    stick_rep.to_csv(out / "stick_churn.csv")
    sk.groupby(["basin", "position_basis"]).size().rename("n").reset_index().to_csv(out / "stick_position_basis.csv", index=False)
    sk[sk["moved"]].groupby(["basin", "live", "rule"]).size().rename("n").reset_index().sort_values("n", ascending=False).to_csv(out / "stick_moves.csv", index=False)
    # stick-like distance: median distance from a multi-code-family stick to its nearest same-basin producer lateral
    multi = sk[sk["family"].isin(["AVA", "WCA", "WCB"])]
    S["reported"]["stick_nearest_producer_mi_median"] = round(float(sp.groupby("i")["d"].min().reindex(multi.index).median() / sb.M_PER_MI), 2) \
        if len(multi) else None
    S["reported"]["multi_family_sticks_without_producer_within_1p5mi"] = int(multi.index.difference(sp["i"].unique()).size)

    # ---- blast radius
    pools = ctx["pools"].merge(d[["api10", "live", "final"]], on="api10", how="left")
    codes = pools.groupby(["basin", "pool"])["live"].agg(lambda s: set(s.dropna()))
    pools["pool_codes"] = [codes.get((b, p), set()) for b, p in zip(pools["basin"], pools["pool"], strict=True)]
    pools["leaves"] = [f not in c for f, c in zip(pools["final"], pools["pool_codes"], strict=True)]
    pools["code_changes"] = pools["final"] != pools["live"]
    pools.groupby(["basin", "pool"]).agg(members=("api10", "size"), code_changes=("code_changes", "sum"), leaves=("leaves", "sum")) \
        .to_csv(out / "blast_box_record_pools.csv")
    sid = sk.set_index("stick_id")
    rs = ctx["record_sticks"].assign(stick_id=lambda x: x["stick_id"].astype(str))
    rs["rule"] = rs["stick_id"].map(sid["rule"])
    rs["changes"] = rs["rule"].notna() & (rs["rule"] != rs["bench"])
    rs.groupby(["basin", "coverage"]).agg(sticks=("stick_id", "size"), bench_changes=("changes", "sum")).to_csv(out / "blast_box_record_sticks.csv")
    sc = ctx["scout"].assign(stick_id=lambda x: x["stick_id"].astype(str))
    sc["rule"] = sc["stick_id"].map(sid["rule"])
    sc["changes"] = sc["rule"].notna() & (sc["rule"] != sc["bench"])
    sc.groupby(["basin", "bench"]).agg(locations=("stick_id", "size"), label_changes=("changes", "sum")).to_csv(out / "blast_scout_labels.csv")
    rc = ctx["recon"].assign(stick_id=lambda x: x["stick_id"].astype(str))
    rc["stick_rule"] = rc["stick_id"].map(sid["rule"])
    fin = d.set_index("api10")["final"]
    liv = d.set_index("api10")["live"]
    rc["stick_changes"] = rc["stick_rule"].notna() & (rc["stick_rule"] != rc["formation_blueox"])
    rc["matched_changes"] = rc["matched_api10"].notna() & (rc["matched_api10"].map(fin) != rc["matched_api10"].map(liv))
    rc.groupby(["basin", "status"], dropna=False).agg(sticks=("stick_id", "size"), stick_tag_changes=("stick_changes", "sum"),
                                                      matched_well_changes=("matched_changes", "sum")).to_csv(out / "blast_reconciliation.csv")
    S["reported"]["blast"] = {
        "box_pool_members": len(pools), "box_pool_code_changes": int(pools["code_changes"].sum()), "box_pool_leaves": int(pools["leaves"].sum()),
        "record_sticks": len(rs), "record_stick_bench_changes": int(rs["changes"].sum()),
        "scout_locations": len(sc), "scout_label_changes": int(sc["changes"].sum()),
        "recon_rows": len(rc), "recon_stick_changes": int(rc["stick_changes"].sum()), "recon_matched_well_changes": int(rc["matched_changes"].sum()),
    }
    S["reported"]["producer_churn"] = churn.reset_index().to_dict("records")
    S["reported"]["stick_churn"] = stick_rep.reset_index().to_dict("records")
    S["passed"] = {k: v["pass"] for k, v in K.items()}
    (out / "summary.json").write_text(json.dumps(S, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"passed": S["passed"], **{k: {kk: vv for kk, vv in v.items() if kk not in ("per_bench", "holds", "pad_3240")} for k, v in K.items()}},
                     indent=1, default=str))
    print(json.dumps(S["reported"]["blast"], indent=1))
    return S


def stick_grid(sk: pd.DataFrame, order: dict[str, list[str]]) -> pd.DataFrame:
    """Grid evidence at each Delaware stick midpoint (one pseudo-station), aligned with sk rows."""
    from box import tops_qc as tq
    from box import tops_qc_report as rep

    de = sk[(sk["basin"] == "delaware") & sk["evidence"] & sk["midpoint_lon"].notna()]
    if de.empty:
        return pd.DataFrame(index=sk.index)
    x, y = rep._to_geology(de["midpoint_lon"].to_numpy(float), de["midpoint_lat"].to_numpy(float))
    xy = np.column_stack([x, y])
    stack = tq.load_stack(pkg.GRID_DIR)
    depths = tq.sample_stack(stack, xy)
    key = de["stick_id"].astype(str).to_numpy()
    stations = pd.DataFrame({"api10": key, "tvd": de["tvd"].to_numpy(float)})
    wells = pd.DataFrame({"basin": de["basin"].to_numpy(), "vendor": de["vendor"].to_numpy(), "county": de["county"].to_numpy()}, index=key)
    ctrl = {s: pkg.dist_to_control(s, xy) for s in sorted({s for tb in tq.TAG_INTERVAL.values() for s in tb} | set(tq.STACK))}
    g = tr.grid_evidence(stations, depths, wells, order, ctrl, pkg.TRUST_MAX_FT)
    return g.reindex(sk["stick_id"].astype(str).to_numpy()).reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    run(a.cache, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
