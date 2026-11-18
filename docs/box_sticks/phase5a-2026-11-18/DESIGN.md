# BOX sticks phase 5a: nightly reconciliation, design for review

2026-11-18. Read-only. **No SQL applied, nothing written to the warehouse, nothing added to the nightly.** Plan:
`docs/box_sticks_plan.md`, phase 5. Branch `claude/box-sticks-phase5a`, cut from main at `5023291` (PR #257 merged).

Files here: `BARS.md` (the bars, committed as `d2b06a0` before anything was scored), `predicate_draft.sql` (the predicate
as one read-only SELECT against `box.location_stick`), `ddl_draft.sql` (draft tables; not on the apply path),
`day0_*` and `backtest_*` (the measurement), `scripts/box_sticks_phase5a.py` (how it was produced).

## 1. What is live (read 2026-11-18 20:00 UTC)

| Check | State |
|---|---|
| PRs #252 to #257 | all MERGED into main; no PR open |
| sql/73 objects | `box.location_set`, `box.location_stick`, `box.location_set_dsu` / `_bench` / `_well` exist; `box.location` has the six identity columns |
| Record sets | **set 6 = Delaware, 46,709 sticks** (54,985 legs, 448.5 MM ft, 8,276 U-turns, ids 10,046,716 to 10,093,424); **set 7 = Midland, 33,829 sticks** (37,470 legs, 348.3 MM ft, 3,641 U-turns, ids 10,093,425 to 10,127,253). Both `is_record`, generator `box_sticks_0.11` from `fb5c6c8`, one pull of 2026-11-18 18:26:45 UTC, tag rule run 8 |
| BOX forecast records | run 32 (Delaware), run 30 (Midland), unchanged |
| `curated.reconciled_inventory` (sql/68, Novi sticks) | Delaware 165,084 remaining / 1,535 conflict / 3,596 phantom; Midland 85,174 / 663 / 1,345. **0 drift rows**: it reads producing wells only and has not been refreshed since the reload |
| Indexes | `box_location_stick_geog_gix` and `box_location_stick_geom_gix` exist |
| Vintage date | `curated.intel_vintage_date()` = 2026-09-30 |

## 2. Where the result lives and who writes it

**Recommendation: three ETL-owned tables written by a nightly hook, reading `box.*` and never writing it.**
`curated.box_location_status` (today, one row per record stick), `curated.box_location_status_log` (one row per location
per night it changed), `meta.box_recon_run` (one row per night). Draft in `ddl_draft.sql`.

| | A. Matview in `curated` | **B. Tables + nightly hook (recommended)** |
|---|---|---|
| Writes schema `box` | no | no. The hook reads `box.location_set` / `_stick` / `_dsu` / `_bench` |
| History log | not possible in a matview; needs a second writer anyway | the hook diffs tonight against last night and writes the log in the same transaction |
| Never fails the nightly | `refresh_curated` re-raises any error but a missing optional matview, so a bad night fails the run unless `etl/db.py` is changed | the hook catches everything and records a `failed` run row (the `etl/tag_rule.nightly_hook` pattern, sql/72) |
| No-op until its tables exist | a matview in the list must exist or the nightly fails | `to_regclass` check; also a no-op when a basin has no record set |
| `etl/db.py:_CURATED_MATVIEWS` | one more entry | **unchanged**. One line in `etl/refresh.py` (the hooks dict) and a new module `etl/box_recon.py` |
| Dependency on `curated.wells` | yes: every sql/04 CASCADE would drop it, one more victim to re-create (the sql/69 problem) | none; plain tables |
| Recomputed, not latched | yes | yes: the status table is rebuilt from scratch each night; only `status_since` is carried |
| Circuit breaker | no | yes: a night that changes more than max(200, 1 %) of locations with no set change writes the run row only |
| Nightly runtime | the same SELECT | **47 s** measured on the live session pooler for both basins (80,538 sticks, 85,035 wells), plus the write of 80,538 rows. The curated refresh today takes about 16 min without `production_forecast` |

The plan said "a slot in `_CURATED_MATVIEWS`". B replaces that with a hook slot: the hook fires just before
`curated.codev_context`, the first refresh after everything the predicate reads (`curated.wells`,
`curated.well_lateral_survey`, `curated.formation_blueox`, `curated.formation_blueox_tvd`, through `wells_enriched`).
The hook sets `SET LOCAL statement_timeout = '600s'` so it cannot wedge the run.

## 3. The predicate (`predicate_draft.sql`)

Grain: stick LEG against well. sql/68's rule with five additions.

1. **Legs.** `ST_Dump(legs_geom)`; overlap = length of the leg inside the well's 46 m (150 ft) corridor / length of the leg.
   One well at >= 0.5 = the leg is matched; the best in [0.2, 0.5), or two wells at >= 0.5, = conflict.
2. **Well classes.** producing (first production date); drilled (no first production; status Spud / DUC / Completed or a
   spud date; never Permit Cancelled); permit (Permit Approved, no spud date). Permits are judged apart and only flag.
3. **Depth evidence** as the generator defines it: never a planned survey; survey lateral median, else `tvd_ft` unless it is a
   round 100; at least 4,000 ft. With evidence: same code within 500 ft, or within 150 ft whatever the tag. Without:
   formation family, `match_basis = 'planned'`.
4. **Real U-turn wells use the survey path.** 467 wells are marked `is_uturn` (Delaware 333, Midland 134). Their
   `wellstick_geom` averages 2,859 / 2,989 ft against a 9,273 / 9,954 ft lateral: it is a short line across the two legs.
   `curated.well_lateral_survey.lateral_geom` (11,469 / 12,358 ft with the turn) is used instead.
5. **Crowded** from the record set's own stored envelope (section 5, question 5).

Stick status: conflict if any leg is in conflict; else producing / drilled if any leg is matched; else permitted; else open.

Pair search: `ST_DWithin(legs_geom::geography, well line::geography, 400 ft)`, served by `box_location_stick_geog_gix`
(sql/73). EXPLAIN on live names that index. No new spatial index is needed: the wells drive the loop.

## 4. Day 0: the record sets against today's wells

Grain: sticks of sets 6 and 7 (pull 2026-11-18 18:26 UTC) against 85,035 horizontals read 2026-11-18 20:00 UTC (Delaware
31,905 producing / 3,236 drilled / 4,661 permits; Midland 29,032 / 2,459 / 806; 12,936 ignored, of which 12,800 cancelled
permits).

### 4a. The bars, on the predicate as written (variant A)

| Bar | Delaware (set 6) | Midland (set 7) | Verdict |
|---|---|---|---|
| D1 drilled + producing + conflict <= 0.5 % of sticks | 1,321 of 46,709 = **2.83 %** (216 drilled, 569 producing, 536 conflict) | 423 of 33,829 = **1.25 %** (205, 44, 174) | **FAILS both** |
| D2 crowded flag <= 0.5 % | 1,799 = **3.85 %** | 1,542 = **4.56 %** | **FAILS both** |
| D3 draft SQL = Python reference, >= 99.5 % of sticks | 99.98 % status, 99.96 % crowded | 100.00 % status, 99.95 % crowded | passes |
| D4 SQL wall time <= 300 s, stick index in the plan | 46.8 s for both basins; `box_location_stick_geog_gix` | | passes |

Reported: sticks flagged permitted: Delaware NM 740 (572 on the planned basis), Delaware TX 31 (26), Midland 76 (52).

### 4b. Why day 0 is not quiet

The record sets were generated knowing these wells, so every day-0 match is a place where the predicate and the generator
disagree. Five causes, all traced to a rule or a defect:

| Cause | Delaware sticks | Midland sticks | What it is |
|---|---|---|---|
| WCA_1 against WCA_2 in a co-developed DSU | 455 matched or conflict (327 producing, 125 conflict, 3 drilled); 391 crowded | 0 | The generator runs no envelope test between the two members there (decision of 2026-11-15). sql/68's "within 150 ft whatever the tag" calls the same pair one bench |
| Well with no depth evidence, lithology sibling | 233 matched or conflict (mostly BS2_C against BS2_S, BS3_C against BS3_S); 354 crowded | 3; 18 crowded | The family rule matches a BS3_S permit-depth well to the BS3_C stick under it. The generator takes such a well at the DSU's landing of its tagged bench |
| Crowded: corridor form against the generator's measure | 661 crowded | 1,092 crowded | The generator's sideways gap is the MEDIAN distance over the shared length. "30 % of the leg within the limit" is looser: rows the generator placed at 305 to 380 ft from a stacked parent read as inside 300 ft |
| Wells the generator never read | 207 matched or conflict, 228 crowded | 253, 303 | Status Inactive / P&A / Abandoned with a spud date and no production (Midland Inactive: 588 wells, 365 spudded in 2026), and Permit Approved with a spud date. The generator reads Spud / DUC / Completed only |
| Real U-turn wells | 83, 98 crowded | 65, 89 | The generator read the short wellstick, so it never saw the legs |

### 4c. Variant B: the same predicate with three generator rules mirrored

Not what the bars were written on; reported next to them. B = A with: (1) no "any tag within 150 ft" match and no
same-landing envelope between WCA_1 and WCA_2 in a DSU the set recorded as co-developed (1,227 Delaware DSUs); (2) a well
with no depth evidence is taken at the DSU's landing of its tagged bench where that bench kept a row, family only
otherwise; (3) crowded = at least half of the alongside length inside the sideways limit, alongside >= 30 %.

| Status (sticks) | Delaware (set 6) | Midland (set 7) |
|---|---|---|
| open | 45,397 | 33,325 |
| permitted | 671 | 79 |
| drilled | 162 | 206 |
| producing | 133 | 44 |
| conflict | 346 | 175 |
| drilled + producing + conflict | 641 = **1.37 %** | 425 = **1.26 %** |
| crowded flag (on open / permitted) | 529 = **1.13 %** | 519 = **1.53 %** |

Still above 0.5 %, so **D1 and D2 fail under B too**. What is left is mostly real:

| What is left under B | Delaware matched or conflict / crowded | Midland |
|---|---|---|
| Wells the generator never read | 207 / 228 | 253 / 303 |
| Real U-turn wells | 83 / 98 | 65 / 89 |
| Same code, 150 to 500 ft apart vertically (a second landing in the stick's slot) | 130 / 4 | 33 / 1 |
| Well without depth evidence | 33 / 27 | 1 / 3 |
| Other | 188 / 172 | 73 / 123 |

"Other" includes a generator defect found here (section 7, finding 1): at least 22 Delaware and 2 Midland sticks sit on a
producing well of the same code at the same depth.

## 5. Back-test and open questions

BACKTEST_PLACEHOLDER
