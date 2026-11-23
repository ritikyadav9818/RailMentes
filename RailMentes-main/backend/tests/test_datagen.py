"""Tests for the synthetic data generator."""

import csv
import math
import sqlite3
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.ml import datagen
from app.ml import features as feature_module
from app.ml.datagen import (
    DaySpec,
    generate_dataset,
    generate_day,
    plan_days,
    sample_rows,
    write_csv,
    write_sqlite,
)
from app.ml.features import ALL_COLUMNS, FEATURE_COLUMNS, OPTIONAL_FEATURES, REQUIRED_FEATURES, TARGET_COLUMNS
from app.models.corridor import build_corridor
from app.models.train import TrainCategory
from app.simulation.disruptions import Intensity
from app.simulation.realism import MAX_EXTRA_MIN, make_dwell_extra, mean_extra_minutes
from app.simulation.scenario import Scenario


@pytest.fixture(scope="module")
def three_days() -> list[list[dict]]:
    return list(generate_dataset(plan_days(3, seed=5)))


def flat(days: list[list[dict]]) -> list[dict]:
    return [row for day in days for row in day]


# ---- planning the days ---------------------------------------------------------------------------------
def test_plan_days_is_reproducible_and_consecutive() -> None:
    first, second = plan_days(30, seed=1), plan_days(30, seed=1)
    assert first == second and first != plan_days(30, seed=2)
    assert [s.day for s in first] == [date(2025, 10, 1) + timedelta(days=i) for i in range(30)]
    assert len({s.seed for s in first}) == 30


def test_intensity_mix_is_mostly_calm() -> None:
    mix = Counter(s.intensity for s in plan_days(2000, seed=3))
    share = {k: v / 2000 for k, v in mix.items()}
    assert share[Intensity.NONE] + share[Intensity.LOW] > 0.6
    assert 0.12 < share[Intensity.MEDIUM] < 0.28 and 0.05 < share[Intensity.HIGH] < 0.15


# ---- determinism ---------------------------------------------------------------------------------------------
def test_same_seed_gives_identical_dataset(three_days: list[list[dict]]) -> None:
    assert list(generate_dataset(plan_days(3, seed=5))) == three_days


def test_different_seed_gives_different_dataset(three_days: list[list[dict]]) -> None:
    assert list(generate_dataset(plan_days(3, seed=6))) != three_days


def test_parallel_workers_give_the_same_dataset(three_days: list[list[dict]]) -> None:
    assert list(generate_dataset(plan_days(3, seed=5), workers=2)) == three_days


# ---- row content --------------------------------------------------------------------------------------------------
def test_rows_have_exactly_the_declared_columns(three_days: list[list[dict]]) -> None:
    rows = flat(three_days)
    assert len(rows) > 400
    assert all(list(row) == list(ALL_COLUMNS) for row in rows)
    assert list(FEATURE_COLUMNS) == [c for c in ALL_COLUMNS if c in FEATURE_COLUMNS]


def test_required_columns_have_no_missing_values(three_days: list[list[dict]]) -> None:
    for row in flat(three_days):
        for column in (*datagen.ALL_COLUMNS[:8], *REQUIRED_FEATURES, "target_delay_1"):
            value = row[column]
            assert value is not None, column
            assert not (isinstance(value, float) and not math.isfinite(value)), column


def test_optional_columns_are_missing_only_near_the_end_of_a_route(three_days: list[list[dict]]) -> None:
    for row in flat(three_days):
        for k in (2, 3):
            ahead_missing = row["stations_ahead"] < k
            assert (row[f"target_delay_{k}"] is None) == ahead_missing
            assert (row[f"sched_to_s{k}"] is None) == ahead_missing
            assert (row[f"dist_to_s{k}_km"] is None) == ahead_missing
    assert set(OPTIONAL_FEATURES) == {"sched_to_s2", "sched_to_s3", "dist_to_s2_km", "dist_to_s3_km"}


def test_targets_are_sane(three_days: list[list[dict]]) -> None:
    rows = flat(three_days)
    for row in rows:
        for column in TARGET_COLUMNS:
            if row[column] is not None:
                assert isinstance(row[column], int) and -40 <= row[column] <= 400
    first = [r["target_delay_1"] for r in rows]
    assert min(first) < 0 < max(first)  # some trains run early, some late
    close = sum(abs(r["target_delay_1"] - r["delay_now"]) <= 15 for r in rows) / len(rows)
    assert close > 0.85  # the next delay is usually near the current one


def test_feature_values_are_in_range(three_days: list[list[dict]]) -> None:
    for row in flat(three_days):
        assert row["train_category"] in {c.value for c in TrainCategory}
        assert row["priority"] in (1, 2, 3, 4) and 0 <= row["hour"] <= 23 and 0 <= row["day_of_week"] <= 6
        assert row["dist_to_s1_km"] > 0 and row["speed_kmph"] >= 0 and 0 <= row["min_speed_factor"] <= 1
        assert row["month"] in (10, 11, 12) and row["trains_in_next_blocks"] >= 0


def test_one_row_per_departure_event() -> None:
    spec = plan_days(1, seed=9)[0]
    rows = generate_day(spec)
    engine = Scenario(seed=spec.seed, intensity=spec.intensity, start_date=spec.day, realism=True).build(
        build_corridor()
    )
    expected = sum(len(plan.stops) - 1 for plan in engine.plans.values())
    assert len(rows) == expected
    assert len({(r["train_id"], r["station_idx"]) for r in rows}) == expected


# ---- training path == live path ---------------------------------------------------------------------------------------
def test_generator_uses_the_shared_feature_builder(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    original = feature_module.build_features

    def spy(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(feature_module, "build_features", spy)
    rows = generate_day(plan_days(1, seed=2)[0])
    assert len(calls) == len(rows) > 0


def test_a_generated_row_equals_the_live_features_at_that_moment() -> None:
    spec = plan_days(1, seed=4)[0]
    rows = generate_day(spec)
    network = build_corridor()
    for row in (rows[5], rows[len(rows) // 2], rows[-3]):
        engine = Scenario(seed=spec.seed, intensity=spec.intensity, start_date=spec.day, realism=True).build(
            network
        )
        while engine.tick < row["tick"]:
            engine.step()
        snapshot = engine.snapshot()
        train = next(t for t in snapshot.trains if t.id == row["train_id"])
        live = feature_module.build_features(snapshot, train, network, engine.last_arrival_delay(train.id))
        assert live == {c: row[c] for c in FEATURE_COLUMNS}


# ---- realism switch -------------------------------------------------------------------------------------------------------
def test_realism_changes_the_run_and_is_off_by_default() -> None:
    network = build_corridor()
    base = Scenario(seed=3, start_date=date(2025, 11, 3))
    assert base.realism is False
    plain, noisy = (
        base.build(network),
        Scenario(seed=3, start_date=date(2025, 11, 3), realism=True).build(network),
    )
    plain.run_until_done()
    noisy.run_until_done()
    assert plain.arrival_log != noisy.arrival_log


def test_dwell_extra_is_larger_at_rush_hour_and_on_busy_days() -> None:
    monday_peak, monday_night = datetime(2025, 11, 3, 8), datetime(2025, 11, 3, 13)
    sunday_noon, tuesday_noon = datetime(2025, 11, 9, 13), datetime(2025, 11, 4, 13)
    assert mean_extra_minutes(TrainCategory.PASSENGER, monday_peak) > mean_extra_minutes(
        TrainCategory.PASSENGER, monday_night
    )
    assert mean_extra_minutes(TrainCategory.EXPRESS, sunday_noon) > mean_extra_minutes(
        TrainCategory.EXPRESS, tuesday_noon
    )
    assert mean_extra_minutes(TrainCategory.FREIGHT, monday_peak) == 0

    draw = make_dwell_extra(1, datetime(2025, 11, 3))
    peak = [draw(TrainCategory.PASSENGER, "KLP", 8 * 60) for _ in range(3000)]
    quiet = [draw(TrainCategory.PASSENGER, "KLP", 13 * 60) for _ in range(3000)]
    assert sum(peak) > sum(quiet) and max(peak) <= MAX_EXTRA_MIN and min(peak) >= 0
    assert {draw(TrainCategory.FREIGHT, "KLP", 600) for _ in range(50)} == {0}
    again = make_dwell_extra(1, datetime(2025, 11, 3))
    assert [again(TrainCategory.PASSENGER, "KLP", 480) for _ in range(20)] == peak[:20]


def test_scenario_start_date_sets_calendar_and_fog_season() -> None:
    network = build_corridor()
    engine = Scenario(seed=1, start_date=date(2025, 12, 21), month=7).build(
        network
    )  # a Sunday; date wins over month
    assert engine.snapshot().sim_time == datetime(2025, 12, 21)
    assert engine.snapshot().sim_time.weekday() == 6


# ---- end to end: 3 days to disk ----------------------------------------------------------------------------------------------
def test_three_days_to_csv_and_sqlite(tmp_path: Path, three_days: list[list[dict]]) -> None:
    csv_path = tmp_path / "runs.csv"
    count = write_csv(iter(three_days), csv_path)
    with csv_path.open(encoding="utf-8") as handle:
        table = list(csv.DictReader(handle))
    assert count == len(table) == len(flat(three_days))
    assert list(table[0]) == list(ALL_COLUMNS)
    assert table[0]["train_category"] in {c.value for c in TrainCategory}

    db_path = tmp_path / "runs.sqlite"
    assert write_sqlite(flat(three_days), db_path) == count
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == count
        assert db.execute("SELECT COUNT(DISTINCT scenario_id) FROM runs").fetchone()[0] == 3
        assert db.execute(
            "SELECT typeof(target_delay_1), typeof(delay_now) FROM runs LIMIT 1"
        ).fetchone() == ("integer", "real")


def test_sample_rows_picks_evenly() -> None:
    rows = [{"i": i} for i in range(1000)]
    picked = sample_rows(rows, 100)
    assert len(picked) == 100 and picked[0]["i"] == 0 and picked[-1]["i"] > 900
    assert sample_rows(rows[:10], 100) == rows[:10]


def test_dayspec_scenario_id_is_unique_per_day() -> None:
    specs = plan_days(50, seed=8)
    assert len({s.scenario_id for s in specs}) == 50
    assert isinstance(specs[0], DaySpec)
