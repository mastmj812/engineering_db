"""BOX step 20a — a Midland consensus-flag swap class vs its Delaware analogue (D134 B; read-only, pure).

Plan docs/box_type_curves_plan.md §5 step 20 / D134 B (gate 19): the Midland applies the Delaware class rule of record
(box/qc_rule.py) as written; "a swap class is carded only when its flag rate or GOR / TVD signature is clearly unlike its
Delaware analogue". The analogue of a Midland class is the SAME pooled class in the Delaware (same consensus detector, same
sql/23 audit, same scoring code), measured on the Delaware pull of the same day.

Signature per pooled swap class (flagged wells whose tag pool differs from the suggested pool, WCXY suggestions dropped as
in the cards):
    rate_per_k     flags per 1,000 producing horizontals tagged into the class's FROM pool;
    sql23_concur   share whose sql/23 nearest band = the suggestion (the rule's second vote);
    gor_own        share whose GOR vote says the well produces like its OWN tag (the rule's veto);
    own_delta_ft   median |TVD - own local band median| (how far the well sits from its tagged band).

"Clearly unlike" (stated here, before any card is drawn; the gate confirms or replaces it): the Midland class holds
>= MIN_FLAGS flags AND the Delaware class holds >= MIN_ANALOGUE flags AND at least one of
    rate ratio (Midland / Delaware) >= RATE_RATIO or <= 1 / RATE_RATIO;
    |sql23_concur difference| >= SHARE_DIFF;
    |gor_own difference| >= SHARE_DIFF;
    own_delta_ft ratio >= TVD_RATIO or <= 1 / TVD_RATIO.
A class with no Delaware analogue is listed, not carded: the rule's default for an uncalibrated class (tag kept) applies,
exactly as it would in the Delaware.
"""

from __future__ import annotations

import html
from typing import Any

import numpy as np
import pandas as pd

from box import qc_rule as qr
from box.family_qc import class_standing
from box.flag_cards import NEVER_INTO, pool

MIN_FLAGS = 20
MIN_ANALOGUE = 10
RATE_RATIO = 2.0
SHARE_DIFF = 0.25
TVD_RATIO = 1.5

COLS = ["n", "from_pool", "n_from_tagged", "rate_per_k", "sql23_concur", "gor_own", "gor_suggest", "own_delta_ft",
        "nearest_delta_ft", "n_cohort", "n_reassigned", "standing"]


def class_signatures(scored: pd.DataFrame, family: tuple[str, ...]) -> pd.DataFrame:
    """Per pooled swap class touching the family (from or to a family bench's pool): the signature columns (COLS)."""
    fam = {pool(b) for b in family}
    x = scored.assign(from_pool=scored["formation_blueox"].map(pool))
    n_tagged = x["from_pool"].value_counts()
    f = x[(x["cons_status"] == "flag") & x["cons_suggest"].notna()].copy()
    f = f[~f["cons_suggest"].isin(NEVER_INTO)]
    f["to_pool"] = f["cons_suggest"].map(pool)
    f = f[(f["from_pool"] != f["to_pool"]) & (f["from_pool"].isin(fam) | f["to_pool"].isin(fam))]
    if f.empty:
        return pd.DataFrame(columns=COLS)
    f["swap_class"] = f["from_pool"] + "->" + f["to_pool"]
    f["box_action"] = qr.apply_rule(f)["box_action"].values
    f["concur"] = f["sql23_nearest"] == f["cons_suggest"]
    g = f.groupby("swap_class")
    out = pd.DataFrame({
        "n": g.size(),
        "from_pool": g["from_pool"].first(),
        "sql23_concur": g["concur"].mean(),
        "gor_own": g["cons_gor_vote"].apply(lambda s: float((s == "own").mean())),
        "gor_suggest": g["cons_gor_vote"].apply(lambda s: float((s == "suggest").mean())),
        "own_delta_ft": g["cons_own_delta"].apply(lambda s: float(pd.to_numeric(s, errors="coerce").abs().median())),
        "nearest_delta_ft": g["cons_nearest_delta"].apply(lambda s: float(pd.to_numeric(s, errors="coerce").abs().median())),
        "n_cohort": g["cohort"].sum().astype(int),
        "n_reassigned": g["box_action"].apply(lambda s: int((s == "reassign").sum())),
        "standing": [class_standing(c, s.iloc[0]) for c, s in g["cons_suggest"]],
    })
    out["n_from_tagged"] = out["from_pool"].map(n_tagged).astype(int)
    out["rate_per_k"] = out["n"] / out["n_from_tagged"] * 1000.0
    return out[COLS].sort_values("n", ascending=False)


def _ratio(a: float, b: float) -> float:
    return a / b if b and np.isfinite(a) and np.isfinite(b) else np.nan


def compare(mid: pd.DataFrame, dela: pd.DataFrame) -> pd.DataFrame:
    """Midland classes (rows) with their Delaware analogue's signature, the ratios / differences and the verdict:
    ``unlike`` (card it), ``alike`` (rule as written), ``no analogue`` (rule default) or ``small`` (< MIN_FLAGS)."""
    j = mid.join(dela, rsuffix="_del", how="left")
    rows = []
    for cls, r in j.iterrows():
        n_del = 0 if pd.isna(r.get("n_del")) else int(r["n_del"])
        rr = _ratio(r["rate_per_k"], r.get("rate_per_k_del", np.nan))
        ds = r["sql23_concur"] - r.get("sql23_concur_del", np.nan)
        dg = r["gor_own"] - r.get("gor_own_del", np.nan)
        tr = _ratio(r["own_delta_ft"], r.get("own_delta_ft_del", np.nan))
        why = []
        if np.isfinite(rr) and (rr >= RATE_RATIO or rr <= 1 / RATE_RATIO):
            why.append(f"flag rate {rr:.2f}x")
        if np.isfinite(ds) and abs(ds) >= SHARE_DIFF:
            why.append(f"sql/23 concurrence {ds:+.0%}")
        if np.isfinite(dg) and abs(dg) >= SHARE_DIFF:
            why.append(f"GOR own-vote {dg:+.0%}")
        if np.isfinite(tr) and (tr >= TVD_RATIO or tr <= 1 / TVD_RATIO):
            why.append(f"own-band TVD offset {tr:.2f}x")
        if r["n"] < MIN_FLAGS:
            verdict = "small"
        elif n_del < MIN_ANALOGUE:
            verdict = "no analogue"
        else:
            verdict = "unlike" if why else "alike"
        rows.append({"swap_class": cls, "rate_ratio": rr, "sql23_diff": ds, "gor_own_diff": dg, "tvd_ratio": tr,
                     "verdict": verdict, "why": "; ".join(why) if verdict == "unlike" else ""})
    v = pd.DataFrame(rows).set_index("swap_class")
    return j.join(v)


def unlike_classes(cmp: pd.DataFrame) -> list[str]:
    return list(cmp.index[cmp["verdict"] == "unlike"])


def _f(v: Any, nd: int = 0, pct: bool = False) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    if pct:
        return f"{v:.0%}"
    return f"{v:,.{nd}f}"


def render_section(cmp: pd.DataFrame, n_tagged_note: str, cards_href: str | None) -> str:
    """The family page's D134 B section: every Midland class next to its Delaware analogue, the verdict and why."""
    head = ["swap class", "standing (rule of record)", "Midland flags", "per 1,000 tagged", "Delaware flags", "per 1,000 tagged",
            "sql/23 concurs Mid / Del", "GOR votes own Mid / Del", "median own-band Δ ft Mid / Del", "rule reassigns (Mid)", "D9 cohort (Mid)", "verdict", "why"]
    rows = []
    for cls, r in cmp.iterrows():
        rows.append([cls, r["standing"], _f(r["n"]), _f(r["rate_per_k"], 1), _f(r.get("n_del")), _f(r.get("rate_per_k_del"), 1),
                     f"{_f(r['sql23_concur'], pct=True)} / {_f(r.get('sql23_concur_del'), pct=True)}",
                     f"{_f(r['gor_own'], pct=True)} / {_f(r.get('gor_own_del'), pct=True)}",
                     f"{_f(r['own_delta_ft'])} / {_f(r.get('own_delta_ft_del'))}", _f(r["n_reassigned"]), _f(r["n_cohort"]),
                     f"<b>{r['verdict']}</b>" if r["verdict"] == "unlike" else r["verdict"], r["why"]])
    th = "".join(f"<th>{html.escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c if str(c).startswith('<b>') else html.escape(str(c))}</td>" for c in row) + "</tr>" for row in rows)
    un = unlike_classes(cmp)
    return (
        "<h2 id=analogue>4b. Midland swap classes vs their Delaware analogue (D134 B: card only a class clearly unlike it)</h2>"
        f"<p>Same detector, same sql/23 audit, same code, both basins pulled the same day ({html.escape(n_tagged_note)}). "
        f"Test stated before any card was drawn: a class with ≥ {MIN_FLAGS} Midland flags and ≥ {MIN_ANALOGUE} Delaware flags is "
        f"<b>unlike</b> when its flag rate is ≥ {RATE_RATIO:g}× or ≤ 1/{RATE_RATIO:g}× the Delaware's, or sql/23 concurrence or the GOR "
        f"own-vote share differs by ≥ {SHARE_DIFF:.0%} points, or the median own-band TVD offset is ≥ {TVD_RATIO:g}× or ≤ 1/{TVD_RATIO:g}×. "
        "<i>no analogue</i> = fewer than the minimum Delaware flags: the rule's default (uncalibrated → tag kept) applies, as it would in the Delaware. "
        "<i>small</i> = too few Midland flags to judge.</p>"
        f"<table><tr>{th}</tr>{body}</table>"
        + (f"<p><b>Carded:</b> {', '.join(html.escape(c) for c in un)} → <a href={cards_href}>{cards_href}</a> "
           "(10 per class at evenly spaced margin quantiles; fill <code>cards_sample.csv</code> <code>verdict</code>). "
           "Until verdicts are in, these classes follow the rule as written (the extents below are built on that set).</p>" if un and cards_href else
           "<p>No class is unlike its Delaware analogue: no cards.</p>")
    )
