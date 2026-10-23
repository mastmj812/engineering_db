"""BOX step 16d — the frozen r2 evidence pack the production build reads (box/production16.py). Read-only; local files only.

    python -m scripts.box_step16d evidence --runs runs/step16c --out docs/box/step16d-2026-10-23

Per production group, from its 16c tuning views (WCA from the full fold, as accepted; every other group from the analog fold):
r2 x the PDP-proximity factor exactly as production applies it (docs/box/prox-2026-10-19 configuration + factor tables), the
per-cutoff package cells, the WCA / BS2_S walk-forward haircut table from those TUNING cells (D120 §4), and the disclosure in the
schema erebor reads. Writes r2_evidence.json (+ its sha256 in r2_evidence.sha256).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from box import production16 as p16
from box import step16c as c16

PROX = Path("docs") / "box" / "prox-2026-10-19"
GROUPS: tuple[str, ...] = (*p16.VALIDATED, *p16.PROVISIONAL)


def _json(o: object) -> object:
    if hasattr(o, "item"):
        return o.item()  # type: ignore[attr-defined]
    return str(o)


def cmd_evidence(a: argparse.Namespace) -> int:
    factors = p16.oil_factors(pd.read_csv(PROX / "config_children.csv.gz", dtype={"api10": str}),
                              pd.read_csv(PROX / "haircut_table_candidate.csv"))
    pack: dict[str, object] = {"selection": p16.SELECTION, "decision": "D121", "source_runs": str(a.runs),
                               "prox_tables": [str(PROX / "config_children.csv.gz"), str(PROX / "haircut_table_candidate.csv")], "groups": {}}
    for g in GROUPS:
        fold = "full" if g == "WCA" else "analog"
        run_dir = a.runs / (g if fold == "analog" else f"{g}_{fold}")
        meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        v = c16.load_views(run_dir, g, fold)
        ev = p16.group_evidence(g, v, factors)
        ev["source"] = {"run_dir": str(run_dir), "fold": fold, "head": meta["head"], "frozen_sha": meta["frozen_sha"], "n_view_rows": len(v)}
        pack["groups"][g] = ev  # type: ignore[index]
        h = ev["haircut"]
        o = ev["disclosure"]["hindcast_bias"]["oil"]["12"]
        print(f"{g}: spec {ev['spec']}, oil cum-12 raw {o['box_v2_pooled_bias']} disclosed {o['disclosed_bias']} ({o['disclosed_packages']} pkgs), thin cum-24 {ev['disclosure']['thin_control']['oil_cum24_bias']}"
              + (f", haircut oil 12/24/36/48 = {[round(h['oil'][k]['factor'], 3) for k in (12, 24, 36, 48)]}" if h else ""), flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(pack, indent=1, default=_json)
    (a.out / "r2_evidence.json").write_bytes(text.encode("utf-8"))  # LF; the digest is of the LF-normalised bytes
    (a.out / "r2_evidence.sha256").write_text(hashlib.sha256(text.encode("utf-8")).hexdigest() + "\n", encoding="utf-8")
    print(f"wrote {a.out / 'r2_evidence.json'}")
    return 0


def cmd_prox_measure(a: argparse.Namespace) -> int:
    """D116 on a new base run: the step-4 proximity measurement of run `--run-id`, its box rows read from `--box-db` (the rehearsal
    container or live), curated read from live; outcomes to --out, PUD links to --links-out (the run-10 reviewed files untouched)."""
    import psycopg

    from etl.db import get_connection
    from scripts import box_rehearsal as reh
    from scripts import box_step16d_prox as sdp

    live = get_connection()
    try:
        if a.box_db == "rehearsal":
            e = reh._box_env()
            box = psycopg.connect(host=e["PGHOST"], port=int(e["PGPORT"]), dbname=e["PGDATABASE"], user=e["PGUSER"], password=e["PGPASSWORD"])
        else:
            box = live
        try:
            r = sdp.run(box, live, a.run_id, a.prec_runs, a.out, a.links_out)
        finally:
            if box is not live:
                box.close()
    finally:
        live.close()
    m = r["meta"]
    print(f"run {m['run_id']}: {m['n_puds']:,} PUDs, {m['n_links']:,} links, identity {m['identity_ok']}, outcomes {m['outcomes']}; oil "
          f"{m['oil_mmbbl_before']:,.1f} -> {m['oil_mmbbl_after']:,.1f} MMbbl")
    return 0 if m["identity_ok"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evidence")
    e.add_argument("--runs", type=Path, default=Path("runs") / "step16c")
    e.add_argument("--out", type=Path, default=Path("docs") / "box" / "step16d-2026-10-23")
    m = sub.add_parser("prox-measure")
    m.add_argument("--run-id", type=int, required=True)
    m.add_argument("--box-db", choices=("rehearsal", "live"), default="rehearsal")
    m.add_argument("--prec-runs", type=Path, default=Path("runs") / "prox", help="the study's drilled-children inputs (precedent)")
    m.add_argument("--out", type=Path, default=Path("docs") / "box" / "step16d-2026-10-23" / "prox")
    m.add_argument("--links-out", type=Path, default=Path("runs") / "box16d_prox")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    return cmd_prox_measure(a) if a.cmd == "prox-measure" else cmd_evidence(a)


if __name__ == "__main__":
    raise SystemExit(main())
