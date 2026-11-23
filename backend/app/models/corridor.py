"""The fictional RailMentes demo corridor.

DISCLAIMER: station names are Indian-style but the network, distances and
speeds are invented and simplified. It is inspired by, not a copy of, any real
railway line.

Layout (west -> east)::

    SGP-DVG-KLP-MJG-VDJ-BHP-GNK-RMJ-SLP-TLG-ARC      main line (11 stations)
                     |           |
                    PTK-KSG-TLK  RGY                 branch (from VDJ), goods yard (from RMJ)
"""

from __future__ import annotations

from app.models.network import LineType, Network, Segment, Station

DISCLAIMER = "Fictional network inspired by Indian railways; not real data."

_D, _S = LineType.DOUBLE, LineType.SINGLE

STATIONS: list[Station] = [
    # Main line
    Station("SGP", "Sarangpur Central", 1, 5),
    Station("DVG", "Devgarh", 3, 2),
    Station("KLP", "Kalyanpur", 2, 3),
    Station("MJG", "Maharajganj", 3, 2),
    Station("VDJ", "Vindhyapur Junction", 1, 6, is_junction=True),
    Station("BHP", "Bhimpur", 2, 3),
    Station("GNK", "Gangakhed", 3, 2),
    Station("RMJ", "Ramnagar Junction", 1, 6, is_junction=True),
    Station("SLP", "Shivalipur", 2, 3),
    Station("TLG", "Talgaon", 3, 2),
    Station("ARC", "Aryavart Central", 1, 5),
    # Branch line from VDJ
    Station("PTK", "Patharkhand", 2, 3),
    Station("KSG", "Kesarganj", 3, 2),
    Station("TLK", "Tilakpur Terminus", 1, 3),
    # Goods yard spur from RMJ
    Station("RGY", "Ramnagar Goods Yard", 3, 4, freight_only=True),
]

SEGMENTS: list[Segment] = [
    # Main line: double track, except the single-line stretch BHP-GNK-RMJ
    Segment("SGP", "DVG", 34, _D, 130),
    Segment("DVG", "KLP", 34, _D, 130),
    Segment("KLP", "MJG", 29, _D, 130),
    Segment("MJG", "VDJ", 34, _D, 130),
    Segment("VDJ", "BHP", 41, _D, 130),
    Segment("BHP", "GNK", 32, _S, 100),
    Segment("GNK", "RMJ", 37, _S, 100),
    Segment("RMJ", "SLP", 36, _D, 130),
    Segment("SLP", "TLG", 33, _D, 130),
    Segment("TLG", "ARC", 38, _D, 130),
    # Branch line (single, slower)
    Segment("VDJ", "PTK", 40, _S, 80),
    Segment("PTK", "KSG", 38, _S, 80),
    Segment("KSG", "TLK", 34, _S, 80),
    # Goods yard spur (single, very slow)
    Segment("RMJ", "RGY", 12, _S, 30),
]


def build_corridor() -> Network:
    """Build the demo corridor network."""
    return Network(STATIONS, SEGMENTS)
