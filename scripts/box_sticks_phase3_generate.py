"""BOX sticks phase 3a: run the generator (box/sticks) over DSUs of the pilot and check the invariants of BARS.md.

Read-only: inputs come from the phase 3 cache frame; outputs are files (sticks.jsonl, ledger.csv, benches.csv,
dsus.csv, run_summary.json). Nothing is written to the warehouse.

    python -m scripts.box_sticks_phase3_generate --out <dir> --cache <cache> [--pads 10785,11331]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from box.sticks import checks, core, reads
from scripts import box_sticks_phase3_pilot as p3


def pilot_pads(ctx: reads.Context) -> dict[int, str]:
    return {int(p): name for name, a in p3.AREAS.items() for p in p3.area_pads(ctx.F, a)}


def run(out: Path, cache: Path, pads: list[int] | None) -> dict:
    ctx = reads.Context(cache)
    area = pilot_pads(ctx)
    ids = pads or sorted(area)
    link = reads.link_fn()
    cfg = {b: reads.default_cfg(b) for b in ("delaware", "midland")}
    sticks, ledger, benches, dsus = [], [], [], []
    viol: dict[str, list[str]] = {k: [] for k in ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8")}
    for pid in ids:
        d = ctx.dsu(pid)
        res = core.generate_dsu(d, cfg[d.basin], link)
        for k, v in checks.run_all(res, d, cfg[d.basin], link).items():
            viol[k] += [f"{pid}: {x}" for x in v]
        sticks += res.sticks
        ledger += res.ledger
        benches += res.benches
        dsus.append(res.meta | {"area": area.get(pid, ""), "sticks": len(res.sticks), "legs": sum(s["n_legs"] for s in res.sticks),
                                "wells_read": len(d.wells), "wells_member": sum(w.member for w in d.wells)})
    out.mkdir(parents=True, exist_ok=True)
    (out / "sticks.jsonl").write_text("".join(json.dumps(s, sort_keys=True) + "\n" for s in sticks), encoding="utf-8", newline="\n")
    L, B, D = pd.DataFrame(ledger), pd.DataFrame(benches), pd.DataFrame(dsus)
    L.to_csv(out / "ledger.csv", index=False)
    B.to_csv(out / "benches.csv", index=False)
    D.to_csv(out / "dsus.csv", index=False)
    S = {"generator_version": core.VERSION, "tags": ctx.F["tags"], "pulled": ctx.F["pulled"], "dsus": len(ids), "sticks": len(sticks),
         "legs": int(D["legs"].sum()), "by_area": D.groupby("area")[["sticks", "legs"]].sum().to_dict("index"),
         "well_type": D["well_type"].value_counts(dropna=False).to_dict(), "azimuth_basis": D["azimuth_basis"].value_counts().to_dict(),
         "row_reasons": dict(Counter(L.loc[L["status"] == "culled", "reason"])) if len(L) else {},
         "bench_reasons": dict(Counter(B.loc[B["no_row_reason"] != "", "no_row_reason"])),
         "grid": B["grid"].value_counts().to_dict() if "grid" in B else {},
         "violations": {k: len(v) for k, v in viol.items()}, "violation_examples": {k: v[:8] for k, v in viol.items() if v}}
    (out / "run_summary.json").write_text(json.dumps(S, indent=1, default=str), encoding="utf-8")
    print(json.dumps(S, indent=1, default=str))
    return S


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--pads", default="")
    a = ap.parse_args(argv)
    run(a.out, a.cache, [int(x) for x in a.pads.split(",") if x] or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
