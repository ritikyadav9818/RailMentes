"""Scenario: a small config object that creates a reproducible simulation run.

Same ``Scenario`` -> same timetable, same random disruptions, same run.
"""

from dataclasses import dataclass
from datetime import date, datetime, time

from app.models.network import Network
from app.models.schemas import Disruption
from app.simulation.disruptions import Intensity, generate_disruptions
from app.simulation.engine import SIM_START, SimulationEngine
from app.simulation.realism import make_dwell_extra
from app.simulation.timetable import generate_timetable


@dataclass(frozen=True)
class Scenario:
    """Configuration of one run.

    Attributes:
        seed: Seeds the timetable and the random disruptions.
        intensity: How many random disruptions to generate (none = clean run).
        month: Month of the simulated day (1-12). Sets the date shown in snapshots and
            how likely fog is (Nov-Feb: mostly fog).
        manual_disruptions: Extra disruptions to add; they are renumbered m-001, m-002, ...
        start_date: Optional real calendar date of the simulated day. When given it replaces
            ``month`` (the month is taken from the date) and sets the day of week. The data
            generator uses it to simulate many different days.
        realism: Add random extra halt time at stations (more at rush hour and on busy days).
            Off by default, which keeps the exact-timetable behaviour of earlier phases.

    """

    seed: int = 42
    intensity: Intensity = Intensity.NONE
    month: int = SIM_START.month
    manual_disruptions: tuple[Disruption, ...] = ()
    start_date: date | None = None
    realism: bool = False

    def build(self, network: Network) -> SimulationEngine:
        """Create the engine, with generated and manual disruptions registered."""
        if not 1 <= self.month <= 12:
            raise ValueError("month must be between 1 and 12")
        if self.start_date is not None:
            start = datetime.combine(self.start_date, time())
        else:
            start = datetime(SIM_START.year, self.month, SIM_START.day)
        plans = generate_timetable(network, self.seed)
        dwell = make_dwell_extra(self.seed, start) if self.realism else None
        engine = SimulationEngine(network, plans, self.seed, sim_start=start, dwell_extra=dwell)
        for disruption in generate_disruptions(network, plans, engine.rng, self.intensity, start.month):
            engine.add_disruption(disruption)
        for disruption in self.manual_disruptions:
            engine.add_manual_disruption(disruption)
        return engine
