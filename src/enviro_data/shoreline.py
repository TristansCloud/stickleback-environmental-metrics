"""Exploratory DEM shoreline-buffer elevation; never a depth prediction."""

from __future__ import annotations
import math
import numpy as np
from .river_snapping import number

BUFFERS = (50, 100, 250)


def sample_plan(geometry, surface_count=12, ring_count=20):
    from shapely.geometry import shape, mapping
    from shapely import transform
    from shapely import contains_xy

    water = shape(geometry)
    if (
        not water.is_valid
        or water.is_empty
        or water.geom_type not in {"Polygon", "MultiPolygon"}
    ):
        raise ValueError("valid whole-lake polygon required")
    lon, lat = water.representative_point().coords[0]
    sx = 111195 * math.cos(math.radians(lat))
    sy = 111195

    def forward(coordinates):
        return np.column_stack(
            ((coordinates[:, 0] - lon) * sx, (coordinates[:, 1] - lat) * sy)
        )

    projected = transform(water, forward)
    if (
        projected.bounds[2] - projected.bounds[0] > 200000
        or projected.bounds[3] - projected.bounds[1] > 200000
    ):
        raise ValueError("lake too large for local exploratory projection")

    def points(region, count):
        if region.is_empty:
            return []
        x0, y0, x1, y1 = region.bounds
        xs, ys = np.meshgrid(
            np.linspace(x0, x1, 65)[1:-1], np.linspace(y0, y1, 65)[1:-1]
        )
        mask = contains_xy(region, xs.ravel(), ys.ravel())
        candidates = list(zip(xs.ravel()[mask], ys.ravel()[mask]))
        if not candidates:
            candidates = [region.representative_point().coords[0]]
        indices = np.linspace(
            0, len(candidates) - 1, min(count, len(candidates)), dtype=int
        )
        return [
            [float(candidates[i][0] / sx + lon), float(candidates[i][1] / sy + lat)]
            for i in indices
        ]

    interior = projected.buffer(-90)
    fallback = interior.is_empty
    surface = points(projected if fallback else interior, surface_count)
    result = {"lake_surface": surface}
    previous = projected
    for radius in BUFFERS:
        outer = projected.buffer(radius)
        result[f"shore_{radius}m"] = points(outer.difference(previous), ring_count)
        previous = outer
    return {
        "groups": result,
        "surface_inset_fallback": fallback,
        "buffer_definition": "disjoint land-side distance bands 0-50,50-100,100-250 m; includes island shores",
        "source_resolution_m": 90,
        "method": "deterministic grid samples in local tangent plane; DEM water-surface proxy",
    }


def summarize(plan, elevations):
    groups = plan["groups"]
    offset = 0
    values = {}
    for name, coordinates in groups.items():
        values[name] = [
            number(v) for v in elevations[offset : offset + len(coordinates)]
        ]
        values[name] = [v for v in values[name] if v is not None]
        offset += len(coordinates)
    if offset != len(elevations):
        raise ValueError("shoreline sample count mismatch")
    surface = values["lake_surface"]
    proxy = float(np.median(surface)) if surface else None
    spread = max(surface) - min(surface) if surface else None
    stable = (
        bool(surface)
        and len(surface) >= max(3, math.ceil(len(groups["lake_surface"]) * 0.75))
        and spread <= 5
        and not plan["surface_inset_fallback"]
    )
    result = {
        "status": (
            "exploratory" if stable else "lake_surface_proxy_unstable_or_insufficient"
        ),
        "lake_surface_dem_proxy_m": proxy,
        "lake_surface_dem_range_m": spread,
        "surface_valid_sample_count": len(surface),
        "depth_estimate_m": None,
        "depth_status": "thesis_equation_and_buffer_rule_pending",
        "shoreline_slope_degrees": None,
        "shoreline_slope_status": "not_computed",
        "rings": {},
    }
    for radius in BUFFERS:
        samples = values[f"shore_{radius}m"]
        result["rings"][str(radius)] = {
            "sample_count": len(samples),
            "mean_terrain_elevation_m": float(np.mean(samples)) if samples else None,
            "mean_relative_elevation_m": (
                float(np.mean(samples) - proxy) if stable and samples else None
            ),
            "median_relative_elevation_m": (
                float(np.median(samples) - proxy) if stable and samples else None
            ),
            "p90_relative_elevation_m": (
                float(np.percentile(samples, 90) - proxy)
                if stable and samples
                else None
            ),
            "status": (
                "exploratory_below_source_resolution"
                if stable and radius < 90
                else "exploratory" if stable and samples else "unresolved"
            ),
        }
    return result
