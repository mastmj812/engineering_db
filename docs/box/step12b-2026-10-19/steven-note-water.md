# Draft — note to Steven (Michael sends; no email convention: Slack / direct)

Steven — BOX record run 10 now carries a **water** stream for every covered location (50,963). Oil and gas are unchanged,
byte for byte.

**How water is built**
- Water = water-oil ratio vs cumulative oil, fitted on nearby same-bench wells with MEASURED water (sql/41 measured, all
  reported NM water, seller VDR daily where loaded).
- The ratio is applied month by month to the location's BOX oil before any haircut.
- 49 locations (BS2_C, Texas) had no measured offsets within 50 mi and use vendor-calculated water instead; they are flagged.

**Where it lives**
- `box.pud_forecast_stream` / `box.pud_forecast_month` with `stream = 'water'`: 600 monthly volumes, uptime-free like oil
  and gas, and no haircut.
- Each water row has a `tier`:
  - `validated` on WCA and BS2_S. Out-of-sample water bias on those benches was within about ±10 % at cum-12 / 24 / 36.
  - `provisional` everywhere else.
- The named water analogs per location are in `box.location_water_analog`.
- The per-bench bias lines (tuning / holdout / pooled) are in `box.forecast_run.disclosure -> 'water'`.

**Caveats**
- On WCA in Texas, the holdout water ran about 15–17 % high (NM about on target).
- On the provisional benches, water runs well below actual on AVA (about 50–65 %), and at cum-36 on BS1_S / BS3_C.
- The disclosure lines carry the numbers.

Your existing downtime treatment applies to water the same way it applies to oil and gas.
