"""BOX sticks identity (phase 4): ids carry between generation runs by co-extent overlap inside a DSU x bench. DB-free."""
from __future__ import annotations

from box.sticks import identity as idn

M = 1.0 / idn.FT_PER_M      # one foot in metres


def stick(key: str, xs_ft: tuple[float, ...], bench: str = "WCA_1", pad: int = 1, y0_ft: float = 0.0, y1_ft: float = 10000.0,
          slot: int | None = None) -> idn.Stick:
    """N-S legs at the given cross-section positions (ft)."""
    return idn.Stick(key, pad, bench, tuple(((x * M, y0_ft * M), (x * M, y1_ft * M)) for x in xs_ft), slot)


def test_seed_numbers_each_dsu_bench_from_one() -> None:
    s = [stick("a", (0,)), stick("b", (880,)), stick("c", (0,), bench="WCB_1"), stick("d", (0,), pad=2)]
    assert idn.seed(s) == {"a": 1, "b": 2, "c": 1, "d": 1}


def test_unchanged_run_carries_every_id() -> None:
    prev = [stick("p1", (0,), slot=1), stick("p2", (880,), slot=2)]
    x = idn.crosswalk(prev, [stick("n1", (0,)), stick("n2", (880,))])
    assert {k: v[:2] for k, v in x["carried"].items()} == {"n1": ("p1", 1), "n2": ("p2", 2)}
    assert not x["new"] and not x["stopped"]


def test_a_row_added_at_the_edge_keeps_the_others_and_takes_the_next_number() -> None:
    prev = [stick(f"p{i}", (i * 580.0,), slot=i + 1) for i in range(3)]
    new = [stick(f"n{i}", (i * 578.0,)) for i in range(4)]            # grid tightened 2 ft, one more row fits
    x = idn.crosswalk(prev, new)
    assert [x["carried"][f"n{i}"][1] for i in range(3)] == [1, 2, 3]
    assert x["new"] == {"n3": 4} and not x["stopped"]


def test_a_removed_row_does_not_renumber_the_rest() -> None:
    prev = [stick(f"p{i}", (i * 880.0,), slot=i + 1) for i in range(4)]
    new = [stick("a", (0.0,)), stick("b", (1760.0,)), stick("c", (2640.0,))]    # the second row was drilled
    x = idn.crosswalk(prev, new)
    assert {k: v[1] for k, v in x["carried"].items()} == {"a": 1, "b": 3, "c": 4}
    assert x["stopped"] == ["p1"]


def test_slot_numbers_are_never_reused() -> None:
    prev = [stick("p1", (0,), slot=1), stick("p3", (1760,), slot=3)]             # slot 2 stopped in an earlier run
    x = idn.crosswalk(prev, [stick("a", (0,)), stick("b", (880,)), stick("c", (1760,))])
    assert x["new"] == {"b": 4}


def test_outside_the_corridor_is_a_new_location() -> None:
    prev = [stick("p1", (0,), slot=1)]
    assert idn.crosswalk(prev, [stick("n", (219.0,))])["carried"]["n"][:2] == ("p1", 1)
    x = idn.crosswalk(prev, [stick("n", (221.0,))])
    assert x["new"] == {"n": 2} and x["stopped"] == ["p1"]


def test_one_to_one_takes_the_nearer_row() -> None:
    prev = [stick("p1", (0,), slot=1)]
    x = idn.crosswalk(prev, [stick("far", (-200.0,)), stick("near", (150.0,))])
    assert x["carried"]["near"][:2] == ("p1", 1) and x["new"] == {"far": 2}


def test_bench_and_dsu_are_part_of_identity() -> None:
    prev = [stick("p1", (0,), bench="WCA_2", slot=1)]
    x = idn.crosswalk(prev, [stick("n", (0,), bench="WCA_1"), stick("m", (0,), bench="WCA_2", pad=2)])
    assert not x["carried"] and x["stopped"] == ["p1"] and x["new"] == {"n": 1, "m": 1}


def test_short_overlap_does_not_carry() -> None:
    prev = [stick("p1", (0,), slot=1)]                                            # 10,000 ft
    assert not idn.crosswalk(prev, [stick("n", (0,), y0_ft=6000.0, y1_ft=16000.0)])["carried"]      # 40 % shared
    assert idn.crosswalk(prev, [stick("n", (0,), y0_ft=4000.0, y1_ft=14000.0)])["carried"]          # 60 % shared


def test_uturn_carries_on_both_legs_and_not_on_a_repaired_half() -> None:
    prev = [stick("u1", (0, 1200), slot=1), stick("u2", (2400, 3600), slot=2)]
    same = idn.crosswalk(prev, [stick("a", (0, 1200)), stick("b", (2400, 3600))])
    assert {k: v[:2] for k, v in same["carried"].items()} == {"a": ("u1", 1), "b": ("u2", 2)}
    # legs re-paired one row over: each new U-turn shares exactly one leg (50 %) with a previous one; it carries, 1:1
    x = idn.crosswalk(prev, [stick("c", (1200, 2400))])
    assert len(x["carried"]) == 1 and len(x["stopped"]) == 1
    assert idn.share(prev[0], stick("c", (1200, 2400)))[0] == 0.5


def test_a_new_stick_starts_above_every_number_ever_issued_not_only_the_previous_sets() -> None:
    # the previous set holds slot 1 only; an older, stopped location of this DSU x bench still holds slot 2 (found 2026-11-20)
    prev = [stick("p1", (0,), slot=1)]
    new = [stick("n1", (0,)), stick("n2", (880,)), stick("n3", (1760,)), stick("o1", (0,), bench="WCB_1")]
    x = idn.crosswalk(prev, new, used={(1, "WCA_1"): 2})
    assert x["carried"]["n1"][:2] == ("p1", 1) and x["new"] == {"n2": 3, "n3": 4, "o1": 1}
    assert idn.crosswalk(prev, new)["new"] == {"n2": 2, "n3": 3, "o1": 1}          # without the history: the old behaviour
    assert idn.crosswalk([], [stick("n", (0,))], used={(1, "WCA_1"): 7})["new"] == {"n": 8}
