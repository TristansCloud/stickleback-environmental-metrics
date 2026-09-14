"""Dependency-free temporal summaries for evolutionary exposure variables."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class TemporalSummary:
    mean: float | None
    minimum: float | None
    maximum: float | None
    range: float | None
    standard_deviation: float | None
    coefficient_of_variation: float | None
    valid_count: int
    missing_count: int
    status: str


def summarize_temporal(values: Iterable[object]) -> TemporalSummary:
    valid: list[float] = []
    missing = 0
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            missing += 1
            continue
        if not math.isfinite(number):
            missing += 1
            continue
        valid.append(number)
    if not valid:
        return TemporalSummary(None, None, None, None, None, None, 0, missing, "no_valid_data")
    mean = statistics.fmean(valid)
    sd = statistics.pstdev(valid)
    cv = sd / abs(mean) if mean != 0 else None
    return TemporalSummary(mean, min(valid), max(valid), max(valid) - min(valid), sd, cv,
                           len(valid), missing, "ok")
