"""BOX step 1c — apply the ratified QC rule and write the final well sets (read-only).

    python -m scripts.box_apply_rule [--out docs/box/step1-YYYY-MM-DD]

Re-pulls and re-scores the Delaware producing horizontals (box.bench_qc), applies
box.qc_rule (class gate + sql/23 second vote + GOR veto + A-prime + no Bone
Spring -> Wolfcamp; pooled WCA per D19/D20) and writes, per pilot pool,
wells_final_<pool>.csv plus rule_summary.json. These are the gate-1 well sets
that step 2 reads. Nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

from box.bench_qc import PILOT_BENCHES, pull_delaware_producers, score_consensus
from box.flag_cards import pool
from box.qc_rule import apply_rule, load_verdicts, rule_summary, write_final_sets
from etl.db import get_connection


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("docs") / "box" / f"step1-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}")
    ap.add_argument("--bench", nargs="*", default=list(PILOT_BENCHES))
    ap.add_argument("--verdicts", type=Path, action="append", default=None,
                    help="cards_sample.csv with Michael's AGREE/REJECT verdicts (default: <out>/cards_sample.csv if present); repeatable")
    a = ap.parse_args(argv)
    t0 = time.time()
    pools = tuple(sorted({pool(b) for b in a.bench}))
    paths = a.verdicts if a.verdicts is not None else [p for p in [a.out / "cards_sample.csv"] if p.exists()]
    verdicts: dict[str, str] = {}
    for pth in paths:
        verdicts.update(load_verdicts(pth))
    with get_connection() as conn:
        df = score_consensus(pull_delaware_producers(conn))
    df = apply_rule(df, verdicts)
    a.out.mkdir(parents=True, exist_ok=True)
    write_final_sets(df, a.out, pools)
    s = rule_summary(df, pools)
    s["built_at"] = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    s["asof"] = str(df.attrs.get("asof"))
    s["verdicts_loaded"] = {"files": [str(p) for p in paths], "agree": sum(v == "AGREE" for v in verdicts.values()), "reject": sum(v == "REJECT" for v in verdicts.values())}
    print(f"verdicts: {s['verdicts_loaded']['agree']} agree / {s['verdicts_loaded']['reject']} reject from {len(paths)} file(s)")
    (a.out / "rule_summary.json").write_text(json.dumps(s, indent=1, default=str), encoding="utf-8")
    for pb in pools:
        r = s[pb]
        print(
            f"{pb:>6}: tagged {r['n_tagged']:,} -> after rule {r['n_after_rule']:,} "
            f"(out {r['reassigned_out']}, in {r['reassigned_in']}, tvd_suspect {r['tvd_suspect']}); "
            f"depth witnesses {r['depth_witnesses']:,}; cohort {r['cohort_after']:,}"
        )
    if s["unknown_classes"]:
        print("uncalibrated classes (tag kept):", ", ".join(s["unknown_classes"]))
    print(f"wrote {a.out / 'wells_final_<pool>.csv'} + rule_summary.json  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
