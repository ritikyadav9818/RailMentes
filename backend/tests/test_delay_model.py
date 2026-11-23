"""Tests for the delay model: split, baselines, training, prediction, fallback, explanations, API."""

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.api.runner import SimulationRunner
from app.config import Settings
from app.ml.baselines import fit_mean, mean_predict, persistence_predict
from app.ml.datagen import generate_dataset, plan_days
from app.ml.dataset import Split, feature_matrix, rows_to_frame, split_by_day, target_for, usable_rows
from app.ml.evaluate import collect_predictions, error_table, late_quality
from app.ml.features import FEATURE_COLUMNS
from app.ml.model import DelayModel, ModelConfig, train_model
from app.ml.predict import DelayPredictor, load_predictor
from app.models.schemas import StateSnapshot
from app.simulation.disruptions import Intensity

FAST = ModelConfig(max_rounds=80, early_stopping_rounds=10, seed=7)
TICKS_BEFORE_CHECK = 300  # several trains are on the line by then


@pytest.fixture(scope="module")
def data() -> pd.DataFrame:
    rows = [row for day in generate_dataset(plan_days(24, seed=11)) for row in day]
    return rows_to_frame(rows)


@pytest.fixture(scope="module")
def split(data: pd.DataFrame) -> Split:
    return split_by_day(data)


@pytest.fixture(scope="module")
def model(split: Split) -> DelayModel:
    return train_model(split, FAST)


@pytest.fixture(scope="module")
def model_file(model: DelayModel, tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("models") / "delay_model.json"
    model.save(path)
    return path


# ---- the split -----------------------------------------------------------------------------------------
def test_split_has_no_day_overlap_and_is_in_time_order(split: Split, data: pd.DataFrame) -> None:
    train, validation, test = (set(p["day"]) for p in (split.train, split.validation, split.test))
    assert not (train & validation) and not (train & test) and not (validation & test)
    assert max(train) < min(validation) and max(validation) < min(test)
    assert len(split.train) + len(split.validation) + len(split.test) == len(data)


def test_split_default_fractions_are_roughly_70_15_15(split: Split) -> None:
    days = {name: info["days"] for name, info in split.describe().items()}
    assert days == {"train": 16, "validation": 3, "test": 5}


def test_split_needs_enough_days(data: pd.DataFrame) -> None:
    with pytest.raises(ValueError):
        split_by_day(data[data["day"] == data["day"].iloc[0]])
    with pytest.raises(ValueError):
        split_by_day(data, train_fraction=0.9, validation_fraction=0.2)


def test_feature_matrix_has_fixed_numeric_columns(split: Split) -> None:
    matrix = feature_matrix(split.test)
    assert list(matrix.columns) == list(FEATURE_COLUMNS)
    assert all(dtype.kind == "f" for dtype in matrix.dtypes)
    assert set(matrix["train_category"].unique()) <= {0.0, 1.0, 2.0, 3.0}


# ---- baselines and the model ---------------------------------------------------------------------------
def test_persistence_is_the_current_delay(split: Split) -> None:
    assert np.array_equal(persistence_predict(split.test), split.test["delay_now"].to_numpy())


def test_model_beats_the_mean_baseline(split: Split, model: DelayModel) -> None:
    means = fit_mean(split.train)
    for horizon in (1, 2, 3):
        rows = usable_rows(split.test, horizon)
        actual = target_for(rows, horizon).to_numpy()
        model_mae = np.abs(model.predict(rows, horizon) - actual).mean()
        mean_mae = np.abs(mean_predict(means, rows, horizon) - actual).mean()
        assert model_mae < mean_mae / 2


def test_training_is_deterministic_with_a_fixed_seed(split: Split, model: DelayModel) -> None:
    again = train_model(split, FAST)
    for horizon in (1, 2, 3):
        assert np.array_equal(model.predict(split.test, horizon), again.predict(split.test, horizon))
    assert model.info["best_iterations"] == again.info["best_iterations"]


def test_save_and_load_give_the_same_predictions(split: Split, model: DelayModel, model_file: Path) -> None:
    loaded = DelayModel.load(model_file)
    for horizon in (1, 2, 3):
        assert np.allclose(model.predict(split.test, horizon), loaded.predict(split.test, horizon))


def test_loading_a_model_for_other_features_is_refused(model_file: Path, tmp_path: Path) -> None:
    text = model_file.read_text(encoding="utf-8").replace('"speed_kmph"', '"speed_mph"', 1)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        DelayModel.load(wrong)


# ---- evaluation ----------------------------------------------------------------------------------------
def test_error_table_and_late_quality_on_a_tiny_example() -> None:
    predictions = pd.DataFrame(
        {
            "horizon": 1,
            "model": ["lightgbm"] * 4,
            "actual": [0.0, 10.0, 8.0, 2.0],
            "predicted": [1.0, 12.0, 4.0, 9.0],  # said late: rows 2 and 4; really late: rows 2 and 3
        }
    )
    errors = error_table(predictions).iloc[0]
    assert errors["n"] == 4 and errors["mae"] == pytest.approx((1 + 2 + 4 + 7) / 4)
    quality = late_quality(predictions).iloc[0]
    assert quality["precision"] == pytest.approx(0.5) and quality["recall"] == pytest.approx(0.5)


def test_collect_predictions_has_every_model_and_horizon(split: Split, model: DelayModel) -> None:
    predictors = {"persistence": lambda rows, k: persistence_predict(rows), "lightgbm": model.predict}
    table = collect_predictions(split.test, predictors)
    assert set(table["model"]) == set(predictors) and set(table["horizon"]) == {1, 2, 3}
    assert table[["actual", "predicted"]].notna().all().all()
    assert set(table["disruption"]) <= {"disruption ahead", "no disruption"}


# ---- live prediction -----------------------------------------------------------------------------------
def runner_with(predictor: DelayPredictor, intensity: Intensity = Intensity.HIGH) -> SimulationRunner:
    runner = SimulationRunner(seed=3, intensity=intensity, month=1, predictor=predictor)
    for _ in range(TICKS_BEFORE_CHECK):
        runner.engine.step()
    return runner


def test_prediction_for_a_live_snapshot_is_valid(model_file: Path) -> None:
    predictor = load_predictor(model_file)
    assert predictor.source == "lightgbm" and predictor.reason == ""
    runner = runner_with(predictor)
    snapshot = runner.snapshot()
    StateSnapshot.model_validate(snapshot.model_dump())  # still a valid contract object
    plain = runner._raw_snapshot()
    assert any(t.next_stations and t.position for t in snapshot.trains)
    changed = 0
    for train, before in zip(snapshot.trains, plain.trains, strict=True):
        assert (train.id, train.delay_min, train.status) == (before.id, before.delay_min, before.status)
        assert [s.station for s in train.next_stations] == [s.station for s in before.next_stations]
        for stop, old in zip(train.next_stations, before.next_stations, strict=True):
            assert isinstance(stop.predicted_min, int) and stop.predicted_min >= snapshot.tick
            assert stop.scheduled_min == old.scheduled_min
            changed += stop.predicted_min != old.predicted_min
    assert changed > 0  # the model really changes some predicted times


def test_predict_delays_returns_three_numbers_per_train(model_file: Path) -> None:
    runner = runner_with(load_predictor(model_file))
    features = runner.live_features()
    delays = runner.predictor.predict_delays(features)
    assert features and set(delays) == set(features)
    assert all(len(v) == 3 and all(np.isfinite(v)) for v in delays.values())


# ---- fallback ------------------------------------------------------------------------------------------
def test_missing_model_falls_back_to_persistence_and_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING"):
        predictor = load_predictor(tmp_path / "nope.json")
    assert predictor.source == "persistence" and "not found" in predictor.reason
    assert "persistence" in caplog.text
    runner = runner_with(predictor)
    assert runner.snapshot().trains == runner._raw_snapshot().trains  # the fallback changes no times
    features = runner.live_features()
    delays = predictor.predict_delays(features)
    for train_id, row in features.items():
        assert delays[train_id] == [row["delay_now"]] * 3


def test_switched_off_and_broken_files_also_fall_back(model_file: Path, tmp_path: Path) -> None:
    assert load_predictor(model_file, enabled=False).source == "persistence"
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    predictor = load_predictor(broken)
    assert predictor.source == "persistence" and "could not load" in predictor.reason


def test_explaining_without_a_model_raises() -> None:
    with pytest.raises(RuntimeError):
        DelayPredictor().explain({}, 1)


# ---- explanations --------------------------------------------------------------------------------------
def first_on_line(runner: SimulationRunner) -> str:
    return next(iter(runner.live_features()))


def test_explanation_has_sensible_fields_and_adds_up(model_file: Path) -> None:
    runner = runner_with(load_predictor(model_file))
    train_id = first_on_line(runner)
    for horizon in (1, 2):
        result = runner.explain_train(train_id, horizon=horizon, top_n=4)
        assert result.train_id == train_id and result.horizon == horizon and result.model_source == "lightgbm"
        assert 1 <= len(result.factors) <= 4
        assert all(f.feature in FEATURE_COLUMNS for f in result.factors)
        effects = [abs(f.effect_min) for f in result.factors]
        assert effects == sorted(effects, reverse=True)
        total = result.current_delay_min + result.expected_change_min + result.other_effect_min
        total += sum(f.effect_min for f in result.factors)
        assert total == pytest.approx(result.predicted_delay_min, abs=0.1)
        row = runner.live_features()[train_id]
        expected = runner.predictor.predict_delays({train_id: row})[train_id][horizon - 1]
        assert result.predicted_delay_min == pytest.approx(expected, abs=0.1)  # SHAP agrees with the model


def test_explanation_errors(model_file: Path) -> None:
    runner = runner_with(load_predictor(model_file))
    with pytest.raises(LookupError):
        runner.explain_train("NOPE")
    not_started = next(t.id for t in runner.snapshot().trains if t.position is None)
    with pytest.raises(ValueError):
        runner.explain_train(not_started)
    with pytest.raises(RuntimeError):
        runner_with(DelayPredictor()).explain_train("anything")


# ---- API -----------------------------------------------------------------------------------------------
@pytest.fixture
def ml_client(model_file: Path) -> Iterator[TestClient]:
    settings = Settings(use_ml_model=True, model_path=model_file)
    with TestClient(create_app(settings)) as client:
        yield client


def step_runner(client: TestClient, ticks: int = TICKS_BEFORE_CHECK) -> None:
    client.post("/scenario/reset", json={"intensity": "high", "month": 1})
    for _ in range(ticks):
        client.app.state.runner.engine.step()


def test_explanation_endpoint(ml_client: TestClient) -> None:
    step_runner(ml_client)
    train_id = first_on_line(ml_client.app.state.runner)
    response = ml_client.get(f"/trains/{train_id}/explanation", params={"horizon": 2, "top": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["train_id"] == train_id and body["horizon"] == 2 and len(body["factors"]) <= 3
    assert set(body["factors"][0]) == {"feature", "value", "effect_min"}
    assert ml_client.get(f"/trains/{train_id}/explanation", params={"horizon": 4}).status_code == 422
    assert ml_client.get("/trains/NOPE/explanation").status_code == 404
    assert ml_client.get("/state").json()["trains"]  # the state endpoint keeps working with the model on


def test_explanation_endpoint_without_model_is_503() -> None:
    with TestClient(create_app(Settings())) as client:
        assert client.get("/trains/X1/explanation").status_code == 503


def test_state_shape_is_the_same_with_and_without_the_model(model_file: Path) -> None:
    with (
        TestClient(create_app(Settings())) as plain,
        TestClient(create_app(Settings(use_ml_model=True, model_path=model_file))) as with_model,
    ):
        for client in (plain, with_model):
            step_runner(client, 100)
        a, b = plain.get("/state").json(), with_model.get("/state").json()
        assert a.keys() == b.keys()
        assert [t.keys() for t in a["trains"]] == [t.keys() for t in b["trains"]]
