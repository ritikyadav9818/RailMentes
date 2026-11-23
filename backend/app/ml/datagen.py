"""Synthetic training-data generator: runs the SAME simulation engine headless for many days.

For every day we pick a calendar date, a seed and a disruption intensity, run the engine to the end
and record one row each time a train leaves (or passes) a station:

    features  - built by ``features.build_features`` from the snapshot at that moment (same code as live)
    targets   - the train's real delay at each of its next 3 stations (known only after the day ends)

All data is synthetic. See docs/DATA.md for the limits of the simulation.
"""

import csv
import functools
import random
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from app.ml import features as feature_module
from app.ml.features import ALL_COLUMNS, STATIONS_AHEAD, TARGET_COLUMNS
from app.models.corridor import build_corridor
from app.models.network import Network
from app.simulation.disruptions import Intensity
from app.simulation.scenario import Scenario

DEFAULT_START = date(2025, 10, 1)  # 180 days from here cover October to March (the fog season)
INTENSITY_WEIGHTS = {Intensity.NONE: 0.35, Intensity.LOW: 0.35, Intensity.MEDIUM: 0.20, Intensity.HIGH: 0.10}
MAX_TICKS = 4000  # a day that runs longer than this is treated as a deadlock

Row = dict[str, float | int | str | None]
_TEXT_COLUMNS = {"train_category", "scenario_id", "day", "intensity", "train_id", "station"}
_INT_COLUMNS = {
    *("seed", "station_idx", "tick", "priority", "hour", "day_of_week", "month"),
    *("stations_ahead", "next_will_stop", "sched_to_s1", "sched_to_s2", "sched_to_s3"),
    *(
        "trains_in_next_blocks",
        "opposing_trains_in_next_blocks",
        "next_hop_single_line",
        "single_line_blocks_ahead",
    ),
    *("fog_active", "weather_slowdown_active", "signal_failure_active", "closure_active"),
    *TARGET_COLUMNS,
}


@dataclass(frozen=True)
class DaySpec:
    """What one simulated day looks like."""

    index: int
    day: date
    seed: int
    intensity: Intensity

    @property
    def scenario_id(self) -> str:
        """Return an id that is unique per day and seed."""
        return f"D{self.index:04d}-S{self.seed}"


@functools.cache
def _network() -> Network:
    return build_corridor()


def plan_days(num_days: int, seed: int, start: date = DEFAULT_START) -> list[DaySpec]:
    """Pick the date, seed and disruption intensity of every day (reproducible from ``seed``)."""
    rng = random.Random(f"plan-days-{seed}")
    intensities = list(INTENSITY_WEIGHTS)
    weights = list(INTENSITY_WEIGHTS.values())
    return [
        DaySpec(i, start + timedelta(days=i), rng.randrange(1, 2**31), rng.choices(intensities, weights)[0])
        for i in range(num_days)
    ]


def generate_day(spec: DaySpec, realism: bool = True) -> list[Row]:
    """Simulate one day and return its rows (one per station departure)."""
    network = _network()
    engine = Scenario(seed=spec.seed, intensity=spec.intensity, start_date=spec.day, realism=realism).build(
        network
    )
    pending: list[tuple[str, int, int]] = []
    engine.on_departure = lambda train_id, idx, tick: pending.append((train_id, idx, tick))
    events: list[tuple[str, int, int, dict]] = []
    while not engine.is_done():
        if engine.tick >= MAX_TICKS:
            raise RuntimeError(f"day {spec.scenario_id} did not finish (deadlock?)")
        engine.step()
        if not pending:
            continue
        snapshot = engine.snapshot()  # one snapshot serves every departure of this minute
        trains = {t.id: t for t in snapshot.trains}
        for train_id, idx, tick in pending:
            feats = feature_module.build_features(
                snapshot, trains[train_id], network, engine.last_arrival_delay(train_id)
            )
            events.append((train_id, idx, tick, feats))
        pending.clear()
    return [_row(spec, engine, *event) for event in events]


def _row(spec: DaySpec, engine, train_id: str, idx: int, tick: int, feats: dict) -> Row:
    """Join metadata, features and targets (arrival delays at the next stations, known after the day)."""
    stops = engine.plans[train_id].stops
    arrivals = engine.arrival_log[train_id]
    targets: dict[str, int | None] = {}
    for k in range(1, STATIONS_AHEAD + 1):
        j = idx + k
        targets[f"target_delay_{k}"] = arrivals[j][1] - stops[j].arrive_min if j < len(stops) else None
    meta: Row = {
        "scenario_id": spec.scenario_id,
        "day": spec.day.isoformat(),
        "seed": spec.seed,
        "intensity": spec.intensity.value,
        "train_id": train_id,
        "station": stops[idx].station,
        "station_idx": idx,
        "tick": tick,
    }
    return {**meta, **feats, **targets}


def _generate_day_args(args: tuple[DaySpec, bool]) -> list[Row]:
    return generate_day(*args)


def generate_dataset(specs: Iterable[DaySpec], realism: bool = True, workers: int = 1) -> Iterator[list[Row]]:
    """Yield the rows of each day, in order. ``workers`` > 1 simulates days in parallel processes."""
    jobs = [(spec, realism) for spec in specs]
    if workers <= 1:
        for job in jobs:
            yield generate_day(*job)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(_generate_day_args, jobs, chunksize=2)


# ---- output ------------------------------------------------------------------------------------
def write_csv(
    days: Iterable[list[Row]], path: Path, on_day: Callable[[list[Row]], None] | None = None
) -> int:
    """Write rows to a CSV file (empty cell = missing value). Returns the number of rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(ALL_COLUMNS)
        for rows in days:
            writer.writerows([["" if r[c] is None else r[c] for c in ALL_COLUMNS] for r in rows])
            count += len(rows)
            if on_day:
                on_day(rows)
    return count


def sql_type(column: str) -> str:
    """Return the SQLite column type for a dataset column."""
    if column in _TEXT_COLUMNS:
        return "TEXT"
    return "INTEGER" if column in _INT_COLUMNS else "REAL"


def write_sqlite(rows: Iterable[Row], path: Path) -> int:
    """Write rows to a SQLite table ``runs`` (replaces an existing file). Returns the number of rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    columns = ", ".join(f"{c} {sql_type(c)}" for c in ALL_COLUMNS)
    marks = ", ".join("?" for _ in ALL_COLUMNS)
    with sqlite3.connect(path) as db:
        db.execute(f"CREATE TABLE runs ({columns})")
        cursor = db.executemany(
            f"INSERT INTO runs VALUES ({marks})", ([r[c] for c in ALL_COLUMNS] for r in rows)
        )
        db.execute("CREATE INDEX runs_day ON runs (scenario_id)")
    return cursor.rowcount


def sample_rows(rows: list[Row], n: int) -> list[Row]:
    """Pick ``n`` evenly spaced rows (all rows if there are fewer)."""
    if len(rows) <= n:
        return rows
    return [rows[round(i * len(rows) / n)] for i in range(n)]
