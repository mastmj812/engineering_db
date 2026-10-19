# BOX step 12a — water: freeze, tuning identity, ONE-TIME holdout score — GATE 12a CLOSED 2026-10-19 (§7)

2026-10-19. Plan §5 step 12a, under the rule frozen at gate 11.

- **Rules applied.** D107 (`ratio`: WOR vs cumulative oil on measured-water analogs), D108 (on the raw box_v2 oil months),
  D109 (acceptance rule).
- **Read-only.** No DDL; sql/62 stays reserved for 12b. No oil or gas forecast was touched.
- **Sign convention.** Error = actual / forecast − 1; negative = forecast HIGH.

## 0. Headline

1. **Spec frozen at 546c51a** (pushed before either run). `intervals_water.csv` is checked against its gate-11 sha256
   `969981e5…` before scoring.
2. **Tuning identity: 39 / 39 pooled ratio cells reproduce step 11, max |diff| 4.4e-16.**
   - Same data: curated.production was last refreshed 2026-10-18 14:49 UTC, before step 11 ran, and not again before the
     holdout finished at 15:28 UTC today.
3. **Holdout scored once: all 26 judged cells lie inside their frozen tuning intervals.** No cell is outside. One more cell is
   not judged (BS1_S cum-36, 7 packages).
4. **D109 water tiers.**
   - **WCA and BS2_S → validated water.**
   - The other 11 groups → provisional water. WCXY_WCA1, WCB_1 and WCC fail rule (ii) on tuning spread, as gate 11 foresaw.
     The 8 D105 groups are capped at their oil's provisional tier.
5. **Disclose with WCA: TX holdout water runs 15–17 % HIGH** (−16.7 / −14.6 / −15.7 % at cum-12 / 24 / 36, 133–188 packages).
   NM is flat (−5.1 / −0.9 / −0.1 %).
   - Tuning TX was −9.7 / −6.1 / −4.7 %.
   - WCA's pooled holdout cum-36 (−8.7 %) sits 0.1 pt inside its interval's low end (−8.8 %).

## 1. Freeze (`546c51a`)

- **Spec.** `box/water11.py` selection (D54 ladder + 30 / 40 / 50 mi water extension, measured labels as of the cutoff, NM
  amendment, calculated fallback). Method `ratio` on the raw box_v2 oil months × F_oil(k).
- **Rule.** `box/water12a.py` (D109 tier logic, `INTERVALS_SHA256`, identity tolerance 1e-9).
- **Runner.** `scripts/box_water11.py holdout` refuses to run without `--holdout-once`.
- **Tests.** `tests/test_box_water11.py`: 8 pass, including the D109 tier rule and the identity check. Ruff is clean on every
  touched file.
- **Holdout inputs.** Each group's SPENT oil holdout run, copied to `runs/step12a_inputs/<group>/` (63 files, sha256 in
  `runs/step12a_inputs/digests.txt`): the holdout views (package ids, held-out flag) and the uptime-free box_v2 oil months with
  their F_oil(k).
  - WCA = the 9a guard holdout (analog fold, step-1 well set, the same set as WCA's water tuning view).
  - BS2_S and WCXY_WCA1 = the 9b holdout runs.
  - WCB_1, WCC, BS3_S, BS3_C, WCB_2 and BS1_S = the step-15 holdout runs.
  - Every holdout row is asserted held out before anything is computed.
- **No holdout run exists for AVA_0 / 1 / 2 or BS2_C.** D105 benches were never holdout-scored, so no holdout oil forecast
  exists to carry water.
  - Producing one would mean running their oil holdout, which D105 deliberately did not do.
  - Their water stays provisional either way; their disclosure is the tuning line (§4). Ask 3.

## 2. Tuning identity (`identity.csv`, `cells_tuning_rescore.csv`)

- The re-score ran the step-11 tuning path at 546c51a on the same inputs (digests unchanged).
- All 39 group × horizon ratio cells agree in packages, bias, band and benchmark within 4.4e-16.
- The first pass lost AVA_2 to a dropped Supabase connection ("server closed the connection unexpectedly"). AVA_2 was re-run
  alone; its three cells are identical too.

## 3. Holdout cells (`holdout_cells.csv`; ratio, pooled across cutoffs; 3,409 measured-water wells, 7 on a calculated-fallback cohort)

| group | cum | holdout pkgs | holdout bias | frozen interval | verdict | ±20 % (reported) | spread vs bench (reported) |
|---|---|---|---|---|---|---|---|
| **WCA** | 12 | 344 | −11.4 % | −13.0 … −1.9 % | INSIDE | yes | 1.01 vs 0.83 (miss) |
| **WCA** | 24 | 297 | −8.2 % | −10.5 … +3.3 % | INSIDE | yes | 0.99 vs 0.91 (ok) |
| **WCA** | 36 | 240 | −8.7 % | −8.8 … +7.8 % | INSIDE (edge) | yes | 1.05 vs 0.99 (ok) |
| **BS2_S** | 12 | 144 | −0.8 % | −6.1 … +11.2 % | INSIDE | yes | 0.84 vs 0.86 (ok) |
| **BS2_S** | 24 | 118 | +3.0 % | −6.9 … +11.7 % | INSIDE | yes | 0.85 vs 0.83 (ok) |
| **BS2_S** | 36 | 67 | −1.4 % | −10.3 … +13.6 % | INSIDE | yes | 0.62 vs 0.82 (ok) |
| WCXY_WCA1 | 12 / 24 / 36 | 83 / 72 / 58 | −12.1 / −9.3 / −6.3 % | inside all | INSIDE ×3 | yes | misses ×3 |
| WCB_1 | 12 / 24 / 36 | 109 / 91 / 77 | +1.0 / −0.8 / −14.3 % | inside all | INSIDE ×3 | yes | ok ×3 |
| WCC | 12 / 24 / 36 | 44 / 30 / 20 | −7.3 / −12.4 / −11.2 % | inside all | INSIDE ×3 | yes | cum-24 miss |
| WCB_2 | 12 / 24 / 36 | 51 / 38 / 25 | −1.4 / −6.8 / −1.8 % | inside all | INSIDE ×3 | yes | cum-36 miss |
| BS3_S | 12 / 24 / 36 | 122 / 97 / 55 | −0.7 / +4.4 / +8.9 % | inside all | INSIDE ×3 | yes | ok ×3 |
| BS3_C | 12 / 24 / 36 | 79 / 56 / 26 | +4.7 / +10.5 / +33.6 % | inside all | INSIDE ×3 | cum-36 no | cum-12 miss |
| BS1_S | 12 / 24 / 36 | 40 / 28 / 7 | 0.0 / +14.9 / +42.1 % | inside / inside / — | INSIDE ×2, n.j. | cum-36 no | ok |

The water holdout says the same as tuning everywhere, including the provisional benches' known cum-36 under-forecast
(BS3_C +33.6 %, BS1_S +42 %; the water forecast is low there).

## 4. Water tier per group (`water_tiers.csv`) and disclosure lines (`disclosure_water.csv`)

| group | oil | water (D109) | why | tuning / holdout / pooled bias, cum-12 · 24 · 36 |
|---|---|---|---|---|
| **WCA** | validated | **validated** | all three conditions | −7.7 · −3.8 · −1.1 / −11.4 · −8.2 · −8.7 / −8.7 · −5.0 · −3.1 % |
| **BS2_S** | validated | **validated** | all three conditions | +2.0 · +2.0 · +0.8 / −0.8 · +3.0 · −1.4 / +1.3 · +2.2 · +0.3 % |
| WCXY_WCA1 | validated | provisional | tuning spread, 2 / 3 cells | −6.2 · −4.3 · −4.2 / −12.1 · −9.3 · −6.3 / −7.7 · −5.5 · −4.7 % |
| WCB_1 | validated | provisional | tuning spread, 3 / 3 | +1.6 · +2.7 · −6.3 / +1.0 · −0.8 · −14.3 / +1.4 · +1.7 · −8.9 % |
| WCC | validated | provisional | tuning spread, 3 / 3 | −0.6 · −3.7 · +2.4 / −7.3 · −12.4 · −11.2 / −2.3 · −5.7 · −1.2 % |
| WCB_2 | provisional | provisional | oil tier + 1 tuning cell | −3.5 · −3.9 · −3.5 / −1.4 · −6.8 · −1.8 / −3.0 · −4.5 · −3.1 % |
| BS3_S | provisional | provisional | oil tier + 1 tuning cell | −4.5 · +4.3 · +11.5 / −0.7 · +4.4 · +8.9 / −3.6 · +4.3 · +10.9 % |
| BS3_C | provisional | provisional | oil tier + 2 tuning cells | +8.6 · +8.5 · +32.0 / +4.7 · +10.5 · +33.6 / +7.7 · +9.0 · +32.4 % |
| BS1_S | provisional | provisional | oil tier + 1 tuning cell | +10.8 · +8.4 · +40.9 / 0.0 · +14.9 · (+42.1, 7 pkgs) / +8.8 · +9.8 · +41.1 % |
| BS2_C | provisional | provisional | oil tier; no holdout run | +6.4 · −5.3 · −16.8 / — / — |
| AVA_2 | provisional | provisional | oil tier; no holdout run | +11.1 · +13.7 · +20.7 / — / — |
| AVA_1 | provisional | provisional | oil tier; no holdout run | +50.9 · +54.9 · +63.8 / — / — |
| AVA_0 | provisional | provisional | oil tier; no holdout run | +54.7 · +65.8 · +110 / — / — |

Pooled = tuning + holdout packages together (D102 pattern). Per D105, a workup never shows the pooled figure alone.

**WCA by state** (`holdout_cells_by_state.csv`).
- TX holdout: −16.7 / −14.6 / −15.7 % (188 / 160 / 133 packages). NM: −5.1 / −0.9 / −0.1 % (156 / 137 / 107).
- The measured benchmark misses TX by only −3 … −12 %, so this is a WCA-TX level issue the analog WOR carries. TX WCA locations
  draw ~5 % NM analogs, so it is not NM water being pushed into TX.
- Disclosure, not a spec change: the rule passed, and a fix now would be tuning after the look.

**BS2_S per cutoff** (`holdout_cells_per_cutoff.csv`). Cum-12 drifts from +16 % (2019) to −19 % (2024, 2024 cutoff only).
- Newer packages are drier than the WOR says.
- Watch item for the prospective read; not gating.

## 5. Gate-12a asks (Michael)

1. **Accept the D109 verdict as scored:** water validated for WCA and BS2_S; provisional for the other 11, each workup carrying
   its tuning / holdout / pooled water line (§4).
2. **WCA TX caveat.** Should WCA workups in TX state the measured holdout over-forecast (water ~15–17 % high at cum-12 / 36,
   NM ~0) the way D101 states BS2_S's edges? Recommended: yes, workup text only.
3. **AVA_0 / 1 / 2 and BS2_C:** accept tuning-only water disclosure.
   - Their oil was never holdout-scored (D105), so there is no holdout oil to carry water.
   - Running one would spend their oil holdout. Their water is provisional either way.
   - Recommended: tuning-only.
4. **Go for 12b.**
   - sql/62: `box.pud_forecast_stream` / `pud_forecast_month` admit water, plus a water tier / provenance column for the
     validated-vs-provisional split, D107 reach and fallback flags.
   - Container-validated first, then go-apply.
   - A production run with water on all 13 groups.
   - D72 retired by a new decision. Steven told.

## 6. Reproduce

```
python -m scripts.box_water11 tune    --out runs/step12a/tuning  --inputs runs/step11_inputs  --workers 12   # identity (~45 min)
python -m scripts.box_water11 holdout --holdout-once --out runs/step12a/holdout --inputs runs/step12a_inputs \
       --groups WCA,BS2_S,WCXY_WCA1,WCB_1,WCB_2,WCC,BS1_S,BS3_S,BS3_C --workers 12                         # 1,651 s, run once
python -m scripts.box_water12a_report                                                                         # this folder
```

The holdout ran 2026-10-19 15:01–15:28 UTC at 546c51a (`runs/step12a_holdout_sha.txt`). The report script came after; it only
aggregates the stored rows.

## 7. Gate 12a decisions (Michael 2026-10-19) — plan D110

1. **Tiers accepted as scored.** Water is validated for WCA and BS2_S and provisional for the other 11 groups. Each workup
   carries its §4 water line.
2. **WCA-TX caveat** goes in as workup text: TX water ~15–17 % high in the holdout, NM ~0.
3. **AVA_0 / 1 / 2 and BS2_C** carry a tuning-only water disclosure.
4. **Go on 12b.** sql/62 is container-validated first; Michael is asked before anything is applied live.
