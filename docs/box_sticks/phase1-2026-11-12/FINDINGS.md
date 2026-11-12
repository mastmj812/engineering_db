# BOX sticks, phase 1: landing surfaces on today's tags (2026-11-12)

Read-only. `python -m scripts.box_sticks_phase1 --out docs/box_sticks/phase1-2026-11-12`. Plan: `docs/box_sticks_plan.md`.

Surfaces are `box.landing_surfaces` unchanged, on LIVE tags: a 0.25-mi lattice per code inside its BOX record
extent; **direct** where the code has >= 3 evidence wells within 2 mi and the nearest within 1 mi; **thickness**
(an anchor bench's surface plus the local thickness to the code) out to 5 mi from the code's nearest well; nothing
beyond. Evidence wells: 56,842 (planned surveys and round-100 permit depths excluded). Nothing is stored.

## 1. Coverage: a third of the DSU x bench pairs get no depth

Grain: 52,712 pairs of (2026Q3 DSU polygon, bench whose extent it intersects), sampled at the polygon centroid.

| | Direct | Thickness | None |
|---|---|---|---|
| All pairs | 48.2 % | 16.3 % | 35.5 % |
| Delaware BS1_S (2,359 DSUs) | 26.7 % | 24.5 % | 48.7 % |
| Midland DEAN (2,271 DSUs) | 24.1 % | 28.8 % | 47.1 % |

- About 5-7 points of "none" on most benches are polygons whose centroid falls outside the extent (edge clips).
- Worst "none": WCXY 76 %, Midland WCD 50 %, BS3_C 50 %, BS1_S 49 %, BS2_C 48 %, DEAN 47 %, WCA_2 40 %, WCA_1 38 %.
- Best: Delaware WCB_1 14 %, Midland WCB_1 14 %, WCC 17 %. Full table `coverage.csv`; maps `surface_*.png`.
- WCXY / WCA_1 / WCA_2 have no thickness path by decision (direct control only), which is why WCA_1 and WCA_2
  show 38-40 % none inside the pooled WCA extent.

## 2. Held-out error

Direct = the well plus same-code wells within 1/4 mi held out. Thickness = every same-code well within 1 mi held
out (the condition under which thickness is actually used), configured anchor.

| Bench | Direct median / P90 | Thickness median / P90 | Thickness > 150 ft |
|---|---|---|---|
| Delaware BS1_S | 44 / 154 ft | 63 / 198 ft (anchor BS2_S) | 16 % |
| Midland DEAN | 29 / 89 ft | 41 / 124 ft (anchor LSSH) | 7 % |
| Delaware, all benches | 26-71 / 79-230 ft | 37-95 / 130-335 ft | 9-31 % |
| Midland, all benches | 25-44 / 81-157 ft | 29-84 / 87-362 ft | 2-25 % |

- Thickness costs roughly 10-20 ft of median error over direct on most benches. It is poor on Midland WCC
  (84 / 362 ft), Delaware BS2_S from BS3_C (95 / 267 ft) and Delaware AVA_1 (72 / 246 ft).
- **Error grows slowly with distance from control.** Holding out everything within 1, 2, 3 mi: BS1_S 63, 67, 78 ft
  median; DEAN 41, 42, 41 ft. That argues the 5-mi reach could be extended on the stable benches; not yet tested.
- **The configured anchor is often not the best one** (`holdout_thickness.csv`, every other bench tried):
  - BS1_S: the WCA family gives 48 / 175 ft vs BS2_S 63 / 198 ft, but predicts 69 % of wells vs 78 %.
  - BS3_C: WCA 64 ft at 85 % predictable vs BS2_S 68 ft at 58 %. BS2_C: WCA 62 ft at 83 % vs BS2_S 69 ft at 49 %.
  - BS2_S: WCA 69 / 209 ft at 72 % vs BS3_C 95 / 267 ft at 52 %. AVA_0: WCA P90 86 ft vs BS2_S 130 ft.
  - DEAN: WCA_1 below (39 / 106 ft) is as good as LSSH above (41 / 124 ft), each predicting about 59 %.
  - A fallback chain of anchors would raise coverage and lower error together.
- **Sandwich** (fractional position between a bench above and one below): DEAN between JM and WCA_1 is the best
  DEAN result, 34 / 103 ft, but only 33 % of wells have both. Elsewhere it does not beat the best single anchor.

## 3. Stratigraphic order per DSU (minimum separation 75 ft)

| | Delaware | Midland |
|---|---|---|
| DSUs with >= 2 benches carrying a depth | 3,876 | 3,037 |
| With an adjacent pair out of order or under 75 ft | 1,274 (33 %) | 382 (13 %) |
| With a pair actually out of order | 327 (8 %) | 84 (3 %) |

- Delaware is dominated by the WCA family: WCA_1 / WCA_2 (500 DSUs; 5 % out of order, 20 % under 75 ft; median
  gap only 122 ft) and WCXY / WCA_1 (280 DSUs; median gap 109 ft). These are direct surfaces on both sides, so it
  is the tags / the thinness of the split, not the thickness method. A 75-ft floor is tight for two halves of one
  bench sitting about 120 ft apart.
- Next: WCA_2 / WCB_1 172, BS3_S / WCXY 108, WCB_1 / WCB_2 103, WCB_2 / WCC 96. For the WCB and WCC pairs about
  70 % of violations involve a thickness-carried depth.
- Midland: DEAN / WCA_1 103 (72 % with thickness), WCB_1 / WCB_2 91, WCA_1 / WCB_1 65, WCB_2 / WCC 52.
- Lithology pairs behave: BS2_C / BS2_S median gap 482 ft (2 violations); BS3_C / BS3_S 586 ft (63). They are not
  at near-equal depth where both have a surface, so the special pair rule in the plan may be unnecessary.
- Full table `order_pairs.csv`.

## 4. Other observations

- Outlier depths survive into surfaces: the DEAN map shows a node near 13,000 ft at the west edge, and BS1_S
  direct P99 is 2,243 ft. A surface of record needs an outlier screen on evidence wells (the plan already names
  `ref.formation_tag_depth_exclusions`; that table is not applied by this report).
- `box.landing_surfaces.ANCHOR` is shared with the formation-tag code (sub-bench inference, crossings) that is in
  shadow until 11-16. Any anchor change for BOX sticks should be a separate configuration, not an edit there.

## Decisions for Gate 1

1. **The 35 % with no depth**: extend thickness reach beyond 5 mi (test first), add fallback anchors, or accept no
   sticks there.
2. **Anchor chain per bench** for BOX sticks, chosen from `holdout_thickness.csv` (WCA family first for most
   Delaware Bone Spring / Avalon benches; LSSH then WCA_1 for DEAN).
3. **WCA_1 vs WCA_2 separation**: with a median gap of about 120 ft, either a lower minimum separation for the
   family or one landing per DSU where the two surfaces are closer than the floor.
4. Whether a thickness-carried depth is acceptable on the three weak cases (Midland WCC, Delaware BS2_S, AVA_1).

Re-run after the 11-16 tag decision if the cutover goes ahead; phase 0 suggests the change will be small.
