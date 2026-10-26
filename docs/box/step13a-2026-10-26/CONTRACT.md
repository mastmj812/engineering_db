# Step 13a — the BOX refresh contract and cadence (APPROVED 2026-10-26 as written = D126)

Decision only: nothing built, nothing stored. Sits on D123 (keep only the record), D124 (step 13 approved) and D125 (the 2026
prospective test, frozen). The tooling that implements it is 13b.

## 1. What was measured (read-only, live warehouse 2026-10-26, production through 2026-10-01)

**The frozen well sets are current.** Every group's `wells_final_*.csv` (2026-10-06 WCA / BS2_S refresh, 2026-10-16 step 15)
already holds wells first producing through about mid-August 2026. An analog needs at least 6 months of production, so every
well that could be an analog today is already in the pools. Staleness only starts accruing from here.

**How fast it accrues.** New in-extent producers per month, from the 2026 cohort (Jan–Jul 2026), compared with the group's
in-extent modern pool (first production ≥ 2016):

| group | in-extent modern producers | new / month | new / quarter as a share of pool |
|---|---|---|---|
| WCA (WCA_1 + WCA_2) | 9,344 | 45.1 | 1.4 % |
| WCXY_WCA1 | 1,673 | 8.6 | 1.5 % |
| BS2_S | 3,303 | 45.3 | 4.1 % |
| WCB_1 | 1,601 | 9.6 | 1.8 % |
| WCC | 757 | 10.6 | 4.2 % |
| AVA_0 | 232 | 1.9 | 2.5 % |
| AVA_1 | 399 | 6.4 | 4.8 % |
| AVA_2 | 283 | 4.6 | 4.9 % |
| BS1_S | 958 | 18.3 | 5.7 % |
| BS2_C | 532 | 12.4 | 7.0 % |
| BS3_C | 1,498 | 29.1 | 5.8 % |
| BS3_S | 2,354 | 21.7 | 2.8 % |
| WCB_2 | 949 | 11.4 | 3.6 % |

- **Without a pool refresh for a year,** 6–28 % of each group's evidence would be missing.
- **That evidence is the local evidence r2 reaches for first,** in the active development areas.
- **A monthly refresh would add only 0.5–2.3 % per month.**

**The extents are tight.** Modern producers of the group's own tags outside the extent:

| group | within 1 mi | within 2 mi | of those within 2 mi, first producing since 2025 |
|---|---|---|---|
| WCA | 1 | 5 | 3 |
| WCXY_WCA1 | 0 | 1 | 0 |
| BS2_S | 10 | 13 | 6 |
| WCB_1 | 7 | 14 | 2 |
| WCC | 5 | 8 | 0 |
| AVA_0 | 1 | 2 | 0 |
| AVA_1 | 0 | 5 | 2 |
| AVA_2 | 3 | 3 | 2 |
| BS1_S | 0 | 1 | 0 |
| BS2_C | 2 | 6 | 0 |
| BS3_C | 12 | 19 | 4 |
| BS3_S | 5 | 9 | 1 |
| WCB_2 | 4 | 13 | 1 |

The extents (2026-10-09 / 10-16) contain nearly every producer. Edge growth since 2025 is 0–6 wells per group within 2 mi.

**What a refresh costs.**
- About 11 h of compute: build 7.3 h, water 0.7 h, proximity 0.2 h, live store about 3.1 h. The build resumes per group.
- Steven re-prices every new record. Under D123 the previous run and its econ are pruned once the new record is verified.

## 2. The contract: what each refresh does

| input | per refresh | rule |
|---|---|---|
| Novi PUD universe + sticks | recomputed with each vintage | D73 / D83 crosswalk at store. Carried, new and stopped locations are counted |
| production data | recomputed every build | last full warehouse month |
| analog well sets | **new wells only, all 13 groups** (D84 extended) | the bench-QC consensus + the class rule of record on wells never judged before. Old wells are never re-decided (tag changes come only through 13e). Per-group set and its new-well count in the run notes |
| selection (D121 r2), Cui, measured spacing | frozen | method of record; changes only by its own acceptance |
| per-well fits, F(k) | recomputed every build | — |
| proximity configuration | recomputed every record run | D116 (`box_step16d prox-measure`) |
| walk-forward haircut (WCA oil, BS2_S oil + gas) + every disclosure line | **frozen between annual re-scores** | §3 |
| proximity precedent + factor table | **frozen between annual re-scores** | §3 |
| tier (validated / provisional) | frozen | moves only through the prospective test (D125) |
| extents | frozen | re-review on the trigger in §4 |
| water method | frozen | its data-through follows the run (13b tooling; no hand-bumped pin) |
| run notes | — | stamp the Novi vintage, production-through, each group's pool set and new-well count, the 13e tag-release id, the evidence-pack and proximity-table digests |

## 3. The annual re-score (haircut, disclosure, proximity precedent)

- **When:** once a year, in the Q1 refresh, with production through January. The first is about 2027-Q1. By then every well of
  the 2024-12-01 fold (wells first producing in 2025) has cum-12; 16c could score only the earlier half of them.
- **What:** re-run the tuning folds with current production under the frozen D120 §4 source rule. Re-derive the WCA / BS2_S
  haircut tables (the 9c guard, D106, still applies) and the disclosure lines. Re-measure the proximity precedent from drilled
  children.
- **The prospective fold is never a tuning fold before its judgment.** The next cutoff, 2025-12-01, scores the wells first
  producing in 2026, which is exactly the D125 cohort. It joins the tuning folds only after the cum-12 judgment (about 2028-Q1).
  This corrects the plan text's "2025 cutoff ≈ 2027-Q1".
- **What it can and cannot change:**
  - it can change haircut factors and disclosed biases;
  - it cannot change a tier, the selection rules or a frozen test.
  - A re-score that moves a disclosed oil bias by more than 5 points on any group is reported at its own gate before it ships.
- **Not re-scored between years.** A quarterly refresh ships the new pools and production under the last annual evidence pack,
  and says so.

## 4. Extent re-review trigger (D17's N, X)

Re-review a group's extent when either of these holds:
- at least **N = 10** modern producers of its tags, first producing after the extent's `created_at`, have lateral midpoints
  **outside** the extent and **within X = 2 mi** of it;
- a 13e tag release moves at least 10 wells within 1 mi of its boundary, in either direction.

Checked at every refresh and printed in the run notes. On today's numbers it would fire for none; BS2_S (6) and BS3_C (4) are
the closest. Re-review = the step-3 method plus the geologist's look (D28). A new extent is stored as its own version on go.

## 5. Tag-release thresholds (13e: small vs large)

A group's moved wells = its modern in-extent producers that gain or lose the group's tags in a release.

| class | condition (any one) | what happens |
|---|---|---|
| **large** | moved wells ≥ 5 % of the group's in-extent modern producers (WCA 467, BS2_S 165, BS3_C 75, BS1_S 48, AVA_0 12 wells today), OR ≥ 5 % of the group's oil cum-12 tuning wells | that group's evidence is re-scored on the new tags at its own gate (§3 method, out of cycle); the tier does not move |
| **group-changing** | a release merges or splits groups (e.g. rule A) | re-acceptance of the family (step-15 pattern), its own gate; the prospective amendment (D125 §3) is committed first |
| **small** | neither | picked up at the next refresh; the evidence pack stands; the release id is disclosed |

An extent re-review is triggered as in §4.

## 6. Cadence

- **Quarterly, with the Novi vintage.** That is when the PUD universe changes, so a record has to be rebuilt anyway; it also
  takes in 1.4–7 % new pool wells per group.
- **Plus on demand** when you ask. That is for a live deal on a group with a material fresh-well count, or for an out-of-cycle
  re-score after a large tag release.
- **Safety net:** if the record's production-through lags the warehouse by more than 4 months (a late vintage), a refresh is
  due without a vintage.
- **No monthly refresh.** It would add 0.5–2.3 % new wells a month and cost about 11 h of compute plus a Steven re-price each
  time.
- **So per year:** 4 record runs (plus any on-demand), 4 re-prices, 1 annual re-score (Q1).

## 7. Gate 13a — the calls (APPROVED as written, Michael 2026-10-26: "approve the contract as written (CONTRACT §7, all five)")

1. The contract table (§2): new-wells-only pools on all 13 groups; evidence and proximity precedent frozen between annual
   re-scores.
2. The annual re-score: Q1, first about 2027-Q1; the prospective fold excluded until judged; a 5-point oil-bias move goes to
   its own gate.
3. The extent trigger: N = 10, X = 2 mi, plus a 13e trigger of 10 edge wells.
4. Tag-release threshold: 5 % of in-extent modern producers or of oil cum-12 tuning wells = large.
5. Cadence: quarterly with the vintage + on demand + the 4-month safety net; no monthly refresh.
