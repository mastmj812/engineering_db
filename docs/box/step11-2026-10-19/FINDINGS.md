# BOX step 11 — water: method + acceptance design (read-only) — AT GATE 11

2026-10-19. Plan §5 step 11.

- **Scope.** Every `covered` + `covered_provisional` location of record run 10: 50,963 locations in 13 groups (18,607 + 32,356;
  the 480 no-analog rows are out of scope).
- **Data.** Production through 2026-07-01, the same as run 10 and every tuning run.
- **Read-only.** No DDL; sql/62 stays reserved for 12b.
- **No holdout water read.** The counts in §4 read holdout labels and months on production only.
- **Pre-registration.** The tolerance and every rule were committed in `PREREGISTRATION.md` (51d589c, pushed) BEFORE any water
  forecast was scored.
- **Sign convention.** Error = actual / forecast − 1; negative = forecast HIGH.

## 0. Headline

1. **Measured-water analogs exist almost everywhere.**
   - 50,914 of 50,963 locations (99.9 %) close a measured-water cohort. 92 % close inside the D54 ladder (≤ 20 mi); 4.1 % need
     the 30–50 mi water extension.
   - Only **49 locations fall back to vendor-calculated water**, all BS2_C in TX (3.7 % of BS2_C TX).
   - The extension is a TX phenomenon: 49 % of BS2_C TX, 36 % of BS1_S TX and 18 % of BS3_C TX locations.
   - 21 % of TX locations draw at least one NM analog; 7.8 % draw mostly NM analogs.
2. **Method: WOR vs cumulative oil (`ratio`), as leaned.**
   - Under the pre-registered choice rule, `arps` passes 3 more cells (19 vs 16 of 37 judged) but has double the median |bias|
     (13.5 % vs 6.2 %), so `ratio` stands.
   - Pooled across all groups, ratio water is unbiased: **+0.2 / +1.8 / +4.6 %** at cum-12 / 24 / 36, vs the measured
     local-offsets benchmark at +2.7 / +4.4 / +3.2 %.
   - The independent water Arps P50 runs **13–17 % LOW** at every horizon.
3. **Most failures are spread, not bias.**
   - Of 21 failing ratio cells, 14 fail only the scale-free spread test against a measured-offsets benchmark, 6 only the
     ±20 % bias, and 1 both.
   - The bias failures are AVA_0 / AVA_1 (water +51 … +66 % above forecast; the benchmark misses the same way, +49 … +89 %),
     plus the cum-36 cells of AVA_2, BS1_S and BS3_C.
   - The validated-oil groups WCA and BS2_S pass all 3 cells.
4. **One decision surfaced after scoring (§3.4): which oil the WOR rides on.**
   - The pre-registration says production water rides on the DELIVERED oil. For WCA and BS2_S that oil carries the D62 / D102
     haircut.
   - On the haircut oil, BS2_S water would run **+14 / +17 / +21 % LOW** (cum-36 outside the ±20 % tolerance), against
     **+2 / +2 / +1 %** on the raw box_v2 oil it was scored on. WCA moves from −8 / −4 / −1 % to −2 / +4 / +8 %.
   - Raw groups are unaffected.

## 1. What was read, and the kickoff as applied

**Kickoff, as given (Michael 2026-10-19).**
1. Measured-water analogs at any reach; calculated fallback only where none exist.
2. Measured = sql/41 `measured` + VDR daily water.
3. A wider tolerance, pre-registered.

**Amendment before scoring (Michael 2026-10-19).**
- **NM water counts as measured unless sql/41 would call it `insufficient`.** sql/41's 0.05 CV floor labelled steady,
  genuinely reported NM water as `calculated` (15 wells, CV 0.021–0.049) or `indeterminate` (972 wells, median CV 0.12).
- TX keeps the sql/41 label only.
- Check: recomputing the labels as of 2026-07-01 reproduces sql/41's own labels exactly (AVA_0 smoke, 480 / 480). The only
  differences are the amended NM ones.

**VDR.** 22 wells are loaded (Alchemist, all TX). 19 are already sql/41 `measured`. The rule upgrades at most 3, and the 2
calculated ones first produced in 2026-02, too young to be analogs. The VDR path is wired and changes almost nothing today.

**Pool.** Each group's own run-10 well set (`water11.GROUP_WELLS`: the D84 refresh for WCA / BS2_S / WCXY, step-15 QC sets
for the rest). For water it is not clipped to the extent.

Measured share of the pool (horizontals first producing ≥ 2016, `pool_labels.csv`):

| bench | NM measured | TX measured |
|---|---|---|
| validated benches | 88–96 % | 43–78 % |
| BS1_S | — | 30 % (55 wells) |
| BS2_C | — | 17 % (50 wells) |
| AVA_1 | — | 27 % (3 wells) |

**Tuning inputs.** The tuning views + box_v2 oil months of each group's tuning run, copied tuning-only to
`runs/step11_inputs/` (sha256 in `inputs_digests.txt`). A tuning view holds no held-out package; the runner asserts it.
- WCA / BS2_S / WCXY are the 9a runs; the rest are the step-15 runs.
- WCA's 9a tuning view was built on the step-1 well set; its water analog pool here is the D84 refresh, the same set as run 10.

## 2. (a) Measured-water reach per location (`reach_by_group_state.csv`, `reach_radius_counts.csv`)

Selection is box_v2's first-ring rules, as written:
- deal-intake config v10 classify + tier-blind fill, completed laterals (D56), the 7,500–12,500 ft band for short laterals;
- circles only;
- the D54 ladder 5 / 7.5 / 10 / 15 / 20 mi, then **30 / 40 / 50 mi** until ≥ 10 eligible measured wells.

At 50 mi, 3–9 measured analogs are used and flagged `thin`; fewer than 3 means calculated fallback, flagged.

| radius closed (measured) | 5 | 7.5 | 10 | 15 | 20 | 30 | 40 | 50 | fallback |
|---|---|---|---|---|---|---|---|---|---|
| locations | 20,846 | 12,626 | 7,223 | 6,411 | 1,739 | 1,170 | 437 | 462 | 49 |

| group | NM: median radius / ≥ 30 mi | TX: median radius / ≥ 30 mi | TX: any NM analog / mean NM share | thin / fallback |
|---|---|---|---|---|
| WCA | 5 / 0 % | 5 / 0.6 % | 10 % / 5 % | 0 |
| WCXY_WCA1 | 5 / 0 % | 5 / 0 % | 7 % / 3 % | 0 |
| BS2_S | 5 / 0 % | 10 / 0.1 % | 49 % / 24 % | 0 |
| WCB_1 | 7.5 / 1.7 % | 7.5 / 0.9 % | 9 % / 4 % | 0 |
| WCC | 7.5 / 0 % | 7.5 / 0 % | 21 % / 8 % | 0 |
| BS3_S | 7.5 / 0.7 % | 10 / 1.4 % | 18 % / 7 % | 0 |
| BS3_C | 7.5 / 0.3 % | 15 / 18 % | 20 % / 8 % | thin 1.9 % TX |
| WCB_2 | 7.5 / 1.2 % | 7.5 / 0.7 % | 11 % / 4 % | 0 |
| BS1_S | 7.5 / 1.0 % | 15 / **36 %** | 59 % / 27 % | 0 |
| BS2_C | 7.5 / 0 % | **30 / 49 %** | 26 % / 14 % | thin 6.5 %, **fallback 3.7 %** TX |
| AVA_0 / 1 / 2 | 5–7.5 / ≤ 0.2 % | 5 / 15 / 7.5, 0 % | 91 / 100 / 100 % | 0 |

**TX reaching into NM.** 4,597 of 21,703 TX locations (21 %) draw at least one NM analog; 1,692 (7.8 %) draw a majority.
- These are concentrated where TX measured water is thin: BS1_S, BS2_S, AVA.
- AVA_1 TX (14 locations) is almost all-NM (mean 94 %). Only 3 TX AVA_1 wells are measured.

## 3. (b) Method comparison on tuning packages (`cells_pooled.csv`, `cells_per_cutoff.csv`, `cells_by_state.csv`)

**Grain.** 9,222 measured-water scored wells (29 on a calculated-fallback cohort; 1.5 % thin), D53 packages restricted to their
measured members, pooled across the six cutoffs (D99).

**Methods (pre-registered §2).**
- `ratio`: boxfit WOR-vs-cum-oil ratio mode on the measured cohort's per-1,000-ft mean series, applied to the location's raw
  box_v2 oil months.
- `arps`: water Arps P50.
  - Median fitted Di is 3.3/yr nominal at b = 1.18 (≈ 74 % 1-yr effective); P10–P90 Di is 1.5–7.1.
  - 0.3 % pin at the 12/yr cap (≈ 92 % effective at b = 1).

Both are scaled by the fold's F_oil(k).

### 3.1 All groups pooled

| cum | ratio bias (median pkg) | arps bias (median pkg) | benchmark bias | ratio / arps / benchmark scale-free band |
|---|---|---|---|---|
| 12 | **+0.2 %** (−9.1 %) | +13.0 % (+0.6 %) | +2.7 % | 1.05 / 1.01 / 0.98 |
| 24 | **+1.8 %** (−8.3 %) | +16.0 % (+3.5 %) | +4.4 % | 1.08 / 0.99 / 1.00 |
| 36 | **+4.6 %** (−5.7 %) | +17.2 % (+5.1 %) | +3.2 % | 1.08 / 1.03 / 1.09 |

**Reading the mean and the median.** Ratio's mean package is unbiased while its median package is ~6–9 % high. The arps
pattern is the mirror image: unbiased median, mean 13–17 % low. A few wet packages pull the mean up in both. The mean is the
D53 statistic because package SUMS are what get priced. On that statistic ratio is the unbiased one; Arps P50 under-forecasts
the wet tail.

**Vintage.**
- Ratio's per-cutoff bias stays within −6 … +8 % at every cutoff and horizon.
- Arps is low at every cutoff (+3 … +29 %).

### 3.2 Per group (pooled cells; P = pass, F = fail, n = not judged)

| group | cum-12 ratio / arps | cum-24 ratio / arps | cum-36 ratio / arps | benchmark 12 / 24 / 36 | packages 12 / 24 / 36 |
|---|---|---|---|---|---|
| **WCA** | −7.7 % P / +6.7 % P | −3.8 % P / +10.9 % P | −1.1 % P / +13.5 % P | −1.7 / −3.2 / −7.6 % | 983 / 840 / 680 |
| **BS2_S** | +2.0 % P / +10.8 % P | +2.0 % P / +11.9 % F | +0.8 % P / +9.9 % P | +5.5 / +6.8 / +10.6 % | 479 / 363 / 225 |
| **WCXY_WCA1** | −6.2 % F / +8.8 % P | −4.3 % P / +12.2 % P | −4.2 % F / +12.2 % P | +0.9 / −1.5 / −8.3 % | 256 / 225 / 182 |
| **WCB_1** | +1.6 % F / +14.9 % F | +2.7 % F / +17.8 % P | −6.3 % F / +7.9 % F | +10.6 / +13.5 / +5.9 % | 262 / 212 / 158 |
| **WCC** | −0.6 % F / +19.0 % F | −3.7 % F / +8.4 % F | +2.4 % F / +8.3 % P | −1.9 / −5.7 / −4.1 % | 131 / 100 / 55 |
| BS3_S | −4.5 % F / +4.1 % F | +4.3 % P / +15.4 % P | +11.5 % P / +23.6 % F | −7.9 / +0.3 / +8.1 % | 382 / 304 / 188 |
| BS3_C | +8.6 % P / +39.6 % F | +8.5 % F / +37.7 % F | +32.0 % F / +45.9 % F | +3.6 / +16.9 / +22.0 % | 270 / 168 / 82 |
| WCB_2 | −3.5 % P / +11.8 % P | −3.9 % F / +15.8 % F | −3.5 % P / +15.7 % P | +2.7 / −2.7 / −9.7 % | 174 / 127 / 79 |
| BS1_S | +10.8 % P / +13.5 % P | +8.4 % P / +18.7 % P | +40.9 % F / +42.2 % F | +6.5 / +10.1 / +2.0 % | 181 / 107 / 31 |
| BS2_C | +6.4 % P / −1.0 % P | −5.3 % P / −2.5 % P | −16.8 % F / −12.5 % P | +9.2 / +16.6 / +23.9 % | 90 / 51 / 35 |
| AVA_2 | +11.1 % F / +11.7 % F | +13.7 % F / +18.1 % P | +20.7 % F / +24.0 % F | −2.7 / +2.8 / +3.3 % | 69 / 52 / 32 |
| AVA_1 | +50.9 % F / +53.5 % F | +54.9 % F / +70.8 % F | +63.8 % F / +63.8 % F | +55.8 / +71.3 / +88.8 % | 58 / 42 / 35 |
| AVA_0 | +54.7 % F / +62.4 % F | +65.8 % n / +77.6 % n | +110 % n / +122 % n | +49.0 / +54.2 / +60.4 % | 36 / 28 / 16 |

Bold = validated-oil groups (`covered`).

**Spread failures.**
- The near misses: WCC cum-12 fails by 0.002, WCXY cum-12 by 0.016, WCXY cum-36 by 0.05.
- The others: WCB_1 by 0.14–0.24, WCB_2 cum-24 by 0.11.
- The benchmark here is 15 local MEASURED offsets. It is tighter than any 10–20-well cohort curve on a stream whose per-well
  water varies this much.

**AVA.** Water runs 51–66 % above forecast, and the measured benchmark misses by the same amount. Newer AVA wells are wetter
than their offsets, so this is a cohort / vintage effect, not a method one. It is AVA's provisional disclosure line.

**By state** (`cells_by_state.csv`; reported, never judged).
- NM and TX ratio biases agree within a few points on WCA, WCXY, BS3_S and WCB_2.
- TX is worse where TX measured water is thin: BS3_C TX +25 / +18 / +51 %; WCC TX +40 … +52 % on 13–31 packages.

### 3.3 Diagnostic: the WOR on ACTUAL oil (`ratio_actoil`, never chosen)

- Median package error is +1.7 / +4.4 / +7.2 %, so the WOR curve itself is sound.
- The mean is +55 … +111 %, driven by low-oil / high-water wells (e.g. 702 bbl oil, 1.45 MMbbl water in 12 months).
- At well level, log(actual / forecast water) tracks log(actual / forecast oil) with an **elasticity of 0.47** (r = 0.43,
  8,482 wells). Water is only about half as sensitive to a well's oil miss as a fixed WOR assumes.
- Two consequences:
  - The analog-average oil protects water from single-well oil misses.
  - A future oil refinement carries into water 1 : 1 under `ratio`, while history says water moved ~0.5 : 1. Fine for an
    unbiased cohort oil; worth knowing before a large oil re-level.

### 3.4 Which oil the WOR rides on (`haircut_oil_sensitivity.csv`) — surfaced after scoring, decision needed

| group | oil cum factor 12 / 24 / 36 | ratio bias on raw box_v2 oil (scored) | on the haircut oil delivered (first order) |
|---|---|---|---|
| WCA (D62) | 0.943 / 0.929 / 0.916 | −7.7 / −3.8 / −1.1 % | −2.1 / +3.5 / +8.0 % |
| BS2_S (D102) | 0.891 / 0.873 / 0.832 | +2.0 / +2.0 / +0.8 % | **+14.4 / +16.8 / +21.2 %** |

- First order = water × the cum factor. The WOR's own Np shift lowers the haircut-oil water further.
- The WOR was fitted against analog oil. BS2_S raw oil runs 11–17 % high, and the ratio fitted against that same analog oil
  lands water unbiased. Cutting the oil again cuts water that was already right.
- PREREGISTRATION §2 says production water rides on the delivered oil. That line was written before this effect was known and
  is the one place a post-score finding bears on the frozen spec, so it goes to Michael (ask 2), not changed here.

## 4. (c) The frozen acceptance rule for gate 12a (`PREREGISTRATION.md` §5; `intervals_water.csv`, `intervals_power.csv`, `judgeable_counts.csv`)

**Rule (unchanged from the pre-registration).**
- Pooled group × horizon cells on measured-water packages.
- Water cell test: |bias| ≤ 20 % AND scale-free band ≤ benchmark + 0.10, judged at ≥ 30 packages.
- 12a scores the holdout ONCE. A holdout cell with ≥ 10 packages is consistent when its bias lies inside the frozen tuning
  interval (P2.5–P97.5 of 2,000 20 % block draws, seed 20261019).
- Validated water needs all three: validated oil, every judged tuning cell passing, and every judged holdout cell consistent.
  Otherwise water is provisional (D105-style disclosure). Never re-tuned, never dropped.

**Judgeable cells.** Package counts below are tuning / holdout measured-water packages at cum-12 / 24 / 36, pooled.

| group | tuning (≥ 30) | holdout (≥ 10) | holdout cells judgeable |
|---|---|---|---|
| WCA | 985 / 842 / 682 | 345 / 298 / 241 | 3 |
| BS2_S | 481 / 365 / 266 | 148 / 122 / 87 | 3 |
| WCXY_WCA1 | 259 / 228 / 185 | 83 / 72 / 58 | 3 |
| WCB_1 | 272 / 222 / 168 | 110 / 92 / 78 | 3 |
| WCC | 133 / 102 / 79 | 47 / 33 / 27 | 3 |
| BS3_S | 393 / 315 / 232 | 128 / 103 / 70 | 3 |
| BS3_C | 296 / 201 / 133 | 85 / 62 / 38 | 3 |
| WCB_2 | 215 / 167 / 131 | 65 / 52 / 41 | 3 |
| BS1_S | 222 / 156 / 103 | 47 / 36 / 21 | 3 |
| BS2_C | 97 / 60 / 50 | 29 / 20 / 14 | 3 |
| AVA_1 | 58 / 42 / 35 | 21 / 15 / 12 | 3 |
| AVA_2 | 71 / 54 / 39 | 10 / 6 / 6 | 1 |
| AVA_0 | 37 / 29 / 20 | 7 / 5 / 5 | **0** |

The tuning counts from this pass match the tuning run itself (e.g. WCA 985 vs 983 scored).

**Power** (`intervals_power.csv`). A forecast as good as tuning passes a cell 95 % of the time by construction. How often a
biased forecast is still passed:

| group | forecast 10 % off | forecast 15–20 % off |
|---|---|---|
| WCA | 7–38 % | ≤ 9 % |
| BS2_S | 34–65 % | ≤ 36 % |
| WCXY, WCB_1, BS3_S, WCB_2 | 60–88 % | 22–68 % |
| WCC, BS1_S, BS2_C, AVA | > 75 % | > 60 % |

Validated water can be told apart from a 15 % miss only on WCA and BS2_S; on the small benches the holdout mainly guards
against a gross miss.

**What 12a can conclude, given these tuning results.**
- Rule (ii) already fails for WCXY_WCA1, WCB_1 and WCC on spread. Only **WCA and BS2_S** can reach validated water.
- The other three validated-oil groups carry provisional water whatever their holdout says. The holdout is still scored and
  disclosed.
- The 8 provisional-oil groups carry provisional water by construction.

## 5. Gate-11 asks (Michael)

1. **Approve `ratio` as the BOX water method of record.** WOR vs cum oil on measured analogs, at the §2 reach with the
   calculated fallback flagged. It is unbiased pooled (+0.2 / +1.8 / +4.6 %) where Arps P50 is 13–17 % low.
2. **Which oil the WOR rides on in production (§3.4).**
   - Recommendation: the **raw box_v2 oil months**, i.e. exactly what was scored. For the raw groups (11 of 13) that already
     is the delivered oil.
   - For WCA and BS2_S, "delivered oil" would make BS2_S water 14–21 % low (cum-36 outside ±20 %).
   - Either way it is a one-line change to PREREGISTRATION §2's production sentence before 12a freezes the spec.
3. **Accept the frozen gate-12a rule (§4) as written**, knowing it can validate water only for WCA and BS2_S (rule (ii) spread
   failures on WCXY / WCB_1 / WCC). The alternative is a decision on the spread half before 12a: e.g. judge spread against an
   analog-cohort benchmark, or report-only spread as D99 did for holdout. That would change the rule after seeing tuning, so
   it is yours to make or decline; this session recommends **as written**.
4. **The NM amendment is recorded** (PREREGISTRATION §0; shared notes `step11-water-kickoff-amendment.md`). sql/41 itself is
   unchanged. Whether sql/41 should gain a state rule is a separate warehouse question, not proposed here.
5. **Next = step 12a.**
   - Freeze spec + code SHA.
   - Tuning identity re-score (1e-9).
   - Holdout scored once vs `intervals_water.csv`.
   - Then 12b: sql/62 + a production run with water.

## 6. Reproduce

```
python -m scripts.box_water11 reach --out runs/step11 --workers 12            # 372 s
python -m scripts.box_water11 tune  --out runs/step11 --workers 12            # 2,468 s (inputs: runs/step11_inputs, digests)
python -m scripts.box_water11 counts --out runs/step11                        # 630 s
python -m scripts.box_water11_report                                          # writes this folder's CSVs + index.html
```

Code: `box/water11.py`, `box/water11_report.py`, `scripts/box_water11*.py`, `tests/test_box_water11.py` (6 tests). The
reach / tune / counts runs ran at 51d589c (the pre-registration commit); the report module came after, and it only aggregates.

## 7. Caveats

- **F_oil(k) is used for water.** No water calendar factor was calibrated. Downtime takes both streams together.
- **Circles only.** The D55 strike ellipse is not used for water.
- **Benchmark eligibility.** The benchmark needs ≥ 15 measured offsets with cum-k known. A cell without one passes the spread
  half by `judge_cell`'s rule; none of the judged cells lacked one.
- **Package composition.** A package's water members are its measured members only. A mixed TX package is scored on fewer
  wells than its oil package.
- **Water is a technical forecast.** Nothing here touches oil or gas forecasts, and no economics is computed. Water volumes go
  to Steven as a stream, not as cost.
