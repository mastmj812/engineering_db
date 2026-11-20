# BOX sticks generator 0.13: stored as set 21 (Delaware), NOT record

2026-11-20. Stored on Michael's "Go pull and store". **Set 16 is still the Delaware record and set 17 the Midland record.**
Nothing reads set 21; the nightly reconciliation still judges sets 16 and 17; the forecast records (run 32 Delaware, run 30
Midland) are untouched. The record flip is a separate go.

Files here: `manifest.json` (the pull), `summary_delaware.json` (the generation), `backtest_summary.json` (the back-test
stored in the set row), `store.log`.

## What was stored

Generator `box_sticks_0.13`, generated from `6404ffd` (branch `claude/box-sticks-grid-rung`, PR #268, not yet merged; clean
tree), narvi `bfc7955` (pinned = installed). Pull 2026-11-20 20:45:19 UTC, the first on the Novi v4 source; tag rule run 12
(run 8 for sets 16 and 17; still run 12 at the store).

| | Set 21, Delaware |
|---|---|
| Sticks / legs / completed lateral | 46,132 / 54,257 / 443.1 MM ft |
| DSUs / DSU x bench / wells read | 5,072 / 29,719 / 33,166 |
| Ids carried from the record (set 16) | 44,333 of 46,062 (96.2 %) |
| New ids | 1,799 (10,136,770 to 10,138,568) |
| Ids of set 16 that stop | 1,729 |
| Store checks | 10 of 10 ok |
| Every DSU regenerated from the STORED rows | 5,072 DSUs, 0 differences |
| `is_record` | false |

Sticks by landing rung:

| Rung | Set 16 (0.12) | Set 21 (0.13) |
|---|---|---|
| direct | 16,471 | 16,523 |
| thickness | 19,517 | 19,248 |
| bracket | 2,577 | 2,513 |
| offset | 7,497 | 1,946 |
| grid | 0 | 5,902 |

Flags on set 21: `grid_bounded` 464 sticks, `outside_grid` 426, `pinned` 11,640, `second_level_nearby` 3,517,
`dsu_drilled_across` 1,172, `two_landings_observed` 222.

**Two causes are mixed in the difference to set 16.** On set 16's own inputs the grid change alone stopped 332 sticks and
started 333 (`docs/box_sticks/grid-rung-2026-11-20/FINDINGS.md`). This store stops 1,729 and starts 1,799, so most of the
turnover comes from the inputs having moved since the 11-19 pull: the v4 source and four tag-rule runs. It was not broken
down further.

## Two defects the rehearsals found (both fixed before the store)

The store was rehearsed three times in a transaction that rolls back. The first two failed, as rehearsals should:

1. **A new stick was given a slot number an older location already held** (`box_location_slot_uq`, DSU 10791 WCB_2 slot 2).
   Ids were carried from the previous set only; a location that stopped two sets earlier keeps its number. Third stored
   generation, first time it could happen. Fix `99b4539`: a new stick starts above every number ever issued for its DSU
   and bench. Test added.
2. **Regenerating from the stored rows lost the grid flags** (890 sticks, flags only). The note is a stick flag, not a
   bench column. Fix `c52db1b`: the rebuild reads it back from the bench's stored sticks. Test added.

The set was generated at `6404ffd` and stored with the store path as of `c52db1b`; neither fix touches what the generator
places. The third rehearsal passed 10 of 10; the store then passed the same 10.

## Back-test stored with the set (pilot areas, cutoff 2023-01-01, 718 hidden producers)

| Bar | 0.13 | Verdict | 0.12 (set 16) |
|---|---|---|---|
| T1 wells on a slot, >= 60 % (>= 50 % each area) | 59.9 % (Lea 53.2, Ward 52.1, Glasscock 68.9) | **fails** by 0.1 point | 59.3 % |
| T2 wells on a bench with no row, <= 10 % | 4.2 % | passes | 4.6 % |
| T3 legs within 1 of the wells drilled, >= 70 %; ratio 0.85 to 1.20 | 62.5 %; 0.99 | **fails** | 62.5 % |
| T4 unused slots, <= 25 % | 36.6 % | **fails** | 37.5 % |
| T5 direct rung: median <= 75 ft, >= 80 % within 150 ft | 55.4 ft, 82.5 % | passes | 55.1 ft, 83.2 % |
| T5 grid rung, <= 1.5 x its held-out median | 0.46 x (33.6 ft on 23 pairs, against 72.4 ft) | passes | n/a |
| T5 offset rung | 1.33 x (19 pairs) | passes | 1.10 x |
| T5 thickness rung | 1.53 x | **fails** | 1.56 x |
| T5 bracket rung | 1.93 x | **fails** | 1.79 x |

The bars stand as written and the same ones fail as before. The grid rung's first back-test reading is 33.6 ft median on 23
well and stick pairs.

## Live, verified from a second read-only connection (after the store)

| | Before | After |
|---|---|---|
| `box.location_set` | 4 rows (6, 7, 16, 17) | 5 rows: 16 and 17 still the records; 21 not record, `prev_set_id` 16 |
| `box.location_stick` | 159,738 | 205,870 (= 159,738 + 46,132) |
| `box.location` | 335,352 | 337,151 (= + 1,799); Novi rows unchanged (252,925) |
| Delaware BOX-stick locations by last set seen | | set 21: 46,132; set 16: 1,729; set 6: 1,921 |
| Forecast records | run 32 Delaware, run 30 Midland | the same |
| Nightly reconciliation | sets 16 and 17, 79,200 status rows | the same (it reads record sets only) |
| Location id sequence | 10,132,926 | 10,138,568 |

Set ids 18 to 20 and location ids 10,132,927 to 10,136,769 were used up by the rolled-back rehearsals; no row refers to
them.

## Not done

- No record flip. Set 21 changes nothing downstream until it is made the record.
- PR #268 is not merged; the set's `code_sha` is a commit of that branch, which stays in history when the PR merges (merge
  commit, not squash).
- The Midland needs no 0.13 set (identical on the same inputs).

## Record flip (2026-11-20 22:15 UTC, Michael: "Go flip set 21")

Dry run first (7 of 7 checks, rolled back), then the flip (the same 7, committed; `record_flip.log`). Verified from a second
read-only connection:

| | After the flip |
|---|---|
| Delaware record | set 21 (`box_sticks_0.13`); set 16 superseded by 21, kept |
| Midland record | set 17, unchanged |
| Record sticks | 79,270 (46,132 + 33,138) |
| Stick and location rows | 205,870 and 337,151, unchanged: no stick row was touched |
| Forecast records | runs 30 and 32, unchanged |
| Nightly reconciliation tables | still the 79,200 rows of sets 16 and 17 until the next nightly, which re-judges on set 21 and logs it as a set change |

The title of this file is from the store; since the flip, set 21 IS the Delaware record.
