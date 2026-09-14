"""Versioned catalog of active and candidate global environmental sources.

Catalog entries describe routing and provenance.  They do not authorize a
network request; extraction remains an explicit, bounded operation.
"""
from __future__ import annotations

from dataclasses import dataclass

from .habitats import HabitatDomain, normalize_habitat


@dataclass(frozen=True, slots=True)
class SourceVariable:
    output_name: str
    band: str
    unit: str | None
    ecological_axis: str
    transform: str = "identity"


@dataclass(frozen=True, slots=True)
class SourceSpec:
    source_id: str
    provider: str
    backend: str
    asset_id: str
    resolution_m: float
    habitats: frozenset[HabitatDomain]
    variables: tuple[SourceVariable, ...]
    temporal_support: str
    status: str
    documentation_url: str
    extraction_geometry: str = "point"

    def applies_to(self, habitat: object) -> bool:
        return normalize_habitat(habitat) in self.habitats


FRESH_AND_TRANSITION = frozenset({HabitatDomain.FRESHWATER, HabitatDomain.TRANSITION})
MARINE_AND_TRANSITION = frozenset({HabitatDomain.MARINE, HabitatDomain.TRANSITION})
ALL_KNOWN = frozenset({HabitatDomain.FRESHWATER, HabitatDomain.TRANSITION, HabitatDomain.MARINE})


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "merit_hydro_v1_0_1", "MERIT Hydro", "earth_engine_image",
        "MERIT/Hydro/v1_0_1", 90, FRESH_AND_TRANSITION,
        (
            SourceVariable("merit_elevation_m", "elv", "m", "topography"),
            SourceVariable("upstream_drainage_area_km2", "upa", "km2", "hydrology"),
            SourceVariable("height_above_drainage_m", "hnd", "m", "hydrology"),
            SourceVariable("channel_width_m", "wth", "m", "hydrodynamics"),
            SourceVariable("water_body_mask", "wat", "category", "habitat_geometry"),
        ),
        "static", "active_pilot",
        "https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1",
    ),
    SourceSpec(
        "jrc_global_surface_water_v1_4", "EC JRC / Google", "earth_engine_image",
        "JRC/GSW1_4/GlobalSurfaceWater", 30, FRESH_AND_TRANSITION,
        (
            SourceVariable("surface_water_occurrence_pct", "occurrence", "%", "hydroperiod"),
            SourceVariable("surface_water_seasonality_months", "seasonality", "months", "hydroperiod"),
            SourceVariable("surface_water_recurrence_pct", "recurrence", "%", "hydroperiod"),
        ),
        "1984-2021 summary", "verified_candidate",
        "https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater",
    ),
    SourceSpec(
        "era5_land_monthly", "ECMWF / Copernicus", "earth_engine_collection",
        "ECMWF/ERA5_LAND/MONTHLY_AGGR", 11132, FRESH_AND_TRANSITION,
        (
            SourceVariable("air_temperature_c", "temperature_2m", "degC", "temperature", "kelvin_to_celsius"),
            SourceVariable("precipitation_mm", "total_precipitation_sum", "mm", "freshwater_input", "m_to_mm_nonnegative"),
            SourceVariable("runoff_mm", "runoff_sum", "mm", "flow_regime", "m_to_mm"),
            SourceVariable("lake_mixed_layer_temperature_c", "lake_mix_layer_temperature", "degC", "temperature", "kelvin_to_celsius"),
        ),
        "monthly, 1950-near-real-time", "verified_candidate",
        "https://developers.google.com/earth-engine/datasets/catalog/ECMWF_ERA5_LAND_MONTHLY_AGGR",
    ),
    SourceSpec(
        "noaa_oisst_v2_1", "NOAA", "earth_engine_collection",
        "NOAA/CDR/OISST/V2_1", 27830, MARINE_AND_TRANSITION,
        (
            SourceVariable("sea_surface_temperature_c", "sst", "degC", "temperature", "scale_0.01"),
            SourceVariable("sea_surface_temperature_anomaly_c", "anom", "degC", "temperature", "scale_0.01"),
            SourceVariable("sea_ice_concentration_pct", "ice", "%", "ice_regime", "scale_0.01"),
        ),
        "daily, 1981-present", "verified_candidate",
        "https://developers.google.com/earth-engine/datasets/catalog/NOAA_CDR_OISST_V2_1",
    ),
    SourceSpec(
        "hycom_surface_temperature_salinity", "HYCOM", "earth_engine_collection",
        "HYCOM/sea_temp_salinity", 8905.6, MARINE_AND_TRANSITION,
        (
            SourceVariable("surface_water_temperature_c", "water_temp_0", "degC", "temperature", "scale_0.001_offset_20"),
            SourceVariable("surface_salinity_psu", "salinity_0", "psu", "salinity", "scale_0.001_offset_20"),
        ),
        "daily, 1992-2024 historical series", "verified_candidate",
        "https://developers.google.com/earth-engine/datasets/catalog/HYCOM_sea_temp_salinity",
    ),
    SourceSpec(
        "hycom_surface_velocity", "HYCOM", "earth_engine_collection",
        "HYCOM/sea_water_velocity", 8905.6, MARINE_AND_TRANSITION,
        (
            SourceVariable("surface_current_u_ms", "velocity_u_0", "m/s", "hydrodynamics", "scale_0.001"),
            SourceVariable("surface_current_v_ms", "velocity_v_0", "m/s", "hydrodynamics", "scale_0.001"),
        ),
        "1992-2024 historical series", "verified_candidate",
        "https://developers.google.com/earth-engine/datasets/catalog/HYCOM_sea_water_velocity",
    ),
    SourceSpec(
        "modis_aqua_ocean_color", "NASA Ocean Biology Processing Group", "earth_engine_collection",
        "NASA/OCEANDATA/MODIS-Aqua/L3SMI", 4616, MARINE_AND_TRANSITION,
        (
            SourceVariable("chlorophyll_a_mg_m3", "chlor_a", "mg/m3", "productivity"),
            SourceVariable("particulate_organic_carbon_mg_m3", "poc", "mg/m3", "productivity"),
            SourceVariable("diffuse_attenuation_kd490_m1", "Kd_490", "m-1", "optical_environment"),
            SourceVariable("photosynthetically_available_radiation", "par", "einstein/m2/day", "light_environment"),
        ),
        "daily, 2002-2025 historical series", "verified_candidate",
        "https://developers.google.com/earth-engine/datasets/catalog/NASA_OCEANDATA_MODIS-Aqua_L3SMI",
    ),
    SourceSpec(
        "esa_worldcover_2021_v200", "ESA WorldCover Consortium", "earth_engine_collection",
        "ESA/WorldCover/v200", 10, ALL_KNOWN,
        (SourceVariable("land_cover_class", "Map", "category", "terrestrial_context"),),
        "2021 snapshot", "verified_candidate",
        "https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200",
        extraction_geometry="terrestrial_buffer_or_catchment",
    ),
)


def sources_for_habitat(habitat: object, *, include_active: bool = True,
                        include_candidates: bool = True) -> tuple[SourceSpec, ...]:
    allowed = set()
    if include_active:
        allowed.add("active_pilot")
    if include_candidates:
        allowed.add("verified_candidate")
    return tuple(source for source in SOURCES if source.status in allowed and source.applies_to(habitat))
