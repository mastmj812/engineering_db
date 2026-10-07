# BOX step 2 — edge-gap prototype: findings for gate 2

**Built 2026-10-07, read-only** (nothing written to the warehouse). Plan: `docs/box_type_curves_plan.md`
§5 step 2, D5/D6. Inputs: gate-1 final sets `docs/box/step1-2026-10-06/wells_final_{WCA,BS2_S}.csv`
(pooled WCA incl. WCXY one-way per D19/D20; BS2_S after the gate-1 rule).

**Review surface:** `index.html` → `edge_WCA.html`, `edge_BS2_S.html`. Each page has an interactive
map (outline coloured by gap, pre-2016 laterals grey, step-outs magenta, edge-pinning wells with a QC
caveat cyan; click any segment or lateral), the expected-result test, the by-side table, gap
histogram, edge-performance 2×2 input, pinning-well caveat list, step-outs, holes and the alpha sweep.
Serve locally (the map pulls Leaflet + Esri tiles from the web):
`python -m http.server 8766 --directory docs/box`, then open
`http://localhost:8766/step2-2026-10-07/`.

**Reproduce:** `python -m scripts.box_edge_gap --out docs/box/step2-2026-10-07` (≈ 7 min, mostly
the sweep). Code: `box/edge_gap.py` (pure metric), `box/edge_gap_report.py` (pull + pages),
`tests/test_box_edge_gap.py` (18 DB-free tests).

Grain throughout: one lateral per api10. Evidence = first production ≥ 2016-01-01. 12-mo oil =
Novi `cum_12m_oil_bbl` ÷ `lateral_length_ft` × 1,000 (calendar basis as Novi computed it), D9 cohort
only. Medians, not means.

## 1. The v1 metric failed the test, so the outline was rebuilt (flag: method change)

v1 followed the plan literally: an edge-length-limited Delaunay alpha hull of the densified laterals,
with a lateral "pinning" the outline only where the hull touches it (≤ 75 ft). Alpha had to reach
**L = 2.5 mi** before WCA came out as one body (99.9 %). At that L:

- WCA read as **not** pinned: 67 % of the perimeter was in gaps > 1 mi, gap median 6,850 ft, and
  gap p90 12,650 ft ≈ L (saturated).
- The gaps sat in the diagonal-facing flanks of **both** benches (NE/SE/SW/NW 93–95 % gap). The
  laterals run N–S, so a hull that big cuts every DSU stair-step with a 1.5–2.5 mi chord. That is
  an orientation artifact, not maturity.
- BS2_S's southern front came out as islands beyond L, not as gaps, so its S side read as pinned
  (median gap 1,550 ft).

**v2 (what is built):** the same alpha-shape idea in its union-of-discs form, with two knobs:

- **r = 2,640 ft (pin radius).** Each lateral is dilated by r; a lateral pins ground within ½ mi of it.
- **c = 3,960 ft (0.75 mi) closing radius.** This is the per-basin alpha. Tuning rule: the smallest
  c that makes WCA one body at r = ½ mi (sweep r ∈ {¼, ½, ¾} × c ∈ {½ … 2} mi on each page).
  BS2_S uses the same c (one alpha per basin).

The dilation fills stair-step notches narrower than 2r, so a densely drilled diagonal flank reads as
pinned (test `test_staircase_notch_reads_pinned_not_gap`).

- **Walk:** sample the main body's outer ring every 100 ft. A sample within r (+60 ft) of a lateral
  is pinned by the nearest one. A **gap** is the unpinned outline between two consecutive pinning
  laterals; adjacent pinners hand over with no gap.

**Consequence you should know:** a gap cannot exceed about 2c (~1.5 mi of opening). A wider opening
is not bridged, and the tests beyond it fall *outside* the body. So a moving front shows up in the
**step-out table** (≥ 2016 laterals outside the body, by side, distance, vintage and performance),
not as long gaps. The step-out table is an addition to D6's metric, not a replacement — **accept or
reject it at the gate.**

## 2. Gap distribution per bench (main body, outer ring)

| pool | evidence laterals | in main body | perimeter | pinned share | gaps | gap median | gap p90 | perimeter-mi per pinning well | share in gaps > 1 mi | step-outs |
|---|---|---|---|---|---|---|---|---|---|---|
| WCA | 11,146 | 99.8 % | 742 mi | 66 % | 370 | 3,400 ft | 7,500 ft | 1.63 | 17 % | 25 |
| BS2_S | 3,157 | 97.2 % (5 bodies) | 642 mi | 67 % | 302 | 3,400 ft | 7,400 ft | 1.69 | 18 % | 88 |

BS2_S's 2nd–5th bodies (2.8 % of laterals, separate clusters such as the NW Eddy patch) are counted
in the step-outs, not walked.

## 3. The expected-result test

**WCA uniformly pinned — PASS.**

| side | pinned share | gaps > 1 mi | edge oil/ft ÷ interior |
|---|---|---|---|
| N | 64 % | 20 % | 0.99 |
| NE | 65 % | 10 % | 0.69 |
| E | 74 % | 17 % | 0.77 |
| SE | 68 % | 13 % | 0.72 |
| S | 62 % | 15 % | 0.69 |
| SW | 61 % | 16 % | 0.43 |
| W | 68 % | 21 % | 0.53 |
| NW | 68 % | 15 % | 0.83 |

No side stands out on pinning. Only 25 step-outs, 23 of them within 5 mi of the body, and they
perform poorly (W 0.16×, SW 0.03×, S 0.31×). Operators tested past the edge and stopped: a capped
edge. The W/SW flank (Reeves west / Culberson) is clearly rolled, at 0.43–0.53× interior.

**BS2_S "pinned W/N/E, long S/SE gaps" — PARTIAL; the data disagrees on W.**

| side | pinned share | gaps > 1 mi | step-outs ≤ 5 / 5–20 / > 20 mi | step-out first prod (median) | step-out oil/ft ÷ interior |
|---|---|---|---|---|---|
| N | 72 % | 10 % | 0 / 0 / 0 | – | – |
| E | 73 % | 7 % | 0 / 0 / 0 | – | – |
| W | 66 % | 18 % | **27 / 4 / 0** | **2025** | **0.84** |
| SE | 62 % | 25 % | 3 / 2 / **20** | 2020 | 0.54 |
| S | 66 % | 16 % | 7 / 2 / 5 | 2023 | 0.27 |
| SW | 63 % | 25 % | 9 / 0 / 0 | 2023 | 0.40 |

- **N and E are capped.** Pinned, no step-outs. ✔
- **W is a live front, not a capped edge.** There are 31 step-outs 1–3 mi beyond the body (Matador
  and Mewbourne, Eddy Co., median first production 2025) at 0.84× interior oil/ft. ✘ vs the
  expectation.
- **S/SE/SW are the gappiest sides** (16–25 % in gaps > 1 mi vs 7–10 % N/E). But the S step-outs are
  weak (0.27×), and the SE ones are scattered Texas tests a median 42 mi out (Diamondback, Exxon,
  VTX; median 2020, 0.54×). So the south reads as *probed and rolling over*, not as a clean moving
  front. Partly ✔.

My read: the metric discriminates, since WCA is uniform and BS2_S is asymmetric with E/N clean. The
mismatch is the **expectation for BS2_S W**, which may predate the 2023–2026 Matador/Mewbourne
program. Per the plan rule ("if either fails, the metric or alpha is wrong"), this is your call
before step 3.

## 4. Edge performance (the 2×2 input for step 3; nothing here sets a buffer)

The interior median is taken over D9 cohort laterals ≥ r + 1 mi inside the edge: WCA **22,238
bbl/1,000 ft** (n = 6,735), BS2_S **24,810** (n = 1,365). Perimeter by class:

| pool | pinned strong / unknown / rolled | gap strong / unknown / rolled |
|---|---|---|
| WCA | 145 / 137 / 206 mi | 77 / 74 / 103 mi |
| BS2_S | 113 / 200 / 115 mi | 65 / 76 / 74 mi |

"Pinned + strong" is the plan's **flag-for-geology** class (an edge not explained by performance):
145 mi in WCA and 113 mi in BS2_S. The reference is the *pool-wide* interior median per §6. With
the Delaware's regional trend, a local reference (interior wells within a few miles) may be the
fairer 2×2. That is a step-3 knob, not changed here.

## 5. Items for your eyes

1. **Edge-pinning wells with a QC caveat** (the gate-1 agreement: only these get individual eyes),
   cyan on the map, listed on each page and in `pinning_wells_<pool>.csv`.
   - WCA: **93 of 454** pinning wells. 59 planned survey, 22 consensus flags kept, 13 permit-round
     TVD, 7 reassigned in, 2 A′ TVD-suspect.
   - BS2_S: **62 of 380**. 53 planned survey, 8 reassigned in, 5 permit-round, 2 A′.
2. **WCXY pins WCA** in 42 wells / 38.7 of 488 pinned mi (all north side). This is allowed by D20
   (WCXY counts as WCA evidence); flagged so it is visible.
3. **Holes** are listed, not walked: WCA 22 (178 sq mi, largest 24 sq mi), BS2_S 26 (209 sq mi,
   largest 34 sq mi with 116 pre-2016 laterals inside — an old-vintage area with no modern test).
   Geology hole vs surface constraint (D8) is geology's call in step 3.
4. **Geometry:** 99.6 % of laterals are Enverus survey `LateralLine` (sql/39), the rest the Novi LP→BHL
   chord or the wellstick. LateralLine runs a median 1.16× the reported lateral length (it includes
   the build curve). That is immaterial at r = ½ mi.

## 6. Gate 2 — your decisions

1. **Accept the metric** as built: the union-of-discs outline (r = ½ mi, c = ¾ mi tuned on WCA), gap =
   unpinned outline between consecutive pinning laterals, sides by bearing from the body centroid.
   Or ask for a different r (the sweep has ¼ and ¾).
2. **Accept the step-out table** as the second half of the edge read (a moving front shows up as
   tests ahead of the body), and therefore as an input to step 3's buffers.
3. **BS2_S W:** is the 2025 Matador/Mewbourne W program a front (buffer W like a gap), or was the
   "capped W" expectation right and these wells are something else?
4. Note for step 3: whether the edge-perf reference stays pool-wide (§6) or goes local.

## 7. Michael's answers, 2026-10-07 (gate 2 partly answered)

- **Buffer basis — option (b):** the ½-mi pin radius r is a *measuring* radius only. The extent is
  laterals + variable buffer (k × gap, capped, 2×2-refined); it is **not** the r-dilated outline plus
  a buffer. Step 3 builds the extent from the lateral lines. Recorded as plan D21.
- **BS2_S W:** Michael reviewed the W step-outs. They are genuine BS2_S, so **W is a live front**
  and step 3 buffers it like a gap side, not a capped edge. The "capped W" expectation is
  superseded. Recorded as plan D22.
- **The large BS2_S gap/hole on the potash side is very likely the potash mining operation** (a
  surface constraint, D8), not geology. **Not resolved here.** D8's "add a manual ignore-gap polygon
  only if it keeps recurring" now applies: the same footprint also opens WCA's north-central hole,
  so it recurs across benches. Proposal for step 3: one shared potash ignore-gap polygon (BLM
  Secretary's Potash Area or geology's own outline). Inside it, gaps neither widen buffers nor count
  as negative evidence. Michael to confirm the source polygon.
- Still open from §6: explicit acceptance of the metric (r, c) and of the step-out table; the
  edge-perf reference (step 3).

## 8. Side-probe: do Holden's structure grids add edge information? (2026-10-07)

**Question:** where structure is quiet and continuous, should the extent follow it?
**Probe:** `structure_probe.py` → `structure_probe_BS2_S.png`. Inputs: Holden's GGX grids
`HCA_2BSPGS` (2BS sand top) and `HCA_3BSPGC` (3BS carbonate top). The isopach is the BS2 sand
interval. Grids are UTM 14N US-ft, Z ≈ KB-relative TVD, 5,028-ft (~1 mi) nodes, 2,203 control
points. Each edge segment is sampled 1 mi inside vs 1 mi outside the BS2_S outline.

| side | grid coverage 1 mi outside | dip in / out (ft/mi) | isopach in / out (ft) | grid control pts within ½ mi of the outside sample |
|---|---|---|---|---|
| N | 47 % | 111 / 120 | 428 / 436 | 0.04 |
| NE | 27 % | 114 / 39 | 488 / 429 | 0.35 |
| E | 92 % | 144 / 159 | 433 / 481 | 0.50 |
| SE | 100 % | 121 / 104 | 441 / 420 | 0.37 |
| S | 100 % | 92 / 94 | 535 / 545 | 0.14 |
| SW | 100 % | 101 / 92 | 400 / 369 | 0.28 |
| W | 100 % | 103 / 106 | 321 / 290 | 0.03 |
| NW | 79 % | 123 / 120 | 466 / 470 | 0.09 |

Grid-wide inside vs 0–5 mi outside: dip median 97 vs 100 ft/mi, isopach 460 vs 434 ft. On gap
segments vs pinned segments: isopach 444 vs 439 ft outside, dip 104 vs 107 ft/mi.

**Read:**
1. **Structure is quiet and continuous on every side, inside and outside alike.** The 2BS top is
   a ~100 ft/mi eastward homocline with no break at any edge. By the proposed rule, every edge would
   "follow structure outward". The signal doesn't discriminate a capped edge from a gap, because the
   BS2_S edge isn't structurally controlled. It's facies/charge (sand quality, oil saturation),
   which structure doesn't map.
2. **Isopach is the more relevant surface, and it is weak too.** It thins W (321 → 290 ft) and SW
   (400 → 369 ft), consistent with the rolled W/SW performance. But it's flat across S and SE and
   indistinguishable between gaps and pinned stretches.
3. **The grid is weakest exactly where we'd need it.** It doesn't cover the N and NE of the extent
   (27–47 %). Outside the edge it's interpolation: ≤ 0.5 control points within ½ mi, and 0.03–0.14
   on N/W/S/NW. Inside the edge its control is largely the same wells that already define the
   extent. At ~1-mi nodes it can't resolve anything finer than the gaps we measure. The dip map's
   bullseyes around control clusters are gridding artifacts.

**Recommendation:** not worth adding as an automated extent driver for step 2 or step 3. The
practical use is as a **context layer in the step-3 geology package**: ship the 2BS isopach
contours (and the structure contours, `*_cont.xyz`) beside the extent shapefile. Geology can then
judge, for example, whether the W thinning supports a tighter W buffer despite the live front. That
is geology's call in GGX, where Holden already has these surfaces. Revisit only if a bench's edge
proves structurally controlled (a fault or a structural nose), which the BS2_S data doesn't show.

## 9. Gate 2 closed (Michael, 2026-10-07)

- **Metric accepted** as built (r = ½ mi measuring radius, c = ¾ mi tuned on WCA) **and the step-out
  table accepted** as the second half of the edge read. Plan D23.
- **Potash ignore-gap polygon = BLM Secretary's Potash Area.** Plan D24; step 3 sources it.
- **Grids:** agreed context-only. They were built as regional grids; edge detail takes interpretation time,
  and far-flung areas have few vertical penetrations to pick tops from. The BS2_S W edge is likely
  governed by depth (pressure) and water saturation, not structure. Plan D25.
- Step-3 note: if the W edge is depth/pressure-controlled, the relevant measure is the 2BS top's
  *depth* (or the producers' own TVD) at the W edge, not dip. Producers' TVD is available
  wherever wells exist, so it doesn't depend on grid coverage. Candidate geology-package layer;
  not decided.
