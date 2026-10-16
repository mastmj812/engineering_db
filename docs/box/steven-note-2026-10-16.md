# Note to Steven — BOX forecasts on oilgas (draft for Michael to send)

Updated 2026-10-16 for record run 7 (supersedes the run-4 draft in `step7d-2026-10-15/FINDINGS.md` §6, ask 5). Every number
below was checked live on 2026-10-16. Not sent; Michael sends it.

---

> Steven — the BOX type-curve forecasts for Delaware WCA are live on oilgas and you can read them now. A few things to know
> before you run econs on them.
>
> **Which run.** Always take the run marked `is_record` in `box.forecast_run`. Today that is **run 7** (Novi 2026Q3
> locations, production through 2026-07-01, stored 2026-10-16). It covers **1,907 WCA_1 / WCA_2 PUD locations**. Run 7
> replaced run 6 yesterday: we changed how the hindcast haircut is applied, so a location's monthly volumes no longer drop in
> year 4 and jump back at month 49. **Oil EUR is about 4 % lower than run 6** (gas about 2 % higher). If you pulled run 6
> volumes, please re-pull. The location ids did not change between runs 6 and 7.
>
> **Where the numbers are.**
> - `box.pud_forecast_month` — monthly oil (bbl) and gas (mcf) volumes, months 1–600, one row per (run, location, stream, month).
> - `box.pud_forecast_stream` — per location and stream: EUR, EUR per 1,000 ft, cum-12 / cum-24.
> - `box.pud_forecast` — the location's coverage, lateral, planned spacing, analog count and review flags.
> - `box.location` — our location id and geometry; `box.location_source` maps it to the Novi stick id.
>
> ```sql
> SELECT m.location_id, m.stream, m.month_no, m.volume
> FROM box.pud_forecast_month m
> JOIN box.forecast_run r ON r.run_id = m.run_id AND r.is_record
> ORDER BY 1, 2, 3;
> ```
>
> **What the volumes are.** Technical forecasts only: each is the analog cohort P50 for the location (offset PDP wells, same
> bench), scaled to its lateral and corrected by a stated haircut for this method's measured historical over-forecast. EUR is
> the raw 50-year volume (no economic limit — that is yours). **Oil and gas only, no water** in this version. NGL as in the
> Blue Ox drops (your yield).
>
> **Downtime — the one thing to get right.** The volumes are **uptime-free**: they carry no downtime. Apply **your own
> downtime factor**, and only that one. Don't also apply our published calendar factor F(k) (stored on the run; about
> 0.90 / 0.91 / 0.92 for oil at months 12 / 24 / 48), or you count downtime twice. One check: the haircut was measured on
> forecasts that already had about 10 % year-1 downtime, so it's right if your factor is in that range. If yours is very
> different, tell Michael and we'll look at it.
>
> **Where your econ goes.** Write it to `box_econ.box_pud_econ`: the same metric and provenance columns as your `pud_econ`,
> keyed (`run_id`, `location_id`, `deck_id`, `assumption_set_id`). Two things are new:
> - **`downtime_basis` is required** on every row: `steven_downtime_factor` (expected) or `box_calendar_factor`.
> - Put the EUR you priced (before your downtime factor) in `oil_eur` / `gas_eur`. `box_econ.box_pud_econ_tie` flags any
>   location where it differs from ours by more than 0.5 %, so a mis-loaded curve shows up before anyone screens on it.
>
> Only covered locations of a run can be priced, and a run you've priced can't be deleted from under you. Your existing
> `pud_econ` on Novi sticks stays as is and gives the BOX-vs-Novi comparison. Your econ shows in erebor's Highgrade tab as a
> screen labelled with your deck and assumption set (display only; nothing flows back into the forecasts).

---

**Facts behind the note (live, 2026-10-16):** record run 7, data through 2026-07-01, Novi 2026Q3, 1,907 covered;
1,907 / 1,907 covered locations keep their run-6 location id; F(k) oil 0.895 / 0.908 / 0.921 and gas 0.918 / 0.945 / 0.980
at months 12 / 24 / 48; `box_pud_econ_tie` threshold 0.5 %; his sandbox `box_econ.pud_econ` = 501,045 rows (untouched);
role `steven` has SELECT on every box table and INSERT on `box_econ.box_pud_econ`. Run 7 vs run 6: oil EUR median −4.2 %,
gas +2.4 % (D92).
