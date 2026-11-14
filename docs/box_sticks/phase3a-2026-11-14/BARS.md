# BOX sticks, phase 3a: definitions and pass/fail bars for the generator pilot, fixed before the first generator run (2026-11-14)

Committed before any generator code exists. Proposed values; Michael may amend them before his go. After the first
generator run nothing here is tuned: a missed bar is reported as missed.

Scope: the three pilot areas of `PROPOSAL.md` (114 DSU polygons, 990 DSU x bench; `pilot_dsus.csv`). Live tags, cache
pulled 2026-11-14. Nothing is written to the warehouse.

## Definitions

- **Stick** = one generated well: one leg (straight) or two legs and a turn (U-turn). **Leg** = one row position;
  counts of slots are counts of legs.
- **Counted well** = an existing well the generator must respect. Which wells count, and what a well with no depth
  evidence does, are open rules 1 and 2 of `PROPOSAL.md`. The bars apply to the set Michael decides.
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
| I1 | Envelope | No placed leg is inside the envelope of a counted well with depth evidence (pair metric). Against a counted well with no depth evidence, the rule decided under open rule 2 holds |
| I2 | Stagger | (a) Two adjacent benches on the same spacing: every row of one sits half a spacing (within 1 ft) from the rows of the other, unless one of them is pinned by existing wells. (b) Always: no leg is closer than 300 ft in 3-D (sideways gap and TVD difference combined) to a leg of the adjacent bench. Reading of "never under 300 ft": narvi's 3-D inter-zone offset; if Michael means 300 ft sideways, (b) is restated before the first run. How (b) is met where adjacent benches carry different spacings is open rule 10 |
| I3 | Order | In every DSU the target TVDs of the benches with sticks are in stratigraphic order and at least 75 ft apart. Two landings of one bench (open rule 3) are one bench for this test and are at least 150 ft apart |
| I4 | Well type | No single-leg stick has a completed lateral under 7,000 ft. A two-leg stick exists only in a DSU whose straight lateral is under 7,000 ft, and its legs are at least the decided leg separation apart (open rule 5) |
| I5 | Inside the DSU | Every leg lies inside its DSU polygon less the 330 ft setback, within 1 ft |
| I6 | Provenance | Every stick carries DSU id, bench, generator version, azimuth and its basis, `tvd_basis` (direct / thickness / bracket / offset, with the rung's held-out median and P90), `spacing_basis` (n_eff, weighted median, band value, final value), well type, legs with gunbarrel offsets |
| I7 | Ledger | Every DSU x bench of the pilot is accounted for: legs placed, legs culled each with exactly one reason from a closed list, or one reason the bench has no row. Rows considered = placed + culled |
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
depth evidence, |stick TVD - well depth| at most 150 ft. Where a DSU got one WCA landing, WCA_1 / WCA_2 / WCXY wells
match on the family. Wells with no depth evidence are matched without the depth test and counted separately.

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
