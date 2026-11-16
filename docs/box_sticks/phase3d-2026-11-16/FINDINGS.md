# BOX sticks: WCXY on the full landing-depth chain (generator 0.8)

2026-11-16. Decided by Michael after the trials of `phase3c-2026-11-15/`: Delaware WCXY takes the full landing-depth
chain (thickness, bracket, offset) like every other bench. Generator `box_sticks_0.8_pilot`; no generator rule and no
bar changed, only WCXY's depth input (`scripts/box_sticks_phase1c.CHAIN_DIRECT_ONLY` is now empty). Read-only;
**nothing is stored**. Live tags pulled 2026-11-14; the formation-tag switch was still OFF on 2026-11-16 (shadow run 6
written that morning), so these are the tags the warehouse serves today.

Files: `basin*.csv`, `basin_summary.json`, `dsu_bench.csv.gz` (basin-wide against Novi, same layout as phase 3b);
`backtest/` (same layout as phase 3a). The review cards in `phase3a-2026-11-14/cards/` are re-rendered at 0.8.

## What changed

Grain: DSU x bench, sticks, legs. Filters as in phases 3a / 3b.

| | 0.7 | 0.8 |
|---|---|---|
| WCXY DSU x bench with a landing depth (of 1,299) | 854 | 1,277 (direct 854, thickness 329, offset 64, bracket 30) |
| WCXY DSU x bench with BOX sticks | 294 | 527 |
| WCXY DSU x bench with no row | 592 | 230 |
| WCXY sticks (legs) | 454 (546) | 963 (1,150) |
| Other Delaware benches, sticks | 45,548 | 45,536 |
| **Delaware sticks** (legs, lateral) | 46,002 (54,168; 441.5 MM ft) | **46,499** (54,764; 446.4 MM ft) |
| Midland sticks | 34,045 | 34,045 (no row changed) |
| Novi remaining sticks, same DSUs and benches (Delaware) | 55,627 | 55,627 |
| Pilot sticks (legs), 114 DSUs | 1,526 (1,751) | 1,537 (1,766); Lea 875 -> 886 |
| Errors / invariant violations | 0 / 0 | 0 / 0 |

- The other benches move by a net -12 sticks: WCA_2 -8, BS3_S -4, WCA_1 -2, BS3_C -1, WCC -1, WCB_1 +3, WCB_2 +1. A
  WCXY depth now takes part in stack reconciliation, so a neighbour inside 75 ft of it can lose its row
  (`reconciled_out` on the pilot 25 -> 30) and a no-depth WCXY well is now tested at its bench depth.
- Of the 1,299 WCXY DSU x bench, 22 still have no depth. WCXY rows not placed go from 2,025 to 2,840, mostly the
  envelope (same landing 1,399 -> 1,857, stacked 456 -> 734): the new rows sit in developed ground.
- TVD bust of WCXY sticks against same-bench producers in the DSU: 23 ft median, 82 ft P90 (174 DSU x bench); 22 / 80 ft
  at 0.7. Only the direct rung can be scored this way; the carried rungs' held-out error is 59 ft median, 172 ft P90.
- BOX now places 84 % of the Novi stick count and 91 % of its footage in the Delaware on the DSUs and benches where
  both exist (83 % and 90 % at 0.7).

## Back-test at 0.8 (cutoff 2023-01-01, 707 hidden producers)

| Bar | 0.7 | 0.8 | Verdict |
|---|---|---|---|
| T1 hidden wells with a leg (>= 60 %) | 58.9 % | 59.2 % (Lea 52.9, Ward 46.9, Midland 69.8) | fails |
| T2 | 5.1 % | 5.0 % | passes |
| T3 units within one leg (>= 70 %); count ratio | 63.2 %; 0.96 | 63.2 %; 0.96 | fails; ratio passes |
| T4 unused slots (<= 25 %) | 33.3 % | 33.0 % | fails |
| T5 direct rung: pairs, median, within 150 ft | 121, 59.0 ft, 80.2 % | 121, 59.0 ft, 80.2 % | passes |
| T5 thickness rung, observed / held-out median | 1.28x (215 pairs) | 1.32x (217 pairs) | passes (<= 1.5x) |
| T5 offset rung | 1.15x (37) | 1.14x (38) | passes |
| T5 bracket rung | 1.59x (24) | 1.59x (24) | fails |

The same bars fail as at gate 3a. The thickness rung moved from 1.28x to 1.32x on two added pairs.

## Not adopted (switches stay off)

`Cfg.check_carried` and `Cfg.two_levels`: see `phase3c-2026-11-15/FINDINGS.md`.

## Short polygons drilled across their line

Michael, 2026-11-16: an artifact of the Novi DSU shapefile, and BOX sticks stay on the Novi polygons; drawing our own
DSUs is not undertaken now. Nothing changed in the generator. Whether the sticks in those DSUs carry a flag is open.
