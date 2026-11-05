# Sub-bench inference v2: score at f138eb0 (2026-11-03T12:50:09)

Hold-out radius 0.74 mi; reference pool 38,275 laterals (30,866 producers); 35,290 coarse sticks; current-rule re-implementation reproduces the live tag on 95.6%.

## Criteria (PLAN.md §3)

| Criterion | Group | Draft | Reference | Pass |
|---|---|---|---|---|
| C1 held-out producers | delaware_WCA | 74.5% | current 65.2% | PASS |
| C1 held-out producers | delaware_WCB | 84.2% | current 78.7% | PASS |
| C1 held-out producers | midland_WCB | 88.5% | current 85.5% | PASS |
| C2 Texas WCB vs depth below WCA (n=9,102) | delaware_WCB | 77.1% | live 70.3% | PASS |
| C2 Texas WCB vs depth below WCA (n=10,763) | midland_WCB | 84.3% | live 82.8% | PASS |
| C3 calibration (accuracy by band) | delaware_WCB | <0.80 71.9% / 0.80-0.95 89.4% / >=0.95 93.3% | increasing | PASS |
| C3 calibration (accuracy by band) | midland_WCB | <0.80 66.7% / 0.80-0.95 87.5% / >=0.95 95.9% | increasing | PASS |
| C4 Pad 3240 stays WCB_1 | delaware_WCB | WCB_1, WCB_1, WCB_1, WCB_1 | WCB_1 | PASS |

**All criteria: PASS**

## Stick impact

| Group | Sticks | Flips vs live | Undrilled flips | Flips in box_scout | Frontier | Frontier in box_scout | Conf < 0.80 (non-frontier) |
|---|---|---|---|---|---|---|---|
| delaware_WCA | 6,585 | 1,999 (30.4%) | 1,950 | 566 | 3,152 | 0 | 1,832 |
| delaware_WCB | 16,676 | 4,178 (25.1%) | 4,064 | 1,145 | 4,474 | 0 | 4,576 |
| midland_WCB | 12,029 | 1,181 (9.8%) | 1,157 | 0 | 1,932 | 0 | 1,873 |

## Held-out producers by path

| Group | Path | n | Draft | Current |
|---|---|---|---|---|
| delaware_AVA | frontier | 44 | 59.1% | 54.5% |
| delaware_AVA | vote | 1,623 | 77.8% | 75.6% |
| delaware_WCA | frontier | 6 | 50.0% | 33.3% |
| delaware_WCA | local_model | 7,578 | 78.3% | 67.1% |
| delaware_WCA | vote | 2,454 | 63.0% | 59.5% |
| delaware_WCB | frontier | 26 | 69.2% | 61.5% |
| delaware_WCB | local_model | 2,533 | 85.5% | 79.0% |
| delaware_WCB | vote | 514 | 78.6% | 78.2% |
| midland_WCB | frontier | 17 | 76.5% | 76.5% |
| midland_WCB | vote | 8,425 | 88.5% | 85.5% |
