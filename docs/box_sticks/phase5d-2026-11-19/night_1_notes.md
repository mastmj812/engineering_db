# Shadow night 1 of 7 (nightly of 2026-11-20): notes beside the generated reports

Night 1 is **run 4** (`night_run_4.md`). The script heads that file "Shadow night 2" because it counts written run rows, and
a written run row already existed. By the bars' own definition ("a night is one `etl-nightly` run that reached the curated
refresh") run 4 is the first night.

## 1. Run 3 was not written by a nightly (reported first)

`meta.box_recon_run` held a `written` row before the first shadow night:

| run | started (UTC) | status | seconds | changed | source |
|---|---|---|---|---|---|
| 3 | 2026-11-19 16:44:40 | written | 61.2 | 79,200 (all `first_run`) | **no `etl-nightly` run at that time** |
| 4 | 2026-11-20 11:15:20 | written | 58.3 | 8 | `etl-nightly` 44723918879 (dispatch, green, `etl` job 11:00 to 11:44 UTC) |

The GitHub runs on 11-19 were the 11:00 UTC dispatch (before the hook reached main at 13:04 UTC) and the 19:29 UTC backstop,
whose `etl` job was skipped. Nothing on GitHub ran at 16:44 UTC. `etl/refresh.py` installs the hook by default, so any local
`python -m etl.refresh` without `--no-box-recon` writes the tables; that is the likely source, **not verified** (no log of the
local run was found). BARS.md says nothing is run by hand to fill the tables; that did not hold for the first fill.

Effect: the `first_run` fill (S3's subject) came from run 3, outside a nightly. Run 3's counts equal the night 0 baseline in
every cell (`night_run_3.md`). Nothing was changed or re-run in response.

## 2. The stick that went to producing (S8)

Location 10069400 (Delaware, WCC, pad 11975, target TVD 10,333.8 ft) went open to producing on well 3001554342, overlap
0.977, `match_basis = planned`. S8's independent read agrees on its three stated tests: first production 2024-06-19, well
tag WCC = stick bench WCC, best leg share 0.986.

Stated beside that, not explained away:

- The well's directional survey is flagged **planned** (`directional_survey_is_planned = TRUE`), so the hook matched on the
  bench tag with no depth test.
- Its recorded TVD is 9,471 ft (lateral p50 9,461 ft): **863 ft above** the stick's 10,333.8 ft target.
- First production is 2024-06-19, yet the well matched this stick for the first time tonight. What changed on the well
  between the two runs was not traced.

## 3. Wells that take a BOX stick out and touch no Novi stick under sql/68's rule

Grain: wells that are the matching well of a `producing` BOX stick, status table as of run 4. 89 wells: 16 realize a Novi
stick, 7 conflict, **66 nothing** (night 0: 65 of 88; the 66th is the well in section 2). All 66 were read, not a sample.
For each, every Novi PUD/RES stick crossing the well's corridor was listed with and without sql/68's bench/TVD guard
(same tag and within 500 ft, or within 150 ft).

| what sql/68 sees for the well | wells |
|---|---|
| A. No Novi PUD/RES stick crosses the corridor | 2 |
| B. A Novi stick overlaps >= 0.2, but none passes the bench/TVD guard | 35 |
| C. Novi sticks cross, none passes the guard, and none overlaps >= 0.2 | 9 |
| D. A Novi stick passes the guard, overlap < 0.2 | 20 |

- In 64 of 66 Novi has undrilled sticks in the corridor (1 to 34 per well), but on other benches: the best-overlapping stick
  is typically hundreds to thousands of feet off the well's TVD (for example well 3002549268, BS2_S at 10,045 ft, against an
  AVA_1 stick 1,149 ft shallower at overlap 1.00). Novi carries no undrilled stick on the well's own bench under the well.
- The BOX match in all but one of the 66 is on depth (`match_basis = depth`), 54 of them at overlap >= 0.7.
- First production of the 66 wells: 59 before 2026-01, 7 in 2026 (latest 2026-07). So most of these wells were producing
  long before the stick sets were generated, and the BOX set still holds a same-bench stick under them.
- Split: Delaware 51, Midland 15.

Reading (mine, not measured further): on these wells the two rules are not disagreeing about the well. Novi has no location
left there to realize; BOX has one. The open question this raises is on the generator side, why sets 16 and 17 keep a
same-bench stick under a well that old, and it was not investigated here.
