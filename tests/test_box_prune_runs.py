"""D104 selection: keep the record + every priced run; prune the rest."""

from scripts.box_prune_runs import select_prune


def test_select_prune_keeps_record_and_priced_runs():
    runs = [(4, False, 6, 1, 1, 0), (6, False, 7, 1, 1, 12), (7, False, 8, 1, 1, 0), (8, True, None, 1, 1, 0)]
    assert select_prune(runs) == [4, 7]


def test_d123_include_priced_prunes_every_non_record_run():
    runs = [(4, False, 6, 10, 100, 0), (6, False, 7, 10, 100, 12), (7, True, None, 10, 100, 0), (8, False, None, 10, 100, 5)]
    assert select_prune(runs) == [4]
    assert select_prune(runs, include_priced=True) == [4, 6, 8]  # the record is never pruned
