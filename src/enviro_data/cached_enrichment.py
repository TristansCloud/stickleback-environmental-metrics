"""Materialize ecological metrics from the checked-in pilot cache."""
from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from .habitats import HabitatDomain, normalize_habitat
from .metrics import EnvironmentalMetric, MetricProvenance


_EMPTY = {"", "none", "null", "nan"}


def _number(value: object) -> float | None:
    if value is None or str(value).strip().lower() in _EMPTY:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _status(source_status: object, value: object, *, not_applicable: bool = False) -> str:
    if not_applicable:
        return "not_applicable"
    normalized = str(source_status or "").strip().lower()
    if normalized in {"valid_value", "ok", "cache_hit", "acquired"} and value is not None:
        return "ok"
    if normalized in {"not_applicable_marine", "not_applicable"}:
        return "not_applicable"
    return "no_valid_data" if value is None else "ok"


def _metric(name: str, value: float | int | None, source_status: object, axis: str,
            unit: str | None, provenance: MetricProvenance, *, not_applicable: bool = False,
            diagnostics: Mapping[str, Any] | None = None) -> EnvironmentalMetric:
    if not_applicable:
        value = None
    return EnvironmentalMetric(name, value, _status(source_status, value, not_applicable=not_applicable),
                               axis, unit, provenance, diagnostics or {})


def enrich_cached_row(row: Mapping[str, object]) -> tuple[EnvironmentalMetric, ...]:
    """Convert one flattened validation row to analysis-ready variables.

    No network access or spatial calculation occurs. Values remain null when
    the original source was masked or absent.
    """
    habitat = normalize_habitat(row.get("ecotype", row.get("site_Ecotype")))
    marine = habitat is HabitatDomain.MARINE
    merit = MetricProvenance(
        source_id=str(row.get("merit_dataset") or row.get("merit_hydro_dataset") or "MERIT/Hydro/v1_0_1"),
        source_version="v1_0_1",
        method="Earth Engine point sample",
        spatial_scale_m=_number(row.get("merit_sampling_scale_m") or row.get("merit_hydro_sampling_scale_m")),
    )
    terrain = MetricProvenance(
        source_id="Copernicus DEM GLO-30",
        method="cached 3x3 window",
        spatial_scale_m=30.0,
        retrieved_at_utc=str(row.get("copernicus_retrieval_utc") or "") or None,
        checksum_sha256=str(row.get("copernicus_window_checksum_sha256") or "") or None,
    )
    upa = _number(row.get("merit_upa"))
    terrain_status = row.get("terrain_status") or row.get("topography_status")
    slope = _number(row.get("terrain_slope_degrees") or row.get("topography_slope_degrees"))
    metrics = [
        _metric("local_terrain_elevation_m", _number(row.get("terrain_elevation_m") or row.get("topography_elevation_m")),
                terrain_status, "topography", "m", terrain, not_applicable=marine),
        _metric("local_terrain_slope_deg", slope, terrain_status,
                "topography", "degree", terrain, not_applicable=marine),
        _metric("local_terrain_relief_m", _number(row.get("terrain_local_relief_m") or row.get("topography_local_relief_m")),
                terrain_status, "topography", "m", terrain, not_applicable=marine),
        _metric("upstream_drainage_area_km2", upa, row.get("merit_upa_status"), "hydrology", "km2", merit, not_applicable=marine),
        _metric("height_above_drainage_m", _number(row.get("merit_hnd")), row.get("merit_hnd_status"),
                "hydrology", "m", merit, not_applicable=marine),
        _metric("channel_width_m", _number(row.get("merit_wth")), row.get("merit_wth_status"),
                "hydrodynamics", "m", merit, not_applicable=marine),
        _metric("merit_elevation_m", _number(row.get("merit_elv")), row.get("merit_elv_status"),
                "topography", "m", merit, not_applicable=marine),
        _metric("upstream_drainage_pixels", _number(row.get("merit_upg")), row.get("merit_upg_status"),
                "hydrology", "count", merit, not_applicable=marine),
        _metric("flow_direction_d8", _number(row.get("merit_dir")), row.get("merit_dir_status"),
                "hydrology", "D8 code", merit, not_applicable=marine),
        _metric("water_body_mask", _number(row.get("merit_wat")), row.get("merit_wat_status"),
                "habitat_geometry", "category", merit, not_applicable=marine),
    ]
    log_area = math.log10(1.0 + upa) if upa is not None and upa >= 0 and not marine else None
    metrics.append(_metric(
        "log10_upstream_drainage_area", log_area, row.get("merit_upa_status"),
        "hydrology", "log10(1+km2)", merit, not_applicable=marine,
        diagnostics={"derivation": "log10(1 + upstream_drainage_area_km2)"},
    ))
    gradient = math.tan(math.radians(slope)) if slope is not None and not marine else None
    metrics.append(_metric(
        "local_terrain_gradient", gradient, terrain_status,
        "topography", "rise/run", terrain, not_applicable=marine,
        diagnostics={"derivation": "tan(local_terrain_slope_deg); not channel gradient"},
    ))
    return tuple(metrics)


def flatten_enriched_row(row: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {
        "sample_id": row.get("sample_id"),
        "population_name": row.get("population_name") or row.get("site_Population.name"),
        "population_abbreviation": row.get("population_abbreviation") or row.get("site_population.abbreviation"),
        "latitude": row.get("latitude") or row.get("site_Latitude"),
        "longitude": row.get("longitude") or row.get("site_Longitude"),
        "ecotype": row.get("ecotype") or row.get("site_Ecotype"),
        "habitat_domain": normalize_habitat(row.get("ecotype") or row.get("site_Ecotype")).value,
    }
    for metric in enrich_cached_row(row):
        result.update(metric.as_flat_fields())
    return result


def read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_enriched_csv(rows: Iterable[Mapping[str, object]], path: str | Path) -> Path:
    enriched = [flatten_enriched_row(row) for row in rows]
    if not enriched:
        raise ValueError("cannot write an empty enrichment table")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(enriched[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(enriched)
    return destination
