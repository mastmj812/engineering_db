"""BOX step 20a follow-up — screen every basin producer's bench tag against its neighbourhood + card the review subset.

    python -m scripts.box_tag_screen --basin midland --family MID_WC --out docs/box/step20a-2026-10-26/tag_screen \
        --prior-verdicts docs/box/step20a-2026-10-26/cards_sample.csv [--cache <scored.pkl>] [--round 2]

Read-only: pulls + scores the basin's producing horizontals (box.bench_qc), pulls both vendors' labels, applies
box.tag_screen rules A / B, writes screen_flags.csv (every flagged well), classes.csv, conflict_agree.csv, cards.html,
cards_sample.csv (verdict column; wells judged on the 20a cards are prefilled, verdict_source = 20a) and summary.json.
Round 2 (--round 2) reads the round-1 verdicts and tops up the mixed classes; every non-blank verdict already in the
file is carried over verbatim (free-text comments included). --whatif applies the drafted sql/16 basin trigger
(box.tag_screen.NOVI_COARSE_BY_BASIN) to the tags in memory and re-scores before screening. Nothing is written to the
warehouse.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from box import flag_cards as fc
from box import tag_screen as ts
from box.bench_qc import (
    DEFAULT_PARAMS,
    NM_FIPS,
    _esc,
    _fmt,
    _project_xy_ft,
    _table,
    score_consensus,
)
from box.family_qc import FAMILIES
from scripts.box_family_qc import _git_sha, _scored

_COLS = ["screen_class", "screen_rule", "api10", "well_name", "operator", "county", "formation_blueox", "screen_dest", "tag_source",
         "novi_formation", "env_interval", "other_vendor", "cons_status", "cons_suggest", "sql23_nearest", "cons_gor_vote", "n_votes",
         "tvd_ft", "cons_own_delta", "cons_nearest", "cons_nearest_delta", "screen_margin", "first_production_date", "cohort", "oil12_kft",
         "gor12", "mid_lon", "mid_lat"]


def _card(df: pd.DataFrame, xy: np.ndarray, subj: pd.Series) -> str:
    i = int(df.index[df["api10"] == subj["api10"]][0])
    png, meta = fc.card_figure(subj, fc._neighbourhood(df, xy, i, DEFAULT_PARAMS), DEFAULT_PARAMS)
    own = meta["bands"].get(subj["formation_blueox"])
    dst = meta["bands"].get(subj["screen_dest"])
    votes = [n for n, k in (("other vendor", "vote_vendor"), ("sql/23", "vote_sql23"), ("GOR", "vote_gor")) if bool(subj.get(k))]
    why = (f"rule A: sits in the {subj['screen_dest']} band; independent votes: {', '.join(votes)}" if subj["screen_rule"] == "A"
           else f"rule B: vendors disagree and depth cannot confirm the tag ({subj['cons_status']})")
    kv = (
        f"<b>{_esc(subj['api10'])}</b> {_esc(subj['well_name'])} · {_esc(subj['operator'])} · {'NM' if subj['state_code'] == NM_FIPS else 'TX'} "
        f"{_esc(subj['county'])} · fp {_esc(subj['first_production_date'])} · lateral {_fmt(subj['lateral_length_ft'], 0)} ft · TVD <b>{_fmt(subj['tvd_ft'], 0)}</b>"
        f"{' · <b>planned survey</b>' if subj['planned'] else ''}{' · <b>permit-round TVD</b>' if subj['tvd_round'] else ''} · lat {_fmt(subj['mid_lat'], 3)}<br>"
        f"tag <b>{_esc(subj['formation_blueox'])}</b> from {_esc(subj['tag_source'])} · Novi <b>{_esc(subj['novi_formation'])}</b> · Enverus <b>{_esc(subj['env_interval'])}</b> "
        f"→ proposed <b>{_esc(subj['screen_dest'])}</b> ({_esc(why)})<br>"
        f"own band {_fmt(own['med'] if own else None, 0)} (n={_fmt(own['n'] if own else 0)}) · {_esc(subj['screen_dest'])} band "
        f"{_fmt(dst['med'] if dst else None, 0)} (n={_fmt(dst['n'] if dst else 0)}) · nearest band {_esc(subj['cons_nearest'])} Δ {_fmt(subj['cons_nearest_delta'], 0)} ft · "
        f"sql/23 nearest {_esc(subj['sql23_nearest'])} · 12-mo oil {_fmt(subj['oil12_kft'], 0)} bbl/kft{'' if subj['cohort'] else ' (not cohort)'} · "
        f"GOR {_fmt(subj.get('gor12'), 0)} scf/bbl"
    )
    return f"<div class=card id=\"w{_esc(subj['api10'])}\"><div class=kv>{kv}</div><img src=\"{png}\"></div>"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--basin", default="midland")
    ap.add_argument("--family", default="MID_WC", help="classes touching this family are carded (the Spraberry waits for 20b)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cache", type=Path, default=None, help="pickle of the scored frame; read if present, else written")
    ap.add_argument("--prior-verdicts", type=Path, nargs="+", default=None,
                    help="earlier card files (20a / tag-screen cards_sample.csv): same well, same move -> agree / reject reused")
    ap.add_argument("--whatif", action="store_true", help="apply the drafted sql/16 basin trigger to the tags in memory, re-score")
    ap.add_argument("--round", type=int, default=1, choices=(1, 2))
    a = ap.parse_args(argv)
    t0 = dt.datetime.now(tz=dt.UTC)
    family = FAMILIES[a.family]
    a.out.mkdir(parents=True, exist_ok=True)
    scored = _scored(a.basin, a.cache).reset_index(drop=True)
    scored["api10"] = scored["api10"].astype(str)
    from etl.db import get_connection

    with get_connection() as conn:
        labels = ts.pull_labels(conn, a.basin, scored["api10"].tolist())
    whatif: dict = {}
    basin_coarse: frozenset[str] = frozenset()
    if a.whatif:
        attrs = dict(scored.attrs)
        p, labels = ts.whatif_retag(scored.drop(columns=[c for c in scored.columns if c.startswith("cons_")]), labels, a.basin)
        basin_coarse = ts.NOVI_COARSE_BY_BASIN.get(a.basin, frozenset())
        lab_hit = labels["novi_formation"].isin(basin_coarse) & (labels["tag_source"] == "enverus")
        whatif = {"trigger": sorted(basin_coarse), "retagged": int(p["whatif_changed"].sum()),
                  "kept_sql23_corrected": int((p["api10"].isin(labels.loc[lab_hit, "api10"]) & p["formation_blueox_tvd_corrected"].fillna(False).astype(bool)).sum()),
                  "by_move": {f"{a_}->{b_}": int(n) for (a_, b_), n in
                              scored.loc[p["whatif_changed"].values, "formation_blueox"].to_frame("a").assign(b=p.loc[p["whatif_changed"], "formation_blueox"].values)
                              .value_counts().items()}}
        p.attrs.update(attrs)
        scored = score_consensus(p.drop(columns=["whatif_changed"]))
        scored.attrs.update(attrs)
    d = ts.screen(scored, labels, basin_coarse)
    flagged = d[d["screen_rule"] != ""]
    flagged[_COLS].sort_values(["screen_class", "api10"]).to_csv(a.out / "screen_flags.csv", index=False)
    d.loc[d["conflict_agree"], [c for c in _COLS if not c.startswith("screen")]].to_csv(a.out / "conflict_agree.csv", index=False)
    cls = ts.classes(d)
    cls["touches_family"] = [ts.touches(f, t, family) for f, t in zip(cls["from"], cls["to"])]
    cls["carded"] = cls["touches_family"] & (cls["n_cohort"] >= ts.MIN_COHORT_TO_CARD)

    # prior verdicts: an earlier card on the same well proposing the same destination. ``judged`` = the count's reading
    # (agree / reject); ``verbatim`` = what was written and where (always what the file shows); ``carried`` = written
    # verdicts the count does not read (free text: holds, data defects) — never re-drawn, never dropped.
    judged: dict[str, str] = {}
    verbatim: dict[str, tuple[str, str]] = {}
    carried_rows: list[pd.DataFrame] = []
    for path in a.prior_verdicts or []:
        pv = pd.read_csv(path, dtype=str).fillna("")
        dcol = "screen_dest" if "screen_dest" in pv.columns else "cons_suggest"
        for r in pv.itertuples():
            text = str(r.verdict).strip()
            v = ts.clear_verdict(text, str(getattr(r, dcol)))
            src = (getattr(r, "verdict_source", "") or "round 1") if "verdict_source" in pv.columns else "20a"
            hit = flagged[(flagged["api10"] == r.api10) & (flagged["screen_dest"] == str(getattr(r, dcol)))]
            if len(hit) and v:
                judged[r.api10], verbatim[r.api10] = v, (text, src)
        if "screen_class" in pv.columns:
            free = pv[(pv["verdict"].str.strip() != "") & (pv["verdict"].map(ts.clear_verdict) == "")]
            carried_rows.append(free.assign(verdict_source=free["verdict_source"].replace("", "round 1")))

    sample_path = a.out / "cards_sample.csv"
    if a.round == 2:
        old = pd.read_csv(sample_path, dtype=str).fillna("")
        for r in old.itertuples():
            v = ts.clear_verdict(r.verdict, r.screen_dest)
            if v:
                judged[r.api10], verbatim[r.api10] = v, (str(r.verdict).strip(), r.verdict_source or "round 1")
        carried_rows.append(old[(old["verdict"].str.strip() != "")])
    elif sample_path.exists():  # verdicts other than the prefilled ones are Michael's record: never overwrite them
        old = pd.read_csv(sample_path, dtype=str).fillna("")
        if ((old["verdict"].str.strip() != "") & ~old["verdict_source"].isin(["20a", "round 1"])).any():
            raise fc.VerdictFileExists(f"{sample_path} carries verdicts; use --round 2")
    carried = pd.concat(carried_rows, ignore_index=True).drop_duplicates("api10", keep="last") if carried_rows else pd.DataFrame(columns=["api10"])
    seen = set(judged) | set(carried["api10"])  # a well already carded is never re-drawn

    pos = d["mid_lon"].notna() & d["mid_lat"].notna()
    xy = np.full((len(d), 2), np.nan)
    xy[pos.values] = _project_xy_ft(d.loc[pos, "mid_lon"].values, d.loc[pos, "mid_lat"].values)
    rows, sections, status = [], [], {}
    for name, c in cls[cls["carded"]].iterrows():
        g = flagged[flagged["screen_class"] == name]
        done = g[g["api10"].isin(judged)]
        n_agree = int((done["api10"].map(judged) == "agree").sum())
        state = ts.decide(n_agree, len(done), len(g))
        target = 0 if state in ("accept", "reject") else ts.CARDS_PER_CLASS if state == "round 2" else ts.ROUND1
        need = max(0, min(target, len(g)) - len(done))
        new = ts.sample(g[~g["api10"].isin(seen)], need) if need else g.iloc[0:0]
        status[name] = {"n": int(c["n"]), "n_cohort": int(c["n_cohort"]), "prior_judged": len(done), "prior_agree": n_agree, "state_before": state, "new_cards": len(new)}
        for _, s in done.iterrows():
            text, src = verbatim[s["api10"]]
            rows.append({**{k: s.get(k) for k in _COLS}, "verdict": text, "verdict_source": src})
        for _, s in new.iterrows():
            rows.append({**{k: s.get(k) for k in _COLS}, "verdict": "", "verdict_source": ""})
        if len(new):
            sections.append(f"<h2 id=\"c{_esc(name)}\">{_esc(name)} — {int(c['n'])} flagged ({int(c['n_cohort'])} cohort); "
                            f"{len(done)} already judged ({n_agree} agree), {len(new)} new cards</h2>" + "".join(_card(d, xy, s) for _, s in new.iterrows()))
    sample = pd.DataFrame(rows)
    if len(carried):  # never drop a written verdict: rows not re-emitted above (free text, set-aside wells) ride along verbatim
        rest = carried[~carried["api10"].isin(sample["api10"] if len(sample) else [])]
        sample = pd.concat([sample, rest[[c for c in sample.columns if c in rest.columns]]], ignore_index=True)
    lost = set(carried["api10"]) - (set(sample["api10"]) if len(sample) else set())
    assert not lost, f"verdicts would be dropped: {sorted(lost)}"
    sample.to_csv(sample_path, index=False)
    cls.to_csv(a.out / "classes.csv")

    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    carded = cls[cls["carded"]]
    listed = cls[cls["touches_family"] & ~cls["carded"]]
    fam_conf = d[d["conflict_agree"] & (d["formation_blueox"].isin(family) | d["other_vendor"].isin(family))]
    page = [
        f"<!doctype html><html><head><meta charset=\"utf-8\"><title>Midland tag screen</title><style>{fc._CSS}</style></head><body>",
        f"<h1>{_esc(a.basin.title())} tag screen — review cards (round {a.round}){' — WHAT-IF: drafted sql/16 trigger' if a.whatif else ''}</h1>",
        (f"<div class=meta><b>What-if:</b> Novi {', '.join(_esc(t) for t in sorted(basin_coarse))} defers to Enverus in this basin (drafted sql/16, "
         f"NOT live). {whatif.get('retagged', 0):,} producer tags change before scoring; {whatif.get('kept_sql23_corrected', 0):,} sql/23-corrected rows keep "
         "their corrected tag (sql/23 not re-simulated).</div>" if a.whatif else ""),
        (f"<div class=meta>Built {built}, git {_git_sha()}, read-only; {len(d):,} producing horizontals as of {_esc(scored.attrs.get('asof'))}. "
        "Rule A: the well sits in another bench's local band (1.5-mi consensus) and at least one vote that does not come from the neighbours' tags "
        "agrees (the other vendor's label, sql/23 nearest, GOR). Rule B: Novi and Enverus disagree and the neighbourhood cannot confirm the tag "
        "(off band / ambiguous / no evidence); destination = the other vendor's bench. Mark each card agree / reject in <code>cards_sample.csv</code> "
        "(column <code>verdict</code>). Sequential: 5 cards per class; 5/5 agree accepts, 0–1/5 rejects, otherwise 5 more and the class is judged at 7/10. "
        "Accepted classes become warehouse tag overrides (ref.formation_tag_overrides) on your go; everything else keeps its tag. "
        "Star = subject; dots = wells within 1.5 mi coloured by tag (hollow = not clean evidence); dashed = local band medians.</div>"),
        (f"<p><b>{len(flagged):,} flagged</b> ({(flagged['screen_rule'] == 'A').sum():,} rule A, {(flagged['screen_rule'] == 'B').sum():,} rule B) in {len(cls)} classes; "
        f"{int(cls['touches_family'].sum())} classes ({int(cls.loc[cls['touches_family'], 'n'].sum()):,} wells) touch the Wolfcamp; "
        f"{len(carded)} of them carded (≥ {ts.MIN_COHORT_TO_CARD} cohort wells), {len(listed)} listed only. Spraberry-only classes: 20b.</p>"),
        "<div class=toc>" + "".join(f"<a href=\"#c{_esc(n)}\">{_esc(n)}</a>" for n in carded.index if status[n]["new_cards"]) + "</div>",
        "<h2>Carded classes</h2>",
        _table(["class", "flagged", "cohort", "other-vendor votes", "sql/23 votes", "GOR votes", "judged on 20a cards", "new cards"],
               [[n, _fmt(int(r.n)), _fmt(int(r.n_cohort)), _fmt(int(r.vendor_votes)), _fmt(int(r.sql23_votes)), _fmt(int(r.gor_votes)),
                 f"{status[n]['prior_judged']} ({status[n]['prior_agree']} agree)", _fmt(status[n]["new_cards"])] for n, r in carded.iterrows()]),
        "<h2>Wolfcamp classes listed, not carded (&lt; 5 cohort wells; tags stay)</h2>",
        _table(["class", "flagged", "cohort"], [[n, _fmt(int(r.n)), _fmt(int(r.n_cohort))] for n, r in listed.iterrows()]),
        ("<h2>Not flagged: vendors disagree, but the well sits in its own tag's band</h2>"
        "<p>The neighbours use the same label, so depth cannot settle the naming. Counted, not carded (<code>conflict_agree.csv</code>).</p>"),
        _table(["tag", "other vendor says", "wells", "cohort"],
               [[t, o, _fmt(len(g)), _fmt(int(g["cohort"].sum()))] for (t, o), g in fam_conf.groupby(["formation_blueox", "other_vendor"])]),
        *sections,
        "</body></html>",
    ]
    (a.out / "cards.html").write_text("".join(page), encoding="utf-8")
    summary = {"built_at": built, "git_sha": _git_sha(), "basin": a.basin, "family": a.family, "round": a.round, "whatif": whatif or None, "asof": str(scored.attrs.get("asof")),
               "n_producers": len(d), "n_flagged": len(flagged), "by_rule": flagged["screen_rule"].value_counts().to_dict(),
               "n_conflict_agree": int(d["conflict_agree"].sum()), "classes": status, "n_new_cards": int(sum(s["new_cards"] for s in status.values())),
               "seconds": round((dt.datetime.now(tz=dt.UTC) - t0).total_seconds(), 1)}
    (a.out / "summary.json").write_text(json.dumps(summary, indent=1, default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else str(x)), encoding="utf-8")
    print(f"{len(flagged):,} flagged; {len(carded)} classes carded; {summary['n_new_cards']} new cards -> {a.out / 'cards.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
