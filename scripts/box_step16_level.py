"""BOX step 16 level work on the r2 selection of record (D121) — POST-LOOK, read-only, on the 16c tuning views.

    python -m scripts.box_step16_level runs/step16c docs/box/step16-level-2026-10-23

Applies the PDP-proximity factor exactly as production does (box.prox_pud.decide on docs/box/prox-2026-10-19 config_children +
haircut_table_candidate; precedent ignored so every multi-parent backtest well is scored with its factor; oil only) and the D57
walk-forward haircut (per bench, and pooled over the provisional family), then reports oil bias overall, on thin-control wells
(< 3 local wells within 3 mi) and on the far-with-local stratum, and per cutoff. Not a pre-registered score."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import analog as an
from box import prox_pud as pp
from box import step16 as s16
from box import step16c as c16

R = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
ALL = ("WCA", "BS2_S", "WCXY_WCA1", "WCB_1", "WCC", *c16.PROVISIONAL)
cfg = pd.read_csv("docs/box/prox-2026-10-19/config_children.csv.gz", dtype={"api10": str}).set_index("api10")
hair = pp.haircut_lookup(pd.read_csv("docs/box/prox-2026-10-19/haircut_table_candidate.csv"))


class _Any(dict):
    def get(self, k, d=None):  # type: ignore[override]  # precedent ignored in the backtest: score every multi-parent well with its factor
        return {"multi": 10**9, "package": 10**9}


dec = pp.decide_all(cfg.reset_index(), hair, _Any())
dec.index = cfg.index
FACTOR = dec["factor"].where(dec["outcome"] == "haircut", 1.0)
OUTCOME = dec["outcome"]

BASE = "box_v2s_r2"
views = {g: c16.load_views(R / g, g) for g in ALL}
for g, v in views.items():
    f = v["api10"].map(FACTOR).fillna(1.0).to_numpy(float)
    v["prox_factor"] = f
    v["prox_outcome"] = v["api10"].map(OUTCOME).fillna("not_in_config")
    for k in ac.HORIZONS:
        for s in ac.STREAMS:
            col = f"pred_{BASE}_{s}{k}"
            if col in v:
                v[f"pred_r2p_{s}{k}"] = v[col] * (f if s == "oil" else 1.0)
                v[f"r2p_err_{s}{k}"] = v[f"actual_{s}{k}"] / v[f"pred_r2p_{s}{k}"] - 1.0


def per_cutoff_cells(v: pd.DataFrame, variants) -> pd.DataFrame:
    return pd.concat([ac.score_fold(x, c, variants) for c, x in v.groupby("cutoff")], ignore_index=True)


def walk_forward(v: pd.DataFrame, base: str, cells: pd.DataFrame, out_name: str) -> None:
    """D57 on `base`: prediction x (1 + mean package bias at the same stream / horizon over >= 2 earlier cutoffs, >= 30 pkgs)."""
    for s in ac.STREAMS:
        for k in ac.HORIZONS:
            col = f"pred_{base}_{s}{k}"
            if col not in v:
                continue
            hist = cells[(cells.variant == base) & (cells.stream == s) & (cells.horizon == k) & (cells.n_packages >= ac.MIN_PACKAGES)]
            hb = dict(zip(hist["cutoff"], hist["pkg_bias"], strict=True))
            h = v["cutoff"].astype(str).map(lambda c, hb=hb: an.walk_forward(hb, c))
            v[f"pred_{out_name}_{s}{k}"] = v[col] * (1.0 + h.astype(float))


# per-bench walk-forward on r2 and r2p
for g, v in views.items():
    cells = per_cutoff_cells(v, (BASE, "r2p"))
    walk_forward(v, BASE, cells, "r2_wf")
    walk_forward(v, "r2p", cells, "r2p_wf")
# provisional-family pooled walk-forward on r2p
pv = pd.concat([views[g] for g in c16.PROVISIONAL], ignore_index=True)
pcells = per_cutoff_cells(pv, ("r2p",))
for g in c16.PROVISIONAL:
    walk_forward(views[g], "r2p", pcells, "r2p_wfpool")

VARS = ("box_v2", "box_v2_wf", "box_v2s", BASE, "r2p", "r2_wf", "r2p_wf", "r2p_wfpool")
rows, cells_all = [], []
for g, v in views.items():
    pc = c16.pooled_cells(v, VARS).assign(group=g)
    cells_all.append(pc)
    thin = pd.to_numeric(v["n_local"], errors="coerce") < s16.LOCAL_MIN_WELLS
    fwl = s16.stratum_mask(v)
    for var in VARS:
        col = f"pred_{var}_oil12"
        if col not in v:
            continue
        r = {"group": g, "tier": "provisional" if g in c16.PROVISIONAL else "validated", "variant": var}
        for k in (12, 24):
            a, p = v[f"actual_oil{k}"].astype(float), v[f"pred_{var}_oil{k}"].astype(float)
            ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
            for nm, m in (("all", ok), ("thin", ok & thin), ("fwl", ok & fwl)):
                r[f"oil{k}_{nm}"] = a[m].sum() / p[m].sum() - 1 if m.any() else np.nan
                if k == 12:
                    r[f"n_{nm}"] = int(m.sum())
        j = pc[(pc.variant == var) & pc.verdict.isin(["PASS", "FAIL"])]
        r.update({"judged": len(j), "fails": int((j.verdict == "FAIL").sum()), "med_abs": j.pkg_bias.abs().median()})
        rows.append(r)
res = pd.DataFrame(rows)
res.to_csv(OUT / "level_by_group.csv", index=False)
pd.concat(cells_all, ignore_index=True).to_csv(OUT / "level_pooled_cells.csv", index=False)
# pooled over tiers (well-level)
tot = []
for tier, gs in (("provisional", c16.PROVISIONAL), ("validated", ("WCA", "BS2_S", "WCXY_WCA1", "WCB_1", "WCC"))):
    V = pd.concat([views[g] for g in gs], ignore_index=True)
    thin = pd.to_numeric(V["n_local"], errors="coerce") < s16.LOCAL_MIN_WELLS
    fwl = s16.stratum_mask(V)
    for var in VARS:
        if f"pred_{var}_oil12" not in V:
            continue
        r = {"tier": tier, "variant": var}
        for k in (12, 24):
            a, p = V[f"actual_oil{k}"].astype(float), V[f"pred_{var}_oil{k}"].astype(float)
            ok = np.isfinite(a) & np.isfinite(p) & (p > 0)
            for nm, m in (("all", ok), ("thin", ok & thin), ("fwl", ok & fwl)):
                r[f"oil{k}_{nm}"] = a[m].sum() / p[m].sum() - 1 if m.any() else np.nan
                r[f"n{k}_{nm}"] = int(m.sum())
        tot.append(r)
tot = pd.DataFrame(tot)
tot.to_csv(OUT / "level_by_tier.csv", index=False)
pd.set_option("display.width", 250)
print(tot[["tier", "variant", "oil12_all", "oil12_thin", "oil12_fwl", "oil24_all", "oil24_thin", "n12_all", "n12_thin", "n12_fwl"]].round(3).to_string(index=False))
print(res[res.variant.isin([BASE, "r2p", "r2p_wf", "r2p_wfpool", "box_v2_wf", "box_v2"])][["group", "variant", "oil12_all", "oil24_all", "oil12_thin", "judged", "fails", "med_abs"]].round(3).to_string(index=False))
V = pd.concat(views.values(), ignore_index=True)
print("prox outcome on scored wells:", V["prox_outcome"].value_counts().to_dict(), " mean oil factor", round(V["prox_factor"].mean(), 4))

print("\n=== SAME WELLS (every variant finite), oil, well-level")
for tier, gs in (("provisional", c16.PROVISIONAL), ("validated", ("WCA", "BS2_S", "WCXY_WCA1", "WCB_1", "WCC"))):
    V = pd.concat([views[g] for g in gs], ignore_index=True)
    vs = ["box_v2s", BASE, "r2p", "r2p_wf"] + (["r2p_wfpool"] if tier == "provisional" else [])
    for k in (12, 24):
        ok = np.isfinite(V[f"actual_oil{k}"])
        for var in vs:
            ok &= np.isfinite(V[f"pred_{var}_oil{k}"]) & (V[f"pred_{var}_oil{k}"] > 0)
        thin = pd.to_numeric(V["n_local"], errors="coerce") < s16.LOCAL_MIN_WELLS
        line = [f"{tier} oil{k} n={int(ok.sum())} (thin {int((ok & thin).sum())}):"]
        for var in vs:
            a, p = V.loc[ok, f"actual_oil{k}"], V.loc[ok, f"pred_{var}_oil{k}"]
            at, pt = V.loc[ok & thin, f"actual_oil{k}"], V.loc[ok & thin, f"pred_{var}_oil{k}"]
            line.append(f"{var} {a.sum() / p.sum() - 1:+.3f} (thin {at.sum() / pt.sum() - 1:+.3f})")
        print("  ".join(line))
print("\n=== r2p by cutoff, pooled package bias oil-12 (provisional pooled / validated pooled)")
for tier, gs in (("provisional", c16.PROVISIONAL), ("validated", ("WCA", "BS2_S", "WCXY_WCA1", "WCB_1", "WCC"))):
    V = pd.concat([views[g] for g in gs], ignore_index=True)
    c = per_cutoff_cells(V, ("r2p",))
    c = c[(c.stream == "oil") & (c.horizon == 12)][["cutoff", "n_packages", "pkg_bias"]]
    print(tier, c.round(3).to_string(index=False))
