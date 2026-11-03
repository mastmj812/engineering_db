# Step 21a pre-registration — errata (new file; the frozen text is not edited)

The pre-registration text and `box/step21.DEFINITION` stay byte-identical: the definition digest `9780f326` (revision 8,
frozen SHA `5ceadc2`) is pinned by tests and quoted by 21b, 21c and 21d. Corrections of wording live here.

## E1 — §6 tiers, "moved at the tuning gate" (D151 Q1; carried to step 23, 2026-11-03)

**Frozen wording** (PREREGISTRATION §6; `DEFINITION["tiers"]["provisional"]`):
"provisional: D99 FAIL, or no cell judgeable (no holdout scored), or moved at the tuning gate".

**Reads as:** "... or moved **to provisional** at the tuning gate".

**Why.** §5 allows two different moves at the tuning gate. One is a treatment move, `mid_r2p_wf` → `mid_r2p`, on tuning
evidence (the step-15 BS3_C / WCB_1 precedent). The other is a tier move to provisional (the step-15 BS2_C precedent). A
treatment move is judged on its group's own holdout. Step-15 WCB_1 made that move, passed its holdout 6 / 6 and shipped
validated in run 9. Gate 21c applied this reading to LSSH: its record moved `mid_r2p_wf` → `mid_r2p` at gate 21b, passed 6 / 6
on the `mid_r2p` intervals frozen for exactly that case, and ships validated (D151 (1), Q1 (b); Michael 2026-11-03,
"LSSH validated").

**Effect:** none on any score, interval, tier or digest. This erratum records the reading D151 already decided.
