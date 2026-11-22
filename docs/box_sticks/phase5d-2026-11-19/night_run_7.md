# Shadow night 2: run 7, written

Started 2026-11-22 11:18:08.767800+00:00, 230.5 s, rule `box_recon_1`, sets [24, 25], wells read 85124, changed 419, breaker limit 792, stale 3.

| sticks | delaware | midland |
|---|---|---|
| sticks | 46,153 | 33,122 |
| open | 45,239 | 33,014 |
| permitted | 700 | 72 |
| pending | 64 | 18 |
| producing | 121 | 16 |
| conflict | 29 | 2 |
| crowded | 227 | 47 |
| inventory | 45,776 | 33,057 |

Identities: 79,275 status rows, 79,275 locations, 79,275 record sticks (ok); inventory rule breaks 0; log rows 419 against changed 419.
Schema box: 7 sets, 285,145 stick rows, 337,742 locations, records [24, 25].
Objects reading the tables: 0.

## Changes tonight

| cause | from | to | locations |
|---|---|---|---|
| well | open | open | 170 |
| well | open | permitted | 87 |
| well | open | producing | 62 |
| well | permitted | open | 47 |
| well | open | pending | 31 |
| well | open | conflict | 9 |
| well | permitted | pending | 4 |
| well | conflict | open | 3 |
| well | producing | open | 2 |
| well | permitted | conflict | 1 |
| well | pending | open | 1 |
| well | pending | pending | 1 |
| well | conflict | producing | 1 |

Crowded flag changes: 172. Stale DSU x bench: 3. Conflict queue: 31 sticks.
One well, two sticks: 1 of 136 matching wells (1 within one DSU, of which 0 on one bench; 0 across DSUs only).
S8, sticks newly producing: 63; independent read agrees on 63.

## Against sql/68, per well

Wells compared: 75.

| BOX nightly (well) | sql/68 rule on Novi sticks (well) | wells |
|---|---|---|
| conflict | conflict | 2 |
| conflict | nothing | 6 |
| conflict | realizes | 1 |
| crowds only | nothing | 3 |
| crowds only | realizes | 1 |
| takes a stick out | conflict | 2 |
| takes a stick out | nothing | 48 |
| takes a stick out | realizes | 12 |
