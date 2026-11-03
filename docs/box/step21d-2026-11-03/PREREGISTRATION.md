# Step 21d — 2026 Midland prospective test of the step-23 method, all nine groups (PRE-REGISTRATION, DRAFT at gate 21d)

**Status: DRAFT, at gate 21d.** Nothing is frozen until Michael chooses the graduation rule (FINDINGS §6 Q1) and the remaining
gate calls. Then the definition digest and the commit SHA are frozen, and the merge of this file's PR is the freeze.

Nothing is scored. No 2026 Midland well's production volume has been read. The only 2026 facts used are well identities, tags,
first-production dates, locations, laterals, TVDs and the geometry of their neighbours (`cohort_at_draft.csv`). FINDINGS §7
lists exactly what was read.

- **Definition of record:** `box/prospective21.py` `DEFINITION`, SHA-256 pinned in `DIGEST`. `tests/test_box_prospective21.py`
  fails on any edit, and checks the method against step 21 revision 8, D150's Midland curve and D151's tiers and haircut.
- **Commands:** `python -m scripts.box_prospective21 status | snapshot | manifest | oc | score`. `score` refuses until it is
  built (§7).
- **Decisions:** D124 (the prospective test is the only tier route), D125 (the 13d pattern), D149 (record treatments),
  D150 (continuous proximity), D151 (tiers, haircut, this step).

## 1. Why this test

- **It is the only way a Midland group changes tier (D124).** 21c spent every Midland D52 holdout (D151). Without this test a
  provisional Midland bench has no path to validated, and a validated one is never re-checked.
- **It tests what ships, not what was scored.** Step 23 replaces the step-21 proximity table with D150's continuous factor. The
  tiers were earned on the table. This test is the first out-of-time look at the combination that actually publishes.
- **It is frozen before step 23 publishes and before any 2026 Midland outcome is read.**

## 2. The cohort

**Definition:**
- Midland wells (`curated.formation_blueox.basin_blueox = 'midland'`), horizontal, first producing 2026-01-01 … 2026-12-31.
- Real lateral (completed lateral > 0) and a stick.
- Lateral midpoint inside the group's stored record extent (the nine Midland records, step 20).
- `docs/box/exclusions.csv` as it stands at scoring (the harness's load-time filter).

**Draft snapshot** (2026-11-03; first production January to September 2026 so far; FINDINGS §3 has the full-year projection):

| group | tier at freeze (D151) | extent | wells now | packages now | expected judged packages, full year |
|---|---|---|---|---|---|
| MID_WCA_1 | validated | 36 | 350 | 113 | 180 |
| MID_WCB_1 | provisional | 37 | 225 | 81 | 131 |
| MID_WCB_2 | provisional | 38 | 90 | 31 | 47 |
| MID_WCC | provisional | 39 | 4 | 3 | 1 (never judgeable) |
| MID_WCD | validated | 42 | 88 | 35 | 39 |
| MID_MS | provisional | 44 | 114 | 53 | 74 |
| MID_JM | provisional | 45 | 194 | 66 | 124 |
| MID_LSSH | validated | 47 | 252 | 88 | 121 |
| MID_DEAN | provisional | 49 | 110 | 50 | 60 |
| **total** | | | **1,427** | **520** | |

The cohort keeps growing through December and through reporting lag. A cell is judged on packages.

## 3. Which membership governs (the 13d rule, adapted to the Midland)

- **The verdict uses the membership current at SCORING time.** That is `curated.formation_blueox` then, with its 13e
  tag-release id stamped on the score, plus the Midland BOX-only rules of record applied to every 2026 well:
  - **D136 (c):** a WCB_2-tagged well north of the D136 line that lands less than 392 ft below the local WCA_1 band counts as
    WCB_1. Today 14 WCB_2-tagged 2026 wells sit inside the WCB_1 extent north of the line (`d136_candidates.csv`); the depth
    test is applied at scoring.
  - **The step-13b pool-refresh class rule** (`box/pool_refresh`), once the Midland joins step 13 after step 23.
- It applies to both sides of the test: which group each 2026 well tests, and the analog pools the hindcast forecasts it from.
- **The freeze-time tags are a sensitivity, never the verdict:** this file's snapshot, and the pools as frozen at
  `pool-midland-2026-10-31`.
- **A release that merges or splits groups** changes the test's units. The affected groups are re-defined by an amendment
  committed BEFORE any score is read, never after.

## 4. The method (what step 23 ships for the Midland)

- **Base:** step 21 revision 8 at its frozen SHA `5ceadc2` (digest `9780f326`). That is r2 selection (`box_v2s_r2`), the Midland
  rules (lateral band 5,000 ft with no upper bound), Cui & Cross on the Midland panel with the Delaware panel for targets longer
  than their cohort (D148), measured spacing (D119), uptime-free volumes (D63), Df 0.06 / yr (D132), the D57 short-history
  transfer and per-variant F(k).
- **Fold:** the next rolling-origin fold of the step-21 harness at cutoff **2025-12-01**. Analogs, fits and F(k) come from data
  before the cutoff.
- **Proximity (D150, replacing the step-21 table):** oil × level × F_R3 over the well's counting parents. Midland curve
  F_min 0.720, d50 485 ft, k 1.96, a_below = a_above = 0.50, level 1.067 (`box/prox_cont.py` at `77d50a7`, digest `2e8bb5a7`).
  - A well with no counting parent carries the level; single-parent wells get F.
  - Gas and water are untouched (D150 keeps D113's stream rule).
  - **Configuration = the drilled side**, as D150 was fitted and validated and as 21b / 21c scored. A parent is a horizontal
    at least 365 days on production at the well's first production, at least 30 % alongside, within 1,000 ft vertically and
    2,640 ft sideways, permit TVDs dropped, no shielding exemption. The stick-side configuration at the cutoff is reported
    (FINDINGS §6 Q4).
  - **Every cohort well is scored, precedent ignored**, as in 21b / 21c and D150's validation. The wells the shipped gates
    would leave without a forecast (the 21a pattern precedent, the 400-ft same-bench floor, D114's package tier) are counted and
    their bias reported, never the verdict (FINDINGS §6 Q5).
- **Haircut:** WCA_1 oil only, the D102 table **as delivered by the Midland record run** (the D85 pattern). At gate 21c it reads
  0.979 / 0.975 at cum-12 / cum-24. Gate 23 decides whether it is recomputed on the D150 treatment. Every other stream: none.
  - **Why the open item cannot move a verdict:** the haircut is one factor per horizon on every well. Package bias under
    forecasts × h is (1 + b) / h − 1, for the cohort and for every draw behind the interval, so both interval ends and the cohort
    bias move by the same monotone map. The consistency verdict is identical with or without the haircut, or with any recomputed
    value of it (checked numerically, FINDINGS §2). The accuracy route never applies to WCA_1 (it is validated, and keeping
    validated is consistency only).
- **Record-run check:** before any read, the scorer checks the Midland record run's stored spec against this block. A mismatch
  is an amendment committed before the read, never after.
- **Disclosed:** the D150 curve and the D102 haircut are constants fitted on 2019–2024 tuning children with production through
  2026-08-01. That is after the cutoff, but no 2026-first-producing well entered either fit.
- **Grain:** D53 development packages (co-developed within 180 d, overlap ≥ 30 %). Error = Σ actual ÷ Σ forecast − 1
  (negative = forecast HIGH). Bias = mean over packages.

## 5. Verdict, tier consequence and schedule

**Cells:** oil and gas × cum-12 and cum-24. A cell is judged when the full cohort holds at least 30 packages there.

**Consistency (D99), the cell test:** the cohort's package bias lies inside the cell's interval.
- **Interval (proposed, FINDINGS §6 Q2):** P2.5–P97.5 of [bias(draw) − bias(complement)] + bias(all tuning), over 2,000 draws of
  3-mi blocks of the group's 21b tuning packages. The block share is cohort packages ÷ tuning packages; seed 20261103.
- That is D125's subset draw plus the tuning mean's own sampling error. D125's subset interval is reported beside it.
- The reference is the 21b tuning packages pooled over cutoffs 2019–2024, under the §4 treatment. They are pinned in
  `tuning_views.sha256`, together with the links cache the factor is measured on.

**Accuracy (D53 / D58), the cell test:** |package bias| ≤ 10 % AND scale-free spread ≤ the local-offsets benchmark's + 0.05.

**Tier rules:**

| group at freeze | rule | consequence |
|---|---|---|
| provisional | **graduation: ★ chosen at gate 21d** — (a) consistency on every judged cell (D125), or (b) consistency on every judged cell OR accuracy on every judged cell | PASS: proposed for validated at its own gate. A group that passes on accuracy alone ships raw, no haircut, with the cohort line as its disclosure until that gate decides |
| validated | keep: consistency on every judged cell (D99) | any judged cell outside: provisional (D105); diagnose, never re-tune |
| any | no oil cell reaches 30 packages | NOT JUDGED, tier unchanged |

**Reported, never gating:**
- consistency and accuracy for every judged cell under both rules, and the D125 subset interval;
- the no-forecast subset (precedent, 400-ft floor, package tier): counted, bias shown;
- the stick-side configuration at the cutoff, as a proximity sensitivity;
- the freeze-time-tag sensitivity;
- thin-control wells (< 3 local wells within 3 mi);
- laterals > 15,000 ft and the D120 mismatch classes (D149 (6));
- production-sharing vs non-sharing wells;
- **water:** the D109 measured-water read on the cohort (FINDINGS §6 Q3).

**Schedule: one judgment per horizon, on a date fixed now.**

| read | when | status |
|---|---|---|
| cum-6 | wells with ≥ 7 reported months, any time | reported, never judged |
| cum-12 on wells first producing Jan–Jun 2026 | production through 2027-08-01 (~2027-Q3) | reported, never judged |
| **cum-12, full cohort** | the first build with production through ≥ **2028-01-01** (~2028-Q1) | **judged once** |
| **cum-24, full cohort** | the first build with production through ≥ **2029-01-01** | **judged once** |

Each horizon's verdict takes effect at its own judgment. A cum-24 FAIL after a cum-12 PASS demotes.

**Watch items** (reported):
- DEAN's holdout under-forecast (21c: oil +22 / +23 %, gas +29 %; the gas miss is BOX's own).
- WCB_2's tuning-vs-holdout contrast (tuning −6 / −9 %, holdout +5 / +2 % oil).
- WCB_1 / JM / MS gas cum-12 below tuning at 21c.
- MS ships about 6–9 % high on oil, raw (D151).
- The D150 Midland level drifting by fold (C8 1.000 → 0.960).

## 6. What this forbids

- No edit to `DEFINITION` after the freeze. The digest test fails. The membership amendments of §3 and the record-run check of
  §4 are the only sanctioned paths, and both are written before a score.
- No re-tune, no redrawn interval, no moved judgment date. A FAIL means diagnose.
- **A step-17 correction or a later proximity revision does not change this test.** It scores the step-23 method as frozen
  here. A corrected method needs its own prospective cohort (2027).
- Nothing here stores a run, flips a record or writes `box.bench_scope.validation`. Step 23 writes the D151 tiers; a tier
  move from this test is proposed at its own gate.

## 7. The scorer (built later, before it is run)

`score` is not built. The first judged read is about 2028-Q1. When it is built:
1. Commit it before its run (the 16c pattern).
2. Check it on a past cutoff first. The 2024-12-01 fold must reproduce the 21b tuning cells for every group, and the §4
   treatment on the tuning views must reproduce `oc_tuning_cells.csv`.
3. Check the Midland record run's spec against §4 (the record-run check).
4. Then run it once at 2025-12-01 on the judgment date.

Early reads use the same scorer and are labelled "not judged".

## 8. Durability

- The 54 tuning views (`runs/step21b/MID_*`) and the links cache (`runs/step21a/links.pkl`) live only on this laptop. They are
  pinned by hash in `tuning_views.sha256`. Without them the intervals cannot be drawn in 2028. FINDINGS §6 Q6 asks for the
  OneDrive copy (the 13d precedent).
