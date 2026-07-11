# intel_sf reconciliation - 2026-07-08

Old = curated.intel_locations (raw_novi_intel, 3Q25 static drop). New = qa.intel_locations_sf (raw_intel, Snowflake share, 2025Q3).

## 1. Row counts per (basin, category)

| basin | category | old | new | delta |
|---|---|---|---|---|
| delaware | PDP | 22215 | 24581 | 2366 |
| delaware | PUD | 83282 | 83282 | 0 |
| delaware | RES | 44674 | 44674 | 0 |
| midland | PDP | 22517 | 23435 | 918 |
| midland | PUD | 48183 | 48183 | 0 |
| midland | RES | 27747 | 27747 | 0 |

## 2. Formation distribution (PUD/RES)

- formation distributions identical (PUD/RES)

## 3. Value deviations on joined sticks

Relative deviation |new-old|/|old| on sticks joined by (basin, category, unique_id):

| column | joined | both non-null | p50 rel dev | p90 rel dev | max |
|---|---|---|---|---|---|
| oil_eur | 248615 | 248615 | 0.000000 | 0.000000 | 0.0000 |
| gas_eur | 248615 | 248615 | 0.000000 | 0.000000 | 0.0000 |
| npv10 | 248615 | 248615 | 0.000000 | 0.000000 | 0.0000 |
| npv25 | 248615 | 248615 | 0.000000 | 0.000000 | 0.0000 |
| irr_pct | 248606 | 248606 | 0.000000 | 0.000000 | 0.0006 |
| tvd | 248618 | 248618 | 0.000000 | 0.000000 | 0.0000 |
| ll_ft | 248618 | 248618 | 0.000000 | 0.000000 | 0.0000 |
| pp_months | 246006 | 246006 | 0.000000 | 0.000000 | 0.0000 |
| ttpt | 198334 | 198334 | 0.000000 | 0.000000 | 0.0000 |
| dc_cost | 248618 | 248618 | 0.000000 | 0.000000 | 0.0000 |
| oil_ip | 248615 | 248615 | 0.000000 | 0.000000 | 0.0000 |

## 4. Arps segment parameters

- old segments: 1,851,759; joined to new on (wellname, stream, segment): 1,834,974
- within 0.1%: b 1,834,974/1,834,974, d_nom 1,834,974/1,834,974, q_start 1,834,974/1,834,974

## 5. Geometry sample

- 1,000-stick sample: 1000/1000 within 10 m Hausdorff; max 0.0 m (approx, 111 km/deg)

## 6. pad_npv25 + pad coverage

pad_npv25 old (shapefile rollup) vs new (SUM of member sticks), joined pads:
| pads joined | p50 rel dev | p90 rel dev |
|---|---|---|
| 4455 | 0.0000 | 0.7490 |

pad_name coverage in new layer (share gap: Delaware BASE_CASE only):
| basin | category | with pad_name | total |
|---|---|---|---|
| delaware | PDP | 0 | 24581 |
| delaware | PUD | 83282 | 83282 |
| delaware | RES | 0 | 44674 |
| midland | PDP | 0 | 23435 |
| midland | PUD | 0 | 48183 |
| midland | RES | 0 | 27747 |

## 7. ML tier distributions

Rock-quality tier distribution (old vs new, all categories):
| tier | old | new |
|---|---|---|
| Tier-1 | 26908 | 44143 |
| Tier-2 | 32761 | 44563 |
| Tier-3 | 37240 | 44990 |
| Tier-4 | 34556 | 44641 |

Spacing tier distribution:
| tier | old | new |
|---|---|---|
| Tier-1 | 23651 | 43105 |
| Tier-2 | 34482 | 43661 |
| Tier-3 | 36664 | 43725 |
| Tier-4 | 36668 | 43774 |

## 8. Forecast spot-check (old local vs Snowflake)

- 20 wells x first 12 months: 240 periods compared, 0 with any stream off by >0.1% (OK - same forecast, mop=ip_day/30 contract holds)
