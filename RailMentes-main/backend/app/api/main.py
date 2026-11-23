"""FastAPI application. Run it with ``python -m uvicorn app.api.main:app`` (see README)."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes, ws
from app.api.kpi_jobs import KpiService
from app.api.runner import SimulationRunner
from app.config import Settings, load_settings
from app.ml.predict import load_predictor


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app: CORS for the frontend, REST routes, WebSocket and one simulation runner."""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        predictor = load_predictor(settings.model_path, enabled=settings.use_ml_model)
        await asyncio.to_thread(predictor.warm_up)  # no-op without a model
        kpi_model = settings.model_path if predictor.model is not None else None  # workers load a copy
        app.state.results_dir = settings.results_dir
        app.state.runner = SimulationRunner(
            seed=settings.default_seed,
            predictor=predictor,
            kpi_service=KpiService(kpi_model),
            precompute_kpis=settings.precompute_kpis,
        )
        yield
        await app.state.runner.shutdown()

    app = FastAPI(
        title="RailMentes API",
        description="Simulated railway corridor with live state. All data is synthetic.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes.router)
    app.include_router(ws.router)
    return app


app = create_app()


def run() -> None:
    """Start the server with the configured host and port."""
    settings = load_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
