"""BOX sticks phase 4a: the id crosswalk measured between two basin-wide generator runs. Read-only, files in, files out.

    python -m scripts.box_sticks_phase4_identity --prev <run dir> --new <run dir> --out <dir> [--pads 1,2,3]

A run dir is what scripts.box_sticks_phase3_basin writes (sticks_<basin>.jsonl, summary_<basin>.json). The previous run
is seeded (slot = position in its DSU x bench), then the new run is carried onto it with box.sticks.identity at several
corridor widths. Nothing is read from or written to the warehouse.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from box.sticks import identity as idn

CORRIDORS = (50.0, 100.0, 150.0, 220.0, 250.0, 330.0)
BASINS = ("delaware", "midland")


def load(run: Path, basin: str) -> tuple[list[idn.Stick], dict[str, dict]]:
    sticks, raw = [], {}
    with (run / f"sticks_{basin}.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            s = json.loads(line)
            raw[s["well_name"]] = s
            sticks.append(idn.Stick(s["well_name"], int(s["pad_id"]), s["bench"],
                                    tuple((tuple(leg["heel_xy"]), tuple(leg["toe_xy"])) for leg in s["legs"])))
    return sticks, raw


def seeded(sticks: list[idn.Stick]) -> list[idn.Stick]:
    slot = idn.seed(sticks)
    return [idn.Stick(s.key, s.pad_id, s.bench, s.legs, slot[s.key]) for s in sticks]


def measure(prev: Path, new: Path, out: Path, pads: list[int]) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    S: dict = {"prev": {}, "new": {}, "basins": {}}
    rows, detail = [], []
    for basin in BASINS:
        for k, d in (("prev", prev), ("new", new)):
            m = json.loads((d / f"summary_{basin}.json").read_text(encoding="utf-8"))
            S[k][basin] = {x: m[x] for x in ("generator_version", "pulled", "sticks", "legs")}
        P, praw = load(prev, basin)
        N, nraw = load(new, basin)
        P = seeded(P)
        for c in CORRIDORS:
            x = idn.crosswalk(P, N, corridor_ft=c)
            off = np.array([v[3] for v in x["carried"].values()]) if x["carried"] else np.array([0.0])
            rows.append({"basin": basin, "corridor_ft": c, "prev_sticks": len(P), "new_sticks": len(N), "carried": len(x["carried"]),
                         "new": len(x["new"]), "stopped": len(x["stopped"]), "carried_share_of_new": round(len(x["carried"]) / len(N), 4),
                         "offset_p50_ft": round(float(np.median(off)), 1), "offset_p90_ft": round(float(np.quantile(off, 0.9)), 1),
                         "offset_max_ft": round(float(off.max()), 1)})
        x = idn.crosswalk(P, N)
        pslot = {p.key: p.slot for p in P}
        # what a positional name would have done: the carried sticks whose position number in the DSU x bench changed
        renum = sum(1 for nk, (pk, *_rest) in x["carried"].items() if nk.rsplit("-", 1)[1] != pk.rsplit("-", 1)[1])
        dz = np.array([nraw[nk]["target_tvd_ft"] - praw[v[0]]["target_tvd_ft"] for nk, v in x["carried"].items()])
        ntype = sum(1 for nk, v in x["carried"].items() if nraw[nk]["well_type"] != praw[v[0]]["well_type"])
        why_new = Counter()
        pg = Counter((p.pad_id, p.bench) for p in P)
        for nk in x["new"]:
            s = nraw[nk]
            why_new["bench new to the DSU" if (s["pad_id"], s["bench"]) not in pg else "bench already in the DSU"] += 1
        ng = Counter((n.pad_id, n.bench) for n in N)
        why_stop = Counter("bench gone from the DSU" if (praw[k]["pad_id"], praw[k]["bench"]) not in ng else "bench still in the DSU" for k in x["stopped"])
        S["basins"][basin] = {"corridor_ft": idn.CORRIDOR_FT, "min_share": idn.MIN_SHARE, "carried": len(x["carried"]), "new": len(x["new"]),
                              "stopped": len(x["stopped"]), "carried_exact_position": int(sum(v[3] <= 1.0 for v in x["carried"].values())),
                              "carried_position_number_changed": renum, "carried_tvd_moved_over_50ft": int((np.abs(dz) > 50).sum()),
                              "carried_tvd_moved_over_150ft": int((np.abs(dz) > 150).sum()), "carried_well_type_changed": ntype,
                              "new_by": dict(why_new), "stopped_by": dict(why_stop),
                              "dsu_bench_count_changed": int(sum(pg[g] != ng[g] for g in set(pg) | set(ng))), "dsu_bench": len(set(pg) | set(ng))}
        for pid in pads:
            ps = [p for p in P if p.pad_id == pid]
            ns = [n for n in N if n.pad_id == pid]
            if not ps and not ns:
                continue
            seen = set()
            for n in ns:
                r = nraw[n.key]
                base = {"basin": basin, "pad_id": pid, "bench": n.bench, "new_name": n.key, "new_gb_x_ft": ";".join(f"{leg['gunbarrel_x_ft']:.0f}" for leg in r["legs"]),
                        "new_tvd_ft": r["target_tvd_ft"], "new_type": r["well_type"]}
                if n.key in x["carried"]:
                    pk, slot, sh, off = x["carried"][n.key]
                    seen.add(pk)
                    q = praw[pk]
                    detail.append(base | {"status": "carried", "slot": slot, "prev_name": pk, "share": sh, "offset_ft": off,
                                          "prev_gb_x_ft": ";".join(f"{leg['gunbarrel_x_ft']:.0f}" for leg in q["legs"]), "prev_tvd_ft": q["target_tvd_ft"]})
                else:
                    detail.append(base | {"status": "new", "slot": x["new"][n.key]})
            for p in ps:
                if p.key not in seen:
                    q = praw[p.key]
                    detail.append({"basin": basin, "pad_id": pid, "bench": p.bench, "status": "stopped", "slot": pslot[p.key], "prev_name": p.key,
                                   "prev_gb_x_ft": ";".join(f"{leg['gunbarrel_x_ft']:.0f}" for leg in q["legs"]), "prev_tvd_ft": q["target_tvd_ft"]})
    pd.DataFrame(rows).to_csv(out / "crosswalk_by_corridor.csv", index=False)
    if detail:
        cols = ["basin", "pad_id", "bench", "slot", "status", "prev_name", "new_name", "share", "offset_ft", "prev_gb_x_ft", "new_gb_x_ft", "prev_tvd_ft",
                "new_tvd_ft", "new_type"]
        pd.DataFrame(detail).reindex(columns=cols).sort_values(["basin", "pad_id", "bench", "slot"]).to_csv(out / "crosswalk_example_dsus.csv", index=False)
    (out / "crosswalk_summary.json").write_text(json.dumps(S, indent=1), encoding="utf-8")
    print(pd.DataFrame(rows).to_string(index=False))
    print(json.dumps(S, indent=1))
    return S


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prev", required=True, type=Path)
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--pads", default="")
    a = ap.parse_args(argv)
    measure(a.prev, a.new, a.out, [int(p) for p in a.pads.split(",") if p])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
