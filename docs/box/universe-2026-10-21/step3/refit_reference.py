"""Reference refit only: 24 stable carried run-19 rows per group refitted on the pool rebuilt at run 19's data-through."""
import sys, time, json
from pathlib import Path
from types import SimpleNamespace
import numpy as np, pandas as pd
from scripts import box_pud_run as bpr
from box import production as pr
from dealintake import config as di_config
from etl.db import get_connection
def main():
    out = Path(sys.argv[1]); groups = sys.argv[2].split(",")
    S = bpr._load(Path(r"C:\Users\MichaelMast\Projects\engineering_db\runs\box16d"))
    run_s = S["run"]; sel = run_s["selection"]
    a = SimpleNamespace(selection="r2", wells=Path(run_s["wells_dir"]), limit=0, data_through=run_s["data_through"], workers=12)
    a.pack, a.pack_sha256 = bpr.load_evidence(Path(sel["evidence"]))
    u = S["universe"]; u = u[u["basin"] == "delaware"].copy(); u["category"] = "PUD"
    by = {l["stick_id"]: (l, r) for l, r in zip(S["locs"], S["results"], strict=True)}
    cfg = di_config.load(); t0 = time.time(); rows = []
    for b in groups:
        with get_connection() as conn:
            cov = u[u["coverage"].isin(pr.COVERED) & (u["prod_bench"] == b)]
            near = bpr.nearest_by_stick(conn, u, cov)
            stable = sorted(s for s, v in near.items() if bpr.same_gap(None if v is None else v[0], by[s][0]["spacing_ft"]))
            refs = sorted(int(x) for x in np.random.default_rng(20261030).choice(stable, size=24, replace=False))
            a.only = set(refs)
            B = bpr.build_bench(conn, a, u, b, cfg, t0)
        for l, r1 in zip(B["locs"], B["results"], strict=True):
            r0 = by[l["stick_id"]][1]
            row = {"group": b, "stick_id": l["stick_id"], "n_pool_rebuilt": B["record"]["n_pool"], "n_pool_source": run_s["by_bench"][b]["n_pool"],
                   "months_max_rel_diff": bpr.months_rel_diff(r1, r0),
                   "same_analogs": sorted(x["api10"] for x in r0["analogs"]) == sorted(x["api10"] for x in r1["analogs"])}
            for st in pr.STREAMS:
                e0, e1 = r0["streams"].get(st, {}).get("eur_raw"), r1["streams"].get(st, {}).get("eur_raw")
                row[f"{st}_eur_raw_rel"] = (e1 / e0 - 1) if e0 and e1 else None
            rows.append(row)
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"[{b}] done ({time.time()-t0:.0f} s)", flush=True)


if __name__ == '__main__':
    main()
