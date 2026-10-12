# BOX step 5d — type-curve + risk-factor record (gate 5d summary)

Built 2026-10-12 on branch `claude/box-step5d-record`. **Nothing is applied to Supabase and nothing is stored.**
`sql/58` was validated on a throwaway PostGIS 16 container only. Applying it needs your "go apply", and the
`--store --record` write needs its own go-ahead.

**Review surface:** `record.html`. Open it directly, or serve it with
`python -m http.server 8766 --directory docs/box` → `/step5d-2026-10-12/record.html`.

## 1. What exists

| File | What |
|---|---|
| `sql/58_box_type_curve.sql` | `box.type_curve`, `box.tc_member`, `box.risk_factor`, their indexes, the `analyst_ro` grant, comments. |
| `scripts/apply_box_type_curve.py` | Apply + identity validation + a rolled-back smoke of every guard (28 checks). |
| `box/tc_record.py` | Pure rules: D42 relabel, D45 ladder, D41 × D44 lookup, D43 reference scale. |
| `box/tc_record_report.py` | Builds the record from the committed 5b / 5c deliverables, checks it by identity, writes the page. |
| `box/tc_record_store.py` | The write (one transaction, identity-checked before commit). |
| `scripts/box_tc_record.py` | CLI: `[--drift-check] [--store [--record]]`. DB-free by default. |
| `record.html` | The review page: identity checks, factor tables per stream / bench / level, 5c comparison, 35 curves, store plan, flags. |
| `risk_factor.csv`, `type_curve.csv`, `tc_member.csv` | Exactly the rows `--store` writes (108 / 105 / 22,581). |
| `compare_5c.csv`, `summary.json` | 5c-vs-5d comparison; run stamp, checks, drift result. |

Tests: `tests/test_box_tc_record.py`, 20 DB-free tests. Full suite: 373 passed, 36 skipped. Ruff is clean on every
touched file (mypy is not installed in this venv). The run takes ~19 min with 400 bootstrap draws.

## 2. The record = what you reviewed (identity checks, all pass)

- Installed blueox-boxfit = the 5b and 5c record SHA (3380317).
- The 5c frame (`wells.csv` + gate-1 midpoints) re-estimates the committed 5c `factors.csv` on all 66 terms of the three
  record metrics, worst relative gap 2e-16. Estimation wells are WCA 7,425 / BS2_S 1,804, the same as 5c.
- Every one of the 105 area curves (35 × oil / gas / water), re-fitted from its members' per-well fits, equals the 5b
  stored row (oil / water qo, qi, Di, b, EUR; gas α, β, EUR). Worst relative gap 0.0, with round-trip CSV parsing. The stored
  values are the 5b CSV's; the refit supplies the peak_ramp anchors.
- Members = the 5b strict cohort (7,527 wells); per curve, included members = n_wells. No member is in `exclusions.csv`.
- Every curve is at rung 1. Rung 3 is never emitted, and sql/58 refuses it (D37).
- **Live drift check** (read-only, `curated.dev_scenario` 2026-10-12 07:40): of 9,391 scored wells, **0** changed class and
  **0** changed infill flag since the 5c frame. One well is unscored, the same as in 5c.

## 3. Factors of record (D41–D47)

Model: Poisson PML, location FE + first-prod-year FE, reference = codev_stack with no same-bench parent, same-pool
parents = infill (D42), 90 % cluster bootstrap over 3-mi blocks (400 draws), D45 ladder at n ≥ 30. Oil / water factors are
cum-12 per 1,000 ft (uniform scale, D43). The gas factor is 12-mo GOR / the D30 local level, applied through α on top of the oil factor (D46).

| Term (factor of record, rung) | WCA oil | WCA gas (GOR) | WCA water | BS2_S oil | BS2_S gas | BS2_S water |
|---|---|---|---|---|---|---|
| **infill** | **0.923** [0.91–0.94] n 1,664 | 1.042 | 0.933 | **0.905** [0.88–0.93] n 486 | 1.057 | 0.935 |
| standalone *(scoring only, D44)* | 1.046 | 1.009 | 1.034 | 1.068 | 1.001 | 0.971 |
| topfill \| WCB_1 / WCB_2 / WCC | 0.952 / 0.973 / 0.995 | | | | | |
| underfill \| BS3_S / BS3_C | 0.897 / 0.920 | | | | | |
| topfill \| BS3_C / BS3_S | | | | **0.780** / 1.063 | | |
| underfill \| BS1_S (23 wells → class, rung 2) | | | | 0.941 | | |
| sandwich (rung 3, 10 wells across benches) | 0.786 | 1.401 | 0.931 | 0.786 | 1.401 | 0.931 |

Against the 5c evidence (oil cum-12, `compare_5c.csv`):

- WCA infill is 0.935 in the 5c record view and 0.929 in the 5c pooled view. 5d gives 0.929 (pooled view, log-OLS) and
  **0.923 (PPML, record)**. The 5c FINDINGS expected ≈ 0.93. The D42 relabel moved 187 WCA wells into infill.
- BS2_S topfill | BS3_C goes from 0.694 (log-OLS) to 0.780 (PPML). This is the estimator gap 5c flagged.
- Standalone rises 1–1.3 points under PPML (WCA 1.046, BS2_S 1.068).
- **Area normalisation (ref_mult):** oil median ×1.007 (0.969–1.042), water ×1.005 (0.978–1.041). The reference-scenario EUR is
  the as-built EUR × ref_mult. For example, area 1 oil goes from 46,822 to 46,551 bbl/kft (Di 3.17/yr nominal ≈ 74 % 1-yr effective, b 1.10).

## 4. Warehouse (`sql/58`) — container only

- Applied **twice** (idempotent) to a throwaway `postgis/postgis:16-3.4` carrying sql/54 + 56 + 57.
- `apply_box_type_curve`: **28/28**. That covers tables, PKs, named indexes, analyst_ro reads, no Data-API usage, and the ETL never
  naming box. The rolled-back smoke shows each guard refusing: rung 3, gas not in ratio mode, a non-thin curve under 10 wells,
  a 2nd record curve, a dropped member with no reason, a malformed api10, a reference off rung 0, rung 4, and a 2nd record factor.
  Deleting a curve cascades to its members.
- **Store dry run** into the container, against the live WCA extent + 35 areas of record (copied with a read-only pull):
  - v1 stored as record: 105 / 22,581 / 108 rows;
  - a duplicate v1 is refused;
  - v2 `--record` takes the record over cleanly (v1 0 record rows, v2 105 / 108).
  The dry run used a 5-draw build: same rows and point estimates, only the CIs differ. The container has been removed.
- No geometry columns, so no sql/26 step is needed.

**After your go-apply, in order:**

1. `python -m scripts.apply_box_type_curve` (DDL, 28 checks live).
2. `python -m scripts.box_tc_record --store --record` (the write; its own go-ahead). It re-runs the build in ~19 min and stores what it
   rebuilt. Identities are checked before commit.
3. Regenerate the dictionary: add `_CONSUMERS` entries for the 3 tables, then
   `python -m scripts.gen_data_dictionary --html docs/data_dictionary.html`.

## 5. Flags (choices I made; none of them change a decision of record)

a. **D42 on sandwiches.** 7 WCA sandwich wells had a same-pool side. That side became infill and the other side's one-sided
   relation was kept, which leaves 1 true WCA sandwich. D42's text names topfill / underfill only.
b. **Relabel order.** D42 is applied to the raw (class, parent) *before* rare pairs pool to `|other`. 5c's pooled view did it after
   pooling. The difference is small (WCA underfill | BS3_S 0.889 → 0.865 log-OLS).
c. **What type_curve stores.** The params are the reviewed *as-built* (mixed-scenario) mean curve, plus `ref_mult`. The reference
   curve is derived: qo, qi × ref_mult (D43). The alternative is to store the reference curve itself. Your call.
d. **ref_mult weights** = actual cum-12 per kft, with the factors of record (5c's `mult_cum12` convention, consistent with D43).
e. **Gas level offset (D46 as written).** GOR factors are relative to the reference class, but the D30 local level is the median of
   mixed neighbours. WCA reference-class wells run 1.041× (mean) / 1.000× (median) their local level (n 4,232). Reported, not changed.
f. **Thin rung-3 terminal.** Sandwich rests on 10 wells across both benches. Its gas factor is 1.401 [0.99–2.05], which would raise a
   sandwich PUD's GOR by 40 % on 10 wells. Under D45 rung 3 is terminal whatever n is. Consider a floor of "reference if n < 30 at
   rung 3". That would change D45, so it's yours.
g. BS2_S has factors but no TC areas and no curves (the D4 pilot is WCA). `box.type_curve` holds WCA only.
h. `box.risk_factor` is versioned globally, as one factor set across both benches; the 5c evidence file is unchanged.

## 6. Gate-5d asks

1. **Go-apply sql/58?** (DDL on Supabase.)
2. **Go-ahead for `--store --record`** of this record as v1.
3. Flag c (store as-built + ref_mult, rec) and flag f (thin rung-3 floor: rec, keep D45 as is for now and revisit at step 6).
