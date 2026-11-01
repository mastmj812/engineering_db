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
- Tests: eng_db suite 817 passed / 46 skipped; step-21 tests 25 passed (digest pinned at revision 4).
- **Revision 1 (2026-10-31):** same bench ≤ 300 ft + neighbour-pattern precedent (§3.6) — 1,481 sticks to no forecast.

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
The factor used to decide the package tier is the **Delaware D113 table (INTERIM)**. Counts are sticks, not volumes. The table
and bullets below are **as registered**; revision 1 (§3.6) changes them, and `prox_by_group.csv` / `index.html` now carry the
revision-1 outcomes.

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
  floor 35 of 117 keys fill at k1, 43 / 121 at k2, 44 / 94 at k3, 33 / 43 at k4 (revision 1's 300-ft cap: 34 / 125, 42 / 122,
  43 / 95, 33 / 44; multi-parent children unchanged at 1,884); thin configurations fall to the class rungs, as
  in the Delaware.
- Hash note (no change): 13d's pin of `haircut_table_candidate.csv` (0a62beb8…) is the RAW (CRLF) bytes, while
  `prospective16.sha256_file` normalises to LF (382d2e08…). Same file, unchanged since e0845b1; a 2028 check through that helper
  would read a false mismatch.

### 3.6 Revision 1 (Michael, 2026-10-31, card 13): which sticks get a forecast

Card 13 is an MS stick between two producing MS wells (667 / 866 ft either side), a JM 120 ft below at 159 ft, a US 367 ft above
and three LSSH below — one 2024 Diamondback development. D114 passed it on `MS>mixed` (82 drilled wells), but that key is the
bench alone: 81 of the 82 had one MS neighbour plus a deeper one; **none** had a neighbour above, and none sat as tight. Michael:
a stick like this will never be drilled and has no analogs to measure a haircut from, so it should not be forecast. Two rules,
Midland only (`box/step21_prox.py`, revision row in `PREREGISTRATION.md`); the Delaware record keeps D114 until it is revised
from what the Midland shows:

- **Same bench = same BOX bench AND ≤ 300 ft vertically** (was 1,000 ft, a leftover of the exposure screen). Drilled same-bench
  pairs: median 48 ft, p99 334 ft; 214 sticks had a same-bench neighbour > 300 ft off (WCC and JM sticks with suspect tags).
  Farther ones are classed by depth (below / above) and need that envelope.
- **Neighbour-pattern precedent, on top of D114.** A stick with 2+ neighbours is forecast only when ≥ 30 drilled Midland wells of
  its bench, also with 2+ neighbours, sit in its pattern: same-bench neighbours on none / one side / both sides, + one above, +
  one below. The pattern's package count is reported, not gated (gating it on the interim Delaware factor would refuse 1,751 more,
  mostly "a well above and below, none beside" — not what was approved).

Drilled Midland wells with 2+ neighbours, by pattern (`prox_precedent_pattern.csv`; precedent floor 30):

| pattern | MS | JM | LSSH | DEAN | WCA | WCB_1 | WCB_2 |
|---|---|---|---|---|---|---|---|
| one side + below | 80 | 56 | 426 | 17 | 321 | 71 | 10 |
| none beside + below | 130 | 86 | 378 | 38 | 273 | 32 | 3 |
| none beside + above + below | 1 | 40 | 18 | 69 | 60 | 37 | 11 |
| one side + above + below | 0 | 23 | 33 | 5 | 87 | 37 | 4 |
| both sides | 3 | 2 | 32 | 0 | 74 | 33 | 6 |
| both sides + below | 1 | 2 | 31 | 1 | 30 | 2 | 0 |
| both sides + above | 0 | 0 | 2 | 0 | 21 | 16 | 2 |
| both sides + above + below | 0 | 0 | 3 | 2 | 15 | 2 | 1 |

**Effect (sticks; as registered → revision 1; `prox_revision1.csv`):** haircut 12,407 → 10,897; no forecast 1,523 → 3,016
(4.6 % → 9.1 %). 1,481 move haircut → `no_forecast_pattern`. The 300-ft cap moves 54 more: 27 haircut → no forecast on D114
itself, 14 no forecast → as-is, 9 single neighbour → unexposed, 3 haircut → as-is, 1 no forecast → haircut.

| group | no_forecast_pattern | main patterns |
|---|---|---|
| MID_LSSH | 370 | none beside + above + below 263, both sides + above + below 105 |
| MID_WCB_1 | 363 | both sides + above 273 |
| MID_JM | 333 | one side + above + below 211, both sides + above + below 75 |
| MID_MS | 146 | **both sides + below 109** (MS drilled between two MS producers: 3 times, ever), both sides + above + below 6 |
| MID_WCB_2 | 119 | none beside + above + below 47 |
| MID_WCA_1 | 108 | both sides + above + below 73, both sides + above 35 |
| MID_DEAN | 42 | one side + above + below 19 |
| MID_WCC / MID_WCD | 0 | their multi-neighbour sticks already fail D114 |

DEAN (D143): forecast share in the loop's addition 86.8 % → 83.5 %, body 96.5 % → 94.1 %. Most DEAN additions sit in "none
beside + above + below" (69 drilled precedents), so they still pass.

Cards: the same 46 sticks re-rendered (`prox_cards/cards.html`; as-registered outcomes kept in `cards_sample_r0.csv`); four
change — #13 (MS, both sides + above + below, 0 precedents) and #15 (WCB_2, one side + below, 10) and #32 (DEAN, one side +
above, 8) → no forecast; #39 (WCC) → single neighbour once a same-tag well 300+ ft off is classed by depth.

### 3.7 Revision 2 (Michael, 2026-11-01): conflict sticks are not drillable (D145)

The population drops the 475 reconciliation-`conflict` sticks: 33,016 → **32,541** (DEAN 39, JM 73, LSSH 76, MS 31, WCA_1 114, WCB_1 118, WCB_2 7, WCC 6, WCD 11). Their revision-1 outcomes were haircut 243, no forecast (pattern) 74, as-is unexposed 69, no forecast (precedent) 51, single neighbour 38. After revision 2: haircut 10,654; no forecast 2,891 (**8.9 %**: precedent 1,472, package 12, pattern 1,407); as-is 18,996 (`prox_by_group.csv`). Nothing on the drilled side moves. Cards #10, #13, #22 and #30 were conflict sticks and now read "excluded" (numbering kept). The Tables above §3.6 stay as registered.

### 3.8 Revision 3 (Michael, 2026-11-01, cards 14 / 18): same bench by depth, tag-free precedent key

Same bench = within 150 ft vertically whatever the tag; D114 keyed on the stick's bench × neighbour class. On 32,541 sticks: haircut 10,654 → 10,782; no forecast 2,891 → **2,763 (8.5 %)**: pattern 2,173, precedent 584, package 6 (`prox_by_group.csv`). 2,419 sticks change outcome; the total barely moves, the mix does:

| group | no forecast r2 | r3 |
|---|---|---|
| DEAN | 13.9 % | **27.3 %** |
| JM | 12.8 % | 11.8 % |
| LSSH | 6.8 % | 4.0 % |
| MS | 13.3 % | **3.9 %** |
| WCA_1 | 2.8 % | 6.8 % |
| WCB_1 | 7.8 % | 10.0 % |
| WCB_2 | 16.5 % | 16.4 % |
| WCC / WCD | 43.5 / 3.6 % | unchanged |

- DEAN: LSSH / WCA_1 wells within 150 ft now count beside a DEAN stick, so more DEAN sticks are flanked (both sides + above + below has 2 drilled DEAN precedents). D143: loop-addition sticks forecast 83.5 % → **69.2 %**, generated body 94.1 % → 85.7 %.
- MS: the old key split MS precedents by the neighbour's tag (MS>topfill>JM had 19); pooled by class they clear 30.
- Stick-TVD cost (deferred, Michael): a depth rule trusts the stick's Novi TVD. 231 of the 2,419 changed sticks sit > 150 ft (median) from their same-tag neighbours — e.g. card 41, a WCB_1 stick 226–297 ft below the WCB_1 wells either side, now "none beside + above". Card 18 is the same shape.
- Cards changed: #14 → no forecast (both sides + above + below, 2 precedents); #18 / #41 → two neighbours above, haircut (33); #19 / #21 / #24 / #25 / #26 → haircut (pooled key ≥ 30; #21 is the bad-TVD JM stick); #27 / #31 / #34 → no forecast (pattern); #28 / #29 → no forecast (DEAN>topfill 29 < 30); #20 pattern only.

### 3.9 Revision 4 (Michael, 2026-11-01, card 8): every existing producer is a stick's parent

2,298 producers under 12 months on at 2026-08-01 sit alongside 3,132 sticks; they now count. On 32,541 sticks: unexposed 15,579 → 14,271; single neighbour 3,417 → 3,444; haircut 10,782 → 11,409; no forecast 2,763 → **3,417 (10.5 %)**: pattern 2,777, precedent 630, package 10. No forecast by group (r3 → r4): DEAN 27.3 → 31.1 %, JM 11.8 → 15.3, LSSH 4.0 → 5.5, MS 3.9 → 5.8, WCA_1 6.8 → 8.3, WCB_1 10.0 → 12.1, WCB_2 16.4 → 19.2, WCC 43.5 → 45.8, WCD 3.6 → 4.5. The new no-forecast sticks are mostly flanked: both sides + below 181, both sides + above + below 165, both sides + above 113. D143: DEAN loop addition forecast 69.2 → **65.9 %**, body 85.7 → 80.0 %. Precedents and factors are unchanged (drilled side).

Cards changed: #2 (LSSH) and #4 (WCA_1) unexposed → single neighbour (still as-is); #8 (MS) single → no forecast (both sides + below, 1 precedent); #21 (JM) and #40 (LSSH) haircut → no forecast (pattern). Card tables mark a young neighbour "counts (< 12 months today)".

Found while measuring (reported, nothing changed): 619 sticks have a same-bench producer ≤ 330 ft sideways and ≥ 50 % alongside (184 of them under 12 months on); 83 within 200 ft. Drilled wells sit that close to a same-bench neighbour 4.4 % (330 ft) / 1.4 % (200 ft) of the time — the 200-ft group looks like already-drilled slots the reconciliation missed.

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
6. **D114 mixed precedent — DONE as revision 1 (§3.6), Midland only.** Same bench ≤ 300 ft; neighbour-pattern precedent on top of
   D114. Open: whether the pattern's PACKAGE count should also gate (it would refuse 1,751 more on the interim factor — better
   decided on the Midland factor at 21b). The Delaware is revised later from the Midland result.
7. **The 46 proximity cards** (`prox_cards/cards.html`, re-rendered under revision 1) — your review, before the freeze.

**Flags (no action taken):** D129's "scored against the r2 band … with its own acceptance" vs D134 C (one variant, classes
reported) — the pre-registration follows D134 C. Every Midland `box.bench_scope` row reads `validation = 'validated'` (the column
default) though no Midland tier exists; step 23 writes it from 21c. The 13d table-hash convention (§3).

**Gate 21a** = your answers to 1–5 (6–7 inform), any revision committed with its row in the table, then the digest stamped and
the SHA frozen in `PREREGISTRATION.md` §11.
