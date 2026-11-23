"""REST endpoints (see docs/API.md). Domain errors become 400/404/409 with a ``detail`` message."""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.api.benchmark import (
    BenchmarkMissingError,
    BenchmarkReadError,
    BenchmarkSummary,
    Variant,
    load_benchmark,
)
from app.api.kpi_jobs import KpiJobFailed, KpiProgress
from app.api.requests import (
    ActionRequest,
    DisruptionRequest,
    ResetRequest,
    ScenarioInfo,
    SpeedRequest,
    StartRequest,
    TrainExplanation,
)
from app.api.runner import FinishedError, RecommendationError, SimulationRunner
from app.models.corridor import DISCLAIMER
from app.models.schemas import (
    KPI,
    BlockInfo,
    Disruption,
    NetworkInfo,
    StateSnapshot,
    StationInfo,
)
from app.optimizer.kpi import RunKpis

router = APIRouter()


def get_runner(request: Request) -> SimulationRunner:
    """Return the app's single simulation runner."""
    return request.app.state.runner


Runner = Depends(get_runner)


def _bad_request(error: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(error))


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Report that the server is up."""
    return {"status": "ok"}


@router.get("/network", response_model=NetworkInfo, tags=["state"])
async def get_network(runner: SimulationRunner = Runner) -> NetworkInfo:
    """Return the static network (stations and block sections)."""
    return NetworkInfo(
        disclaimer=DISCLAIMER,
        stations=[StationInfo(**vars(s)) for s in runner.network.stations],
        blocks=[
            BlockInfo(
                id=b.id,
                from_code=b.from_code,
                to_code=b.to_code,
                length_km=b.length_km,
                line=b.line,
                speed_limit_kmph=b.speed_limit_kmph,
            )
            for b in runner.network.blocks
        ],
    )


@router.get("/state", response_model=StateSnapshot, tags=["state"])
async def get_state(runner: SimulationRunner = Runner) -> StateSnapshot:
    """Return the current snapshot."""
    return runner.snapshot()


@router.get("/scenario", response_model=ScenarioInfo, tags=["scenario"])
async def get_scenario(runner: SimulationRunner = Runner) -> ScenarioInfo:
    """Return the scenario configuration, speed and progress."""
    return ScenarioInfo(
        seed=runner.seed,
        intensity=runner.intensity,
        month=runner.month,
        speed=runner.speed,
        running=runner.running,
        tick=runner.engine.tick,
        finished=runner.finished,
    )


@router.post("/scenario/start", response_model=StateSnapshot, tags=["scenario"])
async def start_scenario(
    body: StartRequest | None = None, runner: SimulationRunner = Runner
) -> StateSnapshot:
    """Start or resume the simulation."""
    body = body or StartRequest()
    try:
        return await runner.start(seed=body.seed, strategy=body.strategy, speed=body.speed)
    except FinishedError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise _bad_request(error) from error


@router.post("/scenario/pause", response_model=StateSnapshot, tags=["scenario"])
async def pause_scenario(runner: SimulationRunner = Runner) -> StateSnapshot:
    """Pause the simulation (state is kept)."""
    return await runner.pause()


@router.post("/scenario/reset", response_model=StateSnapshot, tags=["scenario"])
async def reset_scenario(
    body: ResetRequest | None = None, runner: SimulationRunner = Runner
) -> StateSnapshot:
    """Rebuild the scenario at tick 0 (paused). The same seed gives the same run."""
    body = body or ResetRequest()
    return await runner.reset(seed=body.seed, intensity=body.intensity, month=body.month)


@router.post("/scenario/speed", tags=["scenario"])
async def set_speed(body: SpeedRequest, runner: SimulationRunner = Runner) -> dict[str, float]:
    """Set the simulation speed in ticks (simulated minutes) per real second."""
    runner.set_speed(body.speed)
    return {"speed": runner.speed}


@router.post("/actions", tags=["control"])
async def post_action(body: ActionRequest, runner: SimulationRunner = Runner) -> dict[str, object]:
    """Queue a hold/precedence action, or decide on a recommendation."""
    if body.action is not None:
        try:
            tick = runner.queue_action(body.action)
        except ValueError as error:
            raise _bad_request(error) from error
        return {"status": "queued", "applies_at_tick": tick}
    if body.recommendation_id is None or body.decision is None:  # the request model rules this out
        raise HTTPException(status_code=422, detail="recommendation_id and decision are required")
    try:
        rec = runner.decide_recommendation(body.recommendation_id, body.decision)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RecommendationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise _bad_request(error) from error
    return {"status": rec.status.value, "recommendation_id": rec.id}


@router.post("/disruptions", response_model=Disruption, status_code=201, tags=["control"])
async def post_disruption(body: DisruptionRequest, runner: SimulationRunner = Runner) -> Disruption:
    """Inject a manual disruption now."""
    try:
        return runner.inject(
            body.kind, body.duration_min, body.target_ids, body.speed_factor, body.description
        )
    except ValueError as error:
        raise _bad_request(error) from error


@router.get(
    "/kpis",
    response_model=dict[str, KPI],
    responses={202: {"model": KpiProgress, "description": "Computing; see Retry-After."}},
    tags=["state"],
)
async def get_kpis(runner: SimulationRunner = Runner) -> dict[str, KPI] | JSONResponse:
    """Return KPIs per implemented strategy for the current scenario (computed in the background, cached)."""
    return _kpi_answer(runner.kpis)


@router.get(
    "/kpis/detail",
    response_model=dict[str, RunKpis],
    responses={202: {"model": KpiProgress, "description": "Computing; see Retry-After."}},
    tags=["state"],
)
async def get_kpi_details(runner: SimulationRunner = Runner) -> dict[str, RunKpis] | JSONResponse:
    """Return the full KPI set per strategy (weighted delay, conflicts detected, actions applied, ...)."""

    def detail() -> dict[str, RunKpis] | KpiProgress:
        report = runner.kpi_report()
        if isinstance(report, KpiProgress):
            return report
        return {name.value: kpi for name, kpi in report.items()}

    return _kpi_answer(detail)


def _kpi_answer(compute: Callable[[], Any]) -> Any:
    """Return the finished body, or 202 + Retry-After while computing, or 503 if the workers failed."""
    try:
        result = compute()
    except KpiJobFailed as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if isinstance(result, KpiProgress):
        return JSONResponse(
            status_code=202, content=result.model_dump(), headers={"Retry-After": str(result.retry_after_s)}
        )
    return result


@router.get(
    "/benchmark/summary",
    response_model=BenchmarkSummary,
    responses={
        404: {"description": "Benchmark file missing."},
        500: {"description": "Benchmark file unreadable."},
    },
    tags=["state"],
)
async def get_benchmark_summary(request: Request, variant: Variant = "ml") -> BenchmarkSummary:
    """Serve the saved 20-seed benchmark summary (mean and standard deviation per strategy and intensity)."""
    try:
        return load_benchmark(request.app.state.results_dir, variant)
    except BenchmarkMissingError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except BenchmarkReadError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/trains/{train_id}/explanation",response_model=TrainExplanation, tags=["state"])
async def get_explanation(
    train_id: str,
    horizon: int = Query(default=1, ge=1, le=3, description="1 = next station, 2 = the one after, 3"),
    top: int = Query(default=5, ge=1, le=10, description="how many factors to list"),
    runner: SimulationRunner = Runner,
) -> TrainExplanation:
    """Explain (SHAP) why the delay model predicts this train's delay at an upcoming station."""
    try:
        return runner.explain_train(train_id, horizon, top)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise _bad_request(error) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
