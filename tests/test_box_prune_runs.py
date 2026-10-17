"""D104 selection: keep the record + every priced run; prune the rest."""

from scripts.box_prune_runs import select_prune


def test_select_prune_keeps_record_and_priced_runs():
    runs = [(4, False, 6, 1, 1, 0), (6, False, 7, 1, 1, 12), (7, False, 8, 1, 1, 0), (8, True, None, 1, 1, 0)]
    assert select_prune(runs) == [4, 7]
