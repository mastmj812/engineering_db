# Engineering Curve-Drop Contract — v1 (2026-07-20)

> **Checked-in reference copy.** Received from Blue Ox (S. Murray) 2026-07-20. The text below
> the amendment block is the contract verbatim; Blue Ox's repo-side source of truth is their
> `src/inputs_loader.py` / `src/well_inventory.py`.
>
> **Agreed amendment (2026-07-20, M. Mast / S. Murray) — NGL responsibility:**
> Blue Ox provides the NGL yield and derives NGL volumes on their side. The engineering drop
> delivers **oil, gas, and water only**. In terms of the contract text below:
> - `ngl_bbl` on zone sheets is delivered **all-zero** (column present per spec), at every
>   delivered percentile level, so triplets stay complete.
> - `manifest` `ngl_basis` reads `derived_by_blue_ox_via_yield` — the yield value itself is
>   Blue Ox's input, not part of the drop.
> - No NGL rows in `curve_params`; no `ngl_bbl` in `analog_production`.
> - `eur_ngl_bbl` in `manifest` Block B is 0 (sum of the delivered all-zero column, per the
>   compute-from-final-sheets rule).
> This supersedes §1.1's "all-zero only if the deal genuinely has no NGL" and the `ngl_basis`
> value list in §1.7 for our drops until Blue Ox issues a revised contract.

Instructions for the engineering deliverable that feeds a Blue Ox deal underwrite and
reproduces the engineering exhibit deck (type-curve and historical-production slides). This is
written to be handed to the engineer (and to the Claude session in his own project) verbatim.
Repo-side source of truth for every token below: `src/inputs_loader.py` and
`src/well_inventory.py` — if the loader changes, this document changes in the same commit.

---

## 0. Principles

1. **One file governs.** Exactly one curve workbook per deal per drop. Never send two exports
   covering the same zones — competing exports have historically disagreed by up to 4x on gas
   and are the single largest source of silent valuation error. If a re-export is needed, it
   is a NEW dated file that replaces the old one entirely, and the covering email/message says
   "supersedes <prior filename>".
2. **The engineer's nomenclature is canonical.** Zone names, landing-zone assignments, type
   curves, and inventory originate with the engineer — Blue Ox adopts the drop's zone-name
   strings verbatim as the model's area identifiers and never renames them. The only
   constraints are mechanical:
   - Valid Excel sheet names, **26 characters or fewer** (so the companion `<Zone> meta`
     sheet fits Excel's 31-character limit); none of `: \ / ? * [ ]`; no leading/trailing
     spaces or apostrophes.
   - `meta`, `inventory`, `manifest`, `analog_production`, and `curve_params` are reserved
     sheet names (case-insensitive) — a zone cannot use them.
   - PDP group names must differ from every zone name.
   - Names are **stable across re-drops**. Renaming a zone is a declared supersede event
     (say so in the covering message and in `manifest`), never a silent change.
3. **Curves are raw physics, nothing else.** Gross wellhead volumes for one well. No working
   interest, no royalty, no shrink, no risking, no economics baked in. All commercial terms
   enter on our side.
4. **Everything declared, nothing implied.** Basis, orientation, and reconciliation targets
   travel inside the workbook (the `manifest` sheet) — not in an email.
5. **Never overwrite a prior drop in place.** New drop = new filename with a new date. Prior
   drops stand as the audit record.

## What Blue Ox sends the engineer at kickoff (per deal)

The workbook cannot be built without these — ask if any is missing:

- Deal **codename**
- Required **curve length in months** (all zones the same length; historical norm 360)
- Which **percentile levels** are wanted beyond P50 (from: P10, P25, P75, P90), if any —
  request the full set whenever the exhibit deck needs P10–P90 bands
- Deal **effective date** (needed only if a PDP workbook is requested)
- Whether **producing wells convey** (a PDP workbook is needed) and the intended grouping

The zone list travels the other way: the engineer's drop defines the zones, and his names are
adopted verbatim (Principle 2). Blue Ox never supplies zone nomenclature.

---

## 1. Deliverable A — the curve workbook (always)

**Filename:** `<codename>_curves_<YYYY-MM-DD>.xlsx` (date = the export/as-of date).
Do not use the words `type_curves`, `areas`, `pdp`, or `pinned` in the filename — those
stems are reserved on our side.

**Workbook-wide formatting rules (apply to every sheet except the analog sheets in §1.4):**
- Row 1 is the header row. No title rows, no merged cells, no frozen decoration above headers.
- Values only — no formulas, no external links.
- Numbers stored as numbers, not text. No blank cells mid-column; a zero is a real zero.
- No columns beyond the ones specified. Column headers exactly as written (they are
  case-sensitive lowercase on the zone sheets).

### 1.1 Zone sheets — one per zone

- **Sheet name = the zone name, chosen by the engineer** (Principle 2 naming rules). These
  strings become the canonical zone identifiers across every Blue Ox output for the deal, and
  every other sheet in the drop refers to zones by exactly these strings.
- **No month column.** Row order IS the month: the first data row is production month 1.
  Every zone sheet has exactly the agreed number of rows (zero-fill the tail after economic
  depletion so all zones share one length).
- Values are **monthly volumes** (not daily rates, not cumulative), **gross wellhead, one
  well, unrisked**, at the normalization basis declared in `meta` (§1.2).

Columns, in this order:

| Column header (exact) | Required | Units | Notes |
|---|---|---|---|
| `oil_bbl` | yes | bbl/month | P50. Never emit an `oil_bbl_p50` column. |
| `gas_mcf` | yes | Mcf/month | P50. **Wellhead, unshrunk** gas. Mcf, not MMcf. |
| `ngl_bbl` | yes | bbl/month | P50. If the shop derives NGL by yield, compute it into this column and state the yield in `manifest`. All-zero only if the deal genuinely has no NGL (declare in `manifest`). |
| `water_bbl` | optional | bbl/month | Include if forecast — it improves our water-cost modeling. Must match the other columns' row count. |
| `oil_bbl_p10`, `gas_mcf_p10`, `ngl_bbl_p10` | per kickoff | as above | Percentile levels come as a **complete triplet or not at all** — a partial triplet is a hard failure. Same rule for `_p25`, `_p75`, `_p90`. No other levels exist. No percentile water columns. |

**Percentile orientation — critical.** Blue Ox curve files are **ascending**: P10 is the
conservative low case, P90 the optimistic high case. This is the opposite of SPE/exceedance
convention used in most engineering databases. If the source system stores exceedance
percentiles, **flip them at export** and set `percentile_orientation = ascending` in
`manifest`. Self-check: for every zone and stream, column sums must be monotonic —
sum(p10) < sum(P50 base) < sum(p90).

### 1.2 `meta` sheet

Sheet named `meta`. One row per zone. Headers (case/space-insensitive):

| Column | Required | Accepted values |
|---|---|---|
| `area` | yes | The exact zone name (must match a zone sheet) |
| `normalization_basis` | yes | `per_1000_lateral_ft` (curve is normalized per 1,000 ft of lateral — we scale by actual lateral) or `per_well` (curve is absolute for one well) |
| `reserve_category` | yes | `PUD` (proven undeveloped — will be scheduled and valued) or `RES` (non-proven — carried as unscheduled upside). Nothing else. |

If curves are per-1,000-ft normalized, **do not bake the lateral multiplier into the
volumes** — deliver the normalized curve and let the `inventory` laterals do the scaling.

### 1.3 `inventory` sheet

Sheet named `inventory`. **One row per planned undeveloped well** — the row count per zone IS
the gross location count we value. Headers (case/space-insensitive):

| Column | Required | Units | Meaning |
|---|---|---|---|
| `area` | yes | — | Exact zone name |
| `producing_lateral_ft` | yes | ft | Lateral basis of the analog set behind the curve (drives volume scaling) |
| `drilled_lateral_ft` | yes | ft | Design/drilled lateral for the planned well (drives per-ft capex) |
| `well_name` | optional | — | Label only, ignored by the loader |

Laterals must be within 3,000–25,000 ft (hard bounds on our side).

### 1.4 Analog well sheets — one per zone (feeds the well-location map and keys the production history)

For each zone, a sheet named **`<Zone name> meta`** (the sheet name must start with the
exact zone name and contain the word `meta`), structured as:

- Any cell in **column A** containing exactly the text `per_well_summary`
- The **next row** = column headers
- Then one row per analog well, ending at the first fully blank row

Headers are matched loosely by substring. Include:

| Column | Required | Notes |
|---|---|---|
| `api10` | yes | 10-digit API. **Include only ONE column containing "api"** in the header — a second one (e.g. api14) can be picked up instead. |
| `well_name` | optional | |
| `operator` | optional | |
| `formation` | optional | |
| `lateral` | optional | ft |

Additional per-well stat columns the engineer's own exhibits quote (e.g. `first_prod`,
fitted `eur_oil_mbbl`, `eur_gas_mmcf`) are welcome and ride through to the deck untouched.
Anything derivable from `analog_production` (cums to date, months on, IP30/IP90) need not
be repeated here — Blue Ox derives those from the history so the two can never disagree.

No latitude/longitude — well locations are joined spatially on our side from the API-10.

### 1.5 `analog_production` sheet — monthly history for every analog well

Sheet named `analog_production`. Long format: **one row per well per production month**,
covering every well listed in the §1.4 analog sheets, from first production through the
`production_history_through` month declared in `manifest`. This is the sheet that makes the
engineering exhibit deck (type-curve vs. actual-production overlays, per-well history
spaghetti plots) reproducible from the drop alone.

| Column | Required | Units | Notes |
|---|---|---|---|
| `api10` | yes | — | Must appear in a §1.4 analog sheet |
| `date` | yes | YYYY-MM | Calendar production month (first-of-month dates also fine) |
| `oil_bbl` | yes | bbl/month | Gross wellhead |
| `gas_mcf` | yes | Mcf/month | Gross wellhead, unshrunk |
| `water_bbl` | optional | bbl/month | Include if available |
| `ngl_bbl` | optional | bbl/month | Only if well-level NGL is genuinely measured/allocated — state the basis in `manifest` |
| `days_on` | optional | days | Producing days in the month — enables producing-day rate plots (without it, rate charts fall back to calendar-day rates) |

Sort by `api10`, then `date`. A listed analog with no available history is either removed
from the analog sheets or declared as an exception in `manifest` — never silently absent.

### 1.6 `curve_params` sheet — decline parameters and headline curve stats (exhibit data)

Sheet named `curve_params`. One row per zone × stream × level. These are **display values
quoted verbatim from the engineer's decline model** — they label the exhibits (type-curve
detail tables, chart annotations). The volume vectors in the zone sheets remain the sole
economic input; **Blue Ox never re-fits decline parameters**, so anything the deck quotes
must be declared here.

| Column | Required | Notes |
|---|---|---|
| `area` | yes | Exact zone name |
| `stream` | yes | `oil` or `gas` (NGL only if a real fit exists) |
| `level` | yes | `P50`, `P10`, `P25`, `P75`, `P90` — oil and gas `P50` rows required per zone; other levels as delivered |
| `qi` | yes | Initial rate from the fit |
| `qi_units` | yes | e.g. `bbl/d`, `Mcf/d` |
| `qi_basis` | yes | What qi means: `fitted_qi`, `ip30`, `peak_month_avg`, ... |
| `b_factor` | yes | Arps b |
| `di` | yes | Initial decline |
| `di_convention` | yes | **Mandatory** — e.g. `nominal_annual`, `secant_effective_annual`, `tangent_effective_annual`. Decline-convention ambiguity is a classic silent error. |
| `dmin` | optional | Terminal decline, same convention |
| `ip30`, `ip90`, `ip180` | optional | In `qi_units` |
| `notes` | optional | |

Parameters must come from the **same run/vintage as the volume vectors** (declare it in
`manifest`); headline qi/IP values should be consistent with the delivered vectors' early
months.

### 1.7 `manifest` sheet — provenance + reconciliation targets

Sheet named `manifest` (do not name it anything containing "meta"). Two blocks:

**Block A — key/value rows (column A = key, column B = value):**

| Key | Value |
|---|---|
| `deal_codename` | as given at kickoff |
| `export_date` | YYYY-MM-DD |
| `source_system` | e.g. the warehouse/vintage the curves came from |
| `governing_export` | identity of the single governing export/query per zone set |
| `percentile_orientation` | must read `ascending` |
| `gas_basis` | must read `wellhead_unshrunk` |
| `ngl_basis` | how NGL was derived (explicit forecast / yield of X bbl/MMcf / none) |
| `risking` | must read `unrisked` |
| `curve_months` | the row count of every zone sheet |
| `production_history_through` | YYYY-MM — the last month of history included in `analog_production` |
| `curve_params_source` | run id/date of the decline fits — must be the same vintage as the volume vectors |
| `prepared_by` | name |

**Block B — one row per zone (starting a few rows below Block A, with its own header row):**

| Column | Meaning |
|---|---|
| `area` | exact zone name |
| `eur_oil_bbl` | the arithmetic sum of that zone sheet's `oil_bbl` column, as delivered |
| `eur_gas_mcf` | sum of `gas_mcf`, as delivered |
| `eur_ngl_bbl` | sum of `ngl_bbl`, as delivered |
| `gross_locations` | must equal that zone's row count in `inventory` |
| `avg_producing_lateral_ft` | must equal the mean of that zone's `producing_lateral_ft` rows |
| `avg_drilled_lateral_ft` | must equal the mean of that zone's `drilled_lateral_ft` rows |

These are the reconciliation targets: on receipt, Blue Ox ties loaded EUR per zone per
stream to Block B within **±0.1%**, and location counts and laterals **exactly**. A miss
blocks the deal until resolved, so compute Block B from the final sheets, not from the
source system.

---

## 2. Deliverable B — PDP workbook (only when producing wells convey)

**Filename:** `<codename>_pdp_<YYYY-MM-DD>.xlsx`. One sheet per PDP group, sheet name = the
group name agreed at kickoff. **Group names must not equal any zone name.**

- **No date/month column** — rows are consecutive months starting at the first month after
  the deal effective date. A date column, if present, is ignored (so leave it out).
- Volumes are the **group aggregate** (all wells in the group summed), gross, monthly.
  Gas in **Mcf, not MMcf**; oil/NGL/water in bbl.
- Header matching is lenient, but use the canonical headers:

| Column | curves mode | cashflow mode | Notes |
|---|---|---|---|
| `gross_oil_bbl` | required | required | |
| `gross_gas_mcf` | required | required | wellhead |
| `gross_ngl_bbl` | optional | optional | |
| `gross_water_bbl` | optional | optional | |
| `revenue_oil` | — | required | $ |
| `revenue_gas` | — | required | $ |
| `revenue_ngl` | — | optional | $ |
| `opex_total` | — | required | $ |
| `sev_tax`, `ad_valorem`, `net_oil_bbl`, `net_gas_mcf`, `net_ngl_bbl`, `net_cf` | — | optional | |

**Dollar basis must be declared** (in a `manifest` sheet mirroring §1.7 Block A, plus per
group: `mode` intended (`curves` or `cashflow`), `well_count`, `dollar_basis`):
revenue/opex lines are either **net-to-seller** or **gross 8/8ths** — say which. An
undeclared basis is the most common PDP error (gross opex read as net inflates LOE by 1/WI).
Well count, ownership, and LOE parameters are configured on our side; the workbook carries
only the streams above.

---

## 3. What Blue Ox verifies on receipt (the acceptance gate)

1. The workbook loads with zero parse errors (sheet names, required columns, triplets,
   uniform lengths).
2. Per zone, per stream: loaded EUR == `manifest` Block B within ±0.1%.
3. Per zone: `inventory` row count == `gross_locations`; lateral means tie exactly.
4. Percentile monotonicity (ascending) per zone per stream.
5. `analog_production` ties to the analog sheets: every `api10` in one appears in the other
   (exceptions declared in `manifest`).
6. `curve_params` covers every zone (oil and gas at P50 minimum) with `di_convention`
   stated.
7. Exactly one governing curve workbook exists for the deal. If a second export covering the
   same zones is ever received, everything stops until the engineer rules which governs.

## 4. Self-check checklist (run before sending)

- [ ] Filename `<codename>_curves_<YYYY-MM-DD>.xlsx`; no reserved words in the name
- [ ] One sheet per zone; zone names are the engineer's own, within the Principle 2 naming
      rules, and unchanged from the prior governing drop (or the rename is declared)
- [ ] `oil_bbl`, `gas_mcf`, `ngl_bbl` present, lowercase, monthly volumes, no month column
- [ ] All zone sheets have identical row counts == `curve_months`
- [ ] No `_p50` columns; every percentile level a complete oil/gas/NGL triplet
- [ ] Percentile sums monotonic ascending (p10 < base < p90) for every zone and stream
- [ ] `meta` has every zone with a valid `normalization_basis` and `reserve_category`
- [ ] Per-1,000-ft curves NOT pre-multiplied by lateral
- [ ] `inventory` has one row per planned well, laterals in 3,000–25,000 ft
- [ ] One `<Zone> meta` analog sheet per zone with the `per_well_summary` marker and a
      single api column
- [ ] `analog_production` present: long format, every analog api10 tied both ways, history
      complete through `production_history_through`
- [ ] `curve_params` present: oil + gas P50 row per zone, `di_convention` and `qi_basis`
      filled, same vintage as the curves
- [ ] `manifest` Block A complete; Block B computed from the final sheets themselves
- [ ] Values only, no formulas, no merged cells, numbers as numbers
- [ ] Gross, wellhead, unshrunk, unrisked, one well, no WI/NRI applied
- [ ] PDP (if any): group sheets aggregate-gross monthly, no date column, dollar basis and
      mode declared per group

Questions on any item go to S. Murray before building around an assumption.
