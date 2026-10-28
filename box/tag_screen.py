"""BOX step 20a follow-up — screen every basin producer's bench tag against its neighbourhood (read-only, pure core).

Michael (2026-10-26): many Midland PDP wells tagged WCC are questionable (worst to the north), which defeats drawing
extents around them; screen ALL Midland PDP tags against their neighbourhood bands, pick a subset for manual review,
fix the tags in the warehouse (ref.formation_tag_overrides, on his go), then re-run 20a. Spraberry classes are carded at 20b.

The consensus detector (box.bench_qc) builds its local bands from the neighbours' tags, so it is blind where a whole
neighbourhood carries the same wrong label. The screen adds votes that do not come from the neighbours:

  * other vendor  — formation_blueox takes Novi's formation unless Novi's call is coarse (sql/16 trigger list), else
                    Enverus ENVInterval; the vendor NOT used, mapped through ref.formation_crosswalk, is a second label.
                    A coarse Novi value is no vote.
  * sql/23        — the warehouse's own TVD-nearest bench (sql23_nearest).
  * GOR           — cons_gor_vote (box.bench_qc): does the well's 12-mo GOR sit nearer the suggested bench's.

Flag rules (fixed before looking at the cards):
  A  depth      cons_status = flag (sits in another bench's band) AND at least one of other vendor / sql/23 / GOR
                names the suggested bench. Destination = the suggested bench.
  B  label      the two vendors disagree AND the depth jury cannot confirm the tag (off_band / ambiguous /
                no_evidence). Destination = the other vendor's bench. Catches a shared wrong label.
Not flagged, counted: vendors disagree but the well sits in its own tag's band (``conflict_agree``) — the neighbours
use the same label, so depth cannot settle the naming. Sand <-> carbonate swaps (ambiguous_lith) are never flags.

Classes = tag -> destination per rule. A class is carded when it touches a bench of the carded family and holds
>= MIN_COHORT_TO_CARD D9-cohort wells; the sample favours cohort wells, evenly across the margin. Carding is sequential
(``decide``): ROUND1 cards, a second round only when round 1 is mixed. Michael accepts or rejects each class wholesale at
qc_rule.CLASS_GATE; a class not carded, or rejected, keeps its tags.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# sql/16 coarse / unreliable Novi formation values (Enverus wins there) — pinned to sql/16 by a test
NOVI_COARSE: frozenset[str] = frozenset({
    "WOLFCAMP A", "WOLFCAMP A (XY)", "WOLFCAMP A (XY) SHELF", "WOLFCAMP B", "LOWER SPRABERRY SAND",
    "WOLFCAMP", "BONE SPRING", "BONE SPRINGS", "SPRABERRY", "UNKNOWN", "SUB-WOODFORD",
})
# What-if only (--whatif): Novi values treated as coarse in one basin. The Midland WOLFCAMP C trigger was drafted into
# sql/16 on 2026-10-27 and DROPPED the same day (Michael), never applied: depth backed 81 of its 258 retags and opposed
# 91 (step 20a FINDINGS §8.7). A test pins that sql/16 carries none of these.
NOVI_COARSE_BY_BASIN: dict[str, frozenset[str]] = {"midland": frozenset({"WOLFCAMP C"})}
# Classes Michael parked: no more cards, never applied (tags stay), verdicts already written kept. Keyed by basin.
PARKED: dict[str, dict[str, str]] = {"midland": {
    "OTHER->WCA_1 (B)": "parked 2026-10-27 (Michael): TVD-defect bucket, not a naming class (median margin 6,225 ft; "
                        "8 of 9 verdicts TVD holds); OTHER is outside every cohort",
}}
UNCONFIRMED = ("off_band", "ambiguous", "no_evidence")
CARDS_PER_CLASS = 10
MIN_COHORT_TO_CARD = 5  # a class with fewer D9-cohort wells barely moves a bench's evidence: listed, not carded, not applied
MID_WOLFCAMP: tuple[str, ...] = ("WCA_1", "WCB_1", "WCB_2", "WCC", "WCD")


def pull_labels(conn: Any, basin: str, api10: list[str]) -> pd.DataFrame:
    """Both vendors' raw labels and their crosswalk codes for the given wells (READ ONLY transaction)."""
    sql = """
        SELECT w.api10, w.formation AS novi_formation, w.env_interval, fb.formation_blueox_source AS tag_source,
               nx.canonical_code AS novi_code, ex.canonical_code AS env_code
        FROM curated.wells w
        JOIN curated.formation_blueox fb USING (api10)
        LEFT JOIN ref.formation_crosswalk nx ON nx.basin = %(b)s AND nx.raw_value = w.formation
        LEFT JOIN ref.formation_crosswalk ex ON ex.basin = %(b)s AND ex.raw_value = w.env_interval
        WHERE w.api10 = ANY(%(a)s)
    """
    with conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql, {"b": basin, "a": api10})
        cols = [c.name for c in cur.description]
        rows = cur.fetchall()
    conn.rollback()
    return pd.DataFrame(rows, columns=cols).astype({"api10": str})


def other_vendor(row: pd.Series, basin_coarse: frozenset[str] = frozenset()) -> str | None:
    """The bench the vendor NOT used for the tag would give (None = no usable second label). ``basin_coarse`` = the
    basin's extra coarse Novi values (only once the sql/16 basin trigger is live, or in a what-if)."""
    src = row.get("tag_source")
    novi = None if (row.get("novi_formation") in NOVI_COARSE | basin_coarse) else row.get("novi_code")
    env = row.get("env_code")
    if src == "novi":
        return env if isinstance(env, str) else None
    if src == "enverus":
        return novi if isinstance(novi, str) else None
    return None  # ratified_override / unmapped: the tag is already a human call


def whatif_retag(producers: pd.DataFrame, labels: pd.DataFrame, basin: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """What the drafted sql/16 basin trigger does to the producer tags: a Novi-sourced tag whose Novi value is coarse in
    this basin takes the Enverus code instead (crosswalk gap -> '(unmapped)'; no Enverus value -> unchanged, as sql/16).
    Rows sql/23 TVD-corrected keep their corrected tag (sql/23 is not re-simulated) — an approximation, counted by the
    caller. Returns (producers, labels), both with the change applied."""
    extra = NOVI_COARSE_BY_BASIN.get(basin, frozenset())
    lab = labels.copy()
    hit = lab["novi_formation"].isin(extra) & (lab["tag_source"] == "novi") & lab["env_interval"].notna()
    new = lab.loc[hit].set_index("api10")["env_code"].fillna("(unmapped)")
    lab.loc[hit, "tag_source"] = "enverus"
    p = producers.copy()
    m = p["api10"].map(new)
    keep = p["formation_blueox_tvd_corrected"].fillna(False).astype(bool)
    p["whatif_changed"] = m.notna() & ~keep & (m != p["formation_blueox"])
    p.loc[m.notna() & ~keep, "formation_blueox"] = m[m.notna() & ~keep]
    return p, lab


def screen(scored: pd.DataFrame, labels: pd.DataFrame, basin_coarse: frozenset[str] = frozenset()) -> pd.DataFrame:
    """Apply rules A / B to a consensus-scored frame; adds other_vendor, votes_*, screen_rule, screen_dest, screen_class."""
    d = scored.merge(labels, on="api10", how="left")
    d["other_vendor"] = [other_vendor(r, basin_coarse) for _, r in d.iterrows()]
    tag = d["formation_blueox"]
    sug = d["cons_suggest"]
    d["vote_vendor"] = d["other_vendor"].notna() & (d["other_vendor"] == sug)
    d["vote_sql23"] = d["sql23_nearest"].notna() & (d["sql23_nearest"] == sug)
    d["vote_gor"] = d["cons_gor_vote"] == "suggest"
    d["n_votes"] = d[["vote_vendor", "vote_sql23", "vote_gor"]].sum(axis=1)
    conflict = d["other_vendor"].notna() & (d["other_vendor"] != tag)
    rule_a = (d["cons_status"] == "flag") & sug.notna() & (d["n_votes"] >= 1)
    rule_b = ~rule_a & conflict & d["cons_status"].isin(UNCONFIRMED)
    d["screen_rule"] = np.select([rule_a, rule_b], ["A", "B"], default="")
    d["screen_dest"] = np.where(rule_a, sug, np.where(rule_b, d["other_vendor"], None))
    d["conflict_agree"] = conflict & (d["cons_status"] == "agree")
    hit = d["screen_rule"] != ""
    d["screen_class"] = np.where(hit, tag + "->" + d["screen_dest"].astype(str) + " (" + d["screen_rule"] + ")", "")
    # margin for sampling: A = own-band delta / suggested-band delta (inf = own band absent); B = nearest-band delta (ft)
    own = d["cons_own_delta"].astype(float)
    near = d["cons_nearest_delta"].astype(float).clip(lower=1)
    d["screen_margin"] = np.where(rule_a, np.where(own.isna(), np.inf, own / near), np.where(rule_b, d["cons_nearest_delta"].astype(float), np.nan))
    return d


def classes(d: pd.DataFrame) -> pd.DataFrame:
    """One row per screen class: counts overall / cohort, vote mix, how many are north of 31.765 N."""
    f = d[d["screen_rule"] != ""]
    g = f.groupby("screen_class")
    out = pd.DataFrame({
        "rule": g["screen_rule"].first(), "from": g["formation_blueox"].first(), "to": g["screen_dest"].first(),
        "n": g.size(), "n_cohort": g["cohort"].sum(), "vendor_votes": g["vote_vendor"].sum(), "sql23_votes": g["vote_sql23"].sum(),
        "gor_votes": g["vote_gor"].sum(), "median_margin": g["screen_margin"].median(),
    })
    return out.sort_values(["n_cohort", "n"], ascending=False)


def touches(cls_from: str, cls_to: str, family: tuple[str, ...]) -> bool:
    return cls_from in family or cls_to in family


def sample(cls: pd.DataFrame, n: int = CARDS_PER_CLASS) -> pd.DataFrame:
    """Cohort wells first (the ones that change a bench's evidence), evenly across the margin; a class of <= n in full."""
    if len(cls) <= n:
        return cls.sort_values(["screen_margin", "api10"])
    pool = cls[cls["cohort"]] if cls["cohort"].sum() >= n else cls
    s = pool.sort_values(["screen_margin", "api10"]).reset_index(drop=True)
    idx = np.unique(np.round(np.linspace(0, len(s) - 1, n)).astype(int))
    return s.iloc[idx]


ROUND1 = 5  # cards per class in round 1 (sequential, below)


def clear_verdict(text: Any, dest: str | None = None) -> str:
    """A card verdict as the class count reads it: 'agree' / 'reject' / '' (not counted). 'reject...' with a comment is a
    reject; a bare bench code is the reviewer's own destination (agree when it is the proposed one, else reject for the
    class — the well-level call is kept verbatim in the file); any other free text is a hold, never counted."""
    v = "" if text is None or (isinstance(text, float) and np.isnan(text)) else str(text).strip()
    low = v.lower()
    if low == "agree":
        return "agree"
    if low.startswith("reject"):
        return "reject"
    if v and v == v.upper() and " " not in v and any(ch.isalpha() for ch in v):
        return "agree" if dest is not None and v == dest else "reject"
    return ""


def reuse_verdict(text: Any, card_dest: str, live_dest: str | None, known: set[str]) -> str:
    """How an earlier card counts for the move proposed NOW ('' = it does not apply). A card counts only for the move it
    was drawn for (same destination); a bench-code verdict is the reviewer's call on the well and answers any move."""
    if live_dest is None:
        return ""
    v = "" if text is None or (isinstance(text, float) and np.isnan(text)) else str(text).strip()
    if v in known or card_dest == live_dest:
        return clear_verdict(v, live_dest)
    return ""


def unknown_bench_codes(texts: Any, known: set[str]) -> list[str]:
    """Verdicts written as a bench code that is not a real code (a typo like 'WCB2' would otherwise count as a reject)."""
    out = []
    for t in texts:
        v = "" if t is None or (isinstance(t, float) and np.isnan(t)) else str(t).strip()
        if v and v.lower() != "agree" and not v.lower().startswith("reject") and v == v.upper() and " " not in v                 and any(ch.isalpha() for ch in v) and v not in known:
            out.append(v)
    return sorted(set(out))


def decide(n_agree: int, n_judged: int, n_class: int, gate: float = 0.70) -> str:
    """Sequential class decision. A class carded in full is judged on its precision. Otherwise round 1 = ROUND1 cards:
    all agree -> accept; so few agree that even 5 more agrees cannot reach the gate on 10 -> reject; else round 2 tops up to
    CARDS_PER_CLASS and the class is judged at the gate."""
    if n_judged == 0:
        return "pending"
    if n_judged >= n_class or n_judged >= CARDS_PER_CLASS:
        return "accept" if n_agree / n_judged >= gate else "reject"
    if n_judged >= ROUND1:
        if n_agree == n_judged:
            return "accept"
        if n_agree + (CARDS_PER_CLASS - n_judged) < gate * CARDS_PER_CLASS:
            return "reject"
        return "round 2"
    return "pending"


def card_target(state: str, n_class: int) -> int:
    """Total cards a class should hold in its state. 'full review' (Michael's call on a decided class, e.g. when depth
    disagrees with its sample) cards every flagged well, and each card then decides only its own well."""
    if state == "full review":
        return n_class
    if state in ("accept", "reject", "parked"):
        return 0
    return CARDS_PER_CLASS if state == "round 2" else ROUND1


SEED_TAG = "tag screen step 20a"  # every row this screen seeds carries it, so a re-seed replaces exactly its own block


def override_seed(flags: pd.DataFrame, cards: pd.DataFrame, well_calls: pd.DataFrame, states: dict[str, dict],
                  card_dates: dict[str, str], date: str) -> pd.DataFrame:
    """ref.formation_tag_overrides rows (api10, corrected_code, was, note) from a finished screen, convention (a) as
    amended 2026-10-28 (FINDINGS §8.4 / §8.9 / §8.10):
      * a card decides its own well, whatever its class did: 'agree' -> the card's destination; a bench code -> that
        bench (nothing when it is the live tag); reject / hold / free text -> nothing;
      * an ACCEPTED class moves its uncarded wells to the class destination ('full review' and 'parked' classes move
        nobody uncarded; rejected classes neither);
      * well_calls.csv rows (chat / what-if calls) land as written; a well also carded must carry the same call.
    ``states`` = summary.json classes; ``card_dates`` maps verdict_source -> the date that round was judged."""
    rows: dict[str, dict] = {}
    carded = set(cards["api10"])
    for r in cards.itertuples():
        v = "" if pd.isna(r.verdict) else str(r.verdict).strip()
        to = r.screen_dest if v.lower() == "agree" else v if v and v == v.upper() and " " not in v else None
        if to is None or to == r.formation_blueox:
            continue
        rows[r.api10] = {"api10": r.api10, "corrected_code": to, "was": r.formation_blueox,
                         "note": f"carded {card_dates[r.verdict_source]} ({r.verdict_source} card, {r.screen_class}: {v}); "
                                 f"ratified by MM; {SEED_TAG}"}
    for name, s in states.items():
        if s["state_before"] != "accept":
            continue
        g = flags[(flags["screen_class"] == name) & ~flags["api10"].isin(carded)]
        for r in g.itertuples():
            rows[r.api10] = {"api10": r.api10, "corrected_code": r.screen_dest, "was": r.formation_blueox,
                             "note": f"class-accepted {name} {s['prior_agree']}/{s['prior_judged']} cards {date}; "
                                     f"convention (a); {SEED_TAG}"}
    for r in well_calls.itertuples():
        if r.api10 in rows:
            if rows[r.api10]["corrected_code"] != r.call:
                raise ValueError(f"{r.api10}: card says {rows[r.api10]['corrected_code']}, well_calls says {r.call}")
            continue
        rows[r.api10] = {"api10": r.api10, "corrected_code": r.call, "was": r.live_tag,
                         "note": f"{r.source} {r.date}: {r.note}; ratified by MM; {SEED_TAG}"}
    return pd.DataFrame(list(rows.values()), columns=["api10", "corrected_code", "was", "note"]).sort_values("api10", ignore_index=True)
