# BOX step 7d: contracts, quarterly refresh, prospective freeze, rule text (gate 7d)

**Built 2026-10-15.** sql/61 is validated on a throwaway container only and **NOT applied**. The other pieces are code,
skill text and CLAUDE.md, with no warehouse writes.

## 1. Steven's econ contract: `sql/61_box_econ_contract.sql` + `scripts/apply_box_econ_contract.py`

**His sandbox already exists.** `box_econ.pud_econ` holds 501,063 rows: 167,015 Novi sticks × 3 decks (wti60 / 70 / 80,
HH $3.00), each deck with its own `assumption_set_id`.
- Provenance: schema_version 1.0.0, git_sha 5df7907, built 2026-09-23, pushed 2026-10-06.
- It prices **Novi's** forecasts. So it already IS the "run your deck on Novi once" exhibit the plan asked for.
- **All 1,929 covered BOX locations have a Novi-priced row in it** (joined on stick_id), so the BOX-vs-Novi comparison
  works straight from the data.

**The contract table `box_econ.box_pud_econ`** keeps his metric names and his provenance block, re-keyed:
- **Key:** `(run_id, location_id, deck_id, assumption_set_id)`.
- **Covered only:** a foreign key on `(run_id, location_id, coverage = 'covered')` means only covered BOX locations can be
  priced.
- **No deletes under him:** a priced run can't be deleted (no cascade).
- **`downtime_basis` is required:** `steven_downtime_factor` or `box_calendar_factor` (D63 / D81: one treatment, stated).
- **Tie-out:** the view `box_econ.box_pud_econ_tie` compares the EUR he loaded against the BOX stream EUR (±0.5 % →
  `eur_tie_fail`). His echoed EUR is the curve EUR before his downtime factor.
- **Ownership:** owner postgres; `box_econ_writer` gets SELECT / INSERT / UPDATE / DELETE only (no DDL); analyst_ro reads.
  A check asserts nothing in `box` depends on `box_econ` (D13).

**Container rehearsal:** `postgis/postgis:16-3.4` with sql/52–60 applied first and a `steven` login wired the same way as live.
`apply_box_econ_contract` passed **23/23, twice**:
- 15 validation checks;
- a smoke run AS `steven`: he prices a covered location, and the tie view reports its +0.500 % gap;
- each of these is refused: pricing a not-covered location, a duplicate key, a missing or unknown `downtime_basis`,
  `ALTER TABLE` by steven, and deleting a priced run.

**Blast radius of the live apply:** one new table + one view in `box_econ`, plus grants. Steven's sandbox is untouched.
Nothing else changes; no app reads it yet. It takes seconds.

## 2. D73 crosswalk (in `box_pud_run store`)

Without this, `store` refused any new Novi vintage. It now carries locations forward from the most recent earlier vintage.
- **The match:** same basin + `formation_blueox`, and ≥ 50 % of the SHORTER stick lies within **250 ft** of the other (rule
  9 co-extent). Matching is 1:1, greedy by share, then by midpoint distance.
- **What follows:** unmatched sticks become `new` locations; unmatched locations stop at their `last_seen_vintage`.
- **Order guard:** storing an older vintage than one already stored is refused.
- **Tests:** 2 new pure tests (co-extent / shorter-stick / other-basin / one-to-one / greedy).

**Container rehearsal:** I seeded the real 2026Q3 record, then stored a synthetic "2026Q4" built from it:
- 92 % of sticks re-issued about 186 ft east under new ids;
- 4 % moved about 1,240 ft;
- 4 % dropped.

Result: **30,755 carried** (minimum share 0.511), **1,059 new**, **2,407** locations stopped at 2026Q3 (= 1,348 dropped +
1,059 whose successor moved too far). Re-storing 2026Q3 afterwards was refused.

**Behaviour to know:** 225 of the 1,284 "moved 1,240 ft" sticks landed on a NEIGHBOURING location's line and took that
location's id. A stick drawn where a location was is that location. That's geometry identity, as D73 defines it.

## 3. Quarterly refresh: `novi-quarterly-reload` skill §9 (new)

Build → store (D73) → verify → render → tell Steven the new `run_id` → prospective scoring when due. Every write is its own
explicit go. `build` gained `--wells <dir>` for the analog-pool well set.
**One open decision is written into the skill (ask 3):** how the pool's gate-1 well set is refreshed each quarter. Today it's
the 2026-10-06 frozen set, so new producers never become analogs.

## 4. Prospective 2026 cohort: frozen (`box/prospective.py`, `scripts/box_prospective.py`)

The definition is frozen **before any outcome was looked at**, and SHA-256-pinned (`a72c797d…`). `tests/test_box_prospective.py`
fails CI if anyone edits it. What's frozen:
- **The fold:** the next D53 rolling-origin fold, cutoff 2025-12-01.
- **The cohort:** Delaware WCA-pool wells (WCA_1 / WCA_2 / WCXY) first producing in calendar 2026, real lateral, midpoint
  inside extent 6.
- **The method:** box_v2 × the **D62 haircut as delivered** (record run 4). That's what Steven receives, rather than the
  D58 walk-forward rule.
- **Grain / verdict:** D53 / D58 / D70 unchanged. cum-12 / 24 / 36 are judged at ≥ 30 packages; cum-6 is reported only; NM
  vs TX cum-12 spread is the D68 watch item.
- **Stated difference:** bench comes from curated `formation_blueox` as-is (the gate-1 consensus class rule isn't re-run on
  2026 wells).

**`status` today:** 378 cohort wells (WCA_1 185 / WCA_2 134 / WCXY 59). 75 already have the 7 reported months a cum-6 read
needs; none can be judged yet. cum-12 for the earliest wells arrives around 2027-Q2, which is why `score` isn't built yet
(it refuses, saying so).

## 5. Rule text

- **CLAUDE.md** (not in git; backup at the session scratchpad, `CLAUDE.md.pre-7d-2026-10-15`):
  - the scope rule gains the **D13** sentence: econ may be STORED in `box_econ` and shown as a screen with provenance, like
    Novi's NPV; nothing computes it, and it never flows back into a forecast, extent or location;
  - the failure-mode list gains **`box.*` and `box_econ.*` are app-owned**: who writes each, the record run, and §9 of the
    reload skill.
- **sql/31 / data dictionary:** box comments live in the box SQL files themselves (sql/54–61). sql/31 is curated-only. The
  dictionary was regenerated after sql/60, and is regenerated again after the sql/61 apply.

## 6. Asks for gate 7d

1. **Go-apply sql/61** (`python -m scripts.apply_box_econ_contract`; expect 23/23), then regenerate the dictionary.
2. **The D73 interpretation:** a 250-ft co-extent buffer, and neighbour-line takeover as geometry identity.
   Recommendation: accept.
3. **Quarterly pool refresh.** Recommendation: re-run bench QC + the class rule of record on the NEW wells only, no
   calibration cards. The alternative is a frozen pool (analogs never update, and the method decays).
4. **Prospective definition** (still changeable now, before any data):
   - formation_blueox bench, with no gate-1 re-run;
   - scored with the D62 haircut as delivered.

   Recommendation: accept as frozen.
5. **Steven.** I have NOT contacted him. A draft for you to send:

   > *Steven — BOX forecasts are live: `box.forecast_run` run_id 4 is the record (1,929 WCA PUD locations, oil/gas monthly,
   > uptime-free, haircut applied). Once Michael applies it, the contract table for pricing them is
   > `box_econ.box_pud_econ`: same metric + provenance columns as your `pud_econ`, keyed (run_id, location_id, deck_id,
   > assumption_set_id). One required field is new: `downtime_basis` — the volumes are uptime-free, so either you apply
   > your own downtime factor (`steven_downtime_factor`) or BOX's published F(k) (`box_calendar_factor`), never both. Load
   > the curve EUR you priced in oil_eur / gas_eur (before your downtime factor); `box_econ.box_pud_econ_tie` flags any
   > mismatch. Your existing `pud_econ` on Novi sticks already gives the BOX-vs-Novi comparison.*

6. **Confirm the CLAUDE.md wording** (§5).
