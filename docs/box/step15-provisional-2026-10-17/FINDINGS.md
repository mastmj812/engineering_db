# BOX provisional tier (D105) — AVA_0 / AVA_1 / AVA_2 + BS2_C — AT GATE (go-apply sql/63)

2026-10-17. Michael: "I'd rather have a less robust forecast for AVA and BS2_C than simply null … a representative PDP analog
informed forecast (~2016 and later first prod date simply to control for completion size) to tie to the locations."

**State:** nothing stored. sql/63 is authored and validated in a container only; the live apply needs "go apply". Review surface:
`index.html` (disclosure tables). Builders:
- `python -m scripts.box_provisional_disclosure` (`box/provisional.py`, 3 DB-free tests; reads the tuning runs in `runs/box15t/`);
- `python -m scripts.apply_box_provisional` (sql/63; 21 checks incl. a rolled-back smoke).

## 1. Decision recorded (D105, proposed text for plan §2)

**Provisional coverage tier.** A bench whose development history cannot support the D53 / D99 out-of-time test (step 14 / the
step-15 tuning gate) is still forecast.
- **Workup:** the same analog workup as every other bench (`box_v2`: deal-intake config v10 selection — same bench, first
  production ≥ 2016, ≥ 6 months produced, lateral band, nearest-first to 10 analogs, D55 strike past 5 mi, D50 / D56 lateral
  handling). No haircut, no holdout.
- **Storage:** coverage = `covered_provisional` (sql/63), so `covered` keeps meaning VALIDATED in every app, Steven's queries
  and the gate identities. `box.bench_scope.validation = 'provisional'` marks the bench.
- **Disclosure** (per workup): the bias measured on the bench's tuning packages, pooled across cutoffs, with a 95 %
  cluster-bootstrap range over 3-mi blocks, plus the bias by vintage. Labelled "measured in-sample, never out-of-time
  validated". The pooled number is primary for AVA because a single AVA bench holds 36–69 packages.
- **Benches:** AVA_0, AVA_1, AVA_2 (each its own analog pool and extent; disclosure pooled AVA 0 + 1 + 2), BS2_C (own pool,
  extent 20).
- **Not changed:** WCD and WDFD stay emerging. They have no extent, and WCD's median 10th-analog distance is 14 mi.

The "≥ 2016 first production" control is already the analog engine's rule (config v10), so no new filter was needed.

## 2. What the disclosure says (raw `box_v2`, tuning packages, all cutoffs 2019–2024)

**Sign convention:** bias = Σ actual / Σ forecast − 1 per package, so **+ = forecast LOW**.

| group | stream | cum-12 bias [95 % range] (pkgs) | cum-24 | cum-36 |
|---|---|---|---|---|
| **AVA pooled** | oil | **−7.1 %** [−15.9, +2.1] (163) | −3.6 % [−11.8, +6.2] (122) | +4.1 % [−5.9, +15.3] (83) |
| AVA pooled | gas | −10.0 % [−21.3, +0.9] | −16.1 % [−26.2, −6.6] | −8.7 % [−23.4, +8.2] |
| AVA_0 | oil | −18.4 % [−29.7, −7.5] (36) | −14.1 % (28) | −4.9 % (16) |
| AVA_1 | oil | −5.1 % (58) | +1.0 % (42) | +4.8 % (35) |
| AVA_2 | oil | −3.0 % (69) | −1.6 % (52) | +7.8 % (32) |
| **BS2_C** | oil | **−7.5 %** [−15.9, +1.3] (151) | **−22.5 %** [−28.9, −16.7] (90) | **−32.5 %** [−39.2, −25.7] (55) |
| BS2_C | gas | +5.7 % [−9.8, +21.0] | −16.5 % [−30.3, −0.8] | −28.0 % [−40.4, −12.8] |

**By vintage: the pooled number hides a trend on both groups** (oil cum-12 bias of the cohort first producing in the 12 months
after each cutoff):

| | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|
| AVA pooled (pkgs 19–37) | +23 % | +8 % | −7 % | −14 % | −16 % | −18 % |
| AVA pooled, cum-24 | +16 % | +16 % | +1 % | −14 % | −26 % | — |
| BS2_C (pkgs 10–35) | −30 % | −16 % | −19 % | −21 % | +13 % | +12 % |

- **AVA:** recent wells come in BELOW the analog forecast, −14…−18 % at cum-12 and −14…−26 % at cum-24 for the 2022–24
  cohorts. Early wells came in above it. The pooled −7 / −4 % averages the two, and a new AVA PUD is a recent-vintage well.
- **BS2_C:** the opposite. Early cohorts were over-forecast 16–30 %; the 2023–24 cohorts were under-forecast ~12 % (gas
  +43…+45 %). The compounding −23 / −33 % at cum-24 / 36 comes from the 2020–22 cohorts.

## 3. Asks for this gate (Michael)

1. **Go-apply sql/63** on Supabase (`python -m scripts.apply_box_provisional`). It adds the `covered_provisional` value, widens the
   four tables' coverage checks and Steven's `box_pud_econ` to admit it, and adds `bench_scope.validation`. Then: data
   dictionary regen and a sql/31 note.
   - Container (postgis 16-3.4, Supabase layout, sql/52–61 chain): 21 / 21 checks, applied four times (idempotent). The sql/60
     and sql/61 apply scripts still pass after it. Live coverage counts are asserted unchanged by identity.
2. **Which number the workup leads with.** Recommendation: the pooled bias + range, AND the latest-vintage line, both stated:
   - AVA: "recent cohorts (2022–24) produced 14–18 % below forecast at 12 months";
   - BS2_C: "the miss changed sign; the 2023–24 cohorts came in ~12 % above forecast".

   Both are in-sample measurements; neither is validated.
3. **No haircut**, as you said. Note that the recent-vintage AVA reading (−14…−18 %) is a larger miss than BS1_S's accepted
   −10 %. A future haircut would be a separate decision with its own evidence.
4. **bench_scope rows:** AVA_0 / AVA_1 / AVA_2 / BS2_C stay `in_scope = true` with `validation = 'provisional'` and a D105 reason.
   This replaces the earlier "emerging" write, which never happened. It is a live write, done with the sql/63 apply on your go.

## 4. What follows (not built here)

- **Run 9 code** (the 9c pattern): `box_pud_run` rows provisional benches as `covered_provisional`, writes their stream / analog
  rows with the tier, puts the disclosure under `disclosure.by_bench`, and applies the 9c haircut guard to `box_v2_wf` benches.
- **erebor** (after the live apply; warehouse first):
  - Highgrade / pad workup show a "provisional" badge and the D105 disclosure;
  - the screen counts keep validated and provisional apart;
  - `coverage != 'covered'` checks in `app/api/box.py` become tier-aware.
- **Steven:** a note that provisional rows can appear in `box_pud_econ` (contract amendment).
- **The holdouts for the validated step-15 benches** (BS3_S, BS3_C, WCB_1, WCB_2, BS1_S, WCC) are still the next gate in that
  chain.
