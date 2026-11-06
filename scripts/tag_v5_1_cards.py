"""Rule v5.1 sub-bench review cards (read-only) — docs/formation_tag_redesign/RULE_V5_1.md, Acceptance.

    python -m scripts.tag_v5_1_cards --cache <scoreboard cache> --out docs/formation_tag_redesign/v5_1-cards-<date>

One card per v5.1 change (full review: no change class reaches 20 wells); each card decides only its own well. A card
shows the strike section of evidence wells by their LIVE tags (box.flag_cards), both vendor strings, and every candidate
sub-bench's witness depth at the well. The pre-check is the plain median of the same sub-bench witnesses within 2 mi
(>= 3); a card whose pre-check disagrees is MARKED, not dropped. Needs producers_v5_1.pkl (scripts.tag_subbench_dev).
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
from box import tag_precedence as tp
from box import tag_scoreboard as sb
from box import tag_subbench as ts1
from box.bench_qc import DEFAULT_PARAMS, _esc, _fmt, _project_xy_ft
from scripts.box_family_qc import _scored


def plain_check(d: pd.DataFrame, v: pd.Series, r_mi: float = 2.0) -> tuple[dict[str, tuple[float, int]], str]:
    """Plain median (and n) of each candidate's sub-bench witnesses within r_mi, and whether it backs the call."""
    codes = ts1.unit_codes(v["basin"])[tp.unit(v["basin"], v["sb_code"])]
    w = d[(d["basin"] == v["basin"]) & d["wit_code"].isin(codes)]
    near = np.hypot(w["x"] - v["x"], w["y"] - v["y"]) <= r_mi * sb.M_PER_MI
    med = {}
    for c in codes:
        g = w[near & (w["wit_code"] == c)]["depth_ft"]
        med[c] = (float(g.median()) if len(g) >= 3 else np.nan, len(g))
    dist = {c: abs(v["depth_ft"] - m) for c, (m, _) in med.items() if np.isfinite(m)}
    if v["sb_code"] not in dist or len(dist) < 2:
        return med, "no plain-median read (a candidate has < 3 witnesses within 2 mi)"
    lead = min(x for c, x in dist.items() if c != v["sb_code"]) - dist[v["sb_code"]]
    return med, (f"agrees ({lead:.0f} ft closer to {v['sb_code']})" if lead >= 100 else f"DISAGREES (only {lead:.0f} ft closer to {v['sb_code']})")


def card(dd: pd.DataFrame, xy: np.ndarray, subj: pd.Series, v: pd.Series, med: dict) -> str:
    i = int(dd.index[dd["api10"] == subj["api10"]][0])
    wide = fc._neighbourhood(dd, xy, i, replace(DEFAULT_PARAMS, radius_ft=fc.SECTION_PREFILTER_FT))
    png, _ = fc.card_figure(subj, fc._neighbourhood(dd, xy, i, DEFAULT_PARAMS), DEFAULT_PARAMS, dest=v["sb_code"],
                            section=fc.strike_section(subj, wide))
    refs = " · ".join(f"{_esc(c)} {_fmt(v.get(f'z_{c}', np.nan), 0)} ft (plain median {_fmt(m, 0)}, n={n})" for c, (m, n) in med.items())
    kv = (
        f"<b>card {int(v['card'])}</b> · {_esc(v['basin'])} {_esc(v['accepted'])} → {_esc(v['sb_code'])} (sub-bench by depth, lead "
        f"{_fmt(v['sb_lead_ft'], 0)} ft) · <b>{_esc(subj['api10'])}</b> {_esc(subj['well_name'])} · {_esc(subj['operator'])} · "
        f"{_esc(v['county'])} · fp {_esc(subj['first_production_date'])}<br>"
        f"depth <b>{_fmt(v['depth_ft'], 0)}</b> ft ({_esc(v['depth_source'])}; tvd_ft {_fmt(subj['tvd_ft'], 0)}) · Novi <b>{_esc(v['novi_raw'])}</b> "
        f"({_esc(v['novi_code'])}) · Enverus <b>{_esc(v['env_raw'])}</b> ({_esc(v['env_code'])}) · today <b>{_esc(v['live'])}</b> · "
        f"v5 <b>{_esc(v['accepted'])}</b> (vendor default) → proposed <b>{_esc(v['sb_code'])}</b><br>"
        f"sub-bench witness depths here: {refs} · check: <b>{_esc(v['check'])}</b>"
    )
    return f"<div class=card id=\"w{_esc(subj['api10'])}\"><div class=kv>{kv}</div><img src=\"{png}\"></div>"


def run(cache: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    sample = out / "cards_sample.csv"
    fc.guard_verdict_file(sample)
    d = pd.read_pickle(cache / "producers_v5_1.pkl")
    ch = d[d["sb_code"].fillna("~") != d["accepted"].fillna("~")].copy()
    ch = ch.sort_values(["basin", "accepted", "sb_code", "county", "api10"]).reset_index(drop=True)
    ch["card"] = np.arange(1, len(ch) + 1)
    meds, checks = [], []
    for _, v in ch.iterrows():
        m, c = plain_check(d, v)
        meds.append(m)
        checks.append(c)
    ch["check"] = checks
    sections: dict[str, list[str]] = {}
    rows = []
    for b in ("delaware", "midland"):
        dd = _scored(b, cache / f"scored_{b}.pkl").reset_index(drop=True)
        dd["api10"] = dd["api10"].astype(str)
        ok = ~dd["planned"].fillna(False).astype(bool) & (pd.to_numeric(dd["tvd_ft"], errors="coerce") >= sb.MIN_EVIDENCE_TVD_FT)
        dd = dd[ok | dd["api10"].isin(set(ch["api10"]))].reset_index(drop=True)
        xy = _project_xy_ft(dd["mid_lon"].to_numpy(float), dd["mid_lat"].to_numpy(float))
        for k, v in ch[ch["basin"] == b].iterrows():
            subj = dd[dd["api10"] == v["api10"]].iloc[0]
            head = f"{b.title()} {v['accepted']} → {v['sb_code']}"
            sections.setdefault(head, []).append(card(dd, xy, subj, v, meds[k]))
            rows.append({"card": int(v["card"]), "basin": b, "api10": v["api10"], "well_name": subj["well_name"], "county": v["county"],
                         "live": v["live"], "v5": v["accepted"], "proposed": v["sb_code"], "lead_ft": round(float(v["sb_lead_ft"])),
                         "check": v["check"], "verdict": "", "verdict_source": ""})
    pd.DataFrame(rows).sort_values("card").to_csv(sample, index=False)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    body = "".join(f"<h2>{_esc(h)} ({len(v)})</h2>" + "".join(v) for h, v in sections.items())
    page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Rule v5.1 sub-bench cards</title><style>{fc._CSS}</style></head><body>"
            "<h1>Rule v5.1 — sub-bench review cards (full review)</h1>"
            f"<div class=meta>Built {built}, read-only. {len(rows)} cards: every well whose vendor-default sub-bench v5.1 changes by "
            "depth. Each card decides only its own well. The unit is never changed. Witness depths come from wells whose vendors agree on "
            "the unit and whose specific strings name one sub-bench. Neighbours are evidence wells only, by their LIVE tags. A card whose "
            "plain-median check disagrees is marked, not dropped. Mark <code>cards_sample.csv</code>: agree / reject (keep the v5 code) / "
            "a bench code / free text (a hold). Nothing is applied.</div>" + body + "</body></html>")
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
