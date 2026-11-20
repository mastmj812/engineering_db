"""BOX sticks identity: carry location ids from one generation run to the next (phase 4; the D73 / D83 idea on our own sticks).

Pure and DB-free. A stick is the same location in the next run when it sits in the same DSU and bench and its legs run
along the previous stick's legs: shared length >= MIN_SHARE of the shorter stick, legs within CORRIDOR_FT sideways.
Matching is 1:1, greedy by share then by sideways offset. A carried stick keeps its slot number; a new one takes the
next unused number of its DSU x bench (numbers are never reused); a previous stick with no successor stops.

Depth is not part of identity: a location whose landing moved is the same location with a new target TVD. Bench is
(D73): a row set that changed bench is a new location.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

FT_PER_M = 3.280839895
CORRIDOR_FT = 220.0        # half the tight cap (440 ft): two rows of one bench can never both sit inside it
MIN_SHARE = 0.5            # D73 / D83


@dataclass(frozen=True)
class Stick:
    key: str                               # the run's own handle (well_name, or a location id for the previous run)
    pad_id: int
    bench: str
    legs: tuple[tuple[tuple[float, float], tuple[float, float]], ...]   # ((heel x, y), (toe x, y)) in metres, work CRS
    slot: int | None = None                # previous run only

    @property
    def length_ft(self) -> float:
        return sum(math.dist(a, b) for a, b in self.legs) * FT_PER_M


def _leg_share(a: tuple, b: tuple, corridor_ft: float) -> tuple[float, float]:
    """(shared length ft, sideways offset ft) of leg b along leg a; (0, inf) when b is outside the corridor."""
    (ax, ay), (bx, by) = a
    la = math.hypot(bx - ax, by - ay)
    if la < 1.0:
        return 0.0, math.inf
    ux, uy = (bx - ax) / la, (by - ay) / la
    t, d = zip(*(((x - ax) * ux + (y - ay) * uy, (x - ax) * -uy + (y - ay) * ux) for x, y in b), strict=True)
    lo, hi = max(0.0, min(t)), min(la, max(t))
    if hi <= lo or t[0] == t[1]:
        return 0.0, math.inf
    # sideways distance at the middle of the shared interval
    f = ((lo + hi) / 2.0 - t[0]) / (t[1] - t[0])
    off = abs(d[0] + f * (d[1] - d[0])) * FT_PER_M
    return ((hi - lo) * FT_PER_M, off) if off <= corridor_ft else (0.0, math.inf)


def share(a: Stick, b: Stick, corridor_ft: float = CORRIDOR_FT) -> tuple[float, float]:
    """(share of the shorter stick that runs alongside, length-weighted sideways offset ft). Each leg of b is used once."""
    pairs = sorted(((*_leg_share(la, lb, corridor_ft), i, j) for i, la in enumerate(a.legs) for j, lb in enumerate(b.legs)), key=lambda p: -p[0])
    used_i: set[int] = set()
    used_j: set[int] = set()
    tot = wt = 0.0
    for ln, off, i, j in pairs:
        if ln <= 0.0 or i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        tot += ln
        wt += ln * off
    short = min(a.length_ft, b.length_ft)
    return (tot / short, wt / tot) if tot > 0.0 and short > 0.0 else (0.0, math.inf)


def crosswalk(prev: list[Stick], new: list[Stick], corridor_ft: float = CORRIDOR_FT, min_share: float = MIN_SHARE,
              used: dict[tuple[int, str], int] | None = None) -> dict:
    """{"carried": {new key: (prev key, slot, share, offset ft)}, "new": {new key: slot}, "stopped": [prev key]}.
    used: the highest slot number EVER issued per (pad_id, bench), from every earlier set and not only `prev`. A location
    that stopped two sets ago still holds its number, so a new stick must start above it (found 2026-11-20 at the third
    stored generation: the previous set alone gave a number an older location already had)."""
    used = used or {}
    P: dict[tuple, list[Stick]] = defaultdict(list)
    N: dict[tuple, list[Stick]] = defaultdict(list)
    for s in prev:
        P[(s.pad_id, s.bench)].append(s)
    for s in new:
        N[(s.pad_id, s.bench)].append(s)
    carried: dict[str, tuple] = {}
    fresh: dict[str, int] = {}
    stopped: list[str] = []
    for g in sorted(set(P) | set(N)):
        ps, ns = P.get(g, []), N.get(g, [])
        cand = []
        for n in ns:
            for p in ps:
                sh, off = share(p, n, corridor_ft)
                if sh >= min_share:
                    cand.append((-sh, off, p.key, n.key, p.slot))
        got_p: set[str] = set()
        got_n: set[str] = set()
        for sh, off, pk, nk, slot in sorted(cand):
            if pk in got_p or nk in got_n:
                continue
            got_p.add(pk)
            got_n.add(nk)
            carried[nk] = (pk, slot, round(-sh, 4), round(off, 1))
        nxt = max(max((p.slot or 0 for p in ps), default=0), int(used.get(g, 0))) + 1
        # new sticks take the next numbers in cross-section order (the order the generator lists them in)
        for n in ns:
            if n.key not in got_n:
                fresh[n.key] = nxt
                nxt += 1
        stopped += [p.key for p in ps if p.key not in got_p]
    return {"carried": carried, "new": fresh, "stopped": stopped}


def seed(new: list[Stick]) -> dict[str, int]:
    """First run: slot = the stick's position in its DSU x bench, in the order given (cross-section order)."""
    n: dict[tuple, int] = defaultdict(int)
    out = {}
    for s in new:
        n[(s.pad_id, s.bench)] += 1
        out[s.key] = n[(s.pad_id, s.bench)]
    return out
