"""Train categories and their operating characteristics.

All numbers are synthetic and simplified. They are inspired by Indian train
classes but are NOT taken from real Indian Railways data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TrainCategory(StrEnum):
    """The four train classes used in RailMentes."""

    PREMIUM = "premium"  # Rajdhani / Vande Bharat style
    EXPRESS = "express"
    PASSENGER = "passenger"
    FREIGHT = "freight"


@dataclass(frozen=True)
class TrainType:
    """Operating profile shared by all trains of one category.

    Attributes:
        category: Which class of train this is.
        label: Human-readable name for the UI.
        priority: Higher number wins a conflict (also the weight in the
            optimizer's "priority-weighted delay" objective).
        max_speed_kmph: Top speed on a section with no lower limit.
        halt_minutes: Planned stop time at every station where it stops.
        max_stop_size: Stops at stations whose ``size`` is <= this value
            (1 = major, 2 = medium, 3 = minor). 0 means "no commercial stops".

    """

    category: TrainCategory
    label: str
    priority: int
    max_speed_kmph: int
    halt_minutes: int
    max_stop_size: int


TRAIN_TYPES: dict[TrainCategory, TrainType] = {
    TrainCategory.PREMIUM: TrainType(TrainCategory.PREMIUM, "Premium (Rajdhani/Vande Bharat)", 4, 130, 2, 1),
    TrainCategory.EXPRESS: TrainType(TrainCategory.EXPRESS, "Express", 3, 110, 2, 2),
    TrainCategory.PASSENGER: TrainType(TrainCategory.PASSENGER, "Passenger", 2, 80, 1, 3),
    TrainCategory.FREIGHT: TrainType(TrainCategory.FREIGHT, "Freight", 1, 60, 0, 0),
}


def get_train_type(category: TrainCategory) -> TrainType:
    """Return the operating profile for a train category."""
    return TRAIN_TYPES[category]


def run_minutes(length_km: float, speed_limit_kmph: float, train_type: TrainType) -> float:
    """Minimum running time over a section, in minutes.

    The train runs at the lower of its own top speed and the section limit.
    """
    if length_km <= 0 or speed_limit_kmph <= 0:
        raise ValueError("length_km and speed_limit_kmph must be positive")
    speed = min(speed_limit_kmph, train_type.max_speed_kmph)
    return length_km / speed * 60.0


def stops_at(train_type: TrainType, station_size: int) -> bool:
    """Return True if this train type makes a commercial stop at a station of this size."""
    return station_size <= train_type.max_stop_size
