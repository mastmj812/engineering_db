"""BOX step 9c — summarise a production build artifact per coverage group and compare its WCA rows with a previous build (read-only).

    python -m scripts.box_run_compare --new runs/box9c --old ../../../runs/box8_c1 --out docs/box/step9c-2026-10-17

Writes <out>/groups.csv (per group x stream: locations, forecast, EUR totals / per-kft median, Di nominal + 1-yr effective median,
radius class + search mode shares, edge regions) and <out>/wca_vs_old.json + wca_vs_old.csv (per WCA stick: analog-set identity,
raw / delivered EUR ratio new / old). No database access.
"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import production as pr


def _load(d: Path) -> dict[str, Any]:
    with open(d / "run.pkl", "rb") as fh:
        return pickle.load(fh)


def frame(A: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for loc, r in zip(A["locs"], A["results"], strict=True):
        base = {"stick_id": loc["stick_id"], "group": loc.get("prod_bench", "WCA"), "lateral_ft": loc["lateral_ft"], "edge_region": loc.get("edge_region"),
                "radius_mi": r["radius_mi"], "search_mode": r["search_mode"], "n_analogs": r["n_analogs"],
                "analogs": ";".join(sorted(x["api10"] for x in r.get("analogs", []))), "forecast": "oil" in r.get("streams", {})}
        for s in pr.STREAMS:
            st = r.get("streams", {}).get(s)
            base[f"{s}_eur_raw"] = st["eur_raw"] if st else np.nan
            base[f"{s}_eur"] = st["eur"] if st else np.nan
            base[f"{s}_di"] = st["params"]["Di_nominal"] if st else np.nan
            base[f"{s}_di_eff"] = st["params"]["Di_eff_1yr"] if st else np.nan
            base[f"{s}_b"] = st["params"]["b"] if st else np.nan
            base[f"{s}_cum12"] = float(np.sum(st["months"][:12])) if st else np.nan
        rows.append(base)
    return pd.DataFrame(rows)


def groups(f: pd.DataFrame) -> pd.DataFrame:
    out = []
    for g, x in f.groupby("group", sort=False):
        ok = x[x["forecast"]]
        for s in pr.STREAMS:
            kft = ok[f"{s}_eur"] / (ok["lateral_ft"] / 1000.0)
            out.append({"group": g, "stream": s, "locations": len(x), "with forecast": len(ok), "no analogs": int((~x["forecast"]).sum()),
                        "EUR total (MMbbl | Bcf)": ok[f"{s}_eur"].sum() / 1e6, "EUR/kft P10 (high)": float(np.percentile(kft, 90)),
                        "EUR/kft median": float(kft.median()), "EUR/kft P90 (low)": float(np.percentile(kft, 10)),
                        "EUR haircut factor (sum)": ok[f"{s}_eur"].sum() / ok[f"{s}_eur_raw"].sum(),
                        "Di nominal median /yr": ok[f"{s}_di"].median(), "Di 1-yr eff median": ok[f"{s}_di_eff"].median(), "b median": ok[f"{s}_b"].median(),
                        "past-5-mi share": float((ok["radius_mi"] > pr.RING_MI).mean()), "strike share": float((ok["search_mode"] == "strike").mean()),
                        "south_edge": int((x["edge_region"] == "south_edge").sum()), "other_edge": int((x["edge_region"] == "other_edge").sum())})
    return pd.DataFrame(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new", type=Path, required=True)
    ap.add_argument("--old", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    N, O = _load(a.new), _load(a.old)
    fn, fo = frame(N), frame(O)
    g = groups(fn)
    g.to_csv(a.out / "groups.csv", index=False)
    print(g.to_string(index=False))
    w = fn[fn["group"] == "WCA"].merge(fo, on="stick_id", how="outer", suffixes=("", "_old"), indicator=True)
    both = w[w["_merge"] == "both"]
    fb = both[both["forecast"].astype(bool) & both["forecast_old"].astype(bool)]
    summ = {"new_wca_locations": int((w["_merge"] != "right_only").sum()), "old_locations": int((w["_merge"] != "left_only").sum()),
            "only_new": sorted(int(x) for x in w.loc[w["_merge"] == "left_only", "stick_id"]),
            "only_old": sorted(int(x) for x in w.loc[w["_merge"] == "right_only", "stick_id"]),
            "both_with_forecast": len(fb), "analog_set_identical": int((fb["analogs"] == fb["analogs_old"]).sum()),
            "n_analogs_identical": int((fb["n_analogs"] == fb["n_analogs_old"]).sum())}
    for s in pr.STREAMS:
        for col in ("eur_raw", "eur"):
            r = fb[f"{s}_{col}"] / fb[f"{s}_{col}_old"]
            summ[f"{s}_{col}_ratio"] = {"median": float(r.median()), "p10_high": float(np.percentile(r, 90)), "p90_low": float(np.percentile(r, 10)),
                                        "identical_1e-9": int((np.abs(r - 1) < 1e-9).sum()), "sum_ratio": float(fb[f"{s}_{col}"].sum() / fb[f"{s}_{col}_old"].sum())}
    same = fb["analogs"] == fb["analogs_old"]
    summ["oil_eur_raw_ratio_same_analogs"] = float((fb.loc[same, "oil_eur_raw"] / fb.loc[same, "oil_eur_raw_old"]).median()) if same.any() else None
    (a.out / "wca_vs_old.json").write_text(json.dumps(summ, indent=2), encoding="utf-8")
    fb.assign(oil_eur_ratio=fb["oil_eur"] / fb["oil_eur_old"], analogs_same=same)[
        ["stick_id", "n_analogs", "n_analogs_old", "analogs_same", "oil_eur", "oil_eur_old", "oil_eur_ratio"]].to_csv(a.out / "wca_vs_old.csv", index=False)
    print(json.dumps({k: v for k, v in summ.items() if k not in ("only_new", "only_old")}, indent=1))
    print(f"only new {len(summ['only_new'])}, only old {len(summ['only_old'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
