"""BOX step 21c — the PREREGISTRATION §10 harness, run on the D52 HOLDOUT (Michael 2026-11-02, 21c option A).

    python -m scripts.box_step21c_harness <the scripts.box_acceptance arguments, verbatim, incl. --score-holdout --holdout-once>

The frozen box/acceptance.run refuses `step16 and score_holdout` (a Delaware step-16 guard: those holdouts were spent, D118),
and the Midland record variant mid_r2 exists only on the --step16 path. This module replaces box.acceptance.run with the frozen
run() compiled from its own source minus exactly that two-line guard (box/step21c.unguarded_run: refuses unless the source hashes
to the 5ceadc2 run(); tests/test_box_step21c.py pins the diff), then calls scripts.box_step21b_harness.main(argv) unchanged — the
21b months observer, which in turn calls scripts.box_acceptance.main(argv). Nothing else differs from a 21b run: same frozen pool,
fold, F(k) training sample (drawn from the fold, not the view), actuals pin. The harness's own mid_r2_wf on this run takes its
haircuts from HOLDOUT cells (the step-16 branch passes history=None) and is never read: scripts.box_step21c judge applies the
TUNING haircuts (D58).
"""

from __future__ import annotations

import sys

from box import acceptance as ac
from box import step21c as s21c


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--score-holdout" not in argv or "--step16" not in argv:
        raise SystemExit("box_step21c_harness is the --step16 --score-holdout run only")
    ac.run = s21c.unguarded_run()  # box_acceptance.main looks it up as an attribute at call time
    from scripts import box_step21b_harness

    return box_step21b_harness.main(argv)


if __name__ == "__main__":
    sys.exit(main())
