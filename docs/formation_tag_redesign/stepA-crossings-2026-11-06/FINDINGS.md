# Step A — landing-surface crossings in the BOX record extents, estimator rev 1 (2026-11-06, read-only)

```
python -m scripts.tag_landing_crossings --cache <scoreboard cache> --out <this folder>
```

**This replaces the first run, kept in `stepA-crossings-2026-11-06-superseded/`.**

That run fitted tilted planes through a few one-sided wells. Michael's gunbarrel check of ART SMITH STATE #130H
(3002555344, Lea) caught it:
- the BS3_C "surface" there was 10,559 ft, extrapolated from four BS3_C wells at 10,020–10,110 ft, all on one side;
- 61 of the 67 cards drawn from that run rested on a surface more than 150 ft off the plain local median;
- crossings concentrate exactly where a surface misbehaves, so the first run's crossing areas were inflated.

**Estimator rev 1** (`box/landing_surfaces.estimate`):
- a Gaussian distance-weighted median of the bench's wells;
- replaced by a robust plane only when at least 6 wells surround the node, the fitted dip is at most 300 ft/mi, and
  the plane stays within 150 ft of the weighted median;
- thickness surfaces only where the target bench's samples sit on more than one side.

**Validation** (`surface-estimator-rev1-2026-11-06/`): held-out wells, the same hold-out as before.

| | Old P99 error | New P99 error | Misses > 300 ft, old → new |
|---|---|---|---|
| Delaware, all | 603 ft | 431 ft | 2.6 % → 1.9 % |
| Delaware, one-sided remaining wells | 1,676 ft | 683 ft | 7.0 % → 4.1 % |
| Midland, one-sided remaining wells | 603 ft | 311 ft | 3.5 % → 1.1 % |

The median error is unchanged (Delaware 42 ft, Midland 36 ft). In Delaware's outer mile it is about 5 ft worse
(54 → 60 ft).

## Corrected baseline (the scoreboard number)

| Adjacent pairs | Shared area | Crossing | Merged (< 50 ft) | Non-adjacent crossing |
|---|---|---|---|---|
| Delaware | 16,165 sq mi | **532 sq mi (3.3 %)** | 772 sq mi (4.8 %) | 171 sq mi |
| Midland | 13,271 sq mi | **94 sq mi (0.7 %)** | 238 sq mi (1.8 %) | 5 sq mi |

The first run's figures were Delaware 722 sq mi / 4.0 % with 642 non-adjacent, and Midland 328 sq mi / 2.0 % with
184 non-adjacent. The shared area is smaller now because one-sided thickness surfaces are refused.

What remains is the expected kind:
- **Thin Delaware Wolfcamp A splits:** WCA_1 | WCA_2 6.0 % crossing, WCXY | WCA_1 6.2 %.
- **Delaware WCB_2 | WCC:** 5.4 %.
- **Delaware BS3_C | BS3_S:** 3.8 % at a 588-ft median gap, the BS3_C naming class.
- **Midland:** WCB_2 | WCC 2.8 %, WCB_1 | WCB_2 1.5 %, DEAN | WCA_1 1.5 %; everything else ≤ 0.5 %.

**Investigation list** (`wells_in_zones.csv`): Delaware 2,476 wells in crossing or merging nodes, 771 of them closer
to the other bench's surface; Midland 614, 195 closer.

**Cards** (`stepA-cards-2026-11-06/`): every card must also pass the plain-median check, i.e. ≥ 100 ft closer to the
proposed bench on plain medians of both benches' wells within 2 mi, with ≥ 3 wells each.
- 15 wells are ≥ 100 ft closer on the surfaces (thin WCA splits and already-ruled wells excluded);
- 13 have enough wells to check;
- **10 pass**, all Delaware. ART SMITH STATE #130H is not among them.
