# Rule v3 — development-fold sanity run (2026-11-05, before the freeze)

```
python -m scripts.tag_rule_dev --cache <scoreboard cache> --out <this folder>
```

This run is read-only, on the scoreboard's cached pull from 2026-11-05. Per RULE.md §2 it reports only churn (all
wells), the guards, and the band test on development-fold wells (even 6-mi cells, 28,812 clean wells). The labelled
set, grid agreement and the test fold have NOT been computed.

**Churn: producing horizontals whose code changes, rule vs vendor (no overrides)**

| Basin | Wells | Code changes | Family changes |
|---|---|---|---|
| Delaware | 31,821 | 2,439 (7.7 %) | 734 (2.3 %) |
| Midland | 28,865 | 1,251 (4.3 %) | 723 (2.5 %) |

Family changes stay under the K11 cap of 5 %.

Largest moves (`moves_from_to.csv`):
- Delaware WCA_2→WCA_1: 547
- Midland WCB_1→WCB_2: 413
- Delaware WCA_1→WCA_2: 358
- Delaware WCA_1→WCXY: 223
- Delaware WCXY→WCA_1: 215
- Midland WCA_1→WCB_1: 185
- Midland LSSH→JM: 172
- Midland WCB_1→WCA_1: 172
- Delaware WCA_2→WCB_1: 168

The Delaware WCA moves run in both directions, which is what fixing the 9–11 % inverted thin splits should look
like rather than a one-way shift.

**Guards (K10):**
- 0 moves into or out of WDFD / BRNT / MISS;
- 0 BS2 / BS3 sand↔carbonate swaps;
- 0 XY crossings in Lea or Ward.

Blocked moves were flagged instead:
- 137 for lithology;
- 94 for rule B (pending in Lea / Ward);
- 61 `family_conflict`. That includes grid moves that depth couldn't place, which keep the vendor code.

**Basis.**
- Delaware family checks: 7,944 used the grid, 17,786 used local bands, and 2,885 had no clean depth.
- Midland: 26,413 used local bands.
- Positions inside multi-code families: Delaware 9,985 placed by local bands, and 5,559 kept the vendor code
  because depth could not resolve the split there (Q1 (a)).

**Confidence** (clean wells in multi-code families):
- Delaware WCA: 5,598 high / 5,631 low.
- Delaware WCB: 1,226 high / 1,852 low.
- Delaware AVA: 829 high / 600 low.
- Midland WCB: 4,333 high / 4,128 low.

Half the thin-split calls are low confidence. That is the honest answer for 104–170 ft splits.

**Band test, development fold, 1 mi:**

| Basin | vendor | rule |
|---|---|---|
| Delaware | 9.7 % | 5.6 % |
| Midland | 6.0 % | 3.1 % |

This drop is **partly by construction**: the rule places wells by the same local bands the band test uses. It shows
the rule does what it says. It is not evidence that the tags are right. That evidence is K1–K6 in step 2.
