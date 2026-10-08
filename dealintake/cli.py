r"""python -m dealintake (or .\di from the repo root) — deal-intake v2 runner.

A first pass on a land deal is an ECONOMIC SCREEN (Michael 2026-10-08): gpkg ->
dossier -> handoff -> Blue Ox drop; Steven's econs pick where to look harder.

  .\di login
      once: anduin email + password (hidden prompt) -> a 30-day token kept in the
      Windows Credential Manager. ANDUIN_EMAIL / ANDUIN_PASSWORD still win if set.

  propose  <deal.gpkg|.zip> --run-dir runs/<deal>-<date>
           [--window MIN MAX --window-basis "who correlated, from what"]
      Upload units to narvi, snapshot, planned lateral, bench proposal,
      Gate 2. Writes proposal.json + proposal.md, then STOPS for review.

  evaluate <run> [--benches WCA_1 WCA_2 WCB_1] [--spacing WCA_1=880 ...]
           (no --benches = the reviewer's per-unit benches.yaml from propose)
           [--cohort BS3_C=pool ...] [--radius BS2_S=10 ...] [--tc-groups WCA_2=unitA,unitB ...]
           [--no-anduin] [--no-short-history-transfer | --short-history-transfer N] [--forget]
      Gates 2-7 on the confirmed benches; writes signals.json and the dossier.
      Reviewer flags are REMEMBERED per run (evaluate_args.json): a re-run is
      just `.\di evaluate rallycaps`.

  handoff  <run> [--deal "Rally Caps" --codename "RALLY CAPS"] [--apply [--new-version] [--replace]]
      Gate 8. Without --apply: DRY RUN -> handoff_plan.json + handoff.html.
      --apply WRITES the narvi scenarios (one per DSU), the anduin type curves,
      deal and Blue Ox config; anything edited since the last handoff is refused.
      Deal + codename are remembered per run after the first time.

  render   <run> [--fetch-sticks]
      re-render dossier.html + dossier.md from signals.json (--fetch-sticks first
      pulls the TC wells' laterals for the maps — needed for runs before 2026-10-06).

<run> = a deal name (`rallycaps` -> the newest runs/rallycaps* folder) or a path;
--run-dir still works. Read-only against the warehouse; narvi/anduin in preview
mode except `handoff --apply` (see dealintake.pipeline / dealintake.handoff).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from dealintake import config as cfgmod
from dealintake import credentials, handoff, pipeline
from dealintake import warehouse as wh
from dealintake.clients.anduin import Anduin, AnduinError
from dealintake.clients.narvi import Narvi
from dealintake.pipeline import write_json
from dealintake.render import dossier, dossier_html, handoff_html, review


def _spacing(items: list[str]) -> dict[str, float]:
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        if not v:
            raise SystemExit(f"--spacing expects BENCH=FT, got {it!r}")
        out[k.strip()] = float(v)
    return out


def _cohort(items: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        b, _, v = it.partition("=")
        try:
            out[b.strip()] = 0 if v.strip().lower() == "pool" else int(v)
        except ValueError:
            raise SystemExit(f"--cohort expects BENCH=N or BENCH=pool, got {it!r}") from None
        if not b.strip() or out[b.strip()] < 0 or (out[b.strip()] == 0 and v.strip().lower() != "pool"):
            raise SystemExit(f"--cohort expects BENCH=N (N >= 1) or BENCH=pool, got {it!r}")
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


RUNS = Path(__file__).resolve().parents[1] / "runs"
EVALUATE_ARGS = "evaluate_args.json"
HANDOFF_ARGS = "handoff_args.json"


def _run_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("run", nargs="?", help="deal name (e.g. rallycaps -> the newest runs/rallycaps-* folder) or a path")
    p.add_argument("--run-dir", help="the run folder (same as the positional)")


def _resolve_run(a: argparse.Namespace) -> Path:
    """`rallycaps` -> the newest runs/rallycaps* folder that has a proposal."""
    name = a.run or a.run_dir
    if not name:
        raise SystemExit(r"name the run: e.g.  .\di evaluate rallycaps   (or --run-dir runs/<folder>)")
    p = Path(name)
    if (p / "proposal.json").exists():
        return p
    key = name.lower().replace(" ", "")
    cands = [d for d in RUNS.glob("*") if d.is_dir() and d.name.lower().startswith(key) and (d / "proposal.json").exists()]
    if not cands:
        raise SystemExit(f"no run folder for {name!r} under {RUNS}")
    best = max(cands, key=lambda d: max(f.stat().st_mtime for f in d.iterdir()))
    if len(cands) > 1:
        print(f"run: {best.name} (newest of {', '.join(sorted(c.name for c in cands))})")
    return best


def _remember_evaluate(run_dir: Path, a: argparse.Namespace) -> None:
    """Reviewer flags persist per run (evaluate_args.json): a re-run needs only the
    run name; today's flags replace the remembered ones bench by bench."""
    f = run_dir / EVALUATE_ARGS
    saved = {} if a.forget or not f.exists() else json.loads(f.read_text(encoding="utf-8"))

    def by_bench(name: str) -> list[str]:
        merged = {it.partition("=")[0].strip(): it for it in saved.get(name, [])}
        merged.update({it.partition("=")[0].strip(): it for it in getattr(a, name) or []})
        return list(merged.values())

    for name in ("spacing", "cohort", "radius", "tc_groups"):
        setattr(a, name, by_bench(name))
    a.tc_single = sorted(set(saved.get("tc_single", [])) | set(a.tc_single or []))
    if a.benches is None:
        a.benches = saved.get("benches")
    if not (a.short_history_transfer or a.no_short_history_transfer):
        a.short_history_transfer = saved.get("short_history_transfer")
        a.no_short_history_transfer = bool(saved.get("no_short_history_transfer"))
    keep = {k: getattr(a, k) for k in ("benches", "spacing", "cohort", "radius", "tc_groups", "tc_single",
                                       "short_history_transfer", "no_short_history_transfer")}
    f.write_text(json.dumps(keep, indent=1), encoding="utf-8")
    shown = {k: v for k, v in keep.items() if v}
    if shown:
        print(f"reviewer flags in effect (remembered in {EVALUATE_ARGS}):")
        for k, v in shown.items():
            print(f"  --{k.replace('_', '-')} {' '.join(v) if isinstance(v, list) else v}")


def _handoff(run_dir: Path, a: argparse.Namespace, cfg: cfgmod.Config) -> int:
    f = run_dir / HANDOFF_ARGS
    saved = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    deal, codename = a.deal or saved.get("deal"), a.codename or saved.get("codename")
    if not deal or not codename:
        raise SystemExit('first handoff for this run: pass --deal "Rally Caps" --codename "RALLY CAPS" '
                         "(the codename = the ArcMap / Deal Folder name); both are remembered after that")
    f.write_text(json.dumps({"deal": deal, "codename": codename}, indent=1), encoding="utf-8")
    narvi = Narvi()
    with wh.connect() as conn:
        P = handoff.plan(run_dir, narvi, cfg, deal=deal, codename=codename, conn=conn)
    write_json(run_dir / "handoff_plan.json", P)
    print(f"{P['status']}: {len(P['units'])} narvi scenarios, {len(P['curves'])} curves -> "
          f"anduin deal {deal!r}, Blue Ox codename {codename!r}")
    for b in P["blocked"]:
        print(f"BLOCKED: {b}")
    if not a.apply:
        (run_dir / "handoff_applied.json").unlink(missing_ok=True)
        print(f"wrote {handoff_html.render(run_dir)} - review it, then:  .\\di handoff {a.run or run_dir} --apply")
        return 0 if P["status"] == "READY" else 3
    try:
        res = handoff.apply(P, run_dir, narvi, Anduin(), wh.connect, new_version=a.new_version, replace=a.replace)
    except (handoff.HandoffRefused, AnduinError) as e:
        print(f"STOPPED: {e}", file=sys.stderr)
        handoff_html.render(run_dir)
        return 3
    write_json(run_dir / "handoff_applied.json", res)
    for n in res["narvi"]:
        print(f"narvi {n['scenario']}: {n['action']}" + ("" if n.get("verified", True) else " - NOT VERIFIED"))
    for c in res["curves"]:
        d = c.get("diff_pct")
        print(f"anduin {c['name']}: {c['action']}" + ("" if d is None else f" (oil EUR {d:+.2f}% vs dossier preview)"))
    print(f"anduin deal {res['deal']['name']}: Blue Ox config saved - {res['deal']['zones']} zones, "
          f"{res['deal']['scenarios_pinned']} narvi scenarios pinned")
    print(f"wrote {handoff_html.render(run_dir)} - next: the blueox-curve-drop skill (build + sweep)")
    return 0


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

    lg = sub.add_parser("login", help="log in to anduin once; the 30-day token is kept in Windows Credential Manager")
    lg.add_argument("--url", help="anduin URL (default ANDUIN_URL or http://localhost:8000)")

    e = sub.add_parser("evaluate")
    _run_args(e)
    e.add_argument("--forget", action="store_true",
                   help="drop the reviewer flags this run remembered (evaluate_args.json) before applying today's")
    e.add_argument("--benches", nargs="+",
                   help="ONE deal-wide bench list (simple deals). Omit it to use the reviewer's per-unit "
                        "benches.yaml in the run dir — required for depth-severed stacked DSUs")
    e.add_argument("--spacing", nargs="*", default=[], help="per-bench planned spacing, BENCH=FT")
    e.add_argument("--cohort", nargs="*", default=[],
                   help="reviewer cohort size, BENCH=N or BENCH=pool — that bench's type curve is built from the nearest "
                        "N pool wells (pool = every eligible well) instead of type_curve.max_wells; decision-logged")
    e.add_argument("--radius", nargs="*", default=[],
                   help="reviewer pool radius, BENCH=MILES — exactly that concentric radius, bypassing the "
                        "5/7.5/10 mi steps and the edge-trigger block (e.g. an emerging bench); decision-logged")
    e.add_argument("--no-anduin", action="store_true", help="skip anduin forecast/QC/TC preview")
    e.add_argument("--tc-single", nargs="*", default=[], metavar="BENCH",
                   help="reviewer: ONE type curve for this bench, whatever the split test said "
                        "(escalated gradient with no clean break / pool without a multiplier); decision-logged")
    e.add_argument("--tc-groups", nargs="*", default=[],
                   help="reviewer TC grouping, BENCH=unitA,unitB[;unitC] — named groups, the rest pooled")
    e.add_argument("--short-history-transfer", type=int, metavar="POST_PEAK_MONTHS",
                   help="ON BY DEFAULT at type_curve.short_history_transfer_months (9): anduin cohort "
                        "transfer — short wells get the pool's long-well median Di/b + own peak qi; "
                        "overwrites their unlocked anduin forecasts. Pass N to override the cutoff")
    e.add_argument("--no-short-history-transfer", action="store_true",
                   help="keep the short wells' own autofits (no anduin writes beyond missing fits)")

    r = sub.add_parser("render")
    _run_args(r)
    r.add_argument("--fetch-sticks", action="store_true",
                   help="(re)write well_sticks.json from the warehouse (read-only) so the maps draw laterals")
    h = sub.add_parser("handoff", help="gate 8: plan (dry run, handoff.html) or --apply the narvi + anduin saves")
    _run_args(h)
    h.add_argument("--deal", help="anduin deal name, e.g. 'Rally Caps' (remembered per run)")
    h.add_argument("--codename", help="Blue Ox codename = the ArcMap / Deal Folder name (remembered per run)")
    h.add_argument("--apply", action="store_true",
                   help="WRITE: narvi scenarios, anduin type curves + deal + Blue Ox config (plan must be READY)")
    h.add_argument("--new-version", action="store_true",
                   help="a curve edited in anduin since the handoff: save the dossier cohort as a NEW version")
    h.add_argument("--replace", action="store_true",
                   help="overwrite narvi scenarios / the Blue Ox config edited since the handoff")
    v = sub.add_parser("review", help="re-render review.html from proposal.json (after editing benches.yaml)")
    _run_args(v)

    a = ap.parse_args(argv)
    cfg = cfgmod.load(a.config)
    if a.cmd == "login":
        client = Anduin(a.url) if a.url else Anduin()
        try:
            user = credentials.interactive_login(client)
        except AnduinError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        print(f"logged in to {client.base} as {user.get('display_name') or user.get('email')} - token saved "
              "to Windows Credential Manager (30 days)")
        return 0
    run_dir = Path(a.run_dir) if a.cmd == "propose" else _resolve_run(a)

    if a.cmd == "propose":
        if a.window and not a.window_basis:
            raise SystemExit("--window needs --window-basis (the decision log records who correlated it)")
        prop = pipeline.propose(Path(a.deal), run_dir, cfg,
                                correlated_window=tuple(a.window) if a.window else None,
                                window_basis=a.window_basis)
        shutil.copy(cfg.path, run_dir / "thresholds.snapshot.yaml")
        (run_dir / "proposal.md").write_text(dossier.proposal_md(prop), encoding="utf-8")
        print(f"wrote {review.render(run_dir)} — open it in a browser: the review surface")
        for w in prop.get("warnings", []):
            print(f"WARNING: {w}")
        print(f"wrote {run_dir / 'proposal.md'} + benches.yaml — review/edit the per-unit benches, "
              "planned laterals and spacing, then run evaluate")
    elif a.cmd == "evaluate":
        _remember_evaluate(run_dir, a)
        try:
            pipeline.evaluate(run_dir, cfg, benches=a.benches, spacing_ft=_spacing(a.spacing),
                              use_anduin=not a.no_anduin, tc_group_overrides=_tc_groups(a.tc_groups),
                              short_history_transfer=_transfer_cutoff(a, cfg),
                              radius_overrides=_radius(a.radius), tc_single=a.tc_single,
                              cohort_sizes=_cohort(a.cohort))
        except AnduinError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        shutil.copy(cfg.path, run_dir / "thresholds.snapshot.yaml")   # the config evaluate actually ran under
        dossier.render(run_dir)
        print(f"wrote {dossier_html.render(run_dir)} — open it in a browser (dossier.md beside it is the text record)")
    elif a.cmd == "handoff":
        return _handoff(run_dir, a, cfg)
    elif a.cmd == "review":
        print(f"wrote {review.render(run_dir)}")
    else:
        if a.fetch_sticks:
            res = json.loads((run_dir / "signals.json").read_text(encoding="utf-8"))
            with wh.connect() as conn:
                write_json(run_dir / "well_sticks.json", wh.wellsticks(conn, pipeline.map_api10s(res)))
        dossier.render(run_dir)
        print(f"wrote {dossier_html.render(run_dir)} (+ dossier.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
