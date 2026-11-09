"""Rule v5.2 gross-miss review cards (read-only) — docs/formation_tag_redesign/RULE_V5_2.md, Acceptance.

    python -m scripts.tag_v5_2_cards --cache <scoreboard cache> --out docs/formation_tag_redesign/v5_2-cards-<date>

Three sections (Michael, 2026-11-08):
  A  the one change class of >= 20 wells (Delaware OTHER -> AVA_0): a seeded sample of 10, accepted at 7/10;
  B  every other v5.2 move (classes < 20): full review, each card decides only its own well;
  C  the sql/23 wells v5.2 calls a gross miss but cannot place ('gm_unplaced'): sql/23's code is the proposal.
A card shows the strike section (neighbours = evidence wells by LIVE tags; the subject drawn with its INPUT tag), both
vendor strings, the input / v5 / proposed codes, and each nearby code's witness depth at the well with the plain median
of the same witnesses within 2 mi (>= 3, the well left out). The pre-check repeats the move's test on plain medians; a
card whose check disagrees is MARKED, not dropped. Needs producers_v5_2.pkl (scripts.tag_grossmiss_dev).
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
from box import tag_grossmiss as gm
from box import tag_precedence as tp
from box import tag_scoreboard as sb
from box.bench_qc import DEFAULT_PARAMS, _esc, _fmt, _project_xy_ft
from scripts.box_family_qc import _scored

SAMPLE_CLASS = ("delaware", "OTHER", "AVA_0")
SAMPLE_N, SEED = 10, 20261108


def refs_at(d: pd.DataFrame, cw: pd.Series, v: pd.Series) -> dict[str, tuple[float, float, int]]:
    """code -> (witness depth by the rule's estimator, plain median, n) at the well, witnesses within 2 mi, well left out."""
    out = {}
    b = v["basin"]
    pt, pid = np.array([[v["x"], v["y"]]]), np.array([v.name])
    for c in gm.column(b):
        w = d.index[(d["basin"] == b) & (cw == c) & (d.index != v.name)]
        near = w[np.hypot(d.loc[w, "x"] - v["x"], d.loc[w, "y"] - v["y"]) <= tp.RULE.r_mi * sb.M_PER_MI]
        if len(near) < tp.RULE.n_min:
            continue
        est = gm._refs(d.loc[w, ["x", "y"]].to_numpy(float), d.loc[w, "depth_ft"].to_numpy(float), w.to_numpy(), pt, pid, tp.RULE)[0]
        out[c] = (float(est), float(d.loc[near, "depth_ft"].median()), len(near))
    return out


def plain_check(v: pd.Series, refs: dict, proposed: str) -> str:
    """The move's own test, repeated on plain medians (unit distance = its nearest code's median)."""
    b, dep = v["basin"], float(v["depth_ft"])
    order = tp.UNIT_ORDER.get(b, [])
    ud: dict[str, float] = {}
    for c, (_, med, _) in refs.items():
        u = tp.unit(b, c)
        ud[u] = min(ud.get(u, np.inf), abs(dep - med))
    own, tgt = tp.unit(b, v["base52"]), tp.unit(b, proposed)
    if tgt not in ud:
        return f"no plain-median read for {proposed}'s unit"
    others = [x for u, x in ud.items() if u != tgt]
    lead = (min(others) - ud[tgt]) if others else np.inf
    tol = tp.RULE.far_ft if own in order else tp.RULE.other_match_ft
    own_txt = f"input unit {ud[own]:.0f} ft off" if own in ud else ("input is OTHER / unmapped" if own not in order else "no plain read for the input unit")
    ok = ud[tgt] <= tol and lead >= tp.RULE.margin_ft and (own not in ud or ud[own] > gm.RULE.miss_ft)
    word = "agrees" if ok else "DISAGREES"
    return f"{word} ({own_txt}; {proposed}'s unit {ud[tgt]:.0f} ft, lead {lead:.0f} ft)"


def card(dd: pd.DataFrame, xy: np.ndarray, subj: pd.Series, v: pd.Series, refs: dict) -> str:
    i = int(dd.index[dd["api10"] == subj["api10"]][0])
    s = subj.copy()
    s["formation_blueox"] = v["base52"] if isinstance(v["base52"], str) else "(unmapped)"
    wide = fc._neighbourhood(dd, xy, i, replace(DEFAULT_PARAMS, radius_ft=fc.SECTION_PREFILTER_FT))
    png, _ = fc.card_figure(s, fc._neighbourhood(dd, xy, i, DEFAULT_PARAMS), DEFAULT_PARAMS, dest=v["proposed"],
                            section=fc.strike_section(s, wide))
    col = gm.column(v["basin"])
    idx = [col.index(c) for c in (v["base52"], v["proposed"]) if c in col]
    lo, hi = (max(min(idx) - 1, 0), min(max(idx) + 1, len(col) - 1)) if idx else (0, len(col) - 1)
    shown = [c for c in col[lo: hi + 1] if c in refs]
    rtxt = " · ".join(f"{_esc(c)} {_fmt(refs[c][0], 0)} ft (plain {_fmt(refs[c][1], 0)}, n={refs[c][2]})" for c in shown) or "none within 2 mi"
    v5 = (f"v5 <b>{_esc(v['v5'])}</b> ({_esc(v['basis'])}, {_esc(v['accepted_basis'])}) · "
          if v["v5"] != v["base52"] and v["basis"] != "sql23_kept" else "")
    s23 = f"sql/23 today <b>{_esc(v['sql23_code'])}</b> · " if isinstance(v["sql23_code"], str) else ""
    why = ("v5.2 gross miss, unplaced: proposal = sql/23's code" if v["section"] == "C"
           else f"v5.2 gross miss: input unit {_fmt(v['gm_own_gap_ft'], 0)} ft off, {_esc(v['proposed'])} {_fmt(v['gm_target_gap_ft'], 0)} ft, "
                f"lead {_fmt(v['gm_lead_ft'], 0)} ft, sub-bench {_esc(v['gm_sub'])}")
    kv = (
        f"<b>card {int(v['card'])}</b> ({v['section']}) · {_esc(v['basin'])} {_esc(v['base52'])} → {_esc(v['proposed'])} · {why}<br>"
        f"<b>{_esc(subj['api10'])}</b> {_esc(subj['well_name'])} · {_esc(subj['operator'])} · {_esc(v['county'])} · fp "
        f"{_esc(subj['first_production_date'])} · depth <b>{_fmt(v['depth_ft'], 0)}</b> ft ({_esc(v['depth_source'])}; tvd_ft "
        f"{_fmt(subj['tvd_ft'], 0)})<br>"
        f"Novi <b>{_esc(v['novi_raw'])}</b> ({_esc(v['novi_code'])}) · Enverus <b>{_esc(v['env_raw'])}</b> ({_esc(v['env_code'])}) · "
        f"today <b>{_esc(v['live'])}</b> · {s23}{v5}input <b>{_esc(v['base52'])}</b> → proposed <b>{_esc(v['proposed'])}</b><br>"
        f"witness depths here: {rtxt} · check: <b>{_esc(v['check'])}</b>"
    )
    return f"<div class=card id=\"w{_esc(subj['api10'])}\"><div class=kv>{kv}</div><img src=\"{png}\"></div>"


def select(d: pd.DataFrame) -> pd.DataFrame:
    mv = d[d["gm_code"].fillna("~") != d["base52"].fillna("~")].copy()
    mv["proposed"] = mv["gm_code"]
    key = list(zip(mv["basin"], mv["base52"].fillna("(unmapped)"), mv["gm_code"], strict=True))
    in_cls = pd.Series([k == SAMPLE_CLASS for k in key], index=mv.index)
    a = mv[in_cls].sample(n=min(SAMPLE_N, int(in_cls.sum())), random_state=SEED).assign(section="A")
    b_ = mv[~in_cls].assign(section="B")
    c = d[(d["live_source"] == "tvd_corrected") & (d["gm_basis"] == "gm_unplaced")].copy()
    c["proposed"], c["section"] = c["sql23_code"], "C"
    out = pd.concat([a, b_, c])
    out = out.sort_values(["section", "basin", "base52", "proposed", "county", "api10"], na_position="first")
    out["card"] = np.arange(1, len(out) + 1)
    return out


def run(cache: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    sample = out / "cards_sample.csv"
    fc.guard_verdict_file(sample)
    d = pd.read_pickle(cache / "producers_v5_2.pkl")
    cw = gm.code_witness(d)
    ch = select(d)
    refs = {i: refs_at(d, cw, v) for i, v in ch.iterrows()}
    ch["check"] = [plain_check(v, refs[i], v["proposed"]) for i, v in ch.iterrows()]
    heads = {"A": "A · class sample", "B": "B · full review", "C": "C · sql/23 wells v5.2 cannot place"}
    sections: dict[str, list[str]] = {}
    rows = []
    for b in ("delaware", "midland"):
        dd = _scored(b, cache / f"scored_{b}.pkl").reset_index(drop=True)
        dd["api10"] = dd["api10"].astype(str)
        ok = ~dd["planned"].fillna(False).astype(bool) & (pd.to_numeric(dd["tvd_ft"], errors="coerce") >= sb.MIN_EVIDENCE_TVD_FT)
        dd = dd[ok | dd["api10"].isin(set(ch["api10"]))].reset_index(drop=True)
        xy = _project_xy_ft(dd["mid_lon"].to_numpy(float), dd["mid_lat"].to_numpy(float))
        for i, v in ch[ch["basin"] == b].iterrows():
            subj = dd[dd["api10"] == v["api10"]].iloc[0]
            head = f"{heads[v['section']]} — {b.title()} {v['base52'] if isinstance(v['base52'], str) else '(unmapped)'} → {v['proposed']}"
            sections.setdefault(head, []).append((int(v["card"]), card(dd, xy, subj, v, refs[i])))
            rows.append({"card": int(v["card"]), "section": v["section"], "basin": b, "api10": v["api10"], "well_name": subj["well_name"],
                         "county": v["county"], "live": v["live"], "sql23": v["sql23_code"], "input": v["base52"],
                         "v5": v["v5"] if v["basis"] != "sql23_kept" else "", "proposed": v["proposed"], "check": v["check"],
                         "verdict": "", "verdict_source": ""})
    pd.DataFrame(rows).sort_values("card").to_csv(sample, index=False)
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    body = "".join(f"<h2>{_esc(h)} ({len(v)})</h2>" + "".join(c for _, c in sorted(v))
                   for h, v in sorted(sections.items(), key=lambda kv: min(k for k, _ in kv[1])))
    n = ch["section"].value_counts().to_dict()
    page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Rule v5.2 cards</title><style>{fc._CSS}</style></head><body>"
            "<h1>Rule v5.2 — gross-miss review cards</h1>"
            f"<div class=meta>Built {built}, read-only. {len(rows)} cards. <b>A</b> ({n.get('A', 0)}): a seeded sample of the one class of "
            "20+ wells, Delaware OTHER → AVA_0 (38 wells; accepted at 7/10). <b>B</b> "
            f"({n.get('B', 0)}): every other v5.2 move, each card deciding only its own well. <b>C</b> ({n.get('C', 0)}): wells sql/23 "
            "moves today that v5.2 calls a gross miss (&gt; 600 ft off the input unit) but cannot place; the proposal is sql/23's code. "
            "<b>Input</b> = the accepted tag without sql/23 (what the well becomes if sql/23 retires); the subject is drawn with it. "
            "Neighbours are evidence wells by their LIVE tags. Witness depths: the rule's estimator, then the plain median of the same "
            "witnesses within 2 mi. A card whose plain-median check disagrees is marked, not dropped. Mark <code>cards_sample.csv</code>: "
            "<b>ACCEPT</b> (the proposed code) / <b>REJECT</b> (keep the INPUT code) / <b>a bench code</b> whenever your answer is "
            "neither — please write the code rather than REJECT when you mean v5's code or another bench. Nothing is applied.</div>"
            + body + "</body></html>")
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
