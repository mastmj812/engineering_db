"""BOX record-run map: covered PUD sticks coloured by BOX oil EUR per foot (READ ONLY).

    python -m scripts.box_eur_map [--out docs/box/eur-map-2026-10-17]

EUR/ft = box.pud_forecast_stream.eur_per_kft / 1,000 for oil: the delivered EUR (raw 50-yr technical integral x the bench's
haircut, D62 / D92 / D102; raw box_v2 benches carry factor 1, D97) per foot of COMPLETED lateral (D56; the box_pud_run
denominator). One layer per formation_blueox, the extents of record of every covered bench as outlines, a popup per stick.
Whatever bench a later record run covers appears without code changes. Writes one self-contained index.html (Leaflet 1.9.4).
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import tc_curve_report as rep
from etl.db import get_connection

BINS = (40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0)  # bbl/ft class breaks
COLORS = ("#440154", "#46327e", "#365c8d", "#277f8e", "#1fa187", "#4ac16d", "#a0da39", "#fde725")  # viridis, 8 classes

_SQL = """
SELECT f.location_id, f.formation_blueox, f.bench, f.pad_name, f.completed_lateral_ft, f.radius_class, f.radius_mi, f.n_analogs, f.search_mode,
       s.eur, s.eur_per_kft / 1000.0, s.eur_haircut, s.cum24,
       extensions.ST_AsGeoJSON(extensions.ST_SimplifyPreserveTopology(l.geom, 0.0002), 5)
FROM box.pud_forecast f
JOIN box.forecast_run r USING (run_id)
JOIN box.pud_forecast_stream s ON s.run_id = f.run_id AND s.location_id = f.location_id AND s.stream = 'oil'
JOIN box.location l ON l.location_id = f.location_id
WHERE r.is_record AND r.basin = 'delaware'  -- D130: the Delaware record
"""
_COUNTS_SQL = """
SELECT f.bench, f.coverage, count(*) FROM box.pud_forecast f JOIN box.forecast_run r USING (run_id)
WHERE r.is_record AND r.basin = 'delaware' AND f.basin = 'delaware' GROUP BY 1, 2 ORDER BY 1, 2
"""
_EXT_SQL = """
SELECT e.bench, e.extent_id, extensions.ST_AsGeoJSON(extensions.ST_SimplifyPreserveTopology(e.geom, 0.002), 4)
FROM box.extent e WHERE e.is_record AND e.basin = 'delaware'
  AND e.bench IN (SELECT DISTINCT f.bench FROM box.pud_forecast f JOIN box.forecast_run r USING (run_id) WHERE r.is_record AND r.basin = 'delaware' AND f.coverage = 'covered')
"""
_RUN_SQL = "SELECT run_id FROM box.forecast_run WHERE is_record AND basin = 'delaware'"


def color_of(v: float) -> str:
    return COLORS[int(np.searchsorted(BINS, v, side="right"))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "eur-map-2026-10-17")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        d = pd.DataFrame(rep._read(conn, _SQL, {}), columns=["location_id", "formation", "bench", "pad", "lat_ft", "radius_class", "radius_mi", "n_analogs",
                                                           "search", "eur", "eur_ft", "haircut", "cum24", "geo"])
        counts = pd.DataFrame(rep._read(conn, _COUNTS_SQL, {}), columns=["bench", "coverage", "n"])
        ext = rep._read(conn, _EXT_SQL, {})
        run = rep._read(conn, _RUN_SQL, {})
        conn.rollback()
    for c in ("lat_ft", "radius_mi", "eur", "eur_ft", "haircut", "cum24"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    feats: dict[str, list[dict]] = {}
    for r in d.itertuples():
        g = json.loads(r.geo)
        feats.setdefault(r.formation, []).append({"c": g["coordinates"], "t": g["type"], "k": color_of(r.eur_ft),
                                                 "p": f"<b>{r.formation}</b> · {r.pad or ''}<br>oil EUR <b>{r.eur_ft:.1f} bbl/ft</b> · {r.eur / 1e3:,.0f} Mbbl<br>"
                                                      f"completed lateral {r.lat_ft:,.0f} ft · haircut ×{r.haircut:.3f}<br>"
                                                      f"cum-24 {r.cum24 / 1e3:,.0f} Mbbl · {r.n_analogs} analogs, {r.search} {r.radius_mi:g} mi ({r.radius_class})"})
    stats = d.groupby("formation")["eur_ft"].describe(percentiles=[0.1, 0.5, 0.9])[["count", "10%", "50%", "90%"]].round(1).reset_index()
    rid = run[0][0] if run else "?"
    legend = "".join(f"<div><span style='background:{c}'></span>{lab}</div>" for c, lab in zip(
        COLORS, [f"< {BINS[0]:.0f}"] + [f"{lo:.0f}–{hi:.0f}" for lo, hi in itertools.pairwise(BINS)] + [f"≥ {BINS[-1]:.0f}"], strict=True))
    stat_rows = "".join(f"<tr><td>{r.formation}</td><td>{int(r['count']):,}</td><td>{r['10%']}</td><td>{r['50%']}</td><td>{r['90%']}</td></tr>"
                        for _, r in stats.iterrows())
    cov = counts.pivot_table(index="bench", columns="coverage", values="n", fill_value=0)
    cov_rows = "".join(f"<tr><td>{b}</td><td>{int(row.get('covered', 0)):,}</td><td>{int(row.sum() - row.get('covered', 0)):,}</td></tr>" for b, row in cov.iterrows())
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    payload = json.dumps({"layers": feats, "extents": [{"bench": b, "id": i, "g": json.loads(g)} for b, i, g in ext]}, separators=(",", ":"))
    page = f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>BOX oil EUR map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{{--bg:#fff;--fg:#111827;--muted:#6b7280;--panel:rgba(255,255,255,.94);--line:#e5e7eb}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--bg:#0f1115;--fg:#e5e7eb;--muted:#9ca3af;--panel:rgba(20,22,28,.94);--line:#2a2f3a}}}}
:root[data-theme="dark"]{{--bg:#0f1115;--fg:#e5e7eb;--muted:#9ca3af;--panel:rgba(20,22,28,.94);--line:#2a2f3a}}
html,body{{margin:0;height:100%;background:var(--bg);color:var(--fg);font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif}}
#map{{position:absolute;inset:0}}
.panel{{position:absolute;z-index:1000;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px 10px;max-width:min(360px,calc(100vw - 32px))}}
#info{{top:10px;left:56px;max-height:calc(100vh - 220px);overflow:auto}} summary{{cursor:pointer}} #leg{{bottom:22px;left:10px}} h1{{font-size:15px;margin:0 0 4px}} .m{{color:var(--muted);font-size:11px}}
#leg span{{display:inline-block;width:22px;height:5px;margin-right:6px;vertical-align:middle}}
table{{border-collapse:collapse;font-size:11px;margin-top:4px}} td,th{{border-bottom:1px solid var(--line);padding:1px 6px;text-align:right}} td:first-child,th:first-child{{text-align:left}}
</style></head><body><div id=map></div>
<div class="panel" id=info><h1>BOX oil EUR per foot — record run {rid}</h1>
<div class=m>Covered PUDs only · delivered oil EUR (raw 50-yr technical integral × bench haircut; raw-record benches ×1) ÷ completed lateral ·
built {built} · code {sha} · read-only. Toggle formations top-right; click a stick for its numbers.</div>
<details open><summary class=m>EUR/ft by formation (bbl/ft)</summary>
<table><tr><th>formation</th><th>PUDs</th><th>P10</th><th>P50</th><th>P90</th></tr>{stat_rows}</table>
<div class=m>P10 / P90 here = 10th / 90th percentile (P10 low), not SPE.</div></details>
<details><summary class=m>coverage on this run (not-covered PUDs are not drawn; never zero)</summary>
<table><tr><th>bench</th><th>covered</th><th>not covered</th></tr>{cov_rows}</table></details></div>
<div class="panel" id=leg><b>oil EUR, bbl/ft</b>{legend}<div class=m>outline = extent of record</div></div>
<script>
const D={payload};
const map=L.map('map',{{preferCanvas:true}}).setView([31.9,-103.6],8);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{attribution:'© OpenStreetMap contributors',maxZoom:17,opacity:.55}}).addTo(map);
const overlays={{}}, all=[];
for(const e of D.extents){{const g=L.geoJSON(e.g,{{style:{{color:'#555',weight:1.2,fill:false,dashArray:'4 3'}},interactive:false}}).addTo(map);overlays['extent '+e.bench+' ('+e.id+')']=g;}}
for(const [fm,fs] of Object.entries(D.layers)){{
  const grp=L.layerGroup();
  for(const f of fs){{
    const ll=(f.t==='LineString'?f.c:f.c.flat()).map(p=>[p[1],p[0]]);
    const s=ll.length>1?L.polyline(ll,{{color:f.k,weight:3,opacity:.95}}):L.circleMarker(ll[0],{{radius:3,color:f.k,fillOpacity:1}});
    s.bindPopup(f.p); grp.addLayer(s); all.push(...ll);
  }}
  grp.addTo(map); overlays[fm+' ('+fs.length.toLocaleString()+')']=grp;
}}
L.control.layers(null,overlays,{{collapsed:false}}).addTo(map);
if(all.length) map.fitBounds(L.latLngBounds(all).pad(0.03));
</script></body></html>"""
    (a.out / "index.html").write_text(page, encoding="utf-8")
    stats.to_csv(a.out / "eur_ft_by_formation.csv", index=False)
    print(stats.to_string(index=False))
    print(f"wrote {a.out / 'index.html'} ({len(d):,} sticks, {(a.out / 'index.html').stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
