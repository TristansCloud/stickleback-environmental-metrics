"""Deterministic bounded pilot selection for the 40-site validation run."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .input import SiteRecord


@dataclass(frozen=True, slots=True)
class PilotConfig:
    """Selection policy; defaults are the checked-in 40-site pilot."""

    size: int = 40
    # Geographic distance is computed in normalized latitude/longitude space.
    latitude_weight: float = 1.0
    longitude_weight: float = 1.0


def _quota(records: list[SiteRecord], size: int) -> dict[str, int]:
    groups: dict[str, list[SiteRecord]] = {}
    for record in records:
        groups.setdefault(record.ecotype, []).append(record)
    if size > len(records):
        raise ValueError(f"pilot size {size} exceeds {len(records)} valid records")
    # Largest-remainder allocation, with one slot for every represented ecotype
    # where possible. This preserves composition while avoiding silent omission.
    raw = {key: size * len(value) / len(records) for key, value in groups.items()}
    result = {key: min(len(groups[key]), int(math.floor(value))) for key, value in raw.items()}
    for key in sorted(groups):
        if result[key] == 0 and size >= len(groups):
            result[key] = 1
    while sum(result.values()) < size:
        key = max(groups, key=lambda k: (raw[k] - result[k], len(groups[k]), k))
        if result[key] < len(groups[key]):
            result[key] += 1
        else:
            break
    return result


def _spread_select(group: list[SiteRecord], count: int, config: PilotConfig) -> list[SiteRecord]:
    if count >= len(group):
        return sorted(group, key=lambda x: x.sample_id)
    lat_min, lat_max = min(x.latitude for x in group), max(x.latitude for x in group)
    lon_min, lon_max = min(x.longitude for x in group), max(x.longitude for x in group)
    def point(x: SiteRecord) -> tuple[float, float]:
        lat = (x.latitude - lat_min) / (lat_max - lat_min or 1.0)
        lon = (x.longitude - lon_min) / (lon_max - lon_min or 1.0)
        return lat * config.latitude_weight, lon * config.longitude_weight
    ordered = sorted(group, key=lambda x: x.sample_id)
    selected = [ordered[0]]
    while len(selected) < count:
        def score(candidate: SiteRecord) -> tuple[float, str]:
            p = point(candidate)
            nearest = min(math.dist(p, point(chosen)) for chosen in selected)
            return nearest, candidate.sample_id
        remaining = [x for x in ordered if x not in selected]
        selected.append(max(remaining, key=score))
    return sorted(selected, key=lambda x: x.sample_id)


def select_pilot(records: Iterable[SiteRecord], config: PilotConfig | None = None) -> tuple[SiteRecord, ...]:
    """Select exactly ``config.size`` valid records, stratified by ecotype and spread geographically."""
    config = config or PilotConfig()
    if config.size <= 0:
        raise ValueError("pilot size must be positive")
    valid = list(records)
    quotas = _quota(valid, config.size)
    selected: list[SiteRecord] = []
    for ecotype in sorted(quotas):
        group = [record for record in valid if record.ecotype == ecotype]
        selected.extend(_spread_select(group, quotas[ecotype], config))
    return tuple(sorted(selected, key=lambda x: x.sample_id))


def write_pilot_csv(records: Iterable[SiteRecord], path: str | Path) -> None:
    """Write normalized pilot records using the public input schema."""
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("sample_id", "Population.name", "population.abbreviation", "Latitude", "Longitude", "Ecotype"))
        for record in records:
            writer.writerow((record.sample_id, record.population_name, record.population_abbreviation,
                             record.latitude, record.longitude, record.ecotype))
