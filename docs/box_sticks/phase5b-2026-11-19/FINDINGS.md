# BOX sticks gate 5b: nightly reconciliation, authored

2026-11-19. **Nothing applied on live. No DDL, no write to `box.*`, `curated.*` or `meta.*` on the warehouse.** Live was
only read (the module's read-only pass, and a read-only dump to seed the rehearsal container). Bars: `BARS.md`, committed
(`c61b853`) before the module's SQL was run on anything. Branch `claude/box-sticks-phase5b`, cut from main at `b0affb5`.

Record sets judged: set 16 (Delaware, 46,062 sticks) and set 17 (Midland, 33,138), generator `box_sticks_0.12`, pull
2026-11-19 01:00 UTC. Wells read 2026-11-19 03:28 UTC.

## 1. What was authored

| File | What it is |
|---|---|
| `sql/74_box_recon.sql` | Four ETL-owned tables: `meta.box_recon_run`, `curated.box_location_status`, `curated.box_location_status_log`, `curated.box_dsu_bench_stale`. Plain tables, additive, commented, `analyst_ro` read-only. Nothing in `box`, no matview, nothing dropped |
| `etl/box_recon.py` | The nightly step, pure SQL through psycopg (`JUDGE_SQL`, `STALE_SQL`, version `box_recon_1`): judge every record stick, list the stale DSU x bench, circuit breaker, write the log and replace the two tables in one transaction. `--dry-run` is read-only |
| `scripts/apply_box_recon.py` | Applies sql/74 twice and verifies: 33 checks (tables, indexes, constraints, comments, grants, empty after a first apply, `box` untouched by identity, EXPLAIN names the stick index, one row per record stick, seven refused inserts). `--dry-run` rolls back |
| `etl/refresh.py` | The hook: fires just before `curated.codev_context`. `etl/db.py` and `_CURATED_MATVIEWS` are not edited. `--no-box-recon` skips it |
| `tests/test_box_recon.py` | 12 DB-free tests: the constants are the decisions of record, the SQL is read-only and literal, the module writes only its four tables and never `box`, writer and DDL agree, the hook never raises and is a no-op before sql/74, the wiring comes after everything it reads |
| `scripts/box_sticks_phase5b.py`, `scripts/box_recon_rehearsal.py` | The measurements below. `scripts/box_rehearsal.py`: seeds the sql/73 tables and mirrors `curated.well_lateral_survey` |
| `scripts/gen_data_dictionary.py` | The four tables in the consumer map. The dictionary itself is regenerated after a live apply (it reads live) |

The rule, as decided 2026-11-18: only a producing well takes a stick out (`pending` and `permitted` flag and stay in
inventory); conflict from 30 % of a leg; the three generator rules mirrored; flat-ended corridors; the well line as generator
0.12 reads it; a stale row per DSU x bench with an estimated count.

One change against the 5a sketch, made before E4 was scored: a stale row's `sticks_out` counts the sticks **its new producers**
took out, not every stick that is out there, so the estimate compares like with like against a regeneration.

## 2. The bars

| Bar | Result | Verdict |
|---|---|---|
| E1 the module's SQL on live against the Python reference, stick by stick | same status on 99.993 % (Delaware; 3 sticks differ) and 100.000 % (Midland); same crowded flag on 99.967 % (15 differ) and 99.943 % (19) | passes |
| E2 wall time of the read-only pass on live, both basins, status + stale; stick index in the plan | 131.6 s; `box_location_stick_geog_gix` | passes |
| E3 day 0 on sets 16 and 17: producing or conflict; crowded | Delaware 0.20 % (72 producing, 20 conflict) and 0.15 % (67); Midland 0.05 % (16, 2) and 0.14 % (47) | passes |
| E4 the stale estimate against a regeneration, 156 DSU x bench per basin | total -7.3 % Delaware (165 against 178), +7.8 % Midland (207 against 192); mean abs error 0.51 and 0.47 against 0.69 / 0.57 and 0.63 / 0.72 for the two single estimates; exact on 58.3 % and 63.5 % | passes |
| E5 container: sql/74 through the apply script | 33 of 33 checks, twice; the second apply changed no row | passes |
| E6 container, night 1 | 79,200 status rows = record sticks, one per location; 79,200 log rows, all `first_run`; run row `written` | passes |
| E7 container, night 2 with nothing changed | 0 log rows; status table identical but for the run id; `changed = 0` | passes |
| E8 container, absence, failure, breaker | tables absent: returns `absent`, creates nothing; forced SQL error: the hook did not raise, table untouched, `failed` run row; a real change of 5 locations over a forced limit of 1: `breaker`, nothing written; let through: 5 log rows `producing -> pending`, cause `well`; wells restored: back to 88 producing | passes |

All eight pass. The rehearsal driver ran 24 checks, 24 ok (`rehearsal_summary.json`, `rehearsal_apply.log`).

## 3. Day 0 on live (read-only), sets 16 and 17

| Status (sticks) | Delaware | Midland |
|---|---|---|
| open | 45,286 | 33,027 |
| permitted (flag; inventory) | 656 | 76 |
| pending (flag; inventory) | 28 | 17 |
| producing (out) | 72 | 16 |
| conflict (out, for review) | 20 | 2 |
| crowded flag (out) | 67 | 47 |
| **counts as inventory** | **45,903 of 46,062** | **33,073 of 33,138** |

Stale DSU x bench on day 0: 3. Review queue on day 0: 22 conflict sticks. Files: `live_day0_not_open.csv`,
`live_day0_stale.csv`, `live_sql_vs_reference_diff.csv`.

## 4. How it runs in the nightly

- The hook reads only; it returns at once while sql/74 is not applied or no basin has a record set. With the tables present
  it takes about 1 to 3 minutes (131.6 s for the read-only pass on live, which evaluates the judge twice; 48 to 174 s per
  night in the container), inside `SET LOCAL statement_timeout = '600s'`.
- Any error is caught, logged, and recorded as a `failed` run row; the previous night's tables stand.
- Circuit breaker: more than max(200, 1 % of record sticks = 792 today) locations changed in one night with the same record
  sets and rule version writes only the run row. A new record set or a new rule version is not held by the breaker; every log
  row of that night says `set_change` or `rule_change`.

## 5. Not in this gate, stated

- **Conflict review cards and their verdict table** (`DESIGN.md` Q8): not authored. With producing-only and the 30 % floor
  the day-0 queue is 22 sticks, and no decision on the review surface was taken. Recommend deciding it during the shadow week.
- **One well, two sticks in one DSU** (`DESIGN.md` Q3): no rule; counted in the shadow reports.
- **sql/68 side by side** (`DESIGN.md` Q6): for the shadow reports of gate 5d, read-only.
- Comments live in sql/74 itself (the sql/73 pattern), not in sql/31. The data dictionary is not regenerated: it reads live.
- `scripts/box_sticks_phase5a.py` gained a `flat` option used by the reference; its tests are unchanged and pass.

## 6. Gate 5c, when you say so

What the go would be for, exactly: `python -m scripts.apply_box_recon` on live. It creates the four tables above (new,
empty), their indexes, constraints, comments and `analyst_ro` grants, and nothing else. No CASCADE, no lock on an existing
table, no app goes dark. With it, the standing authorization for the nightly to write those four tables behind the breaker.

Merge order: **apply (5c) before this branch merges**, as with sql/73, so that nothing reaches the nightly path first. If
it merged first the hook would still be a no-op (it checks for its tables), but your rule was nothing on the nightly path
before 5c.
