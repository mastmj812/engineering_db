"""BOX step 21b — the scorer (PREREGISTRATION §4-§9 on the §10 harness runs). Called by `python -m scripts.box_step21b score`.

Reads runs/step21b/<group>/ (the harness views, cells, provenance, observed mid_r2 months), runs/step21b/prox.pkl (the 21a links,
re-derived), the 21a package COUNTS (holdout counted, never read) and, read-only, the extents of record + production-sharing
flags. Writes the deliverable tables under --docs. No holdout package exists in any input: the harness dropped them before writing.
"""

from __future__ import annotations

import datetime as dt
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import dev_factor_report as dfr
from box import prox_pud as pp
from box import prox_pud_report as ppr
from box import rehearse9b as r9
from box import step21 as st
from box import step21_prox as sp
from box import step21b as sb
from box import tune15_report as t15

RAW, PROX, PROX_WF = sb.RAW, sb.PROX, sb.PROX_WF
DE, GAP = "mid_r2p_de", "mid_r2p_gap"  # sensitivities: the Delaware D113 table; the nearest-gap rung
TWINS = (f"{RAW}_lin", f"{RAW}_cuide")
CARDS_Q1 = (9, 11, 12, 33, 45)  # FINDINGS §5 Q1: the interim haircuts Michael read as too light
_SHARING_SQL = "SELECT api10, COALESCE(has_production_sharing, false) FROM curated.wells_enriched WHERE api10 = ANY(%(a)s)"


def tag(group: str) -> str:
    return f"tuning_v2_{group}_analog"


def load_group(run: Path, group: str) -> dict[str, Any]:
    """Views (cutoff -> frame, harness row order), observed months, harness cells / summary, and the F(k) identity per cutoff."""
    d = run / group
    t = tag(group)
    z = np.load(d / "months_mid_r2.npz")
    views, months, fchk = {}, {}, []
    for f in sorted(d.glob(f"view_{t}_*.csv.gz")):
        y = f.name.split("_")[-1][:4]
        v = pd.read_csv(f, dtype={"api10": str, "package": str})
        c = f"{y}-12-01"
        v["cutoff"] = c
        if f"{y}_api10" not in z.files:
            if len(v):
                raise RuntimeError(f"{group} {y}: scored wells but no observed months")
            continue
        if not np.array_equal(z[f"{y}_api10"].astype(str), v["api10"].to_numpy(str)):
            raise RuntimeError(f"{group} {y}: observed months not in view order")
        months[c] = {s: z[f"{y}_{s}"] for s in ac.STREAMS}
        for s in ac.STREAMS:
            for k in ac.HORIZONS:
                if f"pred_{RAW}_{s}{k}" in v and v[f"pred_{RAW}_{s}{k}"].notna().any():
                    F, spread = sb.f_from_view(v, months[c][s], s, k)
                    fchk.append({"group": group, "cutoff": c, "stream": s, "horizon": k, "F": F, "max_rel_spread": spread})
        views[c] = v
    cells = pd.read_csv(d / f"cells_{t}.csv")
    summ = json.loads((d / f"summary_{t}.json").read_text(encoding="utf-8"))
    run_meta = json.loads((d / "run.json").read_text(encoding="utf-8"))
    return {"views": views, "months": months, "cells": cells, "summary": summ, "run": run_meta, "fcheck": pd.DataFrame(fchk)}


def harness_identity(cells_h: pd.DataFrame, cells_new: pd.DataFrame, variant: str = RAW) -> float:
    """Max |diff| between the harness's mid_r2 cells and the same cells re-scored here from its views (a D98-style guard)."""
    cols = ["n_packages", "pkg_bias", "pkg_band", "bench_bias", "bench_band"]
    a = cells_h[cells_h.variant == variant].set_index(["cutoff", "stream", "horizon"])[cols].astype(float)
    b = cells_new[cells_new.variant == variant].set_index(["cutoff", "stream", "horizon"])[cols].astype(float)
    j = a.join(b, lsuffix="_h", rsuffix="_n", how="outer")
    return float(np.nanmax(np.abs(np.column_stack([j[f"{c}_h"] - j[f"{c}_n"] for c in cols]))) if len(j) else 0.0)


def proof(run: Path, group: str = "MID_WCC") -> dict[str, Any]:
    """The observer's equivalence proof: every output of the plain §10 run vs the observed run (decompressed CSV content,
    npz arrays, summary JSON without its build timestamp)."""
    a, b = run / group, run / f"{group}_plain"
    if not (b / "run.json").exists():
        return {"status": "plain run missing"}
    out: dict[str, Any] = {"files": {}}
    for f in sorted(b.iterdir()):
        if f.name in ("run.json", "log.txt") or f.suffix == ".html":
            continue
        g = a / f.name
        if f.suffix == ".npz":
            x, y = np.load(f), np.load(g)
            same = x.files == y.files and all(np.array_equal(x[k], y[k], equal_nan=True) for k in x.files)
        elif f.suffix == ".json":
            x, y = (json.loads(p.read_text(encoding="utf-8")) for p in (f, g))
            x.pop("built_at", None)
            y.pop("built_at", None)
            same = x == y
        else:
            x, y = pd.read_csv(f, dtype=str), pd.read_csv(g, dtype=str)
            same = x.equals(y)
        out["files"][f.name] = bool(same)
    out["status"] = "identical" if all(out["files"].values()) else "DIFFERENT"
    return out


def stick_table(prox: dict[str, Any], table: pd.DataFrame, gap_table: pd.DataFrame) -> pd.DataFrame:
    """Every in-extent stick re-decided under the Midland table (box/step21_prox.decide_all, everything else as at 21a r7) beside
    the interim (Delaware) outcome, + the nearest-gap-rung sensitivity factor."""
    cfg = prox["cfg"]
    hair = pp.haircut_lookup(table)
    d = sp.decide_all(cfg, hair, prox["prec"], prox["prec_pat"], prox["near_same"])
    it = prox["interim"]
    out = pd.DataFrame({"location_id": cfg.index, "bench": cfg["bench"].to_numpy(), "config_class": cfg["config_class"].to_numpy(),
                        "n_parents_total": cfg["n_parents_total"].to_numpy(), "config": cfg["config"].to_numpy(),
                        "outcome_interim": it["outcome"].to_numpy(), "factor_interim": it["factor"].to_numpy(),
                        "key_interim": it["haircut_key"].to_numpy(), "outcome": d["outcome"].to_numpy(), "factor": d["factor"].to_numpy(),
                        "key": d["haircut_key"].to_numpy(), "pattern": d["pattern"].to_numpy(), "pattern_package": d["pattern_package"].to_numpy(),
                        "near_same_ft": d["near_same_ft"].to_numpy(), "prec_package": d["prec_package"].to_numpy()})
    g = sb.assign(cfg.reset_index(drop=True), gap_table, rungs=sb.APPLIED_RUNGS, gap_rung=True)
    out["factor_gap"], out["key_gap"], out["rung_gap"] = g["factor"].to_numpy(), g["key"].to_numpy(), g["rung"].to_numpy()
    return out


def class_bias(v: pd.DataFrame, mask: pd.Series, variants: tuple[str, ...], label: str, horizons: tuple[int, ...] = (12, 24, 36)) -> list[dict[str, Any]]:
    """Package bias on a subset of scored wells (packages = the subset's members), oil + gas, per variant."""
    rows = []
    x = v[mask.to_numpy()]
    for s in ac.STREAMS:
        for k in horizons:
            r: dict[str, Any] = {"class": label, "stream": s, "horizon": k, "wells": int(x[f"actual_{s}{k}"].notna().sum()) if f"actual_{s}{k}" in x else 0}
            for var in variants:
                col = f"pred_{var}_{s}{k}"
                if col not in x or f"actual_{s}{k}" not in x:
                    continue
                p = ac.package_errors(x, "pkg", f"actual_{s}{k}", col)
                r[f"{var} pkgs"], r[f"{var} bias"] = len(p), (float(p["err"].mean()) if len(p) else np.nan)
            rows.append(r)
    return rows


def run_score(run: Path, docs: Path, groups: list[str] | None = None, conn: Any | None = None, n_draws: int = 2000) -> dict[str, Any]:
    docs.mkdir(parents=True, exist_ok=True)
    groups = [g for g in (groups or list(st.GROUPS)) if (run / g / "run.json").exists()]
    with open(run / "prox.pkl", "rb") as fh:
        prox = pickle.load(fh)
    kc = prox["kc"]
    counts = pd.read_csv(st.DOCS / "package_counts.csv")
    G = {g: load_group(run, g) for g in groups}

    # ---- §4 the Midland factor table: every group's scored tuning children, pooled
    children = []
    for g, x in G.items():
        children.append(sb.child_frame(sb.frames(x["views"]), kc, g))
    ch = pd.concat(children, ignore_index=True)
    table = sb.fit_table(ch)
    gap_table = sb.fit_table(ch, gap_rung=True)
    de_table = pd.read_csv(ppr.HAIRCUT_TABLE)
    fac = sb.record_factor(ch, table)
    fac_de = sb.delaware_factor(ch, de_table)
    gapf = sb.assign(ch, gap_table, rungs=sb.APPLIED_RUNGS, gap_rung=True)
    fac_gap = pd.Series(gapf["factor"].to_numpy(), index=ch["api10"].to_numpy())
    rung = sb.record_rung(ch, table)
    ch = ch.join(rung.rename(columns={"factor": "factor_lookup", "key": "key_applied", "rung": "rung_applied"}))
    ch["factor"] = ch["api10"].map(fac).fillna(1.0)
    ch["factor_de"] = ch["api10"].map(fac_de).fillna(1.0)
    ch["factor_gap"], ch["rung_gap"] = gapf["factor"].to_numpy(), gapf["rung"].to_numpy()
    ch["multi"] = sp.is_multi(ch)
    table.to_csv(docs / "prox_factor_table.csv", index=False)
    gap_table.to_csv(docs / "prox_factor_table_gap_sensitivity.csv", index=False)
    ch.drop(columns=[c for c in ch.columns if c.startswith(("pred_", "actual_"))]).to_csv(docs / "prox_children.csv.gz", index=False)

    # ---- per group: treatments, cells, record, guard, D99
    rows, cells_all, ivl_all, wf_all, eh_all, pooled_all, guard_all, fchk_all, ll_rows, thin_rows, share_rows = [], [], [], [], [], [], [], [], [], [], []
    region_rows = []
    sharing: dict[str, bool] = {}
    ext: dict[str, Any] = {}
    if conn is not None:
        from box import tc_area_report as tar
        from box.tc_curve_report import _read

        ids = sorted({a for x in G.values() for v in x["views"].values() for a in v["api10"]})
        sharing = {str(a): bool(b) for a, b in _read(conn, _SHARING_SQL, {"a": ids})}
        ext = {g: tar.pull_extent(conn, st.GROUPS[g][0], "midland") for g in G}
        conn.rollback()
    for g, x in G.items():
        views = x["views"]
        sb.add_prox(views, fac.to_dict(), PROX)
        sb.add_prox(views, fac_de.to_dict(), DE)
        sb.add_prox(views, fac_gap.to_dict(), GAP)
        c_new = sb.score(views, [RAW, PROX, DE, GAP, *TWINS])
        ident = harness_identity(x["cells"], c_new)
        c_wf, wf_log = sb.walk_forward(c_new, views, PROX)
        cells = pd.concat([c_new, c_wf], ignore_index=True).assign(group=g)
        cells_all.append(cells)
        wf_all.append(pd.DataFrame(wf_log).assign(group=g))
        cnt = counts[counts.group == g]
        rt = sb.record_treatment(cells, cnt)
        months = {s: np.concatenate([m[s] for m in x["months"].values()]) for s in ac.STREAMS}
        tab = sb.d62_table(cells, PROX)
        gd = sb.guard(tab, months)
        rec_by_stream = {s: (PROX if (rt["record"] == PROX or gd[s]["refused"]) else PROX_WF) for s in ac.STREAMS}
        v = sb.frames(views)
        for s in ac.STREAMS:
            for k in ac.HORIZONS:
                src = f"pred_{rec_by_stream[s]}_{s}{k}"
                if src in v:
                    v[f"pred_record_{s}{k}"] = v[src]
        rec_name = rec_by_stream["oil"] if rec_by_stream["oil"] == rec_by_stream["gas"] else f"{PROX_WF} oil / {PROX} gas (D106)"
        eh = sb.expected_holdout(cells, rec_by_stream["oil"], cnt)
        horizons = tuple(int(k) for k in eh.loc[eh["d99_cell"], "horizon"] if int(k) in st.HORIZONS_JUDGEABLE)
        dd = sb.d99(v, "record", horizons, n_draws=n_draws)
        alt = PROX if rt["record"] == PROX_WF else PROX_WF
        eh_alt = sb.expected_holdout(cells, alt, cnt)
        h_alt = tuple(int(k) for k in eh_alt.loc[eh_alt["d99_cell"], "horizon"] if int(k) in st.HORIZONS_JUDGEABLE)
        da = sb.d99(v, alt, h_alt, n_draws=n_draws)
        ivl_all += [dd["intervals"].assign(group=g, treatment=rec_name, role="record"),
                    da["intervals"].assign(group=g, treatment=alt, role="alternative (only if the tuning gate moves the group)")]
        eh_all += [eh.assign(group=g, treatment=rec_by_stream["oil"], role="record"), eh_alt.assign(group=g, treatment=alt, role="alternative")]
        for var in (RAW, PROX, PROX_WF, DE, GAP, *TWINS, f"{RAW}_wf"):
            if any(c.startswith(f"pred_{var}_") for c in v.columns):
                pooled_all.append(t15.pooled(r9.package_table(v, var)).assign(group=g, variant=var))
        pooled_all.append(dd["pooled"].assign(group=g, variant="record"))
        for s in ac.STREAMS:
            guard_all.append({"group": g, "stream": s, "refused": gd[s]["refused"], "reasons": "; ".join(gd[s]["reasons"]),
                              "factors": " / ".join(f"{gd[s]['factors'][k]:.3f}" for k in sorted(gd[s]["factors"])),
                              "g48_median": (gd[s]["g48"] or {}).get("median"), "g48_min": (gd[s]["g48"] or {}).get("min"),
                              "g48_max": (gd[s]["g48"] or {}).get("max"), "g48_share_outside": (gd[s]["g48"] or {}).get("share_outside")})
        fchk_all.append(x["fcheck"])
        cr = dd["pass_rate"]
        good = float(cr.loc[np.isclose(cr.scale, 1.0), "pass_rate"].iloc[0]) if len(cr) else np.nan
        miss = 1.0 - float(cr.loc[np.isclose(cr.scale, 1.15), "pass_rate"].iloc[0]) if len(cr) else np.nan
        miss_lo = 1.0 - float(cr.loc[np.isclose(cr.scale, 0.85), "pass_rate"].iloc[0]) if len(cr) else np.nan
        pr = dd["pooled"]
        po = {int(r.horizon): r.pkg_bias for r in pr[pr.stream == "oil"].itertuples()}
        pg = {int(r.horizon): r.pkg_bias for r in pr[pr.stream == "gas"].itertuples()}
        rows.append({"group": g, "pool wells": x["summary"]["n_pool_wells"], "extent": x["summary"]["extent_id"],
                     "scored tuning wells": int(sum(len(vv) for vv in views.values())),
                     "record (rule)": rt["record"], "expected wf holdout cum-12 / 24": f"{rt['expected_wf'].get(12, 0):.0f} / {rt['expected_wf'].get(24, 0):.0f}",
                     "D106 oil / gas": f"{'REFUSED' if gd['oil']['refused'] else 'ok'} / {'REFUSED' if gd['gas']['refused'] else 'ok'}",
                     "record treatment": rec_name, "D99 horizons": ", ".join(f"cum-{k}" for k in horizons) or "none",
                     "route": st.tier_route({k: (999 if k in horizons else 0) for k in st.HORIZONS_JUDGEABLE}),
                     "record oil bias cum-12 / 24 / 36": " / ".join(f"{po.get(k, np.nan):+.1%}" for k in (12, 24, 36)),
                     "record gas bias cum-12 / 24 / 36": " / ".join(f"{pg.get(k, np.nan):+.1%}" for k in (12, 24, 36)),
                     "consistency passes a good forecast": good, "catches 15 % high": miss, "catches 15 % low": miss_lo,
                     "harness identity max |diff|": ident, "frozen files identical (start / end)":
                         f"{x['run']['frozen_check']['identical']} / {x['run'].get('frozen_check_at_end', {}).get('identical')}",
                     "run head": x["run"]["head"][:7], "engine (boxfit)": x["summary"]["engine_sha"][:7]})

        # §8 long laterals (reported, never judged)
        v["lat_ratio"] = pd.to_numeric(v.get(f"{RAW}_lat_ratio"), errors="coerce")
        mm = pd.Series(np.where(v["lat_ratio"] < st.MISMATCH_CUTS[0], "shorter", np.where(v["lat_ratio"] >= st.MISMATCH_CUTS[1], "longer", "near")), index=v.index)
        mm[v["lat_ratio"].isna()] = "(no cohort)"
        lc = v["lateral_ft"].map(st.lateral_class)
        for lab in ("shorter", "near", "longer"):
            ll_rows += [dict(r, group=g, kind="mismatch (well / cohort mean lateral)") for r in class_bias(v, mm == lab, (RAW, *TWINS), lab)]
        for lab in sorted(lc.unique()):
            ll_rows += [dict(r, group=g, kind="completed lateral, ft") for r in class_bias(v, lc == lab, (RAW, *TWINS), lab)]
        ll_rows.append({"group": g, "kind": "share of scored wells", "class": "> 12,500 ft", "wells": int((v["lateral_ft"] > 12_500).sum()),
                        "share": float((v["lateral_ft"] > 12_500).mean())})
        ll_rows.append({"group": g, "kind": "share of scored wells", "class": "> 15,000 ft (past the Midland panel)", "wells": int((v["lateral_ft"] > 15_000).sum()),
                        "share": float((v["lateral_ft"] > 15_000).mean())})
        # §9 thin-control, sharing, edges
        nloc = pd.to_numeric(v.get("n_local"), errors="coerce")
        thin_rows += [dict(r, group=g) for r in class_bias(v, nloc < 3, (RAW, "record"), "thin-control (< 3 local wells in 3 mi)", (12, 24))]
        thin_rows += [dict(r, group=g) for r in class_bias(v, nloc >= 3, (RAW, "record"), "with local control", (12, 24))]
        if sharing:
            shr = v["api10"].map(sharing).fillna(False).astype(bool)
            share_rows += [dict(r, group=g) for r in class_bias(v, shr, (RAW, "record"), "production-sharing", (12, 24))]
            share_rows += [dict(r, group=g) for r in class_bias(v, ~shr, (RAW, "record"), "not sharing", (12, 24))]
        if g in ext:
            xx, yy = dfr._xy(v["mid_lon"], v["mid_lat"])
            vv = pd.concat([v.reset_index(drop=True), t15.side_classes(np.asarray(xx), np.asarray(yy), ext[g]["geom_ft"])], axis=1)
            vv["package"] = vv["pkg"]
            region_rows.append(t15.region_table(vv, "record").assign(group=g))
        G[g]["v"] = v
        G[g]["record"] = rec_by_stream

    # ---- write
    summary = pd.DataFrame(rows)
    cells_all_df = pd.concat(cells_all, ignore_index=True)
    ivl = pd.concat(ivl_all, ignore_index=True)
    out_tables = {"summary_table": summary, "cells": cells_all_df, "walk_forward": pd.concat(wf_all, ignore_index=True),
                  "expected_holdout": pd.concat(eh_all, ignore_index=True), "pooled": pd.concat(pooled_all, ignore_index=True),
                  "guard_d106": pd.DataFrame(guard_all), "f_identity": pd.concat(fchk_all, ignore_index=True),
                  "long_laterals": pd.DataFrame(ll_rows), "thin_control": pd.DataFrame(thin_rows), "sharing": pd.DataFrame(share_rows),
                  "edge_regions": pd.concat(region_rows, ignore_index=True) if region_rows else pd.DataFrame(), "intervals_all": ivl}
    for name, df in out_tables.items():
        df.to_csv(docs / f"{name}.csv", index=False)
    frozen = ivl[ivl["role"] == "record"].copy()
    frozen_alt = ivl[ivl["role"] != "record"].copy()
    txt = sb.frozen_intervals_csv(pd.concat([frozen, frozen_alt], ignore_index=True))
    (docs / "frozen_d99.csv").write_text(txt, encoding="utf-8", newline="\n")
    digest = sb.sha256_text(txt)

    # ---- sticks under the Midland table; the five cards; DEAN body vs addition
    stx = stick_table(prox, table, gap_table)
    s21 = pd.read_csv(st.DOCS / "sticks.csv.gz", usecols=["stick_id", "group", "part", "pad_name", "length_ft"])
    s21["location_id"] = s21["stick_id"].astype(str)
    stx = stx.merge(s21, on="location_id", how="left")
    stx.to_csv(docs / "sticks_midland_table.csv.gz", index=False)
    cards = pd.read_csv(st.DOCS / "prox_cards" / "cards_sample.csv")
    cq = cards[cards["card"].isin(CARDS_Q1)][["card", "stick_id", "group", "verdict", "note"]].merge(
        stx.assign(stick_id=stx["location_id"].astype(int)), on=["stick_id", "group"], how="left")
    cq.to_csv(docs / "cards_q1.csv", index=False)
    meta = {"built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "groups": groups, "n_draws": n_draws,
            "frozen_d99_sha256": digest, "prox": prox["meta"], "n_children": len(ch), "n_children_multi": int(ch["multi"].sum()),
            "n_children_multi_scored_oil24": int((ch["multi"] & ch[f"l_{sb.METRIC}"].notna()).sum()),
            "proof": proof(run), "definition_digest": st.digest()}
    (docs / "score_meta.json").write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")
    return {"meta": meta, "summary": summary, "G": G, "children": ch, "table": table, "gap_table": gap_table, "sticks": stx, "cards": cq,
            **out_tables}
