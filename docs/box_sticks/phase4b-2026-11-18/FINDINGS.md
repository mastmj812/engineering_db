# BOX sticks phase 4b: authoring and dry-run

2026-11-18. **Nothing applied to the warehouse; no `box.*` or `narvi.*` write on live.** Every write below went to the
throwaway rehearsal container (`scripts.box_rehearsal`, PostGIS on localhost:5437, seeded read-only from live `box`).
Decisions of gate 4a (all nine recommendations accepted, Michael 2026-11-18) are in the plan's decision table.

## What exists

| File | What it is |
|---|---|
| `sql/73_box_location_set.sql` | The DDL: `box.location_set`, six identity columns on `box.location`, `box.location_stick`, `box.location_set_dsu` / `_bench` / `_well`, id sequence restart at 10,000,001, comments. Additive, idempotent, no matview, no CASCADE. sql/73 was the next free number on main, in open PRs (none) and on every remote branch |
| `scripts/apply_box_location_set.py` | Applies sql/73 twice, validates by identity, smokes inside a rolled-back savepoint, commits only if every check passes. `--dry-run` rolls the whole thing back |
| `scripts/box_sticks_run.py` | `pull` (new run dir, key-ordered frames, manifest with pull time at the DB, tag run, digests, file hashes), `generate` (any DSU error fails the run), `store` (one transaction; dry run unless `--go`) |
| `box/sticks/store.py` | Generator output and inputs as table rows, and the way back (stored rows -> the DSU the generator was given) |
| `box/sticks/identity.py` | The id crosswalk (gate 4a) |
| `box/sticks/core.py`, `reads.py` | Generator `box_sticks_0.11`: anchor set(s) and the direct-rung expected error carried onto the stick |
| `scripts/box_pud_run.py` | The Novi store path filters `source = 'novi'` |
| `scripts/gen_data_dictionary.py` | Consumer lines for the five new tables |
| `tests/test_box_sticks_identity.py`, `tests/test_box_sticks_store.py` | 20 tests, DB-free |
| narvi PR #34 | Public names for the four engine functions (aliases; narvi suite 149 passed). Not merged |

BOX comments live in their own sql file (sql/31 holds none for schema `box`), so the comments are in sql/73.

## Checks run

**Generator 0.11 against 0.10 on identical inputs** (the 2026-11-18 morning pull, grain sticks): 0 of 46,709 Delaware and 0 of
33,829 Midland sticks differ in anything but the new fields and the version. Direct-rung sticks without an expected error: 0.
Carried sticks without an anchor: 0.

**Ordered pull through the new entry point** (pulled 2026-11-18 17:28:29 UTC, tag rule run 8, 42 s): Delaware 5,072 DSUs,
29,719 DSU x bench, 46,709 sticks, 54,985 legs, 448.5 MM ft, 32,376 wells read; Midland 4,385 DSUs, 19,835 DSU x bench,
33,829 sticks, 37,470 legs, 348.3 MM ft, 30,004 wells read. 0 errors, 0 invariant violations. The same counts as the
unordered pull of that morning.

**sql/73 in the container** (`apply_box_location_set --dry-run`, then applied there): 31 of 31 checks. The 252,925 existing
`box.location` rows are unchanged by identity (ids 4 to 252,947; digest over id, basin, bench, vintages and geometry equal)
and read `source = 'novi'`; `location_source` 252,925, record runs 30 and 32 unchanged; EXPLAIN of a geography DWithin on
`box.location_stick` names `box_location_stick_geog_gix`; a Novi-style insert still works; twelve bad rows are refused.

**Store dry-run in the container** (written in one transaction, verified, rolled back):

| | Midland | Delaware |
|---|---|---|
| Sticks written (`box.location_stick`) = generated | 33,829 | 46,709 |
| DSU / DSU x bench / well rows = generated | 4,385 / 19,835 / 30,004 | 5,072 / 29,719 / 32,376 |
| New locations, all with id >= 10,000,001 | 33,829 (seed) | 46,709 (seed) |
| Every stick agrees with its location on DSU, bench, slot, basin | yes | yes |
| Stored leg length = completed lateral (0.5 % + 5 ft) | yes | yes |
| Sticks without an expected depth error | 0 | 0 |
| DSU x bench stick counts = stick rows | yes | yes |
| Stored as record | no | no |
| **DSUs regenerated from the STORED rows alone, differences against the stored sticks** | **4,385 DSUs, 0 differences** (274 s) | **5,072 DSUs, 0 differences** (276 s) |
| Write time | 16 s | 23 s |

The regeneration reads `box.location_set_dsu` / `_bench` / `_well` and the DSU polygons, nothing from the run directory:
that is the "reproducible from the warehouse" test, and it passes on every DSU of both basins.

**Id carry between two sets** (Midland, in one rolled-back transaction): the set stored, then the same sticks minus every 50th
stored as a second set. 33,152 carried, 0 new, 677 stopped; 33,152 locations last seen in the second set and 677 left at the
first; 0 carried sticks changed their stored name.

A rolled-back store still uses up id numbers (a sequence does not roll back): the Delaware dry run started at 10,067,665.
Harmless; ids are not meant to be dense.

## What 4c would do on live (for the go)

`python -m scripts.apply_box_location_set`, outside the nightly window (05:00 CT dispatch, done by about 06:30 CT).

- Objects: five new tables with their indexes; on `box.location` six `ADD COLUMN` (metadata-only), `DROP NOT NULL` on
  `first_seen_vintage` / `last_seen_vintage`, two CHECKs validated against 252,925 rows, two indexes, the id sequence
  restarted at 10,000,001.
- Nothing is dropped. No CASCADE. No matview, so nothing changes in the nightly refresh list.
- Lock: a brief ACCESS EXCLUSIVE on `box.location` while the columns and CHECKs go on (seconds in the container). erebor
  reads `box.location` only through the record runs; a request in that instant waits.
- Not touched: `box.pud_forecast`, `box_econ`, `box.extent`, `box.bench_scope`, the tag rule and its tables, `narvi.*`.
- After sql/73, a NEW Novi-seeded location (a future Novi-universe store) would also take an id from 10,000,001 up. Existing
  ids do not change.

## Order that matters

`scripts/box_pud_run.py` now filters `source = 'novi'`, a column that exists only after sql/73. **Apply sql/73 (4c) before
this branch is merged**, or a Novi-universe `box_pud_run store` run from main would fail on a missing column. No such run is
planned (runs 30 and 32 are to be replaced by BOX-stick runs).

## Not done, stated

- The narvi pin is not bumped: PR #34 has to merge first. Until then `core.py` uses the underscore names and a test fails if
  any of the four is missing.
- `store --go` refuses a run built from a dirty tree, a narvi that is not the pinned commit, or no `--backtest` file. The
  dry runs above were built from an uncommitted tree; the run to store at 4d is pulled again from the committed code.
- The back-test was not re-run on 0.11 (0.11 moves no stick, so the 0.10 verdicts on the 2026-11-17 pull stand: T1 59.7 %
  against 60 %, T3 63.2 % against 70 %, T4 36.5 % against 25 %, thickness rung 1.56x and bracket rung 1.71x against 1.5x).
  The set row stores whichever back-test summary is passed at 4d.
- `scripts/gen_data_dictionary.py` has 9 ruff findings that are on main already; the lines added here are clean. The
  dictionary is regenerated after the live apply (it reads live).
- `two_landings` and `second_level` shares are not stored per bench (the flag and the other level's TVD are).
