"""Rule v4 blind review cards (read-only) — RULE_V4.md §2 step 3 (criterion K0).

    python -m scripts.tag_ladder_cards --cache <scoreboard cache> --out docs/formation_tag_redesign/v4-blind-cards-<date>

Draws 15 producers per basin at random (seed 20261105) from wells where v4 + overrides differs from the live tag.
Every labelled, overridden or non-evidence (planned / no clean depth) well is excluded, so no card's answer is known.
Each card is the strike-section card of the earlier screens (box.flag_cards). Neighbours are shown by their LIVE tags,
and the header carries the v4 reading (offset below the local anchor, the local rungs). Verdicts go in
cards_sample.csv: agree / reject / a bench code (your own call) / free text (a hold).
Needs producers_v4.pkl in the cache (scripts.tag_ladder_dev).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from box import flag_cards as fc
from box import tag_ladder as tl
from box import tag_scoreboard as sb
from box.bench_qc import DEFAULT_PARAMS, _esc, _fmt, _project_xy_ft
from scripts.box_family_qc import _scored

SEED = 20261105
PER_BASIN = 15


def previously_carded(root: Path = sb.ROOT) -> set[str]:
    """Every api10 on any earlier v4 card draw (judged or superseded): a fresh draw never repeats a well."""
    out: set[str] = set()
    for f in (root / "docs" / "formation_tag_redesign").glob("v4*-blind-cards-*/cards_sample.csv"):
        out |= set(pd.read_csv(f, dtype={"api10": str})["api10"])
    return out


def candidates(d: pd.DataFrame, labels: pd.DataFrame, exclude: set[str] | None = None) -> pd.DataFrame:
    c = d[d["evidence"] & d["override"].isna() & ~d["api10"].isin(set(labels["api10"]) | (exclude or set()))
          & (d["final"].fillna("~") != d["live"].fillna("~")) & d["final"].notna()]
    return c


def draw(c: pd.DataFrame, per_basin: int = PER_BASIN, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    parts = []
    for b in ("delaware", "midland"):
        g = c[c["basin"] == b].sort_values("api10")
        parts.append(g.iloc[np.sort(rng.choice(len(g), size=min(per_basin, len(g)), replace=False))])
    return pd.concat(parts, ignore_index=True)


def rung_text(row: pd.Series, rungs: pd.DataFrame, order: dict[str, list[str]]) -> str:
    lk = tl.rung_lookup(rungs)
    lad = tl.ladder_for(row["basin"], row["county"], row["state_code"], row["anchor_used"], order, lk)
    fam = {row["live"], row["final"]}
    keep = [i for i, (c, _) in enumerate(lad) if c in fam]
    if not keep:
        return ""
    lo, hi = max(min(keep) - 1, 0), min(max(keep) + 2, len(lad))
    return " · ".join(f"{c} {r:+.0f}" for c, r in lad[lo:hi])


def card(dd: pd.DataFrame, xy: np.ndarray, subj: pd.Series, v4: pd.Series, rungs: pd.DataFrame, order: dict[str, list[str]], n: int) -> str:
    i = int(dd.index[dd["api10"] == subj["api10"]][0])
    wide = fc._neighbourhood(dd, xy, i, replace(DEFAULT_PARAMS, radius_ft=fc.SECTION_PREFILTER_FT))
    png, _ = fc.card_figure(subj, fc._neighbourhood(dd, xy, i, DEFAULT_PARAMS), DEFAULT_PARAMS, dest=v4["final"],
                            section=fc.strike_section(subj, wide))
    anchor = v4["anchor_used"]
    kv = (
        f"<b>card {n}</b> · <b>{_esc(subj['api10'])}</b> {_esc(subj['well_name'])} · {_esc(subj['operator'])} · {_esc(subj['county'])} · "
        f"fp {_esc(subj['first_production_date'])} · lateral {_fmt(subj['lateral_length_ft'], 0)} ft · "
        f"depth <b>{_fmt(v4['depth_ft'], 0)}</b> ({_esc(v4['depth_source'])}; tvd_ft {_fmt(subj['tvd_ft'], 0)})<br>"
        f"live tag <b>{_esc(v4['live'])}</b> · Novi <b>{_esc(v4['novi_raw'])}</b> · Enverus <b>{_esc(v4['env_raw'])}</b> "
        f"→ proposed <b>{_esc(v4['final'])}</b><br>"
        f"v4: {_fmt(v4['offset_ft'], 0)} ft vs the local {_esc(anchor)} band (vendor-agreeing witnesses, 1.5 mi) · rungs here: "
        f"{_esc(rung_text(v4, rungs, order))} · margin {_fmt(v4['margin_ft'], 0)} ft · basis {_esc(v4['basis'])}"
    )
    return f"<div class=card id=\"w{_esc(subj['api10'])}\"><div class=kv>{kv}</div><img src=\"{png}\"></div>"


def run(cache: Path, out: Path, rungs_csv: Path, seed: int = SEED) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    sample_path = out / "cards_sample.csv"
    if sample_path.exists():
        fc.guard_verdict_file(sample_path)
    d = pd.read_pickle(cache / "producers_v4.pkl")
    rungs = pd.read_csv(rungs_csv)
    order = sb.bench_order()
    prior = previously_carded()
    pick = draw(candidates(d, sb.labelled_set(), prior), seed=seed)
    sections, rows = [], []
    n = 0
    for b in ("delaware", "midland"):
        dd = _scored(b, cache / f"scored_{b}.pkl").reset_index(drop=True)
        dd["api10"] = dd["api10"].astype(str)
        # rev 2 (Michael 2026-11-05): cards draw evidence wells only: no planned survey, nothing shallower than 4,000 ft
        ok = ~dd["planned"].fillna(False).astype(bool) & (pd.to_numeric(dd["tvd_ft"], errors="coerce") >= sb.MIN_EVIDENCE_TVD_FT)
        dd = dd[ok | dd["api10"].isin(set(pick["api10"]))].reset_index(drop=True)
        xy = _project_xy_ft(dd["mid_lon"].to_numpy(float), dd["mid_lat"].to_numpy(float))
        g = pick[pick["basin"] == b]
        html = []
        for _, v in g.iterrows():
            if not (dd["api10"] == v["api10"]).any():
                continue
            n += 1
            subj = dd[dd["api10"] == v["api10"]].iloc[0]
            html.append(card(dd, xy, subj, v, rungs, order, n))
            rows.append({"card": n, "basin": b, "api10": v["api10"], "well_name": subj["well_name"], "county": v["county"],
                         "live": v["live"], "proposed": v["final"], "verdict": "", "verdict_source": ""})
        sections.append(f"<h2>{b.title()} — {len(html)} cards</h2>" + "".join(html))
    pd.DataFrame(rows).to_csv(sample_path, index=False)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    page = [
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Ladder blind cards</title><style>{fc._CSS}</style></head><body>",
        "<h1>formation_blueox rule v4 — blind review cards (K0)</h1>",
        (f"<div class=meta>Built {built}, read-only. 15 random producers per basin (seed {seed}; every earlier card well excluded) where rule v4 + overrides differs from "
        "today's tag; no card is a labelled, overridden or planned-survey well, so none has a known answer. Neighbours are evidence wells only (no planned survey, none under 4,000 ft), drawn by their "
        "LIVE tags (strike section, orthogonal to the lateral; dashed = 1.5-mi band medians). Mark each card in "
        "<code>cards_sample.csv</code>: <b>agree</b> / <b>reject</b> / a bench code (your own call) / free text (a hold, not counted). "
        "Pass = 70 % agree among judged, and 60 % in each basin. Nothing here is applied.</div>"),
        *sections, "</body></html>",
    ]
    (out / "cards.html").write_text("".join(page), encoding="utf-8")
    return out / "cards.html"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--rungs", type=Path, required=True, help="rungs.csv from the matching tag_ladder_dev run")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    print(run(a.cache, a.out, a.rungs, a.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
