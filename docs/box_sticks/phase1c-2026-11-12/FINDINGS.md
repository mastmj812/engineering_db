# BOX sticks, phase 1c: the full chain for every bench, and the stack check (2026-11-12)

Read-only, live tags. `python -m scripts.box_sticks_phase1c --out docs/box_sticks/phase1c-2026-11-12`.

Question (Michael): can each bench's landing depth be solved on its own, or does the stack have to be solved at
once, given that DEAN may be inferred from LSSH and WCA_1? Answer by construction: a carried depth uses only
neighbours' DIRECT surfaces, never another carried depth, so each bench is independent. What needed measuring is
whether the resulting stack is consistent per DSU. This runs the adopted chain (direct -> local thickness -> bracket
-> single-neighbour offset) for every bench at all 52,712 DSU x bench pairs and checks adjacent benches.

**Revision (same day).** The first run kept the whole Delaware WCA family on direct control only. Michael then
decided WCA_1 and WCA_2 take the full chain; WCXY stays direct-only until it has its own extent. The numbers below
are from the re-run with that decision, outlier screen on. First-run figures are quoted where the change matters.

## 1. Coverage with the full chain

| Rung | Share of DSU x bench pairs |
|---|---|
| direct | 48.6 % |
| local thickness | 25.6 % |
| bracket | 3.7 % |
| single-neighbour offset | 10.3 % |
| none | 11.9 % |

- **WCXY alone is 6.4 of the 11.9 points** (76 % of its 4,457 DSUs, direct-only by decision). Every other bench
  together is 6.0 % none (2,872 of 48,255 pairs); about 2 points of that are edge polygons whose centroid lies
  outside the extent.
- Delaware WCA_1: none falls from 37.5 % to 10.8 %; WCA_2 from 39.9 % to 10.2 %. Their carried depths have an
  expected median error of 52 ft and 59 ft.
- **Low confidence** (the rung's held-out P90 above 200 ft) is 14.8 % of all pairs: every carried depth on
  Delaware AVA_1, BS2_S, BS3_C, WCC and Midland WCC; 68 % of carried WCA_2 and 31 % of carried WCA_1; about half
  on BS1_S and Midland WCD; under 6 % elsewhere in Midland (`rungs_screened.csv`).

## 2. The stack

Adjacent benches in a DSU, out of order or under 75 ft apart, by where the two depths came from:

| Basin | Both direct | One carried | Both carried |
|---|---|---|---|
| Delaware | 14.9 % of 7,952 pairs | 9.6 % of 9,843 | 9.4 % of 5,535 |
| Midland | 3.5 % of 5,776 pairs | 4.5 % of 6,622 | 6.1 % of 2,381 |

- **Midland: carried depths conflict about as often as direct ones (3.5-6 %).**
- **Delaware is the WCA family.** 1,543 of its 2,647 conflicting pairs are WCA_1 / WCA_2 or WCXY / WCA_1. With the
  family on direct only (first run) Delaware's carried pairs conflicted at 4.2-4.4 %, the same as Midland; putting
  WCA_1 / WCA_2 on the chain raises that to about 9.5 %, because two halves of one bench about 115 ft apart are
  now carried into DSUs where neither has its own wells.
- Outside the family: Delaware 970 of 4,399 DSUs with a conflict; Midland 615 of 3,482 (129 out of order).
- Worst pairs outside the family: Delaware WCA_2 / WCB_1 254, BS3_S / WCA_1 218, BS3_S / WCXY 121,
  WCB_1 / WCB_2 117, WCB_2 / WCC 109; Midland DEAN / WCA_1 184 (9.5 %), WCB_1 / WCB_2 103, LSSH / DEAN 98,
  WCB_2 / WCC 96 (`order_pairs_screened.csv`).
- **Conclusion: no joint surface fit is needed.** Estimate each bench independently, then reconcile per DSU.

## 3. WCA_1 vs WCA_2 (Delaware)

| | Both direct (first run) | Full chain |
|---|---|---|
| DSUs carrying both | 2,040 | 3,886 |
| Median gap | 122 ft | 114 ft |
| Out of order | 5 % | 8 % |
| Under 50 ft | 14 % | 20 % |
| Under 75 ft (or out of order) | 25 % | 31 % |
| Under 100 ft | 37 % | 42 % |

With the one-landing rule at 75 ft, 1,204 of the 3,886 DSUs get a single WCA landing.
WCXY / WCA_1: 1,071 DSUs, median gap 110 ft, 32 % out of order or under 75 ft.

## 4. Outlier screen

Each evidence well against the landing depth of its same-bench neighbours within 2 mi, itself left out (>= 5
neighbours; 49,201 of 56,842 wells can be judged):

| More than | 200 ft | 300 ft | 400 ft | 500 ft |
|---|---|---|---|---|
| Wells | 1,897 | 702 | 383 | 258 |

- At 300 ft: 0.1-0.7 % of the Wolfcamp benches, 1-4 % of the Bone Spring / Avalon benches, 15-18 % of the
  out-of-scope WDFD / BRNT / OTHER tags (`outliers_by_bench.csv`, list `outliers_300ft.csv`).
- The largest are not landing depths at all: 21,930 ft and 21,961 ft "TVD" in Lea, WCC wells at 15,000-18,000 ft,
  Bone Spring tags at 4,800 ft.
- The screen barely changes coverage or the stack counts. Its value is removing bad nodes from a stored surface.
  The 7,641 wells with too few neighbours cannot be judged this way.

## Decisions (Michael, 2026-11-12)

1. WCA_1 / WCA_2 take the full chain. Done in this run.
2. One WCA landing per DSU where WCA_1 and WCA_2 are under the 75 ft floor or out of order.
3. Reconciliation of a conflicting pair: the less trusted depth gives way (carried before direct; among carried,
   the higher held-out error); it moves to the minimum separation if that stays inside its own error band,
   otherwise no stick for that bench in that DSU.

Still open: the outlier screen at 300 ft for the surface of record.
