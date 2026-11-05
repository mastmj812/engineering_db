"""Sub-bench inference v2 what-if: score the drafted replacement for sql/19 tier 2 against the current rule.

    python -m scripts.subbench_whatif --out docs/subbench_inference_v2/score-<date> [--cache <pull.pkl>]

Read-only. Pulls the coarse Novi sticks (sql/19 tier-2 set) and the splitting-bench reference laterals (sql/18 pool
definition, live sources) with their real lateral geometry in EPSG:3083 metres, then:

  * re-implements the CURRENT rule (12 nearest same-parent laterals, full pool incl. permits, copy the TVD-nearest);
  * runs the DRAFT rule (docs/subbench_inference_v2/PLAN.md §2): producer-only pool; Delaware WCA/WCB = local two-bench
    model, Delaware Avalon + Midland WCB = weighted vote; frontier flag; confidence;
  * scores both on held-out producers (stick-like hold-out radius), on Texas WCB sticks vs depth below local WCA,
    and on confidence calibration; writes summary.json, SUMMARY.md and stick_tags.csv (every coarse stick).

Every rule constant lives in RULE below; PLAN.md §2 quotes it and the freeze commit pins it. Nothing is written to the
warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely import from_wkb
from shapely import distance as sh_distance

MI_M = 1609.344

# Frozen rule constants (PLAN.md §2). Distances in metres on EPSG:3083, TVD in ft.
RULE = {
    "pool": "first_production_date IS NOT NULL AND tvd_ft % 100 <> 0",
    "candidates": 200,            # midpoint-KD superset scanned for true lateral-to-lateral distance
    "model_n": 30,                # local model: nearest same-parent producers ...
    "model_r_m": 5 * MI_M,        # ... within this distance
    "model_bw_m": 1.5 * MI_M,     # Gaussian distance weight bandwidth
    "model_min_per_bench": 2,     # each bench needs this many wells in the neighbourhood
    "model_min_sep_ft": 40.0,     # lower-bench mean must sit at least this far below the upper
    "model_sigma_floor_ft": 25.0,
    "vote_n": 12,
    "vote_sigma_tvd_ft": 60.0,
    "vote_sigma_d_m": 1.5 * MI_M,
    "frontier_min_n": 4,          # fewer than this many same-parent producers within frontier_r_m = frontier
    "frontier_r_m": 5 * MI_M,
    "current_n": 12,              # the sql/19 v1 rule
    "conf_bands": [0.80, 0.95],
    "wcb2_cut_ft": 400.0,         # depth-below-WCA reference cut (erebor_locations.wca_delta_ft), Texas only
}
LADDER = {"WCA": ["WCA_1", "WCA_2"], "WCB": ["WCB_1", "WCB_2"], "AVA": ["AVA_0", "AVA_1", "AVA_2"]}
# Which path assigns the bench where the local model can run (PLAN.md §2.2): Avalon's three thin benches and the
# Midland scored worse on the model than on the vote in the prototype.
MODEL_GROUPS = {("delaware", "WCA"), ("delaware", "WCB")}
NM_COUNTIES = {"Lea", "Eddy"}

_POOL_SQL = """
SELECT w.api10, fb.basin_blueox AS basin, fb.formation_blueox AS bench, left(fb.formation_blueox, 3) AS parent,
       w.tvd_ft::float8 AS tvd, w.first_production_date IS NOT NULL AS produced, (w.tvd_ft::int % 100 = 0) AS round100,
       ST_AsBinary(extensions.ST_Transform(w.wellstick_geom, 3083)) AS wkb
FROM curated.wells w JOIN curated.formation_blueox fb USING (api10)
WHERE fb.formation_blueox IN ('WCA_1','WCA_2','WCB_1','WCB_2','AVA_0','AVA_1','AVA_2')
  AND fb.basin_blueox IN ('delaware','midland') AND w.wellstick_geom IS NOT NULL AND w.tvd_ft IS NOT NULL
"""
_STICK_SQL = """
SELECT il.stick_id, il.basin, il.tvd::float8 AS tvd, il.county, il.pad_name, il.category,
       CASE UPPER(il.formation) WHEN 'WOLFCAMP A' THEN 'WCA' WHEN 'WOLFCAMP B' THEN 'WCB' WHEN 'AVALON' THEN 'AVA' END AS parent,
       ifb.formation_blueox AS live, ifb.formation_blueox_source AS live_source, el.recon_status, el.wca_delta_ft,
       bsl.stick_id IS NOT NULL AS in_box_scout,
       ST_AsBinary(extensions.ST_Transform(il.wellstick_geom, 3083)) AS wkb
FROM curated.intel_locations il
JOIN curated.intel_formation_blueox ifb USING (stick_id)
LEFT JOIN curated.erebor_locations el USING (stick_id)
LEFT JOIN curated.box_scout_locations bsl USING (stick_id)
WHERE il.category IN ('PUD','RES') AND il.wellstick_geom IS NOT NULL AND il.tvd IS NOT NULL
  AND ((il.basin = 'delaware' AND UPPER(il.formation) IN ('WOLFCAMP A','WOLFCAMP B','AVALON'))
    OR (il.basin = 'midland'  AND UPPER(il.formation) = 'WOLFCAMP B'))
"""


# ---------------------------------------------------------------------------------------------------------------
# Pure rule functions (tests/test_subbench_whatif.py). Inputs are the neighbour arrays already restricted to the
# query's basin + parent and sorted by distance.
# ---------------------------------------------------------------------------------------------------------------

def current_pick(tvd: float, n_tvd: np.ndarray, n_bench: np.ndarray, n: int = RULE["current_n"]) -> str | None:
    """sql/19 v1: of the n nearest laterals, copy the bench of the one nearest in TVD (first wins a tie)."""
    if len(n_bench) == 0:
        return None
    t, b = n_tvd[:n], n_bench[:n]
    return str(b[int(np.argmin(np.abs(t - tvd)))])


def vote_pick(tvd: float, n_d: np.ndarray, n_tvd: np.ndarray, n_bench: np.ndarray, ladder: list[str],
              rule: dict = RULE) -> tuple[str | None, float]:
    """Weighted vote of the vote_n nearest: weight = Gaussian(TVD gap) x Gaussian(distance). Confidence = winner share."""
    if len(n_bench) == 0:
        return None, float("nan")
    d, t, b = n_d[: rule["vote_n"]], n_tvd[: rule["vote_n"]], n_bench[: rule["vote_n"]]
    w = np.exp(-0.5 * ((t - tvd) / rule["vote_sigma_tvd_ft"]) ** 2) * np.exp(-0.5 * (d / rule["vote_sigma_d_m"]) ** 2) + 1e-12
    share = {lb: float(w[b == lb].sum()) for lb in ladder}
    win = max(share, key=lambda k: share[k])
    return win, share[win] / sum(share.values())


def model_pick(tvd: float, n_d: np.ndarray, n_tvd: np.ndarray, n_bench: np.ndarray, ladder: list[str],
               rule: dict = RULE) -> tuple[str | None, float]:
    """Local two-bench model: distance-weighted mean TVD of each bench in the neighbourhood, pooled weighted scatter,
    Gaussian posterior of the stick's TVD against the two bench means (equal priors). None when it cannot run."""
    keep = n_d <= rule["model_r_m"]
    d, t, b = n_d[keep][: rule["model_n"]], n_tvd[keep][: rule["model_n"]], n_bench[keep][: rule["model_n"]]
    present = [lb for lb in ladder if (b == lb).sum() >= rule["model_min_per_bench"]]
    if len(present) != 2:
        return None, float("nan")
    w = np.exp(-0.5 * (d / rule["model_bw_m"]) ** 2)
    up, lo = present
    mu = {lb: float(np.average(t[b == lb], weights=w[b == lb])) for lb in present}
    if mu[lo] - mu[up] < rule["model_min_sep_ft"]:
        return None, float("nan")
    use = np.isin(b, present)
    res = t[use] - np.array([mu[x] for x in b[use]])
    sig = max(rule["model_sigma_floor_ft"], float(np.sqrt(np.average(res ** 2, weights=w[use]))))
    z = ((tvd - mu[lo]) ** 2 - (tvd - mu[up]) ** 2) / (2 * sig ** 2)   # log p(up) - log p(lo)
    p_lo = float(1.0 / (1.0 + np.exp(np.clip(z, -700, 700))))
    return (lo, p_lo) if p_lo >= 0.5 else (up, 1.0 - p_lo)


def draft_pick(basin: str, parent: str, tvd: float, n_d: np.ndarray, n_tvd: np.ndarray, n_bench: np.ndarray,
               rule: dict = RULE) -> tuple[str | None, float, str]:
    """The v2 rule: (bench, confidence, path). path in {local_model, vote, frontier}."""
    ladder = LADDER[parent]
    n_close = int((n_d <= rule["frontier_r_m"]).sum())
    if n_close < rule["frontier_min_n"]:
        b, c = vote_pick(tvd, n_d, n_tvd, n_bench, ladder, rule)
        return b, c, "frontier"
    if (basin, parent) in MODEL_GROUPS:
        b, c = model_pick(tvd, n_d, n_tvd, n_bench, ladder, rule)
        if b is not None:
            return b, c, "local_model"
    b, c = vote_pick(tvd, n_d, n_tvd, n_bench, ladder, rule)
    return b, c, "vote"


def conf_band(c: float, bands: list[float] = RULE["conf_bands"]) -> str:
    if not np.isfinite(c) or c < bands[0]:
        return f"<{bands[0]:.2f}"
    return f"{bands[0]:.2f}-{bands[1]:.2f}" if c < bands[1] else f">={bands[1]:.2f}"


# ---------------------------------------------------------------------------------------------------------------
# Neighbour search on real lateral geometry
# ---------------------------------------------------------------------------------------------------------------

class RefGroup:
    """One (basin, parent) reference pool: midpoint KD superset, then exact lateral-to-lateral distance."""

    def __init__(self, ref: pd.DataFrame):
        self.ref = ref.reset_index(drop=True)
        self.geom = self.ref["geom"].to_numpy()
        self.mid = np.array([[g.interpolate(0.5, normalized=True).x, g.interpolate(0.5, normalized=True).y] for g in self.geom])
        self.tree = cKDTree(self.mid)
        self.tvd = self.ref["tvd"].to_numpy(float)
        self.bench = self.ref["bench"].to_numpy()
        self.api = self.ref["api10"].to_numpy()

    def query(self, geom, exclude_api: str | None = None, exclude_r_m: float | None = None):
        k = min(len(self.ref), RULE["candidates"])
        m = geom.interpolate(0.5, normalized=True)
        _, idx = self.tree.query([m.x, m.y], k=k)
        idx = np.atleast_1d(idx)
        d = sh_distance(self.geom[idx], geom)
        keep = np.ones(len(idx), bool)
        if exclude_api is not None:
            keep &= self.api[idx] != exclude_api
        if exclude_r_m is not None:
            keep &= d > exclude_r_m
        idx, d = idx[keep], d[keep]
        o = np.argsort(d, kind="stable")
        return d[o], self.tvd[idx[o]], self.bench[idx[o]]


def _pull(cache: Path | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if cache and cache.exists():
        return pd.read_pickle(cache)
    from etl.db import get_connection
    out = []
    with get_connection() as c, c.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        for q in (_POOL_SQL, _STICK_SQL):
            cur.execute(q)
            out.append(pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description]))
    for df in out:
        df["geom"] = from_wkb(df.pop("wkb").map(bytes).to_numpy())
    if cache:
        pd.to_pickle(tuple(out), cache)
    return out[0], out[1]


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _acc(pred: pd.Series, truth: pd.Series) -> float:
    return round(100.0 * float(np.mean(pred.to_numpy() == truth.to_numpy())), 1) if len(truth) else float("nan")


def run(out: Path, cache: Path | None) -> dict:
    pool, sticks = _pull(cache)
    pool["prod"] = pool["produced"] & ~pool["round100"]
    full = {k: RefGroup(v) for k, v in pool.groupby(["basin", "parent"])}
    prod = {k: RefGroup(v) for k, v in pool[pool["prod"]].groupby(["basin", "parent"])}
    groups = sorted(k for k in prod if not (k[0] == "midland" and k[1] == "WCA"))   # Midland WCA is one bench (crosswalk)

    # Stick-like hold-out radius: median true distance from a coarse stick to its nearest same-parent producer.
    near = []
    for r in sticks.itertuples():
        g = prod.get((r.basin, r.parent))
        if g is not None:
            near.append(g.query(r.geom)[0][0])
    hold_r = float(np.median(near))

    # ---- producers, held out --------------------------------------------------------------------------------
    rows = []
    for key in groups:
        for r in prod[key].ref.itertuples():
            dF, tF, bF = full[key].query(r.geom, exclude_api=r.api10, exclude_r_m=hold_r)
            dP, tP, bP = prod[key].query(r.geom, exclude_api=r.api10, exclude_r_m=hold_r)
            b, c, path = draft_pick(key[0], key[1], r.tvd, dP, tP, bP)
            rows.append({"basin": key[0], "parent": key[1], "api10": r.api10, "bench": r.bench,
                         "current": current_pick(r.tvd, tF, bF), "draft": b, "conf": c, "path": path})
    P = pd.DataFrame(rows)

    # ---- sticks ----------------------------------------------------------------------------------------------
    srows = []
    for r in sticks.itertuples():
        key = (r.basin, r.parent)
        dF, tF, bF = full[key].query(r.geom)
        dP, tP, bP = prod[key].query(r.geom)
        b, c, path = draft_pick(r.basin, r.parent, r.tvd, dP, tP, bP)
        srows.append({"stick_id": r.stick_id, "current": current_pick(r.tvd, tF, bF), "draft": b, "conf": c, "path": path})
    S = sticks.drop(columns="geom").merge(pd.DataFrame(srows), on="stick_id")
    S["band"] = S["conf"].map(conf_band)
    S["undrilled"] = S["recon_status"].isna() | S["recon_status"].isin(["remaining_pud", "conflict"])

    res: dict = {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "git_sha": _git_sha(), "rule": RULE,
                 "hold_out_radius_mi": round(hold_r / MI_M, 2), "n_pool": int(len(pool)), "n_pool_producers": int(pool["prod"].sum()),
                 "n_sticks": int(len(S)), "current_reproduces_live_pct": _acc(S["current"], S["live"]), "groups": {}}
    crit = {"C1": {}, "C2": {}, "C3": {}}
    for key in groups:
        name = f"{key[0]}_{key[1]}"
        p = P[(P.basin == key[0]) & (P.parent == key[1])]
        s = S[(S.basin == key[0]) & (S.parent == key[1])]
        g: dict = {"producers": int(len(p)), "held_out_current_pct": _acc(p["current"], p["bench"]),
                   "held_out_draft_pct": _acc(p["draft"], p["bench"]),
                   "held_out_by_path": {k: {"n": int(len(v)), "draft_pct": _acc(v["draft"], v["bench"]),
                                            "current_pct": _acc(v["current"], v["bench"])} for k, v in p.groupby("path")},
                   "calibration": {k: {"n": int(len(v)), "draft_pct": _acc(v["draft"], v["bench"])}
                                   for k, v in p.assign(band=p["conf"].map(conf_band)).groupby("band")}}
        if len(s):
            fl = s["draft"] != s["live"]
            g["sticks"] = {"n": int(len(s)), "flips_vs_live": int(fl.sum()), "flip_pct": round(100 * float(fl.mean()), 1),
                           "flips_undrilled": int((fl & s["undrilled"]).sum()), "flips_in_box_scout": int((fl & s["in_box_scout"]).sum()),
                           "flip_matrix": {f"{a}->{b}": int(n) for (a, b), n in s[fl].groupby(["live", "draft"]).size().items()},
                           "paths": {k: int(v) for k, v in s["path"].value_counts().items()},
                           "bands": {k: int(v) for k, v in s["band"].value_counts().items()},
                           "frontier_in_box_scout": int((s["in_box_scout"] & (s["path"] == "frontier")).sum()),
                           "review_conf_lt_080_non_frontier": int(((s["conf"] < 0.80) & (s["path"] != "frontier")).sum())}
        if key[1] in ("WCA", "WCB"):
            crit["C1"][name] = {"draft": g["held_out_draft_pct"], "current": g["held_out_current_pct"],
                                "pass": bool(g["held_out_draft_pct"] >= g["held_out_current_pct"])}
        if key[1] == "WCB":
            tx = s[~s["county"].isin(NM_COUNTIES) & s["wca_delta_ft"].notna()]
            ref = np.where(tx["wca_delta_ft"] >= RULE["wcb2_cut_ft"], "WCB_2", "WCB_1")
            dr, lv = _acc(tx["draft"], pd.Series(ref)), _acc(tx["live"], pd.Series(ref))
            crit["C2"][name] = {"n": int(len(tx)), "draft": dr, "live": lv, "pass": bool(dr >= lv)}
            cal = g["calibration"]
            order = [f"<{RULE['conf_bands'][0]:.2f}", f"{RULE['conf_bands'][0]:.2f}-{RULE['conf_bands'][1]:.2f}", f">={RULE['conf_bands'][1]:.2f}"]
            vals = [cal.get(o, {}).get("draft_pct", float("nan")) for o in order]
            crit["C3"][name] = {"bands": dict(zip(order, vals)), "pass": bool(vals[0] < vals[1] < vals[2])}
        res["groups"][name] = g
    p3240 = S[(S["pad_name"] == "Delaware Pad 3240") & (S["parent"] == "WCB")]
    crit["C4"] = {"pad_3240": p3240[["draft", "conf"]].round(3).to_dict("records"),
                  "pass": bool(len(p3240) > 0 and (p3240["draft"] == "WCB_1").all())}
    crit["all_pass"] = bool(all(v["pass"] for c in ("C1", "C2", "C3") for v in crit[c].values()) and crit["C4"]["pass"])
    res["criteria"] = crit

    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    S.drop(columns=["undrilled"]).to_csv(out / "stick_tags.csv", index=False)
    (out / "SUMMARY.md").write_text(_summary_md(res), encoding="utf-8")
    return res


def _summary_md(res: dict) -> str:
    c = res["criteria"]
    L = [f"# Sub-bench inference v2: score at {res['git_sha']} ({res['run_at']})", "",
         f"Hold-out radius {res['hold_out_radius_mi']} mi; reference pool {res['n_pool']:,} laterals "
         f"({res['n_pool_producers']:,} producers); {res['n_sticks']:,} coarse sticks; current-rule re-implementation "
         f"reproduces the live tag on {res['current_reproduces_live_pct']}%.", "",
         "## Criteria (PLAN.md §3)", "", "| Criterion | Group | Draft | Reference | Pass |", "|---|---|---|---|---|"]
    for g, v in c["C1"].items():
        L.append(f"| C1 held-out producers | {g} | {v['draft']}% | current {v['current']}% | {'PASS' if v['pass'] else 'FAIL'} |")
    for g, v in c["C2"].items():
        L.append(f"| C2 Texas WCB vs depth below WCA (n={v['n']:,}) | {g} | {v['draft']}% | live {v['live']}% | {'PASS' if v['pass'] else 'FAIL'} |")
    for g, v in c["C3"].items():
        L.append(f"| C3 calibration (accuracy by band) | {g} | {' / '.join(f'{k} {x}%' for k, x in v['bands'].items())} | increasing | {'PASS' if v['pass'] else 'FAIL'} |")
    L.append(f"| C4 Pad 3240 stays WCB_1 | delaware_WCB | {', '.join(str(r['draft']) for r in c['C4']['pad_3240'])} | WCB_1 | {'PASS' if c['C4']['pass'] else 'FAIL'} |")
    L += ["", f"**All criteria: {'PASS' if c['all_pass'] else 'FAIL'}**", "", "## Stick impact", "",
          "| Group | Sticks | Flips vs live | Undrilled flips | Flips in box_scout | Frontier | Frontier in box_scout | Conf < 0.80 (non-frontier) |",
          "|---|---|---|---|---|---|---|---|"]
    for g, v in res["groups"].items():
        s = v.get("sticks")
        if s:
            L.append(f"| {g} | {s['n']:,} | {s['flips_vs_live']:,} ({s['flip_pct']}%) | {s['flips_undrilled']:,} | {s['flips_in_box_scout']:,} | "
                     f"{s['paths'].get('frontier', 0):,} | {s['frontier_in_box_scout']:,} | {s['review_conf_lt_080_non_frontier']:,} |")
    L += ["", "## Held-out producers by path", "", "| Group | Path | n | Draft | Current |", "|---|---|---|---|---|"]
    for g, v in res["groups"].items():
        for k, x in v["held_out_by_path"].items():
            L.append(f"| {g} | {k} | {x['n']:,} | {x['draft_pct']}% | {x['current_pct']}% |")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None, help="pickle of the pulled pool + sticks (reused if present)")
    a = ap.parse_args()
    res = run(a.out, a.cache)
    print(_summary_md(res))


if __name__ == "__main__":
    main()
