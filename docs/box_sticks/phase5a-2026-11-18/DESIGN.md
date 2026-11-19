# BOX sticks phase 5a: nightly reconciliation, design for review

2026-11-18. Read-only. **No SQL applied, nothing written to the warehouse, nothing added to the nightly.** Plan:
`docs/box_sticks_plan.md`, phase 5. Branch `claude/box-sticks-phase5a`, cut from main at `5023291` (PR #257 merged).

Files here: `BARS.md` (the bars, committed as `d2b06a0` before anything was scored), `predicate_draft.sql` (the predicate
as one read-only SELECT against `box.location_stick`), `ddl_draft.sql` (draft tables; not on the apply path),
`day0_*` and `backtest_*` (the measurement), `scripts/box_sticks_phase5a.py` (how it was produced).

## Summary

- **Design recommended:** three ETL-owned tables in `curated` / `meta` written by a nightly hook that reads `box.*` and never
  writes it; `_CURATED_MATVIEWS` unchanged; 47 s on live for both basins.
- **The draft SQL reproduces the Python reference** (99.98 % and 100.00 % of sticks) and uses the sql/73 geography index.
- **Day 0 is not quiet. D1 and D2 fail.** On the predicate as written 2.83 % of Delaware and 1.25 % of Midland record sticks
  already match or conflict with a well, and 3.85 % / 4.56 % are flagged crowded. Three causes are rule mismatches with
  the generator (variant B removes them: 1.37 % / 1.26 % and 1.13 % / 1.53 %); the rest are wells the generator never saw.
- **The back-test fails B3, B4 and B5 in both basins and B1 in the Delaware; B2 passes.** One newly spudded well takes about
  one stick out (0.83 Delaware, 1.11 Midland), but only 18 % / 27 % of wells land cleanly on a stick, and about 30 % of the
  sticks taken out are conflicts.
- **Four generator findings**, one of them a defect that places a stick on a producing well (section 7).
- Thirteen questions wait on you (section 8, Q0 to Q12).

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
5. **Crowded** from the record set's own stored envelope (section 8, Q5).

Stick status: conflict if any leg is in conflict; else producing / drilled if any leg is matched; else permitted; else open.

`predicate_draft.sql` is the predicate as the bars were written (variant A below). The three rules of variant B
(section 4c) are in the Python reference only; if you adopt them, 5b writes them into the SQL (two joins, to
`box.location_set_dsu.wca_class` and `box.location_set_bench.target_tvd_ft`, and one more corridor share).

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

## 5. Back-test: wells spudded since the 2026Q3 vintage

**Design.** A fresh pull (2026-11-18 19:59 UTC, tag run 8); every not-yet-producing well with a spud date after 2026-09-30
removed from what the generator reads (353 wells); generator `box_sticks_0.11` unchanged: Delaware 46,758 hindcast sticks,
Midland 33,950, 0 errors, 0 invariant violations. Files only, nothing stored. Then the wells with a spud date after
2026-09-30 are run through the predicate against the hindcast sticks.

**Test wells: 570** (Delaware 298, Midland 272; horizontals with a line; none produces yet). 354 have status Spud and
**216 still say Permit Approved** (Delaware 166, Midland 50): the spud date arrives before the status changes, which is
why "or with a spud date" is in the drilled rule. 341 of the 570 have no depth evidence (60 %).

**W** (the wells the bars are judged on: members of a DSU holding a hindcast stick of the well's formation family):
Delaware 191, Midland 92. The other 287:

| Not in W | Delaware | Midland |
|---|---|---|
| No stick of its family in its DSU | 97 | 173 |
| of which the family has no row in the DSU at all (no BOX extent there, or the tag is not a BOX bench) | 90 (WCD 27, OTHER 23, WCC 12, WDFD 10) | 167 (OTHER 110, WCC 24, BRNT 14, US 11) |
| of which every row was culled beside wells already there | 6 | 5 |
| Member of no DSU / no tag | 10 | 7 |

**145 of the 570 newly spudded wells carry tag OTHER or none (Midland 112 of 272 = 41 %).** The family rule has nothing
to match them on. 75 of them lie along at least half of a hindcast stick leg in plan view, over 137 sticks (median 2 benches
under one well, up to 10).

### 5a. The bars (predicate as written, variant A)

| Bar | Delaware | Midland | Verdict |
|---|---|---|---|
| B1 wells of W taking at least one stick out, >= 80 % | **67.5 %** (129 of 191) | 82.6 % (76 of 92) | **FAILS Delaware**, passes Midland |
| B2 sticks out per well of W, 0.8 to 1.3 | 0.83 (158 sticks) | 1.11 (102 sticks) | passes both |
| B3 wells of W with a clean match, >= 40 % | **17.8 %** (34) | **27.2 %** (25) | **FAILS both** |
| B4 conflict sticks / sticks out, <= 15 % | **29.1 %** (46 of 158) | **34.3 %** (35 of 102) | **FAILS both** |
| B5 hindcast sticks not open before the hidden wells are shown, <= 0.5 % | **6.41 %** (2,995) | **5.70 %** (1,936) | **FAILS both** (the same disagreement D1 + D2 measure) |

How the sticks went out (A): Delaware 36 drilled, 46 conflict, 76 crowded; Midland 25, 35, 42.

Variant B (reported, not the bar): B1 55.0 % / 81.5 %, B2 0.68 / 1.20, B3 15.2 % / 26.1 %, B4 30.2 % / 30.9 %,
B5 2.30 % / 2.69 %. B is quieter before the wells are shown and does not do better on the new wells; in the Delaware it
takes out fewer (129 sticks for 191 wells), under the 0.8 floor of B2.

Reported, no bar: 61 % (Delaware) and 65 % (Midland) of W match on the planned basis. U-turn sticks taken out as drilled:
Delaware 7 (1 with both legs), Midland 5 (0 with both). Wells matching sticks in two or more DSUs: 1.

### 5b. What the back-test says

1. **The count moves about right; the identity of the stick does not.** One well takes about one stick out (0.83 and
   1.11), but only 1 well in 5 (Delaware) or 1 in 4 (Midland) lands cleanly on a stick. The rest go out as crowded or as a
   conflict. That is the phase 3a result again (rows hang where a random phase would put them): a new well usually falls
   between two rows, not on one.
2. **Conflict is about 30 % of what goes out**, twice the bar. 81 conflict sticks came from seven weeks of drilling, about 50 a
   month to review, plus the day-0 backlog (section 4).
3. **Delaware loses a third of the wells entirely** (62 of 191 take nothing out). 36 of those 62 run within 150 ft of a
   same-family stick and still cover less than 20 % of it or miss the depth test; 37 of the 62 have no depth evidence.
   Not traced further here.
4. **Tags at spud time are the larger gap.** 41 % of new Midland wells are OTHER or untagged, and 257 of the 570 wells sit
   in a DSU that holds no row for their family.

None of this was tuned. The bars stand as written.

## 6. How it runs inside the nightly without ever failing it

- **Module** `etl/box_recon.py`, pure SQL through psycopg. The nightly installs `requirements.txt` only (no shapely, no
  narvi), so nothing from `box/sticks` or `scripts/` can be imported there. The Python reference stays a test and
  measurement tool; a golden table of synthetic pairs pins the SQL to it.
- **Hook**: one more key in the `hooks` dict that `etl/refresh.py` passes to `refresh_curated`, firing just before
  `curated.codev_context`. `etl/db.py` and `_CURATED_MATVIEWS` are not edited. `--no-box-recon` skips it, like `--no-tag-rule`.
- **Never raises.** Everything is inside try / except; a failure logs, writes a `failed` row to `meta.box_recon_run` if it
  can, and the nightly carries on with yesterday's status table.
- **No-op until its tables exist** (`to_regclass('curated.box_location_status') IS NULL` returns at once), and for a basin
  with no record set.
- **One transaction**: the predicate into a temp table, diff against the current table into the log, replace the current
  table, write the run row. `SET LOCAL statement_timeout = '600s'`; `SET LOCAL extra_float_digits = 1` is not needed (the
  hook compares inside the database and reads no float back).
- **Circuit breaker**: more than max(200, 1 % of record sticks) changed in one night with the same set ids and the same
  predicate version writes only the run row with `status = 'breaker'` (the tag rule's breaker).
- **Runtime**: 47 s for the SELECT on live today; the write is 80,538 rows.
- Nothing is added to the nightly path before gate 5c. In gate 5d the hook writes these tables and nothing reads them.

## 7. Found on the way (generator; reported, nothing changed)

These came out of the day-0 measurement. Each would change a stored set, so each is a regeneration question, not a phase 5
change.

1. **A well whose stored line starts at a stepped-out surface location is invisible to the envelope.** The generator's
   link measure takes a line's bearing from its first to its last point and drops pairs more than 15 degrees apart. Pad
   10662 (Delaware): BS1_S stick `10662-BS1_S-01` runs at 1.8 degrees; producing BS1_S well 4230137188 (12,065 ft, 34 ft
   deeper) has a first vertex about 2,500 ft east of its heel, so it reads 166.6 degrees, 15.2 degrees off, and is never
   tested. The stick sits on the well (98 % inside its 150 ft corridor). Same on pads 10875 AVA_0, 11073 WCA_1,
   10791 WCA_2. At least 22 Delaware and 2 Midland sticks.
2. **The generator reads Spud / DUC / Completed only.** Not read: wells with a spud date and no production under status
   Inactive (Midland 588, Delaware 283), P&A, Abandoned, and Permit Approved (Delaware 511, Midland 116). Day 0 under B:
   207 Delaware and 253 Midland sticks matched or in conflict with such a well, 228 and 303 crowded.
3. **Real U-turn wells are read as their short wellstick** (467 wells): 83 Delaware and 65 Midland sticks matched or in
   conflict, 98 and 89 crowded.
4. **A same-code well 150 to 500 ft above or below a stick** is outside the envelope's stacked rectangles, so the row is
   placed; the reconciliation's "same code within 500 ft" then calls it drilled (130 Delaware, 33 Midland). This is the
   per-bench density decision of 2026-11-13 meeting the envelope: by that decision the slot is taken.

Together these are about 1.3 % of each record set. Until a regeneration fixes 1 to 3, reconciliation is what removes them.

## 8. Open questions, with a recommendation each

**Q0. Go on to 5b with these failures stated?** *Recommend yes, with variant B's three rules and Q3's one-stick-per-DSU
rule.* The failing bars are about which stick a new well lands on (the generator's row phase) and about tags at spud time,
not about the machinery: the SQL is fast, reproduces the reference and moves the count by about one stick per well. What
you would be accepting: a clean `drilled` match is the minority outcome (about 1 well in 5 Delaware, 1 in 4 Midland);
`crowded` and `conflict` carry most of the count; the conflict queue runs at about 50 sticks a month. The alternative is
to hold phase 5 until a regeneration fixes the findings of section 7, then re-run this measurement.

**Q1. Where the status lives.** *Recommend B: `curated.box_location_status` + `_log` + `meta.box_recon_run`, written by a
hook.* Section 2. `_CURATED_MATVIEWS` unchanged; about 1 minute on the nightly.

**Q2. U-turns: drilled with one leg matched, or both?** *Recommend one leg takes the stick out of inventory, with
`legs_matched` stored (1 of 2 or 2 of 2).* Reason: the generator does not place an odd leg (decision of 2026-11-15), so the
other leg alone is not a location. Day 0 under B, U-turn sticks drilled or producing: Delaware 63 with one leg, 19 with
both; Midland 24 and 4.
- Pad 10816 BS2_S (Lea), stick 10052507: Bell Lake 24 Federal #004H on leg 1 (75 %) and #003H on leg 2 (100 %), two
  one-mile straight wells. Both legs, either rule.
- Pad 10703 BS2_S, stick 10050404: Cascade 29 Federal #221H, a real U-turn, covers both legs (83 % and 100 %) on its
  survey path. On its wellstick it would cover neither.
- Pad 10883 AVA_1, stick 10053920: Dragon 36 State #202H, a 6,207 ft straight producer, lies on leg 1 only. "Both legs"
  would leave this stick in inventory as a full U-turn.

**Q3. Short DSUs drilled across (`dsu_drilled_across`).** *Recommend each stick is judged on its own legs; one well may
take out sticks in two or more DSUs; no special rule.* Day 0 under B: 5 wells match sticks in two DSUs.
- Pads 20789 and 20819 WCB_2 (Midland): Brook N-18F 106H (22,218 ft) covers 100 % of the stick in 20789 and 65 % of the
  one in 20819. Both are drilled.
- Pads 23618 and 24250 LSSH (U-turn DSUs): RWT Brazos 9-28 Unit 1525LS (20,961 ft) covers one leg in each (70 %, 55 %).
  Both U-turn sticks are out, one leg each.
- Of the 1,955 sticks carrying the flag, 60 are drilled / producing / conflict on day 0 (Delaware 51 of 1,463; Midland 9
  of 492): the flag marks the risk, the predicate needs the well.

A related case the rule does not settle: **one well matching two sticks in the same DSU** (29 of 535 matching wells on
day 0). Hazel Inez 08 32 Federal Com #213H (Lea, 18,536 ft, no depth evidence) matches the WCB_1 and the WCA_2 stick of
pad 11827. *Recommend: a well takes out at most one stick per DSU: its own code first, then the higher overlap; the other
stick goes to conflict for a card.*

**Q4. What an "approved permit" is.** `well_status = 'Permit Approved'` (Novi `WellStatus`, else Enverus) with no spud date.
Dates exist (`raw_novi."Wells"."PermitApprovedDate"`, `"PermitExpirationDate"`), not carried into `curated.wells`.

| | New Mexico | Texas (both basins) |
|---|---|---|
| Approved permits today, horizontal, no production | 4,674 | 1,424 |
| of which carry a spud date (so they are "drilled" by the plan's rule) | 423 | 206 |
| approved more than 2 years ago | 878 (oldest 2002) | 0 (oldest 2024-11) |
| with a past expiration date | 0 | 0 |
| depth is a planned survey | 2,681 | 1 |
| `tvd_ft` is a round 100 | 475 | 936 |
| Permits approved in 2024: now drilled / cancelled / still approved | 1,808 / 577 / 625 of 3,010 = 60 / 19 / 21 % | 4,161 / 283 / 18 of 4,462 = 93 / 6 / 0.4 % |

A Texas permit is a reliable sign of a well within about a year and ages out by itself. A New Mexico permit is drilled
6 times in 10, never expires in the data, and 878 are stale. Almost every permit matches on the planned basis in both
states (NM planned surveys, TX round-100 depths). *Recommend: permits flag only, as decided, in both states; the status
row carries the permit's approval date so a reader can age New Mexico permits; no cut-off is built in.* Also for your
decision: 629 wells have status Permit Approved AND a spud date. By the plan's rule they are drilled (87 sticks on day 0).
*Recommend keep that:* in the back-test 216 of the 570 wells spudded since 2026-09-30 still say Permit Approved. 761 wells have status Permit Cancelled and a spud date: *recommend ignored.*

**Q5. `crowded`: which constants, from where.** *Recommend read them at run time from the record set itself:
`box.location_set.cfg -> 'generator'`.* Set 6: same landing 150 ft vertically and 400 ft sideways, 30 % alongside,
stacked [-250, -150] and [150, 350] ft within 300 ft. Set 7: stacked [-350, -150] and [150, 350]. **No constant is copied,
so no new cross-repo contract**; `scripts/box_sticks_phase2b.py` stays the one source and each set records what it used.
What is duplicated is the MEASURE (SQL corridor shares against the generator's sampled median distance). 5b pins it with a
golden table, and uses the median form (variant B rule 3), which cuts day-0 crowded from 3,341 to 1,048 sticks.
Second decision here: **does a crowded stick count as inventory?** *Recommend no once reconciliation drives counts (the
generator's own rule would not place it), stored as its own flag so both counts can be read.*

**Q6. Against sql/68 on the same wells.** They judge different sticks, so the comparison is per WELL: did the well realize a
Novi stick (sql/68), did it take out a BOX stick (nightly)? Today there is nothing to compare: sql/68 reads producing wells
only, `curated.reconciled_inventory` is not in the nightly list (0 drift rows), and no well has first production after
2026-09-30. *Recommend for the shadow week: the nightly report evaluates sql/68's SELECT read-only for the wells that
changed a BOX status that night and prints both answers side by side; `reconciled_inventory` itself is not refreshed or
touched.*

**Q7. A regenerated set.** Status is keyed on `location_id` and each row carries `set_id`. On the night after a record
flip: a carried id (about 99 % after one night, about 90 % across a tag cutover) keeps its history and is re-judged on its
new geometry; an id that stopped gets one last log row `stopped` with `cause = 'set_change'` and leaves the status table;
a new id gets a first row. Every log row of that night has `cause = 'set_change'`, and the circuit breaker does not fire
on a set change. A stick that was `drilled` usually stops at the regeneration, because the generator now culls its row;
the log then reads open, drilled, stopped. Nothing is rewritten in the log.

**Q8. Review surface for conflicts.** *Recommend cards, one per DSU holding a conflict: plan view of the DSU with the stick's
legs, the well line and its 150 ft corridor, overlap per leg; and a strike section across the laterals with the stick's
target TVD, the well's depth (or "no depth evidence"), and the neighbouring sticks of the bench above and below.* A verdict
is a row in a repo seed loaded to `ref.box_recon_override` (drilled / not this stick), never a hand edit. Day-0 queue under
B: 346 Delaware and 175 Midland conflict sticks. That is too many for a first round; the first cards should be the conflicts
caused by a NEW well each night, not the day-0 backlog (most of which a regeneration clears).

**Q9 (new). WCA_1 / WCA_2 in co-developed DSUs.** *Recommend variant B rule 1: no "any tag within 150 ft" match between
the two members there.* Pad 11756 (Eddy): WCA_1 stick 10066357 at 10,427 ft lies 95 % inside the corridor of Fuller 13 12
W1ED Federal Com #002H, a WCA_2 producer 89 ft deeper. The generator placed that stick on purpose. As written, 455
Delaware sticks go out on day 0 for this reason alone.

**Q10 (new). A well with no depth evidence.** *Recommend variant B rule 2: take it at the DSU's landing of its tagged bench
where that bench has a row; family only where it has none. Still `match_basis = 'planned'`, still re-judged when the
survey lands.* As written, 233 Delaware sticks go out on day 0 because a BS2_S or BS3_S permit-depth well matches the
carbonate stick under it.

**Q11 (new). The four generator findings of section 7.** Not for this phase. *Recommend they go on the list for the next
regeneration, and that the shadow week is read knowing about 1.3 % of each set is already out on night 1.*

**Q12 (new). A drilled well with tag OTHER or none and no depth evidence.** 65 of the 570 test wells; the family rule cannot
place them, and 41 % of new Midland wells are OTHER or untagged at spud. Pad example: in the hindcast, such wells lie along
137 sticks, a median of 2 stacked benches per well and up to 10. *Recommend: no status change; every stick the well runs
along (>= 0.5 of a leg in plan view) gets a flag `unassigned_well` with the api10, stays in inventory, and is re-judged the
night the well gets a tag or a survey. It needs one more column in the draft.*

## 9. How to check this

```powershell
python -m pytest -q tests/test_box_sticks_phase5a.py        # 8 tests, DB-free
python -m scripts.box_sticks_phase5a day0 --run runs\p5a_day0   # read-only; re-reads the record sets and today's wells
```

`day0_summary.json` holds the record-set ids, the wells pull time, the status counts of both variants and the SQL
timing. `backtest_wells_variant_a.csv` has one row per test well with what it did. Nothing here needs a write to check.

Next is gate 5b (authoring), on your answers to section 8. Nothing was applied, and nothing is on the nightly path.
