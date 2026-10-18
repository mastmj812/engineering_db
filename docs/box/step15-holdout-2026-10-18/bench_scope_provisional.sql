-- Holdout gate 2026-10-18 (Michael): the four step-15 benches that FAILED their one-time D99 holdout join the D105 provisional tier.
-- NOT APPLIED. Run only on an explicit go (live write to box.bench_scope; Michael-owned table).
BEGIN;
DO $$ BEGIN
  IF (SELECT count(*) FROM box.bench_scope WHERE basin = 'delaware' AND bench IN ('BS3_S', 'BS3_C', 'WCB_2', 'BS1_S')
        AND in_scope AND validation = 'validated') <> 4 THEN RAISE EXCEPTION 'unexpected bench_scope state before the write'; END IF;
END $$;
UPDATE box.bench_scope
   SET validation = 'provisional',
       reason = 'Provisional after a FAILED one-time D52 / D99 holdout (Michael 2026-10-18): raw box_v2, no haircut; tuning + holdout + pooled bias disclosed. '
                || 'Evidence docs/box/step15-holdout-2026-10-18. Prior: ' || reason,
       decided_on = DATE '2026-10-18',
       decision_ref = 'step 15 holdout gate (docs/box/step15-holdout-2026-10-18/FINDINGS.md §7)'
 WHERE basin = 'delaware' AND bench IN ('BS3_S', 'BS3_C', 'WCB_2', 'BS1_S') AND validation = 'validated';
DO $$ BEGIN
  IF (SELECT count(*) FROM box.bench_scope WHERE validation = 'provisional') <> 8 THEN RAISE EXCEPTION 'expected 8 provisional benches after the write'; END IF;
  IF (SELECT count(*) FROM box.bench_scope WHERE bench IN ('WCB_1', 'WCC') AND validation = 'validated') <> 2 THEN RAISE EXCEPTION 'WCB_1 / WCC must stay validated'; END IF;
END $$;
COMMIT;
