"""Tests for server settings."""

from pathlib import Path

import pytest

from app.config import DEFAULT_MODEL_PATH, DEFAULT_ORIGINS, Settings, load_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "BACKEND_HOST",
        "BACKEND_PORT",
        "FRONTEND_ORIGIN",
        "SIM_SEED",
        "USE_ML_MODEL",
        "DELAY_MODEL_PATH",
        "PRECOMPUTE_KPIS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_without_env_file(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / "missing.env")
    assert (settings.host, settings.port, settings.default_seed) == ("127.0.0.1", 8000, 42)
    assert settings.allowed_origins == DEFAULT_ORIGINS
    assert "http://localhost:5173" in settings.allowed_origins


def test_env_file_is_read(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nBACKEND_PORT=9001\nSIM_SEED=7\nFRONTEND_ORIGIN=http://localhost:3000\n", encoding="utf-8"
    )
    settings = load_settings(env)
    assert settings.port == 9001 and settings.default_seed == 7
    assert (
        "http://localhost:3000" in settings.allowed_origins
        and "http://localhost:5173" in settings.allowed_origins
    )


def test_real_environment_wins_over_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("BACKEND_PORT=9001\n", encoding="utf-8")
    monkeypatch.setenv("BACKEND_PORT", "9002")
    assert load_settings(env).port == 9002


def test_delay_model_is_on_by_default_and_can_be_switched_off(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "missing.env").use_ml_model is True
    assert load_settings(tmp_path / "missing.env").model_path == DEFAULT_MODEL_PATH
    env = tmp_path / ".env"
    for word in ("false", "0", "No", "OFF"):
        env.write_text("USE_ML_MODEL=" + word, encoding="utf-8")
        assert load_settings(env).use_ml_model is False


def test_model_path_can_be_set(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("DELAY_MODEL_PATH=somewhere/model.json", encoding="utf-8")
    assert load_settings(env).model_path == Path("somewhere/model.json")


def test_plain_settings_never_load_a_model() -> None:
    assert Settings().use_ml_model is False


def test_kpi_precompute_is_on_by_default_and_plain_settings_start_no_workers(tmp_path: Path) -> None:
    assert load_settings(tmp_path / "missing.env").precompute_kpis is True
    off = tmp_path / "off.env"
    off.write_text("PRECOMPUTE_KPIS=false", encoding="utf-8")
    assert load_settings(off).precompute_kpis is False
    assert Settings().precompute_kpis is False
