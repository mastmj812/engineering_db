# BOX sticks nightly reconciliation, rule `box_recon_2`: bars

Written 2026-11-20, **before the rule is authored or run on anything**. Committed on its own first. Branch
`claude/box-sticks-recon2`, cut from main at `d36ff24`. A DRAFT for Michael's review: nothing below is built until he
agrees the rule and the bars. Why: `docs/box_sticks/phase5d-2026-11-19/matched_wells_vs_generator.md` (draft PR #261).

Record sets: set 16 (Delaware, 46,062 sticks) and set 17 (Midland, 33,138), generator `box_sticks_0.12`.

## The one change proposed

Today (`box_recon_1`), a producing well matches a stick leg when it covers >= 0.5 of the leg inside its 150 ft corridor and

- **same tag within 500 ft TVD**, or any tag within 150 ft.

Proposed (`box_recon_2`):

- **within the record set's own same-landing window, `cfg.generator.same_dv_ft` (150 ft today), whatever the tag.** The
  500 ft same-tag branch is dropped. The value is read from `box.location_set.cfg`, as the crowded rule already reads it;
  no constant is copied.

Unchanged, stated so the bars are read against the right rule:

- A well with **no depth evidence** (planned survey, round-100 TVD, screened out) is still taken at the DSU's landing of its
  tagged bench, family where that bench has no row. Its `match_basis` stays `planned`.
- Overlap thresholds (0.5 match, 0.3 conflict), flat-ended corridors, the well line of generator 0.12, producing-only
  trigger, the WCA_1 / WCA_2 rule, `pending` / `permitted` flags, the stale row and its estimate.
- **Crowded** is unchanged and already reads the set's envelope, stacked bands included. So a producer inside a stacked band
  directly over or under a stick (which rule 1 may call `producing`) is `crowded` under rule 2: out of inventory either way.
- sql/68 and the Novi objects are not touched; their 500 ft guard stays theirs.

Depth offsets below are dz = well depth - stick target TVD.

## Bars

| Bar | Measure (grain) | Passes when |
|---|---|---|
| R1 | The module's SQL on live (read-only) against the Python reference, stick by stick (sticks) | >= 99.5 % same status and >= 99.5 % same crowded flag, per basin |
| R2 | Wall time of the read-only pass on live; plan | <= 300 s; EXPLAIN names `box_location_stick_geog_gix` |
| R3 | Day 0 on sets 16 and 17 (sticks): producing or conflict; crowded | producing or conflict <= 0.1 % of each basin's sticks (46 Delaware, 33 Midland); crowded <= 0.5 % (as bar E3) |
| R4 | Every stick whose status differs between rule 1 and rule 2 on the same wells, live, read-only (sticks) | 100 % are `producing` or `conflict` under rule 1 with the matching well at 150 < abs(dz) <= 500 ft; **no** stick goes the other way (open to producing or conflict) |
| R5 | Agreement with a regeneration, on the 5a pair (generator 0.12 as of 2026-01-01; the same inputs regenerated with the 745 hidden producers put back). Sticks the nightly takes out (producing, conflict or crowded) because of a hidden producer: is the stick gone from the regenerated set? Sticks it leaves in inventory in a DSU x bench holding a hidden producer: is the stick still there? (sticks, matched by carried id) | rule 2 agrees with the regeneration on a share at least as high as rule 1 on **both** questions, per basin; and of the sticks rule 1 takes out and rule 2 leaves in, >= 70 % are still in the regenerated set |
| R6 | Capture on the same pair: hidden producers that take at least one stick out, status or crowded (wells) | not more than 5 points below rule 1, per basin. The wells lost are listed with their dz |
| R7 | The stale estimate (bar E4 of gate 5b, same 156 DSU x bench per basin) | total within +-10 % of the regenerated count per basin |
| R8 | Rehearsal container: the night the version changes; the night after | first night: status `written`, every log row `rule_change`, not held by the breaker; second night: 0 log rows. `pytest -q` green; ruff clean on touched files |

R5 is the bar that decides the question. If the regeneration removes the sticks that rule 2 leaves in, the 500 ft guard was
right and rule 2 fails; that would be reported as such and the rule dropped, not tuned.

## Reported, no bar

- The two sticks within 150 ft of a producer the set had read (locations 10132195 and 10132738): traced, generator side.
- The 48 of 89 sticks with no same-bench well at the stick's own depth, by landing rung: how many the regeneration keeps.
- Day-0 counts by status and basin under both rules, side by side.

## Questions for Michael before anything is authored

1. **The rule itself**: 150 ft from the set's config, tag-blind, as above? Or keep a same-tag branch wider than 150 ft but
   narrower than 500?
2. **When it lands.** A rule change mid-week makes that night's log all `rule_change` and the nights before and after are
   not on one rule. Recommend: author and rehearse now, apply nothing to the nightly path until the shadow week closes on
   11-26, then land it and run a short second shadow (3 nights) on rule 2 before the gate 5 decision.
3. **Planned-survey matches** (location 10069400: taken out on a planned-survey well recorded 863 ft above the stick). Rule
   2 does not change these. Should a `match_basis = planned` match put the stick in `conflict` (review queue) instead of
   `producing`? Day 0 has 2 such matches of 89. Not proposed here; your call.
