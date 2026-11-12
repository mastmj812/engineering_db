"""BOX sticks: WCXY review cards, Delaware (read-only).

    python -m scripts.box_sticks_wcxy_cards --out docs/box_sticks/wcxy-cards-<date> --cache <phase 0 cache>

docs/box_sticks/wcxy-2026-11-12/FINDINGS.md: neither automated test reproduces Michael's read of "a distinct XY
landing above WCA_1" vs "one landing" where the WCXY-tagged wells sit 75-175 ft above the WCA_1 surface. These cards
are the labelled sample the rule will be fitted to.

One card per pad of WCXY-tagged wells (same operator, same 0.01-degree cell): a strike section through the pad,
orthogonal to its laterals, showing every evidence well whose midpoint lies within ALONG_FT along the laterals and
HALF_WIDTH_FT across. Depth is the evidence depth (survey lateral median TVD, else tvd_ft); planned-survey and
round-100 wells are never drawn. The cards are BLIND: no test result or separation number is printed on them
(key.csv holds those). Pads are sampled across the separation range and both states; the St Brides and Polaris pads
are included as the two calls Michael already made.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts import box_sticks_phase0 as p0
from scripts import box_sticks_wcxy as wx

FT = p0.FT_PER_M
ALONG_FT = 5280.0
HALF_WIDTH_FT = 7920.0
DEPTH_UP_FT, DEPTH_DOWN_FT = 450.0, 600.0
BINS = (-1e9, 50, 75, 100, 125, 150, 200, 1e9)
PER_BIN_STATE = 2
FORCED = ("ST BRIDES 76 3031", "POLARIS 7 70")
MIN_WCA1_NEAR = 4
SEED = 20261112
COLORS = {"WCXY": "#dc2626", "WCA_1": "#f59e0b", "WCA_2": "#16a34a", "WCB_1": "#7c3aed", "BS3_S": "#2563eb", "BS3_C": "#0891b2"}
OTHER = "#9ca3af"


def pads(x: pd.DataFrame) -> pd.DataFrame:
    x = x.assign(group=x["operator"].astype(str) + "|" + (x["midpoint_lat"] / 0.01).round().astype(str) + "|" + (x["midpoint_lon"] / 0.01).round().astype(str))
    g = x.groupby("group")
    p = g.agg(operator=("operator", "first"), county=("county", "first"), state=("state_code", "first"), wells=("api10", "size"),
              sep_median_ft=("above_wca1_ft", "median"), sep_min_ft=("above_wca1_ft", "min"), sep_max_ft=("above_wca1_ft", "max"),
              wca1_near=("wca1_within_1mi", "median"), name=("well_name", "first"),
              distinct_pct=("landing", lambda s: 100 * float((s == "distinct_upper").mean())),
              single_pct=("landing", lambda s: 100 * float((s == "single_landing").mean()))).reset_index()
    return p, x


def sample(p: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    forced = p[p["name"].str.upper().str.contains("|".join(FORCED), regex=True)]
    ok = p[(p["wells"] >= 2) & (p["wca1_near"] >= MIN_WCA1_NEAR) & p["sep_median_ft"].notna() & ~p["group"].isin(forced["group"])]
    ok = ok.assign(bin=pd.cut(ok["sep_median_ft"], BINS, labels=False))
    picks = [forced]
    for _, g in ok.groupby(["bin", "state"]):
        picks.append(g.iloc[rng.permutation(len(g))[:PER_BIN_STATE]])
    s = pd.concat(picks, ignore_index=True)
    s = s.iloc[rng.permutation(len(s))].reset_index(drop=True)     # shuffled: card order carries no information
    s.insert(0, "card", np.arange(1, len(s) + 1))
    return s


def _stick(pts: list) -> np.ndarray:
    return np.asarray(pts, float) if pts else np.zeros((0, 2))


def card(n: int, pad: pd.Series, subj: pd.DataFrame, bw: pd.DataFrame, out: Path) -> str:
    c = subj[["x", "y"]].to_numpy(float).mean(axis=0)
    dirs = []
    for pts in subj["pts"]:
        s = _stick(pts)
        if len(s) >= 2:
            v = s[-1] - s[0]
            v = v / (np.hypot(*v) or 1.0)
            dirs.append(v if not dirs or np.dot(v, dirs[0]) >= 0 else -v)
    u = np.mean(dirs, axis=0) if dirs else np.array([0.0, 1.0])
    u = u / (np.hypot(*u) or 1.0)
    nrm = np.array([u[1], -u[0]])
    if (abs(nrm[0]) >= abs(nrm[1]) and nrm[0] < 0) or (abs(nrm[0]) < abs(nrm[1]) and nrm[1] < 0):
        nrm = -nrm                                               # read W -> E, or S -> N for E-W laterals
    d = bw[["x", "y"]].to_numpy(float) - c
    along, off = d @ u * FT, d @ nrm * FT
    z0 = float(subj["depth_ft"].median())
    m = (np.abs(along) <= ALONG_FT) & (np.abs(off) <= HALF_WIDTH_FT) & bw["depth_ft"].between(z0 - DEPTH_UP_FT, z0 + DEPTH_DOWN_FT).to_numpy()
    v = bw[m].assign(off=off[m])
    is_subj = v["api10"].isin(subj["api10"]).to_numpy()

    fig, (ax, mp) = plt.subplots(1, 2, figsize=(15, 6.2), gridspec_kw={"width_ratios": [2.6, 1]})
    for tag, g in v[~is_subj].groupby("live"):
        ax.scatter(g["off"], g["depth_ft"], s=46, c=COLORS.get(tag, OTHER), edgecolors="white", linewidths=0.6,
                   label=f"{tag} ({len(g)})" if tag in COLORS else None, zorder=2)
    oth = v[~is_subj & ~v["live"].isin(list(COLORS))]
    if len(oth):
        ax.scatter([], [], s=46, c=OTHER, label=f"other benches ({len(oth)})")
    sv = v[is_subj]
    ax.scatter(sv["off"], sv["depth_ft"], s=120, c=COLORS["WCXY"], edgecolors="black", linewidths=1.6, marker="D",
               label=f"this pad, tagged WCXY ({len(sv)})", zorder=3)
    for r in sv.itertuples():
        ax.annotate(str(r.well_name).split()[-1], (r.off, r.depth_ft), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=7)
    ax.set_ylim(z0 + DEPTH_DOWN_FT, z0 - DEPTH_UP_FT)
    ax.set_xlim(-HALF_WIDTH_FT, HALF_WIDTH_FT)
    ax.grid(True, color="#e5e7eb", lw=0.6)
    ax.set_axisbelow(True)
    we = abs(nrm[0]) >= abs(nrm[1])
    ax.set_xlabel(f"offset across the laterals, ft ({'W -> E' if we else 'S -> N'})")
    ax.set_ylabel("landing TVD, ft")
    ax.legend(fontsize=8, loc="lower right", ncol=2)
    ax.set_title(f"Card {n}: {pad['name']} pad, {pad['operator']}, {pad['county']} County "
                 f"({'TX' if int(pad['state']) == 42 else 'NM'}): wells within 1 mi along the laterals", fontsize=10)

    for r in v.itertuples():
        s = (_stick(r.pts) - c) * FT
        if len(s) >= 2:
            sub = r.api10 in set(subj["api10"])
            mp.plot(s[:, 0], s[:, 1], color=COLORS.get(r.live, OTHER), lw=2.2 if sub else 0.9, alpha=1.0 if sub else 0.7, zorder=3 if sub else 2)
    e = nrm * HALF_WIDTH_FT
    mp.plot([-e[0], e[0]], [-e[1], e[1]], "--", color="#111827", lw=0.9)
    mp.set_aspect("equal")
    mp.set_title("plan view (north up; dashed = section line)", fontsize=9)
    mp.set_xticks([])
    mp.set_yticks([])
    f = out / f"card_{n:02d}.png"
    fig.savefig(f, dpi=95, bbox_inches="tight")
    plt.close(fig)
    return f.name


_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>WCXY review cards</title><style>
body{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:1180px;margin:24px auto;padding:0 16px;color:#111827}
.card{border:1px solid #d1d5db;border-radius:8px;padding:12px;margin:18px 0}.card img{width:100%}
label{margin-right:18px;font-size:15px}input[type=text]{width:420px;margin-left:8px}
#bar{position:sticky;top:0;background:#fff;padding:10px 0;border-bottom:1px solid #d1d5db;z-index:5}
button{padding:6px 14px;font-size:14px}</style></head><body>
<h1>WCXY review cards</h1>
<p>For each pad: do the red diamonds (this pad's WCXY-tagged wells) form a <b>distinct landing above</b> the Wolfcamp A
development around them, or are they part of <b>one landing</b>? Depths are survey lateral median TVD; planned-survey and
permit-depth wells are not drawn. No dip correction. The cards are in random order and carry no test results.</p>
<div id="bar"><span id="count"></span> &nbsp; <button onclick="dl()">Download verdicts.csv</button></div>
__CARDS__
<script>
const N=__N__;
function load(){try{return JSON.parse(localStorage.getItem('wcxy_cards')||'{}')}catch(e){return {}}}
function save(s){try{localStorage.setItem('wcxy_cards',JSON.stringify(s))}catch(e){}}
let S=load();
function paint(){let d=0;for(let i=1;i<=N;i++){const v=S[i]||{};document.querySelectorAll('input[name=v'+i+']').forEach(r=>{r.checked=(r.value===v.verdict)});
const t=document.getElementById('n'+i);if(t&&document.activeElement!==t)t.value=v.note||'';if(v.verdict)d++;}
document.getElementById('count').textContent=d+' of '+N+' cards marked';}
function setv(i,x){S[i]=S[i]||{};S[i].verdict=x;save(S);paint();}
function setn(i,x){S[i]=S[i]||{};S[i].note=x;save(S);}
function dl(){let rows=['card,verdict,note'];for(let i=1;i<=N;i++){const v=S[i]||{};rows.push(i+','+(v.verdict||'')+',"'+(v.note||'').replace(/"/g,'""')+'"');}
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([rows.join('\\n')],{type:'text/csv'}));a.download='verdicts.csv';a.click();}
paint();
</script></body></html>"""


def page(cards: list[tuple[int, str, str]]) -> str:
    parts = []
    for n, png, title in cards:
        radios = "".join(f'<label><input type="radio" name="v{n}" value="{v}" onchange="setv({n},\'{v}\')"> {lab}</label>'
                         for v, lab in (("XY", "Distinct XY landing"), ("ONE", "One landing (upper WCA)"), ("UNSURE", "Can't tell")))
        parts.append(f'<div class="card"><h3>Card {n}: {html.escape(title)}</h3><img src="{png}" alt="card {n}"><p>{radios}'
                     f'<input type="text" id="n{n}" placeholder="note (optional)" oninput="setn({n},this.value)"></p></div>')
    return _PAGE.replace("__CARDS__", "\n".join(parts)).replace("__N__", str(len(cards)))


def run(out: Path, cache: Path | None) -> pd.DataFrame:
    out.mkdir(parents=True, exist_ok=True)
    d = p0.pull(cache)
    w = p0.evidence(d["wells"], d["rule"])
    bw = w[w["basin"] == "delaware"].reset_index(drop=True)
    x = wx.classify(bw)
    x = x.join(wx.landings(bw, x))
    p, x = pads(x)
    s = sample(p)
    cards = []
    for r in s.itertuples():
        subj = x[x["group"] == r.group]
        pad = pd.Series(r._asdict())
        cards.append((r.card, card(r.card, pad, subj, bw, out), f"{r.name} pad, {r.operator}, {r.county}"))
    (out / "index.html").write_text(page(cards), encoding="utf-8")
    s.drop(columns=["group"]).to_csv(out / "key.csv", index=False)
    print(s[["card", "name", "county", "state", "wells", "sep_median_ft", "distinct_pct"]].to_string(index=False))
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
