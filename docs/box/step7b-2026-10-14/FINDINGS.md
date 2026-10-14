# BOX step 7b: production schema (sql/60), gate 7b

**Built 2026-10-14. Validated on a throwaway PostGIS container only. NOT applied to Supabase, and nothing is stored.**
Files: `sql/60_box_pud_forecast.sql`, `scripts/apply_box_pud_forecast.py`, and `scripts/gen_data_dictionary.py`
(`_CONSUMERS` entries).

## 1. What the schema holds

| table | grain | role |
|---|---|---|
| `box.location` | one per drillable location | **our id**, outliving Novi stick ids, which don't carry across vintages. Steven's `box_econ` keys on it (7d). Geometry + plain and geography GiST indexes. |
| `box.location_source` | location × Novi vintage | the quarterly crosswalk: which `(report_version, stick_id)` the location was. Method `seed` / `overlap` (share stored) / `new`. One location per stick per vintage. |
| `box.forecast_run` | one per production run | spec `box_v2_wf` (the only value allowed), code + boxfit SHAs, deal-intake config, Novi vintage, data-through. **D62 haircut** table (oil and gas required), **D63 F(k)** (published, not applied), **D59/D69 disclosure** (hindcast bias by horizon + radius-class ranges, both required). `volumes_basis = uptime_free` and `horizon_months = 600` are fixed by CHECK. One record run. |
| `box.pud_forecast` | run × location, the **whole D67 universe** | coverage class + reasons: inside_extent, recon status, D64 spacing + source, search mode, radius, D69 radius class, n analogs, flags, and the D65 pad workup ref. |
| `box.pud_forecast_stream` | run × covered location × stream (oil, gas) | analog P50 params per 1,000 ft (D57), lateral multiplier (D50 Cui under 7,500 ft), haircut, raw and haircut EUR, EUR/kft, cum-12/24. |
| `box.pud_forecast_month` | run × location × stream × month 1–600 | derived monthly volumes: exact per-month integrals (D39), uptime-free (D63), haircut applied. |
| `box.location_analog` | run × covered location × analog well | the named analogs (D54 provenance): rank, distance, lateral, first production, transfer flag. |

**Guards that are part of the DDL** (not left to the writer):
- Stream, month and analog rows can only exist for **covered** locations. Enforced by a foreign key on
  `(run_id, location_id, coverage)` with a `coverage = 'covered'` check on each child table.
- A covered row must be fully described: inside the extent, with an extent id, at least 3 analogs, a search
  mode, radius and radius class, planned spacing plus its source, and a completed lateral.
- Not-covered rows carry no search. The one exception is `not_covered_no_analogs`, which may record how far
  it looked.
- The radius class must agree with the radius (5-mi ring ⇔ radius ≤ 5).
- `eur = eur_raw × eur_haircut`.
- No water stream (the frozen spec forecasts oil and gas only).
- Months stop at 600.

**D66:** the four step-4/5 tables get a one-time `SUPERSEDED (D54/D57/D66 …)` prefix on their table
comment. The prefix is applied idempotently and never stacks.

**Blast radius of the apply:** new tables in schema `box` only, plus comment text on four box tables.
- No matview, no CASCADE, no curated object, nothing in the nightly.
- No app reads `box.*` yet, so nothing goes dark.
- It runs in seconds; no off-hours window needed.

## 2. Universe and the gate-7 identity target (live, read-only, 2026Q3 vintage)

D67 universe = Novi `category = 'PUD'` (no RES) × reconciled status ∈ {remaining_pud, conflict,
not-yet-reconciled}, on every `box.bench_scope` bench. "Inside" = ≥ 50 % of the stick length inside the
record extent, the same rule step 3 used. There are currently **no** not-yet-reconciled PUDs.

| bench pool | formation | universe | inside record extent | v1 coverage |
|---|---|---|---|---|
| WCA | WCA_1 | 1,837 | **975** | covered if inside, else outside_extent |
| WCA | WCA_2 | 1,588 | **959** | covered if inside, else outside_extent |
| WCA | WCXY | 3,408 | 3,211 | not_covered_wcxy (D61) |
| BS2_S | BS2_S | 15,122 | 7,478 | not_covered_unvalidated (D60) |
| WDFD (Delaware) | WDFD | 7,050 | — | not_covered_emerging |
| BRNT (Midland) | BRNT | 4,157 | — | not_covered_emerging |
| MISS / MRMC / WDFD (Midland) | — | 0 | — | — |
| **total** | | **33,162** | | |

**Gate-7 identity:** covered = **1,934** (975 + 959), identical to step 3's in-extent count. Every one of the
33,162 rows gets a class. Precedence when several reasons apply: emerging → wcxy → unvalidated →
outside_extent → no_analogs → covered. `inside_extent` is stored separately, so the geography fact survives
whatever the class says.

## 3. Validation (throwaway `postgis/postgis:16-3.4`, Supabase layout)

- **Container setup:** PostGIS in schema `extensions`, plus `analyst_ro`, `anon` and `authenticated` roles.
  sql/54 + 56, 57 and 58 applied through their own apply scripts first, all green.
- **`apply_box_pud_forecast`: 57/57 checks, applied twice** (idempotent; the D66 prefix stays single).
  - Validation (40): every table, PK and named index exists; analyst_ro reads all seven; no Data-API usage on
    box; the ETL never names box. An **EXPLAIN assertion** shows a geography `ST_DWithin` on `box.location`
    using `box_location_geog_gix`.
  - Rolled-back smoke (17): a covered and a WCXY row insert. Each of these is refused:
    - a covered row with a NULL analog count (the NULL trap I caught in my own first draft of the CHECK)
    - a covered row with 2 analogs
    - a covered row outside the extent
    - a WCXY row with a search
    - a radius class that disagrees with the radius
    - the same stick twice in a run
    - the same stick on two locations in a vintage
    - an overlap match with no share
    - a second record run
    - a run without a gas haircut
    - a stream or analog row for a not-covered location
    - a water stream
    - `eur ≠ eur_raw × haircut`
    - month 601

    Deleting a run cascades through all four child tables.
- `pytest -q tests/test_sql_unique_index.py`: green (no matview, so nothing to lint). ruff is clean on
  `apply_box_pud_forecast.py`. `gen_data_dictionary.py` carries 9 pre-existing ruff findings on lines this
  change doesn't touch; I left them.
- **Data dictionary:** it can only be regenerated after the live apply (the generator reads the live catalog).
  That's step 3 of the go-apply sequence below.

## 4. Asks for gate 7b

1. **Go-apply sql/60** (blast radius in §1).
   Sequence: `python -m scripts.apply_box_pud_forecast` on Supabase (expect 57/57) →
   `python -m scripts.gen_data_dictionary --html docs/data_dictionary.html` → commit the regenerated dictionary
   on this PR.
2. **Water.** The frozen spec (`box_v2_wf`) forecasts oil and gas; it never scored water, and the schema
   refuses a water stream. Blue Ox drops carry water.
   Recommendation: **no water in v1 BOX**, stated on the delivery. Anduin's deal TC and the seller VDR (PDP)
   remain the water sources. The alternative is deal-intake's water P50, unvalidated and flagged, which would
   need a schema change.
3. **Crosswalk rule** (exercised from the next Novi vintage; the first run seeds every location).
   Recommendation: carry a location forward when a new-vintage stick has the same basin + `formation_blueox`
   and co-extent overlap ≥ 50 % of the shorter stick (rule 9), matched 1:1, greedy by overlap. Otherwise it's a
   `new` location, and the old one stops at its `last_seen_vintage`. A Novi re-bench becomes a new location by
   design.
4. **`not_covered_no_analogs`.** D54 says an in-extent PUD is always forecast. The class exists so a selection
   that finds fewer than 3 analogs at the 20-mi cap is recorded instead of silently dropped. I expect 0 on WCA.
   Any such row would break the gate-7 identity and gets reported, not hidden.
   Recommendation: keep the class.
5. **Run retention.** Monthly volumes run about 2.3 M rows per run (1,934 × 2 streams × 600).
   Recommendation: keep every run (about 9 M rows a year at quarterly cadence); prune only on a later decision.
