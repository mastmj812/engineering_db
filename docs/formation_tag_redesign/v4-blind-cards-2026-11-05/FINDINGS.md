# Rule v4 (rev 2) — blind cards, K0 (Michael, 2026-11-05)

**K0 FAILS: 14 of 30 agree (47 %).** Delaware is 7/15 and Midland 7/15, against a bar of ≥ 70 % overall and ≥ 60 % per
basin. Per RULE_V4.md §3, "if K0 fails, v4 fails", so the full score (K1–K13) was not run. Verdicts are in
`cards_sample.csv`.

## What separates your agrees from your rejects

This section is descriptive only. It reads the same 30 cards after the fact, so it can't validate a fix. A fix
would need a fresh blind draw.

| Cut | Agree / cards |
|---|---|
| Delaware, family moved by the **grid** (his B1 top) | **0 / 4** (cards 7, 8, 10, 13) |
| Delaware, ladder | 7 / 11 |
| Midland, ladder | 7 / 15 |
| Margin ≥ 50 ft | 12 / 21 |
| Margin ≥ 70 ft | 10 / 14 |
| Margin ≥ 80 ft | 8 / 8 |

The median margin on your agrees was 87 ft; on your rejects, 51 ft.

1. **The geologist's B1 top is not where operators put the WCA / WCB boundary.**
   - Every Delaware move the grid decided was rejected.
   - Three of them were WCB_1→WCA: Novi "WOLFCAMP A", Enverus "WOLFCAMP B UPPER", with the grid calling the
     lateral XY→B1.
   - The fourth was WCA_2→WCB_1.
   - The baseline pointed the same way: WCB_1 wells agree with the grid only 67 % of the time, with 26 % sitting
     shallower than B1.
   - So B1 is an open boundary, like B2 (WCB_2 / WCC), and the grid should not decide WCA vs WCB.
2. **Ladder calls are right about when the margin is large, and a coin flip when it isn't.**
   - The rungs are county medians. Your judgement uses the local strike section.
   - On 100–250 ft splits, a 30–60 ft margin sits inside the gap between the county ladder and local reality.
3. **Most likely to hold up:** moves with a wide margin, cross-family Bone Spring / Avalon moves (cards 1–4), and
   rule V's ladder below WCA (15/15).

## Where the run of attempts stands

| Attempt | Self-consistency | Agrees with you |
|---|---|---|
| v3 (local bands from vendor codes) | up (band test 10.0 → 6.0 % Delaware) | 30–43 % of labelled calls |
| v4 rev 2 (anchor + county ladder) | not scored | 47 % of blind cards |
| Rule V (Lea/Eddy, a ladder below WCA, ≥ 3 witnesses within 1.5 mi, one class) | — | 15 / 15 family calls |

An automatic sub-bench call on the thin splits does not reach your agreement bar with the evidence we have. What
reaches it is narrower: big-margin, family-level corrections against a nearby reliable reference.
