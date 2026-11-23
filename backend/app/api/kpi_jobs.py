"""Background KPI computation: run every strategy over the whole current day without blocking the API.

Why a separate PROCESS pool: a full day under the CP-SAT strategy (and the ML model) is CPU-heavy Python.
In a thread it would hold the interpreter lock and make the live simulation stutter; in other processes it
does not. The pool uses the ``spawn`` start method on every platform (the only one Windows has), so the
worker function is a plain top-level function that takes and returns simple values, and nothing here runs at
import time. Anything that creates a pool must be started from a ``if __name__ == "__main__"`` guarded
entry point (uvicorn and pytest both are).

One job = one (seed, intensity, month) scenario = one task per strategy. The API asks ``report``:
the answer is either the finished KPIs, or a ``KpiProgress`` ("computing, 2 of 4 done").
"""

import multiprocessing
import os
from concurrent.futures import Future, ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ml.predict import DelayPredictor, load_predictor
from app.models.corridor import build_corridor
from app.models.schemas import StrategyName
from app.optimizer.closed_loop import run_closed_loop
from app.optimizer.kpi import RunKpis
from app.optimizer.registry import IMPLEMENTED_STRATEGIES, make_strategy
from app.simulation.disruptions import Intensity
from app.simulation.scenario import Scenario

JobKey = tuple[int, Intensity, int]  # (seed, intensity, month)
RETRY_AFTER_S = 2
MAX_KEPT_JOBS = 4


class KpiProgress(BaseModel):
    """Body of the 202 answer of GET /kpis while the numbers are still being computed."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["computing"] = "computing"
    done: list[str]  # strategies that are finished
    total: int
    retry_after_s: int = RETRY_AFTER_S


class KpiJobFailed(Exception):
    """Raised when a worker crashed; the next request starts the job again."""


@lru_cache(maxsize=1)
def _worker_predictor(model_path: str | None) -> DelayPredictor | None:
    return load_predictor(Path(model_path)) if model_path else None


def run_strategy_kpis(
    seed: int, intensity: str, month: int, strategy: str, model_path: str | None
) -> RunKpis:
    """Worker: run one strategy over one scenario and return its KPIs (a top-level function)."""
    network = build_corridor()
    scenario = Scenario(seed=seed, intensity=Intensity(intensity), month=month)
    impl = make_strategy(StrategyName(strategy), network)
    return run_closed_loop(scenario, impl, network, _worker_predictor(model_path)).kpis


class KpiService:
    """Starts KPI jobs in worker processes and reports their progress. Used from the event loop only."""

    def __init__(self, model_path: Path | None = None, max_workers: int | None = None) -> None:
        self.model_path = str(model_path) if model_path else None
        self.max_workers = max_workers or max(1, min(len(IMPLEMENTED_STRATEGIES), (os.cpu_count() or 2) - 1))
        self._pool: ProcessPoolExecutor | None = None
        self._jobs: dict[JobKey, dict[StrategyName, Future[RunKpis]]] = {}

    def ensure(self, key: JobKey) -> None:
        """Start the job for ``key`` unless it is already running or finished."""
        if key in self._jobs:
            return
        for other in self._jobs.values():  # a newer scenario matters more: drop work that has not started
            for future in other.values():
                future.cancel()
        while len(self._jobs) >= MAX_KEPT_JOBS:
            del self._jobs[next(iter(self._jobs))]
        pool = self._get_pool()
        seed, intensity, month = key
        self._jobs[key] = {
            name: pool.submit(run_strategy_kpis, seed, intensity.value, month, name.value, self.model_path)
            for name in IMPLEMENTED_STRATEGIES
        }

    def report(self, key: JobKey) -> dict[StrategyName, RunKpis] | KpiProgress:
        """Return the finished KPIs, or the progress while the job is still running.

        Raises:
            KpiJobFailed: a worker raised an error or died (the job is forgotten so a retry starts afresh).

        """
        self.ensure(key)
        futures = self._jobs[key]
        failed = [f for f in futures.values() if f.done() and (f.cancelled() or f.exception() is not None)]
        if failed:
            del self._jobs[key]
            error = failed[0].exception() if not failed[0].cancelled() else "cancelled"
            raise KpiJobFailed(f"KPI computation failed: {error}")
        if all(f.done() for f in futures.values()):
            return {name: f.result() for name, f in futures.items()}
        done = [name.value for name, f in futures.items() if f.done()]
        return KpiProgress(done=done, total=len(futures))

    def shutdown(self) -> None:
        """Stop accepting work, cancel what has not started, and do not wait for running workers."""
        pool, self._pool = self._pool, None
        self._jobs.clear()
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    def _get_pool(self) -> ProcessPoolExecutor:
        if self._pool is None:
            self._pool = ProcessPoolExecutor(
                max_workers=self.max_workers, mp_context=multiprocessing.get_context("spawn")
            )
        return self._pool
