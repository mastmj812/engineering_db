"""Sync (or incrementally update) Novi's bulk TSV files to disk.

Wraps `NoviDataSdk.update_bulk_data()` from the vendored Novi sample SDK
(`etl/novi/sdk.py`). The SDK handles both first-time full downloads and
diff merging on subsequent runs; we just pass through the env-configured
scope/version and surface the on-disk path it produces.

Run as a module:
    python -m etl.novi.sync
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .sdk import NoviDataSdk

logger = logging.getLogger(__name__)


def sync_bulk(data_dir: Path | None = None) -> Path:
    """Sync (or incrementally update) the on-disk Novi TSV files.

    Args:
        data_dir: Optional override for where to keep the local data tree.
            Defaults to `./data` relative to the working directory.

    Returns:
        Path returned by the Novi SDK — the directory containing the current
        bulk TSV files (typically `<data_dir>/<scope>/All basins/All
        subbasins/Bulk/` or similar).

    Raises:
        RuntimeError: if the SDK returns without raising but the expected
            MVP TSVs are missing on disk. Guards against the SDK's
            diff-merge bug, which can destroy local TSVs silently when a
            fresh export becomes available between syncs.
    """
    load_dotenv()
    email = os.environ["NOVI_EMAIL"]
    password = os.environ["NOVI_PASSWORD"]
    scope = os.getenv("NOVI_SCOPE", "us-horizontals")
    version = os.getenv("NOVI_VERSION", "v3")

    data_dir = data_dir or Path("data")
    sdk = NoviDataSdk(
        email=email,
        password=password,
        version=version,
        scope=scope,
        data_dir=data_dir,
    )
    target = sdk.update_bulk_data()
    logger.info("Novi bulk sync complete; data at: %s", target)
    _verify_bulk_dir(target)
    return target


def _verify_bulk_dir(bulk_dir: Path) -> None:
    """Verify the MVP TSVs exist post-sync.

    Defends against the SDK's diff-merge code path which can destroy
    local TSVs silently (renames Bulk/ to _tmp/current/, downloads diffs,
    merges into a new Bulk/; if merge output goes wrong, the finally
    block's `rmtree(tmp_dir_base)` takes the original data with it).

    Raised here so the orchestrator's per-step try/except records a
    clear failure BEFORE `etl.novi.load` reaches its TRUNCATE statement
    and damages the DB.
    """
    from etl.novi.load import MVP_TABLES  # avoid circular import at module load

    db_dir = bulk_dir / "Database"
    if not db_dir.exists():
        raise RuntimeError(
            f"Novi sync returned {bulk_dir} but Database/ subdirectory is "
            f"missing. Likely the SDK's diff-merge path failed destructively. "
            f"Recovery: delete data/_tmp and data/{bulk_dir.parts[-4] if len(bulk_dir.parts) >= 4 else '<scope>'} "
            f"then re-run sync (will trigger full re-download)."
        )
    missing = [t for t in MVP_TABLES if not (db_dir / f"{t}.tsv").exists()]
    if missing:
        raise RuntimeError(
            f"Novi sync completed but expected TSVs are missing: {missing}. "
            f"Likely the SDK's diff-merge path failed destructively. "
            f"Recovery: delete data/_tmp and the scope directory, then re-sync."
        )


def main() -> int:
    """CLI entry point; returns 0 on success."""
    path = sync_bulk()
    print(path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
