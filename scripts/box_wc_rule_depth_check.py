"""BOX step 20a — depth-only check of the drafted sql/16 Midland 'WOLFCAMP C' rule (read-only).

    python -m scripts.box_wc_rule_depth_check --out docs/box/step20a-2026-10-26/tag_screen_whatif_wc/depth_check.csv \
        [--cache <scored.pkl>] [--labels-cache <labels.pkl>]

The rule hands every Novi-WOLFCAMP-C-sourced Midland tag to Enverus. This scores each producer whose tag the rule
changes by DEPTH ONLY, against a jury that neither side controls: consensus v2.2 clean witnesses minus every well whose
Novi formation is 'WOLFCAMP C' (a ratified override stays in). The jury is the same under the live and the what-if tags.

  local     the jury's coherent bands within 1.5 mi (box.bench_qc rule; 2 then 3 mi when none): the nearest band within
            120 ft is the new tag -> confirms; a band of the new tag exists but sits > 120 ft away -> contradicted.
  ladder    regional fallback: depth below the local jury WCA_1 band, snapped to the nearest rung. Rungs = median depth
            below WCA_1 of v2.2 witnesses per tag; WCC split into the Novi-WOLFCAMP-C-tagged wells ("WC slot") and the rest.
Nothing is written to the warehouse; votes from names, vendors, GOR and sql/23 are deliberately not used.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from box import tag_screen as ts
from box.bench_qc import DEFAULT_PARAMS, FT_PER_MI, _project_xy_ft, local_bands
from scripts.box_family_qc import _scored

RADII_MI = (1.5, 2.0, 3.0)
LADDER = ("WCA_1", "WCB_1", "WCB_2", "WCD")
NORTH_LAT = 31.765  # the tag screen's north / south split


def _labels(api10: list[str], cache: Path | None) -> pd.DataFrame:
    if cache and cache.exists():
        return pd.read_pickle(cache)
    from etl.db import get_connection

    with get_connection() as conn:
        lab = ts.pull_labels(conn, "midland", api10)
    if cache:
        lab.to_pickle(cache)
    return lab


def rungs(d: pd.DataFrame, novi_wc: pd.Series) -> dict[str, float]:
    """Median depth below the local WCA_1 band (ft) of v2.2 witnesses, per ladder tag + the Novi-WC 'WC slot'."""
    ok = d["cons_witness"] & d["cons_bands"].map(lambda b: isinstance(b, dict) and "WCA_1" in b)
    below = d.loc[ok, "tvd_ft"].astype(float) - d.loc[ok, "cons_bands"].map(lambda b: b["WCA_1"])
    tag = d.loc[ok, "formation_blueox"]
    out = {b: float(below[tag == b].median()) for b in LADDER}
    out["WC slot"] = float(below[(tag == "WCC") & novi_wc[ok]].median())
    return out


def depth_call(r: pd.Series, rung: dict[str, float]) -> tuple[str, str | None]:
    """(call, ladder rung) for one retagged well."""
    lad = None if pd.isna(r["off_wca1_ft"]) else min(rung, key=lambda k: abs(r["off_wca1_ft"] - rung[k]))
    if r["verdict"] == "new":
        return "new tag (local band)", lad
    contradicted = r["verdict"] != "no jury" and pd.notna(r["off_new_ft"])
    if lad is None:
        return ("not the new tag (local band)" if contradicted else "undecided"), lad
    if lad == r["new_tag"]:
        return ("contradicted locally, ladder says new" if contradicted else "new tag (WCA_1 ladder)"), lad
    return ("WC slot (stays WCC)" if lad == "WC slot" else "other rung"), lad


def check(d: pd.DataFrame, lab: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float], int]:
    d = d.reset_index(drop=True).copy()
    p, _ = ts.whatif_retag(d.drop(columns=[c for c in d.columns if c.startswith("cons_")]), lab, "midland")
    d["new_tag"] = p["formation_blueox"].values
    d["retag"] = p["whatif_changed"].values
    d = d.merge(lab[["api10", "novi_formation", "env_interval"]], on="api10", how="left")
    novi_wc = (d["novi_formation"] == "WOLFCAMP C") & (d["formation_blueox_source"] != "ratified_override")
    jury = d["cons_witness"] & ~novi_wc
    pos = d["mid_lon"].notna() & d["mid_lat"].notna() & d["tvd_ft"].notna()
    xy = np.full((len(d), 2), np.nan)
    xy[pos.values] = _project_xy_ft(d.loc[pos, "mid_lon"].values, d.loc[pos, "mid_lat"].values)
    ji = np.where(jury.values)[0]
    tree = cKDTree(xy[ji])
    jb, jt = d["formation_blueox"].values[ji], d["tvd_ft"].values[ji].astype(float)
    rows = []
    for i in np.where((d["retag"] & pos).values)[0]:
        r = d.iloc[i]
        tvd, old, new = float(r["tvd_ft"]), r["formation_blueox"], r["new_tag"]
        bands: dict = {}
        rad = np.nan
        for rad in RADII_MI:
            by: dict[str, list[float]] = {}
            for j in tree.query_ball_point(xy[i], r=rad * FT_PER_MI):
                if ji[j] != i:
                    by.setdefault(str(jb[j]), []).append(float(jt[j]))
            bands = local_bands({b: np.array(v) for b, v in by.items()}, DEFAULT_PARAMS)
            if bands:
                break
        rec = {"api10": r["api10"], "well_name": r["well_name"], "operator": r["operator"], "county": r["county"],
               "lat": r["mid_lat"], "lon": r["mid_lon"], "north": r["mid_lat"] >= NORTH_LAT, "tvd_ft": tvd,
               "first_prod": r["first_production_date"], "cohort": bool(r["cohort"]), "old_tag": old, "new_tag": new,
               "env_interval": r["env_interval"], "jury_radius_mi": rad if bands else np.nan,
               "jury_bands": "; ".join(f"{b} {m:,.0f} (n{n})" for b, (m, n, _) in sorted(bands.items(), key=lambda kv: kv[1][0]))}
        for nm, b in (("new", new), ("old", old), ("wca1", "WCA_1")):
            rec[f"off_{nm}_ft"] = tvd - bands[b][0] if b in bands else np.nan  # + = the well sits deeper than the band
        if not bands:
            v, b1, d1 = "no jury", None, np.nan
        else:
            b1 = min(bands, key=lambda b: abs(tvd - bands[b][0]))
            d1 = abs(tvd - bands[b1][0])
            v = "off band" if d1 > DEFAULT_PARAMS.sits_in_ft else "new" if b1 == new else "old" if b1 == old else "third"
        rec.update(jury_nearest=b1, jury_nearest_ft=d1, verdict=v)
        rows.append(rec)
    x = pd.DataFrame(rows)
    rung = rungs(d, novi_wc)
    calls = [depth_call(r, rung) for _, r in x.iterrows()]
    x["depth_call"] = [c for c, _ in calls]
    x["ladder_rung"] = [lad for _, lad in calls]
    return x, rung, int(jury.sum())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None, help="pickle of the scored Midland frame; read if present, else written")
    ap.add_argument("--labels-cache", type=Path, default=None)
    a = ap.parse_args(argv)
    d = _scored("midland", a.cache)
    d["api10"] = d["api10"].astype(str)
    lab = _labels(d["api10"].tolist(), a.labels_cache)
    x, rung, n_jury = check(d, lab)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    x.to_csv(a.out, index=False, float_format="%.1f")
    print(f"as of {d.attrs.get('asof')}; retagged {len(x)}; jury {n_jury:,}; rungs below WCA_1 (ft): "
          + ", ".join(f"{k} {v:,.0f}" for k, v in rung.items()))
    print(pd.crosstab(x["new_tag"], x["depth_call"], margins=True).to_string())
    print("cohort only:")
    print(pd.crosstab(x.loc[x.cohort, "new_tag"], x.loc[x.cohort, "depth_call"], margins=True).to_string())
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
