# BOX sticks phase 4d: the first stored set (Delaware)

2026-11-18. Michael: "go store Delaware first". **`box.location_set` set 6, Delaware, NOT record.** Midland is not stored.

## What was stored

Generator `box_sticks_0.11`, built from `fb5c6c8` (main after PR #253), narvi `bfc7955`. Pull 2026-11-18 18:26:45 UTC (42 s),
tag rule run 8, DSU polygons 2026Q3. `manifest.json` and `summary_delaware.json` here are the run's own.

| Grain | Rows |
|---|---|
| Sticks (`box.location_stick`, set 6) | 46,709 (54,985 legs, 448.5 MM ft completed; 8,276 U-turns) |
| New locations (`box.location`, `source = 'box_sticks'`) | 46,709, ids 10,046,716 to 10,093,424 (seed: no earlier set) |
| DSUs (`box.location_set_dsu`) | 5,072 |
| DSU x bench (`box.location_set_bench`) | 29,719, of which 10,987 hold no stick, each with its reason |
| Wells read (`box.location_set_well`) | 32,376 |

By rung (sticks; mean held-out median error): thickness 19,721 (57.1 ft), direct 16,825 (44.5 ft), offset 7,534 (82.9 ft),
bracket 2,629 (66.6 ft). Every stick has an expected error; every carried stick names its anchor(s); no direct stick has one.
Flags: pinned 11,607; `second_level_nearby` 3,584 (thickness rung only); `dsu_drilled_across` 1,463; `two_landings_observed` 212.

The set row carries the back-test summary of generator 0.10 on the 2026-11-17 pull (0.11 moves no stick against 0.10), with
its failed bars as written.

## Checks

In the store transaction (10 of 10): row counts equal the generated counts at every grain; every id >= 10,000,001; every stick
agrees with its location on DSU, bench, slot and basin; stored leg length = completed lateral; DSU x bench stick counts = the
stick rows; not record; **all 5,072 DSUs regenerated from the stored rows alone give the stored sticks (0 differences, 372 s).**

From a second, read-only connection after the commit: the same counts; all 46,709 sticks intersect their own DSU polygon; the
Novi side is unchanged (252,925 `source = 'novi'` locations, 252,925 `location_source` rows, records run 32 and run 30,
252,410 `pud_forecast` rows).

Pad 11132 WCC (the gate 4a example): 8 sticks, slots 1 to 8, ids 10,058,529 to 10,058,536, 9,792.2 ft, direct rung, expected
error 71.0 ft, spacing 577.5 ft, pinned.

## The first attempt rolled back

The first `store --go` wrote the set, failed its own regeneration check (29,766 differences, all `tvd_basis`) and rolled back;
nothing was stored. Cause: the live pooler session returns `float8` with `extra_float_digits = 0` (15 digits:
81.1598931105509 for a stored 81.15989311055091); the rehearsal container reads with 1. The stored values were exact; the
verifier's read-back was not. Fix (`1245f9b`): the verifier sets `extra_float_digits = 1` before it reads. The comparison is
unchanged. **Anyone regenerating a set from these tables must do the same**; the `box.location_set` comment in sql/73 now
says so (the live comment is not yet re-applied: that is a `COMMENT ON`, waiting for a go).

The two attempts used id numbers 10,000,007 to 10,046,715 without keeping them (a sequence does not roll back).

## Not done

- Midland is not stored. Nothing is record. No app, forecast or reconciliation reads the set.
- The back-test was not re-run on 0.11.
