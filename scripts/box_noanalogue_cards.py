"""BOX step 20b — calibration cards for the swap classes with NO Delaware analogue (read-only; drawn for gate 20b's choice).

    python -m scripts.box_noanalogue_cards --cache <mid_scored.pkl> --cmp docs/box/step20b-YYYY-MM-DD/swap_classes_vs_delaware.csv \
        --out docs/box/step20b-YYYY-MM-DD/cards_noanalogue --family MID_SPR \
        --judged docs/box/step20a-2026-10-26/cards_sample.csv docs/box/step20a-2026-10-26/ask3/cards_sample.csv \
                 docs/box/step20a-2026-10-26/tag_screen/cards_sample.csv docs/box/step20a-2026-10-26/tag_screen/well_calls.csv \
                 docs/box/step20a-2026-10-26/owner_benches.csv seeds/formation_tag_overrides.csv

Under D134 B a class is carded only when it is unlike its Delaware analogue; a class with no analogue (the Spraberry: the
Delaware has no MS / JM / LSSH / DEAN) falls to the rule default, tag kept (step 20a FINDINGS §8.21, D141). Gate 20b decides
whether to card them anyway. These cards are drawn so that choice costs no extra round: every class the comparison calls
``no analogue`` with >= MIN_FLAGS (box/swap_compare) Midland flags, 10 cards each (box/flag_cards, margin-stratified), on the
same scored frame as the QC run. Wells MM already judged are never re-carded (ask-3 pattern, D139): any api10 in a --judged
file (card samples, well calls, owner benches, the override seed) is left out before sampling. Nothing reads these cards
until MM fills the verdicts; nothing is written to the warehouse.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from box import family_qc as fq
from box import flag_cards
from box import swap_compare as sc


def judged_api10(paths: list[Path]) -> set[str]:
    """Every api10 in the given CSVs (column api10)."""
    out: set[str] = set()
    for p in paths:
        out |= set(pd.read_csv(p, dtype={"api10": str}, usecols=["api10"])["api10"].str.strip())
    return out


def noanalogue_classes(cmp: pd.DataFrame, min_flags: int = sc.MIN_FLAGS, within: tuple[str, ...] | None = None) -> list[str]:
    """Classes the D134 B comparison could not judge for want of a Delaware analogue, with >= min_flags Midland flags;
    ``within`` keeps only classes whose both ends are those benches (step 20b: the Spraberry-internal classes)."""
    out = list(cmp.index[(cmp["verdict"] == "no analogue") & (cmp["n"] >= min_flags)])
    if within is not None:
        out = [c for c in out if set(c.split("->")) <= set(within)]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True, help="the QC run's scored Midland frame (box_family_qc --cache)")
    ap.add_argument("--cmp", type=Path, required=True, help="the QC run's swap_classes_vs_delaware.csv")
    ap.add_argument("--family", choices=sorted(fq.FAMILIES), required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--judged", type=Path, nargs="*", default=[])
    ap.add_argument("--within-family", action="store_true",
                    help="only classes inside the family (step 20b: Spraberry-internal; the Wolfcamp crossings stay tag kept, D140)")
    ap.add_argument("--title", default="BOX step 20b — Midland Spraberry calibration cards: swap classes with no Delaware analogue")
    a = ap.parse_args(argv)
    scored = pd.read_pickle(a.cache)
    cmp = pd.read_csv(a.cmp, index_col=0)
    classes = noanalogue_classes(cmp, within=fq.FAMILIES[a.family] if a.within_family else None)
    judged = judged_api10(a.judged)
    f = flag_cards.flag_classes(scored.reset_index(drop=True), fq.FAMILIES[a.family])
    f = f[f["swap_class"].isin(classes)]
    left_out = f[f["api10"].isin(judged)].groupby("swap_class").size().to_dict()
    s = flag_cards.build(scored, a.out, fq.FAMILIES[a.family], only_classes=tuple(classes), exclude_api10=judged, title=a.title)
    print(f"classes {classes}")
    print(f"already judged, left out: {left_out}")
    print(f"cards {s['n_cards']} from {s['n_flags_carded_classes']} flags: {s['classes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
