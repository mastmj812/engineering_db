# Blue Ox curve-drop contract — pending amendments log

Tracks every deviation between the workbooks we actually ship and the checked-in
contract (`docs/blue_ox_curve_drop_contract.md`, v1 2026-07-20) that still needs
S. Murray's acknowledgement / a loader change on the Blue Ox side. The contract
doc itself co-versions with their loader (`src/inputs_loader.py` /
`src/well_inventory.py`) and is only amended once the loader change is agreed —
until then, this file is the ledger.

Conventions: entries are dated by when the engineering side started emitting the
deviation. "Loader impact" states the minimum Blue Ox must do to load our
workbooks without error; anything marked *tolerated* means a lenient loader that
ignores unknown sheets/columns already copes.

---

## 1. Zone `reserve_category`: `RES` → `UPSIDE` — **awaiting loader ack**

- **Since:** 2026-07-22 (doc amendment merged, eng_db PR #10).
- **What:** zone-level `meta.reserve_category` value `RES` renamed `UPSIDE`
  (identical semantics — non-proven, carried unscheduled) so the zone label
  matches the per-well inventory `category` column and the narvi handoff
  vocabulary. anduin refuses `RES` at build; every drop since emits
  `PUD | UPSIDE`.
- **Loader impact:** accept `UPSIDE` wherever `RES` was accepted. **Required**
  — current drops fail a loader that still whitelists only `PUD|RES`.

## 2. Inventory `category` column + PDP display rows — **awaiting loader ack**

- **Since:** 2026-07-22 (anduin PR #14/#16; first shipped in the theCan drop).
- **What:** `inventory` gains a `category` column (`PDP | PUD | UPSIDE`), and
  **PDP rows are included** — existing in-unit producers (≥30 % co-extent
  membership) carried for downstream gunbarrel reconstruction. PDP rows are
  display-only: excluded from `gross_locations` and the Block B lateral means,
  exempt from the 3,000–25,000 ft lateral bounds. Unzoned PDP rows carry their
  bench code (e.g. `WCA_1`) in `area` — the one sanctioned case where `area`
  is not a zone-sheet name.
- **Loader impact:** count only `PUD`/`UPSIDE` rows toward `gross_locations`
  and lateral means; tolerate bench-code `area` values on `PDP` rows.
  **Required** for §3 gate 3 to keep passing.

## 3. Geologic risking disclosure — **awaiting loader ack** (eng_db PR #11)

- **Since:** 2026-07-24 (anduin PR #20; first risked drop: toucan re-export
  2026-07-27, `risk_mult` 0.8 on `toucan_bs2s`).
- **What:** per-stream geologic multipliers may be applied at the export
  boundary. Disclosure: `curve_params` gains a `risk_mult` column and risked
  fits carry `qi_basis = fitted_qi_risked`; manifest `risking` reads
  `geologic_multipliers_applied` (instead of the v1-mandated `unrisked`) when
  any zone is risked. Narrows Principle 3 to "no *commercial* / no
  *undeclared* risking". Analog/observed actuals are never risked.
- **Loader impact:** accept the second `risking` token; tolerate `risk_mult`
  in `curve_params`. **Required** for risked drops.

## 4. `zone_scenario_scope` manifest keys — **awaiting ack** (tolerated)

- **Since:** 2026-07-27 (anduin PR #22).
- **What:** when a zone's curve applies to a subset of the deal's DSUs
  (wide deals carrying e.g. WEST + EAST curves on the same bench), manifest
  Block A declares `zone_scenario_scope[<zone>]` rows listing the scoped
  narvi scenarios. Absent on unscoped zones (legacy output byte-identical).
- **Loader impact:** ignore unknown Block A keys — informational only.

## 5. Format questions from the theCan dry-run — **answers outstanding**

Open since 2026-07-21; drops currently use our chosen forms:
1. Date-string format in `analog_production.date` / manifest dates.
2. Manifest exception key name: `analog_history_exceptions`.
3. `ngl_basis` token: `derived_by_blue_ox_via_yield` (NGL-via-yield amendment
   itself is in the contract doc, agreed 2026-07-20).
4. `qi_units` strings (`bbl/d`, `Mcf/d`).

## 6. Inventory gunbarrel geometry columns + `dsu_meta` sheet — **NEW (this change, 2026-07-27)**

Requested by S. Murray so Blue Ox can rebuild per-DSU gunbarrels
(PDP/PUD/UPSIDE) from the drop alone.

- **What — `inventory` additive columns** (appended after the existing
  `area, category, producing_lateral_ft, drilled_lateral_ft, well_name`;
  existing names/order unchanged):

  | Column | Units | Meaning |
  |---|---|---|
  | `dsu_id` | — | DSU/scenario key (`<narvi deal_id>/<scenario_id>`); groups rows into one gunbarrel |
  | `bench` | — | `formation_blueox` bench code (finer than `area`: a zone may span benches) |
  | `landing_tvd_ft` | ft | landing TVD (gunbarrel Y, increasing down) |
  | `gunbarrel_offset_ft` | ft | signed cross-section offset of producing leg A (gunbarrel X) |
  | `gunbarrel_offset_b_ft` | ft | leg B offset — U-turn wells only, else blank |
  | `lateral_azimuth_deg` | deg | lateral azimuth of the well |
  | `heel_a_lon`, `heel_a_lat`, `toe_a_lon`, `toe_a_lat` | deg (WGS84) | producing-leg-A endpoints |
  | `heel_b_lon`, `heel_b_lat`, `toe_b_lon`, `toe_b_lat` | deg (WGS84) | leg-B endpoints — U-turn only, else blank |

- **What — new sheet `dsu_meta`** (one row per `dsu_id`):
  `dsu_id, azimuth_deg, origin_lon, origin_lat`. Reproducibility of the
  offsets: `gunbarrel_offset_ft` = signed projection of the leg midpoint onto
  the axis 90° clockwise of `azimuth_deg` (folded to [0°, 180°)) through the
  origin (parcel centroid), in feet. Plotting offset vs `landing_tvd_ft`
  reproduces the narvi gunbarrel; U-turn legs A/B join at one TVD.
- **Loader impact:** extra `inventory` columns *tolerated* (ignore unknowns);
  `dsu_meta` joins the reserved sheet-name list (must never collide with a
  zone name). Gunbarrel rebuild itself is new Blue Ox-side tooling.

## 7. `novi_comparison` + `novi_comparison_meta` sheets + manifest keys — **NEW (this change, 2026-07-27)**

Requested by S. Murray: every type curve ships with the median Novi
Intelligence ML forecast of a representative location set, so the TC-vs-Novi
comparison figure in the dossier is reproducible from the drop.

- **Selection rule** (single source of truth:
  `curated.intel_representative_sticks`, sql/35): per planned well —
  *generated* narvi sticks take the neighborhood set (same `formation_blueox`
  bench, novi_intel PUD/RES sticks within 1 mi stick-to-stick, intel lateral
  within ±25 % of the subject's completed lateral; n < 3 flagged, never
  silently widened); *curated* narvi sticks (locations that ARE novi_intel
  sticks) use exactly their own stick's forecast (`self`). PDP wells
  contribute nothing (no intel ML forecast exists for producers). Per zone,
  the representative sets of all captured wells are unioned (deduped) and the
  median is taken across sticks.
- **What — new sheet `novi_comparison`** (long): `area, month, oil_bbl,
  gas_mcf, water_bbl` — median monthly volumes **per 1,000 ft lateral**
  (same not-pre-multiplied discipline as the zone sheets), months 1–600,
  Novi aligned to IP (month 1 = first forecast month; the TC zone vectors
  remain peak-fit laid at the head per `qi_basis`). Zones with no eligible
  sticks have no rows here (declared in the meta sheet).
- **What — new sheet `novi_comparison_meta`** (one row per zone):
  `area, n_sticks, n_self, n_neighborhood, n_pud, n_res, n_wells_no_set,
  radius_m, lateral_tol, intel_vintage, low_n_flag, stale_vintage_flag,
  tc_risked`.
- **What — manifest Block A keys:** `novi_intel_vintage`,
  `novi_selection_radius_m`, `novi_selection_lateral_tol`,
  `novi_alignment` (= `novi_to_ip_tc_to_peak`), `novi_rate_to_volume_days`
  (day-count constant converting Novi per-day rates to monthly volumes).
- **Loader impact:** two new reserved sheet names + Block A keys —
  *tolerated* by a lenient loader; parsing them is new Blue Ox-side tooling.
  The Novi series is a **screen/benchmark only** — the zone-sheet vectors
  remain the sole economic input (no change to §3 gates).

## 8. Analog-sheet well coordinates — **NEW (2026-07-29)** (tolerated)

Added so Blue Ox can map the type-curve (analog) wells without a separate
header pull.

- **What:** every per-zone analog sheet (`<Zone> meta`, the
  `per_well_summary` block) gains six columns appended after the existing
  twelve (existing names/order unchanged):

  | Column | Units | Meaning |
  |---|---|---|
  | `surface_lat`, `surface_lon` | deg (WGS84) | surface hole location |
  | `heel_lat`, `heel_lon` | deg (WGS84) | landing point (start of lateral; wellstick SHL→LP→MP→BHL vertex 2) |
  | `toe_lat`, `toe_lon` | deg (WGS84) | bottomhole location |

  Values rounded to 6 decimals (~0.1 m). Wells with no wellstick geometry
  carry blank heel cells but keep surface/toe; wells with no geometry at all
  carry six blanks — blank cells inside the block are sanctioned, matching
  the §6 inventory-geometry precedent. Note the lat-before-lon ordering
  (differs from §6's `heel_a_lon, heel_a_lat` — that block's ordering was
  already shipped and stands).
- **Loader impact:** extra analog-sheet columns *tolerated* (ignore
  unknowns). The api-column-uniqueness rule (§1.4) is unaffected.

**2026-07-29 follow-up — mid-lateral heel defect + `wellstick_wkt` column**
(reported by S. Murray on the bro_time drop; anduin PR #31):

- **Defect:** the warehouse wellstick builder removes NULL vertices, so a
  well whose Novi landing point is missing carries a 3-vertex SHL→MP→BHL
  stick — the first drops' "heel" (stick vertex 2) was the **mid-lateral
  point** on those wells (2,443 of ~61.7k sticks; e.g. Echo B 2254H heel→toe
  5,132 ft vs 10,675 ft stated lateral). 110 further 2-vertex sticks put the
  toe at vertex 2.
- **Fix (values, not names):** `heel_lat`/`heel_lon` now emit only when the
  stick carries all 4 vertices (vertex 2 = landing point guaranteed);
  otherwise blank per the sanctioned-blanks rule. Do not trust heel columns
  from workbooks exported before 2026-07-29 (toucan, bro_time) — re-drops
  supersede them.
- **New column `wellstick_wkt`** appended after `toe_lon`: the full wellbore
  polyline as WKT `LINESTRING(lon lat, …)`, WGS84, 6 decimals — the
  authoritative geometry (identical to the anduin map render), faithful at
  any vertex count. Parse with `shapely.wkt.loads`; prefer it over the
  scalar pairs wherever the actual path matters. Blank when the well has no
  stick at all.
- **Loader impact:** *tolerated* (one more unknown column). Plotting
  guidance: use `wellstick_wkt` verbatim; heel→toe scalar segments are only
  valid where the heel cells are populated.

---

*Column/sheet/key names in §6–§8 are final once the first workbook carrying
them ships; any rename during implementation updates this file in the same
commit.*
