"""BOX sticks phase 5a: the reconciliation predicate measured read-only (docs/box_sticks/phase5a-2026-11-18).

    python -m scripts.box_sticks_phase5a hindcast --run <new dir>      # fresh pull, wells spudded after the vintage hidden, generate
    python -m scripts.box_sticks_phase5a wells    --run <dir>          # today's wells, one read-only pull
    python -m scripts.box_sticks_phase5a day0     --run <dir> --out <dir>   # record sets: Python reference + the draft SQL on live
    python -m scripts.box_sticks_phase5a backtest --run <dir> --out <dir>   # hidden wells against the hindcast sticks

Read-only: every statement runs inside SET TRANSACTION READ ONLY; outputs are files. Nothing is written to the warehouse
and nothing is stored. The bars are in BARS.md, written before the first run. The predicate is stated there and in
predicate_draft.sql; `judge` below is the Python reference of the same rule (EPSG:3083 metres).
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from box.sticks.core import family

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "box_sticks" / "phase5a-2026-11-18"
VINTAGE = pd.Timestamp("2026-09-30")          # curated.intel_vintage_date() at 2026Q3; checked in `wells`
FT = 0.3048
CORRIDOR_M = 46.0                             # sql/20: +-150 ft
MATCH, CONFLICT = 0.5, 0.2                    # sql/68
SAME_CODE_FT, ANY_TAG_FT = 500.0, 150.0       # sql/68
MEMBER = 0.30                                 # rule 9
BASINS = ("delaware", "midland")
TO_3083 = Transformer.from_crs("EPSG:4326", "EPSG:3083", always_xy=True)

_WELLS_SQL = """
SELECT e.api10, e.basin_blueox AS basin, e.state_code, e.county, e.well_name, e.current_operator AS operator, e.well_status,
       e.spud_date, e.first_production_date AS fp, e.formation_blueox AS code, e.directional_survey_is_planned AS planned,
       e.tvd_ft, sv.lat_tvd_p50_ft, COALESCE(sv.is_uturn, FALSE) AS is_uturn,
       n."PermitApprovedDate"::date AS permit_approved, n."PermitExpirationDate"::date AS permit_expires,
       extensions.ST_AsText(extensions.ST_Transform(
           CASE WHEN COALESCE(sv.is_uturn, FALSE) AND sv.lateral_geom IS NOT NULL THEN sv.lateral_geom ELSE e.wellstick_geom END, 3083)) AS wkt
FROM curated.wells_enriched e
LEFT JOIN curated.well_lateral_survey sv ON sv.api10 = e.api10
LEFT JOIN raw_novi."Wells" n ON n."API10" = e.api10
WHERE e.basin_blueox IN ('delaware', 'midland') AND e.is_horizontal
  AND extensions.ST_GeometryType(e.wellstick_geom) = 'ST_LineString'
ORDER BY e.api10
"""
_STICKS_SQL = """
SELECT s.set_id, s.location_id, s.basin, s.pad_id, s.formation_blueox AS bench, s.well_name, s.well_type, s.n_legs, s.target_tvd_ft,
       s.flags, extensions.ST_AsText(extensions.ST_Transform(s.legs_geom, 3083)) AS wkt
FROM box.location_stick s JOIN box.location_set t USING (set_id) WHERE t.is_record ORDER BY s.set_id, s.location_id
"""
_REC_SQL = "SELECT set_id, basin, generator_version, pulled_at, tag_run_id, cfg -> 'generator' AS gen FROM box.location_set WHERE is_record ORDER BY set_id"


def _read(sql: str) -> pd.DataFrame:
    from etl.db import get_connection

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL extra_float_digits = 1")
        cur.execute(sql)
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
        conn.rollback()
    return pd.DataFrame(rows, columns=cols)


# ----------------------------------------------------------------------------
# Wells
# ----------------------------------------------------------------------------


def classify(w: pd.DataFrame) -> pd.DataFrame:
    """Adds cls (producing / drilled / permit / None), depth_ft (evidence or NaN), fam, geom. The rule of BARS.md."""
    w = w.copy()
    st, spud, fp = w["well_status"], pd.to_datetime(w["spud_date"]), pd.to_datetime(w["fp"])
    cls = np.where(fp.notna(), "producing",
          np.where(st == "Permit Cancelled", None,
          np.where(st.isin(["Spud", "DUC", "Completed"]) | spud.notna(), "drilled",
          np.where(st == "Permit Approved", "permit", None))))
    w["cls"] = cls
    tvd, sv = pd.to_numeric(w["tvd_ft"], errors="coerce"), pd.to_numeric(w["lat_tvd_p50_ft"], errors="coerce")
    planned = w["planned"].fillna(False).astype(bool)
    depth = np.where(sv.notna(), np.where(sv >= 4000, sv, np.nan), np.where((tvd >= 4000) & (tvd % 100 != 0), tvd, np.nan))
    w["depth_ft"] = np.where(planned, np.nan, depth)
    w["fam"] = [family(c if isinstance(c, str) else None) for c in w["code"]]
    w["geom"] = shapely.from_wkt(w["wkt"].to_numpy())
    w["spud_date"], w["fp"] = spud, fp
    return w


def cmd_wells(run: Path) -> pd.DataFrame:
    f = run / "wells_today.pkl"
    if f.exists():
        return pd.read_pickle(f)
    v = _read("SELECT curated.intel_vintage_date() AS v, now() AS t")
    if pd.Timestamp(v["v"].iloc[0]) != VINTAGE:
        raise SystemExit(f"vintage date is {v['v'].iloc[0]}, not {VINTAGE.date()}")
    w = _read(_WELLS_SQL)
    w["api10"] = w["api10"].astype(str)
    w.attrs["pulled_at"] = str(v["t"].iloc[0])
    w.to_pickle(f)
    print(f"wells pulled {v['t'].iloc[0]}: {len(w):,} horizontals with a line", flush=True)
    return w


# ----------------------------------------------------------------------------
# The predicate (Python reference)
# ----------------------------------------------------------------------------


def legs_frame(sticks: pd.DataFrame) -> pd.DataFrame:
    """One row per leg from a sticks frame with a MULTILINESTRING `geom` (EPSG:3083)."""
    parts, idx = shapely.get_parts(np.array(sticks["geom"].to_numpy(), dtype=object), return_index=True)
    L = sticks.iloc[idx].drop(columns=["geom"]).reset_index(drop=True)
    L["leg"] = parts
    L["leg_no"] = L.groupby("key").cumcount() + 1
    L["leg_m"] = shapely.length(parts)
    L["sfam"] = [family(c) for c in L["bench"]]
    return L


GATE_FT = 2640.0                              # the generator's pair gate (phase 2b): "alongside" is measured inside it
WCA_PAIR = {"WCA_1", "WCA_2"}


def judge(sticks: pd.DataFrame, wells: pd.DataFrame, gen: dict[str, dict], mirror: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """sticks: key, basin, pad_id, bench, target_tvd_ft, geom. wells: classify() output with cls not None.
    gen: basin -> the set's cfg['generator']. Returns (stick status frame, judged pair frame).

    mirror = None is the predicate as written in BARS.md (variant A). mirror = {"codev": set of pad_id, "landing":
    {(pad_id, bench): target TVD}} is variant B, which follows three generator rules: no test between WCA_1 and WCA_2 in a
    co-developed DSU; a well with no depth evidence is taken at the DSU's landing of its tagged bench where that bench
    kept one (family only otherwise); crowded = at least half of the alongside length inside the sideways limit (the
    generator's median distance), alongside >= min_overlap."""
    L = legs_frame(sticks)
    out_pairs = []
    for basin in BASINS:
        g = gen[basin]
        same_dv, same_dh, min_ov, rects = float(g["same_dv_ft"]), float(g["same_dh_ft"]), float(g["min_overlap"]), [tuple(map(float, r)) for r in g["stacked"]]
        lb = L[L["basin"] == basin].reset_index(drop=True)
        wb = wells[(wells["basin"] == basin) & wells["cls"].notna()].reset_index(drop=True)
        if lb.empty or wb.empty:
            continue
        wl, leg = wb["geom"].to_numpy(), lb["leg"].to_numpy()
        i, j = shapely.STRtree(leg).query(wl, predicate="dwithin", distance=same_dh * FT)
        p = pd.DataFrame({"w": i, "l": j})

        def share(dist_m: float, rows: np.ndarray, p: pd.DataFrame = p, wl: np.ndarray = wl, leg: np.ndarray = leg, lb: pd.DataFrame = lb) -> np.ndarray:
            a, b = p["w"].to_numpy()[rows], p["l"].to_numpy()[rows]
            return shapely.length(shapely.intersection(leg[b], shapely.buffer(wl[a], dist_m))) / lb["leg_m"].to_numpy()[b]

        allr = np.arange(len(p))
        p["ov"] = share(CORRIDOR_M, allr)
        p["ov_same"] = share(same_dh * FT, allr)
        for c in ("api10", "cls", "code", "fam", "depth_ft"):
            p[c] = wb[c].to_numpy()[p["w"].to_numpy()]
        for c in ("key", "leg_no", "bench", "sfam", "target_tvd_ft"):
            p[c] = lb[c].to_numpy()[p["l"].to_numpy()]
        for c in ("pad_id",):
            p[c] = lb[c].to_numpy()[p["l"].to_numpy()]
        p["planned_basis"] = p["depth_ft"].isna()
        cross = np.zeros(len(p), bool)
        if mirror is not None:
            assumed = np.array([mirror["landing"].get((int(a), c), np.nan) if isinstance(c, str) else np.nan for a, c in zip(p["pad_id"], p["code"], strict=True)], dtype=float)
            p["depth_ft"] = np.where(p["planned_basis"], assumed, p["depth_ft"])
            cross = np.array([int(a) in mirror["codev"] and {c, bn} == WCA_PAIR for a, c, bn in zip(p["pad_id"], p["code"], p["bench"], strict=True)], dtype=bool)
            p["ov_gate"] = share(GATE_FT * FT, allr)
        p["dz"] = p["depth_ft"] - p["target_tvd_ft"]
        nod = p["depth_ft"].isna()
        p["same_bench"] = np.where(nod, p["fam"] == p["sfam"], ((p["code"] == p["bench"]) & (p["dz"].abs() <= SAME_CODE_FT)) | (p["dz"].abs() <= ANY_TAG_FT))
        if mirror is not None:
            p["same_bench"] = p["same_bench"] & ~cross

        def inside(ov_lim: np.ndarray, rows: np.ndarray, p: pd.DataFrame = p, min_ov: float = min_ov) -> np.ndarray:
            if mirror is None:
                return ov_lim >= min_ov
            gate = p["ov_gate"].to_numpy()[rows]
            return (gate >= min_ov) & (ov_lim >= 0.5 * gate)

        near = inside(p["ov_same"].to_numpy(), allr)
        env = np.where(nod, (p["fam"] == p["sfam"]) & near, (p["dz"].abs() <= same_dv) & near & ~cross)
        for lo, hi, lim in rects:
            rows = np.flatnonzero((~nod & (p["dz"] > lo) & (p["dz"] <= hi)).to_numpy())
            if len(rows):
                hit = np.zeros(len(p), bool)
                hit[rows] = inside(share(lim * FT, rows), rows)
                env = env | hit
        p["in_envelope"] = env & p["cls"].isin(["producing", "drilled"]).to_numpy()
        p["basin"] = basin
        out_pairs.append(p.drop(columns=["w", "l"]))
    P = pd.concat(out_pairs, ignore_index=True) if out_pairs else pd.DataFrame()
    return roll_up(sticks, L, P), P


def roll_up(sticks: pd.DataFrame, L: pd.DataFrame, P: pd.DataFrame) -> pd.DataFrame:
    real = P[P["same_bench"] & (P["cls"] != "permit")].sort_values(["ov", "api10"], ascending=[False, True])
    g = real.groupby(["key", "leg_no"], sort=False)
    leg = g.agg(best_ov=("ov", "first"), best_api10=("api10", "first"), best_cls=("cls", "first"), best_planned=("planned_basis", "first")).reset_index()
    leg = leg.merge(real[real["ov"] >= MATCH].groupby(["key", "leg_no"]).size().rename("n_strong").reset_index(), how="left").fillna({"n_strong": 0})
    leg["state"] = np.where(leg["n_strong"] >= 2, "conflict", np.where(leg["best_ov"] >= MATCH, "matched", np.where(leg["best_ov"] >= CONFLICT, "conflict", "open")))
    leg = leg[leg["state"] != "open"]
    m = leg[leg["state"] == "matched"]
    S = sticks[["key", "basin", "pad_id", "bench", "well_type", "n_legs", "target_tvd_ft"]].copy()
    S = S.merge(leg.groupby("key").agg(any_conflict=("state", lambda s: bool((s == "conflict").any())), best_ov=("best_ov", "max"),
                                       matched_api10=("best_api10", "first")).reset_index(), how="left")
    S = S.merge(m.groupby("key").agg(legs_matched=("leg_no", "size"), all_producing=("best_cls", lambda s: bool((s == "producing").all())),
                                     any_planned=("best_planned", "any"), wells_matched=("best_api10", "nunique")).reset_index(), how="left")
    pm = P[P["same_bench"] & (P["cls"] == "permit") & (P["ov"] >= MATCH)].sort_values(["key", "leg_no", "ov"], ascending=[True, True, False])
    S = S.merge(pm.groupby("key").agg(permit_api10=("api10", "first"), permit_planned=("planned_basis", "first")).reset_index(), how="left")
    cr = P[P["in_envelope"]].sort_values(["key", "leg_no", "ov_same"], ascending=[True, True, False])
    S = S.merge(cr.groupby("key").agg(crowd_api10=("api10", "first")).reset_index(), how="left")
    S["any_conflict"] = S["any_conflict"].fillna(False).astype(bool)
    S["legs_matched"] = S["legs_matched"].fillna(0).astype(int)
    S["status"] = np.where(S["any_conflict"], "conflict",
                  np.where((S["legs_matched"] > 0) & S["all_producing"].fillna(False).astype(bool), "producing",
                  np.where(S["legs_matched"] > 0, "drilled", np.where(S["permit_api10"].notna(), "permitted", "open"))))
    S["crowded"] = S["crowd_api10"].notna() & S["status"].isin(["open", "permitted"])
    S["match_basis"] = np.where(S["status"].isin(["drilled", "producing", "conflict"]), np.where(S["any_planned"].fillna(False).astype(bool), "planned", "depth"), None)
    return S


def counts(S: pd.DataFrame) -> pd.DataFrame:
    t = S.groupby(["basin", "status"]).size().unstack(fill_value=0)
    for c in ("open", "permitted", "drilled", "producing", "conflict"):
        if c not in t:
            t[c] = 0
    t = t[["open", "permitted", "drilled", "producing", "conflict"]]
    t["crowded_flag"] = S[S["crowded"]].groupby("basin").size().reindex(t.index, fill_value=0)
    t["sticks"] = S.groupby("basin").size()
    t["not_open_ex_permit_pct"] = (100 * (t["drilled"] + t["producing"] + t["conflict"]) / t["sticks"]).round(3)
    t["crowded_pct"] = (100 * t["crowded_flag"] / t["sticks"]).round(3)
    return t.reset_index()


# ----------------------------------------------------------------------------
# day0: the record sets
# ----------------------------------------------------------------------------


def cmd_day0(run: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    rec = _read(_REC_SQL)
    gen = {r.basin: r.gen for r in rec.itertuples()}
    st = _read(_STICKS_SQL)
    st["key"] = st["location_id"].astype(int)
    st["geom"] = shapely.from_wkt(st["wkt"].to_numpy())
    w = classify(cmd_wells(run))
    S, P = judge(st, w, gen)
    S = S.merge(st[["key", "set_id", "well_name", "flags"]], on="key")
    c = counts(S)
    c.to_csv(out / "day0_status_counts.csv", index=False)
    wi = w.set_index("api10")
    # sticks flagged permitted: by state and basis
    per = S[S["status"] == "permitted"].copy()
    per["state_code"] = wi["state_code"].reindex(per["permit_api10"]).to_numpy()
    per["basis"] = np.where(per["permit_planned"].fillna(False).astype(bool), "planned", "depth")
    per.groupby(["basin", "state_code", "basis"]).size().rename("sticks").reset_index().to_csv(out / "day0_permitted_by_state.csv", index=False)
    # every stick that is not open on day 0, with its cause
    no = S[S["status"].isin(["drilled", "producing", "conflict"]) | S["crowded"]].copy()
    api = no["matched_api10"].fillna(no["crowd_api10"])
    for col in ("well_status", "spud_date", "fp", "code", "depth_ft", "is_uturn", "state_code", "well_name"):
        no["w_" + col] = wi[col].reindex(api).to_numpy()
    seen = _read("SELECT set_id, api10, depth_ft AS set_depth_ft, status AS set_status FROM box.location_set_well w JOIN box.location_set t USING (set_id) WHERE t.is_record")
    seen["api10"] = seen["api10"].astype(str)
    no["api10"] = api.to_numpy()
    no = no.merge(seen, on=["set_id", "api10"], how="left")
    no["cause"] = np.where(no["set_status"].isna(), "well not read by the generator",
                  np.where(no["set_depth_ft"].isna() & no["w_depth_ft"].notna(), "generator held no depth for the well (screened out)",
                  np.where(no["w_is_uturn"].fillna(False).astype(bool), "real U-turn well: survey path here, wellstick in the generator", "same well, different measure")))
    no.drop(columns=["flags"]).to_csv(out / "day0_not_open.csv", index=False)
    cause = no.assign(kind=np.where(no["crowded"], "crowded", no["status"])).groupby(["basin", "kind", "cause"]).size().rename("sticks").reset_index()
    cause.to_csv(out / "day0_not_open_by_cause.csv", index=False)

    # variant B: the three generator rules mirrored (see judge)
    dsu = _read("SELECT d.pad_id FROM box.location_set_dsu d JOIN box.location_set t USING (set_id) WHERE t.is_record AND d.wca_class = 'co-developed'")
    bl = _read("SELECT b.pad_id, b.formation_blueox, b.target_tvd_ft FROM box.location_set_bench b JOIN box.location_set t USING (set_id) "
               "WHERE t.is_record AND b.no_row_reason = '' AND b.target_tvd_ft IS NOT NULL")
    mirror = {"codev": set(dsu["pad_id"].astype(int)), "landing": {(int(r.pad_id), r.formation_blueox): float(r.target_tvd_ft) for r in bl.itertuples()}}
    SB, PB = judge(st, w, gen, mirror)
    cb = counts(SB)
    cb.to_csv(out / "day0_status_counts_variant_b.csv", index=False)
    nb = SB[SB["status"].isin(["drilled", "producing", "conflict"]) | SB["crowded"]].merge(st[["key", "set_id"]], on="key")
    nb["api10"] = nb["matched_api10"].fillna(nb["crowd_api10"]).astype(str)
    nb = nb.merge(seen, on=["set_id", "api10"], how="left")
    nb["w_status"] = wi["well_status"].reindex(nb["api10"]).to_numpy()
    nb["w_uturn"] = wi["is_uturn"].reindex(nb["api10"]).fillna(False).to_numpy().astype(bool)
    pb = PB.assign(api10=PB["api10"].astype(str)).sort_values("ov", ascending=False).drop_duplicates(["key", "api10"])
    nb = nb.merge(pb[["key", "api10", "dz", "code", "planned_basis"]], on=["key", "api10"], how="left")
    nb["why"] = np.where(nb["set_status"].isna(), "well not read by the generator: " + nb["w_status"].astype(str),
                np.where(nb["w_uturn"], "real U-turn well (survey path here, wellstick in the generator)",
                np.where(nb["planned_basis"].fillna(False).astype(bool), "well without depth evidence",
                np.where((nb["dz"].abs() > 150) & (nb["code"] == nb["bench"]), "same code, 150 to 500 ft apart vertically", "other"))))
    causeb = nb.assign(kind=np.where(nb["crowded"], "crowded", nb["status"])).groupby(["basin", "kind", "why"]).size().rename("sticks").reset_index()
    causeb.to_csv(out / "day0_not_open_by_cause_variant_b.csv", index=False)
    nb.to_csv(out / "day0_not_open_variant_b.csv", index=False)
    print(cb.to_string(index=False), "\n", causeb.to_string(index=False), flush=True)

    # the draft SQL on live
    sql = (DOC / "predicate_draft.sql").read_text(encoding="utf-8")
    t0 = time.time()
    Q = _read(sql)
    secs = time.time() - t0
    plan = "\n".join(_read("EXPLAIN " + sql).iloc[:, 0])
    (out / "day0_sql_explain.txt").write_text(plan, encoding="utf-8")
    Q["key"] = Q["location_id"].astype(int)
    cmp_ = S[["key", "basin", "status", "crowded", "legs_matched"]].merge(Q[["key", "status", "crowded", "legs_matched"]], on="key", suffixes=("_py", "_sql"))
    agree = cmp_.groupby("basin").apply(lambda d: pd.Series({"sticks": len(d), "same_status_pct": 100 * float((d["status_py"] == d["status_sql"]).mean()),
                                                              "same_crowded_pct": 100 * float((d["crowded_py"] == d["crowded_sql"].astype(bool)).mean())}), include_groups=False).reset_index()
    cmp_[cmp_["status_py"] != cmp_["status_sql"]].to_csv(out / "day0_sql_vs_python_diff.csv", index=False)
    summ = {"record_sets": json.loads(rec.drop(columns=["gen"]).to_json(orient="records", date_format="iso")), "wells_pulled_at": cmd_wells(run).attrs.get("pulled_at"),
            "wells_by_class": w.assign(cls=w["cls"].fillna("ignored")).groupby(["basin", "cls"]).size().rename("n").reset_index().to_dict("records"),
            "wells_no_depth_evidence": w[w["cls"].notna()].assign(nod=lambda d: d["depth_ft"].isna()).groupby(["basin", "state_code", "cls"])["nod"].agg(["size", "sum"]).reset_index().to_dict("records"),
            "status_counts": c.to_dict("records"), "by_cause": cause.to_dict("records"),
            "variant_b_status_counts": cb.to_dict("records"), "variant_b_by_cause": causeb.to_dict("records"),
            "sql": {"seconds": round(secs, 1), "rows": len(Q), "agreement": agree.to_dict("records"),
                    "uses_stick_index": [n for n in ("box_location_stick_geog_gix", "box_location_stick_geom_gix") if n in plan],
                    "sql_status_counts": Q.groupby(["basin", "status"]).size().rename("n").reset_index().to_dict("records"),
                    "sql_crowded": Q[Q["crowded"].astype(bool)].groupby("basin").size().to_dict()}}
    (out / "day0_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    pd.to_pickle({"S": S, "P": P, "SB": SB, "PB": PB}, run / "day0.pkl")
    print(c.to_string(index=False), "\n", cause.to_string(index=False), "\n", json.dumps(summ["sql"], indent=1, default=str), flush=True)


# ----------------------------------------------------------------------------
# hindcast + back-test
# ----------------------------------------------------------------------------


def cmd_hindcast(run: Path) -> None:
    from scripts import box_sticks_run as br

    br.pull(run)
    cache = run / "cache"
    for f in cache.glob("*.pkl"):
        if f.stem not in br.KEYS:
            f.unlink()                                   # every derived frame is rebuilt without the hidden wells
    pre = pd.read_pickle(cache / "p3_preprod.pkl")
    hide = pd.to_datetime(pre["spud_date"]) > VINTAGE
    pre[hide][["api10", "basin", "well_status", "spud_date"]].to_csv(run / "hidden_preprod.csv", index=False)
    shutil.copy(cache / "p3_preprod.pkl", run / "p3_preprod_full.pkl")
    pre[~hide].reset_index(drop=True).to_pickle(cache / "p3_preprod.pkl")
    u = pd.read_pickle(cache / "wells.pkl")
    late = [c for c in ("first_production_date", "fp") if c in u]
    print(f"hidden: {int(hide.sum()):,} of {len(pre):,} not-yet-producing wells (spud after {VINTAGE.date()}); "
          f"producers with first production after it: {int((pd.to_datetime(u[late[0]]) > VINTAGE).sum()) if late else 'n/a'}", flush=True)
    for b in BASINS:
        br.generate(run, b)


def hind_sticks(run: Path) -> tuple[pd.DataFrame, dict]:
    rows, gen = [], {}
    for b in BASINS:
        art = pd.read_pickle(run / f"set_{b}.pkl")
        gen[b] = art["cfg"]["generator"]
        for s in art["sticks"]:
            ml = shapely.multilinestrings([[TO_3083.transform(*leg["heel_lonlat"]), TO_3083.transform(*leg["toe_lonlat"])] for leg in s["legs"]])
            rows.append({"key": s["well_name"], "basin": b, "pad_id": int(s["pad_id"]), "bench": s["bench"], "well_type": s["well_type"], "n_legs": int(s["n_legs"]),
                         "target_tvd_ft": float(s["target_tvd_ft"]), "flags": list(s["flags"]), "geom": ml})
    return pd.DataFrame(rows), gen


def hind_mirror(run: Path) -> dict:
    codev, landing = set(), {}
    for b in BASINS:
        art = pd.read_pickle(run / f"set_{b}.pkl")
        codev |= {int(r["pad_id"]) for r in art["dsu_rows"] if r.get("wca_class") == "co-developed"}
        landing |= {(int(r["pad_id"]), r["formation_blueox"]): float(r["target_tvd_ft"]) for r in art["bench_rows"]
                    if not r["no_row_reason"] and r.get("target_tvd_ft") is not None}
    return {"codev": codev, "landing": landing}


def cmd_backtest(run: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    st, gen = hind_sticks(run)
    w = classify(cmd_wells(run))
    hidden_ids = set(pd.read_csv(run / "hidden_preprod.csv", dtype={"api10": str})["api10"])
    # the generator reads Spud / DUC / Completed only; every other well with a spud date after the vintage is a test well too
    late = (w["spud_date"] > VINTAGE) & w["cls"].isin(["drilled", "producing"])
    test = w[late].copy()
    vis = w[~(w["spud_date"] > VINTAGE)]
    pads = pd.read_pickle(run / "cache" / "pads.pkl")
    pads["geom"] = shapely.from_wkt(pads["wkt"].to_numpy())
    fam_in_pad = set(zip(st["pad_id"], [family(c) for c in st["bench"]], strict=True))
    pg, pid, tg = pads["geom"].to_numpy(), pads["pad_id"].to_numpy(), test["geom"].to_numpy()
    a, k = shapely.STRtree(pg).query(tg, predicate="intersects")
    sh = shapely.length(shapely.intersection(tg[a], pg[k])) / shapely.length(tg[a])
    ok = (sh >= MEMBER) & (pads["basin"].to_numpy()[k] == test["basin"].to_numpy()[a])
    pads_of = pd.DataFrame({"t": a[ok], "pad_id": pid[k][ok]}).groupby("t")["pad_id"].apply(list)
    grp = []
    for n, r in enumerate(test.itertuples()):
        mine = pads_of.get(n, [])
        grp.append("no tag" if not r.fam else "member of no DSU" if not mine else
                   "W" if any((int(p), r.fam) in fam_in_pad for p in mine) else "no stick of its family in its DSU")
    test["grp"] = grp
    summ = {"cutoff": str(VINTAGE.date()), "hidden_from_generator": len(hidden_ids), "test_wells": len(test),
            "test_wells_by_status": test.groupby(["basin", "well_status"]).size().rename("n").reset_index().to_dict("records"),
            "hindcast_sticks": st.groupby("basin").size().to_dict()}
    keep = {}
    for tag, mirror in (("a", None), ("b", hind_mirror(run))):
        S0, _ = judge(st, vis[vis["cls"] != "permit"], gen, mirror)         # before the hidden wells are shown
        S1, P1 = judge(st, test, gen, mirror)                               # the hidden wells alone
        base_out = S0["status"].isin(["drilled", "producing", "conflict"]) | S0["crowded"]
        b5 = S0.assign(out=base_out).groupby("basin")["out"].agg(["size", "sum"]).rename(columns={"size": "sticks", "sum": "not_open_before"}).reset_index()
        b5["pct"] = (100 * b5["not_open_before"] / b5["sticks"]).round(3)
        # per well: what it did to the hindcast sticks (sticks already out before it was shown do not count)
        live = S1[~S1["key"].isin(S0.loc[base_out, "key"])]
        stat = live.set_index("key")
        P = P1[P1["key"].isin(stat.index)].copy()
        P["stick_status"] = stat["status"].reindex(P["key"]).to_numpy()
        P["stick_crowded"] = stat["crowded"].reindex(P["key"]).to_numpy()
        strong = P[P["same_bench"] & (P["ov"] >= MATCH)]
        weak = P[P["same_bench"] & (P["ov"] >= CONFLICT) & (P["ov"] < MATCH)]
        crowd = P[P["in_envelope"] & P["stick_crowded"]]
        per = test[["api10", "basin", "state_code", "well_name", "well_status", "spud_date", "code", "fam", "is_uturn", "grp"]].copy()
        per["basis"] = np.where(test["depth_ft"].isna(), "planned", "depth")
        clean = strong[strong["stick_status"].isin(["drilled", "producing"])]
        confl = pd.concat([strong[strong["stick_status"] == "conflict"], weak[weak["stick_status"] == "conflict"]])
        for name, df, col in (("sticks_matched", clean, "key"), ("dsus_matched", clean, "pad_id"), ("sticks_conflict", confl, "key"), ("sticks_crowded", crowd, "key")):
            per[name] = per["api10"].map(df.groupby("api10")[col].nunique()).fillna(0).astype(int)
        per["outcome"] = np.where(per["sticks_matched"] > 0, "match", np.where(per["sticks_conflict"] > 0, "conflict", np.where(per["sticks_crowded"] > 0, "crowded", "nothing")))
        per.to_csv(out / f"backtest_wells_variant_{tag}.csv", index=False)
        W = per[per["grp"] == "W"]
        touched = pd.concat([clean, confl, crowd])
        touched = touched[touched["api10"].isin(set(W["api10"]))]
        kind = stat.loc[touched["key"].unique()]
        rows = []
        for b in BASINS:
            wb, kb = W[W["basin"] == b], kind[kind["basin"] == b]
            n, removed = len(wb), len(kb)
            ut = live[(live["basin"] == b) & (live["n_legs"] == 2) & live["status"].isin(["drilled", "producing"])]
            rows.append({"variant": tag, "basin": b, "test_wells": int((per["basin"] == b).sum()), "W": n,
                         "B1_take_out_pct": round(100 * float((wb["outcome"] != "nothing").mean()), 1) if n else None,
                         "B2_sticks_out_per_well": round(removed / n, 3) if n else None, "sticks_out": removed,
                         "B3_clean_match_pct": round(100 * float((wb["outcome"] == "match").mean()), 1) if n else None,
                         "B4_conflict_share_pct": round(100 * float((kb["status"] == "conflict").mean()), 1) if removed else None,
                         "B5_not_open_before_pct": float(b5.loc[b5["basin"] == b, "pct"].iloc[0]),
                         "out_drilled": int(kb["status"].isin(["drilled", "producing"]).sum()), "out_conflict": int((kb["status"] == "conflict").sum()),
                         "out_crowded": int(kb["crowded"].sum()), "wells_planned_basis_pct": round(100 * float((wb["basis"] == "planned").mean()), 1) if n else None,
                         "uturn_sticks_drilled": len(ut), "uturn_sticks_both_legs": int((ut["legs_matched"] == 2).sum()),
                         "wells_matching_2plus_sticks": int((wb["sticks_matched"] >= 2).sum()), "wells_matching_2plus_dsus": int((wb["dsus_matched"] >= 2).sum())})
        res = pd.DataFrame(rows)
        res.to_csv(out / f"backtest_bars_variant_{tag}.csv", index=False)
        g = per.groupby(["basin", "state_code", "grp", "outcome", "basis"]).size().rename("wells").reset_index()
        g.to_csv(out / f"backtest_wells_by_outcome_variant_{tag}.csv", index=False)
        so = live[(live["status"] != "open") | live["crowded"]].merge(st[["key", "flags"]], on="key")
        so.assign(flags=so["flags"].map(",".join)).to_csv(out / f"backtest_sticks_out_variant_{tag}.csv", index=False)
        summ[f"variant_{tag}"] = {"B5": b5.to_dict("records"), "bars": res.to_dict("records")}
        keep[tag] = {"S0": S0, "S1": S1, "P1": P1, "per": per}
        print(f"--- variant {tag}\n", res.T.to_string(), "\n", g.groupby(["basin", "grp", "outcome"])["wells"].sum().to_string(), flush=True)
    (out / "backtest_summary.json").write_text(json.dumps(summ, indent=1, default=str), encoding="utf-8")
    pd.to_pickle(keep | {"st": st, "test": test}, run / "backtest.pkl")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("hindcast", "wells", "day0", "backtest"))
    ap.add_argument("--run", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=DOC)
    a = ap.parse_args(argv)
    a.run.mkdir(parents=True, exist_ok=True)
    {"hindcast": lambda: cmd_hindcast(a.run), "wells": lambda: cmd_wells(a.run), "day0": lambda: cmd_day0(a.run, a.out),
     "backtest": lambda: cmd_backtest(a.run, a.out)}[a.step]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
