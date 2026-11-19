# BOX sticks phase 5a, second measurement: bars for the producing-well trigger

Written 2026-11-18 after Michael's review of the first measurement ("trying to reconcile against wells that are DUCs, or
worse, permits, is dubious"; "Yes, re-run it"). **Written before the second hindcast was generated or anything in it was
scored.** Committed on its own first. `BARS.md` and its verdicts stand as they are; this file does not replace them.

What was known when this was written: the first measurement in full (DESIGN.md); tag and depth quality by well stage; the
day-0 counts of the record sets with only producing wells counted (Delaware 0.76 % matched or conflict and 0.53 % crowded;
Midland 0.35 % and 0.49 %); and the SIZE of the new test population below. No well of the new population had been run
against a stick.

The thresholds are the ones of `BARS.md`, not loosened. A failed bar is reported as failed.

## What changes against BARS.md

- **Which wells take a stick out (the trigger).** Two are scored:
  - **T1, producing:** a well with a first production date.
  - **T2, producing or completed with depth evidence:** T1, plus a well with no first production whose status is DUC or
    Completed AND which has depth evidence. (Not "any well with depth evidence": a Spud well's `tvd_ft` that happens not
    to be a round 100 is still a permit depth.)
  - Every other well (Spud, anything without depth evidence under T2, permits) only flags; it takes nothing out and is
    not scored here.
- **The predicate is variant B of DESIGN.md section 4c** (no test between WCA_1 and WCA_2 in a co-developed DSU; a well
  with no depth evidence taken at the DSU's landing of its tagged bench, family otherwise; crowded on the median form).
  Variant A is reported next to it, not judged.
- Everything else is as written in BARS.md: legs, the 46 m corridor, 0.5 / 0.2, same code within 500 ft or within 150 ft
  whatever the tag, the survey path for real U-turn wells, the envelope from the set's own constants.

## The hindcast

As of 2026-01-01. Hidden from everything the generator reads: every well with a spud date after 2026-01-01, and every well
with no spud date whose first production is after it. Same pull as the first hindcast (2026-11-18 19:59 UTC, tag run 8),
generator `box_sticks_0.11` unchanged, files only. Not hidden: live tags, DSU polygons, BOX extents, rank tables, constants.

Hidden wells that pass a trigger today (counted before scoring): producing 745 (Delaware 412, of which 73 without depth
evidence; Midland 333, 1 without). DUC / Completed with depth evidence are counted in the run.

W = test wells of the trigger that are members (>= 30 % of the line inside) of a DSU holding at least one hindcast stick
of the well's formation family. Wells outside W are reported by reason.

| Bar | Measure | Passes when |
|---|---|---|
| P1 | Wells of W that take at least one stick out of open inventory (drilled, producing, conflict or crowded) | >= 80 % per basin |
| P2 | Sticks taken out / wells of W | 0.8 to 1.3 per basin |
| P3 | Wells of W with a clean match (>= 0.5 of a leg, no conflict) | >= 40 % per basin |
| P4 | Conflict sticks / sticks taken out | <= 15 % per basin |
| P5 | Hindcast sticks not open before the hidden wells are shown, visible wells judged under the same trigger | <= 0.5 % per basin |

Each bar is judged for T1 and for T2, per basin. Reported, no bar: the same under variant A; Delaware split NM / TX; the
share of W on the planned basis; the median vertical gap of clean matches with depth evidence; U-turn sticks by legs matched.

What this test cannot show: a hindcast hides a well completely, while in operation the generator already knows most wells
that turn producing as Spud / DUC at the last regeneration and has culled the row beside them. So the test measures the
predicate on a well the set has never seen, which is the hard case, not the common one.
