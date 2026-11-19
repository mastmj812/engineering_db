# BOX sticks gate 5b: bars for the authored nightly reconciliation

Written 2026-11-19, **before the nightly module's SQL was run on anything**. Committed on its own first. Branch
`claude/box-sticks-phase5b`, cut from main at `b0affb5` (PR #259 merged). Record sets: set 16 (Delaware, 46,062 sticks) and
set 17 (Midland, 33,138), generator `box_sticks_0.12`, pull 2026-11-19 01:00 UTC.

## What is being authored (the shape Michael agreed 2026-11-18)

- **Stick status**, one row per record stick, recomputed every night: open / permitted / pending / producing / conflict.
  Only a **producing** well takes a stick out. A matching well that is drilled but not producing sets `pending`, an approved
  permit sets `permitted`; both stay in inventory. Overlap of a leg inside the well's 150 ft corridor: >= 0.5 = match, 0.3
  to 0.5 = conflict. Same code within 500 ft TVD, or within 150 ft whatever the tag.
- The three generator rules mirrored: no test between WCA_1 and WCA_2 in a co-developed DSU; a well with no depth evidence
  is taken at the DSU's landing of its tagged bench (family only where that bench has no row); crowded on the median form
  (at least half of the alongside length inside the set's sideways limit, alongside >= 30 %).
- **Flat-ended corridors**; the well line as generator 0.12 reads it (surface step-out dropped; a real U-turn on its
  survey path).
- **Stale row**, one per DSU x bench holding a producing well of that bench that the record set never read: the wells, and
  an estimated stick count = the lower of (sticks minus sticks out by status) and (sticks minus new producers, not below 0).
- Written by a nightly hook into ETL-owned tables; `box.*` is read, never written.

## Bars

| Bar | Measure | Passes when |
|---|---|---|
| E1 | The module's SQL on live (read-only) against the Python reference, stick by stick, sets 16 and 17 | >= 99.5 % of sticks with the same status, and >= 99.5 % with the same crowded flag, per basin |
| E2 | Wall time of the module's read-only pass on the live session pooler, both basins, status + stale | <= 300 s; EXPLAIN names `box_location_stick_geog_gix` |
| E3 | Day 0 on sets 16 and 17: sticks producing or in conflict; sticks crowded | each <= 0.5 % of the basin's sticks |
| E4 | The stale estimate on the 5a pair (generator 0.12 as of 2026-01-01 against the same inputs regenerated with the 745 producers put back), over the DSU x bench holding a new producer | total within +-10 % of the regenerated count per basin; mean absolute error lower than each single estimate; exactly right on >= 50 % |
| E5 | Rehearsal container, sql/NN applied by the apply script | every check of the apply script passes; applying twice changes nothing |
| E6 | Container, night 1 | status rows = record sticks by identity, one per location; log rows = status rows, all `first_run`; one run row `written` |
| E7 | Container, night 2 with nothing changed | 0 log rows; status table identical but for the run id; run row `written`, `changed = 0` |
| E8 | Container, failure and absence | with the tables absent the hook returns without error and writes nothing; with a forced SQL error it does not raise, the status table is untouched and a `failed` run row exists; a forced mass change writes only a `breaker` run row |

E4 was seen on a close variant in 5a (the lower of the two: -7 % Delaware, +8 % Midland, exact on 58 % / 64 %), after the
bars of that round. Here it is the bar, on the final predicate (30 % floor, flat ends), so the numbers may move.

Not judged in 5b: nights on live (gate 5d), and anything that reads these tables (gate 5 proper).
