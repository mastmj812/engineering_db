"""BOX step 21d — the 2026 Midland prospective test (box/prospective21.py). Read-only.

    python -m scripts.box_prospective21 snapshot   cohort identities + packages + proximity configuration (NO volumes):
                                                   cohort_at_draft.csv, judgeability_*.csv, snapshot.json; the 2025 cohort
                                                   (tuning-era wells, identities only) is counted beside it for the full-year scale
    python -m scripts.box_prospective21 manifest   tuning_views.sha256 (the 21b tuning views + the links cache the intervals use)
    python -m scripts.box_prospective21 oc         DB-free: operating characteristics of both graduation rules on TUNING packages
    python -m scripts.box_prospective21 status     cohort per group now (identities only) + when each horizon is judged
    python -m scripts.box_prospective21 score      refuses: not built. Written and committed BEFORE its one run, first checked on
                                                   the 2024-12-01 fold (must reproduce the 21b tuning cells)

Nothing here reads a 2026 well's production volume: the cohort query names its columns (an allowlist the test pins), the
proximity links are geometry + first-production dates (box/prox_study.links_for_child), and the operating characteristics read
only the 21b tuning views (wells first producing before 2025-12-01).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely

from box import acceptance as ac
from box import prospective21 as p21
from box import prox_cont as pc
from box import prox_study_report as psr
from box import spacing3d as s3
from box import step21_prox as sp
from box import wcb_split as wcb

RUNS = Path("runs") / "step21d"


# ----------------------------------------------------------------------------
# snapshot (DB, identities only)
# ----------------------------------------------------------------------------

COHORT_COLS = ["api10", "formation_blueox", "first_production_date", "state_code", "operator", "lateral_length_ft", "tvd_ft",
               "has_production_sharing", "mid_lon", "mid_lat"]


def _cohort_frame(conn: Any, fp0: dt.date, fp1: dt.date) -> pd.DataFrame:
    rows = []
    for g in p21.GROUPS:
        rows += [(g, *r) for r in p21.cohort(conn, g, fp0, fp1)]
    d = pd.DataFrame(rows, columns=["group", *COHORT_COLS])
    d["api10"] = d["api10"].astype(str)
    d["first_production_date"] = pd.to_datetime(d["first_production_date"]).dt.date
    return d


def _d136_candidates(conn: Any, fp0: dt.date, fp1: dt.date) -> pd.DataFrame:
    """WCB_2-tagged wells inside the WCB_1 extent north of the D136 line: D136 (c) moves the ones landing < 392 ft below the
    local WCA_1 band into WCB_1 for BOX. Counted here (the depth test is applied at scoring); identities only."""
    rows = p21.cohort(conn, "MID_WCB_1", fp0, fp1, forms=["WCB_2"])
    d = pd.DataFrame(rows, columns=COHORT_COLS)
    if d.empty:
        return d.assign(north=pd.Series(dtype=bool))
    north = shapely.contains_xy(wcb.north_poly(), pd.to_numeric(d["mid_lon"]).to_numpy(float), pd.to_numeric(d["mid_lat"]).to_numpy(float))
    return d.assign(north=north)


def _packages(c: pd.DataFrame, geom: dict[str, Any], tvd: dict[str, float]) -> dict[str, str]:
    """D53 packages among one group-year cohort: box/acceptance.packages on co-extent pairs (box/spacing3d.pair_geometry) between
    cohort wells only. A well without lateral geometry or TVD is a package of one (the harness's behaviour)."""
    ids = [a for a in c["api10"] if a in geom]
    fp = dict(zip(c["api10"], c["first_production_date"], strict=True))
    lines = [geom[a] for a in ids]
    tree = shapely.STRtree(lines) if lines else None
    pairs: dict[str, list[s3.Pair]] = {}
    for i, a in enumerate(ids):
        out = []
        for j in (tree.query(lines[i], predicate="dwithin", distance=s3.GATE) if tree is not None else []):
            if j == i:
                continue
            b = ids[j]
            p = s3.pair_geometry(lines[i], lines[j], tvd.get(a, np.nan), tvd.get(b, np.nan), (fp[b] - fp[a]).days, b, ac.PACKAGE_OVERLAP)
            if p is not None:
                out.append(p)
        pairs[a] = out
    pk = ac.packages(ids, pairs)
    return {a: pk.get(a, a) for a in c["api10"]}


def _model() -> pc.Model:
    m = p21.D150_MIDLAND
    return pc.Model(curve=pc.Curve(m["f_min"], m["d50_ft"], m["k"]), a_below=m["a_below"], a_above=m["a_above"], level=m["level"])


def d150_factor(d: pd.DataFrame, links: pd.DataFrame, drilled: bool = True, model: pc.Model | None = None) -> pd.DataFrame:
    """The shipped oil multiplier per well: level x F_R3 over its counting parents (box/prox_cont.parents + rule_factor). `d`
    needs api10. Returns F_rule, factor, n_parents, nearest_d_eff, pattern (index aligned to d)."""
    model = model or _model()
    par = pc.parents(links, drilled=drilled)
    rf = pc.rule_factor(d[["api10"]], par, model, p21.D150_MIDLAND["rule"])
    rf["factor"] = model.level * rf["F_rule"].to_numpy(float)
    return rf


def snapshot(out: Path) -> int:
    t0 = time.time()
    from etl.db import get_connection

    out.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        c26 = _cohort_frame(conn, p21.FP_FROM, p21.FP_TO).assign(cohort="2026")
        c25 = _cohort_frame(conn, dt.date(2025, 1, 1), dt.date(2025, 12, 31)).assign(cohort="2025")
        d136 = pd.concat([_d136_candidates(conn, p21.FP_FROM, p21.FP_TO).assign(cohort="2026"),
                          _d136_candidates(conn, dt.date(2025, 1, 1), dt.date(2025, 12, 31)).assign(cohort="2025")], ignore_index=True)
        print(f"[cohort] 2026 {len(c26):,} wells, 2025 {len(c25):,} ({time.time() - t0:.0f} s)", flush=True)
        u = psr.pull_universe(conn, "midland")   # geometry + bench + first production + TVD only (box/prox_study_report)
        print(f"[universe] {len(u):,} producing horizontals ({time.time() - t0:.0f} s)", flush=True)
    c = pd.concat([c26, c25], ignore_index=True)
    geom = dict(zip(u["api10"], u["geom"], strict=True))
    tvd = dict(zip(u["api10"], u["tvd_ft"], strict=True))
    # packages per group x cohort year
    c["package"] = None
    for (g, y), x in c.groupby(["group", "cohort"]):
        pk = _packages(x, geom, tvd)
        c.loc[x.index, "package"] = [f"{y}:{pk[a]}" for a in x["api10"]]
    # drilled-side links of every cohort well (children = cohort wells with TVD + lateral in the universe)
    kids = u[u["api10"].isin(set(c["api10"])) & u["tvd_ft"].notna() & (u["lat_ft"] >= psr.MIN_LATERAL_FT)].reset_index(drop=True)
    L = psr.build_links(u, kids, log_every=0)
    L.to_pickle(RUNS / "cohort_links.pkl")
    print(f"[links] {len(kids):,} children, {len(L):,} links ({time.time() - t0:.0f} s)", flush=True)
    c["has_links_row"] = c["api10"].isin(set(kids["api10"]))
    drilled = d150_factor(c, L, drilled=True)
    for col in ("factor", "n_parents", "nearest_d_eff", "pattern"):
        c[f"{col}_drilled" if col != "factor" else "d150_factor"] = drilled[col].to_numpy()
    # stick-side sensitivity: every producer existing at the cutoff is a parent (21a revision 4), permit TVDs counted
    # each cohort year against its own cutoff (2026 wells: 2025-12-01; the 2025 reference wells: 2024-12-01)
    cut_of = {"2026": p21.CUTOFF, "2025": dt.date(2024, 12, 1)}
    lagd = {a: (f - cut_of[y]).days for a, f, y in zip(c["api10"], c["first_production_date"], c["cohort"], strict=True)}
    lag = L["child"].map(lagd).fillna(0)
    stick = sp.existing_as_parents(L[(L["age_days"] > lag) & (L["rel"] != "child")])
    st = d150_factor(c, stick, drilled=False)
    c["d150_factor_stick"], c["n_parents_stick"] = st["factor"].to_numpy(), st["n_parents"].to_numpy()
    near = sp.nearest_same_ft(sp.by_depth(stick))
    c["nearest_same_ft_at_cutoff"] = c["api10"].map(near)
    c["floor_400"] = c["nearest_same_ft_at_cutoff"] <= sp.SPACING_FLOOR_FT
    c["fp_month"] = [f"{d.year}-{d.month:02d}" for d in c["first_production_date"]]
    keep = ["group", "cohort", *COHORT_COLS, "fp_month", "package", "has_links_row", "n_parents_drilled", "nearest_d_eff_drilled",
            "pattern_drilled", "d150_factor", "n_parents_stick", "d150_factor_stick", "nearest_same_ft_at_cutoff", "floor_400"]
    c[keep].sort_values(["cohort", "group", "first_production_date", "api10"]).to_csv(out / "cohort_at_draft.csv", index=False, lineterminator="\n",
                                                                                       float_format="%.6g")
    d136.to_csv(out / "d136_candidates.csv", index=False, lineterminator="\n", float_format="%.6g")
    by_month = c.groupby(["cohort", "group", "fp_month"]).agg(wells=("api10", "size"), packages=("package", "nunique")).reset_index()
    by_month.to_csv(out / "cohort_by_month.csv", index=False, lineterminator="\n")
    meta = {"built_utc": dt.datetime.now(tz=dt.UTC).strftime("%Y-%m-%d %H:%M"), "definition_digest": p21.digest(),
            "wells_2026": int((c["cohort"] == "2026").sum()), "wells_2025": int((c["cohort"] == "2025").sum()),
            "universe": len(u), "children_with_links": len(kids), "links": len(L), "seconds": round(time.time() - t0),
            "newest_first_production_2026": str(c26["first_production_date"].max()) if len(c26) else None,
            "read": "curated.wells identity / geometry / first-production / TVD columns, curated.formation_blueox, curated.wells_enriched "
                    "bench, box.extent; no production table, no volume column"}
    (out / "snapshot.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=1))
    return 0


# ----------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------


def status() -> int:
    from etl.db import get_connection

    print(f"definition {p21.DEFINITION['name']} · digest {p21.digest()[:12]} (pinned {p21.DIGEST[:12]}) · cutoff {p21.CUTOFF} · "
          f"as of {dt.datetime.now(tz=dt.UTC).date()}")
    tot: Counter[str] = Counter()
    with get_connection() as conn:
        for g, (_, ext, tier) in p21.GROUPS.items():
            n = len(p21.cohort(conn, g))
            tot[tier] += n
            print(f"  {g:10s} {tier:11s} extent {ext:2d}  wells {n:4d}")
    print(f"  total {sum(tot.values())} (validated {tot['validated']}, provisional {tot['provisional']}); packages <= wells")
    for k, v in p21.DEFINITION["schedule"].items():
        print(f"  {k}: {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("snapshot", "manifest", "oc", "status", "score"))
    ap.add_argument("--out", type=Path, default=p21.DOCS)
    ap.add_argument("--runs", type=Path, default=p21.TUNING_RUNS, help="the 21b tuning runs root (default runs/step21b)")
    ap.add_argument("--links", type=Path, default=p21.LINKS_CACHE)
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        return snapshot(a.out)
    if a.cmd == "status":
        return status()
    if a.cmd in ("manifest", "oc"):
        from scripts import box_prospective21_oc as oc

        return oc.manifest(a.runs, a.links, a.out) if a.cmd == "manifest" else oc.run(a.runs, a.links, a.out)
    raise SystemExit("score is not built yet: cum-12 is judged once, with production through >= 2028-01-01 (PREREGISTRATION §5)")


if __name__ == "__main__":
    sys.exit(main())
