"""formation_blueox scoreboard (read-only) — step 0 of docs/formation_tag_redesign/PLAN.md.

    python -m scripts.tag_scoreboard --out docs/formation_tag_redesign/baseline-<date> [--cache <dir>]

Scores the three baseline candidates (box.tag_scoreboard.CANDIDATES) on clean producing horizontals in Delaware
and Midland. Writes CSV tables + summary.json. Every query runs under SET TRANSACTION READ ONLY. Nothing is written
to the warehouse. --cache keeps the pulled frames (pickles) so a re-render doesn't re-pull.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from box import extent_package as pkg
from box import tag_scoreboard as sb
from box import tops_qc as tq
from box import tops_qc_report as rep

RADII_MI = (1.0, 0.5)


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def pull(cache: Path | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    if cache and (cache / "wells.pkl").exists() and (cache / "stations.pkl").exists():
        return pd.read_pickle(cache / "wells.pkl"), pd.read_pickle(cache / "stations.pkl")
    from etl.db import get_connection

    with get_connection() as conn:
        w = sb.pull_wells(conn)
        ids = w.loc[(w["basin"] == "delaware") & w["lat_tvd_p50_ft"].notna(), "api10"].tolist()
        st = rep._read(conn, rep._STATIONS_SQL, {"a": ids})
    for c in ("lon", "lat", "tvd"):
        st[c] = pd.to_numeric(st[c], errors="coerce")
    st["api10"] = st["api10"].astype(str)
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        w.to_pickle(cache / "wells.pkl")
        st.to_pickle(cache / "stations.pkl")
    return w, st


def grid_frame(clean: pd.DataFrame, st: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, pd.DataFrame]:
    """Delaware evidence stations (survey where the well has one, else the midpoint at tvd_ft), their grid depths
    (sampled once) and the per-well midpoint frame used for control distances."""
    de = clean[clean["basin"] == "delaware"]
    s = st[st["api10"].isin(set(de.loc[de["depth_source"] == "survey", "api10"]))][["api10", "lon", "lat", "tvd"]].copy()
    m = de[(de["depth_source"] != "survey") & de["midpoint_lon"].notna()][["api10", "midpoint_lon", "midpoint_lat", "depth_ft"]]
    m = m.rename(columns={"midpoint_lon": "lon", "midpoint_lat": "lat", "depth_ft": "tvd"})
    stations = pd.concat([s, m], ignore_index=True).dropna(subset=["lon", "lat", "tvd"])
    stations["x"], stations["y"] = rep._to_geology(stations["lon"].to_numpy(), stations["lat"].to_numpy())
    stack = tq.load_stack(pkg.GRID_DIR)
    depths = tq.sample_stack(stack, stations[["x", "y"]].to_numpy(float))
    mid = de[de["midpoint_lon"].notna()][["api10", "midpoint_lon", "midpoint_lat"]].copy()
    mid["x"], mid["y"] = rep._to_geology(mid["midpoint_lon"].to_numpy(), mid["midpoint_lat"].to_numpy())
    return stations, depths, mid


def control_distances(mid: pd.DataFrame) -> dict[str, np.ndarray]:
    xy = mid[["x", "y"]].to_numpy(float)
    surfaces = sorted({s for tb in tq.TAG_INTERVAL.values() for s in tb})
    return {s: pkg.dist_to_control(s, xy) for s in surfaces}


def run(out: Path, cache: Path | None, p: sb.Params = sb.DEFAULT) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    w, st = pull(cache)
    order = sb.bench_order()
    labels = sb.labelled_set()
    labels.to_csv(out / "labelled_set.csv", index=False)
    summary: dict[str, Any] = {"built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"),
                               "git_sha": _git_sha(), "params": p.__dict__, "candidates": sb.CANDIDATES,
                               "pulled_wells": len(w), "labelled": labels["tier"].value_counts().to_dict(), "bases": {}}

    for basis in ("best", "tvd_ft"):
        d = sb.evidence_depth(w, basis)
        clean = d[d["clean"]].reset_index(drop=True)
        clean["vintage"] = sb.vintage(clean["first_production_date"])
        pairs = {r: sb.neighbour_pairs(clean, r * sb.M_PER_MI) for r in RADII_MI}
        pairs_close = pairs[min(RADII_MI)]
        bsum: dict[str, Any] = {"clean": clean["basin"].value_counts().to_dict(),
                                "depth_source": clean.groupby(["basin", "depth_source"]).size().rename("n").reset_index().to_dict("records"),
                                "excluded_planned": int(d["planned"].fillna(False).astype(bool).sum()),
                                "candidates": {}}
        if basis == "best":
            stations, depths, mid = grid_frame(clean, st)
            dist = control_distances(mid)
        for cand in sb.CANDIDATES:
            tag = clean[cand].fillna("(unmapped)")
            c = clean.assign(**{cand: tag})
            csum: dict[str, Any] = {}
            for r in RADII_MI:
                res = sb.score_candidate(c, cand, pairs[r], pairs_close, order, labels, p)
                f = res["frame"]
                bt = sb.band_table(f, ["basin"])
                csum[f"band_r{r}"] = bt.set_index("basin")["disagree_pct"].round(2).to_dict()
                if r != 1.0:
                    continue
                pre = out / f"{basis}_{cand}"
                bt.to_csv(f"{pre}_band_by_basin.csv", index=False)
                sb.band_table(f, ["basin", cand]).query("wells >= 100").to_csv(f"{pre}_band_by_bench.csv", index=False)
                sb.band_table(f, ["basin", "live_source"]).to_csv(f"{pre}_band_by_source.csv", index=False)
                sb.band_table(f, ["basin", "vintage"]).to_csv(f"{pre}_band_by_vintage.csv", index=False)
                sb.band_table(f, ["basin", "county"]).query("wells >= 200").to_csv(f"{pre}_band_by_county.csv", index=False)
                inv = res["inversions"]
                it = sb.inversion_table(inv)
                it.to_csv(f"{pre}_inversions.csv", index=False)
                inv["vintage"] = clean["vintage"].to_numpy()[inv["i"]]
                iv = inv[inv["rank_gap"] == 1].groupby(["basin", "vintage"])["inverted"].agg(pairs="size", inverted="sum").reset_index()
                iv["inverted_pct"] = 100 * iv["inverted"] / iv["pairs"]
                iv.to_csv(f"{pre}_inversions_adjacent_by_vintage.csv", index=False)
                res["separation"].to_csv(f"{pre}_band_separation.csv", index=False)
                res["labels"].to_csv(f"{pre}_labels.csv", index=False)
                f[f["band_status"] == "disagree"][["api10", "basin", "county", "operator", "well_name", cand, "closer_bench",
                                                   "depth_ft", "depth_source", "own_band_med", "closer_by_ft", "live_source",
                                                   "first_production_date"]].to_csv(f"{pre}_disagree_wells.csv", index=False)
                csum["inversion"] = it.round(2).to_dict("records")
                csum["separation"] = res["separation"].round(1).to_dict("records")
                csum["labels"] = res["labels"].round(1).to_dict("records")
            if basis == "best":
                de = clean[clean["basin"] == "delaware"].set_index("api10")
                tags = de[cand]
                gv = sb.grid_verdicts(stations, depths, tags, de["county"])
                gv["grid_controlled"] = pd.Series(sb.controlled(tags.reindex(mid["api10"]), mid[["x", "y"]].to_numpy(float),
                                                                dist, pkg.TRUST_MAX_FT), index=mid["api10"].to_numpy()).reindex(gv.index).fillna(False)
                g = de[[cand, "county"]].join(gv)
                gt = sb.grid_table(g, [cand])
                gt.to_csv(out / f"{basis}_{cand}_grid_by_bench.csv", index=False)
                sb.grid_table(g.assign(all="all"), ["all"]).to_csv(out / f"{basis}_{cand}_grid_overall.csv", index=False)
                sb.grid_table(g, ["county"]).to_csv(out / f"{basis}_{cand}_grid_by_county.csv", index=False)
                g["grid_verdict"].value_counts().rename_axis("verdict").reset_index().to_csv(out / f"{basis}_{cand}_grid_verdicts.csv", index=False)
                csum["grid_overall"] = sb.grid_table(g.assign(all="all"), ["all"]).round(2).to_dict("records")
            bsum["candidates"][cand] = csum
        summary["bases"][basis] = bsum
        print(f"[{basis}] clean {len(clean):,}", {k: v.get("band_r1.0") for k, v in bsum["candidates"].items()}, flush=True)

    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.out, a.cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
