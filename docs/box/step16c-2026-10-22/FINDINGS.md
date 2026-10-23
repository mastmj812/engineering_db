# Step 16c — scoring the pre-registered cohort-selection variants (2026-10-23)

Scored under the frozen pre-registration (`docs/box/step16b-2026-10-22/PREREGISTRATION.md`, SHA 109f805, D120): 14 tuning-view
runs (13 groups on the analog fold, WCA also on the full fold), actuals through 2026-07-01, TUNING packages only, plus the §6
level-only hindcast and the §5 off-local review. Every run exited 0 on code identical to 109f805 (`runs/step16c/*/run.json`);
scoring code `box/step16c.py` + `scripts/box_step16c.py` was committed (1282550) before any score was read; one bug fixed
before its run (65468cb: no-ramp fits). Read-only; nothing stored. Files here: `summary.json`, `pooled_cells.csv`,
`validated_keep.csv`, `record_identity.csv`, `stratum_far_with_local.csv`, `offlocal_share.csv`, `cui_vs_linear_*.csv`.

**Sign convention:** bias = Σ actual / Σ forecast − 1; negative = forecast HIGH.

## 1. Results under the rules as written

| | result |
|---|---|
| **Provisional groups (§5)** | **`box_v2s` adopted — the spacing fix alone.** `box_v2s_r2` fails conditions 3 (stratum) and 6 (Cui); `box_v2s_r2lo` also fails 1 (cells) and 5 (hindcast) |
| **Validated groups (§4)** | **BS2_S, WCXY_WCA1 stay validated.** **WCA, WCB_1, WCC are referred to Michael** (no automatic demotion) |
| **Level-only short-history wells (§6)** | **fails**: transferred next-12-month oil bias −15.3 % (1,074 wells; tolerance ±15 %) |
| **Cui-vs-linear flags (§6b)** | 8 groups flagged: AVA_0, AVA_2, BS1_S, BS2_S, BS3_C, WCA, WCB_1, WCC — but see §3: the check as written is confounded |
| **D98 guard** | re-scored record = cells of record within data drift: package bias moves ≤ 1 pt on 11 groups, up to 7 pts on WCB_1 (`curated.production` revised since 10-17); WCA package counts differ in some cutoffs (run-10 well set adds 1 well vs gate 1); AVA_0/1/2 have no committed record cells |

### 1.1 Provisional groups — the adoption inputs (pooled over the eight groups)

| | `box_v2` (record) | `box_v2s` (base) | `box_v2s_r1` (comparison) | `box_v2s_r2` | `box_v2s_r2lo` |
|---|---|---|---|---|---|
| judged pooled cells / failing | 44 / 24 | 44 / 24 | 44 / 21 | 44 / 23 | 44 / 25 |
| median \|pkg bias\| | 5.9 % | 7.5 % | 7.4 % | 8.0 % | 8.4 % |
| far-with-local stratum, oil cum-12 (fixed set, 608–652 wells) | — | **−1.6 %** | −5.0 % | −7.2 % | −7.6 % |
| off-local share, run-10 PUDs (2,500 far-with-local) | — | 37.6 % | 25.8 % | **19.1 %** | 20.4 % |
| scored wells closing inside 5 mi | — | 27.6 % | — | **66.7 %** | — |
| well-level oil cum-12, all provisional (3,187 common wells) | −9.7 % | **−8.0 %** | −10.9 % | −10.8 % | −11.1 % |

Oil cum-12 pooled package bias by group (record → base → r2): AVA_0 −18.4 / −19.7 / −26.1; AVA_1 −5.1 / −9.9 / −0.8;
AVA_2 +0.1 / +2.6 / +3.0; BS1_S −10.1 / −7.7 / −10.0; BS2_C −7.5 / −3.3 / −5.4; BS3_C −5.2 / −0.9 / −10.6; BS3_S −6.3 / −4.2 /
−1.8; WCB_2 +1.3 / +1.4 / −4.2 %.

### 1.2 Validated groups — the keep-rule (§4)

| group | form | new base | judged | max \|bias\| new | fails new / record | verdict |
|---|---|---|---|---|---|---|
| WCA | per-cutoff (full fold) | `box_v2s_wf` | 18 | 8.1 % | **3 / 2** | refer |
| BS2_S | pooled | `box_v2s_wf` | 6 | 5.6 % | 1 / 2 | keeps |
| WCXY_WCA1 | pooled | `box_v2s` | 6 | 8.8 % | 0 / 0 | keeps |
| WCB_1 | pooled | `box_v2s` | 6 | **34.8 %** | 3 / 4 | refer |
| WCC | pooled | `box_v2s` | 6 | **16.1 %** | 3 / 4 | refer |

- **WCA:** every judged cell's bias stays within ±8.1 % (record ±8.6 %). Its three fails are spread-test fails: gas cum-12 2023
  (the record fails it too), gas cum-12 2024 −7.2 %, and gas cum-36 2022 −7.4 %. The record's two fails were oil cum-12 2024 and
  gas cum-12 2023. Gas runs ~1–2 points more over-forecast with the fix.
- **WCB_1:** the failing cells are a PRE-EXISTING gas under-forecast (cum-24 / 36: +18.6 / +34.8 % new, +20.1 / +35.0 % record)
  and oil cum-36 −11.0 % (record −11.2 %). The fix cuts failing cells 4 → 3. Condition 1 (every cell ≤ 10 %) is stricter than
  the record itself met.
- **WCC:** the same pattern. Oil cum-24 / 36 are −10.3 / −16.1 % (record −12.2 / −14.4 %); failing cells 4 → 3.

## 2. What the results say

1. **The spacing fix (D119) is what's adopted.** On the provisional groups' scored wells it lowers the oil cum-12 over-forecast
   from −9.7 % to −8.0 %. Pooled cells are unchanged at 24 fails; median |bias| rises from 5.9 to 7.5 %, because gas and later
   horizons move in mixed directions.
2. **Local-first selection (r2) does what it was designed to do on selection** — 67 % of scored wells close inside 5 mi vs 28 %;
   the share of PUDs > 25 % off their neighbours' year-1 halves (38 → 19 %) — **but it forecasts about 3 points higher overall**
   (−10.8 % vs −8.0 % oil cum-12) on benches that carry no haircut, and in absolute terms it is worse on the very stratum it
   targets (−7.2 % vs −1.6 %).
3. **Nearby older wells overstate the next well.** On the far-with-local stratum, the cohort drawn from local wells
   predicts higher than the far cohort, and the wells came in lower. This matches the 16a backtest finding (BS1_S oil-12 −30 %
   at the 5–7.5 mi radius, shared by the local-offsets benchmark). The likely reading: local producers were drilled first, into
   undepleted rock; the next well beside them is a child. The PDP-proximity layer (D112–D116) haircuts multi-parent PUDs in
   production, but these tuning variants are raw box_v2 without it.
4. **The level-only middle path fails.** Wells 3–5 months past peak, given borrowed Di / b, forecast their next 12 months 15.3 %
   high (their own fits 21.4 % high). It is worst on the thin benches (AVA_0 −36 %, AVA_1 −33 %, BS1_S −23 %). Not adopted.
5. **The provisional groups' dominant error is LEVEL, not selection.** Every variant over-forecasts oil cum-12 by 8–11 %
   (raw box_v2, no haircut, D105). The selection rules move individual PUDs a lot (16a: P10 −19 % / P90 +27 %) but the level by
   a few points. The +13–16 % curve-construction offset found on BS1_S (the P50's month 1–12 against its own cohort's actual
   cum-12) is the first suspect. It is not yet diagnosed per group (§7 item, not done in 16c).

## 3. A flaw in two pre-registered conditions (POST-LOOK — disclosed, the rules were not changed)

Conditions 3 (stratum) and 6 (Cui) compare ABSOLUTE |bias| in a subset. On benches whose overall level is off by ~−10 %, that
rewards a variant whose subset error happens to cancel the level error. Both were my design, and the check should have been
written relative to the variant's own level. Read that way:

- **Cui (condition 6).** Length error measured relative to each group's "near" class (0.80–1.25 × the cohort's mean lateral),
  oil:
  - Pooled over the provisional groups, cum-12: Cui is shorter −0.7 % / longer −4.8 %; linear is +12.1 % / −11.1 %.
  - The same at cum-24: Cui −2.1 / −4.4 %, linear +10.6 / −10.7 %.
  - Per group at cum-12, Cui's summed class error is below linear's in **13 of 13 groups**.
  - At cum-24 it is below in 11 of 13. The exceptions are AVA_0 and AVA_2 (thin longer classes, 5–16 wells); WCC is nearly
    tied (0.130 vs 0.136).
  - **The Cui translation works.** Linear per-ft scaling under-predicts shorter wells by ~11 % and over-predicts longer ones by
    ~11 %; Cui removes most of both. The 8 flags of §1 are artefacts of the absolute comparison.
- **Stratum (condition 3).** The stratum's error relative to the variant's error everywhere else:
  - `box_v2s`: +8.3 points;
  - `box_v2s_r2`: +5.1 points (r1 +8.0, r2lo +4.9).
  
  So r2 is the MORE consistent between far-with-local and the rest. The base's small absolute stratum bias is a far-cohort
  under-forecast cancelling the bench-wide over-forecast.

What the relative reading does NOT change: r2 still forecasts ~3 points higher overall, and that is real money on unhaircut
benches. The level-only path still fails on its own test.

## 4. For gate 16c (Michael)

1. **Provisional groups.** The rule as written adopts `box_v2s` (spacing fix only). The alternative is an owner's-judgment
   exception (the D59 / D113 pattern) adopting `box_v2s_r2` on the §3 reading. Recommendation: **accept `box_v2s` now.**
   - r2's case rests on post-look relative readings.
   - Its absolute level is worse on benches with no haircut.
   - Revisit r2 after the level problem is addressed (the construction offset), with level-relative conditions pre-registered
     and the 2026 cohort as the confirmation.
2. **Validated groups referred.** Recommendation: **keep WCA, WCB_1 and WCC validated with the fix.**
   - WCA: no cell's bias exceeds ±8.1 %, and its extra fail is a spread test on gas.
   - WCB_1 and WCC: their failing cells pre-date the fix, and the fix reduces failing cells 4 → 3.
   - Keep-rule condition 1 demanded more than their records ever met.
   - **WCB_1 gas (+35 % at cum-36, forecast LOW) is a standing problem for its own item.**
3. **Level-only short-history wells:** rejected as scored. The 6-month floor stays; the spacing fix already removes the
   artefact's ~13-month floor.
4. **Next for 16d** (on go): a production build with measured spacing on every bench, with `box/production.fit_location` and
   `build_pool` wired and the harness-equivalence check extended. Then water, the proximity layer re-measured, and store on
   go; Steven re-prices. The step-13 rescope follows gate 16c (queued).
