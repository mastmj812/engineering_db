# BOX step 21d — Midland prospective pre-registration, FINDINGS (AT GATE 21d)

> **AT GATE 21d.** The draft definition is `box/prospective21.py` (digest pinned at this commit, re-pinned once at the gate) and
> `PREREGISTRATION.md`. Gate 21d = Michael chooses the graduation rule (§6 Q1) and answers Q2–Q6, then the digest and the commit
> SHA are frozen. Nothing is scored, stored or flipped. No 2026 Midland production volume was read (§7).

Bias = Σ actual / Σ forecast − 1 per package, mean over packages, so **negative = BOX over-forecasts**. Grain = D53 packages.
Every operating characteristic below is computed on the **21b TUNING packages only** (wells first producing before 2025-12-01,
holdout blocks dropped by the harness before the views were written).

## 1. What exists and how to check it

| file | what |
|---|---|
| `box/prospective21.py` | the definition of record (`DEFINITION`, `DIGEST`), the cohort query (identities only, column allowlist) |
| `tests/test_box_prospective21.py` | digest pin; method = step 21 rev 8 + D150 Midland curve + D151 tiers / haircut; no volume column in the query; earlier frozen digests untouched; the haircut invariance |
| `scripts/box_prospective21.py` | `snapshot` (read-only DB), `status`, `manifest`, `oc`, `score` (refuses) |
| `scripts/box_prospective21_oc.py` | the operating characteristics (DB-free) |
| `PREREGISTRATION.md` | the test as it will be frozen |
| `cohort_at_draft.csv`, `cohort_by_month.csv`, `d136_candidates.csv`, `snapshot.json` | the 2026 cohort (and the 2025 reference cohort) as identities, packages and proximity configuration |
| `judgeability.csv` | expected judged packages per group (§3) |
| `oc_groups.csv`, `oc_vintage.csv`, `oc_tuning_cells.csv`, `oc_factor_identity.csv`, `oc_meta.json` | §4–§5 |
| `rules_on_21c_holdout.csv` | both rules on the committed 21c holdout cells (§5) |
| `tuning_views.sha256` | the 54 tuning views + the links cache the intervals are drawn from (§6 Q6) |

Check it:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_box_prospective21.py
.\.venv\Scripts\python.exe -m scripts.box_prospective21 status
.\.venv\Scripts\python.exe -m scripts.box_prospective21 oc --runs C:\Users\MichaelMast\Projects\engineering_db\runs\step21b --links C:\Users\MichaelMast\Projects\engineering_db\runs\step21a\links.pkl
```

The `oc` run takes about 20 minutes and reproduces every number below (fixed seeds). It refuses unless two identities hold:
- **The D150 factor reproduces 24a.** On the committed 24a Midland frame it finds 5,791 exposed children of 8,834 scored,
  exactly `summary_midland.json`.
- **The views are 21b's.** Raw `mid_r2` pooled tuning bias equals 21b `pooled.csv` on every group and cell (|diff| ≤ 1e-9).

## 2. The method under test, and the D102 open item

**Under test = what step 23 ships for the Midland.** That is the step-21 method at revision 8 (`5ceadc2`), the D149 record
treatments as amended by the D151 tiers, and D150's continuous proximity factor in place of the 21 table. The Midland curve is
R3 per-side product, F_min 0.720, d50 485 ft, k 1.96, a = 0.50, level 1.067. Oil only; single-parent wells get F; unexposed
wells carry the level. D125's pattern, D150 and D151 agree on this; the plan's 21d bullet states the same combination.

**The WCA_1 D102 haircut open item cannot move a 21d verdict.** The haircut is one factor per horizon on every well. Under
forecasts × h, a package's error becomes (1 + e) / h − 1, so the mean over packages maps the same way, for the cohort and for
every draw behind the interval. Both interval ends and the cohort bias move by one monotone map, and inside / outside cannot
change. The `oc` run checks it on WCA_1's real intervals (max |mapped − direct| interval end 2e-16) and the test pins it.
- The accuracy route never touches WCA_1: it is validated, and keeping validated is consistency only.
- So the pre-registration names the haircut "as delivered by the Midland record run" (the D85 pattern) and stays valid
  whether gate 23 keeps 0.979 / 0.975, recomputes it on D150, or drops it.
- **Gate 23 still owes the decision** (D151). 21d does not make it.

**Flag for gate 23 (not decided here): the D150 level moves some tuning biases.** On the tuning packages, the shipped
treatment reads (`oc_tuning_cells.csv`):

| group | oil cum-12: raw → shipped | oil cum-24: raw → shipped | gas cum-12 / 24 | tuning packages (oil 12 / 24) |
|---|---|---|---|---|
| WCA_1 | −4.9% → **−2.2%** | −5.3% → **−2.3%** | +4.9% / +8.4% | 1019 / 876 |
| WCB_1 | −2.9% → **−3.6%** | −3.4% → **−4.2%** | +2.9% / +4.3% | 760 / 639 |
| WCB_2 | −7.6% → **−9.2%** | −10.3% → **−12.0%** | +2.9% / +4.4% | 228 / 197 |
| WCC | −9.2% → **−10.7%** | −17.0% → **−18.4%** | −0.5% / −7.1% | 50 / 43 |
| WCD | −7.5% → **−11.2%** | −7.9% → **−11.5%** | −1.8% / +11.8% | 192 / 145 |
| MS | −6.1% → **−7.2%** | −8.9% → **−10.0%** | +1.1% / −0.4% | 390 / 308 |
| JM | +1.6% → **+1.2%** | +10.8% → **+10.2%** | +1.3% / +6.9% | 400 / 312 |
| LSSH | −4.8% → **−3.7%** | −5.9% → **−4.7%** | −1.4% / −0.4% | 805 / 694 |
| DEAN | −4.2% → **−3.8%** | −2.1% → **−1.9%** | +4.3% / +26.0% | 215 / 159 |

"Raw" is `mid_r2`. WCA_1's shipped column includes its haircut. Gas is untouched by D150.
- **WCD crosses the ±10 % line.** Only 40 % of WCD tuning wells have a counting parent, so most carry the 1.067 level.
  BOX then over-forecasts WCD oil by about 11 % at cum-12 / 24, against −7.5 % on the 21 table it was validated on.
  This matches 24a's WCD residual of 0.960, the Midland's worst.
- WCB_2 and MS drift about 1–2 points further high; the others move ≤ 1.2 points.
- 21d's intervals are drawn on the shipped treatment, so the test stays like for like. Whether WCD ships with that bias is
  gate 23's call.

## 3. Judgeability (identities only)

The 2026 cohort holds 1,427 wells so far (newest first production 2026-09-01). January–June reporting is close to complete
(2026 wells at 89 % of 2025's count for those months); July–August is at 62 %, September at 2 %. So the projection uses
January–June:
- projected 2026 wells = 2026 Jan–Jun wells × (2025 wells / 2025 Jan–Jun wells), per group;
- projected packages = projected wells × the 2025 cohort's packages per well;
- expected judged = projected packages × the 21b tuning share of packages that carried a forecast.

| group | tier | wells so far | packages so far | 2025 wells / packages | projected 2026 packages | scored share | expected judged | judged? |
|---|---|---|---|---|---|---|---|---|
| WCA_1 | validated | 350 | 113 | 546 / 191 | 186 | 0.969 | **180** | cum-12 + cum-24 |
| WCB_1 | provisional | 225 | 81 | 416 / 151 | 135 | 0.972 | **131** | cum-12 + cum-24 |
| WCB_2 | provisional | 90 | 31 | 122 / 46 | 50 | 0.958 | **47** | cum-12 + cum-24 |
| WCC | provisional | 4 | 3 | 13 / 5 | 2 | 0.980 | **1** | NOT JUDGED |
| WCD | validated | 88 | 35 | 175 / 61 | 43 | 0.932 | **39** | cum-12 + cum-24 |
| MS | provisional | 114 | 53 | 250 / 114 | 78 | 0.958 | **74** | cum-12 + cum-24 |
| JM | provisional | 194 | 66 | 261 / 109 | 130 | 0.957 | **124** | cum-12 + cum-24 |
| LSSH | validated | 252 | 88 | 524 / 161 | 126 | 0.965 | **121** | cum-12 + cum-24 |
| DEAN | provisional | 110 | 50 | 221 / 77 | 66 | 0.923 | **60** | cum-12 + cum-24 |

- **WCC is never judgeable.** About one package is expected; it keeps its provisional tier by construction.
- **WCD and DEAN are judgeable.** WCD (39 expected) and DEAN (60) clear 30. DEAN already holds 50 packages.
- **WCB_2 is judgeable but thin** (47 expected). It already holds 31 packages, 29 after the scored share, so it reaches 30
  with almost any further reporting.
- Every 2026 well reaches cum-24 by the 2029-01-01 build, so cum-24 carries the same packages as cum-12.
- **D136 (c):** 14 WCB_2-tagged 2026 wells sit inside the WCB_1 extent north of the line (`d136_candidates.csv`). The depth
  test that would move some of them to WCB_1 is applied at scoring (§3 of the pre-registration).
- All 1,427 wells are in Texas.

## 4. Operating characteristics of the rules (tuning packages only)

**Rules.** Each group is judged on oil + gas × cum-12 / cum-24 (four cells).

| label | rule |
|---|---|
| A | consistency, D125's interval: P2.5–P97.5 of block-draw subsets of tuning at the cohort's share |
| A2 | consistency, interval + the tuning mean's own sampling error: [draw − complement] + all |
| ACC | accuracy: |bias| ≤ 10 % AND scale-free spread ≤ benchmark + 0.05, every judged cell |
| B / B2 | A or ACC / A2 or ACC (graduation only) |

**Readings.**
- **In-sample** is the D125 / 21b rehearsal: the draws that set the interval are also the test.
- **Split** is honest: a pseudo-cohort of blocks at the cohort's share is judged against an interval drawn from the complement
  only (400 × 400 draws).
- **Vintage** leaves one tuning cutoff out. Its packages are the cohort, and the other cutoffs are the reference. That is a
  real new vintage of a method exactly as good as itself.

"Pass" is a forecast as good as tuning. "Catch +15" means BOX forecasts 15 % high relative to tuning; "−15" means 15 % low.
"Accurate cohort" is the WCB_2 situation: the cohort's expected bias is zero on every cell where tuning was biased.

**Split reading** (`oc_groups.csv`):

| group | tier | cohort share | A pass | A2 pass | B pass | B2 pass | A2 catch +15 / −15 | B2 catch +15 / −15 | accurate cohort: A2 | accurate cohort: B2 |
|---|---|---|---|---|---|---|---|---|---|---|
| WCA_1 | validated | 0.18 | 0.70 | 0.87 | 0.85 | 0.93 | 1.00 / 1.00 | 0.98 / 1.00 | 0.36 | 0.93 |
| WCB_1 | provisional | 0.17 | 0.66 | 0.82 | 0.91 | 0.93 | 1.00 / 1.00 | 1.00 / 1.00 | 0.55 | 0.95 |
| WCB_2 | provisional | 0.21 | 0.68 | 0.87 | 0.72 | 0.88 | 0.87 / 0.97 | 0.87 / 0.97 | 0.35 | 0.67 |
| WCC | provisional | — | NOT JUDGED | | | | | | | |
| WCD | validated | 0.20 | 0.69 | 0.87 | 0.69 | 0.87 | 0.45 / 0.58 | 0.45 / 0.57 | 0.60 | 0.64 |
| MS | provisional | 0.19 | 0.71 | 0.88 | 0.76 | 0.90 | 0.77 / 0.88 | 0.77 / 0.86 | 0.59 | 0.75 |
| JM | provisional | 0.31 | 0.50 | 0.90 | 0.63 | 0.92 | 0.73 / 0.89 | 0.73 / 0.89 | 0.70 | 0.85 |
| LSSH | validated | 0.15 | 0.76 | 0.87 | 0.91 | 0.94 | 0.98 / 1.00 | 0.98 / 0.99 | 0.69 | 0.92 |
| DEAN | provisional | 0.28 | 0.53 | 0.88 | 0.54 | 0.89 | 0.61 / 0.77 | 0.61 / 0.77 | 0.68 | 0.70 |

B and B2 apply to the provisional groups. The validated rows show what B would do, for reference only, since keeping validated
is consistency alone.

**Per-cell share outside the interval, honest split, forecast as good as tuning** (the 21c §5 question):

| group | cohort share | outside, A (oil12 / oil24 / gas12 / gas24) | outside, A2 |
|---|---|---|---|
| WCA_1 | 0.18 | 0.14 / 0.13 / 0.12 / 0.13 | 0.06 / 0.06 / 0.04 / 0.05 |
| WCB_1 | 0.17 | 0.16 / 0.16 / 0.12 / 0.13 | 0.07 / 0.09 / 0.06 / 0.07 |
| WCB_2 | 0.21 | 0.16 / 0.15 / 0.12 / 0.14 | 0.06 / 0.06 / 0.04 / 0.04 |
| WCD | 0.20 | 0.12 / 0.11 / 0.14 / 0.17 | 0.04 / 0.03 / 0.05 / 0.05 |
| MS | 0.19 | 0.12 / 0.13 / 0.11 / 0.10 | 0.06 / 0.05 / 0.04 / 0.03 |
| JM | 0.31 | 0.27 / 0.26 / 0.24 / 0.26 | 0.05 / 0.05 / 0.05 / 0.04 |
| LSSH | 0.15 | 0.11 / 0.11 / 0.11 / 0.12 | 0.06 / 0.06 / 0.04 / 0.06 |
| DEAN | 0.28 | 0.19 / 0.17 / 0.21 / 0.23 | 0.02 / 0.03 / 0.03 / 0.06 |

In-sample, A is 0.05 per cell by construction and passes 0.85–0.88 of groups (`oc_groups.csv` `insample_*`). The honest
reading shows that figure is optimistic. The subset draws leave out the tuning mean's error and shrink with the cohort's share,
so the gap is largest where the cohort is large relative to tuning (JM 0.31, DEAN 0.28). 21c §5's "about 8 %" was a 0.20-share
estimate; the honest split puts it at 10–17 % per cell at shares 0.15–0.21.

**Vintage reading** (`oc_vintage.csv`; a cutoff is judged on its cells with ≥ 30 packages):

| group | vintages | A | A2 | ACC | B | B2 | A2 catch +15 / −15 | B2 catch +15 / −15 |
|---|---|---|---|---|---|---|---|---|
| WCA_1 | 6 | 4/6 | 5/6 | 5/6 | 5/6 | 5/6 | 1.00 / 1.00 | 0.83 / 1.00 |
| WCB_1 | 6 | 3/6 | 4/6 | 4/6 | 4/6 | 5/6 | 1.00 / 1.00 | 1.00 / 1.00 |
| WCB_2 | 5 | 1/5 | 2/5 | 0/5 | 1/5 | 2/5 | 0.60 / 0.60 | 0.60 / 0.60 |
| WCD | 4 | 1/4 | 3/4 | 1/4 | 1/4 | 3/4 | 0.75 / 0.25 | 0.75 / 0.25 |
| MS | 6 | 6/6 | 6/6 | 1/6 | 6/6 | 6/6 | 0.83 / 1.00 | 0.83 / 0.83 |
| JM | 6 | 2/6 | 3/6 | 1/6 | 3/6 | 3/6 | 0.83 / 0.67 | 0.83 / 0.67 |
| LSSH | 6 | 3/6 | 4/6 | 6/6 | 6/6 | 6/6 | 1.00 / 1.00 | 1.00 / 1.00 |
| DEAN | 4 | 2/4 | 2/4 | 2/4 | 3/4 | 3/4 | 0.50 / 0.75 | 0.50 / 0.75 |
| **all** | 43 | 0.51 | 0.67 | 0.47 | 0.67 | 0.77 | 0.84 / 0.81 | 0.81 / 0.79 |

- **Real vintages vary more than block sampling captures.** Even with A2, a genuinely as-good method passes 67 % of new
  vintages. This is 21c's "more FAILs than chance" seen on tuning data alone. JM's 2019 cohort reads +54 % on oil against a
  reference of −5 %, and WCB_2 and WCD swing ±10 points vintage to vintage.
- **For the validated groups that is a demotion risk.** Under A2, a WCA_1 / LSSH / WCD as good as its tuning is demoted in
  1 of 6 to 1 of 3 vintages per judged horizon. Under A it is 1 in 3 to 3 in 4.
- No vintage-aware interval is proposed. It would cut the already-weak catch rates on WCD and DEAN, and a vintage that misses
  is a real miss for that vintage's wells. It is reported so the risk is known before the freeze.

## 5. The WCB_2 situation

**What happened at 21c.** WCB_2's holdout was close to unbiased (oil +5.1 / +1.8 %), while its tuning half over-forecast
(−6.2 / −8.9 % on the 21 table). D99 failed it for being unlike tuning.

**What each rule would do, simulated** (split reading, "accurate cohort" columns in §4). An accurate cohort where tuning was
biased graduates:
- under consistency alone (A2), 35–70 % of the time (WCB_2 0.35);
- with the accuracy route (B2), 67–95 % of the time (WCB_2 0.67, WCB_1 0.95, JM 0.85, MS 0.75, DEAN 0.70).

The accuracy route rescues little for DEAN (0.68 → 0.70) and WCD (0.60 → 0.64): their package spreads fail the D58 test even
on tuning (DEAN cum-24 oil and gas).

**What each rule would have done on the committed 21c holdout cells** (cum-12 / 24 only, the 21 treatment;
`rules_on_21c_holdout.csv`):

| group | consistency | accuracy | B | what decides it |
|---|---|---|---|---|
| WCA_1 | PASS | FAIL | PASS | gas cum-24 +11.1 % |
| WCB_1 | FAIL | **PASS** | **PASS** | gas cum-12 −2.4 % missed its interval by 0.2 pt; every cell accurate |
| LSSH | PASS | PASS | PASS | |
| WCB_2 | FAIL | FAIL | FAIL | **gas cum-12 spread 0.950 vs benchmark 0.813 + 0.05** |
| JM | FAIL | FAIL | FAIL | oil cum-12 spread 0.896 vs 0.828 + 0.05 |
| MS | FAIL | FAIL | FAIL | oil cum-12 −11.4 % |
| WCD | PASS | FAIL | PASS | gas spread |
| DEAN | FAIL | FAIL | FAIL | oil +22 / +23 %, gas +29 / +52 % |

**So the accuracy route would not have rescued WCB_2 itself at 21c.** The miss is on its gas spread, not its oil. It would have
graduated WCB_1, whose only miss was 0.2 points.

## 6. Gate 21d questions (recommendation first)

**Q1 ★ Graduation rule (provisional → validated). Recommendation: (b), consistency OR accuracy, with the A2 interval (Q2).**
Keeping validated stays consistency alone either way.
- **What (b) buys.**
  - A provisional group as good as its tuning passes more often: B2 0.88–0.93 vs A2 0.82–0.90 (WCB_1 0.82 → 0.93).
  - An accurate cohort where tuning was biased passes far more often: B2 0.67–0.95 vs A2 0.35–0.70.
- **What (b) costs: almost nothing on misses.** B2's catch of a ±15 % miss equals A2's within 0.02 on every provisional group.
  A forecast 15 % off rarely clears |bias| ≤ 10 %. When it does, the tuning bias had offset the miss and the cohort really is
  accurate.
- **What (b) changes in meaning.** "Validated" would mean either "the disclosed bias is honest" or "the forecast is accurate
  on a new vintage". A group that graduates on accuracy alone has no honest tuning line to disclose. So the definition makes it
  ship raw, with no haircut, carrying the cohort line until its own gate decides. D125 chose (a) for the Delaware and left the
  size of the bias to step 17; (b) is a Midland-only departure from that, stated here.
- **Spread wording.** Your gate text says "spread ≤ the local-offsets benchmark". The draft uses D58 of record, benchmark
  + 0.05. Strict ≤ would close the route more often (WCB_2's 21c gas cell fails either way). Confirm + 0.05.
- **(a) instead** keeps D125 as written. It is the safer reading of "validated", and it leaves WCB_2-like groups provisional
  unless the bias the tuning half showed recurs.

**Q2 Should the consistency interval carry the tuning mean's own sampling error? Recommendation: yes (A2).**
- D125's interval (A) is the spread of subsets of tuning. It leaves out the tuning mean's error and shrinks with the cohort's
  share. On an honest split, a cohort as good as tuning lands outside 10–27 % of the time per cell, not 5 %. Groups pass only
  0.50–0.76 of the time.
- A2 brings the per-cell rate to 2–9 % and group pass to 0.82–0.90.
- **Cost:** lower catch rates where the cohort is small or noisy. At +15 / −15 the change is:
  - WCD 0.71 / 0.77 → 0.45 / 0.58;
  - DEAN 0.92 / 0.94 → 0.61 / 0.77;
  - JM 0.96 / 0.99 → 0.73 / 0.89;
  - MS 0.89 / 0.96 → 0.77 / 0.88.
- It is a departure from D125's interval drawing. 13d (Delaware) stays frozen with A.
- If you choose A, the draft changes one line of the interval text and re-pins.

**Q3 Does water belong in the test? Recommendation: reported only, never a tier (13d judged oil + gas only).**
- Water cannot change tier under D109 here. Validated water needs every judged TUNING water cell to pass, and 21b passed 3 of
  22 (D149 (5)). A 2026 read cannot change that.
- The measured label is itself under diagnosis: the sql/41 Texas "measured" label and an operator concentration of 58–77 %
  (D149 (5)). All 1,427 cohort wells are in Texas.
- The D109 measured-water read is reported at each judgment. A water route can get its own pre-registration after the
  diagnosis, before any 2026 water read.
- I did not count measured-water packages for the 2026 cohort. `water_data_quality` is derived from production series, so
  reading it would read 2026 outcomes.

**Q4 Proximity configuration for scored wells: drilled side (recommended).**
- This is how D150 was fitted and validated, and how 21b / 21c scored: parents ≥ 365 d on production at the well's first
  production.
- Production sticks use the stick side (every producer existing at the data date). On the 2026 cohort the two differ by
  ≤ 1.0 point of mean factor per group, WCC aside (`cohort_at_draft.csv`).
- The stick side is reported.

**Q5 Wells the shipped gates leave without a forecast: score every well, report the subset (recommended).**
- **This is where D125's pattern and D151's differ, so it is flagged, not resolved.** 13d excluded D114 no-precedent wells
  from the verdict. 21b / 21c scored every well with precedent ignored, and the 21d intervals come from those 21b packages.
- Recommendation: score every well, like for like with the intervals and with D150's validation. Count the no-forecast wells
  (pattern precedent, 400-ft floor, package tier) and report their bias.
- It barely matters at the floor: 3 of 1,427 wells sit within 400 ft of a same-bench producer at the cutoff. The pattern
  precedent and the package tier are counted at scoring (they need the 21a decision machinery on the final cohort).
- The alternative is 13d's: exclude them on the cohort side. The intervals would then need the same exclusion on the tuning
  side, which 21b never computed.

**Q6 Durability. Recommendation: copy the pinned inputs to the OneDrive share now (the 13d precedent).**
- `runs/step21b/MID_*` holds the 54 tuning views (46 MB). `runs/step21a/links.pkl` is 24 MB. Both live only on this laptop,
  pinned in `tuning_views.sha256`.
- Without them the 2028 intervals cannot be drawn.

**After the gate:** write Q1–Q6 into `DEFINITION`, re-pin the digest, stamp the freeze commit into the pre-registration, and
merge. Nothing else moves; step 23 is next on your go.

## 7. What was read, and what was not

- **Read, 2026 Midland wells:** `curated.wells` columns api10, first-production date, state, operator, completed lateral, TVD,
  production-sharing flag, wellstick and landing-point geometry, trajectory; `curated.formation_blueox` and
  `curated.wells_enriched` bench tags; `box.extent` geometry.
  - The cohort query names its columns; `tests/test_box_prospective21.py` pins the allowlist.
  - Neighbour links are geometry and first-production dates only (`box/prox_study.links_for_child`).
- **Not read:** `curated.production`, any `cum_*` / `eur_*` / `peak_*` column, `curated.water_data_quality`, or any 2026 well's
  volume.
  - `box/spacing3d_report.build_pairs` was deliberately not used: it pulls parents' cumulative oil, and a 2026 well can be a
    parent of a later 2026 well.
- **Read, other:** the 21b tuning views (wells first producing before 2025-12-01; production through 2026-08-01); the committed
  21c results (already scored and public in the repo); the 2025 cohort's identities for the full-year scale.
- **Not opened:** the 21c holdout run directories (`runs/step21c`).
- **Nightly:** idle at both snapshot runs (last run 2026-11-02 22:01 UTC, green; the next is 05:00 CT).
- **Nothing written to the warehouse.** No run stored or flipped, no `box.bench_scope.validation`, no Delaware object touched.
