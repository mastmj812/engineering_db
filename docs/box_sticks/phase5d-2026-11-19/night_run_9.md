# Shadow night 4: run 9, written

Started 2026-11-24 11:16:50.481258+00:00, 53.9 s, rule `box_recon_1`, sets [24, 25], wells read 85187, changed 174, breaker limit 792, stale 5.

| sticks | delaware | midland |
|---|---|---|
| sticks | 46,153 | 33,122 |
| open | 45,224 | 32,979 |
| permitted | 702 | 73 |
| pending | 63 | 35 |
| producing | 131 | 28 |
| conflict | 33 | 7 |
| crowded | 278 | 110 |
| inventory | 45,711 | 32,977 |

Identities: 79,275 status rows, 79,275 locations, 79,275 record sticks (ok); inventory rule breaks 0; log rows 174 against changed 174.
Schema box: 7 sets, 79,275 stick rows, 337,742 locations, records [24, 25].
Objects reading the tables: 0.

## Changes tonight

| cause | from | to | locations |
|---|---|---|---|
| well | open | open | 121 |
| well | open | producing | 22 |
| well | open | pending | 16 |
| well | open | conflict | 9 |
| well | open | permitted | 4 |
| well | permitted | open | 2 |

Crowded flag changes: 122. Stale DSU x bench: 5. Conflict queue: 40 sticks.
One well, two sticks: 3 of 156 matching wells (3 within one DSU, of which 0 on one bench; 0 across DSUs only).
S8, sticks newly producing: 22; independent read agrees on 21.

## Against sql/68, per well

Wells compared: 28.

| BOX nightly (well) | sql/68 rule on Novi sticks (well) | wells |
|---|---|---|
| conflict | conflict | 2 |
| conflict | no_tvd | 1 |
| conflict | nothing | 5 |
| takes a stick out | no_tvd | 1 |
| takes a stick out | nothing | 18 |
| takes a stick out | realizes | 1 |
