"""BOX step 6 — production plots for the hindcast: actual vs Novi 2025Q3 vs BOX, months 1..24, per holdout well.

Built inside the hindcast run (box/hindcast_report.run) from the same rebuilt objects, so a plotted BOX line is
exactly the prediction that was scored:

  * actual  = curated.production monthly volumes from the first reported month (calendar months, partial first
    month), the well's newest reported month dropped (sql/43's is_latest_reported rule);
  * Novi    = the matched 2025Q3 stick's forecast (raw_intel.production_forecast, 30-day months), scaled to the
    drilled lateral (drilled / Novi stick lateral) — the per-ft basis sql/43 scores it on; Novi-matched wells only;
  * BOX     = area mean curve x lateral / 1,000 x ref_mult x f_oil (gas at the local GOR x f_GOR), per month (D39),
    uptime-free; BOX of record = its cum x F(k) (D36), with F(k) fitted for every month 1..24 on the training
    cohort (the scored cum-6 / cum-12 values are F(6) / F(12) exactly).

Writes production.html (self-contained: data inline, vanilla SVG) next to acceptance.html.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import numpy as np
import pandas as pd

from box import basin as bsn
from box import hindcast as hc
from box import tc_curve_report as rep

K = 24
NOVI_REPORT_NAME = bsn.novi_report(bsn.DELAWARE, "2025Q3")  # basin_research__Delaware_Basin__2025Q3; pull_novi keys on its basin + report

_NOVI_SQL = """
WITH v AS (
    SELECT DISTINCT api10, novi_well_ref FROM curated.intel_forecast_accuracy_vintage
    WHERE report_version = %(r)s AND basin = %(b)s AND tier = 'direct' AND api10 = ANY(%(a)s)
)
SELECT v.api10, (pf.forecast_day / 30)::int AS mop, pf.oil_per_day * 30, pf.gas_per_day * 30
FROM v JOIN raw_intel.production_forecast pf
  ON pf.planned_well_id = substring(v.novi_well_ref FROM 4)::bigint AND pf.report_name = %(rn)s
 AND pf.forecast_day BETWEEN 30 AND %(dmax)s
"""


def monthly_matrix(prod: pd.DataFrame, api10s: list[str], *, asof: dt.date | None = None, drop_latest: bool = False, k: int = K) -> dict[str, np.ndarray]:
    """[wells, k] monthly oil / gas from each well's first reported month; months not yet known are NaN.
    Known = through `asof` (training) or through the well's newest reported month minus one (drop_latest)."""
    out = {s: np.full((len(api10s), k), np.nan) for s in ("oil", "gas")}
    g = dict(tuple(prod.groupby("api10")))
    for i, a in enumerate(api10s):
        p = g.get(a)
        if p is None:
            continue
        p = p.sort_values("prod_date")
        d0 = p["prod_date"].iloc[0]
        idx = np.array([(d.year - d0.year) * 12 + d.month - d0.month for d in p["prod_date"]])
        if asof is not None:
            n = (asof.year - d0.year) * 12 + asof.month - d0.month + 1
        else:
            n = int(idx.max()) + (0 if drop_latest else 1)
        n = min(n, k)
        for s, col in (("oil", "oil_bbl"), ("gas", "gas_mcf")):
            v = np.zeros(k)
            m = idx < k
            v[idx[m]] = pd.to_numeric(p[col], errors="coerce").fillna(0.0).to_numpy(float)[m]
            out[s][i, :n] = v[:n]
    return out


def box_months(fr: pd.DataFrame, cb: dict[str, Any], rm: dict[int, dict[str, Any]], k: int = K) -> dict[str, np.ndarray]:
    """[wells, k] BOX monthly oil / gas WITHOUT F(k): curve months x lateral / 1,000 x ref_mult x f_oil."""
    out = {s: np.full((len(fr), k), np.nan) for s in ("oil", "gas")}
    for i, r in enumerate(fr.itertuples()):
        a = int(r.area_no)
        st = cb["curves"][a]["streams"]
        scale = float(r.lateral_ft) / 1000.0 * rm[a]["ref_mult"] * float(r.f_oil)
        out["oil"][i] = hc.curve_months(st["oil"]["curve"], None, k)["oil"] * scale
        out["gas"][i] = hc.curve_months(st["gas"]["curve"], r.gor_target, k)["gas"] * scale
    return out


def pull_novi(conn: Any, api10s: list[str], report: str, basin: str) -> dict[str, dict[str, np.ndarray]]:
    rows = rep._read(conn, _NOVI_SQL, {"r": report, "b": basin, "a": api10s, "rn": bsn.novi_report(basin, report), "dmax": 30 * K})
    d = pd.DataFrame(rows, columns=["api10", "mop", "oil", "gas"])
    if d.duplicated(["api10", "mop"]).any():
        raise RuntimeError("Novi forecast: more than one row per (well, month)")
    out = {}
    for a, g in d.groupby("api10"):
        arr = {s: np.full(K, np.nan) for s in ("oil", "gas")}
        for s in ("oil", "gas"):
            arr[s][g["mop"].to_numpy() - 1] = pd.to_numeric(g[s], errors="coerce").to_numpy(float)
        out[a] = arr
    return out


def build(conn: Any, cb: dict[str, Any], rm: dict[int, dict[str, Any]], trn: pd.DataFrame, hs: pd.DataFrame, asof: dt.date,
          report: str, basin: str) -> dict[str, Any]:
    """Everything production.html needs + the F(k) curve, with identity checks against the scored values."""
    # F(k) for k = 1..K on the training cohort (same wells / predictions as the scored F(6), F(12))
    t_ids = list(trn["api10"])
    t_act = monthly_matrix(cb["prod"][cb["prod"]["api10"].isin(set(t_ids))], t_ids, asof=asof)
    t_box = box_months(trn, cb, rm)
    Fc = {s: hc.calendar_factor_curve(t_act[s], t_box[s]) for s in ("oil", "gas")}
    # holdout
    h_ids = list(hs["api10"])
    last = rep.last_full_month(rep._read(conn, rep._MONTHS_SQL))
    prod = rep.pull_production(conn, h_ids, last)
    h_act = monthly_matrix(prod, h_ids, drop_latest=True)
    h_box = box_months(hs, cb, rm)
    novi = pull_novi(conn, sorted(hs.loc[hs["tier"] == "direct", "api10"]), report, basin)
    checks = []
    for s in ("oil", "gas"):
        for k in hc.HORIZONS:
            # identity: monthly BOX x F(k) summed = the scored prediction; monthly actual summed = sql/43's actual
            pred = np.nansum(h_box[s][:, :k], axis=1) * Fc[s][0][k - 1]
            gap = np.nanmax(np.abs(pred / hs[f"box_{s}{k}"].to_numpy(float) - 1))
            ca = h_act[s][:, :k].sum(axis=1)
            sq = hs[f"actual_{s}{k}"].to_numpy(float)
            ok = np.isfinite(ca) & np.isfinite(sq) & (sq > 0)
            agree = float(np.mean(np.abs(ca[ok] / sq[ok] - 1) < 1e-3)) if ok.any() else float("nan")
            nv = np.array([np.nansum(novi[a][s][:k]) if a in novi and np.isfinite(novi[a][s][:k]).all() else np.nan for a in h_ids])
            nf = hs[f"novi_fcst_{s}{k}"].to_numpy(float)
            okn = np.isfinite(nv) & np.isfinite(nf) & (nf > 0)
            ngap = float(np.nanmax(np.abs(nv[okn] / nf[okn] - 1))) if okn.any() else float("nan")
            checks.append({"stream": s, "k": k, "box_monthly_x_F_vs_scored_max_rel": float(gap), "actual_sum_eq_sql43_share": agree,
                           "n_actual": int(ok.sum()), "novi_sum_vs_sql43_max_rel": ngap, "n_novi": int(okn.sum())})
    wells = []
    for i, r in enumerate(hs.itertuples()):
        lr = (float(r.lateral_ft) / float(r.novi_ll_ft)) if r.tier == "direct" and r.novi_ll_ft and float(r.novi_ll_ft) > 0 else None
        nv = novi.get(r.api10)
        wells.append({
            "api": r.api10, "name": r.well_name, "op": r.operator, "area": int(r.area_no), "tier": r.tier, "fp": str(r.first_production_date),
            "lat": round(float(r.lateral_ft)), "nll": None if not lr else round(float(r.novi_ll_ft)),
            "scen": (r.p_class if isinstance(r.p_class, str) else "(unscored)") + (" + infill" if r.p_infill is True or r.p_infill == 1 else ""), "f": round(float(r.f_oil), 3), "gor": None if not np.isfinite(r.gor_target) else round(float(r.gor_target)),
            "err": {f"{s}{k}": _r(getattr(r, f"box_err_{s}{k}"), 4) for s in ("oil", "gas") for k in hc.HORIZONS}
            | {f"n_{s}{k}": _r(getattr(r, f"novi_err_{s}{k}"), 4) for s in ("oil", "gas") for k in hc.HORIZONS},
            "a": {s: _arr(h_act[s][i]) for s in ("oil", "gas")},
            "b": {s: _arr(h_box[s][i]) for s in ("oil", "gas")},
            "n": None if nv is None or lr is None else {s: _arr(nv[s] * lr) for s in ("oil", "gas")},
        })
    return {"wells": wells, "F": {s: [_r(v, 5) for v in Fc[s][0]] for s in ("oil", "gas")}, "F_n": {s: [int(v) for v in Fc[s][1]] for s in ("oil", "gas")},
            "checks": checks, "actual_asof": str(last)}


def _r(v: Any, nd: int) -> float | None:
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def _arr(v: np.ndarray) -> list[float | None]:
    return [None if not np.isfinite(x) else round(float(x), 1) for x in v]


# ----------------------------------------------------------------------------
# Page
# ----------------------------------------------------------------------------


def render(data: dict[str, Any], summ: dict[str, Any]) -> str:
    meta = (f"Delaware WCA hindcast · Novi {summ['report']} · BOX rebuilt from wells first-producing before {summ['cliff']}, production through {summ['prod_asof']} · "
            f"actuals curated.production through {data['actual_asof']} (each well's newest month dropped) · blueox-boxfit @ {summ['engine_sha'][:7]}")
    blob = json.dumps({"wells": data["wells"], "F": data["F"], "Fn": data["F_n"]}, separators=(",", ":"))
    return _PAGE.replace("__META__", meta).replace("__DATA__", blob.replace("</", "<\\/"))


_PAGE = r"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>BOX hindcast production</title>
<style>
:root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--grid:#ebeae6;--actual:#9a9893;--box:#2a78d6;--novi:#eb6834;--sel:#eef4fc}
body{font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--surface);margin:0 16px 40px;max-width:1500px}
h1{font-size:19px;margin:16px 0 2px}.meta{color:var(--ink2);font-size:12px}
.wrap{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
.side{width:330px;max-width:100%;flex:0 0 auto}.main{flex:1 1 640px;min-width:0}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}
.seg button{border:1px solid #d6d5d0;background:#fff;padding:4px 10px;cursor:pointer;font:inherit;color:var(--ink2)}
.seg button:first-child{border-radius:6px 0 0 6px}.seg button:last-child{border-radius:0 6px 6px 0}.seg button+button{border-left:0}
.seg button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
input[type=search],select{font:inherit;padding:4px 8px;border:1px solid #d6d5d0;border-radius:6px;width:100%;box-sizing:border-box}
#list{height:620px;overflow:auto;border:1px solid #e5e4df;border-radius:6px;margin-top:6px;background:#fff}
#list div{padding:4px 8px;cursor:pointer;border-bottom:1px solid #f3f2ee;font-size:12px}
#list div:hover{background:#f6f5f2}#list div.on{background:var(--sel)}#list .grp{font-weight:600;color:var(--ink2);background:#f6f5f2;cursor:default}
.e{float:right;color:var(--ink2);font-variant-numeric:tabular-nums}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}
.card{border:1px solid #e5e4df;border-radius:8px;padding:8px 10px;background:#fff;position:relative}
.card h3{margin:2px 0 4px;font-size:13px}
.lg{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--ink2);margin:4px 0}
.lg i{display:inline-block;width:18px;height:3px;vertical-align:middle;margin-right:5px;border-radius:2px}
.tip{position:absolute;pointer-events:none;background:#fff;border:1px solid #d6d5d0;border-radius:6px;padding:6px 8px;font-size:12px;box-shadow:0 2px 6px rgba(0,0,0,.08);display:none;white-space:nowrap}
.tip b{font-variant-numeric:tabular-nums}
svg text{fill:var(--ink2);font-size:11px}
table{border-collapse:collapse;font-size:12px;margin:8px 0}th,td{border:1px solid #e5e4df;padding:3px 7px;text-align:right}th{background:#f6f5f2}td:first-child,th:first-child{text-align:left}
</style></head><body>
<h1>BOX step 6 — production: actual vs Novi 2025Q3 vs BOX</h1>
<div class=meta>__META__</div>
<div class=meta>Novi line = the matched stick's 2025Q3 forecast scaled to the drilled lateral (the per-ft basis sql/43 scores). BOX = area cohort-MEAN curve (D32) × lateral × ref_mult × scenario factor (gas at the local GOR level, D30/D46);
solid = BOX of record (calendar factor F(k) applied, D36 — what was scored at months 6 and 12), dashed = uptime-free curve. Averages: month k is the mean over the wells that have month k reported (n on hover; later months rest on fewer wells); the cumulative view cumulates those monthly means.</div>
<div class=bar>
 <span class=seg id=stream><button data-v=oil class=on>Oil (bbl)</button><button data-v=gas>Gas (mcf)</button></span>
 <span class=seg id=view><button data-v=month class=on>Monthly</button><button data-v=cum>Cumulative</button></span>
 <span class=seg id=tier><button data-v=direct class=on>Novi-matched</button><button data-v=all>All holdout (BOX only where Novi unmatched)</button></span>
</div>
<div class=wrap>
 <div class=side><input type=search id=q placeholder="Search well, API, operator…"><div id=list></div></div>
 <div class=main>
  <div class=charts><div class=card id=c1><h3 id=t1></h3><div class=lg id=lg1></div><svg id=s1 width=100% height=330></svg><div class=tip id=tip1></div></div></div>
  <div id=info></div>
 </div>
</div>
<script>
const D=__DATA__;const K=24;
const st={stream:'oil',view:'month',tier:'direct',sel:'bench'};
const fmt=v=>v==null||!isFinite(v)?'–':Math.round(v).toLocaleString();
const pct=v=>v==null?'–':(v>=0?'+':'')+(100*v).toFixed(1)+'%';
function wellsIn(){return D.wells.filter(w=>st.tier==='all'||(w.tier==='direct'&&w.n))}
function cum(a){let s=0,o=[];for(const v of a){if(v==null||s==null){s=null;o.push(null)}else{s+=v;o.push(s)}}return o}
function series(w,s,view){view=view||st.view; // per-well arrays (monthly or cumulative) for actual, novi, box (record = xF), box raw
  const a=w.a[s],b=w.b[s],n=w.n?w.n[s]:null;const F=D.F[s];
  const bc=cum(b),bf=bc.map((v,k)=>v==null||F[k]==null?null:v*F[k]);
  const bfm=bf.map((v,k)=>v==null?null:(k?(bf[k-1]==null?null:v-bf[k-1]):v));
  if(view==='cum')return{a:cum(a),n:n?cum(n):null,b:bf,r:bc};
  return{a:a,n:n,b:bfm,r:b};
}
function agg(ws,s){ // mean over wells with actual reported at month k (Novi + BOX on the same wells)
  const keys=['a','n','b','r'];const sum={},cnt=new Array(K).fill(0),ncnt=new Array(K).fill(0);keys.forEach(k=>sum[k]=new Array(K).fill(0));
  for(const w of ws){const x=series(w,s,'month');for(let k=0;k<K;k++){if(x.a[k]==null)continue;cnt[k]++;sum.a[k]+=x.a[k];sum.b[k]+=x.b[k]||0;sum.r[k]+=x.r[k]||0;
    if(x.n&&x.n[k]!=null){ncnt[k]++;sum.n[k]+=x.n[k]}}}
  const m=(k,c)=>sum[k].map((v,i)=>c[i]?v/c[i]:null);
  const novOk=st.tier==='direct'&&ncnt.some(c=>c);
  const c=v=>v&&st.view==='cum'?cum(v):v; // averages: cumulate the monthly means (a type-curve view; monotonic as the well count thins)
  return{a:c(m('a',cnt)),b:c(m('b',cnt)),r:c(m('r',cnt)),n:novOk?c(m('n',ncnt)):null,cnt:cnt,ncnt:ncnt};
}
function groups(){const ws=wellsIn();const q=document.getElementById('q').value.toLowerCase();
  const areas=[...new Set(ws.map(w=>w.area))].sort((a,b)=>a-b);const L=document.getElementById('list');L.innerHTML='';
  const add=(id,txt,cls,e)=>{const d=document.createElement('div');d.textContent=txt;if(cls)d.className=cls;if(id){d.dataset.id=id;if(id===st.sel)d.classList.add('on');d.onclick=()=>{st.sel=id;draw()}}
    if(e!=null){const sp=document.createElement('span');sp.className='e';sp.textContent=e;d.appendChild(sp)}L.appendChild(d)};
  add(null,'Averages','grp');add('bench',`WCA bench mean (${ws.length} wells)`);
  for(const a of areas){const n=ws.filter(w=>w.area===a).length;add('area:'+a,`Area ${a} mean (${n})`)}
  for(const a of areas){const aw=ws.filter(w=>w.area===a&&(!q||(w.name+' '+w.api+' '+w.op).toLowerCase().includes(q)));if(!aw.length)continue;
    add(null,`Area ${a}`,'grp');for(const w of aw)add('w:'+w.api,`${w.name}`,null,pct(w.err[st.stream+'6']))}
}
function pick(){const ws=wellsIn();const s=st.stream;
  if(st.sel==='bench')return{title:`WCA bench mean — ${ws.length} wells`,x:agg(ws,s),agg:true};
  if(st.sel.startsWith('area:')){const a=+st.sel.slice(5);const aw=ws.filter(w=>w.area===a);return{title:`Area ${a} mean — ${aw.length} wells`,x:agg(aw,s),agg:true}}
  const w=D.wells.find(w=>'w:'+w.api===st.sel);return{title:`${w.name} (${w.api})`,x:series(w,s),w:w};
}
function draw(){groups();const p=pick();const s=st.stream,u=s==='oil'?'bbl':'mcf';const x=p.x;
  document.getElementById('t1').textContent=`${p.title} — ${s} ${st.view==='cum'?'cumulative':'per month'}, ${u}`;
  const lg=[['actual','var(--actual)','Actual'],['b','var(--box)','BOX of record (× F(k))'],['r','var(--box)','BOX uptime-free','dash']];if(x.n)lg.splice(1,0,['n','var(--novi)','Novi 2025Q3 (scaled to drilled lateral)']);
  document.getElementById('lg1').innerHTML=lg.map(l=>`<span><i style="background:${l[1]};${l[3]?'background:repeating-linear-gradient(90deg,var(--box) 0 4px,transparent 4px 7px)':''}"></i>${l[2]}</span>`).join('');
  const svg=document.getElementById('s1');const W=svg.clientWidth||700,H=330,m={l:62,r:12,t:10,b:32};const iw=W-m.l-m.r,ih=H-m.t-m.b;
  const vals=[...x.a,...x.b,...x.r,...(x.n||[])].filter(v=>v!=null&&isFinite(v));const ymax=(Math.max(1,...vals))*1.08;
  const X=k=>m.l+(k+0.5)*iw/K,Y=v=>m.t+ih-v/ymax*ih;let g='';
  const ticks=5;for(let i=0;i<=ticks;i++){const v=ymax*i/ticks;g+=`<line x1=${m.l} x2=${W-m.r} y1=${Y(v)} y2=${Y(v)} stroke="var(--grid)"/><text x=${m.l-6} y=${Y(v)+4} text-anchor=end>${fmt(v)}</text>`}
  for(let k=0;k<K;k+=3)g+=`<text x=${X(k)} y=${H-12} text-anchor=middle>${k+1}</text>`;g+=`<text x=${m.l+iw/2} y=${H} text-anchor=middle>month on production</text>`;
  for(const kk of [6,12])g+=`<line x1=${X(kk-1)} x2=${X(kk-1)} y1=${m.t} y2=${m.t+ih} stroke="#d6d5d0" stroke-dasharray="2 3"/>`;
  const bw=Math.max(2,iw/K-4);
  if(st.view==='month'){x.a.forEach((v,k)=>{if(v!=null){const y=Y(Math.max(0,v));g+=`<rect x=${X(k)-bw/2} y=${y} width=${bw} height=${Math.max(0,m.t+ih-y)} rx=2 style="fill:var(--actual);opacity:.55"></rect>`}})}
  const line=(a,col,dash)=>{let d='',on=false;a.forEach((v,k)=>{if(v==null){on=false;return}d+=(on?'L':'M')+X(k)+' '+Y(v);on=true});return `<path d="${d}" style="fill:none;stroke:${col};stroke-width:2px;stroke-linejoin:round${dash?';stroke-dasharray:5 4':''}"/>`};
  if(st.view==='cum')g+=line(x.a,'var(--actual)')+x.a.map((v,k)=>v==null?'':`<circle cx=${X(k)} cy=${Y(v)} r=2.5 style="fill:var(--actual)"/>`).join('');
  g+=line(x.r,'var(--box)',true)+line(x.b,'var(--box)');if(x.n)g+=line(x.n,'var(--novi)');
  g+=`<line id="xh" y1="${m.t}" y2="${m.t+ih}" stroke="#8a8984" visibility="hidden"></line><rect x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="transparent" id="hit"></rect>`;
  svg.innerHTML=g;const tip=document.getElementById('tip1'),xh=svg.querySelector('#xh');
  svg.querySelector('#hit').onmousemove=e=>{const r=svg.getBoundingClientRect();const k=Math.max(0,Math.min(K-1,Math.floor((e.clientX-r.left-m.l)/iw*K)));
    xh.setAttribute('x1',X(k));xh.setAttribute('x2',X(k));xh.setAttribute('visibility','visible');
    let h=`Month ${k+1}${p.agg?` · n ${x.cnt[k]} wells`:''}<br>Actual <b>${fmt(x.a[k])}</b>`;if(x.n)h+=`<br>Novi <b>${fmt(x.n[k])}</b>`;
    h+=`<br>BOX (× F) <b>${fmt(x.b[k])}</b><br>BOX uptime-free <b>${fmt(x.r[k])}</b>`;if(st.view==='cum'&&x.a[k]!=null){h+=`<br>actual / BOX − 1: <b>${pct(x.a[k]/x.b[k]-1)}</b>`;if(x.n&&x.n[k])h+=`<br>actual / Novi − 1: <b>${pct(x.a[k]/x.n[k]-1)}</b>`}
    tip.innerHTML=h;tip.style.display='block';const cx=X(k)+18;tip.style.left=(cx+170>W?cx-190:cx)+'px';tip.style.top=(e.clientY-r.top+30)+'px'};
  svg.querySelector('#hit').onmouseleave=()=>{tip.style.display='none';xh.setAttribute('visibility','hidden')};
  const I=document.getElementById('info');
  if(p.w){const w=p.w;I.innerHTML=`<table><tr><th>well</th><th>operator</th><th>area</th><th>first prod</th><th>lateral ft</th><th>Novi stick ft</th><th>scenario (D42)</th><th>f_oil</th><th>local GOR × f, scf/bbl</th></tr>
   <tr><td>${w.name}</td><td>${w.op}</td><td>${w.area}</td><td>${w.fp}</td><td>${fmt(w.lat)}</td><td>${fmt(w.nll)}</td><td>${w.scen}</td><td>${w.f}</td><td>${fmt(w.gor)}</td></tr></table>
   <table><tr><th>error = actual / forecast − 1</th><th>oil cum-6</th><th>oil cum-12</th><th>gas cum-6</th><th>gas cum-12</th></tr>
   <tr><td>BOX</td><td>${pct(w.err.oil6)}</td><td>${pct(w.err.oil12)}</td><td>${pct(w.err.gas6)}</td><td>${pct(w.err.gas12)}</td></tr>
   <tr><td>Novi (per-ft, sql/43)</td><td>${pct(w.err.n_oil6)}</td><td>${pct(w.err.n_oil12)}</td><td>${pct(w.err.n_gas6)}</td><td>${pct(w.err.n_gas12)}</td></tr></table>`}
  else I.innerHTML=`<div class=meta>F(k) by month (${s}): ${D.F[s].map((v,k)=>`${k+1}: ${v==null?'–':v.toFixed(3)}`).join(' · ')}</div>`;
}
for(const id of ['stream','view','tier'])document.querySelectorAll('#'+id+' button').forEach(b=>b.onclick=()=>{st[id]=b.dataset.v;document.querySelectorAll('#'+id+' button').forEach(x=>x.classList.toggle('on',x===b));
  if(st.sel.startsWith('w:')&&st.tier==='direct'){const w=D.wells.find(w=>'w:'+w.api===st.sel);if(w&&w.tier!=='direct')st.sel='bench'}draw()});
document.getElementById('q').oninput=groups;window.onresize=draw;draw();
</script></body></html>"""
