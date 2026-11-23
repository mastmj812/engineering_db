# Shadow night 3: run 8, written

Started 2026-11-23 11:09:52.956142+00:00, 226.8 s, rule `box_recon_1`, sets [24, 25], wells read 85124, changed 3, breaker limit 792, stale 3.

| sticks | delaware | midland |
|---|---|---|
| sticks | 46,153 | 33,122 |
| open | 45,239 | 33,013 |
| permitted | 701 | 72 |
| pending | 63 | 19 |
| producing | 121 | 16 |
| conflict | 29 | 2 |
| crowded | 227 | 47 |
| inventory | 45,776 | 33,057 |

Identities: 79,275 status rows, 79,275 locations, 79,275 record sticks (ok); inventory rule breaks 0; log rows 3 against changed 3.
Schema box: 7 sets, 285,145 stick rows, 337,742 locations, records [24, 25].
Objects reading the tables: 0.

## Changes tonight

| cause | from | to | locations |
|---|---|---|---|
| well | open | permitted | 1 |
| well | pending | open | 1 |
| well | open | pending | 1 |

Crowded flag changes: 0. Stale DSU x bench: 3. Conflict queue: 31 sticks.
One well, two sticks: 1 of 136 matching wells (1 within one DSU, of which 0 on one bench; 0 across DSUs only).
S8, sticks newly producing: 0; independent read agrees on 0.

## Against sql/68, per well

Wells compared: 0.

| BOX nightly (well) | sql/68 rule on Novi sticks (well) | wells |
|---|---|---|
