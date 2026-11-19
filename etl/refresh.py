"""Refresh curated materialized views.

Runs `refresh_curated()`, which refreshes each matview individually and SKIPS a
gated one (e.g. curated.production_forecast) when its source raw table hasn't
changed since its last successful refresh — avoiding the memory-heavy rebuild on
no-change nights.

The nightly tag-rule step (etl/tag_rule.py, sql/72) runs as a hook just before curated.formation_blueox; it is
soft (never fails the refresh) and a no-op until sql/72 is applied.

The nightly BOX sticks reconciliation (etl/box_recon.py, sql/74) runs as a hook just before curated.codev_context, the
first refresh after everything it reads (curated.wells, well_lateral_survey, formation_blueox, formation_blueox_tvd). It
is soft too, and a no-op until sql/74 is applied and a basin has a record box.location_set.

Run as a module:
    python -m etl.refresh              # gated (nightly): skip unchanged matviews
    python -m etl.refresh --force      # refresh everything (use after a reconcile)
    python -m etl.refresh --no-tag-rule   # skip the tag-rule step (manual refreshes only)
    python -m etl.refresh --no-box-recon  # skip the BOX sticks reconciliation step (manual refreshes only)
"""

from __future__ import annotations

import argparse
import logging

from etl import box_recon, tag_rule
from etl.db import refresh_curated

logger = logging.getLogger(__name__)


BOX_RECON_BEFORE = "curated.codev_context"      # the first matview after the ones etl/box_recon.py reads


def build_hooks(tag: bool = True, box: bool = True) -> dict | None:
    """refresh_curated hooks: each fires just before its matview is refreshed; both are soft and no-ops until their tables exist."""
    hooks = {}
    if tag:
        hooks["curated.formation_blueox"] = tag_rule.nightly_hook
    if box:
        hooks[BOX_RECON_BEFORE] = box_recon.nightly_hook
    return hooks or None


def main(argv: list[str] | None = None) -> None:
    """Refresh curated matviews (gated by default) and log success/failure."""
    parser = argparse.ArgumentParser(description="Refresh curated matviews")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh every matview regardless of the change gate (e.g. after a "
        "full_reconcile_table, whose deletions the incremental watermark misses).",
    )
    parser.add_argument(
        "--no-tag-rule",
        action="store_true",
        help="Skip the nightly tag-rule step before curated.formation_blueox (manual refreshes only).",
    )
    parser.add_argument(
        "--no-box-recon",
        action="store_true",
        help="Skip the nightly BOX sticks reconciliation step before curated.codev_context (manual refreshes only).",
    )
    args = parser.parse_args(argv)
    hooks = build_hooks(tag=not args.no_tag_rule, box=not args.no_box_recon)
    try:
        refresh_curated(force=args.force, hooks=hooks)
        logger.info("Curated refresh complete")
    except Exception:
        logger.exception("Curated refresh failed")
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
