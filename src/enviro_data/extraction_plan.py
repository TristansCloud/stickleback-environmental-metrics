"""Pure, serializable extraction plans for habitat-aware source routing."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .habitats import HabitatDomain, normalize_habitat
from .input import SiteRecord
from .source_catalog import SourceSpec, sources_for_habitat


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    sample_id: str
    latitude: float
    longitude: float
    habitat: HabitatDomain
    source_id: str
    asset_id: str
    backend: str
    bands: tuple[str, ...]
    scale_m: float
    extraction_geometry: str

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["habitat"] = self.habitat.value
        return value


def plan_site(record: SiteRecord, *, sources: Iterable[SourceSpec] | None = None) -> tuple[ExtractionRequest, ...]:
    habitat = normalize_habitat(record.ecotype)
    selected = tuple(sources) if sources is not None else sources_for_habitat(habitat)
    return tuple(
        ExtractionRequest(
            record.sample_id, record.latitude, record.longitude, habitat,
            source.source_id, source.asset_id, source.backend,
            tuple(variable.band for variable in source.variables),
            source.resolution_m, source.extraction_geometry,
        )
        for source in selected if source.applies_to(habitat)
    )


def plan_sites(records: Iterable[SiteRecord]) -> tuple[ExtractionRequest, ...]:
    return tuple(request for record in records for request in plan_site(record))
