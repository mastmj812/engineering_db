"""Review cards for the step-A likely mis-tags (read-only) — docs/formation_tag_redesign/stepA-crossings-2026-11-06.

    python -m scripts.tag_stepa_cards --cache <scoreboard cache> --out docs/formation_tag_redesign/stepA-cards-<date>

Picks the wells in wells_in_zones.csv that are clearly closer to another bench's landing surface than to their own:
  suspect = 'this well', not a thin Delaware WCA split (Q1 (a)), and lead >= 100 ft, where
  lead = |depth - own surface| - |depth - other surface| at the well's node.
A well appearing under several pairs is carded once, for the pair it leads most. Wells already ruled on (seeded
overrides, #230 rule-V calls and holds) are dropped. Order: fringe first (distance in from the extent boundary),
then the largest lead. Cards come in batches of about 20.
Each card is the strike-section card of the earlier screens (box.flag_cards), with evidence neighbours only (no planned
survey, none under 4,000 ft) drawn by their live tags. The header gives both landing surfaces at the well.
Verdicts go in cards_sample.csv: agree / reject / a bench code (your own call) / free text (a hold).
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
from box import tag_scoreboard as sb
from box.bench_qc import DEFAULT_PARAMS, _esc, _fmt, _project_xy_ft
from scripts.box_family_qc import _scored

STEP_A = sb.ROOT / "docs" / "formation_tag_redesign" / "stepA-crossings-2026-11-06"
LEAD_FT = 100.0
BATCH = 22
WCA = {"WCXY", "WCA_1", "WCA_2"}


def pick(labels: pd.DataFrame) -> pd.DataFrame:
    z = pd.read_csv(STEP_A / "wells_in_zones.csv", dtype={"api10": str})
    t = z[z["suspect"] == "this well"].copy()
    t["lead_ft"] = (t["depth_ft"] - t["own_surface_ft"]).abs() - (t["depth_ft"] - t["other_surface_ft"]).abs()
    t = t.sort_values("lead_ft", ascending=False).drop_duplicates("api10")
    thin = (t["basin"] == "delaware") & t["live"].isin(WCA) & t["other_code"].isin(WCA)
    t = t[~thin & (t["lead_ft"] >= LEAD_FT) & ~t["api10"].isin(set(labels["api10"]))]
    t = t.sort_values(["edge_mi", "lead_ft"], ascending=[True, False]).reset_index(drop=True)
    t["card"] = np.arange(1, len(t) + 1)
    t["batch"] = (t["card"] - 1) // BATCH + 1
    return t


def card(dd: pd.DataFrame, xy: np.ndarray, subj: pd.Series, v: pd.Series, vend: pd.Series | None) -> str:
    i = int(dd.index[dd["api10"] == subj["api10"]][0])
    wide = fc._neighbourhood(dd, xy, i, replace(DEFAULT_PARAMS, radius_ft=fc.SECTION_PREFILTER_FT))
    png, _ = fc.card_figure(subj, fc._neighbourhood(dd, xy, i, DEFAULT_PARAMS), DEFAULT_PARAMS, dest=v["other_code"],
                            section=fc.strike_section(subj, wide))
    novi = _esc(vend["novi_raw"]) if vend is not None else "?"
    env = _esc(vend["env_raw"]) if vend is not None else "?"
    kv = (
        f"<b>card {int(v['card'])}</b> (batch {int(v['batch'])}) · <b>{_esc(subj['api10'])}</b> {_esc(subj['well_name'])} · {_esc(subj['operator'])} · "
        f"{_esc(v['county'])} · fp {_esc(subj['first_production_date'])} · lateral {_fmt(subj['lateral_length_ft'], 0)} ft · "
        f"depth <b>{_fmt(v['depth_ft'], 0)}</b> ({_esc(v['depth_source'])}; tvd_ft {_fmt(subj['tvd_ft'], 0)})<br>"
        f"live tag <b>{_esc(v['live'])}</b> · Novi <b>{novi}</b> · Enverus <b>{env}</b> → proposed <b>{_esc(v['other_code'])}</b><br>"
        f"landing surfaces here: own {_esc(v['live'])} <b>{_fmt(v['own_surface_ft'], 0)}</b> ft, {_esc(v['other_code'])} "
        f"<b>{_fmt(v['other_surface_ft'], 0)}</b> ft (pair {_esc(v['pair'])}: {_esc(v['state'])}, gap {_fmt(v['gap_ft'], 0)} ft) · "
        f"the well is {_fmt(v['lead_ft'], 0)} ft closer to {_esc(v['other_code'])} · {_fmt(v['edge_mi'], 1)} mi in from the extent edge"
    )
    return f"<div class=card id=\"w{_esc(subj['api10'])}\"><div class=kv>{kv}</div><img src=\"{png}\"></div>"


def run(cache: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    sample = out / "cards_sample.csv"
    if sample.exists():
        fc.guard_verdict_file(sample)
    p = pick(sb.labelled_set())
    vend = pd.read_pickle(cache / "vendors.pkl").assign(api10=lambda x: x["api10"].astype(str)).set_index("api10")
    html: dict[int, list[str]] = {}
    rows = []
    for b in ("delaware", "midland"):
        dd = _scored(b, cache / f"scored_{b}.pkl").reset_index(drop=True)
        dd["api10"] = dd["api10"].astype(str)
        ok = ~dd["planned"].fillna(False).astype(bool) & (pd.to_numeric(dd["tvd_ft"], errors="coerce") >= sb.MIN_EVIDENCE_TVD_FT)
        dd = dd[ok | dd["api10"].isin(set(p["api10"]))].reset_index(drop=True)
        xy = _project_xy_ft(dd["mid_lon"].to_numpy(float), dd["mid_lat"].to_numpy(float))
        for _, v in p[p["basin"] == b].iterrows():
            if not (dd["api10"] == v["api10"]).any():
                continue
            subj = dd[dd["api10"] == v["api10"]].iloc[0]
            html.setdefault(int(v["batch"]), []).append((int(v["card"]), card(dd, xy, subj, v, vend.loc[v["api10"]] if v["api10"] in vend.index else None)))
            rows.append({"card": int(v["card"]), "batch": int(v["batch"]), "basin": b, "api10": v["api10"], "well_name": subj["well_name"],
                         "county": v["county"], "live": v["live"], "proposed": v["other_code"], "lead_ft": round(float(v["lead_ft"])),
                         "edge_mi": round(float(v["edge_mi"]), 2), "verdict": "", "verdict_source": ""})
    pd.DataFrame(rows).sort_values("card").to_csv(sample, index=False)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    secs = [f"<h2>Batch {k}</h2>" + "".join(h for _, h in sorted(v)) for k, v in sorted(html.items())]
    page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Step A review cards</title><style>{fc._CSS}</style></head><body>"
            "<h1>Step A — likely mis-tags in the BOX extents</h1>"
            f"<div class=meta>Built {built}, read-only. {len(rows)} wells that sit at least {LEAD_FT:.0f} ft closer to another bench's landing surface "
            "than to their own (thin Delaware WCA splits and already-ruled wells excluded), fringe first. Neighbours are evidence wells only "
            "(no planned survey, none under 4,000 ft) by their LIVE tags. Mark each card in <code>cards_sample.csv</code>: <b>agree</b> / "
            "<b>reject</b> / a bench code / free text (a hold). Stop after any batch if the hit rate already tells you enough. Agrees become "
            "proposed overrides; nothing is applied without a separate go.</div>" + "".join(secs) + "</body></html>")
    (out / "cards.html").write_text(page, encoding="utf-8")
    return out / "cards.html"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    print(run(a.cache, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
