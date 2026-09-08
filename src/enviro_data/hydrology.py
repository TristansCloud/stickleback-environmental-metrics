"""Hydrologic context and catchment boundary interface.

MERIT Hydro is the configured hydrologic basis; this module never derives a
catchment from a small raw DEM window and never invents a marine catchment.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class HydrologyResult:
    status: str
    area_km2: float | None = None
    geometry: Any = None
    source_path: str | None = None
    message: str | None = None


def delineate_catchment(latitude: float, longitude: float, *, ecotype: str,
                        flow_direction_path: str | None = None,
                        flow_accumulation_path: str | None = None,
                        backend: Callable[..., Any] | None = None) -> HydrologyResult:
    normalized = ecotype.strip().lower().replace("_", "-")
    if normalized in {"marine", "ocean", "pelagic", "coastal-marine"}:
        return HydrologyResult("not_applicable_marine", message="coastal/marine catchment definition requires an explicit scientific policy")
    if normalized in {"marine-freshwater", "brackish", "coastal-transition"}:
        return HydrologyResult("coastal_policy_required", message="marine-freshwater catchment definition requires an explicit scientific policy")
    if not flow_direction_path or not flow_accumulation_path:
        return HydrologyResult("no_hydrology_data", message="MERIT Hydro flow-direction and flow-accumulation rasters are required")
    if backend is None:
        return HydrologyResult("delineation_not_implemented", source_path=flow_direction_path,
                               message="Inject a MERIT-Hydro-aware backend; no watershed operation was performed")
    result = backend(latitude=latitude, longitude=longitude,
                     flow_direction_path=flow_direction_path,
                     flow_accumulation_path=flow_accumulation_path)
    return result if isinstance(result, HydrologyResult) else HydrologyResult("ok", geometry=result, source_path=flow_direction_path)
