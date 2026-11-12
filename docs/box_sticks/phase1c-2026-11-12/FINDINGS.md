# BOX sticks, phase 1c: the full chain for every bench, and the stack check (2026-11-12)

Read-only, live tags. `python -m scripts.box_sticks_phase1c --out docs/box_sticks/phase1c-2026-11-12`.

Question (Michael): can each bench's landing depth be solved on its own, or does the stack have to be solved at
once, given that DEAN may be inferred from LSSH and WCA_1? Answer by construction: a carried depth uses only
neighbours' DIRECT surfaces, never another carried depth, so each bench is independent. What needed measuring is
whether the resulting stack is consistent per DSU. This runs the adopted chain (direct -> local thickness -> bracket
-> single-neighbour offset) for every bench at all 52,712 DSU x bench pairs and checks adjacent benches.

## 1. Coverage with the full chain

| Rung | Share of DSU x bench pairs |
|---|---|
| direct | 48.6 % |
| local thickness | 22.6 % |
| bracket | 3.5 % |
| single-neighbour offset | 8.7 % |
| none | 16.6 % |

- **Of the 16.6 % with none, 13 points are the Delaware WCA family**, which is direct-only by decision: WCXY 76 %
  none, WCA_1 37.5 %, WCA_2 39.9 % of the 4,457 DSUs in the pooled WCA extent. Every other bench together is
  4.9 % none (1,922 of 39,341 pairs).
- Local thickness takes most of what phase 1b gave to the bracket, because it is tried first; the bracket's
  largest role is DEAN (28 % of its DSUs).
- **Low confidence** (the rung's held-out P90 above 200 ft) is 12.4 % of all pairs. It is every carried depth on
  Delaware AVA_1, BS2_S, BS3_C, WCC and Midland WCC, about half on BS1_S and Midland WCD, and under 6 % elsewhere
  in Midland (`rungs_screened.csv`).

## 2. The stack: carried depths do not make it worse

Adjacent benches in a DSU, out of order or under 75 ft apart, by where the two depths came from (screened run):

| Basin | Both direct | One carried | Both carried |
|---|---|---|---|
| Delaware | 14.2 % of 8,461 pairs | 4.4 % of 8,342 | 4.2 % of 4,042 |
| Midland | 3.5 % of 5,776 pairs | 4.5 % of 6,622 | 6.1 % of 2,381 |

- Delaware's direct-on-direct rate is the WCA family (below). Outside it, pairs conflict about 4-6 % of the time
  whether the depths are direct or carried.
- Per DSU: Delaware 1,441 of 4,311 with a conflict (404 actually out of order); 816 of those have a conflict
  outside the WCA family. Midland 615 of 3,482 (129 out of order).
- Worst pairs outside the family: Delaware WCA_2 / WCB_1 190, BS3_S / WCXY 121, WCB_1 / WCB_2 117, WCB_2 / WCC 109;
  Midland DEAN / WCA_1 184 (9.5 %), WCB_1 / WCB_2 103, LSSH / DEAN 98, WCB_2 / WCC 96 (`order_pairs_screened.csv`).
- **Conclusion: no joint surface fit is needed.** Estimate each bench independently, then reconcile the 4-6 % of
  conflicting pairs per DSU with a rule.

## 3. WCA_1 vs WCA_2 (Delaware)

2,040 DSUs carry both, both direct. Median gap 122 ft. 5 % are out of order; 14 % are under 50 ft apart, 25 %
under 75 ft, 37 % under 100 ft. WCXY / WCA_1: 937 DSUs, median gap 109 ft, 32 % out of order or under 75 ft.

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
- The screen barely changes coverage or the stack counts (section 2 is within a few pairs either way). Its value
  is removing bad nodes from a stored surface. The 7,641 wells with too few neighbours cannot be judged this way.

## Decisions for Gate 1

1. **Reconciliation rule for a conflicting pair** (proposal): the bench with the less trusted depth gives way
   (carried before direct; among carried, the higher held-out error). "Gives way" = moved to the minimum
   separation if that keeps it inside its own error band, otherwise no stick for that bench in that DSU.
2. **WCA_1 / WCA_2**: one WCA landing per DSU where the two are under the floor, or a lower floor for the family.
3. **Delaware WCA family with no direct control** (38-40 % of WCA_1 / WCA_2 DSUs, 76 % of WCXY): direct-only was
   decided before the chain existed. WCXY is waiting on its own extent (phase 1b of the plan); WCA_1 / WCA_2 could
   take the chain like every other bench.
4. **Outlier screen at 300 ft** for the surface of record.
