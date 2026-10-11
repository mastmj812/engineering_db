"""BOX step 5b, gate follow-up — (#2) where the curves' early-cum overstatement comes from, (#1) whether
the within-area GOR effect on oil is real (read-only).

    python -m scripts.box_tc_gate5b_dig [out_dir]      (default docs/box/step5b-2026-10-10/dig)

Reads the 5b deliverable (well_fits / members CSVs) and curated.production (READ ONLY, session pooler).
#2: each cohort well's own forecast laid on calendar months from its first report vs its actual monthly
volumes — by month, by cum window, by uptime class (producing_days), vintage, area, and a step-6-like
transfer (factor from wells first-producing <= 2022 applied to 2023-24 wells).
#1: oil vs OWN 12-mo GOR (mechanically coupled: GOR = gas / oil) vs the NEIGHBOURS' GOR (15 nearest
other cohort wells, no mechanical link), within area, with controls, and a blocked held-out test.
Writes dig.json + dig.png.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from boxfit.eur import DAYS_PER_YEAR
from boxfit.ramp_arps import build_ramp_arps_rate
from scipy.spatial import cKDTree

from box import tc_curve as tc
from box import tc_curve_report as rep
from etl.db import get_connection

D = "docs/box/step5b-2026-10-10"
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else f"{D}/dig"
OUT = f"{OUT_DIR}/dig.json"
DPM = DAYS_PER_YEAR / 12
ASOF = dt.date(2026, 7, 1)
wf = pd.read_csv(f"{D}/well_fits_WCA.csv", dtype={"api10": str}).set_index("api10")
mem = pd.read_csv(f"{D}/members_WCA.csv", dtype={"api10": str})
mem = mem[mem.fit_oil].copy()
wells = pd.read_csv("docs/box/step1-2026-10-06/wells_final_WCA.csv", dtype={"api10": str})[["api10", "tvd_ft", "mid_lon", "mid_lat"]]
mem = mem.merge(wells, on="api10", how="left")
with get_connection() as conn:
    prod = rep.pull_production(conn, list(mem.api10), ASOF)
prod["prod_date"] = pd.to_datetime(prod["prod_date"]).dt.date
res = {}

# ---------------- #2: forecast vs actual by calendar month from first report ----------------
K = 120
A = np.full((len(mem), K), np.nan); F = np.full((len(mem), K), np.nan); PD = np.full((len(mem), K), np.nan)
G_A = np.full((len(mem), K), np.nan); G_F = np.full((len(mem), K), np.nan)
pin = []
g = dict(tuple(prod.groupby("api10")))
for i, r in enumerate(mem.itertuples()):
    p = g.get(r.api10)
    if p is None:
        pin.append(False); continue
    p = p.sort_values("prod_date"); d0 = p.prod_date.iloc[0]
    idx = np.array([(x.year - d0.year) * 12 + x.month - d0.month for x in p.prod_date])
    n = (ASOF.year - d0.year) * 12 + ASOF.month - d0.month + 1
    n = min(n, K)
    for s, col, AA, FF in (("oil", "oil_bbl", A, F), ("gas", "gas_mcf", G_A, G_F)):
        q = {k: wf.at[r.api10, f"{s}_{k}"] for k in ("qo", "qi", "Di", "b", "Df", "peak_index_months", "onset_index_months")}
        if pd.isna(q["qi"]):
            continue
        on = 0 if pd.isna(q["onset_index_months"]) else int(q["onset_index_months"])
        rr = build_ramp_arps_rate(n_months=K + 2, qo=q["qo"] if pd.notna(q["qo"]) else q["qi"], qi=q["qi"],
                                  peak_index=0 if pd.isna(q["peak_index_months"]) else int(q["peak_index_months"]), Di=q["Di"], b=q["b"], Df=q["Df"])
        rr = np.array([0.0] * on + list(rr))[: K + 1]
        vol = (rr[:-1] + rr[1:]) / 2 * DPM
        vol[:on] = 0.0
        a = np.zeros(K); m = idx < K
        a[idx[m]] = pd.to_numeric(p[col], errors="coerce").fillna(0).to_numpy()[m]
        AA[i, :n] = a[:n]; FF[i, :n] = vol[:n]
    pdy = np.full(K, np.nan); m = idx < K
    pdy[idx[m]] = pd.to_numeric(p["producing_days"], errors="coerce").to_numpy()[m]
    PD[i, :n] = pdy[:n]
    pin.append(abs(wf.at[r.api10, "oil_Di"] - 4.0) < 1e-3)
pin = np.array(pin)
lat = mem.lateral_ft.to_numpy()

def cumratio(AA, FF, Kc, mask=None):
    ok = ~np.isnan(AA[:, Kc - 1])
    if mask is not None: ok &= mask
    return float(np.nansum(AA[ok, :Kc]) / np.nansum(FF[ok, :Kc])), int(ok.sum())

res["cum_ratio_actual_over_forecast"] = {s: {str(k): cumratio(AA, FF, k) for k in (1, 3, 6, 12, 24, 36, 60, 84)}
                                       for s, AA, FF in (("oil", A, F), ("gas", G_A, G_F))}
res["monthly_ratio_oil"] = {str(k): float(np.nansum(A[:, k]) / np.nansum(F[:, k][~np.isnan(A[:, k])])) for k in list(range(13)) + [18, 24, 36, 48, 60, 84]}
# excluding the first reported month (partial start)
ok12 = ~np.isnan(A[:, 11])
res["cum12_ex_month0"] = float(np.nansum(A[ok12, 1:12]) / np.nansum(F[ok12, 1:12]))
# producing days: how much is downtime?
pdn = PD[ok12, :12]
res["producing_days_nonnull_share_m0_11"] = float(np.mean(~np.isnan(pdn)))
full = (PD >= 28) & ~np.isnan(A)
part = (PD < 28) & ~np.isnan(A)
sel = np.zeros_like(full); sel[:, 1:12] = True
res["ratio_months1_11_full_uptime(pd>=28)"] = float(np.nansum(np.where(full & sel, A, 0)) / np.nansum(np.where(full & sel, F, 0)))
res["ratio_months1_11_partial(pd<28)"] = float(np.nansum(np.where(part & sel, A, 0)) / np.nansum(np.where(part & sel, F, 0)))
res["share_months1_11_partial"] = float((part & sel).sum() / ((full | part) & sel).sum())
res["calday_uptime_months1_11_mean_pd_over_days"] = float(np.nanmean(np.where(sel & ~np.isnan(A), PD, np.nan)) / DPM)
res["cum12_ratio_pinned_vs_not"] = {"pinned": cumratio(A, F, 12, pin), "not_pinned": cumratio(A, F, 12, ~pin)}
fpy = np.array([int(str(x)[:4]) for x in mem.first_production_date])
res["cum12_ratio_by_vintage"] = {str(y): cumratio(A, F, 12, fpy == y) for y in range(2016, 2026)}
res["cum60_ratio_by_vintage"] = {str(y): cumratio(A, F, 60, fpy == y) for y in range(2016, 2022)}
# per area spread of cum-12 ratio (would one basin factor do?)
ar = mem.area_no.to_numpy()
res["cum12_ratio_by_area"] = by_area = {int(a): cumratio(A, F, 12, ar == a)[0] for a in np.unique(ar)}
v = np.array(list(by_area.values())); res["cum12_ratio_area_spread"] = {"median": float(np.median(v)), "p10": float(np.percentile(v, 10)), "p90": float(np.percentile(v, 90))}
# step-6-like transfer: factor from wells first prod <= 2022 applied to 2023-2024 wells
old, new = fpy <= 2022, (fpy >= 2023) & (fpy <= 2024)
for k in (6, 12):
    f_old = cumratio(A, F, k, old)[0]; f_new = cumratio(A, F, k, new)[0]
    res[f"transfer_cum{k}"] = {"factor_fit_le2022": f_old, "ratio_2023_24": f_new, "residual_bias_after_factor": f_new / f_old - 1}
# ---------------- #1: GOR vs oil, mechanical vs real ----------------
c = mem[(mem.gor12 > 0) & (mem.oil12_kft > 0)].copy()
from box import edge_gap as eg

tr = eg._transformer(); x, y = tr.transform(c.mid_lon.to_numpy(float), c.mid_lat.to_numpy(float))
c["x"], c["y"] = np.asarray(x) * eg._M_TO_FT, np.asarray(y) * eg._M_TO_FT
xy = c[["x", "y"]].to_numpy(); _, j = cKDTree(xy).query(xy, k=16); jj = j[:, 1:]
gor = c.gor12.to_numpy(); oil = c.oil12_kft.to_numpy()
c["local_gor"] = np.median(gor[jj], axis=1); c["local_oil"] = np.median(oil[jj], axis=1)
c["gas12_kft"] = c.gor12 * c.oil12_kft / 1000
c["lo"], c["lgo"], c["llg"], c["lga"] = np.log(c.oil12_kft), np.log(c.gor12), np.log(c.local_gor), np.log(c.gas12_kft)
c["fpy"] = [int(str(x)[:4]) for x in c.first_production_date]
ws = tc.within_slope
res["gor1"] = {
    "ln_oil12_on_own_lnGOR": ws(c.lo, c.lgo, c.area_no),
    "ln_oil12_on_local_lnGOR": ws(c.lo, c.llg, c.area_no),
    "ln_gas12_on_local_lnGOR": ws(c.lga, c.llg, c.area_no),
    "ln_oil_eur_on_local_lnGOR": ws(np.log(c.oil_eur_kft), c.llg, c.area_no),
    "local_lnGOR_iqr_within_area": float(c.groupby("area_no").llg.apply(lambda s: s.quantile(.75) - s.quantile(.25)).median()),
}
# controls: area FE + fp-year FE + TVD + ln lateral + top operators FE
def fe_ols(df, ycol, xcols, fes):
    X = df[xcols].astype(float).copy()
    for f in fes:
        X = X.join(pd.get_dummies(df[f].astype(str), prefix=f, drop_first=True).astype(float))
    X.insert(0, "c", 1.0); ok = X.notna().all(1) & df[ycol].notna()
    b, *_ = np.linalg.lstsq(X[ok].to_numpy(), df.loc[ok, ycol].to_numpy(), rcond=None)
    r = df.loc[ok, ycol].to_numpy() - X[ok].to_numpy() @ b
    XtX = np.linalg.pinv(X[ok].to_numpy().T @ X[ok].to_numpy()); se = np.sqrt(np.diag(XtX) * (r @ r) / (ok.sum() - X.shape[1]))
    return {k: (float(b[i]), float(se[i])) for i, k in enumerate(X.columns) if k in xcols} | {"n": int(ok.sum())}
top = c.operator.value_counts().index[:25]
c["op"] = np.where(c.operator.isin(top), c.operator, "other")
c["lnlat"] = np.log(c.lateral_ft)
res["gor1_controls"] = {
    "area": fe_ols(c, "lo", ["llg"], ["area_no"]),
    "area+year": fe_ols(c, "lo", ["llg"], ["area_no", "fpy"]),
    "area+year+tvd+lat": fe_ols(c, "lo", ["llg", "tvd_ft", "lnlat"], ["area_no", "fpy"]),
    "area+year+tvd+lat+operator": fe_ols(c, "lo", ["llg", "tvd_ft", "lnlat"], ["area_no", "fpy", "op"]),
}
# held-out prediction of ln oil12/kft: 5 folds on 3-mi blocks
blk = (np.floor(c.x / 15840).astype(int) * 7919 + np.floor(c.y / 15840).astype(int) * 104729) % 5
c["fold"] = blk
preds = {k: np.full(len(c), np.nan) for k in ("area", "area+localGOR", "local_oil", "local_oil+localGOR")}
for f in range(5):
    trn, tst = c.fold != f, c.fold == f
    T = c[trn]
    am = T.groupby("area_no").lo.mean(); ag = T.groupby("area_no").llg.mean()
    beta = ws(T.lo, T.llg, T.area_no)["slope"]
    Tt = c[tst]
    pa = Tt.area_no.map(am).to_numpy()
    preds["area"][tst.to_numpy()] = pa
    preds["area+localGOR"][tst.to_numpy()] = pa + beta * (Tt.llg - Tt.area_no.map(ag)).to_numpy()
    # local medians from TRAINING wells only
    tr_xy = T[["x", "y"]].to_numpy(); _, jt = cKDTree(tr_xy).query(Tt[["x", "y"]].to_numpy(), k=15)
    lo_loc = np.log(np.median(T.oil12_kft.to_numpy()[jt], axis=1)); lg_loc = np.log(np.median(T.gor12.to_numpy()[jt], axis=1))
    preds["local_oil"][tst.to_numpy()] = lo_loc
    # residual GOR effect on top of local oil, slope from training
    _, jt2 = cKDTree(tr_xy).query(tr_xy, k=16)
    tlo = np.log(np.median(T.oil12_kft.to_numpy()[jt2[:, 1:]], axis=1)); tlg = np.log(np.median(T.gor12.to_numpy()[jt2[:, 1:]], axis=1))
    Xb = np.column_stack([np.ones(len(T)), tlo, tlg]); bb, *_ = np.linalg.lstsq(Xb, T.lo.to_numpy(), rcond=None)
    preds["local_oil+localGOR"][tst.to_numpy()] = bb[0] + bb[1] * lo_loc + bb[2] * lg_loc
    res.setdefault("local_oil+GOR_coefs", []).append([float(v) for v in bb])
yv = c.lo.to_numpy(); sst = ((yv - yv.mean()) ** 2).sum()
res["gor1_heldout_r2_ln_oil12"] = {k: float(1 - ((yv - p) ** 2).sum() / sst) for k, p in preds.items()}
res["n_gor1"] = len(c)
Path(OUT).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
# figure: (left) monthly actual / forecast, oil, with the uptime split; (right) oil vs own vs neighbours' GOR, within area
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, ax = plt.subplots(1, 2, figsize=(13, 4.4))
ks = np.arange(0, 61)
mr = [np.nansum(A[:, k]) / np.nansum(F[:, k][~np.isnan(A[:, k])]) for k in ks]
fr = [np.nansum(np.where(full[:, k], A[:, k], 0)) / max(np.nansum(np.where(full[:, k], F[:, k], 0)), 1e-9) for k in ks]
ax[0].plot(ks, mr, "-", color="#dc2626", lw=2, label="all months (calendar-day actuals)")
ax[0].plot(ks, fr, "-", color="#2563eb", lw=1.4, label="months with producing_days >= 28")
ax[0].axhline(1, color="#6b7280", lw=0.8)
ax[0].set_ylim(0.6, 1.15); ax[0].set_xlabel("calendar month from first report"); ax[0].set_ylabel("sum actual / sum own forecast (oil)")
ax[0].set_title(f"#2 per-well forecast vs actual, {len(mem):,} cohort wells", fontsize=10); ax[0].legend(fontsize=8); ax[0].grid(alpha=0.3)
dm = lambda col: c[col] - c.groupby("area_no")[col].transform("mean")
for col, colr, lab in (("lgo", "#9ca3af", "own GOR12 (GOR = gas/oil)"), ("llg", "#dc2626", "neighbours' GOR12 (15 nearest)")):
    xb = dm(col); yb = dm("lo"); bins = pd.qcut(xb, 20, duplicates="drop")
    gb = pd.DataFrame({"x": xb, "y": yb, "b": bins}).groupby("b", observed=True).mean()
    ax[1].plot(gb.x, gb.y, "o-", color=colr, ms=4, label=lab)
ax[1].axhline(0, color="#6b7280", lw=0.8); ax[1].set_xlabel("ln GOR12, demeaned within area"); ax[1].set_ylabel("ln 12-mo oil/kft, demeaned within area")
ax[1].set_title("#1 oil vs GOR inside an area (20 bins)", fontsize=10); ax[1].legend(fontsize=8); ax[1].grid(alpha=0.3)
fig.tight_layout(); fig.savefig(f"{OUT_DIR}/dig.png", dpi=90)
print(f"wrote {OUT_DIR}")
