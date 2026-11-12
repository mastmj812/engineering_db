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
| WCA_1 / WCA_2 depth (2026-11-12, after phase 1c) | Both take the full landing-depth chain (supersedes "direct control only" for these two; WCXY stays direct-only until it has its own extent) |
| WCA_1 / WCA_2 under the floor (2026-11-12) | Where the two landings are closer than the minimum separation (75 ft) or out of order in a DSU, that DSU gets ONE WCA landing. Detail to settle in the generator: it takes the code and depth of the member with the more trusted depth there |
| Stack reconciliation (2026-11-12) | Benches are estimated independently, then each conflicting adjacent pair in a DSU is reconciled: the less trusted depth gives way (carried before direct; among carried, the higher held-out error). It moves to the minimum separation if that stays inside its own error band; otherwise that bench gets no stick in that DSU, with the reason recorded |
| Evidence screen (2026-11-12) | Two-part, replacing a fixed cutoff. **Likely mis-tag**: a well closer to another bench's direct surface than to its own and more than max(150 ft, half the local gap) off its own is removed from its tagged bench's evidence and listed for formation-tag review; the surface builder never re-tags. **Bad depth**: more than 300 ft off its own surface and not a mis-tag is dropped. Live tags: 1,499 + 377 wells |
| No-place envelope | Calibrated from where operators actually drilled children vs parents; gate before freezing |
| Drop trigger | Spud / DUC removes a location from undrilled counts; an approved permit only flags |

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

**Gate 3a:** pilot areas reviewed on cards. **Gate 3b:** basin-wide run compared with Novi per DSU and bench
(count, lateral footage, TVD bust).

## Phase 4 - Storage and identity (warehouse; explicit go for the DDL)

- `box.location` gains what D14 promised and the generator needs: source, generator version, DSU id, leg and
  turn geometry, target TVD + basis, spacing + basis, well type.
- New `box.location_set`: one versioned generation run per basin, one `is_record`, like `forecast_run`.
- Ids stay stable across regenerations through the existing overlap crosswalk idea (D73/D83) keyed on
  DSU + bench + slot. App-facing `stick_id` stays POSITIVE; the PDP `-(api10)` convention is untouched.
- Built alongside the Novi objects. Nothing is dropped or re-pointed in this phase.

## Phase 5 - Nightly reconciliation

New nightly step after `wells_enriched`, re-targeting the sql/68 co-extent overlap predicate at BOX locations
(+-150 ft corridor; >= 0.5 overlap = match, 0.2-0.5 = conflict; same code within 500 ft TVD, or within 150 ft
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

- Polygon coverage gaps and overlaps (0b) - what happens inside an extent where Novi drew no DSU.
- Tight-spacing cap and whether the 4 WPS floor is 1,320 or 1,540 ft.
- U-turn leg separation where bench spacing is under 990 ft.
- Lithology-pair handling (BS2_C/S, BS3_C/S).
- WCXY: source for the Grisham fault complex line; whether WCXY becomes its own forecast pool; the tag
  policy seed for WCXY tags outside the extent.
- How narvi's engine is made importable in `engineering_db` CI (Python 3.12, no narvi today).
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
