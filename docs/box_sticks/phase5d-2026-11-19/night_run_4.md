# Shadow night 2: run 4, written

Started 2026-11-20 11:15:20.053701+00:00, 58.3 s, rule `box_recon_1`, sets [16, 17], wells read 85059, changed 8, breaker limit 792, stale 3.

| sticks | delaware | midland |
|---|---|---|
| sticks | 46,062 | 33,138 |
| open | 45,280 | 33,027 |
| permitted | 655 | 74 |
| pending | 34 | 19 |
| producing | 73 | 16 |
| conflict | 20 | 2 |
| crowded | 69 | 48 |
| inventory | 45,900 | 33,072 |

Identities: 79,200 status rows, 79,200 locations, 79,200 record sticks (ok); inventory rule breaks 0; log rows 8 against changed 8.
Schema box: 4 sets, 159,738 stick rows, 335,352 locations, records [16, 17].
Objects reading the tables: 0.

## Changes tonight

| cause | from | to | locations |
|---|---|---|---|
| well | permitted | pending | 3 |
| well | open | open | 2 |
| well | open | permitted | 2 |
| well | open | producing | 1 |

Crowded flag changes: 2. Stale DSU x bench: 3. Conflict queue: 22 sticks.
One well, two sticks: 0 of 89 matching wells (0 within one DSU, of which 0 on one bench; 0 across DSUs only).
S8, sticks newly producing: 1; independent read agrees on 1.

## Against sql/68, per well

Wells compared: 1.

| BOX nightly (well) | sql/68 rule on Novi sticks (well) | wells |
|---|---|---|
| takes a stick out | nothing | 1 |
