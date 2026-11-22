# Shadow night 2 (run 7, nightly of 2026-11-22): S4 fails

Written 2026-11-22 from read-only queries. Nothing was changed or tuned.

## The failure

Bar S4 allows 198 changed locations per night (nights 2 to 7). Run 7 changed **419**, all in the Delaware (set 24). The
Midland (set 25) changed nothing. The circuit breaker (792) did not trip, so the run was written.

| Delaware sticks | night 1 (run 6) | night 2 (run 7) | change |
|---|---|---|---|
| open | 45,375 | 45,239 | -136 |
| permitted | 665 | 700 | +35 |
| pending | 30 | 64 | +34 |
| producing | 60 | 121 | +61 |
| conflict | 23 | 29 | +6 |
| crowded (flag) | 69 | 227 | +158 |
| inventory | 46,001 | 45,776 | -225 |

## The cause, as far as it was traced

The nightly loaded a re-issue of Novi directional surveys for New Mexico:

- `meta.etl_log`, `DirectionalSurveys (v4)`: 1,510,540 rows inserted and 926,591 deleted on 2026-11-22, against 448 and 448
  the night before.
- Wells whose survey rows were loaded on 2026-11-22: 7,163, of which 7,162 have a New Mexico API (30...) and 1 Texas.
- The 63 sticks newly `producing` sit on 62 wells: 40 in Lea (30025), 23 in Eddy (30015). All 62 are among the re-issued
  wells. Their first production dates run 2015 to 2026 (41 of 63 are 2023 or later), so these are not new wells: their
  well line moved.
- 56 of the 62 wells carry `directional_survey_is_planned = TRUE` today. The rule gives such a well no depth evidence and
  judges it on its tagged bench's landing in the DSU (`planned_basis`).

Not traced: what the lines of these wells were on 2026-11-21 (the raw rows were replaced), so whether the re-issue is a
correction or a regression on Novi's side is not shown here. Set 24 was generated from the pull of 2026-11-21 00:28 UTC, on
the old lines.

## S8

63 sticks newly producing; the independent read agrees on 63 of 63 (first production date present, same bench or within
150 ft, leg share >= 0.5). The read uses the same re-issued lines, so it confirms the rule was applied as written, not that
the new lines are right.

## Also new tonight

- One well matches two sticks for the first time: 3002549569, pad 11280, WCA_1 stick 10061335 and WCA_2 stick 10137582,
  overlap 0.98 on each.
- Stale DSU x bench: 3 (pads 10703 BS2_S, 10918 BS3_C, 11304 BS1_S; one new producer each).
- Conflict queue: 31 sticks (25 the night before).

## Open for Michael

1. S4 failed on night 2. The bar is not edited and nothing is tuned.
2. Whether a vendor survey re-issue of this size should be held by the breaker or handled as its own cause is a rule
   question, not answered here.
3. 56 of the 62 wells are planned-survey wells with first production. The standing open question (should a planned-survey
   match go to `conflict` instead of `producing`) now covers most of one night's movement.
