"""Rule v5 class review cards (read-only) — docs/formation_tag_redesign/RULE_V5.md, acceptance.

    python -m scripts.tag_v5_cards --cache <scoreboard cache> --out docs/formation_tag_redesign/v5-cards-<date>

For each change class with >= 20 wells, a class being (basin, today's tag -> v5 tag, basis), 5 wells are drawn at
random (seed 51106) from wells that are not labelled, overridden, or on any earlier card. The gate of record applies:
5/5 accepts the class, 0-1/5 rejects it, otherwise 5 more cards and 7/10.
Each card shows the strike section of evidence wells by their LIVE tags (box.flag_cards), both vendor names, and the
witness depths of both units at the well. The pre-check is the plain median of the same witnesses within 2 mi (>= 3).
A card whose pre-check disagrees with the call is MARKED, not dropped, so the class sample stays random.
Needs producers_v5.pkl in the cache (scripts.tag_precedence_dev).

Round 2 (--round1 <scored round-1 folder>): every class whose round-1 decision is 'round 2' or 'pending' gets cards up to
10 judged (box.tag_screen.CARDS_PER_CLASS), drawn the same way with seed 51107 and excluding every earlier card. A class
still 'pending' after round 1 (a hold left it at 4 judged) goes straight to 10, since any fifth verdict leaves it in
round 2. Class numbers carry over from round 1; card numbers continue after round 1's.
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
from box import tag_screen as ts
from box.bench_qc import DEFAULT_PARAMS, _esc, _fmt, _project_xy_ft
from scripts.box_family_qc import _scored

SEED = 51106
SEED_ROUND2 = 51107
PER_CLASS = 5
MIN_CLASS = 20
DOCS = sb.ROOT / "docs" / "formation_tag_redesign"


def previously_carded() -> set[str]:
    out: set[str] = set()
    for f in DOCS.glob("*cards*/cards_sample.csv"):
        out |= set(pd.read_csv(f, dtype={"api10": str})["api10"])
    return out


def classes(d: pd.DataFrame) -> pd.DataFrame:
    ch = d[d["final"].fillna("~") != d["live"].fillna("~")]
    c = ch.groupby(["basin", "live", "final", "basis"]).size().rename("wells").reset_index()
    c = c[c["wells"] >= MIN_CLASS].sort_values("wells", ascending=False, kind="stable").reset_index(drop=True)
    c["class_no"], c["n_cards"] = np.arange(1, len(c) + 1), PER_CLASS
    return c


def class_label(basin: str, live: str, final: str, basis: str) -> str:
    return f"{basin} {live}->{final} ({basis})"


def round2_classes(cls: pd.DataFrame, round1: Path) -> pd.DataFrame:
    """The classes round 1 left open, with round-1 class numbers and the cards needed to reach 10 judged."""
    dec = pd.read_csv(round1 / "class_decisions.csv")
    dec = dec[dec["decision"].isin(["round 2", "pending"])].set_index("class")
    c = cls.copy()
    c["label"] = [class_label(*k) for k in zip(c["basin"], c["live"], c["final"], c["basis"], strict=True)]
    c = c[c["label"].isin(dec.index)].copy()
    missing = set(dec.index) - set(c["label"])
    if missing:
        raise SystemExit(f"round-1 classes not found in producers_v5.pkl: {sorted(missing)}")
    c["class_no"] = c["label"].map(dec["class_no"]).astype(int)
    c["n_cards"] = (ts.CARDS_PER_CLASS - c["label"].map(dec["judged"])).astype(int)
    return c.sort_values("class_no").reset_index(drop=True)


def plain_medians(d: pd.DataFrame, rows: pd.DataFrame, r_mi: float = 2.0) -> pd.DataFrame:
    """Plain median of each unit's witnesses within r_mi of each row (>= 3), for the pre-check."""
    wit = d[d["u_novi"].notna() & (d["u_novi"] == d["u_env"])]
    out = []
    for v in rows.itertuples():
        b = wit[wit["basin"] == v.basin]
        near = np.hypot(b["x"] - v.x, b["y"] - v.y) <= r_mi * sb.M_PER_MI
        res = []
        for u in (v.u_novi, v.u_env):
            g = b[near & (b["u_novi"] == u)]["depth_ft"] if isinstance(u, str) else pd.Series(dtype=float)
            res += [g.median() if len(g) >= 3 else np.nan, len(g)]
        out.append(res)
    return pd.DataFrame(out, columns=["med_novi", "n_novi", "med_env", "n_env"], index=rows.index)


def check(v: pd.Series) -> str:
    """Does the plain-median read agree with the v5 call (the backed vendor >= 100 ft closer)?"""
    backed = "Novi" if v["final"] == v["novi_code"] else ("Enverus" if v["final"] == v["env_code"] else None)
    if backed is None or not (np.isfinite(v["med_novi"]) and np.isfinite(v["med_env"])):
        return "no plain-median read (a unit has < 3 witnesses within 2 mi)"
    dn, de = abs(v["depth_ft"] - v["med_novi"]), abs(v["depth_ft"] - v["med_env"])
    lead = (de - dn) if backed == "Novi" else (dn - de)
    return f"agrees ({lead:.0f} ft closer to {backed}'s unit)" if lead >= 100 else f"DISAGREES (only {lead:.0f} ft closer to {backed}'s unit)"


def card(dd: pd.DataFrame, xy: np.ndarray, subj: pd.Series, v: pd.Series, table: pd.DataFrame) -> str:
    i = int(dd.index[dd["api10"] == subj["api10"]][0])
    wide = fc._neighbourhood(dd, xy, i, replace(DEFAULT_PARAMS, radius_ft=fc.SECTION_PREFILTER_FT))
    png, _ = fc.card_figure(subj, fc._neighbourhood(dd, xy, i, DEFAULT_PARAMS), DEFAULT_PARAMS, dest=v["final"],
                            section=fc.strike_section(subj, wide))
    pat = ""
    if v["basis"] == "pattern":
        by_str = "novi_raw" in table.columns
        m = (table["basin"] == v["basin"]) & ((table["novi_raw"] == v["novi_raw"]) & (table["env_raw"] == v["env_raw"]) if by_str
                                               else (table["u_novi"] == v["u_novi"]) & (table["u_env"] == v["u_env"]))
        t = table[m]
        if len(t):
            t = t.iloc[0]
            who = (f"Novi '{_esc(v['novi_raw'])}' vs Enverus '{_esc(v['env_raw'])}'" if by_str
                   else f"{_esc(v['u_novi'])} (Novi) vs {_esc(v['u_env'])} (Enverus)")
            pat = (f" · learned pattern {who}: Novi backed in {t['novi_share']:.0%} of {int(t['decided'])} depth-decided wells"
                   f" → {_esc(t['winner'])}")
    kv = (
        f"<b>card {int(v['card'])}</b> · class {int(v['class_no'])}: {_esc(v['live'])} → {_esc(v['final'])} ({_esc(v['basis'])}) · "
        f"<b>{_esc(subj['api10'])}</b> {_esc(subj['well_name'])} · {_esc(subj['operator'])} · {_esc(v['county'])} · fp {_esc(subj['first_production_date'])}<br>"
        f"depth <b>{_fmt(v['depth_ft'], 0)}</b> ft ({_esc(v['depth_source'])}; tvd_ft {_fmt(subj['tvd_ft'], 0)}) · Novi <b>{_esc(v['novi_raw'])}</b> "
        f"({_esc(v['novi_code'])}) · Enverus <b>{_esc(v['env_raw'])}</b> ({_esc(v['env_code'])}) · today <b>{_esc(v['live'])}</b> → proposed <b>{_esc(v['final'])}</b><br>"
        f"witness depths here (wells where both vendors agree): {_esc(v['u_novi'])} {_fmt(v['z_novi'], 0)} ft, {_esc(v['u_env'])} {_fmt(v['z_env'], 0)} ft · "
        f"plain medians: {_esc(v['u_novi'])} {_fmt(v['med_novi'], 0)} (n={int(v['n_novi'])}), {_esc(v['u_env'])} {_fmt(v['med_env'], 0)} (n={int(v['n_env'])}) · "
        f"check: <b>{_esc(v['check'])}</b>{pat}"
    )
    return f"<div class=card id=\"w{_esc(subj['api10'])}\"><div class=kv>{kv}</div><img src=\"{png}\"></div>"


def run(cache: Path, out: Path, round1: Path | None = None, only: list[str] | None = None, table_path: Path | None = None,
        first_card: int = 1, first_class: int = 1, seed: int = SEED, title: str = "Rule v5 — class review cards") -> Path:
    out.mkdir(parents=True, exist_ok=True)
    sample = out / "cards_sample.csv"
    if sample.exists():
        fc.guard_verdict_file(sample)
    d = pd.read_pickle(cache / "producers_v5.pkl")
    table = pd.read_csv(table_path or DOCS / "v5-dev-2026-11-06" / "precedence_table.csv")
    excl = set(sb.labelled_set()["api10"]) | previously_carded()
    cls = classes(d)
    if only:
        lab = [class_label(*k) for k in zip(cls["basin"], cls["live"], cls["final"], cls["basis"], strict=True)]
        missing = set(only) - set(lab)
        if missing:
            raise SystemExit(f"--only classes not found (>= {MIN_CLASS} wells): {sorted(missing)}")
        cls = cls[pd.Series(lab, index=cls.index).isin(only)].reset_index(drop=True)
        cls["class_no"] = np.arange(first_class, first_class + len(cls))
    if round1 is not None:
        cls = round2_classes(cls, round1)
        first_card = int(pd.read_csv(round1 / "cards_sample.csv")["card"].max()) + 1
    rng = np.random.default_rng(seed if round1 is None else SEED_ROUND2)
    picks = []
    for c in cls.itertuples():
        k = c.class_no
        pool = d[(d["basin"] == c.basin) & (d["live"] == c.live) & (d["final"] == c.final) & (d["basis"] == c.basis)
                 & d["override"].isna() & ~d["api10"].isin(excl)].sort_values("api10")
        if pool.empty:
            continue
        sel = pool.iloc[np.sort(rng.choice(len(pool), size=min(c.n_cards, len(pool)), replace=False))].copy()
        sel["class_no"], sel["class_wells"] = k, c.wells
        picks.append(sel)
    p = pd.concat(picks)
    p = p.join(plain_medians(d, p))
    p["check"] = p.apply(check, axis=1)
    p["card"] = np.arange(first_card, first_card + len(p))
    sections: dict[int, list[str]] = {}
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
            sections.setdefault(int(v["class_no"]), []).append(card(dd, xy, subj, v, table))
            rows.append({"card": int(v["card"]), "class_no": int(v["class_no"]), "class": f"{v['basin']} {v['live']}->{v['final']} ({v['basis']})",
                         "class_wells": int(v["class_wells"]), "basin": b, "api10": v["api10"], "well_name": subj["well_name"], "county": v["county"],
                         "live": v["live"], "proposed": v["final"], "check": v["check"], "verdict": "", "verdict_source": ""})
    pd.DataFrame(rows).sort_values("card").to_csv(sample, index=False)
    rnd = "" if round1 is None else " — round 2"
    heads = {c.class_no: f"{c.basin.title()} {c.live} → {c.final} ({c.basis}), {c.wells} wells{rnd}" for c in cls.itertuples()}
    built = dt.datetime.now(tz=dt.UTC).astimezone().isoformat(timespec="seconds")
    body = "".join(f"<h2>Class {k}: {_esc(heads[k])}</h2>" + "".join(v) for k, v in sorted(sections.items()))
    page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{_esc(title)}</title><style>{fc._CSS}</style></head><body>"
            f"<h1>{_esc(title)}{rnd} (vendors propose, depth decides)</h1>"
            f"<div class=meta>Built {built}, read-only. {len(rows)} cards, "
            + (f"5 per class for every change class of >= {MIN_CLASS} wells, drawn at random (seed {seed})" if round1 is None else
               f"round 2: each open class topped up to 10 judged cards, drawn at random (seed {SEED_ROUND2})")
            + " from wells that are not labelled, overridden or on any earlier card. "
            + ("Gate per class: 5/5 accepts, 0-1/5 rejects, otherwise 5 more and 7/10. " if round1 is None else
               "Each class is judged on 7/10 with its round-1 cards (a bench code in the proposed unit agrees on the unit). ")
            + "Neighbours are evidence wells only by their LIVE tags. A card whose plain-median check disagrees with "
            "the call is marked, not dropped. Mark <code>cards_sample.csv</code>: agree / reject / a bench code / free text (a hold). "
            "Nothing is applied.</div>" + body + "</body></html>")
    (out / "cards.html").write_text(page, encoding="utf-8")
    return out / "cards.html"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--round1", type=Path, help="scored round-1 folder (class_decisions.csv): draw round 2")
    ap.add_argument("--only", nargs="+", help="card only these classes, e.g. 'delaware BS3_C->BS2_S (pattern)'")
    ap.add_argument("--table", type=Path, help="precedence table shown on pattern cards (default: the v5 dev run's)")
    ap.add_argument("--first-card", type=int, default=1)
    ap.add_argument("--first-class", type=int, default=1)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--title", default="Rule v5 — class review cards")
    a = ap.parse_args(argv)
    print(run(a.cache, a.out, a.round1, a.only, a.table, a.first_card, a.first_class, a.seed, a.title))
    return 0


if __name__ == "__main__":
    sys.exit(main())
