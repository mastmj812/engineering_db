"""The proposed "two levels nearby" detector for thickness-carried depths (measurement only, 2026-11-18)."""

import numpy as np

from scripts.box_sticks_second_landing import SEP_FT, SHARE, levels

RNG = np.random.default_rng(0)


def _flag(rel: np.ndarray) -> bool:
    return levels(rel, np.ones(len(rel)))[f"share_{int(SEP_FT)}"] >= SHARE


def test_two_levels_are_found_with_their_offset_and_share():
    rel = np.r_[RNG.normal(-500, 25, 30), RNG.normal(-340, 25, 15)]
    lv = levels(rel, np.ones(len(rel)))
    assert _flag(rel) and abs(lv["off_150"] - 160) <= 25 and abs(lv["share_150"] - 1 / 3) < 0.05


def test_one_level_and_a_broad_spread_are_not_flagged():
    assert not _flag(RNG.normal(0, 60, 60))
    assert not _flag(RNG.uniform(-200, 200, 60))


def test_a_second_level_closer_than_the_separation_or_too_thin_is_not_flagged():
    assert not _flag(np.r_[RNG.normal(0, 15, 30), RNG.normal(110, 15, 15)])     # 110 ft apart
    assert not _flag(np.r_[RNG.normal(0, 20, 40), RNG.normal(300, 20, 2)])      # two wells
    assert not _flag(np.r_[RNG.normal(0, 20, 40), RNG.normal(300, 20, 5)])      # 11 % of the weight
