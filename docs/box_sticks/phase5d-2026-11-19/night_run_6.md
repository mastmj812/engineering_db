# Shadow night 1: run 6, written

Started 2026-11-21 11:11:49.010062+00:00, 231.1 s, rule `box_recon_1`, sets [24, 25], wells read 85065, changed 81420, breaker limit 792, stale 0.

| sticks | delaware | midland |
|---|---|---|
| sticks | 46,153 | 33,122 |
| open | 45,375 | 33,014 |
| permitted | 665 | 72 |
| pending | 30 | 18 |
| producing | 60 | 16 |
| conflict | 23 | 2 |
| crowded | 69 | 47 |
| inventory | 46,001 | 33,057 |

Identities: 79,275 status rows, 79,275 locations, 79,275 record sticks (ok); inventory rule breaks 0; log rows 81,420 against changed 81420.
Schema box: 7 sets, 285,145 stick rows, 337,742 locations, records [24, 25].
Objects reading the tables: 0.

## Changes tonight

| cause | from | to | locations |
|---|---|---|---|
| set_change | open | open | 76,202 |
| set_change | None | open | 2,147 |
| set_change | open | stopped | 2,061 |
| set_change | permitted | permitted | 649 |
| set_change | producing | producing | 65 |
| set_change | None | permitted | 55 |
| set_change | permitted | stopped | 45 |
| set_change | pending | pending | 41 |
| set_change | permitted | open | 36 |
| set_change | open | permitted | 32 |
| set_change | producing | stopped | 24 |
| set_change | conflict | conflict | 21 |
| set_change | pending | stopped | 12 |
| set_change | None | producing | 11 |
| set_change | producing | open | 4 |
| set_change | None | pending | 4 |
| set_change | conflict | stopped | 3 |
| set_change | None | conflict | 3 |
| set_change | open | pending | 2 |
| set_change | producing | permitted | 1 |

Crowded flag changes: 27. Stale DSU x bench: 0. Conflict queue: 25 sticks.
One well, two sticks: 0 of 76 matching wells (0 within one DSU, of which 0 on one bench; 0 across DSUs only).
S8, sticks newly producing: 0; independent read agrees on 0.

## Against sql/68, per well

Wells compared: 133.

| BOX nightly (well) | sql/68 rule on Novi sticks (well) | wells |
|---|---|---|
| conflict | conflict | 5 |
| conflict | nothing | 18 |
| conflict | realizes | 2 |
| crowds only | conflict | 5 |
| crowds only | nothing | 21 |
| crowds only | realizes | 6 |
| takes a stick out | conflict | 3 |
| takes a stick out | nothing | 58 |
| takes a stick out | realizes | 15 |
