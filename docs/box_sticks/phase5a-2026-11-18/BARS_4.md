# BOX sticks phase 5a, fourth measurement: a DSU-level signal next to the stick status

Written 2026-11-18 after Michael's "yes, should we pursue this now?" on the DSU signal, with two decisions of the same day
applied: **drop trigger = producing only**, **conflict floor = 30 %**. **Written before the truth run was generated and before
any DSU count was compared.** Committed on its own first. The earlier bar files and their verdicts stand.

## The question

`FINDINGS_2.md`: a new producer lands on or beside a particular stick about 83 % of the time in the Midland and 60 % in the
Delaware, so a stick-by-stick status under-counts. What a regeneration does is re-lay the rows of that DSU and bench around
the new well. Can a signal that needs no stick identity say, the night the well produces, how many sticks that DSU x bench
will have after a regeneration?

## The signal

Per DSU x bench of the record set: `new_producers` = wells with a first production date that the set did not know as
producers, tagged that bench, and members of the DSU (>= 30 % of the LATERAL inside the polygon; the lateral as generator
0.12 reads it). The DSU x bench is `stale` when `new_producers > 0`, and its estimated stick count is
`sticks - new_producers`, never below 0.

## The measurement

- **Before:** a 2026-01-01 hindcast as in `BARS_2.md` (every well spudded after 2026-01-01 hidden).
- **Truth:** the same inputs regenerated with the hidden PRODUCERS put back (745 wells) and the not-yet-producing ones still
  hidden. Files only. This is what a regeneration gives once those wells produce.
- **Correction, still before any run:** both runs use generator `box_sticks_0.12` on the pull of 2026-11-18 22:37 UTC, not
  0.11. The 0.11 hindcast of `BARS_2.md` is not reused, so the two sides differ in the hidden producers and nothing else.
- **Judged on:** every DSU x bench that holds hindcast sticks and at least one new producer of that bench ("touched").
- Three estimates of the regenerated stick count, none of which regenerates: **nothing** (the hindcast count), **stick level**
  (hindcast count minus the sticks the nightly predicate takes out: producing trigger, variant B, 30 % floor), **DSU signal**.

| Bar | Measure | Passes when |
|---|---|---|
| G1 | Total sticks over the touched DSU x bench, DSU-signal estimate against the regenerated count, per basin | within +-10 % |
| G2 | Mean absolute error per touched DSU x bench, DSU signal against stick level, per basin | DSU signal is lower |
| G3 | Share of touched DSU x bench where the DSU-signal estimate equals the regenerated count | >= 50 % per basin |
| G4 | New producers that fire the signal on a DSU x bench holding sticks of their own code | >= 70 % per basin |

Reported, no bar: the same three numbers for "nothing" and "stick level"; and the DSU x bench with NO new producer whose
count still changes in the regeneration (spacing map and landing surface move when wells are added), since the signal says
nothing about those.

If G1 to G3 fail, the honest reading is that neither the stick status nor a per-DSU subtraction predicts a regeneration,
and only regenerating does.
