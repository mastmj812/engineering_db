"""BOX progress-update deck (Blue Ox brand template) for the 2026-10-19 group meeting — read-only.

    python -m scripts.box_update_deck frame --artifact runs/box9 --out runs/box9_deck     BOX run 9 (live run_id 10) x Novi BASE_CASE
    python -m scripts.box_update_deck novi-all --artifact runs/box9 --out runs/box9_deck  every Novi BASE_CASE PUD on each bench
    python -m scripts.box_update_deck maps  --out runs/box9_deck                          4 + 1 maps per bench (PNG)
    python -m scripts.box_update_deck deck  --out runs/box9_deck --pptx <file.pptx>      the deck

frame: one row per BOX-forecast location (covered + covered_provisional) with the Novi BASE_CASE forecast of the SAME stick
(curated.intel_locations + raw_intel.production_forecast, latest report): oil EUR per ft of lateral on a 30-YEAR basis for both
(Novi BASE_CASE runs 359 months; BOX months 1-360 of the stored record, whose own EUR is the raw 50-yr integral — stated on every
slide), and 12-month cumulative GOR (scf/bbl = 1,000 x cum-12 gas Mcf / cum-12 oil bbl; Novi volumes = rate x 30 d per 30-day step,
the sql/43 convention). novi-all: the same Novi numbers for EVERY run-9 universe PUD on the bench (inside the BOX extent or not;
remaining_pud / conflict / not_reconciled, no RES, no realized sticks), so the Novi maps show Novi's full bench footprint against
the tighter BOX extent. Extents of record + the TX/NM survey blocks (anduin infra/basemap) are context layers.
No database writes; no economics.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import shapely

from box import edge_gap as eg
from box import production as pr
from box import production_run9 as p9r

ANDUIN = Path(r"C:\Users\MichaelMast\Projects\permian_type_curve")
TEMPLATE = ANDUIN / "backend" / "app" / "exports" / "templates" / "deal_slide.pptx"
BLOCKS = ANDUIN / "infra" / "basemap" / "blocks_tx_nm.geojson"
EXTENT_OF = {g: ("WCA" if g == "WCXY_WCA1" else g) for g in p9r.GROUPS}
LABEL = {"WCXY_WCA1": "WCXY"}

_NOVI_SQL = """
SELECT il.stick_id, il.oil_eur, il.gas_eur, il.ll_ft, il.category,
       sum(pf.oil_per_day * 30) FILTER (WHERE pf.forecast_day BETWEEN 30 AND 360) AS oil12,
       sum(pf.gas_per_day * 30) FILTER (WHERE pf.forecast_day BETWEEN 30 AND 360) AS gas12,
       max(pf.forecast_day) AS last_day
FROM curated.intel_locations il
JOIN raw_intel.stick_id_map sm ON sm.stick_id = il.stick_id
JOIN raw_intel.planned_well pw ON 'PW-' || pw.planned_well_id::text = sm.well_ref
JOIN raw_intel.production_forecast pf ON pf.planned_well_id = pw.planned_well_id AND pf.report_name = pw.report_name
WHERE il.stick_id = ANY(%(sids)s)
  AND pf.report_name IN (SELECT max(report_name) FROM raw_intel.well_master GROUP BY split_part(report_name, '__', 2))
GROUP BY 1, 2, 3, 4, 5
"""


def label(g: str) -> str:
    return LABEL.get(g, g)


def cmd_frame(a: argparse.Namespace) -> int:
    from etl.db import get_connection

    with open(a.artifact / "run.pkl", "rb") as fh:
        A = pickle.load(fh)
    u = A["universe"].set_index("stick_id")
    rows = []
    for loc, r in zip(A["locs"], A["results"], strict=True):
        st = r.get("streams", {})
        if "oil" not in st:
            continue
        o, g = np.asarray(st["oil"]["months"], float), np.asarray(st["gas"]["months"], float)
        rows.append({"group": loc["prod_bench"], "stick_id": loc["stick_id"], "wkt": u.loc[loc["stick_id"], "wkt"], "lateral_ft": loc["lateral_ft"],
                     "box_oil50": float(o.sum()), "box_oil30": float(o[:360].sum()), "box_oil12": float(o[:12].sum()), "box_gas12": float(g[:12].sum()),
                     "edge_region": loc.get("edge_region")})
    f = pd.DataFrame(rows)
    nv = a.out / "novi.csv"
    if nv.exists():
        n = pd.read_csv(nv)
    else:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '1800s'")
            n = pd.DataFrame(cur.execute(_NOVI_SQL, {"sids": sorted(f["stick_id"].astype(int))}).fetchall(),
                             columns=["stick_id", "oil_eur", "gas_eur", "ll_ft", "category", "oil12", "gas12", "last_day"])
            conn.rollback()
        n.to_csv(nv, index=False)
    f = f.merge(n[["stick_id", "oil_eur", "ll_ft", "category", "oil12", "gas12", "last_day"]], on="stick_id", how="left", validate="1:1")
    if f["oil_eur"].isna().any() or set(f["category"]) != {"PUD"}:
        raise SystemExit(f"{int(f['oil_eur'].isna().sum())} BOX locations without a Novi BASE_CASE forecast; categories {set(f['category'])}")
    f = f.rename(columns={"oil_eur": "novi_oil30", "oil12": "novi_oil12", "gas12": "novi_gas12"})
    L = f["lateral_ft"].astype(float)
    f["box_eur_ft"], f["novi_eur_ft"] = f["box_oil30"] / L, f["novi_oil30"] / L
    f["box_gor12"], f["novi_gor12"] = 1000 * f["box_gas12"] / f["box_oil12"], 1000 * f["novi_gas12"] / f["novi_oil12"]
    f["ratio"] = f["box_oil30"] / f["novi_oil30"]
    f.to_csv(a.out / "frame.csv", index=False)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        ext = {b: cur.execute("SELECT extensions.ST_AsText(geom) FROM box.extent WHERE is_record AND basin = 'delaware' AND bench = %s", (b,)).fetchone()[0]
               for b in sorted(set(EXTENT_OF.values()))}
        conn.rollback()
    (a.out / "extents.json").write_text(json.dumps(ext), encoding="utf-8")
    print(f"{len(f)} locations; lateral = Novi ll_ft on {float((np.abs(f['lateral_ft'] - f['ll_ft']) < 1).mean()):.1%}; Novi last day {sorted(set(f['last_day']))[:3]}")
    print(summary(f).to_string(index=False))
    return 0


def bench_universe(A: dict[str, Any], g: str) -> pd.DataFrame:
    """Every run-9 universe PUD on group g's bench + formations, whatever its coverage class (the Novi bench footprint)."""
    u = A["universe"]
    basin, bench, forms = pr.PRODUCTION_BENCHES[g]
    return u[(u["basin"] == basin) & (u["bench"] == bench) & u["formation_blueox"].isin(forms)]


def cmd_novi_all(a: argparse.Namespace) -> int:
    from etl.db import get_connection

    with open(a.artifact / "run.pkl", "rb") as fh:
        A = pickle.load(fh)
    parts = []
    for g in p9r.GROUPS:
        b = bench_universe(A, g)
        parts.append(pd.DataFrame({"group": g, "stick_id": b["stick_id"].astype(int), "wkt": b["wkt"], "coverage": b["coverage"]}))
    u = pd.concat(parts, ignore_index=True)
    if u["stick_id"].duplicated().any():
        raise SystemExit(f"{int(u['stick_id'].duplicated().sum())} sticks fall in more than one group")
    cols = ["stick_id", "oil_eur", "gas_eur", "ll_ft", "category", "oil12", "gas12", "last_day"]
    have = pd.read_csv(a.out / "novi.csv") if (a.out / "novi.csv").exists() else pd.DataFrame(columns=cols)
    miss = sorted(set(u["stick_id"]) - set(have["stick_id"].astype(int)))
    print(f"{len(u):,} bench PUDs; {len(miss):,} need a Novi pull", flush=True)
    got = []
    with get_connection() as conn, conn.cursor() as cur:
        for i in range(0, len(miss), 10000):
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '1800s'")
            got.append(pd.DataFrame(cur.execute(_NOVI_SQL, {"sids": miss[i:i + 10000]}).fetchall(), columns=cols))
            conn.rollback()
            print(f"  {min(i + 10000, len(miss)):,} / {len(miss):,}", flush=True)
    n = pd.concat([have, *got], ignore_index=True).drop_duplicates("stick_id")
    n["stick_id"] = n["stick_id"].astype(int)
    m = u.merge(n, on="stick_id", how="left", validate="1:1")
    lost = m["oil_eur"].isna()
    if (m.loc[~lost, "category"] != "PUD").any():
        raise SystemExit(f"non-PUD categories {set(m['category'])}")
    m = m[~lost].copy()
    L = m["ll_ft"].astype(float)
    m["novi_eur_ft"] = m["oil_eur"].astype(float) / L
    m["novi_gor12"] = 1000 * m["gas12"].astype(float) / m["oil12"].astype(float)
    m["inside"] = m["coverage"].isin(pr.COVERED)
    m[["group", "stick_id", "wkt", "coverage", "inside", "ll_ft", "oil_eur", "oil12", "gas12", "novi_eur_ft", "novi_gor12"]].to_csv(
        a.out / "novi_all.csv", index=False)
    print(f"{int(lost.sum()):,} bench PUDs without a Novi BASE_CASE forecast (dropped)")
    print(m.groupby("group", sort=False).agg(novi_puds=("stick_id", "size"), inside_extent=("inside", "sum")).to_string())
    return 0


def summary(f: pd.DataFrame) -> pd.DataFrame:
    out = []
    for g in p9r.GROUPS:
        x = f[f["group"] == g]
        out.append({"bench": label(g), "tier": p9r.tier(g), "locations": len(x),
                    "BOX oil EUR/ft (30-yr) P50": float(x["box_eur_ft"].median()), "Novi oil EUR/ft P50": float(x["novi_eur_ft"].median()),
                    "BOX / Novi (sum)": float(x["box_oil30"].sum() / x["novi_oil30"].sum()),
                    "BOX / Novi P10 (high)": float(np.percentile(x["ratio"], 90)), "BOX / Novi P90 (low)": float(np.percentile(x["ratio"], 10)),
                    "BOX 30-yr / 50-yr": float(x["box_oil30"].sum() / x["box_oil50"].sum()),
                    "BOX GOR12 P50": float(x["box_gor12"].median()), "Novi GOR12 P50": float(x["novi_gor12"].median()),
                    "BOX oil MMbbl (30-yr)": float(x["box_oil30"].sum() / 1e6), "Novi oil MMbbl": float(x["novi_oil30"].sum() / 1e6)})
    return pd.DataFrame(out)


def project(wkts: list[str]) -> list[Any]:
    return eg.to_ft(list(shapely.from_wkt(wkts)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("frame", "novi-all", "maps", "deck"):
        p = sub.add_parser(name)
        p.add_argument("--artifact", type=Path, default=Path("runs") / "box9")
        p.add_argument("--out", type=Path, default=Path("runs") / "box9_deck")
        p.add_argument("--pptx", type=Path, default=None)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "frame":
        return cmd_frame(a)
    if a.cmd == "novi-all":
        return cmd_novi_all(a)
    from scripts import box_update_deck_render as rd

    return rd.cmd_maps(a) if a.cmd == "maps" else rd.cmd_deck(a)


if __name__ == "__main__":
    sys.exit(main())
