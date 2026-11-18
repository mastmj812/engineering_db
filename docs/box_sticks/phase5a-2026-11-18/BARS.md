# BOX sticks phase 5a: bars for the reconciliation measurement

Written 2026-11-18, **before any stick was scored**. Committed on its own ahead of the measurement script's first run, so
the commit order is the proof. What was known when this was written: the live record sets (set 6 Delaware 46,709 sticks,
set 7 Midland 33,829; pull 2026-11-18 18:26 UTC), the count of wells by status and state, and that 574 horizontals carry a
spud date after 2026-09-30 (the 2026Q3 vintage date; Delaware NM 198, Delaware TX 104, Midland 272). No match, overlap or
status count had been computed.

The bars stand as written. A failed bar is reported as failed; nothing is tuned afterwards.

## The predicate being measured

Grain: stick LEG against well. A U-turn stick has two legs.

- **Well line.** `curated.wells.wellstick_geom`; for a well the survey marks `is_uturn`, the survey path
  (`curated.well_lateral_survey.lateral_geom`), because the wellstick of a real U-turn is a short line across the legs.
- **Corridor.** 46 m (150 ft) either side of the well line (sql/20 / sql/68).
- **Overlap** of a leg = length of the leg inside the corridor / length of the leg.
- **Depth evidence** of a well (the generator's rule): not a planned survey; survey lateral median TVD, else `tvd_ft`;
  at least 4,000 ft; a round-100 `tvd_ft` without a survey is not evidence.
- **Same bench.** With depth evidence: (same `formation_blueox` and within 500 ft of the stick's target TVD) or within
  150 ft whatever the tag. Without depth evidence: same formation family (`box.sticks.core.family`) as the stick,
  `match_basis = 'planned'`.
- **Well classes.** producing = has a first production date. drilled = no first production and (status Spud / DUC /
  Completed, or a spud date) and status is not Permit Cancelled. permit = status Permit Approved with no spud date.
  Everything else is ignored and counted.
- **Leg.** Among producing + drilled wells that pass the bench test: one well at >= 0.5 = matched; two or more at >= 0.5,
  or the best in [0.2, 0.5) = conflict; else open. Permits are judged apart and never make a conflict.
- **Stick.** conflict if any leg is in conflict; else producing / drilled if any leg is matched (producing only when every
  matched leg's well produces); else permitted if a permit covers >= 0.5 of a leg; else open.
- **Crowded** (a flag on open / permitted sticks): a producing or drilled well alongside >= 30 % of a leg and inside the
  record set's stored envelope (`box.location_set.cfg -> generator`: same landing within 150 ft vertically and 400 ft
  sideways; the stacked rectangles within 300 ft). Measured in the corridor form: share of the leg within the sideways
  limit of the well line. A well without depth evidence crowds its formation family within 400 ft.

## Day 0: the record sets against today's wells

The record sets were generated with every producing and Spud / DUC / Completed well known, and the generator culls a row
inside the envelope. So on the day of the pull almost nothing should match.

| Bar | Measure | Passes when |
|---|---|---|
| D1 | Sticks whose status is drilled, producing or conflict, per basin | <= 0.5 % of the basin's sticks. Each listed with its cause |
| D2 | Open sticks flagged crowded, per basin | <= 0.5 % of the basin's sticks. This is the corridor form of the envelope disagreeing with the generator's own link measure |
| D3 | The draft SQL on live against the Python reference, stick by stick | >= 99.5 % of sticks get the same status, both basins |
| D4 | Wall time of the draft SQL on the live session pooler, both basins together | <= 300 s, and EXPLAIN shows `box_location_stick_geom_gix` or `box_location_stick_geog_gix` |

Reported, no bar: sticks flagged permitted, by state, split by depth evidence / planned basis.

## Back-test: wells spudded since the 2026Q3 vintage

A hindcast set per basin: a fresh pull, every well with a spud date after 2026-09-30 removed from what the generator
reads, generator `box_sticks_0.11` unchanged. Files only; nothing stored. Not hidden: live tags, the DSU polygons, the
BOX extents, the rank tables and every constant (the phase 3a back-test's caveat). The hidden wells are then run through
the predicate against the hindcast sticks.

W = hidden wells that are members (>= 30 % of the line inside) of a DSU holding at least one hindcast stick of the well's
formation family. Wells outside W are reported by reason (no DSU, no bench row there).

| Bar | Measure | Passes when |
|---|---|---|
| B1 | Wells of W that take at least one stick out of open inventory (drilled, conflict or crowded) | >= 80 % per basin. A drilled well has to show up in the count |
| B2 | Sticks taken out of open inventory / wells of W | between 0.8 and 1.3 per basin. Under 0.8 the count lags drilling; over 1.3 one well removes too much |
| B3 | Wells of W with a clean match (>= 0.5 of a leg, no conflict) | >= 40 % per basin. Reason for 40: a grid with the right count and an arbitrary phase gives 300 / spacing (34 % at 880 ft); the phase 3a back-test found the phase is no better than arbitrary |
| B4 | Conflict sticks / sticks taken out | <= 15 %. Above that the review queue is the output |
| B5 | Hindcast sticks not open before the hidden wells are shown (drilled, producing, conflict or crowded from visible wells) | <= 0.5 % per basin (the same thing D1 + D2 measure, on the hindcast set) |

Reported, no bar: the share of W matched on the planned basis, by state; the same counts with a U-turn stick needing BOTH
legs matched; wells of W that touch sticks in two or more DSUs.

Not measured here: sql/68 on the same wells. `curated.reconciled_inventory` reads producing wells only and no well has a
first production date after 2026-09-30 in the warehouse today (latest 2026-09-30), so sql/68 has nothing to say about
these 574 wells yet.
