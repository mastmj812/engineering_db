# Night 0 (baseline): the read-only pass, nothing written

Rule `box_recon_1`, record sets [16, 17], 136.2 s. Tables: 0 run rows, 0 status rows.

| sticks | delaware | midland |
|---|---|---|
| sticks | 46,062 | 33,138 |
| open | 45,283 | 33,027 |
| permitted | 656 | 74 |
| pending | 31 | 19 |
| producing | 72 | 16 |
| conflict | 20 | 2 |
| crowded | 68 | 47 |
| inventory | 45,902 | 33,073 |

Stale DSU x bench: 3. Conflict queue: 22 sticks.
One well, two sticks: 0 of 88 matching wells (0 within one DSU, of which 0 on one bench; 0 across DSUs only).

## Against sql/68, per well

Wells compared: 218.

| BOX nightly (well) | sql/68 rule on Novi sticks (well) | wells |
|---|---|---|
| conflict | conflict | 5 |
| conflict | nothing | 16 |
| conflict | realizes | 1 |
| crowds only | conflict | 10 |
| crowds only | nothing | 94 |
| crowds only | realizes | 4 |
| takes a stick out | conflict | 7 |
| takes a stick out | nothing | 65 |
| takes a stick out | realizes | 16 |
