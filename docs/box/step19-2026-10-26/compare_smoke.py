"""Compare the step-19 smoke artifacts: old code (07d2ca2) vs new code, same warehouse snapshot. Exact equality."""
import pickle
import sys
from pathlib import Path

import numpy as np

W = Path("C:/Users/MichaelMast/Projects/engineering_db/.claude/worktrees")
A = pickle.load(open(W / "box-step19-base/runs/step19_smoke_base/run.pkl", "rb"))
B = pickle.load(open(W / "box-step19/runs/step19_smoke_new/run.pkl", "rb"))


def eq(a, b, path="", out=None):
    """Recursive exact comparison; returns list of differing paths."""
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}.{k} only in {'new' if k in b else 'old'}")
            else:
                eq(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            out.append(f"{path} len {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                eq(x, y, f"{path}[{i}]", out)
    elif isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        x, y = np.asarray(a), np.asarray(b)
        if x.shape != y.shape or not np.array_equal(x, y, equal_nan=x.dtype.kind == "f"):
            d = float(np.nanmax(np.abs(x - y) / np.maximum(np.abs(y), 1e-9))) if x.shape == y.shape and x.dtype.kind == "f" else None
            out.append(f"{path} array differs (max rel {d})")
    else:
        try:
            same = a == b or (isinstance(a, float) and isinstance(b, float) and np.isnan(a) and np.isnan(b))
        except Exception:
            same = repr(a) == repr(b)
        if not same:
            out.append(f"{path}: {a!r} vs {b!r}"[:200])
    return out


ra, rb = A["run"], B["run"]
skip = {"built_at", "code_sha"}
d_run = eq({k: v for k, v in ra.items() if k not in skip}, {k: v for k, v in rb.items() if k not in skip}, "run")
print("run header diffs:", d_run or "none")
print("results:", len(A["results"]), "vs", len(B["results"]))
d_res = eq(A["results"], B["results"], "results")
print("results diffs (streams/params/months_raw/months/analogs/flags):", d_res[:10] or "none")
d_loc = eq(A["locs"], B["locs"], "locs")
print("locs diffs:", d_loc[:10] or "none")
ua, ub = A["universe"], B["universe"]
print("universe rows old", len(ua), "new", len(ub))
drop = ua[~ua["stick_id"].isin(ub["stick_id"])]
print("  rows only in old:", len(drop), "basins", drop["basin"].value_counts().to_dict(), "coverage", drop["coverage"].value_counts().to_dict(),
      "benches", drop["bench"].value_counts().to_dict())
print("  rows only in new:", int((~ub["stick_id"].isin(ua["stick_id"])).sum()))
keep = ua[ua["stick_id"].isin(ub["stick_id"])].sort_values("stick_id").reset_index(drop=True)
ubs = ub.sort_values("stick_id").reset_index(drop=True)
cols = [c for c in keep.columns if c in ubs.columns]
print("  shared rows identical:", keep[cols].astype(str).equals(ubs[cols].astype(str)))
print("analog_meta equal:", A["analog_meta"].equals(B["analog_meta"]))
print("analog_cum_kft diffs:", eq(A["analog_cum_kft"], B["analog_cum_kft"], "cum")[:5] or "none")
n_months = sum(len(r.get("streams", {})) for r in B["results"])
print("stream month vectors compared:", n_months, "| per group equivalence old", {g: v["equivalence"] for g, v in ra["by_bench"].items()},
      "new", {g: v["equivalence"] for g, v in rb["by_bench"].items()})
print("data_through", ra["data_through"], rb["data_through"], "cutoff", ra["cutoff"], rb["cutoff"])
sys.exit(1 if (d_res or d_loc or [x for x in d_run if not x.startswith("run.basin")]) else 0)
