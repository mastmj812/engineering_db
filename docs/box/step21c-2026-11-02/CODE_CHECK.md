# BOX step 21c — the new code checked against PREREGISTRATION §5–§7 as written (the 16c pattern)

Written and committed 2026-11-02 BEFORE any holdout run started and before any holdout number existed. The contract is the frozen
pre-registration (`docs/box/step21a-2026-10-31/PREREGISTRATION.md` + `box/step21.DEFINITION`, revision 8, digest `9780f326`,
frozen SHA `5ceadc2`) and gate 21b (D149, `docs/box/step21b-2026-11-01/GATE_21B.json`).

## Why there is a holdout re-run at all (Michael, 2026-11-02: option A)

- The 21b harness runs (`runs/step21b/<group>/`) carry **no** holdout packages. `box/acceptance.run` keeps
  `package_held_out == score_holdout` before any prediction, so a tuning run never forecast a held-out well. Checked on the
  saved views: every row `package_held_out = False`.
- The frozen `run()` refuses `step16 and score_holdout` (`box/acceptance.py:396`, a Delaware step-16 guard, D118). The Midland
  record variant `mid_r2` exists only on the `--step16` path. The old `--score-holdout` path predicts `box_v2`, not the
  registered treatment.
- **Option A (approved):** `scripts/box_step21c_harness.py` replaces `box.acceptance.run` with the frozen `run()` compiled from
  its own source **minus exactly those two lines** (`box/step21c.unguarded_run`), then calls the 21b months observer unchanged.
  `tests/test_box_step21c.py` pins (a) the sha256 of the frozen `run()` source, (b) the diff = the two guard lines removed and
  nothing else, (c) that the lifted function reaches the next check (`fold`) and resolves names in `box/acceptance`.
- No file of `box/`, `scripts/` or `dealintake/` that exists at `5ceadc2` is modified; 21c adds new files only (the frozen
  check passes "A" files and lists them in each `run.json`).

## Paragraph by paragraph

| prereg | text | 21c code | check |
|---|---|---|---|
| §3 | actuals pinned through 2026-08-01; package grain; D52 holdout as frozen | the §10 command verbatim + `--score-holdout --holdout-once`; packages and holdout blocks by the frozen harness | as written |
| §4 | `mid_r2p` = `mid_r2` × the Midland proximity factor, multi-parent, oil only | `box/step21b.record_factor` on the frozen 21b table (`prox_factor_table.csv`, reproduced byte-identical first), production's lookup (Michael's 21b answer) | as written |
| §5 | "Holdout time: walk-forward factors from TUNING cells only (D58)" | `box/acceptance.apply_walk_forward(holdout cells, holdout views, history = the group's TUNING mid_r2p cells)` — the path `box_v2_wf` uses on a holdout. The harness's own `mid_r2_wf` on the holdout run (history = None in the step-16 branch → holdout cells) is never read. Identity table: every holdout haircut vs the 21b tuning log | as written |
| §5 | record treatment per group, D106 guard per stream | read from `GATE_21B.json` (WCA_1 / WCB_1 wf oil + r2p gas; MS wf both; LSSH, JM, WCB_2, WCD, DEAN r2p both; WCC provisional) | as decided at gate 21b |
| §5 | "Production (step 23): D102 — tuning + holdout cells merged per cutoff, then the ≥ 30 floor; the D92 rate shape; the 9c guard" | `box/step21c.d102_table` (`box/production.merge_cells_by_cutoff`, then `haircut_table`'s formula per horizon) + `box/step21b.guard` (reversal > 0.01; median D92 g(48) in [0.6, 1.2]) on tuning + holdout scored-well months | as written; computed for every group, marked *applies* only for a wf stream of a validated group |
| §6 | cells = horizons whose pooled holdout cell under the record treatment reaches 30 packages; oil AND gas at each | count = pooled holdout packages with a scored oil cum-k under the record (oil) treatment; cells = oil + gas at those horizons. Same horizon rule the 21b frozen file used (oil record treatment). Frozen file's `d99_cell` flag (an expectation) reported beside the actual | as written; disclosed: gas cells take oil's horizons |
| §6 | intervals frozen at gate 21b, sha256, never redrawn | `box/step21c.check_frozen` refuses unless both files hash to `GATE_21B.json`; rows of the record treatment (`frozen_rows`: LSSH reads the `mid_r2p` alternative rows drawn for exactly that move) | as written |
| §6 | PASS = every judged cell inside, ≥ 1 oil cell; ±10 %, scale-free spread, per-cutoff reported only; FAIL = diagnose, never re-tune | `box/holdout9b.pooled_cells` / `verdict` (step 9b / 15, unchanged); `per_cutoff`; no knob exists in 21c code | as written |
| §6 | tiers: validated = PASS; provisional = FAIL, no cell, **or moved at the tuning gate** | `tier()` = PASS → validated, else provisional. **LSSH (moved wf → r2p at gate 21b) is NOT auto-classed**: the §6 vs §5 / step-15 WCB_1 conflict is flagged at gate 21c, both readings shown | flagged, not resolved |
| §7 | water holdout once; a cell with ≥ 10 measured packages consistent inside its frozen interval; validated water = validated oil + every tuning cell passes + every holdout cell consistent | `scripts/box_step21c_water.py` = `scripts/box_step21b_water.run_group` with two changes (holdout views; inverted held-out check; diff in this commit's history); judged by `box/water11_report.package_sums` / `_bias` against `frozen_water.csv` | as written; water stays provisional on every group by the tuning half (D149 (5)) whatever the holdout shows |

## Order enforced by `scripts.box_step21c`

`runs` (per group: frozen check + nightly idle at start, frozen check at end, one-time: a completed run is never re-run; the
harness log, which prints box_v2 holdout cells, is not opened unless rc ≠ 0) → `reproduce` (21b scorer on the 21b runs must
equal the committed 21b tables byte for byte, both frozen sha256 included) → `water` → `judge` (refuses without a clean
reproduce; refuses if its verdict file exists: read once).
