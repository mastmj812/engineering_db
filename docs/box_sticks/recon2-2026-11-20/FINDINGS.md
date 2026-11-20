# BOX sticks nightly reconciliation, rule `box_recon_2`: authored and scored

2026-11-20. **Nothing applied on live and nothing on the nightly path: this branch must not merge before the shadow week
closes (nightly of 2026-11-26).** Live was only read. Bars: `BARS.md`, committed (`2075cc8`) before the rule was authored.
Branch `claude/box-sticks-recon2`, cut from main at `d36ff24`.

**Two of the eight bars fail as written: R4 and R5.** R5 was the bar named beforehand as the one that decides. Stated
plainly below; nothing was tuned.

## What was authored

| File | Change |
|---|---|
| `etl/box_recon.py` | `VERSION = "box_recon_2"`. Same landing = well depth within the record set's own `same_dv_ft` (150 ft today, read from `box.location_set.cfg`), whatever the tag. `RULE1_JUDGE_SQL` keeps the old guard for comparison only; the nightly never runs it. The two SQL texts differ in that one expression (a test pins it) |
| `sql/74_box_recon.sql` | The comment on `curated.box_location_status.status` names the new window. Comment text only; re-applying it on live is a DDL statement and needs its own go |
| `scripts/box_sticks_phase5a.py`, `box_sticks_phase5b.py` | The Python reference takes `rule` (1 or 2) |
| `scripts/box_recon2_measure.py`, `box_recon2_rehearsal.py` | The measurements below; read-only on live, writes only in the container |
| `tests/test_box_recon.py` | 13 tests, updated for the rule |

## The bars

Sets 16 and 17, wells read 2026-11-20. dz = well depth - stick target TVD.

| Bar | Result | Verdict |
|---|---|---|
| R1 SQL against the Python reference, stick by stick | same status 99.993 % Delaware (3 sticks differ), 100.000 % Midland; same crowded flag 99.967 % (15) and 99.943 % (19) | passes |
| R2 read-only pass on live | 143.2 s; `box_location_stick_geog_gix` in the plan | passes |
| R3 day 0, rule 2 | producing or conflict: Delaware 7 sticks (0.015 %), Midland 3 (0.009 %); crowded 69 (0.150 %) and 48 (0.145 %) | passes |
| R4 every stick that differs between the rules (157 sticks) | 101 were producing or conflict under rule 1, all with the well at 150 < abs(dz) <= 500 ft; none goes the other way; 101 sticks back in inventory, 0 newly out. **But 56 more differ on a flag only** (33 permitted to open, 23 pending to open), which the bar's "100 %" did not allow for | **fails as written** |
| R5 agreement with a regeneration (the 5a pair, 745 hidden producers) | taken out and gone: 98.8 % Delaware, 98.1 % Midland under both rules. Left in and still there: Delaware 40.1 % against 39.9 %, **Midland 38.4 % against 38.6 %**. Sticks rule 2 puts back: 3 (Delaware 2, Midland 1), **0 of 3 still in the regenerated set** against a bar of >= 70 % | **fails** |
| R6 capture of hidden producers (wells) | Delaware 47.1 % against 47.3 % (194 against 195 of 412); Midland 69.4 % against 70.0 % (231 against 233 of 333) | passes |
| R7 stale estimate | total -6.7 % Delaware (166 against 178), +8.3 % Midland (208 against 192) | passes |
| R8 container | sql/74 applies (33 checks); two nights on rule 1; the night rule 2 lands: `written`, 157 log rows all `rule_change`, not held with the breaker limit forced to 1; the night after: 0 log rows, table identical. 8 of 8 checks. `pytest -q` 1,184 passed, 52 skipped; ruff clean on touched files | passes |

## Day 0 under both rules (sticks)

| | Delaware rule 1 | Delaware rule 2 | Midland rule 1 | Midland rule 2 |
|---|---|---|---|---|
| open | 45,280 | 45,404 | 33,027 | 33,056 |
| permitted (flag) | 655 | 629 | 74 | 71 |
| pending (flag) | 34 | 22 | 19 | 8 |
| producing (out) | 73 | 4 | 16 | 3 |
| conflict (out) | 20 | 3 | 2 | 0 |
| crowded (out) | 69 | 69 | 48 | 48 |
| counts as inventory | 45,900 | 45,986 | 33,072 | 33,087 |

## Reading the two failures

**R4.** The landing test also decides the `pending` and `permitted` flags, so the narrower window drops 56 flags from
permits and drilled-not-producing wells that sit 150 to 500 ft off the stick with depth evidence. I wrote the bar for
sticks that leave inventory and did not think of the flags. Inventory does not move with a flag. The 56 wells were not
traced one by one.

**R5.** Two things in it:

- On wells drilled after a set is made, the two rules are almost the same rule. Of about 620 sticks taken out by the 745
  hidden producers, the rules differ on **3**. New wells land at the stick's depth or they do not match under either
  rule. So the hindcast barely tests the question.
- All 3 are gone from the regenerated set. In each of the three DSU x bench the regeneration went from 4 sticks to 1, 1
  and 0 (several new wells came on in each), so these three sticks would have gone whichever rule judged them.
  It is still 0 of 3, and the bar said 70 %.
- The Midland "left in" share is 98 of 255 against 98 of 254: one more stick left in, the same number surviving.

What the hindcast cannot test is the day-0 class itself. The 101 sticks that rule 2 puts back on live are sticks the
generator placed **with the well already known**, so "does a regeneration keep them" is true for them by construction:
sets 16 and 17 are that regeneration. The pair has no such sticks to speak of.

## Where that leaves the rule

Before the run I wrote that if a regeneration removes the sticks rule 2 leaves in, the 500 ft guard was right and rule 2
would be reported as failed and dropped, not tuned. R5 fails, on 3 sticks. That is the honest state; it is your call
whether 3 sticks decide it.

The alternatives, none taken here:

1. **Drop rule 2**, keep `box_recon_1`. Day 0 then keeps reading about 89 sticks out and 22 in conflict that the generator
   placed on purpose, and the first real count the nightly drives is low by about 101 sticks (0.13 %).
2. **Land rule 2 on the day-0 evidence** (R3, R4's 101, R6, R7), with R5 recorded as failed on a sample too small to bear
   it. After 11-26, with its own go and a short shadow.
3. **Settle it on the generator side first**: decide whether a row pinned on a same-tag producer 250 to 500 ft off is a
   real location (the 41 DSUs with wells at both depths say sometimes yes; the 30 carried-depth sticks say sometimes it
   is a depth miss). If those rows should not exist, the fix is a generator change and a regeneration, and rule 1 is
   right as it stands.

## Not done

- Nothing applied; the live `COMMENT` still names the 500 ft guard and the nightly still runs `box_recon_1`.
- Planned-survey matches (location 10069400) are unchanged by rule 2; no decision was taken on them.
- The two sticks within 150 ft of a producer the set had read (10132195, 10132738) were not traced.
