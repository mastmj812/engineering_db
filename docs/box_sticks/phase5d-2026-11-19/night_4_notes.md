# Shadow night 4 (run 9, nightly of 2026-11-24): S8 fails on one stick

Written 2026-11-24 from read-only queries. Nothing was changed or tuned.

## The failure

Bar S8 asks that every stick newly `producing` is confirmed by the independent read, 100 %. Run 9 sent 22 sticks to
`producing`; the read agrees on **21 of 22**.

| stick | pad | bench | target TVD | well | well tag | well TVD (header) | first production | best leg share | hook basis |
|---|---|---|---|---|---|---|---|---|---|
| 10132711 (Midland, set 25) | 22251 | WCB_2 | 9,831.9 ft | 4232941854 (Midland County) | WCB_1 | 425 ft | 2018-03-15 | 0.505 | `planned` |

The read fails it on depth: the well is tagged WCB_1, the stick is WCB_2, and the well's depth as the warehouse holds it today
is 425 ft against a 9,831.9 ft target. `directional_survey_is_planned` is FALSE on the well, yet the hook's status row says
`match_basis = planned` (no depth evidence, judged on the tagged bench's landing in the DSU). The two reads treat this well
differently and the bar counts that as a miss. Not resolved here.

## What moved, and the traced cause

174 locations changed (bar S4: <= 198, passes tonight): 53 status changes and 121 `open -> open` rows (flag or matching-well
changes; crowded flag changes 122). Both basins moved; the Midland had changed nothing on nights 2 and 3.

The nightly replaced the whole Novi survey table:

- `meta.etl_log`, `DirectionalSurveys (v4)`, 2026-11-24: 16,542,243 rows inserted and 16,538,006 deleted. The table holds
  about 16.54 million rows, so this is every row. (2026-11-22: 1,510,540 / 926,591. 2026-11-23: no survey load.)
- `raw_novi.DirectionalSurveys` now holds 71,636 wells; `curated.well_lateral_survey` 71,636 rows.
- The 28 wells behind tonight's changes (9 counties in Texas, 2 wells in Lea) have **0 rows** in the raw survey table and no
  row in `curated.well_lateral_survey` today. Their first production dates run 2014 to 2026: these are not new wells.
- Of horizontal producers (first production date present, lateral > 3,000 ft), 5,221 of 63,522 have no survey summary row
  today.

Not traced: whether these 28 wells had survey rows on 2026-11-23 (the raw rows were replaced, and no earlier count of
surveyed wells was kept), so "they lost their surveys last night" is consistent with the evidence but not shown. Two of the
28 carry implausible header depths (4232941854 at 425 ft, 4232941760 at 1,600 ft); two Lea wells have no depth at all.

## Also tonight

- Hook seconds 53.9 (226.8 the night before): the query plan change of PR #272, as expected.
- "Schema box" reads 79,275 stick rows (285,145 before): the prune of superseded sets on 2026-11-23, not the hook.
- One well, two sticks: 3 wells (1 before). New: 4213543459 (pad 22124, MS and JM, overlap 0.982 each) and 4230135813
  (pad 11252, BS1_S and BS2_C, overlap 0.65 each). All three are within one DSU on different benches.
- Stale DSU x bench: 5 (3 before). New, both Midland pad 19373: LSSH (2 new producers) and MS (1).
- Conflict queue: 40 sticks (31 before): 33 Delaware, 7 Midland; 30 on depth basis, 10 on planned basis.
- Flapping (S5): 2 of 601 locations returned to an earlier status (0.3 %).

## Open for Michael

1. S8 failed on night 4 (1 stick of 22). S4 had already failed on night 2. Neither bar is edited.
2. A second, larger vendor survey rewrite in three nights. Your position of 2026-11-23 stands (expected noise, no rule
   change); this one reached the Midland record too.
3. Why the hook judged 4232941854 on `planned` basis when its planned flag is FALSE is a question about the rule's reading
   of a well with no survey rows, not answered here.
