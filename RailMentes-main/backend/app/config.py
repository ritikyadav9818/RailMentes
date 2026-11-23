"""Server settings, read from environment variables (and an optional repo-root ``.env`` file).

Variables (see ``.env.example``): BACKEND_HOST, BACKEND_PORT, FRONTEND_ORIGIN, SIM_SEED,
USE_ML_MODEL (on by default; 0/false/no/off disables the delay model), DELAY_MODEL_PATH,
PRECOMPUTE_KPIS (on by default: compute the strategy KPIs in the background after every reset).
Real environment variables win over the ``.env`` file.
"""

import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
DEFAULT_MODEL_PATH = ENV_FILE.parent / "models" / "delay_model.json"
DEFAULT_RESULTS_DIR = ENV_FILE.parent / "docs" / "results"
_FALSE_WORDS = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class Settings:
    """Settings for the API server."""

    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: tuple[str, ...] = DEFAULT_ORIGINS
    default_seed: int = 42
    use_ml_model: bool = False  # load_settings() turns it on by default; plain Settings() stays model-free
    model_path: Path = DEFAULT_MODEL_PATH
    precompute_kpis: bool = False  # load_settings() turns it on; plain Settings() starts no workers
    results_dir: Path = DEFAULT_RESULTS_DIR  # where GET /benchmark/summary reads the benchmark CSVs


def _read_env_file(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines; comments and blank lines are skipped."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def load_settings(env_file: Path = ENV_FILE) -> Settings:
    """Build settings from ``.env`` plus the process environment."""
    env = {**_read_env_file(env_file), **os.environ}
    origins = DEFAULT_ORIGINS
    if "FRONTEND_ORIGIN" in env:
        origins = tuple(dict.fromkeys((*DEFAULT_ORIGINS, env["FRONTEND_ORIGIN"])))
    return Settings(
        host=env.get("BACKEND_HOST", "127.0.0.1"),
        port=int(env.get("BACKEND_PORT", "8000")),
        allowed_origins=origins,
        default_seed=int(env.get("SIM_SEED", "42")),
        use_ml_model=env.get("USE_ML_MODEL", "true").strip().lower() not in _FALSE_WORDS,
        model_path=Path(env.get("DELAY_MODEL_PATH", str(DEFAULT_MODEL_PATH))),
        precompute_kpis=env.get("PRECOMPUTE_KPIS", "true").strip().lower() not in _FALSE_WORDS,
    )
