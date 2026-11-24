# BOX sticks phase 6, step 3: both basins built on BOX sticks, stored in the rehearsal container, bars scored

Written 2026-11-24. **Nothing is applied on live.** Builds and measures read live, read-only. Every store went to the
`box-rehearsal` container. Code `6620691` (clean) for every build, store and measure.

## What was run

| Stage | Delaware | Midland |
|---|---|---|
| Universe (record stick set, producing left out) | 46,032 of set 24's 46,153 (121 producing) | 33,106 of set 25's 33,122 (16 producing) |
| Build: locations fitted, data through 2026-09, the record runs' pools | 45,776 on 13 benches, 31,285 s on 9 workers | 33,057 on 9 benches, 21,147 s on 9 workers |
| Harness equivalence, 24 sampled locations per bench | max relative difference 0.0 on every bench | 0.0 on every bench |
| Water build | 45,776 locations, 0 ratio failures, 2,356 s | 33,057, 0 ratio failures, 1,957 s |
| Base store (container) | run 37, every identity passes, 623 s | run 35, every identity passes, 3,309 s |
| Water store (container) | 45,776 streams, 0 without water, 9 calculated fallback; oil / gas rows md5-unchanged | 33,057 streams, 0 without water; oil / gas md5-unchanged |
| Proximity measure (leg by leg) | 53,873 legs -> 45,776 sticks (8,097 U-turn; second leg the more exposed on 2,734); 314 k links | 36,625 legs -> 33,057 sticks (3,568 U-turn; second leg on 1,091); 268 k links |
| Derived store (container, not record) | run 38, every identity passes: oil 22,518.625 MMbbl = source x new / old; gas and water identical to the source | run 36, every identity passes: oil 11,357.345 MMbbl |

Run ids are the container's (its sequence had moved in the pilot). On live the stores take the next free ids.

The Midland base store took 3,309 s while the Delaware build held the cores; the Delaware one, alone, took 623 s.

## Outcomes after proximity

| | Delaware (run 38) | Midland (run 36) |
|---|---|---|
| Forecast | 40,685 | 28,711 |
| No drilled precedent (D114) | 2,735 | 1,179 |
| Package | 2,356 | 29 |
| Pattern | n/a | 2,861 |
| Spacing floor | n/a | 277 |
| Conflict or crowded (not drillable) | 256 | 49 |
| Proximity factor: mean, min, max | 0.962, 0.417, 1.046 | 0.960, 0.549, 1.067 |

## Bars (DESIGN.md)

| Bar | Result |
|---|---|
| P1 identity | **Pass.** One row per stick; rows + producing sticks left out = record sticks: 46,032 + 121 = 46,153; 33,106 + 16 = 33,122 |
| P2 volumes | **Pass.** Every stream's 600 months sum to its EUR within 0.1 % (0 off of 122,055 and 86,133 stream groups); equivalence 0.0 |
| P3 forecast share, 80 % | **Pass.** Delaware 88.9 % (40,685 of 45,776 inventory sticks); Midland 86.9 % (28,711 of 33,057) |
| P4 oil EUR per foot within 10 % per bench | **Midland 8 of 9; Delaware 10 of 13.** Outside: Midland WCB_2 -10.3 %; Delaware WCA_1 -15.4 %, WCA_2 -15.3 %, WCXY +12.2 %. Explained below; nothing tuned |
| P5 record sets only | **Pass.** 0 rows of either run outside sets 24 / 25; the store names the set and refuses once another set is the record |
| P6 live unchanged | **Pass.** Live read after the stores: records 30 / 32, 85,849 and 166,561 rows, the land team's view 28,754 and 48,077 rows, as before |

### P4 table (median oil EUR per foot, forecast locations)

| Basin | Bench | Forecast new / record | bbl/ft new / record | Change | Before proximity | Median factor new / record |
|---|---|---|---|---|---|---|
| Delaware | AVA_0 | 375 / 362 | 75.70 / 81.47 | -7.1 % | -8.7 % | 1.04 / 1.04 |
| | AVA_1 | 844 / 968 | 67.92 / 70.01 | -3.0 % | -2.7 % | 1.05 / 1.04 |
| | AVA_2 | 830 / 1,764 | 62.10 / 63.50 | -2.2 % | -2.7 % | 1.04 / 1.04 |
| | BS1_S | 4,901 / 4,804 | 70.07 / 72.64 | -3.5 % | -4.3 % | 1.05 / 1.05 |
| | BS2_C | 2,035 / 2,131 | 64.81 / 71.24 | -9.0 % | -8.8 % | 1.05 / 1.05 |
| | BS2_S | 3,744 / 6,925 | 52.46 / 54.49 | -3.7 % | -3.4 % | 1.05 / 1.05 |
| | BS3_C | 6,067 / 7,070 | 51.24 / 54.07 | -5.2 % | -5.0 % | 0.95 / 0.96 |
| | BS3_S | 3,333 / 5,888 | 64.49 / 69.40 | -7.1 % | -6.9 % | 1.03 / 1.03 |
| | WCA_1 | 3,416 / 916 | 49.08 / 58.01 | **-15.4 %** | -7.7 % | 0.95 / 1.02 |
| | WCA_2 | 3,123 / 910 | 48.60 / 57.34 | **-15.3 %** | -6.6 % | 0.95 / 1.04 |
| | WCB_1 | 4,486 / 3,903 | 55.29 / 59.97 | -7.8 % | -2.9 % | 0.89 / 0.94 |
| | WCB_2 | 4,288 / 2,290 | 58.32 / 61.35 | -4.9 % | -2.8 % | 0.98 / 1.00 |
| | WCC | 2,276 / 2,271 | 44.96 / 47.91 | -6.2 % | -3.6 % | 1.02 / 1.05 |
| | WCXY | 967 / 7,946 | 72.10 / 64.29 | **+12.2 %** | +21.0 % | 0.95 / 1.03 |
| Midland | DEAN | 1,453 / 915 | 42.96 / 45.34 | -5.3 % | -1.9 % | 1.02 / 1.04 |
| | JM | 2,983 / 3,437 | 46.93 / 46.63 | +0.7 % | -1.3 % | 0.92 / 0.92 |
| | LSSH | 4,952 / 6,784 | 36.11 / 37.09 | -2.7 % | -2.2 % | 0.92 / 0.95 |
| | MS | 3,896 / 3,891 | 37.81 / 39.21 | -3.6 % | -2.8 % | 0.95 / 0.97 |
| | WCA_1 | 4,719 / 4,586 | 32.62 / 32.83 | -0.6 % | -1.4 % | 0.98 / 0.98 |
| | WCB_1 | 3,681 / 4,718 | 36.16 / 35.31 | +2.4 % | -1.3 % | 1.00 / 0.98 |
| | WCB_2 | 1,585 / 681 | 34.62 / 38.60 | **-10.3 %** | -8.0 % | 0.99 / 1.02 |
| | WCC | 485 / 373 | 33.86 / 36.45 | -7.1 % | -12.8 % | 0.99 / 0.91 |
| | WCD | 4,957 / 3,416 | 41.03 / 41.86 | -2.0 % | -1.9 % | 1.04 / 1.05 |

Basin, lateral-weighted (sum of oil EUR over sum of lateral): Delaware 57.75 vs 61.24 bbl/ft (-5.7 %), oil 22,519 vs 25,421 MMbbl
on 40,685 vs 48,148 forecast locations. Midland 38.61 vs 38.58 bbl/ft, oil 11,357 vs 11,078 MMbbl on 28,711 vs 28,801.

### Why the Delaware reads lower per foot, and the four benches outside the bar

Three things differ between the runs besides the sticks: production data (through 2026-09, against 2026-07 and 2026-08), the
lateral lengths, and where the locations sit.

1. **Short Novi sticks.** Run 32's Novi sticks include many under 6,000 ft, which carry the highest EUR per foot (the lateral
   multiplier is less than proportional to length). BOX sticks have none under 6,000 ft. BS3_S: 2,482 of run 32's 5,888 are under
   6,000 ft at 76.2 bbl/ft; WCXY 3,544 of 7,946 at 72.4; WCA_1 278 of 916 at 75.3. Inside one lateral class the two runs are close
   before proximity (WCA_1, 8,500 to 11,000 ft: 53.90 vs 54.24 bbl/ft; BS3_S: 64.12 vs 66.20).
2. **WCA_1 / WCA_2: more exposed locations.** BOX holds 3,416 and 3,123 forecast locations where run 32 holds 916 and 910: the
   generator places WCA sticks inside developed units that Novi no longer carries sticks in. Their median proximity factor is 0.95
   against 1.02 / 1.04. Before proximity the gap is -7.7 % and -6.6 %, in line with the other benches; the factor adds the rest.
   792 and 798 of the BOX WCA sticks sit in 0.2-degree cells where run 32 has no forecast location at all (median 46.7 and 44.8
   bbl/ft before proximity).
3. **WCXY: a smaller, better area.** 967 BOX sticks in 19 cells against 7,946 Novi sticks in 59. In the 19 shared cells, before
   proximity, the two runs read 83.3 vs 85.4 bbl/ft (-2.5 %). The +12 % is location mix.
4. **Midland WCB_2.** 1,585 BOX sticks (median 9,870 ft) against 681 Novi sticks (median 7,920 ft, 212 of them under 6,000 ft at
   42.1 bbl/ft). In the 8,500 to 11,000 ft class: 34.93 vs 36.47 (-4 %); in shared cells before proximity 37.06 vs 39.12 (-5 %).

The small common shift (1 to 3 % in the Midland, 3 to 5 % in the Delaware inside a lateral class) is not separated between the
newer production data and the lateral lengths. Not done: a rebuild at the record runs' data-through, which would isolate it.

## What the cutover changes for a reader (from these runs)

| | Today (runs 30 / 32, Novi sticks) | After (BOX sticks) |
|---|---|---|
| Delaware forecast locations; land team's view rows | 48,148; 48,077 priced | 40,685; econ blank until Steven prices |
| Midland forecast locations; land team's view rows | 28,801; 28,754 (24,882 priced) | 28,711; econ blank until Steven prices |
| Delaware oil, forecast locations | 25,421 MMbbl | 22,519 MMbbl |
| Midland oil, forecast locations | 11,078 MMbbl | 11,357 MMbbl |

## Not checked

- erebor against the two full runs in the container (step 2 checked it on the AVA_0 pilot; the container now holds both basins).
- The share of the common per-foot shift that is production data and the share that is lateral length.
- Tonight's nightly status: the builds read the status of 2026-11-23. The live stores read it again at store time, so a stick
  that turns producing or conflict in between is handled there (`universe = source - realized since`).

## Step 4 (cutover): every live write is its own explicit go, off-hours, outside the 05:00 CT nightly

1. `python -m scripts.apply_box_pud_forecast_box_sticks --go` (sql/79)
2. base stores (`box_pud_run store --out runs/p6_delaware`, `box_record23_midland store --out runs/p6_midland`), water stores,
   measures on live, derived stores. About 45 minutes per basin from the container timings
3. `python -m scripts.apply_box_stick_locations --go`
4. merge engineering_db #275
5. `box_record23 flip --basin <b> --run <id> --allow-unpriced --commit`, both basins
6. merge erebor #33, restart erebor, verify (bars C1 to C5); regenerate the data dictionary
