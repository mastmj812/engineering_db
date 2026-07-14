# Deal dossier — {deal_name}

## Run snapshot (gate 0)

| Field | Value |
|---|---|
| run_id | {deal_name}-{run_date} |
| config_version | {config_version} |
| Production vintage (nightly loads) | {etl_log run_finished_at} |
| Novi Intelligence vintage | {report_name} |
| erebor_locations as-of | {report_name / refresh date} |
| wellspacing_vintage | {wells_enriched.wellspacing_vintage — as-of-first-production, Novi-confirmed 2026-07-14} |
| Units | {n} — {names} |
| Allowed benches (Land terms, resolved) | {bench codes} — **reviewer confirm** |

## Unit map(s)

{map: deal polygon vs Novi DSU pad, Novi sticks colored by in/out, generated
narvi sticks if any, qualifying PDP offsets by bench}

## Gate results

| Gate | Signal (computed) | Recommendation (rule) | Status | Decision |
|---|---|---|---|---|
| 1 Ingest | {CRS / geometry / attrs} | — | pass/fail | |
| 2 Location source | IoU {x.xx}; outside-endpoint frac {x.xx} | novi / narvi / gray-band | pass/escalate | approve / override |
| 3 Bench inclusion | per-bench pdp_count_3mi min/med/max | include/exclude per bench | pass/escalate | |
| 4 Forecast source | inflation_ratio median {x.xx} (band {lo–hi}); dispersion max/min {x.xx} | novi-ok / anduin-required / optional-anduin | pass/escalate | |
| 5 Well selection | {n} wells after filters+spacing; edge signal dist_nearest {ft}, ring decay {x.xx} | radius / concentric-extend / strike-biased | pass/**reviewer-confirm** | |
| 6 QC | {n flagged}/{n wells} | review flagged only | pass/escalate | |

## Bench matrix (unit x bench)

| Unit | Bench | Locations (src) | pdp_count_3mi (med) | inflation_ratio (med) | Dispersion | Forecast source | TC wells | Edge | Status |
|---|---|---|---|---|---|---|---|---|---|

## Per-bench forecast comparison — ALL THREE STREAMS

(inflation_ratio is oil-only; gas/water shown so the blind spot stays visible.
Di reported nominal /yr AND 1-yr effective %. SPE orientation: P10 = HIGH.
EUR = raw 50-yr integral, no economic limit.)

### {bench}

| Stream | Source | qi (cal-day) | Di nom /yr | Di eff yr-1 % | b | Peak mo | EUR | EUR/1,000 ft |
|---|---|---|---|---|---|---|---|---|
| Oil | Novi (erebor) | | | | | | | |
| Oil | Anduin TC {tc_id} | | | | | | | |
| Gas | Novi | | | | | | | |
| Gas | Anduin | | | | | | | |
| Water | Novi | | | | | | | |
| Water | Anduin | | | | | | | |

{rate/cum overlay chart, peak-aligned}

## QC flags (gate 6 — flagged wells only)

| api10 | Stream | Flag | Value | Bound/threshold | Reviewer action |
|---|---|---|---|---|---|

## Decision log

| # | Gate | Signal | Rule said | Decision | By | Why |
|---|---|---|---|---|---|---|

## Handoff

- Anduin TC ids: {ids}; CSV exports: {paths}
- narvi scenario: {deal_id}/{scenario_id} (if generated)
- Forecast going to finance (Michael's call): {novi | anduin per bench}
