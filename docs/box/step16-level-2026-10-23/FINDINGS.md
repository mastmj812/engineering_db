# Step 16 level work on the r2 selection of record (D121) — 2026-10-23 (POST-LOOK, read-only)

Run on the 16c tuning views (no new backtest runs): `python -m scripts.box_step16_level runs/step16c docs/box/step16-level-2026-10-23`.
This is not a pre-registered score; it informs the 16d production stack. Bias = Σ actual / Σ forecast − 1 (negative = forecast
HIGH), oil, well-level unless stated. "Thin" = a backtest well with < 3 modern local wells within 3 mi at its cutoff (the
edge / thin-PDP situation).

**Treatments of r2 (`box_v2s_r2`):**
- `r2p` = r2 × the PDP-proximity factor exactly as production applies it (D113, `box.prox_pud.decide` on the study's
  configuration table and factor table; oil only). 1,554 of 11,336 backtest wells are multi-parent and get a factor; the mean
  factor is 0.982. The factor table was fit on these same folds (D113), so this part is partly in-sample.
- `r2p_wf` = r2p × the D57 walk-forward haircut per bench: the mean package bias at ≥ 2 earlier cutoffs with ≥ 30 packages.
- `r2p_wfpool` = the same haircut pooled over the eight provisional groups.

## 1. Same wells, every treatment

| | wells (thin) | v2s | r2 | **r2p** | r2p_wf | r2p_wfpool |
|---|---|---|---|---|---|---|
| provisional oil cum-12 | 2,108 (739) | −7.1 % | −10.5 % | **−7.9 %** | −3.2 % | −6.9 % |
| provisional oil cum-12, thin | | −4.7 % | −10.0 % | −7.5 % | −2.0 % | −6.5 % |
| provisional oil cum-24 | 1,301 (446) | −7.2 % | −12.7 % | **−10.5 %** | −7.6 % | −8.7 % |
| provisional oil cum-24, thin | | −8.9 % | −17.4 % | −15.0 % | −12.4 % | −13.4 % |
| validated oil cum-12 | 4,769 (386) | −6.1 % | −6.3 % | −4.8 % | **−1.8 %** | — |
| validated oil cum-12, thin | | −14.7 % | −12.2 % | −11.4 % | −8.8 % | — |
| validated oil cum-24 | 3,594 (319) | −7.1 % | −8.3 % | −6.9 % | **−1.2 %** | — |
| validated oil cum-24, thin | | −15.0 % | −13.7 % | −12.8 % | −8.4 % | — |

(The wells are those where every treatment exists. The walk-forward needs two earlier cutoffs, so these are the 2021–2024
cutoffs.)

## 2. What it says

1. **The proximity layer already in production removes most of r2's extra over-forecast.** Provisional oil cum-12 goes from
   −10.5 % to −7.9 % (v2s raw −7.1 %); validated from −6.3 % to −4.8 %. Production run 14 applies this layer, so in production
   terms r2 lands close to v2s's level. The ~3-point gap in 16c was largely the child-beside-parent effect, which the
   local-first cohort brings into the forecast and the proximity layer was built to take out.
2. **The provisional "level problem" is a vintage episode, not a steady drift.** r2p package bias, oil cum-12, pooled over the
   provisional groups, by cutoff:

   | cutoff | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
   |---|---|---|---|---|---|---|
   | packages | 171 | 212 | 303 | 338 | 358 | 291 |
   | bias | +3.4 % | +5.1 % | −10.0 % | −11.2 % | −0.3 % | −2.0 % |

   The miss sits in wells first producing in 2022–23; the two most recent cutoffs are within 2 %. A walk-forward haircut
   (built from earlier cutoffs) lags an episode like this. Cum-24 exists only through the 2023 cutoff, so it still carries the
   episode (−10.5 %).
3. **The validated benches show the steady bias the walk-forward is built for:** −2 to −7 % each cutoff. It takes them to
   −1.8 % (cum-12) and −1.2 % (cum-24).
4. **Per bench, the walk-forward overshoots on the thin provisional benches.** BS1_S r2p_wf oil cum-12 +8.4 %, BS2_C +20.3 %,
   WCB_2 +11.5 % (forecast LOW), from 2–4 earlier-cutoff cells. The family-pooled version barely moves the level
   (−7.9 → −6.9 %).
5. **Thin-control wells still read high at 24 months:** provisional −15.0 %, validated −12.8 % with r2p. This is the Blue Ox
   opportunity-set situation, and it is the disclosure every edge / thin workup should carry until it is corrected.

## 3. Validated benches re-earn under r2 (pooled cells, like for like with each record's form)

| bench | record form | record: fails / max \|bias\| | r2 + proximity (+ haircut where the record has one) |
|---|---|---|---|
| WCA | `box_v2_wf` | 0 / 6.0 % | `r2p_wf` 0 / 4.8 % |
| BS2_S | `box_v2_wf` | 2 / 7.2 % | `r2p_wf` 2 / 11.8 % |
| WCXY_WCA1 | `box_v2` | 0 / 9.3 % | `r2p` 0 / 9.9 % |
| WCB_1 | `box_v2` | 4 / 35.0 % | `r2p` 2 / 14.0 % |
| WCC | `box_v2` | 4 / 14.4 % | `r2p` 4 / 12.5 % |

No bench fails more pooled cells than its record. WCB_1's 35 % gas cell is gone (14 % max). BS2_S's largest cell rises from
7.2 to 11.8 %. This is a pooled view; WCA's accepted form is per-cutoff on the full fold, not recomputed here with the
proximity factor.

## 4. Proposed 16d production stack (for Michael)

- **Selection:** r2 (D121) on all 13 benches, with measured spacing (D119).
- **Proximity layer:** re-measured on the new run (D116), as now.
- **Walk-forward haircut:** WCA and BS2_S only, as their records do now, recomputed from the r2 + proximity tuning cells (D120
  §4 source rule). WCXY, WCB_1, WCC and the eight provisional groups stay raw. The provisional per-bench haircut overshoots,
  and the pooled one lags the 2022–23 episode.
- **Disclosure on every workup:** the radius class, the r2 relaxations used (count, spacing), the Cui translation factor, and
  the thin-control bias line (cum-12 / cum-24, by tier) next to the existing D69 / D105 lines.
- **Open, not part of 16d:** a thin-control correction (§2.5). It needs its own pre-registered test; the 2026 prospective
  cohort is its clean check.
