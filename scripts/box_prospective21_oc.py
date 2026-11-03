"""BOX step 21d — operating characteristics of the graduation rules, on 21b TUNING packages only (DB-free).

Reads the 21b tuning views (runs/step21b/MID_<g>/view_tuning_v2_MID_<g>_analog_<yyyy>.csv.gz: wells first producing before
2025-12-01, D52 holdout packages dropped by the harness before they were written), the 21a drilled-child links cache (geometry and
dates only) and the committed 24a Midland frame. No 2026 well, no holdout package, no database.

Treatment = what step 23 ships (box/prospective21.DEFINITION['method']): oil = pred_mid_r2 x D150 factor (level x F_R3 over the
drilled-side parents) x the WCA_1 D102 haircut (the gate-21c table); gas = pred_mid_r2.

Rules compared on each group's judged cells (oil + gas x cum-12 / cum-24 where the projected 2026 cohort reaches 30 packages):
  A    consistency, D125 interval  (P2.5-97.5 of block-draw subsets at the cohort's share)
  A2   consistency, interval + the tuning mean's own sampling error ([draw - complement] + all)
  ACC  accuracy (|bias| <= 10 % AND scale-free spread <= benchmark + 0.05) on every judged cell
  B    A or ACC      B2   A2 or ACC          (graduation only; keeping validated stays A / A2)

Three readings of each rule:
  insample   the 21b / D125 rehearsal: the draws that define the interval are also the test (rehearse9b.consistency's pass rate)
  split      honest: a pseudo-cohort of blocks at the cohort's share, judged against an interval drawn from the complement only
  vintage    leave one tuning cutoff out: that cutoff's packages are the cohort, the other cutoffs the reference — a real new
             vintage of a method exactly as good as the one under test
Each at forecast scale 1.00 (pass rate of a forecast as good as tuning), 1.15 (BOX 15 % high) and 0.85 (BOX 15 % low): the
catch rate is 1 - pass at 1.15 / 0.85.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import acceptance as ac
from box import prospective21 as p21
from box import rehearse9b as r9

SHIP = "ship"
SCALES = (1.0, 1.15, 0.85)
N_DRAWS = 2000
N_SPLIT_OUTER, N_SPLIT_INNER = 400, 400
SEED = 20261103
Q = (2.5, 97.5)
CUTOFFS = ("2019-12-01", "2020-12-01", "2021-12-01", "2022-12-01", "2023-12-01", "2024-12-01")


def view_files(runs: Path, group: str) -> list[Path]:
    return sorted((runs / group).glob(f"view_tuning_v2_{group}_analog_*.csv.gz"))


def manifest(runs: Path, links: Path, out: Path) -> int:
    lines = []
    for g in p21.GROUPS:
        fs = view_files(runs, g)
        if not fs:
            raise SystemExit(f"no tuning views under {runs / g}")
        lines += [f"{p21.sha256_file(f)}  step21b/{g}/{f.name}" for f in fs]
    lines.append(f"{p21.sha256_file(links)}  step21a/{links.name}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "tuning_views.sha256").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(f"wrote {out / 'tuning_views.sha256'} ({len(lines)} files)")
    return 0


# ----------------------------------------------------------------------------
# frames
# ----------------------------------------------------------------------------


def load_views(runs: Path, group: str) -> pd.DataFrame:
    fs = view_files(runs, group)
    v = pd.concat([pd.read_csv(f, dtype={"api10": str}) for f in fs], ignore_index=True)
    if "package_held_out" in v and bool(v["package_held_out"].astype(bool).any()):
        raise SystemExit(f"{group}: a tuning view carries held-out packages — refuse")
    if (pd.to_datetime(v["first_production_date"]) >= pd.Timestamp(p21.CUTOFF)).any():
        raise SystemExit(f"{group}: a tuning view carries a well first producing on/after {p21.CUTOFF} — refuse")
    from box import dev_factor_report as dfr
    from box import holdout as ho

    v = v.copy()
    x, y = dfr._xy(v["mid_lon"], v["mid_lat"])
    v["bx"], v["by"] = ho.blocks(np.asarray(x), np.asarray(y))
    v["pkg"] = v["cutoff"].astype(str) + ":" + v["package"].astype(str)
    return v


def add_ship(v: pd.DataFrame, factor: pd.Series, group: str, haircut: dict[int, float] | None) -> None:
    """pred_ship_<s><k>: oil = mid_r2 x D150 factor (x WCA_1 haircut); gas = mid_r2. Also pred_shipnh_ (no haircut) for WCA_1."""
    f = v["api10"].map(factor).fillna(p21.D150_MIDLAND["level"]).to_numpy(float)
    for k in ac.HORIZONS:
        for s in ac.STREAMS:
            col = f"pred_mid_r2_{s}{k}"
            if col not in v:
                continue
            base = v[col].to_numpy(float) * (f if s == "oil" else 1.0)
            h = (haircut or {}).get(k, 1.0) if s == "oil" else 1.0
            v[f"pred_{SHIP}_{s}{k}"] = base * h
            v[f"pred_shipnh_{s}{k}"] = base


# ----------------------------------------------------------------------------
# vectorised cell statistics
# ----------------------------------------------------------------------------


class Cells:
    """Per judged cell: package error e, benchmark error, validity; block membership. Bias of a package subset = mean e."""

    def __init__(self, t: dict[str, Any], cells: list[tuple[str, int]]):
        self.t, self.cells = t, cells
        self.member = t["member"]
        self.cut = t["pkg"]["cutoff"].astype(str).to_numpy()
        self.e, self.ok, self.eb, self.okb = {}, {}, {}, {}
        for c in cells:
            q = t["sums"][c]
            self.ok[c] = np.isfinite(q["box_a"]) & np.isfinite(q["box_p"]) & (q["box_p"] > 0)
            self.e[c] = np.where(self.ok[c], q["box_a"] / np.where(self.ok[c], q["box_p"], 1.0) - 1.0, 0.0)
            self.okb[c] = np.isfinite(q.get("bench_a", np.full(len(self.cut), np.nan))) & np.isfinite(q.get("bench_p", np.full(len(self.cut), np.nan)))
            ba, bp = q.get("bench_a"), q.get("bench_p")
            self.eb[c] = np.where(self.okb[c], (ba if ba is not None else 0) / np.where(self.okb[c], bp if bp is not None else 1.0, 1.0) - 1.0, np.nan)

    def n(self, mask: np.ndarray, c: tuple[str, int]) -> np.ndarray:
        """mask: (draws, pkgs) or (pkgs,) -> package count with a valid error."""
        return (mask & self.ok[c]).sum(axis=-1)

    def bias(self, mask: np.ndarray, c: tuple[str, int]) -> np.ndarray:
        m = mask & self.ok[c]
        with np.errstate(invalid="ignore", divide="ignore"):
            return (m * self.e[c]).sum(axis=-1) / m.sum(axis=-1)

    def spread_ok(self, mask: np.ndarray, c: tuple[str, int], scale: float = 1.0) -> bool:
        """D58 on one subset: BOX scale-free P10-P90 band <= the benchmark's + 0.05 (box/rehearse9b._spread_ok, with scale)."""
        m, mb = mask & self.ok[c], mask & self.okb[c]
        e = (self.e[c][m] + 1.0) / scale - 1.0
        b, w = r9._stats(e)
        bb, bw = r9._stats(self.eb[c][mb])
        return bool(ac.scale_free(w, b) <= ac.scale_free(bw, bb) + ac.BAND_TOL)


def scaled(bias: np.ndarray, sc: float) -> np.ndarray:
    """Package bias when every forecast is multiplied by sc: mean((a / (p sc)) - 1) = (1 + bias) / sc - 1."""
    return (1.0 + np.asarray(bias, float)) / sc - 1.0


def draw_masks(rng: np.random.Generator, member: np.ndarray, share: float, n: int, allowed_pkg: np.ndarray | None = None) -> np.ndarray:
    """n draws of 3-mi blocks at `share` (iid per block, the D52 shape) -> (n, pkgs) membership; restricted to allowed_pkg."""
    blocks = rng.random((n, member.shape[1])) < share
    m = (blocks.astype(np.uint8) @ member.T.astype(np.uint8)) > 0
    return m & allowed_pkg[None, :] if allowed_pkg is not None else m


def intervals(C: Cells, ref: np.ndarray, share: float, rng: np.random.Generator, n: int) -> dict[tuple[str, int], dict[str, tuple[float, float]]]:
    """Per cell: interval A (subset draws of the reference) and A2 ([draw - complement] + all) at `share` of the reference."""
    D = draw_masks(rng, C.member, share, n, ref)
    comp = ref[None, :] & ~D
    out = {}
    for c in C.cells:
        b_all = float(C.bias(ref, c))
        bd, bc = C.bias(D, c), C.bias(comp, c)
        a = np.nanpercentile(bd, Q)
        a2 = np.nanpercentile(bd - bc + b_all, Q)
        out[c] = {"A": (float(a[0]), float(a[1])), "A2": (float(a2[0]), float(a2[1])), "ref_bias": b_all}
    return out


def judge_group(C: Cells, coh: np.ndarray, iv: dict, sc: float | dict[tuple[str, int], float]) -> dict[str, bool]:
    """Every judged cell, per rule, for one cohort mask at forecast scale sc (one number, or one per cell)."""
    res = {"A": True, "A2": True, "ACC": True}
    for c in C.cells:
        s_c = sc[c] if isinstance(sc, dict) else sc
        b = float(scaled(C.bias(coh, c), s_c))
        lo, hi = iv[c]["A"]
        lo2, hi2 = iv[c]["A2"]
        res["A"] &= bool(lo <= b <= hi)
        res["A2"] &= bool(lo2 <= b <= hi2)
        res["ACC"] &= bool(abs(b) <= ac.BIAS_TOL and C.spread_ok(coh, c, s_c))
    res["B"] = res["A"] or res["ACC"]
    res["B2"] = res["A2"] or res["ACC"]
    return res


# ----------------------------------------------------------------------------
# the three readings
# ----------------------------------------------------------------------------


def insample(C: Cells, share: float, seed: int) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    allp = np.ones(len(C.cut), bool)
    iv = intervals(C, allp, share, np.random.default_rng(seed), N_DRAWS)
    D = draw_masks(rng, C.member, share, N_DRAWS)
    rows = []
    cell_out = {c: 0 for c in C.cells}
    for i in range(N_DRAWS):
        for sc in SCALES:
            r = judge_group(C, D[i], iv, sc)
            rows.append({"draw": i, "scale": sc, **r})
        for c in C.cells:
            b = float(C.bias(D[i], c))
            cell_out[c] += not (iv[c]["A"][0] <= b <= iv[c]["A"][1])
    return pd.DataFrame(rows), {"intervals": iv, "cell_outside_A": {f"{s}{k}": v / N_DRAWS for (s, k), v in cell_out.items()}}


def split(C: Cells, share: float, seed: int) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed + 1)
    rows = []
    out_a = {c: 0 for c in C.cells}
    out_a2 = {c: 0 for c in C.cells}
    n_ok = 0
    allp = np.ones(len(C.cut), bool)
    accurate = {c: 1.0 + float(C.bias(allp, c)) for c in C.cells}  # forecasts / (1 + tuning bias): expected cohort bias 0
    for i in range(N_SPLIT_OUTER):
        coh = draw_masks(rng, C.member, share, 1)[0]
        ref = ~coh
        if coh.sum() < 5 or ref.sum() < 5:
            continue
        inner = min(0.9, share / max(1e-9, 1.0 - share))
        iv = intervals(C, ref, inner, rng, N_SPLIT_INNER)
        n_ok += 1
        for sc in SCALES:
            rows.append({"split": i, "scale": sc, **judge_group(C, coh, iv, sc)})
        # the WCB_2 situation: the cohort is ACCURATE (expected bias 0 on every cell) where tuning was biased
        rows.append({"split": i, "scale": "accurate", **judge_group(C, coh, iv, accurate)})
        for c in C.cells:
            b = float(C.bias(coh, c))
            out_a[c] += not (iv[c]["A"][0] <= b <= iv[c]["A"][1])
            out_a2[c] += not (iv[c]["A2"][0] <= b <= iv[c]["A2"][1])
    return pd.DataFrame(rows), {"n_splits": n_ok, "cell_outside_A": {f"{s}{k}": v / max(n_ok, 1) for (s, k), v in out_a.items()},
                                "cell_outside_A2": {f"{s}{k}": v / max(n_ok, 1) for (s, k), v in out_a2.items()}}


def vintage(C: Cells, seed: int, floor: int = p21.MIN_PACKAGES) -> pd.DataFrame:
    """Leave one cutoff out: its packages are the cohort; the cells it can be judged on are those with >= floor packages; the
    interval comes from the other cutoffs at the matching share."""
    rng = np.random.default_rng(seed + 2)
    rows = []
    for cut in CUTOFFS:
        coh = C.cut == cut
        ref = ~coh
        cells = [c for c in C.cells if int(C.n(coh, c)) >= floor]
        if not any(s == "oil" for s, _ in cells):
            continue
        sub = Cells.__new__(Cells)
        sub.__dict__.update(C.__dict__)
        sub.cells = cells
        n_ref = max(int(C.n(ref, cells[0])), 1)
        share = min(0.9, int(C.n(coh, cells[0])) / n_ref)
        iv = intervals(sub, ref, share, rng, N_DRAWS)
        for sc in SCALES:
            r = judge_group(sub, coh, iv, sc)
            rows.append({"cutoff": cut, "scale": sc, "cells": ",".join(f"{s}{k}" for s, k in cells),
                         "n_oil12": int(C.n(coh, cells[0])), **r,
                         **{f"bias_{s}{k}": float(scaled(C.bias(coh, (s, k)), sc)) for s, k in cells},
                         **{f"ref_{s}{k}": iv[(s, k)]["ref_bias"] for s, k in cells}})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# driver
# ----------------------------------------------------------------------------


COMPLETE_MONTHS = (1, 2, 3, 4, 5, 6)  # 2026 first-production months whose reporting is ~complete at the snapshot (FINDINGS §3)


def judgeability(runs: Path, out: Path) -> pd.DataFrame:
    """Expected judged packages per group for the FULL 2026 cohort (identities only):
      projected wells    = 2026 wells first producing in COMPLETE_MONTHS x (2025 full-year wells / 2025 wells in those months)
      projected packages = projected wells x (2025 packages / 2025 wells) for the group
      expected judged    = projected packages x the tuning share of packages that carried a forecast (21b views, oil cum-12)
    'floor' = packages already in the 2026 snapshot x that share (the cohort only grows)."""
    c = pd.read_csv(out / "cohort_at_draft.csv", dtype={"api10": str})
    c["mo"] = c["fp_month"].str[5:].astype(int)
    rows = []
    for g in p21.GROUPS:
        x25, x26 = c[(c["group"] == g) & (c["cohort"] == 2025)], c[(c["group"] == g) & (c["cohort"] == 2026)]
        w25, w25h = len(x25), int(x25["mo"].isin(COMPLETE_MONTHS).sum())
        w26h = int(x26["mo"].isin(COMPLETE_MONTHS).sum())
        pk25, pk26 = x25["package"].nunique(), x26["package"].nunique()
        v = load_views(runs, g)
        tt = r9.package_table(v, "mid_r2", (12,))
        q = tt["sums"][("oil", 12)]
        scored = float(np.mean(np.isfinite(q["box_a"]) & np.isfinite(q["box_p"]) & (q["box_p"] > 0))) if len(q["box_a"]) else 0.0
        proj_w = w26h * (w25 / w25h) if w25h else float(len(x26))
        proj_pk = proj_w * (pk25 / w25) if w25 else float(pk26)
        rows.append({"group": g, "tier": p21.GROUPS[g][2], "wells_2026_so_far": len(x26), "wells_2026_jan_jun": w26h,
                     "packages_2026_so_far": pk26, "wells_2025": w25, "packages_2025": pk25, "projected_wells_2026": round(proj_w, 1),
                     "projected_packages_2026": round(proj_pk, 1), "tuning_scored_share": round(scored, 4),
                     "expected_judged_packages": int(np.floor(proj_pk * scored)), "floor_judged_packages": int(np.floor(pk26 * scored)),
                     "judged_cum12_cum24": bool(np.floor(proj_pk * scored) >= p21.MIN_PACKAGES)})
    j = pd.DataFrame(rows)
    j.to_csv(out / "judgeability.csv", index=False, lineterminator="\n")
    return j


def projected_packages(out: Path) -> pd.DataFrame:
    """Expected judged packages per group: the 2026 cohort projected to the full year (FINDINGS §3 states the rule), times the
    tuning share of packages that carried a forecast."""
    p = out / "judgeability.csv"
    if not p.exists():
        raise SystemExit(f"{p} missing: run `snapshot` and the judgeability step first")
    return pd.read_csv(p).set_index("group")


def run(runs: Path, links_path: Path, out: Path) -> int:
    import warnings

    from scripts import box_prospective21 as cli

    warnings.simplefilter("ignore", pd.errors.PerformanceWarning)
    links = pd.read_pickle(links_path)
    # identity 1: the shipped factor on the 24a Midland frame reproduces its exposed-child count (summary_midland.json fit.n_exposed)
    kids = pd.read_csv(p21.PROX_CHILDREN, dtype={"api10": str, "cutoff": str})
    scored = kids[kids["l_oil24"].notna()] if "l_oil24" in kids else kids
    fk = cli.d150_factor(scored[["api10"]].reset_index(drop=True), links, drilled=True)
    s24 = json.loads((Path("docs") / "box" / "prox-continuous-2026-11-02" / "summary_midland.json").read_text(encoding="utf-8"))["fit"]
    id1 = {"children_scored": len(scored), "want_scored": s24["n_scored"], "exposed": int((fk["n_parents"] > 0).sum()), "want_exposed": s24["n_exposed"]}
    print(f"[identity 1] {id1}", flush=True)
    if id1["exposed"] != id1["want_exposed"] or id1["children_scored"] != id1["want_scored"]:
        raise SystemExit("the D150 factor does not reproduce the 24a Midland frame — stop")
    print(judgeability(runs, out).to_string(index=False), flush=True)
    proj = projected_packages(out)
    pooled21b = pd.read_csv(Path("docs") / "box" / "step21b-2026-11-01" / "pooled.csv")
    rows, cells_rows, vint_rows, ident = [], [], [], []
    for gi, g in enumerate(p21.GROUPS):
        v = load_views(runs, g)
        ids = pd.DataFrame({"api10": sorted(set(v["api10"]))})
        f = cli.d150_factor(ids, links, drilled=True)
        factor = pd.Series(f["factor"].to_numpy(float), index=ids["api10"])
        hair = p21.D102_WCA_1_OIL_AT_21C if g == "MID_WCA_1" else None
        add_ship(v, factor, g, hair)
        # identity: raw mid_r2 pooled tuning bias = 21b pooled.csv
        t_raw = r9.package_table(v, "mid_r2", (12, 24))
        t = r9.package_table(v, SHIP, (12, 24))
        tnh = r9.package_table(v, "shipnh", (12, 24))
        n_c = int(proj.at[g, "expected_judged_packages"]) if g in proj.index else 0
        allc = [(s, k) for s in ac.STREAMS for k in p21.HORIZONS_JUDGED]
        full = np.ones(len(t["pkg"]), bool)
        Craw, Call, Cnh = Cells(t_raw, allc), Cells(t, allc), Cells(tnh, allc)
        for c in allc:
            ref = pooled21b[(pooled21b["group"] == g) & (pooled21b["variant"] == "mid_r2") & (pooled21b["stream"] == c[0]) & (pooled21b["horizon"] == c[1])]
            if len(ref) and abs(float(ref["pkg_bias"].iloc[0]) - float(Craw.bias(full, c))) > 1e-9:
                raise SystemExit(f"{g} {c}: raw mid_r2 tuning bias differs from 21b pooled.csv — not the 21b views; stop")
            cells_rows.append({"group": g, "stream": c[0], "horizon": c[1], "tuning_packages": int(Call.n(full, c)),
                               "bias_mid_r2_21b": float(ref["pkg_bias"].iloc[0]) if len(ref) else np.nan,
                               "bias_mid_r2": float(Craw.bias(full, c)), "bias_ship": float(Call.bias(full, c)),
                               "bias_ship_no_haircut": float(Cnh.bias(full, c)),
                               "spread_ok_ship_full": Call.spread_ok(full, c)})
        ident.append({"group": g, "factor_mean": float(np.mean(factor)), "share_exposed": float(np.mean(f["n_parents"] > 0)),
                      "factor_unexposed": float(p21.D150_MIDLAND["level"])})
        judged = [c for c in allc if n_c >= p21.MIN_PACKAGES]
        base = {"group": g, "tier": p21.GROUPS[g][2], "expected_cohort_packages": n_c,
                "tuning_packages_oil12": int(Call.n(full, ("oil", 12))), "tuning_packages_oil24": int(Call.n(full, ("oil", 24)))}
        if not judged:
            rows.append({**base, "judged": "none (NOT JUDGED)"})
            print(f"[{g}] not judged (expected {n_c} packages)", flush=True)
            continue
        C = Cells(t, judged)
        share = min(0.9, n_c / max(base["tuning_packages_oil12"], 1))
        if hair:
            # identity 2: a uniform per-horizon haircut h maps every interval end and the cohort bias by x -> (1 + x) / h - 1, so the
            # consistency verdict is the same with or without it (same draws, same seed)
            iv_h = intervals(C, full, share, np.random.default_rng(7), N_DRAWS)
            iv_n = intervals(Cells(tnh, judged), full, share, np.random.default_rng(7), N_DRAWS)
            gap = max(abs(scaled(iv_n[c][r][j], hair[c[1]]) - iv_h[c][r][j]) for c in judged if c[0] == "oil" for r in ("A", "A2") for j in (0, 1))
            meta_hair = {"max_abs_diff_mapped_interval_end": float(gap), "haircut": hair}
            print(f"[identity 2] WCA_1 haircut invariance: max |mapped - direct| interval end {gap:.2e}", flush=True)
            if gap > 1e-12:
                raise SystemExit("haircut invariance does not hold numerically — stop")
        ins, ins_meta = insample(C, share, SEED + gi)
        spl, spl_meta = split(C, share, SEED + gi)
        vin = vintage(Cells(t, allc), SEED + gi)
        r = {**base, "judged": ",".join(f"{s}{k}" for s, k in judged), "share": share}
        for rule in ("A", "A2", "ACC", "B", "B2"):
            r[f"split_{rule}_accurate"] = float(spl[spl["scale"] == "accurate"][rule].mean())
        for name, df in (("insample", ins), ("split", spl)):
            for sc in SCALES:
                x = df[df["scale"] == sc]
                for rule in ("A", "A2", "ACC", "B", "B2"):
                    r[f"{name}_{rule}_{sc:.2f}"] = float(x[rule].mean())
        r.update({f"insample_cell_outside_A_{k}": v for k, v in ins_meta["cell_outside_A"].items()})
        r.update({f"split_cell_outside_A_{k}": v for k, v in spl_meta["cell_outside_A"].items()})
        r.update({f"split_cell_outside_A2_{k}": v for k, v in spl_meta["cell_outside_A2"].items()})
        rows.append(r)
        if len(vin):
            vint_rows.append(vin.assign(group=g))
        print(f"[{g}] share {share:.3f} · insample A {r['insample_A_1.00']:.3f} · split A {r['split_A_1.00']:.3f} A2 {r['split_A2_1.00']:.3f} "
              f"B {r['split_B_1.00']:.3f} · catch(1.15) A {1 - r['split_A_1.15']:.3f} B {1 - r['split_B_1.15']:.3f}", flush=True)
    pd.DataFrame(rows).to_csv(out / "oc_groups.csv", index=False, lineterminator="\n", float_format="%.4g")
    pd.DataFrame(cells_rows).to_csv(out / "oc_tuning_cells.csv", index=False, lineterminator="\n", float_format="%.6g")
    pd.DataFrame(ident).to_csv(out / "oc_factor_identity.csv", index=False, lineterminator="\n", float_format="%.6g")
    if vint_rows:
        pd.concat(vint_rows, ignore_index=True).to_csv(out / "oc_vintage.csv", index=False, lineterminator="\n", float_format="%.4g")
    meta = {"built_utc": dt.datetime.now(tz=dt.UTC).strftime("%Y-%m-%d %H:%M"), "seed": SEED, "draws": N_DRAWS,
            "split": [N_SPLIT_OUTER, N_SPLIT_INNER], "scales": SCALES, "definition_digest": p21.digest(),
            "links_sha256": hashlib.sha256(links_path.read_bytes()).hexdigest(), "identity_24a_frame": id1,
            "identity_haircut_invariance": locals().get("meta_hair")}
    (out / "oc_meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    return 0
