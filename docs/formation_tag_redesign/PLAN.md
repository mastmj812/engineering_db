# formation_blueox redesign — plan (DRAFT 2026-11-05, nothing built)

Status: proposal for Michael's review. Every step ends at a gate. Nothing is built, applied or written to Supabase
until the step before it is confirmed.

## 1. Why

`formation_blueox` drives forecasts, BOX pools, screens, reconciliation, scout labels and every app filter. The
2026-11-05 audit measured the tag (read-only; 56,890 clean producing horizontals; memory
`tag-consistency-audit-2026-11-05`):

- **Families hold.** Close pairs (<= 0.25 mi) on benches two or more apart are inverted by more than 50 ft in 0.5 %
  of cases.
- **Thin splits don't.** Local median gaps and inversion rates:
  - Delaware WCXY|WCA_1: 102 ft, 11 % of neighbourhoods inverted.
  - Delaware WCA_1|WCA_2: 128 ft, 9 % inverted.
  - Midland WCB_1|WCB_2: 171 ft, under 50 ft in 17 % of neighbourhoods.
- **Band disagreement** is 10.7 % in Delaware and 5.5 % in Midland at 1 mi.
- **The cause is systemic.** sql/16 maps a vendor string through the crosswalk with no depth check. Coarse Novi
  Wolfcamp values defer to Enverus ENVInterval, which fails the band test 14.4 % of the time against Novi's 4.8 %.
  sql/23 only fires on wells more than 600 ft off.
- **Fixing runs at human rate.** 438 ratified overrides compares with roughly 4,000 band disagreements. Nothing
  measures whether the tag is getting better, and Delaware inversions rise with vintage (4.2 % at or before 2014,
  10.1 % from 2024).
- **Sticks inherit it.** sql/19 (and sub-bench v2, PR #222, not applied) copy the sub-bench from neighbouring
  producers' tags. Producer noise therefore becomes stick noise.

The goal is a tag that is as accurate and representative as the data allows, says how sure it is, and is
measured every time it changes.

## 2. Design principles (proposed)

1. **Family from the vendor, position from depth.** The vendor name is reliable at family level (Bone Spring 2 vs
   3, Wolfcamp A vs B). Within a family, the sub-bench is a depth call, made the same way for every well.
2. **Name only what depth can resolve.** Where depth can't separate two benches locally, the tag says so (low
   confidence or the parent code; decision Q1). It doesn't pass a vendor guess off as a call.
3. **Evidence order:**
   1. ratified override (a human call);
   2. the geologist's surfaces where there is control (Delaware V5 grids);
   3. local producer bands, from clean wells only;
   4. the vendor sub-bench name;
   5. abstain.
4. **Clean depth only.** Use the lateral median survey TVD (`curated.well_lateral_survey`, sql/64) where it exists,
   `tvd_ft` otherwise. Planned surveys and round-100 TVDs are never evidence and never judged; they get the
   family plus the vendor sub-bench, flagged.
5. **One rule for producers and Novi sticks.** sql/19's k=1 copy and the unapplied v2 are replaced. v2's frozen
   held-out scoring method is reused for the stick side.
6. **Keep every layer.** The vendor raw string, the family, the depth call, its basis, its confidence and the final
   code are all kept side by side, so a change can always be traced and reverted.
7. **Measured, not asserted.** A stored scoreboard is re-scored on every rule change, override batch and vendor
   reload.

**Guard against "consistent but wrong".** A rule that relabels every well to match its neighbours scores
perfectly on self-consistency. The scoreboard therefore leads with independent evidence:
- agreement with the geologist's surfaces, where they are controlled;
- reproduction of the labelled set.

Self-consistency (band test, inversions) is reported, but never used as the only pass criterion.

## 3. Steps and gates

### Step 0 — Scoreboard and labelled set (read-only, repo code only)

- Move the audit script into the repo as a tested module, for example `box/tag_scoreboard.py`. It reproduces the
  2026-11-05 numbers.
- Score every bench pair by basin and county:
  - (a) geologist-grid agreement in controlled areas;
  - (b) labelled-set reproduction;
  - (c) band test and close-pair inversions at 0.5 and 1 mi;
  - (d) by vintage.
- The labelled set is the human calls:
  - the 15 #230 rule-V calls plus their 3 holds (which test abstention);
  - the 98 Delaware WCB-audit rows and the 336 Midland step-20a rows;
  - gold labels (Kesey 8H).
- Class-accepted rows (uncarded) are kept as a separate, weaker tier.
- Baseline report under `docs/formation_tag_redesign/baseline-<date>/`.
- **Hygiene found by the audit, listed for a decision, not done:**
  - 4 live override rows are no longer in the seed (reversed calls never reloaded).
  - `curated.well_neighbors` (sql/59) was never applied.
  - sql/30 `wca_delta_ft` still counts planned producers.

**Gate 0:** is this the scoreboard you'd judge the tag by? Answer Q1–Q5 below.

### Step 1 — Rule draft, frozen before scoring

Built offline against the scoreboard. Nothing in the warehouse changes.

**Family**
- Vendor family as today.
- Where Novi and Enverus disagree on family (the rule-V class: Novi says WOLFCAMP B, Enverus says WCA), depth
  decides between the two candidate families. The rule abstains when depth doesn't separate them.

**Position**
- Delaware, inside grid control: the interval between the geologist's surfaces.
- Delaware, no grid control (Pecos Wolfcamp, for one), and all of Midland: local robust bands from clean producers
  in the same family. The bands are fitted iteratively, so mis-tagged wells don't anchor them.
- Each call gets a margin in ft to the nearest boundary and a confidence (high / low / abstain).

**Sticks**
- Same rule at the stick midpoint TVD.
- A stick above both its family's local bands, or outside the grid interval, is flagged rather than forced into a
  bench. That is the Lea WCB case from #230.

**Freeze:** rule constants and pass criteria are committed before the first full score, as sub-bench v2 did.
Draft criteria, to set at the freeze:
- labelled-set reproduction >= today's, with the 3 holds abstaining;
- grid agreement up in every Delaware family;
- family-level inversions no worse;
- protected benches (WDFD / BRNT / MISS) untouched;
- low-confidence share reported by bench.

**Gate 1:** accept the frozen rule and criteria.

### Step 2 — Score once, plus blast radius

- Score against the frozen criteria.
- Churn: wells and sticks by bench, county and vintage.
- What it touches:
  - BOX record pools (Delaware run 32, Midland run 30): members moving in or out;
  - box_scout / erebor labels: about 1.7k Delaware labels moved under v2, to be re-measured;
  - recon re-matches (sql/68);
  - anduin saved curves whose filter is a moved bench;
  - narvi scenarios on moved benches.
- Review cards for a sample of each change class (strike sections, as before).

**Gate 2:** accept the rule, and choose landing timing (Q5).

### Step 3 — Warehouse design (DDL authored, not applied)

- New standalone matview (sql/NN), keyed by api10 and by stick_id, carrying:
  - `formation_family`;
  - `formation_blueox` (final code);
  - `formation_blueox_vendor`;
  - `position_basis` (override / grid / local_band / vendor / abstain);
  - `position_margin_ft`;
  - `formation_blueox_confidence`.
- It takes over sql/23's role, and sql/19's tier 2 for sticks. sql/16 keeps the vendor mapping.
- Stored scoreboard table, plus a nightly or on-change score.
- Cascade map and rebuild order (sql/16 dependents; the intel chain; sql/22 → sql/69 recreate); `_CURATED_MATVIEWS`
  order; sql/31 comments; data dictionary.
- Cross-repo consumers listed: anduin `warehouse_client`, erebor `box_locations`, narvi bench lookups, deal-intake
  `strat_column`, and the Blue Ox drop zone names (FINAL once shipped).

**Gate 3:** your explicit, specific go for the DDL and the apply window.

### Step 4 — Apply off-hours, verify live

- Apply through an `apply_*` script with asserts.
- Verify by row-count identity, EXPLAIN on the geography indexes, and the scoreboard re-scored live, matching
  step 2.

**Gate 4:** live state confirmed.

### Step 5 — Propagate

- BOX: either accept that the priced records stay on old benches until the next run, or follow with a BOX run and
  Steven re-pricing.
- Re-sync anduin headers; re-save narvi scenarios on moved benches.
- Raise the NM Wolfcamp B stick issue with Novi (#230 `sticks_anomalous.csv`).
- Note in the Blue Ox ledger if any emitted bench changes.

## 4. What this supersedes

- **Sub-bench v2 (PR #222, rule f138eb0, not applied).** Folded in as the stick side of step 1. Its held-out
  method and criteria are reused; its producer-tags-as-truth pool is replaced.
- **#230 rule-V overrides (15, ratified, not applied).** Become labelled-set rows. The new rule should reproduce
  them, so they never need applying on their own.
- **sql/23's 600-ft correction and sql/19's k=1 copy.** Replaced in step 3.
- **Existing 438 overrides.** Kept, and they still win. Each is scored, so one the rule now disagrees with comes up
  for review rather than being silently overridden.

## 5. Gate 0 decisions (Michael, 2026-11-05)

| Q | Decision |
|---|---|
| Q1 unresolvable splits | **(a)** keep the vendor sub-bench, `confidence = low`; the code vocabulary is unchanged |
| Q2 Midland | local producer bands only (no geologist surfaces needed first) |
| Q3 low confidence | flag only: the well keeps its vendor sub-bench and is shown and counted |
| Q4 overrides | an override always wins; the 4 stale rows are reloaded in the same apply |
| Q5 landing | off-cycle; priced records run 32 (Delaware) and run 30 (Midland) stay on their old benches until the next BOX run |

Step 0 is go.

### Questions as asked

- **Q1 — Unresolvable splits.** Where depth can't separate WCA_1 / WCA_2 (geologist rule C) or WCXY / WCA_1
  (102 ft locally):
  - **(a)** keep the vendor sub-bench with `confidence = low`. Codes are unchanged downstream. Recommended.
  - **(b)** collapse to a parent code (`WCA`). That changes the vocabulary in every app and in the Blue Ox drop.
  - **(c)** split on local bands anyway.

  Delaware BOX already pools WCA_1+WCA_2 as `WCA`, so (a) costs BOX nothing.
- **Q2 — Midland.** It has no geologist grids. Is position from local producer bands only acceptable, or do you
  want Midland surfaces from your geologist first?
- **Q3 — Low confidence.** Recommended: flag only, as at v2 gate 1 Q1. A low-confidence well keeps its vendor
  sub-bench, is shown, and is counted.
- **Q4 — Overrides.** Keep "override always wins", and reload the 4 stale rows in the same apply. Recommended.
- **Q5 — Landing vs BOX records.** Land off-cycle and accept that priced runs 32 / 30 sit on old benches until the
  next BOX run? Or bundle with a new BOX run plus Steven re-pricing?
