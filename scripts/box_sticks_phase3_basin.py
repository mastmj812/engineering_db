"""BOX sticks phase 3b: the generator over every DSU polygon of a basin, with the invariants of BARS.md checked per DSU.

Read-only: inputs come from the phase 3 cache frame; outputs are files in --out (large; not for the repo). Nothing is
written to the warehouse.

    python -m scripts.box_sticks_phase3_basin --out <dir> --cache <cache> --basin delaware|midland [--limit N]
"""
from __future__ import annotations

import argparse
import json
import time
import traceback
from collections import Counter
from pathlib import Path

import pandas as pd

from box.sticks import checks, core, reads

STICK_COLS = ("pad_id", "bench", "well_name", "well_type", "n_legs", "completed_lateral_ft", "target_tvd_ft", "lateral_azimuth_deg", "azimuth_basis", "flags")


def run(out: Path, cache: Path, basin: str, limit: int | None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    ctx = reads.Context(cache)
    pads = ctx.pads[ctx.pads["basin"] == basin]
    with_bench = set(ctx.F["db"]["pad_id"])
    ids = [int(p) for p in pads.index if p in with_bench][:limit]
    link, cfg = reads.link_fn(), reads.default_cfg(basin)
    sticks, ledger, benches, dsus, errors = [], [], [], [], []
    viol: Counter = Counter()
    examples: dict[str, list[str]] = {}
    t0 = time.time()
    with (out / f"sticks_{basin}.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n, pid in enumerate(ids, 1):
            try:
                d = ctx.dsu(pid)
                res = core.generate_dsu(d, cfg, link)
                for k, v in checks.run_all(res, d, cfg, link).items():
                    viol[k] += len(v)
                    if v and len(examples.setdefault(k, [])) < 10:
                        examples[k].append(f"{pid}: {v[0]}")
            except Exception as e:  # noqa: BLE001                                     # one odd polygon must not stop the basin
                errors.append({"pad_id": pid, "error": f"{type(e).__name__}: {e}", "where": traceback.format_exc().strip().splitlines()[-3].strip()})
                continue
            for s in res.sticks:
                fh.write(json.dumps(s, sort_keys=True) + "\n")
                sticks.append({k: (",".join(s[k]) if k == "flags" else s.get(k)) for k in STICK_COLS} | {
                    "rung": s["tvd_basis"].get("rung"), "spacing_final_ft": s["spacing_basis"].get("final_ft"), "grid": s["spacing_basis"].get("grid")})
            ledger += [{k: r[k] for k in ("pad_id", "code", "row", "status", "reason")} for r in res.ledger]
            benches += res.benches
            dsus.append(res.meta | {"sticks": len(res.sticks), "legs": sum(s["n_legs"] for s in res.sticks), "wells_read": len(d.wells),
                                    "wells_member": sum(w.member for w in d.wells)})
            if n % 250 == 0:
                print(f"{basin} {n}/{len(ids)} dsus, {len(sticks)} sticks, {len(errors)} errors, {time.time() - t0:.0f} s", flush=True)
    K, L, B, D = pd.DataFrame(sticks), pd.DataFrame(ledger), pd.DataFrame(benches), pd.DataFrame(dsus)
    for name, df in (("sticks", K), ("ledger", L), ("benches", B), ("dsus", D), ("errors", pd.DataFrame(errors))):
        df.to_csv(out / f"{name}_{basin}.csv", index=False)
    S = {"generator_version": core.VERSION, "tags": ctx.F["tags"], "pulled": ctx.F["pulled"], "basin": basin, "dsus_run": len(ids),
         "dsus_with_no_bench": int(len(pads) - len([p for p in pads.index if p in with_bench])), "errors": len(errors),
         "sticks": len(K), "legs": int(K["n_legs"].sum()) if len(K) else 0, "completed_lateral_ft": float(K["completed_lateral_ft"].sum()) if len(K) else 0.0,
         "well_type_dsu": D["well_type"].value_counts(dropna=False).to_dict(), "azimuth_basis": D["azimuth_basis"].value_counts().to_dict(),
         "row_reasons": dict(Counter(L.loc[L["status"] == "culled", "reason"])) if len(L) else {},
         "bench_reasons": dict(Counter(B.loc[B["no_row_reason"] != "", "no_row_reason"])), "grid": B["grid"].value_counts().to_dict() if "grid" in B else {},
         "violations": dict(viol), "violation_examples": examples, "seconds": round(time.time() - t0)}
    (out / f"summary_{basin}.json").write_text(json.dumps(S, indent=1, default=str), encoding="utf-8")
    print(json.dumps(S, indent=1, default=str))
    return S


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--basin", required=True, choices=("delaware", "midland"))
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    run(a.out, a.cache, a.basin, a.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
