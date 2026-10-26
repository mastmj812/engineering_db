"""DB-free tests for the D84 analog-pool refresh (box/pool_refresh.py)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from box import edge_gap_report as egr
from box import pool_refresh as pr
from box.qc_rule import apply_rule

HEADER = "api10,well_name,formation_blueox,box_bench,box_action,box_reason,planned,tvd_round,cohort,first_production_date,mid_lon,mid_lat\n"
BASE_ROWS = (
    "3001500001,OLD A 1H,WCA_1,WCA,keep,,False,False,True,2019-01-01,-103.9,32.1\n"
    "3001500002,OLD B 2H,WCB_1,WCA,reassign,class WCB_1->WCA (precision 0.70),False,False,True,2020-05-01,-103.8,32.2\n"
    "4238900003,OLD C 3H,WCXY,WCA,keep,\"in-pool swap, moot for extents (D19)\",False,False,False,2024-03-01,-103.5,31.8\n"
)


def _well(api10: str, tag: str, fp: str, *, flag: str | None = None, sql23: str | None = None, planned: bool = False, gor: str = "none") -> dict:
    return {
        "api10": api10, "well_name": f"W {api10}", "operator": "Op", "state_code": 42, "county": "Reeves", "formation_blueox": tag,
        "cons_status": "flag" if flag else "agree", "cons_suggest": flag, "sql23_nearest": sql23 or tag, "cons_gor_vote": gor,
        "planned": planned, "cons_witness": not planned, "tvd_round": False, "cohort": False,
        "first_production_date": dt.date.fromisoformat(fp), "mid_lon": -103.6, "mid_lat": 31.6, "in_extent": True,
    }


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    d = tmp_path / "step1-2026-10-06"
    d.mkdir()
    (d / "wells_final_WCA.csv").write_bytes((HEADER + BASE_ROWS).encode())
    (d / "wells_final_BS2_S.csv").write_bytes((HEADER + "4238900009,BS A,BS2_S,BS2_S,keep,,False,False,True,2018-01-01,-103.4,31.5\n").encode())
    return d


def _live() -> pd.DataFrame:
    rows = [
        _well("3001500001", "WCA_1", "2019-01-01"),  # base, unchanged
        _well("3001500002", "WCB_1", "2020-05-01"),  # base; the rule no longer concurs -> drift, never touched
        _well("4238900003", "WCA_2", "2024-03-01"),  # base, re-tagged WCXY -> WCA_2 -> drift
        _well("4238900004", "WCA_1", "2023-01-01"),  # judged before (fp <= cut), not in base -> not re-decided
        _well("4238900101", "WCA_1", "2026-09-01"),  # new, no flag -> added keep
        _well("4238900102", "WCB_1", "2026-09-02", flag="WCA_2", sql23="WCA_2"),  # new, accepted class + sql/23 -> added reassign
        _well("4238900103", "WCA_1", "2026-09-03", flag="WCB_2", sql23="WCB_2"),  # new, accepted WCA->WCB_2 -> rule_out
        _well("4238900104", "WCA_1", "2026-09-04", flag="WCXY", sql23="WCXY"),  # new, into WCXY never applied -> added
        _well("4238900105", "WCA_2", "2026-09-05", flag="BS3_S", sql23="BS3_S", planned=True),  # A-prime -> added tvd_suspect
        _well("4238900106", "BS2_S", "2026-09-06", flag="WCA_1", sql23="WCA_1"),  # BS -> WC never applied -> stays BS2_S
        _well("4238900107", "WCA_2", "2026-09-07", flag="AVA_1", sql23="AVA_1"),  # uncalibrated class -> added, tag kept
        _well("4238900108", "WCA_1", "2026-09-08"),  # new + in exclusions -> added, marked excluded
    ]
    return apply_rule(pd.DataFrame(rows), verdicts=None)


def _run(base_dir: Path, out: Path, live: pd.DataFrame, excluded: set[str] | None = None) -> tuple[dict, dict]:
    base = pd.read_csv(base_dir / "wells_final_WCA.csv", dtype={"api10": str})
    seen, seen_meta = pr.reconstruct_seen(base_dir, live)
    parts = pr.classify(live, base, set(seen["api10"]), excluded or {"4238900108"})
    meta = {"label": out.name, "seen": seen_meta, "summary": pr.summarize(parts)}
    man = pr.write_refresh(out, base_dir, parts, pr.next_universe(seen, live, out.name), meta)
    return parts, man


# ----------------------------------------------------------------------------
# judged universe
# ----------------------------------------------------------------------------


def test_reconstruct_seen_names_base_wells_and_cuts_on_newest_first_production(base_dir: Path) -> None:
    seen, meta = pr.reconstruct_seen(base_dir, _live())
    ids = set(seen["api10"])
    assert meta["method"] == "reconstructed" and meta["fp_cut"] == "2024-03-01"
    assert {"3001500001", "3001500002", "4238900003", "4238900009", "4238900004"} <= ids  # named + fp-cut
    assert not any(a.startswith("42389001") for a in ids)  # every 2026 well is new


def test_recorded_universe_wins_and_chains(base_dir: Path, tmp_path: Path) -> None:
    live = _live()
    _run(base_dir, tmp_path / "pool-2026-10-15", live)
    seen, meta = pr.reconstruct_seen(tmp_path / "pool-2026-10-15", live)
    assert meta["method"] == "recorded"
    assert set(live["api10"]) <= set(seen["api10"])
    labels = dict(zip(seen["api10"], seen["first_judged"], strict=True))
    assert labels["3001500001"] == "step1-2026-10-06" and labels["4238900101"] == "pool-2026-10-15"
    # a second refresh on the same live data adds nothing and keeps the file byte-identical
    parts, man = _run(tmp_path / "pool-2026-10-15", tmp_path / "pool-2027-01-15", live)
    assert parts["added"].empty and man["identity"]["WCA"]["n_appended"] == 0
    assert (tmp_path / "pool-2027-01-15" / "wells_final_WCA.csv").read_bytes() == (tmp_path / "pool-2026-10-15" / "wells_final_WCA.csv").read_bytes()


# ----------------------------------------------------------------------------
# classing: the step-1 rule on new wells only
# ----------------------------------------------------------------------------


def test_classify_applies_the_rule_to_new_wells_only(base_dir: Path) -> None:
    live = _live()
    base = pd.read_csv(base_dir / "wells_final_WCA.csv", dtype={"api10": str})
    seen, _ = pr.reconstruct_seen(base_dir, live)
    parts = pr.classify(live, base, set(seen["api10"]), {"4238900108"})
    a = parts["added"].set_index("api10")
    assert list(a.index) == ["4238900101", "4238900102", "4238900104", "4238900105", "4238900107", "4238900108"]
    assert a.at["4238900102", "box_action"] == "reassign" and a.at["4238900102", "flag_class"] == "WCB_1->WCA"
    assert a.at["4238900102", "class_status"].startswith("accepted")
    assert a.at["4238900104", "class_status"].startswith("into WCXY")
    assert a.at["4238900105", "box_action"] == "tvd_suspect" and not a.at["4238900105", "box_depth_witness"]
    assert a.at["4238900107", "class_status"].startswith("uncalibrated") and a.at["4238900107", "box_bench"] == "WCA"
    assert bool(a.at["4238900108", "excluded"]) and not bool(a.at["4238900101", "excluded"])
    ro = parts["rule_out"]
    assert list(ro["api10"]) == ["4238900103"] and ro["box_bench"].iloc[0] == "WCB_2"
    assert "4238900106" not in set(a.index) | set(ro["api10"])  # Bone Spring -> Wolfcamp never applied
    assert list(parts["not_rejudged"]["api10"]) == ["4238900004"]
    kinds = parts["drift"].groupby("kind")["api10"].apply(list).to_dict()
    assert kinds == {"retagged": ["4238900003"], "rule_now_out": ["3001500002"]}
    s = pr.summarize(parts)
    assert s["added"] == 6 and s["rule_out"] == 1 and s["uncalibrated_classes_new"] == ["WCA->AVA_1"]


def test_classify_refuses_a_base_well_outside_the_universe(base_dir: Path) -> None:
    base = pd.read_csv(base_dir / "wells_final_WCA.csv", dtype={"api10": str})
    with pytest.raises(ValueError, match="missing from the judged universe"):
        pr.classify(_live(), base, {"3001500001"}, set())


# ----------------------------------------------------------------------------
# byte identity
# ----------------------------------------------------------------------------


def test_refresh_appends_and_old_rows_stay_byte_identical(base_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "pool-2026-10-15"
    _, man = _run(base_dir, out, _live())
    old = (base_dir / "wells_final_WCA.csv").read_bytes()
    new = (out / "wells_final_WCA.csv").read_bytes()
    assert new.startswith(old) and len(new) > len(old)
    ident = man["identity"]["WCA"]
    assert ident["n_base_rows"] == 3 and ident["n_appended"] == 6 and ident["n_rows"] == 9
    assert (out / "wells_final_BS2_S.csv").read_bytes() == (base_dir / "wells_final_BS2_S.csv").read_bytes()
    # build reads the directory the same way it reads the gate-1 set; exclusions stay a load-time filter
    df = egr.load_final_sets(out, ("WCA",))
    assert len(df) == 9 and df["api10"].is_unique and df["first_production_date"].iloc[-1] == dt.date(2026, 9, 8)
    rep = pd.read_csv(out / "new_wells.csv", dtype={"api10": str})
    assert rep["refresh_class"].value_counts().to_dict() == {"added": 6, "rule_out": 1}


def test_refresh_refuses_a_non_empty_output(base_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "pool-2026-10-15"
    out.mkdir()
    (out / "x").write_text("x")
    with pytest.raises(FileExistsError):
        _run(base_dir, out, _live())


def test_identity_check_catches_an_edited_base_row() -> None:
    old = (HEADER + BASE_ROWS).encode()
    rows = pd.DataFrame([{c: "" for c in HEADER.strip().split(",")} | {"api10": "4238900101"}])
    new = pr.append_rows(old, rows)
    assert pr.verify_identity(old, new, ["4238900101"])["n_rows"] == 4
    with pytest.raises(AssertionError, match="byte-identical prefix"):
        pr.verify_identity(old, new.replace(b"OLD A 1H", b"OLD A 1X"), ["4238900101"])
    with pytest.raises(AssertionError, match="exactly the added wells"):
        pr.verify_identity(old, new, ["4238900999"])
    dup = pr.append_rows(old, rows.assign(api10="3001500001"))
    with pytest.raises(AssertionError, match="already in the base"):
        pr.verify_identity(old, dup, ["3001500001"])


def test_append_keeps_crlf_and_refuses_an_unterminated_base() -> None:
    old = (HEADER + BASE_ROWS).replace("\n", "\r\n").encode()
    rows = pd.DataFrame([{c: "" for c in HEADER.strip().split(",")} | {"api10": "4238900101"}])
    new = pr.append_rows(old, rows)
    assert new.startswith(old) and new.endswith(b"\r\n") and b"\r\r" not in new
    with pytest.raises(ValueError, match="line terminator"):
        pr.append_rows(old.rstrip(b"\r\n"), rows)
    with pytest.raises(ValueError, match="lack base columns"):
        pr.append_rows(old, rows.drop(columns=["cohort"]))


def test_hashes_do_not_depend_on_the_checkout_line_endings() -> None:
    lf = (HEADER + BASE_ROWS).encode()
    crlf = lf.replace(b"\n", b"\r\n")
    rows = pd.DataFrame([{c: "" for c in HEADER.strip().split(",")} | {"api10": "4238900101"}])
    a = pr.verify_identity(lf, pr.append_rows(lf, rows), ["4238900101"])
    b = pr.verify_identity(crlf, pr.append_rows(crlf, rows), ["4238900101"])
    assert (a["base_sha256"], a["new_sha256"], a["base_prefix_bytes"]) == (b["base_sha256"], b["new_sha256"], b["base_prefix_bytes"])


# ----------------------------------------------------------------------------
# all pools (step 13b, D126)
# ----------------------------------------------------------------------------

STEP15_HEADER = HEADER.rstrip("\n") + ",family_role\n"


def _pools(base_dir: Path, tmp_path: Path) -> dict[str, Path]:
    s15 = tmp_path / "step15-WCB-2026-10-16"
    s15.mkdir()
    (s15 / "wells_final_WCB_2.csv").write_bytes((STEP15_HEADER + "4238900201,OLD W2,WCB_2,WCB_2,keep,,False,False,True,2021-01-01,-103.6,31.6,member\n").encode())
    return {"WCA": base_dir / "wells_final_WCA.csv", "BS2_S": base_dir / "wells_final_BS2_S.csv", "WCB_2": s15 / "wells_final_WCB_2.csv"}


def test_all_pools_each_new_well_joins_the_pool_its_bench_names(base_dir: Path, tmp_path: Path) -> None:
    files = _pools(base_dir, tmp_path)
    live = pd.concat([_live(), apply_rule(pd.DataFrame([_well("4238900201", "WCB_2", "2021-01-01"), _well("4238900301", "WCD", "2026-09-09")]),
                                          verdicts=None)], ignore_index=True)
    bases = {p: pd.read_csv(f, dtype={"api10": str}) for p, f in files.items()}
    seen, _ = pr.reconstruct_seen(base_dir, live)
    seen_ids = set(seen["api10"]) | {"4238900201"}  # the step-15 base well counts as judged
    parts = pr.classify_pools(live, bases, seen_ids, {"4238900108"})
    added = {p: set(x["added"]["api10"]) for p, x in parts["pools"].items()}
    assert "4238900103" in added["WCB_2"] and "4238900103" not in added["WCA"]  # ruled out of WCA, INTO WCB_2
    assert "4238900106" in added["BS2_S"] and "4238900101" in added["WCA"]
    assert not set.intersection(*added.values())  # one pool each
    assert parts["new_unpooled"] == {"WCD": 1}  # WCD is no pool: counted only


def test_all_pools_write_one_directory_byte_prefix_per_file(base_dir: Path, tmp_path: Path) -> None:
    files = _pools(base_dir, tmp_path)
    live = _live()
    bases = {p: pd.read_csv(f, dtype={"api10": str}) for p, f in files.items()}
    seen, seen_meta = pr.reconstruct_seen(base_dir, live)
    parts = pr.classify_pools(live, bases, set(seen["api10"]) | {"4238900201"}, {"4238900108"})
    out = tmp_path / "pool-2026-10-26"
    man = pr.write_refresh_pools(out, files, parts, pr.next_universe(seen, live, out.name), {"label": out.name, "seen": seen_meta})
    for p, f in files.items():
        assert (out / pr.final_name(p)).read_bytes().startswith(f.read_bytes()), p
        assert man["identity"][p]["n_appended"] == len(parts["pools"][p]["added"])
    tail = (out / "wells_final_WCB_2.csv").read_text().splitlines()[2:]
    assert tail and all(line.endswith(",member") for line in tail)  # step-15 files get family_role for new rows
    assert set(pd.read_csv(out / pr.NEW_WELLS, dtype={"api10": str})["pool"]) <= set(files)
    with pytest.raises(FileExistsError):
        pr.write_refresh_pools(out, files, parts, seen, {})


def test_wells_dir_prefers_an_all_pool_directory(tmp_path: Path) -> None:
    from box import production_run9 as p9r

    wca_only = tmp_path / "pool-2026-10-15"
    wca_only.mkdir()
    (wca_only / "wells_final_WCA.csv").write_text("x\n")
    assert p9r.wells_dir("WCA", wca_only) == wca_only
    assert p9r.wells_dir("WCB_1", wca_only) == p9r._WELLS["WCB_1"]  # run 19's form: step-15 sets stay
    (wca_only / "wells_final_WCB_1.csv").write_text("x\n")
    assert p9r.wells_dir("WCB_1", wca_only) == wca_only  # a D126 refresh directory feeds every group
