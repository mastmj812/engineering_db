# BOX step 12b — water: sql/62 + water on the record run — CONTAINER-VALIDATED, AT THE LIVE-APPLY ASK

2026-10-19. Plan §5 step 12b, under D107 (method), D108 (raw box_v2 oil), D109 / D110 (tiers).

**Status.** Nothing is applied live yet. sql/62 and the water store were validated in a throwaway PostGIS container
(`box12b`, port 5436) that holds the live box state, copied read-only.

## 0. Headline

1. **sql/62 (16 / 16 checks, applied twice: idempotent).**
   - `box.pud_forecast_stream` admits `water`.
   - A per-stream `tier` column (validated | provisional): required on water, and never above the location's coverage.
   - New table `box.location_water_analog` for the named measured-water analogs.
   - The rest of the box chain re-applied green in the container: sql/54-56-57-58-52-60-61-63. sql/60's apply smoke now
     tests an unknown stream instead of water.
2. **Water built for every forecast location of record run 10.**
   - 50,963 locations (18,607 covered + 32,356 covered_provisional), 0 WOR fit failures.
   - Built from run 10's own artifact (`runs/box9/run.pkl`, sha256 9c45e262…), on its raw box_v2 oil months (D108).
   - The selection reproduces step 11's reach exactly in every radius class (5 → 50 mi).
   - 49 locations are on calculated-fallback cohorts, all BS2_C TX.
   - 76 min build, read-only.
3. **Stored into the container's run 10 in one transaction (410 s), every identity check green:**
   - oil / gas stream rows unchanged: ordered md5 of every row, `oil 873f10a6…` / `gas ff0db292…`, the **same checksums as
     live run 10**;
   - 50,963 water rows = covered + covered_provisional;
   - 600 months per water stream summing to its EUR (0 off);
   - validated water = the WCA + BS2_S `covered` rows exactly (9,301); 41,662 provisional;
   - every location has ≥ 3 named water analogs (min 3, max 20; 829,345 rows);
   - a second store is refused ("run 10 already carries water").
4. **Water is appended to run 10, not stored as a new run.**
   - Oil / gas are untouched, so a new run would only duplicate 61 M oil / gas month rows (~7 GB).
   - Steven has priced nothing (`box_econ.box_pud_econ` = 0 rows), so no priced run changes under him.
5. **Storage.** +30.6 M month rows ≈ 5.2 GB, + 0.35 GB water analogs (container sizes). The live DB is 83 GB today; the
   month table goes from 9.6 GB to ~15 GB.

## 1. What a water row is (D107 / D108 / D110)

- **Selection.** The measured-water cohort of `box/water11` (steps 11 / 12a), as of run 10's data-through (2026-07-01).
- **Volumes.**
  - WOR curve: ln WOR = α + β · Np per 1,000 ft, fitted on the cohort's per-1,000-ft mean oil + water (boxfit ratio mode, post
    oil peak).
  - Applied month by month to the location's raw box_v2 oil months (600, uptime-free, × the oil's lateral multiplier).
  - No water haircut, no F(k) (D63).
  - EUR = Σ months: the raw 50-yr technical integral, no economic limit.
- **Tier.** `validated` on WCA and BS2_S `covered` rows, `provisional` everywhere else (D110).
- **`params` jsonb.**
  - method + oil basis, α, β, sub_mode, R²;
  - source: measured | calculated_fallback;
  - radius reached, thin, n analogs, NM share;
  - flags (fallback, thin, reach past 20 mi).
- **Run-level record.**
  - `forecast_run.disclosure -> 'water'` holds each group's tuning / holdout / pooled line (D110), the WCA-TX caveat, and the
    AVA / BS2_C tuning-only note.
  - The run notes now read "water: … D72 retired" in place of "no water (D72)".

Per group (`group_summary.csv`). WOR = water / oil on the raw oil, median location.

| group | locations | water tier | water EUR per 1,000 ft (median, bbl) | WOR cum-12 | WOR EUR | reach > 20 mi | fallback |
|---|---|---|---|---|---|---|---|
| WCA | 1,907 | validated | 235,894 | 2.75 | 2.93 | 3 | 0 |
| BS2_S | 7,394 | validated | 220,711 | 2.42 | 2.81 | 2 | 0 |
| WCXY_WCA1 | 3,183 | provisional | 436,041 | 4.71 | 5.27 | 0 | 0 |
| WCB_1 | 4,133 | provisional | 470,222 | 6.74 | 7.07 | 43 | 0 |
| WCB_2 | 2,584 | provisional | 572,512 | 9.43 | 9.86 | 23 | 0 |
| WCC | 1,990 | provisional | 564,813 | 9.92 | 11.18 | 0 | 0 |
| BS3_S | 9,192 | provisional | 261,726 | 3.32 | 3.54 | 98 | 0 |
| BS3_C | 7,774 | provisional | 219,062 | 3.61 | 3.79 | 811 | 0 |
| BS1_S | 4,990 | provisional | 262,756 | 3.21 | 3.61 | 430 | 0 |
| BS2_C | 3,005 | provisional | 188,409 | 2.75 | 2.85 | 656 | **49** |
| AVA_0 | 607 | provisional | 164,636 | 1.65 | 2.15 | 1 | 0 |
| AVA_1 | 1,365 | provisional | 95,048 | 1.07 | 1.24 | 1 | 0 |
| AVA_2 | 2,839 | provisional | 154,392 | 1.76 | 2.13 | 1 | 0 |

The deeper Wolfcamp benches carry the high WORs (WCB / WCC ~7–11 over life), Bone Spring ~3–4, AVA ~1–2. The WOR rises over
life on every group (EUR WOR > cum-12 WOR).

## 2. Downstream readers (checked)

- **erebor** `backend/app/api/box.py` reads oil / gas by name (`bso` / `bsg` joins, month rows filtered to oil, or iterated
  over its own `STREAMS`). Water rows change nothing it shows. A water display is a follow-up, not part of this step.
- **engineering_db** `box_eur_map` / deck builder filter `stream = 'oil'`.
- `box_pud_run identity` counts only the oil / gas of a run at store time, before water exists.
- **novi-quarterly-reload skill §9**, new step 3b: water is added to every new record run with
  `box_water_run build` + `store`.
- `scripts.box_prune_runs` cascades water through the same FKs.
- **Data dictionary.** Consumer line added for `box.location_water_analog`; the HTML is regenerated after the live apply (the
  generator reads the live catalog).

## 3. The live-apply ask (Michael) — explicit go needed for each write

1. **Apply sql/62 live:** `python -m scripts.apply_box_water` (expect 16 / 16; DDL on box only, no ETL object touched).
2. **Store water on record run 10 live:** `python -m scripts.box_water_run store --out runs/box12b`, from this worktree.
   - Artifact `runs/box12b/water.pkl`, sha256 9519614d…; code 83bd86f (built at 00ca983, the same box/ + water scripts; the branch was rebased onto main after #160 merged). The `-dirty` stamp was edited out
     with the reason recorded in the artifact: two unrelated scripts (apply_box_pud_forecast.py, gen_data_dictionary.py) were
     edited during the build and are not imported by it.
   - Pre-checks: record = run 10; `box_econ.box_pud_econ` = 0; live oil / gas md5 = the container's (verified above).
   - One transaction; rolls back on any identity failure.
   - Expect ~10–20 min on Supabase for the 30.6 M-row COPY (container: 7 min).
3. **Then:**
   - regenerate the data dictionary (`python -m scripts.gen_data_dictionary --html docs/data_dictionary.html`) and commit it;
   - record **D111: D72 retired** (water is a delivered stream, tier per D110);
   - a note to Steven. Draft: *"BOX run 10 now carries a water stream for every covered location: WOR vs cumulative oil from
     measured-water analogs, on the raw box_v2 oil. It is validated on WCA and BS2_S and provisional elsewhere; the disclosure
     lines are in forecast_run.disclosure -> 'water'. Volumes are uptime-free, like oil and gas. Oil and gas are unchanged."*
4. **Follow-ups, not in this step:**
   - erebor water display + the provisional / WCA-TX disclosure text;
   - the Blue Ox drop picking up BOX water.

## 4. Reproduce

```
python -m scripts.box_water_run build --run-pkl runs/box9/run.pkl --out runs/box12b --workers 14   # 4,552 s, read-only
# container (DB_HOST=localhost DB_PORT=5436 ...):  apply_box_schema ... apply_box_provisional, apply_box_water (x2),
#   runs/box12b_container/copy_live.py (live -> container, read-only), then:
python -m scripts.box_water_run store --out runs/box12b                                              # 410 s, green
```

Logs: `runs/box12b_container/*.txt`, `runs/box12b/store_container.txt` (git-ignored); container `box12b` kept until the live
store is done.
