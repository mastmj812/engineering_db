"""Generic Enverus pull — parameterized by dataset name.

Enverus's iteration pattern (`v3.query(dataset, **filters)`) is identical
across every dataset, so one parameterized function covers all of them.
The per-dataset wrapper `pull_wells.py` is a thin shim that just calls
`pull_dataset(...)` with the right name and conflict columns.

Incremental loads use `meta.etl_log` as the cursor: the timestamp of the
last successful run for this dataset becomes the `updateddate=gt(...)`
filter. The cutoff is approximate (timestamps vs. Enverus's record-update
date), but `gt(...)` semantics prevent double-processing the boundary
record — anything missed gets picked up the following run.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Sequence

from etl.db import get_connection, log_etl_run, upsert_batch_resilient
from etl.enverus.client import get_client

logger = logging.getLogger(__name__)

SCHEMA = "raw_enverus"
BATCH_SIZE = 5000


def _last_successful_run(dataset: str) -> datetime | None:
    """Return the `run_finished_at` of the most recent successful pull, if any."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MAX(run_finished_at)
                  FROM meta.etl_log
                 WHERE source = 'enverus'
                   AND table_name = %s
                   AND status = 'success'
                """,
                (dataset,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None
    finally:
        conn.close()


def pull_dataset(
    dataset: str,
    conflict_cols: Sequence[str],
    incremental: bool = True,
    extra_filters: dict[str, Any] | None = None,
    chunked_filter: tuple[str, list[Any]] | None = None,
    chunk_size: int = 250,
    skip_chunked_filter_on_incremental: bool = False,
) -> int:
    """Pull an Enverus dataset and upsert into `raw_enverus."<dataset>"`.

    Args:
        dataset: Enverus dataset name (e.g. 'wells', 'production'). Used as
            both the SDK's `query(dataset, ...)` argument and the target
            table name in `raw_enverus`.
        conflict_cols: Primary-key columns for the upsert. Confirmed against
            the generated DDL in `sql/03_raw_enverus_ddl.sql`.
        incremental: When True, apply `updateddate=gt(<last_run>)`. When
            False, pull the full universe (use sparingly).
        extra_filters: Optional additional filters merged into the
            `client.query(...)` call. Use this for scope-limiting filters
            like `{"envregion": "PERMIAN"}`.
        chunked_filter: Optional `(field_name, values)` tuple. When set, the
            pull iterates over chunks of `values` and calls
            `client.query(... field_name=in(chunk))` once per chunk. Use
            when a filter target is too long to fit in a single URL — e.g.
            a 100k-element `completionid` list to skip vertical production.
        chunk_size: Number of values per `in(...)` chunk. Default 250 keeps
            the URL well under typical 8 KB limits (each id ~11 chars).
        skip_chunked_filter_on_incremental: If True, the chunked filter
            is bypassed when an incremental cursor exists. **Default is
            False** because empirically (2026-05-28) the broad query
            without per-wellbore filtering forces Enverus's backend into
            a much slower query plan — the `api_uwi_unformatted=in(...)`
            filter appears to also serve as an index hint. The "skip
            chunking on incremental" optimization sounded right in
            theory but is slower in practice; left as an opt-in for
            future experimentation if Enverus's query planning improves.

    Returns:
        Total rows upserted (also recorded in `meta.etl_log`).
    """
    with log_etl_run("enverus", dataset) as run:
        base_filters: dict[str, Any] = {"deleteddate": "null"}
        if extra_filters:
            base_filters.update(extra_filters)

        is_incremental_run_with_cursor = False
        if incremental:
            last = _last_successful_run(dataset)
            if last is not None:
                base_filters["updateddate"] = f"gt({last.date().isoformat()})"
                logger.info(
                    "Enverus %s: incremental cutoff updateddate=%s",
                    dataset,
                    base_filters["updateddate"],
                )
                is_incremental_run_with_cursor = True
            else:
                logger.info(
                    "Enverus %s: no prior successful run; full pull",
                    dataset,
                )

        # Decide whether to apply the chunked filter for this run. Skipping
        # it on incremental runs is a significant speed win (cuts hundreds
        # of API round-trips when each one returns ~0 rows).
        effective_chunked_filter = chunked_filter
        if (
            chunked_filter is not None
            and is_incremental_run_with_cursor
            and skip_chunked_filter_on_incremental
        ):
            logger.info(
                "Enverus %s: incremental run — skipping chunked filter on '%s' "
                "(updateddate cutoff already restricts the response; periodic "
                "cleanup scrubs out-of-scope rows)",
                dataset,
                chunked_filter[0],
            )
            effective_chunked_filter = None

        # Build the list of per-call filter dicts. Without chunked_filter
        # it's a single dict; with chunked_filter it's one dict per chunk.
        if effective_chunked_filter is None:
            query_filter_list: list[dict[str, Any]] = [base_filters]
        else:
            field_name, values = effective_chunked_filter
            chunks = [
                values[i : i + chunk_size]
                for i in range(0, len(values), chunk_size)
            ]
            query_filter_list = [
                {
                    **base_filters,
                    field_name: f"in({','.join(str(v) for v in chunk)})",
                }
                for chunk in chunks
            ]
            logger.info(
                "Enverus %s: chunked filter on '%s' — %d values in %d chunks of %d",
                dataset,
                field_name,
                len(values),
                len(chunks),
                chunk_size,
            )

        client = get_client()

        batch: list[dict] = []
        update_cols: list[str] | None = None
        total = 0

        # Each batch is upserted AND committed on its own (via
        # upsert_batch_resilient), so a mid-pull Supabase restart costs at most
        # the in-flight batch, not the whole streamed pull — the failure mode
        # that stranded the incremental cursor at 2026-06-22. The helper reconnects
        # and replays a batch on connection loss; it may hand back a fresh
        # connection, so we always reassign `conn`.
        conn = get_connection()
        try:
            for chunk_idx, filters in enumerate(query_filter_list, start=1):
                if len(query_filter_list) > 1:
                    logger.info(
                        "Enverus %s: chunk %d/%d",
                        dataset,
                        chunk_idx,
                        len(query_filter_list),
                    )
                for row in client.query(dataset, pagesize=1000, **filters):
                    # Enverus quirks handled here:
                    #   1. JSON keys are PascalCase (e.g. "API_UWI_14") but
                    #      the DDL emits unquoted columns which Postgres
                    #      case-folds to lowercase — lowercase keys to match.
                    #   2. Missing text/date values come back as the string
                    #      "NULL" rather than JSON null. Convert to Python
                    #      None so they land as SQL NULL. (Numeric nulls
                    #      already arrive as proper None.)
                    row = {
                        k.lower(): (None if v == "NULL" else v)
                        for k, v in row.items()
                    }
                    batch.append(row)
                    if len(batch) >= BATCH_SIZE:
                        if update_cols is None:
                            update_cols = [
                                c for c in batch[0].keys() if c not in conflict_cols
                            ]
                        conn, n = upsert_batch_resilient(
                            conn,
                            SCHEMA,
                            dataset,
                            batch,
                            conflict_cols,
                            update_cols,
                        )
                        total += n
                        batch = []

            if batch:
                if update_cols is None:
                    update_cols = [
                        c for c in batch[0].keys() if c not in conflict_cols
                    ]
                conn, n = upsert_batch_resilient(
                    conn,
                    SCHEMA,
                    dataset,
                    batch,
                    conflict_cols,
                    update_cols,
                )
                total += n
        finally:
            # Batches self-commit, so there's no end-of-pull commit; close (which
            # rolls back any incomplete final transaction) is all that's needed.
            conn.close()

        run.rows_inserted = total
        logger.info("Enverus %s: %d total rows upserted", dataset, total)
        return total
