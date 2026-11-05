"""D104 selection: keep the record + every priced run; prune the rest."""

import pytest

from scripts.box_prune_runs import select_named, select_prune


def test_select_prune_keeps_record_and_priced_runs():
    runs = [(4, False, 6, 1, 1, 0), (6, False, 7, 1, 1, 12), (7, False, 8, 1, 1, 0), (8, True, None, 1, 1, 0)]
    assert select_prune(runs) == [4, 7]


def test_d123_include_priced_prunes_every_non_record_run():
    runs = [(4, False, 6, 10, 100, 0), (6, False, 7, 10, 100, 12), (7, True, None, 10, 100, 0), (8, False, None, 10, 100, 5)]
    assert select_prune(runs) == [4]
    assert select_prune(runs, include_priced=True) == [4, 6, 8]  # the record is never pruned


def test_run_names_exactly_the_runs_it_prunes():
    # step 23c: run 27 superseded by 32 while 25 (the source) and 32 stay; the Midland holds no record yet
    runs = [(19, True, None, 1, 1, 0, "delaware"), (25, False, None, 1, 1, 0, "delaware"), (27, False, None, 1, 1, 0, "delaware"),
            (28, False, None, 1, 1, 0, "midland"), (32, False, None, 1, 1, 0, "delaware")]
    assert select_named(runs, [27]) == [27]
    assert select_prune(runs, basin="delaware") == [25, 27, 32]  # what the basin-wide prune would have taken


def test_run_refuses_a_record_a_priced_or_a_missing_run():
    runs = [(19, True, None, 1, 1, 0, "delaware"), (27, False, None, 1, 1, 0, "delaware"), (31, False, None, 1, 1, 9, "delaware")]
    for ids in ([19], [31], [99], [27, 19]):
        with pytest.raises(SystemExit):
            select_named(runs, ids)
    assert select_named(runs, [31], include_priced=True) == [31]
