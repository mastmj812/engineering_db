# Rule v3 — development-fold sanity run (2026-11-05, before scoring; rule revision 1)

```
python -m scripts.tag_rule_dev --cache <scoreboard cache> --out <this folder>
```

This run is read-only, on the scoreboard's cached pull from 2026-11-05. Per RULE.md §2 it reports only churn (all
wells), the guards, and the band test on development-fold wells (even 6-mi cells, 28,812 clean wells). The labelled
set, grid agreement and the test fold have NOT been computed.

These are the numbers after **revision 1** (RULE.md §5: grid control measured on every interval boundary). The
first run, at the freeze commit, never grid-controlled a well in his XY→A or A→B1 interval. In Delaware it judged
7,944 families by grid and moved 734 families; the revised figures follow.

**Churn: producing horizontals whose code changes, rule vs vendor (no overrides)**

| Basin | Wells | Code changes | Family changes |
|---|---|---|---|
| Delaware | 31,821 | 2,571 (8.1 %) | 852 (2.7 %) |
| Midland | 28,865 | 1,251 (4.3 %) | 723 (2.5 %) |

Family changes stay under the K11 cap of 5 %.

Largest moves (`moves_from_to.csv`):
- Delaware WCA_2→WCA_1: 542
- Midland WCB_1→WCB_2: 413
- Delaware WCA_1→WCA_2: 358
- Delaware WCA_1→WCXY: 236
- Delaware WCXY→WCA_1: 223
- Midland WCA_1→WCB_1: 185
- Midland LSSH→JM: 172
- Midland WCB_1→WCA_1: 172
- Delaware WCA_2→WCB_1: 147
- Delaware WCB_1→WCA_2: 127, the up-move revision 1 enables

Moves run in both directions, which is what fixing the 9–11 % inverted thin splits should look like.

**Guards (K10):**
- 0 moves into or out of WDFD / BRNT / MISS;
- 0 BS2 / BS3 sand↔carbonate swaps;
- 0 XY crossings in Lea or Ward.

Blocked moves were flagged instead: 137 for lithology, 144 for rule B (pending), and 69 `family_conflict`.

**Basis.**
- Delaware family checks: 14,509 used the grid, 11,329 used local bands, and 2,885 had no clean depth.
- Midland: 26,413 used local bands.
- Positions inside multi-code families: Delaware 10,065 placed by local bands, and 5,534 kept the vendor code
  because depth could not resolve the split there (Q1 (a)).

**Confidence** (clean wells in multi-code families):
- Delaware WCA: 5,711 high / 5,749 low.
- Delaware WCB: 1,150 high / 1,800 low.
- Delaware AVA: 831 high / 595 low.
- Midland WCB: 4,333 high / 4,128 low.

**Band test, development fold, 1 mi:**

| Basin | vendor | rule |
|---|---|---|
| Delaware | 9.7 % | 5.6 % |
| Midland | 6.0 % | 3.1 % |

This is **partly by construction**, because the rule places wells by the same local bands. It is not evidence the
tags are right. That evidence is K1–K6 in step 2.
