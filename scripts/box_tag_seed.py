"""BOX step 20a — turn the finished Midland tag screen into ref.formation_tag_overrides seed rows (repo only).

    python -m scripts.box_tag_seed --screen docs/box/step20a-2026-10-26/tag_screen [--write] [--check-live]

Reads the screen folder (summary.json, screen_flags.csv, cards_sample.csv, well_calls.csv) and builds the rows with
box.tag_screen.override_seed (convention (a) as amended 2026-10-28). --write replaces the seed's own block (rows whose
note carries tag_screen.SEED_TAG) in seeds/formation_tag_overrides.csv and keeps every other row as it is. --check-live
reads curated.formation_blueox (read-only) and asserts each row's `was` is the live tag and no row is already an
override. Nothing is written to the warehouse: loading the seed is scripts.apply_formation_tag_overrides, on a go.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd

from box import tag_screen as ts

REPO = Path(__file__).resolve().parent.parent
SEED = REPO / "seeds" / "formation_tag_overrides.csv"
# the date each card round was judged (FINDINGS §8: 20a cards 10-26, round 1 + what-if 10-27, round 2 + full review 10-28)
CARD_DATES = {"20a": "2026-10-26", "round 1": "2026-10-27", "what-if round 1": "2026-10-27", "what-if round 2": "2026-10-27",
              "round 2": "2026-10-28", "round 3 (full review)": "2026-10-28"}


def build(screen: Path, date: str) -> pd.DataFrame:
    states = json.loads((screen / "summary.json").read_text(encoding="utf-8"))["classes"]
    rd = {"dtype": {"api10": str}}
    return ts.override_seed(pd.read_csv(screen / "screen_flags.csv", **rd), pd.read_csv(screen / "cards_sample.csv", **rd),
                            pd.read_csv(screen / "well_calls.csv", **rd), states, CARD_DATES, date)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--screen", type=Path, required=True)
    ap.add_argument("--date", default="2026-10-28", help="date the class acceptances were ratified")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check-live", action="store_true")
    a = ap.parse_args(argv)
    new = build(a.screen, a.date)
    with open(SEED, encoding="utf-8", newline="") as fh:
        old = list(csv.DictReader(fh))
    kept = [r for r in old if ts.SEED_TAG not in r["note"]]
    clash = sorted({r["api10"] for r in kept} & set(new["api10"]))
    if clash:
        raise ValueError(f"api10s already overridden outside this screen's block: {clash}")
    kinds = new["note"].str.extract(r"^(carded|class-accepted|\S+)")[0].where(lambda s: s.isin(["carded", "class-accepted"]), "well_calls")
    print(f"{len(new)} rows ({kinds.value_counts().to_dict()}); seed keeps {len(kept)} other rows -> {len(kept) + len(new)} total")
    print(pd.crosstab(new["was"], new["corrected_code"], margins=True).to_string())
    if a.check_live:
        from etl.db import get_connection

        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT api10, formation_blueox, formation_blueox_source FROM curated.formation_blueox WHERE api10 = ANY(%s)",
                        (new["api10"].tolist(),))
            live = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
            cur.execute("SELECT count(*) FROM ref.formation_tag_overrides")
            n_live = cur.fetchone()[0]
        missing = sorted(set(new["api10"]) - set(live))
        drift = [(r.api10, r.was, live[r.api10][0]) for r in new.itertuples() if r.api10 in live and live[r.api10][0] != r.was]
        already = [r for r in new["api10"] if r in live and live[r][1] == "ratified_override"]
        print(f"live check (read-only): {len(live)}/{len(new)} found; `was` = live tag on {len(live) - len(drift)}; "
              f"already overridden {len(already)}; live override table {n_live} rows (seed outside this block {len(kept)})")
        for x in drift:
            print(f"  drift {x[0]}: was {x[1]}, live {x[2]}")
        if missing or drift or already:
            print(f"  missing {missing}; already {already}")
            return 1
    if a.write:
        out = pd.concat([pd.DataFrame(kept), new], ignore_index=True)
        out.to_csv(SEED, index=False, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        print(f"wrote {SEED.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
