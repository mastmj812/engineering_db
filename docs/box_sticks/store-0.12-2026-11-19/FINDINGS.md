# BOX sticks generator 0.12: stored as sets 16 and 17, and made the records

2026-11-19. Stored on Michael's "Go store both" (not record), then made the records on his "Go flip both": **set 16 is the
Delaware record and set 17 the Midland record**; sets 6 and 7 (generator 0.11) are superseded. Nothing reads
`box.location_set` yet; the forecast records (run 32 Delaware, run 30 Midland) are untouched.

Files here: `manifest.json` (the pull), `summary_<basin>.json` (the generation), `backtest_summary.json` (the back-test
stored in each set row).

## What was stored

Generator `box_sticks_0.12` from `0fb5cde` (main after PR #258), narvi `bfc7955` (pinned = installed), clean tree. Pull
2026-11-19 01:00:12 UTC, tag rule run 8 (still run 8 at the store).

| | Set 16, Delaware | Set 17, Midland |
|---|---|---|
| Stored (UTC) | 2026-11-19 02:34 | 2026-11-19 02:41 |
| Sticks / legs / completed lateral | 46,062 / 54,167 / 442.4 MM ft | 33,138 / 36,715 / 339.9 MM ft |
| DSUs / DSU x bench / wells read | 5,072 / 29,719 / 33,133 | 4,385 / 19,835 / 30,697 |
| Ids carried from the record set | 44,788 from set 6 (97.2 %) | 32,523 from set 7 (98.1 %) |
| New ids | 1,274 (10,131,038 to 10,132,311) | 615 (10,132,312 to 10,132,926) |
| Ids of the record set that stop | 1,921 | 1,306 |
| Store checks | 10 of 10 ok | 10 of 10 ok |
| Every DSU regenerated from the STORED rows | 5,072 DSUs, 0 differences | 4,385 DSUs, 0 differences |
| `is_record` | false | false |

Against the records: Delaware 46,709 -> 46,062 sticks (-647), Midland 33,829 -> 33,138 (-691). What 0.12 changed is in
`docs/box_sticks/phase5a-2026-11-18/FINDINGS_3.md`: the lateral instead of the whole stored well line, real U-turn wells on
their survey path, every drilled status read.

## Back-test stored with the sets (pilot areas, cutoff 2023-01-01, 720 hidden producers)

| Bar | 0.12 | Verdict | 0.10 / 0.11 on the 2026-11-17 pull |
|---|---|---|---|
| T1 wells on a slot, >= 60 % (>= 50 % each area) | 59.3 % (Lea 52.5, Ward 49.5, Glasscock 68.9) | **fails** | 59.7 % |
| T2 wells on a bench with no row, <= 10 % | 4.6 % | passes | passes |
| T3 legs within 1 of the wells drilled, >= 70 % of DSU x bench; ratio 0.85 to 1.20 | 62.5 %; 0.99 | **fails** | 63.2 % |
| T4 unused slots, <= 25 % | 37.5 % | **fails** | 36.5 % |
| T5 direct rung: median <= 75 ft, >= 80 % within 150 ft | 55.1 ft, 83.2 % | passes | passes |
| T5 thickness rung, <= 1.5 x its held-out median | 1.56 x | **fails** | 1.56 x |
| T5 bracket rung | 1.79 x | **fails** | 1.71 x |
| T5 offset rung | 1.10 x | passes | 1.16 x |

The bars stand as written. The same ones fail as before; 0.12 was not expected to move them (it changes which wells the
generator sees, not where rows hang).

## Live, verified from a second read-only connection (02:47 UTC)

| | Before (02:33 UTC) | After |
|---|---|---|
| `box.location_set` | 2 rows (6, 7; both records) | 4 rows: 6 and 7 still the records; 16 and 17 not record, `prev_set_id` 6 and 7 |
| `box.location_stick` | 80,538 | 159,738 (= 80,538 + 46,062 + 33,138) |
| `box.location` | 333,463 | 335,352 (= + 1,274 + 615); Novi rows unchanged (167,070 + 85,855) |
| BOX-stick locations last seen in the new sets / still at the old | | Delaware 46,062 / 1,921; Midland 33,138 / 1,306 |
| Forecast records | run 32 Delaware, run 30 Midland | the same |
| Location id sequence | 10,131,037 | 10,132,926 |

Set ids 8 to 15 were used up by rolled-back runs (the 4d first attempt and the dry runs); no row refers to them.

## Record flip (2026-11-19 03:12 UTC, Michael: "Go flip both")

`python -m scripts.box_sticks_run record --set-id 16|17`: dry run first (7 of 7 checks each, rolled back), then `--go`
(7 of 7 each). Verified from a second read-only connection:

| Set | Basin | Generator | `is_record` | `superseded_by` | Sticks |
|---|---|---|---|---|---|
| 6 | Delaware | 0.11 | false | 16 | 46,709 |
| 7 | Midland | 0.11 | false | 17 | 33,829 |
| **16** | Delaware | 0.12 | **true** | | 46,062 (54,167 legs; ids 10,046,716 to 10,132,311) |
| **17** | Midland | 0.12 | **true** | | 33,138 (36,715 legs; ids 10,093,425 to 10,132,926) |

No stick row changed (159,738 rows, 335,352 locations, as after the store). Exactly one record per basin. Forecast records
unchanged: run 32 (Delaware), run 30 (Midland). The 1,921 Delaware and 1,306 Midland location ids that stopped stay in
`box.location` with `last_seen_set` 6 / 7; sets 6 and 7 are kept, so anything keyed on them stays explainable. A new set now
carries its ids from sets 16 and 17.

## Next

- Gate 5b (nightly reconciliation, authoring) against sets 16 and 17, on a new branch cut from main after this PR merges.
