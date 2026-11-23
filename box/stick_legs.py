"""BOX sticks in the PDP-proximity measurement (docs/box_sticks_plan.md phase 6, decision 3 of 2026-11-23).

The proximity code (box/prox_study.pair_signed, box/prox_pud_report.pud_links) measures a location as ONE line: overlap as a share
of that line, the gap as a median along it, the side from its heading. A BOX stick's geometry is its producing legs, and a U-turn
stick has two, about 1,200 ft apart and running opposite ways. Measured as one line (checked on pair_signed, 2026-11-23) the gap
and the side come out as the nearer leg's, but the overlap is a share of BOTH legs, so it is halved: a producer alongside half of
one leg reads 0.25, under MIN_OVERLAP (0.30), and the stick loses a parent it has. The stick's TVD and bench are per stick, so
those are unaffected.

So each leg is measured as a location of its own, and the stick takes the outcome of its MORE EXPOSED leg:

    expand()   one row per leg, keyed '<location_id>' (first leg) or '<location_id>#2' (second leg)
    ...        the existing chain runs on those keys, unchanged
    choose()   per stick, the leg that carries no forecast, else the leg with the lower factor (ties: the first leg)
    fold()     the chosen leg's row per stick, keyed by the stick again
    relabel()  a link frame cut to the chosen legs, its children named by the stick: one link per (stick, producer)

Pure functions; no database. A run on Novi sticks never comes here.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd
from shapely.geometry.base import BaseGeometry

BOX_ID_MIN = 10_000_001          # box.location.location_id of a BOX stick (sql/73); a Novi stick id is far below it
LEG_SEP = "#"
# the nightly status words (curated.box_location_status, sql/74) as the proximity store reads them
REALIZED = "producing"
NOT_DRILLABLE = ("conflict", "crowded")
STATUS_SQL = ("SELECT s.location_id, CASE WHEN s.crowded THEN 'crowded' ELSE s.status END FROM curated.box_location_status s "
              "WHERE s.location_id = ANY(%(ids)s)")
TVD_SQL = ("SELECT k.location_id, k.target_tvd_ft FROM box.location_stick k JOIN box.location_set t ON t.set_id = k.set_id AND t.is_record "
           "WHERE k.location_id = ANY(%(ids)s)")


def is_box_run(stick_ids: Iterable[Any], location_ids: Iterable[Any]) -> bool:
    """True when every row of a run is a BOX stick (stick_id = location_id >= 10,000,001). A run holding both kinds is refused."""
    s, loc = [int(x) for x in stick_ids], [int(x) for x in location_ids]
    box = [a >= BOX_ID_MIN for a in s]
    if not any(box):
        return False
    if not all(box) or s != loc:
        raise SystemExit("a run mixes BOX sticks and Novi sticks, or a BOX stick's stick_id is not its location_id: refused")
    return True


def leg_key(location_id: Any, leg_no: int) -> str:
    return str(int(location_id)) if leg_no == 1 else f"{int(location_id)}{LEG_SEP}{leg_no}"


def stick_of(key: Any) -> int:
    return int(str(key).split(LEG_SEP)[0])


def with_stick_tvd(p: pd.DataFrame, tvd: dict[int, float]) -> pd.DataFrame:
    """`p` with tvd_ft = the stick's own landing TVD (box.location_stick.target_tvd_ft of the record set). Refuses a stick without
    one: the proximity code silently skips a location with no TVD, which stores it as unexposed."""
    out = p.copy()
    out["tvd_ft"] = pd.to_numeric(out["location_id"].map(lambda x: tvd.get(int(x))), errors="coerce")
    n = int(out["tvd_ft"].isna().sum())
    if n:
        raise SystemExit(f"{n} of {len(out)} BOX sticks have no landing TVD in the record stick set (was the set regenerated since the run?): refused")
    return out


def expand(p: pd.DataFrame) -> pd.DataFrame:
    """One row per producing leg. `p` carries location_id and geom (a LineString, or a MultiLineString of legs, in projected feet).
    The result's location_id is the leg key (a string); stick_location_id and leg_no say where it came from."""
    rows = []
    for r in p.to_dict("records"):
        g: BaseGeometry = r["geom"]
        legs = list(getattr(g, "geoms", [g]))
        if not 1 <= len(legs) <= 2:
            raise SystemExit(f"BOX stick {r['location_id']} has {len(legs)} legs: refused")
        for i, leg in enumerate(legs, start=1):
            rows.append({**r, "geom": leg, "stick_location_id": int(r["location_id"]), "leg_no": i, "location_id": leg_key(r["location_id"], i)})
    return pd.DataFrame(rows, columns=[*p.columns, "stick_location_id", "leg_no"])


def choose(keep: pd.Series, factor: pd.Series) -> dict[int, str]:
    """stick -> the key of its more exposed leg. `keep` (False = the leg carries no forecast) and `factor` are indexed by leg key.
    A leg without a forecast outranks any factor; then the lower factor; then the first leg."""
    df = pd.DataFrame({"keep": keep.astype(bool), "factor": pd.to_numeric(factor, errors="coerce")})
    df["stick"] = [stick_of(k) for k in df.index]
    df["leg"] = [1 if LEG_SEP not in str(k) else int(str(k).split(LEG_SEP)[1]) for k in df.index]
    df["key"] = df.index.astype(str)
    df = df.sort_values(["stick", "keep", "factor", "leg"], na_position="last")       # keep False first, then the lower factor
    return dict(df.groupby("stick", sort=False)["key"].first().items())


def fold(d: pd.DataFrame, chosen: dict[int, str]) -> pd.DataFrame:
    """The chosen leg's row per stick, indexed by the stick's key (its location id as a string), with n_legs and exposed_leg added.
    `d` is indexed by leg key."""
    n_legs = pd.Series([stick_of(k) for k in d.index]).value_counts().to_dict()
    out = d.loc[[chosen[s] for s in sorted(chosen)]].copy()
    out["exposed_leg"] = [1 if LEG_SEP not in str(k) else int(str(k).split(LEG_SEP)[1]) for k in out.index]
    out.index = pd.Index([str(stick_of(k)) for k in out.index], name=d.index.name)
    out["n_legs"] = [int(n_legs[int(k)]) for k in out.index]
    if "location_id" in out:
        out["location_id"] = [int(k) for k in out.index]
    return out


def relabel(links: pd.DataFrame, chosen: dict[int, str], child: str = "child") -> pd.DataFrame:
    """A link frame cut to the chosen legs, children renamed to the stick: one link per (stick, producer), as
    box.pud_proximity_parent's key requires."""
    if not len(links):
        return links
    keep = links[links[child].astype(str).isin(set(chosen.values()))].copy()
    keep[child] = [str(stick_of(k)) for k in keep[child]]
    return keep.reset_index(drop=True)
