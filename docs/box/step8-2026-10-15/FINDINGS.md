# BOX step 8a — erebor Highgrade: Novi | BOX toggle (gate 8 surface 1 of 3)

Built 2026-10-15. erebor branch `claude/box-step8-highgrade` (commits 907a745, ef11040). Read-only against the
warehouse (erebor's per-transaction `READ ONLY` hook); no DDL, nothing stored. Per §10 step 8 is one session per
surface: this is **erebor Highgrade**. erebor Accuracy and the anduin dossier / Blue Ox drop are not built here.

## 1. What exists

| Piece | Where |
|---|---|
| Forecast source `novi \| box` on `/api/highgrade/{facets,pads,gunbarrel}` | erebor `backend/app/api/highgrade.py` |
| `/api/box/meta` (record run, provenance, D59 bias + D62 haircut, D69 radius ranges, F(k) points, Steven's priced decks, vintage staleness) and `/api/box/pad` (per-pad workup) | erebor `backend/app/api/box.py` (new) |
| Panel toggle, BOX run note, BOX econ caveat, coverage table, grey not-covered pads, popup coverage rows, BOX workup tab in the pad window | erebor `frontend/src/panels/{HighgradePanel,HighgradeLegend,HighgradeGunbarrelModal,BoxWorkup}.tsx`, `MapView.tsx`, `store.ts` |
| 15 DB-free tests (never-zero rule, per-source metric validation, lateral-weighted per-ft, BOX bounds keep not-covered PUDs, coverage classes = sql/60 values + 3 derived, calendar actual cum, P10 = HIGH band) | erebor `backend/tests/test_highgrade_box.py` |

**How BOX reads.** Same screened Novi PUD population either way (the Novi tier / score / support / depth filters
still apply — they are attributes of the location). BOX numbers come from the record run (`box.forecast_run.is_record`,
today run 6) joined on `stick_id`. Every screened PUD gets one coverage class: the six `box.pud_forecast.coverage`
values, plus three derived for a PUD with no row — `bench_not_in_box` (bench in no `box.bench_scope` pool),
`realized` (only visible with "All Novi BASE_CASE"), `no_box_row` (on a BOX bench, drillable, but missing: expected 0;
non-zero = the Novi vintage moved under the run). Pad values aggregate **covered rows only**; not-covered PUDs are
counted per class and drawn grey, never zero (D2/D67). BOX range bounds (BOX oil EUR, BOX oil EUR / 1,000 ft) never
drop a not-covered PUD.

**Metrics.** Novi: unchanged + new oil / gas EUR per 1,000 ft. BOX: oil / gas EUR, oil / gas EUR per 1,000 ft
(pad = Σ EUR ÷ Σ lateral kft, so a one-well pad equals the stored `eur_per_kft`), Steven PV0–PV30 (from
`box_econ.box_pud_econ` for ONE named deck + assumption set; hidden while he has priced nothing), well count.

## 2. Verification (live warehouse, 2026-10-15, run 6)

Identity, Delaware, drillable inventory, no filters (TestClient against Supabase, then the running app):

| Class | Screen count | `box.pud_forecast` run 6 |
|---|---|---|
| covered | **1,907** | 1,907 |
| not_covered_no_analogs | 5 | 5 (Pad 548, D77) |
| not_covered_outside_extent | 1,483 | 1,483 |
| not_covered_wcxy | 3,385 | 3,385 |
| not_covered_unvalidated (BS2_S) | 15,051 | 15,051 |
| not_covered_emerging (WDFD) | 7,049 | 7,049 |
| bench_not_in_box | 88,693 | — |
| no_box_row | **0** | — |

Σ = 117,573 = every drillable Delaware PUD (116,860 on pads + 713 without a pad). Midland: 0 covered, 4,154 emerging
(BRNT), 56,674 bench_not_in_box — correct for v1. With "All Novi BASE_CASE": covered still 1,907, `realized` 3,040.
BOX mode answers in ~2.5 s vs ~2.3 s Novi.

BOX vs Novi on the 1,907 covered WCA PUDs (oil, raw 50-yr EUR; BOX = P50 analog × D62 haircut, uptime-free):
Σ 1,144.9 vs 1,143.1 MMbbl (1.002×); median EUR / 1,000 ft 66,570 vs 65,345 bbl; per-location BOX ÷ Novi
10th / 50th / 90th percentile 0.75 / 1.00 / 1.30. **In aggregate BOX ≈ Novi on WCA; the difference is in WHERE.**

Click-through in the running app (erebor :5180 / :8077 serving this branch): Highgrade → BOX → Apply → 319 covered
pads on the ramp + 4,007 grey (default screen); popup lists per-class counts; clicking Delaware Pad 595 opens the BOX
workup (run line, bias / haircut / F(k) table, D69 range, 52 PUDs with 5 covered, chart: forecast sits above the
analogs' calendar P50 by roughly F(k), 28 named analogs) and the Gunbarrel tab. Novi mode re-checked unchanged.
Spot check: 3.70/yr nominal, b 0.94 → 80 % 1-yr effective, as displayed.

Checks: erebor `pytest -q` 57 passed (DB-free); frontend `tsc -b --noEmit` clean (erebor has no eslint gate).

## 3. Conflicts with the plan text (flagged, not resolved)

1. **DECIDED 2026-10-15 (D91): accepted** — haircut + analog provenance replace "risk factor"; built as described. Original note: **Step 8 says "BOX EUR/ft, risk factor".** The risk-factor chain was retired by D54/D57 and D66 says apps never read
   `box.type_curve` / `risk_factor`. Built instead: the D57-era equivalents — haircut by horizon (D62), analog
   count + radius + strike/circle search, D69 range, bound flags. Needs your word that this replaces "risk factor".
2. **Step 8 says "Accuracy tab: BOX vs Novi hindcast from `box.hindcast_score`".** That table was never built
   (acceptance moved to D53 package scoring in `docs/box/acceptance`). The Accuracy surface needs a source decision
   before its session (stored cells? the prospective 2026 cohort? both?).
3. **Step 8 says "anduin dossier / Blue Ox drop: BOX regional curve overlay".** Regional curves are retired (D54/D66);
   the overlay would be the pad's BOX analog P50 curve. Same call needed before that session.
4. **"The three Novi caveats get BOX siblings."** Built: highgrade.py module header + the Highgrade panel note. The
   export module and Assumptions sheet carry no BOX numbers (the xlsx export is the Map-tab selection, untouched), so
   their siblings land when an export carries BOX — not in this surface.

## 4. Gate-8 asks (Highgrade surface)

1. **Click-through acceptance** of the toggle as built (§2).
2. **DECIDED 2026-10-15 (D90): option (b)**, built in erebor commit on the same branch — BOX mode screens all depletion tiers by default; default BOX screen now shows 1,896 covered (TVD-excess ≤ 200 ft drops 11). Original ask: **Default Depletion-tier screen vs BOX.** Highgrade defaults Novi Depletion Tier-4 OFF ("drained rock"). On BOX
   that removes **1,307 of the 1,907 covered PUDs (69 %)** — the default screen shows 596 (TVD-excess ≤ 200 ft removes
   only 11 more). The BOX workup already prices depletion through its analogs, so Novi's tier may be double-counting
   on BOX. Options: (a) keep the default in both modes (as built), (b) BOX mode defaults Tier-4 ON, (c) drop the tier
   default entirely. Recommendation: (b), stated in the panel.
3. Conflicts 1–3 above: confirm the substitutes before the Accuracy and anduin sessions.
4. erebor PR merge (link in the handoff); then the Status line marks surface 1 done.

Housekeeping noticed: the workspace CLAUDE.md says erebor has 28 tests; the suite has 57 (42 before this branch).
