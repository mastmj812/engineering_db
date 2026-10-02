# intel_sf reconciliation - 2026-09-16

Old = curated.intel_locations (live vintage in prod). New = qa.intel_locations_sf (sql/29 SELECT over current raw_intel).

## 1. Row counts per (basin, category)

| basin | category | old | new | delta |
|---|---|---|---|---|
| delaware | PDP | 24581 | 34244 | 9663 |
| delaware | PUD | 83282 | 122418 | 39136 |
| delaware | RES | 44674 | 49632 | 4958 |
| midland | PDP | 23435 | 30907 | 7472 |
| midland | PUD | 48183 | 62082 | 13899 |
| midland | RES | 27747 | 25100 | -2647 |

## 2. Formation distribution (PUD/RES)

Formations with count differences (PUD/RES only):
| formation | old | new |
|---|---|---|
| WOLFCAMP C |  | 26008 |
| AVALON | 16122 |  |
| WOLFCAMP A XY |  | 14683 |
| WOODFORD | 4484 | 15881 |
| BARNETT | 2441 | 11058 |
| AVALON MIDDLE CARBONATE |  | 6805 |
| FIRST BONE SPRING LIME |  | 6129 |
| WOLFCAMP A | 25138 | 19197 |
| FIRST BONE SPRING | 16248 | 10874 |
| LOWER AVALON |  | 5182 |
| UPPER AVALON |  | 5008 |
| JO MILL | 8901 | 4711 |
| UPPER SPRABERRY |  | 3757 |
| DEAN | 4428 | 1948 |
| WOLFCAMP B | 26528 | 28705 |
| SECOND BONE SPRING LIME | 16021 | 13849 |
| MIDDLE SPRABERRY | 7163 | 8627 |
| WOLFCAMP D | 11922 | 11131 |
| LOWER SPRABERRY SAND | 2750 | 3512 |
| THIRD BONE SPRING | 15327 | 16086 |
| LOWER SPRABERRY SHALE | 12416 | 11826 |
| SECOND BONE SPRING | 17919 | 18066 |
| THIRD BONE SPRING LIME | 16078 | 16189 |

## 3. Value deviations on joined sticks

Relative deviation |new-old|/|old| on sticks joined by (basin, category, unique_id):

| column | joined | both non-null | p50 rel dev | p90 rel dev | max |
|---|---|---|---|---|---|
| oil_eur | 47877 | 47877 | 0.089732 | 0.343143 | 371.5384 |
| gas_eur | 47877 | 47877 | 0.176791 | 0.745909 | 972.0898 |
| npv10 | 43293 | 43293 | 0.228185 | 1.335514 | 3452.3197 |
| npv25 | 43293 | 43293 | 0.283551 | 1.877004 | 4441.8004 |
| irr_pct | 43659 | 43659 | 0.310819 | 1.207735 | 1541373443523630.0000 |
| tvd | 47645 | 47645 | 0.000000 | 0.000000 | 901.8889 |
| ll_ft | 47905 | 47905 | 0.000000 | 0.018327 | 2.2709 |
| pp_months | 40432 | 40432 | 0.153846 | 0.414894 | 41.6667 |
| ttpt | 28537 | 28537 | 0.219178 | 0.547619 | 50.0000 |
| dc_cost | 43327 | 43327 | 0.047619 | 0.111111 | 0.7623 |
| oil_ip | 47877 | 47877 | 0.013699 | 0.057225 | 76.8875 |

## 4. Geometry sample

- 1,000-stick sample: 519/1000 within 10 m Hausdorff; max 1899.4 m (approx, 111 km/deg)

## 5. pad_npv25 + pad coverage

pad_npv25 old (shapefile rollup) vs new (SUM of member sticks), joined pads:
| pads joined | p50 rel dev | p90 rel dev |
|---|---|---|
| 0 |  |  |

pad_name coverage in new layer (share gap: Delaware BASE_CASE only):
| basin | category | with pad_name | total |
|---|---|---|---|
| delaware | PDP | 0 | 34244 |
| delaware | PUD | 0 | 122418 |
| delaware | RES | 0 | 49632 |
| midland | PDP | 0 | 30907 |
| midland | PUD | 62082 | 62082 |
| midland | RES | 25100 | 25100 |

## 6. ML tier distributions

Rock-quality tier distribution (old vs new, all categories):
| tier | old | new |
|---|---|---|
| Tier-1 | 44143 | 60149 |
| Tier-2 | 44563 | 60135 |
| Tier-3 | 44990 | 59286 |
| Tier-4 | 44641 | 59370 |

Spacing tier distribution:
| tier | old | new |
|---|---|---|
| Tier-1 | 43105 | 58561 |
| Tier-2 | 43661 | 58482 |
| Tier-3 | 43725 | 58492 |
| Tier-4 | 43774 | 58485 |
