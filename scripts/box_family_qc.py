"""BOX step 15 / 20 — bench QC + pooling evidence for a bench family (read-only).

    python -m scripts.box_family_qc --family BS3 [--out docs/box/step15a-YYYY-MM-DD] [--pool-dir docs/box/pool-2026-10-15]
                                    [--cache <scratch.pkl>] [--asks <asks.json>]
    python -m scripts.box_family_qc --family MID_WC --out docs/box/step20a-YYYY-MM-DD --analogue --cards --alloc
                                    [--cache <mid.pkl>] [--analogue-cache <del.pkl>]

Pulls the basin's producing horizontals (box.bench_qc, READ ONLY transaction), scores the consensus detector,
applies the class rule of record with Michael's gate-1 card verdicts, reconciles against the frozen D84 pools and
writes per-bench step-1 QC pages, the family page (index.html), wells_final_<bench>.csv, family_roles.csv and
summary.json. ``--cache`` keeps the scored frame so a re-render does not re-pull. Nothing is written to the warehouse.

Step 20a (Midland, D134 B): ``--analogue`` pulls + scores the Delaware the same way and compares every Midland swap class
with its Delaware analogue (box/swap_compare.py); ``--cards`` draws calibration cards for the classes that are clearly
unlike it (box/flag_cards.py); ``--alloc`` runs the allocation-well screen (box/alloc_screen.py; laterals pulled read-only).
The basin follows the family (family_qc.FAMILY_BASIN); a basin with no frozen pools (the Midland) uses none.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from box import alloc_screen as al
from box import basin as bsn
from box import edge_gap_report as egr
from box import exclusions, flag_cards
from box import family_qc as fq
from box import swap_compare as sc
from box.bench_qc import TX_FIPS, pull_producers, score_consensus
from box.qc_rule import load_verdicts

GATE1_CARDS = Path("docs") / "box" / "step1-2026-10-06" / "cards_sample.csv"
DELAWARE_POOLS = [Path("docs") / "box" / "pool-2026-10-15", Path("docs") / "box" / "step15a-2026-10-16"]


def _git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=False).stdout.strip()
    return sha + ("+dirty" if dirty else "")


def _scored(basin: str, cache: Path | None) -> pd.DataFrame:
    """The basin's producing horizontals, consensus-scored (box.bench_qc, READ ONLY); ``cache`` read if present, else written."""
    if cache and cache.exists():
        return pd.read_pickle(cache)
    from etl.db import get_connection

    with get_connection() as conn:
        scored = score_consensus(pull_producers(conn, basin))
    if cache:
        scored.to_pickle(cache)
    return scored


def _analogue(scored: pd.DataFrame, dela: pd.DataFrame, family: tuple[str, ...], out: Path, step: str, label: str, cards: bool) -> tuple[str, dict]:
    """D134 B: every swap class vs its Delaware analogue; cards for the unlike ones."""
    cmp = sc.compare(sc.class_signatures(scored, family), sc.class_signatures(dela, family))
    un = sc.unlike_classes(cmp)
    cmp.to_csv(out / "swap_classes_vs_delaware.csv")
    if cards and un:
        flag_cards.build(scored, out, family, only_classes=tuple(un), stem="cards",
                         title=f"BOX step {step} — {label} calibration cards: swap classes unlike their Delaware analogue (D134 B)")
    html = sc.render_section(cmp, f"{label} as-of {scored.attrs.get('asof')}, Delaware as-of {dela.attrs.get('asof')}",
                             "cards.html" if cards and un else None)
    info = {"unlike": un, "verdicts": {k: int(v) for k, v in cmp["verdict"].value_counts().items()},
            "thresholds": {"min_flags": sc.MIN_FLAGS, "min_analogue": sc.MIN_ANALOGUE, "rate_ratio": sc.RATE_RATIO,
                           "share_diff": sc.SHARE_DIFF, "tvd_ratio": sc.TVD_RATIO}}
    return html, info


def _alloc(basin: str, scored: pd.DataFrame, dela: pd.DataFrame, family: tuple[str, ...], excluded: set[str], out: Path) -> tuple[str, dict]:
    """Twin laterals (both basins: the Delaware run checks the detector against the recorded exclusions) + production sharing."""
    from etl.db import get_connection

    frames = {basin: scored, bsn.DELAWARE: dela}
    with get_connection() as conn:
        geo = {b: egr.pull_laterals(conn, sorted(f["api10"].unique())) for b, f in frames.items()}
    pairs = {b: al.twin_pairs(egr.attach_geometry(f, geo[b])) for b, f in frames.items()}
    pairs[basin].to_csv(out / "alloc_twin_pairs.csv", index=False)
    check = al.recall(pairs[bsn.DELAWARE], excluded)
    fam = set(family)
    con = al.sharing_contrast(scored[scored["cohort"] & scored["formation_blueox"].isin(fam)])
    # reference: Delaware TEXAS wells of the same benches (WCA pool in full) - the same state's reporting
    ref = al.sharing_contrast(dela[dela["cohort"] & dela["formation_blueox"].isin(fam | {"WCA_2", "WCXY"}) & (dela["state_code"] == TX_FIPS)])
    p = pairs[basin]
    touch = p["formation_blueox_a"].isin(fam) | p["formation_blueox_b"].isin(fam)
    info = {"pair_classes": {k: int(v) for k, v in p.loc[touch, "pair_class"].value_counts().items()},
            "family_twins": int((touch & (p["pair_class"] == "twin")).sum()), "delaware_check": check,
            "sharing_share": con["share_sharing"],
            "sharing_oil": {k: con["oil12_kft"][k] for k in ("ratio", "ci90", "n_blocks_both")},
            "sharing_gor": {k: con["gor12"][k] for k in ("ratio", "ci90", "n_blocks_both")},
            "sharing_oil_delaware_tx": {k: ref["oil12_kft"][k] for k in ("ratio", "ci90", "n_blocks_both")}}
    return al.render_section(p, family, con, ref, check), info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--family", choices=sorted(fq.FAMILIES), required=True)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--pool-dir", type=Path, nargs="*", default=None,
                    help="frozen pool dirs (wells_final_*.csv); the first with universe.csv gives the judged universe. Default: the "
                         "Delaware pools (pool-2026-10-15 + step15a-2026-10-16) for a Delaware family, none for the Midland")
    ap.add_argument("--verdicts", type=Path, action="append", default=None)
    ap.add_argument("--cache", type=Path, default=None, help="pickle of the scored frame; read if present, else written")
    ap.add_argument("--asks", type=Path, default=None, help="JSON list of gate-ask strings (HTML) for the page")
    ap.add_argument("--basin", default=None, help="the basin pulled and scored (step 19); default = the family's (FAMILY_BASIN)")
    ap.add_argument("--analogue", action="store_true", help="step 20a: compare every swap class with its Delaware analogue (D134 B)")
    ap.add_argument("--analogue-cache", type=Path, default=None, help="pickle of the scored Delaware frame; read if present, else written")
    ap.add_argument("--cards", action="store_true", help="with --analogue: calibration cards for the classes unlike their analogue")
    ap.add_argument("--alloc", action="store_true", help="allocation-well screen (twin laterals + production sharing)")
    ap.add_argument("--step", default=None, help="step label on the page (default 15a; 20a for a Midland family)")
    a = ap.parse_args(argv)
    basin = a.basin or fq.FAMILY_BASIN.get(a.family, bsn.DELAWARE)
    pool_dir = a.pool_dir if a.pool_dir is not None else (DELAWARE_POOLS if basin == bsn.DELAWARE else [])
    step = a.step or ("20a" if basin == bsn.MIDLAND else "15a")
    out = a.out or Path("docs") / "box" / f"step{step}-{dt.datetime.now(tz=dt.UTC).astimezone():%Y-%m-%d}"
    t0 = time.time()
    scored = _scored(basin, a.cache)
    verdicts: dict[str, str] = {}
    for p in a.verdicts or [GATE1_CARDS]:
        verdicts.update(load_verdicts(p))
    excluded = set(exclusions.load()["api10"])
    meta = {
        "built_at": dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds"), "git_sha": _git_sha(),
        "asof": str(scored.attrs.get("asof")), f"n_{basin}_prod_hz": len(scored), "n_witness": int(scored["cons_witness"].sum()),
        "verdicts": {"agree": sum(v == "AGREE" for v in verdicts.values()), "reject": sum(v == "REJECT" for v in verdicts.values())},
        "asks": json.loads(a.asks.read_text(encoding="utf-8")) if a.asks else [],
    }
    family = fq.FAMILIES[a.family]
    label = bsn.get(basin).label
    if basin != bsn.DELAWARE:
        meta |= {"step": step, "basin_label": label, "pool_word": "D128 context (not pooled)",
                 "plan_note": "docs/box_type_curves_plan.md §5 step 20a; D128 (one bench each, no pooling), D134 A / B (the Delaware class rule "
                              "as written; Delaware D23 r / c and D27 constants), D117 (undrilled = any Novi category)."}
    out.mkdir(parents=True, exist_ok=True)
    extra: list[str] = []
    dela = _scored(bsn.DELAWARE, a.analogue_cache) if (a.analogue or a.alloc) else None
    if a.analogue:
        sec, meta["analogue"] = _analogue(scored, dela, family, out, step, label, a.cards)
        extra.append(sec)
        print(f"analogue: unlike {meta['analogue']['unlike']}; {meta['analogue']['verdicts']}")
    if a.alloc:
        sec, meta["alloc"] = _alloc(basin, scored, dela, family, excluded, out)
        extra.append(sec)
        print(f"alloc: {meta['alloc']['pair_classes']}; delaware check {meta['alloc']['delaware_check']}; sharing oil {meta['alloc']['sharing_oil']}")
    meta["extra_sections"] = extra
    s = fq.build(scored, a.family, out, pool_dir, verdicts, excluded, meta, basin=basin)
    for b in s["benches"]:
        r = s["set"][b]
        print(f"{b}: tagged {r['tagged_live']:,} -> final {r['final']:,} (member {r['member']:,}, churn kept {r['old_churn_kept']}, "
              f"frozen elsewhere {r['frozen_elsewhere']} {r['frozen_to']}, new out {r['new_ruled_out']} {r['new_ruled_out_to']}, excluded {r['excluded']}); "
              f"cohort {r['final_cohort']:,}")
    for pr in s["pairs"]:
        pe = pr["pooling"]
        for k in ("oil12_kft", "gor12", "cum24_over_cum12"):
            print(f"  {pe['b']}/{pe['a']} {k}: {pe[k]['ratio']:.3f} [{pe[k]['ci90'][0]:.3f}-{pe[k]['ci90'][1]:.3f}] blocks {pe[k]['n_blocks_both']}")
    print(f"uncalibrated flags {s['uncalibrated_flags']} in {s['uncalibrated_classes']}")
    print(f"wrote {out / 'index.html'}  ({time.time() - t0:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
