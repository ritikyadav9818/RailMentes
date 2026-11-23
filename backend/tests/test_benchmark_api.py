"""Tests for GET /benchmark/summary."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.benchmark import BenchmarkSummary
from app.api.main import create_app
from app.config import DEFAULT_RESULTS_DIR, Settings

HEADER = (
    "intensity,strategy,avg_delay_min,punctuality_pct,throughput_per_hour,priority_weighted_delay,"
    "actions_applied,blocking_events,conflicts_detected,avg_delay_min_std,punctuality_pct_std,"
    "throughput_per_hour_std,priority_weighted_delay_std,actions_applied_std,blocking_events_std,"
    "conflicts_detected_std,runs"
)
ROW = "low,cpsat,7.99,67.4,0.93,496.85,2.3,8.9,11.35,2.56,6.52,0.01,179.6,0.98,1.7,1.7,20"


def client_for(results_dir: Path) -> TestClient:
    return TestClient(create_app(Settings(results_dir=results_dir)))


@pytest.fixture
def real_client() -> Iterator[TestClient]:
    with client_for(DEFAULT_RESULTS_DIR) as client:
        yield client


def test_real_benchmark_file_is_served(real_client: TestClient) -> None:
    body = BenchmarkSummary.model_validate(real_client.get("/benchmark/summary").json())
    assert body.variant == "ml" and body.seeds == 20
    assert len(body.rows) == 12  # 3 intensities x 4 strategies
    assert {r.strategy for r in body.rows} == {"no_control", "fcfs", "priority", "cpsat"}


def test_persistence_variant(real_client: TestClient) -> None:
    body = real_client.get("/benchmark/summary", params={"variant": "persistence"}).json()
    assert body["variant"] == "persistence" and body["source_file"] == "benchmark_persistence_summary.csv"


def test_unknown_variant_is_422(real_client: TestClient) -> None:
    assert real_client.get("/benchmark/summary", params={"variant": "x"}).status_code == 422


def test_values_are_parsed(tmp_path: Path) -> None:
    (tmp_path / "benchmark_summary.csv").write_text(f"{HEADER}\n{ROW}\n", encoding="utf-8")
    with client_for(tmp_path) as client:
        body = client.get("/benchmark/summary").json()
    row = body["rows"][0]
    assert row["mean"]["avg_delay_min"] == 7.99 and row["std"]["avg_delay_min"] == 2.56
    assert row["runs"] == 20 and body["seeds"] == 20


def test_missing_file_gives_clear_404(tmp_path: Path) -> None:
    with client_for(tmp_path) as client:
        response = client.get("/benchmark/summary")
    assert response.status_code == 404
    assert "run_benchmark.py" in response.json()["detail"]


def test_malformed_file_gives_500_with_message(tmp_path: Path) -> None:
    (tmp_path / "benchmark_summary.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    with client_for(tmp_path) as client:
        response = client.get("/benchmark/summary")
    assert response.status_code == 500 and "could not be read" in response.json()["detail"]


def test_empty_file_gives_500(tmp_path: Path) -> None:
    (tmp_path / "benchmark_summary.csv").write_text(f"{HEADER}\n", encoding="utf-8")
    with client_for(tmp_path) as client:
        assert client.get("/benchmark/summary").status_code == 500
