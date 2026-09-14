"""Canonical habitat domains used to route environmental sources."""
from __future__ import annotations

from enum import StrEnum


class HabitatDomain(StrEnum):
    FRESHWATER = "freshwater"
    TRANSITION = "transition"
    MARINE = "marine"
    UNKNOWN = "unknown"


_ALIASES = {
    "freshwater": HabitatDomain.FRESHWATER,
    "lake": HabitatDomain.FRESHWATER,
    "river": HabitatDomain.FRESHWATER,
    "stream": HabitatDomain.FRESHWATER,
    "marine": HabitatDomain.MARINE,
    "ocean": HabitatDomain.MARINE,
    "pelagic": HabitatDomain.MARINE,
    "coastal-marine": HabitatDomain.MARINE,
    "marine-freshwater": HabitatDomain.TRANSITION,
    "brackish": HabitatDomain.TRANSITION,
    "estuary": HabitatDomain.TRANSITION,
    "estuarine": HabitatDomain.TRANSITION,
    "coastal-transition": HabitatDomain.TRANSITION,
}


def normalize_habitat(value: object) -> HabitatDomain:
    """Map source labels to a stable domain without silently guessing."""
    label = str(value or "").strip().lower().replace("_", "-")
    return _ALIASES.get(label, HabitatDomain.UNKNOWN)
