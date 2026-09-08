"""Local topographic extraction from a verified cached raster.

The reader protocol is intentionally tiny so tests can use an in-memory fixture
and production can inject rasterio.  Hydrologic operations belong in hydrology.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from .dem_acquisition import RasterMetadata


@dataclass(frozen=True, slots=True)
class TopographyResult:
    elevation_m: float | None
    slope_degrees: float | None
    local_relief_m: float | None
    status: str
    source_path: str | None = None


def extract_window(values: Any, metadata: RasterMetadata, *, source_path: str | None = None) -> TopographyResult:
    """Derive local terrain metrics from a small raster window.

    Invalid, masked, nodata, and configured ocean-zero cells are excluded from
    every metric.  A window with no valid cells is never interpreted as sea
    level.
    """
    array = np.asarray(values, dtype=float)
    valid = np.isfinite(array)
    if metadata.nodata is not None:
        valid &= array != metadata.nodata
    if metadata.zero_is_ocean_nodata:
        valid &= array != 0.0
    if not valid.any():
        return TopographyResult(None, None, None, "no_valid_dem_data", source_path)
    elevation = float(array[valid][array[valid].size // 2])
    valid_values = array[valid]
    relief = float(valid_values.max() - valid_values.min())
    if array.shape[0] < 2 or array.shape[1] < 2 or not np.all(valid):
        slope = None
    else:
        # DEM resolution is approximately square for GLO-30.  This is a
        # bounded local slope estimate; geographic geodesic correction is not
        # needed for this first-pass pilot extraction.
        dz_drow, dz_dcol = np.gradient(array, metadata.resolution_m, metadata.resolution_m)
        slope = float(np.degrees(np.arctan(np.hypot(dz_drow, dz_dcol))).mean())
    return TopographyResult(elevation, slope, relief, "ok", source_path)


class RasterReader(Protocol):
    def sample(self, points: list[tuple[float, float]]) -> Any: ...


def valid_elevation(value: Any, metadata: RasterMetadata) -> float | None:
    """Normalize a cell to None for nodata/ocean; never coerce invalid cells to zero."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or (metadata.nodata is not None and value == metadata.nodata):
        return None
    if metadata.zero_is_ocean_nodata and value == 0.0:
        return None
    return value


def extract_point(reader: RasterReader, metadata: RasterMetadata, latitude: float, longitude: float,
                  *, source_path: str | None = None) -> TopographyResult:
    metadata.validate()
    raw = next(iter(reader.sample([(longitude, latitude)])))
    if hasattr(raw, "__len__") and not isinstance(raw, (str, bytes)):
        raw = raw[0]
    elevation = valid_elevation(raw, metadata)
    return TopographyResult(elevation, None, None, "ok" if elevation is not None else "no_valid_dem_data", source_path)
