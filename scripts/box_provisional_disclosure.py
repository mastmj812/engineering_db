"""BOX provisional benches (D105): the bias each workup discloses — DB-free, from the tuning runs.

    python -m scripts.box_provisional_disclosure [--runs runs/box15t] [--out docs/box/step15-provisional-2026-10-17]

Reads the `scripts.box_acceptance --bench <B> --fold analog` runs of BS2_C and AVA_0 / AVA_1 / AVA_2 (raw box_v2). AVA is
also pooled (0 + 1 + 2) for the measurement — the disclosure a too-thin single AVA bench carries (step 14: 37–71 packages each).
Writes disclosure.csv, by_vintage.csv, summary.json and index.html. Nothing is stored.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from box import provisional as pv
from box import rehearse9b as r9
from box.edge_gap_report import _CSS, _table

GROUPS: dict[str, tuple[str, ...]] = {"BS2_C": ("BS2_C",), "AVA_0": ("AVA_0",), "AVA_1": ("AVA_1",), "AVA_2": ("AVA_2",),
                                      "AVA (0+1+2 pooled)": ("AVA_0", "AVA_1", "AVA_2")}
VARIANT = "box_v2"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=Path("runs") / "box15t")
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / "step15-provisional-2026-10-17")
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    frames = {}
    for b in sorted({x for m in GROUPS.values() for x in m}):
        v = r9.load_frames(a.runs / b, f"tuning_v2_{b}_analog")
        v["pkg"] = b + "|" + v["pkg"].astype(str)
        frames[b] = pv.package_frame(v, VARIANT)
    disc, vint = [], []
    for g, members in GROUPS.items():
        pk = pd.concat([frames[m] for m in members], ignore_index=True)
        disc.append(pv.disclosure(pk, g))
        vint.append(pv.by_vintage(pk, g))
    disc, vint = pd.concat(disc, ignore_index=True), pd.concat(vint, ignore_index=True)
    disc.to_csv(a.out / "disclosure.csv", index=False)
    vint.to_csv(a.out / "by_vintage.csv", index=False)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    (a.out / "summary.json").write_text(json.dumps({"built_at": built, "code_sha": sha, "variant": VARIANT, "n_boot": pv.N_BOOT, "seed": pv.SEED,
                                                    "groups": {k: list(m) for k, m in GROUPS.items()}}, indent=1), encoding="utf-8")
    pct = {c: "+.1%" for c in ("bias", "range_lo", "range_hi")}
    vp = vint.pivot_table(index=["bench", "stream", "horizon"], columns="cutoff", values="bias").reset_index()
    vp.columns = [str(c)[:4] if str(c)[:2] == "20" else c for c in vp.columns]
    vn = vint.pivot_table(index=["bench", "stream", "horizon"], columns="cutoff", values="n_packages").reset_index()
    vn.columns = [str(c)[:4] if str(c)[:2] == "20" else c for c in vn.columns]
    page = ["<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>BOX provisional disclosure</title>",
            f"<style>{_CSS} body{{overflow-x:hidden}} table{{display:block;overflow-x:auto;max-width:100%}}</style></head><body>",
            "<h1>BOX provisional benches (D105) — the bias each workup discloses</h1>",
            (f"<div class=meta>built {built} · code {sha[:7]} · raw box_v2 on the TUNING packages of each bench (D52 holdout excluded), all cutoffs 2019–2024 · "
             "bias = mean over packages of Σ actual / Σ forecast − 1 (+ = forecast LOW) · range = 95 % cluster bootstrap over 3-mi blocks "
             f"({pv.N_BOOT:,} draws) · measured in-sample, never out-of-time validated · nothing stored</div>"),
            "<h2>Pooled disclosure (what the workup states)</h2>", _table(disc, pct),
            "<h2>Bias by cutoff (the next-12-months cohort scored at each cutoff)</h2>", _table(vp, {c: "+.1%" for c in vp.columns if str(c).isdigit()}),
            "<h3>Packages by cutoff</h3>", _table(vn, {c: ".0f" for c in vn.columns if str(c).isdigit()}), "</body></html>"]
    (a.out / "index.html").write_text("\n".join(page), encoding="utf-8")
    print(disc.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
