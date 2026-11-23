"""Simulation runner: owns the one active engine and drives it from a background asyncio task.

Everything runs on the event loop thread, so the engine needs no locks. Only one scenario is
active at a time. Viewers (WebSocket clients) subscribe to a small queue of JSON snapshots.
"""

import asyncio
import contextlib
from typing import Final

from app.api.kpi_jobs import JobKey, KpiProgress, KpiService
from app.api.requests import MAX_SPEED, MIN_SPEED, TrainExplanation
from app.ml.features import FeatureRow, build_features, is_predictable
from app.ml.predict import DelayPredictor
from app.models.corridor import build_corridor
from app.models.schemas import (
    KPI,
    Action,
    Disruption,
    DisruptionKind,
    Recommendation,
    RecommendationStatus,
    StateSnapshot,
    StrategyName,
)
from app.optimizer.conflicts import ConflictDetector
from app.optimizer.kpi import RunKpis
from app.optimizer.registry import make_strategy
from app.optimizer.strategy import Proposal, Strategy
from app.simulation.disruptions import Intensity
from app.simulation.engine import SimulationEngine
from app.simulation.scenario import Scenario

SUBSCRIBER_QUEUE_SIZE: Final = 4
KEPT_DECIDED_RECOMMENDATIONS: Final = 30  # applied / ignored recommendations kept for the alerts feed


class FinishedError(Exception):
    """Raised when asked to run a scenario that already ended."""


class RecommendationError(Exception):
    """Raised when a recommendation cannot take the requested decision any more (HTTP 409)."""


class SimulationRunner:
    """Holds the active engine and runs, pauses and resets it."""

    def __init__(
        self,
        seed: int = 42,
        intensity: Intensity = Intensity.NONE,
        month: int = 1,
        speed: float = 1.0,
        predictor: DelayPredictor | None = None,
        kpi_service: KpiService | None = None,
        precompute_kpis: bool = False,
    ):
        self.network = build_corridor()
        self.predictor = predictor or DelayPredictor()  # no model = persistence = the engine's own times
        self.seed = seed
        self.intensity = intensity
        self.month = month
        self.speed = speed
        self.running = False
        self.strategy_name = StrategyName.NO_CONTROL
        self._strategy: Strategy = make_strategy(self.strategy_name, self.network)
        self.detector = ConflictDetector(self.network)
        self._recommendations: dict[str, Recommendation] = {}  # by conflict id (one each)
        self._recommendation_count = 0
        self.engine = self._build()
        self._task: asyncio.Task[None] | None = None
        self._subscribers: set[asyncio.Queue[str]] = set()
        self.kpi_service = kpi_service or KpiService()
        self.precompute_kpis = precompute_kpis  # compute KPIs after every reset
        if precompute_kpis:
            self.kpi_service.ensure(self.kpi_key)

    # ---- state ----------------------------------------
    def _build(self) -> SimulationEngine:
        engine = Scenario(seed=self.seed, intensity=self.intensity, month=self.month).build(self.network)
        engine.strategy = self.strategy_name
        return engine

    def snapshot(self) -> StateSnapshot:
        """Return the current state: predictions, detected conflicts and the strategy's recommendations."""
        raw = self._raw_snapshot()
        predicted = raw
        if self.predictor.model is not None:
            predicted = self.predictor.apply(raw, self._features_for(raw))
        conflicts = self.detector.detect(predicted)
        recommendations = self._sync_recommendations(self._strategy.propose(predicted, conflicts))
        return predicted.model_copy(update={"conflicts": conflicts, "recommendations": recommendations})

    def _raw_snapshot(self) -> StateSnapshot:
        self.engine.running = self.running
        return self.engine.snapshot()

    def _features_for(self, snapshot: StateSnapshot) -> dict[str, FeatureRow]:
        return {
            t.id: build_features(snapshot, t, self.network, self.engine.last_arrival_delay(t.id))
            for t in snapshot.trains
            if is_predictable(t)
        }

    def live_features(self) -> dict[str, FeatureRow]:
        """Return model features for every train on the line, from the same code the training data uses."""
        return self._features_for(self._raw_snapshot())

    def explain_train(self, train_id: str, horizon: int = 1, top_n: int = 5) -> TrainExplanation:
        """Explain the model's delay prediction for one train (computed now, on request only).

        Raises:
            LookupError: unknown train id.
            ValueError: the train is not on the line, or has fewer than ``horizon`` stations ahead.
            RuntimeError: no delay model is loaded.

        """
        if self.predictor.model is None:
            raise RuntimeError(f"no delay model loaded ({self.predictor.reason}); nothing to explain")
        snapshot = self._raw_snapshot()
        train = next((t for t in snapshot.trains if t.id == train_id), None)
        if train is None:
            raise LookupError(f"unknown train '{train_id}'")
        if not is_predictable(train):
            raise ValueError(f"train '{train_id}' is not on the line ({train.status.value})")
        if horizon > len(train.next_stations):
            raise ValueError(f"train '{train_id}' has only {len(train.next_stations)} station(s) ahead")
        row = build_features(snapshot, train, self.network, self.engine.last_arrival_delay(train_id))
        explanation = self.predictor.explain(row, horizon, top_n)
        return TrainExplanation(
            **explanation.model_dump(),
            train_id=train_id,
            station=train.next_stations[horizon - 1].station,
            model_source=self.predictor.source,
        )

    @property
    def finished(self) -> bool:
        """Return True when every train has completed its route."""
        return self.engine.is_done()

    @property
    def subscriber_count(self) -> int:
        """Return the number of connected WebSocket viewers."""
        return len(self._subscribers)

    # ---- control ----------------------------------------
    def set_speed(self, speed: float) -> None:
        """Set ticks per real second (takes effect on the next tick)."""
        if not MIN_SPEED <= speed <= MAX_SPEED:
            raise ValueError(f"speed must be between {MIN_SPEED} and {MAX_SPEED}")
        self.speed = speed

    async def start(
        self, seed: int | None = None, strategy: StrategyName | None = None, speed: float | None = None
    ) -> StateSnapshot:
        """Start or resume. A new seed rebuilds the scenario first."""
        new_strategy = make_strategy(strategy, self.network) if strategy is not None else None  # may raise
        if speed is not None:
            self.set_speed(speed)
        if seed is not None and seed != self.seed:
            await self._replace_engine(seed=seed)
        if strategy is not None and new_strategy is not None:
            self.strategy_name, self._strategy = strategy, new_strategy
            self.engine.strategy = strategy
            self._recommendations.clear()
        if self.finished:
            raise FinishedError("the scenario has finished; reset it first")
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._loop())
        return self._broadcast()

    async def pause(self) -> StateSnapshot:
        """Stop ticking (the state is kept)."""
        await self._stop()
        return self._broadcast()

    async def reset(
        self, seed: int | None = None, intensity: Intensity | None = None, month: int | None = None
    ) -> StateSnapshot:
        """Rebuild the scenario at tick 0, paused. Missing arguments keep their current value."""
        await self._replace_engine(seed=seed, intensity=intensity, month=month)
        return self._broadcast()

    async def shutdown(self) -> None:
        """Stop the background task and the KPI workers (server shutting down)."""
        await self._stop()
        self.kpi_service.shutdown()

    async def _stop(self) -> None:
        self.running = False
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _replace_engine(
        self, seed: int | None = None, intensity: Intensity | None = None, month: int | None = None
    ) -> None:
        await self._stop()
        new_seed = self.seed if seed is None else seed
        new_intensity = self.intensity if intensity is None else intensity
        new_month = self.month if month is None else month
        engine = Scenario(seed=new_seed, intensity=new_intensity, month=new_month).build(self.network)
        self.seed, self.intensity, self.month = new_seed, new_intensity, new_month
        engine.strategy = self.strategy_name  # the chosen strategy stays selected across resets
        self.engine = engine
        self._recommendations.clear()
        self._recommendation_count = 0
        if self.precompute_kpis:
            self.kpi_service.ensure(self.kpi_key)  # computed in the background while the user watches

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        next_at = loop.time()
        while self.running and not self.engine.is_done():
            self.engine.step()
            self._broadcast()
            next_at = max(next_at + 1.0 / self.speed, loop.time())  # never try to catch up
            await asyncio.sleep(max(0.0, next_at - loop.time()))
        self.running = False
        self._broadcast()

    # ---- actions and disruptions ----------------------------------------
    def queue_action(self, action: Action) -> int:
        """Queue a hold/precedence action. Returns the tick at which it takes effect."""
        self.engine.apply_action(action)
        return self.engine.tick + 1

    def inject(
        self,
        kind: DisruptionKind,
        duration_min: int,
        target_ids: list[str],
        speed_factor: float | None,
        description: str | None,
    ) -> Disruption:
        """Start a manual disruption now and tell the viewers."""
        disruption = self.engine.inject_disruption(kind, duration_min, target_ids, speed_factor, description)
        self._broadcast()
        return disruption

    # ---- recommendations ----------------------------------------
    def _sync_recommendations(self, proposals: list[Proposal]) -> list[Recommendation]:
        """Bring the stored recommendations in line with what the strategy proposes now (safe to repeat)."""
        current: dict[str, Proposal] = {}
        for proposal in proposals:
            if proposal.conflict_ids:
                current.setdefault(proposal.conflict_ids[0], proposal)
        for conflict_id, proposal in current.items():
            old = self._recommendations.get(conflict_id)
            if old is None and not self._slot_taken(proposal.action):
                self._recommendation_count += 1
                self._recommendations[conflict_id] = Recommendation(
                    id=f"r-{self._recommendation_count:03d}",
                    strategy=self.strategy_name,
                    action=proposal.action,
                    conflict_ids=[conflict_id],
                    expected_delay_saved_min=proposal.expected_delay_saved_min,
                )
            elif old is not None and old.status is RecommendationStatus.PROPOSED:
                self._recommendations[conflict_id] = old.model_copy(
                    update={
                        "action": proposal.action,
                        "expected_delay_saved_min": proposal.expected_delay_saved_min,
                    }
                )
        for conflict_id, rec in list(self._recommendations.items()):  # a vanished proposal is stale
            if rec.status is RecommendationStatus.PROPOSED and conflict_id not in current:
                del self._recommendations[conflict_id]
        decided = [r for r in self._recommendations.values() if r.status is not RecommendationStatus.PROPOSED]
        for rec in decided[:-KEPT_DECIDED_RECOMMENDATIONS]:
            del self._recommendations[rec.conflict_ids[0]]
        return sorted(self._recommendations.values(), key=lambda r: r.id)

    def _slot_taken(self, action: Action) -> bool:
        """Return True if an applied recommendation already acts on this train at this station."""
        return any(
            r.status is RecommendationStatus.APPLIED
            and (r.action.train_id, r.action.at_station) == (action.train_id, action.at_station)
            for r in self._recommendations.values()
        )

    def decide_recommendation(self, recommendation_id: str, decision: str) -> Recommendation:
        """Apply or ignore a recommendation, or undo an ignore.

        Raises:
            LookupError: no such recommendation (it may have expired because the conflict is gone).
            RecommendationError: the decision no longer makes sense (already decided, or the train moved on).
            ValueError: the decision is not possible (an applied action cannot be undone).

        """
        self.snapshot()  # make sure the list is current
        rec = next((r for r in self._recommendations.values() if r.id == recommendation_id), None)
        if rec is None:
            raise LookupError(f"unknown recommendation '{recommendation_id}'")
        key = rec.conflict_ids[0]
        if decision == "undo":
            if rec.status is RecommendationStatus.APPLIED:
                raise ValueError("an applied action cannot be undone; it is already in force")
            updated = rec.model_copy(update={"status": RecommendationStatus.PROPOSED})
        elif rec.status is not RecommendationStatus.PROPOSED:
            raise RecommendationError(f"recommendation '{recommendation_id}' is already {rec.status.value}")
        elif decision == "ignore":
            updated = rec.model_copy(update={"status": RecommendationStatus.IGNORED})
        else:
            try:
                self.engine.apply_action(rec.action)
            except ValueError as error:
                del self._recommendations[key]
                message = f"recommendation '{recommendation_id}' is no longer valid: {error}"
                raise RecommendationError(message) from error
            updated = rec.model_copy(update={"status": RecommendationStatus.APPLIED})
        self._recommendations[key] = updated
        self._broadcast()
        return updated

    # ---- KPIs ----------------------------------------
    @property
    def kpi_key(self) -> JobKey:
        """Return the key of the current scenario's KPI job."""
        return (self.seed, self.intensity, self.month)

    def kpi_report(self) -> dict[StrategyName, RunKpis] | KpiProgress:
        """Return every strategy's KPIs for the current scenario, or the progress while computing.

        Never blocks: the runs happen in worker processes (see ``kpi_jobs.py``) and are cached per scenario.
        All strategies face the same seed, intensity and month, so every one faces the same day.

        Raises:
            KpiJobFailed: a worker crashed; asking again starts the job again.

        """
        return self.kpi_service.report(self.kpi_key)

    def kpis(self) -> dict[str, KPI] | KpiProgress:
        """Return the shared ``KPI`` per strategy (``conflicts_avoided`` vs no control), or the progress."""
        report = self.kpi_report()
        if isinstance(report, KpiProgress):
            return report
        baseline = report[StrategyName.NO_CONTROL].blocking_events
        return {name.value: kpi.to_schema(baseline) for name, kpi in report.items()}

    # ---- viewers ----------------------------------------
    def subscribe(self) -> asyncio.Queue[str]:
        """Register a viewer; it receives every later snapshot as a JSON string."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        """Forget a viewer."""
        self._subscribers.discard(queue)

    def _broadcast(self) -> StateSnapshot:
        snapshot = self.snapshot()
        payload = snapshot.model_dump_json()
        for queue in self._subscribers:
            if queue.full():  # slow viewer: drop its oldest frame, keep the newest
                queue.get_nowait()
            queue.put_nowait(payload)
        return snapshot
