# PDP-proximity → BOX record run 11 — implementation plan (gate 4 → build)

Michael 2026-10-20: keep the rule uniform (AVA / BS2_C included); plan the record-run implementation and stop before
any live write. **Nothing in this plan writes to Supabase until the go-points marked GO.**

## 0. Facts that shape it (read live 2026-10-20, read-only)
- **The record is run 10**, data through 2026-07-01, Novi 2026Q3. It holds 50,963 forecast PUDs × oil / gas / water.
- **Run 10 is PRICED.** `box_econ.box_pud_econ` has 815,408 rows on it, and the D82 contract makes a priced run undeletable.
  - Run 11 is therefore a new record that **supersedes** run 10; run 10 stays (D104 keeps record + priced runs).
- **Storage.** `box.pud_forecast_month` is ~91.7M rows / 12 GB, and the DB is 87 GB.
  - Run 11 adds ~77M month rows, about 10 GB. The 8,488 no-forecast PUDs carry no months.
  - The DB lands around 97 GB.
- **Free numbers on main:** `sql/65` and plan decisions D112+. Both are reserved here; the parallel-collision rule applies.

## 1. Decisions to record (plan §2, `docs/box_type_curves_plan.md`)

| D | content |
|---|---|
| D112 | Pair metric + depleting parent: the deal-intake v14 metric applied basin-wide. Parent ≥ 12 months at the reference date. WCA pool = one bench (D42). |
| D113 | Configuration haircut, option (a): multi-parent configurations only (class × count ≥ 2 × flank, mixed 2/3/4+). Oil only; gas untouched. Factors from `haircut_table_candidate.csv` (cum-24, BOX's calibrated level, fit on all folds). Label "validated with exception": PREREG_2c FAIL as written; multi-parent cells within ±5 %; confirm on the 2026 prospective cohort. |
| D114 | Two-tier precedent: ≥ 30 drilled multi-parent wells of the bench pair (mixed: own bench), plus ≥ 30 drilled packages where the haircut ≤ 0.80. Short of either → `not_covered_no_precedent`. Uniform across benches (gate 4). |
| D115 | No shielding exemption for PUDs; permit-round producer TVDs counted and flagged. |
| D116 | Record implementation: run 11 derived from run 10, not refit (§3). Configuration re-measured on every record run. |

## 2. Schema — `sql/65_box_proximity.sql` + `scripts/apply_box_proximity.py`
Idempotent, in the sql/63 style. Container-validated first; live apply is a **GO**.

1. **`box.pud_forecast` coverage list** gains `not_covered_no_precedent`. Its rows keep the search provenance (search_mode, radius, n_analogs: what BOX would have used), so `uncovered_ck` admits it alongside `not_covered_no_analogs`. It has no stream, month or analog rows: the child FKs already refuse them, because the coverage checks admit only covered / covered_provisional.
2. **`box.pud_forecast_stream`** gets `+ prox_factor double precision NOT NULL DEFAULT 1 CHECK (prox_factor > 0 AND prox_factor <= 1)`.
   - The eur CHECK becomes `eur = eur_raw × eur_haircut × prox_factor`. Existing rows read factor 1, so run 10 is untouched.
   - Gas and water rows always carry 1.
3. **NEW `box.pud_proximity`** (run_id, location_id) PK, FK → pud_forecast. One row per forecast-universe PUD of the run:
   - `config_class`, `n_same`, `n_topfill`, `n_underfill`, `n_parents_total`, `flanked` (per class), `outcome` (the 5 values), `haircut_key`, `factor`, `pair_key`, `prec_multi`, `prec_package`;
   - `label` ('validated_with_exception' | NULL), `n_permit_parents`, `n_recent_producers`;
   - `table_ref` (haircut-table sha256 + PREREG commit).
   - CHECK: `outcome = 'haircut'` ⇔ `factor < 1` and `label` set. no_forecast outcomes ⇔ the pud_forecast row is `not_covered_no_precedent`.
4. **NEW `box.pud_proximity_parent`**: the named parents behind each configuration (run, location, parent api10, class, dv, dh, overlap, signed offset, age_days, permit). This is the provenance that erebor's workup and gunbarrel can show, and it parallels `location_analog`. Expect ~60–80k rows.
5. **`box_econ.box_pud_econ`** needs no change: no-precedent PUDs have no streams and so can't be priced.
6. **sql/31 comments, then dictionary regen** (`scripts.gen_data_dictionary`, with `_CONSUMERS` for the two new tables).

## 3. Build — `scripts.box_pud_run prox` (DB-free transform; no refit)
- **Input:** run 10's stored build artifacts. Those are the main checkout's `runs/box9/run.pkl` (sha256 9c45e262…) and the water `runs/box12b/water.pkl` (sha 9519614d, in worktree modest-spence). Both are digest-checked; they are exactly what run 10 stored.
- **Second input:** the step-4 outcomes, re-measured at build time by `box/prox_pud.py` against live producers (read-only). The digest and producer count are stamped.
- **Transform per PUD:**
  - unexposed / single parent → unchanged;
  - haircut → oil `prox_factor` = factor, oil months × factor (uniform qi + EUR scale, Di / b fixed, as in D43), gas and water months unchanged, so GOR rises by 1 / factor;
  - no forecast → coverage `not_covered_no_precedent`, with streams, months and analogs dropped.
- **Water: untouched (recommended, needs your OK).** D108 water rides on RAW box_v2 oil through WOR. The haircut was validated on oil only, and depleted children showed GOR rising, which says nothing about WOR.
- **Disclosure** (`forecast_run.disclosure → 'proximity'`): method, table ref, PREREG verdict ("FAIL as written; option (a) exception"), multi-parent residuals, survivorship caveat, prospective confirmation date, outcome counts.
- **Identity, checked before store:**
  - counts per coverage and outcome equal the measurement;
  - Σ oil EUR equals Σ(run-10 EUR × factor) over forecast PUDs, about 23,300 MMbbl at step-4 data;
  - ordered md5 of gas and water months for every surviving PUD equals run 10;
  - oil months of as-is PUDs are byte-equal to run 10.
- **Tests:** transform goldens on fixtures, plus the CHECK predicates mirrored in Python.

## 4. Rehearsal → live (the GO points)
1. **Container rehearsal** (box9 pattern: throwaway PostGIS with the live `box` state copied): apply sql/65 → `store --record` run 11 → identities green → erebor read against the container.
2. **GO-apply** `sql/65` live (`apply_box_proximity`, checks incl. a rolled-back smoke).
3. **GO-store** run 11 `--record` (one transaction, identity before COMMIT, ~20 min). Run 10 → `superseded_by = 11`, kept because it is priced.
4. Dictionary regen; docs PR.

## 5. erebor (separate PR, after the container rehearsal; verified against live after the store)
- **Coverage class** `not_covered_no_precedent` in the Highgrade facet / legend: "no forecast — configuration without drilled precedent (D114)". It counts in screen identities like `no_analogs`.
- **Pad workup:** configuration line ("topfill · 3 parents · flanked · nearest WCA_1 340 ft vt / 450 ft hz"), haircut factor + label, precedent counts, the named parents table from `pud_proximity_parent`.
- **Highgrade:** a haircut column and a `prox` filter (as-is / haircut / no-precedent). EUR columns already read `eur`, so they pick up the factor.
- **Disclosure panel:** the run-level `proximity` block.

## 6. Steven
- **Note drafted for Michael to send. No email; the #eng-updates post is his channel for drops, and this BOX change goes in the same thread.**
  - Run 11 supersedes run 10; run 10 stays priced.
  - 9,706 PUDs have oil × factor (0.75–0.94).
  - 8,488 PUDs have no forecast.
  - Gas and water are unchanged.
  - Re-price run 11 under the same `downtime_basis` contract.
- **Blue Ox drop ledger:** no change. The screen drop comes from deal-intake, not BOX records. A ledger entry follows only when deal-intake adopts the same logic (§7).

## 7. After the record (separate builds, each its own gate)
- **Quarterly reload skill §9 (BOX steps):** re-measure configuration (`prox_pud`) with every record run. 4,421 PUDs have a < 12-month producer nearby.
- **Prospective confirmation:** add the configuration haircut to the frozen 2026 cohort scoring as a reported line (D85 stays frozen; this is additive reporting).
- **Deal-intake:** replace v14's 300 / 800 cull with D112–D115, then a cross-repo contract entry and a ledger entry.
- **CLAUDE.md:** a domain-rule line for D112–D115, on your go.

## Open choices for Michael (before the build)

| # | question | recommendation |
|---|---|---|
| a | Water | untouched (rides raw oil, D108) |
| b | No-precedent rows keep search provenance (n_analogs, radius) | yes |
| c | Run 10 kept; DB +~10 GB to ~97 GB | yes — forced by the priced-run contract |

## 8. Built + container-rehearsed 2026-10-20: AT THE GO-APPLY POINT
Decisions taken with the go:
- water untouched;
- no-precedent rows keep their search provenance.

D112–D116 are written into `docs/box_type_curves_plan.md`.

**Code (commit 415ab3d):**
- `sql/65_box_proximity.sql` and `scripts/apply_box_proximity.py` (25 checks incl. a rolled-back smoke);
- `box/prox_record.py`: re-derives every PUD's configuration from `runs/prox/pud_links.pkl` and asserts it equals the reviewed `pud_outcomes.csv.gz` (0 mismatches on 50,963);
- `scripts/box_prox_record.py store`: one transaction; rolls back unless `--commit`; `--record` flips the record.

**Rehearsal container** (postgis 16-3.4 on :5437, throwaway):
- The existing apply chain ran green, except the econ-schema script stopped on a `curated` grant the container lacks.
- Live box state was copied READ-ONLY: 121,727 PUD rows, 152,889 streams, the analogs, and 2.7 M sample months (300 PUDs per outcome).
- **sql/65:** 25/25, twice (idempotent). Log: `rehearsal/apply_box_proximity.txt`.
- **Store:** a rollback rehearsal, then `--commit --record`. Every identity green both times (`rehearsal/store_record.txt`):

  | identity | result |
  |---|---|
  | coverage counts | the source with 8,488 moved to `not_covered_no_precedent` (787 from covered, 7,701 from covered_provisional) |
  | stream rows | 42,475 per stream |
  | oil EUR | **23,300.106 MMbbl = run 10 × factor** (step 4: 23,300.1) |
  | gas / water streams | identical |
  | gas / water / as-is oil months | ordered md5 identical |
  | haircut oil months | = source × factor, 0 rows off |
  | analogs / water analogs | equal the source's survivors |
  | proximity outcomes | equal the gate-4 counts |
  | named parents | 73,307 |
  | run 10 | untouched |

  Then the record flip: run 10 superseded and kept.

**Live run id.** The store takes the next sequence value. Live's sequence sits at 13, so the new record will be **run 14**; "run 11" in this plan is a label. Each rehearsal rollback burns an id, which is harmless.

**Expected live cost:** ~77 M month rows copied in-database (rehearsal: 1.6 M rows in 16 s), so roughly 15–30 min. DB +~10 GB to ~97 GB.

### The GO points (in order; each needs Michael's explicit go)
1. `python -m scripts.apply_box_proximity` against Supabase. Expect 25/25.
2. `python -m scripts.box_prox_record store`: a live rollback rehearsal, which writes nothing.
3. `python -m scripts.box_prox_record store --commit --record`: the new record (~run 14); run 10 superseded and kept.
4. `python -m scripts.gen_data_dictionary --html docs/data_dictionary.html` with `_CONSUMERS` for the two new tables. Then the erebor PR and the Steven note.

## 9. Live 2026-10-20 (Michael: "go apply … then the live store rollback rehearsal")
- **GO 1 done: sql/65 APPLIED LIVE.** `apply_box_proximity` passed 25/25 on the Supabase session pooler (`rehearsal/apply_box_proximity_LIVE.txt`).
  - Every existing stream row reads `prox_factor` 1.
  - Run 10 coverage and stream counts are unchanged by identity.
  - Repo == live for sql/65.
- **GO 2 done: live store rehearsal, ROLLED BACK** (`rehearsal/store_rehearsal_LIVE.txt`, 2,410 s; months 1,423 s, identities ~15 min). Every identity was green on the full data:
  - **76,455,000** month rows = run 10's survivors;
  - oil EUR **23,300.106 MMbbl** = run 10 × factor;
  - gas / water streams and months, and as-is oil months: ordered md5 identical;
  - haircut oil months 0 rows off;
  - analogs 681,618 / water analogs 694,768;
  - outcomes = gate 4; 73,307 named parents.
- **Checked after:** run 10 is still the sole record, and `box.pud_proximity` is empty.
- **The rehearsal burned run_id 13**, so the committed store will be **run 14**.
- **Next (GO 3):** `python -m scripts.box_prox_record store --commit --record` (~40 min; DB +~10 GB). Then the dictionary regen, the erebor PR and the Steven note.

## 10. Run 14 STORED LIVE as the BOX record (2026-10-20 19:32 UTC; Michael: "go store")
- **Store:** `box_prox_record store --commit --record`: 2,588 s, all 17 identities green before COMMIT (`rehearsal/store_record_LIVE.txt`).
- **Result:** run 14 is the one record; run 10 has `superseded_by` 14 and is kept, with Steven's 815,408 priced rows on it intact.
- **Run 14 counts:** covered 17,820 / covered_provisional 24,655 / not_covered_no_precedent 8,488; proximity outcomes = gate 4.
- **DB size 108 GB** (87 before). That is ~10 GB of run-14 rows plus ~10 GB of dead tuples from the rolled-back live rehearsal, which autovacuum makes reusable but does not return to the OS.

**RENUMBERED sql/64 → sql/65 (parallel-collision rule).**
- While this branch was open, another session merged `sql/64_well_lateral_survey.sql` to main (PR #169, the directional-surveys work). This file is the later-merged one, so it is now `sql/65_box_proximity.sql`, with its content unchanged apart from the comment references.
- **Live text still says "sql/64"** in two places until refreshed:
  1. the table/column COMMENTs, which an idempotent re-run of `apply_box_proximity` refreshes;
  2. run 14's `forecast_run.notes`, which needs a one-line UPDATE.
  
  Both are writes to the shared warehouse, so each needs a go.
- The data dictionary was regenerated after merging main (it carries #169's objects and Steven's sandbox tables as live).

## 11. Live text refreshed to sql/65 (2026-10-20; Michael: "go")
- **`apply_box_proximity` re-run live: 26/26** (`rehearsal/apply_box_proximity_LIVE_sql65.txt`). The DDL is idempotent; the COMMENTs now name sql/65.
  - The validation is now state-aware so a re-run after a stored proximity run passes: stream rows off factor 1 must be oil rows matching `pud_proximity.factor` (9,706); the new tables are checked as existing (50,963 / 73,307 rows) rather than empty; the comment must name sql/65.
  - The first re-run under the old first-apply checks reported 3 expected "not empty / not all 1" failures. It changed nothing beyond the idempotent DDL and comment refresh.
- **Run 14 `forecast_run.notes`:** one occurrence of "(D112-D116, sql/64)" replaced with sql/65 (length unchanged, still the record).
- Data dictionary regenerated.
