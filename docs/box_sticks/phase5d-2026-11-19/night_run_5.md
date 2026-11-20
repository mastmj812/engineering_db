# Out-of-band run (not a night): run 5, written

Started 2026-11-20 16:03:41.542569+00:00, 57.8 s, rule `box_recon_1`, sets [16, 17], wells read 85059, changed 27, breaker limit 792, stale 3.

| sticks | delaware | midland |
|---|---|---|
| sticks | 46,062 | 33,138 |
| open | 45,273 | 33,025 |
| permitted | 657 | 74 |
| pending | 34 | 19 |
| producing | 76 | 18 |
| conflict | 22 | 2 |
| crowded | 81 | 48 |
| inventory | 45,883 | 33,070 |

Identities: 79,200 status rows, 79,200 locations, 79,200 record sticks (ok); inventory rule breaks 0; log rows 27 against changed 27.
Schema box: 4 sets, 159,738 stick rows, 335,352 locations, records [16, 17].
Objects reading the tables: 0.

## Changes tonight

| cause | from | to | locations |
|---|---|---|---|
| well | open | open | 12 |
| well | open | permitted | 5 |
| well | open | producing | 5 |
| well | permitted | open | 3 |
| well | open | conflict | 2 |

Crowded flag changes: 12. Stale DSU x bench: 3. Conflict queue: 24 sticks.
One well, two sticks: 0 of 94 matching wells (0 within one DSU, of which 0 on one bench; 0 across DSUs only).
S8, sticks newly producing: 5; independent read agrees on 5.

## Against sql/68, per well

Wells compared: 7.

| BOX nightly (well) | sql/68 rule on Novi sticks (well) | wells |
|---|---|---|
| conflict | nothing | 2 |
| takes a stick out | conflict | 1 |
| takes a stick out | nothing | 4 |
