"""Local DEM summaries and explicit catchment delineation interface."""
from dataclasses import dataclass
from typing import Any, Callable, Optional
import math

@dataclass(frozen=True)
class TerrainSummary:
    elevation: Optional[float]
    slope: Optional[float]
    aspect: Optional[float]
    status: str
    dem_path: Optional[str] = None
    nodata: Any = None

class CatchmentStatus:
    NOT_REQUESTED = "not_requested"
    NOT_IMPLEMENTED = "delineation_not_implemented"
    NO_DEM_DATA = "no_valid_dem_data"
    MARINE = "not_applicable_marine"
    OK = "ok"

@dataclass(frozen=True)
class CatchmentResult:
    status: str
    outlet_latitude: float
    outlet_longitude: float
    area_km2: Optional[float] = None
    geometry: Any = None
    message: Optional[str] = None

class TerrainExtractor:
    """Sample a local DEM; catchment delineation is deliberately a future interface."""
    def __init__(self, opener: Optional[Callable] = None):
        self.opener = opener

    def summary(self, dem_path: str, latitude: float, longitude: float, *, ecotype: Optional[str] = None) -> TerrainSummary:
        if (ecotype or "").strip().lower() in {"marine", "ocean", "pelagic", "coastal_marine"}:
            return TerrainSummary(None, None, None, "not_applicable_marine", str(dem_path))
        if self.opener is None:
            try:
                import rasterio
                opener = rasterio.open
            except ImportError as exc:
                raise RuntimeError("Terrain extraction requires rasterio; install it or inject opener") from exc
        else:
            opener = self.opener
        try:
            with opener(str(dem_path)) as raster:
                x, y = longitude, latitude
                raw = next(iter(raster.sample([(x, y)])))
                value = raw[0] if hasattr(raw, "__len__") else raw
                nodata = getattr(raster, "nodata", None)
                valid = value is not None and not (isinstance(value, float) and math.isnan(value)) and value != nodata
                return TerrainSummary(float(value) if valid else None, None, None,
                                      "ok" if valid else "no_valid_dem_data", str(dem_path), nodata)
        except (FileNotFoundError, OSError):
            return TerrainSummary(None, None, None, "dem_unavailable", str(dem_path))

    def delineate_catchment(self, latitude: float, longitude: float, *, dem_path: Optional[str] = None) -> CatchmentResult:
        return CatchmentResult(CatchmentStatus.NOT_IMPLEMENTED, float(latitude), float(longitude),
                               message="Catchment delineation is an interface stub; no watershed operation was performed.")
