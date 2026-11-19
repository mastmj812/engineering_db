# BOX sticks: replace the Novi Intelligence locations

Plan approved by Michael 2026-11-12. Stepped build: every phase ends at a gate; nothing rolls forward without
Michael's go. Phase 0 evidence: `docs/box_sticks/phase0-2026-11-12/` (`scripts/box_sticks_phase0.py`).

## Context

Undrilled locations today are Novi Intelligence sticks. Three defects drive this work:

1. **5,000 ft laterals** that nobody drills; short DSUs are developed with U-turns in practice.
2. **Stick TVD is often wrong** relative to same-bench PDP, which compromises proximity and reconciliation.
3. **Coarse vendor tags** that we infer a `formation_blueox` onto (sql/19), which is clunky and error-prone.

Outcome: our own generated locations ("BOX sticks") inside the Novi DSU polygons, on benches given by the
BOX extents, at locally-observed density, landed on a surface built from same-bench PDP TVDs, kept out of
depleted rock, reconciled NIGHTLY against new drilling. Then BOX is re-run on those sticks and the Novi
stick chain is retired.

### Decisions already made (Michael, 2026-11-12)

| Topic | Decision |
|---|---|
| Bench eligibility | A DSU that intersects a BOX extent gets that bench (intersect counts) |
| WCXY (Delaware) | Gets its OWN extent, controlled by geology (XY sands, essentially north of the Grisham fault complex), not by wherever a vendor wrote WCXY. No WCXY sticks outside it. See Phase 1b |
| WCA_1 / WCA_2 (Delaware) | Stay pooled in the WCA extent (upper vs lower WCA). Each gets its own row only where same-code PDP gives local landing control |
| U-turns | Straight lateral < 7,000 ft after setbacks -> U-turn (about 1-mile DSUs). 1.5-mile stays straight (~7,260 ft) |
| Density | From offset development; floor 4 wells per section (spacing no wider than 1,320 ft; 1,540 ft is the loosest reading) |
| Stagger | Adjacent benches offset by half the spacing, never under 300 ft |
| Orientation | DSU long axis; square DSU -> surrounding PDP; a U-turn's orientation is its legs |
| Landing TVD | Surface from same-bench PDP TVDs per extent, not structure grids; never out of stratigraphic order in a DSU |
| Landing depth without direct control (2026-11-12, after phase 0) | Allowed for non-pooled benches: depth carried from a neighbour bench by thickness (existing method, to 5 mi), flagged `tvd_basis = 'thickness'` as lower confidence, hold-out error reported separately. WCA_1 / WCA_2 / WCXY still need direct control. Reason: only 17 % of today's stick positions have a same-bench producer within 1 mi |
| Focus benches (2026-11-12) | Delaware BS1_S and Midland DEAN: thin own control over a large extent, dense neighbours. DEAN sits between LSSH above and WCA_1 below, so it is also the test case for topfill / underfill / sandwich no-place logic (phase 2b). Generator pilot AREAS (all benches per DSU) are picked inside these two extents |
| Landing-depth chain (2026-11-12, after phase 1b) | direct -> local thickness (own wells within 5 mi) -> bracket between a bench above and a bench below -> single-neighbour offset -> none. **No error ceiling: weak carried depths are still placed, flagged low confidence.** Every stick records its rung (`tvd_basis`) and that rung's held-out error |
| WCA_1 / WCA_2 depth (2026-11-12, after phase 1c) | Both take the full landing-depth chain (supersedes "direct control only" for these two; WCXY stays direct-only until it has its own extent; **WCXY joined them 2026-11-16, see the WCXY depth row below**) |
| WCA_1 / WCA_2 under the floor (2026-11-12) | Where the two landings are closer than the minimum separation (75 ft) or out of order in a DSU, that DSU gets ONE WCA landing. Detail to settle in the generator: it takes the code and depth of the member with the more trusted depth there |
| Stack reconciliation (2026-11-12) | Benches are estimated independently, then each conflicting adjacent pair in a DSU is reconciled: the less trusted depth gives way (carried before direct; among carried, the higher held-out error). It moves to the minimum separation if that stays inside its own error band; otherwise that bench gets no stick in that DSU, with the reason recorded |
| Evidence screen (2026-11-12) | Two-part, replacing a fixed cutoff. **Likely mis-tag**: a well closer to another bench's direct surface than to its own and more than max(150 ft, half the local gap) off its own is removed from its tagged bench's evidence and listed for formation-tag review; the surface builder never re-tags. **Bad depth**: more than 300 ft off its own surface and not a mis-tag is dropped. Live tags: 1,499 + 377 wells |
| Spacing floor and tight cap (2026-11-12 / 13, phase 2a) | Floor **1,320 ft** (4 WPS), not 1,540 ft: realized gaps peak at 660, 880 and 1,320 ft and show nothing at 1,540 ft. Tight cap **440 ft** (12 WPS), revised from 660 ft on 2026-11-13 when density went back to per bench: a 660 ft cap would hold an 11 WPS development at 8 |
| Density is per bench (2026-11-13, phase 2a; reverses the per-landing choice of 2026-11-12) | Bench density is the count of same-bench wells across a section, however the operator staggered them vertically. Reference case: Ruthless 11 Federal COM (Lea), 11 BS2_S wells across a mile at two landings 350 ft apart = 11 WPS, not 5-6 per landing. Known: this measure fails the cross-check against Novi `lateral_closer_xy_ft` in the Delaware (65 % against a 70 % bar) because Novi counts per zone; kept deliberately. The vertical arrangement is the generator's job: where local wells show two landings, sticks alternate between them (open item) |
| Spacing map (2026-11-13, phase 2a; supersedes the 1 -> 2 -> 3 mi radius chain and the hard band default merged in PR #244) | **Blended surface.** Per bench, the Gaussian-weighted median of per-bench well gaps around the DSU (sigma 3 mi, wells out to 7.5 mi, weight by distance DSU polygon to well), relaxed toward the bench's extent-band median as control thins: spacing = band - c (band - weighted median), c = n_eff / (n_eff + 1), n_eff = sum of weights. Bands are distance inside the bench's BOX extent edge (0-2, 2-5, 5-10, 10+ mi); a band with fewer than 20 wells -> 1,320 ft. Clamped to 440-1,320 ft. Every stick records `spacing_basis` (n_eff, weighted median, band value). Reason (Michael): a mature bench reads as nested contours, densest in the core and thinning outward, because operators drilled the best rock first; a gap in development inside the core must not drop to a default. Evidence: passes its pre-set adoption test in both basins; with wells within 2 mi hidden the median error is 137 ft Delaware / 87 ft Midland against 161 / 104 ft for the chain; adjacent-DSU steps over 200 ft fall from about 15 % to about 2 % |
| No-place envelope (2026-11-14, phase 2b; candidate D) | A stick is not placed when an existing producer runs alongside >= 30 % of it AND sits either (1) at the **same landing** (within 150 ft vertically, whatever the tag) within **400 ft** sideways, both basins (the Midland 21a floor, now the Delaware's too), or (2) **stacked** within **300 ft** sideways: producer 150-350 ft deeper (both basins); producer shallower by 150-250 ft (Delaware) or 150-350 ft (Midland). Gap = median perpendicular distance over the shared length. Outside it the stick is placed and D150 discounts it. Tested against existing producers only, never stick against stick, so a co-developed stagger inside a bench (Ruthless 11) is untouched. Evidence: drilled children next to a parent >= 12 months on are 0.04-0.05 of the far-field rate inside the same-landing part and 0.14-0.22 in the stacked part (0.87-1.15 when the neighbour is co-developed); the envelope would have excluded 260 of 22,610 Delaware children (1.15 %) and 377 of 23,988 Midland (1.57 %). Not adopted: D112's 800 / 500 ft vertical and deal-intake v14 as placement rules (they exclude 7-28 % of what was drilled); a 600 ft same-landing limit; the Midland stacked part past 350 ft. Decided with two failed bars stated: the pair-metric reproduction, and the D150 refit check in the Midland (the Midland factor's near end is re-measured in phase 6) |
| Drop trigger | Spud / DUC removes a location from undrilled counts; an approved permit only flags. **Superseded 2026-11-18: producing only, see the row "Drop trigger, revised"** |
| Generator: which wells count (2026-11-15, gate 3a) | Every producer at any age plus spud / DUC / completed wells. A well's own planned-survey depth is never used |
| Generator: well with no depth evidence (2026-11-15) | Pins its bench's row grid. It is tested through the normal envelope at the DSU's landing depth of its tagged bench, where that bench kept a landing in the DSU; otherwise it closes its whole formation family within 400 ft sideways |
| Generator: one landing per bench (2026-11-15) | One landing per bench per DSU; where the DSU's own wells show two, the flag `two_landings_observed`. Known from the back-test: in 17 of 40 pilot DSU x bench drilled in two campaigns, the later campaign landed more than 150 ft from the earlier one |
| Generator: WCA_1 / WCA_2 (2026-11-15; refines the 11-12 rows) | Both placed only where co-developed nearby (each member >= 8 depth-evidenced producers within 3 mi; >= 3 DSUs within 3 mi drilled in both, making >= 25 % of the WCA-drilled DSUs there), with no envelope test between the two members there. Elsewhere one WCA row set at the locally dominant member |
| Generator: U-turns (2026-11-15) | Legs at max(bench spacing, 1,200 ft), on adjacent rows of ONE bench; an odd leg or a single open slot is not placed. Reproducing short straight wells in Tier-1 rock is not a goal |
| Generator: lithology members (2026-11-15) | BS2_C / BS2_S and BS3_C / BS3_S each get their own rows; BOX precedence downstream decides which are drillable |
| Generator: sliver floor (2026-11-15) | A bench whose extent covers under 10 % of the DSU area gets no row |
| Generator: azimuth (2026-11-15; supersedes "long axis, square -> surrounding PDP") | Wells inside the DSU, then the 6-mi cell (>= 10 horizontals), then the county, snapped to a polygon side; where the two sides tie, the long axis with a flag |
| Generator: setback fit (2026-11-15) | Rows are fitted to the width clear along the whole lateral by tightening SPACING up to 10 % (never under 440 ft; U-turn legs never under 1,200 ft); beyond 10 % a row is dropped and the rest spread evenly. Pinned grids are not moved |
| Generator: no test between planned rows (2026-11-15; supersedes "Stagger ... never under 300 ft") | Rows of different benches are never tested against each other and no bench takes another bench's spacing. Sticks are what is possible in the DSU: its extents, what is drilled, and each extent's own spacing evidence. The envelope against existing wells is the only placement test |
| Generator: grid phase (2026-11-15) | A bench not pinned by existing wells keeps every row its own fit gives and takes, inside the slack of the clear width, the side farthest from the rows of the bench above, so the stack alternates left and right. No bench loses a row to it |
| Generator: rows between parents (2026-11-15) | Stay as placed, with no parent-gap stamp. Whether a child between two parents is worth drilling is for the BOX forecast, so stick counts in developed DSUs overstate practical inventory |
| Generator: narvi engine (2026-11-15) | Imported as a library pinned by commit (`requirements-dealintake.txt`); the canonical copy stays in narvi |
| Gate 3a (2026-11-15) | Pilot generator goes on to the basin-wide run with the back-test failures stated: T1 58.9 % against 60 % (Ward 46.9 % against 50 %), T3 63.2 % of units within one leg against 70 %, T4 33.3 % unused slots against 25 %, bracket depth rung 1.59x against 1.5x. T2, direct-rung depth and the total count (0.96) pass. The bars stand as written. Not adopted: a bench's own in-DSU spacing in place of the map (trial: no gain) |
| WCXY depth (2026-11-16, after the 3c trials; supersedes "WCXY stays direct-only") | Delaware WCXY takes the full landing-depth chain like every other bench. Generator `box_sticks_0.8_pilot`: WCXY DSU x bench with a depth 854 -> 1,277 of 1,299, WCXY sticks 454 -> 963, other benches net -12 |
| DSU polygons (2026-11-16) | BOX sticks stay on the Novi 2026Q3 DSU polygons. Short polygons drilled across with long laterals are an artifact of that shapefile; drawing our own DSUs is not undertaken now. Their sticks carry the flag `dsu_drilled_across` (U-turn DSU with >= 2 existing wells >= 1.3 x its longest row; generator `box_sticks_0.9_pilot`; 400 DSUs, 1,936 sticks; nothing moved or removed) |
| Not adopted (2026-11-16, measured in the 3c trials) | Dropping a carried depth implausible against a direct bench; two landings per bench. Both switches stay off |
| Thickness-rung anchor (2026-11-18) | The anchor stays the first eligible bench in the held-out rank order. The median of every eligible anchor was scored after the tag cutover reordered Midland WCD on a 0.03 ft margin: it wins the hold-out (Delaware 52.8 -> 50.0 ft median, Midland 40.1 -> 37.9 ft) and the back-test run once did not confirm it (same 263 hidden wells, 70.2 -> 79.0 ft median miss; over 150 ft 25.1 -> 19.4 %). Built behind `THICK_RULE`, off. `docs/box_sticks/cutover-2026-11-17/FINDINGS.md` |
| Second level nearby (2026-11-18) | A thickness-carried depth whose neighbouring same-bench wells sit at two levels (second peak >= 150 ft away, >= 25 % of the weight, >= 3 wells) gets the flag `second_level_nearby` and the other level's TVD; nothing is placed or moved by it. Generator `box_sticks_0.10_pilot`: 5,074 sticks flagged (Delaware 3,575, Midland 1,499), 0 sticks changed otherwise. Flagged depths miss 87.1 / 74.1 ft median on the hold-out against 50.0 / 39.2 ft unflagged. Thickness rung only. `docs/box_sticks/phase3e-2026-11-18/FINDINGS.md` |
| Storage: stick rows per set (2026-11-18, gate 4a Q1; refines "`box.location` gains ...") | `box.location` holds identity only (source, DSU vintage, pad id, slot number, first / last seen set; `geom` and `lateral_ft` as last seen). The generated stick (legs, turn, TVD and how it was reached, spacing, flags) is one row per set in `box.location_stick`, so an older set stays explainable after a regeneration |
| Identity rule (2026-11-18, gate 4a) | Same DSU + bench, >= 50 % of the shorter stick alongside within 220 ft sideways, 1:1 greedy; slot numbers never reused; depth is not identity, bench is. A new set carries ids from the basin's RECORD set (from the latest stored set while there is no record). Measured: 91.2 / 89.8 % carried across the tag cutover, 99.65 / 98.96 % over one night (Delaware / Midland) |
| App-facing id (2026-11-18, Q2) | `stick_id = location_id` for BOX sticks; the id sequence restarts at 10,000,001, apart from Novi stick ids (max 1,824,903) and the Novi-seeded location ids (max 252,947). PDP `-(api10)` untouched |
| Stick name (2026-11-18, Q3) | Stored `well_name` = `<pad_id>-<bench>-<slot number>`, stable across sets; not the position in the row |
| First stored set (2026-11-18, Q4) | Stored NOT record. The record flip is a separate explicit go once both basins are stored and checked. Nothing reads `box.location_set` before phase 5. **Flipped 2026-11-18:** set 6 (Delaware) and set 7 (Midland) are the records | **Superseded 2026-11-19 by set 16 (Delaware, 46,062 sticks) and set 17 (Midland, 33,138), generator 0.12** |
| Row ledger (2026-11-18, Q5) | Not stored. Culled rows are counted by reason per DSU x bench (`box.location_set_bench.rows_culled`); the ledger regenerates from the stored inputs |
| WCXY extent storage (2026-11-18, Q6; supersedes "store with the phase 4 writes") | Not stored in `box.extent` in phase 4. The committed geojson is pinned by sha256 in each set's manifest and a missing file fails the run. Reason: a record WCXY extent needs a `box.bench_scope` row and enters the nightly tag rule's inputs, erebor's scope list and the geology package. Store it when phase 6 settles the WCXY forecast pool |
| narvi private functions (2026-11-18, Q7) | Four are imported (`placement._longest_segment`, `generate._make_leg`, `generate._single_well`, `generate._place_uturns`). A narvi PR exposes them under public names with no behaviour change, then the pin is bumped. No engine copy. **Done 2026-11-18:** narvi #34 merged (`bfc7955`), pin bumped, `box/sticks/core.py` uses `longest_segment`, `make_leg`, `single_well`, `place_uturns`; a test fails if any is missing; 5,864 sticks in 400 Delaware DSUs identical on the new pin |
| Second level on bracket / offset rungs (2026-11-18, Q8) | Not measured before storing. `second_level_tvd_ft` is NULL there and the column comment says NULL means not measured |
| Direct-rung expected error (2026-11-18, Q9) | Every stick stores an expected error: direct-rung sticks take their bench's direct hold-out (`holdout_direct.csv`, median and P90). Reported on the stick only; the stack reconciliation keeps using what it used (no stick moves) |
| Drop trigger, revised (2026-11-18, gate 5a; supersedes "Spud / DUC removes a location") | **Producing only.** A location leaves undrilled counts when a matching well has a first production date. A well that is spudded, a DUC or completed but not producing only flags, like an approved permit, and is re-judged the night it produces. Reason (Michael): before a survey or the completion report reaches the vendor, tags and depths are permit data. Measured: no depth evidence on 39 % of Texas and 57 % of New Mexico Spud wells against 0.6 % and 23 % of this year's producers; 41 % of newly spudded Midland wells are tagged OTHER or untagged; conflicts fall from about 30 % of sticks taken out to 11 to 14 %. Cost: a median 196 days (NM) and 220 days (TX) from spud to first production. The GENERATOR still reads wells that are not producing yet (2026-11-15 row); that is not changed |
| Shape of nightly reconciliation (2026-11-18, gate 5a; Michael: "i agree") | **Stick status** as designed in `docs/box_sticks/phase5a-2026-11-18/DESIGN.md` (ETL-owned tables written by a nightly hook that reads `box.*` and never writes it), with the producing-only trigger, the 30 % conflict floor, the three generator-mirroring rules (no test between WCA_1 and WCA_2 in a co-developed DSU; a well with no depth evidence taken at the DSU's landing of its tagged bench, family otherwise; crowded on the median form) and flat-ended corridors. **Stale row:** one nightly row per DSU x bench holding a new producer of that bench, with the new producers and an estimated stick count marked as an estimate. **Regeneration** stays periodic and explicit-go, with the stale list as its work list. The estimate (the lower of the stick status and sticks minus new producers) gets its own bar in 5b |
| Gate 5c go (2026-11-19; Michael: "Go apply sql/74") | **sql/74 applied on live**, the four reconciliation tables only (`meta.box_recon_run`, `curated.box_location_status`, `curated.box_location_status_log`, `curated.box_dsu_bench_stale`), and with it the standing authorization for the nightly to write those four tables behind the circuit breaker. Shadow only: nothing reads them until gate 5 |
| Reconciliation conflict floor (2026-11-18, gate 5a) | A well alongside **30 % to 50 %** of a stick leg is a conflict, not sql/68's 20 % to 50 %. Reason: the generator places a row beside a well that runs along under 30 % of it (2026-11-15, DSU 10600), so 20 to 30 % was a conflict by construction: 168 of 215 Delaware and 52 of 58 Midland day-0 conflicts on generator 0.12. sql/68 itself keeps 0.2 on the Novi sticks |

### What exploration found (shapes the plan)

- **Checkout is 109 commits behind `origin/main`.** The landing-surface and tag-rule code exist only on main. Start from a fresh branch off `origin/main`.
- **Reconciliation is quarterly today** (`curated.reconciled_inventory`, sql/68, rebuilt only in the Novi reload). Nightly reconciliation is new machinery.
- **A landing-surface builder already exists**: `box/landing_surfaces.py` (0.25-mi lattice per code inside its BOX extent; weighted median or robust plane; hold-out median error 42 ft Delaware / 36 ft Midland, P99 431 ft). Results are files only, built from live tags.
- **The geometry engine exists and is DB-free**: narvi `generate_wine_rack` (`narvi/src/narvi/generate.py:574`) already staggers by half spacing with a 300 ft minimum and supports U-turns. It never CHOOSES a U-turn and has no square-parcel rule.
- **No wells-per-section calculation exists anywhere.** Closest: `dealintake/spacing.py` gap method.
- **BOX cannot take a non-Novi location today**: `box.pud_forecast.stick_id` and `box.location_source.stick_id` are NOT NULL; `_UNIVERSE_SQL` (`box/production.py:90`) reads only `intel_*`; proximity takes stick TVD from `erebor_locations.tvd` (Novi).
- **`curated.erebor_locations` (sql/22) mixes Novi sticks with our PDP rows**, so PDP display goes down in every Novi rebuild.
- **DSU polygons are `raw_novi_intel.pads`** (shapefile load, not the Snowflake share). They survive; pad MEMBERSHIP (sql/67, by Novi `pad_name`) does not.

## Phase 0 - Baseline evidence (read-only; can start now)

No dependency on the tag cutover. Nothing written to the warehouse.

- **0a. TVD bust map.** For every Novi PUD/RES stick: `novi tvd - same-bench PDP landing depth` at the stick.
  Landing depth from `box/landing_surfaces.py`; cross-check against `intel_pdp_support.offset_median_tvd` /
  `tvd_excess_3mi_ft` (sql/30). Deliver a map coloured by signed bust per bench plus a table by
  basin x bench x county: n sticks, median, P10/P90, share beyond 150 ft and 300 ft. Run on today's tags and
  on the shadow rule tags so the tag effect is visible separately from the Novi effect.
- **0b. DSU polygon audit** (`raw_novi_intel.pads`, 2026Q3): count per basin, overlapping polygons, size and
  aspect-ratio distribution (how many are near-square), share of each BOX extent's area covered by a polygon,
  PDP laterals outside any polygon, polygons clipped by an extent edge (sliver sizes).
- **0c. Lateral-length audit.** Novi stick length distribution by basin/bench vs the lateral a straight or
  U-turn well would get in the same polygon.

**Gate 0:** Michael reviews the bust map and the polygon audit; confirms the polygons are a usable frame and
names pilot areas (proposal: one Delaware TX, one Delaware NM, one Midland).

## Phase 1 - Landing surfaces of record (after the 11-16 tag decision)

- Rebuild surfaces on the tags that will be live after the cutover decision (shadow run 6, 2026-11-16 nightly).
- Evidence rules, matching the tag rule: survey lateral median TVD (`well_lateral_survey.lat_tvd_p50_ft`) else
  `tvd_ft`; planned-survey wells, round-100 TVDs without a survey, depths < 4,000 ft and
  `ref.formation_tag_depth_exclusions` rows are never evidence.
- Store them: new app-owned table `box.landing_surface` (basin, code, node, tvd, n wells, method, hold-out error,
  version). Method per node kept: direct (same-code wells) vs anchor-thickness (carried from a neighbour bench).
- **Local control** (pooled-extent rule): a member code qualifies in a DSU only on DIRECT nodes. Non-pooled
  benches may use anchor-thickness nodes, flagged `tvd_basis = 'thickness'`.
- **Stratigraphic order**: per DSU, sampled depths must be monotone in `strat_column.yaml` order with a minimum
  separation (start at the tag rule's 75 ft). A violation is flagged and the offending bench is held out of
  that DSU, never silently re-sorted. Lithology pairs (BS2_C/BS2_S, BS3_C/BS3_S) sit at near-equal depth and
  need their own rule: proposal, the pair shares one landing and only the locally developed member gets a row.

**Gate 1:** hold-out error by bench and basin, map of direct vs thickness coverage, list of order violations.

**Phase 1 / 1b evidence (2026-11-12, live tags; `docs/box_sticks/phase1-2026-11-12/`, `phase1b-2026-11-12/`).**
Direct + 5-mi thickness leaves 35.5 % of DSU x bench pairs with no depth. Michael's requirement: that gap must be
closed. Chain adopted (no error ceiling; weak rungs placed and flagged low confidence): direct -> local thickness -> **bracket** between
a bench above and a bench below (Michael's idea; DEAN between LSSH and WCA_1 holds 40 ft median / 135 ft P90 with
no DEAN well within 5 mi) -> single-neighbour offset -> none. The chain leaves 6.7 % with no depth. Weak where a
bench has no dense neighbour on one side (Delaware BS1_S, Midland WCC / WCD). BOX sticks get their own anchor
configuration; `box.landing_surfaces.ANCHOR` is shared with the tag code and is not edited.

**Phase 1c (2026-11-12, `phase1c-2026-11-12/`): benches are estimated independently, the stack is reconciled per
DSU.** A carried depth uses only neighbours' direct surfaces, so there is no circularity. With the full chain,
adjacent benches conflict (out of order or under 75 ft) on 4-6 % of pairs in Midland whether the depths are direct
or carried; Delaware's conflicts are mostly the WCA family (two halves of one bench about 115 ft apart). No joint
surface fit is needed. Decided the same day: WCA_1 / WCA_2 on the full chain (their no-depth share falls from
38-40 % to about 10 %), one WCA landing under the floor (1,204 of 3,886 DSUs), and the reconciliation rule. With
those, 11.9 % of DSU x bench pairs have no depth (6.4 points are WCXY, waiting on its extent) and 14.8 % are low
confidence. Gate 1 decisions are complete (evidence screen decided the same day). Before a surface is stored: the
WCXY extent (phase 1b), a re-run on post-cutover tags, an explicit go for the write.

## Phase 1b - WCXY extent (Delaware)

Why: WCXY means a well landed in the XY sands of the Wolfcamp A, which are essentially only present north of
the Grisham fault complex. Vendors also write WCXY on wells that are merely shallow in the WCA where no XY
sand exists. A tag-derived extent would inherit those mistakes, so the extent is controlled, not learned.

- **Evidence pass (read-only).** For every WCXY-tagged horizontal: its depth position relative to the local
  WCA_1 landing surface, and whether the area carries TWO distinct stacked landings (WCXY above WCA_1, with a
  real separation) or just one. Real XY development shows the stacked pair; a mis-tag shows a lone "WCXY"
  well at the same depth as its WCA_1 neighbours. Map both classes.
- **Candidate extent** from the stacked-pair wells only, using the standard BOX construction (D27 envelope,
  same constants as the other benches: `box/extent.py`, `box/family_extent.py`).
- **Geology control.** Michael edits the southern limit to the Grisham fault complex (hand-drawn or an
  imported line; `scripts/box_extents_import.py` already stores `source = 'geology_edited'`). Open item: we
  have no fault geometry in the warehouse that I know of - confirm a source at the gate.
- **Store** as the WCXY extent of record (`box.extent`; needs its own `box.bench_scope` row, since extents
  key on it). Explicit go, like any `box.*` write.
- **Consequences to state, not assume:**
  - WCXY-tagged PDP OUTSIDE the extent is treated as upper WCA for landing-surface evidence, no-place and
    reconciliation in the generator (the 150 ft same-landing rule already ignores the tag).
  - Correcting those tags themselves is a formation-tag policy seed (outside the WCXY extent, WCXY -> WCA_1).
    That is NOT touched during the shadow test; propose it after the 11-16 cutover decision.
  - Forecast pooling: BOX currently forecasts WCXY inside the pooled WCA bench (D19 / D20 / D95). This plan
    changes WHERE WCXY sticks are placed, not the analog pool. Whether WCXY also becomes its own forecast
    pool is a separate decision for Phase 6.

**Gate 1b:** evidence map (stacked-pair vs lone-tag wells), candidate vs edited extent, count of WCXY-tagged
wells left outside it by county.

**Phase 1b outcome (2026-11-12).** The evidence pass and three automated rules (fixed separation, empty band, tier
count) were tested against 31 blind card calls by Michael; none beat calling every pad XY, so the extent was drawn
by hand (`docs/box_sticks/wcxy-*-2026-11-12/`). **Michael's hand-drawn WCXY extent, reading confirmed by him:
`docs/box_sticks/wcxy-extent-2026-11-12/extent_WCXY_edited.geojson`, 1,730 sq mi, one piece; 1,483 of 1,806
WCXY-tagged evidence wells inside.** It is the WCXY extent for the generator pilot as a FILE. Not stored: a
`box.extent` row needs a `box.bench_scope` row for WCXY, and how the BOX forecast run reads that table must be
checked first (the WCXY forecast-pool decision, phase 6); store with the phase 4 writes on an explicit go.
The extent says where an XY landing is a target. Inside it, a WCXY-tagged well at upper-WCA depth is evidence for
the landing surface it is nearest in depth; outside it, WCXY-tagged wells are treated as upper WCA (WCA_1). Tag
corrections go to the formation-tag review after the 11-16 decision; the surface builder never re-tags.

### Follow-up for the formation-tag workflow: use the WCXY extent (Michael, 2026-11-12)

The tag rule treats WCXY / WCA_1 / WCA_2 as one family and lets depth decide the position; a vendor "Wolfcamp XY"
label is taken at face value anywhere (the shadow rule moves none of the 1,815 WCXY-tagged evidence wells). The
record extents are already in the rule's inputs for reporting only (`box/tag_rule_inputs.py`). The hand-drawn
WCXY extent adds what the rule lacks: where an XY landing can exist at all. Not before the 11-16 decision; the
shadow comparison stays on the rule as frozen.

1. **2026-11-16**: cutover decision on the current rule, unchanged.
2. **Store the WCXY extent** in `box.extent` (explicit go). Needs a `box.bench_scope` row for WCXY: first check how
   the BOX forecast run reads that table, so a new row does not change a forecast pool.
3. **Class 1, outside the extent: WCXY -> WCA_1.** A rule revision through the usual gates (class, sample cards
   for Michael, accept / reject, seed via `scripts/tag_rule_seeds.py`, reload). Never a hand-edited rule row.
   Covers the 323 evidence wells outside (`wcxy-extent-2026-11-12/wcxy_wells_outside_edited.csv`) plus
   WCXY-tagged wells that are not depth evidence (planned surveys, permit depths; not yet counted).
4. **Class 2, inside the extent: pads at upper-WCA depth.** The extent does not settle these (XY and one-landing
   pads sit side by side); the extent only tells the depth step that WCXY is an allowed answer inside and not
   outside. Starting labels: Michael's 31 card calls (`wcxy-cards-2026-11-12/verdicts.csv`). Three automated
   rules failed against them (`wcxy-tiers-2026-11-12/FINDINGS.md`), so expect cards, not a formula.

Blast radius: small. BOX pools WCXY + WCA_1 + WCA_2 in the Delaware (D19 / D20 / D95), so moves between the three
change no forecast pool and no record run. They do change what reads the individual code: the BOX stick landing
surfaces (the point), anduin formation filters and cohorts, deal-intake bench menus near the Loving - Eddy line.

Guard: the extent was drawn on today's tags and depths. After tags are corrected from it, it is NOT re-derived
from the corrected tags; it stays Michael's call, revised by him when the geology warrants.

## Phase 2 - Density and the no-place envelope (studies; read-only)

- **2a. Realized spacing per bench per neighbourhood.** Perpendicular gap between same-bench, co-developed
  producers (first production >= 2016), reusing the gap method in `dealintake/spacing.py` on PDP laterals
  instead of Novi sticks, with `wells_enriched.lateral_closer_xy_ft` as a cross-check (NULL and the 2800
  sentinel excluded). Spacing = local median, clamped to [tight cap, 1,320 ft]; no control -> 1,320 ft (4 WPS).
  Tight cap proposed at 660 ft (8 WPS), to be confirmed from the data.
- **2b. No-place calibration.** For drilled child wells with a parent >= 12 months on production, the
  distribution of horizontal gap x signed vertical gap x overlap, per bench pair and basin (measurement code
  exists: `box/prox_study.py`, `box/prox_dose.py`). The envelope is where real drilling becomes rare.
  Starting points: same landing <= 150 ft vertical and <= 400 ft sideways with >= 30 % alongside (Midland
  21a floor); topfill 800 ft / underfill 500 ft vertical (D112); deal-intake v14 300 / 800 / 30 %.
  Outside the envelope a stick is placed and the existing D150 proximity factor discounts its forecast;
  the envelope must not double-count that.

**Phase 2a outcome (2026-11-12 / 13, `docs/box_sticks/phase2a-2026-11-12/`, `scripts/box_sticks_phase2a*.py`).** Per
bench, 32,124 wells measured (Delaware 13,899, median 1,005 ft = 5.3 WPS; Midland 18,225, median 825 ft = 6.4 WPS).
Decided: floor 1,320 ft, tight cap 440 ft, per-bench density, blended spacing surface relaxing to extent bands
(decision table; the per-landing measure, the radius chain and the hard band default were each decided and then
superseded during the review, see the findings' decision history). The map averages 1,088 ft (4.9 WPS) over 29,719
Delaware DSU x bench and 949 ft (5.6 WPS) over 19,835 Midland. Against Novi: mean spacing 1,276 -> 1,124 ft
Delaware, 1,224 -> 960 ft Midland; wider on Delaware AVA_2, BS2_S and the WCA family, tighter on Midland WCC / WCD
/ DEAN / JM / MS.

**Phase 2b outcome (2026-11-13 / 14, `docs/box_sticks/phase2b-2026-11-13/`, `scripts/box_sticks_phase2b.py`).** 46,598
drilled children against parents >= 12 months on production (57,478 Delaware and 82,948 Midland links). Same landing:
drilling inside 400 ft of a parent runs at 0.04-0.05 of the 1,000-2,000 ft rate and stays rare to 600 ft. Stacked
150-350 ft within 300 ft sideways: 0.14-0.22 beside a parent, about 1.0 beside a co-developed well. Delaware vertical
avoidance is gone by about 450 ft. Decided: candidate D (decision table). DEAN: 139 of 961 children are sandwiches but
only 17 have a parent above and below within 660 ft; 61 of 920 DSUs with LSSH and WCA_1 already developed got DEAN a
year or more later. On today's Novi sticks D culls 11,703 of 166,636 Delaware and 7,243 of 85,811 Midland (Novi TVD;
most already carry no forecast in the record runs). Two pre-set bars failed and are stated in the findings: the pair
metric against `prox_study` (agrees at envelope scale), and the D150 refit check in the Midland (the near end of the
Midland curve rests on about 50-130 close-in wells; direction lenient, not doubled). **Gate 2 is closed.**

**Gate 2:** spacing table and maps; proposed envelope per bench pair with the share of historical children
it would have excluded. Michael freezes both.

## Phase 3 - Generator (pilot, then basin-wide)

New package in `engineering_db` (proposal `box/sticks/`), importing narvi's DB-free core as a library and
feeding it set-based warehouse reads (the per-parcel narvi queries do not scale to every DSU).

Per DSU:

1. **Benches** = record BOX extents intersecting the polygon (sliver floor from 0b). Inside the WCA extent,
   WCA_1 and WCA_2 each need local control; WCXY needs the WCXY extent AND local control.
2. **Azimuth** = long axis of the minimum rotated rectangle. Near-square (aspect below ~1.15, set at Gate 0) ->
   axial mean of surrounding PDP if coherent (existing gate: R >= 0.85, >= 3 wells), else flagged.
   True -> grid conversion via `dealintake/geo.true_to_grid` (narvi places in UTM 13N).
3. **Well type** = straight when the lateral is >= 7,000 ft, else U-turn. Open detail: narvi needs >= 990 ft
   leg separation; where bench spacing is tighter, U-turn legs take 990 ft. A DSU too small even for a
   U-turn gets no sticks and is listed.
4. **Existing development.** Wells in the unit by the >= 30 % overlap rule. Existing same-bench wells pin the
   row grid so new sticks fill open slots; rows inside the frozen no-place envelope are culled, each with a
   recorded reason.
5. **Stagger** via `generate_wine_rack` (half spacing, 300 ft minimum); a bench pinned by existing wells leads.
6. **TVD** sampled from `box.landing_surface` along the stick; order check from Phase 1.
7. **Output** mirrors `narvi.inventory_well`: legs + turn geometry, completed and drilled lateral, azimuth,
   target TVD + basis, spacing + basis, DSU id, generator version, cull reasons.

Review surface: rendered per-DSU cards (plan view + gunbarrel with PDP, BOX sticks, culled rows, and the Novi
sticks for comparison), not YAML.

**Phase 3a outcome (2026-11-14 / 15, `docs/box_sticks/phase3a-2026-11-14/`, `box/sticks/`,
`scripts/box_sticks_phase3_*.py`).** Generator `box_sticks_0.7_pilot` on 114 DSUs in Ward TX, Lea NM and Glasscock /
Midland: 1,526 BOX sticks (1,751 legs) against 1,993 remaining Novi sticks on the same DSUs and benches; all eight
invariants at zero violations. Back-test at a 2023-01-01 cutoff, 707 hidden producers: the count is right in total
(309 legs for 321 wells) and off by 20-30 % in a typical unit (the phase 2a spacing error); grid phase scores what a
random phase would (76 % against 80 % on the sideways test), which is what fails T1 and T4. Reviewed on 43 cards; the
rules decided from them are in the decision table. Nothing stored. **Gate 3a is closed.**

**Phase 3b outcome (2026-11-15, `docs/box_sticks/phase3b-2026-11-15/`).** The same generator over every 2026Q3 polygon
touched by a BOX extent: Delaware 5,072 DSUs, 46,002 sticks (54,168 legs, 441.5 MM ft) against 55,627 remaining Novi
sticks (492.6 MM ft) on the same DSUs and benches; Midland 4,385 DSUs, 34,045 sticks (37,688 legs, 350.4 MM ft) against
35,777 (365.4 MM ft). No errors, no invariant violations. TVD bust against the same-bench producers in the DSU: BOX
28 ft median Delaware / 22 ft Midland, Novi 100 / 62 ft (favours BOX by construction on the direct rung). Not compared:
110,978 Delaware and 50,029 Midland remaining Novi sticks on a bench whose BOX extent does not reach their DSU. Nothing
stored. Waiting on Michael's review (gate 3b).

**After 3b (2026-11-15 / 16, `docs/box_sticks/phase3c-2026-11-15/`, `phase3d-2026-11-16/`).** Four improvements were
measured behind off switches. Adopted by Michael 2026-11-16: Delaware WCXY on the full landing-depth chain, generator
`box_sticks_0.8_pilot`: WCXY sticks 454 -> 963, Delaware 46,002 -> 46,499 sticks (54,764 legs, 446.4 MM ft), Midland
unchanged, pilot 1,537 sticks, back-test T1 59.2 % with the same bars failing. Not adopted: dropping a carried depth
implausible against a direct bench (net -1,346 sticks, back-test slightly worse) and two landings per bench (no
effect; flagged units are already drilled out). Generator `box_sticks_0.9_pilot` adds the flag `dsu_drilled_across`
on the sticks of short polygons drilled across their line (Delaware 1,450 sticks in 284 DSUs, Midland 486 in 116);
sticks otherwise identical to 0.8. Nothing stored.

**Re-run on the post-cutover tags (2026-11-17, `docs/box_sticks/cutover-2026-11-17/`).** The tag switch went ON
2026-11-16; phases 0 through 3b were re-run on a pull of 2026-11-17 (1,313 wells re-tagged against the 11-14 pull),
generator 0.9 unchanged, no threshold reopened. Delaware 46,499 -> 46,690 sticks (54,964 legs, 448.3 MM ft), Midland
34,045 -> 33,791 (37,432 legs, 347.8 MM ft); 6.0 % of DSU x bench changed their count, most of it outside the DSUs
holding a re-tagged well. Candidate D still passes every envelope bar. Back-test: T1 59.7 %, T4 36.5 %, and the T5
thickness rung now fails its bar (1.56x against <= 1.5x; was 1.32x); the other verdicts are unchanged. These are the
numbers of record for gate 3b; the dated pre-cutover folders stay as what was reviewed. Nothing stored.

**Gate 3a:** pilot areas reviewed on cards. **Gate 3b:** basin-wide run compared with Novi per DSU and bench
(count, lateral footage, TVD bust).

## Phase 4 - Storage and identity (warehouse; explicit go for the DDL)

- `box.location` gains what D14 promised and the generator needs: source, generator version, DSU id, leg and
  turn geometry, target TVD + basis, spacing + basis, well type.
- Every stick stores how its depth was reached and how far to trust it (Michael, 2026-11-18): the rung (direct /
  thickness / bracket / offset), the anchor bench(es) of a carried depth, and the held-out expected error of that rung
  for the bench (median and P90, ft). The back-test ratios (carried rungs miss 1.2x to 1.7x their held-out median) go
  in the column comments, so a consumer can filter or weight by depth confidence. Flags travel with the stick:
  `two_landings_observed`, `second_level_nearby` (with the other level's TVD), `dsu_drilled_across`.
- New `box.location_set`: one versioned generation run per basin, one `is_record`, like `forecast_run`.
- Ids stay stable across regenerations through the existing overlap crosswalk idea (D73/D83) keyed on
  DSU + bench + slot. App-facing `stick_id` stays POSITIVE; the PDP `-(api10)` convention is untouched.
- Built alongside the Novi objects. Nothing is dropped or re-pointed in this phase.

**Gate 4a (2026-11-18, `docs/box_sticks/phase4a-2026-11-18/DESIGN.md`, read-only, nothing applied).** Draft DDL: new
`box.location_set`, `box.location_stick` (the stick per set), `box.location_set_dsu` / `_bench` / `_well` (what the
generator was given, so a set re-runs from the warehouse), six identity columns on `box.location`. Id rule
(`box/sticks/identity.py`): same DSU + bench, >= 50 % of the shorter stick alongside within 220 ft, 1:1; slot numbers never
reused. Measured: 0.9 on the 11-14 pull against 0.10 on the 11-17 pull (tag cutover between) carries 91.2 % of Delaware and
89.8 % of Midland sticks; 0.10 on the 11-17 pull against a fresh 11-18 pull carries 99.65 % and 98.96 %. Fresh run
(pull 2026-11-18): Delaware 46,709 sticks, Midland 33,829. Found: the generator drops the anchor benches and stores no
expected error on the direct rung (both needed by the columns above); four private narvi functions are imported, not
three; `scripts/box_pud_run.py` reads `box.location` by vintage with no source filter. Nine questions wait on Michael.

**Gate 4b (2026-11-18, `docs/box_sticks/phase4b-2026-11-18/FINDINGS.md`; nothing applied on live).** `sql/73_box_location_set.sql`,
`scripts/apply_box_location_set.py`, `scripts/box_sticks_run.py` (pull / generate / store), `box/sticks/store.py`, generator
`box_sticks_0.11` (anchors and direct-rung expected error on the stick; 0 of 80,538 sticks moved against 0.10 on identical
inputs), the `source = 'novi'` filter in `scripts/box_pud_run.py`, narvi PR #34 (public names; not merged, pin not bumped).
In the rehearsal container: sql/73 passes 31 of 31 checks; a store dry-run of each basin (pull 2026-11-18 17:28 UTC, Delaware
46,709 sticks, Midland 33,829) passes every identity check, and every DSU regenerated from the stored rows alone gives the
stored sticks (9,457 DSUs, 0 differences). Apply sql/73 (gate 4c) before this branch merges.

**Gate 4c (2026-11-18, Michael: "Go apply sql/73").** sql/73 **LIVE** on Supabase oilgas, committed 2026-11-18 about 18:08 UTC
(`python -m scripts.apply_box_location_set`, 31 of 31 checks; nightly idle, today's run green at 11:00 UTC). Verified from a
second read-only connection: the five new tables exist, commented and EMPTY; `box.location` still holds 252,925 rows, all
`source = 'novi'` (Delaware 167,070, Midland 85,855; ids 4 to 252,947), none with a NULL vintage; records still run 32
(Delaware) and run 30 (Midland), and their 166,561 + 85,849 `pud_forecast` rows still join `box.location`; the id sequence
stands at 10,000,006 (the rolled-back smoke used five numbers). Data dictionary regenerated (107 relations). Nothing stored:
no `box.location_set` row exists.

**Gate 4d, Delaware (2026-11-18, Michael: "go store Delaware first"; `docs/box_sticks/phase4d-2026-11-18/FINDINGS.md`).**
`box.location_set` **set 6, Delaware, NOT record**: generator `box_sticks_0.11` from `fb5c6c8`, pull 2026-11-18 18:26 UTC, tag
run 8; 46,709 sticks (54,985 legs, 448.5 MM ft), ids 10,046,716 to 10,093,424, 5,072 DSUs, 29,719 DSU x bench, 32,376 wells.
All 5,072 DSUs regenerated from the stored rows give the stored sticks. The first attempt rolled back on its own check: the
live session reads `float8` at 15 digits (`extra_float_digits = 0`); the verifier now reads exact floats. Midland is not
stored; nothing is record.

**Gate 4d, Midland (2026-11-18, Michael: "go store midland").** `box.location_set` **set 7, Midland, NOT record**, from the same
pull as set 6 (2026-11-18 18:26 UTC): 33,829 sticks (37,470 legs, 348.3 MM ft), ids 10,093,425 to 10,127,253, 4,385 DSUs,
19,835 DSU x bench, 30,004 wells; all 4,385 DSUs regenerate from the stored rows with 0 differences. Both basins are now stored
(80,538 sticks); **neither is record**. The record flip is its own go (decision Q4). Phase 4's remaining items: that flip, and
re-applying the `box.location_set` comment.

**sql/73 comment re-applied (2026-11-18, Michael: "go re-apply the sql/73 comment").** `python -m scripts.apply_box_location_set`
re-run on live about 19:29 UTC, 31 of 31 checks: the `box.location_set` comment now carries the `extra_float_digits = 1` note.
Data unchanged by identity (2 sets, 80,538 stick rows with an equal digest before and after, 333,463 locations; sets 6 and 7
still not record). Data dictionary regenerated. Left in phase 4: the record flip.

**Record flip (2026-11-18, Michael: "go flip the record for both basins").** `python -m scripts.box_sticks_run record --set-id N --go`
(new command; dry run first, 7 of 7 checks each): **set 6 is the Delaware record (46,709 sticks) and set 7 the Midland record
(33,829 sticks)**, generator `box_sticks_0.11`, pull 2026-11-18 18:26 UTC. No earlier record existed, so nothing was superseded;
no stick row changed (80,538 rows, digest equal before and after). The BOX forecast records are unchanged (run 32 Delaware,
run 30 Midland) and still stand on the Novi sticks: nothing reads `box.location_set` until phases 5 to 7. From here a
regenerated set carries its ids from these two. **Phase 4 is complete.**

## Phase 5 - Nightly reconciliation

New nightly step after `wells_enriched`, re-targeting the sql/68 co-extent overlap predicate at BOX locations
(+-150 ft corridor; >= 0.5 overlap = match, 0.3-0.5 = conflict (0.3 since 2026-11-18, see the decision table); same code within 500 ft TVD, or within 150 ft
whatever the tag).

| Status | Fired by | Counts as inventory |
|---|---|---|
| open | no match | yes |
| permitted | matching approved permit | yes, flagged |
| drilled | matching well at Spud / DUC or with a spud date | no |
| producing | matching well with first production | no |
| conflict | partial overlap or two matches | no, listed for review |

- **New Mexico / planned surveys:** a planned-survey or round-100 TVD is not depth evidence, so those wells
  match on plan-view overlap plus vendor formation family, recorded as `match_basis = 'planned'` and re-judged
  when the actual survey lands. No waiting on surveys.
- Status is recomputed every night, not latched (a cancelled permit or a wrong match heals), with a history
  log for audit.
- A newly drilled well also flags neighbouring locations that now sit inside the no-place envelope
  (`crowded`). Regenerating sticks and re-running forecasts stay periodic, explicit-go operations.
- Needs the geography expression indexes (sql/26 pattern) and a slot in `etl/db.py:_CURATED_MATVIEWS`.

**Gate 5a (2026-11-18, `docs/box_sticks/phase5a-2026-11-18/DESIGN.md`, read-only, nothing applied, nothing on the nightly
path).** Design: three ETL-owned tables (`curated.box_location_status`, `curated.box_location_status_log`, `meta.box_recon_run`)
written by a nightly hook that reads `box.*` and never writes it; `_CURATED_MATVIEWS` unchanged. The predicate is one SELECT
against the record sets (`predicate_draft.sql`): legs judged one by one, wells not yet producing and approved permits as
their own classes, the survey path for the 467 real U-turn wells, crowded from the set's stored envelope. On live it takes
47 s for both basins, uses `box_location_stick_geog_gix`, and gives the Python reference's status on 99.98 % (Delaware) and
100.00 % (Midland) of sticks. Bars were committed before scoring (`BARS.md`, `d2b06a0`). **Day 0 fails D1 and D2:** on sets 6
and 7 (pull 2026-11-18 18:26 UTC) 2.83 % of Delaware and 1.25 % of Midland sticks already match or conflict with a well and
3.85 % / 4.56 % are flagged crowded; with three generator rules mirrored (variant B, not the bar) 1.37 % / 1.26 % and
1.13 % / 1.53 %. **Back-test** (hindcast sets with the 353 not-yet-producing wells spudded after 2026-09-30 hidden; 570 test
wells, 283 of them in a DSU holding a stick of their family): one well takes out 0.83 (Delaware) and 1.11 (Midland) sticks
(B2 passes); **B1 fails in the Delaware** (67.5 % of wells take a stick out, bar 80 %; Midland 82.6 %); **B3 fails** (clean
match 17.8 % / 27.2 %, bar 40 %); **B4 fails** (conflicts 29.1 % / 34.3 % of sticks out, bar 15 %); **B5 fails** (6.41 % /
5.70 %, bar 0.5 %). Found in the generator, nothing changed: a well whose stored line starts at a stepped-out surface
location is never tested by the envelope (a stick placed on a producing well, at least 24 sticks); wells with a spud date
under status Inactive / P&A / Abandoned / Permit Approved are not read; real U-turn wells are read as their short
wellstick. 145 of the 570 newly spudded wells carry tag OTHER or none (Midland 41 %). Thirteen questions wait on Michael.

**Gate 5a, second measurement (2026-11-18, `docs/box_sticks/phase5a-2026-11-18/FINDINGS_2.md`; Michael, on the first: reconciling
against DUCs and permits is dubious, their tags and depths are still permit data).** Measured: no depth evidence on 39 % of
Texas and 57 % of New Mexico Spud wells against 0.6 % and 23 % of this year's producers; spud to first production is a median
196 days (NM) and 220 days (TX). With only producing wells counting, day 0 on sets 6 and 7 is 0.76 % matched or conflict and
0.53 % crowded (Delaware), 0.35 % and 0.49 % (Midland). Back-test as of 2026-01-01 (3,785 wells hidden; bars in `BARS_2.md`,
committed first; 326 Delaware and 289 Midland producing test wells in a DSU with a stick of their family): conflicts pass
(13.7 % / 11.5 % of sticks out, bar 15 %); Midland passes P1 (83.4 % of wells take a stick out) and P2 (1.27 sticks per well);
**the Delaware fails P1 (60.4 %) and P2 (0.74); P3 fails in both (clean match 22.7 % / 35.6 %, bar 40 %); P5 fails in both
(1.24 % / 0.80 %, bar 0.5 %).** Row spacing alone predicts 87 % / 34 % in the Midland (863 ft median) and 73 % / 28 % in the
Delaware (1,193 ft): a new well usually lands between two rows, so a stick-by-stick status is silent for about 1 new producer
in 6 in the Midland and 2 in 5 in the Delaware. Nothing decided; the drop trigger of 2026-11-12 stands until Michael changes it.

**Generator 0.12 (2026-11-18, Michael: "Yes, generator first"; `docs/box_sticks/phase5a-2026-11-18/FINDINGS_3.md`; files only,
NOT stored, sets 6 and 7 stay the records).** Three well-input fixes, no threshold or placement rule changed: a first segment
more than 15 degrees off the rest of a well's stored line (the surface step-out) is dropped; the 467 real U-turn wells are read
on their survey path as two legs; not-yet-producing wells now include Inactive / Active and Permit Approved with a spud date
(3,516 -> 5,020 wells). Pull 2026-11-18 22:37 UTC: Delaware 46,062 sticks (set 6: 46,709), Midland 33,138 (set 7: 33,829), 0
invariant violations. Day 0 on producing wells (bars in `BARS_3.md`, committed first): matched or conflict 0.63 % Delaware
(**fails** the 0.5 % bar; 0.76 % on set 6) and 0.22 % Midland (passes; 0.35 %); crowded 0.41 % and 0.39 % (pass). 168 of the 215
Delaware conflicts are a producer alongside 20 to 30 % of a stick: the generator places such a row (30 % rule, 2026-11-15) and
the predicate's sql/68 floor of 20 % calls it a conflict. Storing a 0.12 set is its own explicit go.

**Gate 5a, DSU-level signal (2026-11-18, `docs/box_sticks/phase5a-2026-11-18/FINDINGS_4.md`; files only).** With the two decisions
of the day (producing-only drop trigger, 30 % conflict floor) day 0 on generator 0.12 is 0.26 % matched or conflict (Delaware)
and 0.07 % (Midland); crowded is 0.63 % / 0.50 % and 0.40 % / 0.34 % with flat-ended corridors (side check; for 5b). Signal
tested: per DSU x bench, sticks minus new producers of that bench that are members of the DSU. Test: generator 0.12 as of
2026-01-01 against the same inputs regenerated with the 745 hidden producers put back; 156 touched DSU x bench per basin (450
-> 178 sticks Delaware, 534 -> 192 Midland; bars in `BARS_4.md`, committed first). **Delaware passes all four bars** (total
+0.6 %, mean abs error 0.57 against 0.69 for the stick status, exact on 55.8 %, fires for 72.3 % of new producers). **Midland
fails three** (total +31.8 %, error 0.72 against 0.62, exact on 49.4 %) and passes the fourth (84.4 %): a regeneration there
removes 1.16 sticks per new producer, not 1. The lower of the two estimates is within 8 % in both basins (seen after scoring;
a proposal for 5b). Size: 10.5 months of new producers make 312 DSU x bench stale (984 of about 83,000 sticks); doing nothing
overstates inventory by 0.57 % (Delaware) and 0.97 % (Midland), the stick status alone by 0.20 % and 0.17 %.

**Generator 0.12, store dry run on live (2026-11-19 00:18 to 00:31 UTC, Michael: "dry run the store"; rolled back;
`docs/box_sticks/phase5a-2026-11-18/STORE_DRY_RUN.md`).** Delaware: 44,788 of 46,062 sticks carry their id from set 6 (97.2 %),
1,274 new, 1,921 ids stop. Midland: 32,523 of 33,138 from set 7 (98.1 %), 615 new, 1,306 stop. All store checks ok; every DSU
regenerated from the stored rows gives the stored sticks (9,457 DSUs, 0 differences). Live unchanged by identity (2 sets, 80,538
stick rows, 333,463 locations, sets 6 and 7 still the records); the id sequence moved from 10,127,259 to 10,129,148 and set ids
12 and 13 are used up. **Nothing is stored.** A real store needs a fresh pull from a clean main after PR #258 merges, the 0.12
back-test on that pull, and its own go.

**Generator 0.12 stored (2026-11-19, Michael: "Go store both"; `docs/box_sticks/store-0.12-2026-11-19/FINDINGS.md`).**
`box.location_set` **set 16 (Delaware, 46,062 sticks) and set 17 (Midland, 33,138 sticks), NOT record**: generator `box_sticks_0.12`
from `0fb5cde`, pull 2026-11-19 01:00 UTC, tag run 8. Ids carried from the records: 44,788 from set 6 (97.2 %) and 32,523 from
set 7 (98.1 %); 1,274 + 615 new ids (10,131,038 to 10,132,926); 1,921 + 1,306 record ids stop. 10 of 10 store checks each; every
DSU regenerated from the stored rows gives the stored sticks (9,457 DSUs, 0 differences). Back-test stored with the sets: T1
59.3 %, T3 62.5 %, T4 37.5 %, thickness 1.56x and bracket 1.79x fail their bars as before; T2, the direct rung and the offset
rung pass. Verified from a second connection: sets 6 and 7 are still the records, 159,738 stick rows, 335,352 locations, forecast
records unchanged (run 32, run 30). **Record flip (2026-11-19 03:12 UTC, Michael: "Go flip both"): set 16 is the Delaware record and set 17 the Midland record;
sets 6 and 7 are superseded and kept.** Dry run then `--go`, 7 of 7 checks each; no stick row changed; forecast records unchanged.
A new set now carries its ids from 16 and 17. Gate 5b is authored against them.

**Gate 5b (2026-11-19, `docs/box_sticks/phase5b-2026-11-19/FINDINGS.md`; authored, NOTHING applied on live).** `sql/74_box_recon.sql`
(four ETL-owned tables: `meta.box_recon_run`, `curated.box_location_status`, `curated.box_location_status_log`,
`curated.box_dsu_bench_stale`), `etl/box_recon.py` (the nightly step, pure SQL, version `box_recon_1`, soft, a no-op until its
tables exist), `scripts/apply_box_recon.py` (33 checks), the hook in `etl/refresh.py` before `curated.codev_context`
(`_CURATED_MATVIEWS` not edited), 13 tests. Bars committed first (`BARS.md`); all eight pass. On sets 16 and 17, read-only on
live: the module's SQL gives the Python reference's status on 99.993 % (Delaware) and 100 % (Midland) of sticks; 131.6 s; day 0
is 0.20 % / 0.05 % producing or conflict and 0.15 % / 0.14 % crowded (inventory 45,903 of 46,062 and 33,073 of 33,138; 22
conflict sticks; 3 stale DSU x bench). The stale estimate against a regeneration: -7.3 % Delaware, +7.8 % Midland in total,
exact on 58 % / 64 % of DSU x bench. Rehearsal container: apply twice, night 1 (79,200 rows), a quiet night 2 (0 log rows), a
forced error (no raise, table untouched, `failed` row), the breaker; 24 of 24 checks. Gate 5c (the apply) is its own go, and
comes before this branch merges.

**Gate 5c (2026-11-19, `docs/box_sticks/phase5c-2026-11-19/apply.log`; APPLIED on live).** After the nightly finished (run 44510796253, green 12:42 UTC): `python -m scripts.apply_box_recon --dry-run` (33 of 33 checks, rolled back), then the apply (33 of 33, COMMITTED). Verified from a second connection: four tables, owner `postgres`, 0 rows each, 8 indexes, table comments, `analyst_ro` SELECT only; `box` unchanged by identity (4 sets, 159,738 stick rows, 335,352 locations, record sets 16 and 17, forecast records runs 30 and 32); `etl.box_recon.missing_tables` empty. Data dictionary regenerated. The tables stay empty until this branch merges and a nightly runs the hook: nothing on main calls it yet. Gate 5d (shadow) reports night by night from the first night after the merge.

**Gate 5d (started 2026-11-19, `docs/box_sticks/phase5d-2026-11-19`; shadow, nothing reads the tables).** PR #260 merged 13:04 UTC, after that day's nightly, so the first shadow night is the nightly of 2026-11-20. Bars S1 to S8 written and committed (`0ccbe78`) before any night. `scripts/box_recon_shadow.py` (read-only; the hook stays the only writer): `baseline`, `night`, `week`. Night 0 baseline (read-only pass, 136.2 s, nothing written): inventory 45,902 of 46,062 Delaware and 33,073 of 33,138 Midland; 88 sticks producing, 22 in conflict, 115 crowded; 3 stale DSU x bench; no well is the matching well of two sticks (0 of 88). sql/68's rule per well on the 218 wells behind those sticks: realizes a Novi stick 21, conflict 22, nothing 175 (reported, no bar). Nights are reported one by one.

**Gate 5:** a week of shadow nights; back-test on wells spudded since the 2026Q3 vintage.

## Phase 6 - BOX forecasts on BOX sticks

- `_UNIVERSE_SQL` reads the record `box.location_set`; `stick_id` constraints on `pud_forecast` /
  `location_source` relaxed; proximity TVD comes from the location, not `erebor_locations.tvd`.
- Planned spacing comes from the generator, replacing the D64 nearest-stick guess.
- In-extent becomes "DSU intersects the extent", replacing the 50 %-of-stick rule: a recorded decision.
- New record run per basin; econ is blank until Steven re-prices (stated choice, per the 11-04 precedent).
- The PUD / RES split disappears with Novi; BOX coverage classes (validated / provisional) carry that meaning.

## Phase 7 - App cutover (warehouse first, apply + verify live, then apps)

- **Warehouse:** split sql/22 into a PDP matview with no Novi dependency and a locations half fed by BOX
  sticks; sql/67 pad membership from the stored DSU id; sql/69 re-pointed.
- **erebor:** `box_locations.py`, tiles, Highgrade, `/pad`, workup sign checks.
- **narvi:** `_STICK_SQL`, `available_benches` (spacing suggestion + last-resort TVD tiers), `apply_novi_rep`.
- **deal-intake:** `novi_sticks`, gate 2 (keep-vs-generate), spacing chain steps 1-2.
- **anduin:** `warehouse_client/intel_forecast.py` representative sticks and the dossier overlay.

## Phase 8 - Retirement (last; every drop an explicit go)

- **Retire** (exist only to make Novi sticks usable): sql/19 `intel_formation_blueox`, sql/25 `net_new_pdp`,
  sql/30 `intel_pdp_support`, sql/35 representative sticks, sql/68 `reconciled_inventory`, sql/42 by-report
  readers, and their apply scripts.
- **Michael decides:** the Novi comparison record - sql/38 / sql/43 accuracy matviews, erebor's Accuracy tab,
  the single-well Novi curve, `box/hindcast_*`. Recommendation: freeze as an archive of the last vintage; it
  is the evidence that BOX beats Novi. Then `raw_intel`, sql/27-29/34 and the `intel_sf` ETL can stop loading.
- **Keep:** `raw_novi_intel.pads` + its loader, sql/20 and sql/23 (producer inputs), sql/48
  (`pdp_support_for_geom`, stick-agnostic), sql/26 indexes.
- **Residual Novi reliance:** the DSU polygons. Either keep a small quarterly shapefile refresh or freeze
  2026Q3; decide at Gate 0.
- Rewrite the `novi-quarterly-reload` skill (delete the stale copy under `Projects/.claude/skills`), update
  CLAUDE.md, sql/31 comments and the data dictionary.

## Open items to settle at the gates

- No-place envelope (phase 2b): which existing wells count for a stick (every producer, or only >= 12 months on as D115; DUCs); a stick beside a well with no depth evidence (planned survey, permit depth); WCA_1 / WCA_2 landings 75-150 ft apart count as one landing for the 400 ft test; re-measure the Midland D150 near end on placed geometry (phase 6).

- Polygon coverage gaps and overlaps (0b) - what happens inside an extent where Novi drew no DSU.
- Spacing bands by SIDE of an extent (Central Basin Platform edge vs the eastern shelf): distance to the nearest edge treats them alike. Not tested.
- Vertical arrangement inside a bench (BS2_S, Delaware WCC, BS3_C, LSSH): per-bench density with one landing surface puts every stick in one plane; the generator should alternate between landings where local wells show two. Ruthless 11: a single BS2_S surface lands near 10,700 ft, between the real landings (10,540 and 10,890 ft). Second row or second bench is a tag question. Pilot cards.
- (Closed 2026-11-15) "35,929 Midland Novi sticks with their midpoint outside every polygon": the `x`, `y` on the stick rows is a stick END, not the midpoint. On the geometry, 166 of 85,811 Midland and 90 of 166,636 Delaware sticks have their midpoint outside every polygon.
- WCXY: source for the Grisham fault complex line; whether WCXY becomes its own forecast pool; the tag
  policy seed for WCXY tags outside the extent.
- (Decided 2026-11-15, Michael) The 30 % alongside threshold stays: a row beside a well that runs along under 30 % of it is placed (DSU 10600).
- Open from gate 3a: a second landing by campaign inside one bench tag (rule 3); three private narvi functions are imported.
- (Stated 2026-11-16, Michael) BOX sticks stay on the Novi 2026Q3 DSU polygons. Short polygons that operators drill across with long straight laterals (402 U-turn DSUs, 1,933 BOX sticks at 0.7; `docs/box_sticks/phase3c-2026-11-15/`) are an artifact of that shapefile. Drawing our own DSUs is not undertaken now: with sparse development it is unclear which sections combine, and who holds the majority working interest per section is inferred, not known. Decided 2026-11-16: those sticks carry the flag `dsu_drilled_across` (400 DSUs, 1,936 sticks at 0.9).
- Open from the 3c trials: a carried depth implausible against a direct bench in the same DSU (637 DSU x bench; Lea 10809). Dropping the bench did not hold up; the repair belongs in the landing chain (prefer an anchor bench with wells in or next to the DSU).
- Novi rock quality (`rqs` / `rqt`) on PDP rows of sql/22: drop or keep.

## Verification

- Phase 0-2: read-only queries and reports; numbers stated with grain and filters.
- Generator: DB-free pytest (order invariant, stagger >= 300 ft, U-turn threshold, no stick inside the
  envelope, the gunbarrel golden table); pilot cards reviewed by Michael.
- Warehouse: `warehouse-change` skill per object - numbered sql, UNIQUE index, apply script with asserts,
  row-count identity (locations = record set), EXPLAIN shows the named geography index.
- Reconciliation: back-test against wells spudded after the 2026Q3 vintage; shadow nights before it drives counts.
- BOX: monthly volumes sum to stored EUR within 0.1 %; coverage counts by class vs the current records.
- Apps: each repo's suite green, plus a live load of the affected pages after the warehouse apply.
