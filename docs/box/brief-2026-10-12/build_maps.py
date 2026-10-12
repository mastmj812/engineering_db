"""Meeting maps for the BOX status brief (read-only). Writes maps.json next to this script.

brief.html = template.html with the compact maps.json text substituted for the __DATA__ token.
Novi sticks are curated.intel_locations category 'PUD' (= BASE_CASE), 2026Q3 vintage as of 2026-10-12."""
import json, math, sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape

REPO = Path(r"C:\Users\MichaelMast\Projects\engineering_db")
sys.path.insert(0, str(REPO))
from etl.db import get_connection  # noqa: E402

OUT = Path(__file__).with_name("maps.json")
EXT = {p: shape([f for f in json.load(open(REPO / f"docs/box/step3-2026-10-07/extent_{p}_v1.geojson"))["features"]
                  if f["properties"].get("layer") == "extent"][0]["geometry"]) for p in ("WCA", "BS2_S")}
BENCH = {"WCA": ["WCA_1", "WCA_2", "WCXY"], "BS2_S": ["BS2_S"]}

SQL = """
SELECT il.stick_id, fb.formation_blueox, ri.status, ST_AsText(il.wellstick_geom)
FROM curated.intel_locations il
JOIN curated.intel_formation_blueox fb ON fb.stick_id = il.stick_id
LEFT JOIN curated.reconciled_inventory ri ON ri.stick_id = il.stick_id
WHERE il.category = 'PUD' AND il.basin = 'delaware'
  AND fb.formation_blueox = ANY(%(b)s) AND il.wellstick_geom IS NOT NULL
"""

# equal-ish projection: lon * cos(32 deg)
K = math.cos(math.radians(32.0))


def proj(x, y):
    return x * K, y


conn = get_connection()
out = {}
for pool, benches in BENCH.items():
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(SQL, {"b": benches})
        rows = cur.fetchall()
    conn.rollback()
    d = pd.DataFrame(rows, columns=["stick_id", "fb", "status", "wkt"])
    g = shapely.from_wkt(d["wkt"].to_numpy())
    ext = EXT[pool]
    shapely.prepare(ext)
    # inside = >= 50 % of stick length (rule 9 co-extent, same as step 3), measured in projected deg
    L = shapely.length(g)
    frac = np.divide(shapely.length(shapely.intersection(g, ext)), L, out=np.zeros(len(L)), where=L > 0)
    d["inside"] = frac >= 0.5
    st = d["status"].fillna("NULL")
    d["d1"] = st.isin(["remaining_pud", "conflict", "NULL"])
    sticks = []
    for gg, ins, d1, fb in zip(g, d["inside"], d["d1"], d["fb"]):
        c = shapely.get_coordinates(gg)
        a, b = c[0], c[-1]
        sticks.append([round(a[0], 4), round(a[1], 4), round(b[0], 4), round(b[1], 4), int(ins), int(d1), fb])
    counts = (d.assign(st=st).groupby(["fb", "st", "inside"]).size().reset_index(name="n").to_dict("records"))
    simp = ext.simplify(0.002)
    out[pool] = {"extent": shapely.geometry.mapping(simp), "sticks": sticks, "counts": counts,
                 "area_sqmi": None}
    print(pool, len(d), "inside", int(d.inside.sum()), "D1 inside", int((d.inside & d.d1).sum()),
          "D1 total", int(d.d1.sum()))
conn.close()

# TC areas + per-area metrics
areas = json.load(open(REPO / "docs/box/step4-2026-10-09/areas_WCA_v1.geojson"))
tc = pd.read_csv(REPO / "docs/box/step5d-2026-10-12/type_curve.csv")
s5 = pd.read_csv(REPO / "docs/box/step5b-2026-10-10/areas_WCA.csv").set_index("area_no")
rec = {}
for _, r in tc.iterrows():
    p = json.loads(r["params"]) if isinstance(r["params"], str) else {}
    rec.setdefault(int(r.area_no), {})[r.stream] = {"eur": r.eur_per_kft, "n": int(r.n_wells), "p": p,
                                                   "cum12": r.cum12_kft}
feats = []
for f in areas["features"]:
    pr = f["properties"]
    a = int(pr["area_no"])
    geom = shape(f["geometry"]).simplify(0.002)
    o = rec.get(a, {}).get("oil", {})
    gas = rec.get(a, {}).get("gas", {})
    feats.append({"area": a, "geom": shapely.geometry.mapping(geom),
                  "bo_ft": pr["bo_ft_p50"], "n_eur": pr["n_eur"], "oil12": pr["oil12_p50"], "n12": pr["n12"],
                  "box_eur_kft": o.get("eur"), "n_oil": o.get("n"), "oil_p": o.get("p"),
                  "gor12": float(s5.loc[a, "area_gor12_actual"]) if a in s5.index else None,
                  "op": pr.get("top_operator"), "op_share": pr.get("top_operator_share"),
                  "sqmi": pr["area_sqmi"]})
out["areas"] = feats
print("sample oil params", feats[0]["oil_p"])
OUT.write_text(json.dumps(out, default=float))
print("wrote", OUT, OUT.stat().st_size)
