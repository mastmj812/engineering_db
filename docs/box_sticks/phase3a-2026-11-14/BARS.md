# BOX sticks, phase 3a: definitions and pass/fail bars for the generator pilot, fixed before the first generator run (2026-11-14)

Committed before any generator code exists. Amended 2026-11-15 with Michael's decisions (section "Decided" below),
still before any generator code. After the first generator run nothing here is tuned: a missed bar is reported as missed.

Scope: the three pilot areas of `PROPOSAL.md` (114 DSU polygons, 990 DSU x bench; `pilot_dsus.csv`). About six single
DSUs outside the blocks (Eddy E-W near-squares, the WCA no-control fringe, Midland U-turns) get cards only and are not
counted in any bar. Live tags, cache
pulled 2026-11-14. Nothing is written to the warehouse.

## Definitions

- **Stick** = one generated well: one leg (straight) or two legs and a turn (U-turn). **Leg** = one row position;
  counts of slots are counts of legs.
- **Counted well** = an existing well the generator must respect: every producer at any age, plus spud / DUC /
  completed wells (rule 1). A counted well with no depth evidence pins its bench's grid and closes 400 ft sideways to
  its formation family (rule 2).
- **Pair metric** = the phase 2b link method (`scripts/box_sticks_phase2b.links`), stick-relative: alongside = share of
  the leg the well runs beside; sideways gap = median perpendicular distance over the shared length (21 samples);
  vertical gap = well evidence depth minus stick target TVD. A pair qualifies at >= 30 % alongside.
- **Envelope** = candidate D as decided 2026-11-14 (same landing within 150 ft vertically: 400 ft sideways; stacked
  within 300 ft sideways: well deeper by 150-350 ft, or shallower by 150-250 ft Delaware / 150-350 ft Midland).
- **Adjacent benches** = two benches with sticks in the same DSU and no bench with sticks between them in depth.

## Generator invariants

Each is 0 violations on the pilot output, and each has a DB-free pytest on synthetic DSUs.

| # | Invariant | Bar |
|---|---|---|
| I1 | Envelope | No placed leg is inside the envelope of a counted well with depth evidence (pair metric). Against a counted well with no depth evidence: no placed leg of its formation family within 400 ft sideways |
| I2 | Stagger | (a) Two adjacent benches whose map spacings are within 15 % share the better-controlled bench's spacing, and every row of one sits half a spacing (within 1 ft) from the rows of the other, unless one of them is pinned by existing wells. ~~(b) Always: no leg is closer than 300 ft, sideways gap and TVD difference combined, to a leg of the adjacent bench; a row that would be is not placed, reason `stagger` (rule 10)~~ **(b) struck 2026-11-15 after the step 3 cards, see "Amended after the cards" below** |
| I3 | Order | In every DSU the target TVDs of the benches with sticks are in stratigraphic order and at least 75 ft apart. A bench has one landing; where its own wells show two, the DSU x bench carries the flag `two_landings_observed` (rule 3) |
| I4 | Well type | No single-leg stick has a completed lateral under 7,000 ft. A two-leg stick exists only in a DSU whose straight lateral is under 7,000 ft, on adjacent rows of one bench, and its legs are at least 1,200 ft apart: legs at max(bench spacing, 1,200 ft); an odd leg or a single open slot is not placed (rule 5) |
| I5 | Inside the DSU | Every leg lies inside its DSU polygon less the 330 ft setback, within 1 ft. Rows are fitted to the width that is clear along the whole lateral: the spacing may be tightened by up to 10 % to keep the row count (never under 440 ft, U-turn legs never under 1,200 ft); beyond 10 % one row is dropped and the rest spread evenly. A grid pinned by existing wells is not moved; an outer row that still clips is culled, reason `setback_clip` |
| I6 | Provenance | Every stick carries DSU id, bench, generator version, azimuth and its basis, `tvd_basis` (direct / thickness / bracket / offset, with the rung's held-out median and P90), `spacing_basis` (n_eff, weighted median, band value, map value, final value after any sharing or setback fit), well type, legs with gunbarrel offsets |
| I7 | Ledger | Every DSU x bench of the pilot is accounted for: legs placed, legs culled each with exactly one reason from a closed list, or one reason the bench has no row. Rows considered = placed + culled. No row disappears at a setback without a reason |
| I8 | Gunbarrel | The golden table of `tests/test_gunbarrel_convention.py` passes on the function the generator uses, and every stored leg offset is reproduced from its geometry within 1 ft (sign rule v2, azimuth at 0.1 deg, true to grid through `dealintake/geo.true_to_grid`) |
| I9 | Repeatable | The same inputs give a byte-identical output file |

## Back-test

Cutoff **2023-01-01**. Hidden from everything the generator reads (spacing gaps, landing evidence, row pinning,
envelope, azimuth): every producer with first production on or after the cutoff and every well not yet producing.
The spacing map and the landing surfaces are rebuilt without them.

Not hidden, stated as limits: the tags (live, learned with today's wells), the 2026Q3 DSU polygons (drawn with today's
wells in view), the BOX extents, the phase 1 thickness tables, and the spacing and envelope constants. It is a test of
placement inside today's frame, not a clean out-of-time test.

Population **W**: hidden producers with >= 30 % of their lateral in a pilot DSU, tagged with a bench that is eligible
in that DSU. Before the eligibility filter: 135 (Ward), 293 (Lea), 294 (Glasscock / Midland) producers in 63 DSUs.

**A well lands on a slot** when it is matched one-to-one to a placed leg of the same bench with: shared length at
least half of the shorter of the two; sideways gap at most min(330 ft, half the leg's spacing); and, where the well has
depth evidence, |stick TVD - well depth| at most 150 ft. Where a DSU got one WCA row set (rule 4: the one-member and
no-control classes, or surfaces under 75 ft apart), WCA_1 / WCA_2 / WCXY wells match on the family. Wells with no depth
evidence are matched without the depth test and counted separately. In a DSU x bench flagged `two_landings_observed`
the depth test is skipped (T1) and the pairs are left out of T5; both are reported separately.

**U-turn DSUs** (straight lateral under 7,000 ft): T1, T3 and T4 are judged on straight DSUs only. U-turn DSUs are
reported beside them as context. Operators drill short straights at bench spacing in the best rock; reproducing that
is not a goal of BOX sticks (Michael, 2026-11-15).

**Drilled-across DSU x bench**: at least 3 hidden wells of the bench, no same-bench well before the cutoff, and the
outer hidden wells within one generated spacing of both setback lines.

| # | Bar | Fixed value |
|---|---|---|
| T1 | Wells that land on a slot | >= 60 % of W over the three areas, and >= 50 % in each. Reason for 60: a grid with the right count and an arbitrary phase scores about 660 / spacing (75 % at 880 ft, 50 % at 1,320 ft), so 60 % needs both the count and the hang of the rows to be about right |
| T2 | Wells on a bench that got no row | <= 10 % of W sit on a bench the generator gave no row in that DSU (no depth, dropped in reconciliation, fully culled). Misses are reported by reason |
| T3 | Count | In drilled-across DSU x bench: generated legs within 1 of the wells drilled in >= 70 % of them, and total generated legs / total wells drilled between 0.85 and 1.20 |
| T4 | Unused slots | In drilled-across DSU x bench: unmatched generated legs <= 25 % of generated legs |
| T5 | Depth | Pairs matched on bench and sideways gap only, wells with depth evidence. Direct rung: median |TVD difference| <= 75 ft and >= 80 % within 150 ft. Carried rungs: the observed median <= 1.5 x the rung's held-out median, reported per rung |
| T6 | Envelope (reported, not a bar) | Share of W lying inside the envelope of a well that was on production before the cutoff. Phase 2b measured 1.15 % Delaware and 1.57 % Midland |

If fewer than 15 DSU x bench are drilled across, T3 and T4 are reported and marked "too few to judge".

## Comparison with Novi (reported, not a bar)

Per pilot area and bench: sticks and lateral footage BOX against Novi, and stick TVD minus same-bench producer landing
depth (the phase 0 bust) for both, on today's wells.

## Decided (Michael, 2026-11-15)

Rules: 1 every producer plus spud / DUC / completed; 2 no-depth well pins and closes 400 ft to its family; 3 one landing
per bench with a flag; 4 WCA_1 and WCA_2 both placed only in the co-developed class (each member >= 8 depth-evidenced
producers within 3 mi, and >= 3 DSUs within 3 mi drilled in both making >= 25 % of the WCA-drilled DSUs there), no
envelope test between them there, otherwise one WCA row set at the locally dominant member; 5 U-turn legs at
max(spacing, 1,200 ft), adjacent rows; 6 lithology members each get their own rows; 7 sliver floor 10 % of DSU area;
8 azimuth = wells inside the DSU, then the 6-mi cell (>= 10 horizontals), then the county, snapped to a polygon side,
the long axis with a flag where the two sides tie; 9 narvi pinned by commit; 10 as I2. Setback fit as I5 (10 %).
Bars: cutoff 2023-01-01 and T1 at 60 % / 50 % kept; two-landing and U-turn treatment as written above.

## Amended after the cards (Michael, 2026-11-15, before any back-test)

**I2(b) is struck: rows of different benches are not tested against each other.** Raised on the card of DSU 10785,
where 4 of 5 BS1_S rows were not placed for sitting 170-236 ft from AVA_2 rows (landings 156 ft apart, spacings 1,096 ft
against 849 ft). Michael: distance to another bench's planned row should not govern placement. BOX sticks represent
what is possible in the DSU, and what is possible is set by the extents the DSU lies in, what has already been drilled,
and the density / spacing evidence of each extent. Two benches 100-300 ft apart may or may not be developed together;
that is for BOX precedence downstream. The envelope against existing wells (I1) is unchanged.

Effect on the 114 pilot DSUs, today's wells: 144 rows no longer culled; 1,332 -> 1,469 sticks (1,523 -> 1,666 legs).
150 pairs of legs of different benches are under 300 ft apart (sideways and vertical combined) in 46 DSUs, 36 of them
under 150 ft vertically; they are reported, not a violation. The reason `stagger` leaves the closed list of row reasons.
Generator version `box_sticks_0.2_pilot`. This removes a bar; it was changed on a stated decision before the back-test
ran, not to make a test pass.

**I2(a) is narrowed: no bench takes another bench's spacing.** Michael, same day: each bench keeps its own map spacing
(the density evidence of its own extent). Before this, 59 DSU x bench in 41 of the 114 pilot DSUs ran at a neighbour's
spacing (Midland DSU 22309: WCB_2 mapped at 757 ft, run at WCA_1's 664 ft). What remains of I2(a): two adjacent benches
under 300 ft apart in TVD whose own spacings are equal (within 0.5 ft) sit half a spacing apart, unless one is pinned.
`shared_with` leaves the spacing basis. Generator version `box_sticks_0.3_pilot`; effect on the pilot in
`cards/README.md` and the run summary.

## Clarifications written with the generator (2026-11-15, after the invariant checks first ran, before any back-test)

Stated here because they narrow or interpret a bar above; none changes a threshold.

- **I2(a) applies to adjacent benches less than 300 ft apart in TVD.** Farther apart, each bench keeps its own map
  spacing (per-bench density). Sharing chains through a stack: where three
  close benches are each within 15 % of the next, all take the best-controlled one's spacing.
- **I2(a) is checked against the bench a row grid was set against** (recorded as `stagger_ref`), not against the nearest
  bench that kept sticks. The first version of the check picked the nearest surviving bench and reported 25 false
  violations on the pilot (rows half a spacing off a bench whose own rows were all culled); the generator output was
  identical before and after the check was corrected.
- **I5 row count to keep** = the rows the DSU would hold if its sides ran parallel to the azimuth (window area over the
  longest row, at the map spacing). The clear width is found per DSU from the row-length profile.
- **I4, straight or U-turn** is decided on the longest row the DSU offers along the resolved azimuth, not on the
  polygon's long axis.
- **Azimuth:** wells inside the DSU within 5 deg of a polygon side take the side's bearing (narvi's own edge-snap gate),
  so rows run parallel to the setback line; farther off, the wells' bearing is kept.
