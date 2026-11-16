"""Screen every human call (seeds/formation_tag_overrides.csv) against today's data. Read-only.

    python -m box.tag_rule_inputs --cache <dir>            # then Steps 1-3 (see a queue-card README)
    python -m scripts.tag_human_call_review --cache <dir> --out docs/formation_tag_redesign/<folder>

A human call wins in sql/16 whatever the data does afterwards, and the nightly never re-judges it. This asks, per call:

  depth now vs then   the depth, depth source and header TVD the review card printed (card sets from 2026-11-06 on;
                      older calls recorded no depth) against today's
  today's benches     the rule's witness depth of every bench at the well (2 mi, >= 3 witnesses, the well left out):
                      'holds' = the called bench is the nearest, or less than margin_ft behind the nearest
  depth support       survey or header TVD; the Novi and Enverus header TVDs behind a header-only depth

Writes screen.csv (every call), listed.csv (the wells to card, for scripts.tag_v5_2_cards --listed; input = the
call, proposed = today's nearest bench) and depth_doubt.csv (header-only depths the two vendors disagree on).
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

import numpy as np
import pandas as pd

from box import tag_grossmiss as gm
from box import tag_precedence as tp
from scripts.tag_rule_seeds import CARD_SETS, DOCS, OVERRIDES
from scripts.tag_v5_2_cards import refs_at

MOVED_FT = 100.0       # a depth change since the card worth a second look
HEADER_GAP_FT = 300.0  # Novi vs Enverus header TVD on a well with no survey depth
_DEPTH = re.compile(r"depth ([\d,]+) ft \((\w+); tvd_ft ([\d,]+)\)")
_SQL_NOVI = '''SELECT n."API10"::text, COALESCE(wd."TVD", n."TVD") FROM raw_novi."Wells" n
               LEFT JOIN raw_novi."WellDetails" wd ON wd."API10" = n."API10" WHERE n."API10"::text = ANY(%s)'''
_SQL_ENV = """SELECT DISTINCT ON (LEFT(api_uwi_14_unformatted, 10)) LEFT(api_uwi_14_unformatted, 10), tvd_ft, updateddate
              FROM raw_enverus.wells WHERE LEFT(api_uwi_14_unformatted, 10) = ANY(%s)
              ORDER BY LEFT(api_uwi_14_unformatted, 10), updateddate DESC NULLS LAST"""


def carded_depths() -> pd.DataFrame:
    """api10 -> the depth its (latest) review card printed."""
    rows = []
    for s, _ in CARD_SETS:
        f = DOCS / s / "cards.html"
        if not f.exists():
            continue
        parts = re.split(r'<div class=card id="w(\d+)">', re.sub(r"<svg.*?</svg>", " ", f.read_text(encoding="utf-8"), flags=re.DOTALL))
        for api, body in zip(parts[1::2], parts[2::2], strict=True):
            m = _DEPTH.search(html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))))
            if m:
                rows.append({"api10": api, "card_set": s, "then_depth_ft": float(m[1].replace(",", "")),
                             "then_source": m[2], "then_tvd_ft": float(m[3].replace(",", ""))})
    return pd.DataFrame(rows).drop_duplicates("api10", keep="last")


def classify(call_gap: float, near_code: object, near_gap: float, call: str, same_unit: bool) -> str:
    if not np.isfinite(near_gap):
        return "no witnesses near"
    if not np.isfinite(call_gap):
        return "called bench has no witnesses"
    if near_code == call or call_gap - near_gap < tp.RULE.margin_ft:
        return "holds"
    return "sub-bench nearer" if same_unit else "another unit nearer"


def screen(d: pd.DataFrame, seed: pd.DataFrame) -> pd.DataFrame:
    cw = gm.code_witness(d)
    call = seed.set_index("api10")["corrected_code"]
    rows = []
    for i in d.index[d["api10"].isin(seed["api10"])]:
        v = d.loc[i]
        b, c, dep = v["basin"], call[v["api10"]], float(v["depth_ft"])
        refs = refs_at(d, cw, v)
        gaps = sorted((abs(dep - z[0]), k) for k, z in refs.items())
        near = gaps[0] if gaps else (np.nan, None)
        cg = abs(dep - refs[c][0]) if c in refs else np.nan
        same = isinstance(near[1], str) and tp.unit(b, near[1]) == tp.unit(b, c)
        rows.append({"api10": v["api10"], "basin": b, "county": v["county"], "well_name": v["well_name"], "call": c,
                     "depth_ft": dep, "depth_source": v["depth_source"], "tvd_ft": v["tvd_ft"],
                     "call_gap_ft": cg, "call_n": refs[c][2] if c in refs else 0, "near_code": near[1],
                     "near_gap_ft": near[0], "near_n": refs[near[1]][2] if gaps else 0,
                     "today": classify(cg, near[1], near[0], c, same),
                     "benches_here": "; ".join(f"{k} {z[0]:.0f} (n={z[2]})" for k, z in sorted(refs.items(), key=lambda t: t[1][0]))})
    return pd.DataFrame(rows)


def header_tvds(ids: list[str]) -> pd.DataFrame:
    from etl.db import get_connection
    with get_connection() as c, c.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(_SQL_NOVI, (ids,))
        nv = pd.DataFrame(cur.fetchall(), columns=["api10", "novi_tvd_ft"])
        cur.execute(_SQL_ENV, (ids,))
        en = pd.DataFrame(cur.fetchall(), columns=["api10", "enverus_tvd_ft", "enverus_updated"])
    out = nv.merge(en, on="api10", how="outer")
    for c in ("novi_tvd_ft", "enverus_tvd_ft"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["enverus_updated"] = pd.to_datetime(out["enverus_updated"]).dt.date
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    seed = pd.read_csv(OVERRIDES, dtype=str, keep_default_na=False)
    d = pd.read_pickle(a.cache / "producers_v5_2.pkl")
    o = screen(d, seed).merge(carded_depths(), on="api10", how="left").merge(header_tvds(seed["api10"].tolist()), on="api10", how="left")
    o["depth_moved_ft"] = o["depth_ft"] - o["then_depth_ft"]
    o["note"] = o["api10"].map(seed.set_index("api10")["note"])
    out = seed[["api10", "corrected_code"]].rename(columns={"corrected_code": "call"}).merge(o.drop(columns="call"), on="api10", how="left")
    out["today"] = out["today"].fillna("not in the judged frame")
    out["note"] = out["api10"].map(seed.set_index("api10")["note"])
    a.out.mkdir(parents=True, exist_ok=True)
    out.round(1).to_csv(a.out / "screen.csv", index=False)

    moved = o["depth_moved_ft"].abs() >= MOVED_FT
    nearer = o["today"].isin(["sub-bench nearer", "another unit nearer"])
    li = o[moved | nearer].copy()
    li["group"] = np.where(moved[li.index], "1 depth moved", "2 another bench nearer")
    li["proposed"] = np.where(nearer[li.index], li["near_code"], li["call"])
    li["input"] = li["call"]
    why = [f"depth was {t:,.0f} ft ({s}) on the card, now {n:,.0f} ft ({ns}); " if m else ""
           for t, s, n, ns, m in zip(li["then_depth_ft"], li["then_source"], li["depth_ft"], li["depth_source"], moved[li.index], strict=True)]
    li["note"] = [f"HUMAN CALL {c} ({nt.split(':')[0][:110]}). {w}today {c} is {g:,.0f} ft off, {k} {kg:,.0f} ft (n={n})"
                  for c, nt, w, g, k, kg, n in zip(li["call"], li["note"], why, li["call_gap_ft"], li["near_code"], li["near_gap_ft"], li["near_n"], strict=True)]
    li = li.sort_values(["group", "basin", "county", "well_name"])
    li[["api10", "input", "proposed", "group", "note"]].to_csv(a.out / "listed.csv", index=False)

    hdr = o[(o["depth_source"] == "tvd_ft") & ((o["novi_tvd_ft"] - o["enverus_tvd_ft"]).abs() >= HEADER_GAP_FT)]
    hdr = hdr[["api10", "well_name", "county", "call", "tvd_ft", "novi_tvd_ft", "enverus_tvd_ft", "enverus_updated",
               "call_gap_ft", "near_code", "near_gap_ft", "today"]].sort_values(["county", "well_name"]).round(0)
    hdr.assign(verdict="").to_csv(a.out / "depth_doubt.csv", index=False)

    print(f"{len(seed)} human calls; {len(o)} in the judged frame")
    print(out["today"].value_counts().to_string())
    print(f"header-only depth: {(o['depth_source'] == 'tvd_ft').sum()}  (Enverus is the only source on "
          f"{((o['depth_source'] == 'tvd_ft') & o['novi_tvd_ft'].isna()).sum()})")
    print(f"depth on a card: {o['then_depth_ft'].notna().sum()}; moved >= {MOVED_FT:.0f} ft: {int(moved.sum())}; "
          f"survey arrived since: {int(((o['then_source'] == 'tvd_ft') & (o['depth_source'] == 'survey')).sum())}")
    print(f"listed.csv {len(li)} wells; depth_doubt.csv {len(hdr)} wells")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
