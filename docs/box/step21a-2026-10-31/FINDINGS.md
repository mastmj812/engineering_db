# BOX step 21a — Midland pre-registration: evidence and gate 21a (2026-10-31) — AT GATE 21a

Read-only. Nothing was forecast, scored or stored; no warehouse write. Branch `claude/box-step21a-prereg`.

- **The pre-registration:** `PREREGISTRATION.md` (text) + `box/step21.DEFINITION` (the record, digest-pinned by
  `tests/test_box_step21.py`).
- **Review surface:** `index.html` (every table below with n and filters), `dean_outcomes.png`.
- **Proximity examples for your review:** `prox_cards/cards.html` — 46 cards (strike section square to the stick, sign rule v2,
  envelopes drawn; plan view; parent table with api10 / well / operator / BOX bench / tag / months on / dz / gap / overlap).
  Verdicts (accept / reject + note) go in `prox_cards/cards_sample.csv`. Built by `python -m scripts.box_step21a_cards`
  (seed 20261031).
- **Builder:** `python -m scripts.box_step21a pool | evidence | render` (`box/step21_evidence.py`, DB-free tests). Run
  2026-10-31, actuals through 2026-08-01, ~18 min (proximity links ~12 min).
- **Harness:** `box/acceptance.BENCH_SPECS` gains the nine `MID_<bench>` groups (basin `midland`); their `--step16` path predicts
  `mid_r2` (run 19's r2 rules, lateral band 5,000 ft → no upper bound) and its linear-per-ft twin. Delaware specs unchanged.
- **Pool:** `docs/box/pool-midland-2026-10-31/` = copies of the step-20 sets of record + `MANIFEST.json` (sha256 + source commit).
- Tests: eng_db suite 807 passed / 46 skipped; the digest pin waits for the gate (§5).

Grain is stated per table: packages, wells or sticks. No bias appears anywhere in this step.

## 1. What the package counts allow (counts only; the D52 holdout counted, never read)

Packages per group, pooled over cutoffs (`judgeability.csv`, `package_counts.csv`). "wf" = only the cutoffs that carry a
walk-forward haircut (≥ 2 earlier judged tuning cells). The rules of `PREREGISTRATION.md` §5–§6 applied to these RAW counts give
the expectation below; the final values come from 21b's SCORED counts (lower at early cutoffs, step-15 §2).

| group | tuning pkgs, cum-12 / 24 / 36 | holdout, cum-12 / 24 / 36 | holdout over wf cutoffs, cum-12 / 24 | expected record | D99 cells | route |
|---|---|---|---|---|---|---|
| MID_WCA_1 | 1,020 / 877 / 519 | 261 / 215 / 130 | 173 / 127 | `mid_r2p_wf` | 12, 24, 36 | holdout |
| MID_WCB_1 | 767 / 646 / 401 | 223 / 181 / 110 | 147 / 105 | `mid_r2p_wf` | 12, 24 | holdout |
| MID_LSSH | 806 / 695 / 430 | 221 / 181 / 116 | 138 / 98 | `mid_r2p_wf` | 12, 24 | holdout |
| MID_JM | 401 / 313 / 192 | 117 / 86 / 52 | 83 / 52 | `mid_r2p_wf` | 12, 24 | holdout |
| MID_MS | 386 / 307 / 186 | 121 / 86 / 45 | 93 / 58 | `mid_r2p_wf` | 12, 24 | holdout |
| MID_WCB_2 | 229 / 198 / 118 | 59 / 48 / 28 | **41 / 30** | `mid_r2p_wf` (marginal) | 12, 24 | holdout |
| MID_DEAN | 218 / 163 / 92 | 52 / 37 / 23 | 35 / 20 | `mid_r2p` | 12, 24 | holdout |
| MID_WCD | 194 / 148 / 76 | 47 / 37 / 19 | 20 / 10 | `mid_r2p` | 12, 24 | holdout |
| MID_WCC | 50 / 43 / 28 | **7 / 6 / 5** | 0 / 0 | `mid_r2p` | none | **provisional by construction** |

- Eight of nine groups can be judged on their own holdout at cum-12 + cum-24 (WCA_1 also cum-36): D131's "validated where data
  allow" is reachable everywhere except WCC, which D131 already targeted as provisional (its extent is 644 sq mi).
- WCB_2's walk-forward holdout sits exactly at the floor (30 at cum-24); with 21b's scored counts it will most likely fall to
  `mid_r2p` by the rule, not by choice.
- Measured-water packages (`water_packages_pooled.csv`), cum-12, tuning / holdout: WCA_1 227 / 67, WCB_1 202 / 61, LSSH 190 / 64,
  JM 96 / 24, MS 90 / 33, WCB_2 68 / **7**, DEAN 55 / 13, WCD 42 / **6**, WCC 14 / **3**. Under D109 (a holdout cell needs ≥ 10
  packages) WCB_2, WCD and WCC water cannot validate, whatever their oil does.

## 2. Long laterals (D129 / D134 C)

**The Midland loses much less oil per foot with length than the Cui & Cross (Delaware WCA) curve says.** Observed 12-month oil
per 1,000 ft relative to the 7,500–10,000 ft class; producers first-producing 2016-01 … 2025-07 in TUNING blocks only; within 3-mi
block × first-production-year cells; 90 % block bootstrap; reported lateral (`per_ft_by_length.csv`):

| lateral class, ft | wells (all 9) | observed [90 %] | Cui implies | Wolfcamp (5) | Spraberry (4) |
|---|---|---|---|---|---|
| 5,000–7,500 | 1,352 | 1.004 [0.987–1.019] | 1.099 | 1.012 | 0.988 |
| 10,000–12,500 | 5,897 | 0.991 [0.979–1.002] | 0.949 | 0.987 | 0.998 |
| 12,500–15,000 | 1,583 | 0.986 [0.977–0.996] | 0.916 | 0.989 | 0.983 |
| 15,000–17,500 | 1,038 | 0.983 [0.971–0.995] | 0.882 | 0.981 | 0.985 |
| 17,500–20,000 | 76 | 0.916 [0.872–0.957] | 0.848 | 0.955 | 0.880 |

- Per-ft oil is flat within ~2 % from 5,000 to 17,500 ft; only the thin 17,500-ft+ tail degrades (−8 %, 76 wells). D129
  anticipated "flatter"; the size is the news. Translating with Cui puts a 16,000-ft PUD drawn from a 10,000–12,500-ft cohort
  ~6 % LOW against what the data show, and a 6,000-ft PUD from the same cohort ~15 % HIGH.
- Exposure: 13–18 % of in-extent sticks per group are > 15,000 ft and 20–25 % > 12,500 ft (`sticks_by_length.csv`).
- Removing the 15,000-ft cap admits 29–537 long producers per pool (`reach_oil.csv`) and moves the oil reach ring on 2–560 sticks
  per group (WCD 550, LSSH 560, DEAN 297); median 10th-analog gain 0.0–0.26 mi.
- **Gate question 5** (§5). It bears on D129 / D134 C, which are settled, so nothing was changed.

## 3. Proximity on Midland producers (D112–D116 pattern; D143 DEAN)

Producer universe 31,051 Midland horizontals; 24,729 drilled children (≥ 2016) with 301,890 links; 33,016 in-extent undrilled
sticks (D117: PUD + RES) with 273,693 links; reference date 2026-08-01. Precedent = Midland drilled children (60 bench-pair keys).
The factor used to decide the package tier is the **Delaware D113 table (INTERIM)**. Counts are sticks, not volumes
(`prox_by_group.csv`).

| group | sticks | unexposed | single parent | haircut | no forecast: precedent / package | multi-parent % |
|---|---|---|---|---|---|---|
| MID_WCA_1 | 5,235 | 2,197 | 575 | 2,413 | 50 / 0 | 47.0 |
| MID_WCB_1 | 5,595 | 2,482 | 673 | 2,351 | 89 / 0 | 43.6 |
| MID_WCB_2 | 856 | 412 | 146 | 274 | 24 / 0 | 34.8 |
| MID_WCC | 698 | 280 | 98 | 0 | **320** / 0 | 45.8 |
| MID_WCD | 3,600 | 3,216 | 250 | 0 | 134 / 0 | 3.7 |
| MID_MS | 4,191 | 1,846 | 448 | 1,477 | **420** / 0 | 45.3 |
| MID_JM | 4,161 | 1,510 | 346 | 2,100 | 205 / 0 | 55.4 |
| MID_LSSH | 7,314 | 3,056 | 749 | 3,381 | 128 / 0 | 48.0 |
| MID_DEAN | 1,366 | 634 | 168 | 411 | 141 / 12 | 41.3 |
| **all** | **33,016** | 15,633 | 3,453 | **12,407** | **1,511 / 12** | **42.2** |

- **Stacked multi-parent development is the Midland norm, as the plan expected:** 42 % of in-extent sticks are multi-parent (the
  Delaware run-19 lineage: 35 % of 51,419 PUDs). The precedent gate removes far fewer here, 4.6 % vs 16 %, because the Midland has
  drilled the same stacks many times (WCA>mixed 728 precedents, LSSH>mixed 552, LSSH>topfill>WCA 215; `prox_precedent.csv`).
- WCC loses 46 % of its in-extent sticks to precedent (WCC>same>WCC has 4 drilled precedents); MS 10 % (MS>topfill>JM 19).
- **D143 (DEAN): your expectation is not borne out at the precedent gate.** In the loop's addition 937 of 1,080 sticks (86.8 %)
  are still forecast, vs 276 of 286 (96.5 %) in the generated body; 143 addition sticks fail precedent (DEAN>underfill>LSSH 84,
  DEAN>topfill>WCB_1 28, …) or the package tier (DEAN>topfill>WCA 11). The reason is D114's **mixed** key: a DEAN stick under
  developed LSSH AND over developed WCA_1 / WCB is "DEAN>mixed", pooled at bench level, and 102 drilled DEAN wells have some mixed
  configuration. 361 addition sticks pass that way and are haircut, not dropped (`prox_dean.csv`, `dean_outcomes.png`). Cards 14
  and 30–33 show it; card 30 is a DEAN stick 7–87 ft below SM Energy's Katie LSSH wells — effectively an LSSH slot.
- Bench-label sensitivity: reading warehouse tags instead of BOX membership relabels 580 producers and changes 84 of 33,016 stick
  outcomes (0.25 %; `prox_sensitivity_tag.csv`).
- A Midland factor table can be fit (`prox_ladder_fill.csv`): 11,923 tuning-window children inside the extents (tuning blocks
  only), 1,884 multi-parent (WCA_1 609, LSSH 566, WCB_1 257, MS 137, JM 135, DEAN 101, WCB_2 63, WCC 11, WCD 5). At the 30-child
  floor 35 of 117 keys fill at k1, 43 / 121 at k2, 44 / 94 at k3, 33 / 43 at k4; thin configurations fall to the class rungs, as
  in the Delaware.
- Hash note (no change): 13d's pin of `haircut_table_candidate.csv` (0a62beb8…) is the RAW (CRLF) bytes, while
  `prospective16.sha256_file` normalises to LF (382d2e08…). Same file, unchanged since e0845b1; a 2028 check through that helper
  would read a false mismatch.

## 4. Water reach (D107 / D133)

Measured = `curated.water_data_quality` `measured`; reach = the 10th nearest measured-water producer (circle) from each
in-extent stick (`reach_water.csv`).

| group | measured / eligible pool | 10th measured, mi P10 / P50 / P90 | thin / fallback | top operator's share of the 10 nearest, median | pool's top measured operator |
|---|---|---|---|---|---|
| MID_WCA_1 | 1,560 / 6,513 (24 %) | 2.3 / 4.4 / 10.6 | 0 / 0 | 0.8 | Diamondback 29 % |
| MID_WCB_1 | 1,321 / 4,719 (28 %) | 2.1 / 4.7 / 10.4 | 0 / 0 | 0.8 | Diamondback 25 % |
| MID_WCB_2 | 317 / 1,560 (20 %) | 2.4 / 5.1 / 10.9 | 0 / 0 | 0.7 | SM Energy 33 % |
| MID_WCC | 72 / 422 (17 %) | 4.5 / 8.3 / 17.3 | 0 / 0 | 0.5 | Apache 38 % |
| MID_WCD | 175 / 760 (23 %) | 4.7 / 11.6 / 23.6 | 0 / 0 | 0.6 | Diamondback 35 % |
| MID_MS | 461 / 1,513 (30 %) | 2.6 / 5.7 / 11.2 | 0 / 0 | 0.8 | ConocoPhillips 39 % |
| MID_JM | 390 / 1,499 (26 %) | 2.9 / 5.2 / 9.5 | 0 / 0 | 0.9 | Diamondback 39 % |
| MID_LSSH | 1,500 / 5,118 (29 %) | 2.1 / 5.2 / 10.6 | 0 / 0 | 0.8 | ConocoPhillips 28 % |
| MID_DEAN | 199 / 818 (24 %) | 7.1 / 13.4 / 23.4 | 0 / 0 | 0.5 | Diamondback 35 % |

- Every stick closes 10 measured analogs inside 50 mi (no thin, no fallback); WCD and DEAN reach 12–13 mi at the median.
- **Concentration is the D133 caveat, and sharper locally than step 18's 26–40 % pool share:** a typical stick's 10 nearest
  measured analogs are 70–90 % one operator on the big benches (Texas measured water = whoever reports it), so the water curve
  there is that operator's water. Reported per D133, not a rule.

## 5. Gate 21a — your calls (recommendation first)

1. **Proximity factor source — rec: Midland TUNING children only** (`PREREGISTRATION.md` §4). 1,884 multi-parent tuning children
   fill the class rungs; the holdout stays unread; the Delaware table is reported as a sensitivity. Alternative: carry the Delaware
   D113 table over unchanged (D134's "transfer, don't re-derive" read literally).
2. **Proximity bench label — rec: BOX membership** (580 producers relabelled; 84 stick outcomes move). Alternative: warehouse tags,
   as the Delaware study read them.
3. **Record-treatment rule (§5) — rec: confirm as written.** Expected: `mid_r2p_wf` WCA_1 / WCB_1 / LSSH / JM / MS (WCB_2
   marginal); `mid_r2p` DEAN / WCD; WCC provisional by construction.
4. **Actuals pin 2026-08-01 — rec: confirm.**
5. **Lateral translation on the Midland (bears on D129 / D134 C — your call; nothing changed).** §2: per-ft oil is flat within
   ~2 % from 5,000 to 17,500 ft, where Cui implies 1.10 → 0.88. Both options stay ONE variant, and the harness computes both in 21b:
   - (a) keep Cui as decided; the 21b length classes measure its bias, disclosed;
   - (b) **rec:** make the linear-per-ft twin (`mid_r2_lin`, same cohort) the Midland record and report Cui as the twin. The
     evidence was read on tuning blocks before any score, so this is the time to choose. The 17,500-ft+ tail (−8 %, 1–3 % of
     sticks) is disclosed. (b) needs a revision row and amends D129's "through Cui".
6. **D143 / D114 mixed precedent (informs, doesn't block 21a).** DEAN's loop additions mostly pass on a bench-level "DEAN>mixed"
   precedent. Judge it on the cards; if a mixed precedent should have to match the parent benches, that is a D114 amendment for all
   groups in both basins — its own step.
7. **The 46 proximity cards** (`prox_cards/cards.html`) — your review, before the freeze.

**Flags (no action taken):** D129's "scored against the r2 band … with its own acceptance" vs D134 C (one variant, classes
reported) — the pre-registration follows D134 C. Every Midland `box.bench_scope` row reads `validation = 'validated'` (the column
default) though no Midland tier exists; step 23 writes it from 21c. The 13d table-hash convention (§3).

**Gate 21a** = your answers to 1–5 (6–7 inform), any revision committed with its row in the table, then the digest stamped and
the SHA frozen in `PREREGISTRATION.md` §11.
