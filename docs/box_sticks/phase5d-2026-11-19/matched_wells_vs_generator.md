# Why sets 16 and 17 keep a stick under a producing well of the same bench

2026-11-20, read-only on live. Asked by Michael after shadow night 1. Nothing changed: no rule, no table, no stick.

Grain: the 89 sticks with status `producing` after run 4 (Delaware 73, Midland 16), each with its matching well, joined to the
generator's own record of that well in `box.location_set_well` (the tag and depth the set was generated from).

## Answer

The generator and the nightly use **different depth windows** for "this well is this stick".

| | same landing when | sideways |
|---|---|---|
| Generator 0.12 (candidate D, phase 2b; `cfg.generator` of sets 16 and 17) | well within **150 ft** TVD of the stick's target, or in a stacked band: dz +150 to +350 ft, or -250 to -150 ft (Delaware) / -350 to -150 ft (Midland), dz = well depth - stick target | 400 ft (same landing), 300 ft (stacked) |
| Nightly `box_recon_1` (inherited from sql/68) | same tag within **500 ft** TVD, or any tag within 150 ft | inside the 150 ft corridor |

All 89 wells **were read by the generator, as producers**. None is new, and none changed tag since the pull that matters here
(1 of 89 has a different live tag). The sticks were not missed; the generator looked at each of these wells and kept the row.

| How the generator read the matching well (sticks) | Delaware | Midland |
|---|---|---|
| Same tag, 350 to 500 ft shallower than the stick's target | 23 | 8 |
| Same tag, 250 to 350 ft shallower | 38 | 0 |
| Same tag, 350 to 500 ft deeper | 8 | 5 |
| Within 150 ft (stick should have been culled; see below) | 1 | 1 |
| No depth evidence in the set (screened `bad_depth` 4, `not_evidence` 1) | 3 | 2 |

So **82 of 89** are a same-tag producer sitting 250 to 500 ft off the stick's depth, outside every band of the generator's
envelope and inside the nightly's 500 ft guard.

They also sit directly over or under the stick: median sideways distance 25 ft, maximum 147 ft. That is by construction: 82
of the 89 sticks are on a **pinned** grid, where the bench's rows are laid through its existing same-bench wells. The row is
drawn on the well's map position at the DSU's landing depth for that bench; the depth cull then lets it stand because the
well is more than 150 ft (and outside the stacked bands) from that landing.

Benches: BS2_S 24, BS3_C 16, BS3_S 7, WCC 5, then 4 or fewer each. Landing rung of the stick: direct 55, thickness 14,
offset 10, bracket 3. First production of the wells: 2012 to 2026, median 2022 to 2023.

## What it means for the two rules

In 41 of the 89 (Delaware 35, Midland 6) the DSU also holds other same-bench producers within 150 ft of the stick's own
depth (approximate membership: at least 30 % of the well's lateral inside the DSU). There the bench has two real landings
in that DSU, the matching well is in the other one, and the stick is a location at the DSU's main landing under or over
it. In the other 48 no same-bench well with depth evidence sits at the stick's depth; 30 of those sticks take their depth
from a carried rung (thickness 16, offset 12, bracket 2), where a 250 to 500 ft miss may be the carried depth and not a
second landing. This note does not decide which is which.

Either way the day-0 `producing` count is mostly this difference between the two windows, not wells drilled since the sets
were made. Under the generator's own window, 2 of the 89 would be `producing` (plus the 5 with no depth evidence, judged at
their bench's landing). The 22 conflicts show the same pattern: 18 of 22 are pinned sticks with the well 250 to 500 ft off.

The same applies to the sql/68 comparison in `night_1_notes.md`: Novi carries no same-bench stick under these wells, BOX
does, because BOX's envelope allows a second location 250 ft or more above or below an existing well of the same tag.

## Two sticks that the generator's own rule should have culled

| location | basin, bench | well | first production | dz | sideways | nightly overlap | flags |
|---|---|---|---|---|---|---|---|
| 10132195 | Delaware, BS2_S | 3001546829 | 2022-05-01 | 0 ft | 10 ft | 0.547 | pinned, dsu_drilled_across |
| 10132738 | Midland, WCD | 4217339383 | 2026-07-15 | -11 ft | 9 ft | 1.000 | pinned |

Not traced here. Candidates: the overlap test at generation (the generator requires 30 % of the row alongside the well) or
the U-turn / step-out line. Worth a look before the next regeneration.

## Not decided here (yours)

1. **Which window is right for the nightly.** The 500 ft same-tag guard came from sql/68, where it absorbs permit-depth
   slop. With real depth evidence (87 of 89 matches are `match_basis = depth`) the nightly could use the record set's own
   envelope, read from `box.location_set.cfg` as the crowded rule already does. Day 0 would then read near zero, which is
   what a set generated yesterday should read. This would be a rule change (`box_recon_2`), bars first, and not during the
   shadow week unless you say so.
2. **Or the generator is too permissive**: a row pinned on a same-tag well 250 to 350 ft shallower in the Delaware is kept
   (38 sticks here; the Delaware band stops at -250, the Midland one at -350). That is candidate D as adopted in phase 2b.
3. Until one of them changes, the nightly takes out about 89 sticks and flags 22 that the generator deliberately placed.
