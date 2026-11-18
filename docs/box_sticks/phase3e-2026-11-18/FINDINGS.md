# BOX sticks 0.10: the `second_level_nearby` flag

2026-11-18. Generator `box_sticks_0.10_pilot` on the post-cutover pull (tags pulled 2026-11-17, the pull of
`cutover-2026-11-17/`; `pilot_summary.json` says `cache_pulled 2026-11-18` because the cache folder was copied that
day). Read-only; **nothing is stored**. The measurement behind the flag is in `cutover-2026-11-17/FINDINGS.md` and
`cutover-2026-11-17/second_landing/`.

## What changed

- The landing chain (`scripts/box_sticks_phase1c`) reports, for every thickness-rung depth, whether the thickness sample
  it was carried from sits at two levels: a second peak 150 ft or more from the main one, holding 25 % or more of the
  weight and 3 or more wells, with the dip between them at 70 % of the smaller peak or lower (30 ft kernel). Columns
  `second_tvd_ft`, `second_share` in the frame.
- The generator carries it onto the stick: flag `second_level_nearby`, and `tvd_basis.second_level_tvd_ft` = the other
  level's TVD. The bench log has the same two fields. **No stick is placed, moved or removed by it.**
- Thickness rung only. The bracket and offset rungs build their samples differently and were not measured.
- The anchor rule is unchanged (rank order; decided 2026-11-18).

## Check: nothing moved

Grain: sticks, both basins, 0.9 run of `cutover-2026-11-17/` against this run, matched on DSU + stick name.

| | 0.9 | 0.10 |
|---|---|---|
| Delaware sticks (legs) | 46,690 (54,964) | 46,690 (54,964) |
| Midland sticks (legs) | 33,791 (37,432) | 33,791 (37,432) |
| Sticks differing in anything but the flag, its TVD and the version | | 0 |
| Errors / invariant violations | 0 / 0 | 0 / 0 |
| Back-test bars | | identical to the 0.9 run |

## What is flagged

| | Sticks flagged (legs) | DSU x bench | DSUs |
|---|---|---|---|
| Delaware | 3,575 of 46,690, 7.7 % (4,290) | 1,249 | 1,014 |
| Midland | 1,499 of 33,791, 4.4 % (1,688) | 499 | 451 |

- Delaware by bench: WCB_2 694, BS3_C 640, WCB_1 499, BS1_S 364, BS2_S 322, BS2_C 298, BS3_S 262, WCC 171, AVA_1 118,
  WCA_1 104, WCA_2 54, WCXY 22, AVA_2 22, AVA_0 5.
- Midland by bench: WCD 404, WCA_1 239, LSSH 199, JM 178, WCC 150, DEAN 142, WCB_2 76, WCB_1 59, MS 52.
- No flagged stick also carries `two_landings_observed` (that flag needs the DSU's own wells; a thickness-rung bench
  has none within 1 mi). 169 flagged sticks also carry `dsu_drilled_across`.

What the flag is worth (from the measurement): on the hold-out, flagged depths miss 87.1 ft (Delaware) and 74.1 ft
(Midland) on the median against 50.0 and 39.2 ft unflagged; over 150 ft 25.4 % and 20.2 % against 10.3 % and 4.3 %. It
says "trust this depth less". It does not say the other level is right: 35 % of flagged hold-out wells are nearer the
second level than the stick.

Pad 22309 (Glasscock), as the frame stood at 2023-01-01: LSSH stick 8,132.7 ft, flagged, second level 8,279.9 ft. The
6 LSSH wells drilled after landed at 8,314 to 8,365 ft. On today's frame the same pad's LSSH is direct (8,048.3 ft)
and carries no flag.

## Files

`basin*.csv`, `basin_summary.json`, `dsu_bench.csv.gz`, the pilot files, `generated/`, `backtest/`, `cards/` as in
`cutover-2026-11-17/phase3/`. The cards print the flag in each bench's note.
