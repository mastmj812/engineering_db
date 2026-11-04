# #eng-updates post (step 23d) — posted 2026-11-04

Drafted 2026-11-04 for Michael. **POSTED 2026-11-04** to #eng-updates on his go ("Post it") as a top-level post tagging Steven:
https://blue-ox-resources.slack.com/archives/C0C7RMAU3BJ/p1793822595781589 (ts 1793822595.781589). Text as below.

---

*BOX record update: new Delaware record + first Midland record, both live and UNPRICED. @Steven, please price runs 32 and 30.*

As of today (2026-11-04) the BOX records are:
• *Delaware: run 32*, replacing run 19
• *Midland: run 30*, the first Midland BOX record

We chose to put both live before you price them. Until you push econ for runs 32 / 30, erebor and `curated.box_scout_locations` show their forecasts with *blank econ*. That beats showing run 19's numbers against a different forecast. As soon as your rows land, they fill in on their own; nothing needs refreshing.

*What to price:* same contract as run 19.
• `box_econ.box_pud_econ`, keyed on run_id + location_id, with provenance + `downtime_basis`.
• Every forecast location (coverage `covered` / `covered_provisional`), on the same 16 decks (wti60/70/80/90 × hh1–4). The scout view and erebor default to wti70_hh3.

| | Delaware run 32 | Midland run 30 |
|---|---|---|
| forecast locations | 48,148 (22,871 validated / 25,277 provisional) | 28,801 (14,786 validated / 14,015 provisional) |
| oil, MMbbl | 25,421.0 | 11,078.0 |
| gas, Bcf | 149,764.5 | 46,382.3 |
| water, MMbbl | 126,826.9 | 54,013.2 |

Volumes are the raw 50-yr technical EUR, no economic limit. For comparison, run 19 was 42,970 locations / 22,623.3 MMbbl oil.

*What changed vs run 19 (Delaware):*
• RES sticks are now in scope alongside PUD (D117).
• The oil proximity factor is the new continuous distance model (D150) instead of the old class table.
  - It runs 0.43–1.05, so *oil factors can now be above 1*: a stick with no nearby depleted parent gets the fitted level, 1.046.
  - 29,447 Delaware locations sit above 1. If your loader assumed `prox_factor ≤ 1`, that assumption no longer holds.
• Reconciliation-conflict sticks are not drillable (D145): 1,567 not covered.
• Sticks drilled since the last run are out.
• Gas and water ride the same fits as before; no factor applies to them.

*Midland run 30:*
• Nine benches. WCA_1 / LSSH / WCD are validated; WCB_1 / WCB_2 / JM / MS / DEAN / WCC are provisional, so keep the two tiers apart in any totals.
• The WCA_1 oil haircut applies (D102).
• The same D150 factor: 0.50 to the 1.067 level, with 13,228 locations above 1.
• One WCD stick (1545426) has no water analog within 20 mi, so it ships no forecast and is classed not covered.

*Heads-up on run 19:* its econ rows (687,520, 16 decks) stay for about a day in case we need to revert, then get pruned with the run. Nothing you need to do.

Questions here in thread. Forecasts stay technical; econ stays yours and display-only.
