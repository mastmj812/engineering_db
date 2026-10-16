# D92 — haircut shape: C1 smooth rate factor (rehearsed, NOT stored)

Built 2026-10-15 on branch `claude/box-d92-c1-haircut` (code 6d5ef2a). **Rehearsed as the record in a throwaway PostGIS
container only; nothing is written to Supabase.** Live store needs Michael's go.

## 1. The defect (record run 6, every covered PUD)

D62 applied its factors to CUMULATIVE production, linear between cum-12/24/36/48 and held flat after month 48. Monthly
volume = Δ(factor × cum), so while the factor falls each month also gives back (factor drop × all production to date),
and the rate snaps back when the factor goes flat. Stored run 6:

- oil month 36 → 37: −29 % (Pad 3545 WCA 2: 2,513 → 1,785 bbl); month 48 → 49: ×2.0 (992 → 2,031). **Year-4 oil = 0.735 ×
  year 5** (median; P10 high 0.802, P90 low 0.680). All 1,907 rise at month 49.
- gas: the mirror image (its factor rises 1.019 → 1.059): year-4 gas = 1.56 × year 5; all 1,907 step up at month 37.
- cum at each knot and the 50-yr EUR were exactly D62 as written; only the monthly shape (what Steven's D16 table and an
  NPV see) was nonphysical. Rendered in erebor's Map-tab overlay, where Michael caught it.

## 2. The method (D92, Michael's choice 2026-10-15)

Rate factor **g(k) = a + b·ln(min(k, 48))**, held at g(48) after month 48; (a, b) by least squares per location so the realised
cumulative factor Σ(raw × g)/Σraw at months 12/24/36/48 matches the D62 table (equal weights). D62's factor TABLE (the measured
walk-forward bias) is unchanged; only how it is applied changes. `box/production.apply_haircut_c1`; `apply_haircut` (D62 as
built) kept to reproduce runs 4 and 6. Scored on run 6's own raw months (`scripts.box_pud_run rehaircut --from runs/box7c_r2`):
same pool, fits, analogs, F(k) and disclosure — only the haircut application differs.

| | cum-12 | cum-24 | cum-36 | cum-48 | tail (after 48) | EUR vs run 6 |
|---|---|---|---|---|---|---|
| oil D62 target | 0.943 | 0.929 | 0.916 | 0.876 | 0.876 (cum) | — |
| oil C1 realised (median) | 0.950 | 0.920 | 0.903 | 0.891 | **0.768** (rate) | **−4.2 %** (0.955–0.961) |
| gas D62 target | 1.002 | 1.021 | 1.019 | 1.059 | 1.059 (cum) | — |
| gas C1 realised (median) | 0.998 | 1.022 | 1.036 | 1.045 | 1.122 (rate) | **+2.4 %** (1.021–1.028) |

Totals over 1,907 covered PUDs: oil 1,096.7 MMbbl (run 6: 1,144.9); gas 5,621.2 Bcf (5,490.6). Year 4 / year 5 now 1.28 oil,
1.22 gas (the raw decline). Oil: no post-peak monthly rise anywhere (D62 had 1,907). Reading the tail: D62's flat cum-48 factor
implied the RATE overstatement recovered from ~0.66 in year 4 back to 0.876 forever; C1 holds the rate factor where the
measured trend ends — the persistence stance of D54 stated in rate terms.

## 3. Container rehearsal (postgis/postgis:16-3.4, Supabase layout)

PostGIS in `extensions`, roles analyst_ro / anon / authenticated / steven (box_econ_writer). sql/54+56, 57, 58, 60, 52, 61
through their own apply scripts: all green. Live `box.extent` 6 / 7 and `box.bench_scope` copied read-only. Then
`box_pud_run store --record --out runs/box8_c1` (log: `runs/box8_c1/store_container.txt`): 33,034 universe rows; covered 1,907 +
5 no_analogs = 1,912; 3,814 stream rows; every stream's 600 months sum to its EUR within 0.1 % (0 off); every covered location
≥ 3 named analogs. Container vs live run 6: coverage / analog counts / radius / flags / named analogs / raw EUR / P50 params
identical (planned spacing equal to 5e-12 ft); only EUR + monthly volumes move. Run notes and `haircut.method` state D92 and
"re-haircut of build 3f7ba4d".

## 4. Asks

1. **Go to store live as the record** (`python -m scripts.box_pud_run store --record --out runs/box8_c1`, ~40 s). Run 6 is
   superseded and kept (D75). Steven has priced nothing yet (box_econ empty), so no priced run is affected.
2. **Gas early bump (flagged, not resolved).** Gas's factor RISES with time, and ln(k) is steepest in the first months, so on
   82 locations the gas peak moves 1–4 months later (biggest month-over-month rise +4.1 %; median +1.5 %). Alternative
   **C1b** = g flat through month 12 (`ln(clamp(k, 12, 48))`): no bump, knots fit slightly better (oil .948/.927/.904/.885) but
   EUR moves twice as far (oil **−9.0 %**, gas **+5.1 %** vs run 6). Recommendation: keep C1 as approved — the bump is
   small and early; C1b's extra −4.8 pt on oil EUR rests on extrapolating a steeper post-12 slope.
3. After a live store: erebor's BOX disclosure shows "haircut applied ×factor" from the D62 table — follow-up to show the
   realised factor (`haircut[s][k].realised_median`) next to the target.
