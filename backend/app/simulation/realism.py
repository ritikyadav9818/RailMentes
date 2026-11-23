"""Optional extra realism for generated data: random extra halt time at stations.

Real trains rarely leave exactly on time: boarding takes longer in rush hour and on busy days.
When switched on (``Scenario(realism=True)``), every halt at an intermediate station gets a random
extra dwell, drawn from an exponential distribution (many small values, a few long ones):

    mean extra minutes = base(category) x peak-hour factor x day-of-week factor, capped at 8 min

Switched off (the default) the engine follows the timetable exactly, as in all earlier phases.
The numbers are invented for plausibility; they are not measured from real railways.
"""

import random
from datetime import datetime, timedelta

from app.models.train import TrainCategory
from app.simulation.engine import DwellExtra

BASE_MEAN_MIN = {
    TrainCategory.PREMIUM: 0.4,
    TrainCategory.EXPRESS: 0.8,
    TrainCategory.PASSENGER: 1.4,
    TrainCategory.FREIGHT: 0.0,  # freight never makes commercial stops
}
PEAK_HOURS = frozenset({7, 8, 9, 17, 18, 19})
PEAK_FACTOR = 1.8
DAY_OF_WEEK_FACTOR = (1.0, 0.9, 0.9, 1.0, 1.25, 1.1, 1.35)  # Monday ... Sunday
MAX_EXTRA_MIN = 8


def mean_extra_minutes(category: TrainCategory, when: datetime) -> float:
    """Return the mean extra halt time for a train category at a given moment."""
    factor = PEAK_FACTOR if when.hour in PEAK_HOURS else 1.0
    return BASE_MEAN_MIN[category] * factor * DAY_OF_WEEK_FACTOR[when.weekday()]


def make_dwell_extra(noise_seed: int, sim_start: datetime) -> DwellExtra:
    """Create the engine hook. It uses its own RNG, so it never disturbs other random draws."""
    rng = random.Random(f"dwell-noise-{noise_seed}")

    def dwell_extra(category: TrainCategory, station: str, tick: int) -> int:
        mean = mean_extra_minutes(category, sim_start + timedelta(minutes=tick))
        if mean <= 0:
            return 0
        return min(MAX_EXTRA_MIN, round(rng.expovariate(1.0 / mean)))

    return dwell_extra
