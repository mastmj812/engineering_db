"""Load Novi Intelligence PUD ML-attribute shapefiles into raw_novi_intel.pud_attrs.

The PUD oil inventory ships two attribute layers alongside the economic PUD_Oil
sticks (which are already in raw_novi_intel.sticks):
    * Other_ML_PUD_Oil        -> spacing / depletion / completion ML score + tier
    * Undrilled_Rock_Quality  -> rock-quality ML score + tier
Geometry is identical across all three (same Unique IDs), so we read ATTRIBUTES
only, join the two files on Unique ID, and key (basin, report_version, unique_id)
for the curated LEFT JOIN (sql/12) onto the PUD sticks.

Per-basin DBF field drift is absorbed by candidate-name lists (mirrors STICK_SRC
in load_shapefiles): Delaware uses SpacingS/SpacingT/... with key 'Unique ID';
Midland uses ML-Spacing/ML-Spaci_1/... with the 10-char-truncated key 'Unique Ide'.

Idempotent per (basin, report_version): DELETEs that slice before inserting.

Run as a module:
    python -m etl.novi_intel.load_pud_attrs                 # both basins
    python -m etl.novi_intel.load_pud_attrs --basin midland
"""

from __future__ import annotations

import logging

from etl.db import get_connection, log_etl_run
from etl.novi_intel import paths
from etl.novi_intel.load_shapefiles import _open_reader, _safe_float

logger = logging.getLogger(__name__)

# Unique-ID join key: Midland's Other_ML DBF truncates the field to 'Unique Ide'.
KEY_FIELDS = ["Unique ID", "Unique Ide"]

# target column -> candidate source DBF field names (Delaware | Midland drift)
OML_SRC: dict[str, list[str]] = {
    "spacing_s": ["SpacingS", "ML-Spacing"],
    "spacing_t": ["SpacingT", "ML-Spaci_1"],
    "deplet_s":  ["DepletS", "ML-Prior D"],
    "deplet_t":  ["DepletT", "ML-Prior_1"],
    "complet_s": ["CompletS", "ML-Complet"],
    "complet_t": ["CompletT", "ML-Compl_1"],
}
RQ_SRC: dict[str, list[str]] = {"rqs": ["RQS"], "rqt": ["RQT"]}
TIER_COLS = {"spacing_t", "deplet_t", "complet_t", "rqt"}

ATTR_COLS = list(OML_SRC) + list(RQ_SRC)                      # 8 attribute columns
PUD_ATTR_COLS = ["basin", "report_version", "unique_id"] + ATTR_COLS


def _pick(rec: dict, candidates: list[str]):
    return next((rec[c] for c in candidates if c in rec and rec[c] not in (None, "")), None)


def _read_attrs(zip_path, src_map: dict[str, list[str]]) -> dict[str, dict]:
    """unique_id -> {col: typed value} for one attribute shapefile (attrs only)."""
    r = _open_reader(zip_path)
    out: dict[str, dict] = {}
    for rec_obj in r.iterRecords():
        rec = rec_obj.as_dict()
        uid = _pick(rec, KEY_FIELDS)
        if uid is None:
            continue
        row: dict = {}
        for col, cands in src_map.items():
            val = _pick(rec, cands)
            row[col] = (None if val is None else str(val).strip()) if col in TIER_COLS else _safe_float(val)
        out[str(uid).strip()] = row
    return out


def load_pud_attrs(basin: str, version: str = paths.REPORT_VERSION) -> int:
    oml_zip = paths.pud_attr_zip(basin, "other_ml")
    rq_zip = paths.pud_attr_zip(basin, "rock_quality")
    if not oml_zip or not rq_zip:
        logger.warning(
            "Missing PUD attr zip(s) for %s (other_ml=%s rock_quality=%s)", basin, oml_zip, rq_zip
        )
        return 0

    with log_etl_run("novi_intel", f"pud_attrs:{basin}") as run:
        oml = _read_attrs(oml_zip, OML_SRC)
        rq = _read_attrs(rq_zip, RQ_SRC)
        uids = set(oml) | set(rq)

        rows: list[tuple] = []
        for uid in uids:
            a, b = oml.get(uid, {}), rq.get(uid, {})
            row = [basin, version, uid]
            row += [(a if col in OML_SRC else b).get(col) for col in ATTR_COLS]
            rows.append(tuple(row))

        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM raw_novi_intel.pud_attrs WHERE basin=%s AND report_version=%s",
                (basin, version),
            )
            placeholders = ", ".join(["%s"] * len(PUD_ATTR_COLS))
            cur.executemany(
                f"INSERT INTO raw_novi_intel.pud_attrs ({', '.join(PUD_ATTR_COLS)}) "
                f"VALUES ({placeholders})",
                rows,
            )
            conn.commit()
        run.rows_inserted = len(rows)
        logger.info(
            "pud_attrs %s: %d rows (other_ml=%d rock_quality=%d)", basin, len(rows), len(oml), len(rq)
        )
        return len(rows)


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Load Novi Intelligence PUD ML attributes.")
    ap.add_argument("--basin", choices=["delaware", "midland"], default=None)
    args = ap.parse_args()
    for b in [args.basin] if args.basin else ["delaware", "midland"]:
        load_pud_attrs(b)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    main()
