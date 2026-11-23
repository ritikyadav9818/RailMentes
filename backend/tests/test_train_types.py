"""Tests for train categories and operating profiles."""

import pytest

from app.models.train import TRAIN_TYPES, TrainCategory, get_train_type, run_minutes, stops_at

ORDER = [TrainCategory.PREMIUM, TrainCategory.EXPRESS, TrainCategory.PASSENGER, TrainCategory.FREIGHT]


def test_all_four_categories_defined() -> None:
    assert set(TRAIN_TYPES) == set(ORDER)


def test_priority_order() -> None:
    priorities = [get_train_type(c).priority for c in ORDER]
    assert priorities == sorted(priorities, reverse=True)
    assert len(set(priorities)) == 4


def test_speed_order() -> None:
    speeds = [get_train_type(c).max_speed_kmph for c in ORDER]
    assert speeds == sorted(speeds, reverse=True)


def test_run_minutes_at_top_speed() -> None:
    assert run_minutes(130, 130, get_train_type(TrainCategory.PREMIUM)) == pytest.approx(60.0)


def test_run_minutes_limited_by_section() -> None:
    premium = get_train_type(TrainCategory.PREMIUM)
    assert run_minutes(100, 100, premium) == pytest.approx(60.0)


def test_run_minutes_limited_by_train() -> None:
    freight = get_train_type(TrainCategory.FREIGHT)
    assert run_minutes(60, 130, freight) == pytest.approx(60.0)


@pytest.mark.parametrize("length,limit", [(0, 100), (-5, 100), (10, 0)])
def test_run_minutes_rejects_bad_input(length: float, limit: float) -> None:
    with pytest.raises(ValueError):
        run_minutes(length, limit, get_train_type(TrainCategory.EXPRESS))


def test_stopping_patterns() -> None:
    premium = get_train_type(TrainCategory.PREMIUM)
    passenger = get_train_type(TrainCategory.PASSENGER)
    freight = get_train_type(TrainCategory.FREIGHT)
    assert stops_at(premium, 1) and not stops_at(premium, 3)
    assert stops_at(passenger, 3)
    assert not any(stops_at(freight, size) for size in (1, 2, 3))
