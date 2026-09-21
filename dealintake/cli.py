"""python -m dealintake — deal-intake v2 runner.

  propose  <deal.gpkg|.zip> --run-dir runs/<deal>-<date>
           [--window MIN MAX --window-basis "who correlated, from what"]
      Upload units to narvi, snapshot, planned lateral, bench proposal,
      Gate 2. Writes proposal.json + proposal.md, then STOPS for review.

  evaluate --run-dir ... --benches WCA_1 WCA_2 WCB_1 [--spacing WCA_1=880 ...]
           [--radius BS2_S=10 ...] [--tc-groups WCA_2=unitA,unitB ...]
           [--no-anduin] [--no-short-history-transfer | --short-history-transfer N]
      Gates 2-7 on the confirmed benches; writes signals.json and the dossier.

  render   --run-dir ...        re-render dossier.md from signals.json.

Read-only against the warehouse; narvi/anduin in preview mode (see
dealintake.pipeline). anduin credentials: ANDUIN_EMAIL / ANDUIN_PASSWORD.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from dealintake import config as cfgmod
from dealintake import pipeline
from dealintake.clients.anduin import AnduinError
from dealintake.render import dossier


def _spacing(items: list[str]) -> dict[str, float]:
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        if not v:
            raise SystemExit(f"--spacing expects BENCH=FT, got {it!r}")
        out[k.strip()] = float(v)
    return out


def _radius(items: list[str]) -> dict[str, float]:
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        try:
            out[k.strip()] = float(v)
        except ValueError:
            raise SystemExit(f"--radius expects BENCH=MILES, got {it!r}") from None
        if out[k.strip()] <= 0:
            raise SystemExit(f"--radius must be > 0 mi, got {it!r}")
    return out


def _tc_groups(items: list[str]) -> dict[str, list[list[str]]]:
    out: dict[str, list[list[str]]] = {}
    for it in items or []:
        bench, _, spec = it.partition("=")
        if not spec:
            raise SystemExit(f"--tc-groups expects BENCH=unitA,unitB[;unitC], got {it!r}")
        out[bench.strip()] = [[u.strip() for u in g.split(",") if u.strip()] for g in spec.split(";") if g.strip()]
    return out


def _transfer_cutoff(a: argparse.Namespace, cfg: cfgmod.Config) -> int | None:
    """Short-history transfer cutoff (post-peak months): ON BY DEFAULT from the
    config; --short-history-transfer N overrides; --no-... disables."""
    if a.no_short_history_transfer:
        return None
    return a.short_history_transfer or cfg["type_curve"].get("short_history_transfer_months")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m dealintake", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="thresholds.yaml (default: the deal-intake skill's)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("propose")
    p.add_argument("deal")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--window", nargs=2, type=float, metavar=("MIN_FT", "MAX_FT"),
                   help="CORRELATED depth window, ft TVD (overrides the declared land depths)")
    p.add_argument("--window-basis", help="who correlated the window, from what log")

    e = sub.add_parser("evaluate")
    e.add_argument("--run-dir", required=True)
    e.add_argument("--benches", nargs="+", required=True, help="reviewer-confirmed formation_blueox codes")
    e.add_argument("--spacing", nargs="*", default=[], help="per-bench planned spacing, BENCH=FT")
    e.add_argument("--radius", nargs="*", default=[],
                   help="reviewer pool radius, BENCH=MILES — exactly that concentric radius, bypassing the "
                        "5/7.5/10 mi steps and the edge-trigger block (e.g. an emerging bench); decision-logged")
    e.add_argument("--no-anduin", action="store_true", help="skip anduin forecast/QC/TC preview")
    e.add_argument("--tc-groups", nargs="*", default=[],
                   help="reviewer TC grouping, BENCH=unitA,unitB[;unitC] — named groups, the rest pooled")
    e.add_argument("--short-history-transfer", type=int, metavar="POST_PEAK_MONTHS",
                   help="ON BY DEFAULT at type_curve.short_history_transfer_months (9): anduin cohort "
                        "transfer — short wells get the pool's long-well median Di/b + own peak qi; "
                        "overwrites their unlocked anduin forecasts. Pass N to override the cutoff")
    e.add_argument("--no-short-history-transfer", action="store_true",
                   help="keep the short wells' own autofits (no anduin writes beyond missing fits)")

    r = sub.add_parser("render")
    r.add_argument("--run-dir", required=True)

    a = ap.parse_args(argv)
    cfg = cfgmod.load(a.config)
    run_dir = Path(a.run_dir)

    if a.cmd == "propose":
        if a.window and not a.window_basis:
            raise SystemExit("--window needs --window-basis (the decision log records who correlated it)")
        prop = pipeline.propose(Path(a.deal), run_dir, cfg,
                                correlated_window=tuple(a.window) if a.window else None,
                                window_basis=a.window_basis)
        shutil.copy(cfg.path, run_dir / "thresholds.snapshot.yaml")
        (run_dir / "proposal.md").write_text(dossier.proposal_md(prop), encoding="utf-8")
        print(f"wrote {run_dir / 'proposal.md'} — review benches/window/spacing, then run evaluate")
    elif a.cmd == "evaluate":
        try:
            pipeline.evaluate(run_dir, cfg, benches=a.benches, spacing_ft=_spacing(a.spacing),
                              use_anduin=not a.no_anduin, tc_group_overrides=_tc_groups(a.tc_groups),
                              short_history_transfer=_transfer_cutoff(a, cfg),
                              radius_overrides=_radius(a.radius))
        except AnduinError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        print(f"wrote {dossier.render(run_dir)}")
    else:
        print(f"wrote {dossier.render(run_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
