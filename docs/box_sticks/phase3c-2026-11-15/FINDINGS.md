# BOX sticks, after gate 3b: trials of four generator improvements

2026-11-15. Read-only; nothing stored. Each change was built as a switch that is OFF in the generator of record
(`box_sticks_0.7_pilot`; output byte-identical with the switches off) and measured on the 114 pilot DSUs, on the
phase 3a back-test, and on the affected DSUs basin-wide. Numbers: `trials_summary.json`. Script:
`scripts/box_sticks_phase3_trials.py`. Live tags pulled 2026-11-14.

| Change | Pilot sticks (1,526 today) | Back-test T1 (58.9 %) | Basin-wide effect | Verdict |
|---|---|---|---|---|
| WCXY on the full landing-depth chain | 1,537 | 59.2 % | WCXY sticks 454 -> 963; other benches net -12 | **Holds up; adopted 2026-11-16** |
| Drop a carried depth that is implausible against a direct bench | 1,465 | 58.3 % | 637 benches dropped, 75 rescued; -1,346 sticks in 500 DSUs | **Does not hold up** |
| Two landings where the DSU's wells show two | 1,526 | 58.9 % | 336 units; legs in them 250 -> 252 | **No effect** |
| Short polygons drilled across their line | (count only) | | 402 U-turn DSUs, 1,933 BOX sticks | **Real; needs a decision** |

## 1. WCXY on the full chain: holds up

Today WCXY takes direct control only (decided 2026-11-12, "until it has its own extent"; it has one now).

- WCXY DSU x bench with a landing depth: 854 -> 1,277 of 1,299. The 423 new depths are thickness 329, offset 64,
  bracket 30; their rungs' held-out error is 59 ft median, 172 ft P90. 22 still have none.
- In the 1,299 DSUs: WCXY sticks 454 -> 963. All other benches together move by a net -12 sticks (16 lost: WCA_2 -8, BS3_S -4, WCA_1 -2, BS3_C -1, WCC -1; 4
  gained: WCB_1 +3, WCB_2 +1; corrected 2026-11-16, first written as "lose 16");
  benches dropped in stack reconciliation 360 -> 400.
- Pilot: +11 sticks, all in Lea. Back-test: T1 59.2 %, T2 5.0 %, T4 33.0 %; nothing worse.

## 2. Dropping an implausible carried depth: does not hold up

Rule tried: a carried depth is implausible when its distance to a direct bench in the same DSU falls outside the
2.5-97.5 % band of that distance where both are direct (>= 30 DSUs), widened by the rung's held-out P90. The bench
then gets no row, before stack reconciliation.

- It flags 637 of 21,034 carried DSU x bench (3.0 %) in 500 DSUs: Midland WCD 88, Delaware BS3_S 69, WCA_1 44, BS1_S 42,
  BS2_C 42, Midland MS 40.
- It rescues 75 benches from reconciliation (223 -> 148) and removes 613. Sticks in the affected DSUs 6,777 -> 5,431.
- Back-test: T1 58.3 % (from 58.9), T2 6.1 % (from 5.1), T3 62.3 % (from 63.2). Slightly worse on every bar.

The case that prompted it is real (Lea 10809), but removing the bench costs far more than it saves and the hidden
wells do not support it. The better repair is in the landing chain itself (prefer an anchor bench that has wells in or
next to the DSU), which is phase 1 work and is not attempted here. The switch (`Cfg.check_carried`) stays off;
`carried_implausible.csv` lists the 637.

## 3. Two landings per bench: no effect

Rule tried: in a straight DSU x bench flagged `two_landings_observed`, rows alternate between the two observed levels
(parity chosen to match the bench's own wells), where both levels clear the benches above and below by 75 ft.

- 534 DSU x bench are flagged basin-wide; 336 can use two levels (the rest are U-turn DSUs or too close to a neighbour).
- Legs placed in those 336 units: 250 with one landing, 252 with two. Pilot sticks unchanged at 1,526; every back-test
  bar unchanged. Only 6 hidden wells fall in such units.
- Why: a unit is flagged only when its own wells already show both landings (>= 4 wells), and by then it is nearly
  drilled out, under one open row per unit. The depth misses in the back-test come from the other case: a unit showing
  ONE landing before the cutoff and a different one after (17 of 40 two-campaign units). No rule reading today's wells
  can anticipate that.

Rule 3 (one landing per bench, with the flag) stands. The switch (`Cfg.two_levels`) stays off.

## 4. Short polygons drilled across their line

A U-turn DSU (straight row under 7,000 ft) holding two or more existing wells at least 30 % longer than its own row:

| | Delaware | Midland |
|---|---|---|
| U-turn DSUs with wells | 1,225 | 271 |
| ... with >= 2 wells 30 % longer than the DSU row | 286 | 116 |
| ... with >= 5 such wells | 61 | 47 |
| Existing wells in those DSUs (long ones) | 2,158 (1,007) | 856 (658) |
| BOX sticks placed in them, all U-turns | 1,447 | 486 |

402 DSUs and 1,933 sticks (2.4 % of the basin-wide 80,047). The operator there develops across the Novi polygon with
long straight laterals; BOX places U-turns between them. Not changed; the choice is to flag those sticks, or to place
none in such a DSU.

## Not trialled

Making the three private narvi functions public (`_make_leg`, `_single_well`, `_place_uturns`): a change in the narvi
repository with no effect on output.
